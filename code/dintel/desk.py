"""리서치 데스크 아침 브리프 - 운용역의 '공시 확인 -> 원문 처리 -> 기록' 과정을 대신한다 (2026-10-06 시제품).

python -X utf8 -m dintel.desk                         (데모 관심목록, 로컬 공시 원천의 최근 5거래일)
python -X utf8 -m dintel.desk watch.csv --days 3      (stock_code[,role] CSV - role: 보유/관심)
python -X utf8 -m dintel.desk --date 20261002

입력: 관심·보유 종목 목록. 원천: data/dintel/events_*.csv (scripts/update_events_daily.py가 매일 갱신),
      공급계약 원문은 dintel.contracts가 받아 파싱(캐시).
출력: data/dintel/desk/brief_<date>.md (브리프) + data/dintel/desk/desk_log.csv (처리 기록 - 판단·근거 칸은 운용역이 채움)

원칙(DINTEL_DESIGN.md와 동일): 매수/매도 의견 없음, 실투자 엔진 점수 미사용. 계산된 사실과 과거 기준율만 보여준다.
한계(desk_eval.py 실측): 제목·유형만으로 거르면 큰 변동의 13~35%만 잡힌다 -> 원문 수치 추출 확대가 다음 과제.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dintel import company as DC  # noqa: E402
from dintel import contracts as K  # noqa: E402
from dintel import feed as FD  # noqa: E402

D = os.path.join(ROOT, "data", "dintel")
OUT = os.path.join(D, "desk")
FILES = {"KOSPI": ("events_kospi_full.csv", "events_I_kospi_full.csv"),
         "KOSDAQ": ("events_kosdaq.csv", "events_I_kosdaq.csv")}
TIER = {1: "위험", 2: "주의", 3: "확인", 4: "일상"}


def demo_watchlist(seed=7):
    """데모용 가상 중소형 펀드: 코스닥 25 + 코스피 10 무작위(실제 고객·개인 보유와 무관)."""
    ix = DC.company_index()
    rng = np.random.default_rng(seed)
    out = []
    for mk, n in (("KOSDAQ", 25), ("KOSPI", 10)):
        codes = ix[ix["market"] == mk]["stock_code"].to_numpy()
        out += [{"stock_code": c, "role": "보유" if i < n * 0.6 else "관심"}
                for i, c in enumerate(rng.choice(codes, n, replace=False))]
    return pd.DataFrame(out)


def load_events(start, end):
    fr = []
    for mk, files in FILES.items():
        for f in files:
            p = os.path.join(D, f)
            if os.path.exists(p):
                x = pd.read_csv(p, dtype=str)
                x = x[(x["rcept_dt"] >= start) & (x["rcept_dt"] <= end)]
                fr.append(x.assign(market=mk))
    return pd.concat(fr, ignore_index=True).drop_duplicates("rcept_no") if fr else pd.DataFrame()


def price_line(code, market):
    ix = DC.company_index()
    h = ix[ix["stock_code"] == code]
    if h.empty:
        return ""
    try:
        p = DC.price_block(DC._stock_rows(h["panel"].iloc[0], code), market)
        return (f"종가 {p['close']:,.0f} ({p['last_date']}) | 1개월 {p.get('ret_1m', 0):+.1%} "
                f"(지수 {p.get('idx_1m', 0):+.1%}) | 변동성 {p['vol_60']:.0%}")
    except Exception:
        return ""


def stat_line(it):
    st, pb, oos = it.get("stat"), it.get("placebo") or {}, it.get("oos")
    if not st:
        return "과거 통계 없음(유형 미분류 또는 표본 부족)"
    net = st["d20"] - pb.get("d20", 0.0)
    s = (f"같은 유형 과거 {st['n']:,.0f}건: 발표 {st['ann2']:+.1%}, 20일 {st['d20']:+.1%} "
         f"(위약 차감 {net:+.1%}, 중앙값 {st['d20_med']:+.1%})")
    if oos:
        keep = np.sign(oos.get("eff_tr", 0)) == np.sign(oos.get("eff_te", 0))
        s += f" | 2022년 이후 검증: {'방향 유지' if keep else '방향 바뀜'} ({oos.get('eff_te', 0):+.1%})"
    return s


def contract_line(k):
    if not k:
        return ""
    bits = []
    if k.get("ratio") is not None:
        bits.append(f"매출액 대비 {k['ratio']:.1f}% ({k.get('bucket') or '-'})")
    for key, nm in (("related", "특수관계인"), ("cond", "조건부"), ("sub", "자회사"), ("overseas", "해외")):
        if k.get(key):
            bits.append(nm)
    bs = k.get("bucket_stat")
    if bs:
        bits.append(f"같은 규모 과거 {bs.get('n', 0):.0f}건 20일 {bs.get('d20', 0):+.1%}")
    return "계약 원문: " + ", ".join(bits)


def risk_section(wl):
    """2026-10-08 관심목록의 12개월 재무위험 조기경보(dintel.risk_score - 표본외 검증된 공시 기반 점수).
    매수·매도 의견이 아니라 '다음 12개월 중대 위험 공시 확률'과 그 근거 공시 수."""
    rows = []
    for mk in ("KOSDAQ", "KOSPI"):
        p = os.path.join(D, f"risk_watch_{mk.lower()}.csv")
        if os.path.exists(p):
            r = pd.read_csv(p, dtype={"stock_code": str}, encoding="utf-8-sig")
            r["stock_code"] = r["stock_code"].str.zfill(6)
            rows.append(r.assign(market=mk))
    if not rows:
        return []
    r = pd.concat(rows).merge(wl[["stock_code", "role"]], on="stock_code", how="inner")
    if r.empty:
        return []
    r = r.sort_values("risk_12m", ascending=False)
    hi = r[r["pctile"] >= 0.9]
    L = [f"## 재무위험 조기경보 (관심·보유 {len(r)}종목, 기준 {str(r['asof'].iloc[0])[:10]})", "",
         f"- 시장 상위 10%(경고): {len(hi)}종목. 검증(2022~) 기준 상위 10%의 다음 12개월 중대 위험 공시 발생률은 "
         "코스닥 19.6%(평균 6.1%의 3.2배), 코스피 10.8%(평균 5.0%의 2.2배).", ""]
    if len(hi):
        L += ["| 종목 | 시장 | 구분 | 12개월 위험 추정 | 시장 내 백분위 | 근거(직전 12개월 공시 수) |", "|---|---|---|---|---|---|"]
        for _, x in hi.iterrows():
            L.append(f"| {x['corp_name']}({x['stock_code']}) | {x['market']} | {x['role']} | {x['risk_12m']:.1%} | "
                     f"{x['pctile']:.0%} | {x['drivers'] if isinstance(x['drivers'], str) and x['drivers'] else '-'} |")
        L.append("")
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("watchlist", nargs="?")
    ap.add_argument("--date")
    ap.add_argument("--days", type=int, default=5)
    a = ap.parse_args()
    wl = pd.read_csv(a.watchlist, dtype=str) if a.watchlist else demo_watchlist()
    wl["stock_code"] = wl["stock_code"].str.zfill(6)
    wl["role"] = wl.get("role", pd.Series("관심", index=wl.index)).fillna("관심")
    ix = DC.company_index()
    wl = wl.merge(ix[["stock_code", "corp_code", "corp_name", "market"]], on="stock_code", how="left")

    allev = load_events("00000000", "99999999")
    end = a.date or allev["rcept_dt"].max()
    days = sorted(allev.loc[allev["rcept_dt"] <= end, "rcept_dt"].unique())[-a.days:]
    ev = allev[allev["rcept_dt"].isin(days)]
    ev = ev.merge(wl[["corp_code", "stock_code", "corp_name", "role"]], on="corp_code", how="inner")
    stats = DC.load_all_stats()
    items = []
    for mk in ("KOSPI", "KOSDAQ"):
        part = ev[ev["market"] == mk].to_dict("records")
        items += [{**x, "market": mk} for x in DC.annotate(part, mk, stats)]
    for it in items:
        if not it["amendment"] and K.kind_of(it["report_nm"]):
            info = K.annotate_item(it["rcept_no"], it["market"], it["report_nm"])
            if info:
                it["contract"] = info
        FD.classify(it)
    items.sort(key=lambda x: (x["tier"], x["role"] != "보유", x["rcept_dt"], x["corp_name"]))

    n_all = len(allev[allev["rcept_dt"].isin(days)])
    read = [x for x in items if x["tier"] <= 3]
    skip = [x for x in items if x["tier"] == 4]
    L = [f"# 리서치 데스크 아침 브리프 ({days[0]}~{days[-1]})", "",
         f"- 관심·보유 {len(wl)}종목 | 같은 기간 시장 전체 공시 {n_all:,}건 중 해당 종목 {len(items)}건",
         f"- 처리 결과: 확인 필요 {len(read)}건 (위험 {sum(x['tier'] == 1 for x in items)}, "
         f"주의 {sum(x['tier'] == 2 for x in items)}) / 일상 {len(skip)}건은 목록만",
         "- 매수·매도 의견이 아니라 공개 데이터의 처리 결과와 과거 기준율입니다.", ""]
    L += risk_section(wl)
    for x in read:
        L += [f"## [{TIER[x['tier']]}] {x['corp_name']} ({x['stock_code']}, {x['market']}, {x['role']}) - {x['rcept_dt']}",
              f"- 공시: {x['report_nm'].strip()} [원문]({x['url']})",
              f"- {stat_line(x)}"]
        if x.get("risk_tags"):
            L.append(f"- 위험 키워드: {', '.join(x['risk_tags'])}")
        if x.get("contract"):
            L.append(f"- {contract_line(x['contract'])}")
        pl = price_line(x["stock_code"], x["market"])
        if pl:
            L.append(f"- 주가: {pl}")
        L += ["- 판단: ____ / 근거: ____ (운용역 기록)", ""]
    if skip:
        L += ["## 일상 공시 (과거 반응이 의미 없던 유형)", ""]
        L += [f"- {x['rcept_dt']} {x['corp_name']} - {x['report_nm'].strip()}" for x in skip]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"brief_{days[-1]}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    log = pd.DataFrame([{"processed_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"), "rcept_dt": x["rcept_dt"],
                         "rcept_no": x["rcept_no"], "stock_code": x["stock_code"], "corp_name": x["corp_name"],
                         "role": x["role"], "tier": x["tier"], "report_nm": x["report_nm"].strip(),
                         "decision": "", "reason": ""} for x in items])
    lp = os.path.join(OUT, "desk_log.csv")
    log.to_csv(lp, mode="a", header=not os.path.exists(lp), index=False, encoding="utf-8-sig")
    print(f"{path} | items {len(items)} (read {len(read)}, routine {len(skip)}) of market {n_all:,}")


if __name__ == "__main__":
    main()

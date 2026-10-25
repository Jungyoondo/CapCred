"""정보공개서 정기변경 보조 리포트 (2026-10-25, 사업 재설계 2단계 시제품 - docs/business/BUSINESS_REBOOT_2026-10-25.md).

python -X utf8 -m caed.fdd_agent <브랜드> [--code 072405|072404] [--fy 2025]   # -> data/caed/agent/<브랜드>_FY<연도>.md (로컬 전용)
python -X utf8 -m caed.fdd_agent --top 2                                        # 카페·음식점에서 서울 매장이 많은 공정위 등록 브랜드 각 N개

누가 쓰나: 가맹거래사(검토·서명·제출은 자격자 - 법제처 17-0355: 정보공개서 작성 자문·등록 대행은 등록 가맹거래사 업무)와,
  자기 정보공개서를 직접 고치는 가맹본부. 이 도구는 공공 기록으로 초안 재료를 모으고 대조 목록을 만드는 데까지만 한다.
하는 일:
  1) 마감일(회계년도 말 + 120일, 재무제표 작성 개인사업자 180일)
  2) 공정위 등록 이력(브랜드 목록 API)
  3) 서울 매장 변동(인허가 실측): 신규·폐업, 같은 자리(10m)·-30~+180일 같은 브랜드 재개업은 '명의변경 추정'으로 분리(H-2026-10-Z 정의)
  4b) 같은 업종 전국 기준선(공정위 업종별 개폐점률 15157660) - 서울 실측은 참고(H-2026-10-AE)
  3b) 공정위 신고 지역별 매장 수(data.go.kr 15125490) + 올해 서울 예상값·변동 경보(작년 신고 x (1 + 인허가 증감률), H-2026-10-AC 성립:
      오차 -16.8%, 경보 정밀도 83.2%)
  4) 2028-01-01 시행 신설 항목(장기운영 비율·1/3년 생존율·폐점 평균 영업기간) 사전 계산 - caed.survival_audit 정의, 업종 가맹 평균과 비교
  5) 대조 체크리스트
한계: 서울만 · 상호 기반 브랜드 추정 · 인허가 기준(본사 계약 기준과 다를 수 있음). 결과물은 브랜드 이름이 들어가므로 로컬 전용.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import brand_health as BH  # noqa: E402
from caed import franchise_survival as FS  # noqa: E402
from caed import ftc_brands as F  # noqa: E402
from caed import survival_audit as SA  # noqa: E402

OUT = os.path.join(ROOT, "data", "caed", "agent")
LABEL = {"072405": "카페·휴게", "072404": "일반음식점"}


def stores(code):
    FS.CODE, FS.UPTAE = code, None
    g = FS.load()
    g["brand_raw"] = BH.merge_variants(g["brand_raw"])
    return g


def transfers(b):
    """같은 브랜드 안에서 폐업 뒤 10m 안 -30~+180일 재개업 쌍 -> (폐업 행, 재개업 행) 인덱스 집합."""
    from scipy.spatial import cKDTree
    ok = b["x"].notna() & b["y"].notna()
    if ok.sum() < 2:
        return set(), set()
    pos = np.flatnonzero(ok.to_numpy())
    tree = cKDTree(b.loc[ok, ["x", "y"]].to_numpy())
    closed, reopened = set(), set()
    cl = np.flatnonzero((b["failed"] & b["close"].notna() & ok).to_numpy())
    opn = b["open"].to_numpy()
    for i, near in zip(cl, tree.query_ball_point(b.iloc[cl][["x", "y"]].to_numpy(), r=10.0)):
        j = pos[near]
        j = j[j != i]
        d = (opn[j] - b["close"].to_numpy()[i]) / np.timedelta64(1, "D")
        hit = j[(d >= -30) & (d <= 180)]
        if len(hit):
            closed.add(b.index[i])
            reopened.add(b.index[hit[0]])
    return closed, reopened


def disclosed(mnnos):
    """공정위 신고 지역별 가맹점+직영점 수 - (회계년도 x 지역) 표. 같은 회계년도는 가장 늦은 기준년도 값."""
    from caed import ftc_frcs as FF
    fs = [os.path.join(FF.OUT, f"frcs_{y}.csv") for y in FF.YEARS]
    d = pd.concat([pd.read_csv(f, dtype=str, keep_default_na=False) for f in fs if os.path.exists(f)], ignore_index=True)
    d = d[d["brandMnno"].isin(mnnos)].copy()
    if d.empty:
        return None
    d["n"] = pd.to_numeric(d["frcsCnt"], errors="coerce").fillna(0) + pd.to_numeric(d["dmsCnt"], errors="coerce").fillna(0)
    d["fy"] = pd.to_numeric(d["acntgYr"], errors="coerce")
    d = d.sort_values("jngBizCrtraYr").drop_duplicates(["brandMnno", "fy", "areaNm"], keep="last")
    return d.pivot_table(index="fy", columns="areaNm", values="n", aggfunc="sum").fillna(0)


def industry_baseline(hist, fy, n_closed, n_start):
    """4b절 - 공정위 업종별 가맹점 수·개폐점률(data.go.kr 15157660)에서 이 브랜드 업종 중분류의 최근 3개 회계년도.
    서울 실측 폐점률은 참고로만 붙인다(H-2026-10-AE: 업종 사이 폐점률 순위는 기각, 추세 방향은 일치)."""
    p = os.path.join(ROOT, "data", "caed", "ftc", "induty_opcl.csv")
    if not os.path.exists(p) or not len(hist):
        return []
    c = hist.sort_values("yr")["indutyMlsfcNm"].iloc[-1]
    n = pd.read_csv(p).sort_values("jngBizCrtrYr").drop_duplicates(["acntgYr", "tpbizMclsfNm"], keep="last")
    n = n[n["tpbizMclsfNm"] == c].sort_values("acntgYr").tail(3)
    if n.empty:
        return [f"## 4b. 같은 업종 전국 기준선", f"- 공정위 업종별 표에 '{c}' 중분류가 없습니다(주요 업종만 제공).", ""]
    rows = [f"| {int(r.acntgYr)} | {int(r.frcsCnt):,} | {r.newFrcsRt:.1f}% | {r.endCncltnRt:.1f}% |" for r in n.itertuples()]
    own = f"{n_closed / n_start:.1%}" if n_start else "-"
    return [f"## 4b. 같은 업종 전국 기준선 — {c} (공정위 업종별 가맹점 수·개폐점률)",
            "| 회계년도 | 전국 가맹점 수 | 신규 비율 | 종료(해지) 비율 |", "|---|---|---|---|", *rows, "",
            f"- 참고: 이 브랜드의 {fy}년 서울 인허가 폐업 비율 {own}(폐업 {n_closed} / 연초 {n_start}, 명의변경 추정 제외). "
            "서울 실측과 전국 비율은 업종 사이 수준이 달라(H-2026-10-AE 폐점률 순위 기각) 직접 비교하지 말고 추세만 본다.", ""]


def survival_items(g, asof):
    """caed.survival_audit 정의 그대로 - g 전체를 '가맹'으로 본 한 묶음."""
    r = SA.measure(g.assign(brand_raw=g["brand_raw"].fillna("_")), asof)["franchise"]
    return r


def report(brand, code, fy, g=None):
    g = stores(code) if g is None else g
    b = g[g["brand_raw"] == brand].copy()
    if b.empty:
        sys.exit(f"'{brand}' not found in Seoul permits ({LABEL[code]})")
    t0, t1 = pd.Timestamp(f"{fy - 1}-12-31"), pd.Timestamp(f"{fy}-12-31")
    alive = lambda t: (b["open"] <= t) & ~(b["gone"] & (b["close"] <= t))  # noqa: E731
    new = b[(b["open"] > t0) & (b["open"] <= t1)]
    end = b[b["failed"] & (b["close"] > t0) & (b["close"] <= t1)]
    tc, tr = transfers(b)
    end_t, new_t = end[end.index.isin(tc)], new[new.index.isin(tr)]
    end_x, new_x = end[~end.index.isin(tc)], new[~new.index.isin(tr)]
    ftc = F.load()
    nb = F.norm(brand)
    fk = F.match({nb}, set(ftc["key"])).get(nb)
    # 등록 이름이 해마다 조금씩 다를 수 있어(예: 영문·한글 병기) 앞부분이 겹치는 이름을 함께 보여 준다 - 브랜드관리번호로 확정할 것
    near = {k for k in set(ftc["key"]) if len(k) >= 3 and (k == nb or k.startswith(nb) or nb.startswith(k))}
    hist = ftc[ftc["key"].isin(near)].sort_values(["yr", "brandNm"]) if near else ftc.iloc[0:0]
    own = survival_items(b, t1)
    ind = survival_items(g[g["brand_raw"].notna()], t1)
    pc = lambda v: "-" if v is None or pd.isna(v) else f"{v:.1%}"  # noqa: E731
    yr = lambda v: "-" if v is None or pd.isna(v) else f"{v:.1f}년"  # noqa: E731
    deadline = (t1 + pd.Timedelta(days=120)).date()
    L = [f"# 정보공개서 정기변경 보조 리포트 — {brand} · 회계년도 {fy}",
         "",
         "> 가맹거래사·가맹본부 검토용 초안 재료입니다. 정보공개서 작성 자문·등록 대행이 아니며, 숫자는 서울 인허가 공공 기록 기준입니다(본사 계약 기준과 다를 수 있음).",
         "",
         "## 1. 마감",
         f"- 정기변경 등록 기한: **{deadline}** (회계년도 말 + 120일. 재무제표를 작성하는 개인사업자 본부는 +180일). 기한을 넘기거나 거짓으로 등록하면 최대 1천만 원 과태료.",
         "",
         "## 2. 공정위 등록 이력 (정보공개서 브랜드 목록)",
         ("| 기준년도 | 등록 브랜드명 | 브랜드관리번호 | 본부 | 업종 | 가맹사업 개시일 |\n|---|---|---|---|---|---|\n" + "\n".join(
             f"| {r['yr']} | {r['brandNm']} | {r['brandMnno']} | {r['corpNm']} | {r['indutyMlsfcNm']} | {r['jngBizStrtDate']} |"
             for _, r in hist.head(40).iterrows()))
         if len(hist) else "- 이름이 맞는 등록 브랜드를 찾지 못했습니다(상호 표기 차이 가능 - 브랜드관리번호로 직접 지정 필요).",
         "",
         f"## 3. 서울 매장 변동 ({fy}년, 인허가 실측)",
         "| 항목 | 수 |", "|---|---|",
         f"| 연초 영업 중 | {int(alive(t0).sum())} |",
         f"| 신규 개업 | {len(new_x)} |",
         f"| 폐업(계약 종료·해지 후보) | {len(end_x)} |",
         f"| 명의변경 추정(같은 자리 폐업 → 180일 안 같은 브랜드 재개업) | {len(end_t)} 건 (재개업 {len(new_t)}) |",
         f"| 연말 영업 중 | {int(alive(t1).sum())} |",
         "",
         "정보공개서 가맹점 현황은 신규·계약종료·계약해지·명의변경을 나눠 적는다. 인허가 대장은 명의변경을 '폐업 + 신규'로 남기는 경우가 많아, 같은 자리 재개업을 따로 묶었다.",
         "",
         "### 3-1. 명세 (본사 가맹점 명단과 대조할 것)"]
    for nm, s, col in (("신규 개업", new_x, "open"), ("폐업", end_x, "close"), ("명의변경 추정(폐업 쪽)", end_t, "close")):
        L += [f"**{nm} {len(s)}**", "", "| 상호 | 구 | 주소 | 개업일 | 폐업일 |", "|---|---|---|---|---|"]
        day = lambda v: "" if pd.isna(v) else f"{v:%Y-%m-%d}"  # noqa: E731
        L += [f"| {r['name']} | {r['gu'] or ''} | {r['addr'] or ''} | {day(r['open'])} | {day(r['close'])} |"
              for _, r in s.sort_values(col).head(60).iterrows()]
        if len(s) > 60:
            L.append(f"| … 외 {len(s) - 60}건 | | | | |")
        L.append("")
    # 지역별 매장 수는 정확히 맞는 등록 이름의 브랜드관리번호만 쓴다(앞부분만 겹치는 다른 브랜드를 더하지 않게)
    mn = set(hist.loc[hist["key"] == fk, "brandMnno"]) if fk else set()
    D = disclosed(mn) if mn else None
    m0, m1 = int(alive(t0).sum()), int(alive(t1).sum())
    L += [f"## 3b. 공정위 신고 매장 수와 올해 서울 예상값", ""]
    if D is None or "서울" not in D.columns or (fy - 1) not in D.index:
        L += [f"- 공정위 지역별 매장 수에서 {fy - 1}년 신고를 찾지 못했습니다(브랜드관리번호 확인 필요). 예상값은 만들지 않습니다.", ""]
        est = None
    else:
        top = [c for c in ("전체", "서울", "경기", "인천", "부산") if c in D.columns]
        L += ["| 회계년도 | " + " | ".join(top) + " |", "|---" * (len(top) + 1) + "|"]
        L += [f"| {int(y)} | " + " | ".join(f"{int(D.at[y, c])}" for c in top) + " |" for y in D.index[-5:]]
        f0 = float(D.at[fy - 1, "서울"])
        est = f0 * (1 + (m1 - m0) / max(m0, 5))
        alert = abs(est - f0) >= max(3, 0.1 * f0)
        L += ["", f"- 작년({fy - 1}) 신고 서울 매장 **{int(f0)}곳** · 인허가 실측 {m0} → {m1} ({m1 - m0:+d})",
              f"- 올해({fy}) 서울 예상값: **{est:.0f}곳** = 작년 신고 x (1 + 실측 증감률). "
              f"{'**변동 경보**: 신고 숫자가 ' + ('늘었을' if est > f0 else '줄었을') + ' 가능성이 높습니다 - 명단을 우선 대조하세요.' if alert else '경보 없음(변동 작음).'}",
              "- 근거: H-2026-10-AC 사전 등록 검정(외식 879개 브랜드, 2019~2025). 작년 숫자를 그대로 쓰는 것보다 오차가 16.8% 작고, 경보의 83.2%가 실제 같은 방향으로 바뀌었다. "
              "인허가 실측은 신고 매장의 중앙값 68%만 잡으므로(H-2026-10-AB2) 실측 숫자 자체를 신고값으로 쓰지 않는다.",
              ""]
    L += [f"## 4. 2028-01-01 시행 신설 항목 사전 계산 ({fy}년 말 기준, 서울 실측 근사)",
          "| 항목 | 이 브랜드 | 같은 업종 가맹 전체 |", "|---|---|---|",
          f"| 장기운영 비율(영업 중 5년+) | {pc(own['long5'])} | {pc(ind['long5'])} |",
          f"| 1년 생존율 (코호트 n) | {pc(own['surv1'])} (n={own['n1']}) | {pc(ind['surv1'])} |",
          f"| 3년 생존율 (코호트 n) | {pc(own['surv3'])} (n={own['n3']}) | {pc(ind['surv3'])} |",
          f"| 폐점 평균 영업기간 (최근 1년 폐점 n) | {yr(own['closed_avg_years'])} (n={own['n_closed']}) | {yr(ind['closed_avg_years'])} |",
          "",
          "정의는 공정위 세부 산식 고시 전 우리 근사(caed/survival_audit.py). 코호트 10곳 미만이면 '-'. 생존율은 명의변경을 폐업으로 셀 수 있어 낮게 나올 수 있다.",
          "",
          *industry_baseline(hist, fy, len(end_x), int(alive(t0).sum())),
          "## 5. 대조 체크리스트",
          f"- [ ] 본사 가맹점 명단의 {fy}년 신규·종료·해지와 3-1 명세를 대조한다(서울).",
          f"- [ ] 명의변경 추정 {len(end_t)}건이 실제 양도인지 확인한다(정보공개서에는 명의변경으로 적는다).",
          "- [ ] 인허가에는 있는데 본사 명단에 없는 매장(상호만 같은 독립 가게일 수 있음)을 걸러낸다.",
          "- [ ] 3b 예상값과 본사 집계 서울 매장 수가 크게 다르면(경보 기준: 3곳 또는 10% 이상) 그 차이의 매장을 찾는다.",
          "- [ ] 2028년 신설 항목: 위 4절 값과 본사 내부 계산이 크게 다르면 정의 차이를 메모해 둔다.",
          "",
          f"_만든 날 {pd.Timestamp.now():%Y-%m-%d} · caed/fdd_agent.py · 서울 인허가 {LABEL[code]} · 상호 기반 브랜드 추정_"]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{F.norm(brand)}_FY{fy}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return path, {"brand": brand, "code": code, "fy": fy, "start": int(alive(t0).sum()), "new": len(new_x), "closed": len(end_x),
                  "transfer": len(end_t), "end": m1, "registered": fk is not None, "est_seoul": None if est is None else round(est)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("brand", nargs="?")
    ap.add_argument("--code", default="072405", choices=list(LABEL))
    ap.add_argument("--fy", type=int, default=pd.Timestamp.now().year - 1)
    ap.add_argument("--top", type=int, default=0)
    a = ap.parse_args()
    if a.top:
        keys = set(F.load()["key"])
        for code in LABEL:
            g = stores(code)
            cnt = g.loc[(g["open"] <= pd.Timestamp(f"{a.fy}-12-31")) & ~(g["gone"] & (g["close"] <= pd.Timestamp(f"{a.fy}-12-31"))), "brand_raw"].value_counts()
            picks = [b for b in cnt.index if F.norm(b) in keys][:a.top]
            for b in picks:
                print(report(b, code, a.fy, g))
        return
    print(report(a.brand, a.code, a.fy))


if __name__ == "__main__":
    main()

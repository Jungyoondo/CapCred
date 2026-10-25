"""공정위 정보공개서 브랜드별 지역 매장 수 vs 서울 인허가 실측 (2026-10-25, H-2026-10-AB).

python -X utf8 -m caed.ftc_frcs fetch    # -> data/caed/ftc/frcs_<기준년도>.csv (data.go.kr 15125490 활용신청 필요)
python -X utf8 -m caed.ftc_frcs test     # AB1~AB3 -> data/caed/FTC_FRCS.txt, ftc_frcs.json
python -X utf8 -m caed.ftc_frcs test --v2  # H-2026-10-AB2 엄격 매칭(외식·이름 정확 일치) -> FTC_FRCS.txt, ftc_frcs_v2.json
python -X utf8 -m caed.ftc_frcs prefill  # H-2026-10-AC 에이전트 사전 채움(작년 신고 x 실측 증감률) vs 작년 복사 -> FTC_FRCS.txt, ftc_frcs_prefill.json

출처: data.go.kr 15125490 '공정거래위원회_가맹정보_브랜드 가맹점 및 직영점정보 제공 서비스'
  getbrandFrcsDmsstus2 - 기준년도·브랜드관리번호·회계년도·업종·지역명·가맹점수·직영점수·전체가맹점직영점수.
왜: 사업 1단계(docs/business/BUSINESS_REBOOT_2026-10-25.md)는 본사 신고와 인허가 실측을 나란히 보여 준다.
  먼저 둘이 같은 것을 재는지(AB1·AB3), 그다음 실측이 신고보다 먼저 방향을 바꾸는지(AB2)를 사전 등록 기준으로 본다.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import ftc_brands as F  # noqa: E402

OUT = F.OUT
TXT = os.path.join(ROOT, "data", "caed", "FTC_FRCS.txt")
JSN = os.path.join(ROOT, "data", "caed", "ftc_frcs.json")
URL = "https://apis.data.go.kr/1130000/FftcBrandFrcsDropInfo3_Service/getbrandFrcsDmsstus2"
YEARS = range(2019, 2027)
MIN_STORES = 10


def fetch():
    import requests
    key = F._key()
    os.makedirs(OUT, exist_ok=True)
    for y in YEARS:
        path = os.path.join(OUT, f"frcs_{y}.csv")
        if os.path.exists(path) and y < 2026:
            continue
        rows, page = [], 1
        while True:
            r = None
            for _ in range(5):
                try:
                    r = requests.get(URL, params={"serviceKey": key, "pageNo": page, "numOfRows": 1000, "resultType": "json",
                                                  "jngBizCrtraYr": str(y)}, timeout=60).json()
                    break
                except Exception:  # noqa: BLE001 - 일시 오류 재시도
                    continue
            if r is None or "items" not in r:
                sys.exit(f"ftc frcs {y}: unexpected response {str(r)[:200]} (data.go.kr 15125490 활용신청 확인)")
            items = r.get("items") or []
            items = items.get("item", items) if isinstance(items, dict) else items
            rows += items if isinstance(items, list) else [items]
            if len(rows) >= int(r.get("totalCount", 0)) or not items:
                break
            page += 1
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")
        print(f"ftc frcs {y}: {len(rows):,} rows")


def load():
    fs = [pd.read_csv(os.path.join(OUT, f"frcs_{y}.csv"), dtype=str, keep_default_na=False)
          for y in YEARS if os.path.exists(os.path.join(OUT, f"frcs_{y}.csv"))]
    if not fs:
        sys.exit("no frcs_*.csv - run fetch first")
    d = pd.concat(fs, ignore_index=True)
    # 10-25 밤: '전체' 합계가 0인 행은 그해 신고가 비어 있는 것(미제출·미갱신)으로 본다 - tot으로 넘겨 진단·화면에서 '미공개'로 처리
    t = d[d["areaNm"] == "전체"].assign(tot=lambda x: pd.to_numeric(x["allFrcsDmsCnt"], errors="coerce").fillna(0))
    t = t.sort_values("jngBizCrtraYr").drop_duplicates(["brandMnno", "acntgYr"], keep="last")[["brandMnno", "acntgYr", "tot"]]
    d = d[d["areaNm"].str.contains("서울")].copy().merge(t, on=["brandMnno", "acntgYr"], how="left")
    for c in ("frcsCnt", "dmsCnt"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["fy"] = pd.to_numeric(d["acntgYr"], errors="coerce")
    d["n_fdd"] = d["frcsCnt"] + d["dmsCnt"]
    # 같은 회계년도가 여러 기준년도에 실리면 가장 늦은 기준년도(최신 등록)를 쓴다
    d = d.sort_values("jngBizCrtraYr").drop_duplicates(["brandMnno", "fy"], keep="last")
    return d[["brandMnno", "fy", "n_fdd", "indutyLclasNm", "tot"]]


def measured(code, asof_list):
    """서울 인허가 상호 브랜드별 영업 중 매장 수 - 날짜마다 한 열."""
    from caed import brand_health as BH
    from caed import franchise_survival as FS
    FS.CODE, FS.UPTAE = code, None
    g = FS.load()
    g["brand_raw"] = BH.merge_variants(g["brand_raw"])
    out = {}
    for t in asof_list:
        alive = (g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))
        out[t] = g.loc[alive, "brand_raw"].value_counts()
    return pd.DataFrame(out).fillna(0)


def test(strict=False):
    """strict = H-2026-10-AB2(v2): 외식 브랜드만, 정규화 이름이 정확히 같은 것만 매칭. 나머지는 v1과 같다."""
    fdd = load()
    if strict:
        fdd = fdd[fdd["indutyLclasNm"] == "외식"]
    names = F.load()[["brandMnno", "key"]].drop_duplicates("brandMnno")
    fdd = fdd.merge(names, on="brandMnno", how="left")
    fys = sorted(int(x) for x in fdd["fy"].dropna().unique())
    last = pd.Timestamp.now().normalize() - pd.offsets.MonthEnd(1)
    dates = [pd.Timestamp(f"{y}-12-31") for y in fys] + [last, last - pd.DateOffset(years=1)]
    M = pd.concat([measured(c, dates) for c in ("072405", "072404")]).groupby(level=0).sum()
    fkeys = set(fdd["key"].dropna())
    m = {b: F.norm(b) for b in M.index if F.norm(b) in fkeys} if strict else F.match(set(M.index), fkeys)
    M = M[M.index.isin(list(m))].copy()
    M["key"] = M.index.map(m)
    M = M.groupby("key").sum()
    rows = []
    for _, r in fdd.dropna(subset=["key", "fy"]).iterrows():
        t = pd.Timestamp(f"{int(r['fy'])}-12-31")
        if r["key"] in M.index and t in M.columns:
            rows.append({"key": r["key"], "fy": int(r["fy"]), "n_fdd": r["n_fdd"], "n_meas": M.at[r["key"], t], "tot": r["tot"]})
    P = pd.DataFrame(rows)
    keep = P.groupby("key")[["n_fdd", "n_meas"]].max().max(axis=1) >= MIN_STORES
    P = P[P["key"].isin(keep[keep].index)].sort_values(["key", "fy"])
    ab1 = float(P[["n_fdd", "n_meas"]].corr(method="spearman").iloc[0, 1])
    P["d_fdd"] = P.groupby("key")["n_fdd"].diff()
    P["d_meas"] = P.groupby("key")["n_meas"].diff()
    D = P.dropna(subset=["d_fdd", "d_meas"])
    ab3 = float(D[["d_fdd", "d_meas"]].corr(method="spearman").iloc[0, 1]) if len(D) > 10 else float("nan")
    # AB2: 브랜드별 가장 최근 신고 증감 vs 실측 최근 12개월 증감
    latest = D.sort_values("fy").groupby("key").tail(1).set_index("key")
    rec = (M[last] - M[last - pd.DateOffset(years=1)]).reindex(latest.index)
    base = M[last].reindex(latest.index).replace(0, np.nan)
    flip = (np.sign(rec) * np.sign(latest["d_fdd"]) < 0) & (rec.abs() >= 0.1 * base)
    ab2 = float(flip.mean()) if len(latest) else float("nan")
    v = {"AB1": ab1 >= 0.8, "AB3": ab3 >= 0.5, "AB2": ab2 >= 0.10}
    verdict = "측정 불충분 - AB2 보류" if not (v["AB1"] and v["AB3"]) else ("1단계 문구 사용" if v["AB2"] else "'1년 늦다'는 쓰지 않음")
    L = [f"\n##### H-2026-10-AB{'2 (v2 엄격 매칭)' if strict else ''} 정보공개서 서울 매장 수 vs 인허가 실측 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 회계년도 {fys[0]}~{fys[-1]} | 실측 마지막 {last:%Y-%m}",
         f"  대상 브랜드 {P['key'].nunique()}개(매칭 + 서울 {MIN_STORES}곳+), 브랜드-연 {len(P):,}",
         f"  AB1 매장 수 순위상관 {ab1:.2f} (>=0.8) -> {'성립' if v['AB1'] else '기각'}",
         f"  AB3 같은 해 증감 순위상관 {ab3:.2f} (>=0.5, n {len(D):,}) -> {'성립' if v['AB3'] else '기각'}",
         f"  AB2 최근 신고 증감과 실측 최근 12개월 증감이 반대(실측 10%+) {ab2:.1%} ({int(flip.sum())}/{len(latest)}) (>=10%) -> {'성립' if v['AB2'] else '기각'}",
         f"  판정: {verdict}"]
    Q = P[P["tot"] > 0]   # 진단(판정 아님): '전체' 합계 0인 빈 신고 제외
    ratio = (Q["n_meas"] / Q["n_fdd"].where(Q["n_fdd"] > 0)).median()
    L.append(f"  진단(판정 아님, 빈 신고 {len(P) - len(Q):,}건 제외): AB1 {Q[['n_fdd', 'n_meas']].corr(method='spearman').iloc[0, 1]:.2f}, 실측/신고 중앙값 {ratio:.2f}")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN.replace(".json", "_v2.json") if strict else JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "AB1": ab1, "AB3": ab3, "AB2": ab2, "verdict": verdict,
                   "n_brands": int(P["key"].nunique()), "flip_brands": sorted(flip[flip].index.tolist())}, fh, ensure_ascii=False, indent=1)


def prefill():
    """H-2026-10-AC: 작년 신고 x (1 + 실측 증감률)이 '작년 신고 복사'보다 올해 신고에 가까운가. AB2(v2) 매칭 그대로."""
    fdd = load()
    fdd = fdd[fdd["indutyLclasNm"] == "외식"]
    fdd = fdd.merge(F.load()[["brandMnno", "key"]].drop_duplicates("brandMnno"), on="brandMnno", how="left").dropna(subset=["key", "fy"])
    fys = sorted(int(x) for x in fdd["fy"].unique())
    dates = [pd.Timestamp(f"{y}-12-31") for y in range(fys[0] - 1, fys[-1] + 1)]
    M = pd.concat([measured(c, dates) for c in ("072405", "072404")]).groupby(level=0).sum()
    fkeys = set(fdd["key"])
    m = {b: F.norm(b) for b in M.index if F.norm(b) in fkeys}
    M = M[M.index.isin(list(m))].copy()
    M["key"] = M.index.map(m)
    M = M.groupby("key").sum()
    P = fdd.groupby(["key", "fy"]).agg(n_fdd=("n_fdd", "sum"), tot=("tot", "sum")).reset_index()
    P["fy"] = P["fy"].astype(int)
    P = P[P["key"].isin(M.index)]
    P["F0"] = P.groupby("key")["n_fdd"].shift()
    P["fy0"] = P.groupby("key")["fy"].shift()
    P = P[(P["fy0"] == P["fy"] - 1) & (P["F0"] >= MIN_STORES)].copy()
    P["M1"] = [M.at[k, pd.Timestamp(f"{y}-12-31")] for k, y in zip(P["key"], P["fy"])]
    P["M0"] = [M.at[k, pd.Timestamp(f"{y - 1}-12-31")] for k, y in zip(P["key"], P["fy"])]
    g = (P["M1"] - P["M0"]) / np.maximum(P["M0"], 5)
    P["P1"] = P["F0"] * (1 + g)
    e0, e1 = (P["n_fdd"] - P["F0"]).abs(), (P["n_fdd"] - P["P1"]).abs()
    mae0, mae1 = float(e0.mean()), float(e1.mean())
    ch = (P["n_fdd"] != P["F0"]) & (P["M1"] != P["M0"])
    hit = float((np.sign(P.loc[ch, "n_fdd"] - P.loc[ch, "F0"]) == np.sign(P.loc[ch, "M1"] - P.loc[ch, "M0"])).mean())
    al = (P["P1"] - P["F0"]).abs() >= np.maximum(3, 0.1 * P["F0"])
    prec = float((np.sign(P.loc[al, "n_fdd"] - P.loc[al, "F0"]) == np.sign(P.loc[al, "P1"] - P.loc[al, "F0"])).mean())
    v = {"AC1": mae1 <= 0.9 * mae0, "AC2": hit >= 0.65, "AC3": prec >= 0.70}
    Q = P[P["tot"] > 0]   # 진단(판정 아님): 올해 신고 '전체' 합계가 0인 빈 신고를 뺀다
    q0, q1 = (Q["n_fdd"] - Q["F0"]).abs().mean(), (Q["n_fdd"] - Q["P1"]).abs().mean()
    qa = (Q["P1"] - Q["F0"]).abs() >= np.maximum(3, 0.1 * Q["F0"])
    qp = float((np.sign(Q.loc[qa, "n_fdd"] - Q.loc[qa, "F0"]) == np.sign(Q.loc[qa, "P1"] - Q.loc[qa, "F0"])).mean())
    verdict = ("예상값·경보 싣기" if v["AC1"] and v["AC3"] else "경보만 싣기" if v["AC3"] else "예상값·경보 빼고 명세 대조만")
    by = P.assign(e0=e0, e1=e1, al=al).groupby("fy").agg(n=("key", "size"), mae0=("e0", "mean"), mae1=("e1", "mean"), alerts=("al", "sum"))
    L = [f"\n##### H-2026-10-AC 에이전트 사전 채움 vs 작년 복사 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 회계년도 {int(P['fy'].min())}~{int(P['fy'].max())}",
         f"  대상 브랜드 {P['key'].nunique()}개, 브랜드-연 {len(P):,} (외식·이름 정확 일치·작년 신고 서울 {MIN_STORES}곳+)",
         f"  AC1 평균 절대오차 복사 {mae0:.2f} -> 사전 채움 {mae1:.2f} ({mae1 / mae0 - 1:+.1%}, 기준 -10%) -> {'성립' if v['AC1'] else '기각'}",
         f"  AC2 부호 적중 {hit:.1%} (n {int(ch.sum()):,}, 기준 65%) -> {'성립' if v['AC2'] else '기각'}",
         f"  AC3 경보 정밀도 {prec:.1%} (경보 {int(al.sum()):,}건 = {al.mean():.1%}, 기준 70%) -> {'성립' if v['AC3'] else '기각'}",
         "  연도별: " + " | ".join(f"{int(y)} n{int(r.n)} {r.mae0:.1f}->{r.mae1:.1f} 경보{int(r.alerts)}" for y, r in by.iterrows()),
         f"  판정: {verdict}",
         f"  진단(판정 아님, 빈 신고 {len(P) - len(Q):,}건 제외, n {len(Q):,}): 오차 {q0:.2f} -> {q1:.2f} ({q1 / q0 - 1:+.1%}), 경보 {int(qa.sum()):,}건 정밀도 {qp:.1%}"]
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN.replace(".json", "_prefill.json"), "w", encoding="utf-8") as fh:
        json.dump({"asof": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "mae_copy": mae0, "mae_prefill": mae1, "sign_hit": hit, "alert_precision": prec,
                   "alert_rate": float(al.mean()), "n_brand_years": len(P), "n_brands": int(P["key"].nunique()), "verdict": verdict,
                   "diag_filed_only": {"n": len(Q), "mae_copy": float(q0), "mae_prefill": float(q1), "alerts": int(qa.sum()), "alert_precision": qp},
                   "by_fy": {int(y): {k: float(x) for k, x in r.items()} for y, r in by.iterrows()}}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__" and "fetch" in sys.argv:
    fetch()
if __name__ == "__main__" and "test" in sys.argv:
    test(strict="--v2" in sys.argv)

if __name__ == "__main__" and "prefill" in sys.argv:
    prefill()

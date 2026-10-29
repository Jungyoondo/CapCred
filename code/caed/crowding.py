"""출점 과밀 검정 H-2026-10-AG (2026-10-26, 로드맵 B-3b ③).

python -X utf8 -m caed.crowding     # -> data/caed/CROWDING.txt(익명 집계), crowding.json

같은 브랜드가 개업 시점에 반경 500m 안(10m 초과 - 같은 자리 전 점포 제외)에 이미 영업 중이면 신규 가맹점의 첫해 폐업이 더 높은가.
결과는 H-2026-10-Z 규칙으로 조정: 같은 자리(10m)에서 폐업 -30~+180일 안 같은 업종 재개업(양도 추정)은 폐업으로 세지 않는다.
주 검정은 브랜드×개업연도 층 Mantel-Haenszel 오즈비(브랜드 규모·연도 효과를 층으로 막는다). 사전 등록은 scoreboard/HYPOTHESES.md.
공개 산출물에는 브랜드 이름을 넣지 않는다.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import franchise_survival as FS  # noqa: E402

TXT = os.path.join(ROOT, "data", "caed", "CROWDING.txt")
JSN = os.path.join(ROOT, "data", "caed", "crowding.json")
MIN_BRAND = 30
SAME_SPOT = 10.0
RADII = (300.0, 500.0, 1000.0)      # 500m가 주 검정, 나머지는 진단
MAIN_R = 500.0


def mh(df, x, y, strata):
    """Mantel-Haenszel 오즈비와 95% 신뢰구간(Robins-Breslow-Greenland)."""
    sR = sS = sPR = sPSQR = sQS = 0.0
    for _, s in df.groupby(strata):
        n = len(s)
        if n < 2 or s[x].nunique() < 2:
            continue
        a = float(((s[x] == 1) & (s[y] == 1)).sum()); b = float(((s[x] == 1) & (s[y] == 0)).sum())
        c = float(((s[x] == 0) & (s[y] == 1)).sum()); d = float(((s[x] == 0) & (s[y] == 0)).sum())
        R, S, P, Q = a * d / n, b * c / n, (a + d) / n, (b + c) / n
        sR, sS, sPR, sPSQR, sQS = sR + R, sS + S, sPR + P * R, sPSQR + P * S + Q * R, sQS + Q * S
    if sR == 0 or sS == 0:
        return None, None, None
    orv = sR / sS
    se = np.sqrt(sPR / (2 * sR ** 2) + sPSQR / (2 * sR * sS) + sQS / (2 * sS ** 2))
    return float(orv), float(np.exp(np.log(orv) - 1.96 * se)), float(np.exp(np.log(orv) + 1.96 * se))


def build(code):
    FS.CODE, FS.UPTAE = code, None
    g = FS.load()
    today = pd.Timestamp.now().normalize()
    ok = (g["x"].notna() & g["y"].notna()).to_numpy()
    xy = g[["x", "y"]].to_numpy()
    opn, cls = g["open"].to_numpy(), g["close"].to_numpy()
    cnt = g["brand_raw"].value_counts()
    brands = set(cnt[cnt >= MIN_BRAND].index)
    inb = g["brand_raw"].isin(brands).to_numpy()
    tgt = inb & ok & (g["open"] >= "2016-01-01").to_numpy() & (g["open"] <= today - pd.DateOffset(years=1)).to_numpy()
    y_raw = (g["failed"] & g["close"].notna() & ((g["close"] - g["open"]).dt.days <= 365)).to_numpy() & tgt

    # 양도 추정(같은 자리 즉시 재개업) - H-2026-10-Z와 같은 규칙, 같은 업종 전체 대장에서 찾는다
    pos = np.flatnonzero(ok)
    tree_all = cKDTree(xy[ok])
    reopen = np.zeros(len(g), dtype=bool)
    idx = np.flatnonzero(y_raw)
    for i, near in zip(idx, tree_all.query_ball_point(xy[idx], r=SAME_SPOT)):
        j = pos[near]
        j = j[j != i]
        dd = (opn[j] - cls[i]) / np.timedelta64(1, "D")
        reopen[i] = bool(((dd >= -30) & (dd <= 180)).any())

    rows = []
    b_all = g["brand_raw"].to_numpy()
    for br in brands:
        m = np.flatnonzero((b_all == br) & ok)
        t_in = np.flatnonzero(tgt[m])
        if not len(t_in):
            continue
        tr = cKDTree(xy[m])
        for k, near in zip(t_in, tr.query_ball_point(xy[m[t_in]], r=max(RADII))):
            i = m[k]
            j = m[np.asarray(near, dtype=int)]
            j = j[j != i]
            dist = np.hypot(*(xy[j] - xy[i]).T) if len(j) else np.array([])
            alive = (opn[j] < opn[i]) & (pd.isna(cls[j]) | (cls[j] >= opn[i])) if len(j) else np.array([], dtype=bool)
            r = {"brand": br, "year": int(pd.Timestamp(opn[i]).year), "y_raw": int(y_raw[i]), "y": int(y_raw[i] and not reopen[i])}
            for R in RADII:
                r[f"n{int(R)}"] = int((alive & (dist > SAME_SPOT) & (dist <= R)).sum())
            rows.append(r)
    d = pd.DataFrame(rows)
    d["ind"] = code
    return d


def main():
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    parts = {c: build(c) for c in ("072405", "072404")}
    labels = {"072405": "카페·휴게", "072404": "음식점"}
    d = pd.concat(parts.values(), ignore_index=True)
    d["stratum"] = d["ind"] + "|" + d["brand"] + "|" + d["year"].astype(str)
    out, L = {"asof": stamp[:10], "radius_main": MAIN_R}, [f"\n##### H-2026-10-AG 출점 과밀 검정 {stamp} | 서울 인허가 가맹점(브랜드 {MIN_BRAND}곳+) 2016~ 개업 | 결과 = 조정 첫해 폐업"]

    def block(df, R, ycol="y"):
        df = df.assign(x=(df[f"n{int(R)}"] >= 1).astype(int))
        orv, lo, hi = mh(df, "x", ycol, "stratum")
        return {"n": len(df), "crowded_share": float(df["x"].mean()), "rate_crowded": float(df.loc[df.x == 1, ycol].mean()),
                "rate_alone": float(df.loc[df.x == 0, ycol].mean()), "mh_or": orv, "ci": [lo, hi]}

    main_ = block(d, MAIN_R)
    bins = pd.cut(d[f"n{int(MAIN_R)}"], [-1, 0, 1, 10 ** 6], labels=["0", "1", "2+"])
    dose = {k: {"n": int((bins == k).sum()), "rate": float(d.loc[bins == k, "y"].mean())} for k in ["0", "1", "2+"]}
    per = {c: block(parts[c].assign(stratum=parts[c]["ind"] + "|" + parts[c]["brand"] + "|" + parts[c]["year"].astype(str)), MAIN_R) for c in parts}
    ag1 = bool(main_["mh_or"] is not None and main_["mh_or"] >= 1.2 and main_["ci"][0] > 1)
    r = [dose[k]["rate"] for k in ["0", "1", "2+"]]
    ag2 = bool(r[0] < r[1] < r[2])
    ag3 = bool(all(p["mh_or"] is not None and p["mh_or"] > 1 for p in per.values()))
    verdict = "성립" if ag1 else "기각"
    out.update({"main": main_, "dose": dose, "by_industry": per, "AG1": ag1, "AG2": ag2, "AG3": ag3, "verdict": verdict,
                "diag": {"r300": block(d, 300.0), "r1000": block(d, 1000.0), "raw500": block(d, MAIN_R, "y_raw")}})

    pc = lambda v: f"{v * 100:.1f}%"   # noqa: E731
    fo = lambda b: (f"n={b['n']:,} 과밀 {pc(b['crowded_share'])} | 첫해 폐업 과밀 {pc(b['rate_crowded'])} vs 단독 {pc(b['rate_alone'])} | "   # noqa: E731
                    f"MH OR {b['mh_or']:.2f} [{b['ci'][0]:.2f}, {b['ci'][1]:.2f}]" if b["mh_or"] else f"n={b['n']:,} MH OR 계산 불가")
    L.append(f"  주(500m, 합침): {fo(main_)}")
    L.append("  같은 브랜드 수별 첫해 폐업: " + " · ".join(f"{k}곳 {pc(v['rate'])} (n={v['n']:,})" for k, v in dose.items()))
    for c, b in per.items():
        L.append(f"  {labels[c]}: {fo(b)}")
    L.append(f"  -> AG1 {'O' if ag1 else 'X'} (OR>=1.2, 하한>1) | AG2 {'O' if ag2 else 'X'} (0<1<2+ 단조) | AG3 {'O' if ag3 else 'X'} (두 업종 OR>1) => {verdict}")
    for k, b in out["diag"].items():
        L.append(f"  진단 {k}: {fo(b)}")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

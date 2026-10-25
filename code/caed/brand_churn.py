"""같은 자리 다음 점포 - 폐업이 '양도(같은 브랜드 재개업)'인지 '갈아타기(다른 브랜드로)'인지 (2026-10-21).

python -X utf8 -m caed.brand_churn      # -> data/caed/BRAND_CHURN.txt, brand_churn.json

왜: (1) 브랜드 건강도의 한계로 적은 '양도' - 인허가는 점주가 바뀌면 폐업 + 같은 자리 새 인허가로 남기도 한다. 그러면 가맹점 '폐업'의 일부는
  매장은 그대로인데 점주만 바뀐 것이다. 은행 입장에선 점주가 바뀌어도 기존 대출은 정리(상환·인수)되는 일이 많아 여전히 의미 있지만,
  '브랜드 매장 감소'로 세면 과대 추정이다. (2) 점주가 다른 브랜드 간판으로 바꿔 다는 '갈아타기'는 가맹점주가 브랜드를 버리는 직접 증거 -
  순증가율(개업 - 폐업)보다 먼저 쇠퇴를 보여 줄 수 있다. 가맹본부·은행 모두에게 파는 조기 경보 후보.
정의(사전 고정):
  같은 자리 = 인허가 좌표(EPSG:5174, 미터) 거리 10m 이내. 다음 점포 = 같은 업종 대장(카페: 휴게음식점 중 커피숍, 음식점: 일반음식점)에서
  폐업일 -30일 ~ +180일 사이에 인허가 난 다른 업소 중 가장 이른 것.
  폐업한 가맹점의 다음 점포가 같은 브랜드 = '같은 브랜드 재개업'(양도로 봄), 다른 브랜드 = '갈아타기', 브랜드 없음/없음 = 그 밖.
사전 가설(결과 전 커밋):
  D1 '같은 브랜드 재개업'을 폐업에서 뺀 정의로도 B1(검증 2021~24 쇠퇴 1/3 가맹점 다음 1년 폐업률 >= 성장 1/3의 2배)이 카페·음식점 모두 성립.
  D2 브랜드 갈아타기율(t) = (t-18개월, t-6개월]에 폐업한 그 브랜드 가맹점 중 '갈아타기'된 수 / t 시점 매장 수 (매장 10곳+ 브랜드, 미래 정보 없음).
     검증 2021~24 해마다 3분위 - 상위 1/3 브랜드 가맹점의 다음 1년 폐업률이 하위 1/3의 1.5배 이상, 카페·음식점 모두.
  D2b 가맹점 단위 로지스틱(업력·면적·순증가율)에 갈아타기율을 더하면 검증 AUC +0.01 이상, 카페·음식점 모두. 학습 t<=2019, 검증 2021~24.
  판정은 그대로 보고.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
TXT = os.path.join(ROOT, "data", "caed", "BRAND_CHURN.txt")
JSN = os.path.join(ROOT, "data", "caed", "brand_churn.json")
DIST, PRE, POST = 10.0, 30, 180


def successors(g):
    """폐업한 업소마다 같은 자리 다음 점포의 브랜드(없으면 NaN)와 존재 여부."""
    from scipy.spatial import cKDTree
    ok = g["x"].notna() & g["y"].notna()
    G = g[ok]
    tree = cKDTree(G[["x", "y"]].to_numpy())
    opens = G["open"].to_numpy()
    brand = G["brand_raw"].to_numpy()
    idx = G.index.to_numpy()
    nxt_brand = pd.Series(np.nan, index=g.index, dtype=object)
    has = pd.Series(False, index=g.index)
    closed = G[G["failed"] & G["close"].notna()]
    nb = tree.query_ball_point(closed[["x", "y"]].to_numpy(), DIST)
    for (i, row), cand in zip(closed.iterrows(), nb):
        lo, hi = row["close"] - pd.Timedelta(days=PRE), row["close"] + pd.Timedelta(days=POST)
        best = None
        for j in cand:
            if idx[j] == i or not (lo <= opens[j] <= hi):
                continue
            if best is None or opens[j] < opens[best]:
                best = j
        if best is not None:
            has[i] = True
            nxt_brand[i] = brand[best]
    return has, nxt_brand


def run(code, uptae, label):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from caed import franchise_survival as FS
    from caed import industry_survival as IS
    FS.CODE, FS.UPTAE = code, uptae
    g = FS.load()
    has, nb = successors(g)
    fr = g["brand_raw"].notna()
    same = fr & g["failed"] & (nb == g["brand_raw"])
    conv = fr & g["failed"] & nb.notna() & (nb != g["brand_raw"])
    g["exit_true"] = g["failed"] & ~same
    cnt = g["brand_raw"].value_counts()
    brands = set(cnt[cnt >= FS.MIN_BRAND].index)
    rows = []
    for yr in range(2014, IS.TEST[1] + 1):
        t = pd.Timestamp(f"{yr}-12-31")
        b = g["brand_raw"]
        alive = (g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))
        opened = (g["open"] > t - pd.DateOffset(years=1)) & (g["open"] <= t)
        closed = g["failed"] & (g["close"] > t - pd.DateOffset(years=1)) & (g["close"] <= t)
        win = g["close"].between(t - pd.DateOffset(months=18), t - pd.DateOffset(months=6), inclusive="right")
        stat = pd.DataFrame({"n": b[alive].value_counts(), "o": b[opened].value_counts(), "c": b[closed].value_counts(),
                             "cv": b[conv & win].value_counts()}).fillna(0)
        stat["growth"] = (stat["o"] - stat["c"]) / stat["n"].replace(0, np.nan)
        stat["convrate"] = stat["cv"] / stat["n"].replace(0, np.nan)
        s = g[alive & b.isin(brands)]
        nxt = (s["close"] > t) & (s["close"] <= t + pd.DateOffset(years=1))
        df = pd.DataFrame({"t": yr, "brand": s["brand_raw"].to_numpy(), "y": (s["failed"] & nxt).astype(int).to_numpy(),
                           "y_true": (s["exit_true"] & nxt).astype(int).to_numpy(),
                           "log_age": np.log1p((t - s["open"]).dt.days / 365.25).to_numpy(), "area": s["area"].to_numpy()})
        df = df.join(stat[["n", "growth", "convrate"]], on="brand")
        rows.append(df[df["n"] >= 10])
    M = pd.concat(rows, ignore_index=True)
    M["area_na"] = M["area"].isna().astype(float)
    M["log_area"] = np.log(M["area"]).fillna(np.log(M.loc[M["t"] <= IS.TRAIN_END, "area"]).median())
    te = M[M["t"].between(*IS.TEST)].copy()

    def terc(col, ycol):
        bt = te.groupby(["t", "brand"]).agg(v=(col, "first"), y=(ycol, "mean"), n=(ycol, "size")).reset_index()
        bt["q"] = bt.groupby("t")["v"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
        return {int(q): float(np.average(x["y"], weights=x["n"])) for q, x in bt.groupby("q")}
    d1 = terc("growth", "y_true")
    d2 = terc("convrate", "y")
    tr = M[M["t"] <= IS.TRAIN_END]
    auc = {}
    for tag, f in (("base", ["log_age", "log_area", "area_na", "growth"]), ("+conv", ["log_age", "log_area", "area_na", "growth", "convrate"])):
        mu, sd = tr[f].mean(), tr[f].std().replace(0, 1)
        m = LogisticRegression(max_iter=3000).fit(((tr[f] - mu) / sd).fillna(0), tr["y"])
        auc[tag] = float(roc_auc_score(te["y"], m.predict_proba(((te[f] - mu) / sd).fillna(0))[:, 1]))
    fc = fr & g["failed"] & g["close"].between(pd.Timestamp("2021-01-01"), pd.Timestamp("2025-04-30"))
    shares = {"closures": int(fc.sum()), "same_brand": float(same[fc].mean()), "converted": float(conv[fc].mean()),
              "independent_next": float((has & nb.isna())[fc].mean()), "empty": float((~has)[fc].mean())}
    return {"label": label, "shares": shares, "D1_tert": d1, "D1": d1[0] >= 2 * d1[2], "D2_tert": d2, "D2": d2[2] >= 1.5 * d2[0],
            "auc": auc, "D2b": auc["+conv"] - auc["base"] >= 0.01}


def main():
    R = [run("072405", "커피숍", "카페"), run("072404", None, "음식점")]
    v = lambda b: "성립" if b else "기각"  # noqa: E731
    L = [f"\n##### 같은 자리 다음 점포 - 양도·갈아타기 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 10m, 폐업 -{PRE}~+{POST}일, 검증 2021~24"]
    for r in R:
        s = r["shares"]
        L += [f"  [{r['label']}] 가맹점 폐업 {s['closures']:,}건(2021-01~2025-04) 다음 점포: 같은 브랜드 {s['same_brand']:.1%} | 다른 브랜드(갈아타기) {s['converted']:.1%} | "
              f"독립 {s['independent_next']:.1%} | 없음 {s['empty']:.1%}",
              f"    D1 같은 브랜드 재개업 뺀 폐업, 순증가율 3분위: 쇠퇴 {r['D1_tert'][0]:.1%} | 중간 {r['D1_tert'][1]:.1%} | 성장 {r['D1_tert'][2]:.1%} -> {v(r['D1'])}",
              f"    D2 갈아타기율 3분위 다음 1년 폐업: 하위 {r['D2_tert'][0]:.1%} | 중간 {r['D2_tert'][1]:.1%} | 상위 {r['D2_tert'][2]:.1%} -> {v(r['D2'])}",
              f"    D2b AUC 업력·면적·순증가율 {r['auc']['base']:.3f} -> +갈아타기율 {r['auc']['+conv']:.3f} -> {v(r['D2b'])}"]
    L.append(f"  사전 가설: D1 {v(all(r['D1'] for r in R))} | D2 {v(all(r['D2'] for r in R))} | D2b {v(all(r['D2b'] for r in R))} (두 업종 모두 성립해야 성립)")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "result": R}, fh, ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    main()

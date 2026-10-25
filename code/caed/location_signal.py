"""상권 신호가 소상공인 폐업 예측에 보탬이 되나 - 신용캐드 '상권 반영 점수'의 실데이터 검정 (2026-10-20).

python -X utf8 -m caed.location_signal          # -> data/caed/LOCATION_SIGNAL.txt, location_signal.json

왜: 신용캐드 진단의 세 번째 점수는 '공정 70% + 상권 30%'다. 상권이 실제 폐업을 더 잘 가려내는지 실제 결과로 본 적이 없다.
  헬스장 검정(H2)은 기각됐지만 표본이 작고 대장 포착률이 17%였다. 대장 포착률이 높고 표본이 큰 업종에서 다시 시험한다.
대상: 일반음식점(072404, 포착률 76%), 휴게음식점(072405), 미용실(051801). 서울 인허가(caed/localdata.py), 매년 말 영업 중 업소.
정답: 다음 12개월 상태 '폐업'. 학습 t<=2019, 검증 t=2021~2024.
모델(로지스틱, 학습기 표준화):
  B 기본: 면적(로그) + 면적 없음 + 업력(로그)                         - 은행이 보는 정보
  E 상권: B + 반경 100m 같은 업종 영업 중 수(로그) + 직전 12개월 반경 100m 개업 수·폐업 수 + 자치구 직전 1년 폐업률
지표: 검증 AUC, 상위 10% 경고의 실제 폐업률.
사전 가설(2026-10-20, 결과 보기 전 커밋):
  L1 E의 AUC가 B보다 0.01 이상 높은 업종이 3개 중 2개 이상.
  L2 E 상위 10% 경고의 실제 폐업률이 B보다 1%p 이상 높은 업종이 3개 중 2개 이상.
  둘 다 성립하면 '상권 반영 점수는 실데이터 근거 있음', 아니면 상권 점수를 '참고'로 낮추고 그대로 보고.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import industry_survival as IS  # noqa: E402
from caed import localdata as LD  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "caed")
TXT = os.path.join(OUT_DIR, "LOCATION_SIGNAL.txt")
JSN = os.path.join(OUT_DIR, "location_signal.json")
CODES = ["072404", "072405", "051801"]
R = 100.0
B_FEAT = ["log_area", "area_na", "log_age"]
E_FEAT = B_FEAT + ["log_dens", "near_open", "near_close", "gu_close"]


def prep(df):
    g = IS.prep(df)
    df = df.apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)
    keep = pd.to_datetime(df["APVPERMYMD"].replace("", None), format="%Y-%m-%d", errors="coerce").notna()
    src = df[keep].reset_index(drop=True)
    g["x"] = pd.to_numeric(src["X"], errors="coerce")
    g["y_"] = pd.to_numeric(src["Y"], errors="coerce")
    g["gu"] = src["gu"]
    return g.dropna(subset=["x", "y_"]).reset_index(drop=True)


def panel(g):
    from scipy.spatial import cKDTree
    xy = g[["x", "y_"]].to_numpy()
    rows = []
    for yr in range(2014, IS.TEST[1] + 1):
        t = pd.Timestamp(f"{yr}-12-31")
        t0 = t - pd.DateOffset(years=1)
        alive = ((g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))).to_numpy()
        opened = ((g["open"] > t0) & (g["open"] <= t)).to_numpy()
        closed = (g["failed"] & (g["close"] > t0) & (g["close"] <= t)).to_numpy()
        idx = np.where(alive)[0]

        def cnt(mask):
            pts = xy[mask]
            return cKDTree(pts).query_ball_point(xy[idx], R, return_length=True) if len(pts) else np.zeros(len(idx))
        gu_alive = g[alive].groupby("gu").size()
        gu_rate = (g[closed].groupby("gu").size() / gu_alive).reindex(g["gu"].iloc[idx]).fillna(0).to_numpy()
        s = g.iloc[idx]
        rows.append(pd.DataFrame({
            "t": yr, "y": (s["failed"] & (s["close"] > t) & (s["close"] <= t + pd.DateOffset(years=1))).astype(int).to_numpy(),
            "age": ((t - s["open"]).dt.days / 365.25).to_numpy(), "area": s["area"].to_numpy(),
            "dens": cnt(alive) - 1, "near_open": cnt(opened & alive) - opened[idx].astype(int), "near_close": cnt(closed),
            "gu_close": gu_rate}))
    P = pd.concat(rows, ignore_index=True)
    P["log_age"] = np.log1p(P["age"])
    P["area_na"] = P["area"].isna().astype(float)
    med = np.log(P.loc[P["t"] <= IS.TRAIN_END, "area"]).median()
    P["log_area"] = np.log(P["area"]).fillna(0.0 if pd.isna(med) else med)
    P["log_dens"] = np.log1p(P["dens"])
    P["near_open"] = np.log1p(P["near_open"])
    P["near_close"] = np.log1p(P["near_close"])
    return P


def evaluate(P, feats):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    tr, te = P[P["t"] <= IS.TRAIN_END], P[(P["t"] >= IS.TEST[0]) & (P["t"] <= IS.TEST[1])].copy()
    mu, sd = tr[feats].mean(), tr[feats].std().replace(0, 1)
    m = LogisticRegression(max_iter=3000).fit((tr[feats] - mu) / sd, tr["y"])
    te["s"] = m.predict_proba((te[feats] - mu) / sd)[:, 1]
    flag = te.groupby("t")["s"].transform(lambda s: s >= s.quantile(0.9))
    auc_y = {int(y): float(roc_auc_score(g_["y"], g_["s"])) for y, g_ in te.groupby("t")}
    return {"auc": float(roc_auc_score(te["y"], te["s"])), "top10": float(te.loc[flag, "y"].mean()), "base": float(te["y"].mean()),
            "auc_by_year": auc_y, "coef": dict(zip(feats, np.round(m.coef_[0], 3).tolist()))}


def main():
    res, L = {}, []
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L.append(f"\n##### 상권 신호 검정 {stamp} | 서울 인허가, 매년 말 영업 중 업소의 12개월 폐업 | 학습 t<={IS.TRAIN_END}, 검증 {IS.TEST[0]}~{IS.TEST[1]} | 반경 {R:.0f}m")
    for code in CODES:
        g = prep(LD.load(code))
        P = panel(g)
        B, E = evaluate(P, B_FEAT), evaluate(P, E_FEAT)
        res[code] = {"name": LD.INDUSTRIES[code][0], "B": B, "E": E, "n_test": int(((P["t"] >= IS.TEST[0]) & (P["t"] <= IS.TEST[1])).sum())}
        L.append(f"  {LD.INDUSTRIES[code][0]:<12} 검증 표본 {res[code]['n_test']:>8,} 폐업률 {B['base']:.1%} | B AUC {B['auc']:.3f} 상위10% {B['top10']:.1%} | "
                 f"E AUC {E['auc']:.3f} 상위10% {E['top10']:.1%} | 연도별 E-B " + " ".join(f"{y}:{E['auc_by_year'][y] - B['auc_by_year'][y]:+.3f}" for y in B["auc_by_year"]))
        L.append(f"    E 계수: {E['coef']}")
    l1 = sum(r["E"]["auc"] - r["B"]["auc"] >= 0.01 for r in res.values())
    l2 = sum(r["E"]["top10"] - r["B"]["top10"] >= 0.01 for r in res.values())
    ok = l1 >= 2 and l2 >= 2
    L.append(f"  사전 가설: L1 AUC +0.01 {l1}/3 {'성립' if l1 >= 2 else '기각'} | L2 상위10% 폐업률 +1%p {l2}/3 {'성립' if l2 >= 2 else '기각'} -> "
             f"{'상권 반영 점수 실데이터 근거 있음' if ok else '상권 점수는 참고로 낮춤 - 그대로 보고'}")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "results": res, "L1": l1, "L2": l2, "supported": ok}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

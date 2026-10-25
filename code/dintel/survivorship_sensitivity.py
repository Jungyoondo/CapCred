"""생존편향 보정의 민감도 - 퇴출 기업 상장 기간 근사를 흔들어도 조기경보 숫자가 유지되는가 (2026-10-23).

python -X utf8 -m dintel.survivorship_sensitivity kosdaq       (kospi도 같은 방식)

사전 등록: scoreboard/HYPOTHESES.md H-2026-10-E (결과 전 커밋).
기준 = dintel.survivorship.evaluate의 B(퇴출 포함 학습·검증, 공시 건수 피처, 로지스틱, 학습 ~2020 / 검증 2022~).
변형은 퇴출 기업 월말 범위만 바꾼다: 끝 -6·-3·+3개월, 시작 +12개월.
성립(변형 4개 모두): 상위 10% 배수 ±0.4배, 포착률 ±5%p, AUC ±0.015 안.
출력: data/dintel/SURVIVORSHIP_SUMMARY.txt ('##### 생존편향 민감도')
"""
import sys

import numpy as np
import pandas as pd

from dintel import survivorship as S

R = S.R
VARIANTS = {"기준(현행 근사)": (0, 0), "끝 -6개월": (0, -6), "끝 -3개월": (0, -3), "끝 +3개월": (0, 3), "시작 +12개월": (12, 0)}
TOL = {"lift": 0.4, "cap": 0.05, "auc": 0.015}


def score(allm, feats):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    d = allm[~allm["risk_prev"] & allm["y_known"]]
    tr, te = d[d["asof"] <= "2020-12-31"], d[d["asof"] >= "2022-01-01"]
    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
    pipe.fit(R._xy(tr, feats), tr["y"])
    s = pipe.predict_proba(R._xy(te, feats))[:, 1]
    k = max(1, int(len(te) * 0.10))
    top = te["y"].to_numpy()[np.argsort(-s)[:k]]
    base = te["y"].mean()
    return {"n_te": len(te), "base": base, "auc": R.auc(te["y"], s), "hit": top.mean(), "lift": top.mean() / base,
            "cap": top.sum() / max(te["y"].sum(), 1)}


def main():
    market = sys.argv[1] if len(sys.argv) > 1 else "kosdaq"
    S.MARKET, S.MK = market, f"{market}_delisted"
    info = S.targets()
    e_cur = S._events(R.EVENTS[market])
    e_del = S._events([f"events_{S.MK}.csv", f"events_I_{S.MK}.csv"])
    last_ev = max(e_cur["dt"].max(), e_del["dt"].max())
    mc = S._feats(R.month_panel(market)[["asof", "corp_code"]].copy(), e_cur, last_ev)
    span = e_del.groupby("corp_code")["dt"].agg(["min", "max"])
    S.log(f"\n##### 생존편향 민감도 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 시장 {market} | H-2026-10-E | 퇴출 기업 월말 범위만 바꿈")
    res = {}
    for name, (s_shift, e_shift) in VARIANTS.items():
        rows = []
        for cc, r in span.iterrows():
            if cc not in info.index:
                continue
            hi = min(r["max"], pd.Timestamp(info.loc[cc, "last_dt"])) + pd.DateOffset(months=e_shift)
            lo = max(r["min"] + pd.DateOffset(months=s_shift), pd.Timestamp("2015-01-31"))
            for d in pd.date_range(lo, hi, freq="ME"):
                rows.append((d, cc))
        md = S._feats(pd.DataFrame(rows, columns=["asof", "corp_code"]), e_del, last_ev)
        allm = pd.concat([mc, md], ignore_index=True)
        feats = [c for c in allm.columns if c.startswith("n_")]
        r_ = res[name] = score(allm, feats)
        S.log(f"  {name:14s} 퇴출 기업-월 {len(md):6,} | 검증 {r_['n_te']:,} 위험률 {r_['base']:.1%} | AUC {r_['auc']:.3f} | "
              f"상위10% {r_['hit']:.1%} ({r_['lift']:.1f}배, 포착 {r_['cap']:.0%})")
    b = res["기준(현행 근사)"]
    bad = [f"{n}: " + ", ".join(k for k in TOL if abs(r[k] - b[k]) > TOL[k]) for n, r in res.items()
           if any(abs(r[k] - b[k]) > TOL[k] for k in TOL)]
    S.log(f"SURVIVORSHIP SENSITIVITY {market}: " + ("HOLDS (all variants within lift ±0.4x, capture ±5pp, AUC ±0.015)" if not bad
                                                    else "SENSITIVE - " + " | ".join(bad)))


if __name__ == "__main__":
    main()

"""경고 선행 기간 - 실제 중대 위험 공시보다 몇 개월 먼저 경고 목록(상위 10%)에 올랐나 (2026-10-10).

python -X utf8 -m dintel.lead_time            # kosdaq
python -X utf8 -m dintel.lead_time kospi

영업 질문 "얼마나 미리 알려 주나"에 대한 실측 답. dintel.risk_score와 같은 패널(퇴출 기업 포함, 공시 건수 피처)·같은 분할:
학습 t<=2020-12로 로지스틱 학습 -> 2022-01 이후 매 월말 점수(표본외) -> 그 달 상위 10% = 경고.
각 위험 사건(기업별 2022-01 이후 첫 중대 위험 공시, 직전 12개월 위험 공시 없는 경우)에 대해, 사건 직전 12개월 동안의
월말 경고 여부를 본다:
  - 사전 경고율: 사건 전 12개월 중 한 번이라도 경고됐는가
  - 선행 기간: 사건 전 '처음' 경고된 달부터 사건까지 개월 수(첫 경고), 사건 직전까지 연속 경고였는지
비교: 같은 기간 위험 사건이 없던 기업이 한 번이라도 경고된 비율(오경보 노출).
출력: data/dintel/LEAD_TIME_SUMMARY.txt
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dintel import risk_score as R  # noqa: E402

OUT = os.path.join(R.DD, "LEAD_TIME_SUMMARY.txt")


def log(s=""):
    print(s, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def main():
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    market = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in R.PANELS else "kosdaq"
    m, last_ev = R.build(market)
    md = R.delisted_panel(m, last_ev, market)
    m = pd.concat([m.assign(delisted=False), md], ignore_index=True) if md is not None else m.assign(delisted=False)
    feats = [c for c in m.columns if c.startswith("n_")]
    tr = m[~m["risk_prev"] & m["y_known"] & (m["asof"] <= "2020-12-31")]
    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
    pipe.fit(R._xy(tr, feats), tr["y"])
    te = m[m["asof"] >= "2022-01-01"].copy()
    te["s"] = pipe.predict_proba(R._xy(te, feats))[:, 1]
    te["warn"] = te.groupby("ym")["s"].rank(pct=True) >= 0.9
    te = te.sort_values(["corp_code", "asof"])
    # 위험 사건: 2022-01 이후 기업별 첫 중대 위험 공시일(직전 12개월 위험 공시 없음)
    e = R.load_events(market)
    from dintel import survivorship as SV
    SV.MARKET, SV.MK = market, f"{market}_delisted"
    if os.path.exists(os.path.join(R.DD, f"events_I_{SV.MK}.csv")):
        e = pd.concat([e, SV._events([f"events_{SV.MK}.csv", f"events_I_{SV.MK}.csv"])], ignore_index=True)
    r = e[e["risk"] & (e["dt"] >= "2022-02-01") & (e["dt"] <= last_ev - pd.Timedelta(days=0))].sort_values("dt")
    rows = []
    W = {c: g.set_index("asof")["warn"] for c, g in te.groupby("corp_code")}
    ri = R._index(e, e["risk"])
    for c, g in r.groupby("corp_code"):
        t = g["dt"].iloc[0]
        prev = ri.get(c)
        if prev is not None and ((prev < np.datetime64(t)) & (prev >= np.datetime64(t - pd.Timedelta(days=365)))).any():
            continue
        w = W.get(c)
        if w is None:
            continue
        win = w[(w.index < t) & (w.index >= t - pd.Timedelta(days=365))]
        if len(win) < 6:                                  # 사건 전 관측이 너무 짧으면 제외
            continue
        first = win[win].index.min() if win.any() else None
        lead = (t - first).days / 30.44 if first is not None else np.nan
        last3 = win.iloc[-3:].all() if len(win) >= 3 else False
        rows.append((c, t, bool(win.any()), lead, bool(win.iloc[-1]), last3,
                     bool(te.loc[te["corp_code"] == c, "delisted"].iloc[0])))
    D = pd.DataFrame(rows, columns=["corp", "event", "warned", "lead_m", "warned_last", "warned_last3", "delisted"])
    # 오경보 노출: 2022-01~(last_ev-12개월) 사이 위험 사건이 없던 기업이 한 번이라도 경고된 비율
    cut = last_ev - pd.Timedelta(days=365)
    clean = te[te["asof"] <= cut].groupby("corp_code").agg(any_warn=("warn", "any"), any_y=("y", "any"))
    fa = clean[~clean["any_y"]]["any_warn"].mean()
    log(f"\n##### 경고 선행 기간 {market} {pd.Timestamp.now():%Y-%m-%d %H:%M} | 표본외(학습 ~2020, 점수 2022-01~) | 퇴출 기업 포함 | "
        f"위험 사건 {len(D):,}건(기업별 첫 사건, 사건 전 관측 6개월+)")
    log(f"  사건 전 12개월 안에 한 번이라도 경고: {D['warned'].mean():.0%} | 사건 직전 달 경고 중: {D['warned_last'].mean():.0%} | "
        f"직전 3개월 연속 경고: {D['warned_last3'].mean():.0%}")
    L = D["lead_m"].dropna()
    log(f"  첫 경고부터 사건까지(경고된 사건 {len(L):,}건): 중앙값 {L.median():.1f}개월 | 평균 {L.mean():.1f} | "
        f"3개월+ {(L >= 3).mean():.0%} | 6개월+ {(L >= 6).mean():.0%}")
    for nm, x in (("퇴출 기업", D[D["delisted"]]), ("현재 상장사", D[~D["delisted"]])):
        if len(x):
            log(f"    {nm}: 사건 {len(x):,} | 사전 경고 {x['warned'].mean():.0%} | 선행 중앙값 {x['lead_m'].median():.1f}개월")
    log(f"  비교(오경보 노출): 같은 기간 위험 사건이 없던 기업 중 한 번이라도 경고된 비율 {fa:.0%}")
    log(f"LEAD {market}: 사건의 {D['warned'].mean():.0%}를 미리 경고, 첫 경고는 사건 {L.median():.1f}개월 전(중앙값)")


if __name__ == "__main__":
    main()

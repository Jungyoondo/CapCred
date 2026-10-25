"""가상 성적표 - 2022-01부터 매달 경고 목록을 고정해 공개했다면, 각 달의 성적은? (2026-10-10)

python -X utf8 -m dintel.pseudo_scoreboard            # kosdaq (퇴출 기업 포함)

공개 성적표(scoreboard/)는 2026-10에 시작해 첫 채점이 2027-10이다. 그 전에 "매달 꾸준한가"를 보여 주기 위해,
2020-12까지만 학습한 고정 모델(dintel.risk_score와 같은 공시 건수 로지스틱, 퇴출 기업 포함)로 2022-01~ 매 월말
상위 10%를 '그달의 경고 목록'으로 보고 12개월 뒤 실제 중대 위험 공시율을 채점한다(정답이 확정된 달까지).
출력: data/dintel/pseudo_scoreboard_<market>.csv (월, 경고 수, 경고 적중률, 전체 평균, 배수), 요약 PSEUDO_SCOREBOARD.txt,
      deliverables/figures/fig11_pseudo_scoreboard.png
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


def main():
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    market = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in R.PANELS else "kosdaq"
    m, last_ev = R.build(market)
    md = R.delisted_panel(m, last_ev, market)
    if md is not None:
        m = pd.concat([m.assign(delisted=False), md], ignore_index=True)
    feats = [c for c in m.columns if c.startswith("n_")]
    d = m[~m["risk_prev"]]
    tr = d[d["y_known"] & (d["asof"] <= "2020-12-31")]
    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
    pipe.fit(R._xy(tr, feats), tr["y"])
    te = d[d["y_known"] & (d["asof"] >= "2022-01-01")].copy()
    te["s"] = pipe.predict_proba(R._xy(te, feats))[:, 1]
    te["warn"] = te.groupby("ym")["s"].rank(pct=True, method="first") > 0.9
    rows = []
    for ym, g in te.groupby("ym"):
        w = g[g["warn"]]
        rows.append({"month": str(ym), "n_firms": len(g), "n_warn": len(w), "hit_pct": w["y"].mean() * 100,
                     "base_pct": g["y"].mean() * 100})
    S = pd.DataFrame(rows)
    S["multiple"] = S["hit_pct"] / S["base_pct"]
    S.to_csv(os.path.join(R.DD, f"pseudo_scoreboard_{market}.csv"), index=False, encoding="utf-8")
    beat = (S["multiple"] > 1).mean()
    beat2 = (S["multiple"] >= 2).mean()
    txt = (f"\n##### 가상 성적표 {market} {pd.Timestamp.now():%Y-%m-%d %H:%M} | 고정 모델(학습 ~2020, 퇴출 포함) | "
           f"{S['month'].iloc[0]}~{S['month'].iloc[-1]} {len(S)}개월\n"
           f"  월별 경고 적중률 중앙값 {S['hit_pct'].median():.1f}% vs 평균 {S['base_pct'].median():.1f}% | 배수 중앙값 "
           f"{S['multiple'].median():.1f}배 (최저 {S['multiple'].min():.1f}, 최고 {S['multiple'].max():.1f})\n"
           f"  평균보다 높았던 달 {beat:.0%} | 2배 이상이었던 달 {beat2:.0%}\n")
    print(txt, flush=True)
    with open(os.path.join(R.DD, "PSEUDO_SCOREBOARD.txt"), "a", encoding="utf-8") as fh:
        fh.write(txt)
    # 그림
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import make_figures as MF
    f = MF.fig("매달 꾸준했다: 2022년부터 매달 경고 목록을 고정했다면",
               f"코스닥 · 2020년까지만 학습한 모델 그대로 · 각 달 상위 10% 경고의 12개월 뒤 실제 위험 공시율 · 퇴출 기업 포함 · {len(S)}개월")
    ax = MF.axes(f)
    x = np.arange(len(S))
    ax.plot(x, S["hit_pct"], color=MF.WARN, lw=3.5, marker="o", ms=6, label="경고 목록 적중률")
    ax.plot(x, S["base_pct"], color="#94a3b8", lw=3, ls="--", label="전체 평균")
    ax.fill_between(x, S["base_pct"], S["hit_pct"], where=S["hit_pct"] > S["base_pct"], color=MF.WARN, alpha=0.08)
    step = max(1, len(S) // 8)
    ax.set_xticks(x[::step], S["month"].iloc[::step])
    ax.set_ylabel("12개월 중대 위험 공시율 (%)")
    ax.set_ylim(0, max(S["hit_pct"].max() * 1.15, 10))
    ax.legend(frameon=False, fontsize=19, loc="upper right")
    f.text(0.10, 0.74, f"평균보다 높았던 달 {beat:.0%} · 배수 중앙값 {S['multiple'].median():.1f}배", fontsize=24,
           fontweight="bold", color=MF.INK)
    MF.save(f, "fig11_pseudo_scoreboard.png", f"data/dintel/pseudo_scoreboard_{market}.csv (dintel/pseudo_scoreboard.py)")


if __name__ == "__main__":
    main()

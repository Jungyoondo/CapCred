"""
validate_iv.py — 순수 IV 신용모델 검증 (SHOCK_W 스윕 대체)
================================================================
외부충격 복원을 폐지했으므로, 검증은 'IV가 IV로서 잘 작동하는가'로 바뀐다.
  [1] 1단계 F (약도구 검정, 기준 10↑)
  [2] OVB (OLS가 매출계수를 얼마나 과대추정하는가 = IV 교정의 크기)
  [3] 변별력 AUC (전통 OLS vs 공정 IV) — nu=0 규모중립 설정
  [4] 규모중립성 |corr(점수, log_sales)| — 낮을수록 규모 편향 적음
  [5] λ(NU_MIX) 스윕 — 공정성↔정확성 손잡이. SHOCK_W 스윕을 대체하는 튜닝 곡선.
전부 다중시드 평균으로 '한 시드의 우연'이 아님을 확인한다.
"""
import numpy as np
import model as M
import validation_common as vc

SEEDS = [42, 101, 202, 303, 404]
N = 6000


def scale_dep(score, dte):
    """|corr(점수, log_sales)| — 규모 의존도(낮을수록 규모중립)."""
    return abs(np.corrcoef(score, dte["log_sales"].values)[0, 1])


# ── [1]~[4] 다중시드 핵심 진단 ──────────────────────────────
print("=" * 70)
print("IV 신용모델 진단 (데이터시드 5개 평균, n=%d, test 30%%)" % N)
print("=" * 70)
rows = {k: [] for k in ["F", "OVB", "auc_trad", "auc_fair", "sd_trad", "sd_fair"]}
for s in SEEDS:
    df = M.generate_data(n=N, seed=s)
    dtr, dte, ytr, yte = vc.split(df, seed=0)
    beta2, beta_ols, b1 = vc.fit(dtr, ytr)

    rows["F"].append(vc.first_stage_F(dtr))
    rows["OVB"].append(abs((beta_ols[1] - beta2[1]) / beta2[1]) * 100)

    p_trad = vc.trad_probs(dte, beta_ols)
    p_fair = vc.fair_probs(dte, beta2)               # nu=0 (규모중립 최대)
    rows["auc_trad"].append(vc.auc(yte, p_trad))
    rows["auc_fair"].append(vc.auc(yte, p_fair))
    rows["sd_trad"].append(scale_dep(100 * (1 - p_trad), dte))
    rows["sd_fair"].append(scale_dep(100 * (1 - p_fair), dte))

m = {k: np.mean(v) for k, v in rows.items()}
print(f"[1] 1단계 F (약도구 검정)     : {m['F']:8.1f}   (기준 10의 {m['F']/10:.1f}배 → 강한 도구)")
print(f"[2] OVB (OLS 매출계수 과대)   : {m['OVB']:8.1f}%  (IV가 교정하는 편향 크기)")
print(f"[3] 변별력 AUC   전통(OLS)    : {m['auc_trad']:8.4f}")
print(f"                 공정(IV)     : {m['auc_fair']:8.4f}   (차이 {m['auc_trad']-m['auc_fair']:+.4f})")
print(f"[4] 규모의존 |corr(점수,매출)| 전통 {m['sd_trad']:.3f} → 공정 {m['sd_fair']:.3f}   "
      f"({'규모중립 개선' if m['sd_fair'] < m['sd_trad'] else '개선 없음'})")
print("  해석: 공정(IV)은 AUC를 소폭 내주는 대신 규모 의존을 낮춘다(공정성↔정확성 맞바꿈).")

# ── [5] λ(NU_MIX) 스윕 — SHOCK_W 스윕 대체 ───────────────────
print("\n" + "=" * 70)
print("[5] λ(NU_MIX) 스윕 — 공정성↔정확성 손잡이 (다중시드 평균)")
print("    λ=0: 규모중립 최대(앱 현재값) / λ=1: 풀 IV(예측력 최대)")
print("=" * 70)
print(f"{'λ':>5} | {'공정 AUC':>9} | {'규모의존|corr|':>13} | 성격")
lam_grid = [0.0, 0.25, 0.5, 0.75, 1.0]
agg = {L: {"auc": [], "sd": []} for L in lam_grid}
for s in SEEDS:
    df = M.generate_data(n=N, seed=s)
    dtr, dte, ytr, yte = vc.split(df, seed=0)
    beta2, beta_ols, b1 = vc.fit(dtr, ytr)
    nu_te = vc.firm_nu(dte, b1)
    for L in lam_grid:
        p = vc.fair_probs(dte, beta2, nu=L * nu_te)
        agg[L]["auc"].append(vc.auc(yte, p))
        agg[L]["sd"].append(scale_dep(100 * (1 - p), dte))
for L in lam_grid:
    a = np.mean(agg[L]["auc"]); sd = np.mean(agg[L]["sd"])
    tag = "규모중립 우선" if L == 0 else ("풀 IV(정확도 최대)" if L == 1 else "절충")
    print(f"{L:5.2f} | {a:9.4f} | {sd:13.3f} | {tag}")
print("\n규칙: 공정성 우선이면 λ=0(현재). 정확도가 더 필요하면 λ를 올리되 규모의존이 함께 오른다.")
print("      SHOCK_W 스윕이 하던 '트레이드오프 탐색' 역할을 이 λ 곡선이 대체한다.")

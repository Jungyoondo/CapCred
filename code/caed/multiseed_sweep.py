"""
multiseed_sweep.py — SHOCK_W 결론이 시드 하나의 우연이 아닌지 다중 시드로 재확인
[리팩터: validation_common 사용 — sweep_shock_w 복사본 대신 단일 정본을 import]
"""
import numpy as np
import model as M
import validation_common as vc


def run_standard(data_seed, split_seed, shock_w):
    df = M.generate_data(n=6000, seed=data_seed)
    dtr, dte, ytr, yte = vc.split(df, seed=split_seed)
    beta2, _, _ = vc.fit(dtr, ytr)
    p_fair = vc.fair_probs(dte, beta2)
    s_fair = 100 * (1 - p_fair)
    credit, _ = vc.credit_scores(s_fair, dte, shock_w)
    return vc.auc(yte, p_fair), vc.auc(yte, 1 - credit / 100)


def run_stress(data_seed, split_seed, shock_w):
    df = vc.generate_unfair(n=6000, seed=data_seed, env=1.0)
    dtr, dte, ytr, yte = vc.split(df, seed=split_seed)
    beta2, beta_ols, _ = vc.fit(dtr, ytr)
    p_trad = vc.trad_probs(dte, beta_ols)
    p_fair = vc.fair_probs(dte, beta2)
    s_fair = 100 * (1 - p_fair)
    credit, _ = vc.credit_scores(s_fair, dte, shock_w)
    return vc.auc(yte, p_trad), vc.auc(yte, 1 - credit / 100)


print("시드 5개 (표준: 데이터시드 42,101,202,303,404 / 스트레스: 1,11,21,31,41) 평균")
print(f"{'SHOCK_W':>8} | {'표준손실 평균':>12} | {'스트레스 vs은행 평균':>18}")
for w in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
    std_losses, stress_gains = [], []
    for ds in [42, 101, 202, 303, 404]:
        a_fair, a_credit = run_standard(ds, 0, w)
        std_losses.append(a_fair - a_credit)
    for ds in [1, 11, 21, 31, 41]:
        a_bank, a_credit = run_stress(ds, 0, w)
        stress_gains.append(a_credit - a_bank)
    print(f"{w:8.1f} | {np.mean(std_losses):12.4f} | {np.mean(stress_gains):+18.4f}")

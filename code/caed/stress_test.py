"""
stress_test.py — 외부충격 복원(v2) '설계 정합성' 검증  [리팩터: validation_common 사용]
================================================================
공통 로직(generate_unfair·auc·학습)은 validation_common.py 로 단일화했다.

주입한 불공정: 진짜 부실은 mgmt(진짜 실력)에만 의존하되, 관측 매출·재무는
업종 위축(industry_prod_idx<중립)일수록 눌려 낮게 관측됨 → 위축업종 우량 운영자가
관측치 기준으로 은행에 부당하게 낮게 매겨진다(= 외부충격 복원이 겨냥하는 상황).
검증: 복원이 (1) 그 부당 페널티를 줄이나? (2) 진짜 부실기업까지 올리는 부작용은?
"""
import numpy as np
import model as M
import validation_common as vc

df = vc.generate_unfair(n=6000, seed=1, env=1.0)
dtr, dte, ytr, yte = vc.split(df, seed=0)
beta2, beta_ols, _ = vc.fit(dtr, ytr)

p_trad = vc.trad_probs(dte, beta_ols)
p_fair = vc.fair_probs(dte, beta2)          # nu=0 (앱 방식)
s_ols = 100 * (1 - p_trad)
s_fair = 100 * (1 - p_fair)
s_credit, _ = vc.credit_scores(s_fair, dte, shock_w=M.SHOCK_W)   # 업종배수 미적용(합성)

ip = dte["industry_prod_idx"].values
hard = ip < M.SHOCK_REF      # 위축 업종
easy = ~hard
good = (yte == 0); bad = (yte == 1)

print("=" * 66)
print("주입 확인: '실제 우량(비부실)' 기업인데 위축 업종이면 은행점수가 낮은가")
print(f"  우량기업 은행(OLS)점수  정상업종 {s_ols[good & easy].mean():5.1f}  "
      f"위축업종 {s_ols[good & hard].mean():5.1f}  "
      f"→ 부당 페널티 {s_ols[good & easy].mean() - s_ols[good & hard].mean():+.1f}점")
print("=" * 66)


def gap(score, mask):
    return score[mask & easy].mean() - score[mask & hard].mean()


print("\n[1] 우량기업(비부실)의 정상-위축 업종 점수격차 (0에 가까울수록 공정)")
print(f"  은행(OLS)   격차 {gap(s_ols, good):+5.1f}점")
print(f"  공정(IV)     격차 {gap(s_fair, good):+5.1f}점")
print(f"  신용평가     격차 {gap(s_credit, good):+5.1f}점   ← 목표: 격차 축소")

print("\n[2] 부작용 — 위축 업종의 '진짜 부실'기업이 받는 평균 복원분")
print(f"  우량기업 평균 복원(위축업종) +{(s_credit - s_fair)[good & hard].mean():.2f}")
print(f"  부실기업 평균 복원(위축업종) +{(s_credit - s_fair)[bad & hard].mean():.2f}  ← 낮을수록 좋음")

print("\n[3] 변별력 AUC (이 불공정 세상에서)")
print(f"  은행(OLS)   {vc.auc(yte, p_trad):.4f}")
print(f"  공정(IV)     {vc.auc(yte, p_fair):.4f}")
print(f"  신용평가     {vc.auc(yte, 1 - s_credit / 100):.4f}")

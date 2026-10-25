"""
validation_common.py — IV 신용모델 검증 공통 헬퍼 (정리판)
================================================================
[정리] 외부충격 복원 폐지(옵션 ①)에 따라 환경 관련 로직을 전부 제거했다.
  삭제: generate_unfair(2세상 스트레스 DGP), credit_scores(환경가점).
남긴 것: 학습/채점 헬퍼 + AUC + 1단계 F. 검증은 validate_iv.py 가 이걸 쓴다.
"""
import numpy as np
import model as M

IV, CTRL = M.IV_COLS, M.CTRL_COLS


def phi(X, b):
    return np.asarray(M.norm_cdf(X @ b)).ravel()


def rankdata_avg(a):
    a = np.asarray(a, float); order = np.argsort(a, kind="mergesort")
    ranks = np.empty(len(a), float); sa = a[order]; i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and sa[j + 1] == sa[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0; i = j + 1
    return ranks


def auc(y, risk):
    """risk(클수록 연체 가능성↑)로 y(1=연체) 순위매김. 0.5=무작위."""
    y = np.asarray(y); n1 = int(y.sum()); n0 = len(y) - n1
    if n1 == 0 or n0 == 0:
        return float("nan")
    r = rankdata_avg(risk)
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2.0) / (n1 * n0)


def split(df, seed=0, frac=0.7):
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(df)); cut = int(len(df) * frac)
    dtr = df.iloc[idx[:cut]].reset_index(drop=True)
    dte = df.iloc[idx[cut:]].reset_index(drop=True)
    return dtr, dte, dtr["delinquent"].values.astype(float), dte["delinquent"].values.astype(int)


def fit(dtr, ytr):
    """1단계 OLS + 2단계 IV Probit / OLS Probit. 반환: (beta2_iv, beta_ols, b1_firststage)."""
    s1 = M.ols_fit(M.add_const(dtr[IV + CTRL].values), dtr["log_sales"].values)
    b1, nu = s1["beta"], s1["resid"]
    beta2 = M.probit_fit(M.add_const(np.hstack([dtr[["log_sales"] + CTRL].values, nu[:, None]])), ytr)
    beta_ols = M.probit_fit(M.add_const(dtr[["log_sales"] + CTRL].values), ytr)
    return beta2, beta_ols, b1


def first_stage_F(dtr):
    """약도구 검정용 1단계 F. 기준 10 이상이면 강한 도구."""
    X1 = M.add_const(dtr[IV + CTRL].values)
    rss_f = float((lambda r: r @ r)(M.ols_fit(X1, dtr["log_sales"].values)["resid"]))
    rss_r = float((lambda r: r @ r)(M.ols_fit(M.add_const(dtr[CTRL].values), dtr["log_sales"].values)["resid"]))
    n_, k_ = X1.shape; k_iv = len(IV)
    return ((rss_r - rss_f) / k_iv) / (rss_f / (n_ - k_))


def firm_nu(dte, b1):
    """테스트 기업별 진짜 1단계 잔차 nu = log_sales − 1단계예측(실제 IV 사용).
    참고용(순수 IV 관점). 앱은 이 값이 아니라 app_firm_nu를 쓰므로, λ 튜닝은
    app_firm_nu로 해야 '계산한 값 = 배포한 값'이 된다."""
    return dte["log_sales"].values - M.add_const(dte[IV + CTRL].values) @ b1


def app_firm_nu(dte, b1):
    """앱(model.calc_fair_score)과 동일하게 계산한 nu.
    거시IV=MACRO_REF, station_dist_z=0, CTRL=실제. 사용자가 거시변수를 입력하지
    않으므로 앱은 거시를 기준값으로 치환한다 → 검증도 같은 정의를 써야 정합.
    (주의: 거시 계수가 큰 실데이터에선 이 치환이 경기 페널티를 nu에 유입시킬 수
     있음 — 알려진 한계, 실데이터 캘리브 시 재점검.)"""
    iv_ref = np.array([0.0 if c == "station_dist_z" else M.MACRO_REF[c] for c in IV])
    ivref = np.tile(iv_ref, (len(dte), 1))
    X = M.add_const(np.hstack([ivref, dte[CTRL].values]))
    return dte["log_sales"].values - X @ b1


def trad_probs(dte, beta_ols):
    return phi(M.add_const(dte[["log_sales"] + CTRL].values), beta_ols)


def fair_probs(dte, beta2, nu=None):
    """공정(IV) 연체확률. nu 미지정이면 앱 방식(nu=0=규모중립 최대)."""
    base = dte[["log_sales"] + CTRL].values
    col = np.zeros(len(dte)) if nu is None else np.asarray(nu)
    return phi(M.add_const(np.hstack([base, col[:, None]])), beta2)

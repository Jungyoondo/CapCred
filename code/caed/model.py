"""
신용캐드 (Credit CAED) - 핵심 모델  [정리판 · 환경복원 제거]
=====================================================
전통 모델 : OLS Probit 연체확률 (IV 내생성 교정 없음 — 은행이 보는 점수)
공정 모델 : IV Probit 연체확률 (도구변수로 매출 내생성 교정 → 경기·규모 편향 제거)

[이번 정리에서 바뀐 것]
1. 업종 생산지수(industry_prod_idx)를 도구변수(IV_COLS)로 되돌렸다.
   - 이전엔 '외부충격 환경가점' 전용으로 빼 두었으나, 그 환경 복원 로직 자체를 제거하므로
     이중사용 우려가 사라져 IV로 복귀하는 게 맞다(팀 논의 결론: 옵션 ①).
2. '외부충격 복원(신용평가 #3)' 관련 전부 삭제:
   environment_index / apply_env_bonus / env_score / SHOCK_* / ENV_MAX_BONUS /
   SECTOR_* / longevity_mult / employee_mult / firm_resilience_mult 등.
   → 상권·환경 맥락은 별도 상권(CSS) 대안신용 엔진이 담당한다(이 모델은 순수 IV 신용).
3. 점수는 두 개(전통·공정)로 단순화. calc_fair_score 는 공정점수만 반환.

=== 변수 구성 ===
CTRL_COLS(재무 6): cash_ratio, equity_ratio, current_ratio, interest_cov, asset_turnover, equity_growth
IV_COLS(도구 6)  : gdp_growth, rate_change, industry_idx, material_idx, station_dist_z, industry_prod_idx
"""

import math, datetime
import numpy as np

try:
    from macro_calib import get_moment as _macro_moment
except ImportError:
    def _macro_moment(key, default_mean, default_std):
        return default_mean, default_std

# ================================================================
# 수치 함수
# ================================================================
_erf_v = np.vectorize(math.erf)

def norm_cdf(x):
    return 0.5 * (1.0 + _erf_v(np.asarray(x, float) / math.sqrt(2.0)))

def norm_pdf(x):
    x = np.asarray(x, float)
    return np.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def add_const(X):
    return np.hstack([np.ones((X.shape[0], 1)), X])

def ols_fit(X, y):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k  = X.shape
    s2    = float(resid @ resid) / (n - k)
    try:    cov = s2 * np.linalg.inv(X.T @ X)
    except: cov = s2 * np.linalg.pinv(X.T @ X)
    return {"beta": beta, "resid": resid, "cov": cov}

def probit_fit(X, y, max_iter=300, tol=1e-8):
    n, k = X.shape
    beta = np.zeros(k); EPS = 1e-10
    for _ in range(max_iter):
        eta   = X @ beta
        Phi   = np.clip(norm_cdf(eta), EPS, 1 - EPS)
        phi   = norm_pdf(eta)
        score = X.T @ (y * phi / Phi + (1 - y) * (-phi / (1 - Phi)))
        w     = phi**2 / (Phi * (1 - Phi))
        H     = X.T @ (w[:, None] * X)
        try:    delta = np.linalg.solve(H, score)
        except: break
        beta_n = beta + delta
        if np.max(np.abs(beta_n - beta)) < tol:
            return beta_n
        beta = beta_n
    return beta

# ================================================================
# 변수 정의
# ================================================================
# 업종 생산지수(industry_prod_idx)는 도구변수로 사용한다(환경가점 폐지에 따른 복귀).
IV_COLS = ["gdp_growth", "rate_change", "industry_idx", "material_idx",
           "station_dist_z", "industry_prod_idx"]

CTRL_COLS = ["cash_ratio", "equity_ratio", "current_ratio",
             "interest_cov", "asset_turnover", "equity_growth"]

# 교통접근성 도구변수 정규화 상수 (역거리 m -> 표준화 z)
STATION_REF_M   = 500.0
STATION_SCALE_M = 500.0
def station_z(dist_m):
    return (float(dist_m) - STATION_REF_M) / STATION_SCALE_M

# 거시환경 기준값(공정점수 정규화 앵커, NU_MIX>0일 때 nu_val 계산에 사용).
# macro_calib.py 실측 평균으로 맞춤(gdp/rate/industry_idx/material_idx).
# industry_prod_idx는 실측 캘리브 대상 제외라 기존 중립값(=100) 유지.
_gdp_ref, _ = _macro_moment("gdp_growth", 1.0, 1.2)
_rate_ref, _ = _macro_moment("rate_change", 0.0, 0.5)
_ind_ref, _ = _macro_moment("industry_idx", 100.0, 10.0)
_mat_ref, _ = _macro_moment("material_idx", 100.0, 15.0)
MACRO_REF = {
    "gdp_growth": _gdp_ref, "rate_change": _rate_ref, "industry_idx": _ind_ref,
    "material_idx": _mat_ref, "industry_prod_idx": 100.0,
}

# ================================================================
# DGP  (log_sales 단위: log(만원) — 3억=log(30000)=10.31)
# 학습용 시뮬레이션 데이터 — 실제 신용정보가 아니며, 계수 추정에만 사용.
# ================================================================
def generate_data(n=2000, seed=42):
    rng  = np.random.default_rng(seed)
    # 거시 4개(gdp_growth·rate_change·industry_idx·material_idx)는 macro_calib.py 실측
    # 모멘트로 캘리브. macro_calib.py가 없으면 기존 합성 기본값(1.0/1.2, 0.0/0.5, 100/10,
    # 100/15)으로 자동 폴백한다. fx·station_dist·industry_prod_idx는 실측 대상 아님(기존 유지).
    gdp_m, gdp_s = _macro_moment("gdp_growth", 1.0, 1.2)
    rate_m, rate_s = _macro_moment("rate_change", 0.0, 0.5)
    ind_m, ind_s = _macro_moment("industry_idx", 100.0, 10.0)
    mat_m, mat_s = _macro_moment("material_idx", 100.0, 15.0)

    gdp  = rng.normal(gdp_m, gdp_s, n);  rate = rng.normal(rate_m, rate_s, n)
    ind  = rng.normal(ind_m, ind_s, n);  fx   = rng.normal(0.0, 3.0, n)
    mat  = rng.normal(mat_m, mat_s, n);  mgmt = rng.normal(0.0, 1.0, n)

    dist   = rng.uniform(50, 1500, n)
    dist_z = (dist - STATION_REF_M) / STATION_SCALE_M          # 교통접근성(외생 IV)
    ind_prod = rng.normal(100, 8, n)                            # 업종 생산지수(외생 IV)

    # 매출 방정식 (내생성: mgmt→ls / 도구: 거시4 + 역거리 + 업종생산지수)
    ls = (9.5 + 0.20*(gdp-1.0) - 0.15*rate
          + 0.015*(ind-100) - 0.008*fx - 0.003*(mat-100)
          - 0.12*dist_z + 0.010*(ind_prod-100)
          + 0.80*mgmt + rng.normal(0, 0.5, n))

    cash = np.clip(0.15+0.05*mgmt-0.03*rate+0.01*(gdp-1.0)+rng.normal(0,.05,n), 0.01, 0.80)
    eq_r = np.clip(0.45+0.08*mgmt-0.02*rate               +rng.normal(0,.08,n), 0.05, 0.95)
    curr = np.clip(1.50+0.20*mgmt                          +rng.normal(0,.30,n), 0.30, 5.0)
    icov = np.clip(3.00+0.50*mgmt+0.10*(gdp-1.0)          +rng.normal(0,.50,n), 0.50, 10.0)
    at_  = np.clip(1.20+0.15*mgmt+0.05*(gdp-1.0)-0.04*rate+rng.normal(0,.30,n), 0.10, 5.0)
    eg   = np.clip(0.05+0.08*mgmt+0.02*(gdp-1.0)          +rng.normal(0,.10,n), -0.50, 0.50)

    lat  = (4.5 - 0.40*ls - 0.50*cash - 0.30*eq_r - 0.20*curr
            - 0.20*icov - 0.15*at_ - 0.10*eg - 0.50*mgmt + rng.normal(0, 1, n))

    import pandas as pd
    return pd.DataFrame({
        "gdp_growth":gdp, "rate_change":rate, "industry_idx":ind,
        "fx_change":fx, "material_idx":mat, "station_dist_z":dist_z,
        "industry_prod_idx":ind_prod, "log_sales":ls,
        "cash_ratio":cash, "equity_ratio":eq_r, "current_ratio":curr,
        "interest_cov":icov, "asset_turnover":at_, "equity_growth":eg,
        "delinquent":(lat > 0).astype(int),
    })

# ================================================================
# 모델 학습
# ================================================================
# λ(nu 혼합) — 공정성↔정확성 손잡이. 예측 시 nu(경영능력 프록시)를 얼마나 반영할지.
#   0.0 = 규모중립 최대(공정 우선, 현재값) / 1.0 = 풀 IV(예측력 최대, 규모의존↑)
NU_MIX = 0.0
_FIRST_STAGE_BETA = None   # train_model 이 채우는 1단계 OLS 계수 (예측 시 nu 계산용)


def train_model(n=2000, seed=42):
    """반환: (beta2_iv, beta_ols, F_stat, OVB_pct)"""
    df = generate_data(n=n, seed=seed)

    X1 = add_const(df[IV_COLS + CTRL_COLS].values)
    s1 = ols_fit(X1, df["log_sales"].values)
    nu = s1["resid"]

    global _FIRST_STAGE_BETA
    _FIRST_STAGE_BETA = s1["beta"]

    X2    = add_const(np.hstack([df[["log_sales"] + CTRL_COLS].values, nu[:, None]]))
    y2    = df["delinquent"].values.astype(float)
    beta2 = probit_fit(X2, y2)

    X_ols    = add_const(df[["log_sales"] + CTRL_COLS].values)
    beta_ols = probit_fit(X_ols, y2)

    k_iv = len(IV_COLS); n_, k_ = X1.shape
    rss_r = ols_fit(add_const(df[CTRL_COLS].values), df["log_sales"].values)["resid"]
    rss_f = s1["resid"]
    F_stat = ((rss_r @ rss_r - rss_f @ rss_f) / k_iv) / (rss_f @ rss_f / (n_ - k_))
    OVB    = beta_ols[1] - beta2[1]
    return beta2, beta_ols, float(F_stat), float(abs(OVB / beta2[1]) * 100)

# ================================================================
# 예측 함수
# ================================================================
def _predict(beta, row):
    eta = float(np.dot(row, beta))
    return float(np.clip(norm_cdf(np.array([eta])), 1e-6, 1-1e-6).flat[0])

def iv_prob(beta2, firm, nu=0.0):
    row = [1.0, firm["log_sales"],
           firm["cash_ratio"], firm["equity_ratio"], firm["current_ratio"],
           firm["interest_cov"], firm["asset_turnover"], firm["equity_growth"],
           float(nu)]
    return _predict(beta2, row)

def ols_prob(beta_ols, firm):
    row = [1.0, firm["log_sales"],
           firm["cash_ratio"], firm["equity_ratio"], firm["current_ratio"],
           firm["interest_cov"], firm["asset_turnover"], firm["equity_growth"]]
    return _predict(beta_ols, row)

# ================================================================
# 신용점수 — 두 가지 뷰 (전통 / 공정)
# ================================================================
def calc_trad_score(beta_ols, firm):
    """전통 신용점수 = 100 × (1 − OLS Probit 연체확률). IV 교정 없음(은행 관점)."""
    p = ols_prob(beta_ols, firm)
    return float(np.clip(100.0 * (1.0 - p), 0.0, 100.0))

def calc_context_score(fair_final, sangkwon_score=None, alpha=0.30):
    """
    3번째 점수 — 공정(IV)점수에 상권(CSS) 환경변수를 반영한 '환경조정 점수'.
    전통·공정 점수를 대체하는 최종 결론이 아니라, 세 번째 관점으로 나란히 제시한다.
    점수 = (1-α)×공정점수 + α×상권점수, α=0.30(비중 유지).
    sangkwon_score가 None이면(CSV·네이버API 미가용) 공정점수를 그대로 반환한다(안전 폴백).
    반환: {"score", "used_sangkwon"(bool), "alpha"}
    """
    fair_final = float(fair_final)
    if sangkwon_score is None:
        return {"score": fair_final, "used_sangkwon": False, "alpha": 0.0}
    blended = (1.0 - alpha) * fair_final + alpha * float(sangkwon_score)
    return {"score": float(np.clip(blended, 0.0, 100.0)), "used_sangkwon": True, "alpha": alpha}


def calc_fair_score(beta2, firm_input):
    """
    공정 신용점수 = 100 × (1 − IV Probit 연체확률).
    전통점수와 유일한 차이는 IV 내생성 교정 여부. 규모·경기 편향이 빠진 순수 실력 점수.
    반환: {"prob", "final"}  (외부충격 복원·환경가점 없음 — 상권 엔진이 별도 담당)
    """
    firm_eval = {
        "log_sales":      firm_input["log_sales"],
        "cash_ratio":     firm_input["cash_ratio"],
        "equity_ratio":   firm_input["equity_ratio"],
        "current_ratio":  firm_input["current_ratio"],
        "interest_cov":   firm_input["interest_cov"],
        "asset_turnover": firm_input["asset_turnover"],
        "equity_growth":  firm_input["equity_growth"],
    }
    # λ(NU_MIX)만큼 nu(경영능력 프록시)를 반영. nu = log_sales − (1단계 예측).
    # 거시·입지·업종지수는 기준값으로 두어 '경기변동 제거 후 초과매출'만 잡는다.
    nu_val = 0.0
    if _FIRST_STAGE_BETA is not None and NU_MIX != 0.0:
        # x1 순서 = const + IV_COLS + CTRL_COLS
        x1 = [1.0,
              MACRO_REF["gdp_growth"], MACRO_REF["rate_change"],
              MACRO_REF["industry_idx"], MACRO_REF["material_idx"],
              0.0,                                   # station_dist_z 기준=0
              MACRO_REF["industry_prod_idx"],
              firm_eval["cash_ratio"], firm_eval["equity_ratio"],
              firm_eval["current_ratio"], firm_eval["interest_cov"],
              firm_eval["asset_turnover"], firm_eval["equity_growth"]]
        nu_val = float(firm_eval["log_sales"] - np.dot(_FIRST_STAGE_BETA, x1))

    p     = iv_prob(beta2, firm_eval, nu=NU_MIX * nu_val)
    final = float(np.clip(100.0 * (1.0 - p), 0.0, 100.0))
    return {"prob": p, "final": final}

# ================================================================
# 등급 테이블
# ================================================================
# ⚠️ [예시 가정값 — 실측 보정 아님] 등급 컷·금리는 시연용이며 실데이터 캘리브레이션 전.
GRADE_TABLE = [
    (90,"AAA","최우량"),(80,"AA","우량"),(70,"A","양호"),
    (60,"BBB","보통"), (50,"BB","주의"),(40,"B","경계"),
    (0, "CCC","고위험"),
]
GRADE_ORDER = ["AAA","AA","A","BBB","BB","B","CCC"]
GRADE_RATE  = {"AAA":3.0,"AA":3.5,"A":4.0,"BBB":5.0,"BB":6.5,"B":8.5,"CCC":11.0}
GRADE_COLOR = {"AAA":"#0F6E56","AA":"#1D9E75","A":"#5DCAA5",
               "BBB":"#BA7517","BB":"#EF9F27","B":"#D85A30","CCC":"#993C1D"}

def assign_grade(score):
    for thr, g, lbl in GRADE_TABLE:
        if score >= thr: return g, lbl
    return "CCC","고위험"

# 입력창 초기값(일반적 평균 소상공인)
DEFAULT_FIRM = {
    "log_sales":math.log(3.0*10000), "cash_ratio":0.15, "equity_ratio":0.55,
    "current_ratio":1.40, "interest_cov":2.80, "asset_turnover":1.20,
    "equity_growth":0.04,
}

# ================================================================
# 단위 변환
# ================================================================
def sales_to_log(sales_억): return math.log(max(float(sales_억),0.001)*10000)
def log_to_sales(log_sales): return math.exp(log_sales)/10000

# ================================================================
# HTML 리포트 (전통 vs 공정, 2점수)
# ================================================================
def make_html_report(firm_name, trad, fair_r, firm_input, loan_b):
    tg, tl = assign_grade(trad)
    fg, fl = assign_grade(fair_r["final"])
    tr, fr = GRADE_RATE[tg], GRADE_RATE[fg]
    excess = max(0, (tr-fr)/100*loan_b)*10000
    gd     = GRADE_ORDER.index(tg) - GRADE_ORDER.index(fg)
    dt     = (f"+{gd}등급 상향" if gd>0 else ("동일 등급" if gd==0 else f"{abs(gd)}등급"))
    date_str = datetime.date.today().strftime("%Y년 %m월 %d일")
    opinions = {
        "AAA":"경기와 무관하게 최우량 신용도를 유지합니다.",
        "AA": "안정적 상환 역량을 보유하고 있습니다.",
        "A":  "양호한 재무 체력을 보유합니다. 대출 승인을 권고합니다.",
        "BBB":"평균 수준 신용도입니다.",
        "BB": "경기 변동의 영향이 일부 있습니다. 정책금융 지원 검토를 권고합니다.",
        "B":  "경기 요인 제거 후에도 개선 여지가 있습니다.",
        "CCC":"소상공인 신용 개선 지원 프로그램을 활용하세요.",
    }
    return f"""<!DOCTYPE html><html lang="ko">
<head><meta charset="UTF-8"><title>공정신용평가 - {firm_name}</title>
<style>
body{{font-family:"Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
     max-width:740px;margin:48px auto;color:#2C2C2A;line-height:1.7;font-size:14px}}
h1{{font-size:20px;color:#0F6E56;border-bottom:2px solid #0F6E56;padding-bottom:8px}}
h2{{font-size:14px;color:#0F6E56;margin:22px 0 8px;padding-left:10px;border-left:3px solid #1D9E75}}
table{{width:100%;border-collapse:collapse;margin:6px 0}}
th,td{{padding:7px 12px;border:1px solid #D3D1C7;font-size:13px;text-align:left}}
th{{background:#E1F5EE;color:#085041;font-weight:500;width:40%}}
.row{{display:flex;gap:16px;margin:8px 0}}
.box{{flex:1;padding:18px;border-radius:10px;text-align:center;border:1px solid #D3D1C7}}
.box-old{{background:#FAECE7}}.box-new{{background:#E1F5EE}}
.num{{font-size:38px;font-weight:700;margin:4px 0}}
.badge{{display:inline-block;padding:3px 14px;border-radius:20px;font-size:13px;font-weight:600;color:white;margin-top:6px}}
.banner{{background:#E1F5EE;border:1px solid #9FE1CB;border-radius:8px;padding:10px 16px;margin:10px 0;font-size:13px;color:#085041}}
.footer{{font-size:11px;color:#888;margin-top:36px;border-top:1px solid #D3D1C7;padding-top:10px}}
button{{display:block;margin:20px auto 0;padding:10px 28px;background:#0F6E56;color:white;border:none;border-radius:8px;font-size:14px;cursor:pointer}}
@media print{{button{{display:none}}}}
</style></head><body>
<h1>소상공인 공정신용 평가 확인서</h1>
<p style="color:#888;font-size:12px">신용캐드 (Credit CAED) | 평가일: {date_str} | 기준연도: 2025년</p>
<h2>평가 대상</h2>
<table>
<tr><th>상호</th><td>{firm_name}</td></tr>
<tr><th>평가 기준</th><td>최근 1년(2025년) 재무정보</td></tr>
</table>
<h2>입력 재무정보</h2>
<table>
<tr><th>현금성자산비율</th><td>{firm_input['cash_ratio']*100:.1f}%</td></tr>
<tr><th>자기자본비율</th><td>{firm_input['equity_ratio']*100:.1f}%</td></tr>
<tr><th>유동비율</th><td>{firm_input['current_ratio']:.2f}</td></tr>
<tr><th>이자보상배율</th><td>{firm_input['interest_cov']:.1f}</td></tr>
<tr><th>총자산회전율</th><td>{firm_input['asset_turnover']:.2f}</td></tr>
</table>
<h2>평가 결과 비교</h2>
<div class="row">
<div class="box box-old">
<div style="font-size:11px;color:#993C1D">① 기존 신용평가 (OLS)</div>
<div class="num" style="color:#D85A30">{trad:.0f}</div>
<div><span class="badge" style="background:{GRADE_COLOR.get(tg,'#888')}">{tg} · {tl}</span></div>
<div style="font-size:11px;color:#73726c;margin-top:6px">금리 {tr:.1f}%</div>
</div>
<div class="box box-new">
<div style="font-size:11px;color:#0F6E56">② 공정평가 (IV · 경기·규모 편향 제거)</div>
<div class="num" style="color:#0F6E56">{fair_r['final']:.0f}</div>
<div><span class="badge" style="background:{GRADE_COLOR.get(fg,'#888')}">{fg} · {fl}</span></div>
<div style="font-size:11px;color:#73726c;margin-top:6px">금리 {fr:.1f}%</div>
</div>
</div>
<div class="banner">
은행 평가 <b>{tg}({tl})</b> → 공정평가 <b>{fg}({fl})</b> ({dt}) |
대출 {loan_b:.1f}억원 기준 <b>예시 금리 가정 시</b> 연 약 {excess:.0f}만원 차이
</div>
<h2>점수 구성</h2>
<table>
<tr><th>② 공정 신용점수 (IV Probit)</th><td><b>{fair_r['final']:.1f}점</b> = 100 × (1 − 연체확률 {fair_r['prob']*100:.1f}%)</td></tr>
</table>
<h2>종합 의견</h2>
<p style="background:#f9f9f7;padding:12px;border-radius:6px;font-size:13px">
{firm_name}의 은행식 평가(OLS) 신용도는 <b>{tg}등급({tl})</b>이며,
경기·규모 편향을 제거한 공정평가(IV)는 <b>{fg}등급({fl})</b>입니다.<br><br>
{opinions.get(fg,"")}
</p>
<div class="footer">본 평가서는 신용캐드(Credit CAED) IV 기반 공정신용 모델 참고 자료입니다.
공식 금융기관 신용평가를 대체하지 않습니다. |
<b>등급·금리·이자절감액은 예시 가정값이며, 점수는 시뮬레이션(합성) 데이터로 학습된
프로토타입 결과입니다.</b> | 거시환경 기준: 한국은행 2025년 국민소득(잠정) 통계</div>
<button onclick="window.print()">브라우저 인쇄 / PDF 저장</button>
</body></html>"""

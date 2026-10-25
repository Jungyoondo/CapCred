"""
신용캐드 (Credit CAED) - Streamlit 앱  [디자인 리프레시]
========================================
실행: streamlit run app.py
설치: pip install streamlit numpy pandas

로직·모델 호출은 기존과 동일. 시각 레이어만 목업(로고+MVP 브랜딩, 아이콘 섹션 카드,
2-업 점수 카드, 3단계 인디케이터)에 맞춰 정돈했다. 흐름은 입력 → 분석 → 결과 3단계.
"""

import math, datetime
import streamlit as st
import numpy as np

import model as M
from model import (
    train_model, calc_trad_score, calc_fair_score, calc_context_score,
    assign_grade, make_html_report,
    sales_to_log, log_to_sales,
    DEFAULT_FIRM, GRADE_RATE, GRADE_ORDER, GRADE_COLOR,
)
from fetch_kosis import get_industry_prod_idx
from fetch_seoul import get_district_closure_rate, get_industry_closure_stats
from code_tables import get_gu_list, get_dong_list, get_industry_list, get_objl1_code
from sangkwon_engine import get_sangkwon_score

# ================================================================
# 0. 페이지 설정 + 스타일
# ================================================================
st.set_page_config(
    page_title="신용캐드 · 소상공인 공정신용 진단",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""<style>
/* ── 캔버스 ── */
.stApp { background:#FBFBF9; }
/* Streamlit 기본 상단 헤더바가 콘텐츠를 가리지 않도록 투명 처리 */
header[data-testid="stHeader"] { background:transparent; }
[data-testid="stToolbar"] { right:0.5rem; }
.block-container { padding-top:5rem; max-width:640px; }

/* ── 가독성 방어: 다크 테마로 떠도 글씨/입력창이 보이도록 강제 ── */
.stApp h1, .stApp h2, .stApp h3, .stApp h4 { color:#123F33 !important; }
[data-testid="stWidgetLabel"] label, [data-testid="stWidgetLabel"] p { color:#2C2C2A !important; }
.stApp .stMarkdown p, .stApp .stMarkdown li { color:#2C2C2A; }
[data-testid="stMetricValue"] { color:#123F33 !important; }
[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p { color:#73726C !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color:#9C9B90 !important; }
/* 입력 위젯 흰 배경 + 어두운 글씨 */
input, textarea { background:#FFFFFF !important; color:#1A1A18 !important; }
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div {
  background:#FFFFFF !important; color:#1A1A18 !important; }
div[data-baseweb="select"] div, div[data-baseweb="input"] input { color:#1A1A18 !important; }
[data-testid="stNumberInput"] button { background:#F3F2EC !important; color:#1B4C3E !important; }

/* ── 브랜드 헤더 ── */
.brand { display:flex; align-items:center; gap:11px; }
.brand-mark { width:36px; height:36px; border-radius:10px;
  background:linear-gradient(135deg,#22A97E,#0F6E56);
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-size:19px; box-shadow:0 2px 8px rgba(15,110,86,.25); }
.brand-title { font-size:17px; font-weight:700; color:#123F33; line-height:1.15; }
.brand-sub   { font-size:11px; color:#9C9B90; letter-spacing:.2px; margin-top:1px; }
.step-badge  { margin-left:auto; background:#E4F6EF; color:#0F6E56;
  font-size:12px; font-weight:600; padding:5px 14px; border-radius:20px; }

/* ── 단계 바 ── */
.stepbar { display:flex; gap:7px; margin:18px 0 6px; }
.stepbar .seg { flex:1; }
.stepbar .lbl { font-size:12px; margin-bottom:7px; color:#BBBAAF; display:flex; gap:5px; }
.stepbar .lbl.on   { color:#0F6E56; font-weight:600; }
.stepbar .lbl.done { color:#1D9E75; font-weight:500; }
.stepbar .bar { height:4px; border-radius:3px; background:#EAE8DF; }
.stepbar .bar.on   { background:#0F6E56; }
.stepbar .bar.done { background:#1D9E75; }

/* ── 입력 섹션 카드 (st.container(border=True)) ── */
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius:14px !important; border:1px solid #EAE8DF !important;
  background:#FFFFFF; padding:2px 2px; }
.sec-title { font-size:13.5px; font-weight:700; color:#1B4C3E;
  display:flex; align-items:center; gap:7px; margin:2px 0 2px; }
.sec-hint  { font-size:11px; color:#9C9B90; margin:-4px 0 6px; }

/* ── 버튼 ── */
.stButton>button, .stDownloadButton>button {
  border-radius:11px; font-weight:600; padding:11px 0; border:1px solid transparent; }
.stButton>button[kind="primary"], .stDownloadButton>button {
  background:#0F6E56; color:#fff; }
.stButton>button[kind="primary"]:hover, .stDownloadButton>button:hover {
  background:#0C5B48; color:#fff; }
.stButton>button[kind="secondary"] {
  background:#fff; color:#0F6E56; border-color:#CFE9DF; }

/* ── 점수 카드 (2-업 히어로) ── */
.hero { display:flex; align-items:stretch; gap:11px; margin:2px 0 4px; }
.scard { flex:1; border-radius:15px; padding:20px 14px; text-align:center; border:1px solid #E7E5DC; }
.scard .cap { font-size:11px; font-weight:600; }
.scard .num { font-size:42px; font-weight:800; line-height:1.1; margin-top:3px; }
.scard .num small { font-size:15px; font-weight:600; }
.scard .badge { display:inline-block; padding:3px 13px; border-radius:16px;
  font-size:12px; font-weight:600; color:#fff; margin-top:7px; }
.scard-old { background:#FBEEE9; }
.scard-new { background:#E4F6EF; }
.arrow { display:flex; align-items:center; color:#C4C3B8; font-size:24px; }
.uplift { text-align:center; color:#0F6E56; font-weight:700; font-size:12.5px; margin:4px 0 2px; }

/* ── 환경조정 점수(3번째 점수) 카드 ── */
.finalcard { background:#FFF6DD; border:1px solid #ECD495; border-radius:15px;
  padding:17px; text-align:center; margin-top:12px; }
.finalcard .num { font-size:38px; font-weight:800; color:#B8860B; line-height:1.1; }

/* ── 배너 ── */
.banner { background:#E4F6EF; border:1px solid #A6E3CF; border-radius:12px;
  padding:13px 16px; margin:14px 0; font-size:13px; color:#0C5B48;
  display:flex; gap:9px; align-items:flex-start; }

/* ── 리포트 확인서 ── */
.rep-sec { font-size:13px; font-weight:700; color:#1B4C3E; margin:16px 0 6px;
  display:flex; align-items:center; gap:7px; }
</style>""", unsafe_allow_html=True)


# ================================================================
# 1. 모델 캐시
# ================================================================
@st.cache_resource(show_spinner="공정신용 모델 초기화 중 (최초 1회)…")
def get_model():
    return train_model(n=2000, seed=42)


@st.cache_data(show_spinner=False, ttl=1800)
def _cached_sangkwon_score(store_query, industry_name):
    """상권 CSS 조회는 느리므로(네이버 API 포함) 캐싱한다. 실패 시 None(안전 폴백)."""
    return get_sangkwon_score(store_query, industry_name)


def compute_scores(firm_input):
    """firm_input → 전통·공정·최종(상권반영) 점수·등급·금리·이자절감액."""
    beta2, beta_ols, F_stat, OVB_pct = get_model()
    trad_s = calc_trad_score(beta_ols, firm_input)
    fair_r = calc_fair_score(beta2, firm_input)
    tg, tl = assign_grade(trad_s)
    fg, fl = assign_grade(fair_r["final"])
    tr, fr = GRADE_RATE[tg], GRADE_RATE[fg]
    loan_b = firm_input["loan_b"]

    # 상권(CSS) 점수 — store_query 없거나 조회 실패 시 None → 공정점수 그대로 폴백
    store_query = firm_input.get("store_query")
    css_score = _cached_sangkwon_score(store_query, firm_input.get("industry_name")) \
        if store_query else None
    ctx = calc_context_score(fair_r["final"], css_score, alpha=0.30)
    xg, xl = assign_grade(ctx["score"])
    xr = GRADE_RATE[xg]

    return dict(
        trad_s=trad_s, fair_r=fair_r, tg=tg, tl=tl, fg=fg, fl=fl,
        tr=tr, fr=fr, loan_b=loan_b, F_stat=F_stat, OVB_pct=OVB_pct,
        excess=max(0, (tr - fr) / 100 * loan_b) * 10000,
        gd=GRADE_ORDER.index(tg) - GRADE_ORDER.index(fg),
        css_score=css_score, ctx=ctx, xg=xg, xl=xl, xr=xr,
    )


# ================================================================
# 2. 세션 상태
# ================================================================
_defaults = dict(step=1, firm_input=None, firm_name="평가 기업")
for k, v in _defaults.items():
    st.session_state.setdefault(k, v)

step = st.session_state.step

# ================================================================
# 3. 브랜드 헤더 + 단계 바
# ================================================================
STEP_LABELS = ["입력", "분석", "결과"]
badge = f"{step}/3 {STEP_LABELS[step-1]}"
st.markdown(f"""
<div class="brand">
  <div class="brand-mark">✦</div>
  <div>
    <div class="brand-title">신용캐드</div>
    <div class="brand-sub">공정신용 진단 MVP</div>
  </div>
  <div class="step-badge">{badge}</div>
</div>""", unsafe_allow_html=True)

seg = '<div class="stepbar">'
for i, lbl in enumerate(STEP_LABELS, 1):
    cls = "on" if step == i else ("done" if step > i else "")
    ico = "✓ " if step > i else f"{i}. "
    seg += f'<div class="seg"><div class="lbl {cls}">{ico}{lbl}</div><div class="bar {cls}"></div></div>'
seg += "</div>"
st.markdown(seg, unsafe_allow_html=True)


def sec(icon, title, hint=None):
    st.markdown(f'<div class="sec-title">{icon} {title}</div>', unsafe_allow_html=True)
    if hint:
        st.markdown(f'<div class="sec-hint">{hint}</div>', unsafe_allow_html=True)


# ================================================================
# STEP 1 — 재무정보 입력
# ================================================================
if step == 1:
    st.markdown("### 사업체 재무정보를 입력하세요")
    st.markdown('<div class="sec-hint">최근 결산(2025년) 기준 재무 상황과 입지 정보를 입력하면 '
                '외부 공정데이터와 결합해 평가합니다.</div>', unsafe_allow_html=True)

    D = DEFAULT_FIRM

    with st.container(border=True):
        sec("🏢", "기본 정보")
        firm_name = st.text_input("상호명", placeholder="예: 한강뷰 식당")
        industry = st.selectbox("업종", get_industry_list(),
                                help="업종별 생산지수(KOSIS)·상권 폐업률(서울시) 조회에 사용됩니다")
        sales_b = st.number_input("연 매출액 (억원)", min_value=0.1, max_value=500.0,
            value=float(f"{log_to_sales(D['log_sales']):.1f}"), step=0.1,
            help="최근 1년간 총 매출액")

    with st.container(border=True):
        sec("📊", "재무 정보")
        c1, c2 = st.columns(2)
        with c1:
            cash_r = st.number_input("현금·예금 비율 (%)", min_value=0.0, max_value=100.0,
                value=D["cash_ratio"]*100, step=1.0, format="%.0f",
                help="지금 당장 쓸 수 있는 현금·예금이 유동자산에서 차지하는 비율") / 100
            curr_r = st.number_input("유동비율 (%)", min_value=0.0, max_value=1000.0,
                value=D["current_ratio"]*100, step=5.0, format="%.0f",
                help="1년 안에 갚을 돈 대비 현금화 가능 자산 비율 (100% 이상 권장)") / 100
        with c2:
            eq_r = st.number_input("자기자본비율 (%)", min_value=0.0, max_value=100.0,
                value=D["equity_ratio"]*100, step=1.0, format="%.0f",
                help="총자산 중 빚이 아닌 순수 내 돈의 비율") / 100
            eg = st.number_input("최근 1년 자기자본 증감률 (%)", min_value=-100.0, max_value=100.0,
                value=D["equity_growth"]*100, step=1.0, format="%.0f",
                help="작년 대비 내 돈(자기자본)이 늘었는지 줄었는지") / 100

    with st.container(border=True):
        sec("💰", "수익 및 운영 정보")
        c3, c4 = st.columns(2)
        with c3:
            icov = st.number_input("이자보상배율 (배)", min_value=0.0, max_value=20.0,
                value=D["interest_cov"], step=0.1, format="%.1f",
                help="영업이익이 이자비용의 몇 배인지 (1.0 미만이면 이자도 못 갚는 상태)")
        with c4:
            at_ = st.number_input("총자산회전율 (배)", min_value=0.0, max_value=10.0,
                value=D["asset_turnover"], step=0.1, format="%.1f",
                help="매출액이 총자산의 몇 배인지")
        loan_b = st.number_input("희망 대출 규모 (억원)", min_value=0.1, max_value=50.0,
            value=0.8, step=0.1, help="이자 절감 효과 계산에 사용됩니다")

    with st.container(border=True):
        sec("📍", "지역·업종 정보", "사장님 실력과 무관한 '외부 조건'입니다. 공정평가에서 별도 반영됩니다.")
        c5, c6 = st.columns(2)
        with c5:
            gu_name = st.selectbox("자치구", get_gu_list(), help="서울 소재 사업장만 실시간 조회 가능")
            station_m = st.number_input("가장 가까운 지하철역까지 거리 (m)",
                min_value=0.0, max_value=3000.0, value=500.0, step=50.0, format="%.0f",
                help="역과 가까울수록 유동인구가 많아 매출에 유리 (교통접근성 도구변수)")
        with c6:
            dong_options = get_dong_list(gu_name)
            dong_name = st.selectbox("행정동",
                dong_options if dong_options else ["(행정동 코드표 미등록 — 기준값 사용)"],
                help="행정동 코드표가 없으면 목록이 비어 기준값으로 대체됩니다")
        c7, c8 = st.columns(2)
        with c7:
            year = st.selectbox("조회 연도", [2025, 2024, 2023], index=0)
        with c8:
            quarter = st.selectbox("조회 분기", [1, 2, 3, 4], index=3)

    yyqu = f"{year}{quarter}"
    yyyymm = f"{year}{quarter*3:02d}"

    # ── 실시간 API 조회 ──
    objl1_code = get_objl1_code(industry)
    ind_prod_idx, ind_live = get_industry_prod_idx(objl1_code, yyyymm, prd_se="M")
    dist_cls_rate, dist_live = get_district_closure_rate(gu_name, dong_name, industry, yyqu)
    clsr_ref, clsr_sd = get_industry_closure_stats(industry, yyqu)

    with st.container(border=True):
        sec("🌐", "실시간 외부지표")
        a1, a2 = st.columns(2)
        a1.metric("업종 생산지수 (KOSIS)", f"{ind_prod_idx:.1f}",
                  "실시간 조회됨" if ind_live else "기준값 대체 중")
        a2.metric("상권 폐업률 (참고)", f"{dist_cls_rate:.1f}%",
                  "실시간 조회됨" if dist_live else "기준값 대체 중")
        if not (ind_live and dist_live):
            st.warning("일부 실시간 데이터를 불러오지 못해 전국 평균 기준값으로 대체되었습니다.")

    if st.button("공정신용 진단 실행  →", type="primary", use_container_width=True):
        st.session_state.firm_input = {
            "log_sales": sales_to_log(sales_b), "cash_ratio": cash_r, "equity_ratio": eq_r,
            "current_ratio": curr_r, "interest_cov": icov, "asset_turnover": at_,
            "equity_growth": eg, "station_m": station_m,
            "industry_prod_idx": ind_prod_idx, "district_closure_rate": dist_cls_rate,
            "clsr_ref": clsr_ref, "clsr_sd": clsr_sd, "loan_b": loan_b,
            "industry_name": industry,
            "store_query": f"{gu_name} {dong_name}" if dong_name and "미등록" not in dong_name else gu_name,
        }
        st.session_state.firm_name = firm_name or "평가 기업"
        st.session_state.step = 2
        st.rerun()


# ================================================================
# STEP 2 — 분석 결과
# ================================================================
elif step == 2:
    fi = st.session_state.firm_input
    name = st.session_state.firm_name
    R = compute_scores(fi)
    fair_r = R["fair_r"]

    st.markdown("### 공정신용 진단 결과")
    st.markdown(f'<div class="sec-hint">기존 금융권과 공정평가를 비교합니다 · {name} · 기준연도 2025년</div>',
                unsafe_allow_html=True)

    # 히어로: 기존 → 공정
    st.markdown(f"""
    <div class="hero">
      <div class="scard scard-old">
        <div class="cap" style="color:#B4552E">기존 평가</div>
        <div class="num" style="color:#D85A30">{R['trad_s']:.0f}<small>점</small></div>
        <span class="badge" style="background:{GRADE_COLOR.get(R['tg'],'#888')}">{R['tg']} · {R['tl']}</span>
      </div>
      <div class="arrow">→</div>
      <div class="scard scard-new">
        <div class="cap" style="color:#0F6E56">공정 평가</div>
        <div class="num" style="color:#0F6E56">{fair_r['final']:.0f}<small>점</small></div>
        <span class="badge" style="background:{GRADE_COLOR.get(R['fg'],'#888')}">{R['fg']} · {R['fl']}</span>
      </div>
    </div>""", unsafe_allow_html=True)
    if R["gd"] > 0:
        st.markdown(f'<div class="uplift">+{R["gd"]}등급 상향</div>', unsafe_allow_html=True)

    if R["gd"] > 0:
        st.markdown(f"""<div class="banner"><span>✓</span>
          <span>현재 <b>과소평가</b> 상태일 가능성이 있습니다 — 기존 평가 대비
          <b>+{R['gd']}등급</b>.</span></div>""", unsafe_allow_html=True)
    else:
        st.markdown("""<div class="banner"><span>✓</span>
          <span>기존 평가와 공정평가가 동일 등급입니다. 과소평가 신호는 발견되지 않았습니다.</span></div>""",
                    unsafe_allow_html=True)

    # 3번째 점수: 환경변수(상권 CSS) 반영 점수 — 공정점수를 대체하는 결론이 아니라 참고용 세 번째 관점
    with st.container(border=True):
        sec("🌱", "③ 환경조정 점수", "공정점수에 상권(CSS) 환경변수를 30% 반영한 참고 점수입니다")
        if R["ctx"]["used_sangkwon"]:
            st.markdown(f"""
            <div class="finalcard">
              <div style="font-size:11px;color:#8A6D1E">공정({R['fair_r']['final']:.0f}) x 70% + 상권환경({R['css_score']:.0f}) x 30%</div>
              <div class="num">{R['ctx']['score']:.0f}점</div>
              <span class="badge" style="background:{GRADE_COLOR.get(R['xg'],'#888')};color:#fff">{R['xg']} · {R['xl']}</span>
              <div style="font-size:11px;color:#73726c;margin-top:6px">참고 금리(예시) {R['xr']:.1f}%</div>
            </div>""", unsafe_allow_html=True)
        else:
            st.info("상권(CSS) 데이터를 불러오지 못해 3번째 점수는 공정점수와 동일하게 표시됩니다. "
                    "(상권 CSV·네이버 API 키가 로컬에 없으면 발생하는 정상적인 폴백입니다.)")
            st.markdown(f"""
            <div class="finalcard">
              <div style="font-size:11px;color:#8A6D1E">공정점수 그대로 (상권환경 미반영)</div>
              <div class="num">{R['ctx']['score']:.0f}점</div>
              <span class="badge" style="background:{GRADE_COLOR.get(R['xg'],'#888')};color:#fff">{R['xg']} · {R['xl']}</span>
            </div>""", unsafe_allow_html=True)

    # 비교 요약
    with st.container(border=True):
        sec("📋", "비교 요약")
        st.markdown("""
- 시설 투자 비중이 높은 업종 특성상, 전통 평가는 초기 투자 부담을 위험으로 반영합니다.
- 매출의 내생성(경영능력 혼입)을 제거하면 공정 점수가 더 높게 나타납니다.
- 공정평가는 외부 경기충격을 참고해 추가 실력 여지를 보여줍니다.
""")

    # 대출 효과
    with st.container(border=True):
        sec("💵", "대출 효과 (예시 가정)")
        rc1, rc2, rc3 = st.columns([2, 1, 2])
        rc1.markdown(f'<div style="text-align:center"><div style="font-size:11px;color:#9C9B90">기존 금리</div>'
                     f'<div style="font-size:22px;font-weight:700;color:#D85A30">{R["tr"]:.1f}%</div></div>',
                     unsafe_allow_html=True)
        rc2.markdown('<div style="text-align:center;font-size:20px;color:#C4C3B8;padding-top:14px">→</div>',
                     unsafe_allow_html=True)
        rc3.markdown(f'<div style="text-align:center"><div style="font-size:11px;color:#9C9B90">공정평가 기준 금리</div>'
                     f'<div style="font-size:22px;font-weight:700;color:#0F6E56">{R["fr"]:.1f}%</div></div>',
                     unsafe_allow_html=True)
        if R["excess"] > 0:
            st.markdown(f'<div style="text-align:center;margin-top:8px;font-size:13px;color:#0C5B48">'
                        f'💸 예상 연간 이자 절감 약 <b>{R["excess"]:.0f}만원</b> (예시)</div>',
                        unsafe_allow_html=True)
        st.caption("※ 등급·금리·이자절감액은 실측 보정 전 예시 가정값입니다.")

    # 참고 외부지표
    with st.container(border=True):
        sec("🌐", "참고 외부지표")
        e1, e2 = st.columns(2)
        e1.metric("KOSIS 업종 생산지수", f"{fi['industry_prod_idx']:.1f}")
        e2.metric("서울시 상권 폐업률", f"{fi['district_closure_rate']:.1f}%")
        st.caption("외부지표는 참고용 설명자료로 활용됩니다.")

    b1, b2 = st.columns([1, 2])
    if b1.button("← 다시 입력", use_container_width=True):
        st.session_state.step = 1; st.rerun()
    if b2.button("평가 확인서 보기  →", type="primary", use_container_width=True):
        st.session_state.step = 3; st.rerun()


# ================================================================
# STEP 3 — 결과 (평가 확인서)
# ================================================================
elif step == 3:
    fi = st.session_state.firm_input
    name = st.session_state.firm_name
    R = compute_scores(fi)
    fair_r = R["fair_r"]

    st.markdown("### 평가 확인서")
    st.markdown('<div class="sec-hint">금융기관 제출용 설명 리포트 · 기준연도 2025년</div>',
                unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown('<div class="rep-sec">👤 1. 평가 대상</div>', unsafe_allow_html=True)
        st.markdown(f"- 상호: **{name}**\n- 업종: {fi.get('industry_name','—')}\n"
                    f"- 평가 기준: 최근 1년 재무정보 + 외부지표")

        st.markdown('<div class="rep-sec">📊 2. 입력 재무정보</div>', unsafe_allow_html=True)
        st.markdown(
            f"- 현금성자산비율 {fi['cash_ratio']*100:.0f}%\n"
            f"- 자기자본비율 {fi['equity_ratio']*100:.0f}%\n"
            f"- 유동비율 {fi['current_ratio']*100:.0f}%\n"
            f"- 이자보상배율 {fi['interest_cov']:.1f}배\n"
            f"- 총자산회전율 {fi['asset_turnover']:.1f}배")

        st.markdown('<div class="rep-sec">⚖️ 3. 평가 결과 비교</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="hero" style="margin-top:2px">
          <div class="scard scard-old" style="padding:14px">
            <div class="cap" style="color:#B4552E">기존 평가</div>
            <div class="num" style="color:#D85A30;font-size:32px">{R['trad_s']:.0f}</div>
            <span class="badge" style="background:{GRADE_COLOR.get(R['tg'],'#888')}">{R['tg']}</span>
          </div>
          <div class="arrow">→</div>
          <div class="scard scard-new" style="padding:14px">
            <div class="cap" style="color:#0F6E56">공정 평가</div>
            <div class="num" style="color:#0F6E56;font-size:32px">{fair_r['final']:.0f}</div>
            <span class="badge" style="background:{GRADE_COLOR.get(R['fg'],'#888')}">{R['fg']}</span>
          </div>
        </div>""", unsafe_allow_html=True)

        st.markdown('<div class="rep-sec">🌐 4. 참고 외부지표</div>', unsafe_allow_html=True)
        st.markdown(f"- KOSIS 업종 생산지수 {fi['industry_prod_idx']:.1f}\n"
                    f"- 서울시 상권 폐업률 {fi['district_closure_rate']:.1f}%")

        st.markdown('<div class="rep-sec">📝 5. 종합 의견</div>', unsafe_allow_html=True)
        st.markdown(f"기존 외부지표로 보면 낮게 평가될 수 있으나, 업종·상권·경기 요인을 함께 "
                    f"제거한 결과 추가 실력 여지가 있습니다. 공정평가는 낮은 점수만이 "
                    f"낮은 평가의 이유가 아님을 설명하는 보조자료입니다.")

    html_out = make_html_report(name, R["trad_s"], fair_r, fi, R["loan_b"])
    st.download_button("리포트 다운로드 (HTML → PDF 인쇄)",
        data=html_out.encode("utf-8"),
        file_name=f"공정신용_{name}_{datetime.date.today()}.html",
        mime="text/html", type="primary", use_container_width=True)
    st.caption("다운로드 후 브라우저에서 열기 → Ctrl+P → PDF 저장")

    b1, b2 = st.columns([1, 1])
    if b1.button("← 분석으로", use_container_width=True):
        st.session_state.step = 2; st.rerun()
    if b2.button("처음부터 다시", use_container_width=True):
        for k, v in _defaults.items():
            st.session_state[k] = v
        st.rerun()

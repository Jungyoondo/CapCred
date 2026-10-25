"""신용캐드 진단 서비스 함수 - Streamlit 없이 사업 사이트(sites/biz.py)에서 호출 (2026-10-08).

diagnose(params) -> dict
  입력(사장님이 아는 값): sales_b(연매출 억원), cash_pct(현금성자산비율 %), equity_pct(자기자본비율 %),
       current_pct(유동비율 %), icr(이자보상배율 배), turnover(총자산회전율 회), growth_pct(자기자본증가율 %),
       loan_b(희망 대출 억원), industry(업종명, 예: 헬스장), store_query(가까운 역·상권, 예: 성신여대입구역)
  출력: 전통 점수(은행식, OLS Probit) / 공정 점수(IV Probit) / 환경조정 점수(공정 70% + 상권 30%),
       등급·예시 금리·이자 차이, 상권 지표, 업종 연체율(한국은행 실측 참고, 점수엔 미반영).
주의: 핵심 모델은 합성 데이터로 학습한 MVP다(model.generate_data). 등급 컷·금리는 예시 가정값.
     실제 정답으로 확인된 것은 dintel.fair_warning(상장 소형사)의 '규모 편향' 결과뿐이다.
"""
import os
import sys
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import model as M  # noqa: E402

_LOCK = threading.Lock()
_MODEL = None
_CSS_CACHE = {}

# 신용캐드 업종 -> 한국은행 산업대분류(연체율 패널 단위)
INDUSTRY_TO_KSIC = {
    "헬스장": "예술, 스포츠 및 여가관련 서비스업", "피트니스": "예술, 스포츠 및 여가관련 서비스업",
    "요가": "예술, 스포츠 및 여가관련 서비스업", "볼링장": "예술, 스포츠 및 여가관련 서비스업",
    "당구장": "예술, 스포츠 및 여가관련 서비스업", "스터디카페": "교육 서비스업", "독서실": "교육 서비스업",
    "학원": "교육 서비스업", "컴퓨터학원": "교육 서비스업", "연극": "예술, 스포츠 및 여가관련 서비스업",
    "미용실": "협회 및 단체, 수리 및 기타 개인서비스업", "카페": "숙박 및 음식점업", "커피": "숙박 및 음식점업",
    "치킨": "숙박 및 음식점업", "음식점": "숙박 및 음식점업", "편의점": "도매 및 소매업",
}


def _model():
    global _MODEL
    with _LOCK:
        if _MODEL is None:
            _MODEL = M.train_model(n=2000, seed=42)      # 앱과 같은 재현 설정
    return _MODEL


def industry_delinquency(industry):
    """업종 연체율 참고(한국은행 산업별, data/delinq_panel.csv) - 인수인계 3-B '업종 부도율' 실측 버전.
    점수 계산엔 넣지 않는다(가중치가 합성 데이터로 정해져 있어 실측 검증 전엔 섞지 않음)."""
    import pandas as pd
    p = os.path.join(os.path.dirname(_HERE), "data", "delinq_panel.csv")
    unit = INDUSTRY_TO_KSIC.get(str(industry).strip())
    if not unit or not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    d = d[(d["dim"] == "산업") & (d["basis"] == "차주수 기준") & (d["item"] == "전체")]
    if d.empty:
        return None
    last = int(d["year"].max())
    cur = d[d["year"] == last].set_index("unit")["val"]
    if unit not in cur:
        return None
    hist = d[d["unit"] == unit].sort_values("year")
    return {"ksic": unit, "year": last, "rate_pct": float(cur[unit]),
            "rank": int(cur.rank(ascending=False)[unit]), "n_industries": int(len(cur)),
            "all_median_pct": float(cur.median()),
            "trend": [{"year": int(r.year), "rate_pct": float(r.val)} for r in hist.itertuples()],
            "source": "한국은행 산업별 연체율(차주수 기준) - 참고 지표, 점수 미반영"}


def _css(store_query, industry):
    key = (store_query, industry)
    if key in _CSS_CACHE:
        return _CSS_CACHE[key]
    out = {"score": None, "profitability": None}
    try:
        import sangkwon_engine as S
        out["score"] = S.get_sangkwon_score(store_query, industry)
        pr = S.get_profitability_score(S.parse_clean_station_name(store_query), industry)
        out["profitability"] = {"score": float(pr[0]), "avg_sales_won": float(pr[1]), "basis": pr[2]}
    except Exception as e:   # 상권 데이터·네이버 API 실패 -> 공정 점수만(앱과 같은 폴백)
        out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    _CSS_CACHE[key] = out
    return out


def _benchmark(industry, p):
    """10-20 서울 동종 업소의 실제 폐업률(caed/industry_benchmark.py) - 업력·면적은 선택 입력."""
    try:
        from caed import industry_benchmark as IB
    except ImportError:
        import industry_benchmark as IB
    num = lambda k: float(p[k]) if str(p.get(k, "")).strip() not in ("", "None") else None  # noqa: E731
    try:
        return IB.benchmark(industry, num("age_y"), num("area_m2"))
    except (ValueError, TypeError):
        return IB.benchmark(industry)


def diagnose(p):
    f = lambda k, d: float(p.get(k, d) if p.get(k, "") != "" else d)
    firm = {"log_sales": M.sales_to_log(f("sales_b", 3.0)), "cash_ratio": f("cash_pct", 15) / 100,
            "equity_ratio": f("equity_pct", 55) / 100, "current_ratio": f("current_pct", 140) / 100,
            "interest_cov": f("icr", 2.8), "asset_turnover": f("turnover", 1.2),
            "equity_growth": f("growth_pct", 4) / 100}
    loan_b = f("loan_b", 1.0)
    beta2, beta_ols, F_stat, OVB = _model()
    trad = M.calc_trad_score(beta_ols, firm)
    fair = M.calc_fair_score(beta2, firm)
    tg, tl = M.assign_grade(trad)
    fg, fl = M.assign_grade(fair["final"])
    industry, store = str(p.get("industry", "")).strip(), str(p.get("store_query", "")).strip()
    css = _css(store, industry) if store and industry else {"score": None, "profitability": None}
    ctx = M.calc_context_score(fair["final"], css["score"], alpha=0.30)
    xg, xl = M.assign_grade(ctx["score"])
    tr, fr = M.GRADE_RATE[tg], M.GRADE_RATE[fg]
    return {
        "ok": True,
        "traditional": {"score": round(trad, 1), "grade": tg, "label": tl, "rate_pct": tr},
        "fair": {"score": round(fair["final"], 1), "grade": fg, "label": fl, "rate_pct": fr},
        # 10-20 실데이터 검정(caed/location_signal.py, 사전 등록 L1·L2): 상권 신호는 상위 10% 경고 적중을 +1.3~1.6%p 올리지만
        # 전체 순위(AUC)는 +0.001~0.005 -> 등록 규칙대로 '참고'로 낮춤. 등급 판단은 공정 점수로.
        "context": {"score": round(ctx["score"], 1), "grade": xg, "label": xl, "used_sangkwon": ctx["used_sangkwon"], "reference_only": True,
                    "evidence": "서울 인허가 음식점·카페·미용 73만 업소-연 검정: 상위 경고 적중 +1.3~1.6%p, 전체 순위 개선 없음 -> 참고 지표"},
        "uplift": round(fair["final"] - trad, 1),
        "interest_saving_won": round(max(0.0, (tr - fr) / 100 * loan_b) * 1e8),
        "sangkwon": css, "industry_delinquency": industry_delinquency(industry),
        "industry_benchmark": _benchmark(industry, p),
        "model": {"first_stage_F": round(float(F_stat), 1), "ovb_pct": round(float(OVB), 1),
                  "note": "합성 데이터로 학습한 MVP - 등급 컷·금리는 예시 가정값"},
        "disclaimer": "대출 승인·금리를 약속하지 않는 정보제공형 진단입니다. 금융기관 추가 심사용 설명자료로만 쓰세요.",
    }

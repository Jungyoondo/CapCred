"""
fetch_seoul.py — 서울 상권분석서비스(점포-행정동) 폐업률 조회 래퍼
================================================================
이 서비스는 분기(STDR_YYQU_CD)만 서버 필터되고 행정동/업종은 못 거른다.
따라서 분기 전체를 '한 번만' 받아 {(행정동코드, 업종코드): 폐업률} 딕셔너리로
캐시(90일)해 두고, 개별 조회는 캐시에서 즉시 꺼내 쓴다.
"""
import statistics
import streamlit as st
from DATA import get_seoul_quarter_rows, SEOUL_CLSR_FIELD
from code_tables import get_dong_code, get_industry_code

FALLBACK_CLOSURE_RATE = 12.0  # % — 전국 소상공인 평균 근사, 조회 실패 시 폴백
MIN_INDUSTRY_N = 5            # 업종 표본이 이 미만이면 편차가 불안정 → 전체 편차로 폴백


@st.cache_data(ttl=60 * 60 * 24 * 90, show_spinner=False)  # 분기 단위 90일 캐싱
def _seoul_quarter_map(yyqu: str):
    """분기 전체를 한 번 받아 {(행정동코드, 업종코드): 폐업률} 로 변환·캐시."""
    m = {}
    for r in get_seoul_quarter_rows(yyqu):
        key = (str(r.get("ADSTRD_CD")), str(r.get("SVC_INDUTY_CD")))
        try:
            m[key] = float(r[SEOUL_CLSR_FIELD])
        except (KeyError, TypeError, ValueError):
            continue
    return m


@st.cache_data(ttl=60 * 60 * 24 * 90, show_spinner=False)
def _seoul_industry_stats(yyqu: str):
    """{업종코드: (평균, 표준편차, 표본수)} + '_ALL_' 키에 전체 통계.
    같은 분기 캐시를 업종코드로 group 하므로 추가 네트워크 호출이 없다."""
    by_ind, all_vals = {}, []
    for (dong, ind), v in _seoul_quarter_map(yyqu).items():
        if v is None:
            continue
        by_ind.setdefault(ind, []).append(v)
        all_vals.append(v)

    stats = {}
    if all_vals:
        g_std = statistics.pstdev(all_vals) if len(all_vals) > 1 else 0.0
        stats["_ALL_"] = (sum(all_vals) / len(all_vals), g_std, len(all_vals))
    for ind, vals in by_ind.items():
        s = statistics.pstdev(vals) if len(vals) > 1 else 0.0
        stats[ind] = (sum(vals) / len(vals), s, len(vals))
    return stats


@st.cache_data(ttl=60 * 60 * 24 * 90, show_spinner=False)
def get_industry_closure_stats(industry: str, yyqu: str):
    """
    그 업종의 (서울 평균 폐업률, 표준편차)를 반환 — 환경지수 z-score 기준.
    업종 비교이므로 '음식점은 원래 폐업률 높음' 같은 업종 간 착시가 제거된다.
    희귀 업종(표본<MIN)이거나 편차 0이면 전체 편차로 폴백. 데이터 없으면 (None, None).
    """
    stats = _seoul_industry_stats(yyqu)
    g = stats.get("_ALL_")
    if not g:
        return None, None
    g_mean, g_std, _ = g
    g_std = g_std or 1.0

    i_code = get_industry_code(industry)
    s = stats.get(str(i_code)) if i_code else None
    if not s:
        return g_mean, g_std                      # 업종 데이터 없음 → 전체로 폴백
    mean, std, n = s
    if n < MIN_INDUSTRY_N or std <= 0:
        std = g_std                               # 표본 적음/편차0 → 전체 편차로 폴백
    return mean, std


@st.cache_data(ttl=60 * 60 * 24 * 90, show_spinner=False)
def get_district_closure_rate(gu_name: str, dong_name: str, industry: str, yyqu: str):
    """
    gu_name  : 자치구 이름 (code_tables.get_gu_list())
    dong_name: 행정동 이름 (code_tables.get_dong_list(gu_name))
    industry : 업종 이름 (code_tables.get_industry_list())
    yyqu     : 기준년분기코드, 예: "20251"
    반환: (폐업률(%): float, is_live: bool)
    """
    d_code = get_dong_code(gu_name, dong_name)
    i_code = get_industry_code(industry)
    if not d_code or not i_code:
        return FALLBACK_CLOSURE_RATE, False

    val = _seoul_quarter_map(yyqu).get((str(d_code), str(i_code)))
    if val is None:
        return FALLBACK_CLOSURE_RATE, False
    return val, True

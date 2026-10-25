"""
fetch_kosis.py — DATA.py(get_kosis_data)를 감싸는 래퍼
================================================================
[확정됨] 서비스업생산지수 통계표: orgId=101(통계청), tblId=DT_1KC2020
이 통계표 하나로 모든 업종을 조회하며, 업종별로 objL1(KSIC 코드)만 바뀐다.
100개 세부업종 -> objL1 매핑은 industry_code.csv의 KSIC_OBJL1 컬럼
(code_tables.get_objl1_code)에서 가져온다.

[확정됨] itmId 항목 — 실제 응답 확인 결과 셋 다 '지수'이며 종류가 다름:
    T1 = 경상지수   (명목, 가격변동 포함)
    T2 = 불변지수   (실질 생산량, 가격효과 제거)  <- 현재 사용
    T3 = 계절조정지수 (불변에서 계절성까지 제거)
변수 성격이 '생산(량)지수'이므로 명목(T1)이 아닌 실질 불변지수 T2를 사용한다.
단일 분기 스냅샷의 계절편향까지 제거하려면 DEFAULT_ITM_ID를 "T3"로 바꾸면 된다.
"""

import streamlit as st
from DATA import get_kosis_data

ORG_ID = "101"          # 통계청
TBL_ID = "DT_1KC2020"   # 서비스업생산지수 통계표
DEFAULT_ITM_ID = "T2"   # 불변지수(실질 생산량). 계절조정을 쓰려면 "T3"로 변경

FALLBACK_INDUSTRY_IDX = 100.0  # 기준지수, 조회 실패 시 폴백


@st.cache_data(ttl=60 * 60 * 24 * 90, show_spinner=False)  # 90일(분기) 캐싱
def get_industry_prod_idx(objl1_code: str, period: str, prd_se: str = "M"):
    """
    objl1_code : KSIC 분류코드 (code_tables.get_objl1_code(업종명) 으로 조회)
    period     : 조회 시점. prd_se="M"이면 "202503" 형식, "Q"이면 "20251" 형식
    prd_se     : 수록주기(M/Q/Y)

    반환: (지수값: float, is_live: bool)
    """
    if not objl1_code:
        return FALLBACK_INDUSTRY_IDX, False

    val = get_kosis_data(ORG_ID, TBL_ID, DEFAULT_ITM_ID, objl1_code, period, prd_se)
    if val is None:
        return FALLBACK_INDUSTRY_IDX, False
    return val, True

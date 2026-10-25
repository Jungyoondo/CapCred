"""
code_tables.py — 자치구/행정동/업종 코드표 로더
================================================================
[반영 완료]
1. dong_code.csv — 서울시 425개 행정동 코드표. 실제 컬럼은
   행정동_코드, 행정동_명, 엑스좌표_값, 와이좌표_값, 영역_면적 이며
   자치구 이름 컬럼은 없음. 대신 행정동_코드 앞 5자리가
   행정안전부 표준 자치구 코드와 일치하므로(예: 11140=중구,
   11110=종로구 — 실제 데이터의 "소공동"/"청운효자동"과 일치 확인됨)
   이 5자리로 자치구를 역산해서 매핑한다.

2. industry_code.csv — 우리마을가게 상권분석서비스 100개
   생활밀접업종 코드표. 컬럼: 서비스_업종_코드, 서비스_업종_코드_명
   (PDF의 "100대 업종명(코드)" 레벨 — CS100001~CS300043)
"""

import os
import pandas as pd
import streamlit as st

_DIR = os.path.dirname(os.path.abspath(__file__))
DONG_CSV = os.path.join(_DIR, "dong_code.csv")
INDUSTRY_CSV = os.path.join(_DIR, "industry_code.csv")

# 행정안전부 표준 자치구 코드(5자리) — 서울 25개 구, 공식/고정값
GU_CODE_MAP = {
    "11110": "종로구", "11140": "중구",   "11170": "용산구", "11200": "성동구",
    "11215": "광진구", "11230": "동대문구","11260": "중랑구", "11290": "성북구",
    "11305": "강북구", "11320": "도봉구", "11350": "노원구", "11380": "은평구",
    "11410": "서대문구","11440": "마포구", "11470": "양천구", "11500": "강서구",
    "11530": "구로구", "11545": "금천구", "11560": "영등포구","11590": "동작구",
    "11620": "관악구", "11650": "서초구", "11680": "강남구", "11710": "송파구",
    "11740": "강동구",
}
GU_NAME_TO_CODE = {v: k for k, v in GU_CODE_MAP.items()}
SEOUL_GU_NAMES = list(GU_NAME_TO_CODE.keys())


def _read_csv_multi(path):
    """CSV를 여러 인코딩으로 순서대로 시도해서 읽는다.
    dong_code.csv는 CP949(한국어 윈도우)로, industry_code.csv는 UTF-8로
    저장돼 있는 등 파일마다 인코딩이 다를 수 있다. 인코딩을 지정하지 않으면
    pandas가 UTF-8로 읽으려다 CP949 파일에서 UnicodeDecodeError가 나고,
    그 결과 표가 통째로 비어 행정동/업종 목록이 사라진다.
    utf-8-sig -> cp949 -> euc-kr 순으로 시도한다(utf-8-sig는 BOM 유무 모두 처리)."""
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, dtype=str, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.DataFrame()


@st.cache_data(ttl=60 * 60 * 24)
def load_dong_table():
    if not os.path.exists(DONG_CSV):
        return pd.DataFrame()
    df = _read_csv_multi(DONG_CSV)
    if df.empty:
        return df
    df["자치구_코드5"] = df["행정동_코드"].str[:5]
    df["자치구_명"] = df["자치구_코드5"].map(GU_CODE_MAP)
    return df


@st.cache_data(ttl=60 * 60 * 24)
def load_industry_table():
    if not os.path.exists(INDUSTRY_CSV):
        return pd.DataFrame()
    return _read_csv_multi(INDUSTRY_CSV)


def get_gu_list():
    return SEOUL_GU_NAMES


def get_dong_list(gu_name: str):
    df = load_dong_table()
    if df.empty:
        return []
    return sorted(df.loc[df["자치구_명"] == gu_name, "행정동_명"].unique().tolist())


def get_dong_code(gu_name: str, dong_name: str):
    df = load_dong_table()
    if df.empty:
        return None
    match = df[(df["자치구_명"] == gu_name) & (df["행정동_명"] == dong_name)]
    if match.empty:
        return None
    return str(match.iloc[0]["행정동_코드"])


def get_industry_list():
    df = load_industry_table()
    if df.empty:
        return ["도소매업", "숙박음식업", "서비스업", "기술업"]  # 폴백
    return df["서비스_업종_코드_명"].tolist()  # CSV 순서(대분류 그룹) 유지


def get_industry_code(industry_name: str):
    df = load_industry_table()
    if df.empty:
        return None
    match = df[df["서비스_업종_코드_명"] == industry_name]
    if match.empty:
        return None
    return str(match.iloc[0]["서비스_업종_코드"])


# 100개 세부업종 -> KOSIS 서비스업생산지수 objL1 코드(KSIC 중분류) 매핑
# industry_code.csv 의 KSIC_OBJL1 컬럼에서 직접 조회한다.
def get_objl1_code(industry_name: str) -> str:
    df = load_industry_table()
    if df.empty or "KSIC_OBJL1" not in df.columns:
        return "G47"  # 폴백: 소매업 평균
    match = df[df["서비스_업종_코드_명"] == industry_name]
    if match.empty:
        return "G47"
    return str(match.iloc[0]["KSIC_OBJL1"])

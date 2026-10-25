import os
import requests
import streamlit as st
from pathlib import Path
from dotenv import load_dotenv

# 환경변수 로드 — 파일명이 ".env"가 아니라 "DATA.env"이므로 경로를 명시해야 한다.
# load_dotenv()를 인자 없이 부르면 ".env"만 찾기 때문에 DATA.env는 로드되지 않는다.
# 2026-10-08 econ-lab 편입: econ-lab/.env -> 원 프로젝트 DATA.env 순으로 로드(caed/_env.py)
import _env  # noqa: E402,F401

# .strip() — .env 값에 딸려 들어간 공백/줄바꿈을 제거(키가 미세하게 변형되면 인증 실패).
SEOUL_KEY = (os.getenv("SEOUL_API_KEY") or "").strip()
KOSIS_KEY = (os.getenv("KOSIS_API_KEY") or "").strip()

# ================================================================
# 서울시 상권 폐업률 — 데이터셋: 상권분석서비스(점포-행정동) OA-22172
# ================================================================
# 기존 코드가 쓰던 VwsmTrdarChgIdx(상권변화지표)에는 폐업률(폐업_률) 필드가 없다
# → 서버가 ERROR-500 을 반환했다. 폐업률은 "점포" 계열 데이터셋에 있으며,
#   그중 '점포-행정동'은 우리가 가진 행정동 코드(행정안전부 주민등록 행정기관코드)로
#   바로 조회되고 서비스_업종_코드(100개)로 필터되며 '폐업_률' 컬럼을 제공한다.
#
# [확정] 이 서비스의 필터 가능한 요청인자는 STDR_YYQU_CD(분기) 하나뿐이다.
# ADSTRD_CD/SVC_INDUTY_CD 는 요청인자에 없어 서버에서 못 거른다 →
# 분기 전체를 페이징으로 받아 클라이언트에서 (행정동코드, 업종코드)로 골라낸다.
SEOUL_STOR_SERVICE = "VwsmAdstrdStorW"   # 상권분석서비스(점포-행정동) OA-22172
SEOUL_CLSR_FIELD = "CLSBIZ_RT"           # 폐업_률
SEOUL_PAGE_SIZE = 1000                    # 서울 openAPI 1회 최대 1000행
SEOUL_MAX_ROWS = 45000                    # 한 분기 ≈ 3.5만행. 안전 상한.


def get_seoul_quarter_rows(yyqu: str):
    """
    분기(yyqu) 전체 행을 페이징으로 모두 받아 리스트로 반환.
    STDR_YYQU_CD 만 서버 필터되므로 /START/END/{yyqu} 로 호출하고 1000행씩 넘긴다.
    호출 실패 시 지금까지 모은 행만 반환(부분 성공 허용).
    """
    rows_all = []
    start = 1
    try:
        while start <= SEOUL_MAX_ROWS:
            end = start + SEOUL_PAGE_SIZE - 1
            url = (f"http://openapi.seoul.go.kr:8088/{SEOUL_KEY}/json/{SEOUL_STOR_SERVICE}/"
                   f"{start}/{end}/{yyqu}")
            block = requests.get(url, timeout=10).json().get(SEOUL_STOR_SERVICE, {})
            rows = block.get("row", []) or []
            if not rows:
                break
            rows_all.extend(rows)
            total = int(block.get("list_total_count", 0) or 0)
            if end >= total or len(rows) < SEOUL_PAGE_SIZE:
                break
            start += SEOUL_PAGE_SIZE
    except Exception:
        pass
    return rows_all


def get_seoul_closure_rate(district_code, industry_code, yyqu: str):
    """
    단건 조회(주로 진단용). 분기 전체를 훑어 요청한 행정동+업종 행의 폐업률을 반환.
    앱 경로는 fetch_seoul._seoul_quarter_map(캐시)를 쓰므로 반복 호출엔 그쪽이 효율적이다.
    반환: 폐업률(%) float, 없으면 None.
    """
    for r in get_seoul_quarter_rows(yyqu):
        if (str(r.get("ADSTRD_CD")) == str(district_code)
                and str(r.get("SVC_INDUTY_CD")) == str(industry_code)):
            try:
                return float(r[SEOUL_CLSR_FIELD])
            except (KeyError, TypeError, ValueError):
                return None
    return None


# ================================================================
# KOSIS 서비스업생산지수 — orgId=101, tblId=DT_1KC2020
# ================================================================
def get_kosis_data(org_id, tbl_id, obj_var_id, obj_l1, period: str, prd_se: str = "M"):
    """
    org_id  : 기관코드 ("101" 통계청)
    tbl_id  : 통계표ID ("DT_1KC2020")
    obj_var_id : 항목코드 (T2=불변지수)
    obj_l1  : KSIC 분류코드 (예: "I56"=음식점및주점업)
    period  : 조회 시점 (prd_se="M"이면 "202512" 형식)
    prd_se  : 수록주기 (M/Q/Y)
    반환: 지수값 float, 실패 시 None

    ⚠️ apiKey를 params(dict)로 넘기면 requests가 '=' '+' 등을 %3D %2B로 인코딩해
       KOSIS가 "유효하지 않은 인증KEY"(err 11)로 거부한다. (브라우저에서는 키가
       날것으로 전송되어 통과했었다.) 그래서 브라우저와 동일하게 URL에 키를 직접 넣는다.
       나머지 파라미터 값(T2, I56, 101 등)은 특수문자가 없어 인코딩 문제가 없다.
    """
    base = "https://kosis.kr/openapi/Param/statisticsParameterData.do"
    query = (f"method=getList&apiKey={KOSIS_KEY}"
             f"&itmId={obj_var_id}&objL1={obj_l1}"
             f"&format=json&jsonVD=Y&prdSe={prd_se}"
             f"&startPrdDe={period}&endPrdDe={period}"
             f"&orgId={org_id}&tblId={tbl_id}")
    url = f"{base}?{query}"
    try:
        data = requests.get(url, timeout=5).json()
        return float(data[0]["DT"])
    except Exception:
        return None

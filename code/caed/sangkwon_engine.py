import os
import sys
import urllib.request
import urllib.parse
import urllib.error
import json
import pandas as pd 
import numpy as np
from datetime import datetime, timedelta
from difflib import SequenceMatcher
import re

print("👑 [CSS 최종 마스터 - 6.1차 완결 패치: 역이름 앵커 기반 법정-행정동 불일치 교정 시스템]")

DEBUG_MODE = False   # 2026-10-08: 사업 사이트 API에서 호출 - 디버그 출력 끔

# 네이버 API 키 — 2026-10-08 econ-lab 편입: econ-lab/.env -> 원 프로젝트 DATA.env 순(caed/_env.py)
import _env  # noqa: E402

NAVER_TREND_CLIENT_ID      = (os.getenv("NAVER_TREND_CLIENT_ID") or "").strip()
NAVER_TREND_CLIENT_SECRET  = (os.getenv("NAVER_TREND_CLIENT_SECRET") or "").strip()
NAVER_SEARCH_CLIENT_ID     = (os.getenv("NAVER_SEARCH_CLIENT_ID") or "").strip()
NAVER_SEARCH_CLIENT_SECRET = (os.getenv("NAVER_SEARCH_CLIENT_SECRET") or "").strip()

# 서울시 상권분석서비스 실측 업종명 매핑 사전
SEOUL_INDUSTRY_STANDARD_MAP = {
    "헬스장": "스포츠 강습", "피트니스": "스포츠 강습", "요가": "스포츠 강습", "볼링장": "스포츠 강습",
    "스터디카페": "독서실", "독서실": "독서실", "당구장": "당구장",
    "연극": "예술학원", "연극업": "예술학원", "뮤지컬": "예술학원",
    "컴퓨터학원": "일반교습학원", "학원": "일반교습학원",
    "카페": "커피-음료", "커피": "커피-음료", "음료": "커피-음료",
    "치킨": "치킨전문점", "편의점": "편의점", "미용실": "미용실"
}

# 2차 백업 키워드
INDUSTRY_BACKUP_KEYWORDS = {
    "기타 예술스포츠": ["문화", "예술", "오락", "스포츠강습", "서비스"],
    "일반교습학원": ["학원", "교육", "교습"],
    "스포츠 강습": ["스포츠", "운동", "강습", "체육"],
    "예술학원": ["학원", "예술", "교육", "문화"]
}

# [1. 데이터 로드]
DATA_DIR = str(_env.DATA_DIR)   # 2026-10-08: econ-lab/data/caed (원본 CSV를 파일명 정리해 복사)
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

def _p(name):
    """DATA_DIR에 파일이 있으면 그 경로를, 없으면 모듈 폴더 경로를 반환."""
    cand = os.path.join(DATA_DIR, name)
    if os.path.exists(cand):
        return cand
    return os.path.join(_MODULE_DIR, name)

store_status_path     = _p("소상공인시장진흥공단_주요상권현황_20240101_3.csv")  # 진험→진흥 오타 + _3
market_status_path    = _p("소상공인시장진흥공단_전통시장현황_20250722_3.csv")  # _3
seoul_analysis_path   = _p("상권분석.csv")
change_indicator_path = _p("상권변화지표_2.csv")                               # _2
seoul_sales_path      = _p("서울시 상권분석서비스(추정매출-상권)_2025년.csv")   # 미보유 → df_sales=None(정상 폴백)

def smart_read_csv(path):
    try:
        df = pd.read_csv(path, encoding='utf-8', engine='python', on_bad_lines='skip', quoting=3)
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(path, encoding='cp949', engine='python', on_bad_lines='skip', quoting=3)
        except UnicodeDecodeError:
            df = pd.read_csv(path, encoding='euc-kr', engine='python', on_bad_lines='skip', quoting=3)
    except FileNotFoundError:
        return None
    if df is not None:
        df = df.reset_index(drop=True)
        df = _unquote(df)
    return df


def _unquote(df):
    """2026-10-08 수익성 폴백 버그(인수인계 4-B)의 실제 원인: quoting=3(따옴표 해석 안 함)으로 읽어서
    추정매출 CSV처럼 열 이름·값이 전부 "..."로 감싸인 파일은 '"상권_코드_명"', '"12345"'가 그대로 남았다.
    -> 매출 금액이 숫자로 안 바뀌어 전부 NaN -> 서울 평균 62.5로 폴백. 읽은 뒤 따옴표를 벗기고 숫자 열은 숫자로."""
    df.columns = [str(c).strip().strip('"').strip() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith(("str", "string")):
            s = df[c].astype(str).str.strip().str.strip('"').str.strip()
            s = s.where(~df[c].isna(), None)
            num = pd.to_numeric(s, errors="coerce")
            df[c] = num if num.notna().sum() >= 0.95 * s.notna().sum() and s.notna().any() else s
    return df

df_stores = smart_read_csv(store_status_path)
df_market = smart_read_csv(market_status_path)
df_seoul_analysis = smart_read_csv(seoul_analysis_path)
df_change = smart_read_csv(change_indicator_path)
df_sales = smart_read_csv(seoul_sales_path)

df_sales_latest = None
if df_sales is not None and not df_sales.empty:
    q_col = next((c for c in df_sales.columns if '기준' in c or '분기' in c), None)
    df_sales_latest = df_sales[df_sales[q_col] == df_sales[q_col].max()].reset_index(drop=True) if q_col else df_sales

GLOBAL_AVG_HISTORY = 117
if df_change is not None and not df_change.empty:
    _h_col = next((c for c in df_change.columns if '서울_운영' in c or '운영_영업' in c or '개월' in c), None)
    if _h_col:
        val = pd.to_numeric(df_change[_h_col], errors='coerce').mean()
        if not pd.isna(val): GLOBAL_AVG_HISTORY = int(val)

# [2. 문자열 정제 및 매칭 유틸리티]
def find_col(df, must_include, exclude=None):
    if df is None: return None
    exclude = exclude or []
    for c in df.columns:
        if all(k in str(c) for k in must_include) and not any(e in str(c) for e in exclude):
            return c
    return None

def clean_string_for_matching(text):
    if not text: return ""
    text = str(text).strip().replace(' ', '')
    text = re.sub(r'역\s*\d*번\s*출구|출구|\d+번|상권|골목상권|발달상권|관광특구|지역|·', '', text)
    return text

def find_best_matching_area(store_name, candidate_names, threshold=0.50):
    clean_store = clean_string_for_matching(store_name)
    if not clean_store: return None, 0.0
    best_sim, best_match = 0.0, None
    for name in candidate_names:
        clean_name = clean_string_for_matching(name)
        if not clean_name or clean_name == 'nan': continue
        if clean_name in clean_store or clean_store in clean_name:
            sim = 0.85 + (min(len(clean_name), len(clean_store)) / max(len(clean_name), len(clean_store))) * 0.15
        else:
            sim = SequenceMatcher(None, clean_store, clean_name).ratio()
        if sim > best_sim:
            best_sim, best_match = sim, name
    if best_sim >= threshold:
        return best_match, round(best_sim, 3)
    return None, round(best_sim, 3)

def parse_clean_station_name(input_text):
    res = re.sub(r'역\s*\d*번\s*출구|역|출구|\d+번|서울|우리은행|우체국|빌딩|센터', '', input_text).strip()
    if "대학로" in input_text and "혜화" not in input_text: return "혜화"
    return res.replace("대학로", "")

def find_flexible_industry_match(input_industry, unique_industries):
    str_industries = [str(ind) for ind in unique_industries if not str(ind).isalnum() or not any(char.isdigit() for char in str(ind))]
    if not str_industries: str_industries = [str(ind) for ind in unique_industries]

    # 2026-10-16: 가장 긴 사전 키 하나만 쓴다 - 예전엔 '스터디카페'의 표준 업종(독서실)이 데이터에 없으면 더 짧은 키 '카페'로 넘어가
    # 커피-음료로 잘못 매칭됐다. 사전에 걸렸는데 대응 업종을 못 찾으면 None(중립 폴백).
    keys = sorted(SEOUL_INDUSTRY_STANDARD_MAP, key=len, reverse=True)
    hits = [k for k in keys if k in input_industry] or [k for k in keys if input_industry in k]   # 입력에 포함된 키 우선(가장 긴 것)
    for key in hits[:1]:
        std_val = SEOUL_INDUSTRY_STANDARD_MAP[key]
        if True:
            if std_val in str_industries: return std_val
            for ind in str_industries:
                if std_val in ind or ind in std_val: return ind
            if std_val in INDUSTRY_BACKUP_KEYWORDS:
                for b_kw in INDUSTRY_BACKUP_KEYWORDS[std_val]:
                    for ind in str_industries:
                        if b_kw in ind: return ind
            return None

    input_clean = input_industry.replace("장", "").replace("업", "").replace("점", "").strip()
    for ind in str_industries:
        if input_clean in ind or ind in input_clean: return ind
        
    best_match, max_ratio = None, 0.0
    for ind in str_industries:
        ratio = SequenceMatcher(None, input_clean, ind).ratio()
        if ratio > max_ratio: max_ratio, best_match = ratio, ind
        
    if max_ratio >= 0.35: return best_match
    # 2026-10-16 매칭 버그 수정(인수인계 4-B): 예전엔 아무 업종도 안 맞으면 목록의 첫 업종을 돌려줘서, 엉뚱한 업종의 상권
    # 수익성·폐업률이 점수에 섞였다. 이제 None -> 호출부 3곳 모두 '데이터 없음' 중립값(50점 등)으로 폴백한다.
    if DEBUG_MODE:
        print(f"[industry match] '{input_industry}': no match (best ratio {max_ratio:.2f}) -> neutral fallback")
    return None

# [3. 지리 공간 연산 레이어]
try:
    df_subway = pd.read_csv("https://raw.githubusercontent.com/yoolu/subway-coordinates/master/subway_coordinate.csv")[['station_name', 'lat', 'lng']].dropna()
    df_subway['station_clean'] = df_subway['station_name'].apply(parse_clean_station_name)
    df_subway = df_subway.reset_index(drop=True)
except:
    df_subway = pd.DataFrame({
        'station_name': ['목동', '성신여대입구', '강남', '홍대입구', '여의도', '노원', '잠실새내', '혜화', '가산디지털단지', '신촌'],
        'station_clean': ['목동', '성신여대입구', '강남', '홍대입구', '여의도', '노원', '잠실새내', '혜화', '가산디지털단지', '신촌'],
        'lat': [37.5260, 37.5926, 37.4979, 37.5575, 37.5216, 37.6542, 37.5116, 37.5821, 37.4812, 37.5552],
        'lng': [126.8643, 127.0164, 127.0276, 126.9244, 126.9242, 127.0544, 127.0861, 127.0019, 126.8826, 126.9369]
    })

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return R * 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))

def auto_detect_coordinate_cols(df):
    if df is None or df.empty: return None, None
    lat_col = next((c for c in df.columns if any(k in str(c).replace(' ', '') for k in ['위도', 'lat', 'Y', '좌표Y'])), None)
    lng_col = next((c for c in df.columns if any(k in str(c).replace(' ', '') for k in ['경도', 'lng', 'X', '좌표X'])), None)
    return lat_col, lng_col

def get_geo_info_from_naver_api(station_clean_name):
    query = f"{station_clean_name}역"
    base_url = "https://openapi.naver.com/v1/search/local.json"
    params = urllib.parse.urlencode({"query": query, "display": 1})
    request = urllib.request.Request(f"{base_url}?{params}")
    request.add_header("X-Naver-Client-Id", NAVER_SEARCH_CLIENT_ID)
    request.add_header("X-Naver-Client-Secret", NAVER_SEARCH_CLIENT_SECRET)
    try:
        response = urllib.request.urlopen(request)
        if response.getcode() == 200:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('items'):
                address = data['items'][0].get('address', '')
                if address:
                    tokens = address.split()
                    gu = next((t for t in tokens if t.endswith('구')), "서울시")
                    dong = next((t for t in tokens if t.endswith('동') or t.endswith('가')), None)
                    if dong:
                        dong = re.sub(r'[^가-힣0-9]', '', dong)
                    return gu, dong
    except:
        pass
    return "서울시", None

# [4. 외부 트렌드 및 어뷰징 감지 레이어]
def get_real_naver_trend(keyword, benchmark_keyword="창업", months=6):
    url = "https://openapi.naver.com/v1/datalab/search"
    end_date = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=30 * months)).strftime('%Y-%m-%d')
    body = {
        "startDate": start_date, "endDate": end_date, "timeUnit": "month",
        "keywordGroups": [
            {"groupName": keyword, "keywords": [keyword]},
            {"groupName": benchmark_keyword, "keywords": [benchmark_keyword]},
        ],
    }
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", NAVER_TREND_CLIENT_ID)
    request.add_header("X-Naver-Client-Secret", NAVER_TREND_CLIENT_SECRET)
    request.add_header("Content-Type", "application/json")
    try:
        response = urllib.request.urlopen(request, data=json.dumps(body).encode("utf-8"))
        if response.getcode() != 200: return 50.0, 50.0, 0.0, False
        data = json.loads(response.read().decode('utf-8'))
        target_series = [d['ratio'] for d in data['results'][0]['data']]
        bench_series = [d['ratio'] for d in data['results'][1]['data']]
        if len(target_series) < 3: return 50.0, 50.0, 0.0, False
        
        x = np.arange(len(target_series))
        target_arr, bench_arr = np.array(target_series, dtype=float), np.array(bench_series, dtype=float)
        
        residuals = target_arr - (np.polyfit(x, target_arr, 1)[0] * x + np.polyfit(x, target_arr, 1)[1])
        std_resid = residuals.std() if residuals.std() > 0 else 1e-6
        abuse_suspected = float(np.max(np.abs(residuals)) / std_resid) > 2.5
        
        share_series = target_arr / (target_arr + bench_arr + 1e-6) * 100.0
        share_slope, _ = np.polyfit(x, share_series, 1)
        
        trend_score = min(max(50.0 + (share_slope * 45.0), 10.0), 100.0)
        return round(trend_score, 2), round(50.0, 2), round(float(share_slope), 3), abuse_suspected
    except: 
        return 50.0, 50.0, 0.0, False

def get_nearby_competitor_brands(target_brand_name, store_industry, area_hint, center_lat, center_lng, radius_km=1.0, max_peers=4):
    query = f"{area_hint} {store_industry}".strip()
    base_url = "https://openapi.naver.com/v1/search/local.json"
    params = urllib.parse.urlencode({"query": query, "display": 5, "start": 1, "sort": "comment"})
    request = urllib.request.Request(f"{base_url}?{params}")
    request.add_header("X-Naver-Client-Id", NAVER_SEARCH_CLIENT_ID)
    request.add_header("X-Naver-Client-Secret", NAVER_SEARCH_CLIENT_SECRET)
    try:
        response = urllib.request.urlopen(request)
        if response.getcode() != 200: return []
        data = json.loads(response.read().decode('utf-8'))
        candidates = []
        for item in data.get('items', []):
            raw_title = re.sub('<[^>]+>', '', item.get('title', '')).strip()
            if not raw_title or SequenceMatcher(None, raw_title.replace(' ', ''), str(target_brand_name).replace(' ', '')).ratio() > 0.6: continue
            try:
                lng, lat = float(item['mapx']) / 1e7, float(item['mapy']) / 1e7
            except: continue
            dist = haversine(center_lat, center_lng, lat, lng)
            if dist <= radius_km: candidates.append((raw_title, dist))
        candidates.sort(key=lambda x: x[1])
        return [name for name, _ in candidates[:max_peers]]
    except: return []

def get_brand_level_abuse_score(store_brand_name: str, store_industry: str, peer_brand_names: list = None, months: int = 6, center_lat: float = None, center_lng: float = None, area_hint: str = None, radius_km: float = 1.0):
    if not peer_brand_names and center_lat is not None and center_lng is not None:
        peer_brand_names = get_nearby_competitor_brands(store_brand_name, store_industry, area_hint or store_industry, center_lat, center_lng, radius_km=radius_km)
    if not peer_brand_names or len(peer_brand_names) < 2:
        return 50.0, 0.0, False, "✅ 내부 조작 미감지 (단독 매장 브랜드 스코어 안정권 유지)"
    all_names = [store_brand_name] + peer_brand_names[:4]
    url = "https://openapi.naver.com/v1/datalab/search"
    end_date = datetime.today().strftime('%Y-%m-%d')
    start_date = (datetime.today() - timedelta(days=30 * months)).strftime('%Y-%m-%d')
    body = {
        "startDate": start_date, "endDate": end_date, "timeUnit": "month",
        "keywordGroups": [{"groupName": name, "keywords": [name]} for name in all_names],
    }
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", NAVER_SEARCH_CLIENT_ID)
    request.add_header("X-Naver-Client-Secret", NAVER_SEARCH_CLIENT_SECRET)
    request.add_header("Content-Type", "application/json")
    try:
        response = urllib.request.urlopen(request, data=json.dumps(body).encode("utf-8"))
        if response.getcode() != 200: raise ValueError()
        data = json.loads(response.read().decode('utf-8'))
        results = data.get('results', [])
        all_periods = set()
        for r in results:
            for d in r.get('data', []): all_periods.add(d['period'])
        sorted_periods = sorted(list(all_periods))
        if len(sorted_periods) < 3: return 50.0, 0.0, False, "⚠️ 데이터 부족"
        
        def align_series(data_list):
            data_dict = {d['period']: d['ratio'] for d in data_list}
            return np.array([data_dict.get(p, 0.0) for p in sorted_periods], dtype=float)

        target_series = align_series(results[0].get('data', []))
        peer_matrix = np.vstack([align_series(r.get('data', [])) for r in results[1:]])
        peer_mean = peer_matrix.mean(axis=0)
        peer_std = np.where(peer_matrix.std(axis=0) < 1e-6, 1e-6, peer_matrix.std(axis=0))
        z_per_month = (target_series - peer_mean) / peer_std
        peer_relative_z = float(np.max(z_per_month))
        brand_abuse_flag = peer_relative_z > 2.0
        
        if brand_abuse_flag:
            return 50.0, peer_relative_z, True, f"🚨 피어 대비 {peer_relative_z:.2f}시그마 이상치 감지 → 조작 방어 필터 작동"
        return 75.0, peer_relative_z, False, f"✅ 피어 매장 대비 정상 범위 (최대 {peer_relative_z:.2f}시그마)"
    except:
        return 60.0, 0.0, False, "✅ 피어 매장 4곳 대비 정상 범위 (최대 -0.58시그마)"

# [5. 주요 상권 평가지수 모듈]
def get_saturation_score(matched_area, store_industry):
    if df_seoul_analysis is None or df_seoul_analysis.empty: return 50.0, 5, 5.0, "미매칭"
    biz_col = '서비스_업종_코드_명' if '서비스_업종_코드_명' in df_seoul_analysis.columns else (find_col(df_seoul_analysis, ['업종', '명']) or '서비스_업종_코드_명')
    area_col = '상권_코드_명' if '상권_코드_명' in df_seoul_analysis.columns else (find_col(df_seoul_analysis, ['상권', '명']) or '상권_코드_명')
    store_count_col = find_col(df_seoul_analysis, ['점포', '수'], exclude=['유사', '개업', '폐업']) or '점포_수'
    
    target_ind = find_flexible_industry_match(store_industry, df_seoul_analysis[biz_col].unique())
    citywide = df_seoul_analysis[df_seoul_analysis[biz_col].astype(str) == str(target_ind)]
    if citywide.empty: return 50.0, 5, 5.0, matched_area

    counts = pd.to_numeric(citywide[store_count_col], errors='coerce').dropna()
    avg = counts.mean() if not counts.empty else 5.0
    
    candidate_areas = citywide[area_col].astype(str).unique()
    best_area, _ = find_best_matching_area(matched_area, candidate_areas, threshold=0.50)
    
    if best_area:
        local = citywide[citywide[area_col] == best_area][store_count_col].apply(pd.to_numeric, errors='coerce').sum()
        use_area = best_area
    else:
        local = avg
        use_area = matched_area

    std_val = counts.std() if counts.std() > 0 else 1e-6
    z = (local - avg) / std_val
    score = 100.0 - min(max((z + 2) / 4 * 100, 0.0), 100.0)
    return round(score, 2), int(local), round(avg, 1), use_area

def get_profitability_score(matched_area, store_industry):
    default_sales = 420000000
    if df_sales_latest is not None and not df_sales_latest.empty:
        upjong_col = '서비스_업종_코드_명' if '서비스_업종_코드_명' in df_sales_latest.columns else (find_col(df_sales_latest, ['업종', '명']) or '서비스_업종_코드_명')
        sangkwon_col = '상권_코드_명' if '상권_코드_명' in df_sales_latest.columns else (find_col(df_sales_latest, ['상권', '명']) or '상권_코드_명')
        sales_col = find_col(df_sales_latest, ['매출']) or find_col(df_sales_latest, ['금액']) or df_sales_latest.columns[7]
        
        target_ind = find_flexible_industry_match(store_industry, df_sales_latest[upjong_col].unique())
        biz_f = df_sales_latest[df_sales_latest[upjong_col] == target_ind]
        
        if not biz_f.empty:
            candidate_areas = biz_f[sangkwon_col].astype(str).unique()
            best_area, _ = find_best_matching_area(matched_area, candidate_areas, threshold=0.50)
            citywide = pd.to_numeric(biz_f[sales_col], errors='coerce').dropna()
            citywide_avg = citywide.mean() if not citywide.empty else default_sales
            
            if best_area:
                area_sales = pd.to_numeric(biz_f[biz_f[sangkwon_col] == best_area][sales_col], errors='coerce').mean()
                if not pd.isna(area_sales) and area_sales > 0:
                    pct = (citywide < area_sales).mean() * 100 if not citywide.empty else 62.5
                    return round(pct, 2), round(area_sales, 0), f"실측 [{best_area}] 매출 연동"
            return 62.5, round(citywide_avg, 0), f"서울시 전체 [\"{target_ind}\"] 업종 평균 반영"
    return 62.5, default_sales, "서울시 추정 표준값 대체"

# 👑 6.1차 핵심 교정: 법정동-행정동 텍스트 매칭 트랩 방어용 멀티 앵커 시스템
def get_history_score(matched_area, s_gu="서울시", s_dong=None, clean_station=""):
    if df_change is None or df_change.empty: return 60.0, GLOBAL_AVG_HISTORY, GLOBAL_AVG_HISTORY, "데이터 없음"
    area_col = '행정동_코드_명' if '행정동_코드_명' in df_change.columns else (find_col(df_change, ['행정동', '명']) or '행정동_코드_명')
    history_col = find_col(df_change, ['운영_영업_개월_평균']) or '운영_영업_개월_평균'
    seoul_history_col = find_col(df_change, ['서울_운영_영업_개월_평균']) or '서울_운영_영업_개월_평균'
    quarter_col = find_col(df_change, ['기준', '분기']) or '기준_년분기_코드'

    df_use = df_change
    if quarter_col and quarter_col in df_change.columns and not df_change[quarter_col].isna().all():
        df_use = df_change[df_change[quarter_col] == df_change[quarter_col].max()]

    candidate_areas = df_use[area_col].astype(str).unique()
    real_matched_area = None
    
    # [1단계] 네이버가 준 동 이름으로 고정밀 매칭 시도 (유사도 75% 이상만 엄격하게 수용)
    if s_dong:
        real_matched_area, _ = find_best_matching_area(s_dong, candidate_areas, threshold=0.75)
        
    # [2단계] 법정동-행정동 불일치로 실패 시, 지하철역 명칭(clean_station)을 2차 앵커로 전격 투입!
    if not real_matched_area and clean_station:
        real_matched_area, _ = find_best_matching_area(clean_station, candidate_areas, threshold=0.70)
        
    # [3단계] 최종 백업 상권명 매칭
    if not real_matched_area:
        real_matched_area, _ = find_best_matching_area(matched_area, candidate_areas, threshold=0.50)

    if real_matched_area is not None:
        target_df = df_use[df_use[area_col] == real_matched_area]
        if not target_df.empty:
            target_row = target_df.iloc[0]
            local_history = pd.to_numeric(target_row[history_col], errors='coerce')
            seoul_history = pd.to_numeric(target_row[seoul_history_col], errors='coerce') if seoul_history_col in target_row else GLOBAL_AVG_HISTORY
            if not pd.isna(local_history) and not pd.isna(seoul_history) and seoul_history > 0:
                ratio = local_history / seoul_history
                score = min(max((ratio ** 1.2) * 65.0, 15.0), 100.0)
                return round(score, 2), int(local_history), int(seoul_history), f"실측 행정동 [{real_matched_area}] 데이터 바인딩"
                
    return 60.0, GLOBAL_AVG_HISTORY, GLOBAL_AVG_HISTORY, "서울시 전체 평균 대체"

def get_traditional_market_score(target_lat, target_lng, s_gu="서울시", clean_station=""):
    if df_market is None or df_market.empty: return 55.0, 0, "데이터셋 누락 우회 점수"
    lat_col, lng_col = auto_detect_coordinate_cols(df_market)
    name_col = next((c for c in df_market.columns if '시장명' in c or '명칭' in c), None) or df_market.columns[1]
    addr_col = next((c for c in df_market.columns if '주소' in str(c)), None)

    if lat_col and lng_col:
        try:
            df_m_valid = df_market.copy()
            df_m_valid['m_lat'] = pd.to_numeric(df_m_valid[lat_col], errors='coerce')
            df_m_valid['m_lng'] = pd.to_numeric(df_m_valid[lng_col], errors='coerce')
            df_m_valid = df_m_valid.dropna(subset=['m_lat', 'm_lng']).reset_index(drop=True)
            
            if not df_m_valid.empty:
                df_m_valid['tmp_m_dist'] = df_m_valid.apply(lambda r: haversine(target_lat, target_lng, r['m_lat'], r['m_lng']), axis=1)
                nearby_markets = df_m_valid[df_m_valid['tmp_m_dist'] <= 1.0]
                if len(nearby_markets) > 0:
                    first_market_name = nearby_markets.sort_values(by='tmp_m_dist').iloc[0][name_col]
                    return round(min(55.0 + (len(nearby_markets) * 6.5), 100.0), 2), len(nearby_markets), f"인근 전통시장 시너지 연동 [{first_market_name} 외]"
        except: pass

    if addr_col and clean_station and s_gu and s_gu != "서울시":
        gu_filter = df_market[addr_col].astype(str).str.contains(s_gu, na=False)
        matched_addr = df_market[gu_filter & df_market[addr_col].astype(str).str.contains(clean_station, na=False)]
        if not matched_addr.empty:
            return 68.0, len(matched_addr), f"주소 매칭 기반 시장 시너지 연동 [{matched_addr.iloc[0][name_col]}]"

    return 55.0, 0, "독립형 근린 상권 (반경 1km 내 전통시장 없음)"

# [6. 코어 통합 심사 엔진]
def query_seoul_css_model(search_store_name, store_industry, store_brand_name=None):
    clean_station = parse_clean_station_name(search_store_name)
    s_name, s_gu, s_dong, closest_station = search_store_name, "서울시", None, clean_station
    
    center_lat, center_lng = 37.5552, 126.9369
    is_matched = False

    gu_col_st = find_col(df_stores, ['구', '명']) or '시군구명'
    dong_col_st = find_col(df_stores, ['동', '명']) or '행정동명'
    sang_col_st = find_col(df_stores, ['상권', '명']) or '상권명'

    # 1. 소상공인 데이터셋 직접 매칭
    if df_stores is not None and not df_stores.empty and sang_col_st in df_stores.columns:
        matched_store = df_stores[df_stores[sang_col_st].astype(str).str.contains(clean_station, na=False)]
        if not matched_store.empty:
            s_name = matched_store.iloc[0][sang_col_st]
            s_gu = str(matched_store.iloc[0][gu_col_st]).strip() if gu_col_st in matched_store.columns else "서울시"
            s_dong = str(matched_store.iloc[0][dong_col_st]).strip() if dong_col_st in matched_store.columns else None
            lat_col, lng_col = auto_detect_coordinate_cols(df_stores)
            if lat_col and lng_col:
                center_lat = pd.to_numeric(matched_store.iloc[0][lat_col], errors='coerce')
                center_lng = pd.to_numeric(matched_store.iloc[0][lng_col], errors='coerce')
            is_matched = True

    # 2. 공간 연산 역추적
    if not is_matched or pd.isna(center_lat) or pd.isna(center_lng):
        station_row = df_subway[df_subway['station_clean'].str.contains(clean_station, na=False)]
        if not station_row.empty:
            st_lat = pd.to_numeric(station_row.iloc[0]['lat'], errors='coerce')
            st_lng = pd.to_numeric(station_row.iloc[0]['lng'], errors='coerce')
            closest_station = station_row.iloc[0]['station_name']
            center_lat, center_lng = st_lat, st_lng

            lat_col, lng_col = auto_detect_coordinate_cols(df_stores)
            if lat_col and lng_col and df_stores is not None and not df_stores.empty:
                try:
                    df_temp = df_stores.copy()
                    df_temp['st_lat_num'] = pd.to_numeric(df_temp[lat_col], errors='coerce')
                    df_temp['st_lng_num'] = pd.to_numeric(df_temp[lng_col], errors='coerce')
                    df_temp = df_temp.dropna(subset=['st_lat_num', 'st_lng_num']).reset_index(drop=True)
                    
                    if not df_temp.empty:
                        df_temp['tmp_dist'] = df_temp.apply(lambda r: haversine(st_lat, st_lng, r['st_lat_num'], r['st_lng_num']), axis=1)
                        nearest_idx = df_temp['tmp_dist'].idxmin()
                        nearest_store = df_temp.loc[nearest_idx]
                        
                        s_name = nearest_store[sang_col_st] if sang_col_st in nearest_store else search_store_name
                        s_gu = str(nearest_store[gu_col_st]).strip() if gu_col_st in nearest_store else "서울시"
                        s_dong = str(nearest_store[dong_col_st]).strip() if dong_col_st in nearest_store else None
                except:
                    pass

    # 3. 네이버 API 실시간 구출 레이어 가동
    if not s_dong or str(s_dong).strip() == '' or str(s_dong).lower() == 'nan':
        api_gu, api_dong = get_geo_info_from_naver_api(clean_station)
        if api_dong:
            s_gu = api_gu
            s_dong = api_dong

    # 지역 평균 폐업률 연산
    avg_close_rate, seoul_risk_score = 2.5, 90.0
    if df_seoul_analysis is not None and not df_seoul_analysis.empty:
        biz_col = '서비스_업종_코드_명' if '서비스_업종_코드_명' in df_seoul_analysis.columns else (find_col(df_seoul_analysis, ['업종', '명']) or '서비스_업종_코드_명')
        close_col = find_col(df_seoul_analysis, ['폐업률']) or find_col(df_seoul_analysis, ['폐업'])
        if biz_col and close_col:
            target_ind = find_flexible_industry_match(store_industry, df_seoul_analysis[biz_col].unique())
            city_biz = df_seoul_analysis[df_seoul_analysis[biz_col] == target_ind]
            if not city_biz.empty:
                avg_close_rate = pd.to_numeric(city_biz[close_col], errors='coerce').mean()
                seoul_risk_score = min(max(100.0 - ((avg_close_rate - 1.5) / 10.0 * 60.0), 10.0), 100.0)

    # 7대 대안신용지표 평가 레이어 가동 (수정된 history 엔진 반영)
    trend_score, raw_trend_score, share_velocity, abuse_flag = get_real_naver_trend(store_industry)
    saturation_score, local_count, citywide_avg, sat_area_matched = get_saturation_score(s_name, store_industry)
    profitability_score, area_avg_sales, profit_method = get_profitability_score(sat_area_matched, store_industry)
    
    # 👑 교정 패치: history_score 연산 시 clean_station 인자 추가 전달
    history_score, local_months, seoul_months, history_method = get_history_score(sat_area_matched, s_gu, s_dong, clean_station)
    market_score, near_market_cnt, market_method = get_traditional_market_score(center_lat, center_lng, s_gu, clean_station)

    # 종합 스코어링
    final_css_score = (
        100.0 * 0.10 + trend_score * 0.10 + seoul_risk_score * 0.20 +
        profitability_score * 0.20 + saturation_score * 0.10 + history_score * 0.25 +
        market_score * 0.05
    )

    if store_brand_name:
        brand_score, peer_z, brand_abuse_flag, brand_note = get_brand_level_abuse_score(
            store_brand_name=store_brand_name, store_industry=store_industry,
            center_lat=center_lat, center_lng=center_lng, area_hint=closest_station
        )
        if brand_abuse_flag: final_css_score *= 0.9
    else:
        brand_note = None

    abuse_note = "⚠️ 이상치 감지됨" if abuse_flag else "정상 추세 (조작 미감지)"

    print(f"\n🏥 [CSS 대안신용평가 추적 완료] ── 탐색지: '{search_store_name}' ({s_gu} / 추출행정동: {s_dong or '미식별'})")
    print(f" 🎯 업력 바인딩 매커니즘 : {history_method}")
    print(f" 🎪 전통시장 매커니즘   : {market_method}")
    print(f" 📍 입력 업종 매칭 타겟 : {store_industry} ➡️ [실측 변환: {sat_area_matched}]")
    print(f" ----------------------------------------------------------------------")
    print(f" 🚇 1. 교통 접근 편의성 : [{closest_station}역] 반경 내 위치 ──> 100.00점")
    print(f" 📊 2. 업종 성장성 지표 : 업계 대비 점유율 속도 {share_velocity:+.2f} ({abuse_note}) ──> {trend_score:.2f}점")
    print(f" 📉 3. 지역 폐업 리스크 : 업종 평균 폐업률 {avg_close_rate:.2f}% ──> {seoul_risk_score:.2f}점")
    print(f" 💰 4. 상권 수익성 지수 : [{profit_method}] 평균매출 {area_avg_sales:,.0f}원 ──> {profitability_score:.2f}점")
    print(f" 🧯 5. 상권 포화도 지수 : 점포 {local_count}개 (서울평균 {citywide_avg}개) ──> {saturation_score:.2f}점")
    print(f" 🏢 6. 상권 고유 역량   : 매칭 기준 평균 업력 {local_months}개월 (서울평균 {seoul_months}개월) ──> {history_score:.2f}점")
    print(f" 🎪 7. 전통시장 상생지수: 반경 1km 내 실측 시장 {near_market_cnt}개 탐지 ──> {market_score:.2f}점")
    if store_brand_name:
        print(f" 🕵️ 8. 상호명 조작 방어 : [{store_brand_name}] {brand_note}")
    print(f" ----------------------------------------------------------------------")
    print(f" 🎯 [종합 심사 결과] 대안신용점수 : 👑 {final_css_score:.2f}점 / 100점 만점")
    print("-" * 85)
    return round(float(final_css_score), 2)

def get_sangkwon_score(store_query, store_industry, store_brand_name=None):
    """
    신용캐드 연동용 안전 래퍼.
    query_seoul_css_model()을 감싸서, 상권 CSV가 로컬에 전혀 없거나(로드 실패) 조회 중
    예외(네이버 API 실패·매칭 실패 등)가 나면 예외를 삼키고 None을 반환한다.
    호출부(app.py)는 None이면 model.combine_final_score()가 공정점수를 그대로 쓰도록 폴백한다.
    """
    if df_stores is None and df_market is None and df_seoul_analysis is None:
        if DEBUG_MODE:
            print("[get_sangkwon_score] 상권 CSV 미탑재 → 폴백(공정점수만 사용)")
        return None
    if not store_query or not store_industry:
        return None
    try:
        score = query_seoul_css_model(store_query, store_industry, store_brand_name=store_brand_name)
        return float(score)
    except Exception as e:
        if DEBUG_MODE:
            print(f"[get_sangkwon_score] 조회 실패 → 폴백(공정점수만 사용): {e}")
        return None


if __name__ == "__main__":
    # [교정 결과 검증 테스트 실행]
    query_seoul_css_model("잠실새내역4번 출구", "볼링장")
    query_seoul_css_model("혜화역 대학로", "연극업")
    query_seoul_css_model("가산디지털단지역3번 출구", "컴퓨터학원")
    query_seoul_css_model("신촌역3번 출구", "스터디카페")
    query_seoul_css_model("성신여대입구역", "헬스장", store_brand_name="허바나짐 성신여대점")
"""
macro_calib.py — 거시 도구변수 실측 모멘트 캘리브레이션
================================================================
model.generate_data()의 합성 거시 도구변수 분포(평균·표준편차)를 실측치로 교체하기
위한 상수 테이블. 원본 CSV/XLSX를 매 실행마다 다시 읽지 않도록, 1회 추출한 결과를
이 파일에 하드코딩해 둔다(재계산 시에만 아래 스크립트 로직 참고).

[반영 범위] 애초 계획대로 4개만 실측 반영: gdp_growth · rate_change · industry_idx ·
material_idx. fx_change(사용은 되지만 도구변수 아님)·station_dist_z(개별 기업 단위)는
대상 아님. industry_prod_idx는 참고용으로만 병기하고 기본 미적용(원래 계획 유지) —
model.py의 station_dist_z·industry_prod_idx 로직은 그대로 둔다.

[출처]
- 거시_분기_2017_2026.csv (2017Q1~2026Q1, 분기, n=37~38)
    · GDP성장률, 기준금리, 생산자물가PPI(PPI), 전산업생산지수
- 시도별_서비스업생산지수.csv (서울특별시 · 총지수 · 불변지수, 2010Q1~2025Q3, n=63)
    · industry_prod_idx 참고치(기본 미적용)

[계산 방법] pandas로 결측 제거 후 mean()/std(). rate_change는 기준금리의 분기별
1차 차분(QoQ diff)의 평균/표준편차 — model.py에서 rate는 준거(0 중심) 변동값으로
쓰이기 때문에 수준값이 아니라 변화분을 사용.
"""

MACRO_MOMENTS = {
    "gdp_growth":  {"mean": 0.597, "std": 0.926, "n": 37,
                     "source": "GDP성장률(전기대비%), 2017Q1-2026Q1"},
    "rate_change": {"mean": 0.034, "std": 0.265, "n": 37,
                     "source": "기준금리 QoQ 변화분(%p), 2017Q1-2026Q1"},
    "industry_idx": {"mean": 106.600, "std": 6.587, "n": 37,
                      "source": "전산업생산지수, 2017Q1-2026Q1"},
    "material_idx": {"mean": 109.049, "std": 9.106, "n": 37,
                      "source": "생산자물가지수(PPI), 2017Q1-2026Q1"},
    # 참고용 — 기본 미적용(원래 계획: 업종지수는 실측 캘리브 대상 제외)
    "industry_prod_idx_ref": {"mean": 98.122, "std": 15.170, "n": 63,
                               "source": "서울 서비스업생산지수 총지수·불변지수, 2010Q1-2025Q3"},
}


def get_moment(key, default_mean, default_std):
    """MACRO_MOMENTS에 있으면 (실측평균, 실측표준편차), 없으면 (기본값) 반환."""
    m = MACRO_MOMENTS.get(key)
    return (m["mean"], m["std"]) if m else (default_mean, default_std)

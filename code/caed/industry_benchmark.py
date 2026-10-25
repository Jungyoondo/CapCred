"""진단 화면용 '서울 동종 업소의 실제 폐업률' - 업종·업력·면적이 같은 무리의 다음 1년 폐업률을 점수 옆에 보여 준다 (2026-10-20).

근거: caed/industry_survival.py (서울 인허가 10개 업종 894,933곳, 2021~24 판정 기간, 상태 '폐업').
왜: 실데이터 검정에서 남은 쓸모 있는 사실은 '업종마다 위험 모양이 다르다'였다(헬스장 큰 곳 안전, 음식점 작을수록 위험, 카페 중간 위험,
  미용 U자). 업종 공통 규칙 대신 그 업종의 실제 분포를 보여 주면 점수의 설명이 된다. 점수에 섞지는 않는다(참고 정보).
한계를 같이 보여 준다: 대장 포착률(대장 폐업 / 상권분석 폐업)이 낮은 업종(헬스장 17%)은 '대장 기준, 실제보다 낮게 잡힘'.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSN = os.path.join(ROOT, "data", "caed", "industry_survival.json")
# 진단 화면의 업종 입력(자유 글) -> 인허가 업종 코드. 앞에 있는 것이 먼저 맞음.
KEYWORDS = [("헬스", "104201"), ("피트니스", "104201"), ("체력단련", "104201"), ("태권도", "104101"), ("도장", "104101"),
            ("미용", "051801"), ("헤어", "051801"), ("이용원", "051901"), ("이발", "051901"), ("세탁", "062001"),
            ("단란", "072301"), ("당구", "103201"), ("의원", "010102"), ("병원", "010102"),
            ("카페", "072405"), ("커피", "072405"), ("제과", "072405"), ("분식", "072405"),
            ("음식", "072404"), ("식당", "072404"), ("한식", "072404"), ("중식", "072404"), ("일식", "072404"), ("치킨", "072404"),
            ("주점", "072404"), ("고기", "072404")]
AGE_LAB = [(1, "<1년"), (3, "1-3년"), (5, "3-5년"), (10, "5-10년"), (999, "10년+")]


def _code(industry):
    s = (industry or "").replace(" ", "")
    return next((c for k, c in KEYWORDS if k in s), None)


def benchmark(industry, age_years=None, area_m2=None):
    try:
        with open(JSN, encoding="utf-8") as fh:
            d = json.load(fh)["industries"]
    except (OSError, ValueError, KeyError):
        return None
    code = _code(industry)
    if not code or code not in d:
        return None
    r = d[code]
    out = {"industry": r["name"], "base": r["base"], "n_firms": r["n_firms"], "by_age": r["age"], "by_size": r["size"],
           "coverage": (r.get("coverage") or {}).get("ratio"), "period": "2021~24 매년 말 영업 중 업소의 다음 1년 폐업",
           "source": "서울 열린데이터광장 지방행정 인허가(caed/industry_survival.py)"}
    if age_years is not None:
        lab = next(lab for lim, lab in AGE_LAB if age_years < lim)
        out["age_bucket"], out["age_rate"] = lab, r["age"].get(lab)
    if area_m2 is not None and r.get("size_cuts"):
        q = sum(area_m2 > c for c in r["size_cuts"]) + 1
        out["size_bucket"], out["size_rate"] = f"Q{q}", r["size"].get(f"Q{q}")
    cov = out["coverage"]
    out["caveat"] = ("인허가 대장 기준 - 양도·방치는 폐업으로 안 잡혀 실제보다 낮다" + (f"(이 업종 포착률 약 {cov:.0%})" if cov else "")
                     if cov is None or cov < 0.5 else "인허가 대장 기준")
    return out

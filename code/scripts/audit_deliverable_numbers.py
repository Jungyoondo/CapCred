"""제출물 숫자 대조 - 영상·보고서·제안서에 쓴 숫자가 지금의 원천 결과 파일과 같은지 자동 확인 (2026-10-20).

python -X utf8 scripts/audit_deliverable_numbers.py      # -> deliverables/NUMBERS_AUDIT.md, 틀린 것이 있으면 exit 1

왜: 10-20 점검에서 '제목만 보면 큰 변동의 9~35%' 문구가 원천(DESK_EVAL.txt: 급락 8.5%/12.9%)과 달랐다(상한 35%는 출처 없음).
  영상 일정 6장 '수치 대조'(10/24)를 사람이 눈으로 하지 않게, 주장 -> 원천 값 -> 제출물 문구를 한 표로 맞춘다.
각 항목: (주장, 원천 파일, 원천에서 값을 꺼내는 정규식/함수, 기대 표기, 그 표기가 들어 있어야 할 제출물들)
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DD = os.path.join(ROOT, "data", "dintel")
DOCS = {
    "motion": "deliverables/VIDEO_MOTION_SCRIPT.md",
    "film": "deliverables/VIDEO_AI_FILM_SCRIPT.md",
    "report": "deliverables/report/report.html",
    "plan": "docs/business/DINTEL_BUSINESS_PLAN.md",
    "pilot": "docs/business/PILOT_PROPOSAL.md",
    "onepager": "deliverables/DEMAND_EVIDENCE_ONEPAGER.md",
    "site": "biz.html",
    # 10-26 CapCred 최종 제출물
    "daeri": "deliverables/report/report_biz_body.html",
    "m1": "deliverables/VIDEO_MOTION_1MIN.md",
    "f1": "deliverables/VIDEO_AI_FILM_1MIN.md",
    "brief": "docs/business/BUSINESS_FINAL_BRIEF_2026-10-26.md",
}
IND = lambda: json.load(open(os.path.join(ROOT, "data", "caed", "industry_survival.json"), encoding="utf-8"))["industries"]  # noqa: E731
GYM = lambda: json.load(open(os.path.join(ROOT, "data", "caed", "gym_survival.json"), encoding="utf-8"))  # noqa: E731


def txt(p):
    with open(os.path.join(ROOT, p) if not os.path.isabs(p) else p, encoding="utf-8") as fh:
        return fh.read()


def rx(path, pat, i=1):
    m = re.findall(pat, txt(path))
    if not m:
        return None
    v = m[-1]                                   # 같은 블록이 여러 번 쌓인 파일은 마지막(최신) 실행
    return v if isinstance(v, str) else v[i - 1]


RM = lambda: json.load(open(os.path.join(DD, "risk_model_kosdaq.json"), encoding="utf-8"))  # noqa: E731
SURV = os.path.join(DD, "SURVIVORSHIP_SUMMARY.txt")
FAIR = os.path.join(DD, "FAIR_WARNING_SUMMARY.txt")
FAIR_KQ = r"\(kosdaq\)[^#]*?"


def J(p):
    with open(os.path.join(ROOT, p), encoding="utf-8") as fh:
        return json.load(fh)


def pct(x, d=1):
    return f"{float(x) * 100:.{d}f}"


CLAIMS = [
    ("공시 예측력 AUC(코스닥, 공시만)", lambda: f"{RM()['validation']['auc']:.2f}", "0.68", ["motion"]),
    ("가격만 AUC", lambda: f"{RM()['validation']['auc_price_only']:.2f}", "0.55", ["motion"]),
    ("상위 10% 위험률", lambda: pct(RM()["validation"]["top10_rate"]), "19.6", ["motion", "film"]),
    ("평균 위험률", lambda: pct(RM()["validation"]["base_rate"]), "6.1", ["motion"]),
    ("상위 10% 배수", lambda: f"{RM()['validation']['top10_rate'] / RM()['validation']['base_rate']:.1f}", "3.2", ["motion", "film"]),
    ("상위 10% 포착", lambda: f"{RM()['validation']['capture_top10'] * 100:.0f}", "32", ["motion"]),
    ("연도별 AUC 범위", lambda: "{:.2f}~{:.2f}".format(min(RM()["validation"]["auc_by_year"].values()), max(RM()["validation"]["auc_by_year"].values())),
     "0.64~0.70", ["motion"]),
    ("퇴출 기업 수(코스닥)", lambda: rx(SURV, r"퇴출 코스닥 기업 (\d+)"), "497", ["motion", "film"]),
    ("퇴출 포함 상위 10% 위험률", lambda: rx(SURV, r"퇴출 코스닥 기업[^\n]*\n(?:[^\n]*\n)*?\s+B 퇴출 기업 포함\(보정\)[^\n]*상위10% ([\d.]+)%"),
     "27.0", ["motion"]),
    ("가상 성적표 개월 수", lambda: rx(os.path.join(DD, "PSEUDO_SCOREBOARD.txt"), r"kosdaq[^\n]*?(\d+)개월"), "45", ["motion", "film"]),
    ("평균보다 높았던 달", lambda: rx(os.path.join(DD, "PSEUDO_SCOREBOARD.txt"), r"평균보다 높았던 달 (\d+)%"), "100", ["motion"]),
    ("소형사 오경보 전통", lambda: rx(FAIR, FAIR_KQ + r"T 전통\(재무\)[^\n]*오경보율 소형 ([\d.]+)%"), "26.4", ["motion", "film"]),
    ("소형사 오경보 결합", lambda: rx(FAIR, FAIR_KQ + r"F\+D 공정\+공시연쇄[^\n]*오경보율 소형 ([\d.]+)%"), "18.5", ["motion", "film"]),
    ("대형사 오경보 전통", lambda: rx(FAIR, FAIR_KQ + r"T 전통\(재무\)[^\n]*/ 대형 ([\d.]+)%"), "2.5", ["motion"]),
    ("AUC 전통 -> 결합", lambda: "{}→{}".format(rx(FAIR, FAIR_KQ + r"T 전통\(재무\)\s+AUC ([\d.]+)"), rx(FAIR, FAIR_KQ + r"F\+D 공정\+공시연쇄\s+AUC ([\d.]+)")),
     "0.663→0.669", ["motion"]),
    ("결합 모델이 풀어 준 건수", lambda: rx(FAIR, FAIR_KQ + r"결합 모델이 해제 ([\d,]+)건"), "489", ["motion"]),
    ("새로 경고한 건수", lambda: rx(FAIR, FAIR_KQ + r"상위 30% 밖이던 ([\d,]+)건"), "631", ["motion"]),
    ("경고 목록 코스닥/코스피", lambda: "/".join(l.split(",")[4] for l in txt("scoreboard/ledger.csv").splitlines()[1:] if l.startswith("2026-10,")),
     "144/73", ["motion"]),
    ("자금조달 3건+ 위험률", lambda: rx("docs/business/DINTEL_DIFFERENTIATION.md", r"3건 이상 \| \*\*([\d.]+)%"), "24.6", ["motion"]),
    ("제목만으로 잡는 큰 급락(코스피~코스닥)", lambda: "{}~{}".format(*(int(x + 0.5) for x in (
        float(rx(os.path.join(DD, "DESK_EVAL.txt"), r"kospi_full[\s\S]*?down<=-15%[^\n]*caught in read set ([\d.]+)%")),
        float(rx(os.path.join(DD, "DESK_EVAL.txt"), r"kosdaq: [\s\S]*?down<=-15%[^\n]*caught in read set ([\d.]+)%"))))),
     "9~13", ["motion", "report", "plan", "pilot", "onepager"]),
    ("소상공인 업소 수(10개 업종)", lambda: f"{sum(r['n_firms'] for r in IND().values()):,}", "894,933", ["report", "plan"]),
    ("음식점 업력<1년 폐업률", lambda: pct(IND()["072404"]["age"]["<1년"]), "14.7", ["report", "plan"]),
    ("음식점 10년+ 폐업률", lambda: pct(IND()["072404"]["age"]["10년+"]), "7.2", ["report", "plan"]),
    ("음식점 면적 하위 20% 폐업률", lambda: pct(IND()["072404"]["size"]["Q1"]), "14.2", ["report", "plan"]),
    ("헬스장 대장 포착률", lambda: f"{IND()['104201']['coverage']['ratio'] * 100:.0f}", "17", ["report", "plan"]),
    ("음식점 대장 포착률", lambda: f"{IND()['072404']['coverage']['ratio'] * 100:.0f}", "76", ["report", "plan"]),
    ("사전 가설 I1 업력", lambda: "{}/{}".format(*json.load(open(os.path.join(ROOT, "data", "caed", "industry_survival.json"), encoding="utf-8"))["I1"]), "2/9", ["report", "plan"]),
    ("헬스장 봉인 수(v2)", lambda: [l.split(",")[2] for l in txt("scoreboard/caed_gym_ledger.csv").splitlines()[1:] if "_v2" in l][0], "4416", ["report", "plan"]),
    ("카페 프랜차이즈 1년 폐업률", lambda: pct(json.load(open(os.path.join(ROOT, "data", "caed", "franchise_survival.json"), encoding="utf-8"))["franchise_rate"]), "6.2", ["report", "plan"]),
    ("카페 독립 1년 폐업률", lambda: pct(json.load(open(os.path.join(ROOT, "data", "caed", "franchise_survival.json"), encoding="utf-8"))["independent_rate"]), "15.7", ["report", "plan"]),
    ("음식점 프랜차이즈 1년 폐업률", lambda: pct(json.load(open(os.path.join(ROOT, "data", "caed", "franchise_survival_072404.json"), encoding="utf-8"))["franchise_rate"]), "6.4", ["report", "plan"]),
    ("카페 쇠퇴 브랜드 가맹점 폐업률", lambda: pct(json.load(open(os.path.join(ROOT, "data", "caed", "franchise_survival.json"), encoding="utf-8"))["momentum"]["result"]["검증 2021~24"]["low"]), "17.5", ["report", "plan"]),
    ("카페 성장 브랜드 가맹점 폐업률", lambda: pct(json.load(open(os.path.join(ROOT, "data", "caed", "franchise_survival.json"), encoding="utf-8"))["momentum"]["result"]["검증 2021~24"]["high"]), "2.5", ["report", "plan"]),
    ("카페 AUC +브랜드", lambda: f"{json.load(open(os.path.join(ROOT, 'data', 'caed', 'franchise_survival.json'), encoding='utf-8'))['auc']['brand']:.3f}", "0.778", ["report", "plan"]),
    # 10-21 공정위 외부 검증·양도/갈아타기 (caed/ftc_brands.py, caed/brand_churn.py)
    ("공정위 매칭 카페", lambda: pct(J("data/caed/ftc_brands.json")["result"]["카페"]["x1"], 0), "74", ["report"]),
    ("공정위 매칭 음식점", lambda: pct(J("data/caed/ftc_brands.json")["result"]["음식점"]["x1"], 0), "87", ["report"]),
    ("등록 이탈 건수", lambda: f'{sum(J("data/caed/ftc_brands.json")["result"][k]["n_exit"] for k in ("카페", "음식점"))}건/'
     f'{sum(v["n"] for k in ("카페", "음식점") for v in J("data/caed/ftc_brands.json")["result"][k]["exit_by_tert"].values())}건', "4건/470건", ["report", "plan"]),
    ("D1 카페 쇠퇴", lambda: pct(J("data/caed/brand_churn.json")["result"][0]["D1_tert"]["0"]), "17.0", ["report"]),
    ("D2 카페 상위", lambda: pct(J("data/caed/brand_churn.json")["result"][0]["D2_tert"]["2"]), "12.0", ["report"]),
    ("브랜드 봉인 수", lambda: txt("scoreboard/caed_brand_ledger.csv").splitlines()[1].split(",")[2], "473", ["report", "plan"]),
    # 10-22 4-4 분기 실적 반응(H-2026-10-R/S/Q)
    ("실적 표류 상위 10% 60일", lambda: f'+{pct(J("data/dintel/earnings_reaction.json")["kosdaq"]["tradable|q_sue|60"]["top"])}', "+2.9", ["report"]),
    ("실적 표류 하위 10% 60일", lambda: pct(J("data/dintel/earnings_reaction.json")["kosdaq"]["tradable|q_sue|60"]["bot"]), "-3.0", ["report"]),
    ("실적 표류 t(코스닥)", lambda: f'{J("data/dintel/earnings_reaction.json")["kosdaq"]["tradable|q_sue|60"]["t"]:.1f}', "5.1", ["report"]),
    ("실적 표류 코스피 차이", lambda: f'+{pct(J("data/dintel/earnings_reaction.json")["kospi"]["tradable|q_sue|60"]["spread"])}', "+3.5", ["report"]),
    ("분기 실적 기업 수", lambda: f'{__import__("pandas").read_parquet(os.path.join(ROOT, "data/quant/quarterly/quarterly_fin.parquet"))["stock_code"].nunique():,}', "2,408", ["report"]),
    ("PEAD 슬리브 IR", lambda: rx("data/alpha3/SUMMARY.txt", r"kosdaq H60 \|.*?excess IR ([\d.]+)"), "0.37", ["report"]),    # 10-26 CapCred: 정보공개서 에이전트 검정(H-2026-10-AC·AB2·AD)과 지난 시즌 재현
    ("AC 예상값 오차 감소", lambda: f'{(1 - J("data/caed/ftc_frcs_prefill.json")["mae_prefill"] / J("data/caed/ftc_frcs_prefill.json")["mae_copy"]) * 100:.1f}', "16.8", ["daeri", "m1", "brief"]),
    ("AC 작년 복사 오차", lambda: f'{J("data/caed/ftc_frcs_prefill.json")["mae_copy"]:.2f}', "5.54", ["daeri"]),
    ("AC 예상값 오차", lambda: f'{J("data/caed/ftc_frcs_prefill.json")["mae_prefill"]:.2f}', "4.60", ["daeri"]),
    ("AC 경보 정밀도", lambda: pct(J("data/caed/ftc_frcs_prefill.json")["alert_precision"]), "83.2", ["daeri", "brief"]),
    ("AC 경보 정밀도(반올림)", lambda: f'{J("data/caed/ftc_frcs_prefill.json")["alert_precision"] * 100:.0f}', "83", ["m1"]),
    ("AC 대상 브랜드", lambda: str(J("data/caed/ftc_frcs_prefill.json")["n_brands"]), "879", ["daeri", "m1", "brief"]),
    ("재현 브랜드 수", lambda: str(J("deliverables/business/agent_replay_public.json")["stats"]["n_brands"]), "537", ["daeri", "brief"]),
    ("재현 매장 변동", lambda: f'{J("deliverables/business/agent_replay_public.json")["stats"]["n_events"]:,}', "1,995", ["daeri", "brief"]),
    ("재현 경보 적중", lambda: f'{J("deliverables/business/agent_replay_public.json")["stats"]["alert_hit"] * 100:.0f}', "88", ["daeri", "brief"]),
    ("AB2 방향 반대 비율", lambda: pct(J("data/caed/ftc_frcs_v2.json")["AB2"]), "6.4", ["daeri", "brief"]),
    ("AD 유령 폐업 배수", lambda: f'{J("data/caed/ghost_permits_follow.json")["pooled"]["못 찾음"] / J("data/caed/ghost_permits_follow.json")["pooled"]["같은 이름"]:.1f}', "1.5", ["daeri", "brief"]),
    ("실전 봉인 브랜드 수(AF)", lambda: txt("scoreboard/caed_fdd_ledger.csv").splitlines()[1].split(",")[2], "334", ["daeri", "brief"]),
    ("AE 폐점률 순위상관", lambda: f'{J("data/caed/ftc_frcs_induty.json")["AE1"]:.2f}', "-0.02", ["daeri", "brief"]),
    ("소상공인 업소 수(CapCred)", lambda: f"{sum(r['n_firms'] for r in IND().values()):,}", "894,933", ["daeri", "f1"]),
]

# 제출물 안의 표기 변형(같은 숫자를 다르게 쓰는 경우)
ALIASES = {"0.64~0.70": ["0.64에서 0.70"], "9~13": ["9~13%", "9퍼센트에서 13퍼센트"], "0.663→0.669": ["0.663 → 0.669", "0.663에서 0.669"],
           "144/73": ["144곳", "코스닥 144"], "0.627→0.601": ["0.627 → 0.601", "0.627 -> 0.601"], "4416": ["4,416"],
           "14.7": ["14.7%"], "6.2": ["6.2%"], "15.7": ["15.7%"], "6.4": ["6.4%"], "17.5": ["17.5%"], "2.5": ["2.5%"], "7.2": ["7.2%"], "14.2": ["14.2%"], "17": ["17%"], "76": ["76%"], "3.2": ["3.2배"], "27.0": ["27퍼센트", "27.0%", "넷 중 하나"], "19.6": ["19.6퍼센트", "19.6%"], "74": ["74%"], "87": ["87%"], "17.0": ["17.0%"], "12.0": ["12.0%"], "4건/470건": ["470건 중 이탈 4건"], "83": ["83%", "83퍼센트"], "88": ["88%"], "1.5": ["1.5배"], "537": ["537개"]}


def main():
    rows, bad = [], 0
    for name, get, shown, where in CLAIMS:
        try:
            src = get()
        except Exception as e:  # noqa: BLE001
            src = f"ERR {str(e)[:40]}"
        src_ok = src is not None and str(src).replace(",", "") == shown.replace(",", "")
        miss = []
        for w in where:
            body = txt(DOCS[w])
            if not any(v in body for v in [shown] + ALIASES.get(shown, [])):
                miss.append(w)
        ok = src_ok and not miss
        bad += not ok
        rows.append(f"| {'OK' if ok else '**확인**'} | {name} | {shown} | {src} | {', '.join(where)}"
                    f"{' (없음: ' + ', '.join(miss) + ')' if miss else ''} |")
    out = ["# 제출물 숫자 대조 (자동, scripts/audit_deliverable_numbers.py)", "",
           "원천 결과 파일과 제출물 문구를 맞춘다. '확인'이 있으면 원천이 바뀌었거나 제출물 문구가 다르다.", "",
           "| 상태 | 주장 | 제출물 표기 | 원천 값 | 들어 있어야 할 곳 |", "|---|---|---|---|---|"] + rows + [
           "", f"합계 {len(rows)}개 중 확인 필요 {bad}개", "",
           "자동 대조 밖(사람 확인): 외부 출처 숫자(상폐 사유 42곳·담보대출 62조 - 헤럴드경제), 공시 26만 6천 건, 신용캐드 시연값(79.4 A -> 84.4 AA, 합성 데이터)."]
    with open(os.path.join(ROOT, "deliverables", "NUMBERS_AUDIT.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    print("\n".join(rows))
    print(f"audit: {len(rows) - bad}/{len(rows)} OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()

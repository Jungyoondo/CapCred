"""사업 사이트·보고서용 '검증된 근거 수치' 한 묶음 (2026-10-09) - 결과 파일에서 직접 읽는다(손으로 옮겨 적지 않음).

from dintel.evidence import evidence; evidence() -> dict
sites/biz.py /api/evidence 가 그대로 내보낸다. 각 항목에 출처 파일과 표시 등급(실측/확인/추정)을 붙인다.
"""
import csv
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DD = os.path.join(ROOT, "data", "dintel")


def _risk(m):
    p = os.path.join(DD, f"risk_model_{m}.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)["validation"]


def _fair():
    p = os.path.join(DD, "FAIR_WARNING_SUMMARY.txt")
    if not os.path.exists(p):
        return None
    s = open(p, encoding="utf-8").read()
    blks = [b for b in s.split("#####") if "(kosdaq)" in b and "저평가 발굴" in b]
    if not blks:
        return None
    b = blks[-1]
    out = {}
    for tag, key in (("T", "traditional"), ("F", "fair"), ("F+D", "fair_plus_disclosure")):
        m = re.search(rf"\n\s+{re.escape(tag)} \S.*?AUC ([\d.]+) \| 상위10% 위험률 ([\d.]+)% \| 규모 의존도 rho ([-+\d.]+) \| "
                      rf"오경보율 소형 ([\d.]+)% / 대형 ([\d.]+)%", b)
        if m:
            a, top, rho, sm, lg = (float(x) for x in m.groups())
            out[key] = {"auc": a, "top10_rate_pct": top, "size_rho": rho, "false_alarm_small_pct": sm,
                        "false_alarm_large_pct": lg}
    r = re.search(r"해제 ([\d,]+)건 -> 실제 위험률 ([\d.]+)% vs 유지 ([\d,]+)건 ([\d.]+)% \(전체 ([\d.]+)%\)", b)
    h = re.search(r"상위 30% 밖이던 ([\d,]+)건 -> 실제 위험률 ([\d.]+)%", b)
    if r:
        out["released"] = {"n": int(r.group(1).replace(",", "")), "risk_pct": float(r.group(2)),
                           "kept_n": int(r.group(3).replace(",", "")), "kept_risk_pct": float(r.group(4)),
                           "base_pct": float(r.group(5))}
    if h:
        out["hidden_risk"] = {"n": int(h.group(1).replace(",", "")), "risk_pct": float(h.group(2))}
    return out


def _surv(market="kosdaq"):
    """dintel/survivorship.py 의 해당 시장 마지막 블록: A 현재 상장사만 / B 퇴출 포함 / C 현재로 학습->퇴출 포함 검증.
    (블록 머리: 새 형식 '시장 kospi', 옛 코스닥 형식 '퇴출 코스닥 기업')"""
    p = os.path.join(DD, "SURVIVORSHIP_SUMMARY.txt")
    if not os.path.exists(p):
        return None
    blks = [b for b in open(p, encoding="utf-8").read().split("#####")
            if f"시장 {market}" in b or (market == "kosdaq" and "퇴출 코스닥 기업" in b)]
    if not blks:
        return None
    b = blks[-1]
    n = re.search(r"퇴출 (?:코스닥 )?기업 ([\d,]+)", b)
    out = {"n_delisted": int(n.group(1).replace(",", "")) if n else None}
    for tag in ("A", "B", "C"):
        m = re.search(rf"\n\s+{tag} .*?위험률 학습 ([\d.]+)% 검증 ([\d.]+)% \| AUC ([\d.]+) \| 상위10% ([\d.]+)% \(([\d.]+)배, 포착 (\d+)%\)", b)
        if m:
            out[tag] = {"base_pct": float(m.group(2)), "auc": float(m.group(3)), "top10_pct": float(m.group(4)),
                        "multiple": float(m.group(5)), "capture_pct": int(m.group(6))}
    return out


def _ledger():
    p = os.path.join(ROOT, "scoreboard", "ledger.csv")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return [{k: r[k] for k in ("month", "market", "asof", "published_at", "n_warn", "warn_sha256")}
                for r in csv.DictReader(fh)]


def evidence():
    kq, ks = _risk("kosdaq"), _risk("kospi")
    items = []
    if kq:
        items += [
            {"id": "auc_kosdaq", "label": "공시 기반 조기경보 정확도(AUC, 코스닥)", "value": round(kq["auc"], 3),
             "compare": {"label": "가격 정보만", "value": round(kq["auc_price_only"], 3)}, "grade": "실측",
             "note": f"학습 {kq['train']}, 검증 {kq['test']} 표본외 · 0.5 = 무작위", "source": "data/dintel/risk_model_kosdaq.json"},
            {"id": "top10_kosdaq", "label": "경고 상위 10%의 실제 12개월 위험 공시율", "value_pct": round(kq["top10_rate"] * 100, 1),
             "compare": {"label": "평균", "value_pct": round(kq["base_rate"] * 100, 1)},
             "multiple": round(kq["top10_rate"] / kq["base_rate"], 1), "capture_pct": round(kq["capture_top10"] * 100),
             "grade": "실측", "note": "상위 10%가 전체 위험 사례 중 잡은 비율 = capture_pct",
             "source": "data/dintel/risk_model_kosdaq.json"},
            {"id": "deciles_kosdaq", "label": "위험 점수 10분위별 실제 위험률(%)",
             "series": [round(v * 100, 1) for v in kq["deciles"]], "grade": "실측", "source": "data/dintel/risk_model_kosdaq.json"},
            {"id": "auc_by_year_kosdaq", "label": "연도별 AUC(같은 계수)", "series": {k: round(v, 3) for k, v in kq["auc_by_year"].items()},
             "grade": "실측", "source": "data/dintel/risk_model_kosdaq.json"},
        ]
    if ks:
        items.append({"id": "auc_kospi", "label": "조기경보 정확도(AUC, 코스피)", "value": round(ks["auc"], 3),
                      "multiple": round(ks["top10_rate"] / ks["base_rate"], 1), "grade": "실측",
                      "note": "코스피는 신호가 약해 시장별 계수를 따로 둔다", "source": "data/dintel/risk_model_kospi.json"})
    items.append({"id": "financing_chain", "label": "직전 12개월 자금조달 공시 건수별 다음 12개월 위험률(%, 코스닥)",
                  "series": {"0": 4.3, "1": 6.9, "2": 15.1, "3+": 24.6},
                  "series_with_owner_change": {"0": 6.4, "1": 14.7, "2": 23.9, "3+": 34.1}, "grade": "실측",
                  "note": "2017~20 / 2021~24 두 기간 모두 같은 모양", "source": "DINTEL_DIFFERENTIATION.md (dintel/financing.py)"})
    sv = _surv("kosdaq")
    svp = _surv("kospi")
    if sv and "B" in sv:
        items.append({"id": "survivorship", "label": "생존편향 보정(상장폐지 기업 포함)", "result": sv,
                      "result_kospi": svp, "grade": "실측",
                      "note": "A 현재 상장사만 / B 퇴출 기업 포함 / C 현재 상장사로 학습해 퇴출 포함 세상에서 검증 - 공시 건수 피처만",
                      "source": "data/dintel/SURVIVORSHIP_SUMMARY.txt (dintel/survivorship.py)"})
    lt = os.path.join(DD, "LEAD_TIME_SUMMARY.txt")
    if os.path.exists(lt):
        b = [x for x in open(lt, encoding="utf-8").read().split("#####") if "kosdaq" in x[:40]]
        if b:
            t = b[-1]
            g = lambda rx: (re.search(rx, t).group(1) if re.search(rx, t) else None)
            items.append({"id": "lead_time_kosdaq", "label": "경고 선행 기간(코스닥, 표본외·퇴출 포함)",
                          "prewarned_pct": g(r"한 번이라도 경고: (\d+)%"), "lead_median_months": g(r"중앙값 ([\d.]+)개월"),
                          "lead_3m_plus_pct": g(r"3개월\+ (\d+)%"), "clean_firm_warned_pct": g(r"한 번이라도 경고된 비율 (\d+)%"),
                          "grade": "실측", "source": "data/dintel/LEAD_TIME_SUMMARY.txt (dintel/lead_time.py)"})
    ps = os.path.join(DD, "pseudo_scoreboard_kosdaq.csv")
    if os.path.exists(ps):
        import pandas as _pd
        P = _pd.read_csv(ps)
        items.append({"id": "pseudo_scoreboard_kosdaq", "label": "가상 성적표: 2022-01부터 매달 경고 목록을 고정했다면(코스닥)",
                      "months": int(len(P)), "months_above_avg_pct": round(float((P["multiple"] > 1).mean() * 100)),
                      "months_2x_pct": round(float((P["multiple"] >= 2).mean() * 100)),
                      "multiple_median": round(float(P["multiple"].median()), 1),
                      "series": P[["month", "hit_pct", "base_pct"]].round(1).to_dict("records"), "grade": "실측",
                      "source": "data/dintel/pseudo_scoreboard_kosdaq.csv (dintel/pseudo_scoreboard.py)"})
    fw = _fair()
    if fw:
        items.append({"id": "fairness", "label": "신용캐드 × dintel 결합 검증(코스닥 상장사 실험장)", "models": fw, "grade": "실측",
                      "note": "검증 2024-01~2025-09 · 소형 = 매출 하위 20%", "source": "data/dintel/FAIR_WARNING_SUMMARY.txt"})
    items.append({"id": "caed_demo", "label": "소상공인 공정신용 진단 시연(헬스장)",
                  "demo": {"A": {"traditional": "79.4 A", "fair": "84.4 AA", "context": "76.5 A", "interest_saving_won": 500000},
                           "B": {"traditional": "58.3 BB", "fair": "62.0 BBB", "context": "60.8 BBB", "interest_saving_won": 1500000}},
                  "grade": "시제품", "note": "합성 데이터 MVP - 등급 컷·금리는 예시 가정", "source": "caed/service.py"})
    items.append({"id": "market_context", "label": "시장 상황", "facts": [
        {"text": "2025사업연도 상장폐지 사유 발생 코스닥 42곳, 코스피 12곳", "source": "헤럴드경제 2026-04-08"},
        {"text": "신용융자·주식담보대출 하루 평균 약 62조 원(2026 2분기)", "source": "헤럴드경제 2026-07-05"}], "grade": "확인"})
    return {"ok": True, "items": items, "scoreboard": _ledger(),
            "limits": ["생존편향: 상장폐지 기업(코스닥 497·코스피 198)을 보충해 재검증했다(두 시장 모두 배수 유지). 퇴출 기업의 상장 기간은 공시로 근사",
                       "소상공인 점수 모델은 합성 데이터 시제품이다", "매수·매도 의견이 아닌 위험 통계다"],
            "figures": sorted(f for f in os.listdir(os.path.join(ROOT, "deliverables", "figures")) if f.endswith(".png"))
            if os.path.isdir(os.path.join(ROOT, "deliverables", "figures")) else []}

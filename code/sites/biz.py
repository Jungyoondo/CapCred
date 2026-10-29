"""사업 사이트(:8766) - dintel × 신용캐드 (biz.html). 매수·매도 의견·실투자 엔진 점수 없음.

python -m sites.biz
엔드포인트: /api/feed?date=, /api/live?since=HH:MM, /api/watchlist?add=|remove=, /api/company?q=&llm=, /api/company/search?q=, /api/risk, /api/caed?..., /api/evidence, /api/gym, /api/status
그림: /figures/fig01_….png (deliverables/figures)
같은 원천 데이터(data/ - DART 공시, 패널, 상권 CSV)를 투자 사이트와 공유하지만 엔드포인트는 겹치지 않는다.
"""
import os
import time

from sites.common import BASE_DIR, Handler, serve

PORT = int(os.environ.get("BIZ_PORT", "8766"))   # 10-20: 영상 녹화용 공개판은 scripts/run_biz_public.ps1 (DINTEL_PUBLIC=1, 8767)
_COMPANY_CACHE = {}


def status(q):
    return {"service": "econ-lab-business-site", "modules": ["dintel", "caed"],
            "invest_site": "http://127.0.0.1:8765/"}, 200


def feed(q):
    from dintel import feed as DF
    return DF.build_feed((q.get("date") or "")[:8] or None), 200


def live(q):
    from dintel import live as DL
    return DL.build_live(since=(q.get("since") or "")[:5] or None), 200


def watchlist(q):
    from dintel import live as DL
    if q.get("add") or q.get("remove"):
        wl, msg = DL.watch_edit(add=(q.get("add") or "")[:40] or None, remove=(q.get("remove") or "")[:6] or None)
        return {"ok": True, "watchlist": wl, "message": msg}, 200
    return {"ok": True, "watchlist": DL.watchlist()}, 200


def company(q):
    from dintel import company as DC
    key = ((q.get("q") or "").strip()[:40], q.get("llm", "1"))
    hit = _COMPANY_CACHE.get(key)
    if hit and time.time() - hit[0] < 1800:
        return hit[1], 200
    body = DC.build_report(key[0], use_llm=key[1] == "1")
    _COMPANY_CACHE[key] = (time.time(), body)
    return body, 200


def company_search(q):
    from dintel import company as DC
    s = (q.get("q") or "").strip()[:40]
    _, cands = DC.resolve(s) if s else (None, [])
    return {"candidates": cands}, 200


def risk(q):
    from dintel import scoreboard as SB
    return SB.api_payload(), 200


def evidence(q):
    from dintel.evidence import evidence as ev
    return ev(), 200


def caed(q):
    import caed  # noqa: F401  (모듈 경로 설정)
    from caed import service as CS
    return CS.diagnose(q), 200


def gym(q):
    """10-20 신용캐드 실데이터 검증 묶음 - 서울 인허가 10개 업종 폐업(caed/industry_survival.py), 상권 신호(caed/location_signal.py),
    헬스장 봉인(caed/gym_survival.py). 모두 공공데이터 집계라 공개 모드에서도 보여 준다."""
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rd = lambda n: json.load(open(os.path.join(root, "data", "caed", n), encoding="utf-8"))  # noqa: E731
    try:
        ind, loc = rd("industry_survival.json"), rd("location_signal.json")
    except OSError:
        return {"ok": False, "error": "python -X utf8 -m caed.industry_survival / caed.location_signal 먼저 실행"}, 200
    rows = []
    for code, r in ind["industries"].items():
        cov = r.get("coverage") or {}
        rows.append({"code": code, "name": r["name"], "n_firms": r["n_firms"], "n_test": r["n_test"], "base": r["base"],
                     "young": r["age"].get("<1년"), "old": r["age"].get("10년+"), "q1": r["size"].get("Q1"), "q5": r["size"].get("Q5"),
                     "coverage": cov.get("ratio")})
    locs = [{"name": v["name"], "auc_b": v["B"]["auc"], "auc_e": v["E"]["auc"], "top_b": v["B"]["top10"], "top_e": v["E"]["top10"]}
            for v in loc["results"].values()]
    fr = {}
    for code, fn in (("072405", "franchise_survival.json"), ("072404", "franchise_survival_072404.json")):
        try:
            d = rd(fn)
            m = d.get("momentum", {}).get("result", {})
            fr[code] = {"name": "카페(커피숍)" if code == "072405" else "일반음식점", "n": d["n"], "franchise": d["franchise_rate"],
                        "independent": d["independent_rate"], "auc": d["auc"], "top_q": d["top_q"], "bottom_q": d["bottom_q"],
                        "decline": m.get("검증 2021~24", {}).get("low"), "growth": m.get("검증 2021~24", {}).get("high"),
                        "decline_train": m.get("학습기 2014~19", {}).get("low"), "growth_train": m.get("학습기 2014~19", {}).get("high")}
        except OSError:
            pass
    try:   # 10-25 실측 생존율 공개판(caed/survival_audit.py) - 브랜드별 값은 빼고 가맹·독립 전체와 브랜드 분포만
        sa = rd("survival_audit.json")
        surv = {"asof": sa["asof"], "industries": {c: {k: v for k, v in r.items() if k != "brands"} | {"n_brands": len(r["brands"])}
                                                    for c, r in sa["result"].items()}}
        for c, r in sa["result"].items():
            vals = {k: sorted(b[k] for b in r["brands"].values() if b[k] is not None) for k in ("long5", "surv3", "closed_avg_years")}
            surv["industries"][c]["brand_dist"] = {k: [v[len(v) // 10], v[len(v) // 2], v[(len(v) * 9) // 10]] if len(v) >= 10 else None
                                                   for k, v in vals.items()}   # 브랜드 하위 10% / 중앙 / 상위 10%
    except OSError:
        surv = None
    try:   # 10-26 H-2026-10-Z 양도 착시 보정(caed/survival_audit.py transfer) - 독립점 첫해 폐업 원값 vs 같은 자리 즉시 재개업 제외값
        tr = rd("survival_transfer.json")
        if surv is not None:
            surv["transfer"] = {"asof": tr["asof"], "industries": {c: {"label": r["label"], "verdict": r["verdict"],
                                "years": {y: [v["y1"], v["adj_y1"]] for y, v in r["years"].items() if v.get("use")}}
                                for c, r in tr["result"].items()}}
    except (OSError, KeyError):
        pass
    return {"ok": True, "asof": ind["asof"], "industries": rows, "franchise": fr, "survival": surv, "I": {"I1": ind["I1"], "I2": ind["I2"], "I3": ind["I3"]},
            "location": locs, "L1": loc["L1"], "L2": loc["L2"], "source": "서울 열린데이터광장 지방행정 인허가(LOCALDATA) · 상권분석서비스"}, 200


def brand(q):
    """10-20 브랜드 건강도 조회(caed/brand_health.py) - 공개 모드(DINTEL_PUBLIC=1)에서는 브랜드 이름을 내지 않는다(판정 전 평판 문제)."""
    from caed import brand_health as BH
    try:
        r = BH.search((q.get("q") or "").strip()[:30])
    except OSError:
        return {"ok": False, "error": "python -X utf8 -m caed.brand_health build 먼저 실행"}, 200
    # 10-24 예비 창업자 1페이지: 국면별 신규 가맹점 첫해 폐업률(H-2026-10-N 성립) + 브랜드별 개업 첫해 폐업률(H-2026-10-P 보류 - 참고·미검증)
    import json
    rd = lambda n: json.load(open(os.path.join(BASE_DIR, "data", "caed", n), encoding="utf-8"))  # noqa: E731
    try:
        ns = rd("franchise_newstore.json")["result"]
    except OSError:
        ns = None
    if os.environ.get("DINTEL_PUBLIC") == "1":
        return {"ok": True, "public": True, "asof": r["asof"], "evidence": r["evidence"], "tier_counts": r["tier_counts"], "newstore": ns}, 200
    try:
        loc = rd("brand_cohort_local.json")
        for h in r["hits"]:
            h["cohort"] = loc["brands"].get(f"{h['code']}|{h['brand']}")
        r["cohort_def"] = {"a": loc["cohort_a"], "b": loc["cohort_b"], "min_n": loc["min_n"]}
    except OSError:
        pass
    return {"ok": True, "public": False, "newstore": ns, **r}, 200


class BizHandler(Handler):
    INDEX = "biz.html"
    ROUTES = {"/api/status": status, "/api/feed": feed, "/api/live": live, "/api/watchlist": watchlist, "/api/company": company, "/api/company/search": company_search,
              "/api/risk": risk, "/api/caed": caed, "/api/evidence": evidence, "/api/gym": gym, "/api/brand": brand}
    # 제출물 그림(deliverables/figures/fig01_….png)을 사이트에서 바로 쓸 수 있게
    FILE_ROUTES = {"/figures/": ("deliverables/figures", r"fig\d{2}_[a-z0-9_]+\.png")}


def main():
    os.chdir(BASE_DIR)
    serve(BizHandler, PORT, "사업 사이트")


if __name__ == "__main__":
    main()

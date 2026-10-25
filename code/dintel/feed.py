"""오늘의 공시 - 시장 전체 공시 흐름에 과거 반응 통계를 붙여 '봐야 할 것'부터 보여준다.

python -X utf8 -m dintel.feed            # 최근 거래일
python -X utf8 -m dintel.feed 20261002   # 특정 접수일

- 대상: 코스피(Y)·코스닥(K) 상장사의 주요사항보고(B) + 거래소공시(I). 최근 7일을 한 번에 받아 10분 캐시.
- 공시마다: 유형(dintel.etypes), 같은 유형의 과거 반응 통계(event_stats*.json), 위약 차감, 밸류업 범주,
  위험 키워드 태그. 통계는 '과거 같은 유형 공시의 평균적 반응'이며 이 공시의 미래 주가 예측이 아니다.
- 정렬 단계(tier):
    1 주의   - 거래정지·관리종목·상장폐지·불성실공시·감사의견 등 위험 키워드, 또는 희석성 자금조달
    2 유의   - 과거 반응이 다중검정 보정 후에도 유의한 유형(d20 또는 발표 반응)
    3 일반   - 통계는 있으나 유의하지 않음 / 통계 없음
    4 일상   - 과거 통계상 반응이 작고 유의하지 않은 정기·절차 공시(주총소집, 명부폐쇄 등)
- 실투자 엔진(alpha3/quant)의 점수는 쓰지 않는다(사업 엔진 분리 원칙).
"""
import os
import re
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from dintel import company as DC  # noqa: E402
from dintel.etypes import etype, kind_of  # noqa: E402

MARKET = {"Y": "KOSPI", "K": "KOSDAQ"}
RISK_WORDS = ["관리종목", "상장폐지", "상장적격성", "거래정지", "매매거래정지", "불성실공시", "감사의견", "의견거절",
              "횡령", "배임", "회생절차", "파산", "부도", "투자주의환기", "자본잠식", "조회공시요구"]
# 해제·기간변경, 액면분할·병합에 따른 기술적 거래정지는 태그만 달고 '주의' 단계로 올리지 않음
RISK_EXCLUDE = ["해제", "정지기간변경", "병합", "분할", "전자등록"]
DILUTIVE = set(DC.DILUTIVE)


def _fetch(start, end):
    import dart_client as Dc
    rows = []
    for ty in ("B", "I"):
        df = Dc.search_disclosures(start_date=start, end_date=end, pblntf_ty=ty)
        if df is None or df.empty:
            continue
        df = df[df["corp_cls"].isin(list(MARKET))]
        rows += df.reindex(columns=["corp_name", "stock_code", "corp_cls", "corp_code", "report_nm", "rcept_no",
                                    "rcept_dt", "flr_nm", "rm"]).fillna("").to_dict("records")
    return rows


def recent(days_back=7):
    end = datetime.now().date()
    start = end - timedelta(days=days_back)
    return DC._cached(f"feed_{start:%Y%m%d}_{end:%Y%m%d}.json", 1 / 6, lambda: _fetch(str(start), str(end)))


def _risk(report_nm):
    n = str(report_nm).replace(" ", "")
    hits = [w for w in RISK_WORDS if w in n]
    return hits, bool(hits) and not any(x in n for x in RISK_EXCLUDE)


MATERIAL = 0.01   # 1%p: 표본이 수만 건인 거래소공시는 +0.2%도 '유의'가 되므로 경제적 크기를 함께 요구(2026-10-05)


def _sig(st, placebo=None):
    """다중검정 보정 후 유의 + 위약 차감 효과가 1%p 이상인 창이 하나라도 있으면 True."""
    if not st:
        return False
    pb = placebo or {}
    for w in ("ann2", "d10", "d20"):
        if st.get(f"{w}_sig") and st.get(w) is not None and abs(st[w] - pb.get(w, 0.0)) >= MATERIAL:
            return True
    return False


def classify(it):
    """annotate된 공시 1건에 위험 태그·중요도·단계(tier 1 위험 / 2 주의 / 3 기타 / 4 일상)를 붙인다.
    build_feed(시장 전체)와 desk(관심종목 브리프)가 같은 규칙을 쓰도록 분리(2026-10-06)."""
    st = it.get("stat")
    risk, risk_hit = _risk(it["report_nm"])
    it["risk_tags"] = risk
    nm = str(it["report_nm"]).replace(" ", "")
    if "기업가치제고" in nm:
        from dintel import valueup as VU
        it["valueup_cat"] = VU.classify(it["report_nm"])
    dil = it.get("etype") in DILUTIVE and not it["amendment"]
    k = it.get("contract") or {}
    k_st, k_pb = k.get("bucket_stat"), {"d20": k.get("placebo_d20") or 0.0}
    it["material"] = _sig(st, it.get("placebo")) or _sig(k_st, k_pb)
    if risk_hit or dil:
        tier = 1
    elif it["material"] and not it["amendment"]:
        tier = 2
    elif st and not it["material"]:
        tier = 4
    elif it["amendment"]:
        tier = 4 if not risk else 3
    else:
        tier = 3
    it["tier"] = tier
    it["dilutive"] = dil
    return it


def build_feed(date=None, days_back=7):
    rows = recent(days_back)
    dates = sorted({r["rcept_dt"] for r in rows}, reverse=True)
    if not dates:
        return {"ok": True, "date": date, "dates": [], "items": [], "counts": {}}
    date = date if date in dates else dates[0]
    day = [r for r in rows if r["rcept_dt"] == date]
    stats = DC.load_all_stats()
    items = []
    for mk in ("Y", "K"):
        part = [r for r in day if r["corp_cls"] == mk]
        items += [{**a, "market": MARKET[mk]} for a in DC.annotate(part, MARKET[mk], stats)]
    from dintel import contracts as K
    for it in items:
        if not it["amendment"] and K.kind_of(it["report_nm"]):
            info = K.annotate_item(it["rcept_no"], it["market"], it["report_nm"])
            if info:
                it["contract"] = info
        classify(it)
    items.sort(key=lambda d: (d["tier"], -abs(d.get("d20_net") or 0) if d["tier"] == 2 else 0,
                              d["market"], d["corp_name"]))
    counts = {"total": len(items), "kospi": sum(d["market"] == "KOSPI" for d in items),
              "kosdaq": sum(d["market"] == "KOSDAQ" for d in items),
              "tier": {t: sum(d["tier"] == t for d in items) for t in (1, 2, 3, 4)},
              "with_stat": sum(1 for d in items if d.get("stat"))}
    have = {k: bool(v) for k, v in stats.items()}
    return {"ok": True, "date": date, "dates": dates, "items": items, "counts": counts, "stats_loaded": have,
            "generated": f"{datetime.now():%Y-%m-%d %H:%M}", "disclaimer": DC.DISCLAIMER}


if __name__ == "__main__":
    f = build_feed(sys.argv[1] if len(sys.argv) > 1 else None)
    print(f"date {f['date']} | dates {f['dates']} | counts {f['counts']} | stats {f.get('stats_loaded')}")
    for d in f["items"][:25]:
        st = d.get("stat")
        s = f"d20 {st['d20']:+.1%} med {st['d20_med']:+.1%} n{st['n']:.0f}" if st else "-"
        print(f"  T{d['tier']} {d['market']:<6} {d['corp_name'][:10]:<10} {str(d['etype'] or d['report_nm'])[:24]:<24} "
              f"| {s} | risk {d['risk_tags']}")

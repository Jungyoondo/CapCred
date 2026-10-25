"""기업 한 장 리포트 - 기업명/종목코드 하나로 공시·재무·뉴스·위험신호·공시반응통계를 묶는다.

python -X utf8 -m dintel.company 삼성전자          # 콘솔 확인용(JSON 요약 출력)

설계 원칙(DINTEL_DESIGN.md)
- 실투자 엔진(quant/, alpha3/)의 점수·순위를 쓰지 않는다. 매수/매도 의견, 목표가 없음.
- 숫자는 전부 이 모듈이 계산한다. LLM(선택)은 계산된 사실을 문장으로 다듬기만 한다.
- 원천: PIT 가격·재무 패널(로컬), DART 공시(실시간 API, 6시간 캐시), 구글뉴스 RSS 제목(링크만, 본문 저장 안 함).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT_DIR = os.path.join(ROOT, "data", "dintel")
CACHE_DIR = os.path.join(OUT_DIR, "cache")
PANELS = {  # 시장 -> 패널(존재하는 것만 사용). kospi_full이 있으면 kospi 표본보다 우선.
    "KOSPI": [os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel_kospi_full.parquet"),
              os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel.parquet")],
    "KOSDAQ": [os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel_kosdaq_full.parquet")],
}
STATS_JSON = os.path.join(OUT_DIR, "event_stats.json")
DILUTIVE = ("유상증자결정", "전환사채권발행결정", "신주인수권부사채권발행결정", "교환사채권발행결정")
DISCLAIMER = ("이 리포트는 공개 데이터의 집계·통계이며 투자 권유나 종목 추천이 아닙니다. "
              "과거 통계는 미래 수익을 보장하지 않습니다.")

_INDEX = None
_XSEC = {}


# ---------------------------------------------------------------- 종목 찾기
def _panel_paths():
    out = []
    for mkt, paths in PANELS.items():
        for p in paths:
            if os.path.exists(p):
                out.append((mkt, p))
                break
    return out


def company_index():
    """패널 전체의 종목 목록(최신 이름/코드/업종) - 프로세스당 1회."""
    global _INDEX
    if _INDEX is None:
        frames = []
        for mkt, p in _panel_paths():
            d = pd.read_parquet(p, columns=["date", "stock_code", "corp_code", "corp_name", "industry_code"])
            d = d.sort_values("date").drop_duplicates("stock_code", keep="last")
            d["market"], d["panel"] = mkt, p
            frames.append(d)
        _INDEX = pd.concat(frames, ignore_index=True)
        _INDEX["stock_code"] = _INDEX["stock_code"].astype(str).str.zfill(6)
        _INDEX["corp_code"] = _INDEX["corp_code"].astype(str).str.zfill(8)
    return _INDEX


def resolve(query):
    """기업명(부분일치)/6자리 코드 -> (선택된 1개 행, 후보 목록)."""
    idx = company_index()
    q = str(query).strip()
    if re.fullmatch(r"\d{6}", q):
        hit = idx[idx["stock_code"] == q]
    else:
        exact = idx[idx["corp_name"] == q]
        hit = exact if len(exact) else idx[idx["corp_name"].str.contains(re.escape(q), na=False)]
    if hit.empty:
        return None, []
    hit = hit.assign(_len=hit["corp_name"].str.len()).sort_values(["_len", "stock_code"])
    cands = hit[["stock_code", "corp_name", "market"]].head(10).to_dict("records")
    return hit.iloc[0], cands


# ---------------------------------------------------------------- 패널 기반 계산
def _stock_rows(panel, code):
    cols = ["date", "stock_code", "close", "volume", "market_cap", "trading_value", "idx_KOSPI", "idx_KOSDAQ",
            "fiscal_year", "available_date", "revenue", "operating_income", "net_income", "total_equity",
            "total_assets", "operating_cash_flow", "roe", "operating_margin", "debt_ratio", "current_ratio",
            "interest_coverage_ratio", "dividend_paid", "industry_code"]
    d = pd.read_parquet(panel, columns=cols, filters=[("stock_code", "=", code)])
    return d.sort_values("date").reset_index(drop=True)


def _cross_section(panel):
    """최신일 시장 단면(동종업계 백분위 계산용) - 패널당 1회 캐시."""
    if panel not in _XSEC:
        dates = pd.read_parquet(panel, columns=["date"])["date"]
        last = dates.max()
        cols = ["date", "stock_code", "industry_code", "market_cap", "net_income", "total_equity", "roe",
                "operating_margin", "debt_ratio", "revenue_growth"]
        x = pd.read_parquet(panel, columns=cols, filters=[("date", "=", last)])
        x["per"] = x["market_cap"] / x["net_income"].where(x["net_income"] > 0)
        x["pbr"] = x["market_cap"] / x["total_equity"].where(x["total_equity"] > 0)
        x["ind2"] = x["industry_code"].astype(str).str[:2]
        _XSEC[panel] = x
    return _XSEC[panel]


PUBLIC_MODE = os.environ.get("DINTEL_PUBLIC") == "1"   # 2026-10-16 외부 공개 시: 토스 원시 시세(가격·차트) 숨김(토스 데이터 제3자 배포 금지)


def price_block(rows, market):
    if PUBLIC_MODE:
        return {"withheld": True, "series": [], "note": "공개판에서는 원시 시세를 표시하지 않습니다(데이터 이용 조건). 상용 시세 라이선스 확보 후 제공."}
    idx_col = "idx_KOSPI" if market == "KOSPI" else "idx_KOSDAQ"
    d = rows.dropna(subset=["close"]).tail(260)
    out = {"last_date": str(d["date"].iloc[-1].date()), "close": float(d["close"].iloc[-1]),
           "market_cap": float(d["market_cap"].iloc[-1]) if pd.notna(d["market_cap"].iloc[-1]) else None,
           "series": [{"d": str(r.date.date()), "c": float(r.close),
                       "i": float(getattr(r, idx_col)) if pd.notna(getattr(r, idx_col)) else None}
                      for r in d.itertuples()]}
    for name, n in (("1m", 21), ("3m", 63), ("1y", 250)):
        if len(d) > n:
            s = d["close"].iloc[-1] / d["close"].iloc[-1 - n] - 1
            m = d[idx_col].iloc[-1] / d[idx_col].iloc[-1 - n] - 1
            out[f"ret_{name}"], out[f"idx_{name}"] = float(s), float(m)
    out["vol_60"] = float(d["close"].pct_change().tail(60).std() * np.sqrt(252))
    out["adv_20"] = float(d["trading_value"].tail(20).mean()) if "trading_value" in d else None
    return out


def financial_block(rows):
    f = rows.dropna(subset=["fiscal_year"]).sort_values("date").drop_duplicates("fiscal_year", keep="last")
    f = f.sort_values("fiscal_year").tail(5)
    keys = ["revenue", "operating_income", "net_income", "total_equity", "total_assets", "operating_cash_flow",
            "roe", "operating_margin", "debt_ratio", "current_ratio", "interest_coverage_ratio"]
    years = []
    for r in f.itertuples():
        y = {"fiscal_year": int(r.fiscal_year), "available_date": str(pd.Timestamp(r.available_date).date())
             if pd.notna(r.available_date) else None}
        for k in keys:
            v = getattr(r, k)
            y[k] = float(v) if pd.notna(v) else None
        years.append(y)
    return years


def peer_block(rows, panel):
    x = _cross_section(panel)
    code = rows["stock_code"].iloc[-1]
    me = x[x["stock_code"] == code]
    if me.empty:
        return None
    ind = me["ind2"].iloc[0]
    peers = x[x["ind2"] == ind]
    out = {"industry2": ind, "n_peers": int(len(peers)), "metrics": {}}
    for k, better in (("per", "low"), ("pbr", "low"), ("roe", "high"), ("operating_margin", "high"),
                      ("debt_ratio", "low"), ("revenue_growth", "high")):
        v = me[k].iloc[0]
        col = peers[k].dropna()
        if pd.isna(v) or len(col) < 5:
            continue
        pct = float((col < v).mean())
        out["metrics"][k] = {"value": float(v), "peer_median": float(col.median()), "pct": pct,
                             "better": better}
    return out


# ---------------------------------------------------------------- DART 공시
def _cached(name, ttl_h, fn):
    os.makedirs(CACHE_DIR, exist_ok=True)
    p = os.path.join(CACHE_DIR, name)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < ttl_h * 3600:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    val = fn()
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(val, fh, ensure_ascii=False, default=str)
    return val


def etype_of(report_nm):
    from dintel.etypes import etype
    return etype(report_nm)


def disclosures(corp_code):
    import dart_client as Dc

    def fetch():
        end = datetime.now().date()
        recent = Dc.search_disclosures(corp_code=corp_code, start_date=str(end - timedelta(days=365)),
                                       end_date=str(end))
        major = Dc.search_disclosures(corp_code=corp_code, start_date=str(end - timedelta(days=3 * 365)),
                                      end_date=str(end), pblntf_ty="B")
        cols = ["rcept_dt", "rcept_no", "report_nm", "flr_nm"]
        to = lambda df: [] if df is None or df.empty else df.reindex(columns=cols).fillna("").to_dict("records")
        return {"recent": to(recent), "major3y": to(major)}
    return _cached(f"disc_{corp_code}.json", 6, fetch)


def load_stats(kind="B"):
    """kind B=주요사항보고(event_stats.json), I=거래소공시(event_stats_I.json)."""
    path = STATS_JSON if kind == "B" else STATS_JSON.replace(".json", f"_{kind}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get("markets", {})


def load_all_stats():
    return {"B": load_stats("B"), "I": load_stats("I")}


_OOS = {"mtime": None, "types": {}}


def _oos_types():
    """dintel.oos_check 결과: 시장 -> 유형 -> 학습(~2021-11)/검증(2022~) 효과. 없으면 빈 dict."""
    p = os.path.join(OUT_DIR, "oos_stats.json")
    if not os.path.exists(p):
        return {}
    mt = os.path.getmtime(p)
    if _OOS["mtime"] != mt:
        with open(p, encoding="utf-8") as fh:
            _OOS.update(mtime=mt, types=json.load(fh).get("oos", {}).get("types", {}))
    return _OOS["types"]


def annotate(items, market, stats):
    """공시마다 같은 유형의 과거 반응 통계를 붙인다(시장별 우선, 없으면 합산).
    stats: load_all_stats()의 {"B": .., "I": ..} 또는 예전 형식(B만)."""
    from dintel.etypes import kind_of
    by_kind = stats if set(stats) <= {"B", "I"} else {"B": stats}

    def pools_for(kind):
        st = by_kind.get(kind) or {}
        mk = market.lower()
        if mk == "kospi" and "kospi_full" in st:
            mk = "kospi_full"
        # 우선순위: 같은 시장 -> 시장 합산 -> 다른 시장(출처를 함께 표시해 혼동 방지)
        order = [mk] + [k for k in st if "+" in k] + [k for k in st if k != mk and "+" not in k]
        return mk, st, [(k, st.get(k, {}).get("types", {})) for k in order]
    P = {k: pools_for(k) for k in ("B", "I")}
    out = []
    for it in items:
        et = etype_of(it["report_nm"])
        kind = kind_of(it["report_nm"])
        mk, kstats, pools = P[kind]
        src, st = next(((k, p[et]) for k, p in pools if et and et in p), (None, None))
        pb = kstats.get(src, {}).get("placebo") if src else None
        oos = _oos_types().get(mk if mk in _oos_types() else ("kospi_full" if mk == "kospi" else mk), {}).get(et)
        out.append({**it, "etype": et, "kind": kind, "amendment": str(it["report_nm"]).startswith("["), "oos": oos,
                    "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={it['rcept_no']}",
                    "stat": st, "stat_src": src, "stat_same_market": src == mk,
                    "placebo": pb,
                    "d20_net": (st["d20"] - pb["d20"]) if st and pb else None})
    return out


SIZE_JSON = os.path.join(OUT_DIR, "event_size_stats.json")
VALUEUP_JSON = os.path.join(OUT_DIR, "valueup_stats.json")


def _corp_of(stock_code):
    idx = company_index()
    h = idx[idx["stock_code"] == stock_code]
    return h["corp_code"].iloc[0] if len(h) else None


def valueup_annotate(items, market, rows):
    """밸류업(기업가치 제고 계획) 공시에 범주(예고/첫 본공시/갱신/이행현황) 통계와 대조군 차감값을 붙인다."""
    from dintel import valueup as VU
    vu = [d for d in items if "기업가치제고" in str(d["report_nm"]).replace(" ", "")]
    if not vu or not os.path.exists(VALUEUP_JSON):
        return items
    with open(VALUEUP_JSON, encoding="utf-8") as fh:
        stats = json.load(fh).get("markets", {})
    mk = market.lower()
    src = mk if mk in stats else next((k for k in stats if "+" in k), next(iter(stats), None))
    groups = {g["group"]: g for g in stats.get(src, {}).get("groups", []) if not g.get("skip")}
    # 첫/갱신 구분은 2024-05 이후 밸류업 이력(valueup_raw 캐시)으로 판단 - 최근 1년 공시만으론 알 수 없음
    corp = str(rows["stock_code"].iloc[-1])
    hist_dates = []
    for pm in (VU.panel_for(mk), mk):
        f = os.path.join(VU.RAW, pm, f"{d_corp}.json") if (d_corp := _corp_of(corp)) else None
        if f and os.path.exists(f):
            hist_dates = sorted(r["rcept_dt"] for r in json.load(open(f, encoding="utf-8"))
                                if VU.classify(r["report_nm"]) == "본공시")
            break
    for d in vu:
        cat = VU.classify(d["report_nm"])
        if cat is None:
            continue
        if cat == "본공시":
            if hist_dates:
                cat = "첫 본공시" if str(d["rcept_dt"]) <= hist_dates[0] else "갱신 본공시"
            else:
                cat = "첫 본공시"          # 이력 캐시가 없으면 추정(화면에 표시)
                d["valueup_note"] = "이력 미수집 - 첫 본공시로 추정"
        d["valueup"] = {"category": cat, "stat": groups.get(cat), "src": src}
        if cat in ("첫 본공시", "갱신 본공시"):
            d["valueup"]["plan"] = _plan_content(d["rcept_no"])
    return items


def contract_annotate(items, market, limit=12):
    """단일판매ㆍ공급계약 공시(최근 limit건)에 매출액 대비 %와 같은 규모 구간의 과거 반응을 붙인다."""
    from dintel import contracts as K
    n = 0
    for d in sorted(items, key=lambda x: str(x["rcept_dt"]), reverse=True):
        if n >= limit or d.get("amendment") or K.kind_of(d["report_nm"]) is None:
            continue
        info = K.annotate_item(d["rcept_no"], market, d["report_nm"])
        n += 1
        if info:
            d["contract"] = info
    return items


def _plan_content(rcept_no):
    """밸류업 계획 본문에서 목표 수치·정책 키워드를 뽑고, 같은 '숫자 목표 개수' 그룹의 과거 통계를 붙인다."""
    from dintel import valueup_text as VT
    p = os.path.join(VT.DOCS, f"{rcept_no}.txt")
    try:
        if not os.path.exists(p):
            txt, _ = VT.fetch_text(rcept_no)
            if txt:
                os.makedirs(VT.DOCS, exist_ok=True)
                open(p, "w", encoding="utf-8").write(txt)
        if not os.path.exists(p):
            return None
        f = VT.parse(open(p, encoding="utf-8").read())
    except Exception:
        return None
    f = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in f.items()}
    grp = "숫자목표 0개" if f["n_targets"] == 0 else ("숫자목표 1개" if f["n_targets"] == 1 else "숫자목표 2개+")
    st = None
    if os.path.exists(VT.STATS_JSON):
        st = next((g for g in json.load(open(VT.STATS_JSON, encoding="utf-8"))["groups"]
                   if g["group"] == grp and not g.get("skip")), None)
    return {**f, "group": grp, "group_stat": st}


def size_annotate(items, corp_code, rows, market):
    """공시마다 상세(금액·비율·방식)를 DART에서 받아 규모를 계산하고, 과거 같은 유형의
    규모 3분위 구간·방식 범주 통계를 붙인다(dintel.size_reaction 결과 필요)."""
    from dintel import details as DT
    if not os.path.exists(SIZE_JSON):
        return items
    with open(SIZE_JSON, encoding="utf-8") as fh:
        size_stats = json.load(fh).get("markets", {})
    mk = market.lower()
    if mk == "kospi" and "kospi_full" in size_stats:
        mk = "kospi_full"
    order = [mk] + [k for k in size_stats if "+" in k] + [k for k in size_stats if k != mk and "+" not in k]
    need = sorted({d["etype"] for d in items if d.get("etype") in DT.SPECS and not d["amendment"]})
    if not need:
        return items
    import dart_client as Dc

    def fetch():
        end = datetime.now().strftime("%Y%m%d")
        start = (datetime.now() - timedelta(days=400)).strftime("%Y%m%d")
        out = {}
        for et in need:
            r = Dc._get(f"{DT.SPECS[et][0]}.json", {"corp_code": corp_code, "bgn_de": start, "end_de": end}).json()
            out[et] = r.get("list", []) if r.get("status") == "000" else []
        return out
    try:
        det = _cached(f"detail_{corp_code}_{'_'.join(need)}.json"[:150], 6, fetch)
    except Exception:
        return items
    mcap = rows.dropna(subset=["market_cap"]).set_index("date")["market_cap"]
    for d in items:
        et = d.get("etype")
        # 상세 API는 최종 정정본 접수번호를 준다 -> 원공시일 이후 90일 이내 가장 가까운 기록
        cands = sorted((str(x.get("rcept_no"))[:8], i, x) for i, x in enumerate(det.get(et, []))
                       if str(d["rcept_dt"]) <= str(x.get("rcept_no"))[:8] <=
                       (pd.Timestamp(d["rcept_dt"]) + pd.Timedelta(days=90)).strftime("%Y%m%d"))
        rec = cands[0][2] if cands else None
        if not rec:
            continue
        before = mcap[mcap.index < pd.Timestamp(d["rcept_dt"])]
        size = DT.SPECS[et][1](rec, float(before.iloc[-1]) if len(before) else None)
        mfield = DT.SPECS[et][3]
        method = DT.norm_method(rec.get(mfield)) if mfield else None
        info = {"size": None if not np.isfinite(size) else float(size), "size_def": DT.SPECS[et][2],
                "method": method}
        for k in order:
            blk = size_stats.get(k, {})
            meta = blk.get("meta", {}).get(et)
            if not meta:
                continue
            q1, q2 = meta["cuts"]
            if info["size"] is not None:
                if meta.get("tie"):
                    b = "소" if info["size"] < q1 and not np.isclose(info["size"], q1) else                         ("중" if np.isclose(info["size"], q1) else "대")
                else:
                    b = "소" if info["size"] <= q1 else ("중" if info["size"] <= q2 else "대")
                info["bucket"] = b
                info["bucket_stat"] = next((r for r in blk["rows"] if r["etype"] == et and r["kind"] == "size"
                                            and r["group"] == b), None)
            if method:
                info["method_stat"] = next((r for r in blk["rows"] if r["etype"] == et and r["kind"] == "method"
                                            and r["group"] == method), None)
            info["src"] = k
            break
        d["size_info"] = info
    return items


# ---------------------------------------------------------------- 뉴스
def news_block(name):
    def fetch():
        if os.path.join(ROOT, "research") not in sys.path:
            sys.path.append(os.path.join(ROOT, "research"))  # news_* live in research/
        import news_sentiment as NS
        import news_trend as NT
        df = NT.fetch_news(f'"{name}"', days=30, max_articles=60)
        if df.empty:
            return []
        scores, matches = NS.score_titles(df["title"].tolist())
        df["sent"], df["words"] = scores, [", ".join(m[:3]) for m in matches]
        df = df.sort_values("published", ascending=False)
        return [{"title": r.title, "link": r.link, "source": r.source,
                 "published": str(r.published)[:16] if pd.notna(r.published) else "",
                 "sent": int(r.sent), "words": r.words} for r in df.itertuples()]
    try:
        return _cached(f"news_{re.sub(r'[^0-9A-Za-z가-힣]', '_', name)}.json", 3, fetch)
    except Exception as e:  # 뉴스 실패가 리포트 전체를 막지 않게
        return [{"error": str(e)[:200]}]


# ---------------------------------------------------------------- 위험 신호(규칙 기반, 투명)
def risk_flags(fin, disc, price):
    flags = []
    last = fin[-1] if fin else {}

    def krw(v):
        return "—" if v is None else (f"{v / 1e12:.1f}조" if abs(v) >= 1e12 else f"{v / 1e8:,.0f}억")

    def add(key, label, hit, value, rule, display=None):
        flags.append({"key": key, "label": label, "hit": bool(hit), "value": value, "rule": rule,
                      "display": display if display is not None else str(value)})

    major = [d for d in disc.get("major3y", []) if not str(d["report_nm"]).startswith("[")]
    cutoff = (datetime.now() - timedelta(days=730)).strftime("%Y%m%d")
    dil = [d for d in major if etype_of(d["report_nm"]) in DILUTIVE and d["rcept_dt"] >= cutoff]
    add("dilution", "최근 2년 지분희석성 자금조달(유상증자·CB·BW·EB)", len(dil) >= 2, len(dil), "2건 이상", f"{len(dil)}건")
    ops = [y.get("operating_income") for y in fin[-3:] if y.get("operating_income") is not None]
    add("op_loss", "최근 3개년 연속 영업적자", len(ops) == 3 and all(v < 0 for v in ops),
        ops, "3개년 모두 음수", " / ".join(krw(v) for v in ops) or "—")
    eq = last.get("total_equity")
    add("neg_equity", "자본잠식(자본총계 음수)", eq is not None and eq < 0, eq, "자본총계 < 0", krw(eq))
    dr = last.get("debt_ratio")
    add("high_debt", "부채비율 과다", dr is not None and dr > 2.0, dr, "부채비율 > 200%", "—" if dr is None else f"{dr:.0%}")
    ic = last.get("interest_coverage_ratio")
    add("int_cover", "이자보상배율 1 미만(영업이익으로 이자 감당 못함)", ic is not None and ic < 1, ic, "< 1", "—" if ic is None else f"{ic:.2f}배")
    ni, ocf, ta = last.get("net_income"), last.get("operating_cash_flow"), last.get("total_assets")
    acc = (ni - ocf) / ta if None not in (ni, ocf, ta) and ta else None
    add("accruals", "발생액 과다(현금 뒷받침 없는 이익)", acc is not None and acc > 0.10, acc,
        "(순이익-영업현금흐름)/총자산 > 10%", "—" if acc is None else f"{acc:+.1%}")
    recent = disc.get("recent", [])
    amend = sum(str(d["report_nm"]).startswith("[기재정정]") for d in recent)
    share = amend / len(recent) if recent else 0.0
    add("amend", "최근 1년 정정공시 비중 과다", amend >= 5 and share >= 0.2, f"{amend}건/{len(recent)}건({share:.0%})",
        "5건 이상 그리고 회사 공시의 20% 이상")
    owner = [d for d in recent if "최대주주" in str(d["report_nm"]) and "변경" in str(d["report_nm"])]
    add("owner", "최근 1년 최대주주 변경 공시", len(owner) > 0, len(owner), "1건 이상", f"{len(owner)}건")
    adv = price.get("adv_20")
    add("illiquid", "거래대금 과소(20일 평균)", adv is not None and adv < 5e8, adv, "< 5억원", krw(adv))
    return flags


# ---------------------------------------------------------------- 요약
def earnings_block(code, market):
    """10-22 분기 실적 + 실적 발표 뒤 시장 반응(사전 등록 H-2026-10-R 성립: 코스닥 60일 상위-하위 10% +5.9% t 5.1).
    분기 숫자 = DART 다중회사 주요계정(data/quant/quarterly), 반응 통계 = data/dintel/earnings_reaction.json(집계 통계).
    SUE = (영업이익 - 전년 같은 분기) / 직전 8분기 그 차이의 표준편차. 분위 = 최근 90일 같은 시장 접수 중 위치."""
    try:
        from alpha3 import quarterly as QF      # 분기 재무 계산 모듈(모델·점수 아님)
        q = pd.read_parquet(QF.QFILE)
        qt = QF.quarter_table()
        st = json.load(open(os.path.join(OUT_DIR, "earnings_reaction.json"), encoding="utf-8")).get(market.lower(), {})
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:120]}
    me = q[q["stock_code"] == code].sort_values(["year", "q"])
    if me.empty:
        return {"quarters": []}
    rows = []
    for r in me.tail(8).itertuples():
        prev = me[(me["year"] == r.year - 1) & (me["q"] == r.q)]
        pr, po = (float(prev["rev"].iloc[0]), float(prev["op"].iloc[0])) if len(prev) else (None, None)
        rows.append({"q": f"{r.year}Q{r.q}", "rev": float(r.rev) if r.rev == r.rev else None, "op": float(r.op) if r.op == r.op else None,
                     "rev_yoy": (r.rev / pr - 1) if pr and pr > 0 and r.rev == r.rev else None,
                     "filed": str(r.filed)[:10] if r.filed == r.filed else None})
    out = {"quarters": rows}
    mine = qt[qt["stock_code"] == code].dropna(subset=["q_sue"])
    if len(mine):
        last = mine.iloc[-1]
        codes = set(company_index().query("market == @market")["stock_code"]) if "market" in company_index() else None
        win = qt[(qt["avail"] > last["avail"] - pd.Timedelta(days=90)) & (qt["avail"] <= last["avail"])]
        if codes:
            win = win[win["stock_code"].isin(codes)]
        win = win["q_sue"].dropna()
        if len(win) >= 100:
            pct = float((win <= last["q_sue"]).mean())
            dec = min(int(pct * 10), 9)
            s60, s20 = st.get("tradable|q_sue|60"), st.get("tradable|q_sue|20")
            out.update({"sue": float(last["q_sue"]), "pct": pct, "decile": dec + 1, "filed": str(last["avail"] - pd.Timedelta(days=1))[:10],
                        "d60": s60["deciles"][dec] if s60 else None, "d20": s20["deciles"][dec] if s20 else None,
                        "top60": s60["top"] if s60 else None, "bot60": s60["bot"] if s60 else None,
                        "n_events": s60["events"] if s60 else None})
    return out


def facts_summary(rep):
    """계산된 사실만으로 만든 요약 문장(LLM 없이 항상 생성)."""
    p, fin, flags = rep["price"], rep["financials"], rep["risk_flags"]
    s = []
    if "ret_3m" in p:
        rel = p["ret_3m"] - p["idx_3m"]
        s.append(f"최근 3개월 주가는 {p['ret_3m']:+.1%}로 지수 대비 {rel:+.1%}p.")
    if len(fin) >= 2 and fin[-1].get("revenue") and fin[-2].get("revenue"):
        g = fin[-1]["revenue"] / fin[-2]["revenue"] - 1
        s.append(f"{fin[-1]['fiscal_year']}년 매출은 전년 대비 {g:+.1%}"
                 + (f", 영업이익률 {fin[-1]['operating_margin']:.1%}." if fin[-1].get("operating_margin") is not None else "."))
    hits = [f["label"] for f in flags if f["hit"]]
    s.append(f"위험 신호 {len(hits)}개" + (f": {', '.join(hits[:3])}." if hits else " - 점검 항목 모두 통과."))
    ann = [d for d in rep["disclosures"] if d.get("stat") and not d["amendment"]]
    if ann:
        d = ann[0]; st = d["stat"]
        src = "" if d["stat_same_market"] else f"({d['stat_src']} 시장 통계 차용) "
        s.append(f"최근 주요공시 '{d['etype']}'({d['rcept_dt']})는 {src}과거 {int(st['n'])}건 기준 발표 반응 평균 "
                 f"{st['ann2']:+.1%}(중앙 {st['ann2_med']:+.1%}), 이후 20일 중앙값 {st['d20_med']:+.1%}였다.")
    e = rep.get("earnings") or {}
    if e.get("decile"):
        s.append(f"최근 분기 보고서({e['filed']} 접수)의 실적 서프라이즈는 최근 90일 접수 기업 중 10분위 {e['decile']}로, "
                 f"과거 같은 분위는 접수 다음 날부터 60거래일 시장 대비 평균 {e['d60']:+.1%}였다.")
    nws = [n for n in rep["news"] if "sent" in n]
    if nws:
        pos = sum(n["sent"] > 0 for n in nws); neg = sum(n["sent"] < 0 for n in nws)
        s.append(f"최근 30일 뉴스 {len(nws)}건(긍정 {pos}, 부정 {neg}, 감성사전 기준).")
    return " ".join(s)


def _load_env_key():
    """.env에 ANTHROPIC_API_KEY가 있으면 환경변수로(값은 출력하지 않음)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    p = os.path.join(ROOT, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip().strip('"')


def llm_summary(rep, facts_text):
    """선택: ANTHROPIC_API_KEY와 anthropic 패키지가 있으면 계산된 사실을 자연스러운 한국어로 다듬는다.
    숫자를 새로 만들지 않도록 지시하고, 실패하면 None(사실 요약만 사용)."""
    try:
        import anthropic
    except ImportError:
        return None
    _load_env_key()
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    payload = {k: rep[k] for k in ("company", "price", "financials", "peers", "risk_flags")}
    payload["price"] = {k: v for k, v in rep["price"].items() if k != "series"}
    payload["disclosures"] = [{k: d[k] for k in ("rcept_dt", "report_nm", "etype", "stat")}
                              for d in rep["disclosures"][:12]]
    payload["news_titles"] = [n.get("title") for n in rep["news"][:15]]
    system = ("너는 한국 상장기업 공시·재무 데이터를 일반 투자자에게 설명하는 리서치 보조다. "
              "주어진 JSON 사실만 사용하고 새로운 숫자를 만들지 마라. 매수·매도 의견, 목표주가, 전망을 쓰지 마라. "
              "통계는 '과거 사례 기준'임을 밝혀라. 한국어 4~6문장, 평서문.")
    try:
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=16000,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": "사실 JSON:\n" + json.dumps(payload, ensure_ascii=False, default=str)
                       + "\n\n규칙 기반 초안:\n" + facts_text}],
        )
        if resp.stop_reason == "refusal":
            return None
        return "".join(b.text for b in resp.content if b.type == "text").strip() or None
    except Exception as e:  # anthropic.APIError 계열 포함 - 요약은 선택 기능이라 조용히 폴백
        print(f"[dintel] LLM 요약 실패, 사실 요약만 사용: {type(e).__name__}", flush=True)
        return None


# ---------------------------------------------------------------- 진입점
def build_report(query, use_llm=True):
    row, cands = resolve(query)
    if row is None:
        return {"ok": False, "error": f"'{query}'에 해당하는 상장사를 찾지 못했습니다(현재 패널: "
                                       f"코스피 {'전체' if os.path.exists(PANELS['KOSPI'][0]) else '385종목 표본'}, 코스닥 전체).",
                "candidates": []}
    code, market, panel = row["stock_code"], row["market"], row["panel"]
    rows = _stock_rows(panel, code)
    price = price_block(rows, market)
    fin = financial_block(rows)
    try:
        disc = disclosures(row["corp_code"])
        disc_err = None
    except Exception as e:
        disc, disc_err = {"recent": [], "major3y": []}, str(e)[:200]
    # 회사 본인이 낸 공시만 목록에(임원·주주가 제출하는 지분보고서는 건수만 별도 집계)
    insider = [d for d in disc["recent"] if d.get("flr_nm") != row["corp_name"]]
    disc = {"recent": [d for d in disc["recent"] if d.get("flr_nm") == row["corp_name"]],
            "major3y": disc["major3y"]}
    stats = load_all_stats()
    rep = {
        "ok": True, "generated": f"{datetime.now():%Y-%m-%d %H:%M}",
        "company": {"name": row["corp_name"], "stock_code": code, "corp_code": row["corp_code"], "market": market,
                    "industry_code": str(row["industry_code"])},
        "candidates": cands, "price": price, "financials": fin, "peers": peer_block(rows, panel),
        "disclosures": contract_annotate(valueup_annotate(
            size_annotate(annotate(disc["recent"], market, stats), row["corp_code"], rows, market), market, rows),
            market),
        "disclosure_error": disc_err,
        "insider_filings_1y": len(insider),
        "news": news_block(row["corp_name"]),
        "stats_meta": {f"{kd}:{k}": v.get("meta") for kd, st in stats.items() for k, v in st.items()},
        "disclaimer": DISCLAIMER,
    }
    rep["earnings"] = earnings_block(code, market)
    rep["risk_flags"] = risk_flags(fin, disc, price)
    rep["summary_facts"] = facts_summary(rep)
    rep["summary_ai"] = llm_summary(rep, rep["summary_facts"]) if use_llm else None
    return rep


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "삼성전자"
    r = build_report(q, use_llm=False)
    if not r["ok"]:
        print(r["error"]); sys.exit(1)
    print(json.dumps({k: r[k] for k in ("company", "summary_facts")}, ensure_ascii=False, indent=1))
    print("risk:", [(f["key"], f["hit"], f["value"]) for f in r["risk_flags"]])
    print("disclosures:", len(r["disclosures"]), "| with stat:", sum(1 for d in r["disclosures"] if d["stat"]),
          "| news:", len(r["news"]), "| fin years:", [y["fiscal_year"] for y in r["financials"]])
    print("peers:", r["peers"])

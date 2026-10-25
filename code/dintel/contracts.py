"""단일판매ㆍ공급계약 공시 - '매출액 대비 %'(계약 규모)별 시장 반응.

python -X utf8 -m dintel.contracts collect kospi_full kosdaq   # 원문 수집(이어받기, DART 한도 시 중단)
python -X utf8 -m dintel.contracts parse-check                 # 파싱 표본 출력(사람 검수용)
python -X utf8 -m dintel.contracts analyze kospi_full kosdaq   # -> CONTRACT_SUMMARY.txt, contract_stats.json

## 대상
거래소공시 이력(collect_events --kind I의 events_raw_I/<market>/) 중 원공시(대괄호 접두 없음)인
'단일판매ㆍ공급계약체결'(자율공시·자회사 주요경영사항 포함)과 '단일판매ㆍ공급계약해지'.
'기타경영사항(…공급계약 진행사항)'은 제외. 같은 기업 같은 날 여러 건이면 매출액 대비가 가장 큰 1건.

## 원문 (2026-10-04 실측)
document.xml 요약본(500~800자)에 표 형태로: 계약금액(원) / 최근 매출액(원) / 매출액 대비(%) /
계약상대방(-회사와의 관계) / 판매ㆍ공급지역 / 계약기간 시작일·종료일 / (2020년대) 조건부 계약여부.
2010년대 문서는 EUC-KR - valueup_text.fetch_text가 자동 판별. 2020년대 양식은 계약상대방의 최근 매출액도
적혀 있어, 회사 매출액은 '최근 매출액' 첫 번째 값만 쓴다.

## 변수
ratio      매출액 대비(%) - 원문 값. 없으면 계약금액/최근매출액으로 계산
voluntary  자율공시(의무공시 기준 미만 규모를 회사가 자진 공시)
sub        자회사(종속회사) 계약
cond       조건부 계약 해당
related    계약상대방이 계열·종속·최대주주 등 특수관계
repeat     같은 상대와 최근 3년간 동종계약 이행 이력(2020년대 양식만, 없으면 None)
overseas   판매ㆍ공급지역이 국내(대한민국·국내·한국)가 아님
years      계약기간(년)
## 분석
같은 방법론(event_reaction.reactions_for): 시장 동일가중 대비 초과수익, 위약(같은 종목 무작위 날짜) 차감,
달력월 블록 부트스트랩 95%CI, 그룹 전체에 BH(q=0.10). 규모 구간은 해석하기 쉬운 고정 구간
(<5%, 5~10%, 10~20%, 20~50%, 50%+)을 시장별로.
"""
import glob
import json
import os
import re
import sys
import time

import numpy as np
import pandas as pd

from dintel import event_reaction as ER
from dintel.valueup_text import fetch_text

OUT_DIR = ER.OUT_DIR
DOCS = os.path.join(OUT_DIR, "contract_docs")
SUMMARY = os.path.join(OUT_DIR, "CONTRACT_SUMMARY.txt")
STATS_JSON = os.path.join(OUT_DIR, "contract_stats.json")
PARSED_CSV = os.path.join(OUT_DIR, "contracts_parsed.csv")   # 공시별 파싱 결과(엔진 공유용 데이터)
MIN_N = int(os.environ.get("DINTEL_MIN_N", "30"))
BINS = [(0, 5, "<5%"), (5, 10, "5~10%"), (10, 20, "10~20%"), (20, 50, "20~50%"), (50, 1e9, "50%+")]
WIN = ("ann2", "d10", "d20", "d60", "pre20")


def bucket(ratio):
    if ratio is None or not np.isfinite(ratio):
        return None
    return next(lab for lo, hi, lab in BINS if lo <= ratio < hi)


def kind_of(report_nm):
    n = str(report_nm).replace(" ", "")
    if n.startswith("[") or not n.startswith("단일판매"):
        return None
    if "공급계약해지" in n:
        return "해지"
    if "공급계약체결" in n:
        return "체결"
    return None


def events(markets):
    """events_raw_I 캐시에서 바로 읽는다(병합 파일이 없어도 부분 수집분으로 동작)."""
    rows = []
    for m in markets:
        files = glob.glob(os.path.join(OUT_DIR, "events_raw_I", m, "*.csv"))
        for f in files:
            d = pd.read_csv(f, dtype=str)
            if len(d):
                rows.append(d.assign(market=m))
    if not rows:
        return pd.DataFrame(columns=["corp_code", "rcept_dt", "rcept_no", "report_nm", "market", "ckind"])
    ev = pd.concat(rows, ignore_index=True)
    ev["ckind"] = ev["report_nm"].map(kind_of)
    ev = ev.dropna(subset=["ckind"]).drop_duplicates("rcept_no")
    ev["corp_code"] = ev["corp_code"].str.zfill(8)
    return ev.reset_index(drop=True)


# ---------------------------------------------------------------- 파싱
_N = r"([\d,]+(?:\.\d+)?)"
# 판매ㆍ공급지역에 외국 지명이 하나라도 있으면 해외(국내+해외 혼합 포함). 국내 지명 목록은 끝이 없어 반대로 정의.
FOREIGN = (r"해외|미국|중국|일본|대만|홍콩|베트남|인도|태국|필리핀|말레이|싱가포르|인도네시아|유럽|독일|프랑스|영국|"
           r"이탈리아|스페인|폴란드|헝가리|체코|네덜란드|스웨덴|노르웨이|핀란드|러시아|튀르키예|터키|중동|사우디|"
           r"아랍|UAE|카타르|쿠웨이트|이라크|이란|이스라엘|이집트|아프리카|북미|남미|중남미|멕시코|브라질|캐나다|칠레|"
           r"호주|뉴질랜드|아시아|글로벌|전세계|세계|[A-Za-z]{3,}")


def _num(s):
    try:
        return float(s.replace(",", ""))
    except (AttributeError, ValueError):
        return None


def parse(text):
    t = re.sub(r"\s+", " ", text)
    # 계약상대방 블록 앞까지만(2020년대 양식은 상대방 매출액도 '최근 매출액'으로 적혀 있음)
    head = re.split(r"3\.\s*계약상대", t, maxsplit=1)[0]
    amt = re.search(r"계약금액\s*총액\s*\(원\)\s*" + _N, head) or re.search(r"계약금액\s*\(원\)\s*" + _N, head) \
        or re.search(r"(?:해지|확정)\s*계약금액\s*(?:\(원\))?\s*" + _N, head) or re.search(r"계약금액\s*" + _N, head)
    rev = re.search(r"최근\s*매출액\s*\(원\)\s*" + _N, head)
    rat = re.search(r"매출액\s*대비\s*\(%\)\s*" + _N, head)
    amount, revenue, ratio = _num(amt.group(1)) if amt else None, _num(rev.group(1)) if rev else None, \
        _num(rat.group(1)) if rat else None
    calc = amount / revenue * 100 if amount and revenue else None
    if ratio is None and calc is not None:
        ratio = calc
    rel = re.search(r"회사와의\s*관계\s*(.{0,30})", t)
    rel_txt = rel.group(1) if rel else ""
    region = re.search(r"판매ㆍ?\s*공급\s*지역\s*(.{0,40}?)\s*5\.", t)
    reg_txt = region.group(1).strip() if region else ""
    per = re.search(r"시작일\s*(\d{4}-\d{2}-\d{2})\s*종료일\s*(\d{4}-\d{2}-\d{2})", t)
    years = None
    if per:
        try:
            years = (pd.Timestamp(per.group(2)) - pd.Timestamp(per.group(1))).days / 365.25
        except ValueError:
            years = None
    return {
        "amount": amount, "revenue": revenue, "ratio": ratio,
        "ratio_check": (abs(calc - ratio) / max(ratio, 1e-9) < 0.05) if calc and ratio else None,
        "voluntary": "자율공시" in t[:200],
        "sub": bool(re.search(r"(자회사|종속회사)\S*\s*\S*\s*의?\s*주요\s*경영", t[:400])),
        "cond": bool(re.search(r"조건부\s*계약\s*여부\s*해당", t)),
        # 2020년대 양식: '회사와 최근 3년간 동종계약 이행여부 해당/미해당' (양식에 없으면 None)
        "repeat": (bool(re.search(r"동종계약\s*이행\s*여부\s*해당", t))
                   if re.search(r"동종계약\s*이행\s*여부", t) else None),
        "related": bool(re.search(r"계열|종속|자회사|모회사|최대주주|특수관계|관계회사", rel_txt.split("-회사와")[0][:20])),
        "overseas": bool(re.search(FOREIGN, reg_txt)),
        "region": reg_txt[:30], "years": years, "rel": rel_txt[:20],
    }


# ---------------------------------------------------------------- 수집
def collect(markets, sleep=0.3):
    os.makedirs(DOCS, exist_ok=True)
    ev = events(markets).sort_values("rcept_dt", ascending=False)      # 최근 것부터(부분 수집으로도 쓸모)
    todo = [r for r in ev["rcept_no"] if not os.path.exists(os.path.join(DOCS, f"{r}.txt"))]
    print(f"contract documents to fetch: {len(todo)} (of {len(ev)}; markets {markets})", flush=True)
    t0, fails = time.time(), 0
    for i, rn in enumerate(todo):
        try:
            txt, err = fetch_text(rn)
        except Exception as e:
            txt, err = None, str(e)[:120]
        if txt is None:
            fails += 1
            if err and any(q in err for q in ('"020"', "020", "한도", '"011"', '"012"', '"901"')):
                print(f"  DART quota/key stop ({err[:80]}) - rerun tomorrow to resume", flush=True)
                sys.exit(3)
            if fails <= 20 or fails % 100 == 0:
                print(f"  fail {rn}: {str(err)[:100]}", flush=True)
            time.sleep(1.0)
            continue
        with open(os.path.join(DOCS, f"{rn}.txt"), "w", encoding="utf-8") as fh:
            fh.write(txt)
        if (i + 1) % 200 == 0 or i + 1 == len(todo):
            el = time.time() - t0
            print(f"  {i + 1}/{len(todo)} ({el / 60:.1f}m, ~{el / (i + 1) * (len(todo) - i - 1) / 60:.0f}m left, "
                  f"fails {fails})", flush=True)
        time.sleep(sleep)


def parsed(ev):
    rows = []
    for rn in ev["rcept_no"]:
        p = os.path.join(DOCS, f"{rn}.txt")
        if os.path.exists(p):
            rows.append({"rcept_no": rn, **parse(open(p, encoding="utf-8").read())})
    return pd.DataFrame(rows)


def parse_check(n=12):
    ev = events(["kospi_full", "kosdaq", "kospi"])
    P = parsed(ev)
    if P.empty:
        print("no documents yet"); return
    print(f"parsed {len(P)} | ratio found {P['ratio'].notna().mean():.0%} | ratio==amount/revenue(±5%) "
          f"{P['ratio_check'].dropna().mean():.0%} | voluntary {P['voluntary'].mean():.0%} sub {P['sub'].mean():.0%} "
          f"cond {P['cond'].mean():.0%} related {P['related'].mean():.0%} overseas {P['overseas'].mean():.0%}")
    for _, r in P.sample(min(n, len(P)), random_state=3).iterrows():
        print(f"  {r.rcept_no} ratio {r.ratio} amt {r.amount} rev {r.revenue} vol {r.voluntary} sub {r['sub']} "
              f"cond {r.cond} rel {r.related}({r.rel!r}) os {r.overseas}({r.region!r}) yrs {r.years}")
    bad = P[P["ratio"].isna()]
    for rn in bad["rcept_no"].head(3):
        print("  NO RATIO", rn, open(os.path.join(DOCS, f"{rn}.txt"), encoding="utf-8").read()[:400])


# ---------------------------------------------------------------- 분석
def _stats(g, rng):
    r = {"n": int(g["d20"].notna().sum())}
    for w in WIN:
        x = g[w].to_numpy()
        lo, hi, p = ER.boot_ci(x, g["month"].to_numpy(), rng)
        r.update({w: float(np.nanmean(x)), f"{w}_med": float(np.nanmedian(x)), f"{w}_lo": lo, f"{w}_hi": hi,
                  f"{w}_p": p})
    r["hit20"] = float(np.nanmean(g["d20"].to_numpy() > 0))
    r["top_firm"] = float(g["corp_code"].value_counts(normalize=True).iloc[0])
    return r


def analyze(markets):
    rng = np.random.default_rng(20261005)
    ev_all = events(markets)
    P = parsed(ev_all)
    if P.empty:
        raise SystemExit("원문 없음 - 먼저: python -X utf8 -m dintel.contracts collect " + " ".join(markets))
    # 공유 데이터 파일(실투자 엔진 alpha3/events.py가 코드 없이 이 파일만 읽는다)
    ev_all[["corp_code", "rcept_dt", "rcept_no", "ckind"]].merge(
        P[["rcept_no", "ratio", "voluntary", "sub", "cond", "related", "overseas", "years"]], on="rcept_no",
        how="inner").to_csv(PARSED_CSV, index=False, encoding="utf-8")
    ev_all = ev_all.merge(P, on="rcept_no", how="inner")
    ev_all["rdate"] = pd.to_datetime(ev_all["rcept_dt"], format="%Y%m%d")
    # 같은 기업·같은 날 여러 건 -> 매출액 대비가 가장 큰 1건(같은 날 공시는 한 번의 가격 반응을 공유)
    ev_all = ev_all.sort_values("ratio", ascending=False).drop_duplicates(["corp_code", "rcept_dt", "ckind"])
    out = [f"##### 공급계약 공시 규모별 반응 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 값 = 시장 동일가중 대비, "
           f"'위약차감' = 같은 종목 무작위 날짜 기준선 차감 | ★=BH 유의 | 최소표본 {MIN_N}"]
    stats = {"generated": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "bins": [b[2] for b in BINS], "markets": {}}
    per_market = []
    for m in markets:
        ev = ev_all[ev_all["market"] == m].copy()
        if ev.empty:
            continue
        ev, pl, _ = ER.reactions_for(ev, m, rng)
        per_market.append((m, ev, pl))
    if len(per_market) > 1:
        per_market.append(("+".join(m for m, _, _ in per_market), pd.concat([e for _, e, _ in per_market]),
                           pd.concat([p for _, _, p in per_market])))
    for tag, ev, pl in per_market:
        base = {w: float(np.nanmean(pl[w])) for w in WIN}
        sign = ev[ev["ckind"] == "체결"]
        groups = [("체결 전체", sign), ("해지 전체", ev[ev["ckind"] == "해지"])]
        groups += [(f"체결 {lab}", sign[(sign["ratio"] >= lo) & (sign["ratio"] < hi)]) for lo, hi, lab in BINS]
        for k, lab in (("voluntary", "자율공시"), ("sub", "자회사 계약"), ("cond", "조건부"), ("related", "특수관계 상대"),
                       ("overseas", "해외")):
            groups += [(f"체결 {lab} O", sign[sign[k]]), (f"체결 {lab} X", sign[~sign[k]])]
        rp = sign[sign["repeat"].notna()]
        groups += [("체결 기존 거래처", rp[rp["repeat"].astype(bool)]), ("체결 신규 거래처", rp[~rp["repeat"].astype(bool)])]
        groups += [("체결 기간 1년 이하", sign[sign["years"] <= 1]), ("체결 기간 1~3년", sign[(sign["years"] > 1) & (sign["years"] <= 3)]),
                   ("체결 기간 3년 초과", sign[sign["years"] > 3])]
        rows = []
        for name, g in groups:
            if g["d20"].notna().sum() < MIN_N:
                rows.append({"group": name, "n": int(g["d20"].notna().sum()), "skip": True})
                continue
            rows.append({"group": name, "skip": False, **_stats(g, rng)})
        T = pd.DataFrame(rows)
        ok = ~T["skip"]
        for w in WIN:
            T[f"{w}_sig"] = False
            T.loc[ok, f"{w}_sig"] = ER.bh(T.loc[ok, f"{w}_p"].to_numpy())
        cov = P[P["rcept_no"].isin(ev["rcept_no"])]
        out.append(f"[{tag}] 체결 {len(sign):,}건 · 해지 {int((ev['ckind'] == '해지').sum()):,}건 | {ev['corp_code'].nunique()}개사 | "
                   f"{ev['rdate'].min():%Y-%m}~{ev['rdate'].max():%Y-%m} | 비율 파싱 {cov['ratio'].notna().mean():.0%} | "
                   f"위약 d20 {base['d20']:+.2%}")
        out.append(f"[{tag}] 그룹 | n(최다기업) | 발표ann2 평균/중앙 | d20 평균/중앙 [95%CI] 상승 | d20 위약차감 | d60 | 사전pre20")
        f = lambda r, w: f"{r[w]:+.1%}{'★' if r[f'{w}_sig'] else ''}"
        for _, r in T.iterrows():
            if r["skip"]:
                out.append(f"  {r['group']:<16} | n={int(r['n'])} (표본 부족)")
                continue
            out.append(f"  {r['group']:<16} | {int(r['n']):>5}({r['top_firm']:.0%}) | {f(r, 'ann2'):>7}/{r['ann2_med']:+.1%} | "
                       f"{f(r, 'd20'):>7}/{r['d20_med']:+.1%} [{r['d20_lo']:+.1%},{r['d20_hi']:+.1%}] {r['hit20']:.0%} | "
                       f"{r['d20'] - base['d20']:+.1%} | {f(r, 'd60'):>7} | {f(r, 'pre20'):>7}")
        keep = [c for c in T.columns if not c.endswith("_p")]
        stats["markets"][tag] = {"placebo": base, "groups": [
            {k: (None if isinstance(v, float) and not np.isfinite(v) else (bool(v) if isinstance(v, (bool, np.bool_)) else v))
             for k, v in r.items()} for r in T[keep].to_dict("records")]}
    text = "\n".join(out)
    print(text, flush=True)
    with open(SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(STATS_JSON, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1, default=float)
    print(f"-> {SUMMARY}\n-> {STATS_JSON}", flush=True)


# ---------------------------------------------------------------- 리포트용(개별 공시 1건)
_STATS = {"mtime": None, "data": None}


def _load_stats():
    if not os.path.exists(STATS_JSON):
        return None
    mt = os.path.getmtime(STATS_JSON)
    if _STATS["mtime"] != mt:
        with open(STATS_JSON, encoding="utf-8") as fh:
            _STATS.update(mtime=mt, data=json.load(fh))
    return _STATS["data"]


def annotate_item(rcept_no, market, report_nm):
    """공급계약 공시 1건 -> 원문 파싱(캐시) + 같은 규모 구간·성격의 과거 통계. 실패하면 None."""
    ck = kind_of(report_nm)
    if ck is None:
        return None
    p = os.path.join(DOCS, f"{rcept_no}.txt")
    try:
        if not os.path.exists(p):
            txt, _ = fetch_text(rcept_no)
            if not txt:
                return None
            os.makedirs(DOCS, exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(txt)
        with open(p, encoding="utf-8") as fh:
            f = parse(fh.read())
    except Exception:
        return None
    f = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in f.items()}
    out = {"kind": ck, **{k: f[k] for k in ("ratio", "amount", "revenue", "voluntary", "sub", "cond", "related",
                                               "overseas", "repeat", "years", "region")},
           "bucket": bucket(f["ratio"]) if ck == "체결" else None}
    st = _load_stats()
    if st:
        mk = str(market).lower()
        mk = "kospi_full" if mk == "kospi" and "kospi_full" in st["markets"] else mk
        src = mk if mk in st["markets"] else next((k for k in st["markets"] if "+" in k), None)
        if src:
            g = {r["group"]: r for r in st["markets"][src]["groups"] if not r.get("skip")}
            name = f"체결 {out['bucket']}" if ck == "체결" else "해지 전체"
            out.update(src=src, bucket_stat=g.get(name), all_stat=g.get("체결 전체" if ck == "체결" else "해지 전체"),
                       placebo_d20=st["markets"][src]["placebo"]["d20"])
    return out


if __name__ == "__main__":
    cmd, ms = sys.argv[1], sys.argv[2:] or ["kospi_full", "kosdaq"]
    if cmd == "collect":
        collect(ms)
    elif cmd == "parse-check":
        parse_check()
    elif cmd == "analyze":
        analyze(ms)

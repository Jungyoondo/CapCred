"""밸류업 계획 '내용' 분석 - 어떤 계획이 시장에서 통했나.

python -X utf8 -m dintel.valueup_text collect kospi kosdaq    # DART document.xml 본문(이어받기)
python -X utf8 -m dintel.valueup_text parse-check            # 파싱 결과 표본 10건 출력(사람 검수용)
python -X utf8 -m dintel.valueup_text analyze kospi kosdaq

## 본문 (2026-10-03 실측)
DART document.xml이 거래소(KIND) 자율공시인 밸류업 공시도 요약본을 준다(1~4천자).
'계획서 명칭 / 주요 내용'에 핵심 지표 목표(ROE·주주환원율·PBR·배당성향)와 자사주 매입·소각, 배당정책이 들어있다.

## 추출(규칙 기반, 투명) - 숫자 목표는 '목표'라는 말이 가까이 있을 때만 목표로 인정
roe_t / ret_t(주주환원율) / payout_t(배당성향) / pbr_t : 목표 수치
cancel(자사주 소각 언급) / cancel_all(전량 소각) / buyback(자사주 매입·취득) / div_up(배당 확대·증가)
qdiv(분기·중간배당) / reduce_cap_div(감액배당) / n_targets(숫자 목표 개수) / text_len
## 분석
valueup_events_<m>.csv(valueup analyze 산출물: 대조군 차감 d20_mnet/d60_mnet 포함)에 붙여, 특징 유무별
대조군 차감 수익률 평균·중앙·95%CI(달력월 블록 부트스트랩)와 BH 보정. 본공시(첫+갱신)만 대상.
"""
import io
import json
import os
import re
import sys
import time
import zipfile

import numpy as np
import pandas as pd

from dintel import event_reaction as ER
from dintel import valueup as VU

OUT_DIR = ER.OUT_DIR
DOCS = os.path.join(OUT_DIR, "valueup_docs")
SUMMARY = os.path.join(OUT_DIR, "VALUEUP_TEXT_SUMMARY.txt")
STATS_JSON = os.path.join(OUT_DIR, "valueup_text_stats.json")
MIN_N = int(os.environ.get("DINTEL_MIN_N", "20"))

NUM = r"(\d{1,3}(?:\.\d+)?)"


def _decode(b):
    """DART 원문은 최근 UTF-8, 2010년대 후반까지는 EUC-KR(cp949)이 섞여 있다(2026-10-04 실측)."""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp949", "ignore")


def fetch_text(rcept_no):
    sys.path.insert(0, ER.ROOT)
    import dart_client as Dc
    import requests
    r = requests.get("https://opendart.fss.or.kr/api/document.xml",
                     params={"crtfc_key": Dc.get_api_key(), "rcept_no": rcept_no}, timeout=30)
    if r.content[:2] != b"PK":
        return None, r.text[:200]
    z = zipfile.ZipFile(io.BytesIO(r.content))
    raw = " ".join(_decode(z.read(n)) for n in z.namelist())
    raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.S)
    txt = re.sub(r"<[^>]+>", " ", raw)
    txt = re.sub(r"\.xforms[^{]*\{[^}]*\}", " ", txt)          # 남은 인라인 CSS 규칙 제거
    txt = re.sub(r"&gt;", ">", re.sub(r"&lt;", "<", re.sub(r"&amp;", "&", txt)))
    return re.sub(r"\s+", " ", txt).strip(), None


def all_events(markets):
    rows = []
    for m in markets:
        ev, pm = VU.load(m)
        if not ev.empty:
            rows.append(ev.assign(market=m))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def collect(markets, sleep=0.3):
    os.makedirs(DOCS, exist_ok=True)
    ev = all_events(markets)
    todo = [r for r in ev["rcept_no"].astype(str).unique() if not os.path.exists(os.path.join(DOCS, f"{r}.txt"))]
    print(f"value-up documents to fetch: {len(todo)} (of {ev['rcept_no'].nunique()})", flush=True)
    t0, fails = time.time(), 0
    for i, rn in enumerate(todo):
        try:
            txt, err = fetch_text(rn)
        except Exception as e:
            txt, err = None, str(e)[:120]
        if txt is None:
            fails += 1
            print(f"  fail {rn}: {err}", flush=True)
            if err and ("020" in err or "한도" in err):
                print("  quota reached - rerun tomorrow", flush=True)
                break
            time.sleep(1.0)
            continue
        with open(os.path.join(DOCS, f"{rn}.txt"), "w", encoding="utf-8") as fh:
            fh.write(txt)
        if (i + 1) % 100 == 0 or i + 1 == len(todo):
            el = time.time() - t0
            print(f"  {i + 1}/{len(todo)} ({el / 60:.1f}m, ~{el / (i + 1) * (len(todo) - i - 1) / 60:.0f}m left, "
                  f"fails {fails})", flush=True)
        time.sleep(sleep)


KEYS = {"ROE": r"(?:ROE|(?<!유형)자기자본이익률)", "RET": r"(?:총\s*주주환원율|주주환원율)", "PAYOUT": r"배당성향",
        "PBR": r"(?:PBR|주가순자산비율)"}
TGT = r"(?:목표|지향)"


def _target(text, key, unit="%"):
    """목표 수치만 추출(실적치 제외). 우선순위:
    1) 'KEY … 목표/지향 … N단위'  (이행현황의 'ROE 19.9% (목표 15% 이상)' -> 15)
    2) '목표/지향 … KEY N단위'  (나열형 '중기 목표 설정 - ROE 15%, 주주환원율 30%' -> 각각)
    3) 'KEY N단위 이상/수준/달성/까지'
    4) 'KEY N단위 … 목표/지향'   ('ROE 10.5%를 … 중기 재무 지향점으로')
    1)·4)는 중간에 다른 지표 키가 끼면 매칭하지 않는다(옆 지표 숫자 오인 방지).
    '유형자기자본이익률(ROTCE)'은 ROE로 보지 않는다."""
    k = KEYS[key]
    others = "|".join(v for kk, v in KEYS.items() if kk != key)
    gap = rf"(?:(?!{others}).)"
    u = re.escape(unit)
    pats = [rf"{k}{gap}{{0,40}}?{TGT}[^0-9]{{0,12}}{NUM}\s*{u}",
            rf"{TGT}.{{0,80}}?{k}[^0-9%]{{0,12}}{NUM}\s*{u}",          # 나열형: 숫자가 키 바로 뒤라 다른 키 허용
            rf"{k}[^0-9%배]{{0,15}}{NUM}\s*{u}\s*(?:이상|수준|달성|까지|내외|~)",
            rf"{k}[^0-9%배]{{0,15}}{NUM}\s*{u}{gap}{{0,60}}?{TGT}"]          # '… 10.5%를 중기 지향점으로'

    for p in pats:
        m = re.search(p, text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return np.nan


def parse(text):
    t = text
    f = {
        "roe_t": _target(t, "ROE"),
        "ret_t": _target(t, "RET"),
        "payout_t": _target(t, "PAYOUT"),
        "pbr_t": _target(t, "PBR", "배"),
        "attach_only": bool(re.search(r"첨부[^.]{0,20}참고|첨부된[^.]{0,30}참고", t)),
        "cancel": bool(re.search(r"소각", t)),
        "cancel_all": bool(re.search(r"전량\s*소각|전부\s*소각|100\s*%\s*소각", t)),
        "buyback": bool(re.search(r"자기주식|자사주", t) and re.search(r"매입|취득", t)),
        "div_up": bool(re.search(r"배당[^.]{0,15}(확대|증가|상향)|DPS[^.]{0,10}(확대|증가|상향)", t)),
        "qdiv": bool(re.search(r"분기\s*배당|중간\s*배당", t)),
        "reduce_cap_div": bool(re.search(r"감액\s*배당", t)),
        "text_len": len(t),
    }
    f["n_targets"] = int(sum(np.isfinite(f[k]) for k in ("roe_t", "ret_t", "payout_t", "pbr_t")))
    return f


def parsed_table(markets):
    ev = all_events(markets)
    rows = []
    for r in ev.itertuples():
        p = os.path.join(DOCS, f"{r.rcept_no}.txt")
        if os.path.exists(p):
            rows.append({"rcept_no": str(r.rcept_no), **parse(open(p, encoding="utf-8").read())})
    return pd.DataFrame(rows)


def parse_check(n=10):
    files = sorted(os.listdir(DOCS))[:n] if os.path.isdir(DOCS) else []
    for f in files:
        t = open(os.path.join(DOCS, f), encoding="utf-8").read()
        p = parse(t)
        print(f"== {f[:-4]} len={p['text_len']} targets: ROE {p['roe_t']} 환원율 {p['ret_t']} 배당성향 {p['payout_t']} "
              f"PBR {p['pbr_t']} | 소각 {p['cancel']}(전량 {p['cancel_all']}) 매입 {p['buyback']} 배당확대 {p['div_up']} "
              f"분기 {p['qdiv']} 감액 {p['reduce_cap_div']}")
        i = t.find("주요 내용")
        print("   ", t[i:i + 260] if i >= 0 else t[:260])


def analyze(markets):
    rng = np.random.default_rng(20261004)
    frames = []
    for m in markets:
        p = os.path.join(OUT_DIR, f"valueup_events_{m}.csv")
        if os.path.exists(p):
            frames.append(pd.read_csv(p, dtype={"rcept_no": str, "corp_code": str}).assign(market=m))
    if not frames:
        raise SystemExit("valueup_events_*.csv 없음 - 먼저: python -X utf8 -m dintel.valueup analyze kospi kosdaq")
    ev = pd.concat(frames, ignore_index=True)
    ev = ev[ev["etype"].isin(["첫 본공시", "갱신 본공시"])]
    ft = parsed_table(markets)
    ev = ev.merge(ft, on="rcept_no", how="inner")
    out = [f"##### 밸류업 계획 내용별 반응 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 본공시 {len(ev)}건(본문 확보) "
           f"| 값 = 동시점·동규모 비공시기업 대조 차감 수익률 | ★=BH 유의"]
    cov = {k: float(ev[k].notna().mean() if ev[k].dtype.kind == "f" else ev[k].mean())
           for k in ("roe_t", "ret_t", "payout_t", "pbr_t", "cancel", "cancel_all", "buyback", "div_up", "qdiv",
                     "reduce_cap_div")}
    out.append("  보유율: " + ", ".join(f"{k} {v:.0%}" for k, v in cov.items()))
    groups = []
    for k, lab in (("cancel", "자사주 소각 언급"), ("cancel_all", "전량 소각 약속"), ("buyback", "자사주 매입 언급"),
                   ("div_up", "배당 확대 언급"), ("qdiv", "분기·중간배당"), ("reduce_cap_div", "감액배당")):
        groups += [(f"{lab} O", ev[ev[k]]), (f"{lab} X", ev[~ev[k]])]
    for k, lab in (("roe_t", "ROE 목표"), ("ret_t", "주주환원율 목표"), ("payout_t", "배당성향 목표"), ("pbr_t", "PBR 목표")):
        groups += [(f"{lab} 수치 O", ev[ev[k].notna()]), (f"{lab} 수치 X", ev[ev[k].isna()])]
    for n_lo, n_hi, lab in ((0, 0, "숫자목표 0개"), (1, 1, "숫자목표 1개"), (2, 9, "숫자목표 2개+")):
        groups.append((lab, ev[(ev["n_targets"] >= n_lo) & (ev["n_targets"] <= n_hi)]))
    rows = []
    for name, g in groups:
        r = {"group": name, "n": int(g["d60_mnet"].notna().sum())}
        if r["n"] < MIN_N:
            r["skip"] = True
            rows.append(r)
            continue
        r["skip"] = False
        for w in ("ann2", "d20_mnet", "d60_mnet"):
            x = g[w].to_numpy()
            lo, hi, p = ER.boot_ci(x, g["month"].to_numpy(), rng)
            r.update({w: float(np.nanmean(x)), f"{w}_med": float(np.nanmedian(x)), f"{w}_lo": lo, f"{w}_hi": hi,
                      f"{w}_p": p})
        rows.append(r)
    T = pd.DataFrame(rows)
    ok = ~T["skip"]
    for w in ("ann2", "d20_mnet", "d60_mnet"):
        T.loc[ok, f"{w}_sig"] = ER.bh(T.loc[ok, f"{w}_p"].to_numpy())
    s = lambda r, w: f"{r[w]:+.1%}{'★' if r.get(f'{w}_sig') else ''}"
    out.append("  그룹 | n | 발표ann2 | 20일(대조차감) 평균/중앙 [95%CI] | 60일(대조차감) 평균/중앙 [95%CI]")
    for _, r in T.iterrows():
        if r["skip"]:
            out.append(f"  {r['group']:<18} | n={r['n']} (표본 {MIN_N} 미만)")
            continue
        out.append(f"  {r['group']:<18} | {r['n']:>3} | {s(r, 'ann2'):>7} | {s(r, 'd20_mnet'):>7}/{r['d20_mnet_med']:+.1%} "
                   f"[{r['d20_mnet_lo']:+.1%},{r['d20_mnet_hi']:+.1%}] | {s(r, 'd60_mnet'):>7}/{r['d60_mnet_med']:+.1%} "
                   f"[{r['d60_mnet_lo']:+.1%},{r['d60_mnet_hi']:+.1%}]")
    text = "\n".join(out)
    print(text, flush=True)
    with open(SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    keep = [c for c in T.columns if not c.endswith("_p")]
    with open(STATS_JSON, "w", encoding="utf-8") as fh:
        json.dump({"generated": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "coverage": cov,
                   "groups": json.loads(T[keep].to_json(orient="records"))}, fh, ensure_ascii=False, indent=1)
    print(f"-> {SUMMARY}", flush=True)
    print(f"-> {STATS_JSON}", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "analyze"
    mk = sys.argv[2:] or ["kospi", "kosdaq"]
    if cmd == "collect":
        collect(mk)
    elif cmd == "parse-check":
        parse_check()
    else:
        analyze(mk)

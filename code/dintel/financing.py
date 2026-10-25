"""자금조달 공시 원문 파싱 - 유상증자·CB·BW의 '조건'이 시장 반응을 가르는가 (2026-10-06).

python -X utf8 -m dintel.financing collect kosdaq kospi_full     # 원문 수집(이어받기, DART 한도 시 exit 3)
python -X utf8 -m dintel.financing parse-check                   # 파싱 표본·추출률(사람 검수용)
python -X utf8 -m dintel.financing analyze kosdaq kospi_full     # -> FINANCING_SUMMARY.txt, financing_stats.json, financing_parsed.csv

## 왜
desk_eval.py 실측: 공시 '유형'만으로 거르면 20일 급락의 9~13%만 잡힌다. 같은 '전환사채 발행'이라도
조건(누구에게, 얼마나 싸게, 리픽싱 하한, 콜옵션, 돈을 어디에 쓰는지)이 다르다. 그 조건은 원문에만 있다.
DART 상세 API(details.py)는 금액·방식·희석률·자금목적은 주지만 할인율·배정대상자·콜/풋옵션은 없다.

## 원문 양식 (2026-10-06 실측, 주요사항보고서 document.xml)
유상증자: '5. 증자방식' '6. 신주 발행가액' '7. 기준주가' '7-2. 기준주가에 대한 할인율 또는 할증율 (%)'
          '16. 증권신고서 제출대상 여부' / 【제3자배정 대상자별 선정경위, 거래내역, 배정내역 등】 표
CB/BW:    '8. 사채발행방법' '4. 사채의 이율 표면이자율 (%) 만기이자율 (%)' '전환가액 (원/주)'(BW는 행사가액)
          '주식총수 대비비율(%)' '최저 조정가액 (원)' / [매도청구권(Call Option)] [조기상환청구권(Put Option)]
          / 【특정인에 대한 대상자별 사채발행내역】 표
## 변수 (원문에 없으면 None)
공통: amount(조달금액), dil(희석: 신주/기존 또는 주식총수 대비), private(사모), purpose_* (자금 목적별 비중)
유상증자: method, price, base_price, discount(%; 음수=할인), lockup, alloc_* (배정대상 성격)
CB/BW: coupon, ytm, conv_price, floor_ratio(최저조정가/전환가), call, call_pct, put, alloc_*
배정대상 성격(표 본문 키워드): alloc_major(최대주주·특수관계·계열·임원), alloc_fund(투자조합·조합),
                              alloc_fin(증권·자산운용·캐피탈·은행·신탁·펀드), alloc_person(개인으로 보이는 이름만)
## 분석
event_reactions_<market>.csv(시장 동일가중 대비 초과수익)와 rcept_no로 결합 -> 조건별 그룹 통계,
달력월 블록 부트스트랩 CI(event_reaction.boot_ci), 학습(~2021-11)/검증(2022-)에서 부호 유지 여부.
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
DOCS = os.path.join(OUT_DIR, "financing_docs")
SUMMARY = os.path.join(OUT_DIR, "FINANCING_SUMMARY.txt")
STATS_JSON = os.path.join(OUT_DIR, "financing_stats.json")
PARSED_CSV = os.path.join(OUT_DIR, "financing_parsed.csv")
KINDS = {"유상증자결정": "RI", "전환사채권발행결정": "CB", "신주인수권부사채권발행결정": "BW"}
MIN_N = int(os.environ.get("DINTEL_MIN_N", "30"))
TRAIN_END, TEST_START = pd.Timestamp("2021-11-30"), pd.Timestamp("2022-01-01")
_N = r"(-?[\d,]+(?:\.\d+)?)"


def kind_of(report_nm):
    n = str(report_nm).replace(" ", "")
    if n.startswith("["):
        return None
    for k, v in KINDS.items():
        if k in n:
            return v
    return None


def events(markets):
    rows = []
    for m in markets:
        p = os.path.join(OUT_DIR, f"events_{m}.csv")
        if os.path.exists(p):
            d = pd.read_csv(p, dtype=str)
            rows.append(d.assign(market=m))
    ev = pd.concat(rows, ignore_index=True)
    ev["fkind"] = ev["report_nm"].map(kind_of)
    return ev.dropna(subset=["fkind"]).drop_duplicates("rcept_no").reset_index(drop=True)


# ---------------------------------------------------------------- 파싱
def _num(s):
    try:
        return float(str(s).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _grab(pat, t):
    m = re.search(pat, t)
    return _num(m.group(1)) if m else None


FIN_WORDS = r"증권|자산운용|운용|캐피탈|은행|신탁|펀드|투자신탁|보험|투자금융|저축은행|인베스트먼트|파트너스|에쿼티|PE|사모투자"
CORP_WORDS = r"주식회사|\(주\)|㈜|유한회사|유한책임회사|Co\.|Ltd|Inc|LLC|Limited|Corp"
MAJOR_WORDS = r"최대주주|특수관계|계열|임원|대표이사|등기|모회사|자회사|종속|관계회사"


def _alloc(seg):
    """배정대상 표 본문(헤더 제외)에서 대상자 성격을 키워드로 판별."""
    if not seg:
        return {"alloc_major": None, "alloc_fund": None, "alloc_fin": None, "alloc_corp": None, "alloc_person": None,
                "alloc_n": None}
    # 헤더('회사 또는 최대주주와의 관계' 등)를 지운 뒤 판별 - 헤더의 '최대주주' 단어 오탐 방지
    body = re.sub(r"회사\s*또는\s*최대주주와의\s*관계", " ", seg)
    body = re.sub(r"선정\s*경위|거래\s*내역|배정\s*주식수|발행\s*권면\S*|비\s*고|발행\s*대상자명|제3자배정\s*대상자", " ", body)
    names = re.findall(r"(?:\(주\)|㈜|주식회사)?\s*[가-힣A-Za-z0-9&·\.\s]{2,40}?(?:조합|주식회사|\(주\)|㈜|증권|운용|캐피탈|은행|신탁|펀드)", body)
    n_rows = len(re.findall(r"이사회에서\s*결정|선정|고려하여", body)) or None
    fund = bool(re.search(r"투자조합|조합(?!원)|신기술사업투자조합|창업투자조합", body))
    fin = bool(re.search(FIN_WORDS, body))
    corp = bool(re.search(CORP_WORDS, body))
    return {"alloc_major": bool(re.search(MAJOR_WORDS, body)), "alloc_fund": fund, "alloc_fin": fin,
            "alloc_corp": corp and not (fund or fin), "alloc_person": not (fund or fin or corp), "alloc_n": n_rows if n_rows else (len(names) or None)}


def _segment(t, start_pat, end_pat=r"【"):
    m = re.search(start_pat, t)
    if not m:
        return ""
    rest = t[m.end():]
    e = re.search(end_pat, rest)
    return rest[: e.start() if e else 1500][:3000]


def _purpose(t):
    keys = {"fclt": "시설자금", "bsninh": "영업양수자금", "op": "운영자금", "dtrp": "채무상환자금",
            "ocsa": r"타법인\s*증권\s*취득자금", "etc": "기타자금"}
    v = {k: _grab(p + r"\s*\(원\)\s*" + _N, t) for k, p in keys.items()}
    tot = sum(x for x in v.values() if x)
    return {f"purpose_{k}": (x / tot if (x and tot) else 0.0) for k, x in v.items()} if tot else \
        {f"purpose_{k}": None for k in keys}


def parse(text, fkind):
    t = re.sub(r"\s+", " ", text)
    out = {"fkind": fkind}
    out.update(_purpose(t))
    if fkind == "RI":
        new = _grab(r"1\.\s*신주의\s*종류와\s*수\s*보통주식\s*\(주\)\s*" + _N, t)
        pre = _grab(r"증자전\s*발행주식총수\s*\(주\)\s*보통주식\s*\(주\)\s*" + _N, t)
        mth = re.search(r"5\.\s*증자방식\s*(\S+)", t)
        price = _grab(r"신주\s*발행가액\s*(?:\(원\))?\s*보통주식\s*\(원\)\s*" + _N, t) or \
            _grab(r"신주\s*발행가액\s*보통주식\s*\(원\)\s*" + _N, t)
        base = _grab(r"7\.\s*기준주가\s*보통주식\s*\(원\)\s*" + _N, t)
        # 원문 할인율은 부호 표기가 회사마다 다름(-10 / 10) -> 발행가·기준주가가 있으면 직접 계산
        disc = (price / base - 1) * 100 if (price and base) else _grab(r"할인율\s*또는\s*할증율\s*\(%\)\s*" + _N, t)
        out.update({
            "amount": (new * price) if (new and price) else None,
            "dil": (new / pre) if (new and pre) else None,
            "method": mth.group(1) if mth else None,
            "price": price, "base_price": base, "discount": disc,
            "private": bool(re.search(r"증권신고서\s*제출대상\s*여부\s*아니오", t)),
            "lockup": "보호예수" in t or "의무보유" in t,
            "major_change": bool(re.search(r"최대주주\s*(?:가|의)?\s*변경", t)),
        })
        out.update(_alloc(_segment(t, r"【제3자배정\s*대상자별")))
    else:
        conv = _grab(r"(?:전환가액|행사가액)\s*\(원/주\)\s*" + _N, t)
        floor = _grab(r"최저\s*조정가액\s*\(원\)\s*" + _N, t)
        callm = re.search(r"매도\s*청구권|Call\s*Option|콜옵션", t, flags=re.I)
        cpct = re.search(r"(?:권면|인수)\S*\s*(?:금액|총액)?\S*\s*의\s*(\d{1,3})\s*%\s*(?:를|을)?\s*초과", t)
        out.update({
            "amount": _grab(r"사채의\s*권면\S*\s*총액\s*\(원\)\s*" + _N, t),
            "dil": (lambda x: x / 100 if x is not None else None)(_grab(r"주식총수\s*대비\s*비율\s*\(%\)\s*" + _N, t)),
            "private": bool(re.search(r"사채발행방법\s*사모", t)),
            "coupon": _grab(r"표면이자율\s*\(%\)\s*" + _N, t),
            "ytm": _grab(r"만기이자율\s*\(%\)\s*" + _N, t),
            "conv_price": conv,
            "floor_ratio": (floor / conv) if (floor and conv) else None,
            # 시가하락 리픽싱: 최저조정가액이 숫자면 있음, '-'면 없음(전환가 고정), 항목이 없으면 None
            "refix": True if floor else (False if re.search(r"최저\s*조정가액\s*\(원\)\s*-", t) else None),
            "call": bool(callm), "call_pct": _num(cpct.group(1)) if (callm and cpct) else None,
            "put": bool(re.search(r"조기상환\s*청구권|Put\s*Option|풋옵션", t, flags=re.I)),
        })
        out.update(_alloc(_segment(t, r"【특정인에\s*대한\s*대상자별")))
    return out


# ---------------------------------------------------------------- 수집
def collect(markets, sleep=0.3):
    os.makedirs(DOCS, exist_ok=True)
    ev = events(markets).sort_values("rcept_dt", ascending=False)
    todo = [r for r in ev["rcept_no"] if not os.path.exists(os.path.join(DOCS, f"{r}.txt"))]
    print(f"financing documents to fetch: {len(todo)} (of {len(ev)}; markets {markets})", flush=True)
    t0, fails = time.time(), 0
    for i, rn in enumerate(todo):
        try:
            txt, err = fetch_text(rn)
        except Exception as e:
            txt, err = None, str(e)[:120]
        if txt is None:
            fails += 1
            if err and any(q in err for q in ('"020"', "020", "한도", '"011"', '"012"', '"901"', "<status>800", "시스템 점검")):
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
    for rn, fk in zip(ev["rcept_no"], ev["fkind"]):
        p = os.path.join(DOCS, f"{rn}.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                rows.append({"rcept_no": rn, **parse(fh.read(), fk)})
    return pd.DataFrame(rows)


def parse_check(n=8):
    ev = events(["kosdaq", "kospi_full"])
    P = parsed(ev)
    if P.empty:
        print("no documents yet")
        return
    for fk, g in P.groupby("fkind"):
        cols = [c for c in g.columns if c not in ("rcept_no", "fkind")]
        rate = {c: g[c].notna().mean() for c in cols if not c.startswith("purpose_")}
        print(f"{fk}: n {len(g)} | extracted: " + ", ".join(f"{c} {v:.0%}" for c, v in rate.items()))
        flags = [c for c in ("private", "lockup", "call", "put", "refix", "alloc_major", "alloc_fund", "alloc_fin",
                             "alloc_corp", "alloc_person",
                             "major_change") if c in g]
        print("   share True: " + ", ".join(f"{c} {g[c].dropna().astype(bool).mean():.0%}" for c in flags))
        num = [c for c in ("discount", "dil", "coupon", "ytm", "floor_ratio", "call_pct") if c in g]
        print("   median: " + ", ".join(f"{c} {g[c].median():.3g}" for c in num if g[c].notna().any()))
        for _, r in g.sample(min(n, len(g)), random_state=1).iterrows():
            print("   ", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()
                         if not str(k).startswith("purpose_") and v is not None})


# ---------------------------------------------------------------- 분석
def _stats(g, rng):
    r = {"n": int(g["d20"].notna().sum())}
    for w in ("ann2", "d20", "d60"):
        x = g[w].to_numpy(dtype=float)
        lo, hi, p = ER.boot_ci(x, g["month"].to_numpy(), rng)
        r.update({w: float(np.nanmean(x)), f"{w}_med": float(np.nanmedian(x)), f"{w}_lo": lo, f"{w}_hi": hi,
                  f"{w}_p": p})
    r["crash20"] = float(np.nanmean(g["d20"].to_numpy(dtype=float) <= -0.15))
    tr, te = g[g["rdate"] <= TRAIN_END], g[g["rdate"] >= TEST_START]
    r["d20_tr"] = float(tr["d20"].mean()) if len(tr) >= 10 else None
    r["d20_te"] = float(te["d20"].mean()) if len(te) >= 10 else None
    r["n_tr"], r["n_te"] = int(len(tr)), int(len(te))
    return r


def groups(P):
    """조건 그룹(이름 -> 불리언 마스크). 사전에 정한 해석 가능한 구간만."""
    G = {}
    ri, cb = P["fkind"] == "RI", P["fkind"].isin(["CB", "BW"])
    m = P.get("method", pd.Series(index=P.index, dtype=object)).fillna("")
    G["RI 전체"] = ri
    G["RI 주주배정·공모"] = ri & m.str.contains("주주|공모")
    G["RI 제3자배정"] = ri & m.str.contains("제3자")
    G["RI 3자·최대주주등 배정"] = ri & m.str.contains("제3자") & (P["alloc_major"] == True)  # noqa: E712
    G["RI 3자·투자조합 배정"] = ri & m.str.contains("제3자") & (P["alloc_fund"] == True)  # noqa: E712
    G["RI 3자·금융기관 배정"] = ri & m.str.contains("제3자") & (P["alloc_fin"] == True)  # noqa: E712
    G["RI 3자·일반법인 배정"] = ri & m.str.contains("제3자") & (P["alloc_corp"] == True)  # noqa: E712
    G["RI 3자·개인만"] = ri & m.str.contains("제3자") & (P["alloc_person"] == True)  # noqa: E712
    G["RI 최대주주 변경 동반"] = ri & (P.get("major_change") == True)  # noqa: E712
    d = P["discount"]
    G["RI 할증·무할인(>=0%)"] = ri & (d >= 0)
    G["RI 할인 0~10%"] = ri & (d < 0) & (d >= -10)
    G["RI 할인 10%+"] = ri & (d < -10)
    for nm, x in (("RI", ri), ("CB/BW", cb)):
        G[f"{nm} 희석 <5%"] = x & (P["dil"] < 0.05)
        G[f"{nm} 희석 5~15%"] = x & (P["dil"] >= 0.05) & (P["dil"] < 0.15)
        G[f"{nm} 희석 15%+"] = x & (P["dil"] >= 0.15)
        G[f"{nm} 채무상환 50%+"] = x & (P["purpose_dtrp"] >= 0.5)
        G[f"{nm} 타법인취득 50%+"] = x & (P["purpose_ocsa"] >= 0.5)
        G[f"{nm} 시설 50%+"] = x & (P["purpose_fclt"] >= 0.5)
    G["CB/BW 전체"] = cb
    G["CB/BW 공모"] = cb & (P["private"] == False)  # noqa: E712
    G["CB/BW 표면0%·만기<=2%"] = cb & (P["coupon"] <= 0) & (P["ytm"] <= 2)
    G["CB/BW 리픽싱 있음(하한 70%)"] = cb & (P["refix"] == True) & (P["floor_ratio"].round(2) <= 0.70)  # noqa: E712
    G["CB/BW 리픽싱 없음(전환가 고정)"] = cb & (P["refix"] == False)  # noqa: E712
    G["CB/BW 콜옵션"] = cb & (P["call"] == True)  # noqa: E712
    G["CB/BW 콜옵션 없음"] = cb & (P["call"] == False)  # noqa: E712
    G["CB/BW 투자조합 대상"] = cb & (P["alloc_fund"] == True)  # noqa: E712
    G["CB/BW 금융기관만"] = cb & (P["alloc_fin"] == True) & (P["alloc_fund"] != True)  # noqa: E712
    G["CB/BW 최대주주등 대상"] = cb & (P["alloc_major"] == True)  # noqa: E712
    G["CB/BW 투자조합+리픽싱70%+채무상환"] = cb & (P["alloc_fund"] == True) & (P["floor_ratio"].round(2) <= 0.70) \
        & (P["purpose_dtrp"] >= 0.3)  # noqa: E712
    return G


def analyze(markets):
    rng = np.random.default_rng(20261006)
    ev = events(markets)
    P = parsed(ev)
    P = P.merge(ev[["rcept_no", "corp_code", "rcept_dt", "market"]], on="rcept_no", how="left")
    P.to_csv(PARSED_CSV, index=False, encoding="utf-8")
    lines = [f"##### 자금조달 공시 원문 조건별 반응 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 원문 {len(P):,}건 "
             f"(대상 {len(ev):,}) | 시장 동일가중 대비 초과수익, 다음 거래일부터 | 학습 ~2021-11 / 검증 2022-"]
    out = {"generated": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "markets": {}}
    for m in markets:
        rp = os.path.join(OUT_DIR, f"event_reactions_{m}.csv")
        if not os.path.exists(rp):
            continue
        R = pd.read_csv(rp, dtype={"rcept_no": str, "corp_code": str})
        R["rdate"] = pd.to_datetime(R["rdate"])
        X = P[P["market"] == m].merge(R[["rcept_no", "rdate", "month", "ann2", "d20", "d60"]], on="rcept_no",
                                      how="inner").dropna(subset=["d20"]).reset_index(drop=True)
        lines.append(f"\n## {m}: 반응과 결합 {len(X):,}건")
        lines.append("  그룹 | n | 발표(2일) | 20일 평균 [95%CI] | 20일 중앙값 | 60일 | 20일 -15% 이하 비율 | 학습→검증 20일")
        res = []
        for name, mask in groups(X).items():
            g = X[mask.fillna(False).to_numpy()]
            if len(g) < MIN_N:
                continue
            s = _stats(g, rng)
            s["group"] = name
            res.append(s)
            keep = ""
            if s["d20_tr"] is not None and s["d20_te"] is not None:
                keep = f"{s['d20_tr']:+.1%}→{s['d20_te']:+.1%}" + (" 유지" if np.sign(s["d20_tr"]) == np.sign(s["d20_te"]) else " 바뀜")
            star = "★" if (s["d20_lo"] > 0 or s["d20_hi"] < 0) else " "
            lines.append(f"  {name:28s} | {s['n']:5d} | {s['ann2']:+.1%} | {s['d20']:+.1%}{star} "
                         f"[{s['d20_lo']:+.1%},{s['d20_hi']:+.1%}] | {s['d20_med']:+.1%} | {s['d60']:+.1%} | "
                         f"{s['crash20']:.0%} | {keep}")
        out["markets"][m] = res
    txt = "\n".join(lines)
    print(txt)
    with open(SUMMARY, "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    with open(STATS_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "parse-check"
    mk = sys.argv[2:] or ["kosdaq", "kospi_full"]
    if cmd == "collect":
        collect(mk)
    elif cmd == "parse-check":
        parse_check()
    elif cmd == "analyze":
        analyze(mk)

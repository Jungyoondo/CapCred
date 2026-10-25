"""주요사항보고서 상세(금액·비율·방식) - 수집과 규모 지표 계산.

python -X utf8 -m dintel.details collect kosdaq [--limit N]     # DART 상세 API, (유형,기업) 단위 이어받기
python -X utf8 -m dintel.details collect kospi

- 대상: events_<market>.csv(또는 코스피 기존 수집본)에 그 유형 공시가 실제로 있는 기업만 호출.
- 캐시: data/dintel/details_raw/<endpoint>/<corp_code>.json  (빈 결과도 저장해 재호출 안 함)
- 엔드포인트·필드명은 2026-10-03 실제 응답으로 확인한 것만 사용(추측 없음).
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT_DIR = os.path.join(ROOT, "data", "dintel")
RAW = os.path.join(OUT_DIR, "details_raw")
LEGACY_KOSPI_EVENTS = os.path.join(ROOT, "data", "quant", "reports", "dart_disclosure_events.csv")

# 유형 -> (엔드포인트, 규모지표 계산, 규모 정의 설명, 범주 필드)
def _num(x):
    try:
        v = float(str(x).replace(",", "").strip())
        return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _pct(field):
    return lambda r, mcap: _num(r.get(field)) / 100.0


def _ratio(num, den):
    return lambda r, mcap: _num(r.get(num)) / _num(r.get(den)) if _num(r.get(den)) else np.nan


def _amt_mcap(field):
    return lambda r, mcap: _num(r.get(field)) / mcap if mcap and mcap > 0 else np.nan


SPECS = {
    "유상증자결정": ("piicDecsn", _ratio("nstk_ostk_cnt", "bfic_tisstk_ostk"), "신주/기존주식(희석률)", "ic_mthn"),
    "전환사채권발행결정": ("cvbdIsDecsn", _pct("cvisstk_tisstk_vs"), "전환주식/총주식", "bdis_mthn"),
    "신주인수권부사채권발행결정": ("bdwtIsDecsn", _pct("nstk_isstk_tisstk_vs"), "신주/총주식", "bdis_mthn"),
    "교환사채권발행결정": ("exbdIsDecsn", _amt_mcap("bd_fta"), "발행액/시가총액", "bdis_mthn"),
    "자기주식취득결정": ("tsstkAqDecsn", _amt_mcap("aqpln_prc_ostk"), "취득예정금액/시가총액", None),
    "자기주식처분결정": ("tsstkDpDecsn", _amt_mcap("dppln_prc_ostk"), "처분예정금액/시가총액", None),
    "자기주식취득신탁계약체결결정": ("tsstkAqTrctrCnsDecsn", _amt_mcap("ctr_prc"), "계약금액/시가총액", None),
    "무상증자결정": ("fricDecsn", lambda r, m: _num(r.get("nstk_ascnt_ps_ostk")), "1주당 배정주식수", None),
    "감자결정": ("crDecsn", _pct("cr_rt_ostk"), "감자비율", None),
    "타법인주식및출자증권양수결정": ("otcprStkInvscrInhDecsn", _pct("inhdtl_tast_vs"), "양수금액/총자산", None),
    "타법인주식및출자증권양도결정": ("otcprStkInvscrTrfDecsn", _pct("trfdtl_tast_vs"), "양도금액/총자산", None),
    "유형자산양수결정": ("tgastInhDecsn", _pct("inhdtl_tast_vs"), "양수금액/총자산", None),
    "유형자산양도결정": ("tgastTrfDecsn", _pct("trfdtl_tast_vs"), "양도금액/총자산", None),
}


def norm_method(s):
    """증자방식/발행방식 문자열을 몇 개 범주로."""
    s = str(s or "")
    if "제3자" in s:
        return "제3자배정"
    if "주주배정" in s or "주주우선" in s:
        return "주주배정"
    if "일반공모" in s:
        return "일반공모"
    if "사모" in s:
        return "사모"
    if "공모" in s:
        return "공모"
    return "기타" if s and s != "-" else None


def events_path(market):
    p = os.path.join(OUT_DIR, f"events_{market}.csv")
    if not os.path.exists(p) and market == "kospi" and os.path.exists(LEGACY_KOSPI_EVENTS):
        return LEGACY_KOSPI_EVENTS
    return p


def collect(market, limit=None, sleep=0.25):
    import dart_client as Dc
    ev = pd.read_csv(events_path(market), dtype=str)
    ev = ev[~ev["report_nm"].str.startswith("[", na=True)]
    ev["etype"] = ev["report_nm"].str.extract(r"\((.*)\)\s*$")[0].str.replace(" ", "", regex=False)
    jobs = []
    for et, (ep, *_rest) in SPECS.items():
        for cc in sorted(ev.loc[ev["etype"] == et, "corp_code"].str.zfill(8).unique()):
            if not os.path.exists(os.path.join(RAW, ep, f"{cc}.json")):
                jobs.append((ep, cc))
    jobs = jobs[:limit] if limit else jobs
    print(f"[{market}] detail calls to make: {len(jobs)} (cached ones skipped)", flush=True)
    t0, fails = time.time(), 0
    for i, (ep, cc) in enumerate(jobs):
        try:
            r = Dc._get(f"{ep}.json", {"corp_code": cc, "bgn_de": "20150101",
                                        "end_de": pd.Timestamp.today().strftime("%Y%m%d")}).json()
        except Exception as e:
            fails += 1
            print(f"  fail {ep} {cc}: {str(e)[:100]}", flush=True)
            time.sleep(2.0)
            continue
        if r.get("status") not in ("000", "013"):          # 013 = 데이터 없음(정상)
            fails += 1
            print(f"  status {r.get('status')} {r.get('message')} ({ep} {cc}) - stop if this is a quota error",
                  flush=True)
            if r.get("status") in ("020", "011", "012", "901"):   # 한도초과/키 문제 - 더 호출하지 않음
                break
            continue
        os.makedirs(os.path.join(RAW, ep), exist_ok=True)
        with open(os.path.join(RAW, ep, f"{cc}.json"), "w", encoding="utf-8") as fh:
            json.dump(r.get("list", []), fh, ensure_ascii=False)
        if (i + 1) % 100 == 0 or i + 1 == len(jobs):
            el = time.time() - t0
            print(f"  {i + 1}/{len(jobs)} ({el / 60:.1f}m, ~{el / (i + 1) * (len(jobs) - i - 1) / 60:.0f}m left, "
                  f"fails {fails})", flush=True)
        time.sleep(sleep)
    if fails:
        print(f"[{market}] {fails} failures - rerun the same command to retry.", flush=True)


def load_details():
    """캐시 전체 -> rcept_no 단위 DataFrame(etype, size, size_def, method)."""
    rows = []
    for et, (ep, fn, sdef, mfield) in SPECS.items():
        d = os.path.join(RAW, ep)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                for r in json.load(fh):
                    rows.append({"rcept_no": str(r.get("rcept_no")), "etype": et, "raw": r,
                                 "corp_code": str(r.get("corp_code", f[:-5])).zfill(8),
                                 "rcept_dt": str(r.get("rcept_no"))[:8],
                                 "method": norm_method(r.get(mfield)) if mfield else None})
    return pd.DataFrame(rows)


def attach_size(det, mcap_lookup):
    """mcap_lookup(rcept_no) -> 공시 직전 시가총액. 규모지표 계산."""
    sizes = []
    for r in det.itertuples():
        fn = SPECS[r.etype][1]
        sizes.append(fn(r.raw, mcap_lookup(r.rcept_no)))
    det = det.assign(size=sizes, size_def=[SPECS[e][2] for e in det["etype"]])
    return det.drop(columns=["raw"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["collect"])
    ap.add_argument("market", choices=["kospi", "kosdaq", "kospi_full"])
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    collect(a.market, a.limit)


def match_details(ev, det, tolerance_days=90):
    """원공시(ev: corp_code, etype, rdate) <-> 상세(det: corp_code, etype, rcept_dt).

    DART 상세 API는 정정이 있으면 '최종 정정본'의 접수번호를 돌려준다(2026-10-03 실측: 9/15 원공시가
    상세에선 9/29 정정본 번호로 조회됨). 그래서 접수번호 정확일치 대신, 같은 기업·같은 유형에서
    원공시일 이후 tolerance_days 이내의 가장 가까운 상세 기록을 붙인다(정정본은 항상 원공시 이후)."""
    left = ev[["corp_code", "etype", "rdate"]].reset_index()
    left = left.dropna(subset=["rdate"]).sort_values("rdate")
    right = det.copy()
    right["ddate"] = pd.to_datetime(right["rcept_dt"], format="%Y%m%d", errors="coerce")
    right = right.dropna(subset=["ddate"]).sort_values("ddate")
    m = pd.merge_asof(left, right.drop(columns=["corp_code", "etype"]).assign(
        corp_code=right["corp_code"], etype=right["etype"]),
        left_on="rdate", right_on="ddate", by=["corp_code", "etype"], direction="forward",
        tolerance=pd.Timedelta(days=tolerance_days))
    return m.set_index("index")

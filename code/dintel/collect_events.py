"""DART 주요사항보고(pblntf_ty=B) 이력 수집 - 시장별, 종목 단위 이어받기.

python -X utf8 -m dintel.collect_events kosdaq [--limit 20]
python -X utf8 -m dintel.collect_events kospi
python -X utf8 -m dintel.collect_events kosdaq --kind I   # 거래소공시(공급계약·배당·거래정지 등)

- 대상 기업: 해당 시장 PIT 패널(corp_code)의 전 종목.
- 종목별 캐시: data/dintel/events_raw/<market>/<corp_code>.csv (이미 있으면 건너뜀 -> Ctrl+C 후
  같은 명령으로 재실행하면 이어서 받는다). 공시 0건인 기업도 빈 파일을 남겨 재호출하지 않는다.
- 결과 병합: data/dintel/events_<market>.csv (corp_code, rcept_dt, rcept_no, report_nm)
- --kind I: 거래소공시(pblntf_ty=I). 캐시 events_raw_I/<market>/, 병합 events_I_<market>.csv.
  DART 일일 한도(사용량 초과 020 등)를 받으면 즉시 멈춘다 -> 다음 날 같은 명령으로 이어받기.
- DART API 키: .env의 DART_API_KEY(dart_client.py와 동일).
"""
import argparse
import os
import sys
import time

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import dart_client as Dc  # noqa: E402

PANELS = {
    "kospi": os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel.parquet"),
    "kospi_full": os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel_kospi_full.parquet"),
    "kosdaq": os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel_kosdaq_full.parquet"),
}
OUT_DIR = os.path.join(ROOT, "data", "dintel")
COLS = ["corp_code", "rcept_dt", "rcept_no", "report_nm"]


def corp_codes_for(market):
    p = pd.read_parquet(PANELS[market], columns=["corp_code"])
    return sorted(p["corp_code"].dropna().astype(str).str.zfill(8).unique())


QUOTA = ("[020]", "[011]", "[012]", "[901]")   # 사용한도 초과·키 문제 -> 계속 불러도 소용없음


def _raw_dir(market, kind):
    return os.path.join(OUT_DIR, "events_raw" if kind == "B" else f"events_raw_{kind}", market)


def collect(market, start="2015-01-01", limit=None, sleep=0.3, kind="B"):
    raw_dir = _raw_dir(market, kind)
    os.makedirs(raw_dir, exist_ok=True)
    codes = corp_codes_for(market)[:limit] if limit else corp_codes_for(market)
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    todo = [c for c in codes if not os.path.exists(os.path.join(raw_dir, f"{c}.csv"))]
    print(f"[{market}/{kind}] corps {len(codes)} | cached {len(codes) - len(todo)} | to fetch {len(todo)} "
          f"| {start}~{end}", flush=True)
    t0, fails = time.time(), 0
    for i, cc in enumerate(todo):
        try:
            df = Dc.search_disclosures(corp_code=cc, start_date=start, end_date=end, pblntf_ty=kind, sleep=sleep)
        except Exception as e:  # 한 기업 실패가 전체를 멈추지 않게 - 캐시를 안 남기므로 재실행 시 재시도
            if any(q in str(e) for q in QUOTA):
                print(f"  DART quota/key stop: {str(e)[:120]} -> rerun tomorrow to resume", flush=True)
                merge(market, kind)
                sys.exit(3)
            fails += 1
            print(f"  fail {cc}: {str(e)[:120]}", flush=True)
            time.sleep(2.0)
            continue
        out = pd.DataFrame(columns=COLS) if df is None or df.empty else \
            df.assign(corp_code=cc).reindex(columns=COLS)
        out.to_csv(os.path.join(raw_dir, f"{cc}.csv"), index=False, encoding="utf-8")
        if (i + 1) % 50 == 0 or i + 1 == len(todo):
            el = time.time() - t0
            print(f"  {i + 1}/{len(todo)} done, {el / 60:.1f}m elapsed, "
                  f"~{el / (i + 1) * (len(todo) - i - 1) / 60:.0f}m left, fails {fails}", flush=True)
        time.sleep(sleep)
    merge(market, kind)
    if fails:
        print(f"[{market}] {fails} corps failed - rerun the same command to retry them.", flush=True)


def merge(market, kind="B"):
    raw_dir = _raw_dir(market, kind)
    parts = []
    for f in os.listdir(raw_dir):
        d = pd.read_csv(os.path.join(raw_dir, f), dtype=str)
        if len(d):
            parts.append(d)
    ev = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=COLS)
    path = os.path.join(OUT_DIR, f"events_{market}.csv" if kind == "B" else f"events_{kind}_{market}.csv")
    ev.to_csv(path, index=False, encoding="utf-8")
    print(f"[{market}] merged {len(ev):,} events from {ev['corp_code'].nunique() if len(ev) else 0} corps "
          f"-> {path}", flush=True)
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("market", choices=sorted(PANELS))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--kind", default="B", choices=["B", "I"])
    a = ap.parse_args()
    collect(a.market, a.start, a.limit, kind=a.kind)

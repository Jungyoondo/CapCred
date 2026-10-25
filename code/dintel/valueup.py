"""밸류업(기업가치 제고 계획) 공시 - 수집과 시장 반응 분석. 사업 주력 후보 '밸류업 코파일럿'의 근거 데이터.

python -X utf8 -m dintel.valueup collect kosdaq [--limit N]   # 기업별 거래소공시(I) 2024-05~ 중 밸류업만
python -X utf8 -m dintel.valueup collect kospi                 # kospi_full 패널이 있으면 그걸 쓰는 걸 권장
python -X utf8 -m dintel.valueup analyze kospi kosdaq

## DART 표기(2026-10-03 실측)
- 본공시  : "기업가치제고계획(자율공시)"
- 예고    : "기업가치제고계획예고(안내공시)"
- 이행현황: "[기재정정]기업가치제고계획(자율공시) (이행현황)" - 정정 형식으로 올라옴
- 재공시  : "... (고배당기업 표시를 위한 재공시)" - 새 정보 없음, 분석 제외
## 분석
- 범주: 예고 / 첫 본공시 / 갱신 본공시 / 이행현황. 같은 기업·같은 범주 10일 내 반복은 첫 건만.
- 수익률·위약·검정은 event_reaction.reactions_for와 동일(시장 동일가중 대비, 달력월 블록 부트스트랩, BH).
- 첫 본공시는 공시 직전 PBR(<1 vs >=1)과 시가총액 3분위로도 나눈다(PIT: 공시일 이전 마지막 패널 값).
출력: data/dintel/VALUEUP_SUMMARY.txt, data/dintel/valueup_events_<market>.csv
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd

from dintel import event_reaction as ER

ROOT = ER.ROOT
OUT_DIR = ER.OUT_DIR
RAW = os.path.join(OUT_DIR, "valueup_raw")
SUMMARY = os.path.join(OUT_DIR, "VALUEUP_SUMMARY.txt")
STATS_JSON = os.path.join(OUT_DIR, "valueup_stats.json")
START = "2024-05-01"
MIN_N = int(os.environ.get("DINTEL_MIN_N", "20"))   # 밸류업은 표본이 작아 기본 20


def panel_for(market):
    if market == "kospi":
        full = ER.PANELS.get("kospi_full")
        if full and os.path.exists(full):
            return "kospi_full"
    return market


def collect(market, limit=None, sleep=0.25):
    sys.path.insert(0, ROOT)
    import dart_client as Dc
    pm = panel_for(market)
    codes = sorted(pd.read_parquet(ER.PANELS[pm], columns=["corp_code"])["corp_code"].dropna()
                   .astype(str).str.zfill(8).unique())
    d = os.path.join(RAW, pm)
    os.makedirs(d, exist_ok=True)
    todo = [c for c in codes if not os.path.exists(os.path.join(d, f"{c}.json"))]
    todo = todo[:limit] if limit else todo
    print(f"[{pm}] corps {len(codes)} | to fetch {len(todo)} | I-type filings since {START}", flush=True)
    t0, fails = time.time(), 0
    for i, cc in enumerate(todo):
        try:
            df = Dc.search_disclosures(corp_code=cc, start_date=START,
                                       end_date=pd.Timestamp.today().strftime("%Y-%m-%d"), pblntf_ty="I", sleep=sleep)
        except Exception as e:
            fails += 1
            print(f"  fail {cc}: {str(e)[:100]}", flush=True)
            time.sleep(2.0)
            continue
        rows = [] if df is None or df.empty else \
            df[df["report_nm"].str.contains("기업가치제고", na=False)][["rcept_dt", "rcept_no", "report_nm"]] \
            .to_dict("records")
        with open(os.path.join(d, f"{cc}.json"), "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False)
        if (i + 1) % 100 == 0 or i + 1 == len(todo):
            el = time.time() - t0
            print(f"  {i + 1}/{len(todo)} ({el / 60:.1f}m, ~{el / (i + 1) * (len(todo) - i - 1) / 60:.0f}m left, "
                  f"fails {fails})", flush=True)
        time.sleep(sleep)


def classify(name):
    n = str(name).replace(" ", "")
    if "재공시" in n:
        return None
    if "이행" in n:
        return "이행현황"
    if n.startswith("["):
        return None                     # 이행현황이 아닌 단순 정정
    if "예고" in n:
        return "예고"
    return "본공시"


def load(market):
    pm = panel_for(market)
    d = os.path.join(RAW, pm)
    rows = []
    for f in os.listdir(d) if os.path.isdir(d) else []:
        for r in json.load(open(os.path.join(d, f), encoding="utf-8")):
            rows.append({"corp_code": f[:-5], **r})
    ev = pd.DataFrame(rows)
    if ev.empty:
        return ev, pm
    ev["etype"] = ev["report_nm"].map(classify)
    ev = ev.dropna(subset=["etype"])
    ev["rdate"] = pd.to_datetime(ev["rcept_dt"], format="%Y%m%d")
    ev = ev.sort_values(["corp_code", "rdate"])
    first = ev[ev["etype"] == "본공시"].groupby("corp_code")["rdate"].transform("min")
    ev.loc[ev["etype"] == "본공시", "etype"] = np.where(
        ev.loc[ev["etype"] == "본공시", "rdate"] == first, "첫 본공시", "갱신 본공시")
    gap = ev.groupby(["corp_code", "etype"])["rdate"].diff().dt.days
    return ev[gap.isna() | (gap > 10)].reset_index(drop=True), pm


def add_pbr_size(ev, pm):
    pan = pd.read_parquet(ER.PANELS[pm], columns=["date", "corp_code", "market_cap", "total_equity"]).dropna(
        subset=["market_cap"])
    pan["corp_code"] = pan["corp_code"].astype(str).str.zfill(8)
    pan = pan.sort_values("date")
    left = ev[["corp_code", "rdate"]].reset_index().sort_values("rdate")
    left["k"] = left["rdate"] - pd.Timedelta(days=1)
    m = pd.merge_asof(left, pan.rename(columns={"date": "k"}), on="k", by="corp_code", direction="backward")
    m = m.set_index("index").reindex(ev.index)
    ev["pbr"] = m["market_cap"] / m["total_equity"].where(m["total_equity"] > 0)
    ev["mcap"] = m["market_cap"]
    return ev


def matched_control(ev, pm, windows=("ann2", "d20", "d60"), excl_days=60):
    """동일 시점·동일 시총 3분위·최근 ±excl_days 거래일 내 밸류업 공시가 없는 기업들의 같은 창 평균 수익률을
    대조군으로 뺀 값(<w>_mnet). '그 시기 대형주가 원래 강했다' 같은 시점·규모 효과를 제거하기 위함."""
    O, C, dates, codes, cmap = ER.load_prices(pm)
    kidx = {c: i for i, c in enumerate(codes)}
    pan = pd.read_parquet(ER.PANELS[pm], columns=["date", "stock_code", "market_cap"])
    pan["stock_code"] = pan["stock_code"].astype(str)
    M = pan.pivot(index="date", columns="stock_code", values="market_cap").reindex(index=dates, columns=codes)
    M = M.to_numpy(np.float64)
    T = len(dates)
    ti = np.searchsorted(dates.values, ev["rdate"].values)
    ki = ev["stock_code"].map(kidx).to_numpy()
    # 밸류업 공시 기업-시점 마스크(대조군 제외용)
    filed = np.zeros((T, len(codes)), dtype=bool)
    for t, k in zip(ti, ki):
        if t < T and not pd.isna(k):
            filed[max(0, t - excl_days):min(T, t + excl_days + 1), int(k)] = True
    for w in windows:
        kind, a, b = ER.WINDOWS[w]
        S = O if kind == "open" else C
        net = np.full(len(ev), np.nan)
        for j, (t, k) in enumerate(zip(ti, ki)):
            if pd.isna(k) or t + a < 1 or t + b >= T:
                continue
            k = int(k)
            with np.errstate(divide="ignore", invalid="ignore"):
                R = np.clip(C[t + b] / S[t + a] - 1, -0.9, 3.0)
            mc = M[t - 1]
            ok = np.isfinite(mc) & np.isfinite(R)
            if not ok[k]:
                continue
            q1, q2 = np.nanquantile(mc[ok], [1 / 3, 2 / 3])
            tert = np.digitize(mc, [q1, q2])
            ctrl = ok & (tert == tert[k]) & ~filed[t]
            ctrl[k] = False
            if ctrl.sum() >= 10:
                net[j] = R[k] - R[ctrl].mean()
        ev[f"{w}_mnet"] = net
    return ev


def table(ev, pl, tag, rng, js=None):
    base = {w: float(np.nanmean(pl[w])) for w in ER.WINDOWS}
    groups = [(c, ev[ev["etype"] == c]) for c in ("예고", "첫 본공시", "갱신 본공시", "이행현황")]
    f1 = ev[ev["etype"] == "첫 본공시"]
    groups += [("첫 본공시 · PBR<1", f1[f1["pbr"] < 1]), ("첫 본공시 · PBR>=1", f1[f1["pbr"] >= 1])]
    if f1["mcap"].notna().sum() >= 3 * MIN_N:
        q1, q2 = np.nanquantile(f1["mcap"], [1 / 3, 2 / 3])
        groups += [("첫 본공시 · 시총 소", f1[f1["mcap"] <= q1]), ("첫 본공시 · 시총 중", f1[(f1["mcap"] > q1) & (f1["mcap"] <= q2)]),
                   ("첫 본공시 · 시총 대", f1[f1["mcap"] > q2])]
    rows = []
    for name, g in groups:
        if g["d20"].notna().sum() < MIN_N:
            rows.append({"group": name, "n": int(g["d20"].notna().sum()), "skip": True})
            continue
        r = {"group": name, "n": int(g["d20"].notna().sum()), "skip": False}
        for w in ER.WINDOWS:
            x = g[w].to_numpy()
            lo, hi, p = ER.boot_ci(x, g["month"].to_numpy(), rng)
            r.update({w: np.nanmean(x), f"{w}_med": np.nanmedian(x), f"{w}_lo": lo, f"{w}_hi": hi, f"{w}_p": p})
        r["hit20"] = float(np.nanmean(g["d20"].to_numpy() > 0))
        for w in ("d20", "d60"):
            if f"{w}_mnet" in g:
                x = g[f"{w}_mnet"].to_numpy()
                lo, hi, p = ER.boot_ci(x, g["month"].to_numpy(), rng)
                r.update({f"{w}_m": np.nanmean(x), f"{w}_m_med": np.nanmedian(x), f"{w}_m_lo": lo, f"{w}_m_hi": hi,
                          f"{w}_m_p": p})
        rows.append(r)
    T = pd.DataFrame(rows)
    ok = ~T["skip"]
    T_ok = T
    for w in list(ER.WINDOWS) + ["d20_m", "d60_m"]:
        if f"{w}_p" in T:
            T.loc[ok, f"{w}_sig"] = ER.bh(T.loc[ok, f"{w}_p"].to_numpy())
    if js is not None:
        keep = [c for c in T.columns if not c.endswith("_p")]
        js[tag] = {"placebo": base, "groups": json.loads(T[keep].to_json(orient="records"))}
    lines = [f"[{tag}] 위약 기준선: " + " ".join(f"{w} {base[w]:+.2%}" for w in ER.WINDOWS),
             f"[{tag}] 범주 | n | 사전pre20 | 발표ann2 평균/중앙 | d10 | d20 평균/중앙 [95%CI] 상승 | d60 "
             f"|| 동시점·동규모 비공시기업 대조 차감: d20 평균/중앙 [95%CI] | d60 평균 [95%CI]   (★=BH 유의)"]
    s = lambda r, w: f"{r[w]:+.1%}{'★' if r.get(f'{w}_sig') else ''}"
    for _, r in T.iterrows():
        if r["skip"]:
            lines.append(f"  {r['group']:<16} | n={r['n']} (표본 {MIN_N} 미만 - 생략)")
            continue
        lines.append(f"  {r['group']:<16} | {r['n']:>3} | {s(r, 'pre20'):>7} | {s(r, 'ann2'):>7}/{r['ann2_med']:+.1%} | "
                     f"{s(r, 'd10'):>7} | {s(r, 'd20'):>7}/{r['d20_med']:+.1%} [{r['d20_lo']:+.1%},{r['d20_hi']:+.1%}] "
                     f"{r['hit20']:.0%} | {s(r, 'd60'):>7} || "
                     + (f"{s(r, 'd20_m'):>7}/{r['d20_m_med']:+.1%} [{r['d20_m_lo']:+.1%},{r['d20_m_hi']:+.1%}] | "
                        f"{s(r, 'd60_m'):>7} [{r['d60_m_lo']:+.1%},{r['d60_m_hi']:+.1%}]" if "d20_m" in r and pd.notna(r.get("d20_m")) else "-"))
    return lines


def analyze(markets):
    rng = np.random.default_rng(20261003)
    out = [f"##### 밸류업 공시 반응 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 최소표본 {MIN_N} | 부트스트랩 {ER.N_BOOT}"]
    evs, pls = [], []
    js = {"generated": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "markets": {}}
    for m in markets:
        ev, pm = load(m)
        if ev.empty:
            out.append(f"[{m}] 수집된 밸류업 공시 없음 - 먼저 collect")
            continue
        cnt = ev["etype"].value_counts().to_dict()
        r, pl, unm = ER.reactions_for(ev, pm, rng)
        r = add_pbr_size(r, pm)
        r = matched_control(r, pm)
        r.to_csv(os.path.join(OUT_DIR, f"valueup_events_{m}.csv"), index=False, encoding="utf-8")
        out.append(f"[{m}] 패널 {pm} | 이벤트 {len(r)}건 {cnt} | 기업 {r['corp_code'].nunique()} | 매핑실패 {unm} "
                   f"| {r['rdate'].min():%Y-%m}~{r['rdate'].max():%Y-%m} | d60은 최근 공시 제외됨")
        out += table(r, pl, m, rng, js["markets"])
        evs.append(r); pls.append(pl)
    if len(evs) > 1:
        out += table(pd.concat(evs), pd.concat(pls), "+".join(markets), rng, js["markets"])
    text = "\n".join(out)
    print(text, flush=True)
    with open(SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(STATS_JSON, "w", encoding="utf-8") as fh:
        json.dump(js, fh, ensure_ascii=False, indent=1, default=str)
    print(f"-> {SUMMARY}", flush=True)
    print(f"-> {STATS_JSON}", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["collect", "analyze"])
    ap.add_argument("markets", nargs="+")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args()
    if a.cmd == "collect":
        for m in a.markets:
            collect(m, a.limit)
    else:
        analyze(a.markets)

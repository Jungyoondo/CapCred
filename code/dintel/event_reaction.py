"""공시 유형별 시장 반응 통계 - 이벤트 스터디(매수후보유 초과수익, BHAR).

python -X utf8 -m dintel.event_reaction kospi            # 코스피 385 표본(기존 수집분)
python -X utf8 -m dintel.event_reaction kosdaq           # dintel.collect_events kosdaq 이후
python -X utf8 -m dintel.event_reaction kospi kosdaq     # 시장별로 각각 + 합산
python -X utf8 -m dintel.event_reaction --kind I kospi_full kosdaq   # 거래소공시(collect_events --kind I 이후)
  -> EVENT_SUMMARY_I.txt, event_stats_I.json, event_reactions_I_<market>.csv. 유형 이름은 dintel.etypes 규칙.

## 이벤트 정의
- 원공시만: report_nm 앞에 [기재정정]/[첨부정정]/[발행조건확정] 등 대괄호 접두가 붙은 후속 공시는 제외.
- 유형 = 괄호 안 명칭(예: "주요사항보고서(유상증자결정)" -> 유상증자결정).
- 같은 기업·같은 유형이 10일(달력일) 안에 반복되면 첫 공시만.
- t0 = 접수일(rcept_dt) 이후 첫 거래일(접수일 당일이 거래일이면 당일). 공시 시각은 데이터에 없음.

## 수익률 창(전부 해당 시장 동일가중 평균 대비 초과수익, 같은 창·같은 가격기준)
- pre20 : 종가[t0-21] -> 종가[t0-1]  (공시 전 선반영)
- ann2  : 종가[t0-1]  -> 종가[t0+1]  (발표 반응. 장중·장마감 후 공시를 모두 포괄)
- d10/d20/d60 : 시가[t0+1] -> 종가[t0+h]  (공시를 보고 다음날 시가에 산 투자자가 얻는 수익 = 실행 가능)
- 개별 수익률은 [-90%, +300%]로 절단(액면분할 미조정 등 극단 오류 방어).

## 통계
- 유형별 n, 평균, 중앙값, 상승비율, 평균의 95% 신뢰구간(달력월 블록 부트스트랩 - 같은 달에 몰린
  이벤트의 상관을 반영), 부트스트랩 p값.
- 다중검정: 창별로 유형 전체에 Benjamini-Hochberg(q=0.10) 적용 - ★는 보정 후에도 유의.
- 위약(placebo): 같은 종목의 무작위 날짜(그 종목 공시일 ±20거래일 제외)를 이벤트 수의 3배만큼 뽑아
  같은 계산. 생존편향 등으로 "아무 날이나 사도 생기는 초과수익"의 크기 = 기준선.
  유형 평균에서 위약 평균을 뺀 값(net)을 함께 본다.

출력: data/dintel/EVENT_SUMMARY.txt(덮어쓰기, 붙여넣기용), data/dintel/event_reactions_<market>.csv(이벤트별).
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "dintel")
PANELS = {
    "kospi": os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel.parquet"),
    "kospi_full": os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel_kospi_full.parquet"),
    "kosdaq": os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel_kosdaq_full.parquet"),
}
LEGACY_KOSPI_EVENTS = os.path.join(ROOT, "data", "quant", "reports", "dart_disclosure_events.csv")
WINDOWS = {  # 이름: (시작가격종류, 시작오프셋, 끝오프셋) - 끝은 항상 종가
    "pre20": ("close", -21, -1),
    "ann2": ("close", -1, 1),
    "d10": ("open", 1, 10),
    "d20": ("open", 1, 20),
    "d60": ("open", 1, 60),
}
MIN_N = int(os.environ.get("DINTEL_MIN_N", "30"))
N_BOOT = int(os.environ.get("DINTEL_NBOOT", "2000"))
SUMMARY = os.path.join(OUT_DIR, "EVENT_SUMMARY.txt")


KIND = "B"   # main()에서 --kind로 바뀜


def _sfx(name):
    """B(주요사항)는 기존 파일명 그대로, 다른 종류는 _<kind>를 붙인다."""
    if KIND == "B":
        return name
    stem, ext = os.path.splitext(name)
    for pre in ("event_reactions_", "events_"):
        if stem.startswith(pre):
            return f"{pre}{KIND}_{stem[len(pre):]}{ext}"
    return f"{stem}_{KIND}{ext}"


def load_events(market):
    path = os.path.join(OUT_DIR, _sfx(f"events_{market}.csv"))
    if not os.path.exists(path) and market == "kospi" and os.path.exists(LEGACY_KOSPI_EVENTS):
        path = LEGACY_KOSPI_EVENTS
    if not os.path.exists(path):
        raise SystemExit(f"[{market}] 이벤트 파일 없음 - 먼저: python -X utf8 -m dintel.collect_events {market}")
    ev = pd.read_csv(path, dtype=str)
    n_raw = len(ev)
    ev = ev[~ev["report_nm"].str.startswith("[", na=True)]                 # 정정·후속 공시 제외
    if KIND == "B":
        ev["etype"] = ev["report_nm"].str.extract(r"\((.*)\)\s*$")[0].str.replace(" ", "", regex=False)
    else:
        from dintel.etypes import etype
        ev["etype"] = ev["report_nm"].map(etype)
    ev = ev.dropna(subset=["etype"])
    ev["rdate"] = pd.to_datetime(ev["rcept_dt"], format="%Y%m%d")
    ev["corp_code"] = ev["corp_code"].str.zfill(8)
    ev = ev.sort_values(["corp_code", "etype", "rdate"])
    gap = ev.groupby(["corp_code", "etype"])["rdate"].diff().dt.days
    ev = ev[gap.isna() | (gap > 10)]
    return ev.reset_index(drop=True), n_raw


def load_prices(market):
    p = pd.read_parquet(PANELS[market], columns=["date", "stock_code", "corp_code", "open", "close"])
    p["stock_code"] = p["stock_code"].astype(str)
    O = p.pivot(index="date", columns="stock_code", values="open").sort_index()
    C = p.pivot(index="date", columns="stock_code", values="close").reindex_like(O)
    cmap = p.dropna(subset=["corp_code"]).drop_duplicates("stock_code").set_index(
        p.dropna(subset=["corp_code"]).drop_duplicates("stock_code")["corp_code"].astype(str).str.zfill(8)
    )["stock_code"].to_dict()
    return O.to_numpy(np.float64), C.to_numpy(np.float64), O.index, list(O.columns), cmap


def window_returns(O, C, ti, ki, kind, a, b):
    """이벤트 배열(ti 날짜인덱스, ki 종목인덱스)에 대해 창 수익률. 범위 밖/결측이면 NaN."""
    T = O.shape[0]
    s_i, e_i = ti + a, ti + b
    ok = (s_i >= 0) & (e_i < T)
    out = np.full(len(ti), np.nan)
    S = O if kind == "open" else C
    with np.errstate(divide="ignore", invalid="ignore"):
        r = C[e_i[ok], ki[ok]] / S[s_i[ok], ki[ok]] - 1
    out[ok] = r
    return np.clip(out, -0.9, 3.0)


def ew_benchmark(O, C, kind, a, b):
    """모든 날짜 t에 대해 같은 창의 시장 동일가중 평균(종목별 절단 후). 길이 T."""
    T = O.shape[0]
    bm = np.full(T, np.nan)
    S = O if kind == "open" else C
    lo, hi = max(0, -a), T - max(0, b)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = C[lo + b:hi + b] / S[lo + a:hi + a] - 1
    r = np.clip(r, -0.9, 3.0)
    bm[lo:hi] = np.nanmean(r, axis=1)
    return bm


def abnormal(O, C, ti, ki, bms):
    out = {}
    for w, (kind, a, b) in WINDOWS.items():
        out[w] = window_returns(O, C, ti, ki, kind, a, b) - bms[w][np.clip(ti, 0, len(bms[w]) - 1)]
    return pd.DataFrame(out)


def boot_ci(x, months, rng):
    """달력월 블록 부트스트랩: 월 단위로 복원추출해 평균 분포."""
    df = pd.DataFrame({"x": x, "m": months}).dropna()
    if len(df) < 5:
        return np.nan, np.nan, np.nan
    groups = [g["x"].to_numpy() for _, g in df.groupby("m")]
    k = len(groups)
    sums = np.array([g.sum() for g in groups]); cnts = np.array([len(g) for g in groups])
    idx = rng.integers(0, k, size=(N_BOOT, k))
    means = sums[idx].sum(1) / cnts[idx].sum(1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    p = 2 * min((means <= 0).mean(), (means >= 0).mean())
    return lo, hi, max(p, 1.0 / N_BOOT)


def bh(pvals, q=0.10):
    p = np.asarray(pvals, dtype=float)
    ok = ~np.isnan(p)
    sig = np.zeros(len(p), dtype=bool)
    if ok.sum() == 0:
        return sig
    order = np.argsort(p[ok])
    ranked = p[ok][order]
    m = ok.sum()
    passed = ranked <= q * (np.arange(1, m + 1) / m)
    kmax = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    s = np.zeros(m, dtype=bool)
    s[order[:kmax]] = True
    sig[np.flatnonzero(ok)] = s
    return sig


def reactions_for(ev, market, rng, placebo_mult=3):
    """임의의 이벤트 목록(corp_code, rdate[, etype, ...]) -> (이벤트별 창 수익률, 위약, 매핑실패 수).
    밸류업 등 다른 모듈도 같은 방법론을 재사용한다."""
    O, C, dates, codes, cmap = load_prices(market)
    kidx = {c: i for i, c in enumerate(codes)}
    ev["stock_code"] = ev["corp_code"].map(cmap)
    n_unmapped = ev["stock_code"].isna().sum()
    ev = ev.dropna(subset=["stock_code"])
    ev["ti"] = np.searchsorted(dates.values, ev["rdate"].values)          # 접수일 이후 첫 거래일
    ev = ev[ev["ti"] < len(dates)]
    ev["ki"] = ev["stock_code"].map(kidx).astype(int)
    bms = {w: ew_benchmark(O, C, *spec) for w, spec in WINDOWS.items()}
    ab = abnormal(O, C, ev["ti"].to_numpy(), ev["ki"].to_numpy(), bms)
    ev = pd.concat([ev.reset_index(drop=True), ab], axis=1)
    ev["month"] = ev["rdate"].dt.to_period("M").astype(str)
    ev["market"] = market

    # 위약: 같은 종목, 그 종목 공시일 ±20거래일 밖의 무작위 날짜
    pl_ti, pl_ki = [], []
    for k, g in ev.groupby("ki"):
        valid = np.flatnonzero(~np.isnan(C[:, k]))
        valid = valid[(valid > 21) & (valid < len(dates) - 61)]
        if len(valid) == 0:
            continue
        mask = np.ones(len(valid), dtype=bool)
        for t in g["ti"].to_numpy():
            mask &= np.abs(valid - t) > 20
        cand = valid[mask]
        if len(cand):
            pick = rng.choice(cand, size=min(placebo_mult * len(g), len(cand)), replace=False)
            pl_ti.extend(pick); pl_ki.extend([k] * len(pick))
    pl = abnormal(O, C, np.array(pl_ti), np.array(pl_ki), bms)
    pl["month"] = pd.DatetimeIndex(dates[np.array(pl_ti)]).to_period("M").astype(str)
    return ev.drop(columns=["ti", "ki"]), pl, int(n_unmapped)


def run_market(market, rng):
    ev, n_raw = load_events(market)
    ev, pl, n_unmapped = reactions_for(ev, market, rng)
    ev.to_csv(os.path.join(OUT_DIR, _sfx(f"event_reactions_{market}.csv")), index=False, encoding="utf-8")
    meta = dict(n_raw=n_raw, n_events=len(ev), n_unmapped=int(n_unmapped), corps=ev["corp_code"].nunique(),
                period=f"{ev['rdate'].min():%Y-%m}~{ev['rdate'].max():%Y-%m}")
    return ev, pl, meta


STATS_JSON = os.path.join(OUT_DIR, "event_stats.json")


def table(ev, pl, tag, rng, stats_out=None):
    """stats_out(dict)이 주어지면 유형별 수치를 stats_out[tag]에 저장(웹 리포트 조회용)."""
    lines = []
    rows = []
    for et, g in ev.groupby("etype"):
        if g["d20"].notna().sum() < MIN_N:
            continue
        r = {"etype": et, "n": int(g["d20"].notna().sum())}
        for w in WINDOWS:
            x = g[w].to_numpy()
            lo, hi, p = boot_ci(x, g["month"].to_numpy(), rng)
            r.update({w: np.nanmean(x), f"{w}_lo": lo, f"{w}_hi": hi, f"{w}_p": p, f"{w}_med": np.nanmedian(x)})
        r["hit20"] = np.nanmean(g["d20"].to_numpy() > 0)
        r["top_firm"] = g["corp_code"].value_counts(normalize=True).iloc[0]   # 한 기업 쏠림
        rows.append(r)
    if not rows:
        return [f"[{tag}] 표본 {MIN_N}건 이상인 유형 없음"]
    T = pd.DataFrame(rows)
    for w in WINDOWS:
        T[f"{w}_sig"] = bh(T[f"{w}_p"].to_numpy())
    T = T.sort_values("n", ascending=False)
    base = {w: np.nanmean(pl[w]) for w in WINDOWS}
    if stats_out is not None:
        keep = ["n", "hit20", "top_firm"] + [f"{w}{suf}" for w in WINDOWS
                                             for suf in ("", "_med", "_lo", "_hi", "_sig")]
        stats_out[tag] = {"placebo": {w: float(base[w]) for w in WINDOWS},
                          "types": {r.etype: {k: (bool(r[k]) if k.endswith("_sig") else float(r[k]))
                                              for k in keep} for _, r in T.iterrows()}}
    pl_ci = {w: boot_ci(pl[w].to_numpy(), pl["month"].to_numpy(), rng) for w in WINDOWS}
    lines.append(f"[{tag}] 위약(무작위 날짜 n={pl['d20'].notna().sum():,}) 기준선: " + " ".join(
        f"{w} {base[w]:+.2%}[{pl_ci[w][0]:+.1%},{pl_ci[w][1]:+.1%}]" for w in WINDOWS))
    lines.append(f"[{tag}] 유형 | n(최다기업비중) | 발표ann2 평균/중앙 | 사후d10 | 사후d20 평균/중앙 [95%CI] 상승비율 | d60 | 사전pre20"
                 f"   (★=BH보정 유의, 평균-중앙 차이가 크면 소수 극단값 주도)")
    f = lambda r, w: f"{r[w]:+.1%}{'★' if r[f'{w}_sig'] else ''}"
    show = T
    if KIND != "B":   # 거래소공시는 유형이 수백 개 -> 붙여넣기용 요약엔 보정 후 유의한 유형만(전체는 json)
        any_sig = T[[f"{w}_sig" for w in ("ann2", "d10", "d20", "d60")]].any(axis=1)
        # 표본이 수만 건이면 +0.2%도 유의 -> 위약 차감 1%p 이상(발표 또는 20일)인 것만, 크기 순
        eff = np.maximum((T["ann2"] - base["ann2"]).abs() * T["ann2_sig"],
                         (T["d20"] - base["d20"]).abs() * T["d20_sig"])
        mat = any_sig & (eff >= 0.01) & (T["n"] >= 100)
        show = T[mat].assign(_e=eff[mat]).sort_values("_e", ascending=False).head(18)
        lines.append(f"  (유형 {len(T)}개 중 보정 후 유의 {int(any_sig.sum())}개, 그중 n>=100이고 위약 차감 1%p 이상 "
                     f"{int(mat.sum())}개 - 효과 큰 순 최대 18개 표시, 전체는 event_stats_I.json)")
    for _, r in show.iterrows():
        lines.append(f"  {r.etype[:18]:<18} | {r.n:>4}({r.top_firm:.0%}) | {f(r, 'ann2'):>7}/{r.ann2_med:+.1%} | "
                     f"{f(r, 'd10'):>7} | {f(r, 'd20'):>7}/{r.d20_med:+.1%} [{r.d20_lo:+.1%},{r.d20_hi:+.1%}] "
                     f"{r.hit20:.0%} | {f(r, 'd60'):>7} | {f(r, 'pre20'):>7}")
    return lines


def main(markets):
    global KIND, SUMMARY, STATS_JSON
    if "--kind" in markets:
        i = markets.index("--kind")
        KIND = markets[i + 1]
        markets = markets[:i] + markets[i + 2:]
        SUMMARY, STATS_JSON = _sfx(SUMMARY), _sfx(STATS_JSON)
    os.makedirs(OUT_DIR, exist_ok=True)
    rng = np.random.default_rng(20261003)
    out = [f"##### 공시 반응 통계{'' if KIND == 'B' else ' [' + KIND + ']'} {pd.Timestamp.now():%Y-%m-%d %H:%M} | 최소표본 {MIN_N} | 부트스트랩 {N_BOOT}"]
    evs, pls = [], []
    stats = {"generated": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "min_n": MIN_N, "kind": KIND, "markets": {}}
    for m in markets:
        ev, pl, meta = run_market(m, rng)
        out.append(f"[{m}] 원공시 {meta['n_events']:,}건(원자료 {meta['n_raw']:,}, 종목매핑 실패 {meta['n_unmapped']}) "
                   f"| {meta['corps']}개사 | {meta['period']}")
        out += table(ev, pl, m, rng, stats["markets"])
        stats["markets"].setdefault(m, {})["meta"] = meta
        evs.append(ev); pls.append(pl)
    if len(markets) > 1:
        out += table(pd.concat(evs), pd.concat(pls), "+".join(markets), rng, stats["markets"])
    text = "\n".join(out)
    print(text, flush=True)
    with open(SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    import json
    with open(STATS_JSON, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, ensure_ascii=False, indent=1, default=str)
    print(f"-> {SUMMARY}", flush=True)
    print(f"-> {STATS_JSON}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["kospi"])

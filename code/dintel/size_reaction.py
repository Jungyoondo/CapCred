"""공시 규모·방식별 반응 통계 - "같은 전환사채라도 희석이 큰 것은 더 나쁜가?"

python -X utf8 -m dintel.size_reaction kospi kosdaq
선행: dintel.event_reaction(이벤트별 수익률 CSV) + dintel.details collect(상세 캐시)

- 이벤트와 상세의 연결 키: (corp_code, 접수일, 유형). 코스피 기존 수집본엔 rcept_no가 없어 이 키를 쓴다.
- 금액 기반 규모(자사주·교환사채)는 공시 직전 거래일 시가총액으로 나눈다(PIT).
- 규모 구간: 유형별 3분위(소/중/대). 경계값을 함께 기록해 웹 리포트가 새 공시를 같은 구간에 배정.
- 방식(사모/공모, 주주배정/제3자배정/일반공모): 표본 30건 이상 범주만.
- 통계·검정은 event_reaction과 동일(평균·중앙·상승비율, 달력월 블록 부트스트랩, BH q=0.10, 위약 차감값 병기).
출력: data/dintel/SIZE_SUMMARY.txt(붙여넣기용), data/dintel/event_size_stats.json(웹 조회용)
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

from dintel import details as DT
from dintel import event_reaction as ER

OUT_DIR = ER.OUT_DIR
SUMMARY = os.path.join(OUT_DIR, "SIZE_SUMMARY.txt")
STATS_JSON = os.path.join(OUT_DIR, "event_size_stats.json")
MIN_N = ER.MIN_N
BUCKETS = ["소", "중", "대"]


def load_market(market, det):
    ev = pd.read_csv(os.path.join(OUT_DIR, f"event_reactions_{market}.csv"),
                     dtype={"corp_code": str, "stock_code": str, "rcept_dt": str}, parse_dates=["rdate"])
    ev["corp_code"] = ev["corp_code"].str.zfill(8)
    ev["rcept_dt"] = ev["rdate"].dt.strftime("%Y%m%d")
    # 공시 직전 거래일 시가총액(PIT)
    pan = pd.read_parquet(ER.PANELS[market], columns=["date", "stock_code", "market_cap"]).dropna()
    pan["stock_code"] = pan["stock_code"].astype(str)
    pan = pan.sort_values("date")
    left = ev[["stock_code", "rdate"]].reset_index().sort_values("rdate")
    left["key_date"] = left["rdate"] - pd.Timedelta(days=1)
    m = pd.merge_asof(left, pan.rename(columns={"date": "key_date"}), on="key_date", by="stock_code",
                      direction="backward")
    ev["mcap_prev"] = m.set_index("index")["market_cap"].reindex(ev.index)
    m = DT.match_details(ev, det)                      # 정정본 접수번호 문제로 날짜 근접 매칭
    ev["raw"] = m["raw"].reindex(ev.index)
    ev["method"] = m["method"].reindex(ev.index)
    # 규모지표: 상세 원자료(_raw)가 있는 행만
    sizes = []
    for r in ev.itertuples():
        raw = getattr(r, "raw", None)
        if isinstance(raw, dict) and r.etype in DT.SPECS:
            sizes.append(DT.SPECS[r.etype][1](raw, r.mcap_prev))
        else:
            sizes.append(np.nan)
    ev["size"] = sizes
    return ev


def stats_row(g, rng, base):
    r = {"n": int(g["d20"].notna().sum())}
    for w in ("ann2", "d20", "d60"):
        x = g[w].to_numpy()
        lo, hi, p = ER.boot_ci(x, g["month"].to_numpy(), rng)
        r.update({w: float(np.nanmean(x)), f"{w}_med": float(np.nanmedian(x)), f"{w}_lo": lo, f"{w}_hi": hi,
                  f"{w}_p": p, f"{w}_net": float(np.nanmean(x) - base[w])})
    r["hit20"] = float(np.nanmean(g["d20"].to_numpy() > 0))
    return r


def analyze(ev, pl, tag, rng, out_json):
    base = {w: float(np.nanmean(pl[w])) for w in ("ann2", "d20", "d60")}
    rows, meta = [], {}
    for et, g in ev.groupby("etype"):
        if et not in DT.SPECS:
            continue
        gs = g[np.isfinite(g["size"])]
        if len(gs) >= 3 * MIN_N:
            q1, q2 = np.nanquantile(gs["size"], [1 / 3, 2 / 3])
            # 한 값에 표본이 몰리면(예: 무상증자 1주당 1주) 두 경계가 같아져 '중'이 비었다(2026-10-04 실측)
            # -> 그 값 자체를 '중'으로: 소 < v, 중 = v, 대 > v
            tie = bool(np.isclose(q1, q2))
            meta[et] = {"size_def": DT.SPECS[et][2], "cuts": [float(q1), float(q2)], "tie": tie,
                        "coverage": float(len(gs) / len(g))}
            parts = (gs[gs["size"] < q1], gs[np.isclose(gs["size"], q1)], gs[gs["size"] > q1]) if tie else                 (gs[gs["size"] <= q1], gs[(gs["size"] > q1) & (gs["size"] <= q2)], gs[gs["size"] > q2])
            for b, sub in zip(BUCKETS, parts):
                if sub["d20"].notna().sum() < MIN_N:
                    continue
                rows.append({"etype": et, "kind": "size", "group": b,
                             "range": f"{sub['size'].min():.3g}~{sub['size'].max():.3g}", **stats_row(sub, rng, base)})
        if "method" in g:
            for mth, sub in g.dropna(subset=["method"]).groupby("method"):
                if sub["d20"].notna().sum() >= MIN_N:
                    rows.append({"etype": et, "kind": "method", "group": mth, "range": "",
                                 **stats_row(sub, rng, base)})
    if not rows:
        return [f"[{tag}] 규모/방식 구간별 표본 부족(상세 수집 전이거나 매칭 실패)"]
    T = pd.DataFrame(rows)
    for w in ("ann2", "d20", "d60"):
        T[f"{w}_sig"] = ER.bh(T[f"{w}_p"].to_numpy())
    lines = [f"[{tag}] 위약 기준선 ann2 {base['ann2']:+.2%} d20 {base['d20']:+.2%} d60 {base['d60']:+.2%} "
             f"| 규모=유형별 3분위, 방식=표본 {MIN_N}건 이상 범주 (★=BH 유의, net=위약 차감 평균)"]
    s = lambda r, w: f"{r[w]:+.1%}{'★' if r[f'{w}_sig'] else ''}"
    for et, g in T.groupby("etype", sort=False):
        mt = meta.get(et, {})
        lines.append(f"  ■ {et}  [규모={mt.get('size_def', '-')}, 상세매칭 {mt.get('coverage', 0):.0%}]")
        for _, r in g.iterrows():
            lines.append(f"    {r.kind:<6} {r.group:<6} {r.range:<15} n={r.n:<4} 발표 {s(r, 'ann2'):>7}/{r.ann2_med:+.1%} | "
                         f"20일 {s(r, 'd20'):>7}/{r.d20_med:+.1%} net{r.d20_net:+.1%} 상승{r.hit20:.0%} | 60일 {s(r, 'd60'):>7}")
    out_json[tag] = {"placebo": base, "meta": meta,
                     "rows": json.loads(T.drop(columns=[c for c in T if c.endswith("_p")]).to_json(orient="records"))}
    return lines


def main(markets):
    det = DT.load_details()
    if det.empty:
        raise SystemExit("상세 캐시 없음 - 먼저: python -X utf8 -m dintel.details collect <market>")
    rng = np.random.default_rng(20261003)
    out = [f"##### 공시 규모·방식별 반응 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 상세 {len(det):,}건"]
    js = {"generated": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "markets": {}}
    evs, pls = [], []
    for m in markets:
        ev = load_market(m, det)
        _, pl, _ = ER.run_market(m, rng)            # 같은 방식의 위약 기준선 재계산
        out += analyze(ev, pl, m, rng, js["markets"])
        evs.append(ev); pls.append(pl)
    if len(markets) > 1:
        out += analyze(pd.concat(evs), pd.concat(pls), "+".join(markets), rng, js["markets"])
    text = "\n".join(out)
    print(text, flush=True)
    with open(SUMMARY, "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    with open(STATS_JSON, "w", encoding="utf-8") as fh:
        json.dump(js, fh, ensure_ascii=False, indent=1, default=str)
    print(f"-> {SUMMARY}", flush=True)
    print(f"-> {STATS_JSON}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["kospi"])

"""생존편향 보정 - 이미 상장폐지된 코스닥 기업을 DART만으로 찾아 넣고, 조기경보 성능이 얼마나 바뀌는지 잰다 (2026-10-09).

python -X utf8 -m dintel.survivorship scan        # 1) 시장조치 공시(I003)를 분기별로 훑어 퇴출 코스닥 기업 찾기 (~500회 호출)
python -X utf8 -m dintel.survivorship collect     # 2) 그 기업들의 주요사항보고(B)·거래소공시(I) 수집 (기업당 2~4회)
python -X utf8 -m dintel.survivorship eval        # 3) 현재 상장사만 vs 퇴출 기업 포함 - 같은 피처·같은 분할로 비교
python -X utf8 -m dintel.survivorship all         # 1~3 연속(이어받기 가능, DART 한도면 exit 3 - 다음 날 같은 명령)

왜 공공데이터 키 없이 되나: DART 공시검색(list.json) 결과에는 상장폐지된 기업도 종목코드가 남아 있고(분류 corp_cls=E),
거래소가 낸 공시의 제출인(flr_nm)이 '코스닥시장본부'라서 당시 소속 시장을 알 수 있다(2026-10-09 확인: 2023Q1 첫 페이지 100건 중
'코스닥시장본부' 제출·현재 E 분류 16건).
퇴출 기업 정의: 코스닥시장본부가 시장조치 공시를 낸 기업 중 현재 코스닥 패널(daily_pit_panel_kosdaq_full)에 없는 기업.
  (코스피 이전상장 기업도 섞일 수 있다 - 현재 코스피 패널에 있으면 제외)
퇴출 기업의 상장 기간(월말 시점 t의 범위): 2015-01 이후 첫 공시 월 ~ 마지막 거래소공시 월.
평가: dintel.risk_score와 같은 목표(12개월 내 중대 위험 공시)·분할(학습 t<=2020-12 / 검증 t>=2022-01)·로지스틱.
  가격 피처는 퇴출 기업에 없으므로 비교는 '공시 건수 피처만(n_*)'으로 양쪽 동일하게 한다(운영 코스닥 모델도 공시만).
출력: data/dintel/SURVIVORSHIP_SUMMARY.txt, delist_scan/<YYYYQn>.csv, events_raw*/kosdaq_delisted/
"""
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import dart_client as Dc  # noqa: E402
from dintel import risk_score as R  # noqa: E402
from dintel.collect_events import COLS, QUOTA  # noqa: E402

DD = R.DD
SCAN = os.path.join(DD, "delist_scan")
OUT = os.path.join(DD, "SURVIVORSHIP_SUMMARY.txt")
MARKET = "kosdaq"
MK = "kosdaq_delisted"
FLR = {"kosdaq": "코스닥시장본부", "kospi": "유가증권시장본부"}


def log(s=""):
    print(s, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def _quarters(start="2015-01-01"):
    q = pd.period_range(start, pd.Timestamp.today(), freq="Q")
    return [(str(p), p.start_time.strftime("%Y%m%d"), min(p.end_time, pd.Timestamp.today()).strftime("%Y%m%d")) for p in q]


def _list(params, sleep=0.25):
    rows, params = [], dict(params, page_no=1, page_count=100)
    while True:
        d = Dc._get("list.json", params).json()
        st = d.get("status")
        if st == "013":
            break
        if st != "000":
            raise RuntimeError(f"[{st}] {d.get('message')}")
        rows += d.get("list", [])
        if params["page_no"] >= d.get("total_page", 1):
            break
        params["page_no"] += 1
        time.sleep(sleep)
    return rows


def scan():
    os.makedirs(SCAN, exist_ok=True)
    for q, b, e in _quarters():
        p = os.path.join(SCAN, f"{q}.csv")
        if os.path.exists(p) and not q.startswith(str(pd.Timestamp.today().year)):
            continue
        try:
            rows = _list({"bgn_de": b, "end_de": e, "pblntf_detail_ty": "I003"})
        except Exception as ex:
            if any(k in str(ex) for k in QUOTA):
                log(f"  DART quota stop at {q}: {ex} -> rerun tomorrow")
                sys.exit(3)
            log(f"  scan fail {q}: {ex}")
            continue
        df = pd.DataFrame(rows, columns=["corp_code", "corp_name", "stock_code", "corp_cls", "report_nm", "rcept_no",
                                         "flr_nm", "rcept_dt"])
        df.to_csv(p, index=False, encoding="utf-8")
        print(f"  scan {q}: {len(df):,} rows, KOSDAQ-filed now-E {((df['flr_nm'] == '코스닥시장본부') & (df['corp_cls'] == 'E')).sum()}",
              flush=True)


def targets():
    parts = [pd.read_csv(os.path.join(SCAN, f), dtype=str) for f in sorted(os.listdir(SCAN)) if f.endswith(".csv")]
    s = pd.concat(parts, ignore_index=True)
    s["corp_code"] = s["corp_code"].str.zfill(8)
    kq = s[s["flr_nm"] == FLR[MARKET]]
    cur = set()
    for m in ("kosdaq", "kospi"):
        cur |= set(pd.read_parquet(R.PANELS[m], columns=["corp_code"])["corp_code"].dropna().astype(str).str.zfill(8))
    t = kq[~kq["corp_code"].isin(cur)]
    info = t.groupby("corp_code").agg(corp_name=("corp_name", "last"), stock_code=("stock_code", "last"),
                                      corp_cls=("corp_cls", "last"), last_dt=("rcept_dt", "max"),
                                      n_delist=("report_nm", lambda x: x.str.contains("상장폐지").sum()))
    return info


def collect(sleep=0.3):
    info = targets()
    end = pd.Timestamp.today().strftime("%Y-%m-%d")
    for kind in ("B", "I"):
        raw = os.path.join(DD, "events_raw" if kind == "B" else "events_raw_I", MK)
        os.makedirs(raw, exist_ok=True)
        todo = [c for c in info.index if not os.path.exists(os.path.join(raw, f"{c}.csv"))]
        print(f"[collect {kind}] delisted KOSDAQ corps {len(info)} | to fetch {len(todo)}", flush=True)
        for i, cc in enumerate(todo):
            try:
                df = Dc.search_disclosures(corp_code=cc, start_date="2015-01-01", end_date=end, pblntf_ty=kind, sleep=sleep)
            except Exception as ex:
                if any(q in str(ex) for q in QUOTA):
                    log(f"  DART quota stop: {str(ex)[:120]} -> rerun tomorrow")
                    sys.exit(3)
                print(f"  fail {cc}: {str(ex)[:100]}", flush=True)
                continue
            out = pd.DataFrame(columns=COLS) if df is None or df.empty else df.assign(corp_code=cc).reindex(columns=COLS)
            out.to_csv(os.path.join(raw, f"{cc}.csv"), index=False, encoding="utf-8")
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(todo)}", flush=True)
            time.sleep(sleep)
    for kind in ("B", "I"):
        raw = os.path.join(DD, "events_raw" if kind == "B" else "events_raw_I", MK)
        parts = [pd.read_csv(os.path.join(raw, f), dtype=str) for f in os.listdir(raw)]
        ev = pd.concat([p for p in parts if len(p)], ignore_index=True) if parts else pd.DataFrame(columns=COLS)
        ev.to_csv(os.path.join(DD, f"events_{MK}.csv" if kind == "B" else f"events_I_{MK}.csv"), index=False,
                  encoding="utf-8")
        print(f"  merged {kind}: {len(ev):,} events, {ev['corp_code'].nunique() if len(ev) else 0} corps", flush=True)


def _events(files):
    e = pd.concat([pd.read_csv(os.path.join(DD, f), dtype=str, usecols=["corp_code", "rcept_dt", "rcept_no", "report_nm"])
                   for f in files if os.path.exists(os.path.join(DD, f))]).drop_duplicates("rcept_no")
    e = e[~e["report_nm"].map(R.T.is_followup)]
    e["corp_code"] = e["corp_code"].str.zfill(8)
    e["dt"] = pd.to_datetime(e["rcept_dt"], format="%Y%m%d")
    e["t"] = e["report_nm"].map(R.T.etype).fillna("")
    nm = e["report_nm"].str.replace(" ", "")
    e["risk"] = nm.str.contains(R.RISK_RE) & ~nm.str.contains(R.RISK_EXCL)
    return e


def _feats(m, e, last_ev):
    corps, asof = m["corp_code"].to_numpy(), m["asof"].to_numpy("datetime64[ns]")
    for g, rx in R.GROUPS.items():
        m[f"n_{g}"] = R.count_window(R._index(e, e["t"].str.contains(rx) & ~e["risk"]), corps, asof, 365)
    m["n_all"] = R.count_window(R._index(e, ~e["risk"]), corps, asof, 365)
    m["n_fin_90"] = R.count_window(R._index(e, e["t"].str.contains(R.GROUPS["fin"])), corps, asof, 90)
    ri = R._index(e, e["risk"])
    m["risk_prev"] = R.count_window(ri, corps, asof, 365) > 0
    m["n_risk_old"] = R.count_window(ri, corps, asof, 1095) - R.count_window(ri, corps, asof, 365)
    m["y"] = R.first_after(ri, corps, asof, 365)
    m["y_known"] = m["asof"] + pd.Timedelta(days=365) <= last_ev
    return m


def evaluate():
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    info = targets()
    e_cur = _events(R.EVENTS[MARKET])
    e_del = _events([f"events_{MK}.csv", f"events_I_{MK}.csv"])
    last_ev = max(e_cur["dt"].max(), e_del["dt"].max())
    # 현재 상장사: 가격 패널의 월말 시점(risk_score와 동일)
    mc = R.month_panel(MARKET)[["asof", "corp_code"]].copy()
    mc = _feats(mc, e_cur, last_ev)
    mc["delisted"] = False
    # 퇴출 기업: 첫 공시 월 ~ 마지막 거래소공시 월의 월말
    rows = []
    span = e_del.groupby("corp_code")["dt"].agg(["min", "max"])
    for cc, r in span.iterrows():
        if cc not in info.index:
            continue
        hi = min(r["max"], pd.Timestamp(info.loc[cc, "last_dt"]))
        for d in pd.date_range(max(r["min"], pd.Timestamp("2015-01-31")), hi, freq="ME"):
            rows.append((d, cc))
    md = pd.DataFrame(rows, columns=["asof", "corp_code"])
    md = _feats(md, e_del, last_ev)
    md["delisted"] = True
    allm = pd.concat([mc, md], ignore_index=True)
    feats = [c for c in allm.columns if c.startswith("n_")]
    log(f"\n##### 생존편향 보정 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 시장 {MARKET} | 퇴출 기업 {len(info):,} (공시 수집 {e_del['corp_code'].nunique():,}) "
        f"| 퇴출 기업-월 {len(md):,} | 피처: 공시 건수만 {len(feats)}개(양쪽 동일)")

    def run(tag, m, test_on=None):
        d = m[~m["risk_prev"] & m["y_known"]]
        tr, te = d[d["asof"] <= "2020-12-31"], d[d["asof"] >= "2022-01-01"]
        if test_on is not None:
            te = test_on[~test_on["risk_prev"] & test_on["y_known"] & (test_on["asof"] >= "2022-01-01")]
        pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
        pipe.fit(R._xy(tr, feats), tr["y"])
        s = pipe.predict_proba(R._xy(te, feats))[:, 1]
        k = max(1, int(len(te) * 0.10))
        hit = te["y"].to_numpy()[np.argsort(-s)[:k]].mean()
        cap = te["y"].to_numpy()[np.argsort(-s)[:k]].sum() / max(te["y"].sum(), 1)
        log(f"  {tag:44s} 학습 {len(tr):,} 검증 {len(te):,} | 위험률 학습 {tr['y'].mean():.1%} 검증 {te['y'].mean():.1%} | "
            f"AUC {R.auc(te['y'], s):.3f} | 상위10% {hit:.1%} ({hit / te['y'].mean():.1f}배, 포착 {cap:.0%})")
        return pipe

    run("A 현재 상장사만(기존 방식)", mc)
    run("B 퇴출 기업 포함(보정)", allm)
    pa = run("C 현재 상장사로 학습 -> 퇴출 포함 검증", mc, test_on=allm)
    d = md[~md["risk_prev"] & md["y_known"]]
    log(f"  퇴출 기업-월만: 위험률 학습기 {d[d['asof'] <= '2020-12-31']['y'].mean():.1%} / 검증기 "
        f"{d[d['asof'] >= '2022-01-01']['y'].mean():.1%} (현재 상장사 {mc[~mc['risk_prev'] & mc['y_known']]['y'].mean():.1%})")
    log("  읽는 법: A와 B의 차이가 생존편향 크기. C는 '지금 운영 방식대로 학습한 모델이 실제(퇴출 포함) 세상에서 얼마나 맞는가'.")


def main():
    global MARKET, MK
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if len(sys.argv) > 2 and sys.argv[2] in FLR:
        MARKET, MK = sys.argv[2], f"{sys.argv[2]}_delisted"
    if cmd in ("scan", "all"):
        scan()
    if cmd in ("collect", "all"):
        collect()
    if cmd in ("eval", "all"):
        evaluate()


if __name__ == "__main__":
    main()

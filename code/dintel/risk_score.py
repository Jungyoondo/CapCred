"""재무위험 조기경보 점수(Financing-Forensics Early Warning) - 2026-10-08.

python -X utf8 -m dintel.risk_score            # 코스닥 + 코스피(시장별 계수), 학습 ~2020 / 검증 2022~
python -X utf8 -m dintel.risk_score kosdaq

질문: "이 회사가 앞으로 12개월 안에 관리종목·상장적격성 실질심사·감사의견 비적정·상장폐지·불성실공시
       같은 중대 위험 공시를 낼 확률은?" - 매수/매도 의견이 아니라 위험 통계(운용사 리스크·컴플라이언스,
       주식담보대출·메자닌 심사용).
설계
- 단위: 기업 x 월말 시점 t. 피처는 t까지 접수된 공시(원공시만)와 t의 가격 정보만 쓴다(PIT).
- 피처: 직전 12개월 유형별 공시 건수(자금조달, 리픽싱, 전환청구, 최대주주변경, 조회공시, 거래정지, 채무보증·대여,
  소송, 무상증자·권리락, 대표이사변경 ...), 자금조달 원문 조건(투자조합·개인 배정, 리픽싱 조항, 무이자, 할인),
  가격(시총, 250일 수익률, 60일 변동성).
- 목표: (t, t+365일]에 중대 위험 공시 첫 발생. 직전 12개월에 이미 위험 공시가 있는 기업-시점은 제외.
- 학습: t <= 2020-12 (목표 창이 2021-12에 끝남) / 검증: t >= 2022-01 (창 겹침 없음) / t <= 마지막-12개월.
- 모델: 로지스틱(표준화, L2) - 설명 가능한 계수. 비교: 가격만 / 공시만 / 둘 다, 그리고 단순 규칙(조달 건수).
- 한계: 패널·공시 수집이 현재 상장사 기준이라 이미 상장폐지된 기업이 빠져 있다(위험률 과소, 생존편향).
  dintel은 운영 매매 엔진(quant/alpha3) 점수를 쓰지 않는다 - 원천 데이터(패널 가격, DART 공시)만 공유.
출력: data/dintel/RISK_SCORE_SUMMARY.txt, risk_model_<market>.json, risk_watch_<market>.csv(최신 시점 점수)
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dintel import etypes as T  # noqa: E402

DD = os.path.join(ROOT, "data", "dintel")
PANELS = {"kosdaq": os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel_kosdaq_full.parquet"),
          "kospi": os.path.join(ROOT, "data", "quant", "panels", "daily_pit_panel_kospi_full.parquet")}
EVENTS = {"kosdaq": ["events_kosdaq.csv", "events_I_kosdaq.csv"],
          "kospi": ["events_kospi_full.csv", "events_I_kospi_full.csv"]}
OUT = os.path.join(DD, "RISK_SCORE_SUMMARY.txt")

RISK_RE = r"관리종목|상장적격성|감사의견|의견거절|상장폐지|불성실공시"
RISK_EXCL = r"해제|해당사유해소|취소"
SEVERE_RE = r"관리종목|상장적격성|감사의견|의견거절|상장폐지"     # 불성실공시 제외한 심각 위험(보조 목표)
# 피처 그룹: 유형 이름(dintel.etypes.etype 결과)에 대한 정규식. 위험 공시 자체(RISK_RE)는 피처에서 제외.
GROUPS = {
    "fin": r"^(유상증자결정|전환사채권발행결정|신주인수권부사채권발행결정|교환사채권발행결정)$",
    "refix": r"^(전환가액의조정|신주인수권행사가액의조정|교환가액의조정)$",
    "conv": r"^(전환청구권행사|신주인수권행사|교환청구권행사)$",
    "early_redeem": r"사채취득$",
    "owner": r"^최대주주변경",
    "pledge": r"담보제공",
    "ceo": r"^대표이사변경$",
    "inquiry": r"^조회공시요구",
    "halt": r"^주권매매거래정지$",
    "guarantee": r"^(타인에대한채무보증결정|금전대여결정|단기차입금증가결정)$",
    "lawsuit": r"^소송등의",
    "bonus": r"^(무상증자결정|권리락)$",
    "capred": r"^감자결정$",
    "acq": r"^(타법인주식및출자증권취득결정|타법인주식및출자증권양수결정|유형자산양수결정)$",
    "pl30": r"^매출액또는손익구조30%이상변",
    "deriv_loss": r"^파생상품거래손실발생$",
    "biz_change": r"^(상호변경안내|본점소재지변경|기타경영사항)$",
}
PRICE_FEATS = ["log_mcap", "ret_250", "vol_60", "penny"]
LABELS = {"n_fin": "자금조달", "n_refix": "리픽싱", "n_conv": "전환청구", "n_early_redeem": "만기전 사채취득",
          "n_owner": "최대주주변경", "n_pledge": "주식담보", "n_ceo": "대표이사변경", "n_inquiry": "조회공시",
          "n_halt": "거래정지", "n_guarantee": "채무보증·대여·차입", "n_lawsuit": "소송", "n_bonus": "무상증자·권리락",
          "n_capred": "감자", "n_acq": "타법인·자산 취득", "n_pl30": "손익구조 30% 변동", "n_deriv_loss": "파생손실",
          "n_biz_change": "상호·본점 변경", "n_risk_old": "과거(13~36개월) 위험공시", "n_fin_90": "최근 90일 조달",
          "n_all": "전체 공시", "x_fund": "투자조합 배정", "x_person": "개인 배정", "x_refix": "리픽싱 조항",
          "x_zero_coupon": "무이자 사채", "x_deep_disc": "10%+ 할인 발행"}


def log(s=""):
    print(s, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def load_events(market):
    e = pd.concat([pd.read_csv(os.path.join(DD, f), dtype=str, usecols=["corp_code", "rcept_dt", "rcept_no", "report_nm"])
                   for f in EVENTS[market] if os.path.exists(os.path.join(DD, f))]).drop_duplicates("rcept_no")
    e = e[~e["report_nm"].map(T.is_followup)]
    e["corp_code"] = e["corp_code"].str.zfill(8)
    e["dt"] = pd.to_datetime(e["rcept_dt"], format="%Y%m%d")
    e["t"] = e["report_nm"].map(T.etype).fillna("")
    nm = e["report_nm"].str.replace(" ", "")
    e["risk"] = nm.str.contains(RISK_RE) & ~nm.str.contains(RISK_EXCL)
    return e


def load_financing(market):
    p = os.path.join(DD, "financing_parsed.csv")
    if not os.path.exists(p):
        return None
    f = pd.read_csv(p, dtype={"corp_code": str, "rcept_dt": str})
    f = f[f["market"].astype(str).str.lower().str.startswith(market[:5])] if "market" in f else f
    f["corp_code"] = f["corp_code"].str.zfill(8)
    f["dt"] = pd.to_datetime(f["rcept_dt"], format="%Y%m%d", errors="coerce")
    tb = lambda c: f[c].astype(str).str.lower().isin(["true", "1", "1.0"])
    f["x_fund"] = tb("alloc_fund") if "alloc_fund" in f else False
    f["x_person"] = tb("alloc_person") if "alloc_person" in f else False
    f["x_refix"] = tb("refix") if "refix" in f else False
    f["x_zero_coupon"] = pd.to_numeric(f.get("coupon"), errors="coerce").fillna(1) <= 0
    f["x_deep_disc"] = pd.to_numeric(f.get("discount"), errors="coerce") <= -0.10
    return f[["corp_code", "dt", "x_fund", "x_person", "x_refix", "x_zero_coupon", "x_deep_disc"]].dropna(subset=["dt"])


def month_panel(market):
    """월말 시점별 (기업, 가격 피처). 상장(패널에 존재) 기업만."""
    p = pd.read_parquet(PANELS[market], columns=["date", "stock_code", "corp_code", "corp_name", "close", "market_cap"])
    p["date"] = pd.to_datetime(p["date"])
    p = p.dropna(subset=["corp_code"]).sort_values(["stock_code", "date"])
    p["corp_code"] = p["corp_code"].astype(str).str.zfill(8)
    g = p.groupby("stock_code")["close"]
    p["ret_250"] = g.pct_change(250, fill_method=None)
    p["vol_60"] = g.pct_change(fill_method=None).groupby(p["stock_code"]).rolling(60, min_periods=40).std() \
        .reset_index(level=0, drop=True)
    p["log_mcap"] = np.log(p["market_cap"].clip(lower=1))
    p["penny"] = (p["close"] < 1000).astype(float)
    p["ym"] = p["date"].dt.to_period("M")
    m = p.groupby(["stock_code", "ym"]).tail(1)            # 각 달의 마지막 거래일
    m = m.rename(columns={"date": "asof"})
    return m[["asof", "ym", "stock_code", "corp_code", "corp_name"] + PRICE_FEATS]


def count_window(ev_dt_by_corp, corps, asof, days, lo_open=True):
    """corps[i] 기업이 (asof-days, asof] 안에 가진 이벤트 수(lo_open)."""
    out = np.zeros(len(corps))
    for i, (c, t) in enumerate(zip(corps, asof)):
        arr = ev_dt_by_corp.get(c)
        if arr is None:
            continue
        hi = np.searchsorted(arr, t, side="right")
        lo = np.searchsorted(arr, t - np.timedelta64(days, "D"), side="right")
        out[i] = hi - lo
    return out


def first_after(ev_dt_by_corp, corps, asof, days):
    out = np.zeros(len(corps), dtype=bool)
    for i, (c, t) in enumerate(zip(corps, asof)):
        arr = ev_dt_by_corp.get(c)
        if arr is None:
            continue
        lo = np.searchsorted(arr, t, side="right")
        hi = np.searchsorted(arr, t + np.timedelta64(days, "D"), side="right")
        out[i] = hi > lo
    return out


def _index(df, mask):
    d = df[mask].groupby("corp_code")["dt"].apply(lambda s: np.sort(s.to_numpy("datetime64[ns]")))
    return d.to_dict()


def build(market):
    e = load_events(market)
    m = month_panel(market)
    corps, asof = m["corp_code"].to_numpy(), m["asof"].to_numpy("datetime64[ns]")
    for g, rx in GROUPS.items():
        m[f"n_{g}"] = count_window(_index(e, e["t"].str.contains(rx) & ~e["risk"]), corps, asof, 365)
    m["n_all"] = count_window(_index(e, ~e["risk"]), corps, asof, 365)
    m["n_fin_90"] = count_window(_index(e, e["t"].str.contains(GROUPS["fin"])), corps, asof, 90)
    f = load_financing(market)
    if f is not None:
        for c in ["x_fund", "x_person", "x_refix", "x_zero_coupon", "x_deep_disc"]:
            m[c] = count_window(_index(f, f[c]), corps, asof, 365)
    risk_idx = _index(e, e["risk"])
    m["risk_prev"] = count_window(risk_idx, corps, asof, 365) > 0
    # 13~36개월 전 위험 공시 이력(재발 경향) - t 이전 정보라 PIT
    m["n_risk_old"] = count_window(risk_idx, corps, asof, 1095) - count_window(risk_idx, corps, asof, 365)
    m["y"] = first_after(risk_idx, corps, asof, 365)
    sev = e["risk"] & e["report_nm"].str.replace(" ", "").str.contains(SEVERE_RE)
    m["y_severe"] = first_after(_index(e, sev), corps, asof, 365)
    last_ev = e["dt"].max()
    m["y_known"] = m["asof"] + pd.Timedelta(days=365) <= last_ev
    return m, last_ev


def delisted_panel(m, last_ev, market="kosdaq"):
    """2026-10-09 생존편향 보정: dintel/survivorship.py가 모은 퇴출 코스닥 기업의 기업-월(같은 공시 피처, 가격·원문조건 피처는 NaN).
    파일이 없으면 None. 상장 기간 = 첫 공시 월 ~ 마지막 거래소공시 월(근사)."""
    from dintel import survivorship as SV
    SV.MARKET, SV.MK = market, f"{market}_delisted"
    files = [f"events_{SV.MK}.csv", f"events_I_{SV.MK}.csv"]
    if not all(os.path.exists(os.path.join(DD, f)) for f in files):
        return None
    info = SV.targets()
    e = SV._events(files)
    span = e.groupby("corp_code")["dt"].agg(["min", "max"])
    rows = []
    for cc, r in span.iterrows():
        if cc not in info.index:
            continue
        hi = min(r["max"], pd.Timestamp(info.loc[cc, "last_dt"]))
        for d in pd.date_range(max(r["min"], pd.Timestamp("2015-01-31")), hi, freq="ME"):
            rows.append((d, cc))
    md = pd.DataFrame(rows, columns=["asof", "corp_code"])
    corps, asof = md["corp_code"].to_numpy(), md["asof"].to_numpy("datetime64[ns]")
    for g, rx in GROUPS.items():
        md[f"n_{g}"] = count_window(_index(e, e["t"].str.contains(rx) & ~e["risk"]), corps, asof, 365)
    md["n_all"] = count_window(_index(e, ~e["risk"]), corps, asof, 365)
    md["n_fin_90"] = count_window(_index(e, e["t"].str.contains(GROUPS["fin"])), corps, asof, 90)
    for c in [c for c in m.columns if c.startswith("x_")] + PRICE_FEATS:
        md[c] = np.nan
    ri = _index(e, e["risk"])
    md["risk_prev"] = count_window(ri, corps, asof, 365) > 0
    md["n_risk_old"] = count_window(ri, corps, asof, 1095) - count_window(ri, corps, asof, 365)
    md["y"] = first_after(ri, corps, asof, 365)
    sev = e["risk"] & e["report_nm"].str.replace(" ", "").str.contains(SEVERE_RE)
    md["y_severe"] = first_after(_index(e, sev), corps, asof, 365)
    md["y_known"] = md["asof"] + pd.Timedelta(days=365) <= last_ev
    md["stock_code"] = md["corp_code"].map(info["stock_code"])
    md["corp_name"] = md["corp_code"].map(info["corp_name"])
    md["ym"] = md["asof"].dt.to_period("M")
    md["delisted"] = True
    return md[[c for c in m.columns if c in md.columns] + ["delisted"]]


def _xy(m, feats):
    X = m[feats].astype(float).copy()
    for c in feats:
        if c.startswith(("n_", "x_")):
            X[c] = np.log1p(X[c])
    return X


def auc(y, s):
    from sklearn.metrics import roc_auc_score
    return roc_auc_score(y, s) if 0 < y.sum() < len(y) else np.nan


def evaluate(market, m, counts_only=False):
    """counts_only=True(퇴출 기업 포함 평가): 퇴출 기업에 없는 가격·원문조건 피처를 빼고 공시 건수(n_*)만 쓴다.
    결측을 채워 넣으면 '값이 비었다 = 퇴출 기업'이 새어 들어간다(2026-10-09 GBM AUC 0.738 착시로 확인)."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    d = m[~m["risk_prev"] & m["y_known"]].copy()
    tr = d[d["asof"] <= "2020-12-31"]
    te = d[d["asof"] >= "2022-01-01"]
    disc = [c for c in d.columns if c.startswith(("n_",) if counts_only else ("n_", "x_"))]
    sets = {"disclosure only": disc} if counts_only else \
        {"price only": PRICE_FEATS, "disclosure only": disc, "price + disclosure": PRICE_FEATS + disc}
    log(f"\n## {market}: 기업-월 {len(d):,} (학습 {len(tr):,}, 검증 {len(te):,}) | 기준 위험률 학습 {tr['y'].mean():.1%} "
        f"/ 검증 {te['y'].mean():.1%} | 기업 {d['corp_code'].nunique():,}")
    rule = te["n_fin"]
    log(f"  단순 규칙(직전 12개월 조달 건수)  검증 AUC {auc(te['y'], rule):.3f}")
    models = {}
    for name, feats in sets.items():
        pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
        pipe.fit(_xy(tr, feats), tr["y"])
        s = pipe.predict_proba(_xy(te, feats))[:, 1]
        k = max(1, int(len(te) * 0.10))
        top = np.argsort(-s)[:k]
        hit = te["y"].to_numpy()[top].mean()
        yrs = " ".join(f"{y}:{auc(te['y'][te['asof'].dt.year == y], s[te['asof'].dt.year.to_numpy() == y]):.2f}"
                       for y in sorted(te["asof"].dt.year.unique()))
        log(f"  {name:20s} 검증 AUC {auc(te['y'], s):.3f} | 상위 10% 적중 {hit:.1%} (기준 {te['y'].mean():.1%}, "
            f"{hit / te['y'].mean():.1f}배) | 연도별 AUC {yrs}")
        models[name] = (pipe, feats, s)
    from sklearn.ensemble import HistGradientBoostingClassifier
    feats_all = disc if counts_only else PRICE_FEATS + disc
    gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=300, l2_regularization=1.0,
                                        min_samples_leaf=200, random_state=0)
    gb.fit(tr[feats_all], tr["y"])
    sg = gb.predict_proba(te[feats_all])[:, 1]
    k = max(1, int(len(te) * 0.10))
    hit_g = te["y"].to_numpy()[np.argsort(-sg)[:k]].mean()
    log(f"  GBM(깊이3) {'공시 건수' if counts_only else '가격+공시'}       검증 AUC {auc(te['y'], sg):.3f} | 상위 10% 적중 {hit_g:.1%} "
        f"({hit_g / te['y'].mean():.1f}배)")
    # 심각 위험(불성실공시 제외) 목표 - 같은 공시 피처
    pipe_s = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
    pipe_s.fit(_xy(tr, disc), tr["y_severe"])
    ss = pipe_s.predict_proba(_xy(te, disc))[:, 1]
    hit_s = te["y_severe"].to_numpy()[np.argsort(-ss)[:k]].mean()
    log(f"  [심각 위험만: 관리·적격성·감사·상폐] 공시 로지스틱 검증 AUC {auc(te['y_severe'], ss):.3f} | 상위 10% 적중 "
        f"{hit_s:.1%} (기준 {te['y_severe'].mean():.1%}, {hit_s / max(te['y_severe'].mean(), 1e-9):.1f}배)")
    best = "disclosure only" if counts_only else \
        max(("disclosure only", "price + disclosure"), key=lambda n: auc(te["y"], models[n][2]))
    log(f"  운영 모델 선택(검증 AUC 기준): {best}")
    pipe, feats, s = models[best]
    models["best"] = models[best]
    te = te.assign(score=s)
    te["dec"] = pd.qcut(te["score"].rank(method="first"), 10, labels=False) + 1
    cal = te.groupby("dec").agg(n=("y", "size"), pred=("score", "mean"), real=("y", "mean"))
    log("  검증 10분위(10=가장 위험): " + " | ".join(f"{i}:{r.real:.1%}" for i, r in cal.iterrows()))
    cap = te.loc[te["dec"] == 10, "y"].sum() / max(te["y"].sum(), 1)
    log(f"  상위 10% 경고 목록이 실제 위험 발생 기업-월의 {cap:.0%}를 포착")
    k = max(1, int(len(te) * 0.10))
    metrics = {"model": best, "auc": float(auc(te["y"], s)), "base_rate": float(te["y"].mean()),
               "top10_rate": float(te["y"].to_numpy()[np.argsort(-s)[:k]].mean()), "capture_top10": float(cap),
               "auc_price_only": float(auc(te["y"], models["price only"][2])) if "price only" in models else None,
               "deciles": [float(v) for v in cal["real"].tolist()],
               "auc_by_year": {int(y): float(auc(te["y"][te["asof"].dt.year == y], s[te["asof"].dt.year.to_numpy() == y]))
                               for y in sorted(te["asof"].dt.year.unique())},
               "train": "~2020-12", "test": f"2022-01~{te['asof'].max():%Y-%m}", "n_test": int(len(te))}
    lr = pipe.named_steps["logisticregression"]
    coef = pd.Series(lr.coef_[0], index=feats).sort_values(ascending=False)
    log("  계수(표준화, +는 위험 증가) 상위: " + ", ".join(f"{k} {v:+.2f}" for k, v in coef.head(8).items()))
    log("  계수 하위: " + ", ".join(f"{k} {v:+.2f}" for k, v in coef.tail(4).items()))
    return models, coef, metrics


def main():
    markets = [a for a in sys.argv[1:] if a in PANELS] or ["kosdaq", "kospi"]
    log(f"\n##### 재무위험 조기경보 점수 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 목표: 다음 12개월 중대 위험 공시 "
        "| 학습 t<=2020-12 / 검증 t>=2022-01 | 퇴출 기업 포함 재평가·학습(생존편향 보정, 코스닥 10/09·코스피 10/10)")
    for market in markets:
        m, last_ev = build(market)
        models, coef, metrics = evaluate(market, m)
        metrics_del, train_m = None, m
        md = delisted_panel(m, last_ev, market)       # 2026-10-10 코스피도(퇴출 198곳)
        if md is not None and len(md):
            # 2026-10-09 생존편향 보정: 퇴출 코스닥 기업을 넣어 다시 평가하고, 운영 모델은 이 데이터로 학습한다.
            # 위 검증(현재 상장사)은 기존 수치와의 연속성을 위해 그대로 남기고 validation_delisted로 따로 기록.
            log(f"  -- 퇴출 {market} 기업 {md['corp_code'].nunique():,}곳, 기업-월 {len(md):,} 포함 재평가 (dintel/survivorship.py) --")
            m_all = pd.concat([m.assign(delisted=False), md], ignore_index=True)
            models, coef, metrics_del = evaluate(market, m_all, counts_only=True)
            train_m = m_all
        # 최종 모델: 정답이 확정된 전 구간으로 다시 학습 -> 최신 시점 점수(운영용)
        pipe, feats, _ = models["best"]
        d = train_m[~train_m["risk_prev"] & train_m["y_known"]]
        pipe.fit(_xy(d, feats), d["y"])
        cur = m[m["ym"] == m["ym"].max()].copy()          # 2026-10-09 최신 달 종목별 마지막 시점(마지막 날짜가 일부 종목만 있어도)
        cur = cur[~cur["risk_prev"]]
        cur["risk_12m"] = pipe.predict_proba(_xy(cur, feats))[:, 1]
        cur["pctile"] = cur["risk_12m"].rank(pct=True)
        top = [c for c in coef.index if coef[c] > 0 and c.startswith(("n_", "x_"))][:8]
        cur["drivers"] = cur.apply(lambda r: ", ".join(f"{LABELS.get(c, c)} {int(r[c])}" for c in top if r[c] > 0), axis=1)
        cur = cur.sort_values("risk_12m", ascending=False)
        cur[["asof", "stock_code", "corp_name", "risk_12m", "pctile", "drivers"] + feats].to_csv(
            os.path.join(DD, f"risk_watch_{market}.csv"), index=False, encoding="utf-8-sig")
        with open(os.path.join(DD, f"risk_model_{market}.json"), "w", encoding="utf-8") as fh:
            json.dump({"asof": str(cur["asof"].max().date()), "features": feats, "coef": coef.round(4).to_dict(),
                       "base_rate_all": float(d["y"].mean()), "n": int(len(d)), "validation": metrics,
                       "validation_delisted": metrics_del, "trained_with_delisted": metrics_del is not None,
                       "labels": {c: LABELS.get(c, c) for c in feats}}, fh, ensure_ascii=False, indent=1)
        log(f"  최신 시점 {cur['asof'].max():%Y-%m-%d}: {len(cur):,}개 기업 점수 -> risk_watch_{market}.csv "
            f"(상위 10% 평균 추정 {cur['risk_12m'].head(max(1, len(cur) // 10)).mean():.1%})")


if __name__ == "__main__":
    main()

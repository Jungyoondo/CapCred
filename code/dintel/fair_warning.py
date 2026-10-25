"""신용캐드(소상공인 공정신용) x dintel(공시 조기경보) 결합 검증 - 실제 정답으로 (2026-10-08).

python -X utf8 -m dintel.fair_warning            # 코스닥(기본) - 상장 소형사를 '정답 있는 실험장'으로
python -X utf8 -m dintel.fair_warning kospi

배경
- 신용캐드(Credit CAED): 재무만 보는 전통 평가는 (1) 규모가 작다는 이유로 위험을 과대평가하고 (2) 업종 전체의
  경기 위축을 개별 기업 탓으로 돌린다 -> 업종 충격을 복원한 '공정' 점수. 한계(스스로 밝힘): 합성 데이터로만 검증,
  위축 업종 안에서 우량/부실을 가리지 못함("개별 기업 신호가 추가로 필요").
- dintel: 실제 정답(다음 12개월 중대 위험 공시)과 표본외 검증, 기업 단위 공시 연쇄 신호를 가짐.
- 여기서는 코스닥 상장 소형사를 실험장으로 신용캐드의 두 가설과 한계를 실제 정답으로 시험한다
  (소상공인 자체는 아님 - 방법론 실증. 결과 해석에 이 차이를 명시한다).

모델(로지스틱, 학습 2020-04~2022-12 / 검증 2024-01~ - PIT 재무가 2020년부터라 risk_score와 다른 분할, 목표·제외 규칙은 같음)
  T  전통(재무): 매출 규모, 현금/자산, 자기자본비율, 유동비율, 이자보상배율, 자산회전율, 매출증가율, 영업이익률, 부채비율
  F  공정(업종 조정): T의 성장·수익 지표를 '업종 중앙값 대비'로 바꾸고 업종 충격(업종 매출증가율·1년 수익률 중앙값)을 별도 입력
  F+D 공정 + 공시 연쇄(dintel 기업 단위 신호)
  D  공시만(참고)
지표: 검증 AUC, 상위 10% 실제 위험률 / 공정성: 점수와 규모의 순위상관(규모 의존도), 매출 하위 20% 기업의
      오경보율(위험 없는데 상위 10% 경고) / 신용캐드 한계: 위축 업종(업종 매출증가율 중앙값<0) 안의 AUC.
출력: data/dintel/FAIR_WARNING_SUMMARY.txt
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dintel import risk_score as RS  # noqa: E402

OUT = os.path.join(RS.DD, "FAIR_WARNING_SUMMARY.txt")
FIN = ["revenue", "cash_and_equivalents", "total_assets", "total_equity", "current_ratio", "interest_coverage_ratio",
       "asset_turnover", "revenue_growth", "operating_margin", "debt_ratio", "industry_code"]


def log(s=""):
    print(s, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def feature_cache(market):
    """quant 피처 캐시(원천 데이터: PIT 재무 + 업종 코드) 경로 - 점수가 아니라 데이터만 읽는다."""
    import dataclasses
    from quant import config as C
    from quant import lab_common as LC
    if market == "kosdaq":
        cfg = dataclasses.replace(C.DEFAULT, fundamental_panel=os.path.join(
            ROOT, "data", "quant", "panels", "fundamentals_kosdaq_full_2016-2025.csv"))
    else:
        cfg = dataclasses.replace(C.DEFAULT, fundamental_panel=os.path.join(
            ROOT, "data", "quant", "panels", "fundamentals_kospi_full_2016-2025.csv"))
    path = LC.FEATURE_CACHE_DIR / f"features_{LC._feature_cache_key(cfg, True, RS.PANELS[market])}.parquet"
    if not path.exists():
        LC.load_cached_features(cfg, panel_path=RS.PANELS[market])
    return path


def add_financials(m, market):
    f = pd.read_parquet(feature_cache(market), columns=["date", "stock_code"] + FIN)
    f["date"] = pd.to_datetime(f["date"])
    f["stock_code"] = f["stock_code"].astype(str)
    f["ym"] = f["date"].dt.to_period("M")
    f = f.sort_values("date").groupby(["stock_code", "ym"]).tail(1).drop(columns="date")
    m = m.merge(f, on=["stock_code", "ym"], how="left")
    m["ind"] = m["industry_code"].astype(str).str[:2]
    m["f_size"] = np.log(m["revenue"].clip(lower=1))
    m["f_cash"] = m["cash_and_equivalents"] / m["total_assets"]
    m["f_equity"] = m["total_equity"] / m["total_assets"]
    m["f_current"] = np.log(m["current_ratio"].clip(0.01, 100))
    m["f_icr"] = np.sign(m["interest_coverage_ratio"]) * np.log1p(m["interest_coverage_ratio"].abs().clip(upper=1000))
    m["f_turn"] = m["asset_turnover"]
    m["f_growth"] = m["revenue_growth"].clip(-1, 5)
    m["f_margin"] = m["operating_margin"].clip(-5, 1)
    m["f_debt"] = np.log1p(m["debt_ratio"].clip(lower=0, upper=100))
    # 업종 충격(같은 시점 같은 업종 중앙값)과 업종 대비 상대값 - 신용캐드 ③의 '외부충격 복원'을 실데이터로
    g = m.groupby(["asof", "ind"])
    m["ind_growth"] = g["f_growth"].transform("median")
    m["ind_ret"] = g["ret_250"].transform("median")
    m["ind_n"] = g["f_growth"].transform("count")
    for c in ("f_growth", "f_margin", "f_turn", "f_cash"):
        m[c + "_rel"] = m[c] - g[c].transform("median")
    return m


T_FEATS = ["f_size", "f_cash", "f_equity", "f_current", "f_icr", "f_turn", "f_growth", "f_margin", "f_debt"]
F_FEATS = ["f_size", "f_equity", "f_current", "f_icr", "f_debt",
           "f_growth_rel", "f_margin_rel", "f_turn_rel", "f_cash_rel", "ind_growth", "ind_ret"]


def fit_score(tr, te, feats, target="y"):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    X = lambda d: RS._xy(d, feats).replace([np.inf, -np.inf], np.nan)
    pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=3000))
    pipe.fit(X(tr), tr[target])
    return pipe.predict_proba(X(te))[:, 1], pipe


def report(name, te, s):
    from scipy.stats import spearmanr
    y = te["y"].to_numpy()
    k = max(1, int(len(te) * 0.10))
    flag = np.zeros(len(te), bool)
    flag[np.argsort(-s)[:k]] = True
    small = (te["f_size"].rank(pct=True) <= 0.2).to_numpy()
    large = (te["f_size"].rank(pct=True) > 0.8).to_numpy()
    fpr = lambda mask: (flag & mask & (y == 0)).sum() / max((mask & (y == 0)).sum(), 1)
    shrink = (te["ind_growth"] < 0).to_numpy()
    rho = spearmanr(s, te["f_size"], nan_policy="omit").correlation
    a_shr = RS.auc(te["y"][shrink], s[shrink])
    a_small = RS.auc(te["y"][small], s[small])
    log(f"  {name:22s} AUC {RS.auc(te['y'], s):.3f} | 상위10% 위험률 {y[flag].mean():.1%} | 규모 의존도 rho {rho:+.2f} | "
        f"오경보율 소형 {fpr(small):.1%} / 대형 {fpr(large):.1%} | 위축 업종 안 AUC {a_shr:.3f} | 소형 20% 안 AUC {a_small:.3f}")
    return dict(auc=RS.auc(te["y"], s), rho=rho, fpr_small=fpr(small), fpr_large=fpr(large), auc_shrink=a_shr)


def main():
    market = next((a for a in sys.argv[1:] if a in RS.PANELS), "kosdaq")
    log(f"\n##### 공정 조기경보: 신용캐드 x dintel ({market}) {pd.Timestamp.now():%Y-%m-%d %H:%M} | 실제 정답 = 다음 12개월 "
        "중대 위험 공시 | 학습 2020-04~2022-12 / 검증 2024-01~ (재무 PIT가 2020년부터) | 상장사 실험장(소상공인 아님), 현재 상장사 기준")
    m, _ = RS.build(market)
    m = add_financials(m, market)
    d = m[~m["risk_prev"] & m["y_known"] & m["f_size"].notna() & (m["ind_n"] >= 5)].copy()
    # 코스닥 PIT 재무가 2020년부터만 있어 이 실험은 별도 분할: 학습 2020-04~2022-12 / 1년 공백 / 검증 2024-01~
    # (정답 창이 겹치지 않음). 네 모델 모두 같은 분할·같은 행으로 비교한다.
    d = d[d["asof"] >= "2020-04-01"]
    tr, te = d[d["asof"] <= "2022-12-31"], d[d["asof"] >= "2024-01-01"]
    disc = [c for c in d.columns if c.startswith(("n_", "x_"))]
    log(f"  표본: 학습 {len(tr):,} / 검증 {len(te):,} 기업-월 | 검증 위험률 {te['y'].mean():.1%} | "
        f"위축 업종 비중(검증) {(te['ind_growth'] < 0).mean():.0%}")
    res = {}
    for name, feats in (("T 전통(재무)", T_FEATS), ("F 공정(업종 조정)", F_FEATS),
                        ("F+D 공정+공시연쇄", F_FEATS + disc), ("D 공시만", disc)):
        s, pipe = fit_score(tr, te, feats)
        res[name] = (report(name, te, s), s, pipe, feats)
    # 신용캐드 '저평가 발굴' 재현: 전통 대비 공정 점수가 크게 낮아진(=위험 하향) 기업이 실제로 안전했나
    sT, sF = res["T 전통(재무)"][1], res["F+D 공정+공시연쇄"][1]
    rT, rF = pd.Series(sT).rank(pct=True).to_numpy(), pd.Series(sF).rank(pct=True).to_numpy()
    up = (rT - rF) >= 0.3          # 전통에선 위험 상위권, 결합 모델에선 30%p 이상 덜 위험 = '저평가 후보'
    dn = (rF - rT) >= 0.3          # 반대: 재무는 멀쩡해 보이나 공시 연쇄가 위험 = '숨은 위험'
    y = te["y"].to_numpy()
    log(f"  재평가: 전통 대비 위험 순위 30%p+ 하향(저평가 후보) {up.mean():.1%} 기업-월 -> 실제 위험률 {y[up].mean():.1%} | "
        f"상향(숨은 위험) {dn.mean():.1%} -> 실제 위험률 {y[dn].mean():.1%} | 전체 {y.mean():.1%}")
    # 정확한 '저평가 발굴' 지표: 전통 모델 상위 10%(경고) 안에서, 결합 모델이 상위 30% 밖으로 내린 기업 vs 유지한 기업
    t_flag = rT >= 0.9
    cleared, kept = t_flag & (rF < 0.7), t_flag & (rF >= 0.7)
    small = (te["f_size"].rank(pct=True) <= 0.2).to_numpy()
    log(f"  저평가 발굴: 전통 경고(상위10%) {t_flag.sum():,}건 중 결합 모델이 해제 {cleared.sum():,}건 -> 실제 위험률 "
        f"{y[cleared].mean():.1%} vs 유지 {kept.sum():,}건 {y[kept].mean():.1%} (전체 {y.mean():.1%}) | 해제 중 매출 하위 20% "
        f"비중 {small[cleared].mean():.0%}")
    f_flag = rF >= 0.9
    new_only = f_flag & (rT < 0.7)
    log(f"  숨은 위험 발굴: 결합 모델 경고 중 전통에선 상위 30% 밖이던 {new_only.sum():,}건 -> 실제 위험률 {y[new_only].mean():.1%}")
    coef = pd.Series(res["F+D 공정+공시연쇄"][2].named_steps["logisticregression"].coef_[0],
                     index=res["F+D 공정+공시연쇄"][3]).sort_values()
    lab = lambda k: RS.LABELS.get(k, k)
    log("  결합 모델 계수 위험↑: " + ", ".join(f"{lab(k)} {v:+.2f}" for k, v in coef.tail(6)[::-1].items()))
    log("  결합 모델 계수 위험↓: " + ", ".join(f"{lab(k)} {v:+.2f}" for k, v in coef.head(4).items()))


if __name__ == "__main__":
    main()

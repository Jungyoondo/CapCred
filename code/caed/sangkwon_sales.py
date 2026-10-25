"""동네 매출 흐름이 다음 해 폐업을 미리 알려 주나 - 서울 상권분석 추정매출 x 점포 개폐업, 행정동 x 업종 패널 (2026-10-20).

python -X utf8 -m caed.sangkwon_sales fetch    # 추정매출(VwsmAdstrdSelngW)·점포(VwsmAdstrdStorW) 2021Q1~ 전 분기 -> data/caed/sangkwon/
python -X utf8 -m caed.sangkwon_sales          # 검정 -> data/caed/SANGKWON_SALES.txt, sangkwon_sales.json

왜: 업종 10개 인허가 검정(caed/industry_survival.py, location_signal.py)에서 공개 데이터의 업소 단위 예측력이 낮았다(AUC 0.56~0.62).
  영업 흐름(현금흐름)이 핵심이라면, 공개된 것 중 가장 가까운 '동네 x 업종 매출'(카드 결제 기반 추정)이 폐업을 미리 알려 주는지 본다.
  제품 쪽 의미: 신용캐드 상권 점수(지금 '참고')를 '매출 흐름 경보'로 바꿀 근거가 되는지.
단위: 행정동 x 서비스업종 칸, 분기 t. 정답 = t+1~t+4 분기 폐업 점포 수 합 / t 점포 수(유사업종 포함 점포 수, SIMILR_INDUTY_STOR_CO).
피처(t 시점까지만): 매출 증감 = 최근 4분기 매출 합 / 그 전 4분기 합 - 1, 점포당 매출(로그), 점포 수(로그), 직전 4분기 폐업률, 직전 4분기 개업률,
  프랜차이즈 비중. 업종 고정효과(업종별 평균 폐업률 - 학습기에서 계산).
기간: 매출이 2021Q1부터라 증감은 2022Q4부터. 학습 t = 2022Q4~2023Q4(정답이 2024Q4까지), 검증 t = 2025Q1~2025Q2(정답 2026Q2까지).
사전 가설(2026-10-20, 결과 전 커밋):
  S1 검증 기간에 매출 증감 하위 20% 칸의 다음 1년 폐업률이 상위 20% 칸의 1.2배 이상(점포 5개 이상 칸만).
  S2 칸 단위 폐업률 예측(선형, 가중 = 점포 수)에서 매출 증감·점포당 매출을 더하면 검증 순위상관(스피어만)이 0.02 이상 오른다
     (기본 = 업종 평균 + 직전 폐업률 + 개업률 + 점포 수 + 프랜차이즈 비중).
  판정은 그대로 보고. 둘 다 성립하면 '매출 흐름 경보'를 제품 후보로, 아니면 상권 점수는 참고 유지.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "caed", "sangkwon")
TXT = os.path.join(ROOT, "data", "caed", "SANGKWON_SALES.txt")
JSN = os.path.join(ROOT, "data", "caed", "sangkwon_sales.json")
SVCS = {"VwsmAdstrdSelngW": ["ADSTRD_CD", "SVC_INDUTY_CD", "SVC_INDUTY_CD_NM", "THSMON_SELNG_AMT", "THSMON_SELNG_CO"],
        "VwsmAdstrdStorW": ["ADSTRD_CD", "SVC_INDUTY_CD", "STOR_CO", "SIMILR_INDUTY_STOR_CO", "OPBIZ_STOR_CO", "CLSBIZ_STOR_CO", "FRC_STOR_CO"]}
QUARTERS = [f"{y}{q}" for y in range(2021, 2027) for q in (1, 2, 3, 4)]
TRAIN = [q for q in QUARTERS if "20224" <= q <= "20234"]
TEST = ["20251", "20252"]


def _key():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _env  # noqa: F401
    return (os.getenv("SEOUL_API_KEY") or "").strip()


def fetch():
    import requests
    from concurrent.futures import ThreadPoolExecutor
    key = _key()
    os.makedirs(D, exist_ok=True)

    def one(svc, q):
        p = os.path.join(D, f"{svc}_{q}.csv")
        if os.path.exists(p):
            return q, "cached"
        b = requests.get(f"http://openapi.seoul.go.kr:8088/{key}/json/{svc}/1/1/{q}", timeout=30).json().get(svc, {})
        total = int(b.get("list_total_count") or 0)
        if not total:
            return q, "none"

        def page(s):
            for _ in range(3):
                try:
                    return requests.get(f"http://openapi.seoul.go.kr:8088/{key}/json/{svc}/{s}/{min(s + 999, total)}/{q}", timeout=60).json()[svc]["row"]
                except Exception:  # noqa: BLE001
                    continue
            raise RuntimeError(f"{svc} {q} page {s}")
        with ThreadPoolExecutor(4) as ex:
            rows = [r for part in ex.map(page, range(1, total + 1, 1000)) for r in part]
        pd.DataFrame(rows)[SVCS[svc]].to_csv(p, index=False, encoding="utf-8")
        return q, len(rows)
    for svc in SVCS:
        for q in QUARTERS:
            print(svc, *one(svc, q), flush=True)


def load():
    S, T = [], []
    for q in QUARTERS:
        ps, pt = os.path.join(D, f"VwsmAdstrdSelngW_{q}.csv"), os.path.join(D, f"VwsmAdstrdStorW_{q}.csv")
        if os.path.exists(ps):
            S.append(pd.read_csv(ps, dtype={"ADSTRD_CD": str}).assign(q=q))
        if os.path.exists(pt):
            T.append(pd.read_csv(pt, dtype={"ADSTRD_CD": str}).assign(q=q))
    S = pd.concat(S).groupby(["ADSTRD_CD", "SVC_INDUTY_CD", "q"])[["THSMON_SELNG_AMT"]].sum()
    T = pd.concat(T).groupby(["ADSTRD_CD", "SVC_INDUTY_CD", "q"])[["SIMILR_INDUTY_STOR_CO", "OPBIZ_STOR_CO", "CLSBIZ_STOR_CO", "FRC_STOR_CO"]].sum()
    X = T.join(S, how="left").reset_index().sort_values(["ADSTRD_CD", "SVC_INDUTY_CD", "q"])
    g = X.groupby(["ADSTRD_CD", "SVC_INDUTY_CD"])
    n = X["SIMILR_INDUTY_STOR_CO"].replace(0, np.nan)
    roll = lambda c, k, sh=0: g[c].transform(lambda s: s.shift(sh).rolling(k, min_periods=k).sum())  # noqa: E731
    X["sales_chg"] = roll("THSMON_SELNG_AMT", 4) / roll("THSMON_SELNG_AMT", 4, 4) - 1
    X["log_sps"] = np.log((roll("THSMON_SELNG_AMT", 4) / n).where(lambda v: v > 0))
    X["log_n"] = np.log(n)
    X["close_prev"] = roll("CLSBIZ_STOR_CO", 4) / n
    X["open_prev"] = roll("OPBIZ_STOR_CO", 4) / n
    X["frc"] = X["FRC_STOR_CO"] / n
    X["y"] = g["CLSBIZ_STOR_CO"].transform(lambda s: s[::-1].rolling(4, min_periods=4).sum()[::-1].shift(-1)) / n
    return X


def main():
    from scipy.stats import spearmanr
    from sklearn.linear_model import LinearRegression
    X = load()
    X = X[(X["SIMILR_INDUTY_STOR_CO"] >= 5)].dropna(subset=["y", "sales_chg", "log_sps", "close_prev", "open_prev", "frc"])
    X = X[np.isfinite(X["sales_chg"]) & (X["sales_chg"].abs() < 5)]
    tr, te = X[X["q"].isin(TRAIN)].copy(), X[X["q"].isin(TEST)].copy()
    ind_mean = tr.groupby("SVC_INDUTY_CD")["y"].mean()
    for d_ in (tr, te):
        d_["ind"] = d_["SVC_INDUTY_CD"].map(ind_mean).fillna(tr["y"].mean())
    base = ["ind", "close_prev", "open_prev", "log_n", "frc"]
    full = base + ["sales_chg", "log_sps"]
    out = {}
    for tag, f in (("기본", base), ("+매출", full)):
        m = LinearRegression().fit(tr[f], tr["y"], sample_weight=tr["SIMILR_INDUTY_STOR_CO"])
        te[f"p_{tag}"] = m.predict(te[f])
        out[tag] = {"spearman": float(spearmanr(te[f"p_{tag}"], te["y"]).correlation), "coef": dict(zip(f, np.round(m.coef_, 4).tolist()))}
    te["qq"] = te.groupby("q")["sales_chg"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
    w = lambda d_: float(d_["y"].mul(d_["SIMILR_INDUTY_STOR_CO"]).sum() / d_["SIMILR_INDUTY_STOR_CO"].sum())  # noqa: E731
    by_q = {int(k): w(v) for k, v in te.groupby("qq")}
    s1 = by_q[0] / by_q[4] if by_q[4] > 0 else float("nan")
    s2 = out["+매출"]["spearman"] - out["기본"]["spearman"]
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L = [f"\n##### 동네 매출 흐름 x 다음 1년 폐업 {stamp} | 서울 상권분석 행정동 x 업종(점포 5개+) | 학습 {TRAIN[0]}~{TRAIN[-1]} {len(tr):,}칸-분기 / 검증 {','.join(TEST)} {len(te):,}",
         f"  검증 다음 1년 폐업률(점포 가중) 매출 증감 5분위(1=가장 줄어듦): " + " ".join(f"{k + 1}:{v:.1%}" for k, v in by_q.items()),
         f"  기본 스피어만 {out['기본']['spearman']:.3f} | +매출 {out['+매출']['spearman']:.3f} (차이 {s2:+.3f}) | +매출 계수 {out['+매출']['coef']}",
         f"  사전 가설: S1 하위/상위 20% 배수 {s1:.2f} (>=1.2) {'성립' if s1 >= 1.2 else '기각'} | S2 순위상관 +0.02 {'성립' if s2 >= 0.02 else '기각'} -> "
         f"{'매출 흐름 경보를 제품 후보로' if s1 >= 1.2 and s2 >= 0.02 else '상권 점수는 참고 유지 - 그대로 보고'}"]
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "by_quintile": by_q, "S1": s1, "S2": s2, "models": out, "n_train": len(tr), "n_test": len(te)},
                  fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    fetch() if "fetch" in sys.argv[1:] else main()

"""리서치 데스크 근거 검증 - '이것만 읽으면 된다'는 분류가 실제로 큰 주가 변동을 잡는가 (2026-10-06).

python -X utf8 -m dintel.desk_eval

운용역의 공시 확인 업무를 대신하려면 두 가지가 동시에 성립해야 한다.
  (1) 읽을 양이 크게 준다       (2) 그래도 큰 변동(특히 급락)은 놓치지 않는다
학습(~2021-11)에서 정한 규칙을 검증 기간(2022-01~)에 그대로 적용해 측정한다(사후 맞춤 금지).
  T1 위험: 위험 키워드(관리종목·거래정지·감사의견 등) 또는 희석성 발행(유상증자·CB·BW·EB)
  T2 주의: 학습 기간 유형별 반응이 유의하고 경제적 크기가 큰 유형(oos_stats.json의 flag)
  T3/4 일상: 나머지
큰 변동 = 공시 후 20거래일 시장 대비 초과수익(d20) <= -15% (급락) 또는 >= +15% (급등)
지표: 읽을 비율, 급락 포착률(recall), 급락 확률 배율(lift = T1+T2 안의 급락 비율 / 전체 급락 비율),
      30종목 포트폴리오 기준 하루 평균 공시 수와 읽을 공시 수
결과: data/dintel/DESK_EVAL.txt
"""
import json
import os

import numpy as np
import pandas as pd

from dintel import feed as FD
from dintel.etypes import etype

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "data", "dintel")
OUT = os.path.join(D, "DESK_EVAL.txt")
TEST_START = pd.Timestamp("2022-01-01")
BIG = 0.15
DIL = ("유상증자결정", "전환사채권발행결정", "신주인수권부사채권발행결정", "교환사채권발행결정")


def load(mk):
    fr = []
    for f in (f"event_reactions_{mk}.csv", f"event_reactions_I_{mk}.csv"):
        p = os.path.join(D, f)
        if os.path.exists(p):
            fr.append(pd.read_csv(p, dtype={"corp_code": str, "rcept_no": str, "stock_code": str}))
    ev = pd.concat(fr, ignore_index=True).drop_duplicates("rcept_no")
    ev["rdate"] = pd.to_datetime(ev["rdate"])
    return ev[(ev["rdate"] >= TEST_START) & ev["d20"].notna()].copy()


def tiers(ev, flags):
    nm = ev["report_nm"].astype(str)
    risk = nm.map(lambda s: FD._risk(s)[1])
    et = ev["etype"].where(ev["etype"].notna(), nm.map(etype))
    amend = nm.str.startswith("[")
    dil = et.isin(DIL) & ~amend
    flag = et.map(lambda e: bool(flags.get(e, {}).get("flag"))) & ~amend
    return np.where(risk | dil, 1, np.where(flag, 2, 3))


def main():
    oos = json.load(open(os.path.join(D, "oos_stats.json"), encoding="utf-8"))["oos"]["types"]
    lines = [f"##### DESK EVAL (rules from <=2021-11, measured {TEST_START:%Y-%m}~) {pd.Timestamp.now():%m-%d %H:%M}"]
    for mk, key in (("kosdaq", "kosdaq"), ("kospi_full", "kospi_full")):
        ev = load(mk)
        ev["tier"] = tiers(ev, oos.get(key, {}))
        read = ev["tier"] <= 2
        down, up = ev["d20"] <= -BIG, ev["d20"] >= BIG
        ndays = ev["rdate"].nunique()
        nstocks = ev["stock_code"].nunique()
        per30 = len(ev) / ndays / nstocks * 30
        lines.append(f"{mk}: filings {len(ev):,} on {ndays} days, {nstocks} stocks | per 30-stock book/day: "
                     f"{per30:.1f} filings, read {per30 * read.mean():.2f}")
        lines.append(f"  read share {read.mean():.1%} (T1 {np.mean(ev['tier'] == 1):.1%}, T2 {np.mean(ev['tier'] == 2):.1%})")
        for nm_, big in (("down<=-15%", down), ("up>=+15%", up)):
            base = big.mean()
            rec = big[read].sum() / max(big.sum(), 1)
            prec = big[read].mean()
            lines.append(f"  {nm_}: base rate {base:.1%} | caught in read set {rec:.1%} | rate in read set "
                         f"{prec:.1%} (lift x{prec / base:.1f}) | T1 rate {big[ev['tier'] == 1].mean():.1%}")
        # 큰 급락의 몇 %가 '공시 없는 날'이 아니라 공시와 함께 왔는지는 이 데이터로 알 수 없음(공시일 기준 표본)
        top = (ev[read & down].groupby("etype").size().sort_values(ascending=False).head(6))
        lines.append("  top types among caught crashes: " + ", ".join(f"{k} {v}" for k, v in top.items()))
    lines.append("note: d20 = excess vs equal-weight market, from the trading day after filing. "
                 "Sample = filing days only (crashes with no filing are not counted).")
    txt = "\n".join(lines)
    print(txt)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(txt + "\n")


if __name__ == "__main__":
    main()

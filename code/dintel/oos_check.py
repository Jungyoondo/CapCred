"""사업 근거 검증 - (1) 과거 통계가 미래에도 맞는가(표본 외), (2) 하루 공시 중 읽을 것은 얼마나 되나.

python -X utf8 -m dintel.oos_check      -> data/dintel/OOS_SUMMARY.txt (붙여넣기용), oos_stats.json

(1) 표본 외 검증
  학습기간 2015-01 ~ 2021-11, (1개월 간격) 검증기간 2022-01 ~. 시장(코스피 전체/코스닥) x 유형별로
  학습기간 평균 20일 초과수익(시장 동일가중 대비, 다음날 시가 진입)을 구해 '방향 표시'를 정하고,
  검증기간에 그 방향이 유지됐는지 본다. 위약은 학습/검증 각 기간 같은 시장 전체 이벤트 평균으로 근사
  (기간별 기준선 차이를 제거해 '이 유형이 평균 공시보다 나은가'만 비교).
  - 순위상관: 학습 유형 효과 vs 검증 유형 효과(유형별 n>=30 둘 다)
  - 표시 유형: 학습에서 |효과|>=1%p 이고 월 군집 t>=3 -> 검증기간 같은 부호 비율, 검증 평균
  - 공급계약 매출액 대비 구간(코스닥)도 같은 방식
(2) 업무량: 최근 250거래일 상장사 원공시를 오늘의 공시와 같은 규칙(위험 키워드·희석성 / 유의+1%p / 일상)으로
  분류했을 때 하루 평균 건수와 '읽을 것' 비율. 통계는 현재 표본 전체 기준(설명용, 예측 성능 주장 아님).
"""
import json
import os
import re

import numpy as np
import pandas as pd

D = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "dintel")
SPLIT_TRAIN_END = pd.Timestamp("2021-11-30")
SPLIT_TEST_START = pd.Timestamp("2022-01-01")
MIN_N = 30


def load():
    parts = []
    for kind, files in (("B", ("event_reactions_kospi_full.csv", "event_reactions_kosdaq.csv")),
                        ("I", ("event_reactions_I_kospi_full.csv", "event_reactions_I_kosdaq.csv"))):
        for f in files:
            p = os.path.join(D, f)
            if os.path.exists(p):
                parts.append(pd.read_csv(p, usecols=["corp_code", "rcept_dt", "etype", "report_nm", "rdate", "ann2",
                                                     "d20", "month", "market"],
                                         dtype={"corp_code": str, "rcept_dt": str}).assign(kind=kind))
    ev = pd.concat(parts, ignore_index=True)
    ev["rdate"] = pd.to_datetime(ev["rdate"])
    return ev


def type_effects(g):
    """유형별 효과(기간 전체 이벤트 평균 대비) + 월 군집 t."""
    base = g["d20"].mean()
    rows = []
    for et, x in g.groupby("etype"):
        x = x.dropna(subset=["d20"])
        if len(x) < MIN_N:
            continue
        m = x.groupby("month")["d20"].mean() - base
        t = m.mean() / (m.std(ddof=1) / np.sqrt(len(m))) if len(m) > 2 and m.std() > 0 else np.nan
        rows.append({"etype": et, "n": len(x), "eff": x["d20"].mean() - base, "t": t})
    return pd.DataFrame(rows).set_index("etype") if rows else pd.DataFrame()


def oos(ev, out):
    res = {}
    for mk, g in ev.groupby("market"):
        tr = type_effects(g[g["rdate"] <= SPLIT_TRAIN_END])
        te = type_effects(g[g["rdate"] >= SPLIT_TEST_START])
        j = tr.join(te, lsuffix="_tr", rsuffix="_te", how="inner")
        rho = j["eff_tr"].corr(j["eff_te"], method="spearman")
        flag = j[(j["eff_tr"].abs() >= 0.01) & (j["t_tr"].abs() >= 3)]
        same = (np.sign(flag["eff_tr"]) == np.sign(flag["eff_te"])).mean() if len(flag) else np.nan
        neg, pos = flag[flag["eff_tr"] < 0], flag[flag["eff_tr"] > 0]
        # 검증기간 이벤트 가중 평균(유형 효과 x 검증 n)
        w = lambda d: np.average(d["eff_te"], weights=d["n_te"]) if len(d) else np.nan
        out.append(f"[{mk}] 유형 {len(j)}개(학습·검증 각 n>={MIN_N}) | 학습 vs 검증 유형효과 순위상관 {rho:+.2f}")
        out.append(f"[{mk}] 학습에서 표시된 유형 {len(flag)}개(|효과|>=1%p, 월군집 t>=3): 검증기간 같은 방향 {same:.0%} | "
                   f"'나쁨' 표시 {len(neg)}개 검증 평균 {w(neg):+.2%} (이벤트 {int(neg['n_te'].sum()) if len(neg) else 0}) | "
                   f"'좋음' 표시 {len(pos)}개 검증 평균 {w(pos):+.2%} (이벤트 {int(pos['n_te'].sum()) if len(pos) else 0})")
        top = flag.reindex(flag["eff_tr"].abs().sort_values(ascending=False).index).head(8)
        out.append(f"[{mk}]   주요 표시 유형: 학습 효과 -> 검증 효과 (검증 n)")
        for et, r in top.iterrows():
            out.append(f"      {et[:20]:<20} {r['eff_tr']:+.1%} -> {r['eff_te']:+.1%} ({int(r['n_te'])})"
                       f"{'' if np.sign(r['eff_tr']) == np.sign(r['eff_te']) else '  ✗ 방향 반전'}")
        res.setdefault("types", {})[mk] = {
            et: {"eff_tr": float(r["eff_tr"]), "eff_te": float(r["eff_te"]), "n_tr": int(r["n_tr"]),
                 "n_te": int(r["n_te"]), "t_tr": None if not np.isfinite(r["t_tr"]) else float(r["t_tr"]),
                 "flag": bool(abs(r["eff_tr"]) >= 0.01 and abs(r["t_tr"]) >= 3)}
            for et, r in j.iterrows()}
        res[mk] = {"n_types": int(len(j)), "spearman": float(rho), "n_flag": int(len(flag)),
                   "same_sign": float(same) if same == same else None, "neg_test": float(w(neg)) if len(neg) else None,
                   "pos_test": float(w(pos)) if len(pos) else None}
    return res


def contracts_oos(out):
    p = os.path.join(D, "contracts_parsed.csv")
    ev = pd.concat([pd.read_csv(os.path.join(D, f), usecols=["rcept_no", "rdate", "d20", "market"],
                                dtype={"rcept_no": str})
                    for f in ("event_reactions_I_kospi_full.csv", "event_reactions_I_kosdaq.csv")])
    k = pd.read_csv(p, dtype={"rcept_no": str}).merge(ev, on="rcept_no", how="inner")
    k = k[(k["ckind"] == "체결") & k["ratio"].notna()]
    k["rdate"] = pd.to_datetime(k["rdate"])
    bins = [0, 5, 10, 20, 50, 1e9]
    labs = ["<5%", "5~10%", "10~20%", "20~50%", "50%+"]
    k["b"] = pd.cut(k["ratio"], bins, labels=labs, right=False)
    res = {}
    for mk, g in k.groupby("market"):
        line = []
        for per, x in (("학습", g[g["rdate"] <= SPLIT_TRAIN_END]), ("검증", g[g["rdate"] >= SPLIT_TEST_START])):
            base = x["d20"].mean()
            mm = x.groupby("b", observed=False)["d20"].agg(["mean", "count"])
            line.append(f"{per} " + " ".join(f"{b} {m - base:+.1%}({int(c)})" for b, (m, c) in mm.iterrows()))
            res.setdefault(mk, {})[per] = {b: float(m - base) for b, (m, c) in mm.iterrows()}
        out.append(f"[{mk}] 공급계약 구간별 20일(같은 기간 계약 평균 대비): " + " || ".join(line))
    return res


RISK = re.compile("관리종목|상장폐지|상장적격성|거래정지|불성실공시|감사의견|의견거절|횡령|배임|회생절차|파산|부도|투자주의환기|자본잠식|조회공시요구")
RISK_EX = re.compile("해제|정지기간변경|병합|분할|전자등록")
DILUTIVE = {"유상증자결정", "전환사채권발행결정", "신주인수권부사채권발행결정", "교환사채권발행결정"}


def workload(ev, out):
    """최근 250거래일, 현재 통계(event_stats*.json) 기준 4단계 분류의 하루 평균."""
    st = {}
    for kind, f in (("B", "event_stats.json"), ("I", "event_stats_I.json")):
        p = os.path.join(D, f)
        if os.path.exists(p):
            st[kind] = json.load(open(p, encoding="utf-8"))["markets"]

    def material(kind, mk, et):
        m = st.get(kind, {}).get(mk, {})
        s, pb = m.get("types", {}).get(et), m.get("placebo", {})
        if not s:
            return None
        return any(s.get(f"{w}_sig") and abs(s[w] - pb.get(w, 0)) >= 0.01 for w in ("ann2", "d10", "d20"))
    days = np.sort(ev["rdate"].unique())[-250:]
    x = ev[ev["rdate"].isin(days)].copy()
    nm = x["report_nm"].astype(str).str.replace(" ", "")
    risk = nm.str.contains(RISK) & ~nm.str.contains(RISK_EX)
    mat = pd.Series([material(k, m, e) for k, m, e in zip(x["kind"], x["market"], x["etype"])], index=x.index)
    tier = np.where(risk | x["etype"].isin(DILUTIVE), 1, np.where(mat == True, 2, np.where(mat == False, 4, 3)))  # noqa: E712
    x["tier"] = tier
    per_day = x.groupby("rdate").size()
    share = x["tier"].value_counts(normalize=True).sort_index()
    out.append(f"최근 {len(days)}거래일 상장사 원공시(정정 제외) 하루 평균 {per_day.mean():.0f}건(중앙 {per_day.median():.0f}, "
               f"최대 {per_day.max()}) | 주의 {share.get(1, 0):.0%} · 유의 {share.get(2, 0):.0%} · 일반(통계 없음) "
               f"{share.get(3, 0):.0%} · 일상(접힘) {share.get(4, 0):.0%} -> 읽을 것(주의+유의) 하루 "
               f"{per_day.mean() * (share.get(1, 0) + share.get(2, 0)):.0f}건")
    return {"days": int(len(days)), "per_day_mean": float(per_day.mean()),
            "share": {int(k): float(v) for k, v in share.items()}}


def main():
    ev = load()
    out = [f"##### 사업 근거 검증 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 학습 ~{SPLIT_TRAIN_END:%Y-%m} / 검증 {SPLIT_TEST_START:%Y-%m}~ "
           f"| 효과 = 20일 초과수익 - 같은 기간 같은 시장 전체 공시 평균"]
    res = {"oos": oos(ev, out), "contracts": contracts_oos(out), "workload": workload(ev, out)}
    text = "\n".join(out)
    print(text)
    open(os.path.join(D, "OOS_SUMMARY.txt"), "w", encoding="utf-8").write(text + "\n")
    json.dump(res, open(os.path.join(D, "oos_stats.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

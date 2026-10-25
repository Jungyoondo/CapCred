"""업종 9개로 넓힌 실데이터 검증 - 서울 인허가 폐업으로 '작고 젊으면 위험한가'를 업종마다 채점 (2026-10-20).

python -X utf8 -m caed.industry_survival              # 받아 둔 업종 전부 -> data/caed/INDUSTRY_SURVIVAL.txt, industry_survival.json

왜: 헬스장(caed/gym_survival.py)에서 '업력이 짧다고 더 망하지 않는다, 큰 곳만 확실히 안전'을 봤다. 사후 발견이라
  같은 질문을 다른 업종에 그대로 던져 일반화되는지 본다. 헬스장은 가설을 만든 표본이라 판정에서 뺀다.
데이터: 서울 열린데이터광장 LOCALDATA(caed/localdata.py). 폐업 = 상태 '폐업'(폐업일). 직권말소·전출·취소는 사건 아님.
  매년 말 영업 중인 업소의 다음 12개월 폐업. 학습 t<=2019, 판정 기간 t=2021~2024.
알려진 한계(10-20 확인): 인허가 대장은 실제 폐업의 일부만 잡는다(헬스장: 대장 연 ~3% vs 서울 상권분석 스포츠클럽 10.8%).
  양도(지위승계)는 같은 관리번호로 이어져 폐업으로 안 잡힌다. -> 아래 '포착률'(대장 폐업 / 상권분석 폐업, 2023)을 업종마다 같이 적는다.
사전 가설(2026-10-20, 9개 업종 결과를 보기 전에 적고 커밋):
  I1 업력: 판정 기간에 업력 1년 미만 폐업률 <= 업력 3년 이상(3-5·5-10·10년+ 평균) 폐업률인 업종이 판정 업종의 과반(9개면 5개).
  I2 규모: 면적 5분위 중 상위 20%(Q5)의 폐업률이 가장 낮은 업종이 면적 기록 50% 이상 업종 중 과반.
  I3 과잉 경고: 면적+업력 로지스틱(학습 t<=2019)의 상위 10% 경고 중 Q1(가장 작은 20%) 비중 / 실제 폐업 중 Q1 비중 >= 1.5인 업종이
     면적 기록 50% 이상 업종 중 과반.
  판정은 그대로 보고(기각이어도). 한 업종이라도 표본(업소-연)이 2,000 미만이면 그 업종은 '표본 부족'으로 빼고 분모에서도 뺀다.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import localdata as LD  # noqa: E402

OUT_DIR = os.path.join(ROOT, "data", "caed")
TXT = os.path.join(OUT_DIR, "INDUSTRY_SURVIVAL.txt")
JSN = os.path.join(OUT_DIR, "industry_survival.json")
TRAIN_END, TEST = 2019, (2021, 2024)
AGE_BINS, AGE_LAB = [0, 1, 3, 5, 10, 80], ["<1년", "1-3년", "3-5년", "5-10년", "10년+"]
JUDGE = [c for c in LD.INDUSTRIES if c != "104201"]           # 헬스장은 가설을 만든 표본 - 판정 제외
# 서울 상권분석(점포-행정동) 서비스 업종 - 포착률 비교용(대응이 분명한 것만)
SANGKWON = {"104201": ["CS200024"], "051801": ["CS200028"], "062001": ["CS200031"], "010102": ["CS200006"], "103201": ["CS200016"],
            "072405": ["CS100010"], "072404": ["CS100001", "CS100002", "CS100003", "CS100004", "CS100007", "CS100008", "CS100009"]}


def prep(df):
    df = df.apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)   # 대장 값에 공백 패딩(pandas 3에선 문자열이 object가 아님)
    d = lambda c: (pd.to_datetime(df[c].replace("", None), format="%Y-%m-%d", errors="coerce") if c in df  # noqa: E731
                   else pd.Series(pd.NaT, index=df.index))
    g = pd.DataFrame({"open": d("APVPERMYMD"), "close": d("DCBYMD").fillna(d("APVCANCELYMD")), "state": df["DTLSTATENM"],
                      "area": pd.to_numeric(df.get("SITEAREA"), errors="coerce").where(lambda s: s > 0) if "SITEAREA" in df else np.nan})
    g["failed"] = g["state"].eq("폐업")
    g["gone"] = g["state"].isin(["폐업", "직권말소", "전출", "신고취소", "등록취소", "허가취소", "취소/말소/만료/정지/중지"])
    g.loc[g["gone"] & g["close"].isna(), "gone"] = False
    return g.dropna(subset=["open"]).reset_index(drop=True)


def panel(g):
    rows = []
    for yr in range(2014, TEST[1] + 1):
        t = pd.Timestamp(f"{yr}-12-31")
        alive = (g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))
        s = g[alive]
        rows.append(pd.DataFrame({"t": yr, "y": (s["failed"] & (s["close"] > t) & (s["close"] <= t + pd.DateOffset(years=1))).astype(int).to_numpy(),
                                  "age": ((t - s["open"]).dt.days / 365.25).to_numpy(), "area": s["area"].to_numpy()}))
    P = pd.concat(rows, ignore_index=True)
    P["log_age"] = np.log1p(P["age"])
    P["area_na"] = P["area"].isna().astype(float)
    med = np.log(P.loc[P["t"] <= TRAIN_END, "area"]).median()
    P["log_area"] = np.log(P["area"]).fillna(0.0 if pd.isna(med) else med)   # 면적 열이 없는 업종은 상수(모델에서 영향 없음)
    return P


def over_warning(P):
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    f = ["log_area", "area_na", "log_age"]
    tr, te = P[P["t"] <= TRAIN_END], P[(P["t"] >= TEST[0]) & (P["t"] <= TEST[1])].copy()
    if tr["y"].sum() < 20 or te["y"].sum() < 20:
        return None
    mu, sd = tr[f].mean(), tr[f].std().replace(0, 1)
    m = LogisticRegression(max_iter=2000).fit((tr[f] - mu) / sd, tr["y"])
    te["s"] = m.predict_proba((te[f] - mu) / sd)[:, 1]
    te["flag"] = te.groupby("t")["s"].transform(lambda s: s >= s.quantile(0.9))
    k = te[te["area"].notna()].copy()
    if len(k) < 500:
        return {"auc": float(roc_auc_score(te["y"], te["s"])), "warn_q1": float("nan"), "fail_q1": float("nan"), "ratio": float("nan"),
                "coef": dict(zip(f, np.round(m.coef_[0], 3).tolist()))}
    k["q"] = pd.qcut(k["area"].rank(method="first"), 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])   # 같은 면적이 많아 순위로 나눔
    warn_q1 = float((k.loc[k["flag"], "q"] == "Q1").mean()) if k["flag"].any() else float("nan")
    fail_q1 = float((k.loc[k["y"] == 1, "q"] == "Q1").mean()) if (k["y"] == 1).any() else float("nan")
    return {"auc": float(roc_auc_score(te["y"], te["s"])), "warn_q1": warn_q1, "fail_q1": fail_q1,
            "ratio": warn_q1 / fail_q1 if fail_q1 > 0 else float("nan"), "coef": dict(zip(f, np.round(m.coef_[0], 3).tolist()))}


def coverage(code, g):
    """대장 폐업(2023) / 서울 상권분석 폐업 점포 수(2023 4개 분기 합) - 대장이 실제 폐업을 얼마나 잡나."""
    p = os.path.join(OUT_DIR, "sangkwon_2023.csv")
    if code not in SANGKWON or not os.path.exists(p):
        return None
    S = pd.read_csv(p, dtype={"SVC_INDUTY_CD": str})
    sk = S[S["SVC_INDUTY_CD"].isin(SANGKWON[code])]
    reg = int((g["failed"] & (g["close"].dt.year == 2023)).sum())
    return {"registry_close_2023": reg, "sangkwon_close_2023": int(sk["CLSBIZ_STOR_CO"].sum()),
            "sangkwon_stores": float(sk.groupby("STDR_YYQU_CD")["SIMILR_INDUTY_STOR_CO"].sum().mean()),
            "ratio": reg / max(int(sk["CLSBIZ_STOR_CO"].sum()), 1)}


def sangkwon_2023():
    """상권분석 2023 4개 분기를 한 번 받아 업종 코드별로 저장(포착률 계산용)."""
    p = os.path.join(OUT_DIR, "sangkwon_2023.csv")
    if os.path.exists(p):
        return
    sys.path.insert(0, os.path.join(ROOT, "caed"))
    import DATA
    out = []
    for q in ("20231", "20232", "20233", "20234"):
        df = pd.DataFrame(DATA.get_seoul_quarter_rows(q))
        for c in ("STOR_CO", "CLSBIZ_STOR_CO", "OPBIZ_STOR_CO", "SIMILR_INDUTY_STOR_CO"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        out.append(df.groupby(["STDR_YYQU_CD", "SVC_INDUTY_CD", "SVC_INDUTY_CD_NM"])[["STOR_CO", "SIMILR_INDUTY_STOR_CO", "CLSBIZ_STOR_CO", "OPBIZ_STOR_CO"]].sum().reset_index())
    pd.concat(out).to_csv(p, index=False, encoding="utf-8")


def main():
    sangkwon_2023()
    res, L = {}, []
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L.append(f"\n##### 업종별 실데이터 검증 {stamp} | 서울 인허가 폐업(상태 '폐업') | 학습 t<={TRAIN_END}, 판정 t={TEST[0]}~{TEST[1]} | 헬스장은 가설 출처라 판정 제외")
    for code, (name, _) in LD.INDUSTRIES.items():
        p = os.path.join(LD.OUT, f"{code}.csv")
        if not os.path.exists(p):
            continue
        g = prep(pd.read_csv(p, dtype=str, keep_default_na=False))
        P = panel(g)
        te = P[(P["t"] >= TEST[0]) & (P["t"] <= TEST[1])]
        age = te.groupby(pd.cut(te["age"], AGE_BINS, labels=AGE_LAB), observed=True)["y"].agg(["mean", "size"])
        k = te[te["area"].notna()]
        area_cov = float(te["area"].notna().mean())
        size = k.groupby(pd.qcut(k["area"].rank(method="first"), 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"]), observed=True)["y"].mean() if len(k) > 500 else pd.Series(dtype=float)
        ow = over_warning(P)
        cov = coverage(code, g)
        cuts = [float(x) for x in k["area"].quantile([0.2, 0.4, 0.6, 0.8]).round(1)] if len(k) > 500 else None   # 진단 화면용 면적 5분위 경계(㎡)
        r = {"name": name, "n_firms": int(len(g)), "size_cuts": cuts, "n_test": int(len(te)), "base": float(te["y"].mean()), "area_cov": area_cov,
             "age": {str(a): float(v) for a, v in age["mean"].items()}, "age_n": {str(a): int(v) for a, v in age["size"].items()},
             "size": {str(a): float(v) for a, v in size.items()}, "over": ow, "coverage": cov}
        young, old = r["age"].get("<1년"), np.nanmean([r["age"].get(x, np.nan) for x in ("3-5년", "5-10년", "10년+")])
        r["I1"] = bool(young is not None and young <= old)
        r["I2"] = bool(len(size) == 5 and size.idxmin() == "Q5") if area_cov >= 0.5 else None
        r["I3"] = bool(ow["ratio"] >= 1.5) if (area_cov >= 0.5 and ow and ow["ratio"] == ow["ratio"]) else None
        r["enough"] = len(te) >= 2000
        res[code] = r
        L.append(f"  {name:<14} 업소 {len(g):>7,} | 판정 표본 {len(te):>7,} 폐업률 {r['base']:.1%} | 업력 "
                 + " ".join(f"{a} {v:.1%}" for a, v in r["age"].items())
                 + (" | 면적 " + " ".join(f"{a} {v:.1%}" for a, v in r["size"].items()) if len(size) else " | 면적 기록 부족")
                 + (f" | 경고 Q1 {ow['warn_q1']:.0%} vs 폐업 Q1 {ow['fail_q1']:.0%} (x{ow['ratio']:.1f})" if ow and ow["ratio"] == ow["ratio"] else "")
                 + (f" AUC {ow['auc']:.3f}" if ow else "")
                 + (f" | 포착률 {cov['ratio']:.0%} (대장 {cov['registry_close_2023']:,} / 상권 {cov['sangkwon_close_2023']:,})" if cov else ""))
    J = {c: r for c, r in res.items() if c in JUDGE and r["enough"]}
    i1 = [r["I1"] for r in J.values()]
    i2 = [r["I2"] for r in J.values() if r["I2"] is not None]
    i3 = [r["I3"] for r in J.values() if r["I3"] is not None]
    v = lambda xs, need: f"{sum(xs)}/{len(xs)} -> {'성립' if xs and sum(xs) >= need else '기각'}"  # noqa: E731
    L.append(f"  사전 가설(판정 업종 {len(J)}개): I1 업력 1년 미만 <= 3년+ {v(i1, len(i1) // 2 + 1)} | I2 큰 곳(Q5)이 가장 안전 {v(i2, len(i2) // 2 + 1)} | "
             f"I3 소형 과잉 경고(x1.5+) {v(i3, len(i3) // 2 + 1)}")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "industries": res, "I1": [sum(i1), len(i1)], "I2": [sum(i2), len(i2)], "I3": [sum(i3), len(i3)]},
                  fh, ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    main()

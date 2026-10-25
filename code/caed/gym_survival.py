"""신용캐드 실데이터 검증 - 서울 체력단련장(헬스장) 7,343곳의 실제 폐업으로 '작다는 이유로 위험하게 보이는가'를 시험 (2026-10-20).

python -X utf8 -m caed.gym_survival            # 수집(캐시 있으면 생략) + 검정 -> data/caed/GYM_SURVIVAL.txt, gym_survival.json
python -X utf8 -m caed.gym_survival --refresh  # 서울 열린데이터 다시 받기
python -X utf8 -m caed.gym_survival seal       # 오늘 영업 중 헬스장 점수 봉인(상위 10% 경고, SHA-256 -> scoreboard/caed_gym_ledger.csv)
python -X utf8 -m caed.gym_survival evaluate   # 봉인 목록 채점(12개월 전이면 중간 성적)

왜: 신용캐드 진단 모델은 합성 데이터 MVP였다(보고서·영상의 '남은 한계'). 헬스장 사장님 인터뷰에서 나온 가설을
  실제 결과(폐업)로 처음 채점한다. 상장사 실험(dintel/fair_warning.py)과 같은 질문·같은 잣대.
데이터: 서울 열린데이터광장 LOCALDATA_104201 '체력단련장업 인허가 정보'(공공누리 - 출처 표시) - 인허가일, 폐업일, 상태,
  시설 면적(SITEAREA), 주소, 좌표(X, Y: 중부원점 TM, 미터). 폐업 = 상태 '폐업'(폐업일) 또는 '직권말소'(폐업일 없으면 취소일).
  '전출'·'신고취소' 등은 사건에서 뺌(이전·행정 정정 - 망한 것이 아님).
표본(시점 고정): 매년 말 t(2014~2024)에 영업 중인 헬스장. 정답 = t 다음 12개월 안 폐업.
  피처는 t 시점에 알 수 있던 것만: 면적, 업력, 반경 500m 안 영업 중 경쟁 헬스장 수, 직전 12개월 반경 500m 신규 개업·폐업 수,
  자치구 직전 1년 폐업률, 지하 여부(주소), 건물 연면적.
학습 t <= 2019, 검증 t = 2021~2024 (2020은 틈 - 학습 정답이 2020년에 끝나게).
모델(로지스틱, 표준화 - fair_warning과 같은 방식):
  T 전통: 면적 + 업력 (대출 심사가 보는 '작고 젊다')
  F 공정: T + 입지·경쟁·상권 흐름(경쟁 수, 주변 개업·폐업, 자치구 폐업률, 지하, 건물 연면적)
지표: AUC, 경고(점수 상위 10%) 중 실제 폐업 비율, 오경보율 = 폐업 안 한 곳 중 경고받은 비율을 소형(면적 하위 20%)/대형(상위 20%)으로,
  규모 의존도 = 점수와 면적의 순위상관.
사전 가설(2026-10-20, 결과 보기 전에 적음):
  H1 전통 모델은 소형 헬스장에 대형보다 오경보를 2배 이상 낸다.
  H2 공정 모델은 AUC가 0.01 이상 높고, 소형 오경보율은 낮다.
  H3 면적의 폐업 설명력은 입지·경쟁을 넣으면 줄어든다(면적 계수 절대값 감소).
  판정: H2가 검증 기간에 성립하면 '신용캐드 가설 실데이터 지지', 아니면 그대로 보고(결과가 나빠도 공개).
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "caed")
RAW = os.path.join(OUT_DIR, "seoul_gym_permits.csv")
TXT = os.path.join(OUT_DIR, "GYM_SURVIVAL.txt")
JSN = os.path.join(OUT_DIR, "gym_survival.json")
SVC = "LOCALDATA_104201"
R = 500.0
TRAIN_END, TEST = 2019, (2021, 2024)


def fetch():
    import requests
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _env  # noqa: F401
    key = (os.getenv("SEOUL_API_KEY") or "").strip()
    rows, s = [], 1
    while True:
        b = requests.get(f"http://openapi.seoul.go.kr:8088/{key}/json/{SVC}/{s}/{s + 999}/", timeout=30).json()[SVC]
        rows += b["row"]
        if s + 999 >= int(b["list_total_count"]):
            break
        s += 1000
    df = pd.DataFrame(rows).apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)
    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_csv(RAW, index=False, encoding="utf-8")
    return df


def load(refresh=False):
    df = fetch() if refresh or not os.path.exists(RAW) else pd.read_csv(RAW, dtype=str, keep_default_na=False)
    d = lambda c: pd.to_datetime(df[c].replace("", None), format="%Y-%m-%d", errors="coerce")  # noqa: E731
    g = pd.DataFrame({
        "open": d("APVPERMYMD"),
        "close": d("DCBYMD").fillna(d("APVCANCELYMD")),
        "state": df["DTLSTATENM"],
        "area": pd.to_numeric(df["SITEAREA"], errors="coerce").where(lambda s: s > 0),
        "bldg": pd.to_numeric(df["BDNGYAREA"], errors="coerce").where(lambda s: s > 0),
        "x": pd.to_numeric(df["X"], errors="coerce"), "y": pd.to_numeric(df["Y"], errors="coerce"),
        "gu": df["RDNWHLADDR"].where(df["RDNWHLADDR"] != "", df["SITEWHLADDR"]).str.split().str[1],
        "basement": df["RDNWHLADDR"].str.contains("지하", na=False).astype(float),
        "mgt": df["OPNSFTEAMCODE"] + "-" + df["MGTNO"],   # 관리번호는 자치구마다 겹친다(10-20) -> 자치구 코드와 묶어 업소 키
    })
    g["failed"] = g["state"].isin(["폐업", "직권말소"])
    g["gone"] = g["failed"] | g["state"].isin(["전출", "신고취소", "등록취소", "허가취소"])   # 어떤 이유로든 목록에서 빠짐
    g.loc[g["gone"] & g["close"].isna(), "gone"] = False                                   # 날짜 없는 종료는 영업 중으로(보수적)
    return g.dropna(subset=["open", "x", "y"]).reset_index(drop=True)


def panel(g, dates=None):
    """dates: [(라벨, 시점)] - 기본은 매년 말 2014~2024. 봉인(seal)은 오늘 하루."""
    rows = []
    xy = g[["x", "y"]].to_numpy()
    for yr, t in dates or [(y_, pd.Timestamp(f"{y_}-12-31")) for y_ in range(2014, TEST[1] + 1)]:
        t0, t1 = t - pd.DateOffset(years=1), t + pd.DateOffset(years=1)
        alive = (g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))
        opened = (g["open"] > t0) & (g["open"] <= t)
        closed = g["failed"] & (g["close"] > t0) & (g["close"] <= t)
        idx = np.where(alive)[0]
        from scipy.spatial import cKDTree

        def cnt(mask, self_in):
            pts = xy[mask.to_numpy()]
            if not len(pts):
                return np.zeros(len(idx))
            return cKDTree(pts).query_ball_point(xy[idx], R, return_length=True) - (1 if self_in else 0)
        gu_alive = g[alive].groupby("gu").size()
        gu_rate = (g[closed].groupby("gu").size() / gu_alive).reindex(g["gu"].iloc[idx]).fillna(0).to_numpy()
        sub = g.iloc[idx]
        rows.append(pd.DataFrame({
            "t": yr, "id": idx, "mgt": sub["mgt"].to_numpy(),
            "y": (sub["failed"] & (sub["close"] > t) & (sub["close"] <= t1)).astype(int).to_numpy(),
            "log_area": np.log(sub["area"]).to_numpy(), "area_na": sub["area"].isna().astype(float).to_numpy(),
            "age": ((t - sub["open"]).dt.days / 365.25).to_numpy(),
            "comp": cnt(alive, True), "near_open": cnt(opened & alive, True) + cnt(opened & ~alive, False),
            "near_close": cnt(closed, False), "gu_close": gu_rate,
            "basement": sub["basement"].to_numpy(), "log_bldg": np.log(sub["bldg"]).to_numpy(),
            "bldg_na": sub["bldg"].isna().astype(float).to_numpy(), "area": sub["area"].to_numpy()}))
    P = pd.concat(rows, ignore_index=True)
    P["log_age"] = np.log1p(P["age"])
    P["log_comp"] = np.log1p(P["comp"])
    for c in ("log_area", "log_bldg"):
        P[c] = P[c].fillna(MED.get(c) if MED else P.loc[P["t"] <= TRAIN_END, c].median())
    if not MED:
        MED.update({c: float(P.loc[P["t"] <= TRAIN_END, c].median()) for c in ("log_area", "log_bldg")})
    return P


MED = {}   # 학습기 기준값(결측 대체 중앙값, 큰 헬스장 기준 면적) - 봉인 때도 같은 값


T_FEAT = ["log_area", "area_na", "log_age"]
F_FEAT = T_FEAT + ["log_comp", "near_open", "near_close", "gu_close", "basement", "log_bldg", "bldg_na"]


def fit(P, feats):
    from sklearn.linear_model import LogisticRegression
    tr = P[P["t"] <= TRAIN_END]
    mu, sd = tr[feats].mean(), tr[feats].std().replace(0, 1)
    m = LogisticRegression(C=1.0, max_iter=2000).fit((tr[feats] - mu) / sd, tr["y"])
    return lambda X: m.predict_proba((X[feats] - mu) / sd)[:, 1], dict(zip(feats, np.round(m.coef_[0], 3).tolist())), len(tr)


def fit_eval(P, feats):
    from sklearn.metrics import roc_auc_score
    score, coef, n_tr = fit(P, feats)
    te = P[(P["t"] >= TEST[0]) & (P["t"] <= TEST[1])].copy()
    te["s"] = score(te)
    te["flag"] = te.groupby("t")["s"].transform(lambda s: s >= s.quantile(0.9))
    flag = te["flag"]
    a = te["area"]
    small, large = a <= a.quantile(0.2), a >= a.quantile(0.8)
    neg = te["y"] == 0
    fa = lambda msk: float((flag & neg & msk).sum() / max((neg & msk).sum(), 1))  # noqa: E731
    q = pd.qcut(a, 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"])
    quint = {str(k): {"close": float(g_["y"].mean()), "flag": float(g_["flag"].mean())} for k, g_ in te.groupby(q, observed=True)}
    return {"auc": float(roc_auc_score(te["y"], te["s"])), "top10": float(te.loc[flag, "y"].mean()), "base": float(te["y"].mean()),
            "fa_small": fa(small), "fa_large": fa(large),
            "rho_size": float(te.loc[a.notna(), "s"].rank().corr(a[a.notna()].rank())),
            "quint": quint, "coef": coef, "n_train": int(n_tr), "n_test": int(len(te))}, te


def main():
    g = load("--refresh" in sys.argv)
    P = panel(g)
    T, _ = fit_eval(P, T_FEAT)
    F, teF = fit_eval(P, F_FEAT)
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L = [f"\n##### 헬스장 실데이터 공정성 검정 {stamp} | 서울 체력단련장 {len(g):,}곳(실패 {int(g['failed'].sum()):,}) | "
         f"헬스장-연 학습 {T['n_train']:,} (t<={TRAIN_END}) / 검증 {T['n_test']:,} (t={TEST[0]}~{TEST[1]}) | 정답 = 12개월 안 폐업·직권말소",
         f"  검증 폐업률 {T['base']:.1%} | 면적 5분위(Q1 작음) 실제 폐업률: " + ", ".join(f"{k} {v['close']:.1%}" for k, v in T["quint"].items())]
    for tag, r in (("T 전통(면적+업력)", T), ("F 공정(+입지·경쟁·흐름)", F) ):
        L.append(f"  {tag:<22} AUC {r['auc']:.3f} | 상위10% 폐업률 {r['top10']:.1%} ({r['top10'] / r['base']:.1f}배) | "
                 f"오경보율 소형 {r['fa_small']:.1%} / 대형 {r['fa_large']:.1%} | 규모 의존도 rho {r['rho_size']:+.2f} | "
                 "경고 비율 " + " ".join(f"{k} {v['flag']:.0%}" for k, v in r["quint"].items()))
    for tag, r in (("T", T), ("F", F)):
        L.append(f"  계수 {tag}: {r['coef']}")
    h1 = T["fa_small"] >= 2 * T["fa_large"]
    h2 = F["auc"] - T["auc"] >= 0.01 and F["fa_small"] < T["fa_small"]
    h3 = abs(F["coef"]["log_area"]) < abs(T["coef"]["log_area"])
    L.append(f"  사전 가설: H1 전통이 소형에 2배+ 오경보 {'성립' if h1 else '기각'} | H2 공정이 AUC +0.01 & 소형 오경보 감소 {'성립' if h2 else '기각'} | "
             f"H3 면적 계수 감소 {'성립' if h3 else '기각'} -> {'신용캐드 가설 실데이터 지지' if h2 else '지지 안 됨 - 그대로 보고'}")
    desc = describe(g)
    for k, v in desc.items():
        L.append(f"  기술 통계 {k}: 업력 " + " ".join(f"{a} {b:.1%}" for a, b in v["age"].items()) + " | 면적 " + " ".join(f"{a} {b:.1%}" for a, b in v["size"].items()))
    L.append("  탐색 결과(사후): 업력 짧은 헬스장이 더 망하지 않는다(두 기간·직권말소 포함/제외 모두), 면적은 상위 20%만 확실히 안전 -> scoreboard/HYPOTHESES.md H-2026-10-C로 등록, 앞으로의 12개월로 판정")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "n_gyms": int(len(g)), "n_failed": int(g["failed"].sum()), "T": T, "F": F, "desc": desc,
                   "large_cut": MED.get("large_cut"), "H1": h1, "H2": h2, "H3": h3,
                   "source": "서울 열린데이터광장 LOCALDATA_104201 체력단련장업 인허가 정보"}, fh, ensure_ascii=False, indent=1)


AGE_BINS, AGE_LAB = [0, 1, 3, 5, 10, 60], ["<1년", "1-3년", "3-5년", "5-10년", "10년+"]


def describe(g):
    """업력·면적 구간별 실제 12개월 폐업률 - 두 기간 x (폐업+직권말소 / 폐업만)."""
    out = {}
    for lab, fail in (("폐업+직권말소", ["폐업", "직권말소"]), ("폐업만", ["폐업"])):
        g2 = g.copy()
        g2["failed"] = g2["state"].isin(fail)
        P = panel(g2)
        for per, (a, b) in (("2014-19", (2014, 2019)), ("2021-24", TEST)):
            te = P[(P["t"] >= a) & (P["t"] <= b)]
            k = te[te["area"].notna()]
            out[f"{per} {lab}"] = {
                "age": {str(x): float(v) for x, v in te.groupby(pd.cut(te["age"], AGE_BINS, labels=AGE_LAB), observed=True)["y"].mean().items()},
                "size": {str(x): float(v) for x, v in k.groupby(pd.qcut(k["area"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"]), observed=True)["y"].mean().items()}}
    return out


SB = os.path.join(ROOT, "scoreboard")
LEDGER = os.path.join(SB, "caed_gym_ledger.csv")


def seal():
    """H-2026-10-C 판정 표본 고정: 오늘 영업 중인 서울 헬스장 전부의 업력·면적 구간을 파일로 고정하고 SHA-256을 원장에 남긴다.
    상호명·주소는 넣지 않는다(인허가 관리번호만). 12개월 뒤 evaluate 가 그 사이 폐업으로 채점."""
    import hashlib
    g = load(refresh=True)
    today = pd.Timestamp.now().normalize()
    S = panel(g, [(today.year, today)])
    f = os.path.join(SB, f"caed_gym_{today:%Y-%m-%d}_v2.csv")   # v1(관리번호만, 키 중복)은 채점 불가 -> v2로 대체(원장에 사유)
    if os.path.exists(f):
        print("already sealed:", f)
        return
    cut = g.loc[g["area"].notna(), "area"]
    out = pd.DataFrame({"mgt": S["mgt"], "area": S["area"], "age": S["age"].round(3),
                        "age_bin": pd.cut(S["age"], AGE_BINS, labels=AGE_LAB).astype(str),
                        "size_q": pd.qcut(S["area"], 5, labels=["Q1", "Q2", "Q3", "Q4", "Q5"]).astype(str)})
    os.makedirs(SB, exist_ok=True)
    out.to_csv(f, index=False, encoding="utf-8")
    sha = hashlib.sha256(open(f, "rb").read()).hexdigest()
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", encoding="utf-8") as fh:
        if new:
            fh.write("sealed_at,file,n,hypothesis,sha256,score_after\n")
        fh.write(f"{pd.Timestamp.now():%Y-%m-%dT%H:%M:%S},{os.path.basename(f)},{len(out)},H-2026-10-C,{sha},"
                 f"{(today + pd.DateOffset(years=1)):%Y-%m-%d}\n")
    print(f"sealed {f} | gyms {len(out)} | age bins {out.age_bin.value_counts().to_dict()} | sha {sha[:16]}")
    del cut


def evaluate():
    """봉인 표본 채점(H-2026-10-C) - 봉인일 이후 폐업(상태 '폐업'만, 직권말소 제외). 12개월 전이면 중간 성적."""
    g = load(refresh=True).set_index("mgt")
    for r in pd.read_csv(LEDGER).itertuples():
        if not str(r.file).endswith("_v2.csv"):
            continue                                   # v1은 키 중복으로 채점 불가(원장 note)
        S = pd.read_csv(os.path.join(SB, r.file), dtype={"mgt": str})
        t0 = pd.Timestamp(r.file[-14:-4])
        end = min(pd.Timestamp.now(), t0 + pd.DateOffset(years=1))
        cl = g.reindex(S["mgt"])
        S["y"] = ((cl["state"] == "폐업") & (cl["close"] > t0) & (cl["close"] <= end)).fillna(False).astype(int).to_numpy()
        young = S.loc[S["age_bin"] == "<1년", "y"].mean()
        old = S.loc[S["age_bin"].isin(["3-5년", "5-10년", "10년+"]), "y"].mean()
        big = S.loc[S["size_q"] == "Q5", "y"].mean()
        rest = S.loc[S["size_q"].isin(["Q1", "Q2", "Q3"]), "y"].mean()
        print(f"{r.file}: {(end - t0).days}/365일 | 폐업 {S.y.sum()}/{len(S)} | C1 업력<1년 {young:.1%} <= 3년+ {old:.1%}: {'성립' if young <= old else '기각'} | "
              f"C2 면적 Q5 {big:.1%} < Q1-3 {rest:.1%}: {'성립' if big < rest else '기각'}{' (중간 성적)' if (end - t0).days < 365 else ''}")


if __name__ == "__main__":
    {"seal": seal, "evaluate": evaluate}.get(sys.argv[1] if len(sys.argv) > 1 else "", main)()

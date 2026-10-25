"""프랜차이즈 카페는 더 오래 사나, 브랜드가 위험 신호인가 - 서울 휴게음식점 인허가 147,814곳 (2026-10-20).

python -X utf8 -m caed.franchise_survival      # -> data/caed/FRANCHISE_SURVIVAL.txt, franchise_survival.json

왜: 공개 데이터의 업소 단위 예측력이 낮았다(AUC 0.56~0.62). 대출 심사에서 쉽게 얻는 정보 중 아직 안 본 것이 '어느 브랜드 가맹점인가'다.
  신용캐드 관점: 가맹점주(소상공인)의 위험을 브랜드가 얼마나 설명하나. 같은 브랜드 안에서도 갈리면 브랜드만으로 심사하는 것은 불공정.
브랜드 판별(상호명, 로컬에서만 사용): 상호가 '브랜드 지점명점'처럼 띄어쓰기로 끝이 '점'이면 앞부분을 브랜드로 본다.
  학습기(t<=2019)까지 문을 연 업소 중 같은 브랜드가 30곳 이상이면 '프랜차이즈 브랜드'. 그 밖은 '독립'.
  공개 산출물에는 브랜드 이름을 내지 않는다(집계·익명 순위만) - 특정 회사 평판 문제.
표본: 매년 말 영업 중 업소의 다음 12개월 상태 '폐업'. 학습 t<=2019, 검증 2021~2024. 대장 포착률 카페 131%(상권분석 대비 - 정의 차이 포함).
사전 가설(2026-10-20, 결과 전 커밋):
  F1 검증 기간 프랜차이즈 카페의 1년 폐업률이 독립 카페보다 20% 이상(상대) 낮다.
  F2 브랜드별 1년 폐업률(검증 기간, 업소-연 200 이상 브랜드)의 상위 25% 평균이 하위 25% 평균의 2배 이상 - 브랜드가 크게 갈린다.
  F3 학습기 브랜드 폐업률을 업력·면적 모델에 더하면 프랜차이즈 카페 안에서 검증 AUC가 0.02 이상 오른다.
  판정은 그대로 보고.
정의 보완(같은 날, 결과를 보기 전 - 첫 실행은 날짜 공백 때문에 상호 병합이 0건이라 결과 없이 멈춤):
  띄어 쓴 상호('브랜드 지점명점')에서 브랜드 사전을 만들고, 붙여 쓴 상호('브랜드지점명점')는 사전의 브랜드(3자 이상)로 시작하면 그 브랜드로 본다(가장 긴 것).
  휴게음식점에는 편의점·과자점·패스트푸드가 섞여 있어(업태) 가설대로 '카페' = 업태 '커피숍'(40,554곳)만 판정에 쓴다.
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import industry_survival as IS  # noqa: E402
from caed import localdata as LD  # noqa: E402

TXT = os.path.join(ROOT, "data", "caed", "FRANCHISE_SURVIVAL.txt")
JSN = os.path.join(ROOT, "data", "caed", "franchise_survival.json")
CODE = "072405"
UPTAE = "커피숍"          # None = 업태 거르지 않음
MIN_BRAND = 30
# 10-20 재현 사전 가설(카페 F1~F3·B1 결과를 본 뒤, 일반음식점 539,188곳으로 같은 정의 그대로 - 결과 전 커밋):
#   R1 프랜차이즈 음식점 1년 폐업률이 독립보다 20%+ 낮다 | R2 쇠퇴 1/3 브랜드 가맹점 폐업률이 성장 1/3의 2배+ (검증 2021~24)
#   R3 브랜드 폐업률 피처가 프랜차이즈 안 AUC +0.02. 실행: python -X utf8 -m caed.franchise_survival --code 072404 [momentum]
# 10-20 R4 추가 재현 사전 가설(결과 전 커밋): 미용실(051801), 휴게음식점 중 커피숍이 아닌 업태(제과·패스트푸드·편의점 등, --code 072405 --not-cafe)에서도
#   F1(프랜차이즈 20%+ 낮음)과 B1(쇠퇴/성장 2배+)이 성립하는가. 두 업종 x 두 가설 4개 중 3개 이상이면 '일반화', 아니면 '카페·음식점 한정'.
if "--code" in sys.argv:
    CODE = sys.argv[sys.argv.index("--code") + 1]
    UPTAE = None
    if "--not-cafe" in sys.argv:
        UPTAE = "!커피숍"
    TXT = TXT.replace(".txt", f"_{CODE}{'_notcafe' if UPTAE == '!커피숍' else ''}.txt")
    JSN = JSN.replace(".json", f"_{CODE}{'_notcafe' if UPTAE == '!커피숍' else ''}.json")


def brand_of(name):
    s = re.sub(r"\(.*?\)|\[.*?\]", " ", str(name)).strip()
    toks = s.split()
    if len(toks) >= 2 and toks[-1].endswith("점") and len(toks[-1]) >= 2:
        b = re.sub(r"[^0-9A-Za-z가-힣]", "", "".join(toks[:-1])).lower()
        return b or None
    return None


def load():
    main = pd.read_csv(os.path.join(LD.OUT, f"{CODE}.csv"), dtype=str, keep_default_na=False)
    names = pd.read_csv(os.path.join(LD.OUT, f"{CODE}.names.csv"), dtype=str, keep_default_na=False)
    names = names.drop_duplicates(["MGTNO", "APVPERMYMD"])
    main = main.apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)
    m = main.merge(names[["MGTNO", "APVPERMYMD", "BPLCNM"] + (["RDNWHLADDR"] if "RDNWHLADDR" in names else [])],
                   on=["MGTNO", "APVPERMYMD"], how="left")
    g = IS.prep(m)
    src = m.apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)
    src = src[pd.to_datetime(src["APVPERMYMD"].replace("", None), format="%Y-%m-%d", errors="coerce").notna()].reset_index(drop=True)
    spaced = src["BPLCNM"].map(brand_of)
    vocab = sorted({b for b, n in spaced.value_counts().items() if n >= 5 and len(b) >= 3}, key=len, reverse=True)
    norm = src["BPLCNM"].fillna("").str.replace(r"[^0-9A-Za-z가-힣]", "", regex=True).str.lower()

    def joined(nm):
        if not nm.endswith("점"):
            return None
        return next((b for b in vocab if nm.startswith(b) and len(nm) > len(b) + 1), None)
    g["brand_raw"] = spaced.where(spaced.notna(), norm.map(joined))
    g["name_ok"] = src["BPLCNM"].fillna("").ne("")
    g["name"], g["addr"] = src["BPLCNM"], src.get("RDNWHLADDR")   # 10-25 정보공개서 보조 리포트(caed.fdd_agent)의 매장 명세용
    g["gu"] = src.get("gu")
    g["uptae"] = src["UPTAENM"]
    g["x"], g["y"] = pd.to_numeric(src["X"], errors="coerce"), pd.to_numeric(src["Y"], errors="coerce")   # EPSG:5174 미터 - brand_churn 같은 자리 판정
    if UPTAE and UPTAE.startswith("!"):
        return g[g["uptae"] != UPTAE[1:]].reset_index(drop=True)
    return (g[g["uptae"] == UPTAE] if UPTAE else g).reset_index(drop=True)


def panel(g, brands):
    rows = []
    for yr in range(2014, IS.TEST[1] + 1):
        t = pd.Timestamp(f"{yr}-12-31")
        alive = (g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))
        s = g[alive]
        rows.append(pd.DataFrame({"t": yr, "y": (s["failed"] & (s["close"] > t) & (s["close"] <= t + pd.DateOffset(years=1))).astype(int).to_numpy(),
                                  "age": ((t - s["open"]).dt.days / 365.25).to_numpy(), "area": s["area"].to_numpy(),
                                  "brand": s["brand_raw"].where(s["brand_raw"].isin(brands)).to_numpy()}))
    P = pd.concat(rows, ignore_index=True)
    P["fr"] = P["brand"].notna().astype(int)
    P["log_age"] = np.log1p(P["age"])
    P["area_na"] = P["area"].isna().astype(float)
    P["log_area"] = np.log(P["area"]).fillna(np.log(P.loc[P["t"] <= IS.TRAIN_END, "area"]).median())
    return P


def main():
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    g = load()
    pre = g[g["open"] <= pd.Timestamp(f"{IS.TRAIN_END}-12-31")]
    cnt = pre["brand_raw"].value_counts()
    brands = set(cnt[cnt >= MIN_BRAND].index)
    P = panel(g, brands)
    tr, te = P[P["t"] <= IS.TRAIN_END].copy(), P[(P["t"] >= IS.TEST[0]) & (P["t"] <= IS.TEST[1])].copy()
    fr_rate, ind_rate = float(te.loc[te["fr"] == 1, "y"].mean()), float(te.loc[te["fr"] == 0, "y"].mean())
    f1 = fr_rate <= 0.8 * ind_rate
    # 업력 맞춘 비교(프랜차이즈는 젊은 업소가 많을 수 있음)
    ageb = pd.cut(te["age"], IS.AGE_BINS, labels=IS.AGE_LAB)
    by_age = te.groupby([ageb, "fr"], observed=True)["y"].mean().unstack()
    br = te[te["fr"] == 1].groupby("brand")["y"].agg(["mean", "size"])
    br = br[br["size"] >= 200].sort_values("mean")
    q = max(len(br) // 4, 1)
    top, bot = float(br["mean"].iloc[-q:].mean()), float(br["mean"].iloc[:q].mean())
    f2 = bot > 0 and top >= 2 * bot
    # F3: 프랜차이즈 안에서 학습기 브랜드 폐업률 피처
    trf, tef = tr[tr["fr"] == 1].copy(), te[te["fr"] == 1].copy()
    brate = trf.groupby("brand")["y"].mean()
    prior = float(trf["y"].mean())
    for d_ in (trf, tef):
        d_["brand_rate"] = d_["brand"].map(brate).fillna(prior)
    res = {}
    for tag, f in (("base", ["log_area", "area_na", "log_age"]), ("brand", ["log_area", "area_na", "log_age", "brand_rate"])):
        mu, sd = trf[f].mean(), trf[f].std().replace(0, 1)
        m = LogisticRegression(max_iter=3000).fit((trf[f] - mu) / sd, trf["y"])
        res[tag] = float(roc_auc_score(tef["y"], m.predict_proba((tef[f] - mu) / sd)[:, 1]))
    f3 = res["brand"] - res["base"] >= 0.02
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L = [f"\n##### 프랜차이즈 생존 {stamp} | 서울 인허가 {LD.INDUSTRIES[CODE][0]}{(' 중 업태 ' + UPTAE) if UPTAE else ''} {len(g):,}곳 | 브랜드 {len(brands)}개(학습기 30곳+) | 학습 t<={IS.TRAIN_END}, 검증 {IS.TEST[0]}~{IS.TEST[1]}",
         f"  검증 1년 폐업률: 프랜차이즈 {fr_rate:.1%} (업소-연 {int((te['fr'] == 1).sum()):,}) vs 독립 {ind_rate:.1%} ({int((te['fr'] == 0).sum()):,})",
         "  업력별(프랜차이즈 / 독립): " + " | ".join(f"{a} {r.get(1, np.nan):.1%} / {r.get(0, np.nan):.1%}" for a, r in by_age.iterrows()),
         f"  브랜드 {len(br)}개(업소-연 200+): 1년 폐업률 최저 {br['mean'].min():.1%} ~ 최고 {br['mean'].max():.1%} | 상위 25% 평균 {top:.1%} vs 하위 25% {bot:.1%} ({top / bot:.1f}배)",
         f"  프랜차이즈 안 AUC: 업력·면적 {res['base']:.3f} -> +브랜드 폐업률 {res['brand']:.3f}",
         f"  사전 가설: F1 프랜차이즈 20%+ 낮음 {'성립' if f1 else '기각'} | F2 브랜드 상하위 2배+ {'성립' if f2 else '기각'} | F3 브랜드 AUC +0.02 {'성립' if f3 else '기각'}"]
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "n": int(len(g)), "n_brands": len(brands), "franchise_rate": fr_rate, "independent_rate": ind_rate,
                   "by_age": {str(a): {"franchise": float(r.get(1, np.nan)), "independent": float(r.get(0, np.nan))} for a, r in by_age.iterrows()},
                   "brand_rates_anonymous": sorted(br["mean"].round(4).tolist()), "top_q": top, "bottom_q": bot, "auc": res,
                   "F1": f1, "F2": f2, "F3": f3}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__" and "momentum" not in sys.argv and "seal" not in sys.argv and "newstore" not in sys.argv:
    main()


# ---------------------------------------------------------------------------------------------------------------
# 10-20 추가 사전 가설 B1(F1~F3 결과를 본 뒤, 브랜드 표에서 떠올린 것 - 결과 전 커밋): 브랜드가 '쇠퇴기'면 그 가맹점이 더 닫는다.
#   브랜드 순증가율(t) = (직전 12개월 서울 신규 인허가 - 직전 12개월 폐업) / t 시점 영업 중 매장 수. t 시점 매장 10곳 이상 브랜드만.
#   B1 검증 기간(2021~24) 브랜드-연 기준 순증가율 하위 1/3 브랜드 매장의 다음 1년 폐업률이 상위 1/3의 2배 이상.
#   B1b 학습기(2014~19)에서도 같은 방향(하위 1/3 > 상위 1/3) - 기간을 바꿔도 성립하는지.
def momentum():
    g = load()
    pre = g[g["open"] <= pd.Timestamp(f"{IS.TRAIN_END}-12-31")]
    cnt = pre["brand_raw"].value_counts()
    brands = set(cnt[cnt >= MIN_BRAND].index) | set(g["brand_raw"].value_counts().loc[lambda s: s >= MIN_BRAND].index)
    rows = []
    for yr in range(2014, IS.TEST[1] + 1):
        t = pd.Timestamp(f"{yr}-12-31")
        t0 = t - pd.DateOffset(years=1)
        alive = (g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))
        opened = (g["open"] > t0) & (g["open"] <= t)
        closed = g["failed"] & (g["close"] > t0) & (g["close"] <= t)
        b = g["brand_raw"]
        n_alive, n_open, n_close = b[alive].value_counts(), b[opened].value_counts(), b[closed].value_counts()
        s = g[alive & b.isin(brands)]
        y = (s["failed"] & (s["close"] > t) & (s["close"] <= t + pd.DateOffset(years=1))).astype(int)
        df = pd.DataFrame({"t": yr, "brand": s["brand_raw"], "y": y})
        stat = pd.DataFrame({"n": n_alive, "o": n_open, "c": n_close}).fillna(0)
        stat["growth"] = (stat["o"] - stat["c"]) / stat["n"].replace(0, np.nan)
        df = df.join(stat[["n", "growth"]], on="brand")
        rows.append(df[df["n"] >= 10])
    M = pd.concat(rows, ignore_index=True)
    out = {}
    for tag, (a, z) in (("검증 2021~24", IS.TEST), ("학습기 2014~19", (2014, IS.TRAIN_END))):
        d = M[(M["t"] >= a) & (M["t"] <= z)].copy()
        bt = d.groupby(["t", "brand"]).agg(growth=("growth", "first"), y=("y", "mean"), n=("y", "size")).reset_index()
        bt["tert"] = bt.groupby("t")["growth"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
        r = bt.groupby("tert").apply(lambda x: float(np.average(x["y"], weights=x["n"])), include_groups=False)
        out[tag] = {"low": float(r.loc[0]), "mid": float(r.loc[1]), "high": float(r.loc[2]), "brand_years": int(len(bt))}
    b1 = out["검증 2021~24"]["low"] >= 2 * out["검증 2021~24"]["high"]
    b1b = out["학습기 2014~19"]["low"] > out["학습기 2014~19"]["high"]
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L = [f"\n##### 브랜드 성장기·쇠퇴기 x 가맹점 폐업 {stamp} | 서울 {LD.INDUSTRIES[CODE][0]}{(' 중 ' + UPTAE) if UPTAE else ''} 인허가 | 브랜드 순증가율(직전 12개월 개업-폐업 / 매장) 3분위"]
    for k, v in out.items():
        L.append(f"  {k}: 다음 1년 폐업률 쇠퇴 1/3 {v['low']:.1%} | 중간 {v['mid']:.1%} | 성장 1/3 {v['high']:.1%} ({v['low'] / max(v['high'], 1e-9):.1f}배, 브랜드-연 {v['brand_years']})")
    L.append(f"  사전 가설: B1 검증 2배+ {'성립' if b1 else '기각'} | B1b 학습기 같은 방향 {'성립' if b1b else '기각'}")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    J = json.load(open(JSN, encoding="utf-8"))
    J["momentum"] = {"result": out, "B1": b1, "B1b": b1b, "asof": stamp}
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump(J, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__" and "momentum" in sys.argv:
    momentum()


# ---------------------------------------------------------------------------------------------------------------
# 10-20 H-2026-10-D 봉인: 오늘 기준 브랜드 성장·쇠퇴 3분위를 고정하고 12개월 뒤 그 가맹점 폐업으로 채점(카페 커피숍 + 일반음식점).
#   브랜드 이름은 공개 저장소에 넣지 않는다 - 정규화 이름의 SHA-256만 봉인 파일에, 이름 대응표는 data/(git 제외)에.
def seal_brands():
    import hashlib
    global CODE, UPTAE
    today = pd.Timestamp.now().normalize()
    t0 = today - pd.DateOffset(years=1)
    rows, names = [], []
    for code, up in (("072405", "커피숍"), ("072404", None)):
        CODE, UPTAE = code, up
        g = load()
        b = g["brand_raw"]
        alive = (g["open"] <= today) & ~(g["gone"] & (g["close"] <= today))
        n_alive = b[alive].value_counts()
        n_open = b[(g["open"] > t0) & (g["open"] <= today)].value_counts()
        n_close = b[g["failed"] & (g["close"] > t0) & (g["close"] <= today)].value_counts()
        st = pd.DataFrame({"n": n_alive, "o": n_open, "c": n_close}).fillna(0)
        st = st[st["n"] >= 10]
        st["growth"] = (st["o"] - st["c"]) / st["n"]
        st["tier"] = pd.qcut(st["growth"].rank(method="first"), 3, labels=["decline", "middle", "growth"]).astype(str)
        for br, r in st.iterrows():
            h = hashlib.sha256(f"{code}:{br}".encode("utf-8")).hexdigest()[:16]
            rows.append({"code": code, "brand_hash": h, "stores": int(r["n"]), "growth": round(float(r["growth"]), 4), "tier": r["tier"]})
            names.append({"code": code, "brand_hash": h, "brand": br})
    sb = os.path.join(ROOT, "scoreboard")
    f = os.path.join(sb, f"caed_brand_{today:%Y-%m-%d}.csv")
    if os.path.exists(f):
        print("already sealed", f)
        return
    pd.DataFrame(rows).to_csv(f, index=False, encoding="utf-8")
    pd.DataFrame(names).to_csv(os.path.join(ROOT, "data", "caed", f"brand_names_{today:%Y-%m-%d}.csv"), index=False, encoding="utf-8")
    sha = hashlib.sha256(open(f, "rb").read()).hexdigest()
    led = os.path.join(sb, "caed_brand_ledger.csv")
    new = not os.path.exists(led)
    with open(led, "a", encoding="utf-8") as fh:
        if new:
            fh.write("sealed_at,file,n_brands,hypothesis,sha256,score_after\n")
        fh.write(f"{pd.Timestamp.now():%Y-%m-%dT%H:%M:%S},{os.path.basename(f)},{len(rows)},H-2026-10-D,{sha},{(today + pd.DateOffset(years=1)):%Y-%m-%d}\n")
    print(f"sealed {f} | brands {len(rows)} | {pd.DataFrame(rows).groupby(['code', 'tier']).size().to_dict()} | sha {sha[:16]}")


if __name__ == "__main__" and "seal" in sys.argv:
    seal_brands()


# ---------------------------------------------------------------------------------------------------------------
# 10-24 H-2026-10-N(결과 전 커밋): 대출이 나가는 '개업 직후' 가맹점만 - 직전 12개월 안 개업, 다음 12개월 폐업, B1과 같은 브랜드 3분위.
#   python -X utf8 -m caed.franchise_survival newstore   (카페 커피숍 + 일반음식점을 한 번에)
def newstore():
    global CODE, UPTAE
    out = {}
    for code, up in (("072405", "커피숍"), ("072404", None)):
        CODE, UPTAE = code, up
        g = load()
        brands = set(g["brand_raw"].value_counts().loc[lambda s: s >= MIN_BRAND].index)
        rows = []
        for yr in range(2014, IS.TEST[1] + 1):
            t = pd.Timestamp(f"{yr}-12-31")
            t0 = t - pd.DateOffset(years=1)
            alive = (g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))
            opened = (g["open"] > t0) & (g["open"] <= t)
            closed = g["failed"] & (g["close"] > t0) & (g["close"] <= t)
            b = g["brand_raw"]
            stat = pd.DataFrame({"n": b[alive].value_counts(), "o": b[opened].value_counts(), "c": b[closed].value_counts()}).fillna(0)
            stat["growth"] = (stat["o"] - stat["c"]) / stat["n"].replace(0, np.nan)
            s = g[alive & opened & b.isin(brands)]
            df = pd.DataFrame({"t": yr, "brand": s["brand_raw"],
                               "y": (s["failed"] & (s["close"] > t) & (s["close"] <= t + pd.DateOffset(years=1))).astype(int)})
            df = df.join(stat[["n", "growth"]], on="brand")
            rows.append(df[df["n"] >= 10])
        M = pd.concat(rows, ignore_index=True)
        res = {}
        for tag, (a, z) in (("test", IS.TEST), ("train", (2014, IS.TRAIN_END))):
            d = M[(M["t"] >= a) & (M["t"] <= z)]
            bt = d.groupby(["t", "brand"]).agg(growth=("growth", "first"), y=("y", "mean"), n=("y", "size")).reset_index()
            bt["tert"] = bt.groupby("t")["growth"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
            r = bt.groupby("tert").apply(lambda x: float(np.average(x["y"], weights=x["n"])), include_groups=False)
            res[tag] = {"low": float(r.loc[0]), "mid": float(r.loc[1]), "high": float(r.loc[2]),
                        "brand_years": int(len(bt)), "stores": int(bt["n"].sum())}
        out[code] = res
    n1 = out["072405"]["test"]["low"] >= 2 * out["072405"]["test"]["high"]
    n2 = out["072404"]["test"]["low"] >= 2 * out["072404"]["test"]["high"]
    n3 = all(out[c]["train"]["low"] > out[c]["train"]["high"] for c in out)
    thin = any(out[c][k]["brand_years"] < 30 for c in out for k in out[c])
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L = [f"\n##### 개업 직후 가맹점 x 브랜드 국면 (H-2026-10-N) {stamp} | 직전 12개월 개업 가맹점의 다음 1년 폐업 | 브랜드 순증가율 3분위"]
    for c, nm in (("072405", "카페(커피숍)"), ("072404", "일반음식점")):
        for k, lab in (("test", "검증 2021~24"), ("train", "학습기 2014~19")):
            v = out[c][k]
            L.append(f"  {nm} {lab}: 쇠퇴 1/3 {v['low']:.1%} | 중간 {v['mid']:.1%} | 성장 1/3 {v['high']:.1%} "
                     f"({v['low'] / max(v['high'], 1e-9):.1f}배, 브랜드-연 {v['brand_years']}, 신규 가맹점 {v['stores']:,})")
    L.append(f"  사전 가설: N1 카페 2배+ {'성립' if n1 else '기각'} | N2 음식점 2배+ {'성립' if n2 else '기각'} | N3 학습기 같은 방향 {'성립' if n3 else '기각'}"
             + (" | 표본 부족(브랜드-연 30 미만) - 판정 보류" if thin else ""))
    txt = "\n".join(L)
    print(txt)
    with open(os.path.join(ROOT, "data", "caed", "FRANCHISE_SURVIVAL.txt"), "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(os.path.join(ROOT, "data", "caed", "franchise_newstore.json"), "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "result": out, "N1": n1, "N2": n2, "N3": n3, "thin": thin}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__" and "newstore" in sys.argv:
    newstore()

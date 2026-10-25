"""공정거래위원회 가맹사업 정보공개서 브랜드 목록 2017~2026 - 서울 인허가로 잰 브랜드 건강도를 공식 등록 기록으로 검증 (2026-10-21).

python -X utf8 -m caed.ftc_brands fetch     # -> data/caed/ftc/brands_<연도>.csv (연도별 이어받기)
python -X utf8 -m caed.ftc_brands test      # X1~X3 -> data/caed/FTC_BRANDS.txt, ftc_brands.json

출처: data.go.kr 15125467 '공정거래위원회_가맹정보_브랜드 목록 정보 제공 서비스' (이용허락범위 제한 없음, 10-21 활용신청 승인).
  getBrandinfo(jngBizCrtraYr) - 기준연도별 정보공개서 등록 브랜드: 브랜드관리번호·본부·업종·가맹사업개시일. 2017 5,886 ~ 2024 11,683개(2026은 등록 진행 중 9,129).
왜: 브랜드 건강도(caed/brand_health.py)는 상호에서 브랜드를 추정하고 서울 인허가 개폐업만으로 잰다. 공식 등록 목록은 서로 독립인 두 번째 출처다.
  (1) 상호 추정 브랜드가 실제 가맹 브랜드인지(판별기 정밀도), (2) 서울에서 '쇠퇴'로 본 브랜드가 실제로 가맹사업을 접는지(정보공개서 등록 이탈),
  (3) 공식 가맹사업 개시일 = 브랜드 나이가 대출 심사에서 쓸 수 있는 공개 위험 신호인지.
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "data", "caed", "ftc")
TXT = os.path.join(ROOT, "data", "caed", "FTC_BRANDS.txt")
JSN = os.path.join(ROOT, "data", "caed", "ftc_brands.json")
URL = "https://apis.data.go.kr/1130000/FftcBrandRlsInfo2_Service/getBrandinfo"
YEARS = range(2017, 2027)


def _key():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _env  # noqa: F401
    return (os.getenv("DATA_GO_KR_SERVICE_KEY") or "").strip()


def fetch():
    import requests
    key = _key()
    os.makedirs(OUT, exist_ok=True)
    for y in YEARS:
        path = os.path.join(OUT, f"brands_{y}.csv")
        if os.path.exists(path) and y < 2026:
            continue
        rows, page = [], 1
        while True:
            for _ in range(5):
                try:
                    r = requests.get(URL, params={"serviceKey": key, "pageNo": page, "numOfRows": 1000, "resultType": "json",
                                                  "jngBizCrtraYr": str(y)}, timeout=60).json()
                    break
                except Exception:  # noqa: BLE001 - 일시 오류 재시도
                    continue
            items = r.get("items") or []
            rows += items
            if len(rows) >= int(r.get("totalCount", 0)) or not items:
                break
            page += 1
        pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")
        print(f"ftc {y}: {len(rows):,} brands")


def norm(s):
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(s or "")).lower()


def load():
    fs = []
    for y in YEARS:
        p = os.path.join(OUT, f"brands_{y}.csv")
        if os.path.exists(p):
            fs.append(pd.read_csv(p, dtype=str, keep_default_na=False))
    d = pd.concat(fs, ignore_index=True)
    d["yr"] = d["jngBizCrtraYr"].astype(int)
    d["key"] = d["brandNm"].map(norm)
    d["start"] = pd.to_datetime(d["jngBizStrtDate"].replace("", None), format="%Y%m%d", errors="coerce")
    return d


def match(seoul_keys, ftc_keys):
    """서울 상호 브랜드 -> 공정위 브랜드 이름 키(사전 등록 규칙: 정확히 같으면 그것, 아니면 한쪽이 다른 쪽으로 시작하는 것 중 가장 긴 것, 둘 다 3자+)."""
    fk = sorted({k for k in ftc_keys if len(k) >= 3}, key=len, reverse=True)
    fset = set(fk)
    out = {}
    for s in seoul_keys:
        if s in fset:
            out[s] = s
        elif len(s) >= 3:
            hit = next((f for f in fk if f.startswith(s) or s.startswith(f)), None)
            if hit:
                out[s] = hit
    return out


def seoul(code, uptae):
    """서울 가맹점 표(F.load)와 브랜드-연 순증가율(B1 정의) - t = 2014~2024 말."""
    from caed import franchise_survival as FS
    from caed import industry_survival as IS
    FS.CODE, FS.UPTAE = code, uptae
    g = FS.load()
    cnt = g["brand_raw"].value_counts()
    brands = set(cnt[cnt >= FS.MIN_BRAND].index)
    rows, st = [], []
    for yr in range(2014, IS.TEST[1] + 1):
        t = pd.Timestamp(f"{yr}-12-31")
        t0 = t - pd.DateOffset(years=1)
        b = g["brand_raw"]
        alive = (g["open"] <= t) & ~(g["gone"] & (g["close"] <= t))
        opened = (g["open"] > t0) & (g["open"] <= t)
        closed = g["failed"] & (g["close"] > t0) & (g["close"] <= t)
        stat = pd.DataFrame({"n": b[alive].value_counts(), "o": b[opened].value_counts(), "c": b[closed].value_counts()}).fillna(0)
        stat = stat[stat.index.isin(brands)]
        stat["growth"] = (stat["o"] - stat["c"]) / stat["n"].replace(0, np.nan)
        st.append(stat.assign(t=yr).rename_axis("brand").reset_index())
        s = g[alive & b.isin(brands)]
        rows.append(pd.DataFrame({"t": yr, "brand": s["brand_raw"].to_numpy(),
                                  "y": (s["failed"] & (s["close"] > t) & (s["close"] <= t + pd.DateOffset(years=1))).astype(int).to_numpy(),
                                  "age": ((t - s["open"]).dt.days / 365.25).to_numpy()}))
    return brands, pd.concat(rows, ignore_index=True), pd.concat(st, ignore_index=True)


def test():
    d = load()
    fo = d[d["indutyLclasNm"] == "외식"]
    first = fo.groupby("key")["start"].min()
    years_of = fo.groupby("key")["yr"].agg(set)
    L = [f"\n##### 공정위 정보공개서 브랜드 목록 외부 검증 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 외식 브랜드 이름 {fo['key'].nunique():,}개(2017~2026)"]
    res = {}
    for code, up, label in (("072405", "커피숍", "카페"), ("072404", None, "음식점")):
        brands, P, S = seoul(code, up)
        m = match(brands, set(fo["key"]))
        x1 = len(m) / max(len(brands), 1)
        stores = P[P["t"] == 2024].groupby("brand").size()
        x1w = float(stores[stores.index.isin(list(m))].sum() / stores.sum())
        # X2: t=2021~2023, 매칭 + 그해 등록 + 서울 10곳+ 브랜드의 순증가율 3분위 -> t+1, t+2 목록 이탈
        S2 = S[(S["t"].between(2021, 2023)) & (S["n"] >= 10) & S["brand"].isin(list(m))].copy()
        S2["fk"] = S2["brand"].map(m)
        S2 = S2[[t in years_of.get(k, set()) for k, t in zip(S2["fk"], S2["t"])]].copy()
        S2["exit"] = [int((t + 1) not in years_of[k] and (t + 2) not in years_of[k]) for k, t in zip(S2["fk"], S2["t"])]
        S2["tert"] = S2.groupby("t")["growth"].transform(lambda s: pd.qcut(s.rank(method="first"), 3, labels=False))
        ex = S2.groupby("tert")["exit"].agg(["mean", "sum", "size"])
        n_exit = int(S2["exit"].sum())
        x2 = None if n_exit < 10 else bool(ex.loc[0, "mean"] >= 2 * ex.loc[2, "mean"])
        # X3: 검증 2021~24 가맹점-연, 브랜드 나이
        T = P[P["t"].between(2021, 2024) & P["brand"].isin(list(m))].copy()
        T["bstart"] = T["brand"].map(m).map(first)
        T = T[T["bstart"].notna()]
        T["bage"] = (pd.to_datetime(T["t"].astype(str) + "-12-31") - T["bstart"]).dt.days / 365.25
        cut = pd.cut(T["bage"], [-1e9, 3, 5, 10, 1e9], labels=["<3년", "3~5년", "5~10년", "10년+"], right=False)
        by = T.groupby(cut, observed=True)["y"].agg(["mean", "size"])
        x3 = bool(by.loc["<3년", "mean"] >= 1.5 * by.loc["10년+", "mean"]) if {"<3년", "10년+"} <= set(by.index) else None
        # 정보: 매장 업력을 맞춘 비교(젊은 브랜드 = 젊은 매장일 수 있음) - 매장 업력 3년 미만 안에서
        yb = T[T["age"] < 3].groupby(cut[T["age"] < 3], observed=True)["y"].agg(["mean", "size"])
        res[label] = {"brands": len(brands), "matched": len(m), "x1": x1, "x1_store_w": x1w, "X1": x1 >= 0.7,
                      "exit_by_tert": {int(k): {"rate": float(v["mean"]), "exits": int(v["sum"]), "n": int(v["size"])} for k, v in ex.iterrows()},
                      "n_exit": n_exit, "X2": x2,
                      "by_brand_age": {str(k): {"rate": float(v["mean"]), "n": int(v["size"])} for k, v in by.iterrows()},
                      "by_brand_age_young_store": {str(k): {"rate": float(v["mean"]), "n": int(v["size"])} for k, v in yb.iterrows()}, "X3": x3}
        verdict = lambda v: "판정 불가" if v is None else ("성립" if v else "기각")  # noqa: E731
        L += [f"  [{label}] 서울 브랜드 {len(brands)}개(30곳+) 중 공정위 매칭 {len(m)}개 ({x1:.0%}, 2024 매장 가중 {x1w:.0%}) -> X1 {verdict(x1 >= 0.7)}",
              "    X2 등록 이탈률(t+1·t+2 목록에 없음) 서울 순증가율 3분위: "
              + " | ".join(f"{['쇠퇴', '중간', '성장'][int(k)]} {v['mean']:.1%} ({int(v['sum'])}/{int(v['size'])})" for k, v in ex.iterrows())
              + f" -> {verdict(x2)}",
              "    X3 브랜드 나이별 가맹점 다음 1년 폐업률(2021~24): " + " | ".join(f"{k} {v['mean']:.1%} (n {int(v['size']):,})" for k, v in by.iterrows())
              + f" -> {verdict(x3)}",
              "    (정보) 매장 업력 3년 미만만: " + " | ".join(f"{k} {v['mean']:.1%} (n {int(v['size']):,})" for k, v in yb.iterrows())]
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": f"{pd.Timestamp.now():%Y-%m-%d %H:%M}", "result": res}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__" and "fetch" in sys.argv:
    fetch()
if __name__ == "__main__" and "test" in sys.argv:
    test()

"""브랜드 건강도 조회 - 외식 가맹 브랜드의 서울 매장 추이·개폐업·성장/쇠퇴 3분위·가맹점 폐업률 (2026-10-20, 시제품).

python -X utf8 -m caed.brand_health build        # -> data/caed/brand_health.json (카페 커피숍 + 일반음식점, 매장 10곳+ 브랜드)
python -X utf8 -m caed.brand_health 메가          # 콘솔 조회

근거: caed/franchise_survival.py - 브랜드 쇠퇴 1/3 가맹점의 다음 1년 폐업률이 성장 1/3의 2.6~7.1배(카페·음식점, 두 기간, 업력 통제 후에도).
범위: 외식(카페·음식점)만 - 미용·제과·편의점에서는 재현 안 됨(R4 1/4).
공개: 브랜드 이름은 판정(H-2026-10-D, 2027-10) 전까지 공개 화면에 내지 않는다(사이트 공개 모드는 이름 숨김). 내부 시연·파일럿용.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "data", "caed", "brand_health.json")
LEGAL_FORMS = {"주식회사", "유한회사", "합자회사", "농업회사법인", "영농조합법인", "사단법인", "재단법인", "협동조합"}
SETS = (("072405", None, "카페·휴게"), ("072404", None, "음식점"))   # 조회용은 업태를 거르지 않음(카페가 기타 휴게음식점으로도 등록)


def merge_variants(b):
    """표기 변형 합치기: 3자 이상 브랜드 A가 다른 브랜드 B의 앞부분이면(이디야 / 이디야커피) B를 A로. 짧은 쪽이 10곳 이상일 때만."""
    vc = b.value_counts()
    keys = sorted([k for k, v in vc.items() if v >= 10 and len(k) >= 3], key=len)
    m = {}
    for k in vc.index:
        root = next((r for r in keys if r != k and k.startswith(r)), None)
        if root:
            m[k] = m.get(root, root)
    return b.map(lambda x: m.get(x, x) if isinstance(x, str) else x)


_FTC = None


def ftc_info(br):
    """공정위 정보공개서 등록(caed/ftc_brands.py 매칭 규칙): 등록 연도, 최초 가맹사업개시일, 업종 중분류. 없으면 등록 안 됨(직영 체인 등)."""
    global _FTC
    from caed import ftc_brands as FB
    if _FTC is None:
        try:
            d = FB.load()
            _FTC = d[d["indutyLclasNm"] == "외식"]
        except (OSError, ValueError):
            _FTC = pd.DataFrame(columns=["key", "yr", "start", "indutyMlsfcNm"])
    hit = FB.match([br], set(_FTC["key"])).get(br)
    if not hit:
        return {"ftc": None}
    r = _FTC[_FTC["key"] == hit]
    st = r["start"].min()
    return {"ftc": {"years": sorted(int(y) for y in r["yr"].unique()), "start": None if pd.isna(st) else f"{st:%Y-%m-%d}",
                    "mid": r["indutyMlsfcNm"].mode().iloc[0] if len(r) else None}}


def build():
    from caed import franchise_survival as F
    today = pd.Timestamp.now().normalize()
    months = pd.date_range(end=today, periods=37, freq="ME")
    out = []
    for code, up, label in SETS:
        F.CODE, F.UPTAE = code, up
        g = F.load()
        g["brand_raw"] = merge_variants(g["brand_raw"])
        b = g["brand_raw"]
        # 10-21 같은 자리 다음 점포(caed/brand_churn.py): 직전 18~6개월 폐업 가맹점 중 다른 브랜드로 바뀐 수 - 설명 지표(점수 아님, D2b 기각)
        from caed import brand_churn as BC
        _, nb = BC.successors(g)
        win = g["close"].between(today - pd.DateOffset(months=18), today - pd.DateOffset(months=6), inclusive="right")
        conv = b.notna() & g["failed"] & nb.notna() & (nb != b) & win
        same = b.notna() & g["failed"] & (nb == b) & win
        cnt = b.value_counts()
        # 10-21 공정위 매칭에서 드러난 판별 오류: '주식회사 OO점'은 법인 형태가 브랜드로 잡힌다(조회에서만 뺌, 봉인 정의는 그대로)
        brands = [x for x in cnt[cnt >= 15].index if x not in LEGAL_FORMS]
        t0, t2 = today - pd.DateOffset(years=1), today - pd.DateOffset(years=2)
        alive_now = (g["open"] <= today) & ~(g["gone"] & (g["close"] <= today))
        ind_close = float((g["failed"] & (g["close"] > t0)).sum() / max(alive_now.sum(), 1))
        rows = []
        for br in brands:
            m = b == br
            gb = g[m]
            n = int(alive_now[m].sum())
            if n < 10:
                continue
            o = int(((gb["open"] > t0) & (gb["open"] <= today)).sum())
            c = int((gb["failed"] & (gb["close"] > t0) & (gb["close"] <= today)).sum())
            c2 = int((gb["failed"] & (gb["close"] > t2) & (gb["close"] <= t0)).sum())
            alive_1y = int(((gb["open"] <= t0) & ~(gb["gone"] & (gb["close"] <= t0))).sum())
            series = [int(((gb["open"] <= me) & ~(gb["gone"] & (gb["close"] <= me))).sum()) for me in months]
            rows.append({"brand": br, "industry": label, "code": code, "stores": n, "open_12m": o, "close_12m": c,
                         "conv_out": int((conv & m).sum()), "same_reopen": int((same & m).sum()), "closed_6_18m": int((g["failed"] & win & m).sum()),
                         **ftc_info(br),
                         "growth": (o - c) / n, "close_rate_12m": c / max(alive_1y, 1), "close_prev_12m": c2,
                         "series": series})
        df = pd.DataFrame(rows)
        df["tier"] = pd.qcut(df["growth"].rank(method="first"), 3, labels=["쇠퇴", "중간", "성장"]).astype(str)
        df["industry_close_12m"] = ind_close
        out += df.to_dict("records")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"asof": f"{today:%Y-%m-%d}", "months": [f"{m:%Y-%m}" for m in months], "brands": out,
                   "evidence": "쇠퇴 1/3 브랜드 가맹점의 다음 1년 폐업률 = 성장 1/3의 2.6~7.1배(서울 인허가, 카페·음식점, 2014~19·2021~24)"},
                  fh, ensure_ascii=False, indent=1, default=float)
    print(f"brand_health: {len(out)} brands -> {OUT}")


def search(q, limit=8):
    with open(OUT, encoding="utf-8") as fh:
        d = json.load(fh)
    import re
    k = re.sub(r"[^0-9A-Za-z가-힣]", "", q or "").lower()
    hits = [b for b in d["brands"] if k and k in b["brand"]]
    hits.sort(key=lambda b: -b["stores"])
    return {"asof": d["asof"], "months": d["months"], "evidence": d["evidence"], "hits": hits[:limit],
            "tier_counts": pd.Series([b["tier"] for b in d["brands"]]).value_counts().to_dict()}


if __name__ == "__main__":
    if "build" in sys.argv:
        build()
    else:
        r = search(" ".join(sys.argv[1:]))
        for h in r["hits"]:
            print(h["industry"], h["brand"], h["stores"], f"+{h['open_12m']} -{h['close_12m']}", h["tier"], f"{h['close_rate_12m']:.1%}", h["series"][-13::6])

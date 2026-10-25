"""예비 창업자용 '브랜드로 열면' 1페이지의 근거 - 과거 개업 코호트의 브랜드 1년 폐업률이 다음 코호트에도 맞나 (2026-10-24, H-2026-10-P).

python -X utf8 -m caed.brand_onepager      # -> data/caed/BRAND_COHORT.txt, brand_cohort.json(익명 분포만)

코호트 A = 2019-01~2021-12 개업, B = 2022-01~2024-06 개업, 결과 = 개업 후 365일 안 '폐업'(서울 인허가).
두 코호트 모두 가맹점 20곳 이상인 브랜드만. 브랜드 판별은 franchise_survival.load()와 같다.
공개 산출물에는 브랜드 이름을 넣지 않는다(익명 분포·판정만). 이름별 조회는 로컬 사업 사이트에서만.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import franchise_survival as FS  # noqa: E402

A = ("2019-01-01", "2021-12-31")
B = ("2022-01-01", "2024-06-30")
MIN_N = 20
TXT = os.path.join(ROOT, "data", "caed", "BRAND_COHORT.txt")
JSN = os.path.join(ROOT, "data", "caed", "brand_cohort.json")


def cohort(g, lo, hi):
    s = g[(g["open"] >= pd.Timestamp(lo)) & (g["open"] <= pd.Timestamp(hi)) & g["brand_raw"].notna()]
    y = (s["failed"] & s["close"].notna() & ((s["close"] - s["open"]).dt.days <= 365)).astype(int)
    return pd.DataFrame({"brand": s["brand_raw"].to_numpy(), "y": y.to_numpy()})


def one(code, uptae):
    from scipy.stats import spearmanr
    from sklearn.metrics import roc_auc_score
    FS.CODE, FS.UPTAE = code, uptae
    g = FS.load()
    ca, cb = cohort(g, *A), cohort(g, *B)
    ra, rb = ca.groupby("brand")["y"].agg(["mean", "size"]), cb.groupby("brand")["y"].agg(["mean", "size"])
    j = ra.join(rb, lsuffix="_a", rsuffix="_b", how="inner")
    j = j[(j["size_a"] >= MIN_N) & (j["size_b"] >= MIN_N)].copy()
    out = {"brands": int(len(j)), "stores_a": int(j["size_a"].sum()), "stores_b": int(j["size_b"].sum())}
    if len(j) < 3:
        return out
    rho = float(spearmanr(j["mean_a"], j["mean_b"]).statistic)
    j["tert"] = pd.qcut(j["mean_a"].rank(method="first"), 3, labels=False)
    w = j.groupby("tert").apply(lambda x: float(np.average(x["mean_b"], weights=x["size_b"])), include_groups=False)
    tb = cb[cb["brand"].isin(j.index)]
    auc = float(roc_auc_score(tb["y"], tb["brand"].map(j["mean_a"]))) if tb["y"].nunique() == 2 else float("nan")
    out.update(rho=rho, worst_b=float(w.loc[2]), best_b=float(w.loc[0]), mid_b=float(w.loc[1]), auc=auc,
               rate_a=float(np.average(j["mean_a"], weights=j["size_a"])), rate_b=float(np.average(j["mean_b"], weights=j["size_b"])),
               dist_a=sorted(j["mean_a"].round(3).tolist()))
    out["P1"] = rho >= 0.3
    out["P2"] = out["best_b"] > 0 and out["worst_b"] >= 1.5 * out["best_b"]
    out["P3"] = auc >= 0.55
    out["thin"] = len(j) < 30
    return out


def main():
    res = {"072405": one("072405", "커피숍"), "072404": one("072404", None)}
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L = [f"\n##### 브랜드 1년 폐업률 코호트 이어짐 (H-2026-10-P) {stamp} | A 개업 {A[0][:7]}~{A[1][:7]} -> B 개업 {B[0][:7]}~{B[1][:7]} | 두 코호트 가맹점 {MIN_N}+ 브랜드"]
    for c, nm in (("072405", "카페(커피숍)"), ("072404", "일반음식점")):
        v = res[c]
        if "rho" not in v:
            L.append(f"  {nm}: 브랜드 {v['brands']}개 - 계산 불가")
            continue
        L.append(f"  {nm}: 브랜드 {v['brands']}개(가맹점 A {v['stores_a']:,} / B {v['stores_b']:,}) | 평균 1년 폐업률 A {v['rate_a']:.1%} B {v['rate_b']:.1%} | "
                 f"순위상관 {v['rho']:.2f} | A 기준 나쁜 1/3 -> B {v['worst_b']:.1%}, 중간 {v['mid_b']:.1%}, 좋은 1/3 {v['best_b']:.1%} "
                 f"({v['worst_b'] / max(v['best_b'], 1e-9):.1f}배) | AUC {v['auc']:.3f}")
        L.append(f"    사전 가설: P1 상관 0.3+ {'성립' if v['P1'] else '기각'} | P2 1.5배+ {'성립' if v['P2'] else '기각'} | P3 AUC 0.55+ {'성립' if v['P3'] else '기각'}"
                 + (" | 브랜드 30개 미만 - 판정 보류" if v["thin"] else ""))
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "cohort_a": A, "cohort_b": B, "min_n": MIN_N, "result": res}, fh, ensure_ascii=False, indent=1)


LOCAL = os.path.join(ROOT, "data", "caed", "brand_cohort_local.json")


def local(min_n=10):
    """10-24 사업 사이트 1페이지용(로컬 전용, 이름 포함) - 브랜드별 개업 첫해 폐업률. H-2026-10-P 보류라 '참고·미검증'으로만 보인다.
    이름은 brand_health 조회와 맞추려고 merge_variants를 거친다(사전 등록 검정 main()은 그대로)."""
    from caed import brand_health as BH
    out = {}
    for code, uptae in (("072405", None), ("072404", None)):   # brand_health.SETS와 같게 업태를 거르지 않음
        FS.CODE, FS.UPTAE = code, uptae
        g = FS.load()
        g["brand_raw"] = BH.merge_variants(g["brand_raw"])
        for tag, (lo, hi) in (("a", A), ("b", B)):
            r = cohort(g, lo, hi).groupby("brand")["y"].agg(["mean", "size"])
            for br, row in r[r["size"] >= min_n].iterrows():
                out.setdefault(f"{code}|{br}", {})[tag] = {"rate": round(float(row["mean"]), 4), "n": int(row["size"])}
    with open(LOCAL, "w", encoding="utf-8") as fh:
        json.dump({"asof": pd.Timestamp.now().strftime("%Y-%m-%d"), "cohort_a": A, "cohort_b": B, "min_n": min_n, "brands": out}, fh, ensure_ascii=False)
    print(f"brand_cohort_local: {len(out)} brand-industry pairs -> {LOCAL}")


if __name__ == "__main__":
    local() if "local" in sys.argv else main()

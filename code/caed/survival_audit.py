"""실측 생존율 공개판 (2026-10-25, 로드맵 B-3b ① '생존율 검증' 준비).

python -X utf8 -m caed.survival_audit     # -> data/caed/SURVIVAL_AUDIT.txt(익명 분포), survival_audit.json(로컬, 이름 포함)
python -X utf8 -m caed.survival_audit transfer   # H-2026-10-Z 양도 착시 검정 -> SURVIVAL_AUDIT.txt, survival_transfer.json

공정위 정보공개서 개정(가맹사업법 시행령, 시행일 원문 확인 중)이 새로 요구하는 세 항목을 서울 인허가 기록으로 같은 모양으로 잰다.
본부가 신고값을 내기 시작하면 브랜드별로 그대로 대조할 수 있게 하려는 것(정의는 우리 근사 - 공정위 세부 산식이 나오면 맞춘다):
  - 장기운영 비율: 지금 영업 중인 가맹점 중 개업 5년 이상
  - 생존율: 3년 전 같은 1년 동안 연 가맹점 중 지금까지(개업 후 3년) 폐업하지 않은 비율, 1년 생존율도 함께
  - 폐점 평균 영업기간: 최근 1년 안 폐업한 가맹점의 개업~폐업 평균 연수
공개 산출물에는 브랜드 이름을 넣지 않는다(익명 분포·업종 비교만). 이름별 표는 로컬 사업 사이트에서만.
한계: 대장은 양도를 폐업으로 못 잡는다(생존율이 높게 나올 수 있음) · 상호 기반 브랜드 추정 · 서울만.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import brand_health as BH  # noqa: E402
from caed import franchise_survival as FS  # noqa: E402

MIN_N = 20          # 지금 영업 중 가맹점 20곳 이상 브랜드만
MIN_COHORT = 10     # 생존율 코호트 10곳 미만이면 비움
TXT = os.path.join(ROOT, "data", "caed", "SURVIVAL_AUDIT.txt")
JSN = os.path.join(ROOT, "data", "caed", "survival_audit.json")


def measure(g, today):
    alive = (g["open"] <= today) & ~(g["gone"] & (g["close"] <= today))
    def surv(s, yrs):
        lo, hi = today - pd.DateOffset(years=yrs + 1), today - pd.DateOffset(years=yrs)
        c = s[(s["open"] > lo) & (s["open"] <= hi)]
        dead = c["failed"] & c["close"].notna() & ((c["close"] - c["open"]).dt.days <= 365.25 * yrs)
        return (float(1 - dead.mean()), int(len(c))) if len(c) else (None, 0)
    def one(s, a):
        r1, n1 = surv(s, 1)
        r3, n3 = surv(s, 3)
        cl = s[s["failed"] & (s["close"] > today - pd.DateOffset(years=1)) & (s["close"] <= today)]
        return {"stores": int(a.sum()),
                "long5": float(((today - s.loc[a, "open"]).dt.days >= 365.25 * 5).mean()) if a.any() else None,
                "surv1": r1 if n1 >= MIN_COHORT else None, "n1": n1, "surv3": r3 if n3 >= MIN_COHORT else None, "n3": n3,
                "closed_avg_years": float(((cl["close"] - cl["open"]).dt.days / 365.25).mean()) if len(cl) else None, "n_closed": int(len(cl))}
    fr = g["brand_raw"].notna()
    out = {"franchise": one(g[fr], alive[fr]), "independent": one(g[~fr], alive[~fr]), "brands": {}}
    # 10-25 개업 연도별 첫해 폐업률 - 독립 카페가 2014~21 약 24% -> 2025 60%로 치솟아 같이 싣는다(실제 변화인지 양도·지위승계가 폐업으로 잡힌 것인지 미확인)
    y1 = g["failed"] & g["close"].notna() & ((g["close"] - g["open"]).dt.days <= 365)
    yr = g["open"].dt.year
    done = g["open"] <= today - pd.DateOffset(years=1)
    out["first_year_by_open_year"] = {k: {int(y): round(float(v), 4) for y, v in y1[m & done & yr.between(2014, today.year)].groupby(yr).mean().items()}
                                      for k, m in (("franchise", fr), ("independent", ~fr))}
    b = g["brand_raw"]
    for br, n in b[alive].value_counts().items():
        if n < MIN_N or br in BH.LEGAL_FORMS:
            continue
        m = b == br
        out["brands"][br] = one(g[m], alive[m])
    return out


def main():
    today = pd.Timestamp.now().normalize()
    res = {}
    for code, label in (("072405", "카페·휴게"), ("072404", "음식점")):   # brand_health.SETS와 같게 업태를 거르지 않음
        FS.CODE, FS.UPTAE = code, None
        g = FS.load()
        g["brand_raw"] = BH.merge_variants(g["brand_raw"])
        res[code] = {"label": label, **measure(g, today)}
    pc = lambda v: "-" if v is None else f"{v:.1%}"  # noqa: E731
    L = [f"\n##### 실측 생존율 공개판 {today:%Y-%m-%d} | 서울 인허가 | 정보공개서 신설 항목과 같은 모양(우리 근사) | 브랜드 이름 비공개"]
    for code, r in res.items():
        L.append(f"  {r['label']}: 가맹점 {r['franchise']['stores']:,} / 독립 {r['independent']['stores']:,} (영업 중)")
        for k, nm in (("franchise", "가맹 전체"), ("independent", "독립 전체")):
            v = r[k]
            yrs = "-" if v["closed_avg_years"] is None else f"{v['closed_avg_years']:.1f}년"
            L.append(f"    {nm}: 장기운영(5년+) {pc(v['long5'])} | 1년 생존 {pc(v['surv1'])} (n={v['n1']:,}) | 3년 생존 {pc(v['surv3'])} (n={v['n3']:,}) | "
                     f"폐점 평균 영업 {yrs} (n={v['n_closed']:,})")
        fy = r["first_year_by_open_year"]
        L.append("    개업 연도별 첫해 폐업률(가맹/독립): " + " ".join(f"{y}:{fy['franchise'].get(y, float('nan')):.0%}/{v:.0%}" for y, v in fy["independent"].items()))
        bs = pd.DataFrame(r["brands"]).T
        if len(bs):
            q = lambda c: bs[c].dropna().astype(float).quantile([0.1, 0.5, 0.9]).tolist() if bs[c].notna().any() else [np.nan] * 3  # noqa: E731
            for c, nm, f in (("long5", "장기운영 비율", "{:.0%}"), ("surv1", "1년 생존", "{:.0%}"), ("surv3", "3년 생존", "{:.0%}"), ("closed_avg_years", "폐점 평균 영업(년)", "{:.1f}")):
                L.append(f"    브랜드 {int(bs[c].notna().sum())}개 {nm} 하위10%/중앙/상위10%: " + " / ".join(f.format(x) for x in q(c)))
    L.append("  주의: 최근(2023~) 개업 코호트의 첫해 폐업률이 독립점에서 크게 올랐다. 실제 변화인지, 양도(지위승계)·업종 전환이 폐업으로 기록된 것인지는 아직 가리지 못했다"
             " - 그래서 1년 생존율은 '가맹 대 독립' 비교와 브랜드 분포로만 읽는다.")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": f"{today:%Y-%m-%d}", "min_n": MIN_N, "min_cohort": MIN_COHORT, "result": res}, fh, ensure_ascii=False)


def transfer():
    """H-2026-10-Z: 독립점 첫해 폐업 중 같은 자리(10m)에서 -30~+180일 안 같은 업종이 다시 연 비중과, 그것을 뺀 조정 첫해 폐업률."""
    from scipy.spatial import cKDTree
    today = pd.Timestamp.now().normalize()
    early, late = range(2014, 2022), range(2023, 2026)
    res, L = {}, [f"\n##### H-2026-10-Z 양도 착시 검정 {today:%Y-%m-%d} | 독립점 | 즉시 재개업 = 폐업 -30~+180일, 10m 안 같은 업종 개업"]
    for code, label in (("072405", "카페·휴게"), ("072404", "음식점")):
        FS.CODE, FS.UPTAE = code, None
        g = FS.load()
        ok = g["x"].notna() & g["y"].notna()
        tree = cKDTree(g.loc[ok, ["x", "y"]].to_numpy())
        pos = np.flatnonzero(ok.to_numpy())
        opn = g["open"].to_numpy()
        ind = g["brand_raw"].isna() & (g["open"] <= today - pd.DateOffset(years=1)) & g["open"].dt.year.between(2014, today.year)
        y1 = ind & g["failed"] & g["close"].notna() & ((g["close"] - g["open"]).dt.days <= 365)
        reopen = np.zeros(len(g), dtype=bool)
        idx = np.flatnonzero((y1 & ok).to_numpy())
        nb = tree.query_ball_point(g.loc[idx, ["x", "y"]].to_numpy(), r=10.0)
        cls = g["close"].to_numpy()
        for i, near in zip(idx, nb):
            j = pos[near]
            j = j[j != i]
            d = (opn[j] - cls[i]) / np.timedelta64(1, "D")
            reopen[i] = bool(((d >= -30) & (d <= 180)).any())
        reopen = pd.Series(reopen, index=g.index)
        yr = g["open"].dt.year
        rows = {}
        for y in range(2014, today.year + 1):
            m = ind & (yr == y)
            if not m.any():
                continue
            miss = float((~ok[m]).mean())
            n_y1 = int(y1[m].sum())
            rows[y] = {"n": int(m.sum()), "coord_missing": round(miss, 4), "y1": float(y1[m].mean()),
                       "reopen_share": float(reopen[m & y1].mean()) if n_y1 else None,
                       "adj_y1": float((y1 & ~reopen)[m].mean()), "use": miss <= 0.3}

        def avg(yrs, k):
            v = [rows[y][k] for y in yrs if y in rows and rows[y]["use"] and rows[y][k] is not None]
            return float(np.mean(v)) if v else None
        e_s, l_s, e_a, l_a = avg(early, "reopen_share"), avg(late, "reopen_share"), avg(early, "adj_y1"), avg(late, "adj_y1")
        z1 = bool(l_s is not None and e_s and l_s >= 2 * e_s)
        z2 = bool(l_a is not None and e_a and l_a <= 1.3 * e_a)
        verdict = "양도 착시" if z1 and z2 else ("실제 증가" if l_a and e_a and l_a >= 1.5 * e_a else "혼합")
        res[code] = {"label": label, "years": rows, "early_reopen": e_s, "late_reopen": l_s, "early_adj": e_a, "late_adj": l_a,
                     "Z1": z1, "Z2": z2, "verdict": verdict}
        L.append(f"  {label}: 개업 연도 n / 첫해 폐업 / 그중 즉시 재개업 / 조정 첫해 폐업 / 좌표 결측")
        for y, r in rows.items():
            rs = "-" if r["reopen_share"] is None else f"{r['reopen_share']:.0%}"
            L.append(f"    {y}: {r['n']:,} / {r['y1']:.1%} / {rs} / {r['adj_y1']:.1%} / {r['coord_missing']:.0%}{'' if r['use'] else ' (제외)'}")
        f = lambda v: "-" if v is None else f"{v:.1%}"  # noqa: E731
        L.append(f"    재개업 비중 2014~21 {f(e_s)} -> 2023~25 {f(l_s)} (Z1 {'성립' if z1 else '기각'}) | "
                 f"조정 첫해 폐업 {f(e_a)} -> {f(l_a)} (Z2 {'성립' if z2 else '기각'}) | 판정: {verdict}")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(os.path.join(ROOT, "data", "caed", "survival_transfer.json"), "w", encoding="utf-8") as fh:
        json.dump({"asof": f"{today:%Y-%m-%d}", "result": res}, fh, ensure_ascii=False)


if __name__ == "__main__":
    transfer() if sys.argv[1:] == ["transfer"] else main()

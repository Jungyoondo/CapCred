"""유령 인허가 - 인허가 대장의 '영업 중'이 실제 상가 목록(소상공인시장진흥공단 상가정보 2026-06)에 있는지 업소 단위로 대조 (2026-10-20).

python -X utf8 -m caed.ghost_permits     # -> data/caed/GHOST_PERMITS.txt, ghost_permits.json
python -X utf8 -m caed.ghost_permits follow   # H-2026-10-AD 유령 표시 -> 이후 장부 폐업 (ghost_permits_follow.json)

왜: 대장 포착률(대장 폐업 / 상권분석 폐업)이 헬스장 17%였다. 폐업 신고 없이 사라진 '유령'과 양도로 이름만 바뀐 곳을 업소 단위로 재 본다.
  사업 쪽 의미: (1) 인허가 대장으로 만든 폐업 통계·모델의 편향 크기, (2) 대출 심사의 '사업장 실재 확인(KYB)' 데이터 상품 가능성.
대조: 대장 영업 중(2026-03 이전 인허가 - 스냅샷 2026-06보다 늦게 연 곳 제외) 업소 좌표(EPSG:5174 -> WGS84)에서 반경 30m 안에
  같은 업종(상가정보 소분류) 점포가 있으면 '있음'. 그중 상호가 비슷하면(정규화 후 한쪽이 다른 쪽을 포함하거나 공통 3글자 이상) '같은 이름',
  아니면 '같은 자리 다른 이름'(양도·재창업 추정). 없으면 '못 찾음'(유령 후보). 상호는 대조에만 쓰고 결과에는 집계만.
업종 대응: 헬스장 104201 -> 헬스장, 미용 051801 -> 미용실, 세탁 062001 -> 세탁소, 커피숍(072405 중 업태 커피숍) -> 카페.
한계: 상가정보 자체도 국세청·카드사 기반 추정 목록이라 누락·지연이 있다. 같은 건물 안 같은 업종이 여럿이면 '있음'이 과대.
사전 가설(2026-10-20, 결과 전 커밋):
  G1 헬스장 대장 영업 중의 '못 찾음' 비율 >= 15%.
  G2 업력 10년+ 인허가의 '못 찾음' 비율이 업력 3년 미만의 1.5배 이상인 업종이 4개 중 3개 이상.
  G3 찾은 곳 중 '같은 자리 다른 이름' 비율이 업력 10년+에서 3년 미만보다 높은 업종이 4개 중 3개 이상.
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import localdata as LD  # noqa: E402
from caed import store_registry as SR  # noqa: E402

TXT = os.path.join(ROOT, "data", "caed", "GHOST_PERMITS.txt")
JSN = os.path.join(ROOT, "data", "caed", "ghost_permits.json")
MAP = {"104201": ("헬스장", ["헬스장"], None), "051801": ("미용실", ["미용실"], None), "062001": ("세탁소", ["세탁소"], None),
       "072405": ("카페", ["카페"], "커피숍")}
R = 30.0
CUTOFF = pd.Timestamp("2026-03-31")
AGE_BINS, AGE_LAB = [0, 3, 10, 80], ["<3년", "3-10년", "10년+"]


def norm(s):
    s = re.sub(r"\(.*?\)|\[.*?\]", "", str(s)).lower()
    s = re.sub(r"[^0-9a-z가-힣]", "", s)
    return re.sub(r"(점|본점|지점)$", "", s)


def similar(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return any(a[i:i + 3] in b for i in range(len(a) - 2))


def registry(code, uptae):
    n = pd.read_csv(os.path.join(LD.OUT, f"{code}.names.csv"), dtype=str, keep_default_na=False)
    if uptae:
        m = pd.read_csv(os.path.join(LD.OUT, f"{code}.csv"), dtype=str, keep_default_na=False)
        m = m.apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)
        keep = set(zip(m.loc[m["UPTAENM"] == uptae, "MGTNO"], m.loc[m["UPTAENM"] == uptae, "APVPERMYMD"]))
        n = n[[k in keep for k in zip(n["MGTNO"], n["APVPERMYMD"])]]
    n = n[n["DTLSTATENM"].isin(["영업중", "영업", "정상영업"])]
    n = n.assign(open=pd.to_datetime(n["APVPERMYMD"], format="%Y-%m-%d", errors="coerce"),
                 x=pd.to_numeric(n["X"], errors="coerce"), y=pd.to_numeric(n["Y"], errors="coerce"))
    n = n.dropna(subset=["open", "x", "y"])
    return n[n["open"] <= CUTOFF].reset_index(drop=True)


def follow():
    """H-2026-10-AD: 2026-06-30 장부상 영업 중 업소를 상가정보와 대조한 상태별로, 그 뒤 장부 폐업이 찍힌 비율."""
    import pyproj
    from scipy.spatial import cKDTree
    T = pd.Timestamp("2026-06-30")
    stores, ym = SR.latest()
    to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:5174", always_xy=True)
    sx, sy = to_m.transform(pd.to_numeric(stores["lon"], errors="coerce").to_numpy(), pd.to_numeric(stores["lat"], errors="coerce").to_numpy())
    stores = stores.assign(x=sx, y=sy).dropna(subset=["x", "y"])
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    rows, res = [], {}
    for code, (name, cats, uptae) in MAP.items():
        m = pd.read_csv(os.path.join(LD.OUT, f"{code}.csv"), dtype=str, keep_default_na=False)
        m = m.apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)
        if uptae:
            m = m[m["UPTAENM"] == uptae]
        n = pd.read_csv(os.path.join(LD.OUT, f"{code}.names.csv"), dtype=str, keep_default_na=False)[["MGTNO", "APVPERMYMD", "BPLCNM"]]
        r = m.merge(n.drop_duplicates(["MGTNO", "APVPERMYMD"]), on=["MGTNO", "APVPERMYMD"])
        r = r.assign(open=pd.to_datetime(r["APVPERMYMD"], format="%Y-%m-%d", errors="coerce"),
                     close=pd.to_datetime(r["DCBYMD"].str[:10], format="%Y-%m-%d", errors="coerce"),
                     x=pd.to_numeric(r["X"], errors="coerce"), y=pd.to_numeric(r["Y"], errors="coerce")).dropna(subset=["open", "x", "y"])
        end = r["close"].max()
        r = r[(r["open"] <= CUTOFF) & (r["close"].isna() | (r["close"] > T))].reset_index(drop=True)
        st = stores[stores["indsSclsNm"].isin(cats)].reset_index(drop=True)
        hits = cKDTree(st[["x", "y"]].to_numpy()).query_ball_point(r[["x", "y"]].to_numpy(), R)
        r["status"] = ["못 찾음" if not h else "같은 이름" if any(similar(nm, st.at[j, "bizesNm"]) or similar(nm, st.at[j, "bizesNm"] + st.at[j, "brchNm"]) for j in h)
                       else "다른 이름" for nm, h in zip(r["BPLCNM"], hits)]
        r["closed"] = r["close"].notna() & (r["close"] > T)
        rate = r.groupby("status")["closed"].agg(["mean", "size", "sum"])
        res[code] = {"name": name, "end": f"{end:%Y-%m-%d}", **{s: {"rate": float(v["mean"]), "n": int(v["size"]), "closed": int(v["sum"])} for s, v in rate.iterrows()}}
        rows.append(r[["status", "closed"]])
    A = pd.concat(rows)
    pool = A.groupby("status")["closed"].mean()
    ad1 = pool.get("못 찾음", 0) >= 2 * pool.get("같은 이름", np.nan)
    ratios = {c: v["못 찾음"]["rate"] / v["같은 이름"]["rate"] if v.get("같은 이름", {}).get("rate") else float("inf") for c, v in res.items()}
    ad2 = sum(x >= 1.5 for x in ratios.values()) >= 3
    L = [f"\n##### H-2026-10-AD 유령 표시 -> 이후 장부 폐업 {stamp} | 2026-06-30 장부 영업 중 vs 상가정보 {ym} | 결과 2026-07-01~데이터 마지막 날"]
    for c, v in res.items():
        L.append(f"  {v['name']:<5} (마지막 {v['end']}) " + " | ".join(f"{s} {v[s]['closed']}/{v[s]['n']:,} {v[s]['rate']:.2%}" for s in ("못 찾음", "같은 이름", "다른 이름") if s in v)
                 + f" | 배수 {ratios[c]:.1f}")
    L += [f"  합계 못 찾음 {pool.get('못 찾음', 0):.2%} · 같은 이름 {pool.get('같은 이름', 0):.2%} · 다른 이름 {pool.get('다른 이름', 0):.2%} -> 배수 {pool.get('못 찾음', 0) / pool.get('같은 이름', np.nan):.1f}",
          f"  사전 가설: AD1 합계 2배+ {'성립' if ad1 else '기각'} | AD2 1.5배+ 업종 {sum(x >= 1.5 for x in ratios.values())}/4 {'성립' if ad2 else '기각'} -> "
          + ("③ 리포트에 '영업 실재 의심' 표시" if ad1 and ad2 else "표시는 참고(미검증)로만")]
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN.replace(".json", "_follow.json"), "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "snapshot": ym, "industries": res, "pooled": {k: float(v) for k, v in pool.items()}, "ratios": ratios,
                   "AD1": bool(ad1), "AD2": bool(ad2)}, fh, ensure_ascii=False, indent=1)


def main():
    import pyproj
    from scipy.spatial import cKDTree
    stores, ym = SR.latest()
    to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:5174", always_xy=True)
    sx, sy = to_m.transform(pd.to_numeric(stores["lon"], errors="coerce").to_numpy(), pd.to_numeric(stores["lat"], errors="coerce").to_numpy())
    stores = stores.assign(x=sx, y=sy).dropna(subset=["x", "y"])
    res, L = {}, []
    stamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    L.append(f"\n##### 유령 인허가 대조 {stamp} | 서울 인허가 '영업 중'(~2026-03 인허가) vs 상가정보 {ym} | 반경 {R:.0f}m 같은 업종")
    for code, (name, cats, uptae) in MAP.items():
        reg = registry(code, uptae)
        st = stores[stores["indsSclsNm"].isin(cats)].reset_index(drop=True)
        tree = cKDTree(st[["x", "y"]].to_numpy())
        hits = tree.query_ball_point(reg[["x", "y"]].to_numpy(), R)
        status = []
        for nm, h in zip(reg["BPLCNM"], hits):
            if not h:
                status.append("못 찾음")
            elif any(similar(nm, st.at[j, "bizesNm"]) or similar(nm, st.at[j, "bizesNm"] + st.at[j, "brchNm"]) for j in h):
                status.append("같은 이름")
            else:
                status.append("다른 이름")
        reg["status"] = status
        reg["age"] = (CUTOFF - reg["open"]).dt.days / 365.25
        reg["ageb"] = pd.cut(reg["age"], AGE_BINS, labels=AGE_LAB)
        tab = reg.groupby("ageb", observed=True)["status"].value_counts(normalize=True).unstack().fillna(0)
        found = reg[reg["status"] != "못 찾음"]
        other = found.groupby("ageb", observed=True)["status"].apply(lambda s: float((s == "다른 이름").mean()))
        tot = reg["status"].value_counts(normalize=True)
        r = {"name": name, "registry_operating": int(len(reg)), "stores_listed": int(len(st)),
             "ghost": float(tot.get("못 찾음", 0)), "same_name": float(tot.get("같은 이름", 0)), "other_name": float(tot.get("다른 이름", 0)),
             "ghost_by_age": {str(a): float(tab.loc[a].get("못 찾음", 0)) for a in tab.index},
             "other_share_found_by_age": {str(a): float(v) for a, v in other.items()},
             "n_by_age": {str(a): int(v) for a, v in reg["ageb"].value_counts().items()}}
        gy, go = r["ghost_by_age"].get("<3년", np.nan), r["ghost_by_age"].get("10년+", np.nan)
        r["G2"] = bool(go >= 1.5 * gy) if gy > 0 else bool(go > 0)
        r["G3"] = bool(r["other_share_found_by_age"].get("10년+", 0) > r["other_share_found_by_age"].get("<3년", 0))
        res[code] = r
        L.append(f"  {name:<5} 대장 영업 중 {len(reg):>6,} | 상가정보 {len(st):>6,} | 못 찾음 {r['ghost']:.0%} · 같은 이름 {r['same_name']:.0%} · 같은 자리 다른 이름 {r['other_name']:.0%} | "
                 "못 찾음 업력별 " + " ".join(f"{a} {v:.0%}" for a, v in r["ghost_by_age"].items())
                 + " | 다른 이름(찾은 곳 중) " + " ".join(f"{a} {v:.0%}" for a, v in r["other_share_found_by_age"].items()))
    g1 = res["104201"]["ghost"] >= 0.15
    g2 = sum(r["G2"] for r in res.values())
    g3 = sum(r["G3"] for r in res.values())
    L.append(f"  사전 가설: G1 헬스장 못 찾음 15%+ {'성립' if g1 else '기각'} | G2 오래된 인허가가 1.5배+ 유령 {g2}/4 {'성립' if g2 >= 3 else '기각'} | "
             f"G3 오래될수록 다른 이름 {g3}/4 {'성립' if g3 >= 3 else '기각'}")
    txt = "\n".join(L)
    print(txt)
    with open(TXT, "a", encoding="utf-8") as fh:
        fh.write(txt + "\n")
    with open(JSN, "w", encoding="utf-8") as fh:
        json.dump({"asof": stamp, "snapshot": ym, "radius_m": R, "industries": res, "G1": g1, "G2": g2, "G3": g3}, fh, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    follow() if sys.argv[1:] == ["follow"] else main()

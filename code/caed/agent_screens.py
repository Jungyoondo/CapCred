"""묶음 그림의 ③·④ 시연 화면 (2026-10-26, AI 영화·보고서 합성용 - docs/business/BUSINESS_FINAL_BRIEF_2026-10-26.md 9절).

python -X utf8 -m caed.agent_screens
  -> deliverables/business/screen_loan.html/.png      ③ 은행 대출 사후점검 '차주 1장'(가명 가게 하나)
  -> deliverables/business/screen_register.html/.png  ④ 구청 인허가 대장 정비 목록(가명 업소, 구 하나)

둘 다 점수를 내지 않는다. 기록을 한 장으로 모을 뿐이다.
③의 '상가 목록에 없음' 표시는 H-2026-10-AD 기각이라 '참고(미검증)'로 적는다.
가명 규칙(사용자 10-25): 상호·주소는 싣지 않는다. 구 이름과 업종, 날짜만.
"""
import html
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import agent_public as AP  # noqa: E402
from caed import fdd_agent as A  # noqa: E402
from caed import ghost_permits as GP  # noqa: E402
from caed import store_registry as SR  # noqa: E402

GU = "마포구"
CSS = AP.page(pd.DataFrame(columns=["alias", "industry", "f0", "m0", "m1", "new", "closed", "transfer", "est", "alert", "f1", "hit", "dir"]),
              {"fy": 0, "deadline": "", "n_brands": 0, "n_events": 0, "n_transfer": 0, "n_alerts": 0, "n_filed": 0,
               "alert_hit": None, "alert_filed": 0, "mae_copy": None, "mae_agent": None}).split("<style>")[1].split("</style>")[0]


def listed(x, y, cats):
    """상가정보(2026-06)에서 반경 30m 같은 업종 점포가 있는지 - 좌표(EPSG:5174)마다 True/False."""
    import pyproj
    from scipy.spatial import cKDTree
    st, ym = SR.latest()
    to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:5174", always_xy=True)
    sx, sy = to_m.transform(pd.to_numeric(st["lon"], errors="coerce").to_numpy(), pd.to_numeric(st["lat"], errors="coerce").to_numpy())
    st = st.assign(x=sx, y=sy).dropna(subset=["x", "y"])
    st = st[st["indsSclsNm"].isin(cats)]
    tree = cKDTree(st[["x", "y"]].to_numpy())
    return [bool(h) for h in tree.query_ball_point(np.c_[x, y], GP.R)], st, ym


def wrap(title, body):
    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-top:12px}}
.row{{display:grid;grid-template-columns:160px 1fr;gap:6px 14px;font-size:14.5px}}.row div:nth-child(odd){{color:var(--mut)}}
.tag{{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12.5px;border:1px solid var(--line)}}</style></head><body><main>{body}</main></body></html>"""


def loan():
    """최근 18개월 안에 연 카페 중, 같은 자리(10m)에서 지난 10년간 가게가 가장 자주 바뀐 곳 하나."""
    from scipy.spatial import cKDTree
    g = A.stores("072405").dropna(subset=["x", "y"]).reset_index(drop=True)
    now = pd.Timestamp.now().normalize()
    cand = g[(~g["gone"]) & (g["open"] >= now - pd.DateOffset(months=18)) & (g["gu"] == GU)]
    tree = cKDTree(g[["x", "y"]].to_numpy())
    best = None
    for i, r in cand.iterrows():
        nb = g.loc[[j for j in tree.query_ball_point([r["x"], r["y"]], 10.0) if j != i]]
        if (~nb["gone"]).any():   # 같은 건물에 지금 영업 중인 다른 카페가 있으면(상가 건물·푸드코트) '같은 자리'가 아니다
            continue
        prev = nb[nb["gone"] & (nb["close"] <= r["open"] + pd.Timedelta(days=30)) & (nb["close"] >= r["open"] - pd.DateOffset(years=10))]
        if len(prev) <= 6 and (best is None or len(prev) > len(best[1])):
            best = (r, prev.sort_values("open"))
    r, prev = best
    ok, _, ym = listed([r["x"]], [r["y"]], ["카페"])
    life = lambda p: f"{(p['close'] - p['open']).days / 365.25:.1f}년"  # noqa: E731
    rows = "".join(f"<tr><td>{p['open']:%Y-%m}</td><td>{p['close']:%Y-%m}</td><td class=n>{life(p)}</td><td>{'가맹' if isinstance(p['brand_raw'], str) else '독립'}</td></tr>"
                   for _, p in prev.iterrows())
    turn = f"{len(prev)}번" if len(prev) else "없음"
    body = f"""<h1>대출 사후점검 — 차주 사업장 1장</h1>
<p class=sub>예시: {GU} · 카페(휴게음식점) · 가명 '가게 A' · 공공 기록 기준 {now:%Y-%m-%d} · 점수가 아니라 확인 자료입니다</p>
<div class=card><div class=row>
<div>인허가 상태</div><div><b>영업 중</b> (서울 지방행정 인허가)</div>
<div>인허가일</div><div>{r['open']:%Y-%m-%d} (개업 {(now - r['open']).days // 30}개월째)</div>
<div>업종</div><div>휴게음식점 · {html.escape(str(r['uptae'] or '커피숍'))}</div>
<div>같은 자리 지난 10년</div><div><b>{turn}</b> 가게가 바뀌었습니다 (반경 10m, 폐업 → 새 인허가)</div>
<div>상가 목록 대조({ym[:4]}-{ym[4:]})</div><div>{'같은 업종 점포 있음' if ok[0] else '같은 업종 점포 못 찾음'} <span class=tag>참고 · 미검증(H-2026-10-AD 기각)</span></div>
<div>다음 알림</div><div>매달 인허가 갱신 때 폐업·명의변경이 찍히면 알림</div>
</div></div>
<h2>같은 자리 이전 가게</h2>
<div class=tw><table><tr><th>개업</th><th>폐업</th><th class=n>영업 기간</th><th>구분</th></tr>{rows}</table></div>
<p class=note>점검 담당자가 서류만으로는 모르는 것(같은 자리의 교체 이력, 장부와 실제 목록의 차이)을 한 장으로 모았습니다. 현장점검 대상 선정과 판단은 금융기관이 합니다.
은행연합회 자금용도외 유용 사후점검준칙 개정(2026-07-30 시행): 개인사업자 5천만 원 초과 대출로 점검 대상 확대.</p>"""
    return wrap("차주 사업장 1장", body), {"turnovers": len(prev), "listed": ok[0]}


def register():
    """GU의 카페·미용실 - 장부상 영업 중(2026-03 이전 인허가)인데 상가정보에서 못 찾았거나 같은 자리에 다른 이름이 있는 곳."""
    out, tot = [], {}
    for code in ("072405", "051801"):
        name, cats, uptae = GP.MAP[code]
        reg = GP.registry(code, uptae)
        reg = reg.merge(pd.read_csv(os.path.join(GP.LD.OUT, f"{code}.csv"), dtype=str, keep_default_na=False)[["MGTNO", "APVPERMYMD", "gu"]],
                        on=["MGTNO", "APVPERMYMD"], how="left")
        reg = reg[reg["gu"] == GU].reset_index(drop=True)
        ok, st, ym = listed(reg["x"].to_numpy(), reg["y"].to_numpy(), cats)
        from scipy.spatial import cKDTree
        st = st.reset_index(drop=True)
        hits = cKDTree(st[["x", "y"]].to_numpy()).query_ball_point(reg[["x", "y"]].to_numpy(), GP.R)
        reg["status"] = ["못 찾음" if not h else "같은 이름" if any(GP.similar(nm, st.at[j, "bizesNm"]) or GP.similar(nm, st.at[j, "bizesNm"] + st.at[j, "brchNm"]) for j in h)
                         else "같은 자리 다른 이름" for nm, h in zip(reg["BPLCNM"], hits)]
        reg["업종"] = name
        tot[name] = reg["status"].value_counts().to_dict() | {"n": len(reg)}
        out.append(reg[reg["status"] != "같은 이름"])
    L = pd.concat(out).sort_values("open").reset_index(drop=True)
    sample = L.groupby(["업종", "status"], sort=False).head(4).sort_values("open")   # 업종 x 대조 결과마다 가장 오래된 4곳
    rows = "".join(f"<tr><td>업소 {i + 1:03d}</td><td>{r['업종']}</td><td>{r['open']:%Y-%m-%d}</td><td class=n>{(pd.Timestamp('2026-06-30') - r['open']).days / 365.25:.0f}년</td>"
                   f"<td>{'<span class=al>상가 목록에 없음</span>' if r['status'] == '못 찾음' else '같은 자리에 다른 이름'}</td></tr>"
                   for i, (_, r) in enumerate(sample.iterrows()))
    cards = "".join(f"<div class=k><div class=kl>{k} 장부 영업 중</div><div class=kv>{v['n']:,}곳</div>"
                    f"<div class=ks>목록에 없음 {v.get('못 찾음', 0):,} · 같은 자리 다른 이름 {v.get('같은 자리 다른 이름', 0):,}</div></div>" for k, v in tot.items())
    body = f"""<h1>인허가 대장 정비 — 확인 우선 목록</h1>
<p class=sub>예시: {GU} · 카페·미용실 · 장부 '영업 중'(2026-03 이전 인허가) vs 상가정보 {ym[:4]}-{ym[4:]} · 업소는 가명</p>
<div class=kp>{cards}</div>
<h2>확인 목록 (일부)</h2>
<div class=tw><table><tr><th>업소</th><th>업종</th><th>인허가일</th><th class=n>업력</th><th>대조 결과</th></tr>{rows}</table></div>
<p class=note>'상가 목록에 없음'은 폐업 확정이 아닙니다(상가정보에도 누락이 있음). 이후 3.7개월 장부 폐업률은 목록에 없음 2.6%, 같은 이름 1.7%, 같은 자리 다른 이름 2.9%였습니다(H-2026-10-AD, 예측 표시로는 기각).
현장 확인 순서를 정하는 참고 자료이며, 처분은 담당 기관이 판단합니다.</p>"""
    return wrap("대장 정비 목록", body), tot


def shot(name, h):
    import subprocess
    edge = next(p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
                if os.path.exists(p))
    hp, png = os.path.join(AP.PUB, f"{name}.html"), os.path.join(AP.PUB, f"{name}.png")
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size=1280,{h}",
                    f"--user-data-dir={os.path.join(os.environ.get('TEMP', ROOT), 'edge_shot_profile')}",
                    f"--screenshot={png}", "file:///" + hp.replace("\\", "/")], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return png


def main():
    os.makedirs(AP.PUB, exist_ok=True)
    for name, fn, h in (("screen_loan", loan, 1100), ("screen_register", register, 1100)):
        page, info = fn()
        with open(os.path.join(AP.PUB, f"{name}.html"), "w", encoding="utf-8") as fh:
            fh.write(page)
        print(name, info, shot(name, h))


if __name__ == "__main__":
    main()

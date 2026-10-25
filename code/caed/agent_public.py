"""정보공개서 정기변경 에이전트 - 지난 시즌 재현 공개판 (2026-10-25, 사업 재설계 2단계 시연용).

python -X utf8 -m caed.agent_public [--fy 2025]
  -> data/caed/agent/replay_FY<연도>.csv            (실명, 로컬 전용)
  -> deliverables/business/agent_replay_public.json (A브랜드·B브랜드 가명)
  -> deliverables/business/agent_demo.html          (가명 공개 화면 - 녹화·보고서 캡처용)
  -> deliverables/business/agent_demo.png           (Edge headless 캡처, --shot 이면 캡처만)

무엇: 서울 외식 등록 브랜드(작년 신고 서울 10곳+) 전부에 에이전트를 돌려, 회계년도 말 기준
  (1) 작년 신고 서울 매장 수, (2) 인허가 실측 변동(신규·폐업·명의변경 추정), (3) 올해 서울 예상값 = 작년 신고 x (1 + 실측 증감률),
  (4) 변동 경보(|예상 - 작년| >= max(3, 10%)), (5) 실제 올해 신고가 이미 공개됐으면 그 값과 적중 여부를 나란히 둔다.
  예상값·경보 규칙은 H-2026-10-AC(사전 등록, 성립)와 같다. 매칭은 AB2(v2) 규칙(외식, 정규화 이름 정확 일치).
공개 범위(사용자 10-25): 공개 화면에는 브랜드 이름·주소를 싣지 않는다. 업종 + 가명만.
"""
import argparse
import html
import json
import os
import string
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import fdd_agent as A  # noqa: E402
from caed import ftc_brands as F  # noqa: E402
from caed import ftc_frcs as FF  # noqa: E402

PUB = os.path.join(ROOT, "deliverables", "business")


def alias(i):
    s, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        s = string.ascii_uppercase[r] + s
    return f"{s}브랜드"


def build(fy):
    t0, t1 = pd.Timestamp(f"{fy - 1}-12-31"), pd.Timestamp(f"{fy}-12-31")
    ftc = F.load()
    ftc = ftc[ftc["indutyLclasNm"] == "외식"]
    keys = set(ftc["key"])
    fdd = FF.load()
    fdd = fdd[fdd["indutyLclasNm"] == "외식"].merge(ftc[["brandMnno", "key"]].drop_duplicates("brandMnno"), on="brandMnno")
    fdd = fdd[fdd["tot"] > 0].groupby(["key", "fy"])["n_fdd"].sum()   # 전체 0인 빈 신고는 미공개로 본다
    ind = ftc.sort_values("yr").drop_duplicates("key", keep="last").set_index("key")["indutyMlsfcNm"]
    rows = []
    for code in A.LABEL:
        g = A.stores(code)
        g = g[g["brand_raw"].notna()]
        g["key"] = g["brand_raw"].map(F.norm)
        g = g[g["key"].isin(keys)]
        for k, b in g.groupby("key"):
            alive = lambda t: int(((b["open"] <= t) & ~(b["gone"] & (b["close"] <= t))).sum())  # noqa: E731
            new = b[(b["open"] > t0) & (b["open"] <= t1)]
            end = b[b["failed"] & (b["close"] > t0) & (b["close"] <= t1)]
            tc, _ = A.transfers(b) if len(end) else (set(), set())
            rows.append({"key": k, "brand": b["brand_raw"].iloc[0], "code": code, "m0": alive(t0), "m1": alive(t1), "new": len(new),
                         "closed": len(end), "transfer": len(end[end.index.isin(tc)])})
    R = pd.DataFrame(rows).groupby("key").agg(brand=("brand", "first"), m0=("m0", "sum"), m1=("m1", "sum"), new=("new", "sum"),
                                              closed=("closed", "sum"), transfer=("transfer", "sum"))
    R["f0"] = [fdd.get((k, fy - 1), np.nan) for k in R.index]
    R["f1"] = [fdd.get((k, fy), np.nan) for k in R.index]
    R = R[R["f0"] >= FF.MIN_STORES].copy()
    R["industry"] = ind.reindex(R.index).values
    R["est"] = R["f0"] * (1 + (R["m1"] - R["m0"]) / np.maximum(R["m0"], 5))
    R["alert"] = (R["est"] - R["f0"]).abs() >= np.maximum(3, 0.1 * R["f0"])
    R["dir"] = np.sign(R["est"] - R["f0"])
    filed = R["f1"].notna()
    R["hit"] = np.where(filed & R["alert"], np.sign(R["f1"] - R["f0"]) == R["dir"], np.nan)
    R = R.sort_values("f0", ascending=False)
    R["alias"] = [alias(i) for i in range(len(R))]
    F_ = R[R["f1"].notna()]
    stats = {"fy": fy, "deadline": f"{(t1 + pd.Timedelta(days=120)).date()}", "n_brands": len(R), "n_stores_fdd": int(R["f0"].sum()),
             "n_events": int((R["new"] + R["closed"]).sum()), "n_transfer": int(R["transfer"].sum()), "n_alerts": int(R["alert"].sum()),
             "n_filed": int(filed.sum()),
             "mae_copy": float((F_["f1"] - F_["f0"]).abs().mean()) if len(F_) else None,
             "mae_agent": float((F_["f1"] - F_["est"]).abs().mean()) if len(F_) else None,
             "alert_filed": int(F_["alert"].sum()), "alert_hit": float(F_.loc[F_["alert"], "hit"].mean()) if F_["alert"].any() else None}
    return R, stats


def page(R, S):
    e = html.escape
    top = R.head(40)
    tr = []
    for _, r in top.iterrows():
        res = "" if pd.isna(r["f1"]) else f"{int(r['f1'])}"
        hit = "" if pd.isna(r["hit"]) else ("<span class=ok>맞음</span>" if r["hit"] else "<span class=no>빗나감</span>")
        al = f"<span class=al>{'▲ 증가' if r['dir'] > 0 else '▼ 감소'}</span>" if r["alert"] else "<span class=mut>-</span>"
        tr.append(f"<tr><td>{e(r['alias'])}</td><td>{e(str(r['industry'] or ''))}</td><td class=n>{int(r['f0'])}</td>"
                  f"<td class=n>{int(r['m0'])} → {int(r['m1'])}</td><td class=n>{int(r['new'])} / {int(r['closed'])} / {int(r['transfer'])}</td>"
                  f"<td class=n><b>{r['est']:.0f}</b></td><td>{al}</td><td class=n>{res}</td><td>{hit}</td></tr>")
    gain = (1 - S["mae_agent"] / S["mae_copy"]) if S["mae_copy"] else None
    kp = [("대상 브랜드", f"{S['n_brands']:,}개", f"서울 외식 · 작년 신고 10곳+"),
          ("확인할 매장 변동", f"{S['n_events']:,}건", f"신규·폐업, 명의변경 추정 {S['n_transfer']:,}건"),
          ("에이전트 경보", f"{S['n_alerts']:,}개", "신고 숫자가 크게 바뀔 브랜드"),
          ("실제 신고와 비교", f"{S['alert_hit']:.0%}" if S["alert_hit"] is not None else "-",
           f"경보 적중(신고 공개 {S['n_filed']:,}개 중 경보 {S['alert_filed']:,}개)")]
    if gain is not None:
        kp.append(("숫자 오차", f"-{gain:.0%}", f"작년 숫자 복사 {S['mae_copy']:.1f}곳 → 에이전트 {S['mae_agent']:.1f}곳"))
    cards = "".join(f"<div class=k><div class=kl>{e(a)}</div><div class=kv>{e(b)}</div><div class=ks>{e(c)}</div></div>" for a, b, c in kp)
    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>정기변경 에이전트 시연</title><style>
:root{{--bg:#f7f6f2;--card:#fff;--ink:#1d1d1b;--mut:#6b6a66;--line:#e3e1da;--acc:#1f5f8b;--ok:#2e7d4f;--no:#b23b3b;--al:#b86e00}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151514;--card:#1f1f1d;--ink:#ecebe6;--mut:#a3a29c;--line:#34342f;--acc:#6fb0dc;--ok:#6cc08c;--no:#e07c7c;--al:#e0a64a}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Pretendard","Apple SD Gothic Neo","Malgun Gothic",sans-serif}}
main{{max-width:1080px;margin:0 auto;padding:28px 16px 48px}}h1{{font-size:24px;margin:0 0 4px}}h2{{font-size:17px;margin:28px 0 10px}}
.sub{{color:var(--mut);margin:0 0 18px}}.ks,.kl,.mut{{color:var(--mut)}}
.kp{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}
.k{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}.kl{{font-size:13px}}.kv{{font-size:26px;font-weight:700;color:var(--acc)}}.ks{{font-size:12px}}
.flow{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}}.flow div{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;font-size:14px}}
.flow b{{color:var(--acc)}}.tw{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}}
table{{border-collapse:collapse;width:100%;font-size:13.5px}}th,td{{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}}
th{{color:var(--mut);font-weight:600}}.n{{text-align:right;font-variant-numeric:tabular-nums}}.ok{{color:var(--ok)}}.no{{color:var(--no)}}.al{{color:var(--al);font-weight:600}}
.note{{color:var(--mut);font-size:12.5px;margin-top:10px}}</style></head><body><main>
<h1>정보공개서 정기변경 에이전트 — 지난 시즌 재현</h1>
<p class=sub>회계년도 {S['fy']} · 정기변경 기한 {S['deadline']} · 서울 인허가 공공 기록 + 공정위 가맹정보 · 브랜드는 가명(A브랜드, B브랜드…)</p>
<div class=kp>{cards}</div>
<h2>에이전트가 하는 일</h2>
<div class=flow><div><b>1. 모은다</b><br>작년 정보공개서 숫자(공정위)와 올해 인허가 개업·폐업 기록</div>
<div><b>2. 가른다</b><br>신규·폐업, 같은 자리 재개업은 명의변경 추정으로 분리</div>
<div><b>3. 미리 채운다</b><br>올해 서울 매장 수 예상값과 변동 경보</div>
<div><b>4. 넘긴다</b><br>대조 체크리스트 → 가맹거래사·본부가 검토·서명·제출</div></div>
<h2>브랜드별 결과 (작년 신고 서울 매장 수 상위 40개)</h2>
<div class=tw><table><tr><th>브랜드</th><th>업종</th><th class=n>작년 신고</th><th class=n>인허가 실측</th><th class=n>신규/폐업/명의변경</th><th class=n>에이전트 예상</th><th>경보</th><th class=n>실제 신고</th><th>경보 결과</th></tr>
{''.join(tr)}</table></div>
<p class=note>예상값 = 작년 신고 서울 매장 수 x (1 + 인허가 실측 증감률). 경보 = 예상과 작년 차이가 3곳 또는 10% 이상. 같은 규칙을 2019~2025 회계년도 879개 브랜드에 사전 등록 검정(H-2026-10-AC)한 결과,
작년 숫자를 그대로 쓰는 것보다 오차가 16.8% 작았고 경보의 83.2%가 실제 같은 방향으로 바뀌었다. 인허가 실측은 신고 매장의 약 2/3만 잡으므로 실측 숫자를 그대로 신고값으로 쓰지 않는다.
'실제 신고' 칸이 비어 있으면 아직 공정위에 공개되지 않은 브랜드다. 이 화면은 정보공개서 작성 자문·등록 대행이 아니다(가맹사업법 제28조, 등록 가맹거래사 업무).</p>
</main></body></html>"""


def shot():
    import subprocess
    edge = next(p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")
                if os.path.exists(p))
    hp, png = os.path.join(PUB, "agent_demo.html"), os.path.join(PUB, "agent_demo.png")
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--window-size=1280,2020",
                    f"--user-data-dir={os.path.join(os.environ.get('TEMP', ROOT), 'edge_shot_profile')}",
                    f"--screenshot={png}", "file:///" + hp.replace("\\", "/")], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("demo ->", png)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fy", type=int, default=2025)
    ap.add_argument("--shot", action="store_true")
    a = ap.parse_args()
    if a.shot:
        return shot()
    R, S = build(a.fy)
    R.to_csv(os.path.join(A.OUT, f"replay_FY{a.fy}.csv"), encoding="utf-8-sig")
    os.makedirs(PUB, exist_ok=True)
    pub = R[["alias", "industry", "f0", "m0", "m1", "new", "closed", "transfer", "est", "alert", "f1", "hit"]].reset_index(drop=True)
    with open(os.path.join(PUB, "agent_replay_public.json"), "w", encoding="utf-8") as fh:
        json.dump({"stats": S, "brands": json.loads(pub.to_json(orient="records", force_ascii=False))}, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(PUB, "agent_demo.html"), "w", encoding="utf-8") as fh:
        fh.write(page(R, S))
    print(json.dumps(S, ensure_ascii=False, indent=1))
    shot()


if __name__ == "__main__":
    main()

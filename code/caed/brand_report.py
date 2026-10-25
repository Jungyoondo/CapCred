"""브랜드 건강도 리포트 한 장 (HTML) - 은행·보증기관 파일럿에 들고 가는 결과물 (2026-10-21).

python -X utf8 -m caed.brand_report 메가            # 내부용(브랜드 이름 포함) -> data/caed/reports/<브랜드>.html (git 제외)
python -X utf8 -m caed.brand_report --demo         # 익명 시연용 2장(쇠퇴·성장 각 1) -> deliverables/pilot/brand_report_demo_*.html

내용: 서울 매장 36개월 추이, 직전 12개월 개업·폐업, 성장·쇠퇴 3분위, 그 3분위의 검증 폐업률과 대출 1건 기대손실(가정 명시),
  같은 자리 다음 점포(갈아타기·같은 브랜드 재개업), 공정위 정보공개서 등록, 근거와 한계.
원칙: 브랜드 이름은 H-2026-10-D 판정(2027-10) 전 공개 금지 - 내부 파일은 data/에만, 시연본은 익명 + 매장 수 10단위 반올림 + 개시 연도만.
  점수는 브랜드 순증가율 3분위만(사전 등록·검증된 것). 갈아타기·브랜드 나이는 설명용(D2b·X3 결과).
"""
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import brand_health as BH  # noqa: E402

OUT_INT = os.path.join(ROOT, "data", "caed", "reports")
OUT_DEMO = os.path.join(ROOT, "deliverables", "pilot")
LOAN, PD_GIVEN_CLOSE, LGD = 50_000_000, 0.5, 0.7


def tier_rates():
    """검증(2021~24) 3분위 다음 1년 폐업률 - caed/franchise_survival.py momentum 결과."""
    out = {}
    for code, f in (("072405", "franchise_survival.json"), ("072404", "franchise_survival_072404.json")):
        with open(os.path.join(ROOT, "data", "caed", f), encoding="utf-8") as fh:
            r = json.load(fh)["momentum"]["result"]["검증 2021~24"]
        out[code] = {"쇠퇴": r["low"], "중간": r["mid"], "성장": r["high"]}
    return out


def spark(series, months, w=640, h=150, fmt=lambda v: f"{v:,}"):
    lo0, hi0 = min(series), max(series)
    pad = max(0.15 * hi0, 1)                 # 축을 너무 좁히면 작은 변화가 과장된다 - 최대값의 15% 이상 여유
    lo, hi = max(lo0 - pad, 0), hi0 + pad / 3
    rng = max(hi - lo, 1)
    pts = [(20 + i * (w - 40) / (len(series) - 1), h - 25 - (v - lo) / rng * (h - 50)) for i, v in enumerate(series)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}" for i, (x, y) in enumerate(pts))
    lab = "".join(f'<text x="{pts[i][0]:.0f}" y="{h - 6}" font-size="11" text-anchor="middle" fill="var(--mut)">{months[i]}</text>'
                  for i in (0, len(series) // 2, len(series) - 1))
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="매장 수 추이">'
            f'<path d="{path}" fill="none" stroke="var(--acc)" stroke-width="2.5"/>'
            f'<text x="20" y="14" font-size="11" fill="var(--mut)">최고 {fmt(hi0)} · 최저 {fmt(lo0)} · 지금 {fmt(series[-1])}</text>{lab}</svg>')


def render(b, asof, months, rates, anon=None, peers=()):
    r = rates[b["code"]]
    el = {k: v * PD_GIVEN_CLOSE * LGD * LOAN for k, v in r.items()}
    name = anon or b["brand"]
    rnd = (lambda x: int(round(x, -1))) if anon else (lambda x: x)  # noqa: E731
    series = b["series"]
    ftc = b.get("ftc")
    if ftc:
        start = (ftc["start"] or "")[:4] if anon else (ftc["start"] or "미기재")
        ftc_txt = f"등록됨 ({ftc['years'][0]}~{ftc['years'][-1]}, 가맹사업 개시 {start or '미기재'}, {ftc['mid'] or ''})"
    else:
        ftc_txt = "공정위 외식 브랜드 목록과 매칭 안 됨 (직영 체인·표기 차이일 수 있음)"
    gs = sorted(x["growth"] for x in peers if x["code"] == b["code"])
    cuts = f"쇠퇴 {gs[len(gs) // 3]:+.1%} 미만 · 성장 {gs[2 * len(gs) // 3]:+.1%} 이상 (브랜드 {len(gs)}개)" if len(gs) >= 3 else ""
    color = {"쇠퇴": "var(--bad)", "중간": "var(--mid)", "성장": "var(--good)"}[b["tier"]]
    closed = max(b.get("closed_6_18m", 0), 1)
    rows = "".join(f"<tr{' class=hl' if k == b['tier'] else ''}><td>{k} 1/3</td><td>{r[k]:.1%}</td><td>{el[k] / 1e4:,.0f}만 원</td></tr>" for k in ("쇠퇴", "중간", "성장"))
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>브랜드 건강도 리포트</title><style>
:root{{--bg:#fff;--fg:#1d2330;--mut:#6b7280;--line:#e5e7eb;--acc:#2f5dd0;--bad:#c2410c;--mid:#a16207;--good:#15803d;--hl:#f3f6fd}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151c;--fg:#e8eaf0;--mut:#9aa1ad;--line:#2a2f3a;--acc:#7aa2ff;--bad:#fb923c;--mid:#facc15;--good:#4ade80;--hl:#1a2030}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,'Malgun Gothic',sans-serif;max-width:760px;margin:0 auto;padding:24px 16px}}
h1{{font-size:22px;margin:0}} h2{{font-size:16px;margin:26px 0 8px;border-bottom:1px solid var(--line);padding-bottom:4px}}
.sub{{color:var(--mut);font-size:13px}} .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:16px}}
.k{{border:1px solid var(--line);border-radius:8px;padding:10px 12px}} .k b{{display:block;font-size:20px}} .k span{{color:var(--mut);font-size:12px}}
.tier{{display:inline-block;padding:2px 10px;border-radius:999px;color:#fff;background:{color};font-weight:600}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left}} tr.hl{{background:var(--hl);font-weight:600}}
ul{{padding-left:18px}} .foot{{color:var(--mut);font-size:12px;margin-top:28px}}
</style></head><body>
<h1>{html.escape(name)} <span class="tier">{b['tier']}</span></h1>
<div class="sub">{b['industry']} 가맹 브랜드 · 서울 인허가 기준 {asof} · 신용캐드 브랜드 건강도{' · 익명 시연본(매장 수 10단위 반올림)' if anon else ' · 내부용(외부 배포 금지)'}</div>
<div class="kpis">
<div class="k"><b>{rnd(b['stores']):,}곳</b><span>서울 영업 중 매장</span></div>
<div class="k"><b>+{b['open_12m']} / −{b['close_12m']}</b><span>직전 12개월 개업 / 폐업</span></div>
<div class="k"><b>{b['growth']:+.1%}</b><span>순증가율 (개업−폐업)/매장</span></div>
<div class="k"><b>{b['close_rate_12m']:.1%}</b><span>1년 전 매장 중 폐업 비율</span></div>
</div>
<h2>서울 매장 수 36개월</h2>{spark(series, months, fmt=lambda v: f"{rnd(v):,}")}
<div class="sub">등급 = 같은 업종 매장 10곳+ 브랜드 중 순증가율 3분위: {cuts}</div>
<h2>이 등급 가맹점의 다음 1년 (검증된 숫자)</h2>
<table><tr><th>브랜드 등급</th><th>다음 1년 폐업률 (2021~24 검증)</th><th>대출 1건 기대손실*</th></tr>{rows}</table>
<div class="sub">* 대출 {LOAN / 1e4:,.0f}만 원 × 폐업 시 부도 {PD_GIVEN_CLOSE:.0%}(가정) × 손실률 {LGD:.0%}(가정). 폐업률만 실측이며, 파일럿에서 실제 연체로 바꾼다.</div>
<h2>같은 자리 다음 점포 (설명 지표)</h2>
<ul><li>6~18개월 전 폐업한 가맹점 {b.get('closed_6_18m', 0)}곳 중 <b>다른 브랜드로 간판 교체 {b.get('conv_out', 0)}곳 ({b.get('conv_out', 0) / closed:.0%})</b>, 같은 브랜드 재개업(양도로 봄) {b.get('same_reopen', 0)}곳.</li>
<li>간판 교체가 많은 브랜드는 남은 가맹점도 더 닫았다(검증 D2). 순증가율에 더한 예측력은 없어 점수에는 넣지 않는다.</li></ul>
<h2>공정위 정보공개서</h2><ul><li>{html.escape(ftc_txt)}</li>
<li>등록 목록은 쇠퇴를 알려 주지 않는다: 서울에서 줄어드는 브랜드도 2년 안에 등록을 거의 유지했다(브랜드-연 470건 중 이탈 4건, 쇠퇴 1/3에서는 158건 중 2건).</li></ul>
<h2>근거와 한계</h2><ul>
<li>근거: 서울 인허가 카페 40,554곳·음식점 539,188곳. 쇠퇴 1/3 브랜드 가맹점의 다음 1년 폐업률이 성장 1/3의 2.6~7.1배(두 기간, 업력 통제).</li>
<li>사전 등록: 2026-10-20 등급을 해시로 봉인, 2027-10 채점(H-2026-10-D).</li>
<li>한계: 서울·외식만. 상호로 브랜드를 추정(공정위 등록과 74~87% 일치). 폐업은 부도가 아니다. 이 리포트만으로 대출을 결정하지 않는다.</li></ul>
<div class="foot">신용캐드 · 공공데이터(서울 열린데이터광장 LOCALDATA, 공정거래위원회 가맹정보) 가공 · {asof}</div>
</body></html>"""


def main():
    rates = tier_rates()
    with open(BH.OUT, encoding="utf-8") as fh:
        d = json.load(fh)
    if "--demo" in sys.argv:
        os.makedirs(OUT_DEMO, exist_ok=True)
        cands = [b for b in d["brands"] if b["stores"] >= 50 and b["code"] == "072405"]
        for tier, tag in (("쇠퇴", "declining"), ("성장", "growing")):
            pool = sorted((x for x in cands if x["tier"] == tier), key=lambda x: x["growth"])
            b = pool[len(pool) // 2]          # 그 등급의 순증가율 중앙 브랜드(대표적인 예) - 가장 큰 브랜드는 익명이어도 짐작될 수 있어 피함
            p = os.path.join(OUT_DEMO, f"brand_report_demo_{tag}.html")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(render(b, d["asof"], d["months"], rates, peers=d["brands"], anon=f"카페 브랜드 {'A' if tier == '쇠퇴' else 'B'}"))
            print("demo ->", p)
        return
    q = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    hits = BH.search(q)["hits"]
    if not hits:
        print("no brand matches", q)
        return
    os.makedirs(OUT_INT, exist_ok=True)
    b = hits[0]
    p = os.path.join(OUT_INT, re.sub(r"[^0-9A-Za-z가-힣]", "", b["brand"]) + ".html")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(render(b, d["asof"], d["months"], rates, peers=json.load(open(BH.OUT, encoding="utf-8"))["brands"]))
    print("report ->", p)


if __name__ == "__main__":
    main()

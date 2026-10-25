"""실시간 공시 - 1분 간격으로 처음 포착한 공시(scripts/collect_disclosures_live.py)에 오늘의 공시와 같은 분류·과거 반응 통계를 붙인다 (2026-10-16).

python -X utf8 -m dintel.live            # 오늘 최근 20건
사이트: /api/live?since=HH:MM (sites/biz.py) - 사업 기능 '관심기업 실시간 공시 경보'의 화면용.
- 분류·통계는 dintel.feed와 동일(annotate + classify) - 단계(tier), 위험 태그, 같은 유형 과거 반응, 희석성 여부.
- first_seen = 우리 수집기가 처음 본 시각(최대 약 1분 지연). backlog=1은 수집기가 꺼져 있던 틈의 공시(시각 부정확) - 화면에 '늦게 확인' 표시.
- 실투자 엔진 점수는 쓰지 않는다(사업 엔진 분리 원칙). 통계는 과거 같은 유형의 평균 반응이며 이 공시의 예측이 아니다.
"""
import csv
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
LIVE = os.path.join(ROOT, "data", "quant", "disclosures_live")
MARKET = {"Y": "KOSPI", "K": "KOSDAQ"}
WATCH = os.path.join(ROOT, "data", "dintel", "watchlist.json")


def watchlist():
    import json
    try:
        return json.load(open(WATCH, encoding="utf-8"))
    except (OSError, ValueError):
        return []


def watch_edit(add=None, remove=None):
    """관심기업 목록(고객이 지켜보는 기업) 추가·삭제 - 기업명 또는 6자리 코드. 반환: (목록, 메시지)."""
    import json
    from dintel import company as DC
    wl = watchlist()
    msg = ""
    if add:
        row, cands = DC.resolve(add)
        if row is None:
            msg = f"'{add}' 기업을 찾지 못했습니다"
        elif any(w["stock_code"] == row["stock_code"] for w in wl):
            msg = f"{row['corp_name']}은(는) 이미 목록에 있습니다"
        else:
            wl.append({"stock_code": row["stock_code"], "corp_name": row["corp_name"], "market": row.get("market", ""),
                       "added": datetime.now().strftime("%Y-%m-%d")})
            msg = f"{row['corp_name']} 추가"
    if remove:
        before = len(wl)
        wl = [w for w in wl if w["stock_code"] != str(remove).zfill(6)]
        msg = "삭제" if len(wl) < before else msg
    os.makedirs(os.path.dirname(WATCH), exist_ok=True)
    with open(WATCH + ".tmp", "w", encoding="utf-8") as f:
        json.dump(wl, f, ensure_ascii=False, indent=1)
    os.replace(WATCH + ".tmp", WATCH)
    return wl, msg



def build_live(day=None, since=None, limit=200):
    from dintel import company as DC
    from dintel import feed as DF
    day = day or datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(LIVE, f"{day}.csv")
    if not os.path.exists(path):
        return {"ok": True, "date": day, "items": [], "collector": "not running today", "disclaimer": DC.DISCLAIMER}
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r.get("corp_cls") in MARKET]
    if since:
        rows = [r for r in rows if r["first_seen"][11:16] >= since]
    watched = {w["stock_code"] for w in watchlist()}
    rows = sorted(rows, key=lambda r: (r["first_seen"], r["rcept_no"]), reverse=True)
    rows = rows[:limit] + [r for r in rows[limit:] if str(r.get("stock_code", "")).zfill(6) in watched]   # 관심기업 공시는 잘리지 않게
    stats = DC.load_all_stats()
    items = []
    for mk, name in MARKET.items():
        part = [r for r in rows if r["corp_cls"] == mk]
        for src, a in zip(part, DC.annotate([{**r, "flr_nm": "", "rm": ""} for r in part], name, stats)):
            it = DF.classify({**a, "market": name})
            it["first_seen"] = src["first_seen"]
            it["late"] = src.get("backlog") == "1"
            it["watched"] = str(src.get("stock_code", "")).zfill(6) in watched
            items.append(it)
    items.sort(key=lambda d: (d["first_seen"], d["rcept_no"]), reverse=True)
    last = max((r["first_seen"] for r in csv.DictReader(open(path, encoding="utf-8"))), default=None)
    age = (datetime.now() - datetime.fromisoformat(last)).total_seconds() / 60 if last else None
    return {"ok": True, "date": day, "items": items,
            "counts": {"total": len(items), "tier1": sum(d["tier"] == 1 for d in items), "tier2": sum(d["tier"] == 2 for d in items),
                       "watched": sum(d["watched"] for d in items)}, "watchlist": watchlist(),
            "collector": "live" if age is not None and age < 5 else (f"last seen {age:.0f} min ago" if age is not None else "no data"),
            "generated": f"{datetime.now():%Y-%m-%d %H:%M:%S}", "disclaimer": DC.DISCLAIMER}


if __name__ == "__main__":
    f = build_live()
    print(f"{f['date']} | {f.get('counts')} | collector {f['collector']}")
    for d in f["items"][:20]:
        st = d.get("stat")
        print(f"  {d['first_seen'][11:19]} T{d['tier']} {d['market']:<6} {d['corp_name'][:10]:<10} {str(d.get('etype') or d['report_nm'])[:26]:<26}"
              f" | {'d20 %+.1f%%' % (st['d20'] * 100) if st else '-'} | {d['risk_tags']}{' (late)' if d['late'] else ''}")

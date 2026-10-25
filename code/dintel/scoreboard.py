"""공개 성적표(Pre-registered Scoreboard) - 경고를 '나중에 고칠 수 없게' 먼저 고정하고, 기간이 지나면 채점한다(2026-10-08).

python -X utf8 -m dintel.scoreboard publish     # 이번 달 경고 목록 발행(이미 발행했으면 건너뜀)
python -X utf8 -m dintel.scoreboard evaluate    # 발행된 목록 채점(진행 중인 것은 중간 성적)
python -X utf8 -m dintel.scoreboard backtest    # 검증 기간(2022~)을 월별로 '그때 발행했다면'으로 재현한 성적

왜: 사후에 고른 사례로 신호를 자랑하는 서비스(LLM 리포트 포함)와 구별되는 신뢰 장치. 경고 목록 파일의 SHA-256을
    원장(ledger.csv)에 남기고, 원장을 git 커밋에 포함하면 커밋 시각이 '그때 이미 그렇게 말했다'는 증거가 된다
    (공개 저장소에 올리면 제3자가 검증 가능 - 올릴지는 사용자 결정).
경고 = dintel.risk_score 의 시장 내 상위 10%. 채점 = 발행일 이후 12개월 안에 중대 위험 공시가 났는가,
       같은 시점 나머지 90%와 비교. 기업 이름을 공개할 때는 '위험 공시 확률 통계'라는 표현만 쓴다(단정·비방 금지).
"""
import hashlib
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dintel import risk_score as RS  # noqa: E402

SB = os.path.join(ROOT, "scoreboard")   # 저장소에 커밋되는 위치(data/는 git 제외) - 커밋 시각이 발행 증거
LEDGER = os.path.join(SB, "ledger.csv")


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def publish(force=False):
    os.makedirs(SB, exist_ok=True)
    led = pd.read_csv(LEDGER, dtype=str) if os.path.exists(LEDGER) else pd.DataFrame()
    month = pd.Timestamp.now().strftime("%Y-%m")
    if not force and len(led) and (led["month"] == month).any():
        print(f"[scoreboard] {month} 이미 발행 - 건너뜀")
        return
    RS.main()                                   # 최신 점수 다시 계산(risk_watch_<market>.csv)
    rows = []
    for mk in ("kosdaq", "kospi"):
        src = os.path.join(RS.DD, f"risk_watch_{mk}.csv")
        if not os.path.exists(src):
            continue
        w = pd.read_csv(src, dtype={"stock_code": str}, encoding="utf-8-sig")
        asof = str(w["asof"].iloc[0])[:10]
        warn = w[w["pctile"] >= 0.9][["asof", "stock_code", "corp_name", "risk_12m", "pctile", "drivers"]]
        rest = w[w["pctile"] < 0.9][["stock_code"]]
        wp = os.path.join(SB, f"warn_{mk}_{asof}.csv")
        rp = os.path.join(SB, f"rest_{mk}_{asof}.csv")
        warn.to_csv(wp, index=False, encoding="utf-8-sig")
        rest.to_csv(rp, index=False, encoding="utf-8-sig")
        rows.append({"month": month, "market": mk, "asof": asof, "published_at": pd.Timestamp.now().isoformat(timespec="seconds"),
                     "n_warn": len(warn), "n_rest": len(rest), "warn_file": os.path.basename(wp),
                     "warn_sha256": _sha(wp), "rest_sha256": _sha(rp),
                     "model_sha256": _sha(os.path.join(RS.DD, f"risk_model_{mk}.json"))})
        print(f"[scoreboard] {mk} {asof}: 경고 {len(warn)} / 나머지 {len(rest)} -> {wp}")
    new = pd.concat([led, pd.DataFrame(rows)], ignore_index=True)
    new.to_csv(LEDGER, index=False)
    print(f"[scoreboard] 원장 {LEDGER} ({len(new)}행) - git 커밋하면 발행 시각이 고정된다")


def evaluate():
    if not os.path.exists(LEDGER):
        raise SystemExit("원장 없음 - publish 먼저")
    led = pd.read_csv(LEDGER, dtype=str)
    out = []
    for mk in led["market"].unique():
        e = RS.load_events(mk)
        risk = e[e["risk"]]
        last = e["dt"].max()
        for _, r in led[led["market"] == mk].iterrows():
            wp = os.path.join(SB, r["warn_file"])
            rp = wp.replace("warn_", "rest_")
            ok = _sha(wp) == r["warn_sha256"] and _sha(rp) == r["rest_sha256"]
            t0 = pd.Timestamp(r["asof"])
            t1 = min(t0 + pd.Timedelta(days=365), last)
            hit_codes = _risk_stock_codes(risk[(risk["dt"] > t0) & (risk["dt"] <= t1)], mk)
            w = pd.read_csv(wp, dtype={"stock_code": str}, encoding="utf-8-sig")
            rest = pd.read_csv(rp, dtype={"stock_code": str}, encoding="utf-8-sig")
            hw, hr = w["stock_code"].isin(hit_codes).mean(), rest["stock_code"].isin(hit_codes).mean()
            out.append(f"{mk} {r['asof']} 발행 | 해시 {'일치' if ok else '불일치!'} | 경과 {(t1 - t0).days}일/365 | "
                       f"경고 {len(w)}종목 중 위험공시 {hw:.1%} vs 나머지 {hr:.1%}")
    print("\n".join(out))


def _risk_stock_codes(risk, mk):
    m = pd.read_parquet(RS.PANELS[mk], columns=["stock_code", "corp_code"]).dropna().drop_duplicates("corp_code")
    m["corp_code"] = m["corp_code"].astype(str).str.zfill(8)
    cmap = dict(zip(m["corp_code"], m["stock_code"].astype(str)))
    return set(risk["corp_code"].map(cmap).dropna())


def api_payload(top=30):
    """홈페이지 PROJECT 탭 '재무위험 조기경보' 화면용: 시장별 검증 성적 + 현재 경고 상위 + 성적표 원장."""
    import json
    out = {"ok": True, "markets": [], "ledger": [], "disclaimer":
           "다음 12개월 중대 위험 공시(관리종목·상장적격성·감사의견·상장폐지·불성실공시) 발생 확률 통계입니다. "
           "매수·매도 의견이 아니며, 현재 상장사 기준 검증이라 상장폐지 기업이 빠진 생존편향이 있습니다."}
    for mk in ("kosdaq", "kospi"):
        mp, wp = os.path.join(RS.DD, f"risk_model_{mk}.json"), os.path.join(RS.DD, f"risk_watch_{mk}.csv")
        if not (os.path.exists(mp) and os.path.exists(wp)):
            continue
        with open(mp, encoding="utf-8") as fh:
            model = json.load(fh)
        w = pd.read_csv(wp, dtype={"stock_code": str}, encoding="utf-8-sig").head(top)
        coef = model.get("coef", {})
        labels = model.get("labels", {})
        out["markets"].append({
            "market": mk.upper(), "asof": model.get("asof"), "validation": model.get("validation", {}),
            "validation_delisted": model.get("validation_delisted"), "trained_with_delisted": model.get("trained_with_delisted", False),
            "drivers": [{"name": labels.get(k, k), "coef": v} for k, v in coef.items() if v > 0][:8],
            "top": [{"stock_code": r.stock_code, "corp_name": r.corp_name, "risk": float(r.risk_12m),
                     "pctile": float(r.pctile), "drivers": r.drivers if isinstance(r.drivers, str) else ""}
                    for r in w.itertuples()]})
    if os.path.exists(LEDGER):
        led = pd.read_csv(LEDGER, dtype=str)
        out["ledger"] = [{"market": r["market"].upper(), "asof": r["asof"], "published_at": r["published_at"],
                          "n_warn": int(r["n_warn"]), "sha": r["warn_sha256"][:16],
                          "status": "채점 대기(12개월)" if pd.Timestamp(r["asof"]) + pd.Timedelta(days=365) > pd.Timestamp.now()
                          else "채점 가능"} for _, r in led.iterrows()]
    return out


def backtest():
    """검증 기간을 월별로 재현: 2020-12까지 학습한 모델로 매월 상위 10%를 '발행'했다면 12개월 뒤 성적."""
    for mk in ("kosdaq", "kospi"):
        m, _ = RS.build(mk)
        RS.evaluate(mk, m)
    print(f"자세한 결과: {RS.OUT}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "evaluate"
    {"publish": lambda: publish("--force" in sys.argv), "evaluate": evaluate, "backtest": backtest}[cmd]()

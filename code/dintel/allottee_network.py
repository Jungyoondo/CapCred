"""배정 대상 네트워크 - 같은 조합·운용사·법인이 돈을 넣은 '다른 회사들'의 과거 결과가 새 회사의 위험을 알려 주는가 (2026-10-09).

python -X utf8 -m dintel.allottee_network            # 코스닥 평가(네트워크는 두 시장 자금조달 원문 전체로 만든다)
python -X utf8 -m dintel.allottee_network kospi

사업계획서 7장 '배정 대상 묶기(투자조합 네트워크)'와 5장 해자 ①(원문 조건 데이터)의 실측 검증.
- 원천: data/dintel/financing_docs/<rcept_no>.txt (유상증자·CB·BW 주요사항보고서 원문 7,156건)
  표 【제3자배정 대상자별 …】 / 【특정인에 대한 대상자별 사채발행내역】에서 대상자 이름을 뽑는다.
- 대상: 조합(투자조합·신기술사업투자조합 등), 자산운용사(사모펀드 운용), 일반 법인.
  제외: 개인 이름(사업 원칙 - 개인 식별 안 함), 신탁업자·판매사로 함께 적히는 증권사·은행(거의 모든 펀드 거래에 등장해 신호가 아님).
  이름 정규화: 공백·'주식회사'·(주)·㈜·괄호 설명 제거.
- PIT 피처(기업 i, 월말 t): i가 직전 12개월에 받은 자금조달의 대상자 e마다
    prior_firms(e,t) = t 이전에 e가 돈을 넣은 '다른' 기업 수
    prior_bad(e,t)   = 그중 e의 투자 이후 t까지 실제로 위험 공시(관리종목·적격성·감사·상폐·불성실)를 낸 기업 수
  (t 이후 정보는 쓰지 않는다 - 결과가 t까지 관측된 것만 센다)
  기업 피처: g_repeat = max_e prior_firms, g_bad = max_e prior_bad, g_bad_any = [g_bad >= 1], g_bad2 = [g_bad >= 2]
- 평가: dintel.risk_score와 같은 패널·목표·분할(학습 t<=2020-12 / 검증 t>=2022-01), 공시 로지스틱에
  네트워크 피처를 더했을 때의 검증 AUC·상위 10% 적중, 그리고 자금조달이 있었던 기업-월 안에서의 조건부 위험률.
판단(사전 고정): 검증 AUC +0.005 이상 또는 자금조달 기업-월 안에서 g_bad_any 그룹 위험률이 나머지의 1.5배 이상이고
  학습·검증 두 기간 모두 같은 방향일 때만 '네트워크 신호 있음'.
출력: data/dintel/NETWORK_SUMMARY.txt, data/dintel/allottees.csv(대상자-거래 목록, 개인 제외)
"""
import glob
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from dintel import risk_score as R  # noqa: E402

DD = R.DD
OUT = os.path.join(DD, "NETWORK_SUMMARY.txt")
DOCS = os.path.join(DD, "financing_docs")

SEG_START = r"【\s*(?:제3자배정\s*대상자별|특정인에\s*대한\s*대상자별)"
SEG_END = r"【|※|◆click◆"
# 조직 이름: 접미어로 끝나는 덩어리
ORG = re.compile(r"((?:[가-힣A-Za-z0-9&·\.\-]+\s?){1,8}?(?:신기술사업투자조합|창업투자조합|벤처투자조합|투자조합|조합"
                 r"|자산운용|투자자문|인베스트먼트|파트너스|캐피탈|홀딩스|주식회사|유한회사|유한책임회사|\(주\)|㈜))")
TRUSTEE = re.compile(r"증권|은행|신탁업자|판매회사|금융투자|미래에셋대우|보험|보증보")
GENERIC = {"주식회사", "유한회사", "투자조합", "조합", "자산운용", "파트너스", "인베스트먼트", "캐피탈", "홀딩스",
           "공동업무집행조합", "업무집행조합", "업무집행조합원"}


def log(s=""):
    print(s, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def norm(name):
    s = re.sub(r"\([^)]*\)", "", name)
    s = re.sub(r"주식회사|\(주\)|㈜|유한책임회사|유한회사", "", s)
    s = re.sub(r"[\s·\.\-&]", "", s)
    s = re.sub(r"^[0-9,]+", "", s)                       # 표에서 앞 칸 금액이 붙은 경우
    if s.endswith("자산운용") and re.search(r"투자신탁|사모|펀드", s):   # 펀드 이름 + 운용사 -> 운용사로 묶는다
        tail = re.split(r"투자신탁|신탁|펀드|호", s)[-1]
        if len(tail) >= 5:
            s = tail
    s = re.sub(r"^(본건펀드\d*|펀드\d*)", "", s)
    return s.strip()


def extract(text):
    """원문 -> 대상자 조직 이름(정규화) 집합. 개인·신탁업자 제외."""
    t = re.sub(r"\s+", " ", text.replace("&cr;", " "))
    out = set()
    for m in re.finditer(SEG_START, t):
        rest = t[m.end():]
        e = re.search(SEG_END, rest[5:])
        seg = rest[: (e.start() + 5) if e else 2500][:4000]
        # 헤더 단어 제거
        seg = re.sub(r"선정\s*경위|거래\s*내역|배정\s*내역|배정\s*주식수|발행\s*권면\S*|발행\s*대상자명|제3자배정\s*대상자|"
                     r"회사\s*또는\s*최대주주와의\s*관계|비\s*고|등】", " ", seg)
        # 괄호 안 설명('… 신탁업자 지위에서')은 통째로 지워 신탁업자가 대상자로 잡히지 않게
        seg = re.sub(r"\([^)]{0,120}지위에서\)", " ", seg)
        for mm in ORG.finditer(seg):
            raw = mm.group(1).strip()
            if TRUSTEE.search(raw):
                continue
            n = norm(raw)
            if len(n) < 3 or n in GENERIC or re.fullmatch(r"[0-9]+", n):
                continue
            out.add(n)
    return out


def allottees():
    p = os.path.join(DD, "financing_parsed.csv")
    f = pd.read_csv(p, dtype={"corp_code": str, "rcept_dt": str, "rcept_no": str})
    f["corp_code"] = f["corp_code"].str.zfill(8)
    f["dt"] = pd.to_datetime(f["rcept_dt"], format="%Y%m%d", errors="coerce")
    rows = []
    for r in f.itertuples(index=False):
        fp = os.path.join(DOCS, f"{r.rcept_no}.txt")
        if not os.path.exists(fp):
            continue
        with open(fp, encoding="utf-8") as fh:
            names = extract(fh.read())
        for n in names:
            rows.append((r.rcept_no, r.corp_code, r.dt, str(r.market), n))
    A = pd.DataFrame(rows, columns=["rcept_no", "corp_code", "dt", "market", "entity"]).dropna(subset=["dt"])
    A.to_csv(os.path.join(DD, "allottees.csv"), index=False, encoding="utf-8")
    return A, f


def features(m, A, risk_first_after):
    """m: risk_score.build 패널. A: 대상자-거래. risk_first_after(corp, dt) -> 그 이후 첫 위험 공시일(없으면 NaT)."""
    A = A.sort_values("dt").reset_index(drop=True)
    A["bad_dt"] = [risk_first_after(c, d) for c, d in zip(A["corp_code"], A["dt"])]
    by_ent = {e: g[["corp_code", "dt", "bad_dt"]].to_numpy() for e, g in A.groupby("entity")}
    by_corp = {c: g[["dt", "entity"]].to_numpy() for c, g in A.groupby("corp_code")}
    rep, bad, n_ent, n_new = np.zeros(len(m)), np.zeros(len(m)), np.zeros(len(m)), np.zeros(len(m))
    corps, asof = m["corp_code"].to_numpy(), m["asof"].to_numpy("datetime64[ns]")
    yr = np.timedelta64(365, "D")
    for i, (c, t) in enumerate(zip(corps, asof)):
        own = by_corp.get(c)
        if own is None:
            continue
        ents = {e for d, e in own if (np.datetime64(d) <= t) and (np.datetime64(d) > t - yr)}
        best_r, best_b = 0, 0
        for e in ents:
            arr = by_ent[e]
            seen, badc = set(), set()
            for cc, d, bd in arr:
                if np.datetime64(d) >= t:
                    break
                if cc == c:
                    continue
                seen.add(cc)
                if bd is not pd.NaT and not pd.isna(bd) and np.datetime64(bd) <= t:
                    badc.add(cc)
            best_r, best_b = max(best_r, len(seen)), max(best_b, len(badc))
            n_new[i] += (len(seen) == 0)
        rep[i], bad[i], n_ent[i] = best_r, best_b, len(ents)
    m = m.copy()
    m["g_repeat"], m["g_bad"] = rep, bad
    m["g_bad_any"] = (bad >= 1).astype(float)
    m["g_bad2"] = (bad >= 2).astype(float)
    m["g_n_ent"], m["g_n_new"] = n_ent, n_new          # 대상자 수, 그중 처음 보는(다른 기업 투자 이력 없는) 대상자 수
    return m


def evaluate(market, m):
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    d = m[~m["risk_prev"] & m["y_known"]].copy()
    tr, te = d[d["asof"] <= "2020-12-31"], d[d["asof"] >= "2022-01-01"]
    disc = [c for c in d.columns if c.startswith(("n_", "x_"))]
    net = ["g_repeat", "g_bad", "g_bad_any", "g_bad2"]
    res = {}
    for name, feats in (("disclosure", disc), ("disclosure + network", disc + net), ("network only", net)):
        Xtr, Xte = R._xy(tr, feats), R._xy(te, feats)
        for c in ("g_repeat", "g_bad"):
            if c in feats:
                Xtr[c], Xte[c] = np.log1p(tr[c]), np.log1p(te[c])
        pipe = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(C=0.5, max_iter=2000))
        pipe.fit(Xtr, tr["y"])
        s = pipe.predict_proba(Xte)[:, 1]
        k = max(1, int(len(te) * 0.10))
        hit = te["y"].to_numpy()[np.argsort(-s)[:k]].mean()
        res[name] = (R.auc(te["y"], s), hit, pipe, feats)
        log(f"  {name:22s} 검증 AUC {res[name][0]:.3f} | 상위 10% 적중 {hit:.1%} ({hit / te['y'].mean():.1f}배)")
    lr = res["disclosure + network"][2].named_steps["logisticregression"]
    co = pd.Series(lr.coef_[0], index=res["disclosure + network"][3])
    log("  네트워크 계수(표준화): " + ", ".join(f"{c} {co[c]:+.2f}" for c in net))
    # 자금조달이 있었던 기업-월 안에서 조건부 위험률(학습·검증 각각)
    rows = {}
    for per, dd in (("학습", tr), ("검증", te)):
        fin = dd[dd["n_fin"] > 0]
        a, b = fin[fin["g_bad_any"] > 0], fin[fin["g_bad_any"] == 0]
        a2 = fin[fin["g_bad2"] > 0]
        rows[per] = (a["y"].mean(), b["y"].mean())
        log(f"  [{per}] 자금조달 기업-월 {len(fin):,}: 대상자의 과거 투자처 중 위험 발생 1곳+ {len(a):,}건 위험률 "
            f"{a['y'].mean():.1%} vs 없음 {len(b):,}건 {b['y'].mean():.1%} ({a['y'].mean() / max(b['y'].mean(), 1e-9):.1f}배)"
            f" | 2곳+ {len(a2):,}건 {a2['y'].mean():.1%}")
        x = fin[fin["x_fund"] > 0]
        xa, xb = x[x["g_bad_any"] > 0], x[x["g_bad_any"] == 0]
        log(f"         그중 투자조합 배정 {len(x):,}건: 위험 이력 대상자 {xa['y'].mean():.1%} (n={len(xa):,}) vs 없음 "
            f"{xb['y'].mean():.1%} (n={len(xb):,})")
    # 사후(탐색) 분해 - 사전 가설이 아니므로 채택 판단에 쓰지 않는다: 대상자 추출 안 됨 / 처음 보는 대상자만 / 반복 대상자 포함
    for per, dd in (("학습", tr), ("검증", te)):
        fin = dd[dd["n_fin"] > 0]
        g0 = fin[fin["g_n_ent"] == 0]
        g1 = fin[(fin["g_n_ent"] > 0) & (fin["g_repeat"] == 0)]
        g2 = fin[fin["g_repeat"] > 0]
        log(f"  [탐색·{per}] 대상자 추출 안 됨(공모·개인 등) {g0['y'].mean():.1%} (n={len(g0):,}) | 처음 보는 대상자만 "
            f"{g1['y'].mean():.1%} (n={len(g1):,}) | 다른 기업 투자 이력 있는 대상자 {g2['y'].mean():.1%} (n={len(g2):,})")
    d_auc = res["disclosure + network"][0] - res["disclosure"][0]
    lift_ok = all(r[0] >= 1.5 * r[1] for r in rows.values() if not np.isnan(r[0]))
    verdict = (d_auc >= 0.005) or lift_ok
    log(f"NETWORK {market}: AUC {res['disclosure'][0]:.3f} -> {res['disclosure + network'][0]:.3f} ({d_auc:+.3f}) | "
        f"조건부 1.5배 이상(학습·검증 모두): {lift_ok} -> {'신호 있음' if verdict else '신호 없음(채택 안 함)'}")
    return res


def main():
    markets = [a for a in sys.argv[1:] if a in R.PANELS] or ["kosdaq"]
    A, f = allottees()
    log(f"\n##### 배정 대상 네트워크 {pd.Timestamp.now():%Y-%m-%d %H:%M} | 원문 {f['rcept_no'].nunique():,}건 중 대상자 추출 "
        f"{A['rcept_no'].nunique():,}건, 대상자 {A['entity'].nunique():,}곳 (개인·신탁업자 제외)")
    cnt = A.groupby("entity")["corp_code"].nunique().sort_values(ascending=False)
    log(f"  2개 기업 이상에 들어간 대상자 {int((cnt >= 2).sum()):,}곳, 5개 이상 {int((cnt >= 5).sum()):,}곳 | "
        f"유형: 조합 {A['entity'].str.contains('조합').mean():.0%}, 운용·투자사 "
        f"{A['entity'].str.contains('자산운용|인베스트먼트|파트너스|투자자문').mean():.0%} (거래-대상자 쌍 기준)")
    for market in markets:
        m, last_ev = R.build(market)
        e = R.load_events(market)
        ridx = R._index(e, e["risk"])

        def first_after(c, d, ridx=ridx):
            arr = ridx.get(c)
            if arr is None:
                return pd.NaT
            i = np.searchsorted(arr, np.datetime64(d), side="right")
            return arr[i] if i < len(arr) else pd.NaT

        # 네트워크의 '결과'는 두 시장 위험 공시를 모두 써야 하므로 다른 시장 위험 공시도 합친다
        other = [k for k in R.PANELS if k != market]
        for o in other:
            eo = R.load_events(o)
            for c, arr in R._index(eo, eo["risk"]).items():
                ridx[c] = np.sort(np.concatenate([ridx[c], arr])) if c in ridx else arr
        m = features(m, A, first_after)
        log(f"\n## {market}: 기업-월 {len(m):,} | g_bad_any 비중 {m['g_bad_any'].mean():.2%} | g_repeat>0 {(m['g_repeat'] > 0).mean():.2%}")
        evaluate(market, m)


if __name__ == "__main__":
    main()

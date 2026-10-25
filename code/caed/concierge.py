"""'대신 해 주는' 에이전트 - 요청 한 줄을 받아 공공데이터·재무제표 도구로 결과물을 만든다 (2026-10-26, 사업 재설계 확장).

python -X utf8 -m caed.concierge "비비큐 정보공개서 정기변경 준비해줘"
python -X utf8 -m caed.concierge "마포구 카페 대장 정비 목록 뽑아줘"
python -X utf8 -m caed.concierge list            # 할 수 있는 일(레시피)과 도구 목록
python -X utf8 -m caed.concierge demo            # 대표 요청 6개를 돌려 걸린 시간·쓴 자료를 data/caed/concierge/demo.json에 남김

구조: 요청 -> 접수(레시피 고르기 + 빈칸 채우기, 지금은 규칙 기반) -> 레시피가 도구를 차례로 부름 -> 결과물(마크다운) + 작업 기록.
  도구 = 저장해 둔 공공데이터(서울 인허가, 공정위 가맹정보 3종, 상가정보) + OpenDART(상장사 재무제표, 비상장 감사보고서 목록).
  레시피 = 누군가 해야 하는 일 하나(누가·근거·지금 비용·사람이 마지막에 할 일).
경계: 결과물은 '초안 재료·확인 자료'다. 정보공개서 작성 자문·등록 대행(가맹거래사 업무), 신용평가, 행정 처분은 하지 않는다.
  사업 제품이므로 주식 엔진(alpha3·quant)을 쓰지 않는다. 결과물에 상호가 들어가면 로컬 전용(data/caed/concierge/).
"""
import json
import os
import re
import sys
import time

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from caed import localdata as LD  # noqa: E402

OUT = os.path.join(ROOT, "data", "caed", "concierge")
IND = {"카페": "072405", "커피": "072405", "음식점": "072404", "식당": "072404", "치킨": "072404", "미용실": "051801", "미용": "051801",
       "세탁소": "062001", "세탁": "062001", "헬스장": "104201", "헬스": "104201"}
IND_NM = {"072405": "카페·휴게음식점", "072404": "일반음식점", "051801": "미용실", "062001": "세탁소", "104201": "헬스장"}
STORE_CATS = {"072405": ["카페"], "072404": None, "051801": ["미용실"], "062001": ["세탁소"], "104201": ["헬스장"]}
LOG = []   # 이번 요청에서 부른 도구 기록


# ---------------------------------------------------------------- 도구 (자료를 읽는 일만)
def tool(label, source):
    def deco(fn):
        def run(*a, **k):
            t = time.time()
            r = fn(*a, **k)
            n = len(r) if hasattr(r, "__len__") else 1
            LOG.append({"tool": label, "source": source, "rows": int(n), "sec": round(time.time() - t, 1)})
            return r
        run.label, run.source = label, source
        return run
    return deco


_REG = {}


@tool("인허가 업소 명부", "서울 열린데이터광장 지방행정 인허가(LOCALDATA)")
def permits(code):
    """업종 하나의 서울 인허가 전체 - 개업·폐업일, 상호, 도로명 주소, 구, 좌표(EPSG:5174)."""
    if code not in _REG:
        m = pd.read_csv(os.path.join(LD.OUT, f"{code}.csv"), dtype=str, keep_default_na=False)
        n = pd.read_csv(os.path.join(LD.OUT, f"{code}.names.csv"), dtype=str, keep_default_na=False)
        cols = ["MGTNO", "APVPERMYMD", "BPLCNM"] + (["RDNWHLADDR"] if "RDNWHLADDR" in n else [])
        g = m.merge(n[cols].drop_duplicates(["MGTNO", "APVPERMYMD"]), on=["MGTNO", "APVPERMYMD"], how="left")
        g = g.assign(open=pd.to_datetime(g["APVPERMYMD"], format="%Y-%m-%d", errors="coerce"),
                     close=pd.to_datetime(g["DCBYMD"].str[:10], format="%Y-%m-%d", errors="coerce"),
                     x=pd.to_numeric(g["X"], errors="coerce"), y=pd.to_numeric(g["Y"], errors="coerce"),
                     name=g["BPLCNM"].fillna(""), addr=g.get("RDNWHLADDR", pd.Series("", index=g.index)).fillna(""))
        g["alive"] = g["close"].isna() & g["DTLSTATENM"].isin(["영업", "영업중", "정상영업"])
        _REG[code] = g.dropna(subset=["open"]).reset_index(drop=True)
    return _REG[code]


@tool("상가 목록", "소상공인시장진흥공단 상가(상권)정보")
def store_list():
    import pyproj
    from caed import store_registry as SR
    st, ym = SR.latest()
    to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:5174", always_xy=True)
    sx, sy = to_m.transform(pd.to_numeric(st["lon"], errors="coerce").to_numpy(), pd.to_numeric(st["lat"], errors="coerce").to_numpy())
    st = st.assign(x=sx, y=sy, ym=ym).dropna(subset=["x", "y"])
    return st


@tool("공정위 브랜드 등록 목록", "공정거래위원회 가맹정보 브랜드 목록(data.go.kr 15125467)")
def ftc_brands():
    from caed import ftc_brands as F
    return F.load()


@tool("공정위 지역별 가맹점 수", "공정거래위원회 가맹정보 브랜드 가맹점·직영점(data.go.kr 15125490)")
def ftc_regional(mnnos):
    from caed import fdd_agent as A
    D = A.disclosed(set(mnnos))
    return D if D is not None else pd.DataFrame()


@tool("기업 공시 목록", "금융감독원 OpenDART 공시검색")
def dart_filings(corp):
    import requests
    from caed import _env  # noqa: F401 - .env에서 DART_API_KEY를 읽는다(값은 출력하지 않음)
    cc = dart_code(corp)
    if cc is None:
        return pd.DataFrame()
    r = requests.get("https://opendart.fss.or.kr/api/list.json", params={"crtfc_key": os.environ["DART_API_KEY"], "corp_code": cc,
                     "bgn_de": f"{pd.Timestamp.now().year - 3}0101", "page_count": 100}, timeout=30).json()
    d = pd.DataFrame(r.get("list") or [])
    return d.assign(report_nm=d["report_nm"].str.strip()) if len(d) else d


@tool("재무제표 주요 계정", "금융감독원 OpenDART 단일회사 주요계정(사업보고서 제출 회사)")
def dart_accounts(corp, years):
    import requests
    from caed import _env  # noqa: F401
    cc = dart_code(corp)
    rows = []
    for y in years:
        if cc is None:
            break
        r = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcnt.json", params={"crtfc_key": os.environ["DART_API_KEY"], "corp_code": cc,
                         "bsns_year": str(y), "reprt_code": "11011"}, timeout=30).json()
        for x in r.get("list") or []:
            if x.get("fs_div") in ("CFS", "OFS"):
                rows.append({"year": y, "fs": x["fs_div"], "account": x["account_nm"], "amount": x.get("thstrm_amount")})
    return pd.DataFrame(rows)


def dart_code(corp):
    c = pd.read_csv(os.path.join(ROOT, "data", "dart_raw", "corp_code.csv"), dtype=str, encoding="utf-8-sig")
    key = re.sub(r"\(주\)|주식회사|㈜|\s", "", corp)
    hit = c[c["corp_name"] == key]
    if hit.empty:
        return None
    hit = hit.sort_values("stock_code", na_position="last")
    return hit.iloc[0]["corp_code"]


# ---------------------------------------------------------------- 공통 계산
def near(g, x, y, r):
    d = np.hypot(g["x"] - x, g["y"] - y)
    return g.assign(dist=d)[d <= r].sort_values("dist")


def turnover(g, row, years=10):
    """같은 자리(10m)에서 이 업소 개업 전 10년 안에 닫은 같은 업종 업소."""
    nb = near(g, row["x"], row["y"], 10.0)
    nb = nb[nb.index != row.name]
    return nb[nb["close"].notna() & (nb["close"] <= row["open"] + pd.Timedelta(days=30)) & (nb["close"] >= row["open"] - pd.DateOffset(years=years))]


def reopened(g, closed):
    """closed 업소 중 같은 자리(10m)에서 폐업 -30~+180일 안에 다른 인허가가 새로 난 수."""
    from scipy.spatial import cKDTree
    gg = g.dropna(subset=["x", "y"])
    c = closed.dropna(subset=["x", "y"])
    if c.empty:
        return 0
    tree, opn = cKDTree(gg[["x", "y"]].to_numpy()), gg["open"].to_numpy()
    n = 0
    for (i, r), nb in zip(c.iterrows(), tree.query_ball_point(c[["x", "y"]].to_numpy(), 10.0)):
        d = (opn[nb] - np.datetime64(r["close"])) / np.timedelta64(1, "D")
        n += bool(((d >= -30) & (d <= 180) & (gg.index.to_numpy()[nb] != i)).any())
    return n


def find_store(name, gu, codes):
    """상호(일부)와 구로 인허가 업소 찾기 - 영업 중을 먼저."""
    for code in codes:
        g = permits(code)
        hit = g[g["name"].str.replace(" ", "").str.contains(re.escape(name.replace(" ", "")), na=False)]
        if gu:
            hit = hit[hit["gu"] == gu]
        if len(hit):
            return code, g, hit.sort_values(["alive", "open"], ascending=[False, False])
    return None, None, None


def md_table(df, cols):
    if df is None or len(df) == 0:
        return "_해당 없음_"
    head = "| " + " | ".join(cols) + " |\n|" + "---|" * len(cols)
    return head + "\n" + "\n".join("| " + " | ".join("" if pd.isna(v) else (f"{v:%Y-%m-%d}" if isinstance(v, pd.Timestamp) else str(v)) for v in r) + " |"
                                   for r in df[cols].itertuples(index=False))


# ---------------------------------------------------------------- 레시피 (누군가 해야 하는 일)
RECIPES = {}


def recipe(rid, who, task, basis, human_cost, signoff, keywords, slots):
    def deco(fn):
        RECIPES[rid] = dict(fn=fn, who=who, task=task, basis=basis, human_cost=human_cost, signoff=signoff, keywords=keywords, slots=slots)
        return fn
    return deco


@recipe("fdd_update", "가맹본부·가맹거래사", "정보공개서 정기변경 초안 재료",
        "가맹사업법: 사업연도 말 + 120일 안 정기변경, 과태료 최대 1천만 원. 2028-01-01부터 중요 항목 분기 변경",
        "가맹거래사 대행 변경 1건 30~33만 원, 5~10일(크몽 공개 가격)",
        "가맹거래사·본부가 검토·서명·등록(작성 자문·등록 대행은 등록 가맹거래사 업무)",
        ["정보공개서", "정기변경", "가맹점 현황", "공정위 신고"], ["brand", "fy", "code"])
def r_fdd(s):
    from caed import fdd_agent as A
    fy = s.get("fy") or pd.Timestamp.now().year - 1
    code = s.get("code") or "072404"
    for c in [code] + [x for x in ("072404", "072405") if x != code]:
        g = A.stores(c)
        if (g["brand_raw"] == s["brand"]).any():
            code = c
            break
    LOG.append({"tool": "인허가 업소 명부", "source": "서울 열린데이터광장 지방행정 인허가(LOCALDATA)", "rows": int(len(g)), "sec": 0})
    path, info = A.report(s["brand"], code, fy, g)
    body = open(path, encoding="utf-8").read()
    fh = ftc_brands()
    ftc_regional(fh.loc[fh["key"] == __import__("caed.ftc_brands", fromlist=["norm"]).norm(s["brand"]), "brandMnno"])   # 리포트 3b에서 쓴 자료를 작업 기록에 남김
    corp = fh.loc[fh["key"] == __import__("caed.ftc_brands", fromlist=["norm"]).norm(s["brand"]), "corpNm"]
    if len(corp):
        fl = dart_filings(corp.iloc[-1])
        if len(fl):
            fl = fl[fl["report_nm"].str.contains("감사보고서|사업보고서")].head(6)
            body += ("\n## 6. 가맹본부 재무 근거 문서 (OpenDART)\n정보공개서 '가맹본부 재무상황' 칸에 옮길 최근 3년 감사보고서입니다.\n\n"
                     + md_table(fl.assign(link="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + fl["rcept_no"]), ["report_nm", "rcept_dt", "link"]) + "\n")
    return body, info


@recipe("nearby10", "가맹본부", "인근 가맹점 10곳 현황문서 초안",
        "가맹사업법 제7조: 정보공개서를 줄 때 예정지에서 가장 가까운 가맹점 10곳의 상호·소재지·전화번호 문서를 함께 준다. 안 주면 계약·가맹금 수령 금지",
        "가맹희망자마다 본부 직원이 명단·지도로 수작업",
        "본부가 자기 가맹점 명단과 대조하고 전화번호를 채워 가맹희망자에게 제공",
        ["인근가맹점", "가까운 가맹점", "10곳", "인근 가맹점", "예정지"], ["brand", "place", "code"])
def r_nearby(s):
    from caed import fdd_agent as A
    code = s.get("code") or "072404"
    g = A.stores(code)
    if not (g["brand_raw"] == s["brand"]).any():
        code = "072405" if code == "072404" else "072404"
        g = A.stores(code)
    LOG.append({"tool": "인허가 업소 명부", "source": "서울 열린데이터광장 지방행정 인허가(LOCALDATA)", "rows": int(len(g)), "sec": 0})
    x, y, where = locate(s.get("place"), code)
    b = g[(g["brand_raw"] == s["brand"]) & ~g["gone"]].dropna(subset=["x", "y"])
    b = b.assign(dist=np.hypot(b["x"] - x, b["y"] - y)).sort_values("dist").head(10)
    b["거리"] = (b["dist"]).round().astype(int).astype(str) + "m"
    body = (f"# 인근 가맹점 현황문서 초안 — {s['brand']}\n\n예정지: {where}\n\n"
            + md_table(b.rename(columns={"name": "상호", "addr": "소재지", "open": "개업일"}), ["상호", "소재지", "개업일", "거리"])
            + "\n\n- 전화번호 칸은 인허가 자료에 없어 본부 명단에서 채운다.\n- 반경 500m 안 같은 브랜드: "
            + f"{int((b['dist'] <= 500).sum())}곳(영업지역 계약 조항과 대조)\n")
    return body, {"brand": s["brand"], "n": len(b), "within500": int((b["dist"] <= 500).sum())}


def locate(place, code):
    """'마포구 양화로 45' 같은 주소 일부 -> 인허가 주소가 맞는 업소들의 좌표 평균. 없으면 구 중심."""
    if not place:
        return 198000.0, 451000.0, "서울 중심(예정지 미지정)"
    for c in (code, "072404", "072405", "051801"):
        g = permits(c)
        hit = g[g["addr"].str.replace(" ", "").str.contains(re.escape(place.replace(" ", "")), na=False)].dropna(subset=["x", "y"])
        if len(hit):
            return float(hit["x"].median()), float(hit["y"].median()), f"{place} (인허가 주소 {len(hit)}건 좌표)"
        gu = place.split()[0] if place.split() and place.split()[0].endswith("구") else None
        if gu and (g["gu"] == gu).any():
            h = g[g["gu"] == gu].dropna(subset=["x", "y"])
            return float(h["x"].median()), float(h["y"].median()), f"{gu} 중심(주소 미일치)"
    return 198000.0, 451000.0, "서울 중심(주소 미일치)"


@recipe("kyb", "은행·상호금융·보증기관·기업 구매팀", "사업장 실재·이력 확인서(차주·거래처 1장)",
        "은행연합회 자금용도외 유용 사후점검준칙 개정(2026-07-30): 개인사업자 5천만 원 초과 대출 사후점검. 거래처 등록 실사",
        "담당자가 서류 확인·현장 방문(1건 수십 분~반나절, 추정)",
        "현장점검 대상 선정과 판단은 금융기관·기업이 한다. 점수를 내지 않는다",
        ["사업장", "실재", "차주", "거래처", "사후점검", "실사", "영업 중인지"], ["store", "gu", "code", "corp"])
def r_kyb(s):
    codes = [s["code"]] if s.get("code") else list(IND_NM)
    code, g, hit = find_store(s["store"], s.get("gu"), codes)
    if hit is None:
        return f"# 사업장 확인서 — '{s['store']}'\n\n인허가 업종 {', '.join(IND_NM[c] for c in codes)}에서 찾지 못했습니다. 인허가가 필요 없는 업종일 수 있습니다.\n", {"found": False}
    row = hit.iloc[0]
    prev = turnover(g, row)
    st = store_list()
    cats = STORE_CATS[code]
    sub = st if cats is None else st[st["indsSclsNm"].isin(cats)]
    listed = bool(len(near(sub, row["x"], row["y"], 30.0))) if pd.notna(row["x"]) else None
    body = [f"# 사업장 실재·이력 확인서 — {row['name']}", "", "> 확인 자료입니다. 점수가 아니며, 판단은 요청 기관이 합니다.", "",
            "| 항목 | 내용 |", "|---|---|",
            f"| 업종 | {IND_NM[code]} |", f"| 소재지 | {row['addr'] or row['gu']} |",
            f"| 인허가 상태 | {'영업 중' if row['alive'] else '폐업 ' + (f'{row.close:%Y-%m-%d}' if pd.notna(row['close']) else '')} |",
            f"| 인허가일 | {row['open']:%Y-%m-%d} (업력 {(pd.Timestamp.now() - row['open']).days / 365.25:.1f}년) |",
            f"| 같은 자리 지난 10년 교체 | {len(prev)}번 |",
            f"| 상가 목록 대조({st['ym'].iloc[0]}) | {'같은 업종 점포 있음' if listed else '같은 업종 점포 못 찾음'} (참고·미검증, H-2026-10-AD 기각) |",
            f"| 같은 상호 다른 인허가 | {len(hit) - 1}건 |", "",
            "## 같은 자리 이전 업소", md_table(prev.rename(columns={"open": "개업", "close": "폐업"}), ["개업", "폐업"]), ""]
    if s.get("corp"):
        fl = dart_filings(s["corp"])
        ac = dart_accounts(s["corp"], [pd.Timestamp.now().year - 2, pd.Timestamp.now().year - 1])
        body += ["## 법인 공시·재무 (OpenDART)"]
        if len(ac):
            p = ac[ac["account"].isin(["매출액", "영업이익", "당기순이익", "자산총계", "부채총계"])].drop_duplicates(["year", "account"])
            body += [md_table(p, ["year", "account", "amount"])]
        if len(fl):
            body += ["", md_table(fl.head(8), ["report_nm", "rcept_dt"])]
        if not len(ac) and not len(fl):
            body += ["_DART에서 찾지 못함(외부감사 대상이 아닐 수 있음)_"]
    return "\n".join(body) + "\n", {"found": True, "alive": bool(row["alive"]), "turnover": len(prev), "listed": listed}


@recipe("register", "구청 위생과 등 인허가 관청", "인허가 대장 정비 확인 목록",
        "식품위생법 등: 폐업 신고 누락 업소 정리, 점검 대상 관리",
        "공무원 현장 확인(이미 없어진 가게를 점검 대상에 넣는 헛걸음)",
        "현장 확인과 직권 처리는 관청이 판단",
        ["대장", "정비", "유령", "폐업 미신고", "점검 대상"], ["gu", "code"])
def r_register(s):
    code = s.get("code") or "072405"
    g = permits(code)
    g = g[g["alive"] & (g["gu"] == s["gu"]) & (g["open"] <= pd.Timestamp("2026-03-31"))].dropna(subset=["x", "y"]).reset_index(drop=True)
    st = store_list()
    cats = STORE_CATS[code] or ["백반/한식", "한식", "중식", "일식"]
    sub = st[st["indsSclsNm"].isin(cats)] if STORE_CATS[code] else st[st["indsLclsNm"].astype(str).str.contains("음식")] if "indsLclsNm" in st else st
    from scipy.spatial import cKDTree
    hits = cKDTree(sub[["x", "y"]].to_numpy()).query_ball_point(g[["x", "y"]].to_numpy(), 30.0)
    g["found"] = [bool(h) for h in hits]
    miss = g[~g["found"]].sort_values("open")
    body = (f"# 인허가 대장 정비 확인 목록 — {s['gu']} {IND_NM[code]}\n\n장부 영업 중 {len(g):,}곳 중 상가 목록({st['ym'].iloc[0]}) 반경 30m에 같은 업종이 없는 곳 **{len(miss):,}곳**.\n"
            "'못 찾음 ≠ 폐업'입니다(상가 목록에도 누락이 있음). 오래된 인허가부터 현장 확인 순서로 정렬했습니다.\n\n"
            + md_table(miss.head(40).rename(columns={"name": "상호", "addr": "소재지", "open": "인허가일"}), ["상호", "소재지", "인허가일"]) + "\n")
    return body, {"gu": s["gu"], "operating": len(g), "not_found": len(miss)}


@recipe("baseline", "예비 창업자·창업 컨설턴트·정책자금 심사역", "동네 업종 기준선(개업·폐업 흐름)",
        "정책자금·보증 심사의 사업장·상권 검토, 창업 계획서의 시장 분석",
        "컨설턴트 상권 보고서(유료) 또는 담당자 수작업 집계",
        "점수가 아닌 기준선 자료 - 판단은 사용자",
        ["폐업률", "기준선", "창업", "개업", "동네", "업종 현황", "생존"], ["gu", "code"])
def r_baseline(s):
    code = s.get("code") or "072405"
    g = permits(code)
    now = pd.Timestamp.now().normalize() - pd.offsets.MonthEnd(1)
    rows = []
    for nm, h in (("서울 전체", g), (s.get("gu") or "서울 전체", g[g["gu"] == s["gu"]] if s.get("gu") else g)):
        alive = lambda t: int(((h["open"] <= t) & (h["close"].isna() | (h["close"] > t))).sum())  # noqa: E731
        t1, t0 = now, now - pd.DateOffset(years=1)
        coh = h[(h["open"] > t0 - pd.DateOffset(years=1)) & (h["open"] <= t0)]
        cl = coh["close"].notna() & (coh["close"] <= coh["open"] + pd.DateOffset(years=1))
        first = float(cl.mean()) if len(coh) else np.nan
        tr = reopened(h, coh[cl])       # 같은 자리(10m) -30~+180일 재개업 = 양도·명의변경 추정(H-2026-10-Z 정의)
        adj = float((cl.sum() - tr) / len(coh)) if len(coh) else np.nan
        rows.append({"지역": nm, "영업 중": alive(t1), "12개월 개업": int(((h["open"] > t0) & (h["open"] <= t1)).sum()),
                     "12개월 폐업": int(((h["close"] > t0) & (h["close"] <= t1)).sum()), "직전 해 개업 첫해 폐업": f"{first:.1%}",
                     "양도 추정 뺀 첫해 폐업": f"{adj:.1%}"})
    R = pd.DataFrame(rows).drop_duplicates("지역")
    body = (f"# 동네 업종 기준선 — {s.get('gu') or '서울'} {IND_NM[code]} ({now:%Y-%m} 기준)\n\n" + md_table(R, list(R.columns))
            + "\n\n- 첫해 폐업에는 같은 자리 양도(명의변경)가 섞여 있다(H-2026-10-Z: 카페는 상당 부분 착시).\n")
    return body, {"rows": R.to_dict("records")}


@recipe("financials", "기업 구매·재무팀, 가맹 희망자", "회사 재무·공시 요약",
        "거래처 신용 검토, 가맹본부 재무 확인(정보공개서 재무 항목)",
        "DART에서 사람이 보고서를 찾아 숫자를 옮김",
        "숫자는 원문 공시로 확인",
        ["재무", "재무제표", "감사보고서", "매출", "공시"], ["corp"])
def r_fin(s):
    y = pd.Timestamp.now().year
    ac = dart_accounts(s["corp"], [y - 3, y - 2, y - 1])
    fl = dart_filings(s["corp"])
    body = [f"# 회사 재무·공시 요약 — {s['corp']}", ""]
    if len(ac):
        p = ac[ac["account"].isin(["매출액", "영업이익", "당기순이익", "자산총계", "부채총계", "자본총계"])].drop_duplicates(["year", "account"])
        pv = p.pivot(index="account", columns="year", values="amount").rename(columns=str).reset_index()
        body += [md_table(pv, ["account"] + sorted(str(y) for y in p["year"].unique()))]
    else:
        body += ["사업보고서 제출 회사가 아니어서 구조화 재무는 없습니다. 아래 감사보고서 원문을 확인하세요."]
    if len(fl):
        body += ["", "## 최근 공시", md_table(fl.head(10).assign(link="https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + fl["rcept_no"]), ["report_nm", "rcept_dt", "link"])]
    return "\n".join(body) + "\n", {"accounts": len(ac), "filings": len(fl)}


# ---------------------------------------------------------------- 접수(레시피 고르기 + 빈칸)
def intake(text):
    t = text.replace("　", " ")
    score = {rid: sum(k in t for k in r["keywords"]) for rid, r in RECIPES.items()}
    rid = max(score, key=score.get)
    if score[rid] == 0:
        return None, {}
    s = {}
    m = re.search(r"(\S+구)\b", t)
    if m:
        s["gu"] = m.group(1)
    for k, c in IND.items():
        if k in t:
            s["code"] = c
            break
    m = re.search(r"(20\d\d)\s*(?:년|회계)", t)
    if m:
        s["fy"] = int(m.group(1))
    m = re.search(r"[\"'“‘]([^\"'”’]+)[\"'”’]", t)
    quoted = m.group(1) if m else None
    m = re.search(r"((?:\(주\)|㈜|주식회사\s*)\S+|\S+(?:\(주\)|㈜))", t)
    if m:
        s["corp"] = re.sub(r"\(주\)|㈜|주식회사", "", m.group(1)).strip()
    m = re.search(r"예정지\s*[:=]?\s*([^,\n]+?)(?:\s*(?:인근|기준|으로|에서|,|$))", t)
    if m:
        s["place"] = m.group(1).strip()
    first = t.split()[0] if t.split() else ""
    if rid in ("fdd_update", "nearby10"):
        s["brand"] = quoted or first
    if rid == "kyb":
        s["store"] = quoted or first
    if rid == "financials" and "corp" not in s:
        s["corp"] = quoted or first
    return rid, s


def handle(text, save=True):
    LOG.clear()
    t0 = time.time()
    rid, s = intake(text)
    if rid is None:
        return None
    r = RECIPES[rid]
    body, info = r["fn"](s)
    sec = time.time() - t0
    head = [f"<!-- 요청: {text} -->", "",
            f"> **대신 한 일**: {r['task']} · 보통 하는 사람: {r['who']}",
            f"> **근거**: {r['basis']}",
            f"> **사람이 할 때**: {r['human_cost']} → **에이전트**: {sec:.0f}초",
            f"> **사람이 마지막에 할 일**: {r['signoff']}", ""]
    srcs = pd.DataFrame(LOG).groupby(["tool", "source"], as_index=False)["rows"].max() if LOG else pd.DataFrame()
    tail = ["", "## 작업 기록", f"- 접수: 레시피 `{rid}`, 빈칸 {json.dumps(s, ensure_ascii=False)}",
            *[f"- 도구: {x.tool} — {x.source} ({x.rows:,}행)" for x in srcs.itertuples()], f"- 걸린 시간: {sec:.1f}초"]
    doc = "\n".join(head) + body + "\n".join(tail) + "\n"
    path = None
    if save:
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, f"{pd.Timestamp.now():%Y%m%d_%H%M%S}_{rid}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(doc)
    return {"request": text, "recipe": rid, "slots": s, "sec": round(sec, 1), "path": path, "info": info,
            "tools": srcs.to_dict("records") if len(srcs) else []}


DEMO = ["'비비큐' 2025년 정보공개서 정기변경 준비해줘",
        "'교촌치킨' 인근가맹점 10곳 문서 만들어줘 예정지 마포구 양화로",
        "'스타벅스' 마포구 카페 사업장 실재 확인해줘, 거래처 등록 실사용",
        "마포구 카페 인허가 대장 정비 목록 뽑아줘",
        "마포구 카페 창업 전에 동네 폐업률 기준선 보여줘",
        "(주)교촌에프앤비 재무제표 요약해줘"]


def main():
    a = sys.argv[1:]
    if not a or a[0] == "list":
        for rid, r in RECIPES.items():
            print(f"[{rid}] {r['task']} — {r['who']}\n    근거: {r['basis']}\n    사람이 할 때: {r['human_cost']}\n    예: {', '.join(r['keywords'][:3])}")
        return
    if a[0] == "demo":
        res = []
        for q in DEMO:
            out = handle(q)
            print(f"{out['sec']:>6.1f}s  {out['recipe']:<11} {q}")
            res.append(out)
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "demo.json"), "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
        return
    out = handle(" ".join(a))
    print("요청을 이해하지 못했습니다 - list로 할 수 있는 일을 보세요." if out is None else json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()

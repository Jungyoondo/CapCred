"""서울 지방행정 인허가(LOCALDATA) 업종별 수집 - 서울 열린데이터광장 openAPI, 1,000행씩, 이어받기 가능 (2026-10-20).

python -X utf8 -m caed.localdata 051801 062001 ...   # 업종 코드(서비스명 LOCALDATA_<코드>) 받기 -> data/caed/localdata/<코드>.csv
python -X utf8 -m caed.localdata --all               # INDUSTRIES 전부

필요한 열만 남긴다(자치구 코드+관리번호 = 업소 키·인허가일·폐업일·취소일·상태·면적·좌표·자치구·업태). 상호·전화번호는 저장하지 않는다.
페이지마다 data/caed/localdata/<코드>.parts/ 에 저장 -> 끊겨도 받은 페이지는 건너뛴다.
출처 표시: 서울 열린데이터광장(공공누리). 코드 목록은 10-20 openAPI 탐색으로 확인한 것.
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "caed", "localdata")
INDUSTRIES = {   # 코드: (이름, 10-20 기준 건수)
    "104201": ("헬스장(체력단련장)", 7343), "104101": ("체육도장(태권도 등)", 5729), "051801": ("미용실", 100054),
    "051901": ("이용원", 15641), "062001": ("세탁소", 15365), "072301": ("단란주점", 11616), "103201": ("당구장", 14041),
    "010102": ("의원", 37723), "072405": ("휴게음식점(카페 등)", 148137), "072404": ("일반음식점", 539188),
}
KEEP = ["OPNSFTEAMCODE", "MGTNO", "APVPERMYMD", "DCBYMD", "APVCANCELYMD", "DTLSTATENM", "SITEAREA", "X", "Y", "RDNWHLADDR", "SITEWHLADDR", "UPTAENM"]


def _key():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _env  # noqa: F401
    return (os.getenv("SEOUL_API_KEY") or "").strip()


def fetch(code, workers=4):
    import requests
    from concurrent.futures import ThreadPoolExecutor
    svc, key = f"LOCALDATA_{code}", _key()
    parts = os.path.join(OUT, f"{code}.parts")
    os.makedirs(parts, exist_ok=True)
    first = requests.get(f"http://openapi.seoul.go.kr:8088/{key}/json/{svc}/1/1/", timeout=30).json()[svc]
    total = int(first["list_total_count"])
    starts = list(range(1, total + 1, 1000))

    def page(s):
        p = os.path.join(parts, f"{s:07d}.csv")
        if os.path.exists(p):
            return 0
        for _ in range(3):
            try:
                rows = requests.get(f"http://openapi.seoul.go.kr:8088/{key}/json/{svc}/{s}/{min(s + 999, total)}/", timeout=60).json()[svc]["row"]
                df = pd.DataFrame(rows)
                df = df[[c for c in KEEP if c in df.columns]].apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)
                df["gu"] = df["RDNWHLADDR"].where(df["RDNWHLADDR"] != "", df["SITEWHLADDR"]).str.split().str[1]
                df.drop(columns=[c for c in ("RDNWHLADDR", "SITEWHLADDR") if c in df.columns]).to_csv(p, index=False, encoding="utf-8")
                return len(df)
            except Exception:  # noqa: BLE001
                continue
        return -1

    with ThreadPoolExecutor(workers) as ex:
        got = list(ex.map(page, starts))
    fails = sum(1 for g in got if g < 0)
    if fails:
        print(f"{code}: {fails} pages failed - run again to resume")
        return None
    df = pd.concat([pd.read_csv(os.path.join(parts, f), dtype=str, keep_default_na=False) for f in sorted(os.listdir(parts))],
                   ignore_index=True).drop_duplicates()   # 관리번호는 자치구마다 따로 매겨져 겹친다(10-20 확인) - 같은 행만 지움
    df.to_csv(os.path.join(OUT, f"{code}.csv"), index=False, encoding="utf-8")
    print(f"{code} {INDUSTRIES.get(code, ('?',))[0]}: {len(df):,} rows (api total {total:,})")
    return df


def load(code):
    p = os.path.join(OUT, f"{code}.csv")
    if not os.path.exists(p):
        fetch(code)
    return pd.read_csv(p, dtype=str, keep_default_na=False)


if __name__ == "__main__":
    codes = list(INDUSTRIES) if "--all" in sys.argv else [a for a in sys.argv[1:] if not a.startswith("-")]
    for c in codes:
        if not os.path.exists(os.path.join(OUT, f"{c}.csv")):
            fetch(c)


def fetch_names(code, workers=4):
    """대조용 상호명(로컬 전용, data/ git 제외) - 키(자치구 코드+관리번호)와 상호만. 제출물·사이트에는 쓰지 않는다(10-20 유령 인허가 대조용)."""
    import requests
    from concurrent.futures import ThreadPoolExecutor
    svc, key = f"LOCALDATA_{code}", _key()
    parts = os.path.join(OUT, f"{code}.names.parts")
    os.makedirs(parts, exist_ok=True)
    total = int(requests.get(f"http://openapi.seoul.go.kr:8088/{key}/json/{svc}/1/1/", timeout=30).json()[svc]["list_total_count"])

    def page(s):
        p = os.path.join(parts, f"{s:07d}.csv")
        if os.path.exists(p):
            return 0
        for _ in range(3):
            try:
                rows = requests.get(f"http://openapi.seoul.go.kr:8088/{key}/json/{svc}/{s}/{min(s + 999, total)}/", timeout=60).json()[svc]["row"]
                df = pd.DataFrame(rows)
                df = df[[c for c in ("OPNSFTEAMCODE", "MGTNO", "BPLCNM", "DTLSTATENM", "APVPERMYMD", "X", "Y", "SITEAREA", "RDNWHLADDR") if c in df]]
                df.apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c).to_csv(p, index=False, encoding="utf-8")
                return len(df)
            except Exception:  # noqa: BLE001
                continue
        return -1
    with ThreadPoolExecutor(workers) as ex:
        got = list(ex.map(page, range(1, total + 1, 1000)))
    if any(g < 0 for g in got):
        print(f"{code} names: some pages failed - run again")
        return None
    df = pd.concat([pd.read_csv(os.path.join(parts, f), dtype=str, keep_default_na=False) for f in sorted(os.listdir(parts))]).drop_duplicates()
    df.to_csv(os.path.join(OUT, f"{code}.names.csv"), index=False, encoding="utf-8")
    print(f"{code} names: {len(df):,}")
    return df

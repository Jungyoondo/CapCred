"""소상공인시장진흥공단 상가(상권)정보 - 서울 전체 점포 스냅샷 수집 (2026-10-20, data.go.kr 활용신청 사용자 완료).

python -X utf8 -m caed.store_registry fetch     # -> data/caed/stores/seoul_<기준연월>.csv (페이지별 이어받기)

용도: 인허가 대장의 '영업 중'이 실제로 있는지 대조(caed/ghost_permits.py), 프랜차이즈·층 정보.
상호명은 대조에만 쓰고 data/(git 제외)에만 둔다 - 제출물·사이트에는 집계만 낸다.
좌표: 상가정보는 WGS84 경위도, 인허가(LOCALDATA)는 EPSG:5174(10-20 '망우로 60' 헬스장으로 확인).
"""
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "caed", "stores")
URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"
COLS = ["bizesId", "bizesNm", "brchNm", "indsLclsNm", "indsMclsNm", "indsSclsCd", "indsSclsNm", "ksicCd", "signguNm", "adongCd", "adongNm",
        "bldMngNo", "flrNo", "lon", "lat"]


def _key():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _env  # noqa: F401
    return (os.getenv("DATA_GO_KR_SERVICE_KEY") or "").strip()


def fetch(ctprvn="11", workers=4):
    import requests
    from concurrent.futures import ThreadPoolExecutor
    key = _key()
    head = requests.get(URL, params={"serviceKey": key, "type": "json", "numOfRows": 1, "pageNo": 1, "divId": "ctprvnCd", "key": ctprvn}, timeout=60).json()
    ym, total = head["header"]["stdrYm"], int(head["body"]["totalCount"])
    parts = os.path.join(OUT, f"seoul_{ym}.parts")
    os.makedirs(parts, exist_ok=True)

    def page(n):
        p = os.path.join(parts, f"{n:04d}.csv")
        if os.path.exists(p):
            return 0
        for _ in range(4):
            try:
                it = requests.get(URL, params={"serviceKey": key, "type": "json", "numOfRows": 1000, "pageNo": n, "divId": "ctprvnCd", "key": ctprvn},
                                  timeout=120).json()["body"]["items"]
                pd.DataFrame(it).reindex(columns=COLS).to_csv(p, index=False, encoding="utf-8")
                return len(it)
            except Exception:  # noqa: BLE001
                continue
        return -1
    pages = range(1, (total + 999) // 1000 + 1)
    with ThreadPoolExecutor(workers) as ex:
        got = list(ex.map(page, pages))
    if any(g < 0 for g in got):
        print(f"{sum(g < 0 for g in got)} pages failed - run again")
        return None
    df = pd.concat([pd.read_csv(os.path.join(parts, f), dtype=str, keep_default_na=False) for f in sorted(os.listdir(parts))]).drop_duplicates("bizesId")
    out = os.path.join(OUT, f"seoul_{ym}.csv")
    df.to_csv(out, index=False, encoding="utf-8")
    print(f"stores {ym}: {len(df):,} (api total {total:,}) -> {out}")
    return df


def latest():
    fs = sorted(f for f in os.listdir(OUT) if f.startswith("seoul_") and f.endswith(".csv"))
    return pd.read_csv(os.path.join(OUT, fs[-1]), dtype=str, keep_default_na=False), fs[-1][6:12]


if __name__ == "__main__":
    if "fetch" in sys.argv:
        fetch()

"""신용캐드 환경변수 로더(2026-10-08 econ-lab 편입).

키 값은 코드·저장소에 두지 않는다. 순서: econ-lab/.env -> 원 프로젝트 폴더의 DATA.env(있으면).
필요한 이름: SEOUL_API_KEY, KOSIS_API_KEY, NAVER_SEARCH_CLIENT_ID/SECRET, NAVER_TREND_CLIENT_ID/SECRET
"""
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "caed"           # 상권 CSV(대용량, git 제외)
for _p in (ROOT / ".env", Path.home() / "anaconda_projects" / "db" / "Finnect" / "DATA.env",
           Path.home() / "anaconda_projects" / "db" / "DATA.env"):
    if _p.exists():
        load_dotenv(_p, override=False)

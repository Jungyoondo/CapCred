"""신용캐드(Credit CAED) - 소상공인 공정신용 진단 모듈 (2026-10-08 원 프로젝트 anaconda_projects/db/Finnect에서 편입).

원 코드는 모듈끼리 `import model as M`처럼 평평하게 불러서, 패키지로 쓸 때 이 폴더를 경로에 넣는다.
옮기지 않은 것: config.py / collectors.py / main.py(옛 파이프라인, config.py에 키 평문) - 키는 .env로만.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 제출물 숫자 대조 (자동, scripts/audit_deliverable_numbers.py)

원천 결과 파일과 제출물 문구를 맞춘다. '확인'이 있으면 원천이 바뀌었거나 제출물 문구가 다르다.

| 상태 | 주장 | 제출물 표기 | 원천 값 | 들어 있어야 할 곳 |
|---|---|---|---|---|
| OK | 공시 예측력 AUC(코스닥, 공시만) | 0.68 | 0.68 | motion |
| OK | 가격만 AUC | 0.55 | 0.55 | motion |
| OK | 상위 10% 위험률 | 19.6 | 19.6 | motion, film |
| OK | 평균 위험률 | 6.1 | 6.1 | motion |
| OK | 상위 10% 배수 | 3.2 | 3.2 | motion, film |
| OK | 상위 10% 포착 | 32 | 32 | motion |
| OK | 연도별 AUC 범위 | 0.64~0.70 | 0.64~0.70 | motion |
| OK | 퇴출 기업 수(코스닥) | 497 | 497 | motion, film |
| OK | 퇴출 포함 상위 10% 위험률 | 27.0 | 27.0 | motion |
| OK | 가상 성적표 개월 수 | 45 | 45 | motion, film |
| OK | 평균보다 높았던 달 | 100 | 100 | motion |
| OK | 소형사 오경보 전통 | 26.4 | 26.4 | motion, film |
| OK | 소형사 오경보 결합 | 18.5 | 18.5 | motion, film |
| OK | 대형사 오경보 전통 | 2.5 | 2.5 | motion |
| OK | AUC 전통 -> 결합 | 0.663→0.669 | 0.663→0.669 | motion |
| OK | 결합 모델이 풀어 준 건수 | 489 | 489 | motion |
| OK | 새로 경고한 건수 | 631 | 631 | motion |
| OK | 경고 목록 코스닥/코스피 | 144/73 | 144/73 | motion |
| OK | 자금조달 3건+ 위험률 | 24.6 | 24.6 | motion |
| OK | 제목만으로 잡는 큰 급락(코스피~코스닥) | 9~13 | 9~13 | motion, report, plan, pilot, onepager |
| OK | 소상공인 업소 수(10개 업종) | 894,933 | 894,933 | report, plan |
| OK | 음식점 업력<1년 폐업률 | 14.7 | 14.7 | report, plan |
| OK | 음식점 10년+ 폐업률 | 7.2 | 7.2 | report, plan |
| OK | 음식점 면적 하위 20% 폐업률 | 14.2 | 14.2 | report, plan |
| OK | 헬스장 대장 포착률 | 17 | 17 | report, plan |
| OK | 음식점 대장 포착률 | 76 | 76 | report, plan |
| OK | 사전 가설 I1 업력 | 2/9 | 2/9 | report, plan |
| OK | 헬스장 봉인 수(v2) | 4416 | 4416 | report, plan |
| OK | 카페 프랜차이즈 1년 폐업률 | 6.2 | 6.2 | report, plan |
| OK | 카페 독립 1년 폐업률 | 15.7 | 15.7 | report, plan |
| OK | 음식점 프랜차이즈 1년 폐업률 | 6.4 | 6.4 | report, plan |
| OK | 카페 쇠퇴 브랜드 가맹점 폐업률 | 17.5 | 17.5 | report, plan |
| OK | 카페 성장 브랜드 가맹점 폐업률 | 2.5 | 2.5 | report, plan |
| OK | 카페 AUC +브랜드 | 0.778 | 0.778 | report, plan |
| OK | 공정위 매칭 카페 | 74 | 74 | report |
| OK | 공정위 매칭 음식점 | 87 | 87 | report |
| OK | 등록 이탈 건수 | 4건/470건 | 4건/470건 | report, plan |
| OK | D1 카페 쇠퇴 | 17.0 | 17.0 | report |
| OK | D2 카페 상위 | 12.0 | 12.0 | report |
| OK | 브랜드 봉인 수 | 473 | 473 | report, plan |
| OK | 실적 표류 상위 10% 60일 | +2.9 | +2.9 | report |
| OK | 실적 표류 하위 10% 60일 | -3.0 | -3.0 | report |
| OK | 실적 표류 t(코스닥) | 5.1 | 5.1 | report |
| OK | 실적 표류 코스피 차이 | +3.5 | +3.5 | report |
| OK | 분기 실적 기업 수 | 2,408 | 2,408 | report |
| OK | PEAD 슬리브 IR | 0.37 | 0.37 | report |
| OK | AC 예상값 오차 감소 | 16.8 | 16.8 | daeri, m1, brief |
| OK | AC 작년 복사 오차 | 5.54 | 5.54 | daeri |
| OK | AC 예상값 오차 | 4.60 | 4.60 | daeri |
| OK | AC 경보 정밀도 | 83.2 | 83.2 | daeri, brief |
| OK | AC 경보 정밀도(반올림) | 83 | 83 | m1 |
| OK | AC 대상 브랜드 | 879 | 879 | daeri, m1, brief |
| OK | 재현 브랜드 수 | 537 | 537 | daeri, brief |
| OK | 재현 매장 변동 | 1,995 | 1,995 | daeri, brief |
| OK | 재현 경보 적중 | 88 | 88 | daeri, brief |
| OK | AB2 방향 반대 비율 | 6.4 | 6.4 | daeri, brief |
| OK | AD 유령 폐업 배수 | 1.5 | 1.5 | daeri, brief |
| OK | 실전 봉인 브랜드 수(AF) | 334 | 334 | daeri, brief |
| OK | AE 폐점률 순위상관 | -0.02 | -0.02 | daeri, brief |
| OK | 소상공인 업소 수(CapCred) | 894,933 | 894,933 | daeri, f1 |

합계 60개 중 확인 필요 0개

자동 대조 밖(사람 확인): 외부 출처 숫자(상폐 사유 42곳·담보대출 62조 - 헤럴드경제), 공시 26만 6천 건, 신용캐드 시연값(79.4 A -> 84.4 AA, 합성 데이터).

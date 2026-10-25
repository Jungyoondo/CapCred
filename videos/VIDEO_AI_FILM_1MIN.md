# 1분 AI 영화 — 「A씨의 4월」 (CapCred 사업 소개, 약 61초)

> 사용자 방향(10-26): 사람이 등장한다. **회사원 A씨가 걱정하고, CapCred 캐릭터가 나타나 문제를 풀어 준다.**
> 보고서·모션그래픽과 **겹치는 장면이 없어야 한다**. 그 둘의 화면·도표·숫자 장면은 쓰지 않는다. 마지막 **서울 야경**(인허가 89만 곳 점 지도)은 그대로 쓴다.
> 모션그래픽이 "어떻게 시험했나"를 숫자로 보여 준다면, 이 영화는 "누구의 어떤 하루를 바꾸나"를 이야기로 보여 준다.

## 0. 지금 상태
- 완성 영상: `deliverables/final/ai_film.mp4`(61.3초)와 자막 `ai_film.srt`.
- 렌더: `python -X utf8 scripts/render_film2.py`. 인물·캐릭터·소품은 코드로 그린 2D 애니메이션이고, 내레이션은 Windows 한국어 음성(Heami) 초안이다.
- 영상 생성 AI로 실사·3D판을 만들 때는 아래 3절의 캐릭터 묘사와 컷 프롬프트를 쓴다.

## 1. 등장인물 (가상)
| 인물 | 설정 | 그림 |
|---|---|---|
| A씨 | 작은 프랜차이즈 본부의 회사원(가맹점 몇 곳 규모). 퇴근 직전 팀장에게서 "정보공개서 정기변경, 4월 30일까지"라는 메시지를 받는다 | 짧은 검은 머리, 하늘색 셔츠, 남색 넥타이. 걱정 → 놀람 → 안도 → 웃음 |
| CapCred | 노트북에서 나타나는 하늘색 둥근 캐릭터. 얼굴 화면에 두 눈, 노란 안테나, 가슴에 "CC" 배지 | 떠다니며 손을 흔든다. 공공 기록 카드를 모아 초안을 만든다 |

## 2. 컷 리스트 (8컷)
| # | 장면 | 자막·내레이션 | 보고서·모션과 겹치나 |
|---|---|---|---|
| 1 | 4월 28일 오후 6시 20분, 야경이 보이는 사무실. A씨 책상 옆 휴대폰에 팀장 메시지 "정보공개서 정기변경 4월 30일까지 부탁해요!" → A씨 표정이 굳는다 | 작은 프랜차이즈 본부의 회사원 A씨. 퇴근 직전, 팀장님 메시지 한 줄에 마음이 무거워집니다. | 없음 |
| 2 | 걱정 말풍선 4개("가맹점이 몇 곳 열고 닫았더라?", "작년 숫자 그대로 내도 되나?", "대행 맡기면 한 건에 30만 원…", "늦으면 과태료…"), 4월 30일 달력 | 가맹점이 몇 곳 열고 닫았는지, 작년 숫자를 그대로 내도 되는지. 맡기자니 한 건에 30만 원, 늦으면 과태료입니다. | 없음(그림 말풍선) |
| 3 | 노트북이 빛나고 CapCred가 튀어나온다. A씨가 놀란다. "안녕하세요, CapCred예요! 해야 하는 일을 말해 주세요" | 그때, 노트북에서 CapCred가 나타납니다. 해야 하는 일을 이유와 함께 한 줄로 말하면 됩니다. | 없음 |
| 4 | A씨가 말한다: "4월 30일까지 정보공개서를 고쳐야 해서요. 우리 브랜드 정기변경 준비해 줘!" → '서울 인허가 기록', '공정위 가맹정보', '전자공시 DART' 카드가 날아와 CapCred 둘레를 돈다 | CapCred는 서울 인허가 기록과 공정위 가맹정보, 전자공시를 불러와 숫자를 미리 채웁니다. | 없음 |
| 5 | CapCred가 '정보공개서 정기변경 초안' 종이를 건넨다. 두 줄에 노란 표시와 ▲▼. "크게 바뀔 곳 두 곳만 확인해 보세요" → A씨가 웃는다 | 크게 바뀔 매장 두 곳은 따로 짚어 줍니다. A씨는 그 두 곳만 확인하면 됩니다. | 없음(실제 시연 화면을 쓰지 않음) |
| 6 | A씨가 '검토·서명' 칸에 서명. 시계 "오후 6시 58분". "오늘은 제시간에 퇴근!" CapCred가 손을 흔든다 | 마지막 확인과 서명은 사람이 합니다. 오늘 A씨는 제시간에 퇴근합니다. | 없음 |
| 7 | 거리. CapCred가 은행 → 구청 → 동네 가게로 날아간다. 말풍선 "대출 사후점검 사업장 확인서", "인허가 대장 정비 목록", "창업 전 동네 업종 기준선" | 은행의 대출 점검도, 구청의 대장 정비도. 누군가 해야 하는 일을 CapCred가 대신합니다. | 내용은 같지만 그림이 다르다(보고서는 화면 캡처, 모션은 상자 도식) |
| 8 | **서울 야경**: 89만 곳 점 지도가 천천히 다가오고, "일할 역량과 믿을 근거 / CapCred / Capacity × Credibility", 손 흔드는 CapCred, 고지 | 서울 89만 개의 문이 열고 닫힌 기록 위에서. 일할 역량과 믿을 근거, CapCred. | 지도는 보고서·모션에 없음 |

**고지(마지막 컷)**: 등장인물·회사는 가상입니다 · 서울 지방행정 인허가 894,933곳의 개업·폐업 기록 · 검토·서명은 사람이 합니다.

## 3. 영상 생성 AI용 프롬프트 (실사·3D판을 따로 만들 때)
- 캐릭터 고정 묘사(모든 프롬프트 앞): `MR_A: a Korean office worker in his early 30s, short black hair, light-blue shirt, navy tie, friendly face` · `CAPCRED: a small floating rounded robot mascot, sky-blue glossy body, dark face screen with two glowing cyan eyes, tiny yellow antenna ball, small "CC" badge, cute and trustworthy`
- 공통 스타일(끝): `Pixar-like 3D animation, soft lighting, night office in Seoul, no readable text, no logos, no watermark`

| # | 프롬프트 |
|---|---|
| 1 | `MR_A at his desk at dusk, city lights through the window, he reads a message on his phone and his face turns worried, slow push-in` |
| 2 | `MR_A rubbing his forehead, floating thought bubbles (empty), a desk calendar, worried, gentle camera sway` |
| 3 | `the laptop screen glows and CAPCRED pops out of it with a sparkle, MR_A leans back surprised` |
| 4 | `MR_A talking to CAPCRED, glowing document cards fly in from the sides and orbit around CAPCRED` |
| 5 | `CAPCRED hands MR_A a printed document with two highlighted lines, MR_A smiles with relief` |
| 6 | `close-up of MR_A signing the document, wall clock near 7pm, CAPCRED waving happily` |
| 7 | `CAPCRED flying along a night street past a bank, a district office with a flag, and a small shop with a striped awning` |
| 8 | `aerial night view of Seoul with thousands of tiny glowing dots, slow zoom` (이 컷은 지금 지도 그림을 그대로 써도 된다) |

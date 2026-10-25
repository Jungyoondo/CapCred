# AI 영상 시나리오·샷 리스트 — 「설명되지 않은 점수」 (약 6분 30초)

> 제출물 2번(AI 영상, 5분 이상). 내용은 사업계획서(DINTEL_BUSINESS_PLAN.md)의 이유 → 내용 → 근거 → 계획 → 절차를 이야기로 옮긴 것이다.
> 모션그래픽 영상(VIDEO_MOTION_SCRIPT.md)이 "숫자로 설명"한다면, 이 영상은 "사람의 문제로 보여 준다".

## 0. 제작 원칙 (먼저 읽기)

1. **인물·회사는 모두 가상이다.**
   - 실존 은행명, 회사명, 로고, 실존 인물 얼굴을 쓰지 않는다.
   - 사고가 나는 상장사는 가상의 "한빛테크"로 한다.
2. **숫자와 한글이 나오는 화면은 AI로 만들지 않는다.** 영상 생성 AI는 한글과 숫자를 깨뜨린다. 모니터, 휴대폰, 문서 화면은 이렇게 처리한다.
   - (a) 실제 사이트를 캡처해 편집에서 합성한다. 사이트는 `python -m sites.biz` → http://127.0.0.1:8766 의 재무위험 조기경보, 공정신용 진단, 오늘의 공시 화면이다.
   - (b) 또는 `deliverables/figures/fig*.png`를 쓴다.
   - AI 프롬프트에는 "blank glowing screen"처럼 빈 화면으로 요청한다.
3. **영상 속 수치는 모두 실측값만 쓴다.** 출처 장면은 6장에 정리했다. 소상공인 점수가 합성 데이터 시제품이라는 점은 마지막 고지 카드에 반드시 넣는다.
4. **"대출이 승인된다"고 약속하지 않는다.** 결말은 이렇다: 심사역이 "낮게 나온 이유"를 보고 추가 심사를 진행한다. 이것이 사업계획서의 포지션("대체가 아닌 보완, 추가 심사 근거")이다.
5. **대사는 화면 밖 목소리(보이스오버)나 뒷모습, 손 위주로 처리한다.** 입 모양 맞추기(립싱크)는 실패가 잦다. 얼굴이 정면으로 나오는 대사 컷은 2개 이하로 줄였다(★ 표시).

## 1. 제작 도구 흐름 (권장)

| 단계 | 할 일 | 도구 예 |
|---|---|---|
| 1 | 인물 기준 이미지: 3인물 × 정면, 측면, 전신 | 이미지 생성 AI(같은 시드·같은 묘사문 유지) |
| 2 | 컷별 첫 프레임 이미지 → 이미지-투-비디오 5~8초 | Veo, Kling, Runway, Sora 등 영상 생성 AI |
| 3 | 화면 합성: 모니터·휴대폰에 실제 캡처 넣기 | CapCut, Premiere, DaVinci(트래킹·코너 핀) |
| 4 | 내레이션·대사 | 본인 녹음 권장. 또는 고품질 한국어 TTS |
| 5 | 음악: 저작권 문제없는 음원 | 음악 생성 AI 또는 무료 음원 라이브러리 |
| 6 | 자막·고지 카드 | 편집 프로그램 |

**인물 일관성 묘사문** (모든 프롬프트 앞에 그대로 붙인다)
- **HAYOON**: `a Korean woman in her mid-30s, athletic build, black hair in a low ponytail, plain charcoal hoodie with no logo, black training pants, warm but tired eyes`
- **SEJIN**: `a Korean woman in her early 40s, navy blazer over white blouse, thin silver-rimmed glasses, shoulder-length straight hair, composed and meticulous`
- **MINJAE**: `a Korean man in his late 20s, gray crewneck sweater, short hair, round glasses, laptop covered with no stickers, focused`

**공통 스타일 문구** (모든 프롬프트 끝): `cinematic, 35mm film look, shallow depth of field, natural color grading, no text, no logos, no watermark`

## 2. 등장인물

| 인물 | 설정 | 사업계획서에서의 역할 |
|---|---|---|
| 하윤 (34) | 서울 성북구 동네 헬스장 사장. 개업 3년, 기구·인테리어에 2억 원 투자 | 신용캐드 인터뷰의 세 장벽(담보·비수기·시설 미반영)을 겪는 차입자 |
| 세진 (41) | 지역 저축은행 여신심사역. 주식담보대출과 소상공인 대출을 함께 본다 | dintel의 1순위 고객(손실이 직접 걸린 심사 부서) |
| 민재 (29) | dintel × 신용캐드 창업자. 혼자 엔진을 만든다 | 화자(내레이션). 절차와 계획을 말한다 |

## 3. 구성 개요

| 막 | 시간 | 제목 | 사업계획서 대응 |
|---|---|---|---|
| 1 | 0:00–1:20 | 설명되지 않은 점수 | 1장 이유 (소상공인), 2장 수요 근거(인터뷰) |
| 2 | 1:20–2:40 | 26만 건 속의 신호 | 1장 이유 (공시는 많고 읽기 어렵다, 담보 손실) |
| 3 | 2:40–4:10 | 두 질문이 만나다 | 0장 결합, 3장 제품 |
| 4 | 4:10–5:20 | 먼저 봉인하고, 나중에 채점한다 | 4장 근거, 공개 성적표 |
| 5 | 5:20–6:30 | 다시, 1월 | 7장 계획, 8장 절차, 한계 고지 |

## 4. 샷 리스트

표기
- **[합성]**: 화면 속 내용을 실제 캡처나 그림으로 넣는다.
- **VO**: 화면 밖 목소리(민재 내레이션).
- **★**: 얼굴이 나오는 대사 컷.

### 1막 — 설명되지 않은 점수 (0:00–1:20)

| # | 시간 | 길이 | 장면 | 영상 생성 프롬프트 (영문) | 소리·대사 | 화면 글자(편집) |
|---|---|---|---|---|---|---|
| 1 | 0:00 | 7초 | 새벽, 빈 헬스장. 형광등이 하나씩 켜진다 | `Wide shot of a small neighborhood gym in Seoul at dawn, rows of treadmills and weight machines, fluorescent ceiling lights flickering on one by one, cold blue light through large windows, empty, quiet` + 공통 | 형광등 소리, 낮은 피아노 | — |
| 2 | 0:07 | 6초 | 하윤이 유리문을 열고 들어온다. 입김 | `HAYOON unlocking a glass gym door from outside on a freezing winter morning, visible breath, keys in gloved hand, seen from inside the gym` + 공통 | 열쇠 소리 | — |
| 3 | 0:13 | 6초 | 출입 명부 클로즈업. 빈칸이 많다 | `Close-up of a clipboard sign-in sheet on a reception desk with mostly empty rows, a pen lying across it, soft morning light` + 공통 | VO: "1월. 헬스장이 가장 조용한 달입니다." | 1월 |
| 4 | 0:19 | 8초 | 하윤이 계산기를 두드리고, 임대료·리스 고지서를 넘긴다 | `HAYOON sitting at a small office desk in the back of a gym, tapping a calculator, flipping through paper bills, worried expression, desk lamp` + 공통 | 하윤(속마음 VO): "이번 달만 넘기면 되는데…" | — |
| 5 | 0:27 | 8초 | 은행 창구. 하윤 맞은편 직원(뒷모습)이 모니터를 본다 | `Bank loan consultation desk, HAYOON seated facing a loan officer whose back is to camera, officer looking at a blank glowing monitor, neutral modern branch interior, no logos` + 공통 | 직원: "매출이 지난 분기보다 많이 줄었네요. 담보로 잡을 만한 자산이 따로 있으세요?" | — |
| 6 ★ | 0:35 | 7초 | 하윤 정면 | `Medium close-up of HAYOON at a bank desk, speaking earnestly, slight frustration, shallow depth of field` + 공통 | 하윤: "기구랑 인테리어에 2억 넘게 들어갔어요." 직원(화면 밖): "그건 평가에 반영이 안 돼서요…" | — |
| 7 | 0:42 | 7초 | 비 오는 거리. 하윤이 휴대폰을 본다 | `HAYOON walking out of a building onto a rainy Seoul street at dusk, looking down at a blank phone screen, city lights reflecting on wet pavement` + 공통 | 빗소리 | [합성] 휴대폰: "심사 결과: 승인 불가 (신용평가 점수 기준 미달)" |
| 8 | 0:49 | 9초 | 하윤이 헬스장으로 돌아와 불 꺼진 기구 사이에 선다 | `HAYOON standing alone among unlit exercise machines at night, silhouette, only street light from window` + 공통 | VO: "점수가 낮다는 건 알았습니다. 왜 낮은지는, 아무도 말해 주지 않았습니다." | — |
| 9 | 0:58 | 10초 | 인터뷰 기록 느낌의 손글씨 메모 세 장 | `Top-down shot of three handwritten notebook pages on a wooden table with blank lines, coffee cup, soft light` + 공통 | VO: "실제로 헬스장 사장님들을 만나 보니 같은 말이 반복됐습니다. 담보가 남지 않는다. 비수기에 더 불리하다. 시설 투자는 보이지 않는다." | [합성] 메모 위 손글씨: 담보 / 비수기 / 시설 투자 |
| 10 | 1:08 | 12초 | 타이틀 | `Slow push-in on a dark gym mirror reflecting a single lit lamp, dust particles in the air` + 공통 | 음악 정지 | **설명되지 않은 점수** |

### 2막 — 26만 건 속의 신호 (1:20–2:40)

| # | 시간 | 길이 | 장면 | 영상 생성 프롬프트 (영문) | 소리·대사 | 화면 글자(편집) |
|---|---|---|---|---|---|---|
| 11 | 1:20 | 8초 | 밤, 저축은행 심사실. 세진의 책상 위 서류 더미와 모니터 세 대 | `SEJIN working late in a credit review office at night, stacks of documents, three blank glowing monitors, city night view through window` + 공통 | 키보드 소리 | — |
| 12 | 1:28 | 10초 | 모니터 클로즈업. 공시 목록이 끝없이 내려간다 | `Over-the-shoulder close-up of a monitor with a blank scrolling list interface, reflections on SEJIN's glasses` + 공통 | VO: "코스닥 상장사가 2015년 이후 낸 공시는 26만 6천 건입니다. 세진의 팀은 주식을 담보로 돈을 빌려준 회사들의 공시를, 매일 사람 눈으로 읽습니다." | [합성] 사업 사이트 "오늘의 공시" 캡처 스크롤 |
| 13 | 1:38 | 6초 | 휴대폰 진동. 세진이 멈춘다 | `Smartphone vibrating on a desk next to SEJIN's hand, she freezes mid-typing` + 공통 | 진동 소리 | [합성] 알림: "한빛테크(가상) 거래정지" |
| 14 | 1:44 | 12초 | 추상 공간. 빛나는 카드가 1년 타임라인 위에 하나씩 쌓인다 | `Abstract dark void, glowing blank paper cards appearing one by one along a horizontal light timeline, each card pulsing amber then red, slow camera dolly` + 공통 | VO: "돌이켜 보면 신호는 있었습니다. 1년 동안 자금조달 세 번, 그리고 최대주주 변경." | [합성] 카드 라벨: 유상증자 → 전환사채 발행 → 전환가액 조정 → 최대주주 변경 |
| 15 | 1:56 | 10초 | 카드들이 수많은 회색 카드 속으로 흩어져 묻힌다 | `Thousands of gray blank cards swirling and burying a few glowing red cards, top-down, dramatic` + 공통 | VO: "문제는, 그 신호가 26만 건 속에 흩어져 있었다는 것입니다. 제목만 보고 거르면 큰 변동의 3분의 1도 잡지 못합니다." | — |
| 16 | 2:06 | 8초 | 팀장(뒷모습)이 세진 책상 옆에 선다 | `A senior manager seen from behind standing beside SEJIN's desk, both looking at a blank monitor, tense atmosphere` + 공통 | 팀장: "이거 미리 알 방법은 없었어요?" | — |
| 17 ★ | 2:14 | 7초 | 세진 정면 | `Close-up of SEJIN taking off her glasses, tired, looking at the screen` + 공통 | 세진: "있었을 거예요. 읽을 사람이 없었을 뿐이죠." | — |
| 18 | 2:21 | 19초 | 도시 야경. 수많은 사무실 창이 켜져 있다 | `Aerial night shot of Seoul office towers with many lit windows, slow drift` + 공통 | VO: "2026년, 상장폐지 기준이 강화되면서 지난 사업연도 퇴출 사유가 생긴 회사만 코스닥 42곳. 주식을 담보로 한 대출은 하루 평균 62조 원. 어느 회사가 위험한지 미리 아는 일에, 큰돈이 걸려 있습니다." | 코스닥 상장폐지 사유 42곳 · 신용융자·주식담보 일평균 62조 원 (출처 자막) |

### 3막 — 두 질문이 만나다 (2:40–4:10)

| # | 시간 | 길이 | 장면 | 영상 생성 프롬프트 (영문) | 소리·대사 | 화면 글자(편집) |
|---|---|---|---|---|---|---|
| 19 | 2:40 | 10초 | 원룸 작업실, 새벽. 민재가 노트북으로 코딩한다 | `MINJAE coding on a laptop in a small studio apartment before dawn, desk lamp, whiteboard on the wall with two blank circles drawn, coffee mugs` + 공통 | VO(민재): "저는 두 가지를 만들고 있었습니다. 동네 사업자의 신용을 공정하게 설명하는 법, 그리고 공시로 상장사의 위험을 미리 읽는 엔진." | — |
| 20 | 2:50 | 10초 | 화이트보드의 두 원이 겹쳐진다 | `Close-up of a whiteboard, a hand drawing two overlapping circles with a marker and shading the overlap` + 공통 | VO: "두 질문은 같은 것이었습니다. 작다는 이유로, 위험하게 보이는가?" | [합성] 원 라벨: 신용캐드 / dintel / 겹친 곳 "가설을 실데이터로" |
| 21 | 3:00 | 12초 | 추상 데이터 흐름. 빛줄기가 프리즘을 지나 세 줄기로 갈라진다 | `Streams of light particles flowing into a glass prism in a dark space and splitting into three colored beams, elegant, slow motion` + 공통 | VO: "공시 원문을 모아 조건을 꺼내고, 그 시점에 공개된 정보만으로 위험을 계산합니다. 조기경보 점수, 공시별 과거 반응, 자금조달 연쇄." | [합성] 세 줄기 라벨: 조기경보 / 반응 통계 / 자금조달 연쇄 |
| 22 | 3:12 | 10초 | 아침, 세진의 사무실. 커피를 들고 모니터를 켠다 | `Morning in the credit office, SEJIN arriving with coffee and switching on a blank monitor, sunlight` + 공통 | VO: "매일 아침, 담보 종목 중 위험이 높은 회사가 근거 공시와 함께 올라옵니다." | [합성] 사업 사이트 "재무위험 조기경보" 캡처 |
| 23 | 3:22 | 10초 | 화면 클로즈업. 세진이 경고 종목을 클릭한다 | `Close-up of a hand clicking a mouse, monitor reflecting on glasses, blank interface` + 공통 | VO: "매수도, 매도도 말하지 않습니다. 확률과, 그 근거만." | [합성] 근거 목록: 자금조달 3건 / 최대주주 변경 / 전환가액 조정 |
| 24 | 3:32 | 8초 | 세진 책상에 소상공인 대출 서류. 표지 사진 속 헬스장 | `A loan application folder placed on a desk, a printed photo of a small gym clipped to the cover, SEJIN opening it` + 공통 | 종이 소리 | [합성] 서류 표지: 하윤 피트니스(가상) |
| 25 | 3:40 | 14초 | 모니터에 공정신용 진단 화면 | `Over-the-shoulder shot of SEJIN reading a blank monitor intently, leaning closer` + 공통 | VO: "같은 재무를 두 번 봅니다. 은행식 점수와, 매출에 섞인 규모와 계절의 영향을 걷어 낸 점수. 그리고 그 차이가 왜 생겼는지를, 문장으로 보여 줍니다." | [합성] 사업 사이트 공정신용 진단 시연 A 캡처 (79.4 A → 84.4 AA) |
| 26 | 3:54 | 16초 | 세진이 메모지에 무언가 적는다 | `SEJIN writing notes on a sticky pad next to the keyboard, thoughtful, warm light` + 공통 | VO: "점수를 바꿔 주는 것이 아니라, 낮게 나온 이유를 설명하는 것. 심사역에게는 추가 심사의 근거가 되고, 사장님에게는 무엇을 보완하면 되는지가 됩니다." | — |

### 4막 — 먼저 봉인하고, 나중에 채점한다 (4:10–5:20)

| # | 시간 | 길이 | 장면 | 영상 생성 프롬프트 (영문) | 소리·대사 | 화면 글자(편집) |
|---|---|---|---|---|---|---|
| 27 | 4:10 | 12초 | 추상: 빛나는 목록이 금속 캡슐에 봉인되고 도장처럼 문양이 찍힌다 | `A glowing list of blank lines sliding into a sleek metal time capsule which seals shut with a glowing geometric stamp, dark studio, dramatic light` + 공통 | VO: "믿어 달라고 하지 않습니다. 매달 경고 목록을 먼저 봉인해 공개하고, 12개월 뒤 실제 결과로 채점합니다." | [합성] 2026-10 경고 · 코스닥 144곳 · 코스피 73곳 · 해시 dac73148… |
| 28 | 4:22 | 12초 | [그림 합성] 경고 상위 10% 막대가 솟는다 | (AI 없음 - fig02 또는 모션그래픽 영상 9번 장면 재사용) | VO: "2020년까지만 배우고, 그 뒤로는 한 번도 고치지 않았습니다. 이미 상장폐지된 회사까지 넣어도, 경고 상위 10% 기업 넷 중 하나가 1년 안에 중대 위험 공시를 냈습니다. 평균의 3.2배. 45개월 동안 단 한 달도 평균 아래로 내려간 적이 없습니다." | fig10 → fig11 (선이 그려지는 장면은 모션그래픽 영상 장면 재사용) |
| 29 | 4:34 | 14초 | [그림 합성] 소형사 오경보 비교 | (AI 없음 - fig04) | VO: "그리고 재무만 보는 모델은 작은 회사에 오경보를 26.4% 냈습니다. 큰 회사의 열 배. 공시 연쇄를 더하자 18.5%로 줄었고, 정확도는 오히려 올랐습니다." | fig04 |
| 30 | 4:48 | 10초 | 회의실. 세진이 위원회 앞에서 슬라이드를 넘긴다(뒷모습) | `SEJIN presenting to a small committee in a glass meeting room, seen from behind, a blank projected slide` + 공통 | 세진: "놓친 위험의 3분의 1을 미리 볼 수 있었습니다. 그리고 작은 회사를 덜 억울하게 봅니다." | [합성] 슬라이드 = fig05 |
| 31 | 4:58 | 22초 | 위원들이 고개를 끄덕인다. 창밖 해가 뜬다 | `Committee members nodding in a meeting room as morning sun breaks through the window, hopeful mood` + 공통 | VO: "상장사에서 확인한 이 방법을, 소상공인에게 구할 수 있는 신호로 옮깁니다. 휴폐업과 대표자 변경, 카드매출 급변, 상권 변화, 업종 연체율." | — |

### 5막 — 다시, 1월 (5:20–6:30)

| # | 시간 | 길이 | 장면 | 영상 생성 프롬프트 (영문) | 소리·대사 | 화면 글자(편집) |
|---|---|---|---|---|---|---|
| 32 | 5:20 | 10초 | 저축은행 상담석. 세진과 하윤이 마주 앉는다(측면) | `Side view of SEJIN and HAYOON sitting across a consultation desk at a small savings bank, a printed report between them, calm atmosphere` + 공통 | 세진: "점수가 낮게 나온 이유가 여기 있네요. 비수기 매출 영향이 크게 잡혔어요. 보완 서류로 다시 보죠." | — |
| 33 ★ | 5:30 | 6초 | 하윤 정면. 안도하는 얼굴 | `Close-up of HAYOON exhaling with relief, a small hopeful smile` + 공통 | 하윤: "처음으로 이유를 들었네요." | — |
| 34 | 5:36 | 10초 | 봄, 헬스장. 회원들이 운동하고 하윤이 자세를 봐 준다 | `The same neighborhood gym in spring, bright and busy, HAYOON coaching a member on a squat, cherry blossoms visible outside` + 공통 | 음악 고조 | — |
| 35 | 5:46 | 14초 | 민재의 작업실. 화이트보드 로드맵 | `MINJAE standing in front of a whiteboard with a hand-drawn timeline of four milestones, morning light, determined` + 공통 | VO: "이미 상장폐지된 회사 497곳을 채워 넣어 다시 검증해도, 경고의 힘은 그대로였습니다. 다음은 11월부터 기관 두 곳과의 무상 파일럿입니다. 경고는 성적표로, 소상공인 리포트는 실제 상환 결과로 검증합니다." | [합성] 생존편향 보정 완료(3.2배 유지) → 11월 파일럿 2곳 → 2027 첫 계약 |
| 36 | 6:00 | 14초 | 민재가 노트북을 닫고 창밖을 본다 | `MINJAE closing a laptop and looking out the window at the city, calm` + 공통 | VO: "우리의 원칙은 네 가지입니다. 배운 기간과 검증한 기간을 나누고, 그 시점의 정보만 쓰고, 같은 잣대로 비교하고, 먼저 봉인한 뒤 채점한다." | 기간 분리 · 시점 고정 · 같은 잣대 · 먼저 봉인 |
| 37 | 6:14 | 8초 | 엔딩 타이틀 | (검은 화면) | VO: "점수가 낮은 이유와, 위험해지는 이유를. 검증된 숫자로." | **점수가 낮은 이유와, 위험해지는 이유를 / 검증된 숫자로** · dintel × 신용캐드 |
| 38 | 6:22 | 8초 | 고지 카드 | (검은 화면) | — | 아래 고지문 |

**고지문 (38번 컷, 그대로 사용)**
> 이 영상의 인물·회사·금융기관은 가상입니다. 소상공인 공정신용 점수는 합성 데이터로 만든 시제품이며 대출 승인이나 금리를 보장하지 않습니다. 상장사 조기경보 수치는 2020년까지 학습, 2022~2025년 표본외 검증 실측값이며, 상장폐지 코스닥 기업 497곳을 보충한 재검증에서도 상위 10% 배수(3.2배)가 유지됐으나, 퇴출 기업의 상장 기간은 공시로 근사했습니다. 투자 권유가 아닙니다.

## 5. 내레이션 전문 (녹음용, 약 4분 10초 분량 + 대사)

1. 1월. 헬스장이 가장 조용한 달입니다.
2. 점수가 낮다는 건 알았습니다. 왜 낮은지는, 아무도 말해 주지 않았습니다.
3. 실제로 헬스장 사장님들을 만나 보니 같은 말이 반복됐습니다. 담보가 남지 않는다. 비수기에 더 불리하다. 시설 투자는 보이지 않는다.
4. 코스닥 상장사가 2015년 이후 낸 공시는 26만 6천 건입니다. 세진의 팀은 주식을 담보로 돈을 빌려준 회사들의 공시를, 매일 사람 눈으로 읽습니다.
5. 돌이켜 보면 신호는 있었습니다. 1년 동안 자금조달 세 번, 그리고 최대주주 변경.
6. 문제는, 그 신호가 26만 건 속에 흩어져 있었다는 것입니다. 제목만 보고 거르면 큰 변동의 3분의 1도 잡지 못합니다.
7. 2026년, 상장폐지 기준이 강화되면서 지난 사업연도 퇴출 사유가 생긴 회사만 코스닥 42곳. 주식을 담보로 한 대출은 하루 평균 62조 원. 어느 회사가 위험한지 미리 아는 일에, 큰돈이 걸려 있습니다.
8. 저는 두 가지를 만들고 있었습니다. 동네 사업자의 신용을 공정하게 설명하는 법, 그리고 공시로 상장사의 위험을 미리 읽는 엔진.
9. 두 질문은 같은 것이었습니다. 작다는 이유로, 위험하게 보이는가?
10. 공시 원문을 모아 조건을 꺼내고, 그 시점에 공개된 정보만으로 위험을 계산합니다. 조기경보 점수, 공시별 과거 반응, 자금조달 연쇄.
11. 매일 아침, 담보 종목 중 위험이 높은 회사가 근거 공시와 함께 올라옵니다.
12. 매수도, 매도도 말하지 않습니다. 확률과, 그 근거만.
13. 같은 재무를 두 번 봅니다. 은행식 점수와, 매출에 섞인 규모와 계절의 영향을 걷어 낸 점수. 그리고 그 차이가 왜 생겼는지를, 문장으로 보여 줍니다.
14. 점수를 바꿔 주는 것이 아니라, 낮게 나온 이유를 설명하는 것. 심사역에게는 추가 심사의 근거가 되고, 사장님에게는 무엇을 보완하면 되는지가 됩니다.
15. 믿어 달라고 하지 않습니다. 매달 경고 목록을 먼저 봉인해 공개하고, 12개월 뒤 실제 결과로 채점합니다.
16. 2020년까지만 배우고, 그 뒤로는 한 번도 고치지 않았습니다. 이미 상장폐지된 회사까지 넣어도, 경고 상위 10% 기업 넷 중 하나가 1년 안에 중대 위험 공시를 냈습니다. 평균의 3.2배. 45개월 동안 단 한 달도 평균 아래로 내려간 적이 없습니다.
17. 그리고 재무만 보는 모델은 작은 회사에 오경보를 26.4% 냈습니다. 큰 회사의 열 배. 공시 연쇄를 더하자 18.5%로 줄었고, 정확도는 오히려 올랐습니다.
18. 상장사에서 확인한 이 방법을, 소상공인에게 구할 수 있는 신호로 옮깁니다. 휴폐업과 대표자 변경, 카드매출 급변, 상권 변화, 업종 연체율.
19. 이미 상장폐지된 회사 497곳을 채워 넣어 다시 검증해도, 경고의 힘은 그대로였습니다. 다음은 11월부터 기관 두 곳과의 무상 파일럿입니다. 경고는 성적표로, 소상공인 리포트는 실제 상환 결과로 검증합니다.
20. 우리의 원칙은 네 가지입니다. 배운 기간과 검증한 기간을 나누고, 그 시점의 정보만 쓰고, 같은 잣대로 비교하고, 먼저 봉인한 뒤 채점한다.
21. 점수가 낮은 이유와, 위험해지는 이유를. 검증된 숫자로.

## 6. 수치 출처 대조표 (편집 전 확인)

| 영상 속 문장 | 값 | 출처 |
|---|---|---|
| 공시 26만 6천 건 | 코스닥, 2015년 이후 | DINTEL_BUSINESS_PLAN.md 1장 |
| 제목만으로 큰 변동의 3분의 1도 못 잡음 | 9~13%(급락, 코스피 8.5%·코스닥 12.9%) | dintel/desk_eval.py, DESK_EVAL.txt |
| 상폐 사유 코스닥 42곳, 담보대출 62조 | 2025사업연도, 2026 2분기 | 사업계획서 출처(헤럴드경제) |
| 자금조달 세 번 + 최대주주 변경 | 3건 이상이면 24.6%, 변경 동반 시 34.1% | DINTEL_DIFFERENTIATION.md |
| 상위 10% 19.6%, 3.2배, 32% | 코스닥 검증 2022-01~2025-09 | data/dintel/risk_model_kosdaq.json |
| 넷 중 하나(27%), 45개월 모두 평균 위 | 퇴출 포함, 가상 성적표 | SURVIVORSHIP_SUMMARY.txt, pseudo_scoreboard_kosdaq.csv |
| 소형사 오경보 26.4% → 18.5%, 대형 2.5% | 코스닥 검증 2024-01~2025-09 | data/dintel/FAIR_WARNING_SUMMARY.txt |
| 79.4 A → 84.4 AA | 시연 A (합성 데이터 MVP) | caed/service.py, docs/site_api_samples/biz_caed_demoAB.json |
| 경고 144곳 / 73곳, 해시 | 2026-10 첫 발행 | scoreboard/ledger.csv |
| 퇴출 497곳 보충해도 3.2배 | 상위 10% 실제 위험률 27.0% | data/dintel/SURVIVORSHIP_SUMMARY.txt |

## 7. 일정 (10/19~10/26)

| 날짜 | 할 일 |
|---|---|
| 10/19 | 인물 기준 이미지 3종 확정, 1~10번 컷 생성 |
| 10/20 | 11~26번 컷 생성, 사이트 화면 캡처(사업 사이트 3화면) |
| 10/21 | 27~38번 컷, 그림 합성 컷 준비 |
| 10/22 | 내레이션 녹음, 대사 녹음 |
| 10/23 | 1차 편집(컷 길이 맞추기, 화면 합성) |
| 10/24 | 음악·자막·고지 카드, 수치 대조(6장) |
| 10/25 | 최종 렌더, PDF 보고서에 스틸 컷 반영 |
| 10/26 | 제출 |

## 8. 음악 프롬프트 (생성형 음악 도구용)

`Minimal cinematic piano and soft strings, 72 BPM, starts sparse and lonely, builds gently with warm pads from 2:40, hopeful resolution at 5:20, ends on a single sustained chord, no vocals, about 6 minutes 30 seconds`

## 9. 추가 장면(선택, 10-20) — 브랜드 건강도
- 위치: 4막 끝(세진의 위원회 장면 다음), 약 15초. 1분 이상 조건이라 전체를 줄일 때도 이 장면은 남기길 권장(독창성의 핵심).
- 화면: 은행 회의실, 세진이 노트북 화면을 돌려 보인다(화면 내용은 합성: 그림 14 '브랜드가 쇠퇴기면 가맹점이 닫는다').
  프롬프트: `SEJIN turning a laptop toward a loan officer in a bank meeting room, chart on screen hidden by angle, warm daylight, calm professional mood` + 공통
- 대사(세진): "이 가맹점이 위험한지 보려면, 먼저 그 브랜드가 커지고 있는지 줄고 있는지를 보세요. 줄어드는 브랜드의 가맹점은 다음 해에 일곱 배 더 닫았습니다."
- 자막: 서울 인허가 실측 · 카페 쇠퇴 브랜드 17.5% vs 성장 브랜드 2.5% · 음식점에서 재현 · 브랜드 이름은 판정 전 비공개
- 주의: 실존 브랜드 로고·상호를 화면에 넣지 않는다.

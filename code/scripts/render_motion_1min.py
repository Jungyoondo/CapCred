"""제출용 1분 모션그래픽 (2026-10-25, 10-26 묶음 그림으로 교체) - 정보공개서 에이전트로 시작해 같은 엔진이 금융·공공 의무 업무로 넓어진다. 무엇을 어떻게 시험했나.

python -X utf8 scripts/render_motion_1min.py            # -> deliverables/final/motion_graphic.mp4 (+ .srt), deliverables/VIDEO_MOTION_1MIN.md
python -X utf8 scripts/render_motion_1min.py --stills   # 장면 정지화면만 -> deliverables/video/m1/stills/
사용자 방향(10-25): 모션그래픽 = 지표·활용 방법·기간·자료의 양과 종류·테스트. 그림 요소와 TTS는 render_motion_video.py를 재사용한다.
숫자는 결과 파일에서 읽는다(손으로 적은 값은 출처 주석). 6분 원본 대본(VIDEO_MOTION_SCRIPT.md)과 tts 파일은 건드리지 않는다.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_motion_video as R  # noqa: E402
from render_motion_video import T, Num, Bars, Box, Arrow  # noqa: E402

ROOT = R.ROOT
R.OUT = os.path.join(ROOT, "deliverables", "video", "m1")      # tts·narration.wav·srt를 6분 원본과 분리
FINAL = os.path.join(ROOT, "deliverables", "final")
DOC = os.path.join(ROOT, "deliverables", "VIDEO_MOTION_1MIN.md")

# 사전 등록 세부 가설 집계(scoreboard/HYPOTHESES.md + data/caed/*.txt 판정 줄, 10-25 기준) - 검정 10건
#   I1~3 기각3 | 헬스장 H1 성립, H2·H3 기각 | 상권 L1 기각, L2 성립 | 유령 G1·G3 성립, G2 기각 | 가맹 F1~3 성립 | 브랜드 B1·B1b 성립
#   공정위 X1 성립, X2 판정불가, X3 기각 | 신규 가맹 N1~3 성립 | 코호트 P1~3 보류 | 양도 Z1 기각, Z2 업종별 엇갈림(보류로 셈)
#   10-25 밤~10-26 추가: AB(v1·v2를 1건) AB1 기각·AB3 성립·AB2 기각 | AC1~3 성립 | AD1·AD2 기각
TALLY = {"tests": 13, "hyp": 35, "ok": 17, "no": 13, "hold": 5}
NAME = "CapCred"   # 10-26 확정(Capacity + Credibility) - 이름이 정해지면 여기만 바꾸고 다시 렌더
R.FOOTER = f"{NAME} · 해야 하는 일을, 공공 기록으로 대신"


def _ffmpeg():
    """PATH의 ffmpeg, 없으면 pip imageio-ffmpeg에 든 실행 파일(10-25 이 PC는 PATH에 없음)."""
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _j(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as fh:
        return json.load(fh)


def scenes():
    """10-26 묶음 그림: 정보공개서 에이전트로 시작해 같은 엔진이 금융·공공 의무 업무로 넓어진다."""
    ind = _j("data", "caed", "industry_survival.json")["industries"]
    n_firms = sum(r["n_firms"] for r in ind.values())
    ac = _j("data", "caed", "ftc_frcs_prefill.json")                      # H-2026-10-AC
    rp = _j("deliverables", "business", "agent_replay_public.json")["stats"]   # 지난 시즌(회계년도 2025) 재현
    gain = 1 - ac["mae_prefill"] / ac["mae_copy"]
    S = []

    def sc(sec, narr, els):
        S.append({"sec": sec, "narr": narr, "tts": None, "els": els, "key": None})

    sc("", f"해야 하는 일을, 공공 기록으로 대신합니다. {NAME}.",
       [T(NAME, 960, 380, 130, "ink", True, 0.0, "mm"),
        T("해야 하는 일을, 공공 기록으로 대신", 960, 570, 58, "acc", True, 0.2, "mm"),
        T("요청 한 줄 → 공공데이터·재무제표 → 결과물 → 사람은 서명만", 960, 700, 34, "muted", False, 0.45, "mm")])

    sc("01  문제", "가맹본부는 해마다 4월 말까지 정보공개서를 고쳐 냅니다. 1만 1천 개 브랜드, 한 건에 30만 원을 내고 사람이 손으로 맞춥니다.",
       [T("누군가 해야 하는 일", 120, 120, 60, "ink", True),
        T("정보공개서 정기변경 · 가맹사업법 · 늦거나 틀리면 과태료 최대 1천만 원", 120, 210, 30, "muted"),
        Num(11000, lambda v: f"{v:,.0f}개", 400, 470, 110, "acc", 0.05, label="해마다 고쳐 내는 등록 브랜드"),
        Num(4.30, lambda v: "4월 30일", 960, 470, 110, "warn", 0.2, label="마감 (사업연도 말 + 120일)"),
        Num(30, lambda v: f"{v:.0f}만 원", 1520, 470, 110, "gold", 0.35, label="가맹거래사 변경 대행 1건 · 5~10일"),
        T("자료는 공공에 다 있다 — 흩어져 있어 사람이 모은다", 960, 820, 40, "ink", True, 0.6, "mm")])

    sc("02  자료", f"공공 기록으로 먼저 채웁니다. 인허가 {n_firms // 10000}만 곳, 공정위 가맹정보 139만 행, 상가정보와 전자공시까지.",
       [T("얼마나 많은, 어떤 자료로", 120, 120, 60, "ink", True),
        Num(n_firms, lambda v: f"{v:,.0f}곳", 560, 330, 100, "acc", 0.05, label="서울 인허가 개업·폐업 기록"),
        Num(1393185, lambda v: f"{v:,.0f}행", 1360, 330, 100, "vio", 0.15, label="공정위 지역별 가맹점 수"),
        Box(120, 560, 540, 170, "① 인허가 대장", "개업·폐업일 · 상호 · 좌표 · 2014~2026", "acc", 0.3, tsize=32, bsize=26),
        Box(690, 560, 540, 170, "② 공정위 가맹정보", "브랜드 목록 9.4만 행 · 지역별 매장 수", "acc", 0.36, tsize=32, bsize=26),
        Box(1260, 560, 540, 170, "③ 상가정보", "55만 곳 · 실제 영업 목록", "ok", 0.42, tsize=32, bsize=26),
        Box(120, 760, 540, 170, "④ 전자공시 DART", "재무제표 · 감사보고서", "vio", 0.48, tsize=32, bsize=26),
        Box(690, 760, 540, 170, "⑤ 상권 추정매출", "서울시 상권분석서비스", "slate", 0.54, tsize=32, bsize=26),
        Box(1260, 760, 540, 170, "⑥ 법령·공개 가격", "가맹사업법 · 대행 가격표", "slate", 0.6, tsize=32, bsize=26)])

    sc("03  판단 규칙", "같은 자리 재개업을 가려 올해 매장 수를 예상하고, 크게 바뀔 브랜드에 경보를 냅니다.",
       [T("에이전트가 쓰는 규칙", 120, 120, 60, "ink", True),
        T("모두 결과 전에 등록하고 시험한 규칙만", 120, 210, 30, "muted"),
        Box(120, 330, 400, 300, "열고 닫은 날", "인허가 대장\n매달 갱신", "slate", 0.08),
        Arrow(530, 480, 600, 480, 0.2, "gold"),
        Box(610, 330, 400, 300, "같은 자리 재개업", "10m · 180일 안\n= 명의변경 추정", "acc", 0.25),
        Arrow(1020, 480, 1090, 480, 0.37, "gold"),
        Box(1100, 330, 330, 300, "예상값", "작년 신고 x\n(1 + 실측 증감률)", "gold", 0.42),
        Arrow(1440, 480, 1500, 480, 0.52, "gold"),
        Box(1510, 330, 290, 300, "경보", "3곳 또는\n10% 이상", "warn", 0.57),
        T("인허가 실측은 신고의 약 2/3만 잡는다 → 숫자가 아니라 증감률만 쓴다", 960, 760, 34, "muted", False, 0.7, "mm")])

    sc("04  시험", f"지난 7개 시즌, 879개 브랜드에 미리 돌려 보니 오차는 {gain * 100:.0f}퍼센트 줄고, 경보의 {ac['alert_precision'] * 100:.0f}퍼센트가 맞았습니다.",
       [T("미리 적고, 지난 시즌에 돌려 봤다", 120, 120, 60, "ink", True),
        T(f"외식 {ac['n_brands']}개 브랜드 · 회계년도 2019~2025 · 브랜드-연 {ac['n_brand_years']:,} (H-2026-10-AC)", 120, 210, 30, "muted"),
        Bars((160, 340, 900, 860), [ac["mae_copy"], ac["mae_prefill"]], ["작년 숫자 복사", "에이전트 예상"], ["slate", "acc"],
             at=0.1, stagger=0.15, vmax=7, fmt="{:.1f}곳", lsize=34, vsize=48),
        T(f"오차 -{gain * 100:.1f}%", 530, 300, 48, "acc", True, 0.4, "mm"),
        Num(ac["alert_precision"] * 100, lambda v: f"{v:.0f}%", 1400, 440, 150, "gold", 0.45, label="경보가 실제 신고와 같은 방향"),
        T(f"지난 시즌 재현: {rp['n_brands']}개 브랜드 · 매장 변동 {rp['n_events']:,}건 · 경보 적중 {rp['alert_hit'] * 100:.0f}%",
          1400, 760, 30, "ink", False, 0.65, "mm")])

    sc("05  기각도 공개", f"틀린 것도 공개합니다. 1년 늦다는 주장은 기각됐고, 가설 {TALLY['hyp']}개 중 {TALLY['ok']}개가 성립했습니다.",
       [T("몇 번 시험했고, 무엇이 틀렸나", 120, 120, 60, "ink", True),
        T(f"사전 등록 검정 {TALLY['tests']}건 · 세부 가설 {TALLY['hyp']}개 (scoreboard/HYPOTHESES.md)", 120, 210, 30, "muted"),
        Bars((200, 360, 1100, 860), [TALLY["ok"], TALLY["no"], TALLY["hold"]], ["성립", "기각", "보류"], ["ok", "warn", "slate"],
             at=0.15, stagger=0.15, vmax=20, fmt="{:.0f}개", lsize=36, vsize=50),
        T("기각 → 제품에서 뺀다", 1240, 400, 44, "ink", True, 0.5),
        T("'1년 늦다' 6.4% < 10%\n'장부 불일치 → 폐업' 1.5배 < 2배", 1240, 480, 30, "muted", False, 0.55),
        T("개별 가게 신용점수도 약했다", 1240, 680, 40, "warn", True, 0.7),
        T("→ 점수 대신, 일을 대신한다", 1240, 750, 40, "gold", True, 0.8)])

    sc("06  넓히기", "같은 엔진이 은행의 대출 사후점검, 구청의 대장 정비까지 대신합니다.",
       [T("같은 엔진, 다른 의무 업무", 120, 120, 60, "ink", True),
        Box(760, 440, 400, 200, "점포 기록 엔진", "공공데이터 + 재무제표", "gold", 0.05, tsize=36, bsize=28),
        Box(120, 260, 520, 190, "정보공개서 정기변경", "가맹거래사·본부 · 30초", "acc", 0.2, tsize=30, bsize=26),
        Box(1280, 260, 520, 190, "인근 가맹점 10곳 문서", "가맹사업법 제7조", "acc", 0.3, tsize=30, bsize=26),
        Box(120, 640, 520, 190, "대출 사후점검 확인서", "은행·상호금융 · 2026-07 확대", "vio", 0.4, tsize=30, bsize=26),
        Box(1280, 640, 520, 190, "인허가 대장 정비", "구청 · 확인 우선 목록", "ok", 0.5, tsize=30, bsize=26),
        Arrow(760, 470, 650, 400, 0.25, "gold"), Arrow(1160, 470, 1270, 400, 0.35, "gold"),
        Arrow(760, 610, 650, 690, 0.45, "gold"), Arrow(1160, 610, 1270, 690, 0.55, "gold"),
        T("요청 한 줄 → 결과물 + 작업 기록 → 사람이 확인·서명", 960, 940, 34, "muted", False, 0.7, "mm")])

    sc("", f"서류는 공공 기록이 먼저 채우고, 사람은 판단만. {NAME}.",
       [T("서류는 공공 기록이 먼저 채우고,", 960, 420, 66, "ink", True, 0.0, "mm"),
        T("사람은 판단만", 960, 530, 80, "acc", True, 0.25, "mm"),
        T(NAME, 960, 720, 90, "gold", True, 0.5, "mm"),
        T("해야 하는 일을, 공공 기록으로 대신", 960, 830, 34, "muted", False, 0.65, "mm")])
    return S


def doc(S, lens):
    t0, rows = 0.0, ["# 1분 모션그래픽 대본·콘티 (자동 생성 - scripts/render_motion_1min.py와 같은 장면 정의)", "",
                     "- 방향(사용자 10-25·26): 지표·방법·기간·자료의 양과 종류·테스트, 그리고 정보공개서에서 금융·공공 업무로 넓어지는 묶음 그림.",
                     "- 영상: `deliverables/final/motion_graphic.mp4` (1920x1080, 24fps, 내레이션 = Windows 한국어 음성 Heami 초안, 자막 .srt)",
                     "- 내레이션을 본인 목소리로 바꾸려면 장면 문장을 그대로 읽어 녹음하고 편집에서 교체하면 된다.",
                     f"- 가설 집계 근거: 스크립트 상단 TALLY 주석(검정 {TALLY['tests']}건, 세부 가설 {TALLY['hyp']}개).", "",
                     "| # | 시간 | 구간 | 화면 | 내레이션 |", "|---|---|---|---|---|"]
    for i, (sc, L) in enumerate(zip(S, lens or [None] * len(S))):
        vis = " / ".join(getattr(e, "s", None) or getattr(e, "title", "") or type(e).__name__ for e in sc["els"]
                         if not isinstance(e, Arrow))[:300].replace("\n", " ")
        when = f"{int(t0 // 60)}:{int(t0 % 60):02d}" if L else "-"
        rows.append(f"| {i + 1} | {when} | {sc['sec'] or '타이틀'} | {vis} | {sc['narr']} |")
        t0 += L or 0
    if lens:
        rows += ["", f"총 길이: {int(t0 // 60)}분 {t0 % 60:.0f}초"]
    with open(DOC, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    print("script ->", DOC)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--rate", type=int, default=3, help="Heami 말 빠르기(-10~10) - 1분에 맞추려고 원본보다 빠르게")
    a = ap.parse_args()
    os.makedirs(R.OUT, exist_ok=True)
    S = scenes()
    bg = R.background()
    if a.stills:
        sd = os.path.join(R.OUT, "stills")
        os.makedirs(sd, exist_ok=True)
        for i, sc in enumerate(S):
            R.frame(bg, sc, 20.0 * 0.97, 20.0, (i + 1) / len(S)).convert("RGB").save(os.path.join(sd, f"s{i:02d}.png"))
        doc(S, None)
        print("stills ->", sd)
        return
    durs = R.synth(S, a.rate)
    pads = [(0.4, 0.6)] * len(S)
    pads[0], pads[-1] = (0.6, 0.6), (0.4, 1.6)
    lens = R.build_audio(S, durs, pads)
    R.srt(S, lens, pads, durs)
    doc(S, lens)
    total = sum(lens)
    print(f"scenes {len(S)}, total {total:.1f} s -> rendering", flush=True)
    os.makedirs(FINAL, exist_ok=True)
    mp4 = os.path.join(FINAL, "motion_graphic.mp4")
    ff = subprocess.Popen([_ffmpeg(),"-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{R.W}x{R.H}",
                           "-r", str(R.FPS), "-i", "-", "-i", os.path.join(R.OUT, "narration.wav"), "-c:v", "libx264",
                           "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                           "-shortest", mp4], stdin=subprocess.PIPE)
    done = 0.0
    for sc, L in zip(S, lens):
        for f in range(int(round(L * R.FPS))):
            t = f / R.FPS
            ff.stdin.write(R.frame(bg, sc, t, L, (done + t) / total).convert("RGB").tobytes())
        done += L
    ff.stdin.close()
    ff.wait()
    os.replace(os.path.join(R.OUT, "motion_draft.srt"), os.path.join(FINAL, "motion_graphic.srt"))
    print("video ->", mp4)


if __name__ == "__main__":
    main()

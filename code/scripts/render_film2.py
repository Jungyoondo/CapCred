"""1분 AI 영화 「A씨의 4월」 (2026-10-26, CapCred) - 사람과 캐릭터가 나오는 그림 애니메이션.

python -X utf8 scripts/render_film2.py            # -> deliverables/final/ai_film.mp4 (+ .srt)
python -X utf8 scripts/render_film2.py --stills   # 같은 렌더 + 컷마다 정지화면 film2/still_N.png
사용자 방향(10-26): 회사원 A씨가 걱정하고, CapCred 캐릭터가 나타나 문제를 풀어 준다. 보고서·모션그래픽과 겹치는 장면이 없어야 한다
  (그 둘의 화면·도표를 쓰지 않는다). 마지막 서울 야경(인허가 89만 곳 점 지도)은 그대로 쓴다.
인물·캐릭터는 도형으로 그린다(2배로 그려 줄여 매끄럽게). 인물·회사·브랜드는 가상이다.
"""
import math
import os
import random
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_motion_video as R  # noqa: E402

ROOT = R.ROOT
OUT = os.path.join(ROOT, "deliverables", "video", "film2")
FINAL = os.path.join(ROOT, "deliverables", "final")
MAP = os.path.join(ROOT, "deliverables", "video", "film1", "composite_A_map.png")   # 10-25 렌더(scripts/render_film1_assets.py map_png)
NAME = "CapCred"   # render_motion_1min.NAME과 같이 바꾼다
SS = 2             # 인물·캐릭터 초과 표본 배율

SKIN, HAIR, SHIRT, TIE = (243, 205, 172), (38, 30, 28), (196, 214, 238), (30, 58, 110)
BOT, BOTD, PAPER, DARK = (56, 189, 248), (12, 22, 44), (246, 247, 250), (24, 32, 52)


def ease(x):
    return R.ease(max(0.0, min(1.0, x)))


def lerp(a, b, p):
    return a + (b - a) * p


def sprite(w, h, fn):
    im = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    fn(ImageDraw.Draw(im), SS)
    return im.resize((w, h), Image.LANCZOS)


def put(img, sp, cx, cy, alpha=1.0, scale=1.0):
    if alpha <= 0 or scale <= 0.02:
        return
    if scale != 1.0:
        sp = sp.resize((max(1, int(sp.width * scale)), max(1, int(sp.height * scale))), Image.LANCZOS)
    if alpha < 1:
        sp = sp.copy()
        sp.putalpha(sp.getchannel("A").point(lambda v: int(v * alpha)))
    img.alpha_composite(sp, (int(cx - sp.width / 2), int(cy - sp.height / 2)))


# ------------------------------------------------------------------ 인물·캐릭터
def person(mood="neutral", blink=False, arm=0.0):
    """회사원 A씨 상반신(360x470). mood: worry / neutral / happy / surprise."""
    def fn(d, s):
        k = lambda *v: [x * s for x in v]  # noqa: E731
        d.rounded_rectangle(k(50, 270, 310, 470), radius=70 * s, fill=SHIRT)                       # 몸
        d.polygon(k(150, 270, 180, 320, 210, 270), fill=(250, 250, 252))                            # 깃
        d.polygon(k(172, 300, 188, 300, 196, 400, 180, 420, 164, 400), fill=TIE)                    # 넥타이
        d.rectangle(k(160, 225, 200, 285), fill=(228, 188, 156))                                    # 목
        d.ellipse(k(98, 52, 262, 160), fill=HAIR)                                                   # 뒷머리
        d.ellipse(k(110, 70, 250, 245), fill=SKIN)                                                  # 얼굴
        d.ellipse(k(98, 140, 122, 182), fill=SKIN)
        d.ellipse(k(238, 140, 262, 182), fill=SKIN)                                                 # 귀
        d.chord(k(104, 52, 256, 150), 180, 360, fill=HAIR)                                          # 앞머리
        d.polygon(k(118, 102, 176, 96, 140, 128), fill=HAIR)
        ey = 155
        for ex in (152, 208):                                                                       # 눈
            if blink:
                d.line(k(ex - 9, ey, ex + 9, ey), fill=DARK, width=3 * s)
            elif mood == "happy":
                d.arc(k(ex - 10, ey - 6, ex + 10, ey + 10), 200, 340, fill=DARK, width=4 * s)
            else:
                r = 9 if mood == "surprise" else 7
                d.ellipse(k(ex - r, ey - r - 1, ex + r, ey + r + 1), fill=DARK)
                d.ellipse(k(ex - 2, ey - 5, ex + 2, ey - 1), fill=(255, 255, 255))
        brows = {"worry": ((138, 134, 164, 126), (196, 126, 222, 134)), "happy": ((138, 128, 164, 124), (196, 124, 222, 128)),
                 "surprise": ((138, 122, 164, 116), (196, 116, 222, 122)), "neutral": ((138, 130, 164, 128), (196, 128, 222, 130))}[mood]
        for b in brows:
            d.line(k(*b), fill=HAIR, width=5 * s)
        if mood == "worry":                                                                         # 입
            d.arc(k(162, 200, 198, 222), 200, 340, fill=(150, 70, 70), width=4 * s)
            d.ellipse(k(232, 112, 244, 132), fill=(140, 200, 255))                                  # 땀
            d.polygon(k(238, 100, 232, 116, 244, 116), fill=(140, 200, 255))
        elif mood == "happy":
            d.chord(k(160, 188, 200, 220), 0, 180, fill=(170, 70, 80))
        elif mood == "surprise":
            d.ellipse(k(172, 196, 188, 216), fill=(150, 70, 70))
        else:
            d.line(k(166, 206, 194, 206), fill=(150, 70, 70), width=4 * s)
        d.ellipse(k(128, 182, 146, 194), fill=(246, 170, 160, 120))
        d.ellipse(k(214, 182, 232, 194), fill=(246, 170, 160, 120))                                 # 볼
        a = 8 * math.sin(arm * math.pi * 2)                                                         # 팔(타자)
        d.rounded_rectangle(k(40, 330 + a, 120, 470), radius=36 * s, fill=SHIRT)
        d.rounded_rectangle(k(240, 330 - a, 320, 470), radius=36 * s, fill=SHIRT)
    return sprite(360, 470, fn)


def bot(eyes="open", wave=0.0):
    """CapCred 캐릭터(280x330): 둥근 몸, 얼굴 화면, 안테나, 작은 팔, CC 배지."""
    def fn(d, s):
        k = lambda *v: [x * s for x in v]  # noqa: E731
        d.line(k(140, 70, 140, 30), fill=BOT, width=6 * s)
        d.ellipse(k(126, 14, 154, 42), fill=(251, 191, 36))
        d.ellipse(k(18, 150, 58, 220), fill=BOT)                                                    # 왼팔
        wy = -40 * wave
        d.ellipse(k(222, 150 + wy, 262, 220 + wy), fill=BOT)                                        # 오른팔(손 흔들기)
        d.rounded_rectangle(k(40, 66, 240, 270), radius=70 * s, fill=BOT)
        d.rounded_rectangle(k(66, 100, 214, 200), radius=34 * s, fill=BOTD)
        for ex in (112, 168):
            if eyes == "blink":
                d.line(k(ex - 12, 150, ex + 12, 150), fill=(160, 240, 255), width=5 * s)
            elif eyes == "happy":
                d.arc(k(ex - 14, 136, ex + 14, 164), 200, 340, fill=(160, 240, 255), width=6 * s)
            else:
                d.rounded_rectangle(k(ex - 11, 128, ex + 11, 172), radius=10 * s, fill=(160, 240, 255))
        d.rounded_rectangle(k(104, 216, 176, 248), radius=12 * s, fill=(251, 191, 36))
        d.text((140 * s, 232 * s), "CC", font=R.font(24 * s, True), fill=BOTD, anchor="mm")
        d.ellipse(k(80, 296, 200, 318), fill=(0, 0, 0, 70))                                         # 그림자
    return sprite(280, 330, fn)


P_CACHE, B_CACHE = {}, {}


def P(mood, blink=False, arm=0.0):
    key = (mood, blink, round(arm % 1, 2))
    if key not in P_CACHE:
        P_CACHE[key] = person(mood, blink, arm)
    return P_CACHE[key]


def B(eyes="open", wave=0.0):
    key = (eyes, round(wave, 1))
    if key not in B_CACHE:
        B_CACHE[key] = bot(eyes, round(wave, 1))
    return B_CACHE[key]


def blinking(t, period=3.1, off=0.0):
    return ((t + off) % period) < 0.12


# ------------------------------------------------------------------ 배경
def office_bg():
    img = R.background()
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 1180, 70, 1860, 600                                                            # 창문 + 도시 실루엣
    d.rectangle((x0, y0, x1, y1), fill=(14, 22, 48))
    rnd = random.Random(7)
    x = x0
    while x < x1:
        w, h = rnd.randint(40, 110), rnd.randint(120, 420)
        d.rectangle((x, y1 - h, min(x + w, x1), y1), fill=(24, 34, 66))
        for wy in range(y1 - h + 12, y1 - 10, 22):
            for wx in range(x + 8, min(x + w, x1) - 8, 16):
                if rnd.random() < 0.35:
                    d.rectangle((wx, wy, wx + 6, wy + 9), fill=(251, 210, 120))
        x += w + rnd.randint(4, 14)
    d.rectangle((x0, y0, x1, y1), outline=(70, 86, 120), width=10)
    d.line(((x0 + x1) // 2, y0, (x0 + x1) // 2, y1), fill=(70, 86, 120), width=8)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))                                                # 스탠드 불빛
    gd = ImageDraw.Draw(glow)
    for r in range(320, 0, -16):
        gd.ellipse((380 - r, 360 - r, 380 + r, 360 + r), fill=(251, 210, 120, int(10 * (1 - r / 320)) + 2))
    img.alpha_composite(glow)
    return img


def desk(img):
    d = ImageDraw.Draw(img)
    d.rectangle((0, 760, 1920, 1080), fill=(46, 40, 52))
    d.rectangle((0, 748, 1920, 772), fill=(70, 62, 76))
    d.rectangle((260, 700, 360, 752), fill=(90, 80, 70))                                            # 머그컵
    d.arc((340, 708, 380, 744), 270, 90, fill=(90, 80, 70), width=8)


def laptop(img, glow=0.0):
    d = ImageDraw.Draw(img)
    d.polygon(((1020, 748), (1340, 748), (1300, 726), (1060, 726)), fill=(120, 130, 150))           # 키보드 면
    d.polygon(((1070, 726), (1290, 726), (1330, 520), (1110, 520)), fill=(90, 100, 124))            # 화면 뒤판
    if glow > 0:
        g = Image.new("RGBA", img.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(g)
        for r in range(260, 0, -20):
            gd.ellipse((1200 - r, 620 - r, 1200 + r, 620 + r), fill=(56, 189, 248, int(24 * glow * (1 - r / 260))))
        img.alpha_composite(g)


def street_bg():
    img = R.background()
    d = ImageDraw.Draw(img)
    d.rectangle((0, 820, 1920, 1080), fill=(30, 36, 54))
    d.rectangle((0, 812, 1920, 826), fill=(60, 70, 96))
    return img


def building(img, x, kind, label):
    d = ImageDraw.Draw(img)
    if kind == "bank":
        d.polygon(((x - 170, 470), (x, 380), (x + 170, 470)), fill=(70, 86, 130))
        d.rectangle((x - 160, 470, x + 160, 500), fill=(84, 100, 146))
        for c in range(5):
            cx = x - 130 + c * 65
            d.rectangle((cx - 14, 500, cx + 14, 790), fill=(150, 165, 200))
        d.rectangle((x - 170, 790, x + 170, 815), fill=(84, 100, 146))
    elif kind == "office":
        d.rectangle((x - 170, 420, x + 170, 815), fill=(64, 80, 120))
        for r in range(6):
            for c in range(4):
                d.rectangle((x - 140 + c * 75, 450 + r * 58, x - 100 + c * 75, 480 + r * 58), fill=(251, 210, 120) if (r + c) % 3 else (40, 52, 84))
        d.line((x + 120, 420, x + 120, 330), fill=(180, 190, 210), width=6)
        d.polygon(((x + 123, 332), (x + 190, 350), (x + 123, 368)), fill=(248, 113, 113))
    else:
        d.rectangle((x - 160, 520, x + 160, 815), fill=(80, 70, 90))
        for i in range(8):
            d.polygon(((x - 170 + i * 42, 520), (x - 128 + i * 42, 520), (x - 128 + i * 42, 580), (x - 149 + i * 42, 600), (x - 170 + i * 42, 580)),
                      fill=(248, 113, 113) if i % 2 else (246, 247, 250))
        d.rectangle((x - 120, 640, x + 120, 815), fill=(40, 52, 84))
        d.rectangle((x - 110, 650, x + 110, 760), fill=(251, 210, 120))
    R.text(img, (x, 870), label, 34, "ink", True, 1.0, "mm")


# ------------------------------------------------------------------ 말풍선·소품
def _fade(lay, a):
    if a < 1:
        lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
    return lay


def bubble(img, s, x, y, a, size=34, tail=(0, 1), think=False, ink=DARK, fill=PAPER):
    if a <= 0:
        return
    lines = s.split("\n")
    fw = max(int(R.font(size, True).getlength(ln)) for ln in lines) + 60
    fh = int(len(lines) * size * 1.45) + 36
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    box = (x - fw // 2, y - fh // 2, x + fw // 2, y + fh // 2)
    d.rounded_rectangle(box, radius=26, fill=fill + (235,))
    tx, ty = x + tail[0] * fw // 3, box[3] if tail[1] > 0 else box[1]
    if think:
        for i, r in enumerate((14, 9, 6)):
            cx, cy = tx + tail[0] * 22 * (i + 1), ty + tail[1] * (22 + 26 * i)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill + (235,))
    else:
        d.polygon(((tx - 18, ty), (tx + 18, ty), (tx + tail[0] * 30, ty + tail[1] * 34)), fill=fill + (235,))
    for i, ln in enumerate(lines):
        d.text((x, box[1] + 18 + i * size * 1.45 + size * 0.7), ln, font=R.font(size, True), fill=ink + (255,), anchor="mm")
    img.alpha_composite(_fade(lay, a))


def phone(img, x, y, a, msg):
    if a <= 0:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((x - 180, y - 260, x + 180, y + 260), radius=34, fill=(20, 24, 36, 255))
    d.rounded_rectangle((x - 164, y - 236, x + 164, y + 236), radius=24, fill=(236, 240, 246, 255))
    d.text((x - 140, y - 200), "팀장님", font=R.font(26, True), fill=DARK + (255,))
    d.rounded_rectangle((x - 146, y - 150, x + 146, y + 10), radius=20, fill=(220, 228, 240, 255))
    for i, ln in enumerate(msg.split("\n")):
        d.text((x - 130, y - 132 + i * 40), ln, font=R.font(26), fill=DARK + (255,))
    img.alpha_composite(_fade(lay, a))


def calendar(img, x, y, a, s=1.0):
    if a <= 0:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    w, h = int(200 * s), int(210 * s)
    d.rounded_rectangle((x - w // 2, y - h // 2, x + w // 2, y + h // 2), radius=18, fill=(246, 247, 250, 255))
    d.rounded_rectangle((x - w // 2, y - h // 2, x + w // 2, y - h // 2 + int(56 * s)), radius=18, fill=(248, 113, 113, 255))
    d.text((x, y - h // 2 + int(28 * s)), "4월", font=R.font(int(30 * s), True), fill=(255, 255, 255, 255), anchor="mm")
    d.text((x, y + int(30 * s)), "30", font=R.font(int(96 * s), True), fill=DARK + (255,), anchor="mm")
    img.alpha_composite(_fade(lay, a))


def paper(img, x, y, a, rows_hi=0.0, sign=0.0, title="정보공개서 정기변경 초안"):
    if a <= 0:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    w, h = 380, 500
    x0, y0 = int(x - w // 2), int(y - h // 2)
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=14, fill=(250, 250, 252, 255))
    d.text((x0 + 24, y0 + 22), title, font=R.font(24, True), fill=DARK + (255,))
    for i in range(9):
        yy = y0 + 80 + i * 38
        if rows_hi > 0 and i in (3, 6):
            d.rectangle((x0 + 16, yy - 8, x0 + w - 16, yy + 22), fill=(251, 191, 36, int(150 * min(1, rows_hi))))
            d.text((x0 + 24, yy - 6), "▲" if i == 3 else "▼", font=R.font(22, True), fill=(200, 60, 60, 255))
        d.rectangle((x0 + 56, yy + 2, x0 + w - (60 + (i * 37) % 90), yy + 12), fill=(190, 198, 214, 255))
    d.line((x0 + 30, y0 + h - 70, x0 + w - 30, y0 + h - 70), fill=(150, 160, 180, 255), width=2)
    d.text((x0 + 30, y0 + h - 60), "검토·서명", font=R.font(20), fill=(110, 120, 140, 255))
    if sign > 0:                                                                                    # 서명 곡선이 그려진다
        pts = [(x0 + 150 + 180 * u, y0 + h - 95 - 22 * math.sin(u * 9) - 10 * u) for u in [i / 60 for i in range(int(60 * min(1, sign)) + 1)]]
        if len(pts) > 1:
            d.line(pts, fill=(30, 58, 140, 255), width=4)
    img.alpha_composite(_fade(lay, a))


def card(img, s, x, y, a, color):
    if a <= 0:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    w = int(R.font(28, True).getlength(s)) + 50
    d.rounded_rectangle((x - w // 2, y - 34, x + w // 2, y + 34), radius=18, fill=R.C["card"] + (240,), outline=R.C[color] + (255,), width=4)
    d.text((x, y), s, font=R.font(28, True), fill=R.C["ink"] + (255,), anchor="mm")
    img.alpha_composite(_fade(lay, a))


# ------------------------------------------------------------------ 장면
OFFICE = STREET = MAPIMG = None


def sc1(img, t, L):        # A씨, 팀장 메시지
    img.alpha_composite(OFFICE)
    mood = "neutral" if t < 0.35 * L else "worry"
    put(img, P(mood, blinking(t), 0.0), 640, 560)
    desk(img)
    laptop(img)
    phone(img, 1540, 640, ease((t - 0.15 * L) / 0.5), "정보공개서 정기변경\n4월 30일까지\n부탁해요!")
    R.text(img, (120, 110), "4월 28일 · 오후 6시 20분", 34, "muted", True, ease(t / 0.6))


def sc2(img, t, L):        # 걱정 말풍선
    img.alpha_composite(OFFICE)
    put(img, P("worry", blinking(t, off=1.0), 0.0), 640, 560)
    desk(img)
    laptop(img)
    th = [("가맹점이 몇 곳\n열고 닫았더라?", 290, 200, 0.05), ("작년 숫자 그대로\n내도 되나?", 1000, 160, 0.22),
          ("대행 맡기면\n한 건에 30만 원…", 1500, 320, 0.4), ("늦으면\n과태료…", 280, 470, 0.58)]
    for s, x, y, at in th:
        bubble(img, s, x, y, ease((t - at * L) / 0.4), 30, think=True, tail=(1 if x < 640 else -1, 1))
    calendar(img, 1640, 680, ease((t - 0.7 * L) / 0.4), 0.9)


def sc3(img, t, L):        # CapCred 등장
    img.alpha_composite(OFFICE)
    q = (t - 0.2 * L) / (0.35 * L)
    mood = "surprise" if 0 < q < 1.3 else ("worry" if q <= 0 else "neutral")
    put(img, P(mood, blinking(t, off=0.4), 0.0), 640, 560)
    desk(img)
    laptop(img, glow=ease((t - 0.05 * L) / 0.4))
    p = ease(q)
    bob = 10 * math.sin(t * 3)
    put(img, B("open" if not blinking(t, 2.6) else "blink"), lerp(1200, 1420, p), lerp(640, 400, p) + bob, alpha=min(1, p * 2), scale=lerp(0.2, 1.0, p))
    bubble(img, f"안녕하세요, {NAME}예요!\n해야 하는 일을 말해 주세요", 1440, 150, ease((t - 0.62 * L) / 0.4), 30, tail=(0, 1))


def sc4(img, t, L):        # 요청 한 줄 -> 공공 기록 모으기
    img.alpha_composite(OFFICE)
    put(img, P("neutral", blinking(t, off=0.7), t * 2.5 if t < 0.35 * L else 0.0), 640, 560)
    desk(img)
    laptop(img, glow=0.6)
    bob = 10 * math.sin(t * 3)
    spin = (t - 0.35 * L) / (0.45 * L)
    put(img, B("open" if not blinking(t, 2.6) else "blink"), 1420, 400 + bob)
    bubble(img, "4월 30일까지 정보공개서를 고쳐야 해서요.\n우리 브랜드 정기변경 준비해 줘!", 680, 150, ease(t / 0.4), 30, tail=(0, 1))
    src = [("서울 인허가 기록", 160, 320, "acc"), ("공정위 가맹정보", 1800, 120, "gold"), ("전자공시 DART", 1800, 700, "vio")]
    for i, (s, x0, y0, c) in enumerate(src):
        p = ease(spin - i * 0.12)
        if p > 0:
            x, y = lerp(x0, 1420 + 230 * math.cos(i * 2.1 + t), p), lerp(y0, 400 + 150 * math.sin(i * 2.1 + t), p)
            card(img, s, x, y, min(1, p * 3) * (1 - ease((spin - 0.95) / 0.1)), c)


def sc5(img, t, L):        # 초안 + 경보 두 곳
    img.alpha_composite(OFFICE)
    put(img, P("neutral" if t < 0.45 * L else "happy", blinking(t, off=0.2), 0.0), 520, 560)
    desk(img)
    laptop(img, glow=0.5)
    put(img, B("happy" if t > 0.5 * L else "open"), 1540, 400 + 10 * math.sin(t * 3))
    p = ease(t / (0.35 * L))
    paper(img, lerp(1400, 1010, p), lerp(420, 470, p), min(1, p * 2), rows_hi=ease((t - 0.4 * L) / 0.3))
    bubble(img, "크게 바뀔 곳 두 곳만\n확인해 보세요", 1560, 150, ease((t - 0.45 * L) / 0.4), 30, tail=(0, 1))


def sc6(img, t, L):        # 서명, 퇴근
    img.alpha_composite(OFFICE)
    put(img, P("happy", blinking(t, off=0.9), 0.0), 520, 560)
    desk(img)
    laptop(img, glow=0.3)
    paper(img, 1010, 470, 1.0, rows_hi=1, sign=ease((t - 0.1 * L) / (0.45 * L)))
    put(img, B("happy", wave=(0.5 + 0.5 * math.sin(t * 6)) if t > 0.6 * L else 0.0), 1540, 400 + 10 * math.sin(t * 3))
    R.text(img, (120, 110), "4월 28일 · 오후 6시 58분", 34, "ok", True, ease((t - 0.55 * L) / 0.5))
    bubble(img, "오늘은 제시간에 퇴근!", 520, 190, ease((t - 0.6 * L) / 0.4), 32, tail=(0, 1))


def sc7(img, t, L):        # 같은 캐릭터가 은행·구청·가게로
    img.alpha_composite(STREET)
    stops = [(400, "bank", "은행", "대출 사후점검\n사업장 확인서"), (960, "office", "구청", "인허가 대장\n정비 목록"), (1520, "shop", "동네 가게", "창업 전\n동네 업종 기준선")]
    for x, kind, label, _ in stops:
        building(img, x, kind, label)
    seg = t / L * 3
    i = min(2, int(seg))
    p = ease((seg - i) / 0.5)
    bx = lerp(stops[i - 1][0] if i > 0 else 100, stops[i][0], p)
    put(img, B("happy"), bx, 250 + 14 * math.sin(t * 4), scale=0.7)
    for j, (x, _, _, msg) in enumerate(stops):
        if j <= i:
            bubble(img, msg, x, 110, ease((seg - j - 0.4) / 0.3), 26, tail=(0, 1), fill=(236, 246, 255))


def sc8(img, t, L):        # 서울 야경(89만 곳 점 지도) + 마무리
    z = 1.0 + 0.15 * (t / L)
    w, h = int(MAPIMG.width * z), int(MAPIMG.height * z)
    m = MAPIMG.resize((w, h), Image.LANCZOS)
    cx, cy = (w - MAPIMG.width) // 2, (h - MAPIMG.height) // 2
    m = m.crop((cx, cy, cx + MAPIMG.width, cy + MAPIMG.height))
    img.alpha_composite(m, ((R.W - m.width) // 2, (R.H - m.height) // 2 - 30))
    a = ease((t - 0.5 * L) / 0.5)
    if a > 0:
        img.alpha_composite(Image.new("RGBA", img.size, (8, 12, 26, int(60 * a))))
        R.text(img, (960, 400), "일할 역량과 믿을 근거", 64, "ink", True, a, "mm")
        R.text(img, (960, 520), NAME, 120, "gold", True, a, "mm")
        R.text(img, (960, 620), "Capacity × Credibility", 34, "acc", False, a, "mm")
        put(img, B("happy", 0.5 + 0.5 * math.sin(t * 6)), 1480, 500, alpha=a, scale=0.55)
        R.text(img, (960, 950), "등장인물·회사는 가상입니다 · 서울 지방행정 인허가 894,933곳의 개업·폐업 기록 · 검토·서명은 사람이 합니다",
               22, "muted", False, a, "mm")


SCENES = [
    (sc1, "작은 프랜차이즈 본부의 회사원 A씨. 퇴근 직전, 팀장님 메시지 한 줄에 마음이 무거워집니다.", None),
    (sc2, "가맹점이 몇 곳 열고 닫았는지, 작년 숫자를 그대로 내도 되는지. 맡기자니 한 건에 30만 원, 늦으면 과태료입니다.",
     "가맹점이 몇 곳 열고 닫았는지, 작년 숫자를 그대로 내도 되는지. 맡기자니 한 건에 삼십만 원, 늦으면 과태료입니다."),
    (sc3, f"그때, 노트북에서 {NAME}가 나타납니다. 해야 하는 일을 이유와 함께 한 줄로 말하면 됩니다.",
     "그때, 노트북에서 캡크레드가 나타납니다. 해야 하는 일을 이유와 함께 한 줄로 말하면 됩니다."),
    (sc4, f"{NAME}는 서울 인허가 기록과 공정위 가맹정보, 전자공시를 불러와 숫자를 미리 채웁니다.",
     "캡크레드는 서울 인허가 기록과 공정위 가맹정보, 전자공시를 불러와 숫자를 미리 채웁니다."),
    (sc5, "크게 바뀔 매장 두 곳은 따로 짚어 줍니다. A씨는 그 두 곳만 확인하면 됩니다.", None),
    (sc6, "마지막 확인과 서명은 사람이 합니다. 오늘 A씨는 제시간에 퇴근합니다.", None),
    (sc7, f"은행의 대출 점검도, 구청의 대장 정비도. 누군가 해야 하는 일을 {NAME}가 대신합니다.",
     "은행의 대출 점검도, 구청의 대장 정비도. 누군가 해야 하는 일을 캡크레드가 대신합니다."),
    (sc8, f"서울 89만 개의 문이 열고 닫힌 기록 위에서. 일할 역량과 믿을 근거, {NAME}.",
     "서울 팔십구만 개의 문이 열고 닫힌 기록 위에서. 일할 역량과 믿을 근거, 캡크레드."),
]


def sub(img, s):
    d = ImageDraw.Draw(img)
    d.rectangle((0, R.H - 78, R.W, R.H), fill=(8, 12, 24, 190))
    R.text(img, (R.W // 2, R.H - 40), s, 30, "ink", False, 1.0, "mm")


def main():
    global OFFICE, STREET, MAPIMG
    from render_motion_1min import _ffmpeg
    os.makedirs(OUT, exist_ok=True)
    R.OUT = OUT
    S = [{"sec": "", "narr": n, "tts": tts, "els": [], "key": None} for _, n, tts in SCENES]
    durs = R.synth(S, 3)
    pads = [(0.5, 0.8)] * len(S)
    pads[-1] = (0.4, 3.2)
    lens = R.build_audio(S, durs, pads)
    R.srt(S, lens, pads, durs)
    OFFICE, STREET = office_bg(), street_bg()
    MAPIMG = Image.open(MAP).convert("RGBA")
    MAPIMG.thumbnail((1700, 900))
    bg = R.background()
    os.makedirs(FINAL, exist_ok=True)
    mp4 = os.path.join(FINAL, "ai_film.mp4")
    ff = subprocess.Popen([_ffmpeg(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{R.W}x{R.H}", "-r", str(R.FPS),
                           "-i", "-", "-i", os.path.join(OUT, "narration.wav"), "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", mp4], stdin=subprocess.PIPE)
    stills = "--stills" in sys.argv
    for i, ((fn, narr, _), L) in enumerate(zip(SCENES, lens)):
        n = int(round(L * R.FPS))
        for f in range(n):
            t = f / R.FPS
            img = bg.copy()
            fn(img, t, L)
            sub(img, narr)
            k = min(1.0, t / 0.35, (L - t) / 0.35)
            if k < 1.0:
                img = Image.blend(bg, img, max(0.0, k))
            if stills and f == int(n * 0.8):
                img.convert("RGB").resize((960, 540)).save(os.path.join(OUT, f"still_{i + 1}.png"))
            ff.stdin.write(img.convert("RGB").tobytes())
    ff.stdin.close()
    ff.wait()
    os.replace(os.path.join(OUT, "motion_draft.srt"), os.path.join(FINAL, "ai_film.srt"))
    print(f"film -> {mp4} {sum(lens):.1f}s")


if __name__ == "__main__":
    main()

"""모션그래픽 영상 초안 렌더러 - 장면 정의 하나에서 영상·내레이션·자막·대본 문서를 함께 만든다 (2026-10-09).

python -X utf8 scripts/render_motion_video.py --stills        장면별 확인용 정지 화면만(빠름) -> deliverables/video/stills/
python -X utf8 scripts/render_motion_video.py                 전체 렌더 -> deliverables/video/motion_draft.mp4 (+ .srt, narration.wav)
python -X utf8 scripts/render_motion_video.py --script        대본 문서만 -> deliverables/VIDEO_MOTION_SCRIPT.md

- 화면: 1920x1080, 24fps, PIL로 프레임을 그려 ffmpeg(libx264)로 인코딩(메모리 수백 MB)
- 내레이션: Windows 내장 한국어 음성(Microsoft Heami, System.Speech) - 초안용. 최종본은 본인 녹음이나 다른 TTS로
  교체하면 된다(장면 길이는 내레이션 길이 + 여백으로 자동 결정되므로 같은 스크립트로 다시 렌더).
- 숫자: 모두 DINTEL_BUSINESS_PLAN.md / data/dintel/*.json / scoreboard/ledger.csv 의 실측값. 신용캐드 점수는 합성 데이터 MVP라고
  화면에 표시한다.
- 배경음악은 넣지 않는다(편집 단계에서 저작권 문제없는 음원으로 추가).
"""
import argparse
import json
import math
import os
import subprocess
import sys
import wave
from functools import lru_cache

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

W, H, FPS = 1920, 1080, 24
OUT = os.path.join(ROOT, "deliverables", "video")
FONT_DIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
C = {"bg1": (8, 12, 26), "bg2": (18, 28, 56), "ink": (241, 245, 249), "muted": (148, 163, 184),
     "acc": (56, 189, 248), "warn": (248, 113, 113), "ok": (52, 211, 153), "vio": (167, 139, 250),
     "slate": (100, 116, 139), "grid": (51, 65, 85), "card": (22, 33, 62), "gold": (251, 191, 36)}


@lru_cache(maxsize=64)
def font(size, bold=False):
    return ImageFont.truetype(os.path.join(FONT_DIR, "malgunbd.ttf" if bold else "malgun.ttf"), size)


def col(c):
    return C[c] if isinstance(c, str) else c


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


# ---------------------------------------------------------------- 그리기 도구(알파는 작은 레이어로만 합성)
def text(img, xy, s, size, color="ink", bold=False, alpha=1.0, anchor="la", dy=0):
    if alpha <= 0.01:
        return
    f = font(size, bold)
    x, y = xy[0], xy[1] + dy
    rgb = col(color)
    if alpha >= 0.995:
        ImageDraw.Draw(img).text((x, y), s, font=f, fill=rgb + (255,), anchor=anchor)
        return
    l, t, r, b = ImageDraw.Draw(img).textbbox((x, y), s, font=f, anchor=anchor)
    l, t = int(l) - 2, int(t) - 2
    w, h = int(r) - l + 4, int(b) - t + 4
    if w <= 0 or h <= 0:
        return
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((x - l, y - t), s, font=f, fill=rgb + (int(255 * alpha),), anchor=anchor)
    img.alpha_composite(layer, (max(l, 0), max(t, 0)))


def rrect(img, box, fill=None, outline=None, width=3, radius=22, alpha=1.0):
    if alpha <= 0.01:
        return
    x0, y0, x1, y1 = [int(v) for v in box]
    if x1 <= x0 or y1 <= y0:
        return
    layer = Image.new("RGBA", (x1 - x0 + 1, y1 - y0 + 1), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = int(255 * alpha)
    d.rounded_rectangle((0, 0, x1 - x0, y1 - y0), radius=radius,
                        fill=(col(fill) + (a,)) if fill else None,
                        outline=(col(outline) + (a,)) if outline else None, width=width)
    img.alpha_composite(layer, (x0, y0))


def wrap(s, size, maxw, bold=False):
    f = font(size, bold)
    out = []
    for para in s.split("\n"):
        line = ""
        for word in para.split(" "):
            cand = (line + " " + word).strip()
            if f.getlength(cand) <= maxw or not line:
                line = cand
            else:
                out.append(line)
                line = word
        out.append(line)
    return out


# ---------------------------------------------------------------- 장면 요소(at = 장면 길이 대비 등장 시점 0~1)
class T:
    def __init__(self, s, x, y, size=44, color="ink", bold=False, at=0.0, anchor="la", maxw=None, lh=1.4, fx="up"):
        self.s, self.x, self.y, self.size, self.color, self.bold = s, x, y, size, color, bold
        self.at, self.anchor, self.maxw, self.lh, self.fx = at, anchor, maxw, lh, fx

    def draw(self, img, t, L):
        p = ease((t - self.at * L) / 0.6)
        if p <= 0:
            return
        lines = wrap(self.s, self.size, self.maxw, self.bold) if self.maxw else self.s.split("\n")
        dy = int((1 - p) * 24) if self.fx == "up" else 0
        for i, ln in enumerate(lines):
            text(img, (self.x, self.y + i * int(self.size * self.lh)), ln, self.size, self.color, self.bold, p,
                 self.anchor, dy)


class Type(T):
    """타자기 효과(해시 등)."""
    def __init__(self, s, x, y, size=36, color="acc", at=0.0, cps=40, anchor="la", bold=False):
        super().__init__(s, x, y, size, color, bold, at, anchor)
        self.cps = cps

    def draw(self, img, t, L):
        n = int((t - self.at * L) * self.cps)
        if n > 0:
            text(img, (self.x, self.y), self.s[:n], self.size, self.color, self.bold, 1.0, self.anchor)


class Num:
    def __init__(self, v, fmt, x, y, size=140, color="acc", at=0.0, dur=1.4, anchor="mm", label=None, lsize=34):
        self.v, self.fmt, self.x, self.y, self.size, self.color = v, fmt, x, y, size, color
        self.at, self.dur, self.anchor, self.label, self.lsize = at, dur, anchor, label, lsize

    def draw(self, img, t, L):
        q = (t - self.at * L)
        if q <= 0:
            return
        p = ease(q / self.dur)
        text(img, (self.x, self.y), self.fmt(self.v * p), self.size, self.color, True, min(1, q / 0.4), self.anchor)
        if self.label:
            for i, ln in enumerate(self.label.split("\n")):
                text(img, (self.x, self.y + self.size * 0.75 + i * self.lsize * 1.35), ln, self.lsize, "muted",
                     False, min(1, q / 0.6), "mm")


class Bars:
    """세로 막대(그룹 가능). values: [v...] 또는 [[s1,s2..]...]. vmin으로 축 시작점(정직하게 축 표시)."""
    def __init__(self, box, values, labels, colors, at=0.1, stagger=0.06, vmin=0.0, vmax=None, fmt="{:.1f}",
                 ref=None, legend=None, lsize=30, vsize=32, ticks=None):
        self.box, self.values, self.labels, self.colors = box, values, labels, colors
        self.at, self.stagger, self.vmin, self.fmt, self.ref, self.legend = at, stagger, vmin, fmt, ref, legend
        flat = [v for g in values for v in (g if isinstance(g, (list, tuple)) else [g])]
        self.vmax = vmax or max(flat) * 1.18
        self.lsize, self.vsize, self.ticks = lsize, vsize, ticks

    def y_of(self, v):
        x0, y0, x1, y1 = self.box
        return y1 - (v - self.vmin) / (self.vmax - self.vmin) * (y1 - y0)

    def draw(self, img, t, L):
        x0, y0, x1, y1 = self.box
        base = (t - self.at * L)
        if base <= -0.5:
            return
        a = min(1, max(0, (base + 0.5) / 0.5))
        d = ImageDraw.Draw(img)
        for tv in (self.ticks or []):
            yy = self.y_of(tv)
            d.line((x0, yy, x1, yy), fill=C["grid"] + (int(255 * a),), width=1)
            text(img, (x0 - 14, yy), self.fmt.format(tv) if isinstance(tv, float) else str(tv), 22, "muted", False,
                 a, "rm")
        d.line((x0, y1, x1, y1), fill=C["slate"] + (int(255 * a),), width=2)
        n = len(self.values)
        slot = (x1 - x0) / n
        for i, g in enumerate(self.values):
            g = g if isinstance(g, (list, tuple)) else [g]
            k = len(g)
            bw = slot * (0.62 if k == 1 else 0.8) / k
            gx = x0 + slot * i + slot * (0.19 if k == 1 else 0.1)
            for j, v in enumerate(g):
                p = ease((base - (i * k + j) * self.stagger * L) / 1.0)
                if p <= 0:
                    continue
                cc = self.colors[i] if k == 1 else self.colors[j]
                top = self.y_of(self.vmin + (v - self.vmin) * p)
                bx = gx + j * bw
                if top < y1 - 2:
                    d.rectangle((bx + 3, top, bx + bw - 3, y1 - 1), fill=col(cc) + (255,))
                if p > 0.85:
                    text(img, (bx + bw / 2, top - 10), self.fmt.format(v), self.vsize, "ink", True, (p - 0.85) / 0.15,
                         "md")
            text(img, (x0 + slot * (i + 0.5), y1 + 18), self.labels[i], self.lsize, "ink", False, a, "ma")
        if self.ref:
            rv, rl, rc = self.ref
            yy = self.y_of(rv)
            for xx in range(int(x0), int(x1), 28):
                d.line((xx, yy, min(xx + 16, x1), yy), fill=col(rc) + (int(255 * a),), width=3)
            # 범례 자리(그래프 오른쪽 위)에 표시 - 막대와 겹치지 않게
            lw = font(26, True).getlength(rl)
            lx = x1 - lw - 70
            for xx in range(int(lx), int(lx + 50), 20):
                d.line((xx, y0 - 37, xx + 12, y0 - 37), fill=col(rc) + (int(255 * a),), width=4)
            text(img, (x1, y0 - 37), rl, 26, rc, True, a, "rm")
        if self.legend:
            for j, (nm, cc) in enumerate(self.legend):
                lx = x0 + 10 + j * 420
                d.rectangle((lx, y0 - 50, lx + 30, y0 - 24), fill=col(cc) + (int(255 * a),))
                text(img, (lx + 42, y0 - 37), nm, 26, "ink", False, a, "lm")


class Box:
    def __init__(self, x, y, w, h, title, body="", color="acc", at=0.0, tsize=36, bsize=30, fill="card"):
        self.r = (x, y, x + w, y + h)
        self.title, self.body, self.color, self.at, self.tsize, self.bsize, self.fill = title, body, color, at, tsize, bsize, fill

    def draw(self, img, t, L):
        p = ease((t - self.at * L) / 0.6)
        if p <= 0:
            return
        x0, y0, x1, y1 = self.r
        dy = int((1 - p) * 30)
        rrect(img, (x0, y0 + dy, x1, y1 + dy), fill=self.fill, outline=self.color, width=3, alpha=p)
        ImageDraw.Draw(img).rectangle((x0 + 3, y0 + dy + 20, x0 + 10, y1 + dy - 20), fill=col(self.color) + (int(255 * p),))
        text(img, (x0 + 36, y0 + 28 + dy), self.title, self.tsize, self.color, True, p)
        for i, ln in enumerate(wrap(self.body, self.bsize, x1 - x0 - 72)):
            text(img, (x0 + 36, y0 + 34 + self.tsize * 1.5 + i * self.bsize * 1.45 + dy), ln, self.bsize, "ink", False, p)


class Arrow:
    def __init__(self, x0, y0, x1, y1, at=0.0, color="muted", width=5):
        self.p0, self.p1, self.at, self.color, self.width = (x0, y0), (x1, y1), at, color, width

    def draw(self, img, t, L):
        p = ease((t - self.at * L) / 0.5)
        if p <= 0:
            return
        (x0, y0), (x1, y1) = self.p0, self.p1
        xe, ye = x0 + (x1 - x0) * p, y0 + (y1 - y0) * p
        d = ImageDraw.Draw(img)
        d.line((x0, y0, xe, ye), fill=col(self.color) + (255,), width=self.width)
        if p > 0.95:
            ang = math.atan2(y1 - y0, x1 - x0)
            pts = [(x1, y1), (x1 - 22 * math.cos(ang - 0.45), y1 - 22 * math.sin(ang - 0.45)),
                   (x1 - 22 * math.cos(ang + 0.45), y1 - 22 * math.sin(ang + 0.45))]
            d.polygon(pts, fill=col(self.color) + (255,))


class Line:
    """두 시계열 선이 왼쪽부터 그려진다(가상 성적표 장면)."""
    def __init__(self, box, series, colors, labels, at=0.1, dur=0.55, vmax=None, xt=None, widths=(6, 4)):
        self.box, self.series, self.colors, self.labels, self.at, self.dur = box, series, colors, labels, at, dur
        self.vmax = vmax or max(max(x) for x in series) * 1.15
        self.xt, self.widths = xt or [], widths

    def draw(self, img, t, L):
        x0, y0, x1, y1 = self.box
        q = (t - self.at * L) / (self.dur * L)
        if q <= -0.2:
            return
        p = max(0.0, min(1.0, q))
        d = ImageDraw.Draw(img)
        for v in range(0, int(self.vmax) + 1, 10):
            yy = y1 - v / self.vmax * (y1 - y0)
            d.line((x0, yy, x1, yy), fill=C["grid"] + (255,), width=1)
            text(img, (x0 - 14, yy), f"{v}%", 22, "muted", False, 1.0, "rm")
        d.line((x0, y1, x1, y1), fill=C["slate"] + (255,), width=2)
        n = len(self.series[0])
        xs = [x0 + (x1 - x0) * i / (n - 1) for i in range(n)]
        for i, lab in self.xt:
            text(img, (xs[i], y1 + 16), lab, 24, "muted", False, 1.0, "ma")
        k = max(2, int(round(p * (n - 1))) + 1)
        for ser, cc, w in zip(self.series, self.colors, self.widths):
            pts = [(xs[i], y1 - ser[i] / self.vmax * (y1 - y0)) for i in range(k)]
            d.line(pts, fill=col(cc) + (255,), width=w, joint="curve")
        for j, (lab, cc) in enumerate(zip(self.labels, self.colors)):
            lx = x1 - 420 + j * 230
            d.rectangle((lx, y0 - 46, lx + 34, y0 - 40), fill=col(cc) + (255,))
            text(img, (lx + 44, y0 - 43), lab, 24, "ink", False, 1.0, "lm")


class Circ:
    """두 원이 가운데로 모이는 결합 장면용."""
    def __init__(self, cx0, cx1, cy, r, color, title, body, at=0.0, dur=1.6, tx_off=0):
        self.cx0, self.cx1, self.cy, self.r, self.color = cx0, cx1, cy, r, color
        self.title, self.body, self.at, self.dur, self.tx_off = title, body, at, dur, tx_off

    def draw(self, img, t, L):
        q = t - self.at * L
        if q <= 0:
            return
        p = ease(q / self.dur)
        a = min(1, q / 0.5)
        cx = self.cx0 + (self.cx1 - self.cx0) * p
        r = self.r
        layer = Image.new("RGBA", (2 * r + 8, 2 * r + 8), (0, 0, 0, 0))
        dd = ImageDraw.Draw(layer)
        dd.ellipse((4, 4, 2 * r + 4, 2 * r + 4), fill=col(self.color) + (int(46 * a),),
                   outline=col(self.color) + (int(255 * a),), width=5)
        img.alpha_composite(layer, (int(cx - r - 4), int(self.cy - r - 4)))
        tx = cx + self.tx_off
        text(img, (tx, self.cy - 130), self.title, 58, self.color, True, a, "mm")
        for i, ln in enumerate(self.body.split("\n")):
            text(img, (tx, self.cy - 30 + i * 56), ln, 34, "ink", False, a, "mm")


class Pulse:
    """결합 장면 가운데 겹친 부분 강조 텍스트."""
    def __init__(self, s, x, y, size=40, color="gold", at=0.0):
        self.s, self.x, self.y, self.size, self.color, self.at = s, x, y, size, color, at

    def draw(self, img, t, L):
        q = t - self.at * L
        if q <= 0:
            return
        a = min(1, q / 0.5)
        text(img, (self.x, self.y), self.s, self.size, self.color, True, a, "mm")


# ---------------------------------------------------------------- 실측값
def _risk(m):
    with open(os.path.join(ROOT, "data", "dintel", f"risk_model_{m}.json"), encoding="utf-8") as fh:
        return json.load(fh)["validation"]


def _ledger():
    import csv
    with open(os.path.join(ROOT, "scoreboard", "ledger.csv"), encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _live_disclosures():
    """실시간 공시 수집(scripts/collect_disclosures_live.py) 일평균 건수와 수집 일수 - 없으면 10-16 첫날 값."""
    import glob
    fs = sorted(glob.glob(os.path.join(ROOT, "data", "quant", "disclosures_live", "20*.csv")))
    if not fs:
        return 250, 1
    n = [sum(1 for _ in open(f, encoding="utf-8")) - 1 for f in fs]
    return int(round(sum(n) / len(n), -1)), len(fs)


def _caed():
    with open(os.path.join(ROOT, "docs", "site_api_samples", "biz_caed_demoAB.json"), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- 장면(내레이션 = 화면 자막·대본 문서와 같은 글)
def scenes():
    kq = _risk("kosdaq")
    led = _ledger()
    kq_led = [r for r in led if r["market"] == "kosdaq"][0]
    ks_led = [r for r in led if r["market"] == "kospi"][0]
    A = _caed()["A"]
    dec = [round(v * 100, 1) for v in kq["deciles"]]
    from dintel.evidence import _surv
    sv = _surv()
    yrs = sorted(kq["auc_by_year"])
    S = []

    def sc(sec, narr, els, tts=None, key=None):
        S.append({"sec": sec, "narr": narr, "tts": tts, "els": els, "key": key})

    sc("", "점수가 낮은 이유와 위험해지는 이유를, 실제 결과로 검증된 숫자로 설명합니다. 공시 기반 재무위험 조기경보 딘텔과, "
           "소상공인 공정신용 진단 신용캐드를 하나로 합친 사업입니다.",
       [T("dintel × 신용캐드", 960, 400, 124, "ink", True, 0.0, "mm"),
        T("점수가 낮은 이유와, 위험해지는 이유를", 960, 580, 54, "ink", False, 0.2, "mm"),
        T("실제 결과로 검증된 숫자로 설명합니다", 960, 665, 54, "acc", True, 0.35, "mm"),
        T("공시 기반 재무위험 조기경보  +  소상공인 공정신용 진단", 960, 800, 34, "muted", False, 0.6, "mm")])

    sc("프롤로그", "코스닥 상장사 천육백 곳이 2015년 이후 낸 공시는 26만 6천 건입니다. 위험한 회사는 이 공시 속에서 먼저 신호를 "
                "보냅니다. 그런데 그 신호를, 누가, 얼마나 정확하게 읽고 있을까요?",
       [Num(1600, lambda v: f"{v:,.0f}곳", 560, 420, 150, "acc", 0.0, label="코스닥 상장사"),
        Num(26.6, lambda v: f"{v:.1f}만 건", 1360, 420, 150, "vio", 0.15, label="2015년 이후 공시"),
        T("위험한 회사는 공시 속에서 먼저 신호를 보낸다", 960, 760, 50, "ink", True, 0.45, "mm"),
        T("그 신호를 누가, 얼마나 정확하게 읽고 있을까?", 960, 860, 42, "warn", False, 0.7, "mm")])

    sc("01  이유", "첫 번째 이유. 위험은 가격보다 공시에 먼저 나타납니다. 시가총액과 수익률, 변동성 같은 가격 정보만으로 다음 열두 달의 "
                 "위험 공시를 예측하면, 정확도 지표가 0.55로 동전 던지기와 거의 같습니다. 같은 기간 공시 정보로 만든 모델은 0.68입니다.",
       [T("위험은 가격보다 공시에 먼저 나타난다", 120, 120, 62, "ink", True),
        T("다음 12개월 중대 위험 공시 예측력 (AUC · 0.5 = 동전 던지기) · 코스닥 · 2020년까지 학습, 2022~2025 검증", 120, 215, 28,
          "muted"),
        Bars((420, 340, 1500, 900), [kq["auc_price_only"], kq["auc"]], ["가격 정보만", "공시 정보"], ["slate", "acc"],
             at=0.3, stagger=0.25, vmin=0.4, vmax=0.75, fmt="{:.2f}", ref=(0.5, "동전 던지기 0.50", "warn"), lsize=36,
             vsize=54, ticks=[0.4, 0.5, 0.6, 0.7])],
       tts=None)

    sc("01  이유", "두 번째 이유. 공시는 너무 많고, 중요한 내용은 원문 깊숙이 있습니다. 제목만 보고 거르면 큰 급락의 "
                 "9퍼센트에서 13퍼센트만 잡힙니다. 누구에게 신주를 배정했는지, 전환가격을 다시 낮출 수 있는지, 할인율이 얼마인지는 원문을 읽어야 보입니다.",
       [T("공시는 많고, 중요한 건 원문 깊숙이 있다", 120, 120, 62, "ink", True),
        Box(120, 270, 1680, 180, "제목만 읽으면", "큰 급락의 9~13%만 잡힌다 (관심목록 데스크 실측, 2022~)", "warn", 0.2),
        Box(120, 490, 1680, 180, "원문에 숨은 조건", "배정 대상 · 리픽싱(전환가 하향 조항) · 할인율 · 최대주주 변경 동반 여부", "acc",
            0.45),
        Box(120, 710, 1680, 180, "이미 파싱한 원문", "자금조달 7,156건 · 공급계약 18,121건", "ok", 0.72)])

    sc("01  이유", "세 번째 이유는 시점입니다. 상장폐지 요건이 강화되면서 지난 사업연도 상장폐지 사유가 발생한 기업은 코스닥 42곳, "
                 "코스피 12곳이었습니다. 증권사 신용융자와 주식담보대출은 하루 평균 약 62조 원입니다. 어느 회사가 위험한지 미리 아는 일에 "
                 "큰돈이 걸려 있습니다.",
       [T("지금이 시점이다", 120, 120, 62, "ink", True),
        T("2026년 상장폐지 요건 강화 이후", 120, 215, 30, "muted"),
        Num(42, lambda v: f"{v:.0f}곳", 400, 480, 150, "warn", 0.18, label="코스닥 상장폐지 사유 발생\n(2025사업연도)"),
        Num(12, lambda v: f"{v:.0f}곳", 960, 480, 150, "warn", 0.3, label="코스피 상장폐지 사유 발생"),
        Num(62, lambda v: f"{v:.0f}조 원", 1520, 480, 150, "gold", 0.55, label="신용융자·주식담보대출\n하루 평균 (2026 2분기)"),
        T("출처: 헤럴드경제(2026-04-08, 2026-07-05)", 120, 990, 22, "muted", False, 0.6)])

    sc("02  현장", "같은 문제는 동네 사업자에게도 있습니다. 신용캐드 팀이 헬스장 사장님들을 인터뷰했을 때 세 가지 장벽이 반복됐습니다. "
                 "시설에 투자하느라 담보가 남지 않고, 운영자금이 필요한 비수기에는 매출이 줄어 심사가 더 불리해지며, 운동기구와 인테리어 "
                 "투자는 평가에 반영되지 않는다는 것입니다. 문제는 점수가 낮다는 것보다, 왜 낮은지 설명되지 않는다는 데 있었습니다.",
       [T("동네 사업자도 같은 문제를 겪는다", 120, 120, 62, "ink", True),
        T("신용캐드 · 헬스장 사장님 인터뷰에서 반복된 세 가지 장벽", 120, 215, 30, "muted"),
        Box(120, 290, 1680, 150, "\u201c담보가 남지 않는다\u201d", "초기 시설투자가 커서 잡을 재산이 없다", "vio", 0.18),
        Box(120, 470, 1680, 150, "\u201c비수기의 역설\u201d", "운영자금이 필요한 때 매출이 떨어져 심사가 더 불리하다", "vio", 0.33),
        Box(120, 650, 1680, 150, "\u201c투자가 안 보인다\u201d", "운동기구·인테리어 투자가 평가에 반영되지 않는다", "vio", 0.48),
        T("문제는 점수가 낮다는 것보다, 왜 낮은지 설명되지 않는다는 것", 960, 900, 42, "gold", True, 0.75, "mm")])

    sc("03  결합", "그래서 두 프로젝트를 합쳤습니다. 신용캐드는 현장에서 확인한 문제와, 재무만 보는 평가가 작은 사업자를 과하게 위험하다고 "
                 "본다는 가설을 가져왔습니다. 딘텔은 신용캐드에 없던 두 가지, 실제로 위험 공시가 났는지라는 정답 데이터와 기업별 공시 연쇄 "
                 "신호를 가져왔습니다.",
       [Circ(420, 700, 520, 390, "vio", "신용캐드", "현장의 문제\n규모 편향 가설\n설명형 리포트", 0.05, tx_off=-120),
        Circ(1500, 1220, 520, 390, "acc", "dintel", "실제 정답 데이터\n공시 연쇄 신호\n시점 고정 검증", 0.35, tx_off=120),
        Pulse("가설을\n실데이터로", 960, 500, 40, "gold", 0.75),
        T("소상공인과 상장 소형사, 같은 질문: \u201c작다는 이유로 위험하게 보이는가?\u201d", 960, 990, 36, "ink", False, 0.8, "mm")])

    sc("04  제품", "제품은 이렇게 동작합니다. 공시 원문을 모아 유형을 분류하고, 자금조달과 공급계약의 조건을 꺼냅니다. 모든 계산은 그 시점에 "
                 "공개돼 있던 정보만 씁니다. 그 위에서 재무위험 조기경보 점수, 공시 유형별 과거 반응 통계, 자금조달 연쇄 분석을 만들고, "
                 "아침 브리프와 API, 그리고 공개 성적표로 전달합니다. 매수나 매도 의견은 내지 않습니다.",
       [T("제품은 이렇게 동작한다", 120, 120, 62, "ink", True),
        Box(120, 300, 380, 470, "원천", "DART 공시 원문\n\n시세는 검증용 내부 계산만(재배포 없음)", "slate", 0.08, bsize=30),
        Arrow(510, 535, 552, 535, 0.25),
        Box(560, 300, 380, 470, "엔진", "유형 분류\n원문 조건 파싱\n시점 고정(PIT) 집계", "acc", 0.25, bsize=30),
        Arrow(950, 535, 992, 535, 0.42),
        Box(1000, 300, 380, 470, "신호", "① 재무위험 조기경보\n② 공시 반응 통계\n③ 자금조달 연쇄", "vio", 0.42, bsize=30),
        Arrow(1390, 535, 1432, 535, 0.6),
        Box(1440, 300, 380, 470, "전달", "아침 데스크 브리프\nAPI\n공개 성적표", "ok", 0.6, bsize=30),
        T("매수·매도 의견은 내지 않는다 — 확률과 근거만", 960, 900, 42, "warn", True, 0.85, "mm")],
       tts=None)

    sc("05  근거", "근거를 보겠습니다. 2020년까지의 데이터로만 학습하고, 2022년부터는 전혀 보지 않은 기간으로 검증했습니다. 코스닥 기업을 "
                 "위험 점수로 열 단계로 나누면, 가장 위험한 10퍼센트의 실제 위험 공시율은 19.6퍼센트였습니다. 평균 6.1퍼센트의 3.2배이고, "
                 "전체 위험 사례의 32퍼센트를 미리 잡았습니다.",
       [T("경고 상위 10%에 위험이 몰린다", 120, 120, 62, "ink", True),
        T(f"코스닥 · 위험 점수 10분위별 실제 12개월 위험 공시율 · 검증 {kq['n_test']:,} 기업-월", 120, 215, 28, "muted"),
        Bars((200, 360, 1760, 900), dec, [str(i) for i in range(1, 11)], ["slate"] * 9 + ["warn"], at=0.25,
             stagger=0.03, vmax=24, fmt="{:.1f}%", ref=(kq["base_rate"] * 100, f"평균 {kq['base_rate']:.1%}", "muted"),
             vsize=28),
        T(f"평균의 {kq['top10_rate'] / kq['base_rate']:.1f}배 · 전체 위험의 {kq['capture_top10']:.0%} 포착", 1760, 300, 44,
          "warn", True, 0.65, "ra"),
        T("위험 점수 10분위 (10 = 가장 위험)", 980, 990, 26, "muted", False, 0.3, "mm")])

    sc("05  근거", "이 성능은 한 해만 맞은 것이 아닙니다. 같은 계수를 그대로 적용해도, 2022년부터 2025년까지 매년 0.64에서 0.70 사이를 "
                 "유지했습니다.",
       [T("한 해만 맞은 게 아니다", 120, 120, 62, "ink", True),
        T("코스닥 조기경보 연도별 AUC · 2020년까지 학습한 계수를 매년 그대로 적용 · 2025년은 9월까지", 120, 215, 28, "muted"),
        Bars((360, 340, 1560, 900), [kq["auc_by_year"][y] for y in yrs], yrs, ["acc"] * len(yrs), at=0.15,
             stagger=0.08, vmin=0.4, vmax=0.78, fmt="{:.2f}", ref=(0.5, "동전 던지기 0.50", "warn"), vsize=44, lsize=34,
             ticks=[0.4, 0.5, 0.6, 0.7])])

    if sv and "B" in sv:
        sc("05  근거", f"혹시 살아남은 회사만 봐서 좋아 보이는 건 아닐까요? 그래서 이미 상장폐지된 코스닥 기업 {sv['n_delisted']}곳을 찾아 "
                     f"넣고 다시 검증했습니다. 경고 상위 10퍼센트의 배수는 {sv['B']['multiple']:.1f}배 그대로였고, 이들의 실제 위험률은 "
                     f"{sv['B']['top10_pct']:.0f}퍼센트. 넷 중 하나가 1년 안에 중대 위험 공시를 냈습니다.",
           [T("퇴출된 회사를 채워 넣어도", 120, 120, 62, "ink", True),
            T(f"상장폐지 코스닥 기업 {sv['n_delisted']}곳을 DART로 보충 · 같은 피처 · 검증 2022~", 120, 215, 28, "muted"),
            Bars((200, 380, 1180, 880), [[sv[k]["base_pct"], sv[k]["top10_pct"]] for k in "AB"],
                 ["현재 상장사만 (기존)", "퇴출 기업 포함 (보정)"], ["slate", "warn"], at=0.25, stagger=0.06, vmax=32,
                 fmt="{:.1f}%", legend=[("평균 위험률", "slate"), ("경고 상위 10%", "warn")], lsize=32, vsize=36),
            T(f"배수 {sv['A']['multiple']:.1f}배 → {sv['B']['multiple']:.1f}배", 1280, 420, 44, "ok", True, 0.5),
            T(f"AUC {sv['A']['auc']:.3f} → {sv['B']['auc']:.3f}", 1280, 510, 38, "acc", False, 0.58),
            T(f"상위 10% {sv['A']['top10_pct']:.1f}% → {sv['B']['top10_pct']:.1f}%", 1280, 580, 38, "warn", False, 0.64),
            T("신호는 진짜였고,\n실제 위험은 더 컸다", 1280, 700, 50, "gold", True, 0.8)])

    psp = os.path.join(ROOT, "data", "dintel", "pseudo_scoreboard_kosdaq.csv")
    if os.path.exists(psp):
        import pandas as pd
        P = pd.read_csv(psp)
        above = (P["multiple"] > 1).mean()
        sc("05  근거", f"한 번 맞힌 것도 아닙니다. 2020년에 학습한 모델을 한 번도 고치지 않고, 2022년부터 매달 경고 목록을 고정했다고 해 봤습니다. "
                     f"{len(P)}개월 동안 경고 목록의 실제 위험률은 단 한 달도 빠짐없이 평균보다 높았고, 대부분의 달에서 두 배가 넘었습니다.",
           [T("매달 꾸준했다", 120, 120, 62, "ink", True),
            T(f"가상 성적표 · 2020년 학습 모델 그대로 · 매달 상위 10% 경고의 12개월 뒤 실제 위험률 · 코스닥 {len(P)}개월", 120, 215, 28, "muted"),
            Line((200, 360, 1720, 880), [P["hit_pct"].tolist(), P["base_pct"].tolist()], ["warn", "slate"],
                 ["경고 목록", "전체 평균"], at=0.15, dur=0.55, vmax=40,
                 xt=[(i, P["month"].iloc[i]) for i in range(0, len(P), max(1, len(P) // 6))]),
            T(f"평균보다 높았던 달 {above:.0%} · 배수 중앙값 {P['multiple'].median():.1f}배", 960, 960, 40, "gold", True, 0.75, "mm")])

    sc("05  근거", "가장 강한 신호는 자금조달의 반복입니다. 직전 1년 동안 자금조달 공시가 세 건 이상인 코스닥 기업은 다음 1년 위험 공시율이 "
                 "24.6퍼센트로, 한 건도 없는 기업의 5.7배였습니다. 최대주주 변경까지 겹치면 34.1퍼센트입니다. 2017년부터 2020년, 2021년부터 "
                 "2024년, 두 기간 모두 같은 모양이었습니다.",
       [T("자금조달이 반복될수록 위험이 커진다", 120, 120, 62, "ink", True),
        T("코스닥 · 직전 12개월 자금조달 공시 건수별 다음 12개월 중대 위험 공시율", 120, 215, 28, "muted"),
        Bars((240, 380, 1700, 900), [[4.3, 6.4], [6.9, 14.7], [15.1, 23.9], [24.6, 34.1]], ["0건", "1건", "2건", "3건 이상"],
             ["acc", "warn"], at=0.2, stagger=0.04, vmax=40, fmt="{:.1f}%",
             legend=[("자금조달만", "acc"), ("+ 최대주주 변경 동반", "warn")], lsize=36, vsize=32),
        T("0건 대비 5.7배 / 7.9배", 1700, 320, 40, "warn", True, 0.6, "ra")])

    sc("06  결합 검증", "이제 두 프로젝트를 합친 결과입니다. 재무만 보는 전통 모델은 매출 하위 20퍼센트 기업에 26.4퍼센트의 오경보를 냈습니다. "
                      "대형사는 2.5퍼센트로, 열 배 차이입니다. 신용캐드의 핵심 가설이 실제 데이터로 처음 확인된 순간입니다. 여기에 딘텔의 공시 "
                      "연쇄를 더하자 소형사 오경보는 18.5퍼센트로 줄었고, 예측력은 오히려 0.663에서 0.669로 올랐습니다. 더 정확하면서 "
                      "덜 불공정해진 것입니다.",
       [T("재무만 보면 작은 회사를 과하게 의심한다", 120, 120, 60, "ink", True),
        T("코스닥 상장사 실험장 · 위험 공시가 없었는데 경고한 비율(오경보) · 검증 2024-01~2025-09", 120, 210, 28, "muted"),
        Bars((150, 370, 1130, 880), [[26.4, 2.5], [25.5, 2.2], [18.5, 3.6]], ["① 전통(재무)", "② 공정(업종 보정)", "③ 공정+공시 연쇄"],
             ["warn", "slate"], at=0.12, stagger=0.05, vmax=32, fmt="{:.1f}%",
             legend=[("매출 하위 20%", "warn"), ("매출 상위 20%", "slate")], lsize=28, vsize=30),
        T("결합 모델 ③", 1230, 380, 44, "ink", True, 0.55),
        T("소형사 오경보 26.4% → 18.5%", 1230, 470, 36, "ok", False, 0.6),
        T("예측력(AUC) 0.663 → 0.669", 1230, 540, 36, "acc", False, 0.68),
        T("점수의 규모 의존도 -0.39 → -0.23", 1230, 610, 36, "vio", False, 0.74),
        T("더 정확하면서\n덜 불공정하다", 1230, 720, 54, "ok", True, 0.86)])

    sc("06  결합 검증", "결합 모델이 전통 모델의 경고를 풀어 준 489건의 실제 위험률은 12.3퍼센트로, 계속 경고한 쪽의 18.2퍼센트보다 낮았습니다. "
                      "풀어 준 기업의 61퍼센트는 소형사였습니다. 반대로 재무로는 보이지 않던 631건을 새로 경고했고, 이들의 실제 위험률은 "
                      "14.1퍼센트로 평균의 두 배였습니다.",
       [T("덜 위험한 회사는 풀어 주고, 숨은 위험은 잡았다", 120, 120, 58, "ink", True),
        T("전통 모델과 결합 모델의 판단이 달랐던 기업-월의 실제 12개월 위험률 · 코스닥 2024~25 표본외", 120, 210, 28, "muted"),
        Bars((200, 360, 1720, 880), [18.2, 12.3, 14.1, 7.2],
             ["전통 경고 유지\n1,618건", "결합 모델이 해제\n489건 (61% 소형사)", "결합 모델이 새로 경고\n631건", "전체 평균"],
             ["warn", "ok", "vio", "slate"], at=0.15, stagger=0.12, vmax=22, fmt="{:.1f}%", lsize=28, vsize=44)])

    sc("07  소상공인 진단", "소상공인 진단 화면에서는 같은 재무정보를 두 번 평가합니다. 은행식 전통 점수와, 매출에 섞인 규모와 경기의 영향을 "
                        "걷어 낸 공정 점수입니다. 재무가 안정된 헬스장 시연에서는 79.4점 에이 등급이 84.4점 더블에이 등급으로 바뀌고, 예시 "
                        "금리로 1억 원 대출의 연 이자가 50만 원 줄어듭니다. 이 모델은 아직 합성 데이터로 만든 시제품이라, 다음 단계에서 실제 "
                        "상환 결과로 검증합니다.",
       [T("같은 재무, 다른 평가", 120, 120, 62, "ink", True),
        T("신용캐드 공정신용 진단 · 시연 A 헬스장(성신여대입구역) · 재무안정형", 120, 215, 28, "muted"),
        Bars((200, 360, 1100, 860), [A["traditional"]["score"], A["fair"]["score"], A["context"]["score"]],
             [f"전통 ({A['traditional']['grade']})", f"공정 ({A['fair']['grade']})", f"상권 반영 ({A['context']['grade']})"],
             ["slate", "acc", "vio"], at=0.15, stagger=0.12, vmax=100, fmt="{:.1f}", lsize=32, vsize=46),
        T(f"예시 금리 {A['traditional']['rate_pct']:.1f}% → {A['fair']['rate_pct']:.1f}%", 1220, 420, 40, "ink", False, 0.5),
        Num(A["interest_saving_won"] / 1e4, lambda v: f"{v:,.0f}만 원", 1500, 600, 110, "ok", 0.55, anchor="mm",
            label="1억 원 대출 연 이자 절감"),
        T("핵심 모델은 합성 데이터 MVP\n등급 컷·금리는 예시 가정", 1220, 800, 28, "warn", False, 0.85),
        T("상권 수익성은 서울시 상권 실측 매출 연동", 1220, 890, 28, "muted", False, 0.88)],
       tts=None)

    # 10-20 신용캐드 실데이터(caed/industry_survival.py, franchise_survival.py) - 숫자는 결과 파일에서 읽는다
    ind = json.load(open(os.path.join(ROOT, "data", "caed", "industry_survival.json"), encoding="utf-8"))["industries"]
    n_all = sum(r["n_firms"] for r in ind.values())
    rest = ind["072404"]
    sc("07  실데이터", f"그래서 실제 결과로 채점했습니다. 서울시 인허가에 남은 소상공인 {n_all // 10000}만 곳의 실제 폐업입니다. 대부분 업종에서 "
                     f"젊고 작은 가게가 실제로 더 많이 닫았습니다. 음식점은 문을 연 지 1년이 안 된 곳의 다음 해 폐업률이 "
                     f"{rest['age']['<1년'] * 100:.1f}퍼센트, 10년 넘은 곳은 {rest['age']['10년+'] * 100:.1f}퍼센트였습니다. 그리고 공개 데이터만으로 "
                     "가게 하나의 폐업을 가려내는 힘은 약했습니다. 미리 적어 둔 가설 대부분이 기각됐고, 우리는 그대로 공개합니다.",
       [T("서울 소상공인의 실제 폐업으로 채점했다", 120, 120, 58, "ink", True),
        T(f"서울 열린데이터광장 지방행정 인허가 10개 업종 · {n_all:,}곳 · 다음 1년 폐업률(2021~24)", 120, 215, 28, "muted"),
        Bars((200, 360, 1150, 860), [[ind[c]["age"]["<1년"] * 100, ind[c]["age"]["10년+"] * 100] for c in ("072404", "072405", "051801", "062001")],
             ["일반음식점", "카페·휴게", "미용실", "세탁소"], ["warn", "slate"], at=0.12, stagger=0.05, fmt="{:.1f}",
             legend=[("업력 1년 미만", "warn"), ("10년 이상", "slate")], lsize=30, vsize=30),
        T("가설은 결과를 보기 전에 커밋", 1300, 420, 34, "ink", True, 0.45),
        T("업력·규모 가설 3개 기각\n상권·동네 매출 신호도 약함\n예측력 AUC 0.56~0.62", 1300, 520, 32, "ink", False, 0.5),
        T("→ 공개 데이터만으로는 부족하다", 1300, 760, 36, "warn", True, 0.7)], key="realdata")
    cf = json.load(open(os.path.join(ROOT, "data", "caed", "franchise_survival.json"), encoding="utf-8"))
    rf = json.load(open(os.path.join(ROOT, "data", "caed", "franchise_survival_072404.json"), encoding="utf-8"))
    cm, rm = cf["momentum"]["result"]["검증 2021~24"], rf["momentum"]["result"]["검증 2021~24"]
    sc("07  브랜드 건강도", f"그런데 한 가지 강한 신호가 있었습니다. 어느 브랜드의 가맹점인가입니다. 직전 1년 동안 서울 매장이 줄어든 브랜드의 "
                       f"카페 가맹점은 다음 해 {cm['low'] * 100:.1f}퍼센트가 문을 닫았고, 매장이 늘어난 브랜드는 {cm['high'] * 100:.1f}퍼센트였습니다. "
                       f"음식점에서도 같은 모양이 다시 나왔습니다. 은행은 이미 가맹점주 대출에서 브랜드의 안정성을 심사합니다. 가맹본부가 1년 늦게 "
                       "스스로 내는 통계 대신, 공공 기록으로 매달 갱신하는 브랜드 건강도를 만듭니다.",
       [T("가맹점의 위험은 브랜드가 가른다", 120, 120, 58, "ink", True),
        T("브랜드 순증가율(직전 12개월 서울 개업-폐업) 3분위별 가맹점의 다음 1년 폐업률 · 카페로 사전 등록, 음식점으로 재현", 120, 215, 26, "muted"),
        Bars((200, 360, 1150, 860), [[cm["low"] * 100, cm["high"] * 100], [rm["low"] * 100, rm["high"] * 100]],
             ["카페", "일반음식점"], ["warn", "ok"], at=0.12, stagger=0.08, fmt="{:.1f}", legend=[("쇠퇴 브랜드", "warn"), ("성장 브랜드", "ok")],
             lsize=34, vsize=40),
        Num(cm["low"] / cm["high"], lambda v: f"{v:.1f}배", 1500, 470, 120, "warn", 0.45, anchor="mm", label="카페 쇠퇴 / 성장"),
        T(f"프랜차이즈 {cf['franchise_rate'] * 100:.1f}% vs 독립 {cf['independent_rate'] * 100:.1f}% (카페 1년 폐업)", 1500, 680, 30, "ink", False, 0.6, "mm"),
        T("브랜드 473개 등급을 해시로 봉인 → 2027-10 채점", 1500, 760, 28, "muted", False, 0.75, "mm"),
        T("고객: 은행 프랜차이즈론 심사 · 보증재단 · 예비 창업자", 1500, 840, 28, "acc", True, 0.85, "mm")], key="brand")

    sc("08  성적표", "우리는 숫자를 고치지 않겠다는 약속을 구조로 만듭니다. 매달 경고 목록을 해시로 고정해 먼저 공개하고, 12개월 뒤 실제 결과로 "
                   "자동 채점합니다. 2026년 10월 첫 발행에서 코스닥 144곳, 코스피 73곳을 경고했습니다. 후발 주자는 지나간 성적표를 소급해서 "
                   "만들 수 없습니다.",
       [T("먼저 고정하고, 나중에 채점한다", 120, 120, 62, "ink", True),
        T("공개 성적표 · scoreboard/ledger.csv (git 기록)", 120, 215, 28, "muted"),
        Box(120, 290, 760, 230, "2026-10 경고 목록 고정", "SHA-256 해시로 봉인 → 공개", "acc", 0.12),
        Arrow(900, 405, 1020, 405, 0.3, "gold"),
        T("12개월", 960, 360, 32, "gold", True, 0.3, "mm"),
        Box(1040, 290, 760, 230, "2027-10 자동 채점", "실제 위험 공시 발생 여부로 적중률 계산", "ok", 0.32),
        Type("kosdaq  " + kq_led["warn_sha256"], 120, 590, 30, "acc", 0.35, cps=60),
        Type("kospi   " + ks_led["warn_sha256"], 120, 640, 30, "vio", 0.42, cps=60),
        Num(int(kq_led["n_warn"]), lambda v: f"{v:.0f}곳", 560, 800, 110, "warn", 0.55, label="코스닥 경고 (첫 발행)"),
        Num(int(ks_led["n_warn"]), lambda v: f"{v:.0f}곳", 1360, 800, 110, "warn", 0.6, label="코스피 경고 (첫 발행)")])

    n_live, n_days = _live_disclosures()
    sc("08  실시간 경보", f"공시는 나온 순간이 가장 비쌉니다. 딘텔은 1분마다 전자공시를 확인해, 공시가 처음 보인 시각을 기록합니다. "
                       f"하루 평균 {n_live:,}건 가운데 고객이 지켜보는 기업의 공시가 뜨면, 같은 유형 공시에 시장이 과거 어떻게 반응했는지와 함께 "
                       "즉시 알립니다. 예를 들어 코스피 자기주식 취득 결정은 발표 이틀 동안 평균 3.2퍼센트, 그 뒤 열흘 동안 1.6퍼센트 더 "
                       "움직였습니다. 공시가 몇 분 안에 가격에 반영되는지는 이렇게 쌓은 시각 기록으로 앞으로 검증합니다.",
       [T("공시가 뜬 그 1분", 120, 120, 62, "ink", True),
        T(f"dintel 실시간 공시 포착 · DART 1분 간격 · 수집 {n_days}일째", 120, 215, 28, "muted"),
        Box(120, 290, 520, 300, "포착", "1분마다 전자공시 확인\n처음 보인 시각 기록", "acc", 0.1),
        Arrow(660, 440, 760, 440, 0.25, "gold"),
        Box(780, 290, 520, 300, "판별", "관심 기업인가?\n공시 유형은?", "vio", 0.3),
        Arrow(1320, 440, 1420, 440, 0.45, "gold"),
        Box(1440, 290, 380, 300, "알림", "과거 반응 통계와\n함께 즉시 전달", "ok", 0.5),
        Num(n_live, lambda v: f"{v:,.0f}건", 560, 800, 96, "acc", 0.6, label="하루 평균 공시"),
        T("예: 자기주식 취득 결정(코스피)\n발표 2일 +3.2% · 이후 10일 +1.6%", 1100, 760, 36, "ink", False, 0.7),
        T("분 단위 반응은 수집 중 - 사전 기준으로 검증 예정", 960, 960, 28, "warn", False, 0.85, "mm")])

    sc("09  계획", "첫 고객은 손실이 직접 걸린 곳입니다. 주식담보대출과 메자닌 투자를 심사하는 증권사, 캐피탈, 저축은행입니다. 기관용 리스크 "
                 "데스크는 연 1,200만 원에서 3,000만 원, 운용사 팀 요금은 계정당 연 240만 원입니다. 1년 차 목표 매출은 약 9,400만 원이고, "
                 "리스크 데스크 한 곳이면 고정비를 넘습니다.",
       [T("누가, 얼마를 내나", 120, 120, 62, "ink", True),
        T("가격은 모두 추정 · 파일럿과 성적표로 검증", 120, 215, 28, "muted"),
        Box(120, 290, 540, 360, "Risk Desk", "증권사 신용공여 · 캐피탈 · 저축은행 · 메자닌 펀드\n\n연 1,200만~3,000만 원", "warn", 0.12),
        Box(690, 290, 540, 360, "Team", "중소형 운용사 리서치·리스크\n\n계정당 연 240만 원 (3계정부터)", "acc", 0.3),
        Box(1260, 290, 540, 360, "API · IR", "MTS·금융 AI·신평사 / 상장사 IR\n\nAPI 연 2,400만 원+ · IR 연 360만 원+", "vio", 0.45),
        Num(9400, lambda v: f"약 {v:,.0f}만 원", 960, 800, 96, "gold", 0.65, label="1년 차 목표 매출 (보수적 추정)")])

    sc("09  계획", "앞으로의 계획입니다. 상장폐지된 기업까지 넣어 코스닥과 코스피 운영 모델을 다시 학습하는 일은 10월에 마쳤습니다. "
                 "11월부터는 기관 두 곳과 3개월 무상 파일럿을 하고, 상장사 경고는 공개 성적표로, 소상공인 리포트는 실제 상환 결과를 모아 "
                 "검증합니다. 경고 목록은 시작일에 먼저 봉인해 건네고, 3개월과 12개월 뒤에 함께 엽니다. 시세 화면은 상용 라이선스를 받은 뒤에 쓰고, "
                 "그 전에는 공시 기반 기능만 제공합니다. 결과를 보고 떠올린 가설은 미리 등록해 두고, 앞으로의 데이터로만 판정합니다.",
       [T("앞으로의 계획", 120, 120, 62, "ink", True),
        Box(120, 280, 400, 330, "10월", "운영 모델 재학습 완료\n(퇴출 기업 포함)\n탐색 가설 사전 등록", "warn", 0.1),
        Box(560, 280, 400, 330, "10/26", "영상 2편 · 보고서\n데모 사이트 공개", "acc", 0.3),
        Box(1000, 280, 400, 330, "11월~", "기관 2곳 · 무상 3개월\n경고 먼저 봉인\n→ 3·12개월 뒤 채점\n지불 의사 설문", "vio", 0.45),
        Box(1440, 280, 380, 330, "2027 상반기", "첫 유료 계약\n예비창업패키지 검토", "ok", 0.6),
        T("시세 화면은 상용 라이선스 후 · 그 전엔 공시(DART) 기능만", 960, 690, 30, "muted", False, 0.5, "mm"),
        T("남은 한계도 숨기지 않는다: 퇴출 기업 상장 기간은 근사 · 코스피 신호는 약함(AUC 0.64) ·소상공인 점수는 합성 데이터", 960, 760, 34, "gold",
          True, 0.2, "mm")])

    sc("10  절차", "우리가 지킨 절차는 단순합니다. 학습 기간과 검증 기간을 나누고, 그 시점에 공개된 정보만 쓰고, 같은 잣대로 비교하고, "
                 "결과를 먼저 고정한 뒤 채점합니다. 맞은 가설은 남기고, 효과 없는 것은 버렸습니다. 업종 충격만 보정하는 방식이 그랬습니다.",
       [T("어떻게 검증하며 만들었나", 120, 120, 62, "ink", True),
        Box(120, 280, 400, 300, "1. 기간 분리", "2020년까지 학습\n2022년부터 검증", "acc", 0.08),
        Box(560, 280, 400, 300, "2. 시점 고정", "그날 공개돼 있던\n정보만 사용(PIT)", "acc", 0.25),
        Box(1000, 280, 400, 300, "3. 같은 잣대", "가격만 / 공시만 / 결합\n같은 행·같은 정답", "acc", 0.42),
        Box(1440, 280, 380, 300, "4. 먼저 고정", "해시 봉인 후\n12개월 뒤 채점", "acc", 0.58),
        T("남긴 것: 규모 편향 · 공시 연쇄     버린 것: 업종 충격만 보정 (AUC 0.663 → 0.662, 효과 없음)", 960, 720, 34, "ink",
          False, 0.8, "mm")])

    sc("", "점수가 낮은 이유와, 위험해지는 이유. 딘텔, 그리고 신용캐드였습니다.",
       [T("점수가 낮은 이유와,", 960, 400, 70, "ink", True, 0.0, "mm"),
        T("위험해지는 이유를", 960, 500, 70, "acc", True, 0.15, "mm"),
        T("검증된 숫자로", 960, 600, 70, "gold", True, 0.3, "mm"),
        T("dintel × 신용캐드", 960, 800, 48, "muted", False, 0.5, "mm")])
    return S


# ---------------------------------------------------------------- 렌더링
def background():
    g = Image.new("RGBA", (W, H))
    px = g.load()
    for y in range(H):
        k = y / H
        c = tuple(int(C["bg1"][i] * (1 - k) + C["bg2"][i] * k) for i in range(3)) + (255,)
        for x in range(W):
            px[x, y] = c
    return g


FOOTER = "dintel × 신용캐드"   # 1분 판(render_motion_1min)이 바꾼다


def chrome(img, sec, prog):
    if sec:
        text(img, (120, 60), sec, 26, "acc", True)
    text(img, (1800, 1040), FOOTER, 22, "muted", False, 1.0, "rm")
    d = ImageDraw.Draw(img)
    d.rectangle((0, H - 6, int(W * prog), H), fill=C["acc"] + (255,))


def frame(bg, sc, t, L, prog):
    img = bg.copy()
    for el in sc["els"]:
        el.draw(img, t, L)
    chrome(img, sc["sec"], prog)
    # 장면 경계 페이드(0.35초)
    k = min(1.0, t / 0.35, (L - t) / 0.35)
    if k < 1.0:
        img = Image.blend(bg, img, max(0.0, k))
    return img


TTS_FIX = [("CapCred", "캡크레드"), ("dintel", "딘텔"), ("AUC", "에이유씨"), ("API", "에이피아이"), ("MVP", "엠브이피"), ("SHA-256", "해시")]


def tts_text(s):
    for a, b in TTS_FIX:
        s = s.replace(a, b)
    return s


def synth(S, rate=1):
    """Windows Heami로 장면별 wav. 반환: 길이(초) 목록."""
    os.makedirs(os.path.join(OUT, "tts"), exist_ok=True)
    jobs = [{"text": tts_text(sc["tts"] or sc["narr"]), "path": os.path.join(OUT, "tts", f"s{i:02d}.wav")}
            for i, sc in enumerate(S)]
    jp = os.path.join(OUT, "tts", "jobs.json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(jobs, fh, ensure_ascii=False)
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        f"$jobs = Get-Content -Raw -Encoding UTF8 '{jp}' | ConvertFrom-Json; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.SelectVoice('Microsoft Heami Desktop'); "
        f"$s.Rate = {rate}; "
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); "
        "foreach ($j in $jobs) { $s.SetOutputToWaveFile($j.path, $fmt); $s.Speak($j.text); $s.SetOutputToNull() }")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    out = []
    for j in jobs:
        with wave.open(j["path"]) as w:
            out.append(w.getnframes() / w.getframerate())
    return out


def build_audio(S, durs, pads):
    """장면 wav + 여백 무음을 이어 붙인 내레이션 트랙. 반환: 장면 길이(초)."""
    lens = []
    path = os.path.join(OUT, "narration.wav")
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(24000)
        for i, (d, (lead, tail)) in enumerate(zip(durs, pads)):
            with wave.open(os.path.join(OUT, "tts", f"s{i:02d}.wav")) as w:
                data = w.readframes(w.getnframes())
            L = lead + d + tail
            n_total = int(round(L * FPS)) / FPS          # 프레임 단위로 맞춤(영상·음성 누적 어긋남 방지)
            out.writeframes(b"\x00\x00" * int(lead * 24000) + data)
            rest = int(n_total * 24000) - int(lead * 24000) - len(data) // 2
            out.writeframes(b"\x00\x00" * max(rest, 0))
            lens.append(n_total)
    return lens


def srt(S, lens, pads, durs):
    import re
    lines, t0, k = [], 0.0, 1
    fmt = lambda s: f"{int(s // 3600):02d}:{int(s % 3600 // 60):02d}:{int(s % 60):02d},{int(s * 1000 % 1000):03d}"
    for sc, L, (lead, _), d in zip(S, lens, pads, durs):
        sents = [x.strip() for x in re.split(r"(?<=[.?!])\s+", sc["narr"]) if x.strip()]
        tot = sum(len(x) for x in sents)
        cur = t0 + lead
        for s in sents:
            dd = d * len(s) / tot
            lines += [str(k), f"{fmt(cur)} --> {fmt(cur + dd)}", s, ""]
            k += 1
            cur += dd
        t0 += L
    with open(os.path.join(OUT, "motion_draft.srt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def script_doc(S, lens=None):
    p = os.path.join(ROOT, "deliverables", "VIDEO_MOTION_SCRIPT.md")
    t0 = 0.0
    rows = ["# 모션그래픽 영상 대본·콘티 (자동 생성 - scripts/render_motion_video.py와 같은 장면 정의)", "",
            "- 초안 영상: `deliverables/video/motion_draft.mp4` (1920x1080, 24fps, 내레이션 = Windows 한국어 음성 Heami, 자막 .srt)",
            "- 최종본 제작 안내: 내레이션을 본인 목소리나 고품질 TTS로 다시 녹음하고, 아래 장면 순서·화면 문구를 그대로 쓰면 된다. "
            "장면 길이는 내레이션 길이에 맞춰 자동으로 바뀐다(`TTS 교체 → 다시 렌더`). 배경음악은 저작권 문제없는 음원으로 편집 단계에서 추가.",
            "- 구성: 사업계획서(DINTEL_BUSINESS_PLAN.md) 순서 그대로 - 이유 → 현장 → 결합 → 제품 → 근거 → 결합 검증 → 소상공인 진단 → 성적표 → "
            "계획 → 절차.", "- 숫자 출처: data/dintel/risk_model_*.json, FAIR_WARNING_SUMMARY.txt, DINTEL_DIFFERENTIATION.md, "
            "scoreboard/ledger.csv, caed/service.py 시연값(합성 데이터 MVP).", ""]
    rows += ["| # | 시간 | 구간 | 화면 | 내레이션 |", "|---|---|---|---|---|"]
    for i, sc in enumerate(S):
        L = lens[i] if lens else None
        when = f"{int(t0 // 60)}:{int(t0 % 60):02d}" if lens else "-"
        vis = " / ".join(getattr(e, "s", None) or getattr(e, "title", "") or type(e).__name__ for e in sc["els"]
                         if not isinstance(e, (Arrow,)))[:300]
        rows.append(f"| {i + 1} | {when} | {sc['sec'] or '타이틀'} | {vis} | {sc['narr']} |")
        if L:
            t0 += L
    if lens:
        rows += ["", f"총 길이: {int(t0 // 60)}분 {int(t0 % 60)}초"]
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    print("script ->", p)


SHORT = ("점수가 낮은 이유와 위험해지는 이유를", "첫 번째 이유. 위험은 가격보다", "근거를 보겠습니다", "혹시 살아남은 회사만",
         "이제 두 프로젝트를 합친 결과", "우리는 숫자를 고치지 않겠다는", "앞으로의 계획입니다", "점수가 낮은 이유와, 위험해지는 이유")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills", action="store_true")
    ap.add_argument("--script", action="store_true")
    ap.add_argument("--rate", type=int, default=1, help="Heami 말 빠르기(-10~10)")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    S = scenes()
    # 10-20 과제 분량 1분+로 변경 -> 3~4분 압축본: MOTION_CUT=short (장면은 내레이션 앞부분으로 고른다)
    if os.environ.get("MOTION_CUT") == "short":
        S = [sc for sc in S if sc.get("key") in ("realdata", "brand") or any(sc["narr"].startswith(p) for p in SHORT)]
    bg = background()
    if a.script:
        script_doc(S)
        return
    if a.stills:
        sd = os.path.join(OUT, "stills")
        os.makedirs(sd, exist_ok=True)
        for i, sc in enumerate(S):
            L = 20.0
            frame(bg, sc, L * 0.97, L, (i + 1) / len(S)).convert("RGB").save(os.path.join(sd, f"s{i:02d}.png"))
        print("stills ->", sd)
        return
    durs = synth(S, a.rate)
    pads = [(0.6, 1.0)] * len(S)
    pads[0] = (1.0, 1.4)
    pads[-1] = (0.6, 2.4)
    lens = build_audio(S, durs, pads)
    srt(S, lens, pads, durs)
    script_doc(S, lens)
    total = sum(lens)
    print(f"scenes {len(S)}, total {total / 60:.1f} min -> rendering frames", flush=True)
    mp4 = os.path.join(OUT, "motion_draft.mp4")
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                           "-r", str(FPS), "-i", "-", "-i", os.path.join(OUT, "narration.wav"), "-c:v", "libx264",
                           "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                           "-shortest", mp4], stdin=subprocess.PIPE)
    done = 0.0
    for i, (sc, L) in enumerate(zip(S, lens)):
        n = int(round(L * FPS))
        lead = pads[i][0]
        for f in range(n):
            t = f / FPS
            # 등장 시점(at)은 내레이션 구간 기준: lead 이후부터 내레이션 길이(durs)에 비례
            img = frame(bg, sc, t, L, (done + t) / total)
            ff.stdin.write(img.convert("RGB").tobytes())
        done += L
        print(f"  scene {i + 1}/{len(S)} done ({done / 60:.1f} min)", flush=True)
    ff.stdin.close()
    ff.wait()
    print("video ->", mp4)


if __name__ == "__main__":
    main()

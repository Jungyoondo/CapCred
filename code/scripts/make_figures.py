"""제출물(PDF·모션그래픽 영상)용 그림 - 모두 저장소의 실측 결과 파일에서 그린다 (2026-10-09).

python -X utf8 scripts/make_figures.py        -> deliverables/figures/fig*.png (1920x1080 16:9, 영상 프레임 겸용)

출처(그림마다 우하단에 표기):
  fig01, fig02, fig09  data/dintel/risk_model_<market>.json (dintel/risk_score.py)
  fig03                DINTEL_DIFFERENTIATION.md 자금조달 연쇄 표 (dintel/financing.py)
  fig04, fig05         data/dintel/FAIR_WARNING_SUMMARY.txt 마지막 kosdaq 블록 (dintel/fair_warning.py)
  fig06                DINTEL_BUSINESS_PLAN.md 4-3 (data/dintel/EVENT_SUMMARY_I.txt, CONTRACT_SUMMARY.txt)
  fig07                caed.service.diagnose 시연 A/B (docs/site_api_samples/biz_caed_demoAB.json)
  fig08                data/delinq_panel.csv (한국은행 산업별 연체율, 차주수 기준)
  fig12~14             data/caed/industry_survival.json, franchise_survival*.json (10-20 서울 인허가 실데이터)
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib import font_manager as fm  # noqa: E402

OUT = os.path.join(ROOT, "deliverables", "figures")
os.makedirs(OUT, exist_ok=True)

for f in ("malgun.ttf", "malgunbd.ttf"):
    p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", f)
    if os.path.exists(p):
        fm.fontManager.addfont(p)
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 20,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.titleweight": "bold",
                     "axes.titlesize": 30, "axes.titlepad": 24, "axes.labelsize": 20, "figure.dpi": 100})

INK, MUTED, GRID = "#1f2937", "#6b7280", "#e5e7eb"
ACCENT, ACCENT2, WARN, OK = "#2563eb", "#7c3aed", "#dc2626", "#059669"
BG = "#ffffff"


def fig(title, sub=None):
    f = plt.figure(figsize=(19.2, 10.8), facecolor=BG)
    f.text(0.06, 0.93, title, fontsize=34, fontweight="bold", color=INK, va="top")
    if sub:
        f.text(0.06, 0.865, sub, fontsize=19, color=MUTED, va="top")
    return f


def axes(f, rect=(0.08, 0.13, 0.86, 0.66)):
    ax = f.add_axes(rect)
    ax.set_facecolor(BG)
    ax.grid(axis="y", color=GRID, lw=1.2)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK, labelsize=19)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#9ca3af")
    return ax


def save(f, name, src, foot="dintel × 신용캐드 | 모든 수치는 시점 고정·표본외 실측"):
    f.text(0.94, 0.03, f"출처: {src}", fontsize=13, color=MUTED, ha="right")
    f.text(0.06, 0.03, foot, fontsize=13, color=MUTED)
    p = os.path.join(OUT, name)
    f.savefig(p, facecolor=BG)
    plt.close(f)
    print("saved", p)


def risk(m):
    with open(os.path.join(ROOT, "data", "dintel", f"risk_model_{m}.json"), encoding="utf-8") as fh:
        return json.load(fh)["validation"]


def fair_block():
    s = open(os.path.join(ROOT, "data", "dintel", "FAIR_WARNING_SUMMARY.txt"), encoding="utf-8").read()
    blk = [b for b in s.split("#####") if "(kosdaq)" in b and "저평가 발굴" in b][-1]
    rows = {}
    for tag in ("T", "F", "F+D", "D"):
        m = re.search(rf"\n\s+{re.escape(tag)} \S.*?AUC ([\d.]+) \| 상위10% 위험률 ([\d.]+)% \| 규모 의존도 rho ([-+\d.]+) \| "
                      rf"오경보율 소형 ([\d.]+)% / 대형 ([\d.]+)%", blk)
        rows[tag] = tuple(float(x) for x in m.groups())
    rel = re.search(r"해제 ([\d,]+)건 -> 실제 위험률 ([\d.]+)% vs 유지 ([\d,]+)건 ([\d.]+)% \(전체 ([\d.]+)%\)", blk)
    hid = re.search(r"상위 30% 밖이던 ([\d,]+)건 -> 실제 위험률 ([\d.]+)%", blk)
    return rows, rel.groups(), hid.groups()


def bar_labels(ax, bars, fmt, color=INK, dy=0.0, size=22):
    for b in bars:
        h = b.get_height()
        ax.text(b.get_x() + b.get_width() / 2, h + dy, fmt(h), ha="center", va="bottom", fontsize=size,
                fontweight="bold", color=color)


# ---- fig01 가격 vs 공시 AUC
def fig01():
    kq, ks = risk("kosdaq"), risk("kospi")
    f = fig("위험은 가격보다 공시에 먼저 나타난다",
            "다음 12개월 중대 위험 공시 예측력(AUC, 0.5 = 동전 던지기) | 학습 ~2020, 검증 2022~2025 표본외")
    ax = axes(f)
    labels = ["코스닥\n가격 정보만", "코스닥\n공시 정보", "코스피\n가격 정보만", "코스피\n가격+공시"]
    vals = [kq["auc_price_only"], kq["auc"], ks["auc_price_only"], ks["auc"]]
    cols = ["#cbd5e1", ACCENT, "#cbd5e1", ACCENT2]
    b = ax.bar(labels, vals, color=cols, width=0.55)
    ax.axhline(0.5, color=WARN, ls="--", lw=2)
    ax.text(3.45, 0.505, "무작위 0.50", color=WARN, fontsize=18, ha="right")
    ax.set_ylim(0.45, 0.72)
    bar_labels(ax, b, lambda v: f"{v:.2f}", dy=0.004, size=26)
    save(f, "fig01_price_vs_disclosure_auc.png", "data/dintel/risk_model_*.json (dintel/risk_score.py)")


# ---- fig02 코스닥 위험 10분위
def fig02():
    v = risk("kosdaq")
    d = np.array(v["deciles"]) * 100
    f = fig("경고 상위 10%에 위험이 몰린다 (코스닥)",
            f"점수 10분위별 실제 12개월 위험 공시율 | 검증 {v['n_test']:,} 기업-월 | 평균 {v['base_rate']:.1%}")
    ax = axes(f)
    cols = ["#cbd5e1"] * 9 + [WARN]
    b = ax.bar([str(i) for i in range(1, 11)], d, color=cols, width=0.65)
    ax.axhline(v["base_rate"] * 100, color=MUTED, ls="--", lw=2)
    ax.text(0.0, v["base_rate"] * 100 + 0.4, f"평균 {v['base_rate']:.1%}", color=MUTED, fontsize=18)
    bar_labels(ax, b, lambda x: f"{x:.1f}%", dy=0.3, size=19)
    ax.set_xlabel("위험 점수 10분위 (10 = 가장 위험)")
    ax.set_ylabel("실제 위험 공시율 (%)")
    ax.set_ylim(0, 23)
    ax.annotate(f"평균의 {v['top10_rate'] / v['base_rate']:.1f}배\n전체 위험의 {v['capture_top10']:.0%} 포착",
                xy=(9, d[9]), xytext=(6.2, 17), fontsize=22, color=WARN, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=WARN, lw=2))
    save(f, "fig02_risk_deciles_kosdaq.png", "data/dintel/risk_model_kosdaq.json")


# ---- fig03 자금조달 연쇄
def fig03():
    base = [4.3, 6.9, 15.1, 24.6]
    own = [6.4, 14.7, 23.9, 34.1]
    f = fig("자금조달이 반복될수록 위험이 커진다 (코스닥)",
            "직전 12개월 자금조달 공시 건수별 다음 12개월 중대 위험 공시율 | 2017~20, 2021~24 두 기간 모두 같은 모양")
    ax = axes(f)
    x = np.arange(4)
    b1 = ax.bar(x - 0.2, base, 0.38, color=ACCENT, label="자금조달만")
    b2 = ax.bar(x + 0.2, own, 0.38, color=WARN, label="+ 최대주주 변경 동반")
    ax.set_xticks(x, ["0건", "1건", "2건", "3건 이상"])
    bar_labels(ax, b1, lambda v: f"{v:.1f}%", dy=0.4, size=20)
    bar_labels(ax, b2, lambda v: f"{v:.1f}%", dy=0.4, size=20)
    ax.set_ylim(0, 40)
    ax.set_ylabel("다음 12개월 위험 공시율 (%)")
    ax.legend(frameon=False, fontsize=20, loc="upper left")
    ax.text(3.2, 37, "0건 대비 7.9배", color=WARN, fontsize=22, fontweight="bold", ha="center")
    save(f, "fig03_financing_chain.png", "DINTEL_DIFFERENTIATION.md (dintel/financing.py)")


# ---- fig04 공정성: 소형사 오경보
def fig04():
    rows, _, _ = fair_block()
    f = fig("재무만 보면 작은 회사를 과하게 의심한다",
            "코스닥 상장사 실험장 | 실제로 위험 공시가 없었는데 경고한 비율(오경보) | 검증 2024-01~2025-09")
    ax = axes(f, (0.08, 0.13, 0.55, 0.66))
    names = {"T": "① 전통\n(재무만)", "F": "② 공정\n(업종 보정)", "F+D": "③ 공정 +\n공시 연쇄"}
    x = np.arange(3)
    small = [rows[k][3] for k in names]
    large = [rows[k][4] for k in names]
    b1 = ax.bar(x - 0.2, small, 0.38, color=WARN, label="매출 하위 20% (소형)")
    b2 = ax.bar(x + 0.2, large, 0.38, color="#94a3b8", label="매출 상위 20% (대형)")
    ax.set_xticks(x, list(names.values()))
    bar_labels(ax, b1, lambda v: f"{v:.1f}%", dy=0.4, size=21)
    bar_labels(ax, b2, lambda v: f"{v:.1f}%", dy=0.4, size=21)
    ax.set_ylim(0, 32)
    ax.set_ylabel("오경보율 (%)")
    ax.legend(frameon=False, fontsize=18, loc="upper right")
    t, d = rows["T"], rows["F+D"]
    f.text(0.68, 0.72, "결합 모델(③)", fontsize=26, fontweight="bold", color=INK)
    lines = [(f"소형사 오경보  {t[3]:.1f}% → {d[3]:.1f}%", OK),
             (f"예측력(AUC)  {t[0]:.3f} → {d[0]:.3f}", ACCENT),
             (f"점수의 규모 의존도  {t[2]:+.2f} → {d[2]:+.2f}", ACCENT2),
             (f"상위 10% 위험률  {t[1]:.1f}% → {d[1]:.1f}%", INK)]
    for i, (s, c) in enumerate(lines):
        f.text(0.68, 0.63 - i * 0.085, s, fontsize=22, color=c)
    f.text(0.68, 0.24, "더 정확하면서 덜 불공정하다", fontsize=24, fontweight="bold", color=OK)
    save(f, "fig04_fair_false_alarm.png", "data/dintel/FAIR_WARNING_SUMMARY.txt (dintel/fair_warning.py)")


# ---- fig05 재평가: 풀어 준 기업 vs 새로 잡은 기업
def fig05():
    _, rel, hid = fair_block()
    n_rel, r_rel, n_keep, r_keep, base = rel
    n_hid, r_hid = hid
    f = fig("다시 보니: 덜 위험한 회사를 풀어 주고, 숨은 위험을 잡았다",
            "전통 모델 경고와 결합 모델 판단이 달랐던 기업들의 실제 12개월 위험률 (코스닥, 2024~25 표본외)")
    ax = axes(f)
    labels = [f"전통 경고 유지\n{n_keep}건", f"결합 모델이 해제\n{n_rel}건 (61% 소형사)", f"결합 모델이 새로 경고\n{n_hid}건", "전체 평균"]
    vals = [float(r_keep), float(r_rel), float(r_hid), float(base)]
    cols = [WARN, OK, ACCENT2, "#94a3b8"]
    b = ax.bar(labels, vals, color=cols, width=0.55)
    bar_labels(ax, b, lambda v: f"{v:.1f}%", dy=0.3, size=26)
    ax.set_ylim(0, 22)
    ax.set_ylabel("실제 위험 공시율 (%)")
    save(f, "fig05_reassessment.png", "data/dintel/FAIR_WARNING_SUMMARY.txt")


# ---- fig06 공시 반응
def fig06():
    ev = [("권리락", -7.9), ("거래정지 해제", -5.2), ("조회공시 요구 이후", -4.8), ("최대주주 변경", -3.7),
          ("대형 공급계약(매출 50%+) 20일", -2.9), ("전환청구", -2.8), ("대형 공급계약 발표 당일", +3.3)]
    f = fig("공시 뒤 주가는 이렇게 움직였다 (코스닥)",
            "공시 후 20일 초과수익(같은 날 무작위 기업으로 만든 위약 차감) | 학습 기간 규칙을 검증 기간에 그대로 적용")
    ax = axes(f, (0.30, 0.12, 0.62, 0.68))
    ax.grid(axis="x", color=GRID, lw=1.2)
    ax.grid(axis="y", visible=False)
    names = [e[0] for e in ev][::-1]
    vals = [e[1] for e in ev][::-1]
    b = ax.barh(names, vals, color=[OK if v > 0 else WARN for v in vals], height=0.6)
    ax.axvline(0, color=INK, lw=1.5)
    for bar, v in zip(b, vals):
        ax.text(v + (0.15 if v > 0 else -0.15), bar.get_y() + bar.get_height() / 2, f"{v:+.1f}%",
                va="center", ha="left" if v > 0 else "right", fontsize=21, fontweight="bold")
    ax.set_xlim(-9.5, 5)
    ax.set_xlabel("초과수익 (%)")
    save(f, "fig06_event_reactions.png", "DINTEL_BUSINESS_PLAN.md 4-3 (data/dintel/EVENT_SUMMARY_I.txt)")


# ---- fig07 신용캐드 시연
def fig07():
    with open(os.path.join(ROOT, "docs", "site_api_samples", "biz_caed_demoAB.json"), encoding="utf-8") as fh:
        D = json.load(fh)
    f = fig("같은 재무, 다른 평가: 소상공인 공정신용 진단",
            "헬스장(성신여대입구역) 시연 | 전통 = 은행식, 공정 = 규모·경기 영향을 도구변수로 걷어 낸 점수, 상권 반영 = 공정 70% + 상권 30%")
    for i, (k, nm) in enumerate((("A", "시연 A · 재무안정형"), ("B", "시연 B · 성장현금형"))):
        r = D[k]
        ax = axes(f, (0.08 + i * 0.46, 0.16, 0.38, 0.6))
        vals = [r["traditional"]["score"], r["fair"]["score"], r["context"]["score"]]
        grades = [r["traditional"]["grade"], r["fair"]["grade"], r["context"]["grade"]]
        b = ax.bar(["전통", "공정", "상권 반영"], vals, color=["#94a3b8", ACCENT, ACCENT2], width=0.6)
        for bar, v, g in zip(b, vals, grades):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 1, f"{v:.1f}\n{g}", ha="center", va="bottom",
                    fontsize=22, fontweight="bold")
        ax.set_ylim(0, 110)
        ax.set_title(nm, fontsize=24, pad=12)
        save_txt = (f"예시 금리 {r['traditional']['rate_pct']:.1f}% → {r['fair']['rate_pct']:.1f}% | "
                    f"1억 대출 연 이자 {r['interest_saving_won'] / 1e4:,.0f}만원 절감")
        f.text(0.08 + i * 0.46, 0.09, save_txt, fontsize=18, color=OK, fontweight="bold")
    save(f, "fig07_caed_demo.png", "caed/service.py diagnose() 시연 A/B",
         foot="신용캐드 시연 | 핵심 모델은 합성 데이터 MVP, 등급 컷·금리는 예시 가정 (상권 수익성만 서울시 실측)")


# ---- fig08 업종 연체율 추이
def fig08():
    d = pd.read_csv(os.path.join(ROOT, "data", "delinq_panel.csv"))
    d = d[(d["dim"] == "산업") & (d["basis"] == "차주수 기준") & (d["item"] == "전체")]
    unit = "예술, 스포츠 및 여가관련 서비스업"
    me = d[d["unit"] == unit].sort_values("year")
    med = d.groupby("year")["val"].median()
    f = fig("헬스장이 속한 업종의 연체율이 오르고 있다",
            "개인사업자 연체율(차주수 기준) | 예술·스포츠·여가 서비스업 vs 15개 산업 중앙값")
    ax = axes(f)
    ax.plot(me["year"], me["val"], color=WARN, lw=4, marker="o", ms=11, label="예술·스포츠·여가(헬스장 포함)")
    ax.plot(med.index, med.values, color="#94a3b8", lw=3, ls="--", marker="o", ms=8, label="15개 산업 중앙값")
    for x, y in zip(me["year"], me["val"]):
        ax.text(x, y + 0.08, f"{y:.1f}", ha="center", fontsize=17, color=WARN)
    ax.set_ylabel("연체율 (%)")
    ax.legend(frameon=False, fontsize=19, loc="upper left")
    ax.set_xticks(me["year"])
    save(f, "fig08_industry_delinquency.png", "한국은행 산업별 개인사업자 연체율 (data/delinq_panel.csv)",
         foot="신용캐드 참고 지표 | 공개 통계")


# ---- fig09 연도별 안정성
def fig09():
    v = risk("kosdaq")
    yrs = sorted(v["auc_by_year"])
    f = fig("한 해만 맞은 게 아니다 (코스닥 조기경보 연도별 AUC)",
            "같은 계수(2020년까지 학습)를 매년 그대로 적용 | 2025년은 9월까지(정답 기간 미완)")
    ax = axes(f)
    vals = [v["auc_by_year"][y] for y in yrs]
    b = ax.bar(yrs, vals, color=ACCENT, width=0.5)
    ax.axhline(0.5, color=WARN, ls="--", lw=2)
    ax.set_ylim(0.45, 0.75)
    bar_labels(ax, b, lambda x: f"{x:.2f}", dy=0.004, size=26)
    save(f, "fig09_auc_by_year.png", "data/dintel/risk_model_kosdaq.json")


# ---- fig10 생존편향 보정
def fig10():
    from dintel.evidence import _surv
    sv = _surv()
    if not sv or "B" not in sv:
        print("skip fig10 (no SURVIVORSHIP_SUMMARY)")
        return
    f = fig("퇴출된 회사를 채워 넣어도 3배는 유지된다",
            f"상장폐지 코스닥 기업 {sv['n_delisted']}곳을 DART로 보충해 재검증 · 검증 2022~ · 공시 건수 피처만(양쪽 동일)")
    ax = axes(f, (0.08, 0.13, 0.58, 0.66))
    labels = ["A 현재 상장사만\n(기존 방식)", "B 퇴출 기업 포함\n(보정)", "C 기존 방식 학습 →\n실제 세상 검증"]
    base = [sv[k]["base_pct"] for k in "ABC"]
    top = [sv[k]["top10_pct"] for k in "ABC"]
    x = np.arange(3)
    b1 = ax.bar(x - 0.2, base, 0.38, color="#94a3b8", label="평균 위험률")
    b2 = ax.bar(x + 0.2, top, 0.38, color=WARN, label="경고 상위 10% 실제 위험률")
    ax.set_xticks(x, labels)
    bar_labels(ax, b1, lambda v: f"{v:.1f}%", dy=0.4, size=20)
    bar_labels(ax, b2, lambda v: f"{v:.1f}%", dy=0.4, size=20)
    ax.set_ylim(0, 34)
    ax.set_ylabel("12개월 중대 위험 공시율 (%)")
    ax.legend(frameon=False, fontsize=18, loc="upper left")
    f.text(0.70, 0.72, "보정 전 → 보정 후", fontsize=26, fontweight="bold", color=INK)
    rows = [(f"배수  {sv['A']['multiple']:.1f}배 → {sv['B']['multiple']:.1f}배", OK),
            (f"AUC  {sv['A']['auc']:.3f} → {sv['B']['auc']:.3f}", ACCENT),
            (f"상위 10% 위험률  {sv['A']['top10_pct']:.1f}% → {sv['B']['top10_pct']:.1f}%", WARN),
            (f"포착률  {sv['A']['capture_pct']}% → {sv['B']['capture_pct']}%", INK)]
    for i, (s, c) in enumerate(rows):
        f.text(0.70, 0.63 - i * 0.085, s, fontsize=22, color=c)
    f.text(0.70, 0.24, "신호는 진짜였고,\n실제 위험은 더 컸다", fontsize=24, fontweight="bold", color=OK)
    save(f, "fig10_survivorship.png", "data/dintel/SURVIVORSHIP_SUMMARY.txt (dintel/survivorship.py)")


# ---- 10-20 신용캐드 실데이터: fig12 업종별 업력 곡선, fig13 프랜차이즈 vs 독립, fig14 브랜드 성장·쇠퇴
def _caed(n):
    with open(os.path.join(ROOT, "data", "caed", n), encoding="utf-8") as fh:
        return json.load(fh)


def fig12():
    d = _caed("industry_survival.json")["industries"]
    show = [("072404", "일반음식점", WARN), ("072405", "카페·휴게", ACCENT2), ("051801", "미용실", ACCENT), ("062001", "세탁소", OK), ("104201", "헬스장*", MUTED)]
    f = fig("대부분 업종에서 젊은 가게가 더 닫는다 - 헬스장만 예외처럼 보였다", "서울 인허가 894,933곳 · 매년 말 영업 중 업소의 다음 1년 폐업률(2021~24) · * 헬스장은 대장이 폐업의 17%만 잡음")
    ax = axes(f)
    labs = ["<1년", "1-3년", "3-5년", "5-10년", "10년+"]
    for code, nm, c in show:
        y = [d[code]["age"].get(k, np.nan) * 100 for k in labs]
        ax.plot(range(5), y, marker="o", lw=4, ms=12, color=c, label=nm, ls="--" if code == "104201" else "-")
    ax.set_xticks(range(5), ["1년 미만", "1~3년", "3~5년", "5~10년", "10년+"])
    ax.set_ylabel("다음 1년 폐업률(%)")
    ax.legend(fontsize=19, frameon=False, ncol=5, loc="upper right")
    save(f, "fig12_industry_age_curves.png", "서울 열린데이터광장 지방행정 인허가 (caed/industry_survival.py)")


def fig13():
    cafe, rest = _caed("franchise_survival.json"), _caed("franchise_survival_072404.json")
    f = fig("프랜차이즈 가맹점은 덜 닫는다 - 특히 첫해", "서울 인허가 · 다음 1년 폐업률(2021~24) · 상호에서 브랜드 추정, 학습기에 30곳 이상인 브랜드")
    labs = ["<1년", "1-3년", "3-5년", "5-10년", "10년+"]
    for i, (d, nm) in enumerate(((cafe, "카페(커피숍 40,554곳)"), (rest, "일반음식점(539,188곳)"))):
        ax = axes(f, (0.07 + i * 0.47, 0.13, 0.40, 0.62))
        x = np.arange(5)
        a = [d["by_age"][k]["franchise"] * 100 for k in labs]
        b = [d["by_age"][k]["independent"] * 100 for k in labs]
        b1 = ax.bar(x - 0.2, b, 0.4, color="#9ca3af", label="독립")
        b2 = ax.bar(x + 0.2, a, 0.4, color=ACCENT, label="프랜차이즈")
        bar_labels(ax, b1, lambda v: f"{v:.0f}", size=15)
        bar_labels(ax, b2, lambda v: f"{v:.0f}", size=15, color=ACCENT)
        ax.set_xticks(x, ["1년 미만", "1~3년", "3~5년", "5~10년", "10년+"], fontsize=15)
        ax.set_title(nm, fontsize=22, pad=10)
        ax.set_ylabel("다음 1년 폐업률(%)" if i == 0 else "")
        if i == 0:
            ax.legend(fontsize=17, frameon=False)
    save(f, "fig13_franchise_vs_independent.png", "서울 인허가 (caed/franchise_survival.py)")


def fig14():
    cafe, rest = _caed("franchise_survival.json")["momentum"]["result"], _caed("franchise_survival_072404.json")["momentum"]["result"]
    f = fig("브랜드가 쇠퇴기면 가맹점이 닫는다", "브랜드 순증가율(직전 12개월 서울 개업-폐업 / 매장) 3분위별 가맹점의 다음 1년 폐업률 · 사전 등록 후 채점")
    for i, (d, nm) in enumerate(((cafe, "카페"), (rest, "일반음식점"))):
        ax = axes(f, (0.07 + i * 0.47, 0.13, 0.40, 0.62))
        for j, (per, c) in enumerate((("학습기 2014~19", "#9ca3af"), ("검증 2021~24", WARN))):
            v = [d[per]["low"] * 100, d[per]["mid"] * 100, d[per]["high"] * 100]
            bs = ax.bar(np.arange(3) + (j - 0.5) * 0.38, v, 0.38, color=c, label=per)
            bar_labels(ax, bs, lambda h: f"{h:.1f}", size=16, color=c if j else INK)
        ax.set_xticks(range(3), ["쇠퇴 1/3", "중간", "성장 1/3"])
        ax.set_title(nm, fontsize=22, pad=10)
        ax.set_ylabel("다음 1년 폐업률(%)" if i == 0 else "")
        if i == 0:
            ax.legend(fontsize=17, frameon=False)
    save(f, "fig14_brand_momentum.png", "서울 인허가 (caed/franchise_survival.py momentum)")


if __name__ == "__main__":
    only = [a for a in sys.argv[1:] if a.startswith("fig")]
    for fn in (fig01, fig02, fig03, fig04, fig05, fig06, fig07, fig08, fig09, fig10, fig12, fig13, fig14):
        if not only or fn.__name__ in only:
            fn()

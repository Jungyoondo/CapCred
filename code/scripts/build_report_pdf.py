"""제출용 PDF 보고서 빌드 - deliverables/report/report.html -> deliverables/dintel_x_caed_report.pdf (2026-10-09).

python -X utf8 scripts/build_report_pdf.py          # 기존 dintel × 신용캐드 보고서
python -X utf8 scripts/build_report_pdf.py --biz    # 10-25 사업 보고서 드래프트: report_biz_body.html + report.html의 <style> -> report_biz.html -> sinyongcaed_business_report.pdf
그림은 scripts/make_figures.py, 영상 콘티 시트는 scripts/render_motion_video.py --stills(1분판은 render_motion_1min.py --stills) 가 먼저 만들어 둔다.
Microsoft Edge 헤드리스 인쇄(머리글·바닥글 없음)를 쓴다.
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML = os.path.join(ROOT, "deliverables", "report", "report.html")
PDF = os.path.join(ROOT, "deliverables", "dintel_x_caed_report.pdf")
BIZ_BODY = os.path.join(ROOT, "deliverables", "report", "report_biz_body.html")
BIZ_HTML = os.path.join(ROOT, "deliverables", "report", "report_biz.html")
BIZ_PDF = os.path.join(ROOT, "deliverables", "capcred_business_report.pdf")   # 10-26 묶음 그림(CapCred), 이전 신용캐드 드래프트는 sinyongcaed_business_report.pdf로 남김
EDGE = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]


def biz_html():
    """기존 보고서와 같은 스타일로 사업 보고서 HTML을 조립한다."""
    with open(HTML, encoding="utf-8") as fh:
        style = re.search(r"<style>.*?</style>", fh.read(), re.S).group(0)
    with open(BIZ_BODY, encoding="utf-8") as fh:
        body = fh.read()
    with open(BIZ_HTML, "w", encoding="utf-8") as fh:
        fh.write(f'<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n<title>CapCred 사업 보고서</title>\n{style}\n</head>\n<body>\n{body}\n</body>\n</html>\n')
    return BIZ_HTML


def main():
    html, pdf = (biz_html(), BIZ_PDF) if "--biz" in sys.argv else (HTML, PDF)
    edge = next((p for p in EDGE if os.path.exists(p)), None)
    if not edge:
        sys.exit("Microsoft Edge not found")
    url = "file:///" + html.replace("\\", "/")
    # 별도 프로필 - 사용 중인 Edge 창이 있으면 기본 프로필로는 인쇄가 조용히 실패한다
    prof = os.path.join(os.environ.get("TEMP", ROOT), "edge_pdf_profile")
    if os.path.exists(pdf):
        os.remove(pdf)
    subprocess.run([edge, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={prof}",
                    f"--print-to-pdf={pdf}", url], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import time
    last = -1
    for _ in range(120):            # Edge가 자식 프로세스로 인쇄하고 먼저 끝나는 경우 - 파일 크기가 멈출 때까지 대기
        time.sleep(1)
        if os.path.exists(pdf):
            sz = os.path.getsize(pdf)
            if sz > 0 and sz == last:
                break
            last = sz
    if not os.path.exists(pdf):
        sys.exit("PDF was not produced")
    print("pdf ->", pdf, f"{os.path.getsize(pdf) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()

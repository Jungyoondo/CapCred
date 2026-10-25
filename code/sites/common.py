"""두 사이트 공용 서버 코어 - 정적 파일 + 라우트 표 기반 JSON API (2026-10-08 econ_lab_bridge.py에서 분리)."""
import http.server
import json
import re
import socketserver
import sys
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


class Handler(http.server.SimpleHTTPRequestHandler):
    """하위 클래스는 ROUTES = {"/api/x": fn(query_dict) -> (body, status)} 와 INDEX(시작 페이지)만 정한다."""
    ROUTES = {}
    # 2026-10-09 하위 폴더 파일 제공: {"/접두사/": (폴더, 파일명 정규식)} - 정규식에 맞는 파일 이름만(경로 이동 불가)
    FILE_ROUTES = {}
    INDEX = "index.html"
    STATIC_ALLOW = (".html", ".css", ".js", ".png", ".svg", ".ico", ".json")   # 정적 파일 화이트리스트

    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(BASE_DIR), **k)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        super().end_headers()

    def send_json(self, body, status=200):
        self.send_response(status)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False, default=str).encode("utf-8"))

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        fn = self.ROUTES.get(u.path)
        if fn is not None:
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            try:
                body, status = fn(q)
            except Exception as e:
                body, status = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}, 500
            return self.send_json(body, status)
        if u.path == "/":
            self.path = "/" + self.INDEX
            return super().do_GET()
        for prefix, (folder, rx) in self.FILE_ROUTES.items():
            if u.path.startswith(prefix):
                name = u.path[len(prefix):]
                fp = (BASE_DIR / folder / name).resolve()
                if not re.fullmatch(rx, name) or fp.parent != (BASE_DIR / folder).resolve() or not fp.is_file():
                    return self.send_error(404, "Not found")
                data = fp.read_bytes()
                self.send_response(200)
                self.send_header("Content-type", "image/png" if name.endswith(".png") else "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
        # 정적 파일은 루트의 화이트리스트 확장자만(.env·데이터·코드 노출 방지)
        p = (BASE_DIR / u.path.lstrip("/")).resolve()
        if p.parent != BASE_DIR or p.suffix.lower() not in self.STATIC_ALLOW:
            return self.send_error(404, "Not found")
        return super().do_GET()

    def log_message(self, fmt, *args):     # 콘솔 소음 줄이기(API 오류는 응답 본문에)
        pass


def serve(handler_cls, port, name):
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    socketserver.ThreadingTCPServer.daemon_threads = True
    with socketserver.ThreadingTCPServer(("", port), handler_cls) as httpd:
        print(f"[{name}] http://127.0.0.1:{port}  (Ctrl+C 종료)", flush=True)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print(f"\n[{name}] 종료")

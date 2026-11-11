# serve.py — 버텨라 캔틸레버 로컬 서버
# 사용법:  python serve.py        → http://localhost:8000/index.html
# 파일을 고친 뒤 새로고침하면 항상 최신 버전이 보이도록 캐시를 끈다.
import http.server
import os
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
os.chdir(os.path.dirname(os.path.abspath(__file__)))


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):  # 콘솔 조용히
        pass


if __name__ == "__main__":
    with http.server.ThreadingHTTPServer(("", PORT), NoCacheHandler) as httpd:
        print(f"버텨라 캔틸레버: http://localhost:{PORT}/index.html")
        httpd.serve_forever()

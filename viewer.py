"""Python 3.9+ local source viewer."""
import json
import webbrowser
from urllib.parse import unquote
from analyzers import analyze, supported_languages
from analyzers.python import outline
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMIT = 5 * 1024 * 1024




class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, mime='text/plain'):
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/languages':
            self.reply(200, json.dumps(supported_languages()), 'application/json')
        elif self.path == '/learning-example':
            self.reply(200, (ROOT / 'learning_example.py').read_text())
        elif self.path == '/':
            self.reply(200, (ROOT / 'index.html').read_text(), 'text/html')
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != '/outline' or self.headers.get('Content-Type') != 'application/octet-stream':
            return self.send_error(400)
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= size <= LIMIT:
                return self.reply(413, '5 MiB 이하의 파일을 선택하세요.')
            html = analyze(self.rfile.read(size), unquote(self.headers.get('X-Source-Name', 'source.py')))
        except SyntaxError as err:
            return self.reply(400, f'{err.lineno or 1}행: {err.msg}')
        except (UnicodeError, ValueError, RecursionError) as err:
            return self.reply(400, f'파일을 분석할 수 없습니다: {err}')
        self.reply(200, html, 'text/html')


if __name__ == '__main__':
    with ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        url = f'http://127.0.0.1:{server.server_port}'
        print(url, flush=True)
        webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

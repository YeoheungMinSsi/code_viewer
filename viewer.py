"""Python 3.9+ local source viewer."""
import json
import os
import threading
import webbrowser
from urllib.parse import unquote
from analyzers import analyze, supported_languages
from analyzers.python import outline
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / 'examples'
LESSON_FILES = {
    '/learning-example': 'learning_example.py',
    '/learning-example-oop': 'inheritance_example.py',
    '/learning-example-java': 'LearningExample.java',
    '/learning-example-csharp': 'LearningExample.cs',
    '/learning-example-ts': 'learning_example.ts',
    '/learning-example-js-oop': 'inheritance_example.js',
}
AUTOSAVE = Path(os.environ.get('CODE_VIEWER_AUTOSAVE', str(ROOT / '.autosave.json')))
SAVE_LOCK = threading.Lock()
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
        if self.path == '/autosave':
            try:
                self.reply(200, AUTOSAVE.read_text(encoding='utf-8') if AUTOSAVE.exists() else 'null', 'application/json')
            except OSError:
                self.reply(500, '자동 저장 파일을 읽을 수 없습니다.')
        elif self.path == '/languages':
            self.reply(200, json.dumps(supported_languages()), 'application/json')
        elif self.path == '/static/app.css':
            self.reply(200, (ROOT / 'static' / 'app.css').read_text(encoding='utf-8'), 'text/css')
        elif self.path == '/static/app.js':
            self.reply(200, (ROOT / 'static' / 'app.js').read_text(encoding='utf-8'), 'application/javascript')
        elif self.path in LESSON_FILES:
            self.reply(200, (EXAMPLES / LESSON_FILES[self.path]).read_text(encoding='utf-8'))
        elif self.path == '/':
            self.reply(200, (ROOT / 'index.html').read_text(encoding='utf-8'), 'text/html')
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/csharp-links':
            if self.headers.get('Content-Type') != 'application/json':
                return self.reply(400, 'JSON 요청이 필요합니다.')
            try:
                size = int(self.headers.get('Content-Length', '-1'))
                if not 0 <= size <= 50 * 1024 * 1024:
                    return self.reply(413, '분석 요청은 최대 50 MiB입니다.')
                files = json.loads(self.rfile.read(size))
                if not isinstance(files, dict) or len(files) > 300 or any(not isinstance(path, str) or not isinstance(source, str) or len(source.encode()) > LIMIT for path, source in files.items()):
                    raise ValueError('올바른 C# 파일 목록이 아닙니다.')
                from analyzers.csharp_calls import Project
                return self.reply(200, json.dumps(Project(files).links()), 'application/json')
            except (ValueError, TypeError, RecursionError) as err:
                return self.reply(400, f'C# 호출을 분석할 수 없습니다: {err}')
        if self.path == '/autosave':
            if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
                return self.reply(403, '허용되지 않은 저장 요청입니다.')
            try:
                size = int(self.headers.get('Content-Length', '-1'))
                if not 0 <= size <= 50 * 1024 * 1024:
                    return self.reply(413, '자동 저장은 최대 50 MiB입니다.')
                raw = self.rfile.read(size).decode('utf-8')
                data = json.loads(raw)
                if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('files'), list):
                    raise ValueError('올바른 작업 파일이 아닙니다.')
                with SAVE_LOCK:
                    temporary = AUTOSAVE.with_suffix('.tmp')
                    temporary.write_text(raw, encoding='utf-8')
                    temporary.replace(AUTOSAVE)
            except (ValueError, OSError) as err:
                return self.reply(400, f'자동 저장 실패: {err}')
            return self.reply(200, '저장 완료')
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

"""Python 3.9+ local source viewer."""
import ast
import io
import tokenize
import webbrowser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIMIT = 1024 * 1024


def outline(raw):
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    source = raw.decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
    lines = source.split('\n')
    tree = ast.parse(source)

    definitions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    imports = {}
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom) and statement.level == 0:
            for alias in statement.names:
                imports[alias.asname or alias.name] = (statement.module or '', alias.name)
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                imports[alias.asname or alias.name] = (alias.name, '')
    calls = {}
    for scope in [tree] + [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        methods = {n.name: n for n in scope.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fn in methods.values():
            # shortcut: dynamic dispatch is not resolved; add scope analysis before linking nested functions.
            if fn.decorator_list or any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)) and n is not fn for n in ast.walk(fn)):
                continue
            bound = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            bound.update(a.arg for a in ast.walk(fn.args) if isinstance(a, ast.arg))
            for call in ast.walk(fn):
                if not isinstance(call, ast.Call):
                    continue
                target = None
                f = call.func
                if isinstance(f, ast.Name) and f.id not in bound:
                    target = definitions.get(f.id)
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == 'self' and isinstance(scope, ast.ClassDef) and not scope.bases and fn.args.args and fn.args.args[0].arg == 'self' and not any(isinstance(n, ast.Name) and n.id == 'self' and isinstance(n.ctx, ast.Store) for n in ast.walk(fn)):
                    target = methods.get(f.attr)
                external = None
                if isinstance(f, ast.Name) and f.id not in bound:
                    external = imports.get(f.id)
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id not in bound:
                    module = imports.get(f.value.id)
                    if module and not module[1]:
                        external = (module[0], f.attr)
                if external and f.lineno == f.end_lineno:
                    calls.setdefault(f.lineno, []).append((f.col_offset, f.end_col_offset, '|'.join(external)))
                if target and f.lineno == f.end_lineno:
                    calls.setdefault(f.lineno, []).append((f.col_offset, f.end_col_offset, str(target.lineno)))

    def code(start, end):
        result = []
        for n in range(start, end + 1):
            raw = lines[n-1].encode('utf-8')
            parts, cursor = [], 0
            for left, right, target in sorted(set(calls.get(n, []))):
                if left < cursor:
                    continue
                parts.append(escape(raw[cursor:left].decode()))
                parts.append(f'<button class="call" data-target="{escape(str(target), quote=True)}" title="같은 파일의 정의로 이동">{escape(raw[left:right].decode())}</button>')
                cursor = right
            parts.append(escape(raw[cursor:].decode()))
            result.append(f'<i>{n}</i>' + ''.join(parts))
        return '<pre>' + '\n'.join(result) + '</pre>'

    def cards(node, in_class=False):
        items = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                cls = isinstance(child, ast.ClassDef)
                kind = '클래스' if cls else ('비동기 함수' if isinstance(child, ast.AsyncFunctionDef) else '함수')
                name = child.name if cls else f'{child.name}({ast.unparse(child.args)})'
                body = (cards(child, True) or '<p>표시할 멤버가 없습니다.</p>') if cls else code(start, child.end_lineno)
                items.append((start, f'<details data-name="{escape(child.name, quote=True)}" data-line="{child.lineno}" class="{"cls" if cls else "fn"}"><summary><small>{kind}</small> <b>{escape(name)}</b> <em>L{child.lineno}</em></summary>{body}</details>'))
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                label = escape(ast.unparse(child))
                items.append((child.lineno, f'<details class="imp"><summary><small>import</small><b>{label}</b><em>L{child.lineno}</em></summary>{code(child.lineno, child.end_lineno)}</details>'))
            elif isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                names = [n.id for target in targets for n in ast.walk(target)
                         if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)]
                if names:
                    label = escape(', '.join(names))
                    kind = '클래스 변수' if in_class else '전역변수'
                    items.append((child.lineno, f'<details class="var"><summary><small>{kind}</small> <b>{label}</b> <em>L{child.lineno}</em></summary>{code(child.lineno, child.end_lineno)}</details>'))
            else:
                items.extend(collect(child, in_class))
        return render(items)

    def collect(node, in_class):
        # Definitions inside if/try blocks belong to the enclosing scope.
        if isinstance(node, (ast.stmt, ast.ExceptHandler)) or type(node).__name__ == 'match_case':
            content = cards(node, in_class)
            if content:
                return [(getattr(node, 'lineno', 0), content)]
        return []

    def render(items):
        return '<section>' + ''.join(html for _, html in sorted(items, key=lambda x: x[0])) + '</section>' if items else ''

    return cards(tree) or '<p>클래스나 함수가 없어 원문을 표시합니다.</p>' + code(1, len(lines))


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, mime='text/plain'):
        data = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/':
            self.reply(200, (ROOT / 'index.html').read_text(), 'text/html')
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != '/outline' or self.headers.get('Content-Type') != 'application/octet-stream':
            return self.send_error(400)
        try:
            size = int(self.headers.get('Content-Length', '-1'))
            if not 0 <= size <= LIMIT:
                return self.reply(413, '1 MiB 이하의 파일을 선택하세요.')
            html = outline(self.rfile.read(size))
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

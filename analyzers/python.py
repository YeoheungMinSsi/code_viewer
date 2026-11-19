"""Python source analysis. Returns escaped canvas markup; never executes source."""
import ast
import io
import tokenize
from html import escape

def outline(raw):
    encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
    source = raw.decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
    lines = source.split('\n')
    tree = ast.parse(source)

    definitions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    imports = {}
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            for alias in statement.names:
                imports[alias.asname or alias.name] = ('.' * statement.level + (statement.module or ''), alias.name)
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                imports[alias.asname or alias.name] = (alias.name, '')
    def function_nodes(fn):
        yield fn
        pending = list(fn.body)
        while pending:
            node = pending.pop()
            yield node
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                pending.extend(ast.iter_child_nodes(node))

    calls = {}
    for scope in [tree] + [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        methods = {n.name: n for n in scope.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fn in methods.values():
            # shortcut: dynamic dispatch is not resolved; add scope analysis before linking nested functions.
            if fn.decorator_list:
                continue
            nodes = list(function_nodes(fn))
            bound = {n.id for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            bound.update(n.name for n in nodes if n is not fn and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
            bound.update(a.arg for a in ast.walk(fn.args) if isinstance(a, ast.arg))
            for call in nodes:
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

    def is_entry(node):
        return isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and ast.dump(node.test) == ast.dump(ast.parse('__name__ == "__main__"', mode='eval').body)

    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    for entry in [n for n in tree.body if is_entry(n)]:
        objects = {}
        for statement in entry.body:
            for call in ast.walk(statement):
                if not isinstance(call, ast.Call):
                    continue
                f, target = call.func, None
                if isinstance(f, ast.Name):
                    target = classes.get(f.id) or definitions.get(f.id)
                elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                    cls = objects.get(f.value.id)
                    if cls and not cls.bases:
                        target = next((n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == f.attr and not n.decorator_list), None)
                if target and f.lineno == f.end_lineno:
                    calls.setdefault(f.lineno, []).append((f.col_offset, f.end_col_offset, str(target.lineno)))
            for n in ast.walk(statement):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                    objects.pop(n.id, None)
            if isinstance(statement, ast.Assign) and isinstance(statement.value, ast.Call) and isinstance(statement.value.func, ast.Name):
                cls = classes.get(statement.value.func.id)
                if cls:
                    for name in statement.targets:
                        if isinstance(name, ast.Name):
                            objects[name.id] = cls

    # Do not claim a definition when the module rebinds its name.
    rebound = {n.id for statement in tree.body if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
               for n in ast.walk(statement) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    for line, entries in calls.items():
        calls[line] = [(left, right, target) for left, right, target in entries
                       if not (target.isdigit() and any(name in rebound and str(node.lineno) == target for name, node in definitions.items()))]
    for call in ast.walk(tree):
        if isinstance(call, ast.Call):
            f = call.func
            if f.lineno == f.end_lineno and not any(left == f.col_offset for left, _, _ in calls.get(f.lineno, [])):
                reason = '객체·동적 호출: 정적 분석으로 대상을 확정할 수 없습니다.' if isinstance(f, ast.Attribute) else '내장 함수 또는 현재 분석 범위에서 정의를 확인할 수 없는 호출입니다.'
                calls.setdefault(f.lineno, []).append((f.col_offset, f.end_col_offset, '?' + reason))

    def code(start, end):
        result = []
        for n in range(start, end + 1):
            raw = lines[n-1].encode('utf-8')
            parts, cursor = [], 0
            for left, right, target in sorted(set(calls.get(n, []))):
                if left < cursor:
                    continue
                parts.append(escape(raw[cursor:left].decode()))
                title = target[1:] if target.startswith('?') else '호출 연결 확인: 클릭하면 점선으로 표시합니다.'
                parts.append(f'<button class="call" data-target="{escape(str(target), quote=True)}" title="{escape(title, quote=True)}">{escape(raw[left:right].decode())}</button>')
                cursor = right
            parts.append(escape(raw[cursor:].decode()))
            result.append(f'<i>{n}</i>' + ''.join(parts))
        return '<pre>' + '\n'.join(result) + '</pre>'

    def cards(node, in_class=False):
        items = []
        import_nodes = [child for child in ast.iter_child_nodes(node)
                        if isinstance(child, (ast.Import, ast.ImportFrom))]
        if import_nodes:
            first = import_nodes[0].lineno
            body = '\n'.join(code(child.lineno, child.end_lineno)[5:-6] for child in import_nodes)
            items.append((first, f'<details class="imp"><summary><small>import</small><b>가져오기 · {len(import_nodes)}개 선언</b><em>L{first}</em></summary><pre>{body}</pre></details>'))
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([child.lineno] + [d.lineno for d in child.decorator_list])
                cls = isinstance(child, ast.ClassDef)
                kind = '클래스' if cls else ('비동기 함수' if isinstance(child, ast.AsyncFunctionDef) else '함수')
                name = child.name if cls else f'{child.name}({ast.unparse(child.args)})'
                body = (cards(child, True) or '<p>표시할 멤버가 없습니다.</p>') if cls else code(start, child.end_lineno)
                items.append((start, f'<details data-name="{escape(child.name, quote=True)}" data-line="{child.lineno}" class="{"cls" if cls else "fn"}"><summary><small>{kind}</small> <b>{escape(name)}</b> <em>L{child.lineno}</em></summary>{body}</details>'))
            elif is_entry(child):
                items.append((child.lineno, f'<details class="entry"><summary><small>실행 시작점</small><b>여기서 시작</b><em>L{child.lineno}</em></summary>{code(child.lineno, child.end_lineno)}</details>'))
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                continue
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


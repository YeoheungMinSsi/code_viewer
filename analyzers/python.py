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

    FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef)
    # Do not claim a definition when the module rebinds its name.
    rebound = {n.id for statement in tree.body if not isinstance(statement, (*FUNCS, ast.ClassDef))
               for n in ast.walk(statement) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    definitions = {n.name: n for n in tree.body if isinstance(n, FUNCS) and n.name not in rebound}
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef) and n.name not in rebound}
    imports = {}
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            for alias in statement.names:
                imports[alias.asname or alias.name] = ('.' * statement.level + (statement.module or ''), alias.name)
        elif isinstance(statement, ast.Import):
            for alias in statement.names:
                imports[alias.asname or alias.name] = (alias.name, '')

    def lineage(cls):
        # Only a single same-file parent chain is certain; multiple or external parents stop it.
        chain = []
        while cls is not None and cls not in chain:
            chain.append(cls)
            base = cls.bases[0] if len(cls.bases) == 1 else None
            cls = classes.get(base.id) if isinstance(base, ast.Name) else None
        return chain

    def owner(cls, name, skip=0):
        for c in lineage(cls)[skip:]:
            found = [m for m in c.body if isinstance(m, FUNCS) and m.name == name]
            if found:
                return c, found[-1]
        return None, None

    def descends(c, cls, seen=()):
        parents = [classes.get(b.id) for b in c.bases if isinstance(b, ast.Name)]
        return any(p is cls or (p is not None and p not in seen and descends(p, cls, seen + (c,))) for p in parents)

    def method_link(cls, name, exact, skip=0):
        target = owner(cls, name, skip)[1]
        if target is None:
            return None
        others = [] if exact else [c.name for c in classes.values() if descends(c, cls) and owner(c, name)[1] is not target]
        if others:
            return f'?자식 클래스 {", ".join(others)}에서 재정의되어, 어떤 객체인지에 따라 실행되는 메서드가 달라집니다.'
        return str(target.lineno)

    def objects(nodes, args=()):
        """Names bound exactly once to ClassName(), or annotated parameters never reassigned."""
        stores, hidden, found = {}, set(), {}
        for n in nodes:
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                stores[n.id] = stores.get(n.id, 0) + 1
            elif isinstance(n, (ast.Global, ast.Nonlocal)):
                hidden.update(n.names)
        for n in nodes:
            if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                    and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
                    and n.value.func.id in classes and n.value.func.id not in stores):
                found[n.targets[0].id] = (classes[n.value.func.id], True)
        for a in args:
            if isinstance(a.annotation, ast.Name) and a.annotation.id in classes and a.annotation.id not in stores:
                found[a.arg] = (classes[a.annotation.id], False)
        return {k: v for k, v in found.items() if k not in hidden and stores.get(k, 0) == (1 if v[1] else 0)}

    calls = {}

    def link(nodes, bound, objs, cls=None, self_name=None):
        for call in nodes:
            if not isinstance(call, ast.Call):
                continue
            f, target = call.func, None
            if isinstance(f, ast.Name) and f.id not in bound:
                node = definitions.get(f.id) or classes.get(f.id)
                target = str(node.lineno) if node else imports.get(f.id) and '|'.join(imports[f.id])
            elif isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
                name = f.value.id
                if name == self_name:
                    target = method_link(cls, f.attr, False)
                elif name in objs:
                    target = method_link(objs[name][0], f.attr, objs[name][1])
                elif name not in bound and imports.get(name, ('', 'x'))[1] == '':
                    target = imports[name][0] + '|' + f.attr
            elif (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Call) and isinstance(f.value.func, ast.Name)
                  and f.value.func.id == 'super' and not f.value.args and cls is not None):
                target = method_link(cls, f.attr, True, 1)
            if target and f.lineno == f.end_lineno:
                calls.setdefault(f.lineno, []).append((f.col_offset, f.end_col_offset, target))

    def function_nodes(fn):
        yield fn
        pending = list(fn.body)
        while pending:
            node = pending.pop()
            yield node
            if not isinstance(node, (*FUNCS, ast.ClassDef, ast.Lambda)):
                pending.extend(ast.iter_child_nodes(node))

    # Nested functions are not analysed yet; their bodies need their own scope.
    for scope in [tree, *classes.values()]:
        for fn in [n for n in scope.body if isinstance(n, FUNCS)]:
            nodes = list(function_nodes(fn))
            bound = {n.id for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            bound.update(n.name for n in nodes if n is not fn and isinstance(n, (*FUNCS, ast.ClassDef)))
            args = [a for a in ast.walk(fn.args) if isinstance(a, ast.arg)]
            bound.update(a.arg for a in args)
            cls = scope if isinstance(scope, ast.ClassDef) else None
            first = fn.args.args[0].arg if cls and fn.args.args and not fn.decorator_list else None
            self_name = first if first and not any(isinstance(n, ast.Name) and n.id == first and isinstance(n.ctx, ast.Store) for n in nodes) else None
            link(nodes, bound, objects(nodes, args), cls, self_name)

    def is_entry(node):
        return isinstance(node, ast.If) and isinstance(node.test, ast.Compare) and ast.dump(node.test) == ast.dump(ast.parse('__name__ == "__main__"', mode='eval').body)

    module_nodes = [n for statement in tree.body if not isinstance(statement, (*FUNCS, ast.ClassDef)) for n in ast.walk(statement)]
    module_objects = objects(module_nodes + [n for n in ast.walk(tree) if isinstance(n, ast.Global)])
    for entry in [n for n in tree.body if is_entry(n)]:
        link([n for statement in entry.body for n in ast.walk(statement)], set(), module_objects)
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
                parent = owner(in_class, child.name, 1)[0] if in_class and not cls else None
                if parent:
                    kind += f' · 재정의({escape(parent.name)})'
                name = child.name if cls else f'{child.name}({ast.unparse(child.args)})'
                body = (cards(child, child) or '<p>표시할 멤버가 없습니다.</p>') if cls else code(start, child.end_lineno)
                bases = ''
                for base in child.bases if cls else []:
                    if isinstance(base, ast.Name) and base.id == 'object':
                        continue
                    found = classes.get(base.id) if isinstance(base, ast.Name) else None
                    target = str(found.lineno) if found else '?이 파일에 정의되지 않은 부모 클래스입니다(외부 라이브러리 또는 다른 파일).'
                    bases += f'<button class="call inheritance" data-target="{escape(target, quote=True)}" title="상속 관계: 부모 클래스의 기능을 물려받습니다.">상속 {escape(ast.unparse(base))}</button>'
                items.append((start, f'<details data-name="{escape(child.name, quote=True)}" data-line="{child.lineno}" class="{"cls" if cls else "fn"}"><summary><small>{kind}</small> <b>{escape(name)}</b> <em>L{child.lineno}</em>{bases}</summary>{body}</details>'))
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


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

    def base_ref(base):
        """Same-file ClassDef, 'module|Class' for an imported class, or '?expr'."""
        if isinstance(base, ast.Name):
            if base.id in classes:
                return classes[base.id]
            if imports.get(base.id, ('', ''))[1]:
                return '|'.join(imports[base.id])
        elif isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name) and imports.get(base.value.id, ('', 'x'))[1] == '':
            return imports[base.value.id][0] + '|' + base.attr
        return '?' + ast.unparse(base)

    mro_cache = {}

    def mro(cls, seen=()):
        """Python C3 linearisation; parents outside this file stay as string entries."""
        if cls in seen:
            return [cls, '?순환 상속']
        if not seen and cls in mro_cache:
            return mro_cache[cls]
        refs = [base_ref(b) for b in cls.bases if not (isinstance(b, ast.Name) and b.id == 'object')]
        seqs = [list(mro(ref, seen + (cls,))) if isinstance(ref, ast.ClassDef) else [ref] for ref in refs]
        if seqs:
            seqs.append([s[0] for s in seqs])
        result = [cls]
        while any(seqs):
            seqs = [s for s in seqs if s]
            head = next((s[0] for s in seqs if not any(s[0] in t[1:] for t in seqs)), None)
            if head is None:
                result = [cls, '?MRO를 만들 수 없는 상속 구조']
                break
            result.append(head)
            seqs = [s[1:] if s[0] == head else s for s in seqs]
        if not seen:
            mro_cache[cls] = result
        return result

    def owner(start, name, after=None, local_only=False):
        """(class name, target) of method `name` found along the MRO of `start`."""
        seq = mro(start)
        if after is not None:
            seq = seq[seq.index(after) + 1:] if after in seq else []
        for c in seq:
            if isinstance(c, str):
                if local_only:
                    return None, None
                # Stop at an imported parent: its methods are resolved across files, anything beyond is unknown here.
                return (c.split('|')[1], c + '.' + name) if '|' in c and not c.startswith('?') else (None, None)
            found = [m for m in c.body if isinstance(m, FUNCS) and m.name == name]
            if found:
                return c.name, str(found[-1].lineno)
        return None, None

    def method_link(cls, name, exact, sup=False):
        pick = lambda start: owner(start, name, cls if sup else None)[1]
        target = pick(cls)
        if target is None or exact:
            return target
        others = [c.name for c in classes.values() if c is not cls and cls in mro(c) and pick(c) != target]
        if others:
            return f'?자식 클래스 {", ".join(others)}에서 재정의되거나 상속 순서가 달라, 어떤 객체인지에 따라 실행되는 메서드가 달라집니다.'
        return target

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

    # self.attr = ClassName(): trusted only if `attr` is written once in the file and never via setattr.
    attr_stores, attributes = {}, {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and isinstance(n.ctx, (ast.Store, ast.Del)):
            attr_stores[n.attr] = attr_stores.get(n.attr, 0) + 1
        elif isinstance(n, ast.Name) and n.id == 'setattr':
            attr_stores = None
            break
    if attr_stores is not None:
        for c in classes.values():
            for fn in [m for m in c.body if isinstance(m, FUNCS) and m.args.args and not m.decorator_list]:
                self_arg = fn.args.args[0].arg
                for n in ast.walk(fn):
                    if (isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Attribute)
                            and isinstance(n.targets[0].value, ast.Name) and n.targets[0].value.id == self_arg
                            and attr_stores.get(n.targets[0].attr) == 1
                            and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
                            and n.value.func.id in classes):
                        attributes[n.targets[0].attr] = (c, classes[n.value.func.id])
        for c in classes.values():
            for member in c.body:
                names = [member.name] if isinstance(member, (*FUNCS, ast.ClassDef)) else [t.id for t in ast.walk(member) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)]
                for name in names:
                    attributes.pop(name, None)

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
            elif (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Attribute) and isinstance(f.value.value, ast.Name)
                  and f.value.value.id == self_name and f.value.attr in attributes and attributes[f.value.attr][0] in mro(cls)):
                target = method_link(attributes[f.value.attr][1], f.attr, True)
            elif (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Call) and isinstance(f.value.func, ast.Name)
                  and f.value.func.id == 'super' and not f.value.args and cls is not None):
                target = method_link(cls, f.attr, False, sup=True)
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

    def analyse(fn, cls=None, outer_bound=frozenset(), outer_objs=None, self_name=None, method=False):
        nodes = list(function_nodes(fn))
        args = [a for a in ast.walk(fn.args) if isinstance(a, ast.arg)]
        stored = {n.id for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        own = stored | {a.arg for a in args} | {n.name for n in nodes if n is not fn and isinstance(n, (*FUNCS, ast.ClassDef))}
        if method:
            first = fn.args.args[0].arg if fn.args.args and not fn.decorator_list else None
            self_name = first if first and first not in stored else None
        elif self_name in own:
            self_name = None
        rebinding = {name for n in ast.walk(fn) if isinstance(n, ast.Nonlocal) for name in n.names}
        objs = {k: v for k, v in (outer_objs or {}).items() if k not in own}
        objs.update(objects(nodes, args))
        objs = {k: v for k, v in objs.items() if k not in rebinding}
        bound = own | outer_bound
        link(nodes, bound, objs, cls, self_name)
        for nested in nodes:
            if nested is not fn and isinstance(nested, FUNCS):
                analyse(nested, cls, bound, objs, self_name)

    for fn in [n for n in tree.body if isinstance(n, FUNCS)]:
        analyse(fn)
    for cls in classes.values():
        for fn in [n for n in cls.body if isinstance(n, FUNCS)]:
            analyse(fn, cls, method=True)

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
                parent = owner(in_class, child.name, in_class, local_only=True)[0] if in_class and not cls else None
                if parent:
                    kind += f' · 재정의({escape(parent)})'
                name = child.name if cls else f'{child.name}({ast.unparse(child.args)})'
                body = (cards(child, child) or '<p>표시할 멤버가 없습니다.</p>') if cls else code(start, child.end_lineno)
                bases = ''
                for base in child.bases if cls else []:
                    if isinstance(base, ast.Name) and base.id == 'object':
                        continue
                    ref = base_ref(base)
                    if isinstance(ref, ast.ClassDef):
                        target = str(ref.lineno)
                    elif isinstance(ref, str) and not ref.startswith('?'):
                        target = ref
                    else:
                        target = '?이 파일에 정의되지 않은 부모 클래스입니다(외부 라이브러리 또는 다른 파일).'
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


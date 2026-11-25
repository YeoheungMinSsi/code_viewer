"""TypeScript / JavaScript structure and conservative call analysis; never executes source."""
from html import escape

CLASS_TYPES = {'class_declaration', 'abstract_class_declaration', 'class', 'interface_declaration'}
FUNC_TYPES = {'function_declaration', 'generator_function_declaration'}
METHOD_TYPES = {'method_definition', 'abstract_method_signature', 'method_signature'}
FIELD_TYPES = {'public_field_definition', 'field_definition', 'property_signature'}
SCOPE_TYPES = FUNC_TYPES | {'method_definition', 'function_expression', 'arrow_function', 'function'}


def outline(raw, typescript=True):
    from tree_sitter import Language, Parser
    if typescript:
        import tree_sitter_typescript as grammar
        language, lang_name = Language(grammar.language_typescript()), 'TypeScript'
    else:
        import tree_sitter_javascript as grammar
        language, lang_name = Language(grammar.language()), 'JavaScript'
    source = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    data = source.encode()
    root = Parser(language).parse(data).root_node
    if root.has_error:
        bad = next((n for n in walk(root) if n.type == 'ERROR' or n.is_missing), root)
        raise ValueError(f'{bad.start_point.row + 1}행: {lang_name} 구문을 분석할 수 없습니다. 완전한 파일을 확인하세요.')
    lines = source.split('\n')

    def text(n):
        return data[n.start_byte:n.end_byte].decode() if n else ''

    def unwrap(n):
        if n.type == 'export_statement':
            decl = next((c for c in n.named_children if c.type in CLASS_TYPES | FUNC_TYPES | {'lexical_declaration', 'variable_declaration'}), None)
            if decl is not None:
                return decl
        return n

    default_exports = set()
    for n in root.named_children:
        if n.type == 'export_statement' and any(text(c) == 'default' for c in n.children):
            target_node = unwrap(n)
            if target_node is not n:
                default_exports.add(target_node)
            elif n.named_children and n.named_children[0].type == 'identifier':
                default_exports.add(text(n.named_children[0]))

    def fn_var(n):
        if n.type not in ('lexical_declaration', 'variable_declaration'):
            return None
        decls = [d for d in n.named_children if d.type == 'variable_declarator']
        if len(decls) != 1:
            return None
        val = decls[0].child_by_field_name('value')
        if val is not None and val.type in ('arrow_function', 'function_expression'):
            return text(decls[0].child_by_field_name('name')), val
        return None

    top = [unwrap(n) for n in root.named_children]
    classes = {text(n.child_by_field_name('name')): n for n in top if n.type in CLASS_TYPES - {'interface_declaration'}}
    interfaces = {text(n.child_by_field_name('name')): n for n in top if n.type == 'interface_declaration'}
    functions = {text(n.child_by_field_name('name')): n for n in top if n.type in FUNC_TYPES}
    for n in top:
        fv = fn_var(n)
        if fv:
            functions[fv[0]] = n
    # Module-level rebinding hides the declaration: do not claim a target.
    reassigned = {text(n.child_by_field_name('left')) for n in walk(root) if n.type == 'assignment_expression'}
    for name in list(classes) + list(functions):
        if name in reassigned:
            classes.pop(name, None)
            functions.pop(name, None)

    imports = {}
    for n in top:
        if n.type != 'import_statement':
            continue
        module = text(n.child_by_field_name('source')).strip('\'"`').rstrip('/').split('/')[-1]
        module = module.rsplit('.', 1)[0] if module.endswith(('.ts', '.js', '.tsx', '.jsx', '.mjs')) else module
        clause = next((c for c in n.named_children if c.type == 'import_clause'), None)
        for c in (clause.named_children if clause else []):
            if c.type == 'identifier':
                imports[text(c)] = (module, 'default')
            elif c.type == 'namespace_import':
                imports[text(c.named_children[0])] = (module, '')
            elif c.type == 'named_imports':
                for spec in c.named_children:
                    name, alias = spec.child_by_field_name('name'), spec.child_by_field_name('alias')
                    imports[text(alias or name)] = (module, text(name))

    def heritage(cls):
        """[(keyword, node)] for extends / implements."""
        result = []
        for h in [c for c in cls.named_children if c.type in ('class_heritage', 'extends_type_clause')]:
            for part in h.named_children:
                if part.type == 'extends_clause':
                    result += [('extends', v) for v in part.named_children if v.type != 'type_arguments']
                elif part.type == 'implements_clause':
                    result += [('implements', v) for v in part.named_children]
                elif h.type == 'extends_type_clause':
                    result.append(('extends', part))
                else:
                    result.append(('extends', part))
        return result

    def parent_class(cls):
        ext = [n for kw, n in heritage(cls) if kw == 'extends' and cls.type != 'interface_declaration']
        return classes.get(text(ext[0])) if len(ext) == 1 else None

    def external_parent(cls):
        ext = [n for kw, n in heritage(cls) if kw == 'extends']
        if len(ext) != 1 or text(ext[0]) in classes:
            return None
        name = text(ext[0])
        if name in imports and imports[name][1]:
            return imports[name][0], imports[name][1]
        return None

    def lineage(cls):
        chain = []
        while cls is not None and cls not in chain:
            chain.append(cls)
            cls = parent_class(cls)
        return chain

    def members(cls, kinds=METHOD_TYPES):
        body = cls.child_by_field_name('body')
        return [m for m in (body.named_children if body else []) if m.type in kinds]

    def own_method(cls, name):
        found = [m for m in members(cls, {'method_definition'}) if text(m.child_by_field_name('name')) == name]
        return found[-1] if found else None

    def owner(cls, name, skip=0):
        chain = lineage(cls)
        for c in chain[skip:]:
            m = own_method(c, name)
            if m is not None:
                return c, str(m.start_point.row + 1)
        tail = chain[-1] if chain else None
        ext = external_parent(tail) if tail is not None else None
        if ext:
            return None, f'{ext[0]}|{ext[1]}.{name}'
        return None, None

    def descends(child, cls):
        return child is not cls and cls in lineage(child)

    def method_link(cls, name, exact, skip=0):
        target = owner(cls, name, skip)[1]
        if target is None or exact:
            return target
        others = [text(c.child_by_field_name('name')) for c in classes.values() if descends(c, cls) and owner(c, name)[1] != target]
        if others:
            return f'?자식 클래스 {", ".join(others)}에서 재정의되어, 어떤 객체인지에 따라 실행되는 메서드가 달라집니다.'
        return target

    def own_nodes(scope):
        """Descendants of scope, not descending into nested functions/classes."""
        pending = list(scope.named_children)
        while pending:
            n = pending.pop()
            yield n
            if n.type not in SCOPE_TYPES | CLASS_TYPES:
                pending.extend(n.named_children)

    def objects(nodes, params=()):
        stores, found = {}, {}
        for n in nodes:
            if n.type == 'variable_declarator':
                key = text(n.child_by_field_name('name'))
                stores[key] = stores.get(key, 0) + 1
                value = n.child_by_field_name('value')
                if value is not None and value.type == 'new_expression':
                    ctor = text(value.child_by_field_name('constructor'))
                    if ctor in classes:
                        found[key] = (classes[ctor], True)
            elif n.type in ('assignment_expression', 'augmented_assignment_expression'):
                key = text(n.child_by_field_name('left'))
                stores[key] = stores.get(key, 0) + 1
        for p in params:
            pattern, annotation = p.child_by_field_name('pattern'), p.child_by_field_name('type')
            type_name = text(annotation).lstrip(':').strip() if annotation else ''
            if pattern is not None and type_name in classes and stores.get(text(pattern), 0) == 0:
                found[text(pattern)] = (classes[type_name], False)
        return {k: v for k, v in found.items() if stores.get(k, 0) == (1 if v[1] else 0)}

    # this.prop = new ClassName(): trusted only if `prop` is written once in the file.
    prop_writes, prop_types = {}, {}
    for n in walk(root):
        if n.type == 'assignment_expression':
            left = n.child_by_field_name('left')
            if left is not None and left.type == 'member_expression':
                pname = text(left.child_by_field_name('property'))
                prop_writes[pname] = prop_writes.get(pname, 0) + 1
    for cls in classes.values():
        for m in members(cls, {'method_definition'}):
            for n in walk(m):
                if n.type == 'assignment_expression':
                    left, right = n.child_by_field_name('left'), n.child_by_field_name('right')
                    if (left is not None and left.type == 'member_expression'
                            and left.child_by_field_name('object').type == 'this'
                            and right is not None and right.type == 'new_expression'):
                        pname = text(left.child_by_field_name('property'))
                        ctor = text(right.child_by_field_name('constructor'))
                        if prop_writes.get(pname) == 1 and ctor in classes:
                            prop_types[pname] = (cls, classes[ctor])

    calls = {}

    def add(n, target):
        if n.start_point.row == n.end_point.row:
            calls.setdefault(n.start_point.row + 1, []).append((n.start_point.column, n.end_point.column, target))

    def link(nodes, bound, objs, cls=None):
        for n in nodes:
            if n.type == 'new_expression':
                ctor = n.child_by_field_name('constructor')
                name = text(ctor)
                if name in classes and name not in bound:
                    add(ctor, str(classes[name].start_point.row + 1))
                elif name in imports and imports[name][1] and name not in bound:
                    add(ctor, f'{imports[name][0]}|{imports[name][1]}')
                continue
            if n.type != 'call_expression':
                continue
            f, target = n.child_by_field_name('function'), None
            if f.type == 'super' and cls is not None:
                target = owner(cls, 'constructor', 1)[1]
            elif f.type == 'identifier' and text(f) not in bound:
                name = text(f)
                if name in functions:
                    target = str(functions[name].start_point.row + 1)
                elif name in imports and imports[name][1]:
                    target = f'{imports[name][0]}|{imports[name][1]}'
            elif f.type == 'member_expression':
                obj, prop = f.child_by_field_name('object'), text(f.child_by_field_name('property'))
                if obj.type == 'this' and cls is not None:
                    target = method_link(cls, prop, False)
                elif obj.type == 'super' and cls is not None:
                    target = method_link(cls, prop, True, 1)
                elif obj.type == 'member_expression' and obj.child_by_field_name('object').type == 'this' and cls is not None:
                    pname = text(obj.child_by_field_name('property'))
                    if pname in prop_types and prop_types[pname][0] in lineage(cls):
                        target = method_link(prop_types[pname][1], prop, True)
                elif obj.type == 'identifier' and text(obj) in objs:
                    target = method_link(objs[text(obj)][0], prop, objs[text(obj)][1])
                elif obj.type == 'identifier' and text(obj) not in bound and imports.get(text(obj), ('', 'x'))[1] == '':
                    target = f'{imports[text(obj)][0]}|{prop}'
            if target:
                add(f, target)

    def analyse(scope, cls=None, outer_bound=frozenset(), outer_objs=None):
        nodes = list(own_nodes(scope))
        params_node = scope.child_by_field_name('parameters')
        params = [p for p in (params_node.named_children if params_node else []) if p.type in ('required_parameter', 'optional_parameter')]
        own = {text(n.child_by_field_name('name')) for n in nodes if n.type == 'variable_declarator' and not (scope is root and text(n.child_by_field_name('name')) in functions)}
        own |= {text(p.child_by_field_name('pattern')) for p in params}
        own |= {text(p) for p in (params_node.named_children if params_node else []) if p.type == 'identifier'}
        if scope is not root:
            own |= {text(n.child_by_field_name('name')) for n in nodes if n.type in FUNC_TYPES | CLASS_TYPES}
        objs = {k: v for k, v in (outer_objs or {}).items() if k not in own}
        objs.update(objects(nodes, params))
        bound = own | outer_bound
        link(nodes, bound, objs, cls)
        for nested in nodes:
            if nested.type in SCOPE_TYPES | {'function_declaration'}:
                analyse(nested, cls, bound, objs)

    module_scope = root
    analyse(module_scope)
    for cls in classes.values():
        for m in members(cls, {'method_definition'}):
            analyse(m, cls)
        for field in members(cls, {'public_field_definition', 'field_definition'}):
            analyse(field, cls)

    for n in walk(root):
        if n.type == 'call_expression':
            f = n.child_by_field_name('function')
            row = f.start_point.row + 1
            if f.start_point.row == f.end_point.row and not any(left == f.start_point.column for left, _, _ in calls.get(row, [])):
                reason = '객체·동적 호출: 정적 분석으로 대상을 확정할 수 없습니다.' if f.type == 'member_expression' else '내장 함수 또는 현재 분석 범위에서 정의를 확인할 수 없는 호출입니다.'
                calls.setdefault(row, []).append((f.start_point.column, f.end_point.column, '?' + reason))

    def code(start, end):
        result = []
        for number in range(start, end + 1):
            line = lines[number - 1].encode()
            parts, cursor = [], 0
            for left, right, target in sorted(set(calls.get(number, []))):
                if left < cursor:
                    continue
                parts.append(escape(line[cursor:left].decode()))
                title = target[1:] if target.startswith('?') else '호출 연결 확인: 클릭하면 점선으로 표시합니다.'
                parts.append(f'<button class="call" data-target="{escape(target, quote=True)}" title="{escape(title, quote=True)}">{escape(line[left:right].decode())}</button>')
                cursor = right
            parts.append(escape(line[cursor:].decode()))
            result.append(f'<i>{number}</i>' + ''.join(parts))
        return '<pre>' + '\n'.join(result) + '</pre>'

    def span(n):
        return code(n.start_point.row + 1, n.end_point.row + 1)

    def card(n, css, kind, name, label, body, extra=''):
        default_attr = ' data-default="true"' if (n in default_exports or name in default_exports) else ''
        return (f'<details class="{css}" data-name="{escape(name, quote=True)}" data-line="{n.start_point.row + 1}"{default_attr}>'
                f'<summary><small>{kind}</small> <b>{escape(label)}</b> <em>L{n.start_point.row + 1}</em>{extra}</summary>{body}</details>')

    def class_card(cls):
        name = text(cls.child_by_field_name('name'))
        kind = {'interface_declaration': '인터페이스', 'abstract_class_declaration': '추상 클래스'}.get(cls.type, '클래스')
        items = []
        body = cls.child_by_field_name('body')
        for m in (body.named_children if body else []):
            if m.type in METHOD_TYPES:
                mname = text(m.child_by_field_name('name'))
                params = text(m.child_by_field_name('parameters'))
                if mname == 'constructor':
                    label = '생성자'
                elif m.type == 'method_definition':
                    label = '메서드'
                else:
                    label = '추상 메서드' if m.type == 'abstract_method_signature' else '메서드 선언'
                parent = owner(cls, mname, 1)[0] if cls.type != 'interface_declaration' and mname != 'constructor' else None
                if parent is not None:
                    label += f' · 재정의({text(parent.child_by_field_name("name"))})'
                items.append(card(m, 'fn', label, mname, mname + params, span(m)))
            elif m.type in FIELD_TYPES:
                fname = text(m.child_by_field_name('name') or m.named_children[0])
                kind_label = '클래스 변수' if any(text(c) == 'static' for c in m.children) else '인스턴스 변수'
                items.append(card(m, 'var', kind_label, fname, fname, span(m)))
        buttons = ''
        for kw, base in heritage(cls):
            bname = text(base)
            if bname in classes:
                target = str(classes[bname].start_point.row + 1)
            elif bname in interfaces:
                target = str(interfaces[bname].start_point.row + 1)
            elif bname in imports and imports[bname][1]:
                target = f'{imports[bname][0]}|{imports[bname][1]}'
            else:
                target = '?이 파일에 정의되지 않은 상위 타입입니다(외부 라이브러리 또는 불러오지 않은 파일).'
            buttons += f'<button class="call inheritance" data-target="{escape(target, quote=True)}" title="상속·구현 관계: 상위 타입의 기능을 물려받거나 구현합니다.">{kw} {escape(bname)}</button>'
        return card(cls, 'cls', kind, name, name, '<section>' + ''.join(items) + '</section>' if items else '<p>표시할 멤버가 없습니다.</p>', buttons)

    def has_call(n):
        return any(c.type in ('call_expression', 'new_expression', 'await_expression') for c in walk(n))

    items, run = [], []

    def flush():
        if run:
            first, last = run[0], run[-1]
            items.append(f'<details class="entry"><summary><small>실행 시작점</small><b>여기서 시작</b><em>L{first.start_point.row + 1}</em></summary>'
                         f'{code(first.start_point.row + 1, last.end_point.row + 1)}</details>')
            run.clear()

    import_nodes = [n for n in top if n.type == 'import_statement']
    if import_nodes:
        body = '\n'.join(span(n)[5:-6] for n in import_nodes)
        items.append(f'<details class="imp"><summary><small>import</small><b>가져오기 · {len(import_nodes)}개 선언</b><em>L{import_nodes[0].start_point.row + 1}</em></summary><pre>{body}</pre></details>')
    for n in top:
        if n.type in ('import_statement', 'comment', 'type_alias_declaration'):
            continue
        if n.type in CLASS_TYPES:
            flush()
            items.append(class_card(n))
        elif n.type in FUNC_TYPES:
            flush()
            name = text(n.child_by_field_name('name'))
            kind = '비동기 함수' if any(text(c) == 'async' for c in n.children) else '함수'
            items.append(card(n, 'fn', kind, name, name + text(n.child_by_field_name('parameters')), span(n)))
        elif fn_var(n):
            flush()
            name, fn_node = fn_var(n)
            kind = '비동기 함수' if any(text(c) == 'async' for c in fn_node.children) else '함수'
            params = fn_node.child_by_field_name('parameters') or fn_node.child_by_field_name('parameter')
            sig = name + (text(params) if params and text(params).startswith('(') else f'({text(params)})' if params else '()')
            items.append(card(n, 'fn', kind, name, sig, span(n)))
        elif n.type in ('lexical_declaration', 'variable_declaration') and not has_call(n):
            flush()
            names = ', '.join(text(d.child_by_field_name('name')) for d in n.named_children if d.type == 'variable_declarator')
            items.append(card(n, 'var', '전역변수', names, names, span(n)))
        elif n.type == 'export_statement':
            continue
        else:
            run.append(n)
    flush()
    return '<section>' + ''.join(items) + '</section>' if items else '<p>클래스나 함수가 없어 원문을 표시합니다.</p>' + code(1, len(lines))


def outline_js(raw):
    return outline(raw, typescript=False)


def walk(n):
    yield n
    for c in n.named_children:
        yield from walk(c)

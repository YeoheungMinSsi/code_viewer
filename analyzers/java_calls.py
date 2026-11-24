"""Conservative, same-compilation-unit Java call resolution (no source execution)."""
from collections import Counter
import javalang as java


def node_id(node):
    return f'J{node.position.line}_{node.position.column}'


def type_name(node):
    if node is None:
        return None
    parts = [node.name]
    child = getattr(node, 'sub_type', None)
    while child:
        parts.append(child.name)
        child = child.sub_type
    return '.'.join(parts) + '[]' * len(node.dimensions or [])


def signature(method):
    return method.name + '(' + ', '.join(type_name(p.type) + ('...' if p.varargs else '') for p in method.parameters) + ')'


def analyze_calls(unit, tokens):
    TYPE_NODES = (java.tree.ClassDeclaration, java.tree.InterfaceDeclaration, java.tree.EnumDeclaration)
    types = [node for _, node in unit.filter(java.tree.TypeDeclaration) if isinstance(node, TYPE_NODES)]
    classes = [node for node in types if isinstance(node, java.tree.ClassDeclaration)]
    counts = Counter(c.name for c in types)
    by_name = {c.name: c for c in types if counts[c.name] == 1}
    imported = {}
    wildcards = []
    pkg = unit.package.name if unit.package else ''
    for imp in (unit.imports or []):
        if imp.static or not imp.path:
            continue
        if imp.wildcard:
            wildcards.append(imp.path)
        else:
            imported[imp.path.split('.')[-1]] = imp.path
    links = {}
    inheritance = {}
    overrides = {}
    primitive = {'byte': ['short', 'int', 'long', 'float', 'double'], 'short': ['int', 'long', 'float', 'double'],
                 'char': ['int', 'long', 'float', 'double'], 'int': ['long', 'float', 'double'],
                 'long': ['float', 'double'], 'float': ['double'], 'double': [], 'boolean': []}
    BUILTIN = set(primitive) | {'Object', 'String', 'System', 'Math', 'Integer', 'Long', 'Double', 'Boolean', 'Float', 'Short', 'Byte', 'Character', 'Exception', 'RuntimeException', 'Throwable', 'Error', 'null'}

    def external_hint(tname):
        """Return module hint(s) for a type outside this file, or None if no import/package context exists."""
        if not tname or tname in by_name or tname in BUILTIN or tname.endswith('[]'):
            return None
        if tname in imported:
            return imported[tname]
        scopes = ([pkg] if pkg else []) + wildcards
        return ','.join(f'{s}.{tname}' for s in scopes) if scopes else None

    def cross_method_target(hint, tname, method_name, arg_types):
        sig = method_name if any(a is None for a in arg_types) else f'{method_name}({",".join(arg_types)})'
        return f'{hint}|{tname}.{sig}'

    def type_parents(node):
        """Return list of (keyword, parent_name) for extends/implements on a class, interface, or enum."""
        result = []
        ext = getattr(node, 'extends', None)
        if isinstance(ext, list):
            result.extend(('extends', type_name(e)) for e in ext if e)
        elif ext:
            result.append(('extends', type_name(ext)))
        for impl in (getattr(node, 'implements', None) or []):
            result.append(('implements', type_name(impl)))
        return result

    def chain(cls):
        seen = set()
        queue = [cls] if cls else []
        while queue:
            cur = queue.pop(0)
            if cur is None or cur.name in seen:
                continue
            seen.add(cur.name)
            yield cur
            for _, pname in type_parents(cur):
                parent_node = by_name.get(pname)
                if parent_node and parent_node.name not in seen:
                    queue.append(parent_node)

    def conversion(actual, expected):
        if actual is None:
            return False
        if actual == expected:
            return True
        if actual in primitive:
            return expected in primitive[actual]
        if actual == 'null':
            return expected not in primitive
        if expected == 'Object':
            return True
        if expected == 'Number' and actual in {'Integer', 'Long', 'Double', 'Float', 'Short', 'Byte'}:
            return True
        return any(c.name == expected for c in chain(by_name.get(actual)))

    def match_method(m, arguments, allow_varargs):
        """Return list of resolved parameter types if `m` matches `arguments`, else None."""
        params = m.parameters
        tp_bounds = {tp.name: [type_name(e) for e in (tp.extends or [])] for tp in (m.type_parameters or [])}
        is_varargs = bool(params and params[-1].varargs)
        if is_varargs:
            if not allow_varargs:
                return None
            fixed = params[:-1]
            if len(arguments) < len(fixed):
                return None
            var_elem = type_name(params[-1].type)
            if len(arguments) == len(params) and arguments[-1] == var_elem + '[]':
                expected = [type_name(p.type) for p in fixed] + [var_elem + '[]']
            else:
                expected = [type_name(p.type) for p in fixed] + [var_elem] * (len(arguments) - len(fixed))
        else:
            if len(params) != len(arguments):
                return None
            expected = [type_name(p.type) for p in params]
        bindings = {}
        resolved = []
        for actual, exp in zip(arguments, expected):
            if exp in tp_bounds:
                if actual in primitive:
                    return None
                if actual != 'null':
                    if tp_bounds[exp] and not all(conversion(actual, b) for b in tp_bounds[exp]):
                        return None
                    prev = bindings.get(exp)
                    if prev is None:
                        bindings[exp] = actual
                    elif prev != actual:
                        if conversion(actual, prev):
                            pass
                        elif conversion(prev, actual):
                            bindings[exp] = actual
                        else:
                            return None
                resolved.append(bindings.get(exp, 'Object'))
            else:
                if not conversion(actual, exp):
                    return None
                resolved.append(exp)
        return resolved

    def choose(candidates, arguments):
        names = ', '.join(signature(m) for m in candidates) or '없음'
        if any(a is None for a in arguments):
            return None, '인자 타입을 확정할 수 없습니다. 후보: ' + names
        # JLS §15.12.2: fixed-arity matches take priority over varargs matches.
        for allow_varargs in (False, True):
            matched = []
            for m in candidates:
                resolved = match_method(m, arguments, allow_varargs)
                if resolved is not None:
                    matched.append((m, resolved))
            if not matched:
                continue
            best = [m for m, r in matched if all(m is om or all(conversion(a, b) for a, b in zip(r, or_)) for om, or_ in matched)]
            if len(best) == 1:
                return best[0], '정적 호출 대상: ' + signature(best[0]) + ' · 실제 객체의 오버라이드에 따라 실행 대상은 달라질 수 있습니다.'
            return None, '오버로딩 대상을 확정할 수 없습니다. 후보: ' + names
        return None, '오버로딩 대상을 확정할 수 없습니다. 후보: ' + names

    def methods(cls, name):
        result, seen = [], set()
        for owner in chain(cls):
            for method in owner.methods:
                if method.name != name or signature(method) in seen:
                    continue
                if owner is not cls and 'private' in method.modifiers:
                    continue
                seen.add(signature(method))
                result.append(method)
        return result

    def store(token, target, reason):
        if isinstance(target, str):
            links[(token.position.line, token.position.column - 1)] = (len(token.value), target, reason)
        else:
            links[(token.position.line, token.position.column - 1)] = (len(token.value), node_id(target) if target else '?' + reason, reason)

    def resolve_parent_target(pname):
        parent = by_name.get(pname)
        if parent:
            return node_id(parent)
        hint = external_hint(pname)
        if hint:
            return f'{hint}|{pname}'
        return '?상위 타입이 이 파일에 없거나 이름이 중복됩니다.'

    for cls in types:
        parent_edges = [(kw, resolve_parent_target(pname), pname) for kw, pname in type_parents(cls)]
        if parent_edges:
            inheritance[id(cls)] = parent_edges
        direct_parents = [by_name[pname] for _, pname in type_parents(cls) if pname in by_name]
        parent = by_name.get(type_name(cls.extends)) if isinstance(cls, java.tree.ClassDeclaration) and cls.extends else None
        ext_parent_name = type_name(cls.extends) if isinstance(cls, java.tree.ClassDeclaration) and cls.extends and not parent else None
        imported_parent = ext_parent_name if external_hint(ext_parent_name) else None
        for method in cls.methods:
            if direct_parents and not {'static', 'private'} & method.modifiers and any(signature(m) == signature(method) and not {'static', 'private'} & m.modifiers for p in direct_parents for m in methods(p, method.name)):
                overrides[id(method)] = '오버라이드'
        all_members = list(cls.methods) + list(getattr(cls, 'constructors', []) or [])
        for method in all_members:
            if method.body is None:
                continue
            environment = {}
            for owner in reversed(list(chain(cls))):
                for field in owner.fields:
                    for var in field.declarators:
                        environment[var.name] = type_name(field.type) + '[]' * len(var.dimensions or [])
            environment.update({p.name: type_name(p.type) for p in method.parameters})
            nodes = list(method)
            method_tokens, depth, started = [], 0, False
            for token in tokens:
                if token.position < method.position:
                    continue
                method_tokens.append(token)
                if isinstance(token, java.tokenizer.Separator):
                    if token.value == '{':
                        depth += 1
                        started = True
                    elif token.value == '}':
                        depth -= 1
                        if started and depth == 0:
                            break
            locals_ = [n for _, n in nodes if isinstance(n, java.tree.LocalVariableDeclaration)]
            outer_names = set(environment)
            duplicate = Counter(v.name for n in locals_ for v in n.declarators)
            for declaration in locals_:
                for var in declaration.declarators:
                    environment[var.name] = type_name(declaration.type) + '[]' * len(var.dimensions or []) if duplicate[var.name] == 1 and var.name not in outer_names else None
            # shortcut: local scopes are conservative; use a type checker for full Java name resolution.
            def infer(expr):
                if getattr(expr, 'selectors', None):
                    return None
                if isinstance(expr, java.tree.Literal):
                    value = expr.value
                    if value in ('true', 'false'): return 'boolean'
                    if value == 'null': return 'null'
                    if value.startswith('"'): return 'String'
                    if value.startswith("'"): return 'char'
                    if value.lower().startswith('0x') and 'p' not in value.lower():
                        return 'long' if value.lower().endswith('l') else 'int'
                    if value.lower().endswith('l'): return 'long'
                    if value.lower().endswith('f'): return 'float'
                    if value.lower().endswith('d'): return 'double'
                    return 'double' if any(c in value.lower() for c in ('.', 'e', 'p')) else 'int'
                if isinstance(expr, java.tree.MemberReference) and not expr.qualifier and not expr.selectors:
                    return environment.get(expr.member)
                if isinstance(expr, java.tree.Cast): return type_name(expr.type)
                if isinstance(expr, java.tree.ClassCreator) and not expr.body: return type_name(expr.type)
                return None

            for special_path, invocation in nodes:
                if not isinstance(invocation, (java.tree.SuperMethodInvocation, java.tree.ClassCreator)):
                    continue
                constructor = isinstance(invocation, java.tree.ClassCreator)
                name = type_name(invocation.type) if constructor else invocation.member
                matches = []
                for i, token in enumerate(method_tokens):
                    tail = method_tokens[i:]
                    if constructor and len(tail) >= 3 and token.value == 'new' and tail[1].value == name and tail[2].value == '(':
                        matches.append(tail[1])
                    elif not constructor and len(tail) >= 4 and [t.value for t in tail[:4]] == ['super', '.', name, '(']:
                        matches.append(tail[2])
                if len(matches) != 1:
                    for token in matches:
                        store(token, None, '동일 위치 후보가 여러 개여서 호출을 확정하지 않습니다.')
                    continue
                receiver = by_name.get(name) if constructor else parent
                target, reason = None, '외부·익명 클래스 또는 지원하지 않는 생성자/상위 호출입니다.'
                nested = any(isinstance(n, (java.tree.ClassCreator, java.tree.ClassDeclaration, java.tree.LambdaExpression)) for n in special_path if not isinstance(n, list))
                if receiver and not nested and not (constructor and invocation.body):
                    candidates = (getattr(receiver, 'constructors', []) or []) if constructor else methods(receiver, name)
                    candidates = [m for m in candidates if 'private' not in m.modifiers or (constructor and receiver is cls)]
                    if constructor and not candidates and not invocation.arguments:
                        target, reason = receiver, '기본 생성자: ' + receiver.name
                    else:
                        target, reason = choose(candidates, [infer(arg) for arg in invocation.arguments])
                elif not nested and not (constructor and invocation.body):
                    arg_types = [infer(arg) for arg in invocation.arguments]
                    if constructor and external_hint(name):
                        target, reason = f'{external_hint(name)}|{name}', f'다른 파일 클래스 생성: {name}'
                    elif not constructor and imported_parent:
                        target, reason = cross_method_target(external_hint(imported_parent), imported_parent, name, arg_types), f'다른 파일 상위 메서드 호출: {imported_parent}.{name}'
                store(matches[0], target, reason)

            for path, call in nodes:
                if not isinstance(call, java.tree.MethodInvocation):
                    continue
                if not call.position:
                    continue
                nearby = [t for t in tokens if t.position >= call.position]
                name_token = next((t for i, t in enumerate(nearby[:20]) if t.value == call.member and i+1 < len(nearby) and nearby[i+1].value == '('), None)
                if name_token is None:
                    continue
                nested = any(isinstance(n, (java.tree.ClassDeclaration, java.tree.ClassCreator, java.tree.LambdaExpression, java.tree.MethodDeclaration)) and n is not method for n in path if not isinstance(n, list))
                if nested:
                    store(name_token, None, '중첩·익명 클래스 및 람다 호출은 아직 해석하지 않습니다.')
                    continue
                is_this = any(isinstance(n, java.tree.This) for n in path if not isinstance(n, list))
                selector = any(isinstance(n, (java.tree.MethodInvocation, java.tree.ClassCreator)) for n in path if not isinstance(n, list))
                qualifier = call.qualifier or ''
                class_receiver = qualifier in by_name and qualifier not in environment
                receiver_type = qualifier if (external_hint(qualifier) and qualifier not in environment) else environment.get(qualifier)
                receiver = cls if not qualifier or qualifier == 'this' or is_this else by_name.get(qualifier if class_receiver else receiver_type)
                this_chain = any(isinstance(n, java.tree.This) and n.selectors and n.selectors[0] is not call for n in path if not isinstance(n, list))
                if selector or this_chain:
                    store(name_token, None, '외부·동적 객체 또는 연속 호출의 타입을 확인할 수 없습니다.')
                    continue
                arg_types = [infer(arg) for arg in call.arguments]
                if receiver is None:
                    hint = external_hint(receiver_type)
                    if hint:
                        store(name_token, cross_method_target(hint, receiver_type, call.member, arg_types), f'다른 파일 호출 대상: {receiver_type}.{call.member}')
                    else:
                        store(name_token, None, '외부·동적 객체 또는 연속 호출의 타입을 확인할 수 없습니다.')
                    continue
                hierarchy = list(chain(receiver))
                missing_parent = any(pname != 'Object' and pname not in by_name for h in hierarchy for _, pname in type_parents(h))
                if missing_parent:
                    imported_ancestor = next((pname for h in hierarchy for _, pname in type_parents(h) if external_hint(pname)), None)
                    local_match = [m for m in methods(receiver, call.member) if 'private' not in m.modifiers or m in cls.methods]
                    if not local_match and imported_ancestor:
                        store(name_token, cross_method_target(external_hint(imported_ancestor), imported_ancestor, call.member, arg_types), f'다른 파일 상위 메서드 호출: {imported_ancestor}.{call.member}')
                    else:
                        store(name_token, None, '상위 클래스가 미등록이거나 상속 순환이 있어 후보를 확정할 수 없습니다.')
                    continue
                candidates = [m for m in methods(receiver, call.member) if 'private' not in m.modifiers or m in cls.methods]
                if class_receiver or (not qualifier and not is_this and 'static' in method.modifiers):
                    candidates = [m for m in candidates if 'static' in m.modifiers]
                target, reason = choose(candidates, [infer(arg) for arg in call.arguments])
                store(name_token, target, reason)
    return links, inheritance, overrides

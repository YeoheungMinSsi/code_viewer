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
    classes = [node for _, node in unit.filter(java.tree.ClassDeclaration)]
    counts = Counter(c.name for c in classes)
    by_name = {c.name: c for c in classes if counts[c.name] == 1}
    links = {}
    inheritance = {}
    overrides = {}
    primitive = {'byte': ['short', 'int', 'long', 'float', 'double'], 'short': ['int', 'long', 'float', 'double'],
                 'char': ['int', 'long', 'float', 'double'], 'int': ['long', 'float', 'double'],
                 'long': ['float', 'double'], 'float': ['double'], 'double': [], 'boolean': []}

    def chain(cls):
        seen = set()
        while cls and cls.name not in seen:
            seen.add(cls.name)
            yield cls
            cls = by_name.get(type_name(cls.extends)) if cls.extends else None

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
        return any(c.name == expected for c in chain(by_name.get(actual)))

    def choose(candidates, arguments):
        names = ', '.join(signature(m) for m in candidates) or '없음'
        if any(a is None for a in arguments):
            return None, '인자 타입을 확정할 수 없습니다. 후보: ' + names
        # Boxing, varargs and generic inference need compiler-level type information.
        if any(m.type_parameters or any(p.varargs or getattr(p.type, 'arguments', None) for p in m.parameters) for m in candidates):
            return None, '제네릭·가변 인자 해석은 미지원입니다. 후보: ' + names
        matching = [m for m in candidates if len(m.parameters) == len(arguments) and all(conversion(a, type_name(p.type)) for a, p in zip(arguments, m.parameters))]
        best = [m for m in matching if all(m is other or all(conversion(type_name(p.type), type_name(q.type)) for p, q in zip(m.parameters, other.parameters)) for other in matching)]
        if len(best) != 1:
            return None, '오버로딩 대상을 확정할 수 없습니다. 후보: ' + names
        return best[0], '정적 호출 대상: ' + signature(best[0]) + ' · 실제 객체의 오버라이드에 따라 실행 대상은 달라질 수 있습니다.'

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
        links[(token.position.line, token.position.column - 1)] = (len(token.value), node_id(target) if target else '?' + reason, reason)

    for cls in classes:
        parent = by_name.get(type_name(cls.extends)) if cls.extends else None
        if cls.extends:
            inheritance[id(cls)] = (node_id(parent) if parent else '?상위 클래스가 이 파일에 없거나 이름이 중복됩니다.', type_name(cls.extends))
        for method in cls.methods:
            if parent and not {'static', 'private'} & method.modifiers and any(signature(m) == signature(method) and not {'static', 'private'} & m.modifiers for m in methods(parent, method.name)):
                overrides[id(method)] = '오버라이드'
        for method in cls.methods + cls.constructors:
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
                    candidates = receiver.constructors if constructor else methods(receiver, name)
                    candidates = [m for m in candidates if 'private' not in m.modifiers or (constructor and receiver is cls)]
                    if constructor and not candidates and not invocation.arguments:
                        target, reason = receiver, '기본 생성자: ' + receiver.name
                    else:
                        target, reason = choose(candidates, [infer(arg) for arg in invocation.arguments])
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
                receiver = cls if not qualifier or qualifier == 'this' or is_this else by_name.get(qualifier if class_receiver else environment.get(qualifier))
                this_chain = any(isinstance(n, java.tree.This) and n.selectors and n.selectors[0] is not call for n in path if not isinstance(n, list))
                if selector or this_chain or receiver is None:
                    store(name_token, None, '외부·동적 객체 또는 연속 호출의 타입을 확인할 수 없습니다.')
                    continue
                hierarchy = list(chain(receiver))
                if hierarchy[-1].extends and type_name(hierarchy[-1].extends) != 'Object':
                    store(name_token, None, '상위 클래스가 미등록이거나 상속 순환이 있어 후보를 확정할 수 없습니다.')
                    continue
                candidates = [m for m in methods(receiver, call.member) if 'private' not in m.modifiers or m in cls.methods]
                if class_receiver or (not qualifier and not is_this and 'static' in method.modifiers):
                    candidates = [m for m in candidates if 'static' in m.modifiers]
                target, reason = choose(candidates, [infer(arg) for arg in call.arguments])
                store(name_token, target, reason)
    return links, inheritance, overrides

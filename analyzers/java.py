"""Java 8 structure parser. Source is parsed, never compiled or executed."""
from html import escape


def outline(raw):
    try:
        import javalang as java
    except ImportError as exc:
        raise ValueError('Java 분석기 설치가 필요합니다: python -m pip install -r requirements.txt') from exc

    source = raw.decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
    lines = source.split('\n')
    try:
        tokens = list(java.tokenizer.tokenize(source))
        unit = java.parser.Parser(tokens).parse()
    except (java.parser.JavaSyntaxError, java.tokenizer.LexerError, TypeError, IndexError) as exc:
        position = getattr(getattr(exc, 'at', None), 'position', None)
        line = position.line if position else 1
        raise ValueError(f'{line}행: Java 구문을 분석할 수 없습니다. Java 8 문법과 완전한 파일을 사용하세요.') from exc

    from .java_calls import analyze_calls, node_id
    links, inheritance, overrides = analyze_calls(unit, tokens)

    def render_line(number):
        line, cursor, parts = lines[number-1], 0, []
        for (row, column), (length, target, title) in sorted(links.items()):
            if row != number or column < cursor:
                continue
            parts.append(escape(line[cursor:column]))
            parts.append(f'<button class="call" data-target="{escape(target, quote=True)}" title="{escape(title, quote=True)}">{escape(line[column:column+length])}</button>')
            cursor = column + length
        parts.append(escape(line[cursor:]))
        return f'<i>{number}</i>' + ''.join(parts)

    def block(node):
        start = node.position.line
        depth = 0
        opened = False
        field = isinstance(node, (java.tree.FieldDeclaration, java.tree.Import, java.tree.PackageDeclaration))
        end = start
        for token in tokens:
            if token.position < node.position:
                continue
            end = token.position.line
            # String literals and comments cannot terminate a declaration.
            if not isinstance(token, java.tokenizer.Separator):
                continue
            if token.value == '{':
                depth += 1
                opened = True
            elif token.value == '}':
                depth -= 1
                if opened and depth == 0 and not field:
                    break
            elif token.value == ';' and depth == 0:
                break
        return '<pre>' + '\n'.join(render_line(n) for n in range(start, end + 1)) + '</pre>'

    def card(node, css, kind, name, body):
        return (f'<details class="{css}" data-line="{node_id(node)}" data-name="{escape(name, quote=True)}">'
                f'<summary><small>{kind}</small><b>{escape(name)}</b><em>L{node.position.line}</em></summary>{body}</details>')

    def class_card(node):
        members = []
        for member in node.body:
            if isinstance(member, java.tree.ClassDeclaration):
                members.append(class_card(member))
            elif isinstance(member, java.tree.FieldDeclaration):
                kind = '클래스 변수' if 'static' in member.modifiers else '인스턴스 변수'
                members.append(card(member, 'var', kind, ', '.join(d.name for d in member.declarators), block(member)))
            elif isinstance(member, (java.tree.MethodDeclaration, java.tree.ConstructorDeclaration)):
                constructor = isinstance(member, java.tree.ConstructorDeclaration)
                main = (not constructor and member.name == 'main' and {'public', 'static'} <= member.modifiers
                        and member.return_type is None and len(member.parameters) == 1
                        and member.parameters[0].type.name == 'String'
                        and (len(member.parameters[0].type.dimensions or []) == 1 or member.parameters[0].varargs))
                label = '실행 시작점 · main' if main else ('생성자' if constructor else '메서드')
                if id(member) in overrides:
                    label += ' · ' + overrides[id(member)]
                signature = member.name + '(' + ', '.join(p.type.name + ('[]' * len(p.type.dimensions or [])) + ('...' if p.varargs else '') + ' ' + p.name for p in member.parameters) + ')'
                members.append(card(member, 'fn entry' if main else 'fn', label, signature, block(member)))
            else:
                raise ValueError('현재 Java 분석기는 클래스·필드·생성자·메서드를 지원합니다. 초기화 블록이나 기타 선언은 아직 지원하지 않습니다.')
        result = card(node, 'cls', '클래스', node.name, '<section>' + ''.join(members) + '</section>')
        if id(node) in inheritance:
            target, name = inheritance[id(node)]
            button = f'<button class="call inheritance" data-target="{escape(target, quote=True)}" title="상속 관계: 부모 클래스의 기능을 물려받습니다.">extends {escape(name)}</button>'
            result = result.replace('</summary>', button + '</summary>', 1)
        return result

    items = []
    if unit.package:
        items.append(card(unit.package, 'imp', '패키지', unit.package.name, block(unit.package)))
    if unit.imports:
        body = '<pre>' + '\n'.join(block(node)[5:-6] for node in unit.imports) + '</pre>'
        items.append(card(unit.imports[0], 'imp', 'import', f'가져오기 · {len(unit.imports)}개 선언', body))
    for node in unit.types:
        if not isinstance(node, java.tree.ClassDeclaration):
            raise ValueError('현재 Java 분석기는 class 선언을 지원합니다. interface·enum·annotation 선언은 아직 지원하지 않습니다.')
        items.append(class_card(node))
    return '<section>' + ''.join(items) + '</section>' if items else '<pre>' + escape(source) + '</pre>'

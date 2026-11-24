"""C# syntax structure and conservative same-type calls; never executes source."""
from html import escape


def outline(raw):
    from tree_sitter import Language, Parser
    import tree_sitter_c_sharp
    raw = raw.decode('utf-8-sig').encode()
    root = Parser(Language(tree_sitter_c_sharp.language())).parse(raw).root_node
    if root.has_error:
        raise ValueError('C# 문법을 분석할 수 없습니다. 완전한 파일을 확인하세요.')
    def text(n):
        return raw[n.start_byte:n.end_byte].decode() if n else ''
    def walk(n):
        yield n
        for c in n.named_children:
            yield from walk(c)
    types = {'class_declaration', 'struct_declaration', 'interface_declaration', 'record_declaration', 'enum_declaration'}
    methods = {'method_declaration', 'constructor_declaration', 'local_function_statement'}
    nodes = list(walk(root))
    def ident(n):
        return 'CS' + str(n.start_byte)
    def owner(n):
        n = n.parent
        while n and n.type not in types:
            n = n.parent
        return n
    from .csharp_calls import Project
    resolved = Project({'': raw.decode()}).links()['']
    links = [(item['start'], item['end'], item['target'][1] if item['target'] else '?' + item['reason'], token, item['reason'])
             for token, item in resolved.items() if not any(n.type == 'base_list' and n.start_byte <= item['start'] < n.end_byte for n in nodes)]
    links.sort(key=lambda item: (item[0], -item[1]))
    def code(n):
        cursor = n.start_byte
        parts = []
        for start, end, target, token, reason in links:
            if start < cursor or end > n.end_byte:
                continue
            parts.extend([escape(raw[cursor:start].decode()), f'<button class="call" data-cs-call="{token}" data-target="{escape(target, quote=True)}" title="{escape(reason, quote=True)}">{escape(raw[start:end].decode())}</button>'])
            cursor = end
        parts.append(escape(raw[cursor:n.end_byte].decode()))
        return '<pre>' + ''.join(parts) + '</pre>'
    def card(n, css, label, name, body):
        return f'<details class="{css}" data-line="{ident(n)}" data-name="{escape(name, quote=True)}"><summary><small>{label}</small><b>{escape(name)}</b><em>L{n.start_point.row+1}</em></summary>{body}</details>'
    def render(n):
        name = text(n.child_by_field_name('name'))
        if n.type in types:
            body = n.child_by_field_name('body')
            content = ''.join(render(c) for c in body.named_children) if body else ''
            result = card(n, 'cls', n.type.replace('_declaration', ''), name, '<section>'+content+'</section>')
            bases = next((c for c in n.named_children if c.type == 'base_list'), None)
            if bases:
                buttons = []
                for base in bases.named_children:
                    item = resolved.get(ident(base))
                    target = item['target'][1] if item and item['target'] else '?상위 타입이 미등록이거나 중복됩니다.'
                    buttons.append(f'<button class="call inheritance" data-cs-call="{ident(base)}" data-target="{escape(target, quote=True)}" title="상속·인터페이스 구현">{escape(text(base))}</button>')
                result = result.replace('</summary>', ''.join(buttons)+'</summary>', 1)
            return result
        if n.type in methods:
            signature = name + text(n.child_by_field_name('parameters'))
            entry = name == 'Main' and any(text(c) == 'static' for c in n.children)
            return card(n, 'fn entry' if entry else 'fn', '시작점' if entry else '메서드·생성자', signature, code(n))
        if n.type in {'field_declaration', 'property_declaration', 'event_field_declaration', 'enum_member_declaration'}:
            return card(n, 'var', '필드·프로퍼티', name or text(n).split('=')[0].strip(), code(n))
        if n.type == 'global_statement':
            return card(n, 'entry', '최상위 실행문', '시작점', code(n))
        if n.type in {'using_directive', 'file_scoped_namespace_declaration'}:
            return card(n, 'imp', 'using·namespace', text(n), code(n))
        if n.type in {'compilation_unit', 'namespace_declaration', 'declaration_list'}:
            body = n.child_by_field_name('body')
            children = body.named_children if body else n.named_children
            imports = [c for c in children if c.type == 'using_directive']
            group = card(imports[0], 'imp', 'using', f'가져오기 · {len(imports)}개 선언', ''.join(code(c) for c in imports)) if imports else ''
            return group + ''.join(render(c) for c in children if c.type != 'using_directive')
        if n.type.endswith('_declaration'):
            return card(n, 'var', '기타 선언', name or n.type, code(n))
        return ''
    return '<section>' + render(root) + '</section>'

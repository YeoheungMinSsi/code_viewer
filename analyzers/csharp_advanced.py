"""C# constraints, extension visibility and bounded reflection analysis."""
import json
import re

# Imported by Project only after its syntax helpers have been defined.
from .csharp_calls import TYPES, METHODS, ancestor, field, key, modifiers, text, walk

VALUE_TYPES = {'bool','char','sbyte','byte','short','ushort','int','uint','long','ulong','float','double','decimal'}


def namespace(project, path, node):
    names=[]
    current=node
    while current:
        if current.type=='namespace_declaration': names.insert(0,text(field(current,'name')))
        current=current.parent
    file_ns=next((text(field(n,'name')) for n in project.units[path].named_children if n.type=='file_scoped_namespace_declaration'),'')
    return '.'.join(([file_ns] if file_ns else [])+names)


def extension_tiers(project, path, call, name):
    """Search inner namespaces before outer ones, honoring scoped/global using."""
    current=namespace(project,path,call)
    imports=[]
    for file,root in project.units.items():
        for node in walk(root):
            if node.type!='using_directive': continue
            raw=text(node)
            global_using=raw.startswith('global using ')
            if not global_using and (file!=path or not node.parent.start_byte<=call.start_byte<=node.parent.end_byte): continue
            match=re.fullmatch(r'(?:global\s+)?using\s+([\w.]+)\s*;',raw)
            if match: imports.append((namespace(project,file,node) if not global_using else '',match[1]))
    groups=[]
    while True:
        groups.append({current})
        groups.append({imported for owner,imported in imports if owner==current})
        if not current: break
        current=current.rpartition('.')[0]
    result=[]
    for group in groups:
        candidates=[]
        for entries in project.types.values():
            if len(entries)!=1: continue
            source,node=entries[0]
            if 'file' in modifiers(node) and source!=path: continue
            if 'static' not in modifiers(node) or field(node,'type_parameters') or ancestor(node,TYPES): continue
            if namespace(project,source,node) not in group: continue
            body=field(node,'body')
            for method in body.named_children if body else []:
                if method.type!='method_declaration' or text(field(method,'name'))!=name: continue
                mods=modifiers(method)
                params=field(method,'parameters').named_children
                if 'static' in mods and mods & {'public','internal'} and params and 'this' in modifiers(params[0]):
                    candidates.append((source,method))
        if candidates: result.append(candidates)
    return result


def stable_initializer(name, site):
    """Only a same-block local with no writes, ref escapes or closure capture."""
    scope=ancestor(site,METHODS | {'global_statement'})
    if scope and scope.type=='global_statement': scope=scope.parent
    if not scope: return None
    declarations=[n for n in walk(scope) if n.type=='variable_declarator' and text(field(n,'name'))==name]
    if len(declarations)!=1: return None
    declaration=declarations[0]
    if declaration.end_byte>=site.start_byte or ancestor(declaration,{'block'})!=ancestor(site,{'block'}): return None
    for node in walk(scope):
        if node.type=='assignment_expression' and text(field(node,'left'))==name: return None
        if node.type in {'prefix_unary_expression','postfix_unary_expression'} and any(text(c)==name for c in node.named_children): return None
        if node.type=='argument' and any(c.type in {'ref','out','in'} for c in node.children) and any(text(c)==name for c in node.named_children): return None
        if node.type in {'lambda_expression','anonymous_method_expression','local_function_statement'} and any(n.type=='identifier' and text(n)==name for n in walk(node)): return None
    children=declaration.named_children
    return children[-1] if len(children)>1 else None


def is_dynamic_expression(node, site):
    if not node or node.type!='identifier': return False
    scope=ancestor(site,METHODS | {'global_statement'})
    if scope and scope.type=='global_statement': scope=scope.parent
    if not scope: return False
    name=text(node)
    return any((n.type=='variable_declarator' and text(field(n,'name'))==name and text(field(n.parent,'type'))=='dynamic') or
               (n.type=='parameter' and text(field(n,'name'))==name and text(field(n,'type'))=='dynamic') for n in walk(scope))


def value_type(project, name):
    entries=project.types.get(name,[])
    return name in VALUE_TYPES or (len(entries)==1 and (entries[0][1].type=='struct_declaration' or re.search(r'\brecord\s+struct\b',text(entries[0][1])) is not None))


def unmanaged(project, name, seen=None):
    if name in VALUE_TYPES: return True
    seen=set() if seen is None else seen
    if name in seen or not value_type(project,name): return False
    seen.add(name)
    path,node=project.types[name][0]
    body=field(node,'body')
    if not body: return False
    for member in body.named_children:
        if 'static' in modifiers(member): continue
        if member.type=='field_declaration':
            declared=next((n for n in member.named_children if n.type=='variable_declaration'),None)
        elif member.type=='property_declaration': declared=member
        else: continue
        field_type=project.type_name(text(field(declared,'type')),path,member)
        if not unmanaged(project,field_type,seen.copy()): return False
    return True


def default_constructor(project, name):
    if value_type(project,name): return True
    entries=project.types.get(name,[])
    if len(entries)!=1: return False
    _,node=entries[0]
    if node.type not in {'class_declaration','record_declaration'} or 'abstract' in modifiers(node): return False
    primary=field(node,'parameters')
    if primary and primary.named_children: return False
    body=field(node,'body')
    constructors=[n for n in body.named_children if n.type=='constructor_declaration' and 'static' not in modifiers(n)] if body else []
    return not constructors or any('public' in modifiers(n) and not field(n,'parameters').named_children for n in constructors)


def constraints_satisfied(project, path, method, substitutions):
    for clause in method.named_children:
        if clause.type!='type_parameter_constraints_clause': continue
        variable=text(clause.named_children[0])
        actual=substitutions.get(variable)
        if not actual or actual=='null': return False
        for constraint in clause.named_children[1:]:
            raw=text(constraint).strip()
            if raw in {'class','class?'}:
                if not project.conversion('null',actual): return False
            elif raw=='struct':
                if not value_type(project,actual): return False
            elif raw=='unmanaged':
                if not unmanaged(project,actual): return False
            elif raw=='notnull':
                if actual.endswith('?'): return False
            elif re.fullmatch(r'new\s*\(\s*\)',raw):
                if not default_constructor(project,actual): return False
            else:
                target=substitutions.get(raw) or project.type_name(raw,path,method)
                if not target or (actual!=target and not project.conversion(actual,target)): return False
    return True


def follow_local(node, site, depth=0):
    if node is None or depth>8: return None
    if node.type!='identifier': return node
    initializer=stable_initializer(text(node),site)
    return follow_local(initializer,initializer,depth+1) if initializer else None


def reflection_target(project, path, call):
    """Resolve only typeof(T).GetMethod(literal[, typeof-array]).Invoke(...)."""
    function=field(call,'function')
    if not function or function.type!='member_access_expression' or text(field(function,'name'))!='Invoke': return None
    lookup=follow_local(field(function,'expression'),call)
    if not lookup or lookup.type!='invocation_expression': return None
    lookup_function=field(lookup,'function')
    if not lookup_function or lookup_function.type!='member_access_expression' or text(field(lookup_function,'name'))!='GetMethod': return None
    type_expr=follow_local(field(lookup_function,'expression'),lookup)
    if not type_expr or type_expr.type!='typeof_expression': return None
    failure=(None,'리플렉션의 타입·메서드 이름·시그니처·호출 인자를 확정할 수 없습니다.')
    type_name=project.type_name(text(field(type_expr,'type')),path,call)
    if not type_name: return failure
    args=field(lookup,'arguments').named_children
    if len(args) not in {1,2}: return failure
    literal=text(args[0].named_children[-1])
    try: name=json.loads(literal)
    except (ValueError,TypeError): return failure
    if not isinstance(name,str) or not name.isidentifier(): return failure
    signature=None
    if len(args)==2:
        array=args[1].named_children[-1]
        if array.type not in {'array_creation_expression','implicit_array_creation_expression'}: return failure
        initializer=next((n for n in array.named_children if n.type=='initializer_expression'),None)
        if initializer is None or any(n.type!='typeof_expression' for n in initializer.named_children): return failure
        signature=[project.type_name(text(field(n,'type')),path,call) for n in initializer.named_children]
        if any(t is None for t in signature): return failure
    candidates=[]
    def collect(typename,seen):
        if typename in seen: return
        seen.add(typename)
        entries=project.types.get(typename,[])
        if len(entries)!=1: return
        source,node=entries[0]
        body=field(node,'body')
        for method in body.named_children if body else []:
            if method.type!='method_declaration' or text(field(method,'name'))!=name or 'public' not in modifiers(method): continue
            if typename!=type_name and 'static' in modifiers(method): continue
            params=field(method,'parameters').named_children
            parameter_types=[project.type_name(text(field(n,'type')),source,method) for n in params]
            if any(n.type!='parameter' or modifiers(n)&{'ref','out','in','params'} for n in params): parameter_types=[None]
            if signature is not None and parameter_types!=signature: continue
            arity=len(field(method,'type_parameters').named_children) if field(method,'type_parameters') else 0
            if any(existing[2]==parameter_types and ancestor(existing[1],TYPES)!=node and (len(field(existing[1],'type_parameters').named_children) if field(existing[1],'type_parameters') else 0)==arity for existing in candidates): continue
            candidates.append((source,method,parameter_types))
        for base in project.bases(typename):
            if base: collect(base,seen.copy())
    collect(type_name,set())
    if len(candidates)!=1: return (None,'GetMethod 이름만으로는 오버로딩을 구분할 수 없거나 공개 메서드가 없습니다.')
    source,method,parameters=candidates[0]
    if field(method,'type_parameters') or any(t is None for t in parameters): return failure
    invoke_args=field(call,'arguments').named_children
    if len(invoke_args)!=2: return failure
    receiver=invoke_args[0].named_children[-1]
    if 'static' not in modifiers(method):
        actual=project.expression_type(receiver,path,call)
        if actual=='null' or not project.conversion(actual,type_name): return failure
    supplied=invoke_args[1].named_children[-1]
    if text(supplied)=='null': values=[]
    elif supplied.type in {'array_creation_expression','implicit_array_creation_expression'}:
        initializer=next((n for n in supplied.named_children if n.type=='initializer_expression'),None)
        if initializer is None: return failure
        values=initializer.named_children
    else: return failure
    if len(values)!=len(parameters) or not all(project.conversion(project.expression_type(v,path,call),t) for v,t in zip(values,parameters)): return failure
    return (source,key(method)), 'typeof·문자열 이름·인자로 찾은 리플렉션 대상 선언입니다. 실행 시 오버라이드는 달라질 수 있습니다.'

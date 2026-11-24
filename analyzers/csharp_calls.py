"""Conservative C# project call resolution from syntax trees; no source execution."""
import re
from tree_sitter import Language, Parser
import tree_sitter_c_sharp

TYPES = {'class_declaration', 'struct_declaration', 'interface_declaration', 'record_declaration'}
METHODS = {'method_declaration', 'constructor_declaration'}
ALIASES = dict(zip(['Int32','Int64','Single','Double','Decimal','String','Boolean','Object','Char','Int16','Byte'], ['int','long','float','double','decimal','string','bool','object','char','short','byte']))
WIDEN = {'sbyte':['short','int','long','float','double','decimal'], 'ushort':['int','uint','long','ulong','float','double','decimal'], 'uint':['long','ulong','float','double','decimal'], 'ulong':['float','double','decimal'], 'byte': ['short','ushort','int','uint','long','ulong','float','double','decimal'], 'short': ['int','long','float','double','decimal'], 'int': ['long','float','double','decimal'], 'long': ['float','double','decimal'], 'float': ['double'], 'char': ['ushort','int','uint','long','ulong','float','double','decimal']}


def walk(node):
    if node is None:
        return
    yield node
    for child in node.named_children:
        yield from walk(child)


def text(node):
    return node.text.decode() if node else ''


def field(node, name):
    return node.child_by_field_name(name) if node else None


def ancestor(node, kinds):
    node = node.parent
    while node and node.type not in kinds:
        node = node.parent
    return node


def modifiers(node):
    return {text(c) for c in node.children if c.type == 'modifier'}


def key(node):
    return 'CS' + str(node.start_byte)


class Project:
    def __init__(self, files):
        parser = Parser(Language(tree_sitter_c_sharp.language()))
        self.units, self.types, self.paths = {}, {}, {}
        for path, source in files.items():
            root = parser.parse(source.removeprefix('\ufeff').encode('utf-8')).root_node
            if root.has_error:
                raise ValueError(path + ': C# 문법 오류')
            self.units[path] = root
            for node in walk(root):
                if node.type not in TYPES:
                    continue
                names = [text(field(node, 'name'))]
                parent = node.parent
                while parent:
                    if parent.type in TYPES | {'namespace_declaration'}:
                        names.insert(0, text(field(parent, 'name')))
                    parent = parent.parent
                file_ns = next((text(field(c, 'name')) for c in root.named_children if c.type == 'file_scoped_namespace_declaration'), '')
                if file_ns:
                    names.insert(0, file_ns)
                full = '.'.join(names)
                self.types.setdefault(full, []).append((path, node))
                self.paths[(path, node.id)] = full

    def type_name(self, value, path, context):
        value = value.replace('global::', '').strip()
        if value.endswith('[]'):
            element = self.type_name(value[:-2], path, context)
            return element + '[]' if element else None
        if value.startswith('System.'):
            value = ALIASES.get(value[7:], value)
        if value in {'int','long','float','double','decimal','string','bool','object','char','short','byte','sbyte','ushort','uint','ulong','void','null'}:
            return value
        current = ancestor(context, TYPES) if context and context.type not in TYPES else context
        prefix = self.paths.get((path, current.id), '') if current else ''
        imports = [n for n in walk(self.units[path]) if n.type == 'using_directive' and (n.parent.type == 'compilation_unit' or n.parent.start_byte <= context.start_byte <= n.parent.end_byte)]
        imports += [n for source,root in self.units.items() if source!=path for n in walk(root) if n.type=='using_directive' and text(n).startswith('global using ')]
        for imp in imports:
            match = re.fullmatch(r'(?:global\s+)?using\s+(\w+)\s*=\s*([\w.]+)\s*;', text(imp))
            if match and value.split('.')[0] == match[1]:
                value = match[2] + value[len(match[1]):]
        candidates = []
        parts = prefix.split('.') if prefix else []
        while parts:
            candidate = '.'.join(parts + [value])
            if candidate in self.types:
                return candidate if len(self.types[candidate]) == 1 else None
            parts.pop()
        file_ns = next((text(field(c, 'name')) for c in self.units[path].named_children if c.type == 'file_scoped_namespace_declaration'), '')
        for prefix in [file_ns] + [re.sub(r'^global\s+','',text(i))[6:].rstrip(';').strip() for i in imports if '=' not in text(i)]:
            candidate = prefix + '.' + value if prefix else value
            if candidate in self.types:
                candidates.append(candidate)
        if value in self.types:
            candidates.append(value)
        candidates = set(candidates)
        return next(iter(candidates)) if len(candidates) == 1 and len(self.types[next(iter(candidates))]) == 1 else None

    def bases(self, type_name):
        entries = self.types.get(type_name, [])
        if len(entries) != 1:
            return []
        path, node = entries[0]
        base_list = next((c for c in node.named_children if c.type == 'base_list'), None)
        return [self.type_name(text(c), path, node) for c in base_list.named_children] if base_list else []

    def conversion(self, source, target, seen=None):
        if not source or not target:
            return False
        if source == target:
            return True
        if target == 'object' and source != 'void':
            return True
        if target in WIDEN.get(source, []):
            return True
        if source == 'null':
            entries = self.types.get(target, [])
            return target.endswith('[]') or target in {'string','object'} or (len(entries) == 1 and entries[0][1].type in {'class_declaration','interface_declaration','record_declaration'})
        seen = seen or set()
        if source in seen:
            return False
        seen.add(source)
        return any(self.conversion(base, target, seen.copy()) for base in self.bases(source) if base)

    def expression_type(self, node, path, site, depth=0):
        if not node or depth > 10:
            return None
        value = text(node)
        if node.type == 'argument':
            return self.expression_type(node.named_children[-1], path, site, depth+1)
        if node.type in {'string_literal','verbatim_string_literal','interpolated_string_expression','raw_string_literal'}:
            return 'string'
        if node.type == 'character_literal': return 'char'
        if value in {'true','false'}: return 'bool'
        if value == 'null': return 'null'
        if node.type == 'integer_literal':
            literal=value.lower().replace('_','')
            suffix=re.search(r'[ul]+$',literal)
            suffix=suffix[0] if suffix else ''
            digits=literal[:-len(suffix)] if suffix else literal
            number=int(digits,16 if digits.startswith('0x') else 2 if digits.startswith('0b') else 10)
            choices=['ulong'] if 'u' in suffix and 'l' in suffix else ['uint','ulong'] if 'u' in suffix else ['long','ulong'] if 'l' in suffix else ['int','uint','long','ulong']
            limits={'int':2**31-1,'uint':2**32-1,'long':2**63-1,'ulong':2**64-1}
            return next((kind for kind in choices if number<=limits[kind]),None)
        if node.type == 'real_literal':
            return {'f':'float','m':'decimal','d':'double'}.get(value[-1].lower(),'double')
        if node.type in {'object_creation_expression','cast_expression'}:
            return self.type_name(text(field(node,'type')),path,site)
        if node.type == 'parenthesized_expression':
            return self.expression_type(node.named_children[0],path,site,depth+1)
        owner = ancestor(site,TYPES)
        if value == 'this': return self.paths.get((path,owner.id)) if owner else None
        if value == 'base':
            bases = self.bases(self.paths.get((path,owner.id))) if owner else []
            return bases[0] if bases else None
        if node.type == 'member_access_expression':
            expression=field(node,'expression')
            prefix=text(expression) or text(node).rsplit('.',1)[0]
            receiver=self.paths.get((path,owner.id)) if prefix=='this' and owner else self.expression_type(expression,path,site,depth+1)
            name=text(field(node,'name'))
            entries=self.types.get(receiver,[])
            if len(entries)==1:
                source_path,definition=entries[0]
                members=[n for n in walk(field(definition,'body')) if n.type in {'variable_declarator','property_declaration'} and text(field(n,'name'))==name and ancestor(n,TYPES)==definition]
                if len(members)==1:
                    member=members[0]
                    declaration=ancestor(member,{'field_declaration'}) if member.type=='variable_declarator' else member
                    if definition==owner or 'public' in modifiers(declaration) or 'internal' in modifiers(declaration):
                        return self.type_name(text(field(member.parent if member.type=='variable_declarator' else member,'type')),source_path,member)
            return None
        if node.type != 'identifier': return None
        scope = ancestor(site, METHODS | {'local_function_statement','global_statement'})
        if scope and scope.type == 'global_statement': scope=self.units[path]
        if scope:
            params = field(scope,'parameters')
            matches = [p for p in (params.named_children if params else []) if text(field(p,'name')) == value]
            locals_ = [n for n in walk(scope) if n.type == 'variable_declarator' and text(field(n,'name')) == value and n.start_byte < site.start_byte and (not ancestor(n,{'block'}) or ancestor(n,{'block'}).start_byte <= site.start_byte <= ancestor(n,{'block'}).end_byte)]
            if locals_:
                # shortcut: multiple shadowing declarations stay unresolved until full lexical binding is added.
                if len(locals_) != 1: return None
                declaration = locals_[0]
                declared = text(field(declaration.parent,'type'))
                if declared == 'dynamic':
                    from .csharp_advanced import stable_initializer
                    initializer=stable_initializer(value,site)
                    if initializer and initializer.type in {'object_creation_expression','integer_literal','real_literal','string_literal','boolean_literal','character_literal'}:
                        return self.expression_type(initializer,path,declaration,depth+1)
                    return None
                if declared == 'var':
                    initializer = declaration.named_children[-1]
                    return self.expression_type(initializer,path,declaration,depth+1) if initializer != field(declaration,'name') else None
                return self.type_name(declared,path,site)
            if len(matches) == 1:
                return self.type_name(text(field(matches[0],'type')),path,site)
        if owner:
            body = field(owner,'body')
            matches = [n for n in walk(body) if n.type == 'variable_declarator' and text(field(n,'name')) == value and ancestor(n,TYPES) == owner and ancestor(n,{'field_declaration'})]
            properties = [n for n in body.named_children if n.type == 'property_declaration' and text(field(n,'name')) == value]
            if len(matches) == 1: return self.type_name(text(field(matches[0].parent,'type')),path,site)
            if len(properties) == 1: return self.type_name(text(field(properties[0],'type')),path,site)
        return None

    def methods(self, type_name, name, caller, seen=None):
        seen = seen or set()
        if not type_name or type_name in seen: return []
        seen.add(type_name)
        entries = self.types.get(type_name, [])
        if len(entries) != 1: return []
        path, node = entries[0]
        body = field(node,'body')
        local = [(path,m) for m in body.named_children if m.type in METHODS and text(field(m,'name')) == name] if body else []
        visible = [(p,m) for p,m in local if type_name == caller or node.type == 'interface_declaration' or 'public' in modifiers(m) or 'internal' in modifiers(m) or ('protected' in modifiers(m) and self.conversion(caller,type_name))]
        if local: return visible
        return [method for base in self.bases(type_name) for method in self.methods(base,name,caller,seen.copy())]

    def resolve(self, path, call, _extension=None):
        from .csharp_advanced import constraints_satisfied, extension_tiers, is_dynamic_expression, reflection_target
        if _extension is None and call.type=='invocation_expression':
            reflection=reflection_target(self,path,call)
            if reflection is not None: return reflection
        owner = ancestor(call,TYPES)
        current = self.paths.get((path,owner.id)) if owner else None
        if ancestor(call, {'lambda_expression','anonymous_method_expression','local_function_statement'}):
            return None, '지역 함수·람다의 바인딩은 확정할 수 없습니다.'
        creation = call.type == 'object_creation_expression'
        function = field(call,'type' if creation else 'function')
        name = text(function)
        receiver = current
        static = False
        explicit_types = []
        receiver_expression=None
        dynamic_receiver=False
        if creation:
            receiver = self.type_name(name,path,call)
            entries = self.types.get(receiver,[])
            if len(entries) != 1: return None, '생성할 타입이 미등록이거나 중복됩니다.'
            name = text(field(entries[0][1],'name'))
        elif function and function.type == 'member_access_expression':
            expression = field(function,'expression') or next((n for n in function.children if n.type in {'this','base'}),None)
            receiver_expression=expression
            dynamic_receiver=is_dynamic_expression(expression,call)
            receiver_text = text(expression) or text(function).rsplit('.',1)[0]
            if receiver_text in {'this','base'}:
                receiver = current if receiver_text == 'this' else next(iter(self.bases(current)),None)
            else:
                receiver = self.expression_type(expression,path,call)
                if receiver is None and not any(n.type in {'variable_declarator','parameter'} and text(field(n,'name')) == receiver_text for n in walk(ancestor(call,METHODS) or self.units[path])):
                    receiver = self.type_name(receiver_text,path,call)
                    static = receiver is not None
            function = field(function,'name')
            name = text(function)
        elif not function or function.type not in {'identifier','generic_name'}:
            return None, '체인·조건부·동적 호출은 확정할 수 없습니다.'
        if function and function.type == 'generic_name':
            name = text(function.named_children[0])
            type_args = next((c for c in function.named_children if c.type == 'type_argument_list'),None)
            explicit_types = [self.type_name(text(c),path,call) for c in type_args.named_children] if type_args else []
        scope = ancestor(call, METHODS)
        if scope and any(n.type == 'local_function_statement' and text(field(n,'name')) == name for n in walk(scope)):
            return None, '지역 함수와 메서드 이름이 겹쳐 대상을 확정할 수 없습니다.'
        candidates = self.methods(receiver,name,current)
        tiers=[]
        if _extension is not None:
            if static or dynamic_receiver or not receiver_expression or not receiver:
                return None, '동적·알 수 없는 수신 객체에는 확장 메서드를 연결할 수 없습니다.'
            tiers=extension_tiers(self,path,call,name)
            if _extension>=len(tiers): return None, '현재 using 범위에서 적용 가능한 확장 메서드가 없습니다.'
            candidates=tiers[_extension]
        if not creation and field(call,'function').type in {'identifier','generic_name'} and scope and 'static' in modifiers(scope): static=True
        if static: candidates = [(p,m) for p,m in candidates if 'static' in modifiers(m)]
        args_node = field(call,'arguments')
        args = args_node.named_children if args_node else []
        if _extension is not None: args=[receiver_expression]+args
        if creation and not candidates and not args:
            p,n = self.types[receiver][0]
            body=field(n,'body')
            if not any(c.type == 'constructor_declaration' for c in body.named_children): return (p,key(n)), '기본 생성자'
        applicable = []
        for p,method in candidates:
            parameter_list = field(method,'parameters')
            parameters = [n for n in parameter_list.named_children if n.type == 'parameter']
            params_type = field(parameter_list,'type') if any(c.type == 'params' for c in parameter_list.children) else None
            if params_type:
                parameters.append(parameter_list)
            if any(any(text(c) in {'ref','out','in'} for c in param.children) for param in parameters): continue
            if any(any(c.type in {'ref','out','in'} for c in arg.children) for arg in args): continue
            generics = next((c for c in method.named_children if c.type == 'type_parameter_list'),None)
            typevars = [text(c) for c in generics.named_children] if generics else []
            if explicit_types and len(explicit_types) != len(typevars): continue
            substitutions = dict(zip(typevars,explicit_types))
            values = {}
            expanded = False
            for i,arg in enumerate(args):
                arg_name = text(field(arg,'name'))
                index = next((j for j,param in enumerate(parameters) if text(field(param,'name')) == arg_name),-1) if arg_name else min(i,len(parameters)-1) if params_type else i
                if index < 0 or index >= len(parameters): break
                if index in values and (not params_type or index != len(parameters)-1 or arg_name): break
                values.setdefault(index,[]).append((self.expression_type(arg,path,call),arg))
            else:
                targets, sources = [], []
                valid=True
                for i,param in enumerate(parameters):
                    if i not in values:
                        if param == parameter_list: expanded=True
                        if param != parameter_list and not any(c.type == '=' for c in param.children): valid=False
                        continue
                    declared=text(field(param,'type'))
                    actuals=values[i]
                    if param == parameter_list:
                        array_type=self.type_name(declared,p,method)
                        if len(actuals)!=1 or not self.conversion(actuals[0][0],array_type):
                            declared=declared[:-2] if declared.endswith('[]') else ''
                            expanded=True
                    for actual,argument in actuals:
                        if declared in typevars and declared not in substitutions and actual not in {None,'null'}: substitutions[declared]=actual
                        target=substitutions.get(declared) if declared in typevars else self.type_name(declared,p,method)
                        constant=False
                        expr=argument.named_children[-1] if argument.type=='argument' else argument
                        ranges={'sbyte':(-128,127),'byte':(0,255),'short':(-32768,32767),'ushort':(0,65535),'uint':(0,2**32-1),'ulong':(0,2**64-1)}
                        if actual=='int' and expr.type=='integer_literal' and target in ranges:
                            literal=text(expr).replace('_','');number=int(literal,16 if literal.lower().startswith('0x') else 2 if literal.lower().startswith('0b') else 10)
                            constant=ranges[target][0]<=number<=ranges[target][1]
                        if not self.conversion(actual,target) and not constant: valid=False
                        if _extension is not None and i==0 and actual!=target and target in WIDEN.get(actual,[]): valid=False
                        sources.append(actual);targets.append(target)
                if any(not substitutions.get(variable) for variable in typevars): valid=False
                if valid and constraints_satisfied(self,p,method,substitutions):
                    applicable.append((p,method,sources,targets,max(0,len(parameters)-len(args)),bool(typevars),expanded))
        def better(a,b):
            if len(a[3]) != len(b[3]): return False
            comparisons=[]
            for source,ta,tb in zip(a[2],a[3],b[3]):
                comparisons.append(0 if ta==tb else (1 if source==ta or (self.conversion(ta,tb) and not self.conversion(tb,ta)) else -1))
            if all(c>=0 for c in comparisons) and any(c>0 for c in comparisons): return True
            if all(c==0 for c in comparisons): return (a[6],a[4],a[5]) < (b[6],b[4],b[5])
            return False
        winners=[a for a in applicable if all(a is b or better(a,b) for b in applicable)]
        if len(winners)==1:
            p,m,*_=winners[0]
            if _extension is not None: reason='using 범위와 수신 객체 타입으로 선택한 확장 메서드입니다.'
            elif dynamic_receiver or any(is_dynamic_expression(a.named_children[-1] if a.type=='argument' else a,call) for a in args): reason='변경되지 않은 dynamic 지역 변수의 초기화 타입을 바탕으로 추적했습니다.'
            else: reason='선언 타입 기준 호출입니다. 실제 객체의 오버라이드 실행 대상은 다를 수 있습니다.'
            return (p,key(m)), reason
        if not applicable and not creation and receiver_expression is not None and receiver is not None and not static and not dynamic_receiver:
            return self.resolve(path,call,0 if _extension is None else _extension+1)
        if dynamic_receiver and receiver is None: return None, 'dynamic의 실행 타입이 불명확하거나 재대입·참조 전달·캡처가 있어 연결하지 않습니다.'
        return None, '인자 타입·접근 권한·오버로딩·제네릭 제약을 확정할 수 없습니다.'

    def links(self):
        result={}
        for path,root in self.units.items():
            links={}
            for call in walk(root):
                if call.type not in {'invocation_expression','object_creation_expression'}: continue
                function=field(call,'type' if call.type=='object_creation_expression' else 'function')
                if not function: continue
                target,reason=self.resolve(path,call)
                links[key(function)+'_'+str(function.end_byte)]={'target':list(target) if target else None,'reason':reason,'start':function.start_byte,'end':function.end_byte}
            for node in walk(root):
                if node.type != 'base_list': continue
                for base in node.named_children:
                    typename=self.type_name(text(base),path,node.parent)
                    entries=self.types.get(typename,[])
                    target=(entries[0][0],key(entries[0][1])) if len(entries)==1 else None
                    links[key(base)]={'target':list(target) if target else None,'reason':'상속·인터페이스 구현' if target else '상위 타입 미등록·중복','start':base.start_byte,'end':base.end_byte}
            result[path]=links
        return result

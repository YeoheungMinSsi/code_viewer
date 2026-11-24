import unittest
from pathlib import Path
from xml.etree.ElementTree import fromstring
from analyzers import analyze

class CSharpTests(unittest.TestCase):
    def test_structure_and_links(self):
        root=fromstring(analyze(Path('CSharpExample.cs').read_bytes(),'example.cs'))
        self.assertEqual(len(root.findall('.//details[@class="cls"]')),3)
        self.assertEqual(len(root.findall('.//details[@class="fn entry"]')),1)
        ids={n.attrib['data-line'] for n in root.findall('.//details')}
        calls=root.findall('.//button')
        self.assertTrue(any(c.text=='Amount' and c.attrib['data-target'] in ids for c in calls))
        self.assertTrue(any(c.text=='order.Receipt' and c.attrib['data-target'] in ids for c in calls))
        self.assertTrue(any(c.attrib.get('class')=='call inheritance' for c in calls))
    def test_invalid(self):
        with self.assertRaises(ValueError): analyze(b'class {', 'bad.cs')
    def test_ambiguous_and_escaping(self):
        root=fromstring(analyze(b'class A { void F(int x){} void F(string x){} void G(){ F(1); } string S = "<script>"; }','a.cs'))
        target=root.find('.//button').attrib['data-target']
        self.assertEqual(root.find('.//details[@data-line="'+target+'"]/summary/b').text,'F(int x)')
        self.assertIsNone(root.find('.//script'))

class CSharpProjectTests(unittest.TestCase):
    def links(self, files):
        from analyzers.csharp_calls import Project
        return Project(files).links()

    def target_source(self, files, path, expression):
        links=self.links(files)[path]
        matching=[link for link in links.values() if files[path].encode()[link['start']:link['end']].decode()==expression]
        self.assertEqual(len(matching),1,matching)
        target=matching[0]['target']
        return files[target[0]].encode()[int(target[1][2:]):].decode() if target else None

    def test_receivers_namespaces_aliases_and_inherited(self):
        files={'Base.cs':'namespace Shop; public class Base { public int Price(int n)=>n; }',
               'Order.cs':'namespace Shop; public class Order : Base { }',
               'Program.cs':'using Alias = Shop.Order; class Program { Shop.Order field; void Run(Alias parameter){ var local=new Alias(); local.Price(1); parameter.Price(2); field.Price(3); } }'}
        for call in ['local.Price','parameter.Price','field.Price']:
            self.assertTrue(self.target_source(files,'Program.cs',call).startswith('public int Price'))
        self.assertIsNotNone(self.target_source(files,'Program.cs','Alias'))

    def test_numeric_optional_named_and_generic(self):
        files={'a.cs':'class A { void F(long x){} void F(double x){} void G(int x, string label="a"){} T Id<T>(T value)=>value; void Run(){ F(1); G(label:"b",x:2); Id(3); } }'}
        self.assertTrue(self.target_source(files,'a.cs','F').startswith('void F(long'))
        self.assertTrue(self.target_source(files,'a.cs','G').startswith('void G'))
        self.assertTrue(self.target_source(files,'a.cs','Id').startswith('T Id<T>'))

    def test_declared_type_and_base(self):
        files={'a.cs':'class Base { public virtual int F()=>1; } class Child:Base { public override int F()=>2; void Run(Base b){ b.F(); base.F(); } }'}
        for name in ['b.F','base.F']:
            self.assertTrue(self.target_source(files,'a.cs',name).startswith('public virtual'))

    def test_unknown_ambiguous_and_duplicate_types(self):
        files={'a.cs':'class A { void F(string x){} void F(A x){} void Run(dynamic x){ F(null); x.F(1); } }'}
        self.assertIsNone(self.target_source(files,'a.cs','F'))
        self.assertIsNone(self.target_source(files,'a.cs','x.F'))
        files={'a.cs':'class X { public static void F(){} }','b.cs':'class X { public static void F(){} }','c.cs':'class C { void Run(){ X.F(); } }'}
        self.assertIsNone(self.target_source(files,'c.cs','X.F'))

    def test_private_external_and_missing_file(self):
        files={'a.cs':'class A { private void F(){} }','b.cs':'class B { void Run(A a){ a.F(); } }'}
        self.assertIsNone(self.target_source(files,'b.cs','a.F'))
        del files['a.cs']
        self.assertIsNone(self.target_source(files,'b.cs','a.F'))

    def test_params_and_optional_and_explicit_generic(self):
        files={'a.cs':'class A { void F(params int[] xs){} void G(int x=1){} T Id<T>(T x)=>x; void Run(){ F(1,2); G(); Id<int>(3); } }'}
        for expression in ['F','G','Id<int>']:
            self.assertIsNotNone(self.target_source(files,'a.cs',expression))

    def test_lexical_shadowing_is_not_static_call(self):
        files={'a.cs':'class X { public static void F(){} } class A { void Run(dynamic X){ X.F(); } }'}
        self.assertIsNone(self.target_source(files,'a.cs','X.F'))

    def test_unicode_byte_offsets(self):
        from analyzers.csharp_calls import Project
        source='class 주문 { int 합계()=>1; int 실행()=>합계(); }'
        normal=Project({'a.cs':source}).links()
        self.assertEqual(normal,Project({'a.cs':'\ufeff'+source}).links())
        self.assertTrue(self.target_source({'a.cs':source},'a.cs','합계').startswith('int 합계'))

    def test_constant_conversion_and_interface_receiver(self):
        files={'a.cs':'interface I { void Run(); } class A { void F(byte n){} void F(long n){} void Main(I obj){ F(1); obj.Run(); } }'}
        self.assertTrue(self.target_source(files,'a.cs','F').startswith('void F(byte'))
        self.assertTrue(self.target_source(files,'a.cs','obj.Run').startswith('void Run'))

    def test_explicit_field_receiver(self):
        files={'a.cs':'class Service { public void Run(){} } class A { Service service; void Main(){ this.service.Run(); } }'}
        self.assertTrue(self.target_source(files,'a.cs','this.service.Run').startswith('public void Run'))

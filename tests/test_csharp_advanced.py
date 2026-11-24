import unittest
from analyzers.csharp_calls import Project


class AdvancedCSharpTests(unittest.TestCase):
    def resolve(self, files, expression, path='Main.cs'):
        links=Project(files).links()[path]
        source=files[path].removeprefix('\ufeff').encode()
        matches=[v for v in links.values() if source[v['start']:v['end']].decode()==expression]
        self.assertEqual(len(matches),1,matches)
        return matches[0]

    def declaration(self, files, link):
        path,token=link['target']
        return files[path].encode()[int(token[2:]):].decode()

    def test_extension_scope_and_instance_priority(self):
        files={'Types.cs':'namespace Shop; public class Item { public int Run(int x)=>x; }',
               'Extensions.cs':'namespace Helpers; public static class E { public static string Run(this Shop.Item x, string s)=>s; public static int Run(this Shop.Item x, int n)=>n; }',
               'Main.cs':'using Helpers; class Main { void Test(Shop.Item item){ item.Run(1); } }'}
        link=self.resolve(files,'item.Run')
        self.assertEqual(link['target'][0],'Types.cs')
        files['Main.cs']='using Helpers; class Main { void Test(Shop.Item item){ item.Run("a"); } }'
        link=self.resolve(files,'item.Run')
        self.assertEqual(link['target'][0],'Extensions.cs')
        self.assertIn('확장 메서드',link['reason'])
        files['Main.cs']=files['Main.cs'].replace('using Helpers;','')
        self.assertIsNone(self.resolve(files,'item.Run')['target'])

    def test_extension_ambiguity_and_global_using(self):
        files={'Global.cs':'global using Shop;', 'A.cs':'namespace Shop; public class Item {} public static class E { public static int Run(this Item x)=>1; }',
               'Main.cs':'class Main { void Test(){ var item=new Item(); item.Run(); } }'}
        self.assertIsNotNone(self.resolve(files,'item.Run')['target'])
        files['B.cs']='namespace Shop; public static class Other { public static int Run(this Item x)=>2; }'
        self.assertIsNone(self.resolve(files,'item.Run')['target'])

    def test_combined_constraints_new_and_interface(self):
        base='interface I {} class Item:I { public Item(){} } class Main { T Keep<T>(T x) where T:class,I,new()=>x; void Test(){ Keep(new Item()); } }'
        files={'Main.cs':base}
        self.assertIsNotNone(self.resolve(files,'Keep')['target'])
        for old,new in [('public Item()','private Item()'),('class Item:I','class Item'),('class Item:I','abstract class Item:I')]:
            with self.subTest(new=new):
                self.assertIsNone(self.resolve({'Main.cs':base.replace(old,new)},'Keep')['target'])

    def test_struct_unmanaged_and_parameter_constraint(self):
        files={'Main.cs':'struct Pair { public int X; } class Main { T Keep<T>(T x) where T:unmanaged=>x; void Test(Pair p){ Keep(p); } }'}
        self.assertIsNotNone(self.resolve(files,'Keep')['target'])
        files['Main.cs']=files['Main.cs'].replace('public int X','public string X')
        self.assertIsNone(self.resolve(files,'Keep')['target'])
        files={'Main.cs':'class Base {} class Child:Base {} class Main { T Keep<T,U>(T x) where T:U=>x; void Test(){ Keep<Child,Base>(new Child()); } }'}
        self.assertIsNotNone(self.resolve(files,'Keep<Child,Base>')['target'])

    def test_generic_extension_constraints(self):
        files={'Main.cs':'class Item {} static class E { public static T Keep<T>(this T x) where T:class,new()=>x; } class Main { void Test(Item item){ item.Keep(); } }'}
        self.assertIsNotNone(self.resolve(files,'item.Keep')['target'])
        files['Main.cs']=files['Main.cs'].replace('class Item {}','class Item { private Item(){} }')
        self.assertIsNone(self.resolve(files,'item.Keep')['target'])

    def test_dynamic_stable_and_writes(self):
        source='class Item { public int Run()=>1; } class Main { void Test(){ dynamic item=new Item(); item.Run(); } }'
        result=self.resolve({'Main.cs':source},'item.Run')
        self.assertIsNotNone(result['target'])
        self.assertIn('dynamic',result['reason'])
        for insertion in ['item = Read();', 'if (Flag()) item = Read();', 'Capture(ref item);', 'System.Action a = ()=> item = Read();']:
            with self.subTest(insertion=insertion):
                files={'Main.cs':source.replace('item.Run();',insertion+'item.Run();')}
                self.assertIsNone(self.resolve(files,'item.Run')['target'])
        files={'Main.cs':'class Item {} static class E { public static void Run(this Item x){} } class Main { void Test(){ dynamic item=new Item(); item.Run(); } }'}
        self.assertIsNone(self.resolve(files,'item.Run')['target'])

    def test_reflection_unique_and_typed_overload(self):
        source='class Item { public void Run(int n){} } class Main { void Test(){ var item=new Item(); var method=typeof(Item).GetMethod("Run"); method.Invoke(item,new object[]{1}); } }'
        result=self.resolve({'Main.cs':source},'method.Invoke')
        self.assertIsNotNone(result['target'])
        self.assertIn('리플렉션',result['reason'])
        source=source.replace('public void Run(int n){}','public void Run(int n){} public void Run(string s){}')
        self.assertIsNone(self.resolve({'Main.cs':source},'method.Invoke')['target'])
        source=source.replace('GetMethod("Run")','GetMethod("Run",new[]{typeof(int)})')
        self.assertTrue(self.declaration({'Main.cs':source},self.resolve({'Main.cs':source},'method.Invoke')).startswith('public void Run(int'))

    def test_reflection_unknown_private_and_changed_lookup(self):
        base='class Item { public void Run(){} } class Main { void Test(){ var item=new Item(); var method=typeof(Item).GetMethod("Run"); method.Invoke(item,null); } }'
        for old,new in [('public void Run','private void Run'),('GetMethod("Run")','GetMethod(Read())'),('method.Invoke','method = Read(); method.Invoke')]:
            with self.subTest(new=new):
                self.assertIsNone(self.resolve({'Main.cs':base.replace(old,new)},'method.Invoke')['target'])

    def test_direct_reflection_and_generic_ambiguity(self):
        source='class Item { public static void Run(){} } class Main { void Test(){ typeof(Item).GetMethod("Run").Invoke(null,null); } }'
        expression='typeof(Item).GetMethod("Run").Invoke'
        self.assertIsNotNone(self.resolve({'Main.cs':source},expression)['target'])
        source=source.replace('public static void Run(){}','public static void Run(){} public static void Run<T>(){}')
        self.assertIsNone(self.resolve({'Main.cs':source},expression)['target'])

    def test_uninferred_generic_and_numeric_extension_are_not_connected(self):
        files={'Main.cs':'class Main { T Keep<T,U>(T x)=>x; void Test(){ Keep(1); } }'}
        self.assertIsNone(self.resolve(files,'Keep')['target'])
        files={'Main.cs':'class Main { T Keep<T>(T x)=>x; void Test(){ Keep(null); } }'}
        self.assertIsNone(self.resolve(files,'Keep')['target'])
        files={'Main.cs':'static class E { public static int Run(this long x)=>1; } class Main { void Test(int n){ n.Run(); } }'}
        self.assertIsNone(self.resolve(files,'n.Run')['target'])

    def test_nested_reflection_render_keeps_outer_invoke(self):
        from analyzers.csharp import outline
        from xml.etree.ElementTree import fromstring
        source='class Item { public static void Run(){} } class Main { void Test(){ typeof(Item).GetMethod("Run").Invoke(null,null); } }'
        root=fromstring(outline(source.encode()))
        buttons=root.findall('.//button')
        invoke=next(b for b in buttons if b.text=='typeof(Item).GetMethod("Run").Invoke')
        self.assertFalse(invoke.attrib['data-target'].startswith('?'))
        self.assertEqual(len({b.attrib['data-cs-call'] for b in buttons}),len(buttons))

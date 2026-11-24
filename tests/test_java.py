import importlib.util
import unittest
from pathlib import Path
from xml.etree.ElementTree import fromstring
from analyzers import analyze


@unittest.skipUnless(importlib.util.find_spec('javalang'), 'Java tests require requirements.txt')
class JavaTests(unittest.TestCase):
    def tree(self, source):
        return fromstring(analyze(source.encode(), 'Example.java'))

    def test_example(self):
        root = self.tree(Path('examples/OrderExample.java').read_text(encoding='utf-8'))
        self.assertEqual([n.text for n in root.findall('details[@class="cls"]/summary/b')], ['Order', 'OrderExample'])
        self.assertEqual([n.text for n in root.findall('.//details[@class="fn"]/summary/small')], ['생성자', '메서드', '메서드'])
        self.assertEqual(len(root.findall('.//details[@class="fn entry"]')), 1)
        field = root.find('.//details[@class="var"]')
        self.assertEqual(field.find('summary/small').text, '인스턴스 변수')
        self.assertIn('private int price;', ''.join(field.itertext()))

    def test_braces_inside_literals_and_nested_code(self):
        root = self.tree('class A {\n int[] values = {1, 2};\n String message() {\n // }\n if (true) { return "<script>};"; }\n return "ok";\n }\n void next() {}\n}')
        methods = root.findall('.//details[@class="fn"]')
        code = ''.join(methods[0].find('pre').itertext())
        self.assertIn('return "ok"', code)
        self.assertNotIn('void next', code)
        self.assertIn('<script>', code)
        self.assertEqual(len(methods), 2)

    def test_main_signature(self):
        root = self.tree('class A { void main() {} public static void main(String... args) {} }')
        self.assertEqual(len(root.findall('.//details[@class="fn entry"]')), 1)

    def test_package_and_nested_class(self):
        root = self.tree('package example;\nclass Outer {\n class Inner { int n; }\n}')
        self.assertEqual(root.find('details/summary/b').text, 'example')
        self.assertEqual(len(root.findall('.//details[@class="cls"]')), 2)

    def test_invalid_and_unsupported(self):
        for source in ['class {', 'record Point(int x) {}']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.tree(source)

    def test_calls_inheritance_overloads_and_override(self):
        root = self.tree(Path('examples/JavaCallsExample.java').read_text(encoding='utf-8'))
        targets = {node.attrib['data-line']: node for node in root.findall('.//details')}
        labels = root.findall('.//button')
        self.assertEqual([targets[b.attrib['data-target']].find('summary/b').text for b in labels if b.text == 'label'], ['label(int count)', 'label(String text)'])
        prices = [targets[b.attrib['data-target']].find('summary/em').text for b in labels if b.text == 'price']
        self.assertEqual(prices, ['L2', 'L11'])
        self.assertIn('오버라이드', ''.join(root.itertext()))
        parent = root.find('.//button[@class="call inheritance"]')
        self.assertEqual(targets[parent.attrib['data-target']].find('summary/b').text, 'BaseOrder')

    def test_same_line_ids_and_ambiguous_calls(self):
        root = self.tree('class A { void f(int a){} void f(String a){} void run(Object x){ f(x); } }')
        ids = [n.attrib['data-line'] for n in root.findall('.//details')]
        self.assertEqual(len(ids), len(set(ids)))
        call = root.find('.//button')
        self.assertTrue(call.attrib['data-target'].startswith('?'))
        self.assertIn('후보:', call.attrib['title'])

    def test_widening_and_null_ambiguity(self):
        root = self.tree('class A { void f(long n){} void f(double n){} void g(String n){} void g(A n){} void run(){ f(0xDEAF); g(null); } }')
        calls = root.findall('.//button')
        target = root.find('.//details[@data-line="' + calls[0].attrib['data-target'] + '"]')
        self.assertEqual(target.find('summary/b').text, 'f(long n)')
        self.assertTrue(calls[1].attrib['data-target'].startswith('?'))

    def test_unknown_receiver_and_parent(self):
        for source in ['class A { void f(){} void run(Object obj){ obj.f(); } }', 'class A extends Missing { void f(){} void run(){ f(); } }']:
            root = self.tree(source)
            call = next(n for n in root.findall('.//button') if n.text == 'f')
            self.assertTrue(call.attrib['data-target'].startswith('?'))

    def test_declared_receiver_type(self):
        root = self.tree('class Base { void f(){} } class Child extends Base { void f(){} void run(Base obj){ obj.f(); } }')
        call = next(n for n in root.findall('.//button') if n.text == 'f')
        base_method = root.find('details/section/details')
        self.assertEqual(call.attrib['data-target'], base_method.attrib['data-line'])
        self.assertIn('실제 객체', call.attrib['title'])

    def test_double_suffix_and_shadowed_local(self):
        root = self.tree("""class A {
 String value;
 void f(int x){}
 void f(double x){}
 void f(String x){}
 void run(){
  f(1d);
  { int value=1; f(value); }
  f(value);
 }
}""")
        calls = root.findall('.//button')
        target = root.find('.//details[@data-line="' + calls[0].attrib['data-target'] + '"]')
        self.assertEqual(target.find('summary/b').text, 'f(double x)')
        self.assertEqual(len(calls), 3)
        for call in calls[1:]:
            self.assertTrue(call.attrib['data-target'].startswith('?'))
            self.assertIn('인자 타입', call.attrib['title'])

    def test_private_super_not_connected(self):
        root = self.tree('class Base { private void f(){} } class Child extends Base { void f(){ super.f(); } }')
        call = next(n for n in root.findall('.//button') if n.text == 'f')
        self.assertTrue(call.attrib['data-target'].startswith('?'))
        self.assertNotIn('오버라이드', ''.join(root.itertext()))

    def test_interface_enum_and_implements(self):
        root = self.tree("""
interface Priced {
    int price();
}
enum Status implements Priced {
    PAID, CANCELLED;
    public int price() { return 1000; }
}
class Order implements Priced {
    public int price() { return 12000; }
    int show(Priced item) { return item.price(); }
}
""")
        kinds = [n.text for n in root.findall('details[@class="cls"]/summary/small')]
        self.assertEqual(kinds, ['인터페이스', '열거형', '클래스'])
        consts = [n.text for n in root.findall('.//details[@class="var"]/summary/b')]
        self.assertEqual(consts, ['PAID', 'CANCELLED'])
        impl_buttons = [b for b in root.findall('.//button[@class="call inheritance"]') if b.text == 'implements Priced']
        self.assertEqual(len(impl_buttons), 2)
        priced_id = root.find('details[@data-name="Priced"]').attrib['data-line']
        self.assertTrue(all(b.attrib['data-target'] == priced_id for b in impl_buttons))
        self.assertIn('오버라이드', ''.join(root.itertext()))
        call = next(b for b in root.findall('.//button') if b.text == 'price')
        self.assertFalse(call.attrib['data-target'].startswith('?'))

    def test_cross_file_java_imports(self):
        root = self.tree("""
import shop.Discount;
import shop.BaseOrder;
class Order extends BaseOrder {
    int total() {
        Discount d = new Discount();
        return d.apply(super.base());
    }
}
""")
        buttons = {b.text: b.attrib['data-target'] for b in root.findall('.//button')}
        self.assertEqual(buttons['extends BaseOrder'], 'shop.BaseOrder|BaseOrder')
        self.assertEqual(buttons['Discount'], 'shop.Discount|Discount')
        self.assertEqual(buttons['apply'], 'shop.Discount|Discount.apply')
        self.assertEqual(buttons['base'], 'shop.BaseOrder|BaseOrder.base()')

    def test_annotation_varargs_and_generics(self):
        root = self.tree("""
@interface Tag {
    String value();
}
class Calc {
    int sum(int a) { return a; }
    int sum(int... nums) { return 0; }
    <T extends Number> T id(T x) { return x; }
    void run(Integer n) {
        sum(1);
        sum(1, 2, 3);
        id(n);
    }
}
""")
        self.assertEqual(root.find('details[@data-name="Tag"]/summary/small').text, '애노테이션')
        self.assertEqual(root.find('details[@data-name="Tag"]//details[@class="fn"]/summary/small').text, '요소')
        targets = {n.attrib['data-line']: n.find('summary/b').text for n in root.findall('.//details')}
        sums = [targets[b.attrib['data-target']] for b in root.findall('.//button') if b.text == 'sum']
        self.assertEqual(sums, ['sum(int a)', 'sum(int... nums)'])
        id_call = next(b for b in root.findall('.//button') if b.text == 'id')
        self.assertEqual(targets[id_call.attrib['data-target']], 'id(T x)')

    def test_wildcard_and_same_package_cross_file_overloads(self):
        root = self.tree("""
package shop;
import util.*;
class Checkout {
    void run(Pricing p, Helper h) {
        p.fee(100);
        p.fee("VIP");
        h.log();
    }
}
""")
        calls = [(b.text, b.attrib['data-target']) for b in root.findall('.//button')]
        self.assertEqual(calls, [
            ('fee', 'shop.Pricing,util.Pricing|Pricing.fee(int)'),
            ('fee', 'shop.Pricing,util.Pricing|Pricing.fee(String)'),
            ('log', 'shop.Helper,util.Helper|Helper.log()'),
        ])

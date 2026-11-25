import re
import unittest
from pathlib import Path
from xml.etree.ElementTree import fromstring
from analyzers import analyze


def links(html):
    return {text: target for target, text in re.findall(r'data-target="([^"]*)"[^>]*>([^<]*)</button>', html)}


class TypeScriptJavaScriptTests(unittest.TestCase):
    def test_typescript_learning_example(self):
        html = analyze(Path('examples/learning_example.ts').read_bytes(), 'learning_example.ts')
        root = fromstring(html)
        self.assertEqual([n.text for n in root.findall('details/summary/b')],
                         ['formatTotal(value: number)', 'Order', '여기서 시작'])
        calls = links(html)
        self.assertEqual(calls['Order'], '5')
        self.assertEqual(calls['order.receipt'], '16')
        self.assertEqual(calls['this.total'], '12')
        self.assertEqual(calls['formatTotal'], '1')
        self.assertTrue(calls['console.log'].startswith('?'))

    def test_javascript_inheritance_super_and_override(self):
        html = analyze(Path('examples/inheritance_example.js').read_bytes(), 'inheritance_example.js')
        calls = links(html)
        self.assertEqual(calls['extends Animal'], '1')
        self.assertIn('메서드 · 재정의(Animal)', html)
        self.assertEqual(calls['super'], '2')
        self.assertEqual(calls['this.introduce'], '10')
        self.assertTrue(calls['this.speak'].startswith('?자식 클래스 Dog'))
        self.assertEqual(calls['Dog'], '15')
        self.assertEqual(calls['dog.learn'], '25')
        self.assertEqual(calls['makeDog'], '31')
        self.assertEqual(calls['animal.speak'], '6')

    def test_typescript_interface_and_cross_file_imports(self):
        pricing = analyze(Path('examples/ts_project_example/pricing.ts').read_bytes(), 'pricing.ts')
        order = analyze(Path('examples/ts_project_example/order.ts').read_bytes(), 'order.ts')
        self.assertIn('인터페이스', pricing)
        self.assertEqual(links(pricing)['implements Priced'], '1')
        order_calls = links(order)
        self.assertEqual(order_calls['extends BaseItem'], 'pricing|BaseItem')
        self.assertEqual(order_calls['this.price'], 'pricing|BaseItem.price')
        self.assertEqual(order_calls['discount'], 'pricing|discount')
        self.assertEqual(order_calls['prices.discount'], 'pricing|discount')
        self.assertEqual(order_calls['book.price'], 'pricing|BaseItem.price')
        self.assertEqual(order_calls['book.label'], '5')

    def test_syntax_error_and_reassigned_object(self):
        with self.assertRaises(ValueError):
            analyze(b'class {', 'broken.ts')
        with self.assertRaises(ValueError):
            analyze(b'function ( {', 'broken.js')
        html = analyze(b'class A { f() {} }\nfunction run(x) { let a = new A(); a = x; a.f(); }\n', 'reassign.js')
        self.assertTrue(links(html)['a.f'].startswith('?'))

    def test_typed_parameter_and_nested_function(self):
        html = analyze(b'class Box { open() {} }\nfunction run(box: Box) { function inner() { box.open(); } inner(); }\n', 'typed.ts')
        calls = links(html)
        self.assertEqual(calls['box.open'], '1')
        self.assertTrue(calls['inner'].startswith('?'))

    def test_top_level_arrow_functions(self):
        html = analyze('const double = (n: number) => n * 2;\nconst label = x => `값: ${double(x)}`;\nconsole.log(label(5));\n'.encode(), 'arrow.ts')
        root = fromstring(html)
        self.assertEqual([n.text for n in root.findall('details[@class="fn"]/summary/b')],
                         ['double(n: number)', 'label(x)'])
        calls = links(html)
        self.assertEqual(calls['double'], '1')
        self.assertEqual(calls['label'], '2')

    def test_export_default_and_this_property_object(self):
        base = analyze(b'export default class Animal {\n  speak() { return "..."; }\n}\n', 'animal.js')
        self.assertIn('data-default="true"', base)
        child = analyze(b'import Animal from "./animal";\nclass Engine {\n  start() {}\n}\nclass Dog extends Animal {\n  constructor() { super(); this.engine = new Engine(); }\n  run() { this.speak(); this.engine.start(); }\n}\n', 'dog.js')
        calls = links(child)
        self.assertEqual(calls['extends Animal'], 'animal|default')
        self.assertEqual(calls['this.speak'], 'animal|default.speak')
        self.assertEqual(calls['this.engine.start'], '3')


if __name__ == '__main__':
    unittest.main()

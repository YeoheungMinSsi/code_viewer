import re
import unittest
from viewer import ROOT, outline


def links(html):
    """{clicked text: data-target} for every call button."""
    return {text: target for target, text in re.findall(r'data-target="([^"]*)"[^>]*>([^<]*)</button>', html)}


class PythonOopTests(unittest.TestCase):
    def setUp(self):
        self.html = outline((ROOT / 'inheritance_example.py').read_bytes())
        self.calls = links(self.html)

    def test_inheritance_button_and_override_label(self):
        self.assertEqual(self.calls['상속 Animal'], '1')
        self.assertIn('함수 · 재정의(Animal)', self.html)

    def test_super_and_inherited_self_call(self):
        self.assertEqual(self.calls['super().__init__'], '2')
        self.assertEqual(self.calls['self.introduce'], '8')

    def test_overridden_self_call_is_not_guessed(self):
        self.assertTrue(self.calls['self.speak'].startswith('?자식 클래스 Dog'))

    def test_objects_inside_functions_and_entry(self):
        self.assertEqual(self.calls['Dog'], '12')
        self.assertEqual(self.calls['dog.learn'], '20')
        self.assertEqual(self.calls['make_dog'], '25')
        self.assertEqual(self.calls['animal.speak'], '5')

    def test_reassigned_or_unknown_objects_stay_unresolved(self):
        calls = links(outline(b'class A:\n def f(self):\n  pass\ndef g(x):\n a = A()\n a = x\n a.f()\n'))
        self.assertTrue(calls['a.f'].startswith('?'))
        calls = links(outline(b'class A(Base):\n def f(self):\n  self.g()\n'))
        self.assertTrue(calls['self.g'].startswith('?'))
        self.assertTrue(calls['상속 Base'].startswith('?'))

    def test_annotated_parameter(self):
        calls = links(outline(b'class A:\n def f(self):\n  pass\ndef run(item: A):\n item.f()\n'))
        self.assertEqual(calls['item.f'], '2')


if __name__ == '__main__':
    unittest.main()

import re
import unittest
from viewer import ROOT, outline


def links(html):
    """{clicked text: data-target} for every call button."""
    return {text: target for target, text in re.findall(r'data-target="([^"]*)"[^>]*>([^<]*)</button>', html)}


class PythonOopTests(unittest.TestCase):
    def setUp(self):
        self.html = outline((ROOT / 'examples' / 'inheritance_example.py').read_bytes())
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

    def test_multiple_inheritance_c3_mro(self):
        src = (
            b'class Base:\n def greet(self):\n  return "base"\n'
            b'class Left(Base):\n def greet(self):\n  return super().greet()\n'
            b'class Right(Base):\n def greet(self):\n  return "right"\n def tag(self):\n  return "R"\n'
            b'class Child(Left, Right):\n def run(self):\n  return self.greet(), self.tag(), super().greet()\n'
        )
        html = outline(src)
        calls = links(html)
        self.assertEqual(calls['상속 Left'], '4')
        self.assertEqual(calls['상속 Right'], '7')
        # Child.self.greet -> Left.greet (line 5), Child.self.tag -> Right.tag (line 10)
        self.assertEqual(calls['self.greet'], '5')
        self.assertEqual(calls['self.tag'], '10')
        # Left.super().greet() differs for Left (Base) vs Child (Right), so it must not guess.
        # Check line 6 specifically:
        line6 = html.split('<i>6</i>')[1].split('\n')[0]
        self.assertIn('?자식 클래스 Child', line6)
        # Child.super().greet() is unambiguous -> Left.greet (line 5)
        line14 = html.split('<i>14</i>')[1].split('\n')[0]
        self.assertIn('data-target="5"', line14)

    def test_cross_file_parent_class(self):
        src = (
            b'from animals import Animal\n'
            b'class Dog(Animal):\n'
            b' def __init__(self):\n'
            b'  super().__init__()\n'
            b' def run(self):\n'
            b'  self.speak()\n'
        )
        html = outline(src)
        calls = links(html)
        self.assertEqual(calls['상속 Animal'], 'animals|Animal')
        self.assertEqual(calls['super().__init__'], 'animals|Animal.__init__')
        self.assertEqual(calls['self.speak'], 'animals|Animal.speak')
        # Must not falsely claim override on an unknown external parent
        self.assertNotIn('재정의(Animal)', html)

    def test_self_attribute_object_call(self):
        src = (
            b'class Engine:\n def start(self):\n  pass\n'
            b'class Car:\n def __init__(self):\n  self.engine = Engine()\n def drive(self):\n  self.engine.start()\n'
            b'class Boat:\n def sail(self):\n  self.engine.start()\n'
        )
        calls = links(outline(src))
        # Car's self.engine.start links to Engine.start (line 2), Boat's does not
        html = outline(src)
        line8 = html.split('<i>8</i>')[1].split('\n')[0]
        line11 = html.split('<i>11</i>')[1].split('\n')[0]
        self.assertIn('data-target="2"', line8)
        self.assertIn('data-target="?', line11)
        # Rewritten attribute is not trusted
        reassigned = links(outline(
            b'class Engine:\n def start(self):\n  pass\n'
            b'class Car:\n def __init__(self):\n  self.engine = Engine()\n def swap(self, x):\n  self.engine = x\n  self.engine.start()\n'
        ))
        self.assertTrue(reassigned['self.engine.start'].startswith('?'))

    def test_nested_function_calls(self):
        src = (
            b'def helper():\n pass\n'
            b'class Box:\n def open(self):\n  pass\n'
            b' def work(self):\n  box = Box()\n  def inner():\n   helper()\n   box.open()\n   self.open()\n  inner()\n'
        )
        calls = links(outline(src))
        self.assertEqual(calls['helper'], '1')
        self.assertEqual(calls['box.open'], '4')
        self.assertEqual(calls['self.open'], '4')
        # inner() has no canvas card, so it stays unresolved rather than linking to anything wrong
        self.assertTrue(calls['inner'].startswith('?'))


if __name__ == '__main__':
    unittest.main()

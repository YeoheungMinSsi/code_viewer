import unittest
from viewer import ROOT, outline


class ViewerTest(unittest.TestCase):
    def test_example_structure(self):
        from xml.etree.ElementTree import fromstring
        root = fromstring(outline((ROOT / 'example.py').read_bytes()))
        self.assertEqual([n.text for n in root.findall('details/summary/b')], ['Order', 'show(order)', 'Cart'])
        methods = root.findall('details/section/details/summary/b')
        self.assertEqual([m.text for m in methods], ['total(self)', 'receipt(self)', 'refresh(self)'])
        self.assertIn('return self.total()', ''.join(root.itertext()))

    def test_class_members_in_order(self):
        from xml.etree.ElementTree import fromstring
        root = fromstring(outline(b'class A:\n x: int = 1\n def f(self):\n  local = 2\n if x:\n  y = 3'))
        members = root.findall('.//details/summary/b')
        self.assertEqual([m.text for m in members], ['A', 'x', 'f(self)', 'y'])
        self.assertEqual(len(root.findall('.//details[@class="var"]')), 2)

    def test_module_order_and_scope(self):
        from xml.etree.ElementTree import fromstring
        root = fromstring(outline(b'LIMIT=3\nclass A:\n def method(self):\n  pass\ndef independent():\n pass'))
        self.assertEqual([n.text for n in root.findall('details/summary/b')],
                         ['LIMIT', 'A', 'independent()'])
        self.assertEqual(root.find('details/summary/small').text, '전역변수')
        self.assertEqual(root.find('details/section/details/summary/b').text, 'method(self)')

    def test_fallback_and_error(self):
        self.assertIn('&lt;script&gt;', outline(b'x = "<script>"'))
        with self.assertRaises(SyntaxError):
            outline(b'class :')

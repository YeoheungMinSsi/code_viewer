import unittest
from unittest.mock import patch
from analyzers import ANALYZERS, analyze
from analyzers.python import outline

class AnalyzerTests(unittest.TestCase):
    def test_python(self):
        source = b'def hello():\n return 1'
        self.assertEqual(analyze(source, 'HELLO.PY'), outline(source))
    def test_unknown(self):
        with self.assertRaises(ValueError):
            analyze(b'class A {}', 'A.unsupported')
    def test_registration(self):
        with patch.dict(ANALYZERS, {'.demo': ('demo', 'Demo', lambda raw: '<section></section>')}):
            self.assertEqual(analyze(b'example', 'test.demo'), '<section></section>')

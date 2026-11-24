import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import viewer


class AutosaveTests(unittest.TestCase):
    def test_persistence_and_invalid_write_preserves_previous(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(viewer, 'AUTOSAVE', Path(directory) / 'work.json'):
            data = json.dumps({'version': 1, 'files': [{'source': '메모'}]})
            for run in range(2):
                server = viewer.ThreadingHTTPServer(('127.0.0.1', 0), viewer.Handler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                url = f'http://127.0.0.1:{server.server_port}'
                try:
                    if run == 0:
                        def post(body, origin):
                            return urlopen(Request(url + '/autosave', data=body.encode(), headers={'Content-Type': 'application/json', 'Origin': origin}))
                        with post(data, url) as response:
                            self.assertEqual(response.status, 200)
                        for body, origin in [('bad json', url), (data, 'https://example.com')]:
                            with self.assertRaises(HTTPError):
                                post(body, origin)
                    with urlopen(url + '/autosave') as response:
                        self.assertEqual(json.loads(response.read()), json.loads(data))
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()

class CSharpEndpointTests(unittest.TestCase):
    def test_project_links_and_invalid_payload(self):
        server = viewer.ThreadingHTTPServer(('127.0.0.1', 0), viewer.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}/csharp-links'
        try:
            files = {'A.cs': 'public class A { public int F(int x)=>x; }',
                     'B.cs': 'class B { void Run(A a){ a.F(1); } }'}
            request = Request(url, data=json.dumps(files).encode(), headers={'Content-Type':'application/json'})
            with urlopen(request) as response:
                data = json.load(response)
                self.assertEqual(next(iter(data['B.cs'].values()))['target'][0], 'A.cs')
            for invalid in [[], {'bad.cs': None}, {'bad.cs': 'class {'}]:
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(url, data=json.dumps(invalid).encode(), headers={'Content-Type':'application/json'}))
                self.assertEqual(error.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

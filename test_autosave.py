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

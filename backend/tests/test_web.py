"""The browser shell is public, while all personal API data stays authenticated."""
import http.client
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import service as s


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.folder.cleanup)
        root = Path(cls.folder.name)
        cls.web = root / 'web'
        cls.web.mkdir()
        (cls.web / 'index.html').write_text('<title>Fieldwork</title>')
        (cls.web / 'main.dart.js').write_text('console.log("Fieldwork")')
        (cls.web / 'canvaskit').mkdir()
        (cls.web / 'canvaskit' / 'canvaskit.wasm').write_bytes(b'wasm')
        (root / 'private.json').write_text('private')
        (cls.web / 'assets').mkdir()
        (cls.web / 'assets' / 'escape.json').symlink_to(root / 'private.json')
        (cls.web / 'assets' / '.hidden').write_text('hidden')
        cls.patcher = patch.object(s, 'WEB_DIR', cls.web)
        cls.patcher.start()
        cls.addClassCleanup(cls.patcher.stop)
        class Handler(s.Handler):
            token = 'test-browser-access-token'
        cls.server = s.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.addClassCleanup(cls.server.server_close)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.server.shutdown)

    def get(self, path, method='GET', token=False):
        c = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        headers = {'Authorization': 'Bearer test-browser-access-token'} if token else {}
        c.request(method, path, headers=headers)
        r = c.getresponse()
        result = r.status, dict(r.getheaders()), r.read()
        c.close()
        return result

    def test_shell_and_assets_load_without_credentials(self):
        for path, mime in [('/', 'text/html'), ('/index.html?v=1', 'text/html'),
                           ('/main.dart.js', 'text/javascript'),
                           ('/canvaskit/canvaskit.wasm', 'application/wasm')]:
            with self.subTest(path=path):
                status, headers, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertEqual(headers['Content-Type'], mime)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
                self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
                self.assertNotIn('Access-Control-Allow-Origin', headers)
                self.assertTrue(body)

    def test_personal_api_routes_still_require_bearer_token(self):
        for path in ['/health', '/cv', '/app', '/app/fieldwork.apk', '/applied',
                     '/gmail-sync', '/ranking/accounts', '/claude/chats', '/search/run']:
            with self.subTest(path=path):
                self.assertEqual(self.get(path)[0], 401)
        for method, path in [('POST', '/search'), ('POST', '/claude/chats'),
                             ('PATCH', '/applied/job'), ('DELETE', '/applied/job')]:
            with self.subTest(method=method, path=path):
                self.assertEqual(self.get(path, method=method)[0], 401)
        self.assertEqual(self.get('/health', token=True)[0], 200)

    def test_traversal_hidden_files_and_symlinks_are_not_served(self):
        for path in ['/assets/../../private.json', '/assets/%2e%2e/%2e%2e/private.json',
                     '/assets/escape.json', '/assets/.hidden', '/assets/missing.js',
                     '/index.html/../private.json', '/backend/.access-token',
                     '/backend/applied.json', '/private.json', '/lib/main.dart']:
            with self.subTest(path=path):
                status, _, body = self.get(path)
                self.assertIn(status, (401, 404))
                self.assertNotEqual(body, b'private')

    def test_missing_build_has_actionable_error(self):
        with patch.object(s, 'WEB_DIR', self.web / 'not-built'):
            status, _, body = self.get('/')
        self.assertEqual(status, 404)
        self.assertIn(b'scripts/build_web.sh', body)

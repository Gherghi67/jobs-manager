import copy
import datetime
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import service as s


def job(**kwargs):
    row = s.remote.job('himalayas', '123', 'Senior TypeScript Backend Engineer', 'Studio', 'https://example.com/job', location='Europe', type_field='Contractor', description='TypeScript Node.js backend', posted=datetime.date.today().isoformat())
    row.update(kwargs)
    return row

class RankingTests(unittest.TestCase):
    def setUp(self):
        self.options = s.validate_options({})
    def test_default_romania_and_remote_gates(self):
        rows = [job(), job(company='US', restrictions=['United States']), job(company='Hybrid', description='Hybrid TypeScript role'), job(company='Unknown', location='Remote')]
        self.assertEqual([r['company'] for r in s.rank(rows, self.options)], ['Studio'])
    def test_explicit_us_only_body_overrides_worldwide(self):
        self.assertEqual(s.rank([job(location='Worldwide', description='TypeScript backend. US-only role.')], self.options), [])
    def test_timezone_does_not_establish_country_eligibility(self):
        self.assertEqual(s.rank([job(location='CET timezone')], self.options), [])
    def test_country_list_wins_over_location_label(self):
        self.assertEqual(s.rank([job(location='Europe', restrictions=['Germany'])], self.options), [])
    def test_contract_hint_is_not_confirmed_contract(self):
        self.options['contract_only'] = True
        self.assertEqual(s.rank([job(type_field='Full-time', description='TypeScript backend with hourly rate')], self.options), [])
    def test_dedupes_sources_but_keeps_location_variants(self):
        rows = s.rank([job(), job(source='remotive'), job(location='Romania')], self.options)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['sources'], ['himalayas', 'remotive'])
    def test_custom_skills_replace_core(self):
        self.options['keywords'] = 'rust'
        self.assertEqual(s.rank([job()], self.options), [])
        self.assertEqual(len(s.rank([job(title='Senior Rust Engineer', description='Rust')], self.options)), 1)
    def test_unknown_eligibility_can_be_included(self):
        self.options['eligibility'] = 'romania_unclear'
        self.assertEqual(len(s.rank([job(location='Remote')], self.options)), 1)
    def test_age_filter_and_board_exception(self):
        self.assertEqual(s.rank([job(posted='2000-01-01')], self.options), [])
        self.assertEqual(len(s.rank([job(posted='2000-01-01', board=True)], self.options)), 1)
    def test_arbeitnow_does_not_invent_europe_wide_eligibility(self):
        class Http:
            def json(self, url):
                return {'data': [{'remote': True, 'slug': '123', 'title': 'TypeScript Engineer', 'company_name': 'Local', 'location': 'Berlin', 'url': 'https://example.com/job'}]}
        rows = s.remote.fetch_arbeitnow(Http(), {'pages': 1})
        self.assertEqual(rows[0]['location'], 'Remote, Berlin')
        self.options['eligibility'] = 'romania_unclear'
        self.assertEqual(s.rank(rows, self.options), [])

    def test_bad_options_rejected(self):
        for options in [{'boards': ['evil']}, {'adzuna': 'yes'}, {'max_age_days': True}, {'countries': []}, {'keywords': 1}, {'preset': 'bad'}, {'unknown': 1}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                s.validate_options(options)

class EngineTests(unittest.TestCase):
    def test_partial_failure_keeps_working_source(self):
        engine = s.Engine()
        o = s.validate_options({'adzuna': False, 'boards': ['remotive', 'remoteok'], 'ai_pick': False})
        engine.runs['x'] = {}
        with patch.dict(s.remote.SOURCES, {'remotive': lambda *a: [job()], 'remoteok': lambda *a: (_ for _ in ()).throw(ValueError('secret-url'))}):
            engine.run('x', o)
        result = engine.get('x')
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['jobs']), 1)
        self.assertEqual(result['sources'][1]['status'], 'error')
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['source'], 'remoteok')
        self.assertNotIn('secret-url', json.dumps(result))
    def test_cache_avoids_repeated_fetch(self):
        engine = s.Engine()
        calls = []
        def fetch():
            calls.append(1)
            return [job()]
        first, cached = engine.cached('x', fetch)
        first.clear()
        second, cached = engine.cached('x', fetch)
        self.assertTrue(cached)
        self.assertEqual(len(second), 1)
        self.assertEqual(len(calls), 1)

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = s.ThreadingHTTPServer(('127.0.0.1', 0), s.Handler)
        cls.token = 'test-token-not-a-real-credential'
        s.Handler.token = cls.token
        cls.url = 'http://127.0.0.1:%d' % cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
    def test_authentication_required(self):
        with self.assertRaises(HTTPError) as e:
            urlopen(self.url + '/health')
        self.assertEqual(e.exception.code, 401)
    def test_health_and_invalid_request(self):
        headers = {'Authorization': 'Bearer ' + self.token}
        with urlopen(Request(self.url + '/health', headers=headers)) as r:
            self.assertEqual(json.load(r)['status'], 'ok')
        with self.assertRaises(HTTPError) as e:
            urlopen(Request(self.url + '/search', data=b'{"max_age_days":999}', headers=headers))
        self.assertEqual(e.exception.code, 400)
    def test_app_release_and_download(self):
        headers = {'Authorization': 'Bearer ' + self.token}
        with tempfile.TemporaryDirectory() as folder, patch.object(s, 'APP_DIR', Path(folder)):
            with urlopen(Request(self.url + '/app', headers=headers)) as r:
                self.assertEqual(json.load(r), {'available': False})
            with self.assertRaises(HTTPError) as e:
                urlopen(Request(self.url + '/app/fieldwork.apk', headers=headers))
            self.assertEqual(e.exception.code, 404)
            apk = b'PK' + bytes(range(256)) * 5000
            (Path(folder) / 'fieldwork.apk').write_bytes(apk)
            (Path(folder) / 'fieldwork.json').write_text('{"version_code": 29700000, "version_name": "1.0.0"}')
            with urlopen(Request(self.url + '/app', headers=headers)) as r:
                self.assertEqual(json.load(r), {'available': True, 'version_code': 29700000, 'version_name': '1.0.0',
                                                'size': len(apk), 'sha256': s.hashlib.sha256(apk).hexdigest()})
            with urlopen(Request(self.url + '/app/fieldwork.apk', headers=headers)) as r:
                self.assertEqual(r.headers['Content-Type'], 'application/vnd.android.package-archive')
                self.assertEqual(r.read(), apk)
            with self.assertRaises(HTTPError) as e:
                urlopen(self.url + '/app/fieldwork.apk')
            self.assertEqual(e.exception.code, 401)
            (Path(folder) / 'fieldwork.json').write_text('{"version_code": "soon"}')
            with urlopen(Request(self.url + '/app', headers=headers)) as r:
                self.assertEqual(json.load(r), {'available': False})

if __name__ == '__main__':
    unittest.main()

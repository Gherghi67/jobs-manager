import copy
import datetime
import json
import os
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

class AppliedTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'applied.json'
        self.store = s.AppliedStore(self.path)
        self.job = s.rank([job()], s.validate_options({}))[0]

    def test_applied_jobs_persist_privately(self):
        first = self.store.add(self.job)
        self.assertEqual(first['title'], 'Senior TypeScript Backend Engineer')
        self.assertIn('applied_at', first)
        # Marking the same job twice keeps the original date.
        self.assertEqual(self.store.add(self.job)['applied_at'], first['applied_at'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        reloaded = s.AppliedStore(self.path)
        self.assertEqual([j['id'] for j in reloaded.list()], [self.job['id']])
        self.assertTrue(reloaded.remove(self.job['id']))
        self.assertFalse(reloaded.remove(self.job['id']))
        self.assertEqual(s.AppliedStore(self.path).list(), [])

    def test_keeps_only_known_fields_and_caps_description(self):
        record = self.store.add(dict(self.job, description='x' * 9000, secret='no'))
        self.assertNotIn('secret', record)
        self.assertEqual(len(record['description']), 6000)

    def test_invalid_jobs_rejected(self):
        for bad in [[], {'id': 'a', 'title': 'T'}, dict(self.job, url='javascript:alert(1)'), dict(self.job, id='x' * 65), dict(self.job, company=3)]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.store.add(bad)

    def test_exclude_matches_id_url_and_company_title(self):
        self.store.add(self.job)
        same_role_elsewhere = job(location='Romania', url='https://other.example/apply')
        same_url = job(company='Agency', title='Backend Engineer', url='https://www.example.com/job/#apply')
        other = job(company='Another', title='Senior TypeScript Backend Engineer', url='https://example.com/other')
        kept, hidden = self.store.exclude([dict(self.job), same_role_elsewhere, same_url, other])
        self.assertEqual([j['company'] for j in kept], ['Another'])
        self.assertEqual(hidden, 3)

    def test_company_title_needs_a_company(self):
        self.store.add(dict(self.job, company='', url='https://example.com/a'))
        kept, hidden = self.store.exclude([job(company='', url='https://example.com/b')])
        self.assertEqual((len(kept), hidden), (1, 0))

    def test_company_entry_hides_every_role_at_that_company(self):
        entry = self.store.add({'scope': 'company', 'company': 'Studio GmbH', 'title': 'Backend Engineer', 'applied_at': '2026-10-02T09:15:00+00:00', 'note': 'Thanks for applying'})
        self.assertEqual((entry['company_key'], entry['applied_at']), ('studio', '2026-10-02T09:15:00+00:00'))
        merged = self.store.add({'scope': 'company', 'company': 'studio', 'title': 'Platform Engineer'})
        self.assertEqual(merged['id'], entry['id'])
        self.assertEqual(merged['title'], 'Backend Engineer; Platform Engineer')
        self.assertEqual(len(self.store.list()), 1)
        rows = s.rank([job(title='Senior Python Engineer', description='Python backend', url='https://example.com/a'),
                       job(company='Studio Inc.', url='https://example.com/b'), job(company='Studios United', url='https://example.com/c')],
                      s.validate_options({}))
        kept, hidden = self.store.exclude(rows)
        self.assertEqual([j['company'] for j in kept], ['Studios United'])
        self.assertEqual(hidden, 2)

    def rows(self):
        return s.rank([job(url='https://example.com/a'), job(title='Senior Python Engineer', description='Python backend', url='https://example.com/b'),
                       job(company='Other', url='https://example.com/c')], s.validate_options({}))

    def test_role_match_hides_only_the_named_roles(self):
        entry = self.store.add({'scope': 'company', 'company': 'Studio', 'title': 'Senior TypeScript Backend Engineer'})
        self.assertEqual(self.store.set_match(entry['id'], 'role')['match'], 'role')
        kept, hidden = self.store.exclude(self.rows())
        self.assertEqual(sorted(j['title'] for j in kept), ['Senior Python Engineer', 'Senior TypeScript Backend Engineer'])
        self.assertEqual([j['company'] for j in kept if j['title'] == 'Senior TypeScript Backend Engineer'], ['Other'])
        self.assertEqual(hidden, 1)

    def test_badge_match_marks_roles_and_puts_them_last(self):
        entry = self.store.add({'scope': 'company', 'company': 'Studio AB', 'applied_at': '2026-10-07T18:10:28Z', 'match': 'badge'})
        kept, hidden = self.store.exclude(self.rows())
        self.assertEqual(hidden, 0)
        self.assertEqual([j['company'] for j in kept], ['Other', 'Studio', 'Studio'])
        self.assertEqual(kept[-1]['applied_badge'], {'company': 'Studio AB', 'applied_at': '2026-10-07T18:10:28Z'})
        self.assertNotIn('applied_badge', kept[0])
        self.assertEqual(s.AppliedStore(self.path).list()[0]['match'], 'badge')
        self.assertEqual(self.store.set_match(entry['id'], 'company')['match'], 'company')
        self.assertEqual([j['company'] for j in self.store.exclude(self.rows())[0]], ['Other'])

    def test_match_changes_validated(self):
        untitled = self.store.add({'scope': 'company', 'company': 'Studio'})
        listing = self.store.add(self.job)
        for match in ('role', 'everything', None):
            with self.subTest(match=match), self.assertRaises(ValueError):
                self.store.set_match(untitled['id'], match)
        self.assertIsNone(self.store.set_match(listing['id'], 'badge'))
        self.assertIsNone(self.store.set_match('missing', 'badge'))
        with self.assertRaises(ValueError):
            self.store.add({'scope': 'company', 'company': 'New', 'match': 'role'})

    def test_company_entries_validated(self):
        for bad in [{'scope': 'company'}, {'scope': 'company', 'company': ' . '}, {'scope': 'company', 'company': 'X', 'applied_at': 'last week'}]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.store.add(bad)

    def test_company_key_drops_legal_suffixes(self):
        for name in ['Proxify AB', 'proxify', 'Proxify, Inc.', 'PROXIFY Sp. z o.o.']:
            self.assertEqual(s.company_key(name), 'proxify')
        self.assertEqual(s.company_key('AB'), 'ab')

    def test_unreadable_file_is_never_overwritten(self):
        self.path.write_text('{not json')
        with self.assertRaises(s.StoreError):
            self.store.add(self.job)
        self.assertEqual(self.path.read_text(), '{not json')


class EngineTests(unittest.TestCase):
    def store(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        return s.AppliedStore(Path(folder.name) / 'applied.json')

    def test_applied_roles_are_left_out_before_claude(self):
        engine = s.Engine(self.store())
        engine.applied.add(s.rank([job()], s.validate_options({}))[0])
        o = s.validate_options({'adzuna': False, 'boards': ['remotive']})
        engine.runs['x'] = {}
        seen = []
        def pick(jobs, o, cache):
            seen.extend(j['company'] for j in jobs)
            return jobs, dict(status='ok', ranked=len(jobs), shortlist=len(jobs))
        with patch.dict(s.remote.SOURCES, {'remotive': lambda *a: [job(), job(company='Fresh', url='https://example.com/fresh')]}), patch.object(s.ai, 'pick', pick):
            engine.run('x', o)
        result = engine.get('x')
        self.assertEqual(seen, ['Fresh'])
        self.assertEqual([j['company'] for j in result['jobs']], ['Fresh'])
        self.assertEqual(result['applied_hidden'], 1)

    def test_badged_roles_stay_last_after_claude(self):
        engine = s.Engine(self.store())
        engine.applied.add({'scope': 'company', 'company': 'Studio', 'match': 'badge'})
        o = s.validate_options({'adzuna': False, 'boards': ['remotive']})
        engine.runs['x'] = {}
        def pick(jobs, o, cache):
            # Claude puts the badged role first; the service moves it back down.
            return sorted(jobs, key=lambda j: j['company'] != 'Studio'), dict(status='ok', ranked=len(jobs), shortlist=len(jobs))
        with patch.dict(s.remote.SOURCES, {'remotive': lambda *a: [job(), job(company='Fresh', url='https://example.com/fresh')]}), patch.object(s.ai, 'pick', pick):
            engine.run('x', o)
        result = engine.get('x')
        self.assertEqual([j['company'] for j in result['jobs']], ['Fresh', 'Studio'])
        self.assertEqual(result['jobs'][1]['applied_badge']['company'], 'Studio')
        self.assertEqual(result['applied_hidden'], 0)

    def test_partial_failure_keeps_working_source(self):
        engine = s.Engine(self.store())
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
        cls.folder = tempfile.TemporaryDirectory()
        cls.engine = s.Handler.engine
        s.Handler.engine = s.Engine(s.AppliedStore(Path(cls.folder.name) / 'applied.json'))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        s.Handler.engine = cls.engine
        cls.folder.cleanup()
    def call(self, method, path, body=None, token=True):
        headers = {'Authorization': 'Bearer ' + self.token} if token else {}
        data = json.dumps(body).encode() if body is not None else None
        with urlopen(Request(self.url + path, data=data, headers=headers, method=method)) as r:
            return json.load(r)
    def test_applied_endpoints(self):
        row = s.rank([job()], s.validate_options({}))[0]
        self.assertEqual(self.call('GET', '/applied'), {'jobs': []})
        self.assertEqual(self.call('POST', '/applied', row)['job']['id'], row['id'])
        self.assertEqual([j['id'] for j in self.call('GET', '/applied')['jobs']], [row['id']])
        with self.assertRaises(HTTPError) as e:
            self.call('POST', '/applied', {'title': 'No id'})
        self.assertEqual(e.exception.code, 400)
        for method, path in [('GET', '/applied'), ('DELETE', '/applied/' + row['id'])]:
            with self.subTest(method=method), self.assertRaises(HTTPError) as e:
                self.call(method, path, token=False)
            self.assertEqual(e.exception.code, 401)
        entry = self.call('POST', '/applied', {'scope': 'company', 'company': 'Proxify AB'})['job']
        self.assertEqual(self.call('PATCH', '/applied/' + entry['id'], {'match': 'badge'})['job']['match'], 'badge')
        for path, body, code in [('/applied/' + entry['id'], {'match': 'role'}, 400), ('/applied/missing', {'match': 'badge'}, 404),
                                 ('/applied/' + row['id'], {'match': 'badge'}, 404)]:
            with self.subTest(path=path, body=body), self.assertRaises(HTTPError) as e:
                self.call('PATCH', path, body)
            self.assertEqual(e.exception.code, code)
        with self.assertRaises(HTTPError) as e:
            self.call('PATCH', '/applied/' + entry['id'], {'match': 'company'}, token=False)
        self.assertEqual(e.exception.code, 401)
        self.assertEqual(self.call('DELETE', '/applied/' + entry['id']), {'removed': True})
        self.assertEqual(self.call('DELETE', '/applied/' + row['id']), {'removed': True})
        self.assertEqual(self.call('DELETE', '/applied/' + row['id']), {'removed': False})
        self.assertEqual(self.call('GET', '/applied'), {'jobs': []})
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
    def test_cv_download(self):
        headers = {'Authorization': 'Bearer ' + self.token}
        with tempfile.TemporaryDirectory() as folder, patch.object(s, 'CV_DIR', Path(folder)):
            with self.assertRaises(HTTPError) as e:
                urlopen(Request(self.url + '/cv', headers=headers))
            self.assertEqual(e.exception.code, 404)
            self.assertIn('cv folder', json.load(e.exception)['error'])
            old, new = Path(folder) / 'Old CV.pdf', Path(folder) / 'Bogdan-Gherghina-CV.pdf'
            old.write_bytes(b'%PDF-old')
            new.write_bytes(b'%PDF-1.5 new')
            (Path(folder) / 'notes.txt').write_text('not a CV')
            os.utime(old, ns=(1, 1))
            with urlopen(Request(self.url + '/cv', headers=headers)) as r:
                self.assertEqual(r.headers['Content-Type'], 'application/pdf')
                self.assertEqual(r.headers['Content-Disposition'], 'attachment; filename="Bogdan-Gherghina-CV.pdf"')
                self.assertEqual(r.read(), b'%PDF-1.5 new')
            with self.assertRaises(HTTPError) as e:
                urlopen(self.url + '/cv')
            self.assertEqual(e.exception.code, 401)
        self.assertEqual(s.download_name(Path('Ștefan "CV".PDF')), 'Stefan -CV-.PDF')
        self.assertEqual(s.download_name(Path('.pdf')), 'CV.pdf')

if __name__ == '__main__':
    unittest.main()

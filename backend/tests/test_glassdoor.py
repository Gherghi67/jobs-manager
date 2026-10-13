import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['JOBS_LINKEDIN'] = 'off'
os.environ['JOBS_GLASSDOOR'] = 'off'
import glassdoor
import jev
import linkedin
import service as s

TODAY = datetime.date.today().isoformat()
RESULTS = 'https://www.glassdoor.com/Job/romania-backend-engineer-remote-jobs-SRCH_IL.0,7_IN203_KO8,31.htm'
LISTING = 'https://www.glassdoor.com/job-listing/senior-backend-engineer-it-labs-JV_IC3184907_KO0,23_KE24,31.htm'


def item(**kwargs):
    row = dict(id='1010289920322', url=LISTING + '?jl=1010289920322', title='Senior Backend Engineer (Remote)',
               company='IT Labs', location='Bucharest, Bucuresti, Romania', workplace=None, countries=None,
               posted=TODAY + 'T00:00:00', employment=['FULL_TIME'], salary='',
               description='Remote backend role building Node.js and TypeScript services on AWS.')
    row.update(kwargs)
    return row


def click(label, role='button', kind='click'):
    return dict(id='a1', kind=kind, label=label, role=role, node=1)


class GuardTests(unittest.TestCase):
    def test_refuses_controls_that_change_the_account_or_post_content(self):
        for label in ('Easy Apply', 'Apply on employer site', 'Save job', 'Create job alert', 'Tailor my resume',
                      'Get insights', 'Let employers find and reach out to you', 'Write a review', 'Add a salary',
                      'Not interested', 'Share', 'Sign Out', 'Upload resume', 'Get recruited instead',
                      'Glassdoor Recruiter'):
            with self.subTest(label=label):
                self.assertIsNotNone(glassdoor.refused(click(label)))
        self.assertIsNotNone(glassdoor.refused(click('Open to offers', role='switch')))
        self.assertIsNotNone(glassdoor.refused(click('Easy Apply only', role='checkbox')))

    def test_allows_the_search_controls(self):
        for action in (click('Find your perfect job', role='combobox', kind='fill'),
                       click('City, state, zipcode, or "remote"', role='combobox', kind='fill'),
                       click('Romania', role='option'), click('Search'), click('Clear'),
                       dict(id='s1', kind='scroll', label='Save job')):
            with self.subTest(action=action['label']):
                self.assertIsNone(glassdoor.refused(action))


class RequestTests(unittest.TestCase):
    def test_one_phrase_with_remote_and_the_preset_otherwise(self):
        o = s.validate_options({'keywords': 'Node.js, NestJS'})
        self.assertEqual(glassdoor.request(o), dict(query='Node.js remote', location='Romania', limit=glassdoor.LIMIT))
        o = s.validate_options({'remote_only': False, 'preset': 'gaming'})
        self.assertEqual(glassdoor.request(o)['query'], 'game backend engineer')

    def test_goal_names_the_search_and_forbids_account_changes(self):
        goal = glassdoor.goal(dict(query='backend engineer remote', location='Romania', limit=25))
        self.assertIn('"backend engineer remote" in Romania', goal)
        for phrase in ('Do not use filters', 'apply to, save', 'job alert', 'review or add a salary', 'employers contact me'):
            self.assertIn(phrase, goal)


class ResultCheckTests(unittest.TestCase):
    req = dict(query='backend engineer remote', location='Romania', limit=25)

    def test_the_requested_search_page_passes(self):
        self.assertEqual(glassdoor.check_results(RESULTS, self.req), [])
        self.assertTrue(glassdoor.searched(RESULTS, self.req))
        self.assertEqual(glassdoor.spans('romania-backend-engineer-remote', 'IL.0,7_IN203_KO8,31'),
                         dict(location='romania', keywords='backend engineer remote'))

    def test_other_pages_and_searches_fail(self):
        for url in ('https://www.glassdoor.com/Job/index.htm',
                    'https://www.glassdoor.com/Job/romania-frontend-engineer-jobs-SRCH_IL.0,7_IN203_KO8,25.htm',
                    'https://www.glassdoor.com/job-listing/x-JV_KO0,1.htm?jl=1',
                    'https://evil.example/Job/romania-backend-engineer-remote-jobs-SRCH_IL.0,7_IN203_KO8,31.htm'):
            with self.subTest(url=url):
                self.assertFalse(glassdoor.searched(url, self.req))
                with self.assertRaises(glassdoor.GlassdoorError):
                    glassdoor.check_results(url, self.req)

    def test_another_location_fails_and_an_unshown_one_warns(self):
        with self.assertRaises(glassdoor.GlassdoorError):
            glassdoor.check_results('https://www.glassdoor.com/Job/united-states-backend-engineer-remote-jobs-SRCH_IL.0,13_IN1_KO14,37.htm', self.req)
        url = 'https://www.glassdoor.com/Job/backend-engineer-remote-jobs-SRCH_KO0,23.htm'
        self.assertEqual(len(glassdoor.check_results(url, self.req)), 1)
        self.assertFalse(glassdoor.searched(url, self.req))
        self.assertEqual(glassdoor.check_results(url, self.req, ['backend engineer remote', 'Romania']), [])


class JobTests(unittest.TestCase):
    def test_runner_items_become_jobs(self):
        rows = glassdoor.to_jobs([item(), item(id='x'), item(id='12345', company=''), 'junk',
                                  item(id='22222', url='https://evil.example/job-listing/a.htm?jl=22222')], s.remote.job)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['id'], 'glassdoor:1010289920322')
        self.assertEqual(row['url'], LISTING + '?jl=1010289920322')
        self.assertEqual((row['posted'], row['type_field'], row['restrictions']), (TODAY, 'Full-time', None))

    def test_remote_roles_carry_where_applicants_may_live(self):
        row = glassdoor.to_jobs([item(workplace='TELECOMMUTE', countries={'@type': 'Country', 'name': 'United States'},
                                      employment='CONTRACTOR')], s.remote.job)[0]
        self.assertEqual((row['location'], row['restrictions'], row['type_field']), ('United States (Remote)', ['United States'], 'Contract'))
        row = glassdoor.to_jobs([item(workplace='TELECOMMUTE', location='Romania')], s.remote.job)[0]
        self.assertEqual((row['location'], row['restrictions']), ('Romania (Remote)', None))

    def test_ranking_keeps_romania_and_drops_us_only_remote(self):
        rows = glassdoor.to_jobs([item(), item(id='22222', title='Senior Backend Engineer', workplace='TELECOMMUTE',
                                               countries=[{'@type': 'Country', 'name': 'United States'}])], s.remote.job)
        ranked = s.rank(rows, s.validate_options({}))
        self.assertEqual([j['source'] for j in ranked], ['glassdoor'])
        self.assertEqual(ranked[0]['eligibility'], 'europe')

    def test_bad_dates_leave_no_date(self):
        for value in (None, 'today', 5, '2026-13-40'):
            self.assertEqual(glassdoor.posted_date(value), '')


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.options = s.validate_options({})
        patcher = patch.object(glassdoor, 'enabled', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_with(self, result, record=None):
        def fake(cmd, **kwargs):
            self.call = (cmd, kwargs)
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(result), stderr='')
        with patch.object(jev.subprocess, 'run', fake), patch.dict(os.environ, {'ADZUNA_APP_KEY': 'a'}):
            return glassdoor.fetch(self.options, s.remote.job, record=record)

    def test_runs_its_own_runner_and_records_usage_as_glassdoor(self):
        recorded = []
        rows, warnings = self.run_with(dict(status='ok', jobs=[item()], warnings=['1 Glassdoor job details could not be read.'],
                                            usage=dict(requests=3)), recorded.append)
        self.assertEqual((len(rows), warnings), (1, ['1 Glassdoor job details could not be read.']))
        cmd, kwargs = self.call
        self.assertEqual(cmd[1:], ['-I', str(glassdoor.RUNNER)])
        self.assertNotIn('ADZUNA_APP_KEY', kwargs['env'])
        self.assertIn('Search Glassdoor Jobs', json.loads(kwargs['input'])['goal'])
        self.assertEqual(recorded, [dict(requests=3, source='glassdoor')])

    def test_failures_and_a_missing_install_raise_a_message_for_the_app(self):
        with self.assertRaises(glassdoor.GlassdoorError) as caught:
            self.run_with(dict(status='error', message='Glassdoor kept covering "Search"; the browser agent stopped.'))
        self.assertIn('kept covering', str(caught.exception))
        with patch.object(glassdoor, 'enabled', return_value=False), self.assertRaises(glassdoor.GlassdoorError):
            glassdoor.fetch(self.options, s.remote.job)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = s.Engine(s.AppliedStore(Path(self.folder.name) / 'applied.json'),
                               s.JevUsage(Path(self.folder.name) / 'jev-usage.json'))
        self.engine.runs['x'] = {}

    def run_search(self, fetch, **options):
        o = s.validate_options({'adzuna': False, 'boards': ['remotive'], 'ai_pick': False, **options})
        def linkedin_fetch(o, job, record=None, runner=None):
            record(dict(requests=2, input_tokens=9000))
            return [], []
        with patch.object(linkedin, 'enabled', return_value=True), patch.object(linkedin, 'fetch', linkedin_fetch), \
             patch.object(glassdoor, 'enabled', return_value=True), patch.object(glassdoor, 'fetch', fetch), \
             patch.dict(s.remote.SOURCES, {'remotive': lambda *a: []}):
            self.engine.run('x', o)
        return self.engine.get('x')

    def test_glassdoor_runs_after_linkedin_and_its_roles_are_ranked(self):
        def fetch(o, job, record=None, runner=None):
            record(dict(requests=3, input_tokens=15000, source='glassdoor'))
            return glassdoor.to_jobs([item()], job), []
        result = self.run_search(fetch)
        self.assertEqual([x['name'] for x in result['sources']], ['remotive', 'linkedin', 'glassdoor'])
        self.assertEqual([j['source'] for j in result['jobs']], ['glassdoor'])
        usage = self.engine.jev_usage.summary()
        self.assertEqual((usage['last']['source'], usage['total']['runs'], usage['total']['requests']), ('glassdoor', 2, 5))

    def test_errors_keep_their_message_and_the_switch_works(self):
        def fail(o, job, record=None, runner=None):
            raise glassdoor.GlassdoorError('No open Chrome profile is signed in to LinkedIn.')
        result = self.run_search(fail)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['sources'][2]['message'], 'No open Chrome profile is signed in to LinkedIn.')
        def never(o, job, record=None, runner=None):
            raise AssertionError('Glassdoor should not run')
        result = self.run_search(never, glassdoor=False)
        self.assertEqual([x['name'] for x in result['sources']], ['remotive', 'linkedin'])

    def test_glassdoor_alone_is_a_valid_source(self):
        with patch.object(glassdoor, 'enabled', return_value=True):
            s.validate_options({'adzuna': False, 'linkedin': False, 'boards': []})
        with self.assertRaises(ValueError):
            s.validate_options({'adzuna': False, 'linkedin': False, 'boards': [], 'glassdoor': True})
        with patch.object(glassdoor, 'enabled', return_value=True), self.assertRaises(ValueError):
            s.validate_options({'glassdoor': 'yes'})


if __name__ == '__main__':
    unittest.main()

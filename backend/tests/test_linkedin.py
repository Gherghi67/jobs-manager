import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['JOBS_LINKEDIN'] = 'off'
import linkedin
import linkedin_jev as runner
import service as s

TODAY_MS = int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)
RESULTS = 'https://www.linkedin.com/jobs/search/?keywords=backend%20engineer%20remote&location=Romania&geoId=106670623'


def item(**kwargs):
    row = dict(id='4467450237', title='Senior Backend Engineer - Node.js & AWS (Remote)', company='Quik Hire Staffing',
               location='EMEA', workplace=2, listed_at=TODAY_MS, employment='Full-time',
               description='Senior backend role building TypeScript and Node.js services on AWS.')
    row.update(kwargs)
    return row


def click(label, role='button', kind='click'):
    return dict(id='a1', kind=kind, label=label, role=role, node=1)


class GuardTests(unittest.TestCase):
    def test_refuses_controls_that_change_the_account(self):
        for label in ('Easy Apply to Senior Backend Engineer at Nango', 'Candidatură simplă pentru postul de Senior AI Engineer la E.ON',
                      'Salvați Salvați Senior AI Engineer (f/m/d) la E.ON', 'Save Senior Backend Engineer at Nango',
                      'Ignorați jobul Senior AI Engineer (f/m/d)', 'Dismiss Senior Backend Engineer job', 'Distribuiți',
                      'Compuneți mesaj', 'Message', 'Follow', 'Urmăriți', 'Set alert', 'Filtru Candidatură simplă.', 'Applied AI Engineer',
                      'Editați preferințele de căutare de joburi', 'Edit job search preferences'):
            self.assertTrue(linkedin.refused(click(label)), label)
        self.assertTrue(linkedin.refused(click('', role='switch')))

    def test_allows_search_and_filter_controls(self):
        for action in (click('Căutați după titlul jobului, cuvinte cheie sau numele companiei', role='combobox', kind='fill'),
                       click('Search by title, skill, or company', role='combobox', kind='fill'),
                       click('Căutați'), click('Filtru La distanță. Cu un clic pe acest buton se afișează toate opțiunile'),
                       click('Filtru Data postării. Cu un clic pe acest buton se afișează toate opțiunile'),
                       click('Aplicați filtrul curent pentru a afișa peste 100 de rezultate'),
                       click('Apply current filter to show 1,000+ results'), click('Dismiss'),
                       click('backend engineer', role='option'), dict(id='scroll_down', kind='scroll', label='Scroll down'),
                       dict(id='wait', kind='wait', label='Wait for the page to update')):
            self.assertIsNone(linkedin.refused(action), action['label'])


class RequestTests(unittest.TestCase):
    def test_keywords_become_one_query_with_remote(self):
        self.assertEqual(linkedin.request(s.validate_options({'keywords': 'NestJS, Go, Python, Rust'}))['query'],
                         '(NestJS OR Go OR Python) remote')
        self.assertEqual(linkedin.request(s.validate_options({'keywords': 'NestJS'}))['query'], 'NestJS remote')
        req = linkedin.request(s.validate_options({'preset': 'backend', 'remote_only': False, 'max_age_days': 7}))
        self.assertEqual(req, dict(query='Node.js backend', location=linkedin.LOCATION, limit=linkedin.LIMIT))

    def test_goal_names_the_search_and_forbids_filters_and_account_changes(self):
        text = linkedin.goal(linkedin.request(s.validate_options({})))
        self.assertIn('"backend engineer remote" in Romania', text)
        self.assertIn('Do not use filters or change job preferences', text)
        self.assertIn('Do not open, apply to, save', text)


class ResultCheckTests(unittest.TestCase):
    req = linkedin.request(s.validate_options({}))

    def test_matching_search_passes(self):
        self.assertEqual(linkedin.check_results(RESULTS, self.req), [])
        self.assertEqual(linkedin.check_results(RESULTS.replace('Romania', 'Rom%C3%A2nia'), self.req), [])
        self.assertEqual(linkedin.check_results(RESULTS + '&f_WT=2&currentJobId=1', self.req), [])

    def test_unshown_location_is_a_warning(self):
        url = 'https://www.linkedin.com/jobs/search/?keywords=Backend+Engineer+Remote&geoId=1'
        self.assertEqual(len(linkedin.check_results(url, self.req)), 1)
        self.assertEqual(linkedin.check_results(url, self.req, ['backend engineer remote', 'România']), [])

    def test_wrong_page_or_search_is_an_error(self):
        for url in ('https://www.linkedin.com/jobs/search/?keywords=backend%20engineer&location=Romania',
                    'https://www.linkedin.com/jobs/view/4467450237/', 'https://www.linkedin.com/feed/',
                    'https://evil.example/jobs/search/?keywords=backend%20engineer%20remote',
                    'https://www.linkedin.com/jobs/search/?keywords=backend%20engineer%20remote&location=Germany'):
            with self.assertRaises(linkedin.LinkedInError, msg=url):
                linkedin.check_results(url, self.req)


class JobTests(unittest.TestCase):
    def test_runner_items_become_jobs(self):
        rows = linkedin.to_jobs([item(), item(id='x'), item(id='123456', title=''), 'junk'], s.remote.job)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['url'], 'https://www.linkedin.com/jobs/view/4467450237/')
        self.assertEqual(row['location'], 'EMEA (Remote)')
        self.assertEqual(row['posted'], datetime.date.today().isoformat())
        self.assertEqual((row['source'], row['id']), ('linkedin', 'linkedin:4467450237'))

    def test_remote_emea_role_passes_ranking_and_hybrid_does_not(self):
        rows = linkedin.to_jobs([item(), item(id='4465712623', company='Other', workplace=3)], s.remote.job)
        ranked = s.rank(rows, s.validate_options({}))
        self.assertEqual([r['company'] for r in ranked], ['Quik Hire Staffing'])
        self.assertEqual(ranked[0]['eligibility'], 'europe')

    def test_bad_timestamps_leave_no_date(self):
        for value in (None, 'today', -5, 1.5, True):
            self.assertEqual(linkedin.posted_date(value), '')


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.options = s.validate_options({})
        patcher = patch.object(linkedin, 'enabled', return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_with(self, stdout='', exc=None):
        def fake(cmd, **kwargs):
            self.call = (cmd, kwargs)
            if exc:
                raise exc
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr='hint\n')
        with patch.object(linkedin.subprocess, 'run', fake), \
             patch.dict(os.environ, {'ADZUNA_APP_KEY': 'a', 'JOBS_ACCESS_TOKEN': 'b', 'ANTHROPIC_API_KEY': 'c', 'PYTHONPATH': 'x'}):
            return linkedin.fetch(self.options, s.remote.job)

    def test_success_returns_jobs_and_warnings(self):
        out = json.dumps(dict(status='ok', jobs=[item()], warnings=['2 LinkedIn job details could not be read.']))
        rows, warnings = self.run_with('noise\n' + out + '\n')
        self.assertEqual(len(rows), 1)
        self.assertEqual(warnings, ['2 LinkedIn job details could not be read.'])
        cmd, kwargs = self.call
        self.assertEqual(cmd[1:], ['-I', str(linkedin.RUNNER)])
        self.assertEqual(kwargs['cwd'], linkedin.JEV_DIR)
        sent = json.loads(kwargs['input'])
        self.assertEqual(sent['query'], 'backend engineer remote')
        self.assertIn('"backend engineer remote"', sent['goal'])

    def test_child_gets_no_service_credentials(self):
        self.run_with(json.dumps(dict(status='ok', jobs=[])))
        env = self.call[1]['env']
        for name in ('ADZUNA_APP_KEY', 'JOBS_ACCESS_TOKEN', 'ANTHROPIC_API_KEY', 'PYTHONPATH'):
            self.assertNotIn(name, env)
        self.assertIn('PATH', env)

    def test_failures_raise_a_message_for_the_app(self):
        cases = [(json.dumps(dict(status='error', message='No open Chrome profile is signed in to LinkedIn.')), None,
                  'No open Chrome profile'),
                 ('Traceback', None, 'without a result'),
                 ('', subprocess.TimeoutExpired('python', 240), 'did not finish in time')]
        for stdout, exc, expected in cases:
            with self.assertRaises(linkedin.LinkedInError) as caught:
                self.run_with(stdout, exc)
            self.assertIn(expected, str(caught.exception))

    def test_missing_install_is_reported(self):
        with patch.object(linkedin, 'enabled', return_value=False), self.assertRaises(linkedin.LinkedInError):
            linkedin.fetch(self.options, s.remote.job)


class Stale(Exception):
    pass


class FakeAgent:
    """Plays (choice, action, url after acting) steps through Agent's predict/act commands.
    A url of STALE makes that execution find the page changed, as jev's act does."""
    def __init__(self, steps, url='https://www.linkedin.com/jobs/search/'):
        self.steps, self.acted, self.keys = list(steps), [], []
        self.state = dict(status='ready', decision=None, page=self.page(url, []), decisions=[], history=[])
        self.browser = self

    def page(self, url, actions):
        return dict(url=url, actions=actions, fingerprint=url)

    def observe(self, screenshot=False):
        return self.state['page']

    def call(self, method, **params):
        self.keys.append((params['type'], params['key']))

    def command(self, name, body=None):
        choice, action, url = self.steps[0]
        if name == 'predict':
            self.state['page'] = self.page(self.state['page']['url'], [action] if action else [])
            self.state['decision'] = dict(choice=choice)
            self.state['decisions'].append(choice)
            return
        self.steps.pop(0)
        if url == 'STALE':
            raise Stale()
        self.acted.append(choice)
        if choice in ('DONE', 'BLOCKED'):
            self.state['status'] = choice.lower()
        else:
            self.state['history'].append(choice)
            self.state['page'] = self.page(url, [])


class DriveTests(unittest.TestCase):
    def drive(self, agent, deadline=None):
        self.log = []
        return runner.drive(agent, Stale, deadline or time.monotonic() + 30, self.log)

    def test_search_runs_until_done(self):
        fill = click('Căutați după titlul jobului', role='combobox', kind='fill')
        agent = FakeAgent([('a1', fill, 'https://www.linkedin.com/jobs/search/'), ('a1', click('Căutați'), 'STALE'),
                           ('a1', click('Căutați'), RESULTS), ('DONE', None, RESULTS)])
        self.assertEqual(self.drive(agent), 2)
        self.assertEqual(agent.acted, ['a1', 'a1', 'DONE'])
        self.assertEqual(self.log, ['Căutați după titlul jobului', 'Căutați (stale)', 'Căutați', 'DONE'])

    def test_refused_action_never_executes(self):
        agent = FakeAgent([('a1', click('Candidatură simplă pentru postul de Senior AI Engineer'), RESULTS)])
        with self.assertRaises(linkedin.LinkedInError) as caught:
            self.drive(agent)
        self.assertEqual(agent.acted, [])
        self.assertIn('nothing was clicked', str(caught.exception))

    def test_leaving_jobs_stops(self):
        agent = FakeAgent([('a1', click('Home'), 'https://www.linkedin.com/feed/'), ('DONE', None, None)])
        with self.assertRaises(linkedin.LinkedInError):
            self.drive(agent)

    def test_stale_retries_count_as_decisions_not_actions(self):
        alternating = [('a1', click('Căutați'), 'STALE'), ('a1', click('Locație'), 'STALE')]
        steps = alternating * runner.MAX_ACTIONS + [('DONE', None, RESULTS)]
        self.assertEqual(self.drive(FakeAgent(steps)), 0)
        agent = FakeAgent(alternating * runner.MAX_DECISIONS)
        with self.assertRaises(linkedin.LinkedInError):
            self.drive(agent)
        self.assertEqual(len(agent.state['decisions']), runner.MAX_DECISIONS)

    def test_a_target_that_stays_covered_gets_escape_then_a_stop(self):
        covered = ('a1', click('Filtru La distanță'), 'STALE')
        agent = FakeAgent([covered, covered, ('a1', click('Filtru La distanță'), RESULTS), ('DONE', None, RESULTS)])
        self.assertEqual(self.drive(agent), 1)
        self.assertEqual(agent.keys, [('keyDown', 'Escape'), ('keyUp', 'Escape')])
        self.assertIn('Escape (pressed by code)', self.log)
        agent = FakeAgent([covered] * runner.STALE_STOP + [('DONE', None, RESULTS)])
        with self.assertRaises(linkedin.LinkedInError) as caught:
            self.drive(agent)
        self.assertIn('kept covering', str(caught.exception))

    def test_waits_before_every_decision(self):
        waits = []
        agent = FakeAgent([('a1', click('Căutați'), RESULTS), ('DONE', None, RESULTS)])
        runner.drive(agent, Stale, time.monotonic() + 30, [], lambda: waits.append(len(agent.state['decisions'])))
        self.assertEqual(waits, [0, 1])

    def test_settle_returns_once_the_page_holds_still(self):
        class Page:
            reads = iter(['a', 'b', None, 'c'] + ['d'] * 50)
            def evaluate(self, expression):
                value = next(self.reads)
                if value is None:
                    raise Stale()
                return value
        started = time.monotonic()
        runner.settle(Page(), 'marker', time.monotonic() + 30, still=0.3, cap=5)
        self.assertLess(time.monotonic() - started, 3)
        started = time.monotonic()
        runner.settle(type('Busy', (), {'evaluate': lambda self, e: time.monotonic()})(), 'marker', time.monotonic() + 30, still=0.3, cap=0.6)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_blocked_overlong_and_late_runs_fail(self):
        with self.assertRaises(linkedin.LinkedInError):
            self.drive(FakeAgent([('BLOCKED', None, None)]))
        agent = FakeAgent([('a1', click('Căutați'), RESULTS)] * (runner.MAX_ACTIONS + 1))
        with self.assertRaises(linkedin.LinkedInError):
            self.drive(agent)
        self.assertEqual(len(agent.acted), runner.MAX_ACTIONS)
        with self.assertRaises(linkedin.LinkedInError):
            self.drive(FakeAgent([('DONE', None, None)]), time.monotonic() - 1)


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = s.Engine(s.AppliedStore(Path(self.folder.name) / 'applied.json'))
        self.engine.runs['x'] = {}

    def run_search(self, fetch, **options):
        o = s.validate_options({'adzuna': False, 'boards': ['remotive'], 'ai_pick': False, **options})
        with patch.object(linkedin, 'enabled', return_value=True), patch.object(linkedin, 'fetch', fetch), \
             patch.dict(s.remote.SOURCES, {'remotive': lambda *a: []}):
            self.engine.run('x', o)
        return self.engine.get('x')

    def test_linkedin_runs_last_and_its_roles_are_ranked(self):
        result = self.run_search(lambda o, job: (linkedin.to_jobs([item()], job), []))
        self.assertEqual([x['name'] for x in result['sources']], ['remotive', 'linkedin'])
        self.assertEqual([j['source'] for j in result['jobs']], ['linkedin'])

    def test_linkedin_errors_keep_their_message(self):
        def fail(o, job):
            raise linkedin.LinkedInError('No open Chrome profile is signed in to LinkedIn.')
        result = self.run_search(fail)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['sources'][1]['message'], 'No open Chrome profile is signed in to LinkedIn.')

    def test_switched_off_per_search(self):
        def never(o, job):
            raise AssertionError('LinkedIn should not run')
        result = self.run_search(never, linkedin=False)
        self.assertEqual([x['name'] for x in result['sources']], ['remotive'])

    def test_linkedin_alone_is_a_valid_source(self):
        with patch.object(linkedin, 'enabled', return_value=True):
            s.validate_options({'adzuna': False, 'boards': []})
        with patch.object(linkedin, 'enabled', return_value=False), self.assertRaises(ValueError):
            s.validate_options({'adzuna': False, 'boards': []})


if __name__ == '__main__':
    unittest.main()

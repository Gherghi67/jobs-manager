import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import service as s
import ai_pick as ai


def job(i, **kwargs):
    row = dict(id=f'id{i}', title=f'Backend Engineer {i}', company=f'Company {i}', location='Europe', type='contract',
               description='TypeScript backend role. ' * 200, sources=['remotive'])
    row.update(kwargs)
    return row


class FakeClaude:
    """Stands in for subprocess.run; answers with a structured result for every listing it is shown."""
    def __init__(self, fits=None, result=None):
        self.calls = []
        self.fits = fits or {}
        self.result = result
    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if self.result is not None:
            return subprocess.CompletedProcess(cmd, 1, stdout=json.dumps(self.result), stderr='')
        rows = []
        for key, title in zip(_ids(kwargs['input']), _titles(kwargs['input'])):
            fit = self.fits.get(title, 50)
            rows.append(dict(id=key, fit=fit, verdict='apply' if fit >= 70 else 'skip', romania='yes', reasons=['Stack match'], concerns=[]))
        out = dict(is_error=False, result='', structured_output=dict(jobs=rows))
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out), stderr='')


def _ids(prompt):
    return [line.split('"')[1] for line in prompt.splitlines() if line.startswith('<listing id=')]


def _titles(prompt):
    return [line[len('Title: '):] for line in prompt.splitlines() if line.startswith('Title: ')]


class PickTests(unittest.TestCase):
    def setUp(self):
        self.options = s.validate_options({})
        self.profile = patch.object(ai, 'profile_text', return_value='Senior Node.js engineer in Romania.')
        self.account = patch.object(ai.accounts, 'resolve', return_value=({}, 'account-1'))
        self.account.start()
        self.addCleanup(self.account.stop)
        self.profile.start()
        self.addCleanup(self.profile.stop)

    def test_ranks_shortlist_by_verdict_then_fit_and_keeps_the_rest(self):
        fake = FakeClaude({'Backend Engineer 1': 40, 'Backend Engineer 2': 90, 'Backend Engineer 3': 75})
        with patch.object(ai, 'LIMIT', 3):
            jobs, status = ai.pick([job(1), job(2), job(3), job(4)], self.options, {}, fake)
        self.assertEqual([j['id'] for j in jobs], ['id2', 'id3', 'id1', 'id4'])
        self.assertEqual(jobs[0]['ai'], dict(fit=90, verdict='apply', romania='yes', reasons=['Stack match'], concerns=[], engine='claude', subscription='personal'))
        self.assertNotIn('ai', jobs[3])
        self.assertEqual((status['status'], status['ranked'], status['shortlist'], status['fresh']), ('ok', 3, 3, 3))

    def test_cache_only_sends_new_listings(self):
        cache, fake = {}, FakeClaude()
        ai.pick([job(1), job(2)], self.options, cache, fake)
        jobs, status = ai.pick([job(1), job(2), job(3)], self.options, cache, fake)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(_titles(fake.calls[1][1]['input']), ['Backend Engineer 3'])
        self.assertEqual((status['ranked'], status['fresh']), (3, 1))
        ai.pick([job(1), job(2), job(3)], self.options, cache, fake)
        self.assertEqual(len(fake.calls), 2)

    def test_changed_preferences_rank_again(self):
        cache, fake = {}, FakeClaude()
        ai.pick([job(1)], self.options, cache, fake)
        self.options['contract_only'] = True
        ai.pick([job(1)], self.options, cache, fake)
        self.assertEqual(len(fake.calls), 2)

    def test_switching_subscription_or_identity_does_not_reuse_rankings(self):
        cache, fake = {}, FakeClaude()
        ai.pick([job(1)], self.options, cache, fake)
        self.options['ai_subscription'] = 'work'
        ai.pick([job(1)], self.options, cache, fake)
        with patch.object(ai.accounts, 'resolve', return_value=({}, 'different-account')):
            ai.pick([job(1)], self.options, cache, fake)
        self.assertEqual(len(fake.calls), 3)

    def test_codex_ranking_routes_to_selected_login_and_schema(self):
        calls = []
        def runner(cmd, **kwargs):
            calls.append((cmd, kwargs))
            self.assertEqual(cmd[:2], ['codex', 'exec'])
            self.assertIn('--ignore-user-config', cmd)
            self.assertIn('forced_login_method="chatgpt"', cmd)
            self.assertEqual(kwargs['env']['CODEX_HOME'], '/accounts/work')
            self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
            schema = json.loads(Path(cmd[cmd.index('--output-schema') + 1]).read_text())
            self.assertEqual(schema, ai.SCHEMA)
            Path(cmd[cmd.index('--output-last-message') + 1]).write_text(json.dumps({'jobs': [
                dict(id='j1', fit=80, verdict='apply', romania='yes', reasons=[], concerns=[])]}))
            return subprocess.CompletedProcess(cmd, 0, stdout='', stderr='')
        self.options.update(ai_engine='codex', ai_subscription='work')
        with patch.object(ai.accounts, 'resolve', return_value=({'CODEX_HOME': '/accounts/work'}, 'work-id')), \
                patch.dict(os.environ, {'OPENAI_API_KEY': 'do-not-use', 'CODEX_API_KEY': 'do-not-use'}):
            jobs, status = ai.pick([job(1)], self.options, {}, runner)
        self.assertEqual(jobs[0]['ai']['engine'], 'codex')
        self.assertEqual(status['subscription'], 'work')
        self.assertEqual(len(calls), 1)

    def test_codex_failures_are_readable_and_do_not_leak_output(self):
        for output, rc in [('not json', 0), ('[]', 0), ('secret-token', 1)]:
            def runner(cmd, **kwargs):
                Path(cmd[cmd.index('--output-last-message') + 1]).write_text(output)
                return subprocess.CompletedProcess(cmd, rc, stdout=output, stderr=output)
            with self.subTest(output=output), self.assertRaises(ai.AIError) as caught:
                ai.run_codex('prompt', {}, runner)
            self.assertNotIn('secret-token', str(caught.exception))

    def test_missing_account_never_falls_back_to_another_login(self):
        fake = FakeClaude()
        with patch.object(ai.accounts, 'resolve', side_effect=ai.accounts.AccountError('Work needs login')):
            with self.assertRaisesRegex(ai.AIError, 'Work needs login'):
                ai.pick([job(1)], self.options, {}, fake)
        self.assertEqual(fake.calls, [])

    def test_invalid_rows_are_ignored_or_clamped(self):
        def runner(cmd, **kwargs):
            rows = [dict(id='j1', fit=250, verdict='hire', romania='maybe', reasons=['a', 'b', 'c', 'd'], concerns=[]),
                    dict(id='j99', fit=10, verdict='skip', romania='no', reasons=[], concerns=[]), 'junk']
            out = dict(is_error=False, structured_output=dict(jobs=rows))
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(out), stderr='')
        jobs, status = ai.pick([job(1), job(2)], self.options, {}, runner)
        self.assertEqual(jobs[0]['ai'], dict(fit=100, verdict='maybe', romania='unclear', reasons=['a', 'b', 'c'], concerns=[], engine='claude', subscription='personal'))
        self.assertNotIn('ai', jobs[1])
        self.assertEqual(status['status'], 'partial')

    def test_claude_error_raises_readable_message(self):
        fake = FakeClaude(result=dict(is_error=True, result='Claude usage limit reached\nresets at 5pm'))
        with self.assertRaisesRegex(ai.AIError, 'usage limit reached resets at 5pm'):
            ai.pick([job(1)], self.options, {}, fake)

    def test_missing_cli_and_timeout_raise(self):
        def missing(*a, **k):
            raise FileNotFoundError('claude')
        def slow(cmd, **k):
            raise subprocess.TimeoutExpired(cmd, 300)
        for runner, message in ((missing, 'not installed'), (slow, 'longer than 5 minutes')):
            with self.subTest(message=message), self.assertRaisesRegex(ai.AIError, message):
                ai.pick([job(1)], self.options, {}, runner)

    def test_call_uses_subscription_without_tools_or_user_settings(self):
        fake = FakeClaude()
        env = {'ANTHROPIC_API_KEY': 'x', 'CLAUDECODE': '1', 'CLAUDE_CODE_SESSION_ID': 'x', 'CS_SESSION_NAME': 'x', 'HOME': '/home/me'}
        with patch.dict(os.environ, env, clear=True):
            ai.pick([job(1)], self.options, {}, fake)
        cmd, kwargs = fake.calls[0]
        self.assertEqual(kwargs['env'], {'HOME': '/home/me'})
        self.assertEqual(cmd[cmd.index('--tools') + 1], '')
        self.assertEqual(cmd[cmd.index('--setting-sources') + 1], 'project')
        self.assertIn('--strict-mcp-config', cmd)
        self.assertIn('--no-session-persistence', cmd)
        self.assertEqual(json.loads(cmd[cmd.index('--json-schema') + 1]), ai.SCHEMA)

    def test_prompt_has_profile_preferences_and_truncated_listings(self):
        fake = FakeClaude()
        self.options.update(keywords='Rust', contract_only=True)
        ai.pick([job(1, salary='€80/h')], self.options, {}, fake)
        prompt = fake.calls[0][1]['input']
        self.assertIn('Senior Node.js engineer in Romania.', prompt)
        self.assertIn('skills: Rust', prompt)
        self.assertIn('- Contract roles only.', prompt)
        self.assertIn('- Fully remote only, except hybrid roles based in Romania or Malta.', prompt)
        self.assertIn('- Hybrid roles based in Romania or Malta are wanted', prompt)
        self.assertIn('- Must be hireable from Romania, except hybrid roles based in Malta.', prompt)
        self.assertIn('Salary: €80/h', prompt)
        self.assertIn('[truncated]', prompt)
        self.assertLess(len(prompt), 3000)

    def test_without_hybrid_places_the_preferences_stay_remote_only(self):
        text = ai.preferences(dict(self.options, hybrid=[]))
        self.assertIn('- Fully remote only.', text)
        self.assertIn('- Must be hireable from Romania.', text)
        self.assertNotIn('ybrid', text)
        self.assertIn('- Must be hireable from Romania.', ai.preferences(dict(self.options, hybrid=['romania'])))


class EngineAiTests(unittest.TestCase):
    def run_engine(self, pick, **options):
        engine = s.Engine()
        o = s.validate_options({'adzuna': False, 'boards': ['remotive'], **options})
        engine.runs['x'] = {}
        listing = s.remote.job('remotive', '1', 'Senior TypeScript Backend Engineer', 'Studio', 'https://example.com/job',
                               location='Europe', type_field='Contractor', description='TypeScript Node.js backend')
        with patch.dict(s.remote.SOURCES, {'remotive': lambda *a: [listing]}), patch.object(s.ai, 'pick', pick):
            engine.run('x', o)
        return engine.get('x')

    def test_ranking_is_attached_to_the_run(self):
        def pick(jobs, o, cache, runner=None):
            jobs[0]['ai'] = dict(fit=88, verdict='apply', romania='yes', reasons=[], concerns=[])
            return jobs, dict(status='ok', ranked=1)
        result = self.run_engine(pick)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['jobs'][0]['ai']['fit'], 88)
        self.assertEqual(result['ai'], dict(status='ok', ranked=1))

    def test_claude_failure_keeps_keyword_results(self):
        def pick(jobs, o, cache, runner=None):
            raise ai.AIError('Claude Code: usage limit reached')
        result = self.run_engine(pick)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(len(result['jobs']), 1)
        self.assertNotIn('ai', result['jobs'][0])
        self.assertEqual(result['ai'], dict(status='error', engine='claude', subscription='personal', message='Claude Code: usage limit reached'))

    def test_unexpected_failure_is_not_leaked(self):
        def pick(jobs, o, cache, runner=None):
            raise KeyError('/Users/me/secret-path')
        result = self.run_engine(pick)
        self.assertEqual(result['status'], 'complete')
        self.assertNotIn('secret-path', json.dumps(result))

    def test_ai_pick_off_skips_claude(self):
        def pick(jobs, o, cache, runner=None):
            raise AssertionError('Claude should not be called')
        result = self.run_engine(pick, ai_pick=False)
        self.assertEqual(len(result['jobs']), 1)
        self.assertNotIn('ai', result)
        with self.assertRaises(ValueError):
            s.validate_options({'ai_pick': 'yes'})


if __name__ == '__main__':
    unittest.main()

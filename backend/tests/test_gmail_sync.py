import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gmail_sync as g
import service as s

NOW = g.epoch('2026-10-09T12:00:00+00:00')
CONFIG = {'mailbox': 'person@example.com', 'claude_account_email': 'person@example.com'}


def event(**kwargs):
    value = dict(application_id='', company='Example', title='Backend Engineer',
                 date='2026-10-08T12:00:00+00:00', kind='confirmation',
                 subject='Application received', **{'from': 'careers@example.com'},
                 message_id='msg-1', thread_id='thread-1')
    value.update(kwargs)
    return value


def output(events=None):
    return dict(mailbox=CONFIG['mailbox'], complete=True, events=events if events is not None else [event()])


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = s.AppliedStore(self.root / 'applied.json')
        self.config = self.root / 'config.json'
        g.private_json(self.config, CONFIG)
        self.state = self.root / 'state.json'
        self.fetcher = Mock(return_value=output())
        self.sync = g.GmailSync(self.store, self.config, self.state, self.fetcher, lambda: NOW)

    def test_daily_due_survives_restart(self):
        self.assertTrue(self.sync.run_due())
        self.assertFalse(self.sync.run_due())
        other = g.GmailSync(self.store, self.config, self.state, self.fetcher, lambda: NOW + g.DAY - 1)
        self.assertFalse(other.run_due())
        other.clock = lambda: NOW + g.DAY
        self.assertTrue(other.run_due())
        self.assertEqual(self.fetcher.call_count, 2)
        self.assertEqual(len(self.store.list()), 1)
        self.assertEqual(self.fetcher.call_args.args[1], NOW - 2 * g.DAY)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)

    def test_first_run_looks_back_thirty_days(self):
        self.sync.run_due()
        self.assertEqual(self.fetcher.call_args.args[1], NOW - 30 * g.DAY)

    def test_scheduled_first_run_waits_without_consuming_an_attempt(self):
        g.private_json(self.config, dict(CONFIG, start_after=g.stamp(NOW + 3600)))
        self.assertFalse(self.sync.run_due())
        self.assertFalse(self.state.exists())
        self.fetcher.assert_not_called()
        self.assertEqual(self.sync.status()['next_run'], g.stamp(NOW + 3600))
        self.sync.clock = lambda: NOW + 3600
        self.assertTrue(self.sync.run_due())

    def test_failure_is_visible_and_no_quota_retry_loop(self):
        self.fetcher.side_effect = g.SyncError('Connector expired')
        self.sync.run_due()
        self.assertEqual(self.sync.status()['error'], 'Connector expired')
        self.assertNotIn('last_success', self.sync.status())
        self.assertFalse(self.sync.run_due())
        self.assertEqual(self.store.list(), [])

    def test_refused_login_keeps_daily_slot_and_retries_soon(self):
        self.fetcher.side_effect = [g.LoginError('Sign in'), output()]
        self.assertTrue(self.sync.run_due())
        status = self.sync.status()
        self.assertEqual(status['error'], 'Sign in')
        self.assertNotIn('last_attempt', status)
        self.assertEqual(status['next_run'], g.stamp(NOW + g.LOGIN_RETRY))
        self.sync.clock = lambda: NOW + g.LOGIN_RETRY - 1
        self.assertFalse(self.sync.run_due())
        self.sync.clock = lambda: NOW + g.LOGIN_RETRY
        self.assertTrue(self.sync.run_due())
        status = self.sync.status()
        self.assertEqual((status['error'], status['last_success']), ('', g.stamp(NOW + g.LOGIN_RETRY)))
        self.assertNotIn('retry_at', status)
        self.assertEqual(self.fetcher.call_count, 2)
        self.assertEqual(len(self.store.list()), 1)

    def test_refused_login_after_success_keeps_previous_attempt(self):
        self.sync.run_due()
        self.sync.clock = lambda: NOW + g.DAY
        self.fetcher.side_effect = g.LoginError('Sign in')
        self.sync.run_due()
        status = self.sync.status()
        self.assertEqual((status['last_attempt'], status['last_success']), (g.stamp(NOW), g.stamp(NOW)))
        self.sync.clock = lambda: NOW + g.DAY + g.LOGIN_RETRY
        self.fetcher.side_effect = None
        self.assertTrue(self.sync.run_due())
        self.assertEqual(self.fetcher.call_args.args[1], NOW - 2 * g.DAY)
        self.assertFalse(self.sync.run_due())

    def test_failure_preserves_success_watermark(self):
        self.sync.run_due()
        self.sync.clock = lambda: NOW + 5 * g.DAY
        self.fetcher.side_effect = g.SyncError('Connector expired')
        self.sync.run_due()
        self.assertEqual(self.sync.status()['last_success'], g.stamp(NOW))

    def test_missing_and_disabled_config_do_not_fetch(self):
        self.config.unlink()
        self.assertFalse(self.sync.run_due())
        g.private_json(self.config, dict(CONFIG, enabled=False))
        self.assertFalse(self.sync.run_due())
        self.fetcher.assert_not_called()

    def test_corrupt_state_fails_closed(self):
        self.state.write_text('{')
        with self.assertRaises(g.SyncError):
            self.sync.run_due()
        self.fetcher.assert_not_called()
        self.assertIn('could not be read', self.sync.status()['error'])
        self.assertFalse(self.sync.running)

    def test_process_lock_prevents_overlap(self):
        import fcntl
        with open(str(self.state) + '.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertFalse(self.sync.run_due())
        self.fetcher.assert_not_called()

    def test_incomplete_wrong_mailbox_invalid_or_future_evidence(self):
        bad = [dict(output(), complete=False), dict(output(), mailbox='wrong@example.com'),
               output([event(message_id='')]), output([event(date='2026-10-10T00:00:00Z')]),
               output([event(date='2026-10-01T00:00:00')]), output([event(), event()])]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(g.SyncError):
                g.validate(value, CONFIG['mailbox'], NOW)

    def test_idempotent_import_keeps_manual_details_and_newer_status(self):
        existing = self.store.add_company(dict(company='Example', title='Backend Engineer', applied_at='2026-10-01T00:00:00+00:00'))
        self.store.update(existing['id'], dict(match='badge', notes='Keep this', follow_up='2026-10-15',
                                             status='interview', status_at='2026-10-09T00:00:00Z'))
        evidence = [event(application_id=existing['id'])]
        self.assertEqual(g.merge(self.store, evidence), 1)
        first = self.store.list()
        self.assertEqual(g.merge(self.store, evidence), 0)
        self.assertEqual(self.store.list(), first)
        self.assertEqual(first[0]['status'], 'interview')
        self.assertEqual(first[0]['match'], 'badge')
        self.assertEqual(first[0]['notes'], 'Keep this')
        self.assertEqual(first[0]['follow_up'], '2026-10-15')
        self.assertEqual(first[0]['emails'][0]['message_id'], 'msg-1')
        self.assertEqual(self.store.path.with_name('applied.json.before-gmail').stat().st_mode & 0o777, 0o600)

    def test_distinct_roles_at_company_stay_distinct(self):
        g.merge(self.store, [event(), event(title='Designer', message_id='msg-2', thread_id='thread-2')])
        self.assertEqual(len(self.store.list()), 2)
        g.merge(self.store, [event(title='Designer', kind='rejection', message_id='msg-3', thread_id='thread-2', date=g.stamp(NOW))])
        self.assertEqual({j['title']: j['status'] for j in self.store.list()},
                         {'Backend Engineer': 'applied', 'Designer': 'rejected'})

    def test_bad_late_event_cannot_partially_commit(self):
        self.store.add_company(dict(company='Old'))
        before = self.store.path.read_bytes()
        with self.assertRaises(g.SyncError):
            g.merge(self.store, [event(), event(application_id='missing', message_id='msg-2')])
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(len(self.store.list()), 1)

    def test_reply_without_application_fails_instead_of_inventing_date(self):
        with self.assertRaises(g.SyncError):
            g.merge(self.store, [event(kind='rejection')])
        self.assertEqual(self.store.list(), [])

    def test_failed_save_restores_memory(self):
        self.store.add_company(dict(company='Old'))
        before = self.store.path.read_bytes()
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                g.merge(self.store, [event()])
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(len(self.store.list()), 1)

    def test_legacy_email_enriched_instead_of_duplicated(self):
        row = self.store.add_company(dict(company='Example', title='Backend Engineer'))
        e = event()
        self.store.update(row['id'], {'emails': [{k: e[k] for k in ('date', 'kind', 'from', 'subject')}]})
        g.merge(self.store, [e])
        self.assertEqual(len(self.store.list()[0]['emails']), 1)
        self.assertEqual(self.store.list()[0]['emails'][0]['message_id'], 'msg-1')

    def test_no_email_still_records_success(self):
        self.fetcher.return_value = output([])
        self.sync.run_due()
        self.assertEqual(self.sync.status()['last_success'], g.stamp(NOW))
        self.assertEqual(self.store.list(), [])


class RunnerTests(unittest.TestCase):
    def test_account_and_read_only_configuration(self):
        runner = Mock(side_effect=[subprocess.CompletedProcess([], 0, json.dumps(dict(loggedIn=True, authMethod='claude.ai', email=CONFIG['claude_account_email']))),
                                   subprocess.CompletedProcess([], 0, json.dumps(dict(structured_output=output())))])
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'do-not-use', 'CLAUDE_CODE_OAUTH_TOKEN': 'inherited'}):
            g.fetch(CONFIG, NOW-g.DAY, NOW, [], runner)
        cmd = runner.call_args.args[0]
        self.assertEqual(cmd[cmd.index('--permission-mode') + 1], 'dontAsk')
        self.assertEqual(cmd[cmd.index('--tools') + 1], 'ToolSearch')
        self.assertNotIn('ANTHROPIC_API_KEY', runner.call_args.kwargs['env'])
        self.assertNotIn('CLAUDE_CODE_OAUTH_TOKEN', runner.call_args.kwargs['env'])
        self.assertIn('--no-session-persistence', cmd)
        self.assertIn('PreToolUse', json.loads(cmd[cmd.index('--settings') + 1])['hooks'])

    def test_wrong_or_api_login_never_starts_model(self):
        for code, login in [(0, json.dumps(dict(loggedIn=True, authMethod='api_key', email=CONFIG['mailbox']))),
                            (0, json.dumps(dict(loggedIn=True, authMethod='claude.ai', email='someone@example.com'))),
                            (1, json.dumps(dict(loggedIn=True, authMethod='claude.ai', email=CONFIG['mailbox']))),
                            (0, 'not json'), (0, '[]')]:
            runner = Mock(return_value=subprocess.CompletedProcess([], code, login))
            with self.assertRaises(g.LoginError):
                g.fetch(CONFIG, NOW-g.DAY, NOW, [], runner)
            self.assertEqual(runner.call_count, 1)

    def test_guard_denies_writes_and_other_connectors(self):
        for name, expected in [('Bash', 'deny'), ('mcp__claude_ai_Gmail__trash_thread', 'deny'),
                               ('mcp__claude_ai_Gmail__send_email', 'deny'), ('mcp__other__read', 'deny'),
                               (g.READ_TOOLS[0], 'allow'), (g.READ_TOOLS[1], 'allow')]:
            result = subprocess.run([sys.executable, str(g.ROOT / 'gmail_sync.py'), '--guard'],
                                    input=json.dumps({'tool_name': name}), capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['permissionDecision'], expected)


if __name__ == '__main__':
    unittest.main()

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gmail_sync as g
import service as s

NOW = g.epoch('2026-10-09T12:00:00+00:00')
CONFIG = {'mailbox': 'person@example.com'}


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
        self.sync = g.GmailSync(self.store, self.config, self.state, self.fetcher, lambda: NOW, password='app-password')

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

    def test_search_checks_outside_the_daily_schedule_at_most_every_fifteen_minutes(self):
        self.assertTrue(self.sync.run_due())
        self.sync.clock = lambda: NOW + g.SEARCH_FRESH - 1
        self.assertEqual(self.sync.run_for_search('codex', 'personal'), dict(status='ok', message='Gmail was checked in the last 15 minutes.'))
        self.assertEqual(self.fetcher.call_count, 1)
        self.sync.clock = lambda: NOW + g.SEARCH_FRESH
        self.fetcher.return_value = output([event(), event(message_id='msg-2', company='Other')])
        self.assertEqual(self.sync.run_for_search('codex', 'personal'),
                         dict(status='ok', imported=1, message='Checked Gmail with Codex · Personal: 1 new application email.'))
        self.assertEqual(self.fetcher.call_args.args[1], NOW - 2 * g.DAY)
        self.assertEqual(self.fetcher.call_args.kwargs, dict(engine='codex', subscription='personal', password='app-password'))
        # The search's sweep also counts as the daily one.
        self.sync.clock = lambda: NOW + g.DAY
        self.assertFalse(self.sync.run_due())
        self.assertEqual(sorted(j['company'] for j in self.store.list()), ['Example', 'Other'])

    def test_search_check_skips_the_login_retry_wait_and_reports_failures(self):
        self.fetcher.side_effect = [g.LoginError('Sign in'), g.SyncError('Connector expired'), output()]
        self.assertEqual(self.sync.run_for_search('claude', 'work'), dict(status='error', message='Gmail check failed: Sign in'))
        self.assertEqual(self.sync.run_for_search('claude', 'work'), dict(status='error', message='Gmail check failed: Connector expired'))
        # A failed sweep still counts as recent, so the next search reports it instead of spending quota again.
        self.assertEqual(self.sync.run_for_search('claude', 'work'), dict(status='error', message='Gmail check failed: Connector expired'))
        self.sync.clock = lambda: NOW + g.SEARCH_FRESH
        self.assertEqual(self.sync.run_for_search('claude', 'work')['message'], 'Checked Gmail with Claude · Work: 1 new application email.')
        self.assertEqual(self.fetcher.call_count, 3)

    def test_search_check_waits_for_a_running_sweep(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args, **kwargs):
            entered.set()
            release.wait(5)
            return output()
        self.fetcher.side_effect = slow
        daily = threading.Thread(target=self.sync.run_due)
        daily.start()
        self.assertTrue(entered.wait(5))
        box = {}
        search = threading.Thread(target=lambda: box.update(line=self.sync.run_for_search('claude', 'personal')))
        search.start()
        search.join(0.2)
        self.assertTrue(search.is_alive())
        release.set()
        daily.join(5)
        search.join(5)
        self.assertEqual(box['line']['message'], 'Gmail was checked in the last 15 minutes.')
        self.assertEqual(self.fetcher.call_count, 1)

    def test_search_check_is_off_without_a_config(self):
        self.config.unlink()
        self.assertIsNone(self.sync.run_for_search('claude', 'personal'))
        self.fetcher.assert_not_called()

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
        self.assertEqual(g.merge(self.store, evidence), (1, []))
        first = self.store.list()
        self.assertEqual(g.merge(self.store, evidence), (0, []))
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

    def test_an_email_pointing_at_an_unknown_application_waits_and_the_rest_imports(self):
        self.store.add_company(dict(company='Old'))
        added, left_out = g.merge(self.store, [event(), event(application_id='missing', message_id='msg-2')])
        self.assertEqual(added, 1)
        self.assertEqual([(e['message_id'], e['reason']) for e in left_out],
                         [('msg-2', 'points at an unknown application or one at another company')])
        self.assertEqual(sorted(j['company'] for j in self.store.list()), ['Example', 'Old'])

    def test_reply_without_application_waits_instead_of_inventing_a_date(self):
        self.store.add_company(dict(company='Old'))
        added, left_out = g.merge(self.store, [event(company='Earlier', message_id='earlier', thread_id='thread-0',
                                                     **{'from': 'jobs@earlier.io'}),
                                               event(kind='rejection', subject='Your Backend Engineer application')])
        self.assertEqual(added, 1)
        self.assertEqual([(e['company'], e['reason']) for e in left_out], [('Example', 'has no matching application')])
        self.assertEqual(sorted(j['company'] for j in self.store.list()), ['Earlier', 'Old'])
        self.assertEqual(g.left_out_note(left_out),
                         '1 reply waits for an application in your list: Example — Your Backend Engineer application. '
                         'Add the application and the next check attaches it.')

    def saved_under_board_name(self):
        """A role saved under the name its board listed (Xperteez Technology), whose confirmation came from the
        agency hiring for it (Micro1, through Dover)."""
        row = self.store.add(dict(id='xp1', title='Competitive Data Scientist | Remote - Contract',
                                  company='Xperteez Technology', url='https://example.com/xp1'))
        other = self.store.add(dict(id='xp2', title='Software Engineer – Backend | Remote - Contract',
                                    company='Xperteez Technology', url='https://example.com/xp2'))
        for entry, title, thread in ((row, 'Competitive Data Scientist', 't-cds'), (other, 'Software Engineer', 't-se')):
            self.store.update(entry['id'], {'emails': [dict(date='2026-10-01T10:00:00+00:00', kind='confirmation',
                                                            **{'from': 'no-reply@send.dover.com'}, thread_id=thread,
                                                            subject=f'Micro1 Application Update | {title} | Remote - Contract',
                                                            message_id=f'conf-{thread}')]})
        # Applied on 1 Oct, before the replies below.
        jobs = self.store.load()
        for entry in (row, other):
            jobs[entry['id']].update(applied_at='2026-10-01T10:00:00+00:00',
                                     history=[dict(status='applied', at='2026-10-01T10:00:00+00:00', source='app')])
        self.store.save()
        return row

    def test_a_reply_from_the_agency_reaches_the_role_saved_under_the_board_name(self):
        row = self.saved_under_board_name()
        reply = event(company='Micro1', title='Competitive Data Scientist', kind='rejection', message_id='m1',
                      thread_id='new-thread', subject='Micro1 Application Update - Competitive Data Scientist, Remote - Contract')
        self.assertEqual(g.merge(self.store, [reply]), (1, []))
        entry = next(j for j in self.store.list() if j['id'] == row['id'])
        self.assertEqual((entry['status'], entry['emails'][-1]['message_id']), ('rejected', 'm1'))
        # The same thread links a reply too, whatever company the sorter names.
        self.assertEqual(g.merge(self.store, [event(company='Dover', title='', kind='update', message_id='m2',
                                                    thread_id='t-se', subject='Next steps')]), (1, []))

    def test_a_confirmation_from_another_company_in_the_thread_is_a_new_application(self):
        self.saved_under_board_name()
        added, left_out = g.merge(self.store, [event(company='Micro1', title='Competitive Data Scientist',
                                                    message_id='c2', thread_id='t-cds')])
        self.assertEqual((added, left_out), (1, []))
        self.assertIn('Micro1', [j['company'] for j in self.store.list()])

    def test_a_reply_from_another_name_needs_the_same_role(self):
        self.saved_under_board_name()
        for title in ('Data Engineer', ''):
            with self.subTest(title=title):
                added, left_out = g.merge(self.store, [event(company='Micro1', title=title, kind='interview',
                                                            message_id='m-' + title, thread_id='new')])
                self.assertEqual((added, [e['reason'] for e in left_out]), (0, ['has no matching application']))
        # A sender no earlier email names isn't linked by the role alone.
        added, left_out = g.merge(self.store, [event(company='Acme', title='Competitive Data Scientist',
                                                    kind='interview', message_id='m-acme', thread_id='new')])
        self.assertEqual((added, len(left_out)), (0, 1))

    def test_left_out_replies_are_reported_and_attached_once_the_application_exists(self):
        reply = event(company='Mastra', title='Backend Engineer', kind='rejection', message_id='late', thread_id='t-late',
                      subject='Update on your application')
        self.fetcher.return_value = output([event(), reply])
        self.assertTrue(self.sync.run_due())
        status = self.sync.status()
        # The rest imports and the watermark moves on.
        self.assertEqual((status['error'], status['last_success'], status['imported']), ('', g.stamp(NOW), 1))
        self.assertEqual([(e['message_id'], e['reason']) for e in status['left_out']], [('late', 'has no matching application')])
        self.sync.clock = lambda: NOW + g.SEARCH_FRESH
        self.fetcher.return_value = output([])
        self.assertEqual(self.sync.run_for_search('claude', 'personal')['message'],
                         'Checked Gmail with Claude · Personal: no new application emails. 1 reply waits for an '
                         'application in your list: Mastra — Update on your application. Add the application and the '
                         'next check attaches it.')
        # A search soon after still names it.
        self.assertTrue(self.sync.run_for_search('claude', 'personal')['message'].startswith(
            'Gmail was checked in the last 15 minutes. 1 reply waits for an application in your list: Mastra'))
        # Once the application is in the list, a later sweep attaches the reply without reading it again.
        self.store.add_company(dict(company='Mastra', title='Backend Engineer', applied_at='2026-10-01T00:00:00+00:00'))
        self.sync.clock = lambda: NOW + 2 * g.SEARCH_FRESH
        self.sync.run_for_search('claude', 'personal')
        mastra = next(j for j in self.store.list() if j['company'] == 'Mastra')
        self.assertEqual((mastra['status'], mastra['emails'][-1]['message_id']), ('rejected', 'late'))
        self.assertEqual(self.sync.status()['left_out'], [])

    def test_left_out_replies_stop_being_retried_after_thirty_days(self):
        g.private_json(self.state, dict(last_success=g.stamp(NOW - g.DAY), last_attempt=g.stamp(NOW - g.DAY), left_out=[
            dict(event(kind='rejection', message_id='old', date=g.stamp(NOW - 31 * g.DAY)), reason='has no matching application'),
            dict(event(kind='rejection', message_id='young', date=g.stamp(NOW - 3 * g.DAY)), reason='has no matching application'),
            {'junk': True}]))
        self.fetcher.return_value = output([])
        self.assertTrue(self.sync.run_due())
        self.assertEqual([e['message_id'] for e in self.sync.status()['left_out']], ['young'])

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


def raw_email(sender, body, subtype='html'):
    return (f'From: {sender}\r\nTo: Person <person@example.com>\r\nSubject: Application received\r\n'
            f'Content-Type: text/{subtype}; charset=utf-8\r\n\r\n{body}').encode()


class FakeImap:
    """Gmail over IMAP: All Mail under its Romanian name, Spam, and two messages in All Mail."""
    MESSAGES = [(b'7 (X-GM-THRID 1879765650256270510 X-GM-MSGID 1879765731797013366 UID 7 INTERNALDATE " 2-Oct-2026 09:15:00 +0300" BODY[]<0> {1}',
                 raw_email('Careers <careers@example.com>', '<p>Thanks for applying to <b>Example</b> &amp; co.</p><style>p {}</style>')),
                b')',
                (b'9 (X-GM-THRID 2 X-GM-MSGID 3 UID 9 INTERNALDATE "03-Oct-2026 10:00:00 +0000" BODY[]<0> {1}',
                 raw_email('Person <Person@example.com>', 'Following up on my application.', 'plain')),
                b')']

    def __init__(self, password='app-password'):
        self.password, self.calls, self.folder = password, [], None

    def login(self, user, password):
        self.calls.append(('login', user))
        if password != self.password:
            raise g.imaplib.IMAP4.error('[AUTHENTICATIONFAILED] Invalid credentials')
        return 'OK', [b'']

    def list(self):
        return 'OK', [b'(\\HasNoChildren) "/" "INBOX"', b'(\\All \\HasNoChildren) "/" "[Gmail]/Toate mesajele"',
                      b'(\\HasNoChildren \\Junk) "/" "[Gmail]/Spam"']

    def select(self, name, readonly=False):
        self.calls.append(('select', name, readonly))
        self.folder = name
        return 'OK', [b'2']

    def uid(self, command, *args):
        self.calls.append((command, *args))
        if command == 'SEARCH':
            return 'OK', [b'7 9' if 'Toate' in self.folder else b'']
        return 'OK', self.MESSAGES

    def logout(self):
        self.calls.append(('logout',))


def message(key, **kwargs):
    value = dict(message_id=f'id-{key}', thread_id=f'thread-{key}', date='2026-10-08T12:00:00+00:00', folder='Inbox',
                 to='person@example.com', subject=f'Subject {key}', text='Thanks for applying.', **{'from': 'careers@example.com'})
    value.update(kwargs)
    return value


class ImapTests(unittest.TestCase):
    def test_reads_job_mail_read_only_from_all_mail_and_spam(self):
        imap = FakeImap()
        rows = g.read_mail(CONFIG['mailbox'], 'app-password', NOW - g.DAY, NOW, lambda: imap)
        self.assertEqual([c[1:] for c in imap.calls if c[0] == 'select'],
                         [('"[Gmail]/Toate mesajele"', True), ('"[Gmail]/Spam"', True)])
        search = next(c for c in imap.calls if c[0] == 'SEARCH')
        self.assertEqual(search[1], 'X-GM-RAW')
        self.assertTrue(search[2].startswith(f'"after:{int(NOW - g.DAY)} before:{int(NOW) + 1} (application OR '))
        self.assertIn('BODY.PEEK[]', next(c for c in imap.calls if c[0] == 'FETCH')[2])
        self.assertEqual(imap.calls[-1], ('logout',))
        # Gmail's web and API ids are the IMAP ids in hex.
        self.assertEqual(rows[0], dict(message_id='1a1644f940b69376', thread_id=format(1879765650256270510, 'x'),
                                       date='2026-10-02T06:15:00+00:00', folder='Inbox', to='Person <person@example.com>',
                                       subject='Application received', text='Thanks for applying to Example & co.',
                                       **{'from': 'Careers <careers@example.com>'}))
        self.assertEqual((rows[1]['folder'], rows[1]['text']), ('Sent', 'Following up on my application.'))

    def test_refused_password_and_missing_all_mail_fail_readably(self):
        with self.assertRaisesRegex(g.SyncError, 'refused the app password'):
            g.read_mail(CONFIG['mailbox'], 'wrong', NOW - g.DAY, NOW, lambda: FakeImap())
        imap = FakeImap()
        imap.list = lambda: ('OK', [b'(\\HasNoChildren) "/" "INBOX"'])
        with self.assertRaisesRegex(g.SyncError, 'no All Mail folder'):
            g.read_mail(CONFIG['mailbox'], 'app-password', NOW - g.DAY, NOW, lambda: imap)
        self.assertEqual(imap.calls[-1], ('logout',))


class SortTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(g.ai.accounts, 'resolve', side_effect=lambda engine, sub: (
            {'CLAUDE_CODE_OAUTH_TOKEN': 'token'} if engine == 'claude' else {'CODEX_HOME': '/codex'}, 'account'))
        self.resolve = patcher.start()
        self.addCleanup(patcher.stop)
        self.reader = Mock(return_value=[message(1), message(2, folder='Sent'), message(3)])
        self.rows = [dict(key='e1', kind='confirmation', company=' Example ', title='Backend Engineer', application_id=''),
                     dict(key='e3', kind='update', company='', title='', application_id='')]

    def claude(self, rows):
        out = dict(is_error=False, structured_output=dict(emails=rows))
        return Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(out), ''))

    def fetch(self, engine='claude', runner=None, **kwargs):
        return g.fetch(CONFIG, NOW - g.DAY, NOW, [dict(id='a1', company='Example', title='Backend Engineer', notes='x')],
                       engine=engine, subscription='personal', password='app-password', runner=runner, reader=self.reader, **kwargs)

    def test_claude_sorts_and_gmail_supplies_the_facts(self):
        runner = self.claude(self.rows)
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'do-not-use'}):
            output = self.fetch(runner=runner)
        self.assertEqual(output['mailbox'], CONFIG['mailbox'])
        self.assertTrue(output['complete'])
        # The empty-company row is dropped; ids, date, sender and subject come from Gmail, not the model.
        self.assertEqual(output['events'], [dict(application_id='', company='Example', title='Backend Engineer',
                                                 date='2026-10-08T12:00:00+00:00', kind='confirmation', subject='Subject 1',
                                                 message_id='id-1', thread_id='thread-1', **{'from': 'careers@example.com'})])
        self.assertEqual(g.validate(output, CONFIG['mailbox'], NOW), output['events'])
        cmd, kwargs = runner.call_args.args[0], runner.call_args.kwargs
        self.assertEqual(cmd[cmd.index('--system-prompt') + 1], g.SORT)
        self.assertEqual(json.loads(cmd[cmd.index('--json-schema') + 1]), g.SORT_SCHEMA)
        self.assertEqual(cmd[cmd.index('--tools') + 1], '')
        self.assertEqual(kwargs['env']['CLAUDE_CODE_OAUTH_TOKEN'], 'token')
        self.assertNotIn('ANTHROPIC_API_KEY', kwargs['env'])
        self.assertIn('<email key="e2">\nFolder: Sent', kwargs['input'])
        self.assertNotIn('notes', kwargs['input'])
        self.reader.assert_called_once_with(CONFIG['mailbox'], 'app-password', NOW - g.DAY, NOW)

    def test_codex_sorts_with_its_own_login(self):
        def runner(cmd, **kwargs):
            Path(cmd[cmd.index('--output-last-message') + 1]).write_text(json.dumps(dict(emails=self.rows[:1])))
            runner.kwargs = kwargs
            return subprocess.CompletedProcess(cmd, 0, '', '')
        output = self.fetch('codex', runner)
        self.assertEqual([e['message_id'] for e in output['events']], ['id-1'])
        self.assertEqual(runner.kwargs['env']['CODEX_HOME'], '/codex')
        self.assertTrue(runner.kwargs['input'].startswith(g.SORT))
        self.resolve.assert_called_with('codex', 'personal')

    def test_unknown_or_repeated_keys_fail_the_whole_batch(self):
        for rows in ([dict(self.rows[0], key='e9')], [self.rows[0], self.rows[0]], ['junk']):
            with self.subTest(rows=rows), self.assertRaises(g.SyncError):
                self.fetch(runner=self.claude(rows))

    def test_large_mailboxes_are_sorted_in_batches(self):
        self.reader.return_value = [message(i) for i in range(1, g.BATCH + 2)]
        runner = self.claude([])
        self.fetch(runner=runner)
        self.assertEqual(runner.call_count, 2)
        self.assertIn(f'<email key="e{g.BATCH + 1}">', runner.call_args.kwargs['input'])

    def test_missing_password_or_login_never_reads_mail_or_starts_a_model(self):
        runner = self.claude(self.rows)
        with self.assertRaisesRegex(g.LoginError, 'keychain as fieldwork-gmail'):
            g.fetch(CONFIG, NOW - g.DAY, NOW, [], password='', runner=runner, reader=self.reader)
        self.resolve.side_effect = g.ai.accounts.AccountError('Claude Work needs a saved login on the service computer.')
        with self.assertRaisesRegex(g.LoginError, 'Claude Work needs a saved login'):
            self.fetch(runner=runner)
        self.reader.assert_not_called()
        runner.assert_not_called()

    def test_model_failure_names_the_engine(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(dict(is_error=True, result="You've hit your limit")), ''))
        with self.assertRaisesRegex(g.SyncError, "Claude · Personal could not sort the emails. Claude Code: You've hit your limit"):
            self.fetch(runner=runner)


if __name__ == '__main__':
    unittest.main()

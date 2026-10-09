import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import claude_chat as cc
import service as s


def event(kind, **fields):
    return dict(type=kind, **fields)


def text_delta(text):
    return event('stream_event', event={'type': 'content_block_delta', 'delta': {'type': 'text_delta', 'text': text}})


def assistant(*blocks, parent=None):
    return event('assistant', message={'content': list(blocks)}, parent_tool_use_id=parent)


def result(text='Done.', error=False, session='session-1', **fields):
    return event('result', subtype='error_during_execution' if error else 'success', is_error=error, result=text,
                 session_id=session, duration_ms=1200, **fields)


class FakeProc:
    """Stands in for a `claude -p` process; prints [events], holding back the last one until released."""
    def __init__(self, events, hold=False, tail=''):
        self.lines = [json.dumps(e) + '\n' for e in events] + ([tail] if tail else [])
        self.release = threading.Event()
        if not hold:
            self.release.set()
        self.killed = False
        self.prompt = []
        self.pid = None
        self.returncode = None
        proc = self

        class Stdin:
            def write(self, text):
                proc.prompt.append(text)
            def close(self):
                pass
        self.stdin = Stdin()
        self.stdout = self.output()

    def output(self):
        for line in self.lines[:-1]:
            yield line
        self.release.wait(5)
        if not self.killed and self.lines:
            yield self.lines[-1]

    def wait(self):
        self.returncode = -15 if self.killed else 0
        return self.returncode

    def kill(self):
        self.killed = True
        self.release.set()


class FakePopen:
    def __init__(self):
        self.calls = []
        self.procs = []
    def queue(self, proc):
        self.procs.append(proc)
        return proc
    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        return self.procs.pop(0)


def finished(store, chat_id):
    for _ in range(200):
        chat = store.get(chat_id)
        if not chat['running']:
            return chat
        time.sleep(0.01)
    raise AssertionError('The turn did not finish.')


class ApplyTests(unittest.TestCase):
    def turn(self, *events):
        turn = dict(prompt='Hi', at='', status='running', items=[])
        sessions = [cc.apply(turn, e) for e in events]
        return turn, sessions

    def test_streamed_text_is_replaced_by_the_finished_block(self):
        turn, _ = self.turn(text_delta('Hel'), text_delta('lo'))
        self.assertEqual(turn['items'], [{'kind': 'text', 'text': 'Hello', 'live': True}])
        cc.apply(turn, assistant({'type': 'text', 'text': 'Hello there.'}))
        cc.apply(turn, text_delta('Second'))
        self.assertEqual(turn['items'], [{'kind': 'text', 'text': 'Hello there.', 'live': False},
                                         {'kind': 'text', 'text': 'Second', 'live': True}])

    def test_tools_are_summarised_and_subagent_messages_skipped(self):
        turn, _ = self.turn(
            assistant({'type': 'thinking', 'thinking': 'secret'},
                      {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'git   status', 'description': 'Show the working tree'}},
                      {'type': 'tool_use', 'name': 'Read', 'input': {'file_path': '/tmp/a.txt'}},
                      {'type': 'tool_use', 'name': 'TodoWrite', 'input': {'todos': []}}),
            assistant({'type': 'text', 'text': 'inside a subagent'}, parent='tool-1'),
            text_delta('also inside') | {'parent_tool_use_id': 'tool-1'})
        self.assertEqual(turn['items'], [{'kind': 'tool', 'name': 'Bash', 'text': 'Show the working tree'},
                                         {'kind': 'tool', 'name': 'Read', 'text': '/tmp/a.txt'},
                                         {'kind': 'tool', 'name': 'TodoWrite', 'text': ''}])

    def test_result_sets_status_session_denials_and_limits(self):
        turn, sessions = self.turn(
            event('system', subtype='init', session_id='abc', model='claude-opus-5-5'),
            event('rate_limit_event', rate_limit_info={'status': 'allowed'}),
            event('rate_limit_event', rate_limit_info={'status': 'allowed_warning', 'rateLimitType': 'five_hour',
                                                       'utilization': 0.93, 'resetsAt': 1791573600}),
            result('Only the final text.', session='abc', permission_denials=[
                {'tool_name': 'Bash', 'tool_input': {'command': 'rm -rf build'}}]))
        self.assertEqual(sessions, ['abc', None, None, 'abc'])
        self.assertEqual((turn['status'], turn['model'], turn['duration_ms']), ('done', 'claude-opus-5-5', 1200))
        self.assertEqual(turn['limit'], {'status': 'allowed_warning', 'kind': 'five_hour', 'used': 0.93, 'resets_at': 1791573600})
        # With no streamed text, the result's text is the answer.
        self.assertEqual(turn['items'], [{'kind': 'blocked', 'name': 'Bash', 'text': 'rm -rf build'},
                                         {'kind': 'text', 'text': 'Only the final text.'}])

    def test_error_result(self):
        turn, _ = self.turn(result('No conversation found with session ID: x', error=True))
        self.assertEqual((turn['status'], turn['error'], turn['items']), ('error', 'No conversation found with session ID: x', []))

    def test_long_text_is_clipped(self):
        turn, _ = self.turn(assistant({'type': 'text', 'text': 'x' * (cc.TEXT_CHARS + 50)}))
        self.assertEqual(len(turn['items'][0]['text']), cc.TEXT_CHARS)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name) / 'Documents'
        (self.root / 'jobs-manager').mkdir(parents=True)
        (self.root / '.hidden').mkdir()
        (self.root / 'notes.txt').write_text('')
        self.path = Path(self.folder.name) / 'chats.json'
        self.popen = FakePopen()
        self.store = cc.ChatStore(self.path, popen=self.popen)
        for p in (patch.dict(os.environ, {'JOBS_CLAUDE_ROOTS': str(self.root), 'ANTHROPIC_API_KEY': 'invalid'}),
                  patch.object(cc.ai, 'available', return_value=True)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.folder.cleanup()

    def project(self):
        return str((self.root / 'jobs-manager').resolve())

    def test_folders_are_the_roots_and_their_visible_subfolders(self):
        self.assertEqual(cc.folders(), [{'name': 'Documents', 'path': str(self.root.resolve())},
                                        {'name': 'jobs-manager', 'path': self.project()}])

    def test_a_chat_runs_claude_code_in_auto_mode_and_resumes_its_session(self):
        self.popen.queue(FakeProc([event('system', subtype='init', session_id='s1', model='opus'),
                                   text_delta('Hi'), assistant({'type': 'text', 'text': 'Hi!'}), result(session='s1')]))
        chat = self.store.create(self.project(), '  What changed today?\nIn this repo.')
        self.assertEqual((chat['title'], chat['folder'], chat['start'], len(chat['turns'])),
                         ('What changed today?', 'jobs-manager', 0, 1))
        done = finished(self.store, chat['id'])
        self.assertEqual(done['turns'][0]['status'], 'done')
        self.assertEqual(done['turns'][0]['items'], [{'kind': 'text', 'text': 'Hi!'}])
        cmd, kwargs = self.popen.calls[0]
        self.assertEqual(cmd[:2], ['claude', '-p'])
        self.assertIn('--permission-mode', cmd)
        self.assertEqual(cmd[cmd.index('--permission-mode') + 1], 'auto')
        self.assertEqual(cmd[cmd.index('--permission-prompts') + 1], 'none')
        self.assertNotIn('--resume', cmd)
        self.assertNotIn('bypassPermissions', cmd)
        self.assertNotIn('--dangerously-skip-permissions', cmd)
        self.assertEqual((kwargs['cwd'], kwargs['start_new_session']), (self.project(), True))
        # The subscription login, never the shell's API key; the prompt goes on stdin, not the command line.
        self.assertNotIn('ANTHROPIC_API_KEY', kwargs['env'])
        self.assertNotIn('What changed', ' '.join(cmd))

        self.popen.queue(FakeProc([result('Second answer', session='s1')]))
        second = self.store.send(chat['id'], 'And now?')
        self.assertEqual((second['start'], [t['prompt'] for t in second['turns']]), (1, ['And now?']))
        finished(self.store, chat['id'])
        cmd = self.popen.calls[1][0]
        self.assertEqual(cmd[cmd.index('--resume') + 1], 's1')
        self.assertEqual(self.store.get(chat['id'], 1)['turns'][0]['items'], [{'kind': 'text', 'text': 'Second answer'}])
        self.assertEqual(oct(self.path.stat().st_mode & 0o777), '0o600')
        self.assertEqual([c['id'] for c in self.store.list()], [chat['id']])

    def test_one_turn_at_a_time_and_stop_ends_it(self):
        proc = self.popen.queue(FakeProc([text_delta('Working'), result()], hold=True))
        chat = self.store.create(self.project(), 'Long task')
        with self.assertRaises(RuntimeError):
            self.store.send(chat['id'], 'Another')
        for _ in range(100):
            if self.store.get(chat['id'])['turns'][0]['items']:
                break
            time.sleep(0.01)
        self.assertTrue(self.store.list()[0]['running'])
        with patch.object(cc.os, 'killpg', side_effect=lambda pid, sig: proc.kill()) as killpg:
            self.store.stop(chat['id'])
        killpg.assert_called_once()
        turn = finished(self.store, chat['id'])['turns'][0]
        self.assertEqual((turn['status'], turn['items']), ('stopped', [{'kind': 'text', 'text': 'Working'}]))

    def test_running_turns_become_interrupted_after_a_restart(self):
        proc = self.popen.queue(FakeProc([text_delta('Half'), result()], hold=True))
        chat = self.store.create(self.project(), 'Task')
        reloaded = cc.ChatStore(self.path, popen=self.popen).get(chat['id'])
        self.assertEqual((reloaded['running'], reloaded['turns'][0]['status']), (False, 'interrupted'))
        with patch.object(cc.os, 'killpg', side_effect=lambda pid, sig: proc.kill()):
            self.assertTrue(self.store.remove(chat['id']))
        self.assertEqual(cc.ChatStore(self.path).list(), [])

    def test_a_process_without_a_result_reports_its_output(self):
        self.popen.queue(FakeProc([], tail='Error: not logged in\n'))
        chat = self.store.create(self.project(), 'Hello')
        turn = finished(self.store, chat['id'])['turns'][0]
        self.assertEqual((turn['status'], turn['error']), ('error', 'Error: not logged in'))

    def test_invalid_requests(self):
        for cwd, text in [('/etc', 'Hi'), (self.project(), ''), (self.project(), '   '), (self.project(), 'x' * (cc.PROMPT_CHARS + 1)),
                          (self.project(), None)]:
            with self.subTest(cwd=cwd, text=str(text)[:10]), self.assertRaises(ValueError):
                self.store.create(cwd, text)
        self.assertIsNone(self.store.send('missing', 'Hi'))
        self.assertIsNone(self.store.stop('missing'))
        self.assertFalse(self.store.remove('missing'))
        with patch.object(cc.ai, 'available', return_value=False), self.assertRaises(cc.ChatError):
            self.store.create(self.project(), 'Hi')
        self.assertEqual(self.store.list(), [])

    def test_unreadable_file_is_reported(self):
        self.path.write_text('{not json')
        with self.assertRaises(cc.ChatError):
            self.store.list()


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

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        (Path(self.folder.name) / 'project').mkdir()
        self.popen = FakePopen()
        chats = s.Handler.chats
        s.Handler.chats = cc.ChatStore(Path(self.folder.name) / 'chats.json', popen=self.popen)
        self.addCleanup(setattr, s.Handler, 'chats', chats)
        for p in (patch.dict(os.environ, {'JOBS_CLAUDE_ROOTS': self.folder.name}),
                  patch.object(cc.ai, 'available', return_value=True)):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.folder.cleanup()

    def call(self, method, path, body=None, token=True):
        headers = {'Authorization': 'Bearer ' + self.token} if token else {}
        data = json.dumps(body).encode() if body is not None else None
        with urlopen(Request(self.url + path, data=data, headers=headers, method=method)) as r:
            return r.status, json.load(r)

    def error(self, method, path, body=None, token=True):
        with self.assertRaises(HTTPError) as e:
            self.call(method, path, body, token)
        with e.exception:
            return e.exception.code, json.load(e.exception)

    def test_chat_endpoints(self):
        status, body = self.call('GET', '/claude/folders')
        project = str((Path(self.folder.name) / 'project').resolve())
        self.assertEqual((status, body['default'], [f['name'] for f in body['folders']]),
                         (200, str(Path(self.folder.name).resolve()), [Path(self.folder.name).name, 'project']))
        proc = self.popen.queue(FakeProc([text_delta('On it'), result('All done.')], hold=True))
        status, body = self.call('POST', '/claude/chats', {'cwd': project, 'text': 'Run the tests'})
        chat = body['chat']
        self.assertEqual((status, chat['title'], chat['running'], chat['turns'][0]['status']), (202, 'Run the tests', True, 'running'))
        self.assertEqual(self.error('POST', f'/claude/chats/{chat["id"]}/messages', {'text': 'More'})[0], 409)
        proc.release.set()
        finished(s.Handler.chats, chat['id'])
        status, body = self.call('GET', f'/claude/chats/{chat["id"]}?from=0')
        # Text streamed without a finished block stays as streamed.
        self.assertEqual(body['chat']['turns'][0]['items'], [{'kind': 'text', 'text': 'On it'}])
        self.popen.queue(FakeProc([result('Second.')]))
        self.assertEqual(self.call('POST', f'/claude/chats/{chat["id"]}/messages', {'text': 'Again'})[0], 202)
        finished(s.Handler.chats, chat['id'])
        status, body = self.call('GET', f'/claude/chats/{chat["id"]}?from=1')
        self.assertEqual((body['chat']['start'], body['chat']['turn_count'], len(body['chat']['turns'])), (1, 2, 1))
        self.assertEqual(self.call('POST', f'/claude/chats/{chat["id"]}/stop', {})[1]['chat']['running'], False)
        self.assertEqual([c['id'] for c in self.call('GET', '/claude/chats')[1]['chats']], [chat['id']])
        self.assertEqual(self.call('DELETE', f'/claude/chats/{chat["id"]}')[1], {'removed': True})
        self.assertEqual(self.call('GET', '/claude/chats')[1], {'chats': []})

    def test_errors_and_switch(self):
        self.assertEqual(self.error('GET', '/claude/chats', token=False)[0], 401)
        self.assertEqual(self.error('POST', '/claude/chats', {'cwd': '/', 'text': 'Hi'}),
                         (400, {'error': 'Choose one of the folders the service offers.'}))
        self.assertEqual(self.error('POST', '/claude/chats', ['not', 'an', 'object'])[0], 400)
        self.assertEqual(self.error('GET', '/claude/chats/missing')[0], 404)
        self.assertEqual(self.error('POST', '/claude/chats/missing/messages', {'text': 'Hi'})[0], 404)
        self.assertEqual(self.error('GET', '/claude/unknown')[0], 404)
        with patch.dict(os.environ, {'JOBS_CLAUDE_CHAT': 'off'}):
            self.assertEqual(self.error('GET', '/claude/chats')[0], 403)
            self.assertFalse(self.call('GET', '/health')[1]['claude_chat'])
        self.assertEqual(self.popen.calls, [])


if __name__ == '__main__':
    unittest.main()

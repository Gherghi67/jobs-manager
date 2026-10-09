import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ranking_accounts as accounts
import ai_pick
import service


class AccountTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.home = Path(folder.name).resolve()
        home = patch.object(Path, 'home', return_value=self.home)
        home.start()
        self.addCleanup(home.stop)
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def write(self, path, value):
        target = self.home / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))

    def codex(self, folder='.codex', plan='plus', mode='chatgpt'):
        payload = base64.urlsafe_b64encode(json.dumps({'https://api.openai.com/auth': {
            'chatgpt_plan_type': plan}}).encode()).decode().rstrip('=')
        self.write(folder + '/auth.json', {'auth_mode': mode, 'tokens': {
            'id_token': 'header.' + payload + '.sig', 'access_token': 'test-secret', 'account_id': folder}})

    def test_codex_default_login_only_matches_its_plan(self):
        self.codex()
        env, identity = accounts.resolve('codex', 'personal')
        self.assertEqual(env, {'CODEX_HOME': str(self.home / '.codex')})
        self.assertEqual(identity, '.codex')
        with self.assertRaises(accounts.AccountError):
            accounts.resolve('codex', 'work')
        self.codex(plan='business')
        accounts.resolve('codex', 'work')
        with self.assertRaises(accounts.AccountError):
            accounts.resolve('codex', 'personal')

    def test_codex_explicit_home_and_api_key_rejection(self):
        self.codex('work', plan='business')
        with patch.dict(os.environ, {'JOBS_CODEX_WORK_HOME': str(self.home / 'work')}):
            env, _ = accounts.resolve('codex', 'work')
            self.assertEqual(env['CODEX_HOME'], str(self.home / 'work'))
            self.codex('work', mode='apikey')
            with self.assertRaises(accounts.AccountError):
                accounts.resolve('codex', 'work')

    def test_claude_accounts_are_read_without_switching_or_refreshing(self):
        self.write('.config/agents-sidebar/accounts.json', {'accounts': [
            {'id': 'one', 'alias': 'Personal', 'accountUuid': 'personal-id'},
            {'id': 'two', 'alias': 'ERPK', 'accountUuid': 'work-id'}]})
        self.write('.claude.json', {'oauthAccount': {'accountUuid': 'work-id'}})
        def secret(service, account):
            token = account if service == 'agents-sidebar-accounts' else 'live'
            return {'claudeAiOauth': {'accessToken': token, 'expiresAt':
                    (time.time() + (7200 if token == 'live' else 3600)) * 1000}}
        with patch.object(accounts, 'secret', side_effect=secret):
            personal, p_id = accounts.resolve('claude', 'personal')
            work, w_id = accounts.resolve('claude', 'work')
        self.assertEqual(personal, {'CLAUDE_CODE_OAUTH_TOKEN': 'one'})
        self.assertEqual(work, {'CLAUDE_CODE_OAUTH_TOKEN': 'two'})
        self.assertNotEqual(p_id, w_id)
        self.assertEqual(accounts.read_json(self.home / '.claude.json')['oauthAccount']['accountUuid'], 'work-id')

    def test_expired_claude_login_and_catalog_never_leak_secrets(self):
        self.write('.config/agents-sidebar/accounts.json', {'accounts': [
            {'id': 'one', 'alias': 'Personal', 'accountUuid': 'personal-id'}]})
        blob = {'claudeAiOauth': {'accessToken': 'secret-value', 'expiresAt': 1}}
        with patch.object(accounts, 'secret', return_value=blob), patch.object(accounts.shutil, 'which', return_value='/bin/cli'):
            with self.assertRaisesRegex(accounts.AccountError, 'expired'):
                accounts.resolve('claude', 'personal')
            catalog = accounts.catalog()
        self.assertEqual(len(catalog), 4)
        self.assertFalse(any(r['available'] for r in catalog))
        self.assertNotIn('secret-value', json.dumps(catalog))

    def test_ranking_env_overrides_inherited_account_and_api_billing(self):
        with patch.dict(os.environ, {'HOME': '/home/me', 'CLAUDE_CODE_OAUTH_TOKEN': 'wrong',
                                    'ANTHROPIC_API_KEY': 'wrong', 'ANTHROPIC_BASE_URL': 'wrong',
                                    'CLAUDE_CODE_USE_BEDROCK': '1', 'CODEX_API_KEY': 'wrong',
                                    'OPENAI_API_KEY': 'wrong', 'CODEX_HOME': '/wrong'}):
            self.assertEqual(ai_pick.ranking_env({'CLAUDE_CODE_OAUTH_TOKEN': 'selected'}),
                             {'HOME': '/home/me', 'CLAUDE_CODE_OAUTH_TOKEN': 'selected'})

    def test_invalid_selections_rejected(self):
        for key, bad in [('ai_engine', 'shell'), ('ai_engine', {}), ('ai_subscription', '../work'), ('ai_subscription', None)]:
            with self.subTest(key=key, value=bad), self.assertRaises(ValueError):
                service.validate_options({key: bad})


if __name__ == '__main__':
    unittest.main()

"""Resolve ranking subscriptions without switching the desktop's active login.

Claude uses a saved Agents sidebar login, or an explicitly configured token file.
Codex uses a separate CLI home per subscription (the matching default login also works).
Only public availability messages cross the service boundary.
"""
from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

ENGINES = ('claude', 'codex')
SUBSCRIPTIONS = ('personal', 'work')


class AccountError(Exception):
    pass


def validate(engine, subscription):
    if engine not in ENGINES:
        raise ValueError('Choose Claude or Codex for ranking.')
    if subscription not in SUBSCRIPTIONS:
        raise ValueError('Choose Personal or Work for ranking.')


def read_json(path):
    try:
        value = json.loads(Path(path).read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def secret(service, account):
    try:
        result = subprocess.run(['security', 'find-generic-password', '-s', service, '-a', account, '-w'],
                                capture_output=True, text=True, timeout=5)
        return json.loads(result.stdout) if result.returncode == 0 else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {}


def claude_login(subscription):
    token_file = os.environ.get(f'JOBS_CLAUDE_{subscription.upper()}_TOKEN_FILE')
    if token_file:
        try:
            token = Path(token_file).expanduser().read_text().strip()
        except OSError:
            token = ''
        if token:
            return token, hashlib.sha256(token.encode()).hexdigest()
        raise AccountError(f'Claude {subscription.title()} token file could not be read.')
    store = read_json(Path.home() / '.config/agents-sidebar/accounts.json')
    alias = os.environ.get(f'JOBS_CLAUDE_{subscription.upper()}_ACCOUNT', subscription).casefold()
    # ERPK is the existing local Work nickname; explicit mappings take precedence.
    aliases = {alias} | ({'erpk'} if subscription == 'work' and alias == 'work' else set())
    stored = store.get('accounts', [])
    rows = [r for r in (stored if isinstance(stored, list) else []) if isinstance(r, dict) and
            isinstance(r.get('id'), str) and isinstance(r.get('accountUuid'), str) and
            (str(r.get('alias', '')).casefold() in aliases or str(r.get('id', '')).casefold() == alias)]
    if len(rows) != 1:
        raise AccountError(f'Claude {subscription.title()} needs a saved login on the service computer.')
    row = rows[0]
    # Read only the account-specific item. The shared live item can change during a desktop switch.
    blobs = [secret('agents-sidebar-accounts', row['id'])]
    valid = [b.get('claudeAiOauth', {}) for b in blobs if isinstance(b, dict)]
    valid = [v for v in valid if isinstance(v, dict) and isinstance(v.get('accessToken'), str)
             and isinstance(v.get('expiresAt'), (float, int)) and v['expiresAt'] > (time.time() + 60) * 1000]
    if not valid:
        raise AccountError(f'Claude {subscription.title()} login expired or is unavailable. Sign in again on the service computer.')
    oauth = max(valid, key=lambda v: v['expiresAt'])
    return oauth['accessToken'], str(row['accountUuid'])


def codex_login(subscription):
    configured = os.environ.get(f'JOBS_CODEX_{subscription.upper()}_HOME')
    home = Path(configured).expanduser() if configured else Path.home() / '.codex'
    auth = read_json(home / 'auth.json')
    tokens = auth.get('tokens') if isinstance(auth.get('tokens'), dict) else {}
    try:
        part = tokens.get('id_token', '').split('.')[1]
        claims = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
        plan = claims.get('https://api.openai.com/auth', {}).get('chatgpt_plan_type', '')
    except (ValueError, IndexError, AttributeError, TypeError):
        plan = ''
    actual = ('work' if plan in ('team', 'business', 'enterprise', 'edu') else
              'personal' if plan in ('free', 'plus', 'pro', 'prolite', 'go') else None)
    if (auth.get('auth_mode') != 'chatgpt' or not tokens.get('access_token') or
            not tokens.get('account_id') or (not configured and actual != subscription)):
        raise AccountError(f'Codex {subscription.title()} needs its own ChatGPT login configured on the service computer.')
    return str(home.resolve()), str(tokens['account_id'])


def resolve(engine, subscription):
    validate(engine, subscription)
    if engine == 'claude':
        token, identity = claude_login(subscription)
        return {'CLAUDE_CODE_OAUTH_TOKEN': token}, identity
    home, identity = codex_login(subscription)
    return {'CODEX_HOME': home}, identity


def catalog():
    rows = []
    for engine in ENGINES:
        for subscription in SUBSCRIPTIONS:
            try:
                if not shutil.which(engine):
                    raise AccountError(f'{engine.title()} is not installed on the service computer.')
                resolve(engine, subscription)
                message, ready = 'Login available. Usage limits are checked when ranking runs.', True
            except AccountError as exc:
                message, ready = str(exc), False
            rows.append(dict(engine=engine, subscription=subscription, available=ready, message=message))
    return rows

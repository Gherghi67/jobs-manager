"""What the job sites searched by the jev-ultrafast browser agent (LinkedIn, Glassdoor) share.

The service never imports jev-ultrafast: each site's runner (`linkedin_jev.py`, `glassdoor_jev.py`) runs in
jev's own virtualenv and reads jev's own .env, so this process keeps no TypeSafe key. The helpers here are
shared with those runners and must stay standard-library only and Python 3.12 compatible.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata

JEV_DIR = Path(os.environ.get('JOBS_JEV_DIR') or Path.home() / 'Documents' / 'jev-ultrafast')
# The runner stops itself and closes its tab first; this is only the backstop.
TIMEOUT = 240
LIMIT = 25
LOCATION = os.environ.get('JOBS_LINKEDIN_LOCATION') or 'Romania'
QUERIES = {'backend': 'Node.js backend', 'broad': 'backend engineer', 'gaming': 'game backend engineer'}
# Parent variables the agent never needs. It loads its own keys from jev-ultrafast/.env.
SECRET_NAME = re.compile(r'KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ADZUNA', re.I)


class AgentError(Exception):
    """A message that is safe to show in the app."""


def python():
    return JEV_DIR / '.venv' / 'bin' / 'python'


def enabled(switch):
    return os.environ.get(switch, 'on') != 'off' and python().is_file()


def plain(text):
    text = unicodedata.normalize('NFKD', str(text or ''))
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).lower().split())


def words(text):
    return set(re.findall(r'[a-z0-9.+#]+', plain(text)))


def child_env():
    env = {k: v for k, v in os.environ.items() if not SECRET_NAME.search(k)}
    for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
        env.pop(name, None)
    return env


def posted_date(epoch_ms):
    if type(epoch_ms) is not int or epoch_ms <= 0:
        return ''
    try:
        return dt.datetime.fromtimestamp(epoch_ms / 1000, dt.timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError):
        return ''


def tokens(usage, *names):
    for name in names:
        value = usage.get(name)
        if type(value) is int and value >= 0:
            return value
    return 0


def usage_of(state):
    """What one agent run used. Every decision is one TypeSafe request, stale ones included, and TypeSafe
    reports tokens, not dollars. The text helper is billed in dollars only through an API (OpenRouter's
    `cost`); through Codex it uses the subscription."""
    decisions = [d.get('usage') or {} for d in state.get('decisions', []) if isinstance(d, dict)]
    texts = [t for t in state.get('text_calls', []) if isinstance(t, dict)]
    text_usage = [t.get('usage') if isinstance(t.get('usage'), dict) else {} for t in texts]
    costs = [u['cost'] for u in text_usage if type(u.get('cost')) in (int, float) and u['cost'] >= 0]
    return dict(requests=len(decisions),
                input_tokens=sum(tokens(u, 'input_tokens') for u in decisions),
                output_tokens=sum(tokens(u, 'output_tokens') for u in decisions),
                text_calls=len(texts), text_model=str(texts[0].get('model') or '')[:80] if texts else '',
                text_tokens=sum(tokens(u, 'input_tokens', 'prompt_tokens') + tokens(u, 'output_tokens', 'completion_tokens')
                                for u in text_usage),
                text_cost=round(sum(costs), 8) if costs else None)


def run(name, runner, error, req, goal, record=None, launch=None):
    """Runs a site's runner with the request and the agent's goal. Returns (job items, warnings) or raises error.
    record receives the run's usage, tagged with the site, also when the run failed after the agent started.
    launch replaces subprocess.run; the service passes one that a cancelled search interrupts."""
    try:
        done = (launch or subprocess.run)([str(python()), '-I', str(runner)], input=json.dumps(dict(req, goal=goal)),
                                          capture_output=True, text=True, timeout=TIMEOUT, cwd=JEV_DIR, env=child_env())
    except subprocess.TimeoutExpired:
        raise error(f'The {name} browser agent did not finish in time.') from None
    try:
        result = json.loads(done.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise error(f'The {name} browser agent stopped without a result.') from None
    if record and isinstance(result, dict) and isinstance(result.get('usage'), dict):
        record(dict(result['usage'], source=name.lower()))
    if not isinstance(result, dict) or result.get('status') != 'ok':
        message = result.get('message') if isinstance(result, dict) else None
        raise error(str(message or f'The {name} browser agent failed.')[:300])
    warnings = result.get('warnings')
    return result.get('jobs'), [str(w)[:200] for w in warnings if w][:5] if isinstance(warnings, list) else []

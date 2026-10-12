"""LinkedIn Jobs through the jev-ultrafast browser agent.

The service never imports jev-ultrafast: `linkedin_jev.py` runs in jev's own virtualenv and reads
jev's own .env, so this process keeps no TypeSafe key. The helpers here are shared with that runner
and must stay standard-library only and Python 3.12 compatible.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import unicodedata
from urllib.parse import parse_qs, urlparse

JEV_DIR = Path(os.environ.get('JOBS_JEV_DIR') or Path.home() / 'Documents' / 'jev-ultrafast')
RUNNER = Path(__file__).resolve().with_name('linkedin_jev.py')
# The runner stops itself and closes its tab first; this is only the backstop.
TIMEOUT = 240
LIMIT = 25
LOCATION = os.environ.get('JOBS_LINKEDIN_LOCATION') or 'Romania'
QUERIES = {'backend': 'Node.js backend', 'broad': 'backend engineer', 'gaming': 'game backend engineer'}
# Parent variables the agent never needs. It loads its own keys from jev-ultrafast/.env.
SECRET_NAME = re.compile(r'KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|ADZUNA', re.I)
# Controls that change the account or reach other people, in LinkedIn's English and Romanian labels.
# Checked on the accent-free, lower-case label before any click or typing executes.
REFUSED = re.compile(
    r'\b(?:apply|applied|save|saved|dismiss\b.*\bjob|hide|share|repost|message|messaging|compose|connect|'
    r'follow|unfollow|send|report|block|alert|sign out|premium|for business|preferences?|settings|open to work|'
    r'candidat\w*|aplica\w*|salva\w*|ignorati jobul|distribui\w*|mesaj\w*|compune\w*|conecta\w*|urmari\w*|'
    r'trimite\w*|raport\w*|bloca\w*|alert\w*|deconecta\w*|pentru business|preferint\w*|setari\w*)\b')
# A filter menu's confirm button: "Apply current filter to show N results".
FILTER_CONFIRM = re.compile(r'^(?:apply current filters? to show|aplicati filtrul curent)\b')
WORKPLACE = {1: 'On-site', 2: 'Remote', 3: 'Hybrid'}


class LinkedInError(Exception):
    """A message that is safe to show in the app."""


def python():
    return JEV_DIR / '.venv' / 'bin' / 'python'


def enabled():
    return os.environ.get('JOBS_LINKEDIN', 'on') != 'off' and python().is_file()


def plain(text):
    text = unicodedata.normalize('NFKD', str(text or ''))
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).lower().split())


def request(o):
    terms = [t.strip() for t in o['keywords'].split(',') if t.strip()]
    query = (terms[0] if len(terms) == 1 else '(' + ' OR '.join(terms[:3]) + ')') if terms else QUERIES[o['preset']]
    # A keyword, not LinkedIn's Remote filter: the agent lost its way in the filter menus. Workplace type and
    # posting date come from each job's details, and rank() applies remote_only and max_age_days to them.
    if o['remote_only']:
        query += ' remote'
    return dict(query=query, location=LOCATION, limit=LIMIT)


def goal(req):
    return (f'Search LinkedIn Jobs for "{req["query"]}" in {req["location"]}: make sure the keyword field holds exactly '
            f'that text and the location field holds {req["location"]}, then run the search. Stop as soon as the matching '
            'job results are listed. Do not use filters or change job preferences. Do not open, apply to, save, dismiss '
            'or share a job, do not create a job alert, and do not message, follow or connect with anyone.')


def refused(action):
    """Why the agent must not execute this observed action, or None."""
    if action.get('kind') in ('scroll', 'wait'):
        return None
    if action.get('role') == 'switch':
        return 'a switch (LinkedIn uses them for job alerts)'
    label = plain(action.get('label'))
    if FILTER_CONFIRM.match(label):
        return None
    return f'"{action.get("label", "")[:80]}"' if REFUSED.search(label) else None


def on_jobs(url):
    u = urlparse(url or '')
    return u.scheme == 'https' and u.hostname == 'www.linkedin.com' and u.path.startswith('/jobs')


def check_results(url, req, fields=()):
    """Independent check of the page the agent called DONE on, from its URL and the values of its text fields.
    Returns warnings; raises when it's not the requested search."""
    u = urlparse(url or '')
    params = parse_qs(u.query)
    words = lambda text: set(re.findall(r'[a-z0-9.+#]+', plain(text)))
    if not on_jobs(url) or not u.path.startswith('/jobs/search') or not words(req['query']) <= words(' '.join(params.get('keywords', []))):
        raise LinkedInError('The LinkedIn search ended on a page that does not show the requested search.')
    if 'location' in params and plain(req['location']) not in plain(' '.join(params['location'])):
        raise LinkedInError(f'The LinkedIn search ended on results outside {req["location"]}.')
    # LinkedIn keeps a profile's default location in the field without adding it to the URL.
    if 'location' not in params and not any(plain(req['location']) in plain(value) for value in fields):
        return [f'LinkedIn did not show the searched location; roles outside {req["location"]} are dropped by eligibility.']
    return []


def child_env():
    env = {k: v for k, v in os.environ.items() if not SECRET_NAME.search(k)}
    for name in ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV'):
        env.pop(name, None)
    return env


def to_jobs(items, job):
    """Validated runner output as normalized jobs, built with remote_search.job."""
    rows = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not re.fullmatch(r'\d{5,20}', str(item.get('id', ''))):
            continue
        text = {k: str(item.get(k) or '')[:limit] for k, limit in
                (('title', 300), ('company', 200), ('location', 200), ('employment', 60), ('description', 20000))}
        if not text['title'] or not text['company']:
            continue
        workplace = WORKPLACE.get(item.get('workplace'))
        location = f'{text["location"]} ({workplace})' if workplace else text['location']
        rows.append(job('linkedin', item['id'], text['title'], text['company'], f'https://www.linkedin.com/jobs/view/{item["id"]}/',
                        location=location, type_field=text['employment'], posted=posted_date(item.get('listed_at')),
                        description=text['description']))
    return rows


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


def fetch(o, job, record=None):
    """Returns (jobs, warnings) like the other collectors, or raises LinkedInError.
    record receives the run's usage, also when the run failed after the agent started."""
    if not enabled():
        raise LinkedInError(f'LinkedIn needs jev-ultrafast installed at {JEV_DIR}.')
    req = request(o)
    try:
        done = subprocess.run([str(python()), '-I', str(RUNNER)], input=json.dumps(dict(req, goal=goal(req))),
                              capture_output=True, text=True, timeout=TIMEOUT, cwd=JEV_DIR, env=child_env())
    except subprocess.TimeoutExpired:
        raise LinkedInError('The LinkedIn browser agent did not finish in time.') from None
    try:
        result = json.loads(done.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise LinkedInError('The LinkedIn browser agent stopped without a result.') from None
    if record and isinstance(result, dict) and isinstance(result.get('usage'), dict):
        record(result['usage'])
    if not isinstance(result, dict) or result.get('status') != 'ok':
        message = result.get('message') if isinstance(result, dict) else None
        raise LinkedInError(str(message or 'The LinkedIn browser agent failed.')[:300])
    warnings = result.get('warnings')
    warnings = [str(w)[:200] for w in warnings if w][:5] if isinstance(warnings, list) else []
    return to_jobs(result.get('jobs'), job), warnings

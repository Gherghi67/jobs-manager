"""LinkedIn Jobs through the jev-ultrafast browser agent; `jev.py` has what it shares with Glassdoor.

The runner, `linkedin_jev.py`, imports this module in jev's virtualenv, so it must stay standard-library
only and Python 3.12 compatible.
"""
from __future__ import annotations
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

import jev
from jev import JEV_DIR, LIMIT, LOCATION, QUERIES, plain, posted_date, usage_of  # noqa: F401 - used by tests

NAME = 'LinkedIn'
START = 'https://www.linkedin.com/jobs/search/'
RUNNER = Path(__file__).resolve().with_name('linkedin_jev.py')
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


class LinkedInError(jev.AgentError):
    pass


Error = LinkedInError


def enabled():
    return jev.enabled('JOBS_LINKEDIN')


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
    if not on_jobs(url) or not u.path.startswith('/jobs/search') or not jev.words(req['query']) <= jev.words(' '.join(params.get('keywords', []))):
        raise LinkedInError('The LinkedIn search ended on a page that does not show the requested search.')
    if 'location' in params and plain(req['location']) not in plain(' '.join(params['location'])):
        raise LinkedInError(f'The LinkedIn search ended on results outside {req["location"]}.')
    # LinkedIn keeps a profile's default location in the field without adding it to the URL.
    if 'location' not in params and not any(plain(req['location']) in plain(value) for value in fields):
        return [f'LinkedIn did not show the searched location; roles outside {req["location"]} are dropped by eligibility.']
    return []


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


def fetch(o, job, record=None, runner=None):
    """Returns (jobs, warnings) like the other collectors, or raises LinkedInError.
    record receives the run's usage, also when the run failed after the agent started. runner replaces subprocess.run."""
    if not enabled():
        raise LinkedInError(f'LinkedIn needs jev-ultrafast installed at {JEV_DIR}.')
    req = request(o)
    items, warnings = jev.run(NAME, RUNNER, LinkedInError, req, goal(req), record, runner)
    return to_jobs(items, job), warnings

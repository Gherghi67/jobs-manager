"""Glassdoor Jobs through the jev-ultrafast browser agent, the way linkedin.py does LinkedIn.

Glassdoor has no public API. The agent types the search in the same Chrome profile as LinkedIn's, and
`glassdoor_jev.py` reads each listed job's schema.org JobPosting from its Glassdoor page. That runner
imports this module in jev's virtualenv, so it must stay standard-library only and Python 3.12 compatible.
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse

import jev
from jev import JEV_DIR, LIMIT, LOCATION, QUERIES, plain

NAME = 'Glassdoor'
START = 'https://www.glassdoor.com/Job/index.htm'
# The jev.PLACES searched for hybrid roles. Glassdoor lists no jobs in Malta: on 7 Nov 2026 its Malta page
# (IN166) showed none, even for "software engineer", so that run would only cost time and agent tokens.
HYBRID_PLACES = ('romania',)
RUNNER = Path(__file__).resolve().with_name('glassdoor_jev.py')
# Controls that change the account, reach other people or post content, checked on the accent-free,
# lower-case label before any click or typing executes. Glassdoor's "give to get" wall asks for a
# review or a salary, "Let employers find and reach out to you" is a switch on the job page, and
# Glassdoor Recruiter lets recruiters find the profile.
REFUSED = re.compile(
    r'\b(?:apply|applied|easy apply|save|saved|hide|not interested|share|message|messages|follow|unfollow|'
    r'send|report|block|alert|alerts|sign out|log out|preferences?|settings|profile|resume|cv|upload|'
    r'tailor|insights|reach out|recruit\w*|review|reviews|salary|salaries|interview|interviews|contribute|'
    r'post|notifications?|premium|employers?)\b')
WORKPLACE_REMOTE = 'TELECOMMUTE'
EMPLOYMENT = {'FULL_TIME': 'Full-time', 'PART_TIME': 'Part-time', 'CONTRACTOR': 'Contract', 'TEMPORARY': 'Temporary',
              'INTERN': 'Internship', 'PER_DIEM': 'Per diem', 'VOLUNTEER': 'Volunteer'}
# A Glassdoor search page: /Job/<location>-<keywords>-jobs-SRCH_IL.<location span>_IN<id>_KO<keyword span>.htm
# The keywords keep their case and punctuation, as in romania-Node.js-backend-remote-jobs-SRCH_….
SEARCH = re.compile(r'^/Job/(?P<slug>[A-Za-z0-9.+#-]+)-jobs-SRCH_(?P<spans>[A-Z0-9_.,]+)\.htm$')
LISTING = re.compile(r'^/job-listing/[A-Za-z0-9_.,%-]+\.htm$')


class GlassdoorError(jev.AgentError):
    pass


Error = GlassdoorError


def enabled():
    return jev.enabled('JOBS_GLASSDOOR')


def request(o, place=None):
    """The search for remote roles in LOCATION or, with a place from jev.PLACES, for hybrid roles there."""
    terms = [t.strip() for t in o['keywords'].split(',') if t.strip()]
    # Glassdoor's job title field takes one phrase, not LinkedIn's OR syntax.
    query = terms[0] if terms else QUERIES[o['preset']]
    # A keyword, not Glassdoor's Remote filter, as for LinkedIn: each job's JobPosting says whether it is
    # remote and where applicants may live, and rank() applies remote_only and eligibility to that.
    if place:
        # JobPosting has no hybrid type, so rank() keeps the roles whose text says hybrid and whose location is there.
        return dict(query=query + ' hybrid', location=jev.PLACES[place], limit=LIMIT)
    if o['remote_only']:
        query += ' remote'
    return dict(query=query, location=LOCATION, limit=LIMIT)


def goal(req):
    return (f'Search Glassdoor Jobs for "{req["query"]}" in {req["location"]}: make sure the job title field holds exactly '
            f'that text and the location field holds {req["location"]}, picking {req["location"]} from the location '
            'suggestions if they appear, then run the search. Stop as soon as the matching job results are listed. Do not '
            'use filters or change job preferences. Do not open, apply to, save, hide or share a job, do not create a job '
            'alert, do not write a review or add a salary, and do not change the profile or let employers contact me.')


def refused(action):
    """Why the agent must not execute this observed action, or None."""
    if action.get('kind') in ('scroll', 'wait'):
        return None
    if action.get('role') in ('switch', 'checkbox'):
        return 'a switch (Glassdoor uses them for alerts and for letting employers contact you)'
    label = plain(action.get('label'))
    return f'"{action.get("label", "")[:80]}"' if REFUSED.search(label) else None


def on_jobs(url):
    u = urlparse(url or '')
    return u.scheme == 'https' and u.hostname == 'www.glassdoor.com' and u.path.startswith('/Job/')


def spans(slug, codes):
    """The location and keyword parts of a search page's slug, from the IL.a,b and KOa,b spans."""
    found = {}
    for name, key in (('location', r'IL\.'), ('keywords', 'KO')):
        m = re.search(key + r'(\d+),(\d+)', codes)
        if m and int(m.group(1)) <= int(m.group(2)) <= len(slug):
            found[name] = slug[int(m.group(1)):int(m.group(2))].replace('-', ' ')
    return found


def searched(url, req):
    """Whether url is the results page of the requested search, so the agent can stop there."""
    try:
        return not check_results(url, req)
    except GlassdoorError:
        return False


def check_results(url, req, fields=()):
    """Independent check of the page the agent called DONE on, from its URL and the values of its text fields.
    Returns warnings; raises when it's not the requested search."""
    u = urlparse(url or '')
    m = SEARCH.match(u.path)
    parts = spans(m.group('slug'), m.group('spans')) if m else {}
    keywords = ' '.join([parts.get('keywords', '')] + parse_qs(u.query).get('sc.keyword', []))
    if not on_jobs(url) or not m or not jev.words(req['query']) <= jev.words(keywords):
        raise GlassdoorError('The Glassdoor search ended on a page that does not show the requested search.')
    if 'location' in parts and plain(req['location']) not in plain(parts['location']):
        raise GlassdoorError(f'The Glassdoor search ended on results outside {req["location"]}.')
    if 'location' not in parts and not any(plain(req['location']) in plain(value) for value in fields):
        return [f'Glassdoor did not show the searched location; roles outside {req["location"]} are dropped by eligibility.']
    return []


def posted_date(value):
    try:
        return dt.date.fromisoformat(str(value or '')[:10]).isoformat()
    except ValueError:
        return ''


def strings(value, limit=200):
    """Names from a JSON-LD value that may be one object, a list of them, or text."""
    values = value if isinstance(value, list) else [value]
    names = [v.get('name') if isinstance(v, dict) else v for v in values]
    return [str(n).strip()[:limit] for n in names if isinstance(n, (str, int)) and str(n).strip()][:60]


def to_jobs(items, job):
    """Validated runner output as normalized jobs, built with remote_search.job."""
    rows = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or not re.fullmatch(r'\d{5,20}', str(item.get('id', ''))):
            continue
        text = {k: str(item.get(k) or '').strip()[:limit] for k, limit in
                (('title', 300), ('company', 200), ('location', 200), ('salary', 120), ('description', 20000))}
        if not text['title'] or not text['company']:
            continue
        u = urlparse(str(item.get('url') or ''))
        if u.scheme != 'https' or u.hostname != 'www.glassdoor.com' or not LISTING.match(u.path):
            continue
        countries = strings(item.get('countries'))
        remote = item.get('workplace') == WORKPLACE_REMOTE
        # Where applicants may live is an explicit country list, like Himalayas' restrictions.
        restrictions = countries if remote and countries else None
        place = ', '.join(countries) if restrictions else text['location']
        location = f'{place} (Remote)' if remote and 'remote' not in plain(place) else place
        employment = ', '.join(EMPLOYMENT.get(e, e.replace('_', ' ').title()) for e in strings(item.get('employment'), 40))
        rows.append(job('glassdoor', item['id'], text['title'], text['company'], f'https://www.glassdoor.com{u.path}?jl={item["id"]}',
                        location=location, restrictions=restrictions, type_field=employment, salary=text['salary'],
                        posted=posted_date(item.get('posted')), description=text['description']))
    return rows


def fetch(o, job, record=None, runner=None, place=None):
    """Returns (jobs, warnings) like the other collectors, or raises GlassdoorError. place searches hybrid roles there.
    record receives the run's usage, also when the run failed after the agent started. runner replaces subprocess.run."""
    if not enabled():
        raise GlassdoorError(f'Glassdoor needs jev-ultrafast installed at {JEV_DIR}.')
    req = request(o, place)
    items, warnings = jev.run(NAME, RUNNER, GlassdoorError, req, goal(req), record, runner)
    return to_jobs(items, job), warnings

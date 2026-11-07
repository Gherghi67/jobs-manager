"""Personal job-search API; collectors are vendored from cv-refactor."""
from __future__ import annotations
import argparse
import contextlib
import copy
import datetime as dt
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT.parent / 'artifacts'
WEB_DIR = ROOT.parent / 'build' / 'web'
CV_DIR = Path(os.environ.get('JOBS_CV_DIR') or ROOT.parent / 'cv')
APPLIED_FILE = Path(os.environ.get('JOBS_APPLIED_FILE') or ROOT / 'applied.json')
JEV_USAGE_FILE = Path(os.environ.get('JOBS_JEV_USAGE_FILE') or ROOT / 'jev-usage.json')
SEARCH_FILE = Path(os.environ.get('JOBS_SEARCH_FILE') or ROOT / 'search.json')
# US dollars per million Jev input tokens; output is free. TypeSafe's docs publish no price and its responses
# carry tokens only, so this is the rate third-party listings gave in October 2026. JOBS_JEV_PRICE overrides it.
JEV_PRICE = 0.042
sys.path.insert(0, str(ROOT / 'vendor'))
import adzuna_search as az
import remote_search as remote
import ai_pick as ai
import claude_chat
import glassdoor
import gmail_sync
import jev
import linkedin
import tailor

PUBLIC_SOURCES = ['remotive', 'remoteok', 'himalayas', 'jobicy', 'workingnomads', 'arbeitnow', 'hackernews']
# Removed boards that options saved by older app builds may still list.
RETIRED_BOARDS = ('weworkremotely',)
# The markets the app offers. All eight with the broad preset's 4 queries make 32 calls at 2.5 s apart.
ADZUNA_MARKETS = ('us', 'gb', 'de', 'nl', 'pl', 'at', 'es', 'fr')
# Countries whose hybrid roles a search adds to the remote ones (the `hybrid` option), with the words that place a
# role's location there, matched on the accent-free, lower-case location. LinkedIn writes Il-Gżira as "il-gzira".
HYBRID_PLACES = {
    'romania': re.compile(r'\b(?:romania|bucharest|bucuresti|ilfov|pipera|cluj|iasi|timisoara|brasov|constanta|sibiu'
                          r'|oradea|craiova)\b'),
    'malta': re.compile(r"\b(?:malta|valletta|sliema|gzira|msida|birkirkara|swieqi|mosta|naxxar|qormi|luqa|mriehel"
                        r"|san gwann|san giljan|ta['’]? ?xbiex|(?:st\.?|saint) julian['’]?s|(?:st\.?|santa) venera)\b"),
}
DEFAULTS = dict(preset='broad', adzuna=True, linkedin=True, glassdoor=True, boards=PUBLIC_SOURCES, countries=['de', 'nl', 'gb'],
                keywords='', remote_only=True, eligibility='romania', hybrid=list(HYBRID_PLACES), contract_only=False,
                prefer_contract=True, max_age_days=30, ai_pick=True, ai_engine='claude', ai_subscription='personal',
                dismissed=[])
# The app sends its most recent dismissals, ~27 bytes each in JSON.
MAX_DISMISSED = 2000


def config(name):
    return json.loads((ROOT / 'config' / name).read_text())


def validate_options(value):
    if not isinstance(value, dict):
        raise ValueError('Options must be an object.')
    if set(value) - set(DEFAULTS):
        raise ValueError('Unknown search option.')
    o = copy.deepcopy(DEFAULTS)
    o.update(value)
    ai.accounts.validate(o['ai_engine'], o['ai_subscription'])
    if o['preset'] not in ('backend', 'broad', 'gaming'):
        raise ValueError('Unknown preset.')
    for key in ('adzuna', 'linkedin', 'glassdoor', 'remote_only', 'contract_only', 'prefer_contract', 'ai_pick'):
        if type(o[key]) is not bool:
            raise ValueError(f'{key} must be true or false.')
    if isinstance(o['boards'], list):
        o['boards'] = [x for x in o['boards'] if x not in RETIRED_BOARDS]
    if not isinstance(o['boards'], list) or any(x not in PUBLIC_SOURCES for x in o['boards']):
        raise ValueError('Unknown remote board.')
    countries = o['countries']
    # Each market costs one Adzuna call per query, so a market may be listed only once.
    if (not isinstance(countries, list) or not countries or any(x not in ADZUNA_MARKETS for x in countries)
            or len(set(countries)) != len(countries)):
        raise ValueError('Choose supported Adzuna countries, each once.')
    agents = (o['linkedin'] and linkedin.enabled()) or (o['glassdoor'] and glassdoor.enabled())
    if not o['adzuna'] and not agents and not o['boards']:
        raise ValueError('Enable at least one source.')
    if o['eligibility'] not in ('romania', 'romania_unclear', 'all'):
        raise ValueError('Unknown eligibility option.')
    if not isinstance(o['hybrid'], list) or any(not isinstance(x, str) or x not in HYBRID_PLACES for x in o['hybrid']):
        raise ValueError('Hybrid roles can be added only for Romania and Malta.')
    if type(o['max_age_days']) is not int or not 1 <= o['max_age_days'] <= 90:
        raise ValueError('Age must be 1–90 days.')
    if not isinstance(o['keywords'], str) or len(o['keywords']) > 200:
        raise ValueError('Keywords must be at most 200 characters.')
    if (not isinstance(o['dismissed'], list) or len(o['dismissed']) > MAX_DISMISSED
            or any(not isinstance(x, str) or not 0 < len(x) <= 64 for x in o['dismissed'])):
        raise ValueError(f'Dismissed roles must be at most {MAX_DISMISSED} listing ids.')
    o['boards'] = list(dict.fromkeys(o['boards']))
    o['countries'] = list(dict.fromkeys(o['countries']))
    o['hybrid'] = list(dict.fromkeys(o['hybrid']))
    return o


def search_config(o):
    c = config({'backend': 'remote_config.json', 'broad': 'broad_remote_config.json', 'gaming': 'gaming_config.json'}[o['preset']])
    c['max_age_days'] = o['max_age_days']
    terms = [s.strip() for s in o['keywords'].split(',') if s.strip()]
    if terms:
        c['scoring']['core_terms'] = terms
        c['scoring']['penalty_title_terms'] = []
    return c


def eligibility(item, locator):
    """Country lists win; timezone compatibility alone never proves eligibility."""
    if item.get('restrictions') is not None:
        return locator.label(item)
    text = item['location'].lower()
    description = item.get('description', '').lower()
    # Explicit restrictions in the body override a broad board location label.
    if re.search(r'(?:must (?:be |reside |live )|only |based (?:in )|residen(?:t|ce) (?:of|in) ).{0,20}(?:united states|u\.s\.|usa)|(?:us|usa|united states)[ -]only', description):
        return 'us'
    if re.search(r'\b(?:romania|worldwide|anywhere|all countries|europe|european union|emea|eu)\b', text):
        if re.search(r'\b(?:except|excluding|not including)\s+romania\b', text + ' ' + description):
            return 'other'
        return 'worldwide' if re.search(r'worldwide|anywhere|all countries', text) else 'europe'
    if re.search(r'\b(?:us|usa|united states|canada|americas)\b', text):
        return 'us'
    if re.search(r'\b(?:germany|berlin|france|paris|netherlands|spain|poland|austria|united kingdom|uk|london|india|brazil|australia)\b', text):
        return 'other'
    if not text or re.search(r'\b(?:remote|cet|cest|eet|est|pst|timezone|time zone)\b', text):
        return 'unclear'
    return 'other'


# The workplace type a site appended to the location: LinkedIn's (Remote), (Hybrid) or (On-site), Glassdoor's (Remote).
WORKPLACE_TAG = re.compile(r'\((remote|hybrid|on-site)\)\s*$')
HYBRID = r'(?:hybrid|hibrid)'
# In a title or location, "hybrid" means the workplace unless it names a technology.
HYBRID_WORD = re.compile(rf'\b{HYBRID}\b(?!\s+(?:cloud|apps?|mobile|infrastructure|it|integration))')
# Descriptions say "hybrid cloud" too, so there it must describe how the job is worked, in English or Romanian.
HYBRID_WORK = re.compile(
    rf'\b{HYBRID}\s+(?:work\w*|model|role|position|job|schedule|set-?up|arrangement|office|mode|policy|format|regime'
    rf'|basis|lucru|munca)\b'
    rf'|\b{HYBRID}\b\W{{0,3}}(?:\w+\W+){{0,4}}?(?:\d|one|two|three|four)\s*(?:days?|x)\b'
    rf'|\b(?:location|workplace|work model|work mode|working model|work arrangement|work setup|work type|regim'
    rf'|program|mod de lucru|lucru)\s*[:\-–]?\s*(?:is\s+)?(?:fully\s+)?{HYBRID}\b'
    rf'|\b(?:is|are)\s+{HYBRID}\b(?!\s+(?:cloud|apps?|mobile|infrastructure))'
    rf'|\b(?:remote|on-?site|office)\s*[/|]\s*{HYBRID}\b|\b{HYBRID}\s*[/|]\s*(?:remote|on-?site|office)\b')


def hybrid_place(item, places):
    """The place, of those the search asked for, where item is a hybrid role, or None. A workplace type the site
    appended to the location decides; otherwise the title or location says hybrid or the description describes
    hybrid work. Only the location places the role: a description may name offices the role isn't at."""
    if not places:
        return None
    location = jev.plain(item.get('location'))
    tag = WORKPLACE_TAG.search(location)
    if tag:
        hybrid = tag.group(1) == 'hybrid'
    else:
        hybrid = bool(HYBRID_WORD.search(jev.plain(item.get('title')) + ' | ' + location)
                      or HYBRID_WORK.search(jev.plain(item.get('description'))))
    return next((p for p in places if HYBRID_PLACES[p].search(location)), None) if hybrid else None


def rank(raw, o):
    c = search_config(o)
    scorer = az.Scorer(c['scoring'])
    locator = remote.LocationLabeler(c.get('location', {}))
    remote_labeler = az.RemoteLabeler(config('config.json')['remote'])
    industry = remote.IndustryFilter(c['industry']) if c.get('industry') else None
    oldest = (dt.date.today() - dt.timedelta(days=o['max_age_days'])).isoformat()
    kept = {}
    for original in raw:
        item = copy.deepcopy(original)
        if not item.get('title') or not item.get('url', '').startswith(('https://', 'http://')):
            continue
        if scorer.excluded_by(item['title']) or (item.get('posted') and item['posted'] < oldest and not item.get('board')):
            continue
        if industry and not industry.allows(item):
            continue
        score, matched = scorer.score(item['title'], item['description'] + ' ' + ' '.join(item['tags']))
        if score < c.get('min_score', 1) or not matched['core']:
            continue
        place = hybrid_place(item, o['hybrid'])
        if place:
            # Wanted beside the remote roles: remote_only and eligibility are about where a remote role may be worked.
            item.update(remote='hybrid', eligibility='hybrid-' + place)
        else:
            label = remote_labeler.label(item['title'], item['description'], item['location'])
            # Remote-focused feeds imply remote, but never override explicit hybrid text.
            if label == 'unknown' and item['source'] in PUBLIC_SOURCES and item['source'] not in ('hackernews', 'arbeitnow'):
                label = 'yes'
            if o['remote_only'] and label != 'yes':
                continue
            item['remote'] = label
            item['eligibility'] = eligibility(item, locator)
            allowed = ('worldwide', 'europe') if o['eligibility'] == 'romania' else ('worldwide', 'europe', 'unclear')
            if o['eligibility'] != 'all' and item['eligibility'] not in allowed:
                continue
        item['type'] = remote.employment(item)
        if o['contract_only'] and item['type'] != 'contract':
            continue
        item.update(score=score, matched=matched, sources=[item['source']], company_key=company_key(item['company']))
        # Keep distinct location variants: country-restricted copies are not equivalent.
        identity = remote.dedupe_key(item) + '|' + item['location'].lower()
        item['id'] = hashlib.sha256(identity.encode()).hexdigest()[:24]
        if identity in kept:
            existing = kept[identity]
            if item['source'] not in existing['sources']:
                existing['sources'].append(item['source'])
            continue
        kept[identity] = item
    rows = list(kept.values())
    rows.sort(key=lambda j: j.get('posted', ''), reverse=True)
    rows.sort(key=lambda j: ((0 if j['eligibility'] in ('worldwide', 'europe') or j['eligibility'].startswith('hybrid-') else 1),
                            remote.TYPE_ORDER[j['type']] if o['prefer_contract'] else 0, -j['score']))
    return rows


APPLIED_FIELDS = ('id', 'title', 'company', 'url', 'location', 'type', 'salary', 'posted', 'source', 'sources',
                  'eligibility', 'remote', 'score', 'matched', 'ai', 'description')


class StoreError(Exception):
    pass


# Where an application stands, in the order the app lists them.
STATUSES = ('applied', 'screening', 'assessment', 'interview', 'offer', 'rejected', 'no_reply', 'withdrawn')
EMAIL_KINDS = ('confirmation', 'screening', 'assessment', 'interview', 'offer', 'rejection', 'update', 'sent')
# Editable on every entry, with their length limits. A role's listing id still identifies it in searches.
DETAIL_FIELDS = {'url': 1000, 'location': 200, 'salary': 200, 'type': 100, 'channel': 100}
PATCH_FIELDS = {'match', 'title', 'status', 'status_at', 'source', 'notes', 'follow_up', 'emails', *DETAIL_FIELDS}


def utc_iso(value):
    """An ISO timestamp in UTC, so history and emails sort as text. Raises ValueError."""
    when = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return (when if when.tzinfo else when.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc).isoformat(timespec='seconds')


def tracking(entry):
    """Fills in the tracking fields on entries saved before they existed."""
    try:
        applied_at = utc_iso(entry.get('applied_at'))
    except ValueError:
        applied_at = str(entry.get('applied_at', ''))
    entry.setdefault('emails', [])
    note = entry.pop('note', '')
    if note and not any(e.get('subject') == note for e in entry['emails']):
        # Entries imported from email kept the confirmation's subject as a note.
        entry['emails'].insert(0, {'date': applied_at, 'kind': 'confirmation', 'from': '', 'subject': note})
    from_email = entry.get('scope') == 'company' and entry.get('source') == 'email'
    entry.setdefault('history', [{'status': 'applied', 'at': applied_at, 'source': 'email' if from_email else 'app'}])
    entry.setdefault('status', entry['history'][-1]['status'])
    for key in ('notes', 'follow_up', 'channel'):
        entry.setdefault(key, '')
    if entry.get('scope') == 'company':
        # The first email import saved entries before match existed.
        entry.setdefault('match', 'company')
    return entry


LEGAL_SUFFIXES = {'inc', 'llc', 'ltd', 'limited', 'gmbh', 'ag', 'ab', 'bv', 'nv', 'srl', 'sa', 'sas', 'sarl', 'spa',
                  'plc', 'corp', 'corporation', 'co', 'oy', 'as', 'aps', 'pty', 'kg', 'ou', 'sp', 'z', 'oo'}


def company_key(name):
    """Company name without case, punctuation or legal suffixes, so "Proxify AB" matches "Proxify"."""
    words = re.sub(r'[^a-z0-9]+', ' ', str(name or '').lower().replace('.', '')).split()
    while len(words) > 1 and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return ' '.join(words)


# What a company entry does in searches: hide every role, hide only its titled roles, or show roles with a badge.
MATCHES = ('company', 'role', 'badge')


def title_key(title):
    return re.sub(r'[^a-z0-9]+', ' ', str(title or '').lower()).strip()


def applied_keys(job):
    """A role counts as applied by listing id, by URL, or by company and title across boards and locations.
    A company entry (from an application email) covers every role at that company, only its titled roles,
    or none (a badge entry marks roles instead of hiding them)."""
    if job.get('scope') == 'company':
        key, match = company_key(job.get('company')), job.get('match', 'company')
        if match == 'role':
            return {f'crole:{key}|{title_key(t)}' for t in str(job.get('title') or '').split('; ') if title_key(t)}
        return {'company:' + key} if match == 'company' else set()
    keys = {'id:' + str(job.get('id', ''))}
    url = re.sub(r'^https?://(?:www\.)?', '', str(job.get('url', '')).split('#')[0].strip().lower()).rstrip('/')
    if url:
        keys.add('url:' + url)
    if str(job.get('company') or '').strip() and str(job.get('title') or '').strip():
        keys.add('role:' + remote.dedupe_key(job))
    return keys


def reposted_for(job, companies):
    """The applied company a reposting board names at the start of its description, as in LinkedIn's
    "Undelucram.ro on behalf of: SoftServe About The Role", or ''. The name runs on into the description,
    so the longest applied company the text starts with wins."""
    poster = str(job.get('company') or '').strip()
    found = poster and re.match(re.escape(poster) + r'\s+on behalf of\b:?\s*(.{1,200})', str(job.get('description') or ''), re.I)
    if not found:
        return ''
    text = company_key(found.group(1))
    return max((k for k in companies if text == k or text.startswith(k + ' ')), key=len, default='')


class AppliedStore:
    """Jobs the user marked as applied, kept on the service so every search leaves them out."""
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.jobs = None

    def load(self):
        if self.jobs is None:
            try:
                rows = json.loads(self.path.read_text())['jobs']
            except FileNotFoundError:
                rows = []
            except (OSError, ValueError, KeyError, TypeError):
                # Never overwrite a file we could not read: it holds the user's application history.
                raise StoreError(f'{self.path.name} on the service could not be read.')
            self.jobs = {j['id']: tracking(j) for j in rows if isinstance(j, dict) and isinstance(j.get('id'), str)}
        return self.jobs

    def save(self):
        temp = self.path.with_name(self.path.name + '.tmp')
        with os.fdopen(os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), 'w') as f:
            json.dump({'jobs': list(self.jobs.values())}, f, indent=1)
        os.replace(temp, self.path)

    def list(self):
        with self.lock:
            return sorted(copy.deepcopy(list(self.load().values())), key=lambda j: j.get('applied_at', ''), reverse=True)

    def add(self, job):
        if not isinstance(job, dict):
            raise ValueError('Job must be an object.')
        if job.get('scope') == 'company':
            return self.add_company(job)
        record = {k: copy.deepcopy(job[k]) for k in APPLIED_FIELDS if k in job}
        if not all(isinstance(record.get(k), str) and record[k].strip() for k in ('id', 'title', 'url')):
            raise ValueError('Job needs an id, title and url.')
        if len(record['id']) > 64 or not record['url'].startswith(('https://', 'http://')) or not isinstance(record.get('company', ''), str):
            raise ValueError('Invalid job.')
        record['description'] = str(record.get('description') or '')[:6000]
        record['applied_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        tracking(record)
        with self.lock:
            jobs = self.load()
            if record['id'] not in jobs:
                jobs[record['id']] = record
                self.save()
            return copy.deepcopy(jobs[record['id']])

    def add_company(self, entry):
        company = entry.get('company')
        if not isinstance(company, str) or len(company) > 200 or not company_key(company):
            raise ValueError('A company entry needs a company name.')
        applied_at = entry.get('applied_at') or dt.datetime.now(dt.timezone.utc).isoformat()
        dt.datetime.fromisoformat(str(applied_at))  # ValueError for a malformed date
        key = company_key(company)
        record = dict(id='company-' + hashlib.sha256(key.encode()).hexdigest()[:20], scope='company', company=company.strip(),
                      company_key=key, title=str(entry.get('title') or '')[:300], source=str(entry.get('source') or 'email')[:40],
                      note=str(entry.get('note') or '')[:500], applied_at=str(applied_at), match=entry.get('match', 'company'))
        self.check_match(record)
        tracking(record)
        with self.lock:
            jobs = self.load()
            existing = jobs.get(record['id'])
            if existing is None:
                jobs[record['id']] = record
            elif record['title'] and record['title'] not in existing['title']:
                # Another role at a company already on the list.
                existing['title'] = '; '.join(x for x in (existing['title'], record['title']) if x)[:300]
            else:
                return copy.deepcopy(existing)
            self.save()
            return copy.deepcopy(jobs[record['id']])

    @staticmethod
    def check_match(entry):
        if entry['match'] not in MATCHES:
            raise ValueError('Unknown match.')
        if entry['match'] == 'role' and not title_key(entry['title']):
            raise ValueError('Hiding by role needs a role title.')

    def set_match(self, entry_id, match):
        """Changes what a company entry does in searches. Returns the entry, or None if there is no such company entry."""
        return self.update(entry_id, {'match': match})

    def update(self, entry_id, change):
        """Applies a change from the app or the email import: status, details, notes, follow-up date, emails or match.
        Returns the entry, or None if there is no such entry (or no such company entry, for match and title).
        ValueError messages are written for the app."""
        if not isinstance(change, dict) or not change or not set(change) <= PATCH_FIELDS:
            raise ValueError('Invalid change.')
        if ('status_at' in change or 'source' in change) and 'status' not in change:
            raise ValueError('Invalid change.')
        with self.lock:
            entry = self.load().get(entry_id)
            if entry is None or (entry.get('scope') != 'company' and ({'match', 'title'} & set(change))):
                return None
            new = copy.deepcopy(entry)
            for key, limit in DETAIL_FIELDS.items():
                if key in change:
                    value = change[key]
                    if not isinstance(value, str) or len(value) > limit:
                        raise ValueError(f'The {key} is too long.')
                    if key == 'url' and value and not value.startswith(('https://', 'http://')):
                        raise ValueError('The link must start with https://.')
                    new[key] = value.strip()
            if 'title' in change:
                if not isinstance(change['title'], str) or len(change['title']) > 300:
                    raise ValueError('The title is too long.')
                new['title'] = change['title'].strip()
            if 'match' in change:
                new['match'] = change['match']
            if 'notes' in change:
                if not isinstance(change['notes'], str) or len(change['notes']) > 4000:
                    raise ValueError('Notes are limited to 4,000 characters.')
                new['notes'] = change['notes']
            if 'follow_up' in change:
                value = change['follow_up']
                if not isinstance(value, str) or (value and dt.date.fromisoformat(value).isoformat() != value):
                    raise ValueError('Invalid follow-up date.')
                new['follow_up'] = value
            if 'emails' in change:
                self.add_emails(new, change['emails'])
            if 'status' in change:
                if change['status'] not in STATUSES or change.get('source', 'app') not in ('app', 'email'):
                    raise ValueError('Unknown status.')
                at = utc_iso(change.get('status_at') or dt.datetime.now(dt.timezone.utc).isoformat())
                step = {'status': change['status'], 'at': at, 'source': change.get('source', 'app')}
                # Picking the current status again, or replaying an email, adds nothing.
                repeat = change['status'] == new['status'] and 'status_at' not in change
                if not repeat and not any(h['status'] == step['status'] and h['at'] == at for h in new['history']):
                    new['history'] = sorted(new['history'] + [step], key=lambda h: h['at'])
                # A status dated earlier (from an old email) doesn't replace a newer one.
                new['status'] = new['history'][-1]['status']
            if new.get('scope') == 'company':
                self.check_match(new)
            self.load()[entry_id] = new
            self.save()
            return copy.deepcopy(new)

    @staticmethod
    def add_emails(entry, emails):
        if not isinstance(emails, list) or len(emails) > 50:
            raise ValueError('Invalid emails.')
        for e in emails:
            if not isinstance(e, dict) or e.get('kind') not in EMAIL_KINDS or not isinstance(e.get('subject'), str):
                raise ValueError('Invalid email.')
            row = {'date': utc_iso(e.get('date')), 'kind': e['kind'], 'from': str(e.get('from') or '')[:200],
                   'subject': e['subject'][:200]}
            for key in ('message_id', 'thread_id'):
                if e.get(key):
                    if not isinstance(e[key], str) or len(e[key]) > 200:
                        raise ValueError('Invalid email identifier.')
                    row[key] = e[key]
            same = next((x for x in entry['emails'] if
                         (row.get('message_id') and x.get('message_id') == row['message_id']) or
                         (x['date'] == row['date'] and x['subject'] == row['subject'])), None)
            if same is None:
                entry['emails'].append(row)
            else:
                for key in ('from', 'message_id', 'thread_id'):
                    if not same.get(key) and row.get(key):
                        same[key] = row[key]
        # Oldest first; the newest 100 are kept.
        entry['emails'] = sorted(entry['emails'], key=lambda x: x['date'])[-100:]

    def remove(self, job_id):
        with self.lock:
            jobs = self.load()
            if job_id not in jobs:
                return False
            del jobs[job_id]
            self.save()
            return True

    def exclude(self, jobs):
        """Drops roles the user already applied to and marks roles at badge companies, which go last.
        Returns (kept, hidden count)."""
        with self.lock:
            records = copy.deepcopy(list(self.load().values()))
        keys = set().union(*(applied_keys(r) for r in records))
        badges = {company_key(r['company']): r for r in records if r.get('scope') == 'company' and r.get('match') == 'badge'}
        names = {}
        for r in records:
            if company_key(r.get('company')):
                names.setdefault(company_key(r['company']), set()).add(r['company'])
        kept, marked = [], []
        for j in jobs:
            ck = j.get('company_key', '')
            listing = applied_keys(j) | ({'company:' + ck, f'crole:{ck}|{title_key(j.get("title"))}'} if ck else set())
            # A reposted role also counts as the company it was posted for.
            client = reposted_for(j, names)
            if client:
                listing |= {'company:' + client, f'crole:{client}|{title_key(j.get("title"))}'}
                listing |= {'role:' + remote.dedupe_key(dict(company=n, title=j['title'])) for n in names[client]}
            if listing & keys:
                continue
            badge = badges.get(ck) or badges.get(client)
            if badge:
                j['applied_badge'] = dict(company=badge['company'], applied_at=badge['applied_at'])
                marked.append(j)
            else:
                kept.append(j)
        return kept + marked, len(jobs) - len(kept) - len(marked)


def jev_price():
    try:
        price = float(os.environ.get('JOBS_JEV_PRICE') or JEV_PRICE)
    except ValueError:
        return JEV_PRICE
    return price if 0 <= price < 1000 else JEV_PRICE


class JevUsage:
    """What the browser agent (LinkedIn, Glassdoor) used on each search, kept on the service for the app.
    Dollars are an estimate from input tokens at the configured price, plus any text-helper cost an API billed."""
    FIELDS = ('requests', 'input_tokens', 'output_tokens', 'text_calls', 'text_tokens')
    KEEP = 500

    def __init__(self, path, price=JEV_PRICE, clock=time.time):
        self.path, self.price, self.clock = Path(path), price, clock
        self.lock = threading.Lock()
        self.data = None

    def load(self):
        if self.data is None:
            try:
                data = json.loads(self.path.read_text())
                if not isinstance(data.get('runs'), list) or not isinstance(data.get('total'), dict):
                    raise TypeError
            except FileNotFoundError:
                data = dict(runs=[], total={})
            except (OSError, ValueError, AttributeError, TypeError):
                # Never overwrite a file we could not read.
                raise StoreError(f'{self.path.name} on the service could not be read.')
            self.data = data
        return self.data

    def add(self, usage):
        """Never raises: losing one record must not lose the search's roles."""
        row = {k: usage[k] if type(usage.get(k)) is int and usage[k] >= 0 else 0 for k in self.FIELDS}
        cost = usage.get('text_cost')
        row.update(text_cost=float(cost) if type(cost) in (int, float) and cost >= 0 else None,
                   text_model=str(usage.get('text_model') or '')[:80], source=str(usage.get('source') or '')[:20],
                   at=dt.datetime.fromtimestamp(self.clock(), dt.timezone.utc).isoformat(timespec='seconds'))
        try:
            with self.lock:
                data = self.load()
                data['runs'] = (data['runs'] + [row])[-self.KEEP:]
                # Running totals outlive the runs that KEEP drops.
                data['total'] = self.sum([data['total'], dict(row, runs=1)])
                temp = self.path.with_name(self.path.name + '.tmp')
                with os.fdopen(os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), 'w') as f:
                    json.dump(data, f, indent=1)
                os.replace(temp, self.path)
        except (OSError, StoreError) as exc:
            print(f'Jev usage was not recorded: {exc}', file=sys.stderr, flush=True)

    def sum(self, rows):
        total = {k: sum(r.get(k) or 0 for r in rows) for k in ('runs',) + self.FIELDS}
        costs = [r['text_cost'] for r in rows if r.get('text_cost') is not None]
        total['text_cost'] = round(sum(costs), 8) if costs else None
        return total

    def priced(self, row):
        jev = round(row['input_tokens'] * self.price / 1e6, 8)
        return dict(row, jev_cost=jev, cost=round(jev + (row.get('text_cost') or 0), 8))

    def summary(self):
        """The last run, the last 30 days and all time. Raises StoreError."""
        cutoff = dt.datetime.fromtimestamp(self.clock() - 30 * 86400, dt.timezone.utc).isoformat(timespec='seconds')
        with self.lock:
            data = copy.deepcopy(self.load())
        recent = [r for r in data['runs'] if r['at'] >= cutoff]
        return dict(price_per_million_input=self.price,
                    last=self.priced(data['runs'][-1]) if data['runs'] else None,
                    days30=self.priced(dict(self.sum(recent), runs=len(recent))),
                    total=self.priced(self.sum([data['total']])))


class Cancelled(Exception):
    """The search was cancelled, or a newer search replaced it."""


class Stop:
    """A search's cancel switch. Setting it interrupts the child process the search is waiting on (a browser
    agent or a ranking call) the way Ctrl+C would, so a browser agent still closes its tab and reports its usage."""
    GRACE = 10

    def __init__(self):
        self.event = threading.Event()
        self.lock = threading.Lock()
        self.procs = set()

    def set(self):
        with self.lock:
            self.event.set()
            procs = list(self.procs)
        for proc in procs:
            with contextlib.suppress(OSError):
                proc.send_signal(signal.SIGINT)
            # Killed only if it ignores the interrupt; kill() does nothing once the process has exited.
            timer = threading.Timer(self.GRACE, proc.kill)
            timer.daemon = True
            timer.start()

    def run(self, cmd, input=None, capture_output=False, timeout=None, **kwargs):
        """subprocess.run for a search's child processes."""
        if capture_output:
            kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with self.lock:
            if self.event.is_set():
                raise Cancelled()
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if input is not None else None, **kwargs)
            self.procs.add(proc)
        try:
            with proc:
                try:
                    out, err = proc.communicate(input, timeout=timeout)
                except BaseException:
                    proc.kill()
                    proc.wait()
                    raise
        finally:
            with self.lock:
                self.procs.discard(proc)
        return subprocess.CompletedProcess(cmd, proc.returncode, out, err)


class SearchResults:
    """The last finished search, kept on the service so every device shows the same roles and a restart keeps them.
    Without a path it lives in memory only."""
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        self.data = None
        self.read = self.path is None

    def get(self):
        with self.lock:
            if not self.read:
                self.read = True
                try:
                    data = json.loads(self.path.read_text())
                    self.data = data if isinstance(data, dict) and isinstance(data.get('jobs'), list) else None
                except (OSError, ValueError):
                    # Only a copy of a search's results: the next search replaces an unreadable file.
                    self.data = None
            return copy.deepcopy(self.data)

    def put(self, run):
        """Never raises: the search still finished when its file can't be written."""
        with self.lock:
            self.data, self.read = copy.deepcopy(run), True
            if not self.path:
                return
            try:
                temp = self.path.with_name(self.path.name + '.tmp')
                with os.fdopen(os.open(temp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), 'w') as f:
                    json.dump(run, f)
                os.replace(temp, self.path)
            except OSError as exc:
                print(f'Could not save the search results: {exc}', file=sys.stderr)


# How long a search waits for its Gmail check after the sources are done.
GMAIL_WAIT = 180


class Engine:
    def __init__(self, applied=None, jev_usage=None, results=None, gmail=None):
        self.lock = threading.Lock()
        self.runs = {}
        self.stops = {}
        self.cache = {}
        self.ai_cache = {}
        self.applied = applied or AppliedStore(APPLIED_FILE)
        self.jev_usage = jev_usage or JevUsage(JEV_USAGE_FILE, jev_price())
        # The service passes SEARCH_FILE; without it (tests) results stay in memory.
        self.results = results or SearchResults()
        # The service's GmailSync, which every search runs first; None skips it.
        self.gmail = gmail

    def start(self, options):
        o = validate_options(options)
        # Kept out of the run state, which every poll sends back to the app.
        dismissed = set(o.pop('dismissed'))
        with self.lock:
            for key, run in self.runs.items():
                if run['status'] == 'running':
                    if run['options'] == o:
                        return key
                    raise RuntimeError('A search is already running. Wait for it to finish.')
            run_id = secrets.token_hex(12)
            self.runs = {run_id: dict(status='running', options=o, jobs=[], sources=[], current='Starting search', fetched=0, applied_hidden=0)}
            self.stops = {run_id: Stop()}
        threading.Thread(target=self.run, args=(run_id, o, dismissed), daemon=True).start()
        return run_id

    def get(self, key):
        with self.lock:
            return copy.deepcopy(self.runs.get(key))

    def latest(self, have=None):
        """What a device shows: the search running now, if any, and the last finished one.
        results is left out when the device already has the search finished at `have`."""
        with self.lock:
            running = next((key for key, run in self.runs.items() if run['status'] == 'running'), None)
        results = self.results.get()
        updated_at = results.get('updated_at') if results else None
        return dict(running=running, updated_at=updated_at, results=None if have and have == updated_at else results)

    def cancel(self, key):
        """Returns the run, or None when the service no longer has it. Only a running search changes."""
        with self.lock:
            run = self.runs.get(key)
            if run is None:
                return None
            if run['status'] == 'running':
                run.update(status='cancelled', current='Search cancelled')
                stop = self.stops.get(key)
                if stop:
                    stop.set()
            return copy.deepcopy(run)

    def update(self, key, **fields):
        with self.lock:
            run = self.runs.get(key)
            # A cancelled search stops at its next step, and so does one a newer search replaced.
            if run is None or run.get('status') == 'cancelled':
                raise Cancelled()
            run.update(fields)
            # Only this search's thread changes the run once it stops running, so callers may copy it later.
            return run

    def cached(self, key, fetch):
        entry = self.cache.get(key)
        if entry and time.time() - entry[0] < 3600:
            return copy.deepcopy(entry[1]), True
        result = fetch()
        self.cache[key] = (time.time(), copy.deepcopy(result))
        # Bound cache memory for varied search options.
        if len(self.cache) > 64:
            del self.cache[min(self.cache, key=lambda k: self.cache[k][0])]
        return result, False

    def adzuna(self, o):
        creds = (os.environ.get('ADZUNA_APP_ID'), os.environ.get('ADZUNA_APP_KEY'))
        if not all(creds):
            raise ValueError('Adzuna credentials are not configured on the service.')
        c = config('broad_config.json' if o['preset'] != 'backend' else 'config.json')
        c['countries'] = o['countries']
        for query in c['queries']:
            query['pages'] = 1
            query['params']['max_days_old'] = o['max_age_days']
            if o['keywords'].strip():
                query['params'] = {'what_or': o['keywords'].replace(',', ' '), 'max_days_old': o['max_age_days'], 'results_per_page': 50}
        if o['keywords'].strip():
            c['queries'] = c['queries'][:1]
        outcome = az.run_search(c, az.LiveFetcher(*creds, timeout=15), delay=2.5)
        rows = []
        for country, _, raw in outcome['results']:
            j = az.normalize_job(raw, country, c['currencies'].get(country, 'USD'))
            if j:
                rows.append(remote.job('adzuna', j['id'], j['title'], j['company'], j['redirect_url'],
                    location=j['location'], type_field=j['contract_type'] + ' ' + j['contract_time'],
                    salary=j['salary'], posted=j['posted'], description=j['description']))
        failures = [az.describe_failure(x) for x in outcome['failures']]
        if failures and not rows:
            raise ValueError('; '.join(failures))
        return rows, failures

    def run(self, key, o, dismissed=frozenset()):
        raw, statuses, jobs, set_aside = [], [], [], []
        stop = self.stops.get(key) or Stop()
        try:
            c = search_config(o)
            plans = [('adzuna', None)] if o['adzuna'] else []
            plans += [(name, c.get('sources', {}).get(name, config('remote_config.json')['sources'].get(name, {}))) for name in o['boards']]
            if o['preset'] == 'gaming' and o['boards']:
                plans += [(name, opts) for name, opts in c['sources'].items() if name not in PUBLIC_SOURCES]
            # Last: the browser agents take the longest, so the other sources show first. Each one searches remote
            # roles, then hybrid roles in each place asked for; for these sites a plan's options is that place.
            # Romania's goes last: LinkedIn keeps the last searched country as the account's job search location.
            places = sorted(o['hybrid'], key=lambda place: place == 'romania')
            for name, site in (('linkedin', linkedin), ('glassdoor', glassdoor)):
                if o[name] and site.enabled():
                    plans += [(name, None)] + [(name, place) for place in places if place in site.HYBRID_PLACES]
            self.update(key, total=len(plans))
            # Gmail is checked beside the sources, so applications found by email are left out below. A cancelled
            # search doesn't stop the check: the next search would only wait for it.
            checked = {}
            def check_gmail():
                try:
                    checked['gmail'] = self.gmail.run_for_search(o['ai_engine'], o['ai_subscription'])
                except Exception:
                    checked['gmail'] = dict(status='error', message='Gmail check failed; check the server.')
            gmail = threading.Thread(target=check_gmail, name='gmail-search', daemon=True) if self.gmail else None
            if gmail:
                gmail.start()
            for name, options in plans:
                # A browser agent's hybrid search names its place; the app shows it beside the source.
                place = options if name in ('linkedin', 'glassdoor') else None
                self.update(key, current=f'Fetching {name}' + (f' hybrid roles in {jev.PLACES[place]}' if place else ''),
                            source=name, place=place)
                try:
                    if name == 'adzuna':
                        cache_key = json.dumps(['adzuna', o['preset'], o['countries'], o['keywords'], o['max_age_days']], sort_keys=True)
                        (rows, warnings), cached = self.cached(cache_key, lambda: self.adzuna(o))
                    elif name in ('linkedin', 'glassdoor'):
                        site = linkedin if name == 'linkedin' else glassdoor
                        cache_key = json.dumps([name, site.request(o, place)], sort_keys=True)
                        (rows, warnings), cached = self.cached(
                            cache_key, lambda: site.fetch(o, remote.job, record=self.jev_usage.add, runner=stop.run, place=place))
                    else:
                        options = copy.deepcopy(options)
                        if name == 'himalayas':
                            options.update(contractor_pages=1, any_type_pages=1)
                            options['queries'] = ([x.strip() for x in o['keywords'].split(',') if x.strip()] or options.get('queries', ['backend']))[:3]
                        if name == 'arbeitnow':
                            options['pages'] = 2
                        cache_key = json.dumps([name, options], sort_keys=True)
                        def fetch():
                            options["_failures"] = []
                            result = remote.SOURCES[name](remote.Http(1.0), options)
                            # Company-board collectors return (jobs, individual-board failures).
                            if isinstance(result, tuple):
                                return result
                            return result, options["_failures"]
                        (rows, warnings), cached = self.cached(cache_key, fetch)
                    raw.extend(rows)
                    statuses.append(dict(name=name, status='partial' if warnings else 'ok', count=len(rows), cached=cached, message=str(warnings) if warnings else '',
                                         **({'place': place} if place else {})))
                except Exception as exc:
                    # Never expose upstream URLs that could contain API keys.
                    own = (name == 'adzuna' and isinstance(exc, ValueError)) or isinstance(exc, jev.AgentError)
                    message = str(exc) if own else f'{type(exc).__name__}: source unavailable; other sources continue.'
                    statuses.append(dict(name=name, status='error', count=0, cached=False, message=message,
                                         **({'place': place} if place else {})))
                # Applied roles go before Claude's step, so they are never ranked or shown again.
                jobs, hidden = self.applied.exclude(rank(raw, o))
                # Dismissed roles still come back for the Dismissed tab, but last and outside the AI step,
                # so they never take a shortlist slot from a role the user hasn't seen.
                jobs, set_aside = [j for j in jobs if j['id'] not in dismissed], [j for j in jobs if j['id'] in dismissed]
                self.update(key, jobs=jobs + set_aside, sources=copy.deepcopy(statuses), fetched=len(raw), applied_hidden=hidden)
            if gmail:
                self.update(key, current='Checking Gmail for roles you applied to', source=None, place=None)
                deadline = time.monotonic() + GMAIL_WAIT
                while gmail.is_alive() and not stop.event.is_set() and time.monotonic() < deadline:
                    gmail.join(1)
                line = checked.get('gmail', dict(status='error', message='Gmail check still running; roles you applied to '
                                                                         'by email since the last check may show.'))
                jobs, hidden = self.applied.exclude(rank(raw, o))
                jobs, set_aside = [j for j in jobs if j['id'] not in dismissed], [j for j in jobs if j['id'] in dismissed]
                self.update(key, jobs=jobs + set_aside, applied_hidden=hidden, **({'gmail': line} if line else {}))
            if o['ai_pick'] and jobs:
                count = min(len(jobs), ai.LIMIT)
                label = f'{o["ai_engine"].title()} · {o["ai_subscription"].title()}'
                self.update(key, current=f'{label} is ranking {count} role{"" if count == 1 else "s"}', source=None, place=None)
                try:
                    # Work on a copy: polling threads deep-copy the published run state.
                    jobs, status = ai.pick(copy.deepcopy(jobs), o, self.ai_cache, stop.run)
                    # Roles at companies already applied to stay below the rest, even when Claude ranked them.
                    jobs.sort(key=lambda j: 'applied_badge' in j)
                except ai.AIError as exc:
                    status = dict(status='error', engine=o['ai_engine'], subscription=o['ai_subscription'], message=str(exc))
                except Exception as exc:
                    status = dict(status='error', engine=o['ai_engine'], subscription=o['ai_subscription'],
                                  message=f'{type(exc).__name__}: {label} ranking failed; keyword ranking shown.')
                self.update(key, jobs=jobs + set_aside, ai=status)
            finished = self.update(key, status='complete', current='Search complete',
                                   updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
            # Every device shows these until the next search finishes. When every source failed, the app keeps the
            # previous results, so the service does too.
            if not statuses or any(s['status'] != 'error' for s in statuses):
                self.results.put(dict(finished, id=key))
        except Cancelled:
            pass
        except Exception:
            with contextlib.suppress(Cancelled):
                self.update(key, status='error', current='Search failed. Please retry.')


def app_release():
    """The APK published by scripts/build_apk.sh, for in-app updates."""
    apk, meta = APP_DIR / 'fieldwork.apk', APP_DIR / 'fieldwork.json'
    try:
        info = json.loads(meta.read_text())
        stat = apk.stat()
    except (OSError, ValueError):
        return {'available': False}
    key = (stat.st_mtime_ns, stat.st_size)
    if app_release.cached[0] != key:
        digest = hashlib.sha256()
        with apk.open('rb') as f:
            for block in iter(lambda: f.read(1 << 20), b''):
                digest.update(block)
        app_release.cached = (key, digest.hexdigest())
    if type(info.get('version_code')) is not int:
        return {'available': False}
    return {'available': True, 'version_code': info['version_code'], 'version_name': str(info.get('version_name', '')),
            'size': stat.st_size, 'sha256': app_release.cached[1]}
app_release.cached = (None, '')


def cv_file():
    """The newest PDF in cv/, which the app saves to the phone's Downloads."""
    try:
        pdfs = [p for p in CV_DIR.iterdir() if p.suffix.lower() == '.pdf' and p.is_file()]
    except OSError:
        return None
    return max(pdfs, key=lambda p: p.stat().st_mtime_ns, default=None)


def download_name(path):
    # Header values must stay ASCII (Ș becomes S); the phone keeps this name in Downloads.
    name = unicodedata.normalize('NFKD', path.name).encode('ascii', 'ignore').decode()
    name = re.sub(r'[^A-Za-z0-9._ -]+', '-', name).strip(' .-')
    return name if name.lower().endswith('.pdf') and len(name) > 4 else 'CV.pdf'


class Handler(BaseHTTPRequestHandler):
    engine = Engine(results=SearchResults(SEARCH_FILE))
    chats = claude_chat.ChatStore()
    gmail = None
    token = ''
    def log_message(self, *args):
        pass
    def respond(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
    def authorized(self):
        if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.token):
            self.respond(401, {'error': 'Check your service access token.'})
            return False
        return True
    def web_file(self):
        """Only the compiled browser shell is public; API routes still need a token."""
        path = unquote(urlparse(self.path).path)
        parts = path.strip('/').split('/')
        entries = {'index.html', 'flutter_bootstrap.js', 'flutter.js',
                   'main.dart.js', 'manifest.json', 'version.json', 'favicon.svg'}
        if path != '/' and parts[0] not in entries | {'assets', 'canvaskit', 'icons'}:
            return False
        base = WEB_DIR.resolve()
        target = (base / ('index.html' if path == '/' else path.lstrip('/'))).resolve()
        if any(part.startswith('.') for part in parts) or not target.is_relative_to(base) or not target.is_file():
            self.respond(404, {'error': 'Website file not found. Build it with scripts/build_web.sh.'})
            return True
        content_type = {'.js': 'text/javascript', '.wasm': 'application/wasm'}.get(
            target.suffix, mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        self.send_file(target, content_type, 'Website file not found.')
        return True

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        super().end_headers()

    def do_GET(self):
        if self.web_file():
            return
        if not self.authorized():
            return
        path = urlparse(self.path).path
        if path == '/health':
            self.respond(200, {'status': 'ok', 'adzuna_configured': bool(os.environ.get('ADZUNA_APP_ID') and os.environ.get('ADZUNA_APP_KEY')),
                               'claude_available': ai.available(), 'claude_chat': claude_chat.enabled(),
                               'linkedin_available': linkedin.enabled(), 'glassdoor_available': glassdoor.enabled()})
        elif path == '/app':
            self.respond(200, app_release())
        elif path == '/ranking/accounts':
            self.respond(200, {'accounts': ai.accounts.catalog()})
        elif path == '/applied':
            try:
                self.respond(200, {'jobs': self.engine.applied.list(),
                                   'gmail_sync': self.gmail.status() if self.gmail else {'enabled': False}})
            except StoreError as exc:
                self.respond(500, {'error': str(exc)})
        elif path == '/gmail-sync':
            self.respond(200, self.gmail.status() if self.gmail else {'enabled': False})
        # /linkedin/usage is the name builds before Glassdoor still ask for.
        elif path in ('/jev/usage', '/linkedin/usage'):
            try:
                self.respond(200, self.engine.jev_usage.summary())
            except StoreError as exc:
                self.respond(500, {'error': str(exc)})
        elif path == '/app/fieldwork.apk':
            self.send_file(APP_DIR / 'fieldwork.apk', 'application/vnd.android.package-archive',
                           'No app build is published on the service.')
        elif path == '/cv':
            cv, missing = cv_file(), 'No CV on the service. Put your PDF in the cv folder on your computer.'
            if cv is None:
                return self.respond(404, {'error': missing})
            self.send_file(cv, 'application/pdf', missing, f'attachment; filename="{download_name(cv)}"')
        elif path.startswith('/claude/'):
            self.claude('GET', path)
        elif path == '/tailored' or path.startswith('/tailored/'):
            self.tailored(path)
        elif path == '/search/latest':
            have = parse_qs(urlparse(self.path).query).get('have', [''])[0]
            self.respond(200, self.engine.latest(have))
        elif path.startswith('/search/'):
            run = self.engine.get(path.rsplit('/', 1)[1])
            self.respond(200 if run else 404, run or {'error': 'Search expired. Start a new search.'})
        else:
            self.respond(404, {'error': 'Not found'})
    def send_file(self, path, content_type, missing, disposition=None):
        try:
            f = path.open('rb')
        except OSError:
            return self.respond(404, {'error': missing})
        with f:
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(os.fstat(f.fileno()).st_size))
            if disposition:
                self.send_header('Content-Disposition', disposition)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            try:
                shutil.copyfileobj(f, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass
    def do_POST(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        if path == '/gmail-sync':
            if not self.gmail:
                return self.respond(503, {'error': 'Gmail sync is not configured.'})
            threading.Thread(target=self.gmail.run_due, daemon=True).start()
            return self.respond(202, self.gmail.status())
        if path.startswith('/claude/'):
            return self.claude('POST', path)
        if path == '/tailor':
            return self.start_tailoring()
        parts = path.strip('/').split('/')
        if len(parts) == 3 and parts[0] == 'search' and parts[2] == 'cancel':
            run = self.engine.cancel(parts[1])
            return self.respond(200 if run else 404, run or {'error': 'Search expired. Start a new search.'})
        if path not in ('/search', '/applied'):
            return self.respond(404, {'error': 'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            # A job carries its description; search options carry up to MAX_DISMISSED listing ids.
            if not 0 < size <= 65536:
                raise ValueError('Invalid request size.')
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(size))
            if path == '/applied':
                return self.respond(200, {'job': self.engine.applied.add(body)})
            self.respond(202, {'id': self.engine.start(body)})
        except (ValueError, TypeError):
            self.respond(400, {'error': 'Invalid search options.' if path == '/search' else 'Invalid job.'})
        except RuntimeError as exc:
            self.respond(409, {'error': str(exc)})
        except StoreError as exc:
            self.respond(500, {'error': str(exc)})
    def do_PATCH(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        if not path.startswith('/applied/'):
            return self.respond(404, {'error': 'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            # Notes and email trails make a change larger than a match switch.
            if not 0 < size <= 32768:
                raise ValueError('Invalid request size.')
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(size))
        except (ValueError, TypeError):
            return self.respond(400, {'error': 'Invalid change.'})
        try:
            entry = self.engine.applied.update(path.rsplit('/', 1)[1], body)
            self.respond(200 if entry else 404, {'job': entry} if entry else {'error': 'No such application.'})
        except ValueError as exc:
            # update's messages are written for the app.
            self.respond(400, {'error': str(exc)})
        except StoreError as exc:
            self.respond(500, {'error': str(exc)})
    def do_DELETE(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        if path.startswith('/claude/'):
            return self.claude('DELETE', path)
        if not path.startswith('/applied/'):
            return self.respond(404, {'error': 'Not found'})
        try:
            self.respond(200, {'removed': self.engine.applied.remove(path.rsplit('/', 1)[1])})
        except StoreError as exc:
            self.respond(500, {'error': str(exc)})
    def read_json(self, limit):
        size = int(self.headers.get('Content-Length', '0'))
        if not 0 < size <= limit:
            raise ValueError('Invalid request size.')
        self.connection.settimeout(10)
        body = json.loads(self.rfile.read(size))
        if not isinstance(body, dict):
            raise ValueError('Invalid request.')
        return body
    def tailored(self, path):
        """Tailored CVs: the list, and each one's PDF and report."""
        parts = path.strip('/').split('/')[1:]
        if not parts:
            return self.respond(200, {'cvs': tailor.listing()})
        folder = tailor.find(*parts[:2]) if len(parts) == 3 else None
        missing = {'error': 'This tailored CV is no longer on the service.'}
        if folder is None:
            return self.respond(404, missing)
        if parts[2] == 'cv':
            pdf, _ = tailor.files(folder)
            if pdf is None:
                return self.respond(404, {'error': 'Claude has not built this PDF yet.'})
            return self.send_file(pdf, 'application/pdf', missing,
                                  f'attachment; filename="{download_name(Path(tailor.pdf_name()))}"')
        if parts[2] == 'report':
            text = tailor.report_text(folder)
            return self.respond(200 if text is not None else 404,
                                {'text': text} if text is not None else {'error': 'This CV has no report yet.'})
        self.respond(404, {'error': 'Not found'})
    def start_tailoring(self):
        """Starts a Claude page chat that tailors the CV to a job, or reopens the one already doing it."""
        if not claude_chat.enabled():
            return self.respond(403, {'error': 'The Claude page is switched off on the service (JOBS_CLAUDE_CHAT).'})
        try:
            chat, existing = tailor.start(self.chats, self.read_json(65536))
            self.respond(200 if existing else 202, {'chat': chat, 'existing': existing})
        except json.JSONDecodeError:
            self.respond(400, {'error': 'Invalid request.'})
        except ValueError as exc:
            self.respond(400, {'error': str(exc)})
        except RuntimeError as exc:
            self.respond(409, {'error': str(exc)})
        except claude_chat.ChatError as exc:
            self.respond(503, {'error': str(exc)})
        except OSError:
            self.respond(500, {'error': 'The tailored CV folder could not be created on the service computer.'})
    def claude(self, method, path):
        """The Claude page: chats with Claude Code on this computer, in a folder the service offers."""
        if not claude_chat.enabled():
            return self.respond(403, {'error': 'The Claude page is switched off on the service (JOBS_CLAUDE_CHAT).'})
        parts = path.strip('/').split('/')[1:]
        chat_id = parts[1] if len(parts) > 1 else ''
        missing = {'error': 'This chat is no longer on the service.'}
        try:
            if method == 'GET' and parts == ['folders']:
                rows = claude_chat.folders()
                return self.respond(200, {'folders': rows, 'default': rows[0]['path'] if rows else '',
                                          'model': claude_chat.MODEL, 'effort': claude_chat.EFFORT})
            if method == 'GET' and parts == ['chats']:
                return self.respond(200, {'chats': self.chats.list()})
            if method == 'GET' and len(parts) == 4 and parts[0] == 'chats' and parts[2] == 'images':
                image = self.chats.image(chat_id, parts[3])
                if not image:
                    return self.respond(404, {'error': 'This image is no longer on the service.'})
                kind = next(k for k, ext in claude_chat.IMAGE_TYPES.items() if image.suffix == '.' + ext)
                return self.send_file(image, kind, 'This image is no longer on the service.')
            if method == 'GET' and len(parts) == 2 and parts[0] == 'chats':
                start = parse_qs(urlparse(self.path).query).get('from', ['0'])[0]
                chat = self.chats.get(chat_id, int(start) if start.isdigit() else 0)
                return self.respond(200 if chat else 404, {'chat': chat} if chat else missing)
            if method == 'DELETE' and len(parts) == 2 and parts[0] == 'chats':
                return self.respond(200, {'removed': self.chats.remove(chat_id)})
            if method == 'POST' and parts == ['chats']:
                body = self.read_json(claude_chat.REQUEST_BYTES)
                return self.respond(202, {'chat': self.chats.create(body.get('cwd'), body.get('text'), body.get('images'))})
            if method == 'POST' and len(parts) == 3 and parts[0] == 'chats' and parts[2] == 'messages':
                body = self.read_json(claude_chat.REQUEST_BYTES)
                chat = self.chats.send(chat_id, body.get('text'), body.get('images'))
                return self.respond(202 if chat else 404, {'chat': chat} if chat else missing)
            if method == 'POST' and len(parts) == 3 and parts[0] == 'chats' and parts[2] == 'stop':
                chat = self.chats.stop(chat_id)
                return self.respond(200 if chat else 404, {'chat': chat} if chat else missing)
            self.respond(404, {'error': 'Not found'})
        except json.JSONDecodeError:
            self.respond(400, {'error': 'Invalid request.'})
        except ValueError as exc:
            # ChatStore's messages are written for the app.
            self.respond(400, {'error': str(exc)})
        except RuntimeError as exc:
            self.respond(409, {'error': str(exc)})
        except claude_chat.ChatError as exc:
            self.respond(503, {'error': str(exc)})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    args = p.parse_args()
    # Taken out of the environment so no child process (the Claude page, ranking, the browser agents) inherits it.
    gmail_password = os.environ.pop('JOBS_GMAIL_APP_PASSWORD', '')
    token_path = ROOT / '.access-token'
    token = os.environ.get('JOBS_ACCESS_TOKEN', '')
    if not token:
        if not token_path.exists():
            fd = os.open(token_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(32))
        token = token_path.read_text().strip()
    if len(token) < 20:
        raise SystemExit('JOBS_ACCESS_TOKEN must be at least 20 characters.')
    Handler.token = token
    print(f'Jobs service: http://{args.host}:{args.port}', flush=True)
    print('Use the token from backend/.access-token (or JOBS_ACCESS_TOKEN) in the app.', flush=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    def gmail_choice():
        # A daily sweep uses the engine and subscription of the last search.
        o = (Handler.engine.results.get() or {}).get('options') or {}
        return o.get('ai_engine', 'claude'), o.get('ai_subscription', 'personal')
    Handler.gmail = Handler.engine.gmail = gmail_sync.GmailSync(Handler.engine.applied, choice=gmail_choice,
                                                                password=gmail_password)
    Handler.gmail.start()
    # Catches up on tailored CVs finished while the service was down or before the export folder was set.
    threading.Thread(target=tailor.export_all, name='tailored-export', daemon=True).start()
    server.serve_forever()

if __name__ == '__main__':
    main()

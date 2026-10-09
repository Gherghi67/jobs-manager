"""Personal job-search API; collectors are vendored from cv-refactor."""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT.parent / 'artifacts'
APPLIED_FILE = Path(os.environ.get('JOBS_APPLIED_FILE') or ROOT / 'applied.json')
sys.path.insert(0, str(ROOT / 'vendor'))
import adzuna_search as az
import remote_search as remote
import ai_pick as ai

PUBLIC_SOURCES = ['remotive', 'remoteok', 'himalayas', 'jobicy', 'workingnomads', 'weworkremotely', 'arbeitnow', 'hackernews']
DEFAULTS = dict(preset='broad', adzuna=True, boards=PUBLIC_SOURCES, countries=['de', 'nl', 'gb'],
                keywords='', remote_only=True, eligibility='romania', contract_only=False,
                prefer_contract=True, max_age_days=30, ai_pick=True)


def config(name):
    return json.loads((ROOT / 'config' / name).read_text())


def validate_options(value):
    if not isinstance(value, dict):
        raise ValueError('Options must be an object.')
    if set(value) - set(DEFAULTS):
        raise ValueError('Unknown search option.')
    o = copy.deepcopy(DEFAULTS)
    o.update(value)
    if o['preset'] not in ('backend', 'broad', 'gaming'):
        raise ValueError('Unknown preset.')
    for key in ('adzuna', 'remote_only', 'contract_only', 'prefer_contract', 'ai_pick'):
        if type(o[key]) is not bool:
            raise ValueError(f'{key} must be true or false.')
    if not isinstance(o['boards'], list) or any(x not in PUBLIC_SOURCES for x in o['boards']):
        raise ValueError('Unknown remote board.')
    if not isinstance(o['countries'], list) or not 1 <= len(o['countries']) <= 7 or any(x not in ('us', 'gb', 'de', 'nl', 'pl', 'at', 'es', 'fr') for x in o['countries']):
        raise ValueError('Choose 1–7 supported Adzuna countries.')
    if not o['adzuna'] and not o['boards']:
        raise ValueError('Enable at least one source.')
    if o['eligibility'] not in ('romania', 'romania_unclear', 'all'):
        raise ValueError('Unknown eligibility option.')
    if type(o['max_age_days']) is not int or not 1 <= o['max_age_days'] <= 90:
        raise ValueError('Age must be 1–90 days.')
    if not isinstance(o['keywords'], str) or len(o['keywords']) > 200:
        raise ValueError('Keywords must be at most 200 characters.')
    o['boards'] = list(dict.fromkeys(o['boards']))
    o['countries'] = list(dict.fromkeys(o['countries']))
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
    rows.sort(key=lambda j: ((0 if j['eligibility'] in ('worldwide', 'europe') else 1),
                            remote.TYPE_ORDER[j['type']] if o['prefer_contract'] else 0, -j['score']))
    return rows


APPLIED_FIELDS = ('id', 'title', 'company', 'url', 'location', 'type', 'salary', 'posted', 'source', 'sources',
                  'eligibility', 'remote', 'score', 'matched', 'ai', 'description')


class StoreError(Exception):
    pass


LEGAL_SUFFIXES = {'inc', 'llc', 'ltd', 'limited', 'gmbh', 'ag', 'ab', 'bv', 'nv', 'srl', 'sa', 'sas', 'sarl', 'spa',
                  'plc', 'corp', 'corporation', 'co', 'oy', 'as', 'aps', 'pty', 'kg', 'ou', 'sp', 'z', 'oo'}


def company_key(name):
    """Company name without case, punctuation or legal suffixes, so "Proxify AB" matches "Proxify"."""
    words = re.sub(r'[^a-z0-9]+', ' ', str(name or '').lower().replace('.', '')).split()
    while len(words) > 1 and words[-1] in LEGAL_SUFFIXES:
        words.pop()
    return ' '.join(words)


def applied_keys(job):
    """A role counts as applied by listing id, by URL, or by company and title across boards and locations.
    A company entry (from an application email) covers every role at that company."""
    if job.get('scope') == 'company':
        return {'company:' + company_key(job.get('company'))}
    keys = {'id:' + str(job.get('id', ''))}
    url = re.sub(r'^https?://(?:www\.)?', '', str(job.get('url', '')).split('#')[0].strip().lower()).rstrip('/')
    if url:
        keys.add('url:' + url)
    if str(job.get('company') or '').strip() and str(job.get('title') or '').strip():
        keys.add('role:' + remote.dedupe_key(job))
    return keys


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
            self.jobs = {j['id']: j for j in rows if isinstance(j, dict) and isinstance(j.get('id'), str)}
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
                      note=str(entry.get('note') or '')[:500], applied_at=str(applied_at))
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

    def remove(self, job_id):
        with self.lock:
            jobs = self.load()
            if job_id not in jobs:
                return False
            del jobs[job_id]
            self.save()
            return True

    def exclude(self, jobs):
        """Drops roles the user already applied to. Returns (kept, hidden count)."""
        with self.lock:
            keys = set().union(*(applied_keys(j) for j in self.load().values()))
        kept = [j for j in jobs if not (applied_keys(j) | ({'company:' + j['company_key']} if j.get('company_key') else set())) & keys]
        return kept, len(jobs) - len(kept)


class Engine:
    def __init__(self, applied=None):
        self.lock = threading.Lock()
        self.runs = {}
        self.cache = {}
        self.ai_cache = {}
        self.applied = applied or AppliedStore(APPLIED_FILE)

    def start(self, options):
        o = validate_options(options)
        with self.lock:
            for key, run in self.runs.items():
                if run['status'] == 'running':
                    if run['options'] == o:
                        return key
                    raise RuntimeError('A search is already running. Wait for it to finish.')
            run_id = secrets.token_hex(12)
            self.runs = {run_id: dict(status='running', options=o, jobs=[], sources=[], current='Starting search', fetched=0, applied_hidden=0)}
        threading.Thread(target=self.run, args=(run_id, o), daemon=True).start()
        return run_id

    def get(self, key):
        with self.lock:
            return copy.deepcopy(self.runs.get(key))

    def update(self, key, **fields):
        with self.lock:
            self.runs[key].update(fields)

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

    def run(self, key, o):
        raw, statuses, jobs = [], [], []
        try:
            c = search_config(o)
            plans = [('adzuna', None)] if o['adzuna'] else []
            plans += [(name, c.get('sources', {}).get(name, config('remote_config.json')['sources'].get(name, {}))) for name in o['boards']]
            if o['preset'] == 'gaming' and o['boards']:
                plans += [(name, opts) for name, opts in c['sources'].items() if name not in PUBLIC_SOURCES]
            self.update(key, total=len(plans))
            for name, options in plans:
                self.update(key, current=f'Fetching {name}', source=name)
                try:
                    if name == 'adzuna':
                        cache_key = json.dumps(['adzuna', o['preset'], o['countries'], o['keywords'], o['max_age_days']], sort_keys=True)
                        (rows, warnings), cached = self.cached(cache_key, lambda: self.adzuna(o))
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
                    statuses.append(dict(name=name, status='partial' if warnings else 'ok', count=len(rows), cached=cached, message=str(warnings) if warnings else ''))
                except Exception as exc:
                    # Never expose upstream URLs that could contain API keys.
                    message = str(exc) if name == 'adzuna' and isinstance(exc, ValueError) else f'{type(exc).__name__}: source unavailable; other sources continue.'
                    statuses.append(dict(name=name, status='error', count=0, cached=False, message=message))
                # Applied roles go before Claude's step, so they are never ranked or shown again.
                jobs, hidden = self.applied.exclude(rank(raw, o))
                self.update(key, jobs=jobs, sources=copy.deepcopy(statuses), fetched=len(raw), applied_hidden=hidden)
            if o['ai_pick'] and jobs:
                count = min(len(jobs), ai.LIMIT)
                self.update(key, current=f'Claude is ranking {count} role{"" if count == 1 else "s"}', source=None)
                try:
                    # Work on a copy: polling threads deep-copy the published run state.
                    jobs, status = ai.pick(copy.deepcopy(jobs), o, self.ai_cache)
                except ai.AIError as exc:
                    status = dict(status='error', message=str(exc))
                except Exception as exc:
                    status = dict(status='error', message=f'{type(exc).__name__}: Claude ranking failed; keyword ranking shown.')
                self.update(key, jobs=jobs, ai=status)
            self.update(key, status='complete', current='Search complete', updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        except Exception:
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


class Handler(BaseHTTPRequestHandler):
    engine = Engine()
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
    def do_GET(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        if path == '/health':
            self.respond(200, {'status': 'ok', 'adzuna_configured': bool(os.environ.get('ADZUNA_APP_ID') and os.environ.get('ADZUNA_APP_KEY')),
                               'claude_available': ai.available()})
        elif path == '/app':
            self.respond(200, app_release())
        elif path == '/applied':
            try:
                self.respond(200, {'jobs': self.engine.applied.list()})
            except StoreError as exc:
                self.respond(500, {'error': str(exc)})
        elif path == '/app/fieldwork.apk':
            self.send_apk()
        elif path.startswith('/search/'):
            run = self.engine.get(path.rsplit('/', 1)[1])
            self.respond(200 if run else 404, run or {'error': 'Search expired. Start a new search.'})
        else:
            self.respond(404, {'error': 'Not found'})
    def send_apk(self):
        try:
            f = (APP_DIR / 'fieldwork.apk').open('rb')
        except OSError:
            return self.respond(404, {'error': 'No app build is published on the service.'})
        with f:
            self.send_response(200)
            self.send_header('Content-Type', 'application/vnd.android.package-archive')
            self.send_header('Content-Length', str(os.fstat(f.fileno()).st_size))
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
        if path not in ('/search', '/applied'):
            return self.respond(404, {'error': 'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            # A job carries its description, so it may be larger than search options.
            if not 0 < size <= (8192 if path == '/search' else 65536):
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
    def do_DELETE(self):
        if not self.authorized():
            return
        path = urlparse(self.path).path
        if not path.startswith('/applied/'):
            return self.respond(404, {'error': 'Not found'})
        try:
            self.respond(200, {'removed': self.engine.applied.remove(path.rsplit('/', 1)[1])})
        except StoreError as exc:
            self.respond(500, {'error': str(exc)})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    args = p.parse_args()
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
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()

if __name__ == '__main__':
    main()

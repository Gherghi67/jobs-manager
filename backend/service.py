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
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
import adzuna_search as az
import remote_search as remote

PUBLIC_SOURCES = ['remotive', 'remoteok', 'himalayas', 'jobicy', 'workingnomads', 'weworkremotely', 'arbeitnow', 'hackernews']
DEFAULTS = dict(preset='broad', adzuna=True, boards=PUBLIC_SOURCES, countries=['de', 'nl', 'gb'],
                keywords='', remote_only=True, eligibility='romania', contract_only=False,
                prefer_contract=True, max_age_days=30)


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
    for key in ('adzuna', 'remote_only', 'contract_only', 'prefer_contract'):
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
        item.update(score=score, matched=matched, sources=[item['source']])
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


class Engine:
    def __init__(self):
        self.lock = threading.Lock()
        self.runs = {}
        self.cache = {}

    def start(self, options):
        o = validate_options(options)
        with self.lock:
            for key, run in self.runs.items():
                if run['status'] == 'running':
                    if run['options'] == o:
                        return key
                    raise RuntimeError('A search is already running. Wait for it to finish.')
            run_id = secrets.token_hex(12)
            self.runs = {run_id: dict(status='running', options=o, jobs=[], sources=[], current='Starting search', fetched=0)}
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
        raw, statuses = [], []
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
                self.update(key, jobs=rank(raw, o), sources=copy.deepcopy(statuses), fetched=len(raw))
            self.update(key, status='complete', current='Search complete', updated_at=dt.datetime.now(dt.timezone.utc).isoformat())
        except Exception:
            self.update(key, status='error', current='Search failed. Please retry.')


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
            self.respond(200, {'status': 'ok', 'adzuna_configured': bool(os.environ.get('ADZUNA_APP_ID') and os.environ.get('ADZUNA_APP_KEY'))})
        elif path.startswith('/search/'):
            run = self.engine.get(path.rsplit('/', 1)[1])
            self.respond(200 if run else 404, run or {'error': 'Search expired. Start a new search.'})
        else:
            self.respond(404, {'error': 'Not found'})
    def do_POST(self):
        if not self.authorized():
            return
        if self.path != '/search':
            return self.respond(404, {'error': 'Not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError('Invalid request size.')
            self.connection.settimeout(10)
            options = json.loads(self.rfile.read(size))
            self.respond(202, {'id': self.engine.start(options)})
        except (ValueError, TypeError):
            self.respond(400, {'error': 'Invalid search options.'})
        except RuntimeError as exc:
            self.respond(409, {'error': str(exc)})


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

#!/usr/bin/env python3
"""Query the Adzuna job search API and rank the results against a backend CV.

Standard library only. Credentials come from ADZUNA_APP_ID and ADZUNA_APP_KEY
and are never printed, logged or written to a report.
"""

import argparse
import datetime
import html
import http.client
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://api.adzuna.com/v1/api/jobs"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "..", "config", "config.json")
DEFAULT_OUT_DIR = os.path.join(SCRIPT_DIR, "reports")
SEEN_FILE = os.path.join(SCRIPT_DIR, "seen.json")
SEEN_FIXTURE_FILE = os.path.join(SCRIPT_DIR, "seen.fixture.json")

REDACTED = "***"
MIN_REDACTED_LENGTH = 4
MAX_RESULTS_PER_PAGE = 50
DEFAULT_DELAY_SECONDS = 2.5
RATE_LIMIT_WAIT_SECONDS = 60
SERVER_ERROR_WAIT_SECONDS = 5
CREDENTIAL_STATUSES = (401, 403)
REMOTE_ORDER = ("yes", "unknown", "hybrid")
CURRENCY_SYMBOLS = {"EUR": "€", "GBP": "£", "USD": "$"}
ATTRIBUTION = "Jobs by [Adzuna](https://www.adzuna.com)."

MISSING_CREDENTIALS_MESSAGE = (
    "Missing Adzuna credentials.\n"
    "Register for a free key at https://developer.adzuna.com and set the two "
    "environment variables ADZUNA_APP_ID and ADZUNA_APP_KEY.\n"
    "(run.sh fills them from the ags secret store when they are unset.)\n"
    "Use --dry-run to preview the requests, or --fixture PATH to run offline."
)


class ConfigError(Exception):
    pass


class RequestFailed(Exception):
    def __init__(self, status, reason):
        super().__init__(reason)
        self.status = status
        self.reason = reason


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def load_config(path):
    try:
        with open(path, encoding="utf-8") as handle:
            config = json.load(handle)
    except OSError as exc:
        raise ConfigError("cannot read config %s (%s)" % (path, exc.strerror)) from None
    except ValueError as exc:
        raise ConfigError("config %s is not valid JSON: %s" % (path, exc)) from None
    validate_config(config)
    return config


def validate_config(config):
    if not isinstance(config, dict):
        raise ConfigError("config must be a JSON object")

    countries = config.get("countries")
    if not isinstance(countries, list) or not countries:
        raise ConfigError("config 'countries' must be a non-empty list")
    for country in countries:
        if not isinstance(country, str) or not re.fullmatch(r"[a-z]{2}", country):
            raise ConfigError("invalid country code %r (use two lowercase letters)" % (country,))

    if not isinstance(config.get("currencies", {}), dict):
        raise ConfigError("config 'currencies' must be an object")

    queries = config.get("queries")
    if not isinstance(queries, list) or not queries:
        raise ConfigError("config 'queries' must be a non-empty list")
    names = set()
    for query in queries:
        if not isinstance(query, dict) or not isinstance(query.get("name"), str) or not query["name"]:
            raise ConfigError("every query needs a non-empty 'name'")
        if query["name"] in names:
            raise ConfigError("duplicate query name %r" % query["name"])
        names.add(query["name"])
        if not isinstance(query.get("params"), dict):
            raise ConfigError("query %r needs a 'params' object" % query["name"])
        for forbidden in ("app_id", "app_key"):
            if forbidden in query["params"]:
                raise ConfigError("query %r must not contain %s; credentials come from the environment" % (query["name"], forbidden))
        pages = query.get("pages")
        if not isinstance(pages, int) or isinstance(pages, bool) or pages < 1:
            raise ConfigError("query %r needs 'pages' as an integer of at least 1" % query["name"])
        per_page = query["params"].get("results_per_page", MAX_RESULTS_PER_PAGE)
        if not isinstance(per_page, int) or not 1 <= per_page <= MAX_RESULTS_PER_PAGE:
            raise ConfigError("query %r: results_per_page must be 1 to %d" % (query["name"], MAX_RESULTS_PER_PAGE))

    for section in ("scoring", "remote"):
        if not isinstance(config.get(section), dict):
            raise ConfigError("config needs a '%s' object" % section)

    prefix = config.get("report_prefix", "")
    if not isinstance(prefix, str) or (prefix and not re.fullmatch(r"[a-z0-9-]+", prefix)):
        raise ConfigError("config 'report_prefix' must use lowercase letters, digits and hyphens")
    seen_file = config.get("seen_file", os.path.basename(SEEN_FILE))
    if not isinstance(seen_file, str) or not re.fullmatch(r"[A-Za-z0-9._-]+\.json", seen_file):
        raise ConfigError("config 'seen_file' must be a .json file name beside the script, not a path")


# --------------------------------------------------------------------------
# Text cleaning and term matching
# --------------------------------------------------------------------------

INLINE_TAG = re.compile(r"</?(?:strong|b|em|i|u|span|mark|small)\b[^>]*>", re.IGNORECASE)
ANY_TAG = re.compile(r"</?[A-Za-z][^>]*>")


def clean_text(value):
    """Strip HTML fragments and entities, normalise unicode and whitespace."""
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = INLINE_TAG.sub("", text)
    text = ANY_TAG.sub(" ", text)
    text = unicodedata.normalize("NFC", text)
    return re.sub(r"\s+", " ", text).strip()


def term_pattern(term):
    """Compile one term: case-insensitive, spaces and hyphens interchangeable.

    A word boundary is added on each side only when that edge of the term is a
    word character, so '.net' also matches 'ASP.NET' and 'c#' needs no trailing
    boundary, while 'java' cannot match 'javascript'.
    """
    text = unicodedata.normalize("NFC", term.strip())
    words = [re.escape(word) for word in re.split(r"[\s\-]+", text) if word]
    if not words:
        raise ConfigError("empty term in config")
    left = r"(?<!\w)" if re.match(r"\w", text) else ""
    right = r"(?!\w)" if re.search(r"\w$", text) else ""
    return re.compile(left + r"[\s\-]+".join(words) + right, re.IGNORECASE)


class TermGroup:
    """One concept written in several ways; counts once however many aliases match."""

    def __init__(self, entry):
        aliases = [entry] if isinstance(entry, str) else list(entry)
        if not aliases or not all(isinstance(alias, str) for alias in aliases):
            raise ConfigError("terms must be strings or lists of strings, got %r" % (entry,))
        self.label = aliases[0]
        self.patterns = [term_pattern(alias) for alias in aliases]

    def found_in(self, text):
        return any(pattern.search(text) for pattern in self.patterns)


class Scorer:
    def __init__(self, scoring):
        self.core_weight = scoring.get("core_weight", 3)
        self.secondary_weight = scoring.get("secondary_weight", 1)
        self.title_multiplier = scoring.get("title_multiplier", 2)
        self.penalty_points = scoring.get("penalty_points", 3)
        self.core = [TermGroup(entry) for entry in scoring.get("core_terms", [])]
        self.secondary = [TermGroup(entry) for entry in scoring.get("secondary_terms", [])]
        self.exclude = [TermGroup(entry) for entry in scoring.get("exclude_title_terms", [])]
        self.penalty = [TermGroup(entry) for entry in scoring.get("penalty_title_terms", [])]

    def excluded_by(self, title):
        for group in self.exclude:
            if group.found_in(title):
                return group.label
        return None

    def score(self, title, description):
        total = 0
        matched = {"core": [], "secondary": [], "title": [], "penalty": []}
        tiers = (
            ("core", self.core, self.core_weight),
            ("secondary", self.secondary, self.secondary_weight),
        )
        for tier, groups, weight in tiers:
            for group in groups:
                in_title = group.found_in(title)
                if not in_title and not group.found_in(description):
                    continue
                total += weight * (self.title_multiplier if in_title else 1)
                matched[tier].append(group.label)
                if in_title:
                    matched["title"].append(group.label)
        for group in self.penalty:
            if group.found_in(title):
                total -= self.penalty_points
                matched["penalty"].append(group.label)
        return total, matched


class RemoteLabeler:
    def __init__(self, remote):
        self.remote = [TermGroup(entry) for entry in remote.get("remote_terms", [])]
        self.hybrid = [TermGroup(entry) for entry in remote.get("hybrid_terms", [])]

    def label(self, title, description, location):
        text = " ".join(part for part in (title, description, location) if part)
        if any(group.found_in(text) for group in self.hybrid):
            return "hybrid"
        if any(group.found_in(text) for group in self.remote):
            return "yes"
        return "unknown"


# --------------------------------------------------------------------------
# Jobs: normalising, salary, dates
# --------------------------------------------------------------------------

def to_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def format_amount(value):
    if value >= 1000:
        return ("%.1f" % round(value / 1000, 1)).rstrip("0").rstrip(".") + "k"
    return str(int(round(value)))


def format_salary(minimum, maximum, predicted, currency):
    low, high = to_number(minimum), to_number(maximum)
    if low is None and high is None:
        return ""
    if low is not None and high is not None and low > high:
        low, high = high, low

    symbol = CURRENCY_SYMBOLS.get(currency)
    prefix = symbol if symbol else (currency + " " if currency else "")

    def money(value):
        return prefix + format_amount(value)

    if low is not None and high is not None:
        if format_amount(low) == format_amount(high):
            text = money(low)
        elif symbol:
            text = money(low) + "–" + money(high)
        else:
            text = prefix + format_amount(low) + "–" + format_amount(high)
    elif low is not None:
        text = money(low) + "+"
    else:
        text = "up to " + money(high)

    if is_predicted(predicted):
        text += " (est.)"
    return text


def is_predicted(value):
    return value is True or str(value).strip() == "1"


def parse_created(value):
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def posted_date(value):
    match = re.match(r"\d{4}-\d{2}-\d{2}", str(value or ""))
    return match.group(0) if match else ""


def dict_at(source, key):
    value = source.get(key) if isinstance(source, dict) else None
    return value if isinstance(value, dict) else {}


def normalize_job(raw, country, currency):
    """Flatten one Adzuna result. Returns None when it has no id."""
    if not isinstance(raw, dict):
        return None
    job_id = raw.get("id")
    if job_id is None or str(job_id).strip() == "":
        return None

    location = dict_at(raw, "location")
    area = location.get("area")
    area = [clean_text(part) for part in area] if isinstance(area, list) else []
    location_name = clean_text(location.get("display_name")) or ", ".join(reversed(area))

    created = raw.get("created")
    created = str(created).strip() if created else ""
    minimum = to_number(raw.get("salary_min"))
    maximum = to_number(raw.get("salary_max"))
    predicted = is_predicted(raw.get("salary_is_predicted"))

    return {
        "id": str(job_id).strip(),
        "title": clean_text(raw.get("title")),
        "company": clean_text(dict_at(raw, "company").get("display_name")),
        "location": location_name,
        "area": area,
        "country": country,
        "description": clean_text(raw.get("description")),
        "created": created,
        "posted": posted_date(created),
        "redirect_url": str(raw.get("redirect_url") or "").strip(),
        "salary_min": minimum,
        "salary_max": maximum,
        "salary_is_predicted": predicted,
        "currency": currency,
        "salary": format_salary(minimum, maximum, predicted, currency),
        "contract_type": clean_text(raw.get("contract_type")),
        "contract_time": clean_text(raw.get("contract_time")),
        "category": clean_text(dict_at(raw, "category").get("label")),
    }


def collect_jobs(results, scorer, labeler, currencies):
    """Dedupe by id, then drop excluded and non-positive jobs, score and label the rest.

    `results` is an iterable of (country, query name, raw result).
    """
    stats = {
        "results_fetched": 0,
        "skipped_no_id": 0,
        "unique_jobs": 0,
        "excluded_by_title": 0,
        "dropped_zero_score": 0,
    }
    unique = {}
    for country, query_name, raw in results:
        stats["results_fetched"] += 1
        job = normalize_job(raw, country, currencies.get(country, ""))
        if job is None:
            stats["skipped_no_id"] += 1
            continue
        source = "%s/%s" % (country, query_name)
        existing = unique.get(job["id"])
        if existing is not None:
            if source not in existing["found_in"]:
                existing["found_in"].append(source)
            continue
        job["found_in"] = [source]
        unique[job["id"]] = job
    stats["unique_jobs"] = len(unique)

    kept = []
    for job in unique.values():
        if scorer.excluded_by(job["title"]) is not None:
            stats["excluded_by_title"] += 1
            continue
        score, matched = scorer.score(job["title"], job["description"])
        if score <= 0:
            stats["dropped_zero_score"] += 1
            continue
        job["score"] = score
        job["matched_terms"] = matched
        job["remote"] = labeler.label(job["title"], job["description"], job["location"])
        kept.append(job)
    return kept, stats


def sort_jobs(jobs):
    """Remote yes, then unknown, then hybrid; score descending; newest first."""
    def key(job):
        created = parse_created(job.get("created"))
        timestamp = created.timestamp() if created else 0.0
        return (REMOTE_ORDER.index(job["remote"]), -job["score"], -timestamp)

    jobs.sort(key=key)
    return jobs


# --------------------------------------------------------------------------
# Seen jobs
# --------------------------------------------------------------------------

def load_seen(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        print("warning: %s is unreadable, starting with an empty seen list" % path, file=sys.stderr)
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def mark_new(jobs, seen, today):
    """Set first_seen and is_new on each job and record unseen ids in `seen`.

    A job first seen today stays NEW on a same-day rerun, so overwriting the
    day's report does not lose the flag.
    """
    for job in jobs:
        first_seen = seen.setdefault(job["id"], today)
        job["first_seen"] = first_seen
        job["is_new"] = first_seen == today


def save_seen(path, seen):
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(seen, handle, indent=1, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, path)


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------

def request_params(query):
    params = dict(query["params"])
    params.setdefault("results_per_page", MAX_RESULTS_PER_PAGE)
    return params


def build_url(country, page, params, credentials=None):
    """Build a search URL. With credentials=None the id and key are shown as ***."""
    if credentials:
        head = urllib.parse.urlencode([("app_id", credentials[0]), ("app_key", credentials[1])])
    else:
        head = "app_id=%s&app_key=%s" % (REDACTED, REDACTED)
    tail = urllib.parse.urlencode(list(params.items()) + [("content-type", "application/json")])
    return "%s/%s/search/%d?%s&%s" % (API_BASE, country, page, head, tail)


class LiveFetcher:
    def __init__(self, app_id, app_key, timeout=30):
        self._credentials = (app_id, app_key)
        self._timeout = timeout

    def __repr__(self):
        return "LiveFetcher()"

    def __call__(self, country, query, page):
        url = build_url(country, page, request_params(query), self._credentials)
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "personal-job-search/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise RequestFailed(status, "HTTP %d" % status) from None
        except urllib.error.URLError as exc:
            raise RequestFailed(None, "network error (%s)" % type(exc.reason).__name__) from None
        except (OSError, http.client.HTTPException) as exc:
            raise RequestFailed(None, "network error (%s)" % type(exc).__name__) from None
        try:
            data = json.loads(body)
        except ValueError:
            raise RequestFailed(None, "invalid JSON response") from None
        if not isinstance(data, dict):
            raise RequestFailed(None, "unexpected response shape")
        return data


class FixtureFetcher:
    """Serves {"<country>": {"<query name>": [page, ...]}} instead of calling the API."""

    def __init__(self, data):
        self._data = data

    def __call__(self, country, query, page):
        by_query = self._data.get(country, {})
        if isinstance(by_query, dict) and "error" in by_query:
            raise self._failure(by_query["error"])
        pages = by_query.get(query["name"], []) if isinstance(by_query, dict) else []
        if isinstance(pages, dict):
            pages = [pages]
        if not isinstance(pages, list) or page > len(pages):
            return {"count": 0, "results": []}
        data = pages[page - 1]
        if isinstance(data, dict) and "error" in data:
            raise self._failure(data["error"])
        return data

    @staticmethod
    def _failure(code):
        status = code if isinstance(code, int) else None
        return RequestFailed(status, "HTTP %s" % code)


def load_fixture(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise ConfigError("cannot read fixture %s (%s)" % (path, exc.strerror)) from None
    except ValueError as exc:
        raise ConfigError("fixture %s is not valid JSON: %s" % (path, exc)) from None
    if not isinstance(data, dict):
        raise ConfigError("fixture must be a JSON object keyed by country")
    return data


def extract_results(data):
    results = data.get("results") if isinstance(data, dict) else None
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


def run_search(config, fetch, delay=0.0, sleep=time.sleep, rate_limit_wait=RATE_LIMIT_WAIT_SECONDS,
               server_error_wait=SERVER_ERROR_WAIT_SECONDS):
    """Run every query for every country. A failed request never aborts the run.

    A rate limit (429) or a server error (5xx) is retried once after a wait.
    A rejected key (401/403) or a rate limit that survives the retry hits every
    remaining request alike, so the run stops querying and reports why.
    """
    outcome = {"results": [], "failures": [], "calls": 0, "successes": 0, "stopped": None}
    first_call = True

    for country in config["countries"]:
        for query in config["queries"]:
            per_page = request_params(query)["results_per_page"]
            for page in range(1, query["pages"] + 1):
                if delay and not first_call:
                    sleep(delay)
                first_call = False

                data, error = None, None
                for attempt in (1, 2):
                    outcome["calls"] += 1
                    try:
                        data, error = fetch(country, query, page), None
                    except RequestFailed as exc:
                        data, error = None, exc
                    if error is not None and error.status == 429 and attempt == 1:
                        sleep(rate_limit_wait)
                        continue
                    if error is not None and (error.status or 0) >= 500 and attempt == 1:
                        sleep(server_error_wait)
                        continue
                    break

                if error is not None:
                    outcome["failures"].append({
                        "country": country,
                        "query": query["name"],
                        "page": page,
                        "status": error.status,
                        "message": error.reason,
                    })
                    if error.status in CREDENTIAL_STATUSES:
                        outcome["stopped"] = "credentials rejected (%s); remaining requests were skipped" % error.reason
                        return outcome
                    if error.status == 429:
                        outcome["stopped"] = "rate limit hit (%s) after one retry; remaining requests were skipped" % error.reason
                        return outcome
                    break

                outcome["successes"] += 1
                items = extract_results(data)
                outcome["results"].extend((country, query["name"], item) for item in items)
                if len(items) < per_page:
                    break
    return outcome


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

def md_cell(value):
    return str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")


def md_link(url):
    if not url:
        return ""
    safe = url.replace(" ", "%20").replace("(", "%28").replace(")", "%29").replace("|", "%7C")
    return "[open](%s)" % safe


def describe_failure(failure):
    return "%s / %s (page %d): %s" % (failure["country"], failure["query"], failure["page"], failure["message"])


def render_markdown(report):
    summary = report["summary"]
    remote = summary["remote"]
    lines = [
        "# Job search report %s" % report["date"],
        "",
        "%d jobs kept (%d new). Remote: %d yes, %d unknown, %d hybrid or on-site. API calls used: %d%s."
        % (
            summary["jobs"],
            summary["new"],
            remote["yes"],
            remote["unknown"],
            remote["hybrid"],
            summary["api_calls"],
            " (fixture, no real requests)" if summary["fixture"] else "",
        ),
        "",
    ]

    if report["failed_requests"] or report["stopped_early"]:
        lines += ["## Failed requests", ""]
        lines += ["- " + describe_failure(failure) for failure in report["failed_requests"]]
        if report["stopped_early"]:
            lines.append("- Run stopped early: %s" % report["stopped_early"])
        lines.append("")

    titles = {"yes": "Remote: yes", "unknown": "Remote: unknown", "hybrid": "Hybrid or on-site"}
    for group in REMOTE_ORDER:
        members = [job for job in report["jobs"] if job["remote"] == group]
        if not members:
            continue
        lines += [
            "## %s (%d)" % (titles[group], len(members)),
            "",
            "| Score | New | Title | Company | Location | Salary | Posted | Link |",
            "|---:|:---:|---|---|---|---|---|---|",
        ]
        for job in members:
            cells = [
                str(job["score"]),
                "NEW" if job["is_new"] else "",
                md_cell(job["title"]),
                md_cell(job["company"]),
                md_cell(job["location"]),
                md_cell(job["salary"]),
                job["posted"],
                md_link(job["redirect_url"]),
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    if not report["jobs"]:
        lines += ["No matching jobs.", ""]

    lines.append(ATTRIBUTION)
    return "\n".join(lines) + "\n"


def build_report(jobs, outcome, stats, today, fixture_mode):
    remote_counts = {label: sum(1 for job in jobs if job["remote"] == label) for label in REMOTE_ORDER}
    return {
        "date": today,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "jobs": len(jobs),
            "new": sum(1 for job in jobs if job["is_new"]),
            "remote": remote_counts,
            "api_calls": outcome["calls"],
            "fixture": fixture_mode,
        },
        "stats": stats,
        "failed_requests": outcome["failures"],
        "stopped_early": outcome["stopped"],
        "jobs": jobs,
        "attribution": ATTRIBUTION,
    }


def redact(text, credentials):
    for secret in credentials or ():
        if secret and len(secret) >= MIN_REDACTED_LENGTH:
            text = text.replace(secret, REDACTED)
    return text


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="adzuna_search.py",
        description="Query the Adzuna job API and rank results against a backend engineer CV.",
        epilog="Credentials are read from ADZUNA_APP_ID and ADZUNA_APP_KEY. "
        "Register for free at https://developer.adzuna.com.",
    )
    parser.add_argument("--fixture", metavar="PATH", help="read responses from a JSON file instead of calling the API")
    parser.add_argument("--dry-run", action="store_true", help="print the requests that would be made (credentials redacted) and exit")
    parser.add_argument("--config", metavar="PATH", default=DEFAULT_CONFIG, help="settings file (default: config.json beside the script)")
    parser.add_argument("--out-dir", metavar="PATH", default=DEFAULT_OUT_DIR, help="report directory (default: reports/ beside the script)")
    parser.add_argument("--seen-file", metavar="PATH", help="override the seen-jobs file (default: seen.json, or seen.fixture.json with --fixture)")
    return parser.parse_args(argv)


def read_credentials():
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    return (app_id, app_key) if app_id and app_key else None


def print_dry_run(config):
    total = 0
    print("Dry run: no requests are made. Credentials are redacted.")
    for country in config["countries"]:
        for query in config["queries"]:
            params = request_params(query)
            for page in range(1, query["pages"] + 1):
                total += 1
                print("[%s/%s page %d] %s" % (country, query["name"], page, build_url(country, page, params)))
    print(
        "Total API calls: %d (upper bound; a query stops early when a page returns "
        "fewer than results_per_page results)" % total
    )


def main(argv=None):
    args = parse_args(argv)

    credentials = read_credentials()
    if not args.dry_run and not args.fixture and credentials is None:
        print(MISSING_CREDENTIALS_MESSAGE, file=sys.stderr)
        return 2

    try:
        config = load_config(args.config)
        scorer = Scorer(config["scoring"])
        labeler = RemoteLabeler(config["remote"])
        fixture = load_fixture(args.fixture) if args.fixture and not args.dry_run else None
    except ConfigError as exc:
        print("error: %s" % redact(str(exc), credentials), file=sys.stderr)
        return 2

    if args.dry_run:
        print_dry_run(config)
        return 0

    if fixture is not None:
        fetch = FixtureFetcher(fixture)
        delay = server_error_wait = 0.0
        seen_path = args.seen_file or SEEN_FIXTURE_FILE
    else:
        fetch = LiveFetcher(*credentials)
        delay = config.get("request_delay_seconds", DEFAULT_DELAY_SECONDS)
        server_error_wait = SERVER_ERROR_WAIT_SECONDS
        seen_path = args.seen_file or os.path.join(SCRIPT_DIR, config.get("seen_file", os.path.basename(SEEN_FILE)))

    today = datetime.date.today().isoformat()
    outcome = run_search(config, fetch, delay=delay, server_error_wait=server_error_wait)

    jobs, stats = collect_jobs(outcome["results"], scorer, labeler, config.get("currencies", {}))
    sort_jobs(jobs)
    seen = load_seen(seen_path)
    mark_new(jobs, seen, today)

    for failure in outcome["failures"]:
        failure["message"] = redact(failure["message"], credentials)
    if outcome["stopped"]:
        outcome["stopped"] = redact(outcome["stopped"], credentials)
    report = build_report(jobs, outcome, stats, today, fixture is not None)

    os.makedirs(args.out_dir, exist_ok=True)
    stem = "%s-%s" % (config["report_prefix"], today) if config.get("report_prefix") else today
    markdown_path = os.path.join(args.out_dir, stem + ".md")
    json_path = os.path.join(args.out_dir, stem + ".json")
    write_text(markdown_path, redact(render_markdown(report), credentials))
    write_text(json_path, redact(json.dumps(report, indent=2, ensure_ascii=False), credentials) + "\n")
    save_seen(seen_path, seen)

    summary = report["summary"]
    remote = summary["remote"]
    print("Jobs kept: %d (%d new). Remote: %d yes, %d unknown, %d hybrid or on-site. API calls used: %d."
          % (summary["jobs"], summary["new"], remote["yes"], remote["unknown"], remote["hybrid"], summary["api_calls"]))
    print("Dropped: %d excluded by title, %d with score <= 0." % (stats["excluded_by_title"], stats["dropped_zero_score"]))
    for failure in outcome["failures"]:
        print("Failed: " + describe_failure(failure))
    if outcome["stopped"]:
        print("Run stopped early: " + outcome["stopped"])
    print("Report: " + os.path.abspath(markdown_path))

    return 1 if outcome["failures"] and outcome["successes"] == 0 else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        creds = read_credentials()
        print("unexpected error: %s: %s" % (type(exc).__name__, redact(str(exc), creds)), file=sys.stderr)
        sys.exit(1)

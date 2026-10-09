#!/usr/bin/env python3
"""Search free remote-job APIs for contract Node.js / TypeScript backend roles.

Sources, none of which needs a key: Remotive, RemoteOK, Himalayas, Jobicy,
Working Nomads, We Work Remotely (RSS), Arbeitnow and the current Hacker News
"Who is hiring?" thread. Each job is scored with the CV terms in
remote_config.json, labelled contract / full-time / unknown, and labelled by
who may apply: worldwide, Europe, US/Americas only, other or unclear.

Standard library only. Shares text cleaning and scoring with adzuna_search.py.
"""

import argparse
import datetime
import email.utils
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from adzuna_search import TermGroup, Scorer, clean_text, md_cell, write_text

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.join(SCRIPT_DIR, "..", "config", "remote_config.json")
DEFAULT_OUT_DIR = os.path.join(SCRIPT_DIR, "reports")
SEEN_FILE = os.path.join(SCRIPT_DIR, "seen.remote.json")

USER_AGENT = "Mozilla/5.0 (personal job search script; stdlib urllib)"
TIMEOUT_SECONDS = 30
TYPE_ORDER = {"contract": 0, "contract?": 1, "unknown": 2, "full-time": 3}
OPEN_LABELS = ("worldwide", "europe")

# Description phrases that suggest, without stating it in a type field, that
# the role is a contract.
CONTRACT_HINTS = [
    TermGroup(entry) for entry in (
        ["independent contractor", "contractor role", "contractor position", "as a contractor"],
        ["contract role", "contract position", "contract basis", "contract engagement", "long-term contract"],
        ["freelance", "freelancer", "freelancing"],
        ["b2b contract", "b2b"],
        ["1099"],
        ["hourly rate", "per hour", "/hour", "/hr"],
    )
]
CONTRACT_STRONG = TermGroup(["contract", "contractor", "freelance", "freelancer", "b2b", "contract-to-hire"])
FULL_TIME_STRONG = TermGroup(["full-time", "full time", "fulltime", "full_time", "permanent"])


class ConfigError(Exception):
    pass


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Http:
    def __init__(self, delay):
        self.delay = delay
        self.last_call = 0.0
        self.calls = 0

    def get(self, url):
        wait = self.delay - (time.monotonic() - self.last_call)
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return response.read()
        finally:
            self.last_call = time.monotonic()
            self.calls += 1

    def json(self, url):
        return json.loads(self.get(url).decode("utf-8"))


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def iso_date(value):
    """Return YYYY-MM-DD from an ISO string, RFC 822 string or epoch seconds."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return datetime.datetime.fromtimestamp(value, datetime.timezone.utc).date().isoformat()
    text = str(value).strip()
    match = re.match(r"\d{4}-\d{2}-\d{2}", text)
    if match:
        return match.group(0)
    try:
        return email.utils.parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return ""


def money(minimum, maximum, currency="USD", period=""):
    def fmt(value):
        value = float(value)
        if value >= 1000:
            return ("%.1f" % (value / 1000)).rstrip("0").rstrip(".") + "k"
        return "%g" % value
    try:
        low = float(minimum) if minimum else 0
        high = float(maximum) if maximum else 0
    except (TypeError, ValueError):
        return ""
    if low <= 0 and high <= 0:
        return ""
    symbol = {"USD": "$", "EUR": "€", "GBP": "£"}.get((currency or "").upper(), (currency or "") + " ")
    span = fmt(low or high) if not (low and high) or low == high else "%s–%s" % (fmt(low), fmt(high))
    suffix = {"hourly": "/h", "hour": "/h", "yearly": "/yr", "annual": "/yr", "monthly": "/mo", "month": "/mo"}.get((period or "").lower(), "")
    return symbol + span + suffix


def job(source, source_id, title, company, url, location="", restrictions=None, type_field="",
        salary="", posted="", tags=None, description="", industry="", board=False):
    """One normalised job. `industry` is set when the source only lists one
    industry (a studio's own job board); `board` marks a company job board,
    which lists only open roles, so its jobs skip the age check."""
    return {
        "source": source,
        "id": "%s:%s" % (source, source_id),
        "title": clean_text(title),
        "company": clean_text(company),
        "url": url or "",
        "location": clean_text(location),
        "restrictions": restrictions,
        "type_field": clean_text(type_field),
        "salary": salary or "",
        "posted": posted or "",
        "tags": [clean_text(tag) for tag in (tags or []) if tag],
        "description": clean_text(description),
        "industry": industry,
        "board": board,
    }


def parse_rss(body, feed):
    if b"<!ENTITY" in body:
        raise ValueError("feed %s declares XML entities; refusing to parse" % feed)
    return ET.fromstring(body)


# --------------------------------------------------------------------------
# Sources. Each returns a list of normalised jobs and may raise on failure.
# --------------------------------------------------------------------------

def fetch_remotive(http, options):
    jobs = []
    for category in options.get("categories", ["software-dev"]):
        data = http.json("https://remotive.com/api/remote-jobs?" + urllib.parse.urlencode({"category": category}))
        for raw in data.get("jobs", []):
            jobs.append(job(
                "remotive", raw.get("id"), raw.get("title"), raw.get("company_name"), raw.get("url"),
                location=raw.get("candidate_required_location"), type_field=raw.get("job_type", "").replace("_", "-"),
                salary=clean_text(raw.get("salary")), posted=iso_date(raw.get("publication_date")),
                tags=raw.get("tags"), description=raw.get("description"),
            ))
    return jobs


def fetch_remoteok(http, options):
    jobs = []
    for tag in options.get("tags", []):
        data = http.json("https://remoteok.com/api?" + urllib.parse.urlencode({"tag": tag}))
        for raw in data:
            if not isinstance(raw, dict) or "position" not in raw:
                continue  # the first element is the legal notice
            jobs.append(job(
                "remoteok", raw.get("id"), raw.get("position"), raw.get("company"), raw.get("url"),
                location=raw.get("location"), salary=money(raw.get("salary_min"), raw.get("salary_max"), "USD", "yearly"),
                posted=iso_date(raw.get("date") or raw.get("epoch")), tags=raw.get("tags"),
                description=raw.get("description"),
            ))
    return jobs


def fetch_himalayas(http, options):
    jobs = []
    plans = []
    for query in options.get("queries", []):
        plans.append((query, "Contractor", options.get("contractor_pages", 2)))
        plans.append((query, None, options.get("any_type_pages", 1)))
    for query, employment_type, pages in plans:
        for page in range(1, pages + 1):
            params = {"q": query, "page": page, "sort": "recent"}
            if employment_type:
                params["employment_type"] = employment_type
            data = http.json("https://himalayas.app/jobs/api/search?" + urllib.parse.urlencode(params))
            batch = data.get("jobs") or []
            jobs += [himalayas_job(raw) for raw in batch]
            if len(batch) < (data.get("limit") or 20):
                break
    return jobs


def himalayas_location(restrictions):
    if not restrictions:
        return "Worldwide"
    if len(restrictions) <= 6:
        return ", ".join(restrictions)
    romania = "incl. Romania" if "Romania" in restrictions else "not Romania"
    return "%d countries, %s" % (len(restrictions), romania)


def himalayas_job(raw):
    restrictions = raw.get("locationRestrictions") or []
    return job(
        "himalayas", raw.get("guid") or raw.get("applicationLink"), raw.get("title"), raw.get("companyName"),
        raw.get("applicationLink") or raw.get("guid"),
        location=himalayas_location(restrictions), restrictions=restrictions, type_field=raw.get("employmentType"),
        salary=money(raw.get("minSalary"), raw.get("maxSalary"), raw.get("currency"), raw.get("salaryPeriod")),
        posted=iso_date(raw.get("pubDate")), tags=raw.get("categories"),
        description=raw.get("description") or raw.get("excerpt"),
    )


def fetch_jobicy(http, options):
    jobs = []
    for tag in options.get("tags", []):
        params = {"count": options.get("count", 50), "tag": tag}
        data = http.json("https://jobicy.com/api/v2/remote-jobs?" + urllib.parse.urlencode(params))
        for raw in data.get("jobs", []):
            jobs.append(job(
                "jobicy", raw.get("id"), raw.get("jobTitle"), raw.get("companyName"), raw.get("url"),
                location=raw.get("jobGeo"), type_field=", ".join(raw.get("jobType") or []),
                salary=money(raw.get("salaryMin"), raw.get("salaryMax"), raw.get("salaryCurrency"), raw.get("salaryPeriod")),
                posted=iso_date(raw.get("pubDate")), tags=raw.get("jobIndustry"),
                description=raw.get("jobDescription") or raw.get("jobExcerpt"),
            ))
    return jobs


def fetch_workingnomads(http, options):
    jobs = []
    for raw in http.json("https://www.workingnomads.com/api/exposed_jobs/"):
        jobs.append(job(
            "workingnomads", raw.get("url"), raw.get("title"), raw.get("company_name"), raw.get("url"),
            location=raw.get("location"), posted=iso_date(raw.get("pub_date")),
            tags=(raw.get("tags") or "").split(","), description=raw.get("description"),
        ))
    return jobs


def fetch_weworkremotely(http, options):
    jobs = []
    for feed in options.get("feeds", []):
        root = parse_rss(http.get(feed), feed)
        for item in root.iter("item"):
            def text(tag):
                node = item.find(tag)
                return node.text if node is not None and node.text else ""
            company, _, title = text("title").partition(": ")
            if not title:
                company, title = "", company
            location = text("region")
            countries = text("country")
            if countries and "romania" in countries.lower():
                location = (location + "; incl. Romania").strip("; ")
            jobs.append(job(
                "weworkremotely", text("guid") or text("link"), title, company, text("link"),
                location=location, type_field=text("type"), posted=iso_date(text("pubDate")),
                tags=text("skills").split(", "), description=text("description"),
            ))
    return jobs


def fetch_arbeitnow(http, options):
    jobs = []
    for page in range(1, options.get("pages", 2) + 1):
        data = http.json("https://www.arbeitnow.com/api/job-board-api?page=%d" % page)
        for raw in data.get("data", []):
            if not raw.get("remote"):
                continue
            location = raw.get("location") or ""
            jobs.append(job(
                "arbeitnow", raw.get("slug"), raw.get("title"), raw.get("company_name"), raw.get("url"),
                location=("Remote, %s" % location) if location else "Remote",
                type_field=", ".join(raw.get("job_types") or []), posted=iso_date(raw.get("created_at")),
                tags=raw.get("tags"), description=raw.get("description"),
            ))
        if not (data.get("links") or {}).get("next"):
            break
    return jobs


def fetch_hackernews(http, options):
    search = http.json(
        "https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring&hitsPerPage=10"
    )
    story = next((hit for hit in search.get("hits", []) if "who is hiring" in hit.get("title", "").lower()), None)
    if story is None:
        raise RuntimeError("no 'Who is hiring?' thread found")
    thread = http.json("https://hn.algolia.com/api/v1/items/%s" % story["objectID"])
    jobs = []
    for comment in thread.get("children", []):
        body = comment.get("text") or ""
        if not body:
            continue
        first_line = clean_text(re.split(r"<p>|\n", body, maxsplit=1)[0])
        if "remote" not in first_line.lower():
            continue
        parts = [part.strip() for part in first_line.split("|") if part.strip()]
        company = parts[0] if parts else ""
        rest = parts[1:]
        role = next((part for part in rest if re.search(r"engineer|developer|programmer|backend|full.?stack|software", part, re.I)), "")
        location = "; ".join(part for part in rest if re.search(r"remote|onsite|on-site|hybrid|\b[A-Z]{2,}\b|,", part) and part != role)
        type_field = "; ".join(part for part in rest if re.search(r"contract|freelance|full.?time|part.?time|intern", part, re.I))
        jobs.append(job(
            "hackernews", comment.get("id"), role or first_line[:120], company,
            "https://news.ycombinator.com/item?id=%s" % comment.get("id"),
            location=location or first_line[:160], type_field=type_field,
            posted=iso_date(comment.get("created_at")), description=body,
        ))
    return jobs


# --------------------------------------------------------------------------
# Company job boards. Each option is {"boards": {slug: company name},
# "industry": "..."}; only fully remote roles are kept, and one board failing
# (a renamed slug, a rate limit) does not stop the others.
# --------------------------------------------------------------------------

FETCH_ERRORS = (urllib.error.URLError, OSError, ValueError, KeyError, TypeError, ET.ParseError)
REMOTE_WORD = re.compile(r"\bremote\b", re.IGNORECASE)


def each_board(name, options, fetch_one):
    jobs = []
    for slug, company in (options.get("boards") or {}).items():
        try:
            jobs += fetch_one(slug, company, options.get("industry", ""))
        except FETCH_ERRORS as exc:
            if "_failures" in options:
                options["_failures"].append(f"{name}/{slug}: {type(exc).__name__}")
            else:
                print("%-15s %s failed: %s" % (name, slug, exc), file=sys.stderr)
    return jobs


def fetch_greenhouse(http, options):
    def one(slug, company, industry):
        data = http.json("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true" % slug)
        jobs = []
        for raw in data.get("jobs", []):
            places = [raw.get("location", {}).get("name", "")] + [o.get("name", "") for o in raw.get("offices") or []]
            location = "; ".join(dict.fromkeys(p for p in places if p))
            if not REMOTE_WORD.search(location):
                continue
            jobs.append(job(
                "greenhouse", raw.get("id"), raw.get("title"), raw.get("company_name") or company,
                raw.get("absolute_url"), location=location,
                posted=iso_date(raw.get("first_published") or raw.get("updated_at")),
                description=raw.get("content"), industry=industry, board=True,
            ))
        return jobs
    return each_board("greenhouse", options, one)


def fetch_lever(http, options):
    def one(slug, company, industry):
        jobs = []
        for raw in http.json("https://api.lever.co/v0/postings/%s?mode=json" % slug):
            categories = raw.get("categories") or {}
            location = ", ".join(categories.get("allLocations") or [categories.get("location") or ""])
            if raw.get("workplaceType") != "remote" and not REMOTE_WORD.search(location):
                continue
            lists = " ".join("%s %s" % (part.get("text", ""), part.get("content", "")) for part in raw.get("lists") or [])
            salary = raw.get("salaryRange") or {}
            jobs.append(job(
                "lever", raw.get("id"), raw.get("text"), company, raw.get("hostedUrl"),
                location="Remote: " + location if not REMOTE_WORD.search(location) else location,
                type_field=categories.get("commitment", ""),
                salary=money(salary.get("min"), salary.get("max"), salary.get("currency"), salary.get("interval")),
                posted=iso_date((raw.get("createdAt") or 0) / 1000),
                description=" ".join([raw.get("descriptionPlain") or "", lists, raw.get("additionalPlain") or ""]),
                industry=industry, board=True,
            ))
        return jobs
    return each_board("lever", options, one)


def fetch_ashby(http, options):
    def one(slug, company, industry):
        data = http.json("https://api.ashbyhq.com/posting-api/job-board/%s?includeCompensation=true" % slug)
        jobs = []
        for raw in data.get("jobs", []):
            if not (raw.get("isRemote") or raw.get("workplaceType") == "Remote"):
                continue
            places = [raw.get("location") or ""] + [p.get("location", "") for p in raw.get("secondaryLocations") or []]
            location = ", ".join(p for p in places if p)
            pay = (raw.get("compensation") or {}).get("scrapeableCompensationSalarySummary") or ""
            jobs.append(job(
                "ashby", raw.get("id"), raw.get("title"), company, raw.get("jobUrl"),
                location="Remote: " + location if not REMOTE_WORD.search(location) else location,
                type_field=raw.get("employmentType", ""), salary=pay, posted=iso_date(raw.get("publishedAt")),
                description=raw.get("descriptionPlain"), industry=industry, board=True,
            ))
        return jobs
    return each_board("ashby", options, one)


def fetch_smartrecruiters(http, options):
    """Lists postings page by page, then fetches the description of each remote one."""
    def one(slug, company, industry):
        jobs, offset = [], 0
        while True:
            data = http.json("https://api.smartrecruiters.com/v1/companies/%s/postings?limit=100&offset=%d" % (slug, offset))
            page = data.get("content") or []
            for raw in page:
                place = raw.get("location") or {}
                if not (place.get("remote") or place.get("fullyRemote")):
                    continue
                detail = http.json(raw["ref"])
                sections = ((detail.get("jobAd") or {}).get("sections") or {}).values()
                jobs.append(job(
                    "smartrecruiters", raw.get("id"), raw.get("name"), (raw.get("company") or {}).get("name") or company,
                    detail.get("postingUrl") or "https://jobs.smartrecruiters.com/%s/%s" % (slug, raw.get("id")),
                    location="Remote: " + (place.get("fullLocation") or place.get("country") or ""),
                    type_field=(raw.get("typeOfEmployment") or {}).get("label", ""),
                    posted=iso_date(raw.get("releasedDate")),
                    description=" ".join(section.get("text", "") for section in sections if isinstance(section, dict)),
                    industry=industry, board=True,
                ))
            offset += len(page)
            if not page or offset >= data.get("totalFound", 0):
                return jobs
    return each_board("smartrecruiters", options, one)


def fetch_workable(http, options):
    def one(slug, company, industry):
        data = http.json("https://apply.workable.com/api/v1/widget/accounts/%s?details=true" % slug)
        jobs = []
        for raw in data.get("jobs", []):
            if not raw.get("telecommuting"):
                continue
            place = ", ".join(p for p in (raw.get("city"), raw.get("country")) if p)
            jobs.append(job(
                "workable", raw.get("shortcode"), raw.get("title"), data.get("name") or company,
                raw.get("url") or raw.get("shortlink"), location="Remote: " + place,
                type_field=raw.get("employment_type", ""), posted=iso_date(raw.get("published_on")),
                description=raw.get("description"), industry=industry, board=True,
            ))
        return jobs
    return each_board("workable", options, one)


def fetch_teamtailor(http, options):
    namespace = {"tt": "https://teamtailor.com/locations"}

    def one(slug, company, industry):
        feed = "https://%s.teamtailor.com/jobs.rss" % slug
        jobs = []
        for item in parse_rss(http.get(feed), feed).iter("item"):
            if (item.findtext("remoteStatus") or "").strip() != "fully":
                continue
            places = [node.text for node in item.findall("tt:locations/tt:location/tt:country", namespace) if node.text]
            jobs.append(job(
                "teamtailor", item.findtext("guid") or item.findtext("link"), item.findtext("title"), company,
                item.findtext("link"), location="Remote: " + ", ".join(dict.fromkeys(places)),
                posted=iso_date(item.findtext("pubDate")), description=item.findtext("description"),
                industry=industry, board=True,
            ))
        return jobs
    return each_board("teamtailor", options, one)


SOURCES = {
    "remotive": fetch_remotive,
    "remoteok": fetch_remoteok,
    "himalayas": fetch_himalayas,
    "jobicy": fetch_jobicy,
    "workingnomads": fetch_workingnomads,
    "weworkremotely": fetch_weworkremotely,
    "arbeitnow": fetch_arbeitnow,
    "hackernews": fetch_hackernews,
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "workable": fetch_workable,
    "teamtailor": fetch_teamtailor,
}


# --------------------------------------------------------------------------
# Labelling
# --------------------------------------------------------------------------

class LocationLabeler:
    def __init__(self, location):
        self.worldwide = [TermGroup(entry) for entry in location.get("worldwide_terms", [])]
        self.europe = [TermGroup(entry) for entry in location.get("europe_terms", [])]
        self.us = [TermGroup(entry) for entry in location.get("us_terms", [])]
        # Other European countries and cities: remote, but tied to a country
        # that is not Romania. Labelled "europe-other" so it can be asked about.
        self.europe_other = [TermGroup(entry) for entry in location.get("europe_country_terms", [])]

    def europe_other_or(self, names_or_text, fallback):
        text = names_or_text if isinstance(names_or_text, str) else ", ".join(names_or_text)
        return "europe-other" if any(group.found_in(text) for group in self.europe_other) else fallback

    def label(self, item):
        restrictions = item.get("restrictions")
        if restrictions is not None:  # Himalayas gives an explicit country list
            names = {name.lower() for name in restrictions}
            if not names:
                return "worldwide"
            if "romania" in names:
                return "worldwide" if len(names) >= 25 else "europe"
            if names <= {"united states", "canada", "puerto rico"}:
                return "us"
            return self.europe_other_or(restrictions, "other")
        text = item["location"]
        if not text:
            return "unclear"
        if any(group.found_in(text) for group in self.worldwide):
            return "worldwide"
        if any(group.found_in(text) for group in self.europe):
            return "europe"
        if any(group.found_in(text) for group in self.us):
            return "us"
        if re.fullmatch(r"(?i)\s*remote\s*[.!]?\s*", text):
            return "unclear"
        return self.europe_other_or(text, "other")


def employment(item):
    type_text = item["type_field"]
    if CONTRACT_STRONG.found_in(type_text) or CONTRACT_STRONG.found_in(item["title"]):
        return "contract"
    if item["source"] == "hackernews" and CONTRACT_STRONG.found_in(item["location"]):
        return "contract"
    if any(group.found_in(item["description"]) for group in CONTRACT_HINTS):
        return "contract?"
    if FULL_TIME_STRONG.found_in(type_text):
        return "full-time"
    return "unknown"


def dedupe_key(item):
    def norm(text):
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
    return norm(item["company"]) + "|" + norm(item["title"])


class IndustryFilter:
    """Keeps only jobs in one industry, from config["industry"].

    A job passes when its source lists a single industry (a studio's job
    board), when a `match_terms` entry is in its title, company or tags, when
    at least `min_text_groups` different `text_terms` entries are in its
    description (one generic listing can name a single games stack among
    dozens of others), or when `count_pattern`
    matches the description at least `min_count` times. Any
    `exclude_text_terms` entry anywhere drops it.
    """

    def __init__(self, industry):
        self.name = industry.get("name", "")
        self.match = [TermGroup(entry) for entry in industry.get("match_terms", [])]
        self.text = [TermGroup(entry) for entry in industry.get("text_terms", [])]
        self.exclude = [TermGroup(entry) for entry in industry.get("exclude_text_terms", [])]
        pattern = industry.get("count_pattern")
        self.count_pattern = re.compile(pattern, re.IGNORECASE) if pattern else None
        self.min_count = industry.get("min_count", 3)
        self.min_text_groups = industry.get("min_text_groups", 1)

    def allows(self, item):
        head = " ".join([item["title"], item["company"], " ".join(item["tags"])])
        everything = head + " " + item["description"]
        if any(group.found_in(everything) for group in self.exclude):
            return False
        if self.name and item.get("industry") == self.name:
            return True
        if any(group.found_in(head) for group in self.match):
            return True
        if sum(1 for group in self.text if group.found_in(item["description"])) >= self.min_text_groups:
            return True
        return bool(self.count_pattern) and len(self.count_pattern.findall(item["description"])) >= self.min_count


def label_jobs(raw_jobs, config, today):
    scorer = Scorer(config["scoring"])
    locator = LocationLabeler(config.get("location", {}))
    oldest = (today - datetime.timedelta(days=config.get("max_age_days", 30))).isoformat()
    min_score = config.get("min_score", 1)
    require_core = config.get("require_core", True)
    industry = IndustryFilter(config["industry"]) if config.get("industry") else None
    kept, by_key = [], {}
    dropped = {"duplicate": 0, "excluded": 0, "old": 0, "low score": 0}
    if industry:
        dropped["other industry"] = 0
    for item in raw_jobs:
        key = dedupe_key(item)
        if key in by_key:
            other = by_key[key]
            if item["source"] not in other["sources"]:
                other["sources"].append(item["source"])
            dropped["duplicate"] += 1
            continue
        if scorer.excluded_by(item["title"]):
            dropped["excluded"] += 1
            continue
        if item["posted"] and item["posted"] < oldest and not item.get("board"):
            dropped["old"] += 1
            continue
        if industry and not industry.allows(item):
            dropped["other industry"] += 1
            continue
        text = " ".join([item["description"], " ".join(item["tags"])])
        score, matched = scorer.score(item["title"], text)
        if score < min_score or (require_core and not matched["core"]):
            dropped["low score"] += 1
            continue
        item.update(score=score, matched=matched, sources=[item["source"]],
                    type=employment(item), eligibility=locator.label(item))
        by_key[key] = item
        kept.append(item)
    return kept, dropped


def sort_jobs(rows):
    """Contract first, then higher score, then newer."""
    rows.sort(key=lambda item: item["posted"], reverse=True)
    rows.sort(key=lambda item: (TYPE_ORDER[item["type"]], -item["score"]))


# --------------------------------------------------------------------------
# Seen file and report
# --------------------------------------------------------------------------

def load_seen(path):
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def render_markdown(groups, limits, stats, failures, today, title="Remote contract search"):
    lines = ["# %s %s" % (title, today), ""]
    lines.append(
        "%d jobs kept from %d fetched (%d API calls). Open to a Romania-based candidate: %d. "
        "Other European countries: %d. US/Americas only: %d. Location unclear: %d."
        % (stats["kept"], stats["fetched"], stats["calls"], len(groups["open"]), len(groups["europe-other"]),
           len(groups["us"]), len(groups["unclear"]))
    )
    lines.append("")
    lines.append("Type: `contract` comes from the source's type field or the title. `contract?` means the description "
                 "mentions contractor, freelance, B2B or hourly pay. Within a section, contract roles come first, then higher score, then newer.")
    lines.append("")
    titles = {
        "open": "Open to Romania (worldwide or Europe)",
        "europe-other": "Remote in other European countries (Romania not listed; worth asking)",
        "us": "US / Americas only (usually needs US residency or work authorisation)",
        "unclear": "Remote, but the location rule is unclear",
    }
    for name in ("open", "europe-other", "us", "unclear"):
        rows = groups[name]
        if name == "europe-other" and not rows:
            continue
        limit = limits.get(name, 50)
        lines += ["## %s (%d)" % (titles[name], len(rows)), ""]
        if not rows:
            lines += ["None.", ""]
            continue
        lines.append("| Score | New | Type | Title | Company | Who can apply | Salary | Posted | Source |")
        lines.append("|---:|:---:|---|---|---|---|---|---|---|")
        for item in rows[:limit]:
            lines.append("| %d | %s | %s | [%s](%s) | %s | %s | %s | %s | %s |" % (
                item["score"], "NEW" if item.get("new") else "", item["type"], md_cell(item["title"]), item["url"],
                md_cell(item["company"]), md_cell(item["location"][:70]), md_cell(item["salary"]), item["posted"],
                ", ".join(item["sources"]),
            ))
        if len(rows) > limit:
            lines.append("")
            lines.append("%d more in the JSON report." % (len(rows) - limit))
        lines.append("")
    if failures:
        lines += ["## Failed sources", ""]
        lines += ["- %s: %s" % (name, reason) for name, reason in failures]
        lines.append("")
    lines.append("Dropped: " + ", ".join("%d %s" % (count, reason) for reason, count in stats["dropped"].items()) + ".")
    lines.append("")
    lines.append("Sources: [Remotive](https://remotive.com), [Remote OK](https://remoteok.com), "
                 "[Himalayas](https://himalayas.app), [Jobicy](https://jobicy.com), "
                 "[Working Nomads](https://www.workingnomads.com), [We Work Remotely](https://weworkremotely.com), "
                 "[Arbeitnow](https://www.arbeitnow.com), [Hacker News Who is hiring](https://news.ycombinator.com), "
                 "and company job boards through the public Greenhouse, Lever, Ashby, SmartRecruiters, Workable "
                 "and Teamtailor APIs, as configured.")
    lines.append("")
    return "\n".join(lines)


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--seen-file", help="default: the config's seen_file, else seen.remote.json")
    parser.add_argument("--only", help="comma-separated source names to query")
    parser.add_argument("--save-raw", metavar="PATH", help="also write every fetched job, before filtering, to PATH")
    parser.add_argument("--from-raw", metavar="PATH", help="relabel jobs saved by --save-raw instead of fetching")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        with open(args.config, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, ValueError) as exc:
        print("bad config %s: %s" % (args.config, exc), file=sys.stderr)
        return 2

    wanted = args.only.split(",") if args.only else list(config.get("sources", SOURCES))
    http = Http(config.get("request_delay_seconds", 1.0))
    raw_jobs, failures = [], []
    if args.from_raw:
        with open(args.from_raw, encoding="utf-8") as handle:
            raw_jobs = json.load(handle)
        wanted = []
    for name in wanted:
        fetch = SOURCES.get(name)
        if fetch is None:
            failures.append((name, "unknown source"))
            continue
        try:
            found = fetch(http, config.get("sources", {}).get(name) or {})
        except (urllib.error.URLError, OSError, ValueError, ET.ParseError, RuntimeError) as exc:
            failures.append((name, str(exc)[:200]))
            print("%-15s failed: %s" % (name, exc), file=sys.stderr)
            continue
        print("%-15s %4d jobs" % (name, len(found)), file=sys.stderr)
        raw_jobs += found

    if not raw_jobs:
        print("every source failed", file=sys.stderr)
        return 1
    if args.save_raw:
        write_text(args.save_raw, json.dumps(raw_jobs) + "\n")

    today = datetime.date.today()
    kept, dropped = label_jobs(raw_jobs, config, today)

    seen_file = args.seen_file or os.path.join(SCRIPT_DIR, config.get("seen_file", os.path.basename(SEEN_FILE)))
    seen = load_seen(seen_file)
    for item in kept:
        first = seen.setdefault(item["id"], today.isoformat())
        item["new"] = first == today.isoformat()
    write_text(seen_file, json.dumps(dict(sorted(seen.items())), indent=1) + "\n")

    groups = {"open": [], "europe-other": [], "us": [], "unclear": [], "other": []}
    for item in kept:
        groups["open" if item["eligibility"] in OPEN_LABELS else item["eligibility"]].append(item)
    for rows in groups.values():
        sort_jobs(rows)

    stats = {"kept": len(kept) - len(groups["other"]), "fetched": len(raw_jobs), "calls": http.calls,
             "dropped": dict(dropped, **{"other region (in JSON only)": len(groups["other"])})}
    stamp = today.isoformat()
    markdown = render_markdown(groups, config.get("report_limits", {}), stats, failures, stamp,
                               config.get("report_title", "Remote contract search"))
    prefix = config.get("report_prefix", "remote")
    os.makedirs(args.out_dir, exist_ok=True)
    md_path = os.path.join(args.out_dir, "%s-%s.md" % (prefix, stamp))
    json_path = os.path.join(args.out_dir, "%s-%s.json" % (prefix, stamp))
    write_text(md_path, markdown)
    for rows in groups.values():
        for item in rows:
            item["description"] = item["description"][:4000]
    write_text(json_path, json.dumps({"date": stamp, "stats": stats, "failures": failures, "groups": groups}, indent=1) + "\n")
    print("wrote %s and %s" % (md_path, json_path), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

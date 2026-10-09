import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

import adzuna_search as aj  # noqa: E402

CONFIG_PATH = os.path.join(ROOT, "config", "config.json")
FIXTURE_PATH = os.path.join(TESTS_DIR, "fixture.json")
SCRIPT_PATH = os.path.join(ROOT, "vendor", "adzuna_search.py")
FAKE_ID = "TESTID123"
FAKE_KEY = "TESTKEY456"


def real_config():
    return aj.load_config(CONFIG_PATH)


def scorer_and_labeler():
    config = real_config()
    return aj.Scorer(config["scoring"]), aj.RemoteLabeler(config["remote"])


def make_job(job_id, score, remote="yes", created="2026-10-01T00:00:00Z"):
    return {"id": job_id, "score": score, "remote": remote, "created": created}


def run_main(argv, env=None):
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        if env is None:
            code = aj.main(argv)
        else:
            with mock.patch.dict(os.environ, env):
                code = aj.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def env_without_adzuna():
    return {key: value for key, value in os.environ.items() if not key.startswith("ADZUNA_")}


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.scorer, _ = scorer_and_labeler()

    def test_core_term_weighs_three_and_secondary_one(self):
        self.assertEqual(self.scorer.score("Engineer", "We use Node.js")[0], 3)
        self.assertEqual(self.scorer.score("Engineer", "We use Redis")[0], 1)
        self.assertEqual(self.scorer.score("Engineer", "TypeScript and NestJS")[0], 6)

    def test_term_in_title_counts_double(self):
        self.assertEqual(self.scorer.score("TypeScript Engineer", "")[0], 6)
        self.assertEqual(self.scorer.score("Redis Engineer", "")[0], 2)

    def test_term_in_title_and_description_is_not_counted_three_times(self):
        self.assertEqual(self.scorer.score("TypeScript Engineer", "typescript everywhere")[0], 6)

    def test_aliases_of_one_term_count_once(self):
        score, matched = self.scorer.score("Engineer", "Node.js, nodejs and node js")
        self.assertEqual(score, 3)
        self.assertEqual(matched["core"], ["node.js"])

    def test_node_js_spellings(self):
        for text in ("Node.js", "NodeJS", "node js", "Node.JS", "node-js", "(Node.js)", "Node.js.", "Node"):
            self.assertEqual(self.scorer.score("Engineer", text)[0], 3, text)
        for text in ("nodejsx", "anode.js", "cluster nodes"):
            self.assertEqual(self.scorer.score("Engineer", text)[0], 0, text)

    def test_secondary_terms_need_whole_words(self):
        self.assertEqual(self.scorer.score("Engineer", "expressive writing")[0], 0)
        self.assertEqual(self.scorer.score("Engineer", "gamer culture")[0], 0)
        self.assertEqual(self.scorer.score("Engineer", "Express and MySQL")[0], 2)

    def test_backend_spellings_count_once(self):
        for text in ("backend", "back-end", "back end", "Back End"):
            self.assertEqual(self.scorer.score("Engineer", text)[0], 1, text)

    def test_java_penalty_does_not_hit_javascript(self):
        score, matched = self.scorer.score("Senior JavaScript Engineer", "TypeScript on Express")
        self.assertEqual(matched["penalty"], [])
        self.assertEqual(score, 4)

    def test_java_penalty_applies_to_java(self):
        score, matched = self.scorer.score("Java Backend Engineer", "Node.js is a plus")
        self.assertEqual(matched["penalty"], ["java"])
        self.assertEqual(score, 2 + 3 - 3)
        self.assertEqual(self.scorer.score("Java/Kotlin Developer", "")[1]["penalty"], ["java"])

    def test_dotnet_and_csharp_penalties(self):
        _, matched = self.scorer.score("C# .NET Developer", "")
        self.assertEqual(matched["penalty"], [".net", "c#"])
        self.assertEqual(self.scorer.score("ASP.NET Developer", "")[1]["penalty"], [".net"])
        self.assertEqual(self.scorer.score("Senior C# Engineer", "")[1]["penalty"], ["c#"])
        self.assertEqual(self.scorer.score("C#/.NET", "")[1]["penalty"], [".net", "c#"])

    def test_dotnet_and_csharp_do_not_overmatch(self):
        for title in ("Network Engineer", "Node.js Developer", "C++ Developer", "ABC# Engineer", "Netz Engineer"):
            _, matched = self.scorer.score(title, "")
            self.assertNotIn(".net", matched["penalty"], title)
            self.assertNotIn("c#", matched["penalty"], title)

    def test_penalties_apply_to_the_title_only(self):
        score, matched = self.scorer.score("Engineer", "php ruby java frontend sap")
        self.assertEqual((score, matched["penalty"]), (0, []))

    def test_frontend_spellings_count_once(self):
        for title in ("Frontend Engineer", "Front-End Engineer", "front end Engineer"):
            self.assertEqual(self.scorer.score(title, "")[0], -3, title)

    def test_each_penalty_costs_three(self):
        self.assertEqual(self.scorer.score("PHP Ruby Developer", "")[0], -6)

    def test_sap_and_salesforce_whole_words(self):
        self.assertEqual(self.scorer.score("SAP Consultant", "")[0], -3)
        self.assertEqual(self.scorer.score("Salesforce Developer", "")[0], -3)
        self.assertEqual(self.scorer.score("Sapphire Engineer", "")[0], 0)

    def test_matched_terms_report_title_hits(self):
        _, matched = self.scorer.score("NestJS Engineer", "Redis and TypeScript")
        self.assertEqual(matched["core"], ["typescript", "nestjs"])
        self.assertEqual(matched["secondary"], ["redis"])
        self.assertEqual(matched["title"], ["nestjs"])


class ExclusionTests(unittest.TestCase):
    def setUp(self):
        self.scorer, _ = scorer_and_labeler()

    def test_excluded_titles(self):
        titles = [
            "Junior Node.js Developer",
            "Werkstudent Backend (m/w/d)",
            "Praktikum Softwareentwicklung",
            "Software Engineering Intern",
            "Backend Internship",
            "Stażysta / Staż Node.js",
            "Trainee Software Developer",
            "Stagiair Developer",
            "Apprentice Developer",
            "Ausbildung Fachinformatiker",
            "JUNIOR backend engineer",
        ]
        for title in titles:
            self.assertIsNotNone(self.scorer.excluded_by(title), title)

    def test_similar_words_are_not_excluded(self):
        for title in ("International Backend Engineer", "Internal Tools Engineer", "Senior Node.js Developer"):
            self.assertIsNone(self.scorer.excluded_by(title), title)

    def test_excluded_job_is_dropped_even_with_a_high_score(self):
        _, labeler = scorer_and_labeler()
        raw = {"id": "1", "title": "Junior Node.js NestJS TypeScript Developer", "description": "Redis"}
        jobs, stats = aj.collect_jobs([("de", "tech", raw)], self.scorer, labeler, {})
        self.assertEqual(jobs, [])
        self.assertEqual(stats["excluded_by_title"], 1)


class RemoteTests(unittest.TestCase):
    def setUp(self):
        _, self.labeler = scorer_and_labeler()

    def label(self, title="Engineer", description="", location=""):
        return self.labeler.label(title, description, location)

    def test_remote_terms_in_title_description_and_location(self):
        self.assertEqual(self.label(title="Backend Engineer (Remote)"), "yes")
        self.assertEqual(self.label(description="This is a 100% remote position"), "yes")
        self.assertEqual(self.label(description="Homeoffice moeglich"), "yes")
        self.assertEqual(self.label(location="Remote, Germany"), "yes")

    def test_other_languages_and_spellings(self):
        for text in ("Telearbeit", "mobiles Arbeiten", "praca zdalna", "zdalnie", "Thuiswerken", "op afstand",
                     "remote-first culture", "work from home", "work-from-home", "Home-Office"):
            self.assertEqual(self.label(description=text), "yes", text)

    def test_hybrid_terms(self):
        for text in ("Hybrid working", "hybride werkplek", "praca hybrydowa", "Arbeit vor Ort", "on-site", "Onsite"):
            self.assertEqual(self.label(description=text), "hybrid", text)

    def test_both_remote_and_hybrid_terms_give_hybrid(self):
        self.assertEqual(self.label(title="Remote Engineer", description="Hybrid, 2 days on-site"), "hybrid")

    def test_unknown_when_nothing_matches(self):
        self.assertEqual(self.label(description="Build services with Node.js"), "unknown")
        self.assertEqual(self.label(description="Remoteness is a state of mind"), "unknown")


class CleanTextTests(unittest.TestCase):
    def test_strips_tags_and_entities(self):
        self.assertEqual(aj.clean_text("<strong>Fully remote</strong> &amp; fun"), "Fully remote & fun")

    def test_inline_tags_do_not_split_words(self):
        self.assertEqual(aj.clean_text("Type<strong>Script</strong>"), "TypeScript")

    def test_block_tags_become_spaces(self):
        self.assertEqual(aj.clean_text("one<br>two<p>three</p>"), "one two three")

    def test_comparison_signs_are_kept(self):
        self.assertEqual(aj.clean_text("5 < 6 and 7 > 3"), "5 < 6 and 7 > 3")

    def test_none_and_whitespace(self):
        self.assertEqual(aj.clean_text(None), "")
        self.assertEqual(aj.clean_text("  a \n\t b  "), "a b")


class SalaryTests(unittest.TestCase):
    def test_eur_range(self):
        self.assertEqual(aj.format_salary(60000, 80000, "0", "EUR"), "€60k–€80k")

    def test_pln_range_uses_the_code_once(self):
        self.assertEqual(aj.format_salary(15000, 20000, "0", "PLN"), "PLN 15k–20k")

    def test_predicted_flag_adds_estimate_marker(self):
        self.assertEqual(aj.format_salary(60000, 80000, "1", "EUR"), "€60k–€80k (est.)")
        self.assertEqual(aj.format_salary(15000, 20000, "1", "PLN"), "PLN 15k–20k (est.)")

    def test_missing_salary_is_blank(self):
        self.assertEqual(aj.format_salary(None, None, "1", "EUR"), "")
        self.assertEqual(aj.format_salary("", "abc", "0", "EUR"), "")
        self.assertEqual(aj.format_salary(0, 0, "0", "EUR"), "")

    def test_one_sided_and_equal_values(self):
        self.assertEqual(aj.format_salary(60000, None, "0", "EUR"), "€60k+")
        self.assertEqual(aj.format_salary(None, 80000, "0", "EUR"), "up to €80k")
        self.assertEqual(aj.format_salary(70000, 70000, "0", "EUR"), "€70k")

    def test_fractions_and_small_amounts(self):
        self.assertEqual(aj.format_salary(62500, 78000, "0", "EUR"), "€62.5k–€78k")
        self.assertEqual(aj.format_salary(900, 950, "0", "EUR"), "€900–€950")

    def test_numbers_as_strings_and_unknown_currency(self):
        self.assertEqual(aj.format_salary("60000.0", "80000.0", "0", "EUR"), "€60k–€80k")
        self.assertEqual(aj.format_salary(60000, 80000, "0", ""), "60k–80k")
        self.assertEqual(aj.format_salary(60000, 80000, "0", "CHF"), "CHF 60k–80k")


class DedupeTests(unittest.TestCase):
    def test_same_id_from_two_queries_and_countries_appears_once(self):
        scorer, labeler = scorer_and_labeler()
        raw = {"id": "42", "title": "NestJS Engineer", "description": "Remote"}
        same_id_as_int = dict(raw, id=42)
        results = [("de", "tech", raw), ("de", "tech-remote", dict(raw)), ("nl", "tech", same_id_as_int)]
        jobs, stats = aj.collect_jobs(results, scorer, labeler, {"de": "EUR"})
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["found_in"], ["de/tech", "de/tech-remote", "nl/tech"])
        self.assertEqual(stats["results_fetched"], 3)
        self.assertEqual(stats["unique_jobs"], 1)

    def test_result_without_id_is_skipped(self):
        scorer, labeler = scorer_and_labeler()
        jobs, stats = aj.collect_jobs([("de", "tech", {"title": "NestJS Engineer"})], scorer, labeler, {})
        self.assertEqual(jobs, [])
        self.assertEqual(stats["skipped_no_id"], 1)

    def test_job_with_only_an_id_is_handled(self):
        job = aj.normalize_job({"id": "7"}, "de", "EUR")
        self.assertEqual(job["title"], "")
        self.assertEqual(job["company"], "")
        self.assertEqual(job["salary"], "")
        self.assertEqual(job["posted"], "")
        self.assertEqual(job["location"], "")

    def test_malformed_nested_fields_are_tolerated(self):
        raw = {"id": "8", "company": "not a dict", "location": ["x"], "category": None, "created": 12345}
        job = aj.normalize_job(raw, "de", "EUR")
        self.assertEqual(job["company"], "")
        self.assertEqual(job["location"], "")

    def test_location_falls_back_to_area(self):
        raw = {"id": "9", "location": {"area": ["Germany", "Bayern", "Munich"]}}
        self.assertEqual(aj.normalize_job(raw, "de", "EUR")["location"], "Munich, Bayern, Germany")

    def test_zero_score_job_is_dropped(self):
        scorer, labeler = scorer_and_labeler()
        raw = {"id": "1", "title": "Office Manager", "description": "Run the office"}
        jobs, stats = aj.collect_jobs([("de", "tech", raw)], scorer, labeler, {})
        self.assertEqual(jobs, [])
        self.assertEqual(stats["dropped_zero_score"], 1)


class SortTests(unittest.TestCase):
    def test_group_then_score_then_newest(self):
        jobs = [
            make_job("hybrid-high", 50, "hybrid"),
            make_job("unknown-high", 40, "unknown"),
            make_job("yes-low", 5, "yes"),
            make_job("yes-high-old", 20, "yes", "2026-09-01T00:00:00Z"),
            make_job("yes-high-new", 20, "yes", "2026-09-30T00:00:00Z"),
            make_job("yes-mid", 10, "yes"),
            make_job("unknown-low", 1, "unknown"),
            make_job("hybrid-low", 3, "hybrid"),
        ]
        aj.sort_jobs(jobs)
        self.assertEqual(
            [job["id"] for job in jobs],
            ["yes-high-new", "yes-high-old", "yes-mid", "yes-low",
             "unknown-high", "unknown-low", "hybrid-high", "hybrid-low"],
        )

    def test_missing_or_bad_created_sorts_last_among_equals(self):
        jobs = [
            make_job("none", 5, "yes", ""),
            make_job("bad", 5, "yes", "not a date"),
            make_job("dated", 5, "yes", "2026-09-01T00:00:00Z"),
        ]
        aj.sort_jobs(jobs)
        self.assertEqual(jobs[0]["id"], "dated")


class SeenTests(unittest.TestCase):
    def test_new_marking_against_a_temporary_seen_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "seen.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"old": "2026-09-01", "today-one": "2026-10-02"}, handle)

            seen = aj.load_seen(path)
            jobs = [{"id": "old"}, {"id": "today-one"}, {"id": "fresh"}]
            aj.mark_new(jobs, seen, "2026-10-02")
            self.assertEqual([job["is_new"] for job in jobs], [False, True, True])
            self.assertEqual(jobs[0]["first_seen"], "2026-09-01")

            aj.save_seen(path, seen)
            reloaded = aj.load_seen(path)
            self.assertEqual(reloaded, {"old": "2026-09-01", "today-one": "2026-10-02", "fresh": "2026-10-02"})

            next_day_jobs = [{"id": "old"}, {"id": "fresh"}, {"id": "newer"}]
            aj.mark_new(next_day_jobs, reloaded, "2026-10-03")
            self.assertEqual([job["is_new"] for job in next_day_jobs], [False, False, True])
            self.assertEqual(reloaded["fresh"], "2026-10-02")

    def test_missing_and_corrupt_seen_files_start_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(aj.load_seen(os.path.join(tmp, "missing.json")), {})
            corrupt = os.path.join(tmp, "corrupt.json")
            with open(corrupt, "w", encoding="utf-8") as handle:
                handle.write("{not json")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(aj.load_seen(corrupt), {})


class RunSearchTests(unittest.TestCase):
    def config(self, per_page=2, pages=3, countries=("de",), queries=1):
        return {
            "countries": list(countries),
            "queries": [
                {"name": "q%d" % index, "params": {"results_per_page": per_page}, "pages": pages}
                for index in range(queries)
            ],
        }

    def test_paging_stops_when_a_page_is_short(self):
        calls = []

        def fetch(country, query, page):
            calls.append(page)
            return {"results": [{"id": "%d-%d" % (page, n)} for n in range(2 if page == 1 else 1)]}

        outcome = aj.run_search(self.config(), fetch)
        self.assertEqual(calls, [1, 2])
        self.assertEqual(outcome["calls"], 2)
        self.assertEqual(len(outcome["results"]), 3)

    def test_paging_continues_while_pages_are_full(self):
        calls = []

        def fetch(country, query, page):
            calls.append(page)
            return {"results": [{"id": "%d-%d" % (page, n)} for n in range(2)]}

        aj.run_search(self.config(pages=3), fetch)
        self.assertEqual(calls, [1, 2, 3])

    def test_a_failed_request_is_recorded_and_the_run_continues(self):
        def fetch(country, query, page):
            if country == "at":
                raise aj.RequestFailed(400, "HTTP 400")
            return {"results": [{"id": country}]}

        outcome = aj.run_search(self.config(countries=("de", "at", "nl"), queries=2), fetch)
        self.assertEqual([f["country"] for f in outcome["failures"]], ["at", "at"])
        self.assertEqual({r[0] for r in outcome["results"]}, {"de", "nl"})
        self.assertIsNone(outcome["stopped"])
        self.assertEqual(outcome["calls"], 6)

    def test_rejected_credentials_stop_the_run(self):
        calls = []

        def fetch(country, query, page):
            calls.append(country)
            raise aj.RequestFailed(401, "HTTP 401")

        outcome = aj.run_search(self.config(countries=("de", "nl", "pl")), fetch)
        self.assertEqual(calls, ["de"])
        self.assertIn("credentials rejected", outcome["stopped"])

    def test_rate_limit_is_retried_once_after_waiting(self):
        attempts = []
        sleeps = []

        def fetch(country, query, page):
            attempts.append(page)
            if len(attempts) == 1:
                raise aj.RequestFailed(429, "HTTP 429")
            return {"results": []}

        outcome = aj.run_search(self.config(), fetch, sleep=sleeps.append, rate_limit_wait=60)
        self.assertEqual(sleeps, [60])
        self.assertEqual(outcome["calls"], 2)
        self.assertEqual(outcome["failures"], [])
        self.assertEqual(outcome["successes"], 1)

    def test_server_error_is_retried_once_and_does_not_stop_the_run(self):
        attempts = []
        sleeps = []

        def fetch(country, query, page):
            attempts.append(country)
            if country == "de" and attempts.count("de") == 1:
                raise aj.RequestFailed(503, "HTTP 503")
            if country == "nl":
                raise aj.RequestFailed(500, "HTTP 500")
            return {"results": []}

        outcome = aj.run_search(self.config(countries=("de", "nl", "pl")), fetch,
                                sleep=sleeps.append, server_error_wait=5)
        self.assertEqual(attempts, ["de", "de", "nl", "nl", "pl"])
        self.assertEqual(sleeps, [5, 5])
        self.assertEqual([f["country"] for f in outcome["failures"]], ["nl"])
        self.assertIsNone(outcome["stopped"])
        self.assertEqual(outcome["successes"], 2)

    def test_persistent_rate_limit_stops_the_run(self):
        def fetch(country, query, page):
            raise aj.RequestFailed(429, "HTTP 429")

        outcome = aj.run_search(self.config(countries=("de", "nl")), fetch, sleep=lambda seconds: None)
        self.assertEqual(outcome["calls"], 2)
        self.assertIn("rate limit", outcome["stopped"])

    def test_delay_is_applied_between_calls_only(self):
        sleeps = []

        def fetch(country, query, page):
            return {"results": []}

        aj.run_search(self.config(countries=("de", "nl", "pl")), fetch, delay=2.5, sleep=sleeps.append)
        self.assertEqual(sleeps, [2.5, 2.5])

    def test_live_fetcher_never_leaks_credentials_in_failures(self):
        error = aj.urllib.error.HTTPError(
            "https://api.adzuna.com/x?app_id=%s&app_key=%s" % (FAKE_ID, FAKE_KEY), 429, "Too Many", {}, None
        )
        fetcher = aj.LiveFetcher(FAKE_ID, FAKE_KEY)
        with mock.patch.object(aj.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(aj.RequestFailed) as caught:
                fetcher("de", {"name": "q", "params": {}}, 1)
        self.assertEqual(caught.exception.status, 429)
        self.assertNotIn(FAKE_ID, str(caught.exception))
        self.assertNotIn(FAKE_KEY, str(caught.exception))
        self.assertNotIn(FAKE_KEY, repr(fetcher))

    def test_live_fetcher_reports_network_errors_without_the_url(self):
        reason = aj.urllib.error.URLError(ConnectionRefusedError("refused %s" % FAKE_KEY))
        fetcher = aj.LiveFetcher(FAKE_ID, FAKE_KEY)
        with mock.patch.object(aj.urllib.request, "urlopen", side_effect=reason):
            with self.assertRaises(aj.RequestFailed) as caught:
                fetcher("de", {"name": "q", "params": {}}, 1)
        self.assertIsNone(caught.exception.status)
        self.assertEqual(caught.exception.reason, "network error (ConnectionRefusedError)")


class UrlTests(unittest.TestCase):
    def test_url_is_built_with_urlencode(self):
        params = {"what_or": "typescript nodejs", "results_per_page": 50}
        url = aj.build_url("de", 2, params, (FAKE_ID, FAKE_KEY))
        self.assertTrue(url.startswith("https://api.adzuna.com/v1/api/jobs/de/search/2?"))
        self.assertIn("app_id=%s&app_key=%s" % (FAKE_ID, FAKE_KEY), url)
        self.assertIn("what_or=typescript+nodejs", url)
        self.assertIn("content-type=application%2Fjson", url)

    def test_redacted_url_hides_both_values(self):
        url = aj.build_url("de", 1, {"results_per_page": 50}, None)
        self.assertIn("app_id=***&app_key=***", url)

    def test_redact_replaces_credentials_in_text(self):
        text = "failed with %s and %s" % (FAKE_ID, FAKE_KEY)
        self.assertEqual(aj.redact(text, (FAKE_ID, FAKE_KEY)), "failed with *** and ***")


class ConfigTests(unittest.TestCase):
    def test_shipped_config_is_valid_and_has_twelve_calls(self):
        config = real_config()
        self.assertEqual(config["countries"], ["de", "nl", "pl", "at"])
        planned = sum(query["pages"] for query in config["queries"]) * len(config["countries"])
        self.assertEqual(planned, 12)

    def test_credentials_in_config_params_are_rejected(self):
        config = real_config()
        config["queries"][0]["params"]["app_key"] = "x"
        with self.assertRaises(aj.ConfigError):
            aj.validate_config(config)

    def test_bad_country_and_page_size_are_rejected(self):
        config = real_config()
        config["countries"] = ["de/../x"]
        with self.assertRaises(aj.ConfigError):
            aj.validate_config(config)
        config = real_config()
        config["queries"][0]["params"]["results_per_page"] = 100
        with self.assertRaises(aj.ConfigError):
            aj.validate_config(config)


    def test_shipped_broad_config_is_valid_and_within_quota(self):
        config = aj.load_config(os.path.join(ROOT, "config", "broad_config.json"))
        self.assertEqual(config["report_prefix"], "broad")
        self.assertEqual(config["seen_file"], "seen.broad.json")
        planned = sum(query["pages"] for query in config["queries"]) * len(config["countries"])
        self.assertLessEqual(planned, 50)
        self.assertTrue(all(country in config["currencies"] for country in config["countries"]))

    def test_report_prefix_and_seen_file_are_validated(self):
        for key, value in (("report_prefix", "../x"), ("report_prefix", "Broad"), ("report_prefix", 3),
                           ("seen_file", "../seen.json"), ("seen_file", "seen.txt"), ("seen_file", "/tmp/seen.json")):
            config = real_config()
            config[key] = value
            with self.assertRaises(aj.ConfigError, msg="%s=%r" % (key, value)):
                aj.validate_config(config)


class CommandLineTests(unittest.TestCase):
    def run_script(self, args, env):
        return subprocess.run(
            [sys.executable, "-B", SCRIPT_PATH] + args,
            capture_output=True, text=True, env=env, cwd=tempfile.gettempdir(), timeout=60,
        )

    def test_dry_run_redacts_credentials_and_counts_twelve_calls(self):
        env = dict(env_without_adzuna(), ADZUNA_APP_ID=FAKE_ID, ADZUNA_APP_KEY=FAKE_KEY)
        result = self.run_script(["--dry-run"], env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(FAKE_ID, result.stdout + result.stderr)
        self.assertNotIn(FAKE_KEY, result.stdout + result.stderr)
        self.assertIn("app_id=***&app_key=***", result.stdout)
        self.assertIn("Total API calls: 12", result.stdout)
        self.assertEqual(result.stdout.count("https://api.adzuna.com/"), 12)

    def test_dry_run_in_process_redacts_credentials(self):
        env = {"ADZUNA_APP_ID": FAKE_ID, "ADZUNA_APP_KEY": FAKE_KEY}
        code, out, err = run_main(["--dry-run"], env)
        self.assertEqual(code, 0)
        self.assertNotIn(FAKE_ID, out + err)
        self.assertNotIn(FAKE_KEY, out + err)

    def test_dry_run_works_without_credentials(self):
        result = self.run_script(["--dry-run"], env_without_adzuna())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Total API calls: 12", result.stdout)

    def test_missing_credentials_exit_two_with_a_clear_message(self):
        result = self.run_script([], env_without_adzuna())
        self.assertEqual(result.returncode, 2)
        self.assertIn("https://developer.adzuna.com", result.stderr)
        self.assertIn("ADZUNA_APP_ID", result.stderr)
        self.assertIn("ADZUNA_APP_KEY", result.stderr)

    def test_only_one_credential_set_still_exits_two(self):
        env = dict(env_without_adzuna(), ADZUNA_APP_ID=FAKE_ID)
        result = self.run_script([], env)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(FAKE_ID, result.stdout + result.stderr)

    def test_bad_config_exits_two(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{broken")
            result = self.run_script(["--dry-run", "--config", path], env_without_adzuna())
        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)


class EndToEndFixtureTests(unittest.TestCase):
    def guarded_paths(self):
        return [os.path.join(ROOT, name) for name in ("reports", "seen.json", "seen.fixture.json")]

    def run_fixture(self, tmp, env=None):
        out_dir = os.path.join(tmp, "reports")
        seen = os.path.join(tmp, "seen.json")
        code, out, err = run_main(
            ["--fixture", FIXTURE_PATH, "--out-dir", out_dir, "--seen-file", seen], env
        )
        files = sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []
        return code, out, err, out_dir, files

    def load_report(self, out_dir, files):
        markdown = next(name for name in files if name.endswith(".md"))
        document = next(name for name in files if name.endswith(".json"))
        with open(os.path.join(out_dir, markdown), encoding="utf-8") as handle:
            text = handle.read()
        with open(os.path.join(out_dir, document), encoding="utf-8") as handle:
            data = json.load(handle)
        return text, data

    def test_fixture_run_produces_the_expected_report(self):
        before = [os.path.exists(path) for path in self.guarded_paths()]
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err, out_dir, files = self.run_fixture(tmp)
            self.assertEqual(code, 0, err)
            self.assertEqual(len(files), 2)
            text, data = self.load_report(out_dir, files)
            by_id = {job["id"]: job for job in data["jobs"]}

            self.assertIn("## Failed requests", text)
            self.assertIn("at / tech (page 1): HTTP 400", text)
            self.assertIn("at / tech-remote (page 1): HTTP 400", text)
            self.assertEqual(len(data["failed_requests"]), 2)
            self.assertEqual({f["country"] for f in data["failed_requests"]}, {"at"})

            self.assertNotIn("Junior", text)
            self.assertNotIn("4001004", json.dumps(data))
            self.assertNotIn("4001009", by_id)
            self.assertNotIn("4001010", by_id)

            self.assertEqual(len(data["jobs"]), 7)
            self.assertEqual(len([j for j in data["jobs"] if j["id"] == "4001001"]), 1)
            self.assertEqual(by_id["4001001"]["found_in"], ["de/tech", "de/tech-remote"])

            self.assertEqual([job["id"] for job in data["jobs"]],
                             ["4001001", "6001001", "4001008", "4001005", "4001003", "5001001", "4001006"])
            self.assertEqual([job["remote"] for job in data["jobs"]],
                             ["yes", "yes", "yes", "unknown", "unknown", "hybrid", "hybrid"])

            self.assertEqual(by_id["4001001"]["score"], 23)
            self.assertEqual(by_id["4001003"]["score"], 2)
            self.assertEqual(by_id["4001003"]["matched_terms"]["penalty"], ["java"])
            self.assertEqual(by_id["4001005"]["score"], 5)
            self.assertEqual(by_id["4001005"]["matched_terms"]["penalty"], [])
            self.assertEqual(by_id["6001001"]["salary"], "PLN 180k–240k (est.)")
            self.assertEqual(by_id["4001001"]["salary"], "€70k–€90k")
            self.assertEqual(by_id["4001008"]["company"], "")
            self.assertEqual(by_id["4001008"]["salary"], "")
            self.assertNotIn("<", by_id["4001006"]["title"])
            self.assertNotIn("<strong>", json.dumps(data))
            self.assertNotIn("<strong>", text)

            self.assertTrue(all(job["is_new"] for job in data["jobs"]))
            self.assertEqual(data["summary"]["new"], 7)
            self.assertEqual(data["summary"]["remote"], {"yes": 3, "unknown": 2, "hybrid": 2})
            self.assertEqual(data["summary"]["api_calls"], 8)
            self.assertIn("| Score | New | Title | Company | Location | Salary | Posted | Link |", text)
            self.assertIn("[open](https://www.adzuna.de/details/4001001", text)
            self.assertTrue(text.rstrip().endswith("Jobs by [Adzuna](https://www.adzuna.com)."))
            self.assertIn("Jobs kept: 7 (7 new)", out)
            self.assertTrue(os.path.exists(os.path.join(tmp, "seen.json")))

        self.assertEqual(before, [os.path.exists(path) for path in self.guarded_paths()])

    def test_same_day_rerun_keeps_new_flags_and_overwrites_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_fixture(tmp)
            code, _, _, out_dir, files = self.run_fixture(tmp)
            self.assertEqual(code, 0)
            self.assertEqual(len(files), 2)
            _, data = self.load_report(out_dir, files)
            self.assertEqual(data["summary"]["new"], 7)

    def test_report_prefix_names_the_report_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = real_config()
            config["report_prefix"] = "broad"
            config_path = os.path.join(tmp, "broad.json")
            with open(config_path, "w", encoding="utf-8") as handle:
                json.dump(config, handle)
            out_dir = os.path.join(tmp, "reports")
            code, _, err = run_main(["--fixture", FIXTURE_PATH, "--config", config_path, "--out-dir", out_dir,
                                     "--seen-file", os.path.join(tmp, "seen.json")])
            self.assertEqual(code, 0, err)
            files = sorted(os.listdir(out_dir))
            self.assertEqual(len(files), 2)
            self.assertTrue(all(name.startswith("broad-") for name in files), files)

    def test_credentials_never_reach_the_report(self):
        env = {"ADZUNA_APP_ID": FAKE_ID, "ADZUNA_APP_KEY": FAKE_KEY}
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err, out_dir, files = self.run_fixture(tmp, env)
            self.assertEqual(code, 0)
            combined = out + err
            for name in files:
                with open(os.path.join(out_dir, name), encoding="utf-8") as handle:
                    combined += handle.read()
        self.assertNotIn(FAKE_ID, combined)
        self.assertNotIn(FAKE_KEY, combined)

    def test_all_requests_failing_exits_one_but_still_writes_a_report(self):
        failing = {"de": {"error": 400}, "nl": {"tech": [{"error": 500}], "tech-remote": [{"error": 500}]},
                   "pl": {"error": 400}, "at": {"error": 400}}
        with tempfile.TemporaryDirectory() as tmp:
            fixture = os.path.join(tmp, "failing.json")
            with open(fixture, "w", encoding="utf-8") as handle:
                json.dump(failing, handle)
            out_dir = os.path.join(tmp, "reports")
            code, out, _ = run_main(["--fixture", fixture, "--out-dir", out_dir,
                                     "--seen-file", os.path.join(tmp, "seen.json")])
            self.assertEqual(code, 1)
            self.assertIn("Failed:", out)
            markdown = next(name for name in os.listdir(out_dir) if name.endswith(".md"))
            with open(os.path.join(out_dir, markdown), encoding="utf-8") as handle:
                text = handle.read()
            self.assertIn("No matching jobs.", text)
            self.assertIn("## Failed requests", text)


class MarkdownTests(unittest.TestCase):
    def test_pipes_and_newlines_are_escaped_in_cells(self):
        self.assertEqual(aj.md_cell("a | b\nc"), "a \\| b c")

    def test_link_escapes_markdown_breaking_characters(self):
        self.assertEqual(aj.md_link("https://x.test/a b(c)|d"), "[open](https://x.test/a%20b%28c%29%7Cd)")
        self.assertEqual(aj.md_link(""), "")


if __name__ == "__main__":
    unittest.main()

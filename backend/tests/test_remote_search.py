import datetime
import json
import os
import sys
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)
sys.path.insert(0, os.path.join(ROOT, "vendor"))

import remote_search as rs  # noqa: E402

with open(os.path.join(ROOT, "config", "remote_config.json"), encoding="utf-8") as handle:
    CONFIG = json.load(handle)

TODAY = datetime.date(2026, 10, 7)


def make(title="Senior Backend Engineer (Node.js)", location="", restrictions=None, type_field="",
         description="Node.js, TypeScript, NestJS, PostgreSQL", posted="2026-10-01", source="remotive"):
    return rs.job(source, title, title, "Acme", "https://example.com/" + title, location=location,
                  restrictions=restrictions, type_field=type_field, posted=posted, description=description)


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.labeler = rs.LocationLabeler(CONFIG["location"])

    def label(self, **kwargs):
        return self.labeler.label(make(**kwargs))

    def test_text_locations(self):
        self.assertEqual(self.label(location="Anywhere in the World"), "worldwide")
        self.assertEqual(self.label(location="REMOTE [Europe / (GMT+2)]"), "europe")
        self.assertEqual(self.label(location="EMEA"), "europe")
        self.assertEqual(self.label(location="Canada, USA"), "us")
        self.assertEqual(self.label(location="Remote (US and Canada)"), "us")
        self.assertEqual(self.label(location="Brazil"), "other")
        self.assertEqual(self.label(location="Remote"), "unclear")
        self.assertEqual(self.label(location=""), "unclear")

    def test_worldwide_beats_us(self):
        self.assertEqual(self.label(location="USA, Europe, Worldwide"), "worldwide")

    def test_himalayas_country_lists(self):
        self.assertEqual(self.label(restrictions=[]), "worldwide")
        self.assertEqual(self.label(restrictions=["Romania", "Poland"]), "europe")
        self.assertEqual(self.label(restrictions=["United States"]), "us")
        self.assertEqual(self.label(restrictions=["Mexico"]), "other")
        self.assertEqual(self.label(restrictions=["Poland", "Bulgaria"]), "other")


class EmploymentTests(unittest.TestCase):
    def test_type_field_and_title(self):
        self.assertEqual(rs.employment(make(type_field="contract")), "contract")
        self.assertEqual(rs.employment(make(type_field="Contractor")), "contract")
        self.assertEqual(rs.employment(make(title="Software Engineer | Remote - Contract")), "contract")
        self.assertEqual(rs.employment(make(type_field="Full-Time")), "full-time")
        self.assertEqual(rs.employment(make()), "unknown")

    def test_description_hint_is_tentative(self):
        item = make(type_field="Full-Time", description="Node.js work as an independent contractor")
        self.assertEqual(rs.employment(item), "contract?")

    def test_api_contracts_is_not_a_contract_role(self):
        item = make(description="Design API contracts in TypeScript")
        self.assertEqual(rs.employment(item), "unknown")


class LabelJobsTests(unittest.TestCase):
    def test_filters_and_dedupes(self):
        jobs = [
            make(location="Worldwide", type_field="contract"),
            make(location="Worldwide", source="remoteok"),  # same company and title
            make(title="Junior Node.js Developer", location="Worldwide"),
            make(title="Senior Node.js Engineer (old)", location="Worldwide", posted="2026-08-01"),
            make(title="Marketing Lead", location="Worldwide", description="Node.js"),
            make(title="Office Manager", location="Worldwide", description="spreadsheets"),
        ]
        kept, dropped = rs.label_jobs(jobs, CONFIG, TODAY)
        self.assertEqual([item["title"] for item in kept], ["Senior Backend Engineer (Node.js)"])
        self.assertEqual(kept[0]["sources"], ["remotive", "remoteok"])
        self.assertEqual(kept[0]["type"], "contract")
        self.assertEqual(kept[0]["eligibility"], "worldwide")
        self.assertEqual(dropped["duplicate"], 1)
        self.assertEqual(dropped["old"], 1)
        self.assertEqual(dropped["excluded"], 2)
        self.assertEqual(dropped["low score"], 1)

    def test_sort_puts_contract_first(self):
        rows = [
            dict(type="full-time", score=20, posted="2026-10-06"),
            dict(type="contract", score=5, posted="2026-10-01"),
            dict(type="contract", score=5, posted="2026-10-05"),
        ]
        rs.sort_jobs(rows)
        self.assertEqual([(r["type"], r["posted"]) for r in rows],
                         [("contract", "2026-10-05"), ("contract", "2026-10-01"), ("full-time", "2026-10-06")])


with open(os.path.join(ROOT, "config", "gaming_config.json"), encoding="utf-8") as handle:
    GAMING = json.load(handle)


class IndustryFilterTests(unittest.TestCase):
    def setUp(self):
        self.games = rs.IndustryFilter(GAMING["industry"])

    def test_board_title_and_text_signals(self):
        self.assertTrue(self.games.allows(dict(make(title="Accountant"), industry="gaming")))
        self.assertTrue(self.games.allows(make(title="Senior Game Server Engineer")))
        self.assertTrue(self.games.allows(make(description="We build mobile games played by millions of players.")))
        self.assertTrue(self.games.allows(make(description="A game about games: the gaming studio behind it.")))

    def test_one_stack_in_a_long_list_is_not_enough(self):
        listing = make(description="Stacks: React, .NET, Unreal Engine & C++, Python, Vue")
        self.assertFalse(self.games.allows(listing))

    def test_gambling_is_excluded_even_on_a_board(self):
        self.assertFalse(self.games.allows(dict(make(description="Our online casino platform"), industry="gaming")))
        self.assertFalse(self.games.allows(make(title="Game Server Engineer", description="sports betting at scale")))


class EuropeOtherTests(unittest.TestCase):
    def setUp(self):
        self.labeler = rs.LocationLabeler(GAMING["location"])

    def test_country_tied_remote(self):
        self.assertEqual(self.labeler.label(make(location="Remote: Paris, Warsaw, Lisboa")), "europe-other")
        self.assertEqual(self.labeler.label(make(restrictions=["Serbia"])), "europe-other")
        self.assertEqual(self.labeler.label(make(location="Remote: Russia, Moscow")), "other")

    def test_romania_and_international_stay_open(self):
        self.assertEqual(self.labeler.label(make(restrictions=["Romania"])), "europe")
        self.assertEqual(self.labeler.label(make(location="Remote - International")), "worldwide")


class BoardTests(unittest.TestCase):
    class FakeHttp:
        def __init__(self, routes):
            self.routes = routes

        def json(self, url):
            for fragment, value in self.routes.items():
                if fragment in url:
                    if isinstance(value, Exception):
                        raise value
                    return value
            raise ValueError("unexpected url " + url)

    def test_greenhouse_keeps_remote_jobs_and_survives_a_bad_board(self):
        http = self.FakeHttp({
            "boards/good/": {"jobs": [
                {"id": 1, "title": "Backend Engineer", "location": {"name": "Remote - Europe"},
                 "absolute_url": "https://x/1", "first_published": "2026-01-02T00:00:00Z", "content": "&lt;p&gt;Node&lt;/p&gt;"},
                {"id": 2, "title": "Backend Engineer", "location": {"name": "Berlin, Germany"}, "absolute_url": "https://x/2"},
            ]},
            "boards/gone/": ValueError("404"),
        })
        jobs = rs.fetch_greenhouse(http, {"industry": "gaming", "boards": {"gone": "Gone Inc", "good": "Good Games"}})
        self.assertEqual([(j["company"], j["location"], j["board"], j["industry"]) for j in jobs],
                         [("Good Games", "Remote - Europe", True, "gaming")])
        self.assertEqual(jobs[0]["description"], "Node")

    def test_board_jobs_skip_the_age_check(self):
        old = dict(make(location="Worldwide", posted="2025-01-01"), board=True)
        kept, dropped = rs.label_jobs([old], CONFIG, TODAY)
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped["old"], 0)


class HelperTests(unittest.TestCase):
    def test_iso_date(self):
        self.assertEqual(rs.iso_date("2026-10-05T05:15:43"), "2026-10-05")
        self.assertEqual(rs.iso_date("Mon, 06 Oct 2026 12:00:00 +0000"), "2026-10-06")
        self.assertEqual(rs.iso_date(1791387089), "2026-10-07")
        self.assertEqual(rs.iso_date(""), "")

    def test_money(self):
        self.assertEqual(rs.money(30, 100, "USD", "hourly"), "$30–100/h")
        self.assertEqual(rs.money(140000, 180000, "USD", "annual"), "$140k–180k/yr")
        self.assertEqual(rs.money(None, None), "")

    def test_himalayas_location(self):
        self.assertEqual(rs.himalayas_location([]), "Worldwide")
        self.assertEqual(rs.himalayas_location(["Romania", "Poland"]), "Romania, Poland")
        many = ["Country %d" % n for n in range(10)]
        self.assertEqual(rs.himalayas_location(many + ["Romania"]), "11 countries, incl. Romania")
        self.assertEqual(rs.himalayas_location(many), "10 countries, not Romania")


if __name__ == "__main__":
    unittest.main()

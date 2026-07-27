#!/usr/bin/env python3

import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import bus_generate  # noqa: E402
import search  # noqa: E402


def vansky_row():
    return {
        "price": 1900, "floor": "above", "date": "2099-01-01",
        "posted": "2099-01-01", "ts": 4070908800, "available": "",
        "lease": "", "tel": "604-555-0100", "tel2": "", "name": "",
        "email": "", "wechat": "", "title": "test", "area": "",
        "url": "https://example.test/1", "src": "vansky",
    }


class DegradedSourceTests(unittest.TestCase):
    @mock.patch.object(search, "search_vansky", return_value=[vansky_row()])
    @mock.patch.object(search, "search_vanpeople",
                       side_effect=search.SourceUnavailable(
                           "HTTP 403 (Cloudflare challenge)"))
    def test_both_sources_falls_back_and_reports_status(self, _vp, _vs):
        status = {}
        rows = search.run_search(source="both", source_status=status)

        self.assertEqual(1, len(rows))
        self.assertEqual("vansky", rows[0]["src"])
        self.assertEqual("unavailable", status["vanpeople"]["status"])
        self.assertEqual("ok", status["vansky"]["status"])

    @mock.patch.object(search, "search_vanpeople",
                       side_effect=search.SourceUnavailable("HTTP 403"))
    def test_single_failed_source_still_raises(self, _vp):
        with self.assertRaises(search.SourceUnavailable):
            search.run_search(source="vanpeople", source_status={})

    def test_source_summary_marks_unavailable_source(self):
        queries = [
            {"sourceStatus": {
                "vanpeople": {"status": "unavailable", "count": 0,
                              "error": "HTTP 403"},
                "vansky": {"status": "ok", "count": 4},
            }},
            {"sourceStatus": {
                "vanpeople": {"status": "unavailable", "count": 0,
                              "error": "HTTP 403"},
                "vansky": {"status": "ok", "count": 3},
            }},
        ]

        result = bus_generate.summarize_sources(queries)

        self.assertEqual("unavailable", result["vanpeople"]["status"])
        self.assertEqual(["HTTP 403"], result["vanpeople"]["errors"])
        self.assertEqual("ok", result["vansky"]["status"])
        self.assertEqual(7, result["vansky"]["count"])

    def test_partial_baseline_counts_only_healthy_source(self):
        previous = {
            "count": 3,
            "items": [
                {"src": "vanpeople"}, {"src": "vanpeople"}, {"src": "vansky"},
            ],
        }
        with mock.patch("builtins.open", mock.mock_open(
                read_data=json.dumps(previous))):
            self.assertEqual(1, bus_generate.previous_count({"vansky"}))


if __name__ == "__main__":
    unittest.main()

"""Tests for filter_and_sort_items (lib/metrics) and the API filter/sort
query parameters on /repos/findings/detail (Milestone 6.3)."""

import unittest
from unittest.mock import patch

from lib.metrics import filter_and_sort_items


# ---------------------------------------------------------------------------
# Sample items used across tests
# ---------------------------------------------------------------------------
ITEMS = [
    {"severity": "warning", "category": "style", "file": "a.py", "line": 1, "message": "trailing space"},
    {"severity": "error", "category": "security", "file": "b.py", "line": 5, "message": "sql injection"},
    {"severity": "critical", "category": "correctness", "file": "c.py", "line": 10, "message": "null deref"},
    {"severity": "info", "category": "maintainability", "file": "d.py", "line": 2, "message": "unused import"},
    {"severity": "error", "category": "style", "file": "a.py", "line": 20, "message": "long line"},
]


class TestFilterAndSortItems(unittest.TestCase):
    """Unit tests for ``filter_and_sort_items``."""

    # --- Filtering -----------------------------------------------------------

    def test_no_filters_returns_all_items(self):
        result = filter_and_sort_items(ITEMS)
        self.assertEqual(len(result), len(ITEMS))

    def test_filter_by_single_severity(self):
        result = filter_and_sort_items(ITEMS, severity=["error"])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(i["severity"] == "error" for i in result))

    def test_filter_by_multiple_severities(self):
        result = filter_and_sort_items(ITEMS, severity=["error", "critical"])
        self.assertEqual(len(result), 3)
        severities = {i["severity"] for i in result}
        self.assertEqual(severities, {"error", "critical"})

    def test_filter_by_single_category(self):
        result = filter_and_sort_items(ITEMS, category=["style"])
        self.assertEqual(len(result), 2)
        self.assertTrue(all(i["category"] == "style" for i in result))

    def test_filter_by_multiple_categories(self):
        result = filter_and_sort_items(ITEMS, category=["style", "security"])
        self.assertEqual(len(result), 3)
        categories = {i["category"] for i in result}
        self.assertEqual(categories, {"style", "security"})

    def test_combined_severity_and_category_filter(self):
        result = filter_and_sort_items(ITEMS, severity=["error"], category=["style"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["message"], "long line")

    def test_filter_is_case_insensitive(self):
        result = filter_and_sort_items(ITEMS, severity=["ERROR"])
        self.assertEqual(len(result), 2)

    def test_filter_no_match_returns_empty(self):
        result = filter_and_sort_items(ITEMS, severity=["nonexistent"])
        self.assertEqual(result, [])

    # --- Sorting -------------------------------------------------------------

    def test_default_sort_is_severity_desc(self):
        result = filter_and_sort_items(ITEMS)
        severities = [i["severity"] for i in result]
        self.assertEqual(severities[0], "critical")
        self.assertIn(result[-1]["severity"], ("info", "warning"))

    def test_sort_severity_asc(self):
        result = filter_and_sort_items(ITEMS, sort="severity", sort_dir="asc")
        # asc = least severe first (info/warning), most severe last (critical)
        self.assertIn(result[0]["severity"], ("info", "warning"))
        self.assertEqual(result[-1]["severity"], "critical")

    def test_sort_by_file_desc(self):
        result = filter_and_sort_items(ITEMS, sort="file", sort_dir="desc")
        files = [i["file"] for i in result]
        self.assertEqual(files, sorted(files, reverse=True))

    def test_sort_by_file_asc(self):
        result = filter_and_sort_items(ITEMS, sort="file", sort_dir="asc")
        files = [i["file"] for i in result]
        self.assertEqual(files, sorted(files))

    def test_sort_by_category(self):
        result = filter_and_sort_items(ITEMS, sort="category", sort_dir="asc")
        categories = [i["category"] for i in result]
        self.assertEqual(categories, sorted(categories))

    def test_invalid_sort_field_falls_back_to_severity(self):
        result = filter_and_sort_items(ITEMS, sort="invalid_field")
        result_default = filter_and_sort_items(ITEMS, sort="severity")
        self.assertEqual(result, result_default)

    def test_deterministic_sort_on_equal_keys(self):
        """Items with the same primary sort key should have a stable secondary order."""
        errors = filter_and_sort_items(ITEMS, severity=["error"])
        # Both items have severity=error; they should sort consistently by file
        self.assertEqual(len(errors), 2)
        files = [i["file"] for i in errors]
        # Running again must produce the same order
        errors2 = filter_and_sort_items(ITEMS, severity=["error"])
        files2 = [i["file"] for i in errors2]
        self.assertEqual(files, files2)

    # --- Combined filter + sort ----------------------------------------------

    def test_filter_then_sort(self):
        result = filter_and_sort_items(
            ITEMS, severity=["error", "warning"], sort="file", sort_dir="asc",
        )
        self.assertEqual(len(result), 3)
        files = [i["file"] for i in result]
        self.assertEqual(files, sorted(files))

    # --- Edge cases ----------------------------------------------------------

    def test_empty_items(self):
        result = filter_and_sort_items([])
        self.assertEqual(result, [])

    def test_items_with_missing_fields(self):
        items = [
            {"message": "bare item"},
            {"severity": "error", "file": "z.py", "message": "has sev"},
        ]
        result = filter_and_sort_items(items, severity=["error"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["file"], "z.py")

    def test_original_list_is_not_mutated(self):
        original = list(ITEMS)
        filter_and_sort_items(ITEMS, severity=["error"], sort="file")
        self.assertEqual(ITEMS, original)


# ---------------------------------------------------------------------------
# API endpoint integration tests
# ---------------------------------------------------------------------------
class TestApiFilterSort(unittest.TestCase):
    """Tests that the ``/repos/findings/detail`` endpoint correctly passes
    filter and sort parameters through to ``filter_and_sort_items``."""

    SNAPSHOT = {
        "repo": "heimgewebe/demo",
        "ts": "2026-03-28T10:00:00+00:00",
        "count": 5,
        "deduped": 5,
        "files": [
            {"file": "a.py", "count": 2, "topSeverity": "error"},
            {"file": "b.py", "count": 1, "topSeverity": "critical"},
            {"file": "c.py", "count": 1, "topSeverity": "info"},
            {"file": "d.py", "count": 1, "topSeverity": "warning"},
        ],
        "items": list(ITEMS),
    }

    @patch("lib.metrics.load_findings_snapshots")
    def test_no_filter_returns_all_items(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo")
        self.assertEqual(len(result["items"]), 5)

    @patch("lib.metrics.load_findings_snapshots")
    def test_severity_filter(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo", severity="error")
        self.assertEqual(len(result["items"]), 2)
        self.assertTrue(all(i["severity"] == "error" for i in result["items"]))

    @patch("lib.metrics.load_findings_snapshots")
    def test_category_filter(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo", category="style")
        self.assertEqual(len(result["items"]), 2)
        self.assertTrue(all(i["category"] == "style" for i in result["items"]))

    @patch("lib.metrics.load_findings_snapshots")
    def test_combined_filter(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(
            repo="heimgewebe/demo", severity="error", category="style",
        )
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["message"], "long line")

    @patch("lib.metrics.load_findings_snapshots")
    def test_sort_by_file_asc(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(
            repo="heimgewebe/demo", sort="file", sort_dir="asc",
        )
        files = [i["file"] for i in result["items"]]
        self.assertEqual(files, sorted(files))

    @patch("lib.metrics.load_findings_snapshots")
    def test_sort_severity_desc_is_default(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo")
        items = result["items"]
        self.assertEqual(items[0]["severity"], "critical")

    @patch("lib.metrics.load_findings_snapshots")
    def test_invalid_sort_field_falls_back(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(
            repo="heimgewebe/demo", sort="bogus",
        )
        items = result["items"]
        self.assertEqual(items[0]["severity"], "critical")

    @patch("lib.metrics.load_findings_snapshots")
    def test_invalid_sort_dir_falls_back_to_desc(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(
            repo="heimgewebe/demo", sort_dir="bogus",
        )
        items = result["items"]
        self.assertEqual(items[0]["severity"], "critical")

    @patch("lib.metrics.load_findings_snapshots")
    def test_filter_returns_empty_on_no_match(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(
            repo="heimgewebe/demo", severity="nonexistent",
        )
        self.assertEqual(result["items"], [])

    @patch("lib.metrics.load_findings_snapshots")
    def test_multi_severity_filter(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(
            repo="heimgewebe/demo", severity="error,critical",
        )
        self.assertEqual(len(result["items"]), 3)
        severities = {i["severity"] for i in result["items"]}
        self.assertEqual(severities, {"error", "critical"})

    @patch("apps.api.main._collect_events", return_value=[])
    @patch("lib.metrics.load_findings_snapshots", return_value=[])
    def test_empty_snapshot_returns_empty_shape(self, mock_load, mock_events):
        from apps.api import main as api_main

        result = api_main.repo_findings_detail(repo="heimgewebe/missing")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["count"], 0)


if __name__ == "__main__":
    unittest.main()

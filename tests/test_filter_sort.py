"""Tests for filter_and_sort_items, summarize_files_for_items (lib/metrics)
and the API filter/sort query parameters on /repos/findings/detail (Milestone 6.3)."""

import unittest
from unittest.mock import patch

from lib.metrics import filter_and_sort_items, summarize_files_for_items


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


# ---------------------------------------------------------------------------
# Tests for summarize_files_for_items helper
# ---------------------------------------------------------------------------
class TestSummarizeFilesForItems(unittest.TestCase):
    """Unit tests for ``summarize_files_for_items``."""

    def test_groups_items_by_file(self):
        items = [
            {"file": "a.py", "severity": "error"},
            {"file": "a.py", "severity": "warning"},
            {"file": "b.py", "severity": "critical"},
        ]
        result = summarize_files_for_items(items)
        self.assertEqual(len(result), 2)
        files = {e["file"]: e for e in result}
        self.assertEqual(files["a.py"]["count"], 2)
        self.assertEqual(files["b.py"]["count"], 1)

    def test_top_severity_per_file(self):
        items = [
            {"file": "a.py", "severity": "warning"},
            {"file": "a.py", "severity": "error"},
            {"file": "b.py", "severity": "info"},
        ]
        result = summarize_files_for_items(items)
        files = {e["file"]: e for e in result}
        self.assertEqual(files["a.py"]["topSeverity"], "error")
        self.assertEqual(files["b.py"]["topSeverity"], "info")

    def test_sorted_alphabetically(self):
        items = [
            {"file": "z.py", "severity": "info"},
            {"file": "a.py", "severity": "warning"},
            {"file": "m.py", "severity": "error"},
        ]
        result = summarize_files_for_items(items)
        self.assertEqual([e["file"] for e in result], ["a.py", "m.py", "z.py"])

    def test_items_without_file_are_skipped(self):
        items = [
            {"severity": "error"},
            {"file": "", "severity": "warning"},
            {"file": "real.py", "severity": "critical"},
        ]
        result = summarize_files_for_items(items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["file"], "real.py")

    def test_empty_items_returns_empty(self):
        self.assertEqual(summarize_files_for_items([]), [])


# ---------------------------------------------------------------------------
# Tests for consistent API view (files/count/deduped match filtered items)
# ---------------------------------------------------------------------------
class TestApiConsistentFilteredView(unittest.TestCase):
    """Verify that files, count, and deduped are always consistent with
    the filtered items returned by /repos/findings/detail."""

    # Snapshot with 5 items across 4 files; raw count/deduped deliberately
    # differ to confirm they are NOT passed through unchanged.
    SNAPSHOT = {
        "repo": "heimgewebe/demo",
        "ts": "2026-03-30T10:00:00+00:00",
        "count": 99,   # intentionally does not match len(items)
        "deduped": 88, # intentionally does not match len(items)
        "files": [
            {"file": "a.py", "count": 2, "topSeverity": "error"},
            {"file": "b.py", "count": 1, "topSeverity": "critical"},
            {"file": "c.py", "count": 1, "topSeverity": "info"},
            {"file": "d.py", "count": 1, "topSeverity": "warning"},
        ],
        "items": [
            {"severity": "warning", "category": "style",          "file": "a.py", "line": 1,  "message": "trailing space"},
            {"severity": "error",   "category": "security",       "file": "b.py", "line": 5,  "message": "sql injection"},
            {"severity": "critical","category": "correctness",    "file": "c.py", "line": 10, "message": "null deref"},
            {"severity": "info",    "category": "maintainability","file": "d.py", "line": 2,  "message": "unused import"},
            {"severity": "error",   "category": "style",          "file": "a.py", "line": 20, "message": "long line"},
        ],
    }

    @patch("lib.metrics.load_findings_snapshots")
    def test_no_filter_files_rebuilt_from_items(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo")
        # files is rebuilt from items, not copied from snapshot verbatim
        returned_files = {e["file"] for e in result["files"]}
        self.assertEqual(returned_files, {"a.py", "b.py", "c.py", "d.py"})

    @patch("lib.metrics.load_findings_snapshots")
    def test_no_filter_count_deduped_match_items_length(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo")
        self.assertEqual(result["count"], len(result["items"]))
        self.assertEqual(result["deduped"], len(result["items"]))

    @patch("lib.metrics.load_findings_snapshots")
    def test_filter_files_only_contain_matched_files(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo", severity="error")
        # Only a.py and b.py have error-severity items
        returned_files = {e["file"] for e in result["files"]}
        self.assertEqual(returned_files, {"a.py", "b.py"})
        # c.py (critical) and d.py (info) must be absent
        self.assertNotIn("c.py", returned_files)
        self.assertNotIn("d.py", returned_files)

    @patch("lib.metrics.load_findings_snapshots")
    def test_filter_count_deduped_match_filtered_items(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo", severity="error")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["deduped"], 2)

    @patch("lib.metrics.load_findings_snapshots")
    def test_filter_no_match_gives_empty_consistent_payload(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        result = api_main.repo_findings_detail(repo="heimgewebe/demo", severity="nonexistent")
        self.assertEqual(result["items"], [])
        self.assertEqual(result["files"], [])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["deduped"], 0)

    @patch("lib.metrics.load_findings_snapshots")
    def test_filter_file_count_matches_filtered_items(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        # a.py has 2 error items (warning + error), but only 1 is actually "error"
        result = api_main.repo_findings_detail(repo="heimgewebe/demo", severity="error")
        files = {e["file"]: e for e in result["files"]}
        # a.py: 1 error item ("long line"), b.py: 1 error item ("sql injection")
        self.assertEqual(files["a.py"]["count"], 1)
        self.assertEqual(files["b.py"]["count"], 1)

    @patch("lib.metrics.load_findings_snapshots")
    def test_filter_top_severity_per_file_recalculated(self, mock_load):
        from apps.api import main as api_main

        mock_load.return_value = [self.SNAPSHOT]
        # Filter to only "warning": a.py gets warning, rest disappear
        result = api_main.repo_findings_detail(repo="heimgewebe/demo", severity="warning")
        self.assertEqual(len(result["files"]), 1)
        self.assertEqual(result["files"][0]["file"], "a.py")
        self.assertEqual(result["files"][0]["topSeverity"], "warning")


if __name__ == "__main__":
    unittest.main()

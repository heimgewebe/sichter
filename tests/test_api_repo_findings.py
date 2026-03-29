import unittest
from unittest.mock import patch

from apps.api import main as api_main


class TestApiRepoFindings(unittest.TestCase):
    @patch("lib.metrics.load_metrics")
    def test_repos_findings_returns_latest_snapshot_per_repo(self, mock_load_metrics):
        mock_load_metrics.return_value = [
            {
                "repo": "heimgewebe/a",
                "findings_count": 2,
                "findings_by_severity": {"warning": 2},
                "timestamp": "2026-03-25T10:00:00+00:00",
            },
            {
                "repo": "heimgewebe/a",
                "findings_count": 1,
                "findings_by_severity": {"error": 1},
                "timestamp": "2026-03-26T10:00:00+00:00",
            },
            {
                "repo": "heimgewebe/b",
                "findings_count": 0,
                "findings_by_severity": {},
                "timestamp": "2026-03-26T11:00:00+00:00",
            },
        ]

        result = api_main.repos_findings(n=50_000)

        mock_load_metrics.assert_called_once_with(n=10_000)
        self.assertEqual(
            result,
            {
                "repos": [
                    {
                        "name": "heimgewebe/a",
                        "findingsCount": 1,
                        "findingsBySeverity": {"error": 1},
                        "topSeverity": "error",
                        "lastReviewedAt": "2026-03-26T10:00:00+00:00",
                    },
                    {
                        "name": "heimgewebe/b",
                        "findingsCount": 0,
                        "findingsBySeverity": {},
                        "topSeverity": "ok",
                        "lastReviewedAt": "2026-03-26T11:00:00+00:00",
                    },
                ]
            },
        )

    @patch("lib.metrics.load_findings_snapshots")
    def test_repo_findings_detail_returns_latest_snapshot(self, mock_load_snapshots):
        mock_load_snapshots.return_value = [
            {
                "repo": "heimgewebe/a",
                "ts": "2026-03-25T10:00:00+00:00",
                "count": 2,
                "deduped": 1,
                "files": [{"file": "a.py", "count": 1, "topSeverity": "warning"}],
                "items": [{"severity": "warning", "category": "correctness", "file": "a.py", "line": 10, "message": "first"}],
            },
            {
                "repo": "heimgewebe/a",
                "ts": "2026-03-26T10:00:00+00:00",
                "count": 3,
                "deduped": 2,
                "files": [{"file": "b.py", "count": 2, "topSeverity": "error"}],
                "items": [{"severity": "error", "category": "security", "file": "b.py", "line": 4, "message": "latest"}],
            },
        ]

        result = api_main.repo_findings_detail(repo="heimgewebe/a", n=50_000)

        mock_load_snapshots.assert_called_once_with(n=10_000)
        self.assertEqual(result["repo"], "heimgewebe/a")
        self.assertEqual(result["count"], 3)
        self.assertEqual(result["deduped"], 2)
        self.assertEqual(result["files"][0]["file"], "b.py")
        self.assertEqual(result["items"][0]["message"], "latest")

    @patch("lib.metrics.load_findings_snapshots", return_value=[])
    def test_repo_findings_detail_returns_empty_shape_when_missing(self, mock_load_snapshots):
        result = api_main.repo_findings_detail(repo="heimgewebe/missing")

        mock_load_snapshots.assert_called_once_with(n=500)
        self.assertEqual(
            result,
            {
                "repo": "heimgewebe/missing",
                "ts": None,
                "count": 0,
                "deduped": 0,
                "files": [],
                "items": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
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


if __name__ == "__main__":
    unittest.main()
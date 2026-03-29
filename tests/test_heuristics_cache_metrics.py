"""Tests for lib/heuristics, lib/cache, and lib/metrics."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from lib.cache import cache_get, cache_set, make_check_key, policy_hash
from lib.findings import Finding
from lib.heuristics.drift import _parse_requirements, _parse_pyproject_deps, run_drift_check
from lib.heuristics.hotspots import run_hotspot_check
from lib.heuristics.redundancy import run_redundancy_check
from lib.metrics import (
    ReviewMetrics,
    aggregate_metrics,
    build_findings_snapshot,
    detect_anomalies,
    latest_findings_snapshot_for_repo,
    latest_repo_findings,
    load_findings_snapshots,
    load_metrics,
    record_findings_snapshot,
    record_metrics,
    review_quality_stats,
    trends_over_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _noop_log(msg: str) -> None:
    pass


# ---------------------------------------------------------------------------
# Hotspot tests
# ---------------------------------------------------------------------------

class TestHotspots(unittest.TestCase):
    def test_no_churn_returns_empty(self):
        def run_cmd(*a, **kw):
            return _Result(stdout="")
        findings = run_hotspot_check(
            repo_dir=Path("/repo"),
            files=None,
            checks_cfg={"hotspots": {"enabled": True, "churn_threshold": 5}},
            run_cmd=run_cmd,
            log=_noop_log,
        )
        self.assertEqual(findings, [])

    def test_detects_hot_file(self):
        # Simulate git log output with 12 occurrences of the same file.
        git_output = "\n".join(["src/main.py"] * 12 + [""])
        def run_cmd(*a, **kw):
            return _Result(stdout=git_output)
        findings = run_hotspot_check(
            repo_dir=Path("/repo"),
            files=None,
            checks_cfg={"hotspots": {"enabled": True, "churn_threshold": 10}},
            run_cmd=run_cmd,
            log=_noop_log,
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].file, "src/main.py")
        self.assertEqual(findings[0].category, "maintainability")
        self.assertEqual(findings[0].tool, "hotspots")

    def test_severity_bands(self):
        git_output = "\n".join(["hot.py"] * 32)
        def run_cmd(*a, **kw):
            return _Result(stdout=git_output)
        findings = run_hotspot_check(
            repo_dir=Path("/repo"),
            files=None,
            checks_cfg={"hotspots": {"enabled": True, "churn_threshold": 5}},
            run_cmd=run_cmd,
            log=_noop_log,
        )
        self.assertEqual(findings[0].severity, "error")

    def test_disabled_by_policy(self):
        run_cmd = MagicMock()
        findings = run_hotspot_check(
            repo_dir=Path("/repo"),
            files=None,
            checks_cfg={"hotspots": False},
            run_cmd=run_cmd,
            log=_noop_log,
        )
        self.assertEqual(findings, [])
        run_cmd.assert_not_called()

    def test_filters_to_changed_files(self):
        git_output = "src/main.py\nother.py\n" * 10
        def run_cmd(*a, **kw):
            return _Result(stdout=git_output)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            target = repo / "src" / "main.py"
            target.parent.mkdir(parents=True)
            target.write_text("")
            findings = run_hotspot_check(
                repo_dir=repo,
                files=[target],
                checks_cfg={"hotspots": {"enabled": True, "churn_threshold": 5}},
                run_cmd=run_cmd,
                log=_noop_log,
            )
        # Only src/main.py should appear (other.py is not in the changed list)
        self.assertTrue(all("main.py" in f.file for f in findings))


# ---------------------------------------------------------------------------
# Drift tests
# ---------------------------------------------------------------------------

class TestDrift(unittest.TestCase):
    def test_parses_requirements_txt(self):
        text = "requests==2.28.0\nnumpy>=1.24\n# comment\n"
        result = _parse_requirements(text)
        self.assertIn("requests", result)
        self.assertIn("numpy", result)

    def test_parses_pyproject_deps(self):
        text = """\
[project]
dependencies = [
  "requests>=2.0",
  "numpy==1.24",
]
"""
        result = _parse_pyproject_deps(text)
        self.assertIn("requests", result)
        self.assertIn("numpy", result)

    def test_detects_version_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pyproject.toml").write_text(
                '[project]\ndependencies = [\n  "requests>=2.0",\n]\n',
                encoding="utf-8",
            )
            (repo / "requirements.txt").write_text(
                "requests==2.28.0\n", encoding="utf-8"
            )
            findings = run_drift_check(
                repo_dir=repo,
                checks_cfg={"drift": {"enabled": True}},
                log=_noop_log,
            )
        self.assertTrue(
            any("requests" in f.message for f in findings),
            f"Expected drift finding for 'requests', got: {[f.message for f in findings]}",
        )

    def test_disabled_returns_empty(self):
        findings = run_drift_check(
            repo_dir=Path("/no-such-dir"),
            checks_cfg={"drift": False},
            log=_noop_log,
        )
        self.assertEqual(findings, [])

    def test_parses_requirements_with_extras(self):
        """Extras like requests[security]==2.0 must not lose the version spec."""
        text = "requests[security]==2.0\nboto3[crt]>=1.20\n"
        result = _parse_requirements(text)
        self.assertIn("requests", result)
        self.assertEqual(result["requests"], "==2.0")
        self.assertIn("boto3", result)
        self.assertEqual(result["boto3"], ">=1.20")

    def test_detects_drift_for_package_with_extras(self):
        """Drift detection must work correctly when requirements.txt uses extras."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "pyproject.toml").write_text(
                '[project]\ndependencies = [\n  "requests>=2.0",\n]\n',
                encoding="utf-8",
            )
            (repo / "requirements.txt").write_text(
                "requests[security]==2.28.0\n", encoding="utf-8"
            )
            findings = run_drift_check(
                repo_dir=repo,
                checks_cfg={"drift": {"enabled": True}},
                log=_noop_log,
            )
        self.assertTrue(
            any("requests" in f.message for f in findings),
            f"Expected drift finding for 'requests', got: {[f.message for f in findings]}",
        )

# ---------------------------------------------------------------------------
# Redundancy tests
# ---------------------------------------------------------------------------

class TestRedundancy(unittest.TestCase):
    def test_detects_duplicate_block(self):
        block = "\n".join(f"x_{i} = value_{i}" for i in range(8))
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "a.py").write_text(block + "\n", encoding="utf-8")
            (repo / "b.py").write_text(block + "\n", encoding="utf-8")
            findings = run_redundancy_check(
                repo_dir=repo,
                files=None,
                checks_cfg={"redundancy": {"enabled": True, "threshold": 2, "block_size": 6}},
                log=_noop_log,
            )
        self.assertTrue(len(findings) >= 1)
        self.assertEqual(findings[0].category, "maintainability")
        self.assertEqual(findings[0].severity, "question")

    def test_disabled_by_default(self):
        findings = run_redundancy_check(
            repo_dir=Path("/repo"),
            files=None,
            checks_cfg={},  # no redundancy key → default disabled
            log=_noop_log,
        )
        self.assertEqual(findings, [])

    def test_no_duplicates_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
            (repo / "b.py").write_text("a = 3\nb = 4\n", encoding="utf-8")
            findings = run_redundancy_check(
                repo_dir=repo,
                files=None,
                checks_cfg={"redundancy": {"enabled": True}},
                log=_noop_log,
            )
        self.assertEqual(findings, [])

    def test_invalid_block_size_falls_back_to_default(self):
        """Non-integer block_size must not crash; should fall back to default."""
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            findings = run_redundancy_check(
                repo_dir=repo,
                files=None,
                checks_cfg={"redundancy": {"enabled": True, "block_size": "bad", "threshold": 2}},
                log=logs.append,
            )
        self.assertEqual(findings, [])
        self.assertTrue(any("block_size" in m for m in logs))

    def test_zero_block_size_clamped_to_one(self):
        """block_size=0 must be clamped to 1 and produce a log message."""
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            run_redundancy_check(
                repo_dir=repo,
                files=None,
                checks_cfg={"redundancy": {"enabled": True, "block_size": 0}},
                log=logs.append,
            )
        self.assertTrue(any("block_size" in m for m in logs))

    def test_threshold_one_clamped_to_two(self):
        """threshold=1 must be clamped to 2 and produce a log message."""
        logs: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            run_redundancy_check(
                repo_dir=repo,
                files=None,
                checks_cfg={"redundancy": {"enabled": True, "threshold": 1}},
                log=logs.append,
            )
        self.assertTrue(any("threshold" in m for m in logs))

    def test_absolute_path_outside_repo_dir_does_not_crash(self):
        """Absolute paths not under repo_dir must fall back to str(filepath)."""
        with tempfile.TemporaryDirectory() as tmp1, \
             tempfile.TemporaryDirectory() as tmp2:
            repo = Path(tmp1)
            outside = Path(tmp2) / "outside.py"
            block = "\n".join(f"x_{i} = value_{i}" for i in range(8))
            outside.write_text(block + "\n", encoding="utf-8")
            # Pass an absolute path that is NOT under repo_dir
            findings = run_redundancy_check(
                repo_dir=repo,
                files=[outside],
                checks_cfg={"redundancy": {"enabled": True, "threshold": 2, "block_size": 6}},
                log=_noop_log,
            )
        # Should not raise; findings may be empty (only one copy of the block)
        self.assertIsInstance(findings, list)


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

class TestCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patcher = patch("lib.cache.CACHE_DIR", Path(self._tmp.name))
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def test_cache_miss_returns_none(self):
        # Use a randomized key to avoid any cross-run state
        key = f"nonexistent-key-{time.time_ns()}"
        result = cache_get(key)
        self.assertIsNone(result)

    def test_cache_set_and_get(self):
        key = f"test-key-{time.time()}"
        payload = {"findings": [{"severity": "warning", "file": "foo.py"}]}
        cache_set(key, payload)
        result = cache_get(key)
        self.assertIsNotNone(result)
        self.assertEqual(result["findings"][0]["file"], "foo.py")

    def test_cache_ttl_expiry(self):
        key = f"ttl-key-{time.time()}"
        cache_set(key, {"x": 1})
        # TTL of 0 seconds should immediately expire
        result = cache_get(key, ttl_seconds=0)
        self.assertIsNone(result)

    def test_make_check_key_is_stable(self):
        k1 = make_check_key("myrepo", "abc123", "ruff", "polhash")
        k2 = make_check_key("myrepo", "abc123", "ruff", "polhash")
        self.assertEqual(k1, k2)

    def test_policy_hash_is_deterministic(self):
        checks = {"ruff": True, "shellcheck": False}
        excludes = ["**/.venv/**"]
        h1 = policy_hash(checks, excludes)
        h2 = policy_hash(checks, excludes)
        self.assertEqual(h1, h2)

    def test_policy_hash_differs_on_change(self):
        h1 = policy_hash({"ruff": True}, [])
        h2 = policy_hash({"ruff": False}, [])
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# Metrics tests
# ---------------------------------------------------------------------------

class TestMetrics(unittest.TestCase):
    def test_record_and_load(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = Path(tf.name)

        metrics = ReviewMetrics(
            repo="myrepo",
            duration_seconds=3.14,
            findings_count=5,
            findings_by_severity={"warning": 3, "error": 2},
            llm_tokens_used=150,
            cache_hits=1,
            prs_created=1,
        )
        record_metrics(metrics, reviews_file=path)
        records = load_metrics(n=10, reviews_file=path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["repo"], "myrepo")
        self.assertEqual(records[0]["prs_created"], 1)
        path.unlink(missing_ok=True)

    def test_aggregate_empty(self):
        result = aggregate_metrics([])
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["total_findings"], 0)
        self.assertEqual(result["total_prs"], 0)
        self.assertEqual(result["total_tokens"], 0)
        self.assertEqual(result["total_cache_hits"], 0)
        self.assertEqual(result["avg_duration_seconds"], 0.0)
        self.assertEqual(result["findings_by_severity"], {})
        self.assertEqual(result["repos"], [])

    def test_aggregate_totals(self):
        records = [
            {
                "repo": "r1",
                "findings_count": 4,
                "prs_created": 1,
                "llm_tokens_used": 100,
                "cache_hits": 0,
                "duration_seconds": 2.0,
                "findings_by_severity": {"warning": 3, "error": 1},
            },
            {
                "repo": "r2",
                "findings_count": 2,
                "prs_created": 0,
                "llm_tokens_used": 50,
                "cache_hits": 1,
                "duration_seconds": 1.0,
                "findings_by_severity": {"warning": 2},
            },
        ]
        summary = aggregate_metrics(records)
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["total_findings"], 6)
        self.assertEqual(summary["total_prs"], 1)
        self.assertEqual(summary["total_tokens"], 150)
        self.assertEqual(summary["total_cache_hits"], 1)
        self.assertAlmostEqual(summary["avg_duration_seconds"], 1.5)
        self.assertEqual(summary["findings_by_severity"]["warning"], 5)
        self.assertEqual(summary["findings_by_severity"]["error"], 1)
        self.assertIn("r1", summary["repos"])
        self.assertIn("r2", summary["repos"])

    def test_load_nonexistent_file_returns_empty(self):
        records = load_metrics(reviews_file=Path("/no/such/file.jsonl"))
        self.assertEqual(records, [])

    def test_load_metrics_respects_n_limit(self):
        """load_metrics(n=2) must return only the last 2 records."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, mode="w") as tf:
            for i in range(5):
                tf.write(json.dumps({"repo": f"r{i}", "findings_count": i,
                                     "prs_created": 0, "llm_tokens_used": 0,
                                     "cache_hits": 0, "duration_seconds": 1.0,
                                     "findings_by_severity": {}}) + "\n")
            path = Path(tf.name)
        try:
            records = load_metrics(n=2, reviews_file=path)
            self.assertEqual(len(records), 2)
            # Should be the last two written entries (r3, r4)
            self.assertEqual(records[0]["repo"], "r3")
            self.assertEqual(records[1]["repo"], "r4")
        finally:            path.unlink(missing_ok=True)

    def test_latest_repo_findings_uses_latest_snapshot_per_repo(self):
        records = [
            {
                "repo": "r1",
                "findings_count": 3,
                "findings_by_severity": {"warning": 3},
                "timestamp": "2026-03-25T10:00:00+00:00",
            },
            {
                "repo": "r2",
                "findings_count": 0,
                "findings_by_severity": {},
                "timestamp": "2026-03-25T11:00:00+00:00",
            },
            {
                "repo": "r1",
                "findings_count": 1,
                "findings_by_severity": {"error": 1},
                "timestamp": "2026-03-26T09:00:00+00:00",
            },
        ]

        summary = latest_repo_findings(records)

        self.assertEqual(len(summary), 2)
        self.assertEqual(summary[0]["name"], "r1")
        self.assertEqual(summary[0]["findingsCount"], 1)
        self.assertEqual(summary[0]["findingsBySeverity"], {"error": 1})
        self.assertEqual(summary[0]["topSeverity"], "error")
        self.assertEqual(summary[0]["lastReviewedAt"], "2026-03-26T09:00:00+00:00")
        self.assertEqual(summary[1]["name"], "r2")
        self.assertEqual(summary[1]["topSeverity"], "ok")

    def test_latest_repo_findings_marks_critical_as_top_severity(self):
        records = [
            {
                "repo": "r-critical",
                "findings_count": 1,
                "findings_by_severity": {"critical": 1},
                "timestamp": "2026-03-26T10:00:00+00:00",
            },
        ]

        summary = latest_repo_findings(records)

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["name"], "r-critical")
        self.assertEqual(summary[0]["topSeverity"], "critical")

    def test_latest_repo_findings_severity_priority_prefers_critical(self):
        records = [
            {
                "repo": "r-mixed",
                "findings_count": 4,
                "findings_by_severity": {
                    "warning": 2,
                    "error": 1,
                    "critical": 1,
                },
                "timestamp": "2026-03-26T10:05:00+00:00",
            },
        ]

        summary = latest_repo_findings(records)

        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["name"], "r-mixed")
        self.assertEqual(summary[0]["topSeverity"], "critical")

    def test_build_findings_snapshot_groups_files_and_dedupes_items(self):
        findings = [
            Finding(
                severity="warning",
                category="correctness",
                file="src/a.py",
                line=10,
                message="duplicate",
                tool="ruff",
                rule_id="F401",
            ),
            Finding(
                severity="warning",
                category="correctness",
                file="src/a.py",
                line=10,
                message="duplicate",
                tool="ruff",
                rule_id="F401",
            ),
            Finding(
                severity="error",
                category="security",
                file="src/b.py",
                line=4,
                message="latest",
                tool="bandit",
                rule_id="B602",
                fix_available=True,
            ),
        ]

        snapshot = build_findings_snapshot("heimgewebe/a", findings, timestamp="2026-03-29T10:00:00+00:00")

        self.assertEqual(snapshot["repo"], "heimgewebe/a")
        self.assertEqual(snapshot["count"], 3)
        self.assertEqual(snapshot["deduped"], 2)
        self.assertEqual(snapshot["files"][0]["file"], "src/a.py")
        self.assertEqual(snapshot["files"][1]["topSeverity"], "error")
        self.assertEqual(snapshot["items"][0]["severity"], "error")
        self.assertTrue(snapshot["items"][0]["fixAvailable"])

    def test_record_and_load_findings_snapshots(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = Path(tf.name)

        findings = [
            Finding(
                severity="info",
                category="maintainability",
                file="src/a.py",
                line=1,
                message="note",
                tool="hotspots",
            )
        ]

        record_findings_snapshot("heimgewebe/a", findings, findings_file=path, timestamp="2026-03-29T10:00:00+00:00")
        records = load_findings_snapshots(n=10, findings_file=path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["repo"], "heimgewebe/a")
        self.assertEqual(records[0]["items"][0]["message"], "note")
        path.unlink(missing_ok=True)

    def test_latest_findings_snapshot_for_repo_returns_empty_shape(self):
        result = latest_findings_snapshot_for_repo("heimgewebe/missing", [])

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




# ---------------------------------------------------------------------------
# trends_over_time tests
# ---------------------------------------------------------------------------

class TestTrendsOverTime(unittest.TestCase):
    def test_empty_records_returns_continuous_zero_series(self):
        result = trends_over_time([], days=5)
        self.assertEqual(len(result), 5)
        self.assertTrue(all(r["findings"] == 0 for r in result))

    def test_invalid_timestamps_are_ignored(self):
        records = [
            {"timestamp": "not-a-date", "findings_count": 10},
            {"timestamp": "", "findings_count": 5},
            {"timestamp": None, "findings_count": 3},
        ]
        result = trends_over_time(records, days=7)
        self.assertEqual(len(result), 7)
        self.assertTrue(all(r["findings"] == 0 for r in result))

    def test_counts_are_aggregated_by_day(self):
        from datetime import date, timedelta
        today = date.today().isoformat()
        records = [
            {"timestamp": f"{today}T10:00:00", "findings_count": 3},
            {"timestamp": f"{today}T14:00:00", "findings_count": 2},
        ]
        result = trends_over_time(records, days=7)
        today_entry = next(r for r in result if r["date"] == today)
        self.assertEqual(today_entry["findings"], 5)

    def test_records_outside_window_are_excluded(self):
        from datetime import date, timedelta
        old_day = (date.today() - timedelta(days=60)).isoformat()
        records = [{"timestamp": f"{old_day}T10:00:00", "findings_count": 99}]
        result = trends_over_time(records, days=7)
        self.assertTrue(all(r["findings"] == 0 for r in result))


# ---------------------------------------------------------------------------
# detect_anomalies tests
# ---------------------------------------------------------------------------

class TestDetectAnomalies(unittest.TestCase):
    def _make_records(self, repo: str, day: str, count: int) -> dict:
        return {"repo": repo, "timestamp": f"{day}T12:00:00", "findings_count": count}

    def test_empty_records_returns_empty(self):
        self.assertEqual(detect_anomalies([]), [])

    def test_no_alert_when_baseline_is_absent(self):
        # Only one day of data – no baseline window to compare against.
        records = [self._make_records("repo-a", "2026-03-28", 100)]
        alerts = detect_anomalies(records, window=7)
        self.assertEqual(alerts, [])

    def test_baseline_window_covers_exactly_window_days(self):
        # latest_day = 2026-03-28 (day 0)
        # window=3: baseline should include days -1, -2, -3 (i.e. 25,26,27)
        # day -4 (2026-03-24) must be excluded from the baseline.
        latest = "2026-03-28"
        records = [
            self._make_records("r", "2026-03-24", 1),  # outside window → excluded
            self._make_records("r", "2026-03-25", 0),
            self._make_records("r", "2026-03-26", 0),
            self._make_records("r", "2026-03-27", 0),
            self._make_records("r", latest, 1000),
        ]
        alerts = detect_anomalies(records, window=3, threshold_factor=2.0)
        # With all 3 baseline days at 0, avg=0 → no alert (avg <= 0 guard).
        # Ensure the day at -4 is not included; if it were, avg=1/4=0.25,
        # ratio=4000 → alert would fire. So no alert confirms the exclusion.
        self.assertEqual(alerts, [])

    def test_alert_fires_on_real_spike(self):
        records = [
            self._make_records("r", "2026-03-25", 2),
            self._make_records("r", "2026-03-26", 2),
            self._make_records("r", "2026-03-27", 2),
            self._make_records("r", "2026-03-28", 20),  # spike
        ]
        alerts = detect_anomalies(records, window=3, threshold_factor=2.0)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["repo"], "r")
        self.assertGreaterEqual(alerts[0]["ratio"], 2.0)

    def test_no_alert_below_threshold(self):
        records = [
            self._make_records("r", "2026-03-25", 2),
            self._make_records("r", "2026-03-26", 2),
            self._make_records("r", "2026-03-27", 2),
            self._make_records("r", "2026-03-28", 4),  # ratio = 2.0, not >= 2.5
        ]
        alerts = detect_anomalies(records, window=3, threshold_factor=2.5)
        self.assertEqual(alerts, [])


# ---------------------------------------------------------------------------
# review_quality_stats tests
# ---------------------------------------------------------------------------

class TestReviewQualityStats(unittest.TestCase):
    def test_empty_records_returns_zeros(self):
        result = review_quality_stats([])
        self.assertEqual(result["record_count"], 0)
        self.assertEqual(result["pr_yield_rate"], 0.0)
        self.assertEqual(result["avg_tokens_per_finding"], 0.0)

    def test_zero_findings_returns_zero_rates(self):
        records = [
            {
                "repo": "r1",
                "findings_count": 0,
                "prs_created": 3,
                "llm_tokens_used": 500,
                "cache_hits": 1,
                "findings_by_severity": {},
            }
        ]
        result = review_quality_stats(records)
        self.assertEqual(result["pr_yield_rate"], 0.0)
        self.assertEqual(result["avg_tokens_per_finding"], 0.0)

    def test_nonzero_findings_divides_correctly(self):
        records = [
            {
                "repo": "r1",
                "findings_count": 4,
                "prs_created": 2,
                "llm_tokens_used": 200,
                "cache_hits": 0,
                "findings_by_severity": {"warning": 4},
            }
        ]
        result = review_quality_stats(records)
        self.assertEqual(result["pr_yield_rate"], round(2 / 4, 4))
        self.assertEqual(result["avg_tokens_per_finding"], round(200 / 4, 1))

    def test_cache_hit_rate_uses_run_count_not_findings(self):
        records = [
            {"repo": "r1", "findings_count": 0, "prs_created": 0, "llm_tokens_used": 0, "cache_hits": 1, "findings_by_severity": {}},
            {"repo": "r2", "findings_count": 0, "prs_created": 0, "llm_tokens_used": 0, "cache_hits": 1, "findings_by_severity": {}},
        ]
        result = review_quality_stats(records)
        self.assertEqual(result["cache_hit_rate"], 1.0)
        self.assertEqual(result["record_count"], 2)


if __name__ == "__main__":
    unittest.main()

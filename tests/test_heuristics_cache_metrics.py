"""Tests for lib/heuristics, lib/cache, and lib/metrics."""
from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from lib.cache import cache_get, cache_set, make_check_key, policy_hash
from lib.heuristics.drift import _parse_requirements, _parse_pyproject_deps, run_drift_check
from lib.heuristics.hotspots import run_hotspot_check
from lib.heuristics.redundancy import run_redundancy_check
from lib.metrics import ReviewMetrics, aggregate_metrics, load_metrics, record_metrics


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
        run_cmd = lambda *a, **kw: _Result(stdout="")
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
        run_cmd = lambda *a, **kw: _Result(stdout=git_output)
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
        run_cmd = lambda *a, **kw: _Result(stdout=git_output)
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
        run_cmd = lambda *a, **kw: _Result(stdout=git_output)
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

    def test_no_files_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings = run_drift_check(
                repo_dir=Path(tmp),
                checks_cfg={},
                log=_noop_log,
            )
        self.assertEqual(findings, [])


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


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------

class TestCache(unittest.TestCase):
    def test_cache_miss_returns_none(self):
        result = cache_get("nonexistent-key-xyz-abc-123")
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


if __name__ == "__main__":
    unittest.main()

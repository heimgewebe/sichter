from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from lib.cache import cache_get, cache_set, make_check_key, policy_hash
from lib.heuristics.drift import _parse_pyproject_deps, _parse_requirements, run_drift_check
from lib.heuristics.hotspots import run_hotspot_check
from lib.heuristics.redundancy import run_redundancy_check
from lib.metrics import ReviewMetrics, aggregate_metrics, load_metrics, record_metrics


class _Result:
  def __init__(self, returncode=0, stdout="", stderr=""):
    self.returncode = returncode
    self.stdout = stdout
    self.stderr = stderr


class TestHeuristics(unittest.TestCase):
  def test_hotspot_detects_churn(self):
    result = run_hotspot_check(
      Path("/repo"),
      None,
      {"hotspots": {"enabled": True, "churn_threshold": 3}},
      lambda *_args, **_kwargs: _Result(stdout="src/a.py\nsrc/a.py\nsrc/a.py\n"),
      lambda _msg: None,
    )
    self.assertEqual(len(result), 1)
    self.assertEqual(result[0].file, "src/a.py")

  def test_parse_dependency_inputs(self):
    self.assertIn("requests", _parse_requirements("requests==2.31.0\n"))
    self.assertIn(
      "requests",
      _parse_pyproject_deps('[project]\ndependencies = ["requests>=2.0"]\n'),
    )

  def test_drift_detects_mismatch(self):
    with tempfile.TemporaryDirectory() as tmp:
      repo = Path(tmp)
      (repo / "pyproject.toml").write_text(
        '[project]\ndependencies = [\n  "requests>=2.0",\n]\n',
        encoding="utf-8",
      )
      (repo / "requirements.txt").write_text("requests==2.31.0\n", encoding="utf-8")
      findings = run_drift_check(repo, {"drift": {"enabled": True}}, lambda _msg: None)
    self.assertEqual(len(findings), 1)

  def test_redundancy_detects_duplicate_block(self):
    with tempfile.TemporaryDirectory() as tmp:
      repo = Path(tmp)
      block = "\n".join([f"line_{index} = {index}" for index in range(8)]) + "\n"
      (repo / "a.py").write_text(block, encoding="utf-8")
      (repo / "b.py").write_text(block, encoding="utf-8")
      findings = run_redundancy_check(
        repo,
        None,
        {"redundancy": {"enabled": True, "threshold": 2, "block_size": 6}},
        lambda _msg: None,
      )
    self.assertGreaterEqual(len(findings), 1)


class TestCache(unittest.TestCase):
  def test_cache_roundtrip(self):
    key = f"test-key-{time.time()}"
    cache_set(key, {"findings": [{"file": "demo.py"}]})
    payload = cache_get(key)
    self.assertIsNotNone(payload)
    self.assertEqual(payload["findings"][0]["file"], "demo.py")

  def test_cache_key_and_policy_hash(self):
    self.assertEqual(
      make_check_key("repo", "abc", "ruff", "hash"),
      make_check_key("repo", "abc", "ruff", "hash"),
    )
    self.assertNotEqual(policy_hash({"ruff": True}, []), policy_hash({"ruff": False}, []))


class TestMetrics(unittest.TestCase):
  def test_record_load_and_aggregate(self):
    with tempfile.TemporaryDirectory() as tmp:
      target = Path(tmp) / "reviews.jsonl"
      record_metrics(
        ReviewMetrics(
          repo="demo",
          duration_seconds=1.5,
          findings_count=2,
          findings_by_severity={"warning": 1, "error": 1},
          llm_tokens_used=20,
          cache_hits=1,
          prs_created=1,
        ),
        reviews_file=target,
      )
      records = load_metrics(reviews_file=target)
      summary = aggregate_metrics(records)
    self.assertEqual(len(records), 1)
    self.assertEqual(summary["total_findings"], 2)
    self.assertEqual(summary["total_prs"], 1)

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.api.main import Job, _enqueue
from apps.worker.run import get_sorted_jobs


class TestQueuePriority(unittest.TestCase):
  def test_job_model_defaults_priority_to_normal(self):
    job = Job(type="ScanChanged")
    self.assertEqual(job.priority, "normal")

  def test_job_model_accepts_high_priority(self):
    job = Job(type="ScanAll", priority="high")
    self.assertEqual(job.priority, "high")

  def test_get_sorted_jobs_prioritizes_high_then_normal_then_low(self):
    with tempfile.TemporaryDirectory() as tmp:
      queue_dir = Path(tmp)
      jobs = [
        ("1700000002-low.json", {"type": "ScanChanged", "priority": "low"}),
        ("1700000003-normal.json", {"type": "ScanChanged", "priority": "normal"}),
        ("1700000001-high.json", {"type": "ScanChanged", "priority": "high"}),
      ]
      for name, payload in jobs:
        (queue_dir / name).write_text(json.dumps(payload), encoding="utf-8")

      sorted_jobs = get_sorted_jobs(queue_dir)
      self.assertEqual([p.name for p in sorted_jobs], [
        "1700000001-high.json",
        "1700000003-normal.json",
        "1700000002-low.json",
      ])

  def test_enqueue_writes_priority_to_queue_file(self):
    """_enqueue() must persist the priority field so the worker can sort by it."""
    with tempfile.TemporaryDirectory() as tmp:
      queue_dir = Path(tmp)
      job = Job(type="ScanChanged", priority="high")

      with patch("apps.api.main.QUEUE", queue_dir):
        jid = _enqueue(job.model_dump())

      written = list(queue_dir.glob("*.json"))
      self.assertEqual(len(written), 1, "exactly one queue file should be written")

      data = json.loads(written[0].read_text(encoding="utf-8"))
      self.assertIn("priority", data, "priority key must be present in queue file")
      self.assertEqual(data["priority"], "high", "priority value must match submitted job")
      self.assertEqual(written[0].name, f"{jid}.json")

  def test_same_priority_preserves_fifo_order(self):
    """Within the same priority tier, older jobs (lower timestamp) must come first."""
    with tempfile.TemporaryDirectory() as tmp:
      queue_dir = Path(tmp)
      jobs = [
        ("1700000001-aaa.json", {"type": "ScanChanged", "priority": "normal"}),
        ("1700000002-bbb.json", {"type": "ScanChanged", "priority": "normal"}),
        ("1700000003-ccc.json", {"type": "ScanChanged", "priority": "normal"}),
      ]
      # Write in reverse order to prove sort is not insertion-order dependent
      for name, payload in reversed(jobs):
        (queue_dir / name).write_text(json.dumps(payload), encoding="utf-8")

      sorted_jobs = get_sorted_jobs(queue_dir)
      self.assertEqual([p.name for p in sorted_jobs], [
        "1700000001-aaa.json",
        "1700000002-bbb.json",
        "1700000003-ccc.json",
      ])


if __name__ == "__main__":
  unittest.main()

import json
import tempfile
import unittest
from pathlib import Path

from apps.api.main import Job
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


if __name__ == "__main__":
  unittest.main()

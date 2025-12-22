import json
from unittest.mock import patch

from apps.worker import run as worker_run
from apps.worker import sweep


def test_policy_load_treats_none_as_default(tmp_path):
  policy_path = tmp_path / "policy.yml"
  policy_path.write_text("auto_pr: null\nsweep_on_omnipull: null\n")

  with (
    patch("lib.config.get_policy_path", return_value=policy_path),
    patch("lib.config.load_yaml") as mock_load_yaml,
  ):
    mock_load_yaml.return_value = {"auto_pr": None, "sweep_on_omnipull": None}
    policy = worker_run.Policy.load()

  assert policy.auto_pr is True
  assert policy.sweep_on_omnipull is True


def test_write_job_defaults_auto_pr_when_none(tmp_path):
  policy = {"auto_pr": None, "org": "example"}

  with patch.object(sweep, "QUEUE_DIR", tmp_path):
    job_file = sweep.write_job(policy, "changed", "demo-repo")

  payload = json.loads(job_file.read_text(encoding="utf-8"))
  assert payload["auto_pr"] is True


def test_policy_bool_with_default_accepts_string_variants():
  true_values = ["true", "True", "1", "yes", "Y", "on"]
  false_values = ["false", "False", "0", "no", "N", "off"]

  for value in true_values:
    assert worker_run.Policy._bool_with_default(value, False) is True

  for value in false_values:
    assert worker_run.Policy._bool_with_default(value, True) is False


def test_policy_bool_with_default_logs_on_unknown_string():
  with patch("apps.worker.run.log") as mock_log:
    result = worker_run.Policy._bool_with_default("flase", True)

  mock_log.assert_called_once()
  message = mock_log.call_args[0][0]
  assert "flase" in message
  assert "Default=" in message
  assert result is True

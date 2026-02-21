from pathlib import Path

def test_omnicheck_remote_has_auth():
  script = Path("bin/omnicheck-remote")
  content = script.read_text()
  assert 'X-API-Key: ${SICHTER_API_KEY:-}' in content

def test_sweep_remote_has_auth():
  script = Path("bin/sweep-remote")
  content = script.read_text()
  assert 'X-API-Key: ${SICHTER_API_KEY:-}' in content

def test_secrets_env_example_has_api_key():
  example = Path("secrets.env.example")
  content = example.read_text()
  assert "SICHTER_API_KEY=" in content

import pytest
from apps.api.auth import check_api_key, ApiKeyError

def test_check_api_key_valid():
  # should not raise
  check_api_key("secret", "secret")

def test_check_api_key_mismatch():
  with pytest.raises(ApiKeyError) as excinfo:
    check_api_key("wrong", "secret")
  assert excinfo.value.kind == "invalid"
  assert "Invalid API Key" in str(excinfo.value)

def test_check_api_key_provided_missing():
  with pytest.raises(ApiKeyError) as excinfo:
    check_api_key(None, "secret")
  assert excinfo.value.kind == "missing"
  assert "API Key is missing" in str(excinfo.value)

def test_check_api_key_expected_missing():
  with pytest.raises(ApiKeyError) as excinfo:
    check_api_key("any", None)
  assert excinfo.value.kind == "not_configured"
  assert "API Key is not configured on server" in str(excinfo.value)

def test_check_api_key_both_missing():
  with pytest.raises(ApiKeyError) as excinfo:
    check_api_key(None, None)
  assert excinfo.value.kind == "not_configured"

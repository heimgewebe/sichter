import pytest
from apps.api.auth import check_api_key

def test_check_api_key_valid():
  # should not raise
  check_api_key("secret", "secret")

def test_check_api_key_mismatch():
  with pytest.raises(ValueError, match="Invalid API Key"):
    check_api_key("wrong", "secret")

def test_check_api_key_provided_missing():
  with pytest.raises(ValueError, match="API Key is missing"):
    check_api_key(None, "secret")

def test_check_api_key_expected_missing():
  with pytest.raises(ValueError, match="API Key is not configured on server"):
    check_api_key("any", None)

def test_check_api_key_both_missing():
  with pytest.raises(ValueError, match="API Key is not configured on server"):
    check_api_key(None, None)

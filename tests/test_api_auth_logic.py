import pytest
from apps.api.auth import check_api_key, ApiKeyError

def test_check_api_key_valid():
  # should not raise
  check_api_key("secret", "secret")

@pytest.mark.parametrize(
  "provided, expected, expected_kind, expected_message",
  [
    # Case: Server not configured (expected is None or empty)
    (None, None, "not_configured", "API Key is not configured on server"),
    ("", None, "not_configured", "API Key is not configured on server"),
    ("any", None, "not_configured", "API Key is not configured on server"),
    (None, "", "not_configured", "API Key is not configured on server"),
    ("", "", "not_configured", "API Key is not configured on server"),
    ("any", "", "not_configured", "API Key is not configured on server"),

    # Case: Provided key is missing (provided is None or empty)
    (None, "secret", "missing", "API Key is missing"),
    ("", "secret", "missing", "API Key is missing"),

    # Case: Invalid key (provided doesn't match expected)
    ("wrong", "secret", "invalid", "Invalid API Key"),
    ("secret ", "secret", "invalid", "Invalid API Key"),
    (" secret", "secret", "invalid", "Invalid API Key"),
  ],
)
def test_check_api_key_errors(provided, expected, expected_kind, expected_message):
  with pytest.raises(ApiKeyError) as excinfo:
    check_api_key(provided, expected)
  assert excinfo.value.kind == expected_kind
  assert expected_message in str(excinfo.value)

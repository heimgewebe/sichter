import hmac

class ApiKeyError(Exception):
  """Custom exception for API key validation errors."""
  def __init__(self, kind: str, message: str):
    self.kind = kind
    self.message = message
    super().__init__(message)

def check_api_key(provided: str | None, expected: str | None) -> None:
  """
  Core API key validation logic.
  Raises ApiKeyError if validation fails.
  Fail-closed: fails if expected key is not set.
  """
  if not expected:
    raise ApiKeyError("not_configured", "API Key is not configured on server")

  if not provided:
    raise ApiKeyError("missing", "API Key is missing")

  if not hmac.compare_digest(provided, expected):
    raise ApiKeyError("invalid", "Invalid API Key")

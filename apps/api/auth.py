def check_api_key(provided: str | None, expected: str | None) -> None:
  """
  Core API key validation logic.
  Raises ValueError if validation fails.
  Fail-closed: fails if expected key is not set.
  """
  if not expected:
    raise ValueError("API Key is not configured on server")

  if not provided:
    raise ValueError("API Key is missing")

  if provided != expected:
    raise ValueError("Invalid API Key")

"""Test suite for API auth logic (requires pytest).

NOTE (Test-Schuldenrest):
  This module contains pytest-native tests (parametrized, fixtures).
  While pytest is not available in the test environment, this file is
  intentionally kept in place (skipped via unittest) rather than migrated.
  
  Future work: Either install pytest or migrate tests to unittest style.
  See: docs/BLUEPRINT.md for test infrastructure roadmap.
"""
import sys
import unittest

try:
    import pytest
    _PYTEST_AVAILABLE = True
except ImportError:
    _PYTEST_AVAILABLE = False

@unittest.skipIf(not _PYTEST_AVAILABLE, "SKIP: pytest not available — requires pytest.parametrize (TEST-SCHULDENREST m3.2)")
class TestApiAuthLogic(unittest.TestCase):
    """Placeholder test class; actual tests require pytest (parametrized).
    
    The parametrized tests below check API key validation edge cases.
    They are NOT executed in unittest.discover() but defined for future pytest runs.
    """
    
    def test_placeholder(self):
        """Placeholder to avoid empty test suite."""
        pass

if _PYTEST_AVAILABLE:
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

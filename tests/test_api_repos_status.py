"""Tests for _build_repos_status() event-lookup semantics.

_build_repos_status() is a pure helper extracted from repos_status() so it can
be tested without a fastapi dependency.
"""
import sys
import unittest
from unittest.mock import MagicMock

# Stub third-party dependencies before importing apps.api.main so the module
# loads successfully in the test environment where fastapi/pydantic are absent.
for _mod in (
    "fastapi",
    "fastapi.security",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    "fastapi.responses",
    "fastapi.staticfiles",
    "pydantic",
):
    sys.modules.setdefault(_mod, MagicMock())

from apps.api.main import _build_repos_status  # noqa: E402


class TestBuildReposStatus(unittest.TestCase):
    """_build_repos_status() must use exact field matching, not substring search."""

    def _make_event(self, repo: str, kind: str = "commit") -> dict:
        """Build a minimal _collect_events entry as the worker would emit it."""
        payload = {"ts": "2026-03-26T10:00:00+00:00", "type": kind, "repo": repo}
        return {"line": "", "payload": payload, "ts": payload["ts"], "kind": None}

    def test_finds_exact_repo_event(self):
        """A matching event for the exact repo name is returned."""
        repo = "heimgewebe/myrepo"
        events = [self._make_event(repo)]

        result = _build_repos_status([repo], events)

        self.assertEqual(len(result["repos"]), 1)
        self.assertEqual(result["repos"][0]["name"], repo)
        self.assertIsNotNone(result["repos"][0]["lastEvent"])
        self.assertEqual(result["repos"][0]["lastEvent"]["payload"]["repo"], repo)

    def test_no_false_positive_via_substring(self):
        """Event for 'foo/barextra' must NOT match a lookup for 'foo/bar'."""
        target = "foo/bar"
        other = "foo/barextra"
        events = [self._make_event(other)]

        result = _build_repos_status([target], events)

        self.assertEqual(result["repos"][0]["name"], target)
        self.assertIsNone(result["repos"][0]["lastEvent"])

    def test_skips_event_with_non_dict_payload(self):
        """Events without a dict payload are ignored without error."""
        repo = "heimgewebe/myrepo"
        events = [{"line": "plain log line", "ts": None, "kind": None}]

        result = _build_repos_status([repo], events)

        self.assertIsNone(result["repos"][0]["lastEvent"])

    def test_returns_most_recent_of_multiple_matching_events(self):
        """When multiple events match the same repo, the last one is returned."""
        repo = "heimgewebe/myrepo"
        first = self._make_event(repo, "start")
        last = self._make_event(repo, "commit")
        last["payload"]["ts"] = "2026-03-27T10:00:00+00:00"
        events = [first, last]

        result = _build_repos_status([repo], events)

        self.assertEqual(result["repos"][0]["lastEvent"]["payload"]["type"], "commit")

    def test_no_events_returns_none_for_last_event(self):
        """When no events exist for a repo, lastEvent is None."""
        repo = "heimgewebe/myrepo"

        result = _build_repos_status([repo], [])

        self.assertIsNone(result["repos"][0]["lastEvent"])

    def test_multiple_repos_isolated(self):
        """Events for one repo do not bleed into another repo's lastEvent."""
        repo_a = "org/a"
        repo_b = "org/b"
        events = [self._make_event(repo_a)]

        result = _build_repos_status([repo_a, repo_b], events)

        repos_by_name = {r["name"]: r for r in result["repos"]}
        self.assertIsNotNone(repos_by_name[repo_a]["lastEvent"])
        self.assertIsNone(repos_by_name[repo_b]["lastEvent"])


if __name__ == "__main__":
    unittest.main()

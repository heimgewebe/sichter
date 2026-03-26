"""Tests for the LLM module: sanitize, prompts, review, factory."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.findings import Finding
from lib.llm.budget import ReviewBudget
from lib.llm.review import ReviewResult, Suggestion, parse_review_response
from lib.llm.sanitize import redact


class TestRedact(unittest.TestCase):
    def test_pem_private_key_is_redacted(self):
        text = (
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA1234...\n"
            "-----END RSA PRIVATE KEY-----"
        )
        result = redact(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("MIIEowIBAAKCAQEA1234", result)

    def test_jwt_token_is_redacted(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123def456ghi789jkl"
        result = redact(jwt)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", result)

    def test_env_style_secret_is_redacted(self):
        text = "API_KEY=supersecretvalue123"
        result = redact(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("supersecretvalue123", result)

    def test_quoted_password_is_redacted(self):
        text = 'password = "myS3cr3tPass"'
        result = redact(text)
        self.assertIn("[REDACTED]", result)
        self.assertNotIn("myS3cr3tPass", result)

    def test_normal_code_is_not_redacted(self):
        text = "def greet(name):\n    return f'Hello {name}'"
        result = redact(text)
        self.assertEqual(result, text)

    def test_short_value_not_redacted(self):
        # Values shorter than 6 chars should NOT be redacted (avoids false positives)
        text = "token=abc"
        result = redact(text)
        # Should not redact very short values
        self.assertNotIn("[REDACTED]", result)

    def test_extra_policy_pattern_is_redacted(self):
        text = "SENSITIVE_MARKER_42"
        result = redact(text, extra_patterns=[r"SENSITIVE_MARKER_\\d+"])
        self.assertEqual(result, "[REDACTED]")


class TestReviewBudget(unittest.TestCase):
    def _budget(self, tmpdir: str) -> ReviewBudget:
        return ReviewBudget(Path(tmpdir) / "budget.jsonl")

    def test_allows_until_limit_then_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = self._budget(tmp)
            now = 1_000_000.0

            self.assertTrue(budget.allow_review(2, now=now))
            budget.record_review("repo", 10, now=now)
            self.assertTrue(budget.allow_review(2, now=now + 1))
            budget.record_review("repo", 15, now=now + 2)
            self.assertFalse(budget.allow_review(2, now=now + 3))

    def test_entries_expire_after_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget = self._budget(tmp)
            now = 1_000_000.0
            budget.record_review("repo", 10, now=now)

            self.assertFalse(budget.allow_review(1, now=now + 3599))
            self.assertTrue(budget.allow_review(1, now=now + 3601))


class TestParseReviewResponse(unittest.TestCase):
    def _valid_json(self, **overrides) -> str:
        data = {
            "summary": "Alles gut.",
            "risk_overall": "low",
            "uncertainty": {"level": 0.1, "sources": [], "productive": False},
            "suggestions": [
                {
                    "theme": "correctness",
                    "recommendation": "Nutze f-strings.",
                    "risk": "low",
                    "why": "Lesbarkeit.",
                    "files": ["foo.py"],
                }
            ],
        }
        data.update(overrides)
        return json.dumps(data)

    def test_parses_valid_json(self):
        raw = self._valid_json()
        result = parse_review_response(raw, model="test-model", provider="ollama")
        self.assertIsInstance(result, ReviewResult)
        self.assertEqual(result.summary, "Alles gut.")
        self.assertEqual(result.risk_overall, "low")
        self.assertEqual(len(result.suggestions), 1)
        self.assertEqual(result.model, "test-model")
        self.assertEqual(result.provider, "ollama")

    def test_extracts_json_from_markdown_code_block(self):
        raw = f"```json\n{self._valid_json()}\n```"
        result = parse_review_response(raw)
        self.assertEqual(result.risk_overall, "low")
        self.assertEqual(result.summary, "Alles gut.")

    def test_extracts_json_from_text_with_preamble(self):
        raw = f"Hier ist meine Einschätzung:\n\n{self._valid_json()}\n\nEnde."
        result = parse_review_response(raw)
        self.assertEqual(result.risk_overall, "low")

    def test_unknown_risk_falls_back_to_medium(self):
        raw = self._valid_json(risk_overall="unknown_level")
        result = parse_review_response(raw)
        self.assertEqual(result.risk_overall, "medium")

    def test_suggestion_count_capped_at_3(self):
        suggestions = [
            {"theme": "style", "recommendation": f"Fix {i}", "risk": "low", "why": ".", "files": []}
            for i in range(10)
        ]
        raw = self._valid_json(suggestions=suggestions)
        result = parse_review_response(raw)
        self.assertLessEqual(len(result.suggestions), 3)

    def test_invalid_json_returns_fallback(self):
        result = parse_review_response("This is not JSON at all.")
        self.assertEqual(result.risk_overall, "medium")
        self.assertIn("parse_failure", result.uncertainty.get("sources", []))
        self.assertEqual(result.suggestions, [])

    def test_empty_string_returns_fallback(self):
        result = parse_review_response("")
        self.assertIn("parse_failure", result.uncertainty.get("sources", []))

    def test_tokens_used_stored(self):
        raw = self._valid_json()
        result = parse_review_response(raw, tokens_used=512)
        self.assertEqual(result.tokens_used, 512)


class TestReviewResultToPrSection(unittest.TestCase):
    def _make_result(self, risk="medium", suggestions=None) -> ReviewResult:
        return ReviewResult(
            summary="Kleiner Fehler gefunden.",
            risk_overall=risk,
            uncertainty={"level": 0.2, "sources": [], "productive": False},
            suggestions=suggestions or [],
            raw_response="{}",
            model="qwen2.5-coder:7b",
            provider="ollama",
        )

    def test_contains_risk_badge(self):
        section = self._make_result(risk="high").to_pr_section()
        self.assertIn("🔴", section)

    def test_green_badge_for_low_risk(self):
        section = self._make_result(risk="low").to_pr_section()
        self.assertIn("🟢", section)

    def test_includes_summary(self):
        section = self._make_result().to_pr_section()
        self.assertIn("Kleiner Fehler gefunden.", section)

    def test_includes_model_provenance(self):
        section = self._make_result().to_pr_section()
        self.assertIn("ollama/qwen2.5-coder:7b", section)

    def test_suggestions_listed(self):
        sug = Suggestion(
            theme="security",
            recommendation="Passwort hashen.",
            risk="high",
            why="Klartextspeicherung.",
            files=["auth.py"],
        )
        section = self._make_result(suggestions=[sug]).to_pr_section()
        self.assertIn("Passwort hashen.", section)
        self.assertIn("auth.py", section)


class TestFactory(unittest.TestCase):
    def test_ollama_provider_created(self):
        from lib.llm.factory import get_provider
        from lib.llm.ollama import OllamaProvider

        cfg = {"provider": "ollama", "model": "llama3", "base_url": "http://localhost:11434"}
        prov = get_provider(cfg)
        self.assertIsInstance(prov, OllamaProvider)
        self.assertEqual(prov.model, "llama3")

    def test_openai_provider_created(self):
        from lib.llm.factory import get_provider
        from lib.llm.openai import OpenAIProvider

        cfg = {"provider": "openai", "model": "gpt-4o", "base_url": "https://api.openai.com/v1"}
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            prov = get_provider(cfg)
        self.assertIsInstance(prov, OpenAIProvider)
        self.assertEqual(prov.model, "gpt-4o")

    def test_unknown_provider_raises(self):
        from lib.llm.factory import get_provider

        with self.assertRaises(ValueError):
            get_provider({"provider": "anthropic"})

    def test_none_config_defaults_to_ollama(self):
        from lib.llm.factory import get_provider
        from lib.llm.ollama import OllamaProvider

        prov = get_provider(None)
        self.assertIsInstance(prov, OllamaProvider)


class TestBuildReviewPrompt(unittest.TestCase):
    def test_prompt_contains_repo_name(self):
        from lib.llm.prompts import build_review_prompt

        prompt = build_review_prompt("myrepo", "diff --git a/x.py", [])
        self.assertIn("myrepo", prompt)

    def test_diff_is_truncated(self):
        from lib.llm.prompts import _MAX_DIFF_CHARS, build_review_prompt

        long_diff = "x" * (_MAX_DIFF_CHARS + 5000)
        prompt = build_review_prompt("repo", long_diff, [])
        self.assertIn("gekürzt", prompt)

    def test_secrets_redacted_in_diff(self):
        from lib.llm.prompts import build_review_prompt

        diff_with_secret = "API_KEY=mysupersecretvalue123"
        prompt = build_review_prompt("repo", diff_with_secret, [])
        self.assertNotIn("mysupersecretvalue123", prompt)
        self.assertIn("[REDACTED]", prompt)

    def test_static_findings_included(self):
        from lib.llm.prompts import build_review_prompt

        findings = [
            Finding(
                severity="error",
                category="correctness",
                file="main.sh",
                line=10,
                message="SC2006 Use $(...) notation",
                tool="shellcheck",
                rule_id="SC2006",
            )
        ]
        prompt = build_review_prompt("repo", "", findings)
        self.assertIn("SC2006", prompt)
        self.assertIn("main.sh", prompt)


if __name__ == "__main__":
    unittest.main()

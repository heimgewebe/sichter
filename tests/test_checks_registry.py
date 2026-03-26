import unittest
from pathlib import Path
from unittest.mock import patch

from lib.findings import Finding
from lib.checks.registry import run_autofixes, run_checks


class TestChecksRegistry(unittest.TestCase):
    @patch("lib.checks.registry.run_ruff")
    @patch("lib.checks.registry.run_yamllint")
    @patch("lib.checks.registry.run_shellcheck")
    def test_run_checks_aggregates_all_enabled_runners(
        self,
        mock_shellcheck,
        mock_yamllint,
        mock_ruff,
    ):
        mock_shellcheck.return_value = [
            Finding(
                severity="warning",
                category="correctness",
                file="a.sh",
                line=1,
                message="x",
                tool="shellcheck",
                rule_id="SC1000",
            )
        ]
        mock_yamllint.return_value = []
        mock_ruff.return_value = [
            Finding(
                severity="error",
                category="correctness",
                file="b.py",
                line=2,
                message="y",
                tool="ruff",
                rule_id="F401",
            )
        ]

        findings = run_checks(
            repo_dir=Path("/fake/repo"),
            files=None,
            checks_cfg={"shellcheck": True, "yamllint": True, "ruff": True},
            excludes=[],
            run_cmd=lambda *args, **kwargs: None,
            log=lambda _msg: None,
        )

        self.assertEqual(len(findings), 2)
        self.assertEqual(findings[0].tool, "shellcheck")
        self.assertEqual(findings[1].tool, "ruff")

    @patch("lib.checks.registry.run_shfmt", return_value=1)
    @patch("lib.checks.registry.run_ruff_autofix", return_value=2)
    def test_run_autofixes_returns_tool_map(self, mock_ruff_autofix, mock_shfmt):
        result = run_autofixes(
            repo_dir=Path("/fake/repo"),
            files=None,
            checks_cfg={"ruff": {"enabled": True, "autofix": True}, "shfmt_fix": True},
            excludes=[],
            run_cmd=lambda *args, **kwargs: None,
            log=lambda _msg: None,
        )

        self.assertEqual(result.get("ruff"), 2)
        self.assertEqual(result.get("shfmt"), 1)


if __name__ == "__main__":
    unittest.main()

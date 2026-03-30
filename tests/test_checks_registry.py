import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.findings import Finding
from lib.checks.registry import run_autofixes, run_checks
from lib.checks.ruff import run_ruff_autofix


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
    @patch("lib.checks.registry.run_eslint_autofix", return_value=0)
    @patch("lib.checks.registry.run_ruff_autofix", return_value=2)
    def test_run_autofixes_returns_tool_map(self, mock_ruff_autofix, mock_eslint_autofix, mock_shfmt):
        result = run_autofixes(
            repo_dir=Path("/fake/repo"),
            files=None,
            checks_cfg={"ruff": {"enabled": True, "autofix": True}, "shfmt_fix": True},
            excludes=[],
            run_cmd=lambda *args, **kwargs: None,
            log=lambda _msg: None,
        )

        self.assertEqual(result.get("ruff"), 2)
        self.assertEqual(result.get("eslint"), 0)
        self.assertEqual(result.get("shfmt"), 1)
        mock_eslint_autofix.assert_called_once()

    @patch("lib.checks.registry.run_shfmt", return_value=1)
    @patch("lib.checks.registry.run_eslint_autofix", return_value=3)
    @patch("lib.checks.registry.run_ruff_autofix", return_value=2)
    def test_run_autofixes_targets_only_fixable_tools_and_files(
        self,
        mock_ruff_autofix,
        mock_eslint_autofix,
        mock_shfmt,
    ):
        target_files = [Path("src/demo.py")]
        expected_ruff_files = [Path("/fake/repo/src/demo.py")]

        result = run_autofixes(
            repo_dir=Path("/fake/repo"),
            files=[Path("src/demo.py"), Path("src/unused.ts")],
            checks_cfg={"ruff": {"enabled": True, "autofix": True}, "eslint": {"enabled": True, "autofix": True}, "shfmt_fix": True},
            excludes=[],
            run_cmd=lambda *args, **kwargs: None,
            log=lambda _msg: None,
            only_tools={"ruff"},
            target_files_by_tool={"ruff": target_files},
        )

        self.assertEqual(result.get("ruff"), 2)
        self.assertEqual(result.get("eslint"), 0)
        self.assertEqual(result.get("shfmt"), 1)
        mock_ruff_autofix.assert_called_once_with(
            Path("/fake/repo"),
            expected_ruff_files,
            [],
            {"ruff": {"enabled": True, "autofix": True}, "eslint": {"enabled": True, "autofix": True}, "shfmt_fix": True},
            unittest.mock.ANY,
            unittest.mock.ANY,
        )
        mock_eslint_autofix.assert_not_called()
        mock_shfmt.assert_called_once()

    @patch("lib.checks.registry.run_shfmt", return_value=0)
    @patch("lib.checks.registry.run_eslint_autofix", return_value=0)
    @patch("lib.checks.registry.run_ruff_autofix", return_value=1)
    def test_run_autofixes_keeps_absolute_targets_unchanged(
        self,
        mock_ruff_autofix,
        _mock_eslint_autofix,
        _mock_shfmt,
    ):
        absolute_target = Path("/tmp/demo.py")

        run_autofixes(
            repo_dir=Path("/fake/repo"),
            files=None,
            checks_cfg={"ruff": {"enabled": True, "autofix": True}},
            excludes=[],
            run_cmd=lambda *args, **kwargs: None,
            log=lambda _msg: None,
            only_tools={"ruff"},
            target_files_by_tool={"ruff": [absolute_target]},
        )

        self.assertEqual(mock_ruff_autofix.call_args.args[1], [absolute_target])

    @unittest.skipIf(
        shutil.which("ruff") is None or shutil.which("git") is None,
        "SKIP: requires ruff and git for live autofix patch/revert test",
    )
    def test_run_ruff_autofix_patch_is_revertible_and_leaves_clean_tree(self):
        def run_cmd(cmd, repo_dir, check=False):
            completed = subprocess.run(
                cmd,
                cwd=repo_dir,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "RUFF_NO_CACHE": "1"},
            )
            if check and completed.returncode != 0:
                raise subprocess.CalledProcessError(
                    completed.returncode,
                    cmd,
                    output=completed.stdout,
                    stderr=completed.stderr,
                )
            return completed

        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp)
            target = repo_dir / "demo.py"

            subprocess.run(["git", "init", "-q"], cwd=repo_dir, check=True)
            subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=repo_dir, check=True)
            subprocess.run(["git", "config", "user.name", "Sichter Tests"], cwd=repo_dir, check=True)

            original = "import os\n\nprint('ok')\n"
            target.write_text(original, encoding="utf-8")
            subprocess.run(["git", "add", "demo.py"], cwd=repo_dir, check=True)
            subprocess.run(["git", "commit", "-qm", "baseline"], cwd=repo_dir, check=True)

            changed = run_ruff_autofix(
                repo_dir,
                [target],
                [],
                {"ruff": {"enabled": True, "autofix": True}},
                run_cmd,
                lambda _msg: None,
            )

            self.assertEqual(changed, 1)

            diff = subprocess.run(
                ["git", "diff", "--binary", "--", "demo.py"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout
            self.assertTrue(diff.strip(), "Expected an autofix patch in git diff output")

            reverse_check = subprocess.run(
                ["git", "apply", "--check", "-R"],
                cwd=repo_dir,
                check=False,
                input=diff,
                capture_output=True,
                text=True,
            )
            self.assertEqual(reverse_check.returncode, 0, reverse_check.stderr)

            reverse_apply = subprocess.run(
                ["git", "apply", "-R"],
                cwd=repo_dir,
                check=False,
                input=diff,
                capture_output=True,
                text=True,
            )
            self.assertEqual(reverse_apply.returncode, 0, reverse_apply.stderr)

            self.assertEqual(target.read_text(encoding="utf-8"), original)
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(status, "")


if __name__ == "__main__":
    unittest.main()

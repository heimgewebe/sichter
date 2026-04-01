import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lib.checks.bandit import run_bandit
from lib.checks.eslint import run_eslint
from lib.checks.trivy import run_trivy


class _Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestCheckModules(unittest.TestCase):
    def test_bandit_parses_json_output(self):
        output = {
            "results": [
                {
                    "filename": "app/main.py",
                    "line_number": 12,
                    "issue_text": "Use of assert detected.",
                    "test_id": "B101",
                    "issue_severity": "LOW",
                    "more_info": "https://bandit.readthedocs.io/",
                }
            ]
        }

        with patch("shutil.which", return_value="/usr/bin/bandit"):
            findings = run_bandit(
                repo_dir=Path("/repo"),
                files=None,
                excludes=[],
                checks_cfg={"bandit": True},
                run_cmd=lambda *_args, **_kwargs: _Result(stdout=json.dumps(output)),
                log=lambda _msg: None,
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].tool, "bandit")
        self.assertEqual(findings[0].rule_id, "B101")
        self.assertEqual(findings[0].category, "security")

    def test_eslint_parses_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "eslint.config.js").write_text("export default []\n", encoding="utf-8")
            target = repo / "src" / "app.js"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("var x = 1\n", encoding="utf-8")

            eslint_output = [
                {
                    "filePath": str(target),
                    "messages": [
                        {
                            "line": 1,
                            "severity": 2,
                            "ruleId": "no-var",
                            "message": "Unexpected var, use let or const instead.",
                        }
                    ],
                }
            ]

            with patch("shutil.which", return_value="/usr/bin/eslint"):
                findings = run_eslint(
                    repo_dir=repo,
                    files=[target],
                    excludes=[],
                    checks_cfg={"eslint": True},
                    run_cmd=lambda *_args, **_kwargs: _Result(stdout=json.dumps(eslint_output)),
                    log=lambda _msg: None,
                )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].tool, "eslint")
        self.assertEqual(findings[0].rule_id, "no-var")
        self.assertEqual(findings[0].severity, "error")

    def test_trivy_parses_vulnerabilities(self):
        output = {
            "Results": [
                {
                    "Target": "requirements.txt",
                    "Vulnerabilities": [
                        {
                            "VulnerabilityID": "CVE-2026-0001",
                            "PkgName": "urllib3",
                            "Title": "Example vulnerability",
                            "Severity": "HIGH",
                            "PrimaryURL": "https://example.com/cve",
                        }
                    ],
                }
            ]
        }

        with patch("shutil.which", return_value="/usr/bin/trivy"):
            findings = run_trivy(
                repo_dir=Path("/repo"),
                files=None,
                excludes=[],
                checks_cfg={"trivy": True},
                run_cmd=lambda *_args, **_kwargs: _Result(stdout=json.dumps(output)),
                log=lambda _msg: None,
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].tool, "trivy")
        self.assertEqual(findings[0].category, "security")
        self.assertEqual(findings[0].severity, "critical")

    def _bandit_output(self, filename: str) -> str:
        return json.dumps({
            "results": [
                {
                    "filename": filename,
                    "line_number": 5,
                    "issue_text": "Use of exec detected.",
                    "test_id": "B102",
                    "issue_severity": "HIGH",
                    "more_info": "https://bandit.readthedocs.io/",
                }
            ]
        })

    def test_bandit_all_files_mode_excludes_matched_pattern(self):
        """In all-files mode, a file matching an exclude pattern is filtered out."""
        output = self._bandit_output("venv/lib/helper.py")

        with patch("shutil.which", return_value="/usr/bin/bandit"):
            findings = run_bandit(
                repo_dir=Path("/repo"),
                files=None,
                excludes=["venv/*"],
                checks_cfg={"bandit": True},
                run_cmd=lambda *_args, **_kwargs: _Result(stdout=output),
                log=lambda _msg: None,
            )

        self.assertEqual(findings, [])

    def test_bandit_all_files_mode_includes_unmatched_file(self):
        """In all-files mode, a file that does not match any exclude is kept."""
        output = self._bandit_output("src/app.py")

        with patch("shutil.which", return_value="/usr/bin/bandit"):
            findings = run_bandit(
                repo_dir=Path("/repo"),
                files=None,
                excludes=["venv/*"],
                checks_cfg={"bandit": True},
                run_cmd=lambda *_args, **_kwargs: _Result(stdout=output),
                log=lambda _msg: None,
            )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].file, "src/app.py")

    def test_bandit_normalizes_dotslash_prefix_before_exclude_matching(self):
        """Filenames like './venv/lib/helper.py' from bandit -r . are normalized."""
        output = self._bandit_output("./venv/lib/helper.py")

        with patch("shutil.which", return_value="/usr/bin/bandit"):
            findings = run_bandit(
                repo_dir=Path("/repo"),
                files=None,
                excludes=["venv/*"],
                checks_cfg={"bandit": True},
                run_cmd=lambda *_args, **_kwargs: _Result(stdout=output),
                log=lambda _msg: None,
            )

        self.assertEqual(findings, [])

    def test_bandit_no_excludes_in_all_files_mode_returns_all(self):
        """With an empty exclude list, all findings are returned regardless."""
        output = self._bandit_output("venv/lib/helper.py")

        with patch("shutil.which", return_value="/usr/bin/bandit"):
            findings = run_bandit(
                repo_dir=Path("/repo"),
                files=None,
                excludes=[],
                checks_cfg={"bandit": True},
                run_cmd=lambda *_args, **_kwargs: _Result(stdout=output),
                log=lambda _msg: None,
            )

        self.assertEqual(len(findings), 1)


if __name__ == "__main__":
    unittest.main()

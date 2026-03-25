import unittest
from pathlib import Path
from unittest.mock import call, patch

from apps.worker import run as worker_run
from lib.findings import Finding


class TestWorkerRun(unittest.TestCase):
    @patch("apps.worker.run.get_changed_files", return_value=[])
    @patch("apps.worker.run.create_or_update_pr")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.run_yamllint", return_value=[])
    @patch("apps.worker.run.run_shellcheck", return_value=[])
    @patch("apps.worker.run.fresh_branch")
    @patch("apps.worker.run.ensure_repo")
    def test_handle_job_respects_auto_pr_flag(
        self,
        mock_ensure_repo,
        mock_fresh_branch,
        mock_run_shellcheck,
        mock_run_yamllint,
        mock_llm_review,
        mock_commit_if_changes,
        mock_create_or_update_pr,
        mock_get_changed_files,
    ):
        # Test case 1: job with auto_pr=False
        job_false = {"repo": "test_repo", "auto_pr": False}
        worker_run.handle_job(job_false)
        mock_create_or_update_pr.assert_called_with(
            "test_repo",
            mock_ensure_repo.return_value,
            mock_fresh_branch.return_value,
            False,
            [],
            mock_llm_review.return_value,
        )

        # Test case 2: job with auto_pr=True
        job_true = {"repo": "test_repo", "auto_pr": True}
        worker_run.handle_job(job_true)
        mock_create_or_update_pr.assert_called_with(
            "test_repo",
            mock_ensure_repo.return_value,
            mock_fresh_branch.return_value,
            True,
            [],
            mock_llm_review.return_value,
        )

        # Test case 3: job without auto_pr (fallback to policy)
        job_none = {"repo": "test_repo"}
        with patch("apps.worker.run.POLICY.auto_pr", True):
            worker_run.handle_job(job_none)
            mock_create_or_update_pr.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                True,
                [],
                mock_llm_review.return_value,
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_none)
            mock_create_or_update_pr.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                False,
                [],
                mock_llm_review.return_value,
            )

        # Test case 4: job with auto_pr=None (should fallback to policy)
        job_none_value = {"repo": "test_repo", "auto_pr": None}
        with patch("apps.worker.run.POLICY.auto_pr", True):
            worker_run.handle_job(job_none_value)
            mock_create_or_update_pr.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                True,
                [],
                mock_llm_review.return_value,
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_none_value)
            mock_create_or_update_pr.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                False,
                [],
                mock_llm_review.return_value,
            )

        # Test case 5: job with non-bool auto_pr defaults to policy
        job_invalid_type = {"repo": "test_repo", "auto_pr": "false"}
        with patch("apps.worker.run.POLICY.auto_pr", True):
            worker_run.handle_job(job_invalid_type)
            mock_create_or_update_pr.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                True,
                [],
                mock_llm_review.return_value,
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_invalid_type)
            mock_create_or_update_pr.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                False,
                [],
                mock_llm_review.return_value,
            )

    @patch("apps.worker.run.get_changed_files")
    @patch("apps.worker.run.create_or_update_pr")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.run_yamllint", return_value=[])
    @patch("apps.worker.run.run_shellcheck", return_value=[])
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.ensure_repo")
    def test_handle_job_mode_changed_calls_get_changed_files(
        self,
        mock_ensure_repo,
        mock_fresh_branch,
        mock_run_shellcheck,
        mock_run_yamllint,
        mock_llm_review,
        mock_commit_if_changes,
        mock_create_or_update_pr,
        mock_get_changed_files,
    ):
        """Test that mode='changed' invokes get_changed_files and passes result to linters."""
        mock_repo_dir = Path("/fake/repo")
        mock_ensure_repo.return_value = mock_repo_dir
        mock_changed = [Path("/fake/repo/test.sh"), Path("/fake/repo/test.yml")]
        mock_get_changed_files.return_value = mock_changed

        job = {"repo": "test_repo", "mode": "changed"}
        worker_run.handle_job(job)

        mock_get_changed_files.assert_called_once()
        mock_run_shellcheck.assert_called_once_with(mock_repo_dir, mock_changed)
        mock_run_yamllint.assert_called_once_with(mock_repo_dir, mock_changed)

    @patch("apps.worker.run.get_changed_files")
    @patch("apps.worker.run.create_or_update_pr")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.run_yamllint", return_value=[])
    @patch("apps.worker.run.run_shellcheck", return_value=[])
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.ensure_repo")
    def test_handle_job_mode_all_skips_get_changed_files(
        self,
        mock_ensure_repo,
        mock_fresh_branch,
        mock_run_shellcheck,
        mock_run_yamllint,
        mock_llm_review,
        mock_commit_if_changes,
        mock_create_or_update_pr,
        mock_get_changed_files,
    ):
        """Test that mode='all' does not invoke get_changed_files and passes None to linters."""
        mock_repo_dir = Path("/fake/repo")
        mock_ensure_repo.return_value = mock_repo_dir

        job = {"repo": "test_repo", "mode": "all"}
        worker_run.handle_job(job)

        mock_get_changed_files.assert_not_called()
        mock_run_shellcheck.assert_called_once_with(mock_repo_dir, None)
        mock_run_yamllint.assert_called_once_with(mock_repo_dir, None)

    @patch("apps.worker.run.get_changed_files", return_value=[])
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.dedupe_findings")
    @patch("apps.worker.run.create_or_update_pr")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.run_yamllint")
    @patch("apps.worker.run.run_shellcheck")
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.ensure_repo")
    def test_handle_job_dedupes_findings(
        self,
        mock_ensure_repo,
        mock_fresh_branch,
        mock_run_shellcheck,
        mock_run_yamllint,
        mock_llm_review,
        mock_commit_if_changes,
        mock_create_or_update_pr,
        mock_dedupe_findings,
        mock_append_event,
        mock_get_changed_files,
    ):
        """Test that findings are collected, deduped, and counted correctly."""
        mock_repo_dir = Path("/fake/repo")
        mock_ensure_repo.return_value = mock_repo_dir

        finding1 = Finding(
            severity="warning",
            category="correctness",
            file="test.sh",
            line=10,
            message="Test finding 1",
            tool="shellcheck",
            rule_id="SC2006",
        )
        finding2 = Finding(
            severity="error",
            category="correctness",
            file="test.yml",
            line=5,
            message="Test finding 2",
            tool="yamllint",
            rule_id="trailing-spaces",
        )
        finding3 = Finding(
            severity="warning",
            category="correctness",
            file="test.sh",
            line=10,
            message="Test finding 1",
            tool="shellcheck",
            rule_id="SC2006",
        )

        mock_run_shellcheck.return_value = [finding1, finding3]
        mock_run_yamllint.return_value = [finding2]
        mock_dedupe_findings.return_value = {
            "key1": [finding1, finding3],
            "key2": [finding2],
        }

        job = {"repo": "test_repo"}
        worker_run.handle_job(job)

        mock_dedupe_findings.assert_called_once()
        args = mock_dedupe_findings.call_args[0][0]
        findings_list = list(args)
        self.assertEqual(len(findings_list), 3)

        event_calls = [
            c
            for c in mock_append_event.call_args_list
            if c[0][0].get("type") == "findings"
        ]
        self.assertEqual(len(event_calls), 1)
        event = event_calls[0][0][0]
        self.assertEqual(event["count"], 3)
        self.assertEqual(event["deduped"], 2)


    @patch("apps.worker.run.POLICY")
    @patch("apps.worker.run.run_cmd")
    def test_run_shellcheck_applies_excludes_with_files(
        self, mock_run_cmd, mock_policy
    ):
        """Test that run_shellcheck applies POLICY.excludes when files are provided."""
        mock_policy.checks = {"shellcheck": True}
        mock_policy.excludes = ["vendor/*", "*.generated.sh"]
        
        repo_dir = Path("/fake/repo")
        files = [
            Path("/fake/repo/script.sh"),
            Path("/fake/repo/vendor/dep.sh"),  # should be excluded
            Path("/fake/repo/test.generated.sh"),  # should be excluded
            Path("/fake/repo/valid.sh"),
        ]
        
        # Mock run_cmd to return no findings
        mock_run_cmd.return_value.returncode = 0
        mock_run_cmd.return_value.stdout = ""
        mock_run_cmd.return_value.stderr = ""
        
        with patch("shutil.which", return_value="/usr/bin/shellcheck"):
            worker_run.run_shellcheck(repo_dir, files)
        
        # Verify shellcheck was called only for non-excluded files
        # Command format: ["shellcheck", "-f", "gcc", "-x", str(script)]
        calls = mock_run_cmd.call_args_list
        checked_files = [c[0][0][-1] for c in calls]  # last arg is the file path
        
        self.assertIn(str(Path("/fake/repo/script.sh")), checked_files)
        self.assertIn(str(Path("/fake/repo/valid.sh")), checked_files)
        self.assertNotIn(str(Path("/fake/repo/vendor/dep.sh")), checked_files)
        self.assertNotIn(str(Path("/fake/repo/test.generated.sh")), checked_files)

    @patch("apps.worker.run.POLICY")
    @patch("apps.worker.run.run_cmd")
    def test_run_yamllint_applies_excludes_with_files(
        self, mock_run_cmd, mock_policy
    ):
        """Test that run_yamllint applies POLICY.excludes when files are provided."""
        mock_policy.checks = {"yamllint": True}
        mock_policy.excludes = ["vendor/*", "*.generated.yml"]
        
        repo_dir = Path("/fake/repo")
        files = [
            Path("/fake/repo/config.yml"),
            Path("/fake/repo/vendor/dep.yaml"),  # should be excluded
            Path("/fake/repo/test.generated.yml"),  # should be excluded
            Path("/fake/repo/valid.yaml"),
        ]
        
        # Mock run_cmd to return no findings
        mock_run_cmd.return_value.returncode = 0
        mock_run_cmd.return_value.stdout = ""
        mock_run_cmd.return_value.stderr = ""
        
        with patch("shutil.which", return_value="/usr/bin/yamllint"):
            worker_run.run_yamllint(repo_dir, files)
        
        # Verify yamllint was called only for non-excluded files
        # Command format: ["yamllint", "-f", "parsable", str(doc)]
        calls = mock_run_cmd.call_args_list
        checked_files = [c[0][0][-1] for c in calls]  # last arg is the file path
        
        self.assertIn(str(Path("/fake/repo/config.yml")), checked_files)
        self.assertIn(str(Path("/fake/repo/valid.yaml")), checked_files)
        self.assertNotIn(str(Path("/fake/repo/vendor/dep.yaml")), checked_files)
        self.assertNotIn(str(Path("/fake/repo/test.generated.yml")), checked_files)

    def test_is_check_enabled_supports_nested_dict(self):
        with patch("apps.worker.run.POLICY.checks", {"ruff": {"enabled": True}}):
            self.assertTrue(worker_run.is_check_enabled("ruff"))

        with patch("apps.worker.run.POLICY.checks", {"ruff": {"autofix": True}}):
            self.assertTrue(worker_run.is_check_enabled("ruff"))

        with patch("apps.worker.run.POLICY.checks", {"ruff": {"enabled": False}}):
            self.assertFalse(worker_run.is_check_enabled("ruff"))

    def test_build_pr_body_includes_findings_summary(self):
        findings = [
            Finding(
                severity="error",
                category="correctness",
                file="apps/main.py",
                line=10,
                message="Undefined name 'x'",
                tool="ruff",
                rule_id="F821",
            ),
            Finding(
                severity="warning",
                category="correctness",
                file="apps/main.py",
                line=12,
                message="Line too long",
                tool="ruff",
                rule_id="E501",
            ),
        ]

        body = worker_run.build_pr_body("demo-repo", findings)

        self.assertIn("Repository: demo-repo", body)
        self.assertIn("- error: 1", body)
        self.assertIn("- warning: 1", body)
        self.assertIn("Undefined name 'x'", body)
        self.assertIn("(F821)", body)

    # ------------------------------------------------------------------
    # LLM gating semantics
    # ------------------------------------------------------------------

    @patch("apps.worker.run.run_cmd")
    def test_llm_review_skipped_when_not_enabled(self, mock_run_cmd):
        """LLM must not run when llm.enabled is false, even in deep run_mode."""
        with patch("apps.worker.run.POLICY") as mock_policy:
            mock_policy.run_mode = "deep"
            mock_policy.llm = {"enabled": False}
            result = worker_run.llm_review("repo", Path("/fake/repo"))
        self.assertIsNone(result)
        mock_run_cmd.assert_not_called()

    @patch("apps.worker.run.run_cmd")
    def test_llm_review_skipped_when_llm_config_absent(self, mock_run_cmd):
        """LLM must not run when llm config is absent (defaults to not enabled)."""
        with patch("apps.worker.run.POLICY") as mock_policy:
            mock_policy.run_mode = "deep"
            mock_policy.llm = None
            result = worker_run.llm_review("repo", Path("/fake/repo"))
        self.assertIsNone(result)
        mock_run_cmd.assert_not_called()

    @patch("apps.worker.run.run_cmd")
    def test_llm_review_skipped_when_no_findings_and_empty_diff(
        self, mock_run_cmd
    ):
        """LLM must not run when there are no findings and the diff is empty."""
        mock_run_cmd.return_value.stdout = ""
        mock_run_cmd.return_value.returncode = 0

        with patch("apps.worker.run.POLICY") as mock_policy, \
             patch("lib.llm.factory.get_provider") as mock_get_provider:
            mock_policy.run_mode = "normal"
            mock_policy.llm = {"enabled": True}
            result = worker_run.llm_review("repo", Path("/fake/repo"), findings=[])
        self.assertIsNone(result)
        mock_get_provider.return_value.complete.assert_not_called()

    @patch("apps.worker.run.run_cmd")
    def test_llm_review_runs_when_enabled_and_has_diff(
        self, mock_run_cmd
    ):
        """LLM must run when enabled and a non-empty diff is present."""
        mock_run_cmd.return_value.stdout = "diff --git a/x.py b/x.py\n+line"
        mock_run_cmd.return_value.returncode = 0

        with patch("apps.worker.run.POLICY") as mock_policy, \
             patch("lib.llm.factory.get_provider") as mock_get_provider, \
             patch("apps.worker.run.append_event"):
            mock_provider = mock_get_provider.return_value
            mock_provider.complete.return_value = (
                '{"summary":"ok","risk_overall":"low",'
                '"uncertainty":{"level":0.1,"sources":[],"productive":false},'
                '"suggestions":[]}',
                10,
            )
            mock_provider.model = "test-model"
            mock_provider.provider_name = "ollama"
            mock_policy.run_mode = "normal"
            mock_policy.llm = {"enabled": True}
            result = worker_run.llm_review("repo", Path("/fake/repo"), findings=[])
        self.assertIsNotNone(result)
        mock_provider.complete.assert_called_once()

    @patch("apps.worker.run.run_cmd")
    def test_llm_review_runs_when_enabled_and_has_findings(
        self, mock_run_cmd
    ):
        """LLM must run when enabled and there are static findings, even with empty diff."""
        mock_run_cmd.return_value.stdout = ""
        mock_run_cmd.return_value.returncode = 0

        finding = Finding(
            severity="error",
            category="correctness",
            file="main.py",
            line=1,
            message="Some issue",
            tool="ruff",
            rule_id="F401",
        )

        with patch("apps.worker.run.POLICY") as mock_policy, \
             patch("lib.llm.factory.get_provider") as mock_get_provider, \
             patch("apps.worker.run.append_event"):
            mock_provider = mock_get_provider.return_value
            mock_provider.complete.return_value = (
                '{"summary":"ok","risk_overall":"low",'
                '"uncertainty":{"level":0.1,"sources":[],"productive":false},'
                '"suggestions":[]}',
                10,
            )
            mock_provider.model = "test-model"
            mock_provider.provider_name = "ollama"
            mock_policy.run_mode = "normal"
            mock_policy.llm = {"enabled": True}
            result = worker_run.llm_review("repo", Path("/fake/repo"), findings=[finding])
        self.assertIsNotNone(result)
        mock_provider.complete.assert_called_once()


if __name__ == "__main__":
    unittest.main()

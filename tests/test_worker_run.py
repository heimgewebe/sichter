
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
            "test_repo", mock_ensure_repo.return_value, mock_fresh_branch.return_value, False
        )

        # Test case 2: job with auto_pr=True
        job_true = {"repo": "test_repo", "auto_pr": True}
        worker_run.handle_job(job_true)
        mock_create_or_update_pr.assert_called_with(
            "test_repo", mock_ensure_repo.return_value, mock_fresh_branch.return_value, True
        )

        # Test case 3: job without auto_pr (fallback to policy)
        job_none = {"repo": "test_repo"}
        with patch("apps.worker.run.POLICY.auto_pr", True):
            worker_run.handle_job(job_none)
            mock_create_or_update_pr.assert_called_with(
                "test_repo", mock_ensure_repo.return_value, mock_fresh_branch.return_value, True
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_none)
            mock_create_or_update_pr.assert_called_with(
                "test_repo", mock_ensure_repo.return_value, mock_fresh_branch.return_value, False
            )

        # Test case 4: job with auto_pr=None (should fallback to policy)
        job_none_value = {"repo": "test_repo", "auto_pr": None}
        with patch("apps.worker.run.POLICY.auto_pr", True):
            worker_run.handle_job(job_none_value)
            mock_create_or_update_pr.assert_called_with(
                "test_repo", mock_ensure_repo.return_value, mock_fresh_branch.return_value, True
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_none_value)
            mock_create_or_update_pr.assert_called_with(
                "test_repo", mock_ensure_repo.return_value, mock_fresh_branch.return_value, False
            )

        # Test case 5: job with non-bool auto_pr defaults to policy
        job_invalid_type = {"repo": "test_repo", "auto_pr": "false"}
        with patch("apps.worker.run.POLICY.auto_pr", True):
            worker_run.handle_job(job_invalid_type)
            mock_create_or_update_pr.assert_called_with(
                "test_repo", mock_ensure_repo.return_value, mock_fresh_branch.return_value, True
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_invalid_type)
            mock_create_or_update_pr.assert_called_with(
                "test_repo", mock_ensure_repo.return_value, mock_fresh_branch.return_value, False
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

        # Verify get_changed_files was called
        mock_get_changed_files.assert_called_once()
        # Verify shellcheck and yamllint were called with changed files
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

        # Verify get_changed_files was NOT called
        mock_get_changed_files.assert_not_called()
        # Verify shellcheck and yamllint were called with None (all files)
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
        # Duplicate finding (same dedupe_key as finding1)
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
        # Simulate dedupe returning 2 groups
        mock_dedupe_findings.return_value = {"key1": [finding1, finding3], "key2": [finding2]}

        job = {"repo": "test_repo"}
        worker_run.handle_job(job)

        # Verify dedupe_findings was called with all findings
        mock_dedupe_findings.assert_called_once()
        args = mock_dedupe_findings.call_args[0][0]
        findings_list = list(args)
        self.assertEqual(len(findings_list), 3)

        # Verify event was appended with correct counts
        event_calls = [call for call in mock_append_event.call_args_list if call[0][0].get("type") == "findings"]
        self.assertEqual(len(event_calls), 1)
        event = event_calls[0][0][0]
        self.assertEqual(event["count"], 3)
        self.assertEqual(event["deduped"], 2)


if __name__ == "__main__":
    unittest.main()

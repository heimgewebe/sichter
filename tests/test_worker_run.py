
import unittest
from unittest.mock import patch

from apps.worker import run as worker_run


class TestWorkerRun(unittest.TestCase):
    @patch("apps.worker.run.create_or_update_pr")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.run_yamllint")
    @patch("apps.worker.run.run_shellcheck")
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

if __name__ == "__main__":
    unittest.main()

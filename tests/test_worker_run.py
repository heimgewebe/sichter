import unittest
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import call, patch

from apps.worker import run as worker_run
from lib.findings import Finding


class TestWorkerRun(unittest.TestCase):
    def test_get_sorted_jobs_prioritizes_high_then_fifo_within_priority(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue_dir = Path(tmp)
            (queue_dir / "1700000003-low.json").write_text(
                json.dumps({"priority": "low"}),
                encoding="utf-8",
            )
            (queue_dir / "1700000001-normal.json").write_text(
                json.dumps({"priority": "normal"}),
                encoding="utf-8",
            )
            (queue_dir / "1700000000-high.json").write_text(
                json.dumps({"priority": "high"}),
                encoding="utf-8",
            )
            (queue_dir / "1700000002-high.json").write_text(
                json.dumps({"priority": "high"}),
                encoding="utf-8",
            )

            ordered = worker_run.get_sorted_jobs(queue_dir)

        self.assertEqual(
            [path.name for path in ordered],
            [
                "1700000000-high.json",
                "1700000002-high.json",
                "1700000001-normal.json",
                "1700000003-low.json",
            ],
        )

    def test_get_sorted_jobs_defaults_invalid_or_missing_priority_to_normal(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue_dir = Path(tmp)
            (queue_dir / "1700000000-normal.json").write_text(
                json.dumps({"priority": "normal"}),
                encoding="utf-8",
            )
            (queue_dir / "1700000001-missing.json").write_text(
                json.dumps({}),
                encoding="utf-8",
            )
            (queue_dir / "1700000002-invalid.json").write_text(
                json.dumps({"priority": "urgent"}),
                encoding="utf-8",
            )

            ordered = worker_run.get_sorted_jobs(queue_dir)

        self.assertEqual(
            [path.name for path in ordered],
            [
                "1700000000-normal.json",
                "1700000001-missing.json",
                "1700000002-invalid.json",
            ],
        )

    def test_notify_internal_timeout_is_logged_and_non_blocking(self):
        class _FakeScript:
            def exists(self):
                return True

            def __str__(self):
                return "/fake/hauski-notify"

        with patch("apps.worker.run.NOTIFY_SCRIPT", _FakeScript()), \
             patch(
                 "apps.worker.run.subprocess.run",
                 side_effect=subprocess.TimeoutExpired(cmd="hauski-notify", timeout=5),
             ) as mock_run, \
             patch("apps.worker.run.log") as mock_log:
            worker_run.notify_internal("hello")

        self.assertEqual(mock_run.call_args.kwargs["timeout"], worker_run.NOTIFY_TIMEOUT_SECONDS)
        self.assertTrue(mock_log.called)
        self.assertIn("Timeout", mock_log.call_args[0][0])

    def test_notify_internal_non_zero_exit_is_logged_and_non_blocking(self):
        class _FakeScript:
            def exists(self):
                return True

            def __str__(self):
                return "/fake/hauski-notify"

        result = subprocess.CompletedProcess(
            args=["/fake/hauski-notify", "hello"],
            returncode=2,
            stdout="",
            stderr="notify failed",
        )
        with patch("apps.worker.run.NOTIFY_SCRIPT", _FakeScript()), \
             patch("apps.worker.run.subprocess.run", return_value=result) as mock_run, \
             patch("apps.worker.run.log") as mock_log:
            worker_run.notify_internal("hello")

        self.assertEqual(mock_run.call_args.kwargs["timeout"], worker_run.NOTIFY_TIMEOUT_SECONDS)
        self.assertTrue(mock_log.called)
        self.assertIn("exit=2", mock_log.call_args[0][0])

    @patch("apps.worker.run.get_changed_files", return_value=[])
    @patch("apps.worker.run.create_themed_prs")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.fresh_branch")
    @patch("apps.worker.run.prepare_repo_base", return_value=True)
    @patch("apps.worker.run.has_commit_candidates", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.is_git_repository", return_value=True)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.ensure_repo")
    def test_handle_job_respects_auto_pr_flag(
        self,
        mock_ensure_repo,
        mock_registry_run_checks,
        mock_registry_run_autofixes,
        _mock_is_git_repository,
        mock_llm_review,
        _mock_has_commit_candidates,
        _mock_prepare_repo_base,
        mock_fresh_branch,
        mock_commit_if_changes,
        mock_create_themed_prs,
        mock_get_changed_files,
    ):
        # Test case 1: job with auto_pr=False
        job_false = {"repo": "test_repo", "auto_pr": False}
        worker_run.handle_job(job_false)
        mock_create_themed_prs.assert_called_with(
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
        mock_create_themed_prs.assert_called_with(
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
            mock_create_themed_prs.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                True,
                [],
                mock_llm_review.return_value,
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_none)
            mock_create_themed_prs.assert_called_with(
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
            mock_create_themed_prs.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                True,
                [],
                mock_llm_review.return_value,
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_none_value)
            mock_create_themed_prs.assert_called_with(
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
            mock_create_themed_prs.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                True,
                [],
                mock_llm_review.return_value,
            )

        with patch("apps.worker.run.POLICY.auto_pr", False):
            worker_run.handle_job(job_invalid_type)
            mock_create_themed_prs.assert_called_with(
                "test_repo",
                mock_ensure_repo.return_value,
                mock_fresh_branch.return_value,
                False,
                [],
                mock_llm_review.return_value,
            )

    @patch("apps.worker.run.get_changed_files")
    @patch("apps.worker.run.create_themed_prs")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.ensure_repo")
    def test_handle_job_mode_changed_calls_get_changed_files(
        self,
        mock_ensure_repo,
        mock_fresh_branch,
        mock_registry_run_checks,
        mock_registry_run_autofixes,
        mock_llm_review,
        mock_commit_if_changes,
        mock_create_themed_prs,
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
        mock_registry_run_checks.assert_called_once()
        args = mock_registry_run_checks.call_args[0]
        self.assertEqual(args[0], mock_repo_dir)
        self.assertEqual(args[1], mock_changed)

    @patch("apps.worker.run.get_changed_files")
    @patch("apps.worker.run.create_themed_prs")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.ensure_repo")
    def test_handle_job_mode_all_skips_get_changed_files(
        self,
        mock_ensure_repo,
        mock_fresh_branch,
        mock_registry_run_checks,
        mock_registry_run_autofixes,
        mock_llm_review,
        mock_commit_if_changes,
        mock_create_themed_prs,
        mock_get_changed_files,
    ):
        """Test that mode='all' does not invoke get_changed_files and passes None to linters."""
        mock_repo_dir = Path("/fake/repo")
        mock_ensure_repo.return_value = mock_repo_dir

        job = {"repo": "test_repo", "mode": "all"}
        worker_run.handle_job(job)

        mock_get_changed_files.assert_not_called()
        mock_registry_run_checks.assert_called_once()
        args = mock_registry_run_checks.call_args[0]
        self.assertEqual(args[0], mock_repo_dir)
        self.assertIsNone(args[1])

    @patch("apps.worker.run.get_changed_files", return_value=[])
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.dedupe_findings")
    @patch("apps.worker.run.create_themed_prs")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review")
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks")
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.ensure_repo")
    def test_handle_job_dedupes_findings(
        self,
        mock_ensure_repo,
        mock_fresh_branch,
        mock_registry_run_checks,
        mock_registry_run_autofixes,
        mock_llm_review,
        mock_commit_if_changes,
        mock_create_themed_prs,
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

        mock_registry_run_checks.return_value = [finding1, finding3, finding2]
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

    @patch("apps.worker.run.create_or_update_pr")
    def test_create_themed_prs_falls_back_to_single_pr_without_findings(self, mock_create_or_update_pr):
        worker_run.create_themed_prs(
            repo="test_repo",
            repo_dir=Path("/fake/repo"),
            source_branch="sichter/autofix-branch",
            auto_pr=True,
            findings=[],
            review=None,
        )

        mock_create_or_update_pr.assert_called_once_with(
            "test_repo",
            Path("/fake/repo"),
            "sichter/autofix-branch",
            True,
            [],
            review=None,
        )

    @patch("apps.worker.run.create_or_update_pr")
    @patch("apps.worker.run.run_cmd")
    @patch("apps.worker.run.commit_if_changes")
    def test_create_themed_prs_creates_pr_per_category(
        self,
        mock_commit_if_changes,
        mock_run_cmd,
        mock_create_or_update_pr,
    ):
        findings = [
            Finding(
                severity="warning",
                category="style",
                file="a.sh",
                line=1,
                message="style issue",
                tool="shellcheck",
                rule_id="SC1000",
            ),
            Finding(
                severity="error",
                category="security",
                file="sec.py",
                line=3,
                message="security issue",
                tool="ruff",
                rule_id="S101",
            ),
        ]

        def _run_cmd_side_effect(cmd, cwd, check=True):
            class _Result:
                def __init__(self, returncode=0, stdout="", stderr=""):
                    self.returncode = returncode
                    self.stdout = stdout
                    self.stderr = stderr

            if cmd[:3] == ["git", "rev-parse", "--short"]:
                return _Result(returncode=0, stdout="abc123\n")
            return _Result(returncode=0, stdout="")

        mock_run_cmd.side_effect = _run_cmd_side_effect
        mock_commit_if_changes.return_value = True

        worker_run.create_themed_prs(
            repo="test_repo",
            repo_dir=Path("/fake/repo"),
            source_branch="sichter/autofix-branch",
            auto_pr=True,
            findings=findings,
            review=None,
        )

        self.assertEqual(mock_create_or_update_pr.call_count, 2)
        called_titles = [kwargs.get("pr_title", "") for _, kwargs in mock_create_or_update_pr.call_args_list]
        self.assertTrue(any("style auto PR" in title for title in called_titles))
        self.assertTrue(any("security auto PR" in title for title in called_titles))

        # In a genuine multi-PR split, the global review must NOT be passed to themed PRs.
        for call in mock_create_or_update_pr.call_args_list:
            review_arg = call.kwargs.get("review")
            self.assertIsNone(review_arg,
                              "review must be None for themed PRs in multi-PR split")

        with patch("apps.worker.run.POLICY.checks", {"ruff": {"autofix": True}}):
            self.assertTrue(worker_run.is_check_enabled("ruff"))

        with patch("apps.worker.run.POLICY.checks", {"ruff": {"enabled": False}}):
            self.assertFalse(worker_run.is_check_enabled("ruff"))

    @patch("apps.worker.run.create_or_update_pr")
    def test_create_themed_prs_falls_back_on_overlapping_files(self, mock_create_or_update_pr):
        """When the same file has findings in multiple categories, themed split must not happen."""
        findings = [
            Finding(
                severity="warning",
                category="style",
                file="shared.py",
                line=1,
                message="style issue",
                tool="ruff",
                rule_id="E501",
            ),
            Finding(
                severity="error",
                category="security",
                file="shared.py",  # same file, different category
                line=5,
                message="security issue",
                tool="bandit",
                rule_id="B101",
            ),
        ]

        worker_run.create_themed_prs(
            repo="test_repo",
            repo_dir=Path("/fake/repo"),
            source_branch="sichter/autofix-branch",
            auto_pr=True,
            findings=findings,
            review=None,
        )

        # Must fall back to a single PR, not two themed PRs
        mock_create_or_update_pr.assert_called_once()
        args = mock_create_or_update_pr.call_args
        # Called without a custom pr_title (single-PR fallback)
        self.assertNotIn("pr_title", args.kwargs or {})

    @patch("apps.worker.run.create_or_update_pr")
    @patch("apps.worker.run.run_cmd")
    @patch("apps.worker.run.commit_if_changes")
    def test_create_themed_prs_review_passed_for_single_category(
        self,
        mock_commit_if_changes,
        mock_run_cmd,
        mock_create_or_update_pr,
    ):
        """When there is only one actionable category, the review is forwarded."""
        from lib.llm.review import ReviewResult

        fake_review = ReviewResult(
            summary="ok",
            risk_overall="low",
            uncertainty={"level": 0.1, "sources": [], "productive": False},
            suggestions=[],
            raw_response="{}",
            model="llama3",
            provider="ollama",
        )
        findings = [
            Finding(
                severity="warning",
                category="style",
                file="only.py",
                line=1,
                message="style issue",
                tool="ruff",
                rule_id="E501",
            ),
        ]

        worker_run.create_themed_prs(
            repo="test_repo",
            repo_dir=Path("/fake/repo"),
            source_branch="sichter/autofix-branch",
            auto_pr=True,
            findings=findings,
            review=fake_review,
        )

        mock_create_or_update_pr.assert_called_once()
        call = mock_create_or_update_pr.call_args
        self.assertIs(call.kwargs.get("review"), fake_review)

    @patch("apps.worker.run.create_or_update_pr")
    def test_create_themed_prs_single_category_returns_real_creation_status(
        self,
        mock_create_or_update_pr,
    ):
        findings = [
            Finding(
                severity="warning",
                category="style",
                file="only.py",
                line=1,
                message="style issue",
                tool="ruff",
                rule_id="E501",
            ),
        ]

        mock_create_or_update_pr.return_value = False
        result_false = worker_run.create_themed_prs(
            repo="test_repo",
            repo_dir=Path("/fake/repo"),
            source_branch="sichter/autofix-branch",
            auto_pr=True,
            findings=findings,
            review=None,
        )
        self.assertEqual(result_false, 0)

        mock_create_or_update_pr.return_value = True
        result_true = worker_run.create_themed_prs(
            repo="test_repo",
            repo_dir=Path("/fake/repo"),
            source_branch="sichter/autofix-branch",
            auto_pr=True,
            findings=findings,
            review=None,
        )
        self.assertEqual(result_true, 1)

    @patch("apps.worker.run.add_inline_pr_comments")
    @patch("apps.worker.run.run_gh_with_backoff")
    @patch("apps.worker.run.run_cmd")
    def test_create_or_update_pr_uses_backoff_for_create(
        self,
        mock_run_cmd,
        mock_run_gh_with_backoff,
        _mock_add_inline,
    ):
        class _Result:
            def __init__(self, returncode=0, stdout="", stderr=""):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        def _run_cmd_side_effect(cmd, cwd, check=True):
            if cmd[:2] == ["git", "push"]:
                return _Result(returncode=0)
            return _Result(returncode=0)

        state = {"view_calls": 0}

        def _backoff_side_effect(cmd, cwd):
            if cmd[:3] == ["gh", "pr", "view"]:
                state["view_calls"] += 1
                if state["view_calls"] == 1:
                    return _Result(returncode=1, stdout="", stderr="not found")
                return _Result(returncode=0, stdout="https://github.com/heimgewebe/sichter/pull/1\n")
            if cmd[:3] == ["gh", "pr", "create"]:
                return _Result(returncode=0, stdout="https://github.com/heimgewebe/sichter/pull/1\n")
            if cmd[:3] == ["gh", "pr", "edit"]:
                return _Result(returncode=0)
            return _Result(returncode=0)

        mock_run_cmd.side_effect = _run_cmd_side_effect
        mock_run_gh_with_backoff.side_effect = _backoff_side_effect

        created = worker_run.create_or_update_pr(
            repo="test_repo",
            repo_dir=Path("/fake/repo"),
            branch="sichter/autofix-branch",
            auto_pr=True,
            findings=[],
            review=None,
        )

        self.assertTrue(created)
        backoff_cmds = [call_args[0][0] for call_args in mock_run_gh_with_backoff.call_args_list]
        self.assertTrue(any(cmd[:3] == ["gh", "pr", "create"] for cmd in backoff_cmds))

    @patch("lib.config.get_policy_path")
    @patch("lib.config.load_yaml")
    def test_policy_load_max_parallel_repos_is_robust(self, mock_load_yaml, mock_get_policy_path):
        mock_path = unittest.mock.Mock()
        mock_path.exists.return_value = True
        mock_get_policy_path.return_value = mock_path

        mock_load_yaml.return_value = {"max_parallel_repos": "bad"}
        policy_bad = worker_run.Policy.load()
        self.assertEqual(policy_bad.max_parallel_repos, 4)

        mock_load_yaml.return_value = {"max_parallel_repos": 0}
        policy_zero = worker_run.Policy.load()
        self.assertEqual(policy_zero.max_parallel_repos, 1)

        mock_load_yaml.return_value = {"max_parallel_repos": -1}
        policy_negative = worker_run.Policy.load()
        self.assertEqual(policy_negative.max_parallel_repos, 1)

    @patch("apps.worker.run.run_redundancy_check", return_value=[])
    @patch("apps.worker.run.run_drift_check", return_value=[])
    @patch("apps.worker.run.run_hotspot_check", return_value=[])
    def test_run_heuristics_non_git_runs_only_file_based_checks(
        self,
        mock_hotspots,
        mock_drift,
        mock_redundancy,
    ):
        with patch("apps.worker.run.POLICY.checks", {}):
            worker_run.run_heuristics(Path("/definitely/not/a/git/repo"), None)

        mock_hotspots.assert_not_called()
        mock_drift.assert_called_once()
        mock_redundancy.assert_called_once()

    def test_select_autofix_targets_uses_fix_available_findings(self):
        tools, target_files = worker_run._select_autofix_targets(
            [
                Finding(
                    severity="error",
                    category="correctness",
                    file="src/app.py",
                    line=1,
                    message="Undefined name",
                    tool="ruff",
                    rule_id="F821",
                    fix_available=True,
                ),
                Finding(
                    severity="warning",
                    category="correctness",
                    file="src/app.py",
                    line=2,
                    message="Import unused",
                    tool="ruff",
                    rule_id="F401",
                    fix_available=True,
                ),
                Finding(
                    severity="warning",
                    category="correctness",
                    file="web/app.ts",
                    line=3,
                    message="Prefer const",
                    tool="eslint",
                    rule_id="prefer-const",
                    fix_available=True,
                ),
                Finding(
                    severity="error",
                    category="security",
                    file="secret.py",
                    line=4,
                    message="Potential secret",
                    tool="bandit",
                    rule_id="B105",
                    fix_available=True,
                ),
            ]
        )

        self.assertEqual(tools, {"ruff", "eslint"})
        self.assertEqual(target_files, {"ruff": [Path("src/app.py")], "eslint": [Path("web/app.ts")]})

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.commit_if_changes", return_value=False)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.ensure_repo")
    def test_process_repo_runs_heuristics_without_git_cache_eligibility(
        self,
        mock_ensure_repo,
        _mock_fresh_branch,
        _mock_registry_run_checks,
        _mock_registry_run_autofixes,
        _mock_llm_review,
        _mock_commit_if_changes,
        mock_run_heuristics,
        _mock_record_metrics,
    ):
        with unittest.mock.patch("pathlib.Path.exists", return_value=False):
            mock_ensure_repo.return_value = Path("/fake/repo")
            worker_run.process_repo("test_repo", "all", True)

        mock_run_heuristics.assert_called_once_with(Path("/fake/repo"), None)

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.create_themed_prs", return_value=1)
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"ruff": 1, "eslint": 0, "shfmt": 0})
    @patch("apps.worker.run.registry_run_checks")
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.ensure_repo", return_value=Path("/fake/repo"))
    def test_process_repo_reruns_checks_after_autofix_changes(
        self,
        _mock_ensure_repo,
        _mock_fresh_branch,
        mock_registry_run_checks,
        mock_registry_run_autofixes,
        _mock_llm_review,
        _mock_commit_if_changes,
        _mock_create_themed_prs,
        mock_run_heuristics,
        _mock_dedupe_findings,
        mock_record_snapshot,
        _mock_append_event,
        _mock_record_metrics,
    ):
        before_fix = Finding(
            severity="warning",
            category="correctness",
            file="src/app.py",
            line=1,
            message="Import unused",
            tool="ruff",
            rule_id="F401",
            fix_available=True,
        )
        after_fix = Finding(
            severity="warning",
            category="maintainability",
            file="README.md",
            line=1,
            message="Residual note",
            tool="docs",
            rule_id="DOC1",
        )
        mock_registry_run_checks.side_effect = [[before_fix], [after_fix]]

        worker_run.process_repo("demo-repo", "all", True)

        self.assertEqual(mock_registry_run_checks.call_count, 2)
        self.assertEqual(mock_run_heuristics.call_count, 1)
        self.assertEqual(
            mock_registry_run_autofixes.call_args.kwargs["only_tools"],
            {"ruff"},
        )
        self.assertEqual(
            mock_registry_run_autofixes.call_args.kwargs["target_files_by_tool"],
            {"ruff": [Path("src/app.py")]},
        )
        mock_record_snapshot.assert_called_once_with("demo-repo", [after_fix])

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={"k": []})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.create_themed_prs")
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.prepare_repo_base", return_value=True)
    @patch("apps.worker.run.has_commit_candidates", return_value=True)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 1})
    @patch("apps.worker.run.registry_run_checks")
    @patch("apps.worker.run.is_git_repository", return_value=True)
    @patch("apps.worker.run.ensure_repo", return_value=Path("/fake/repo"))
    @patch("apps.worker.run._filter_findings_for_prs", return_value=[])
    def test_process_repo_skips_pr_creation_when_all_findings_are_filtered(
        self,
        _mock_filter_findings,
        _mock_ensure_repo,
        _mock_is_git_repository,
        mock_registry_run_checks,
        _mock_registry_run_autofixes,
        _mock_has_commit_candidates,
        _mock_llm_review,
        _mock_prepare_repo_base,
        _mock_fresh_branch,
        _mock_commit_if_changes,
        mock_create_themed_prs,
        _mock_run_heuristics,
        _mock_dedupe_findings,
        _mock_record_snapshot,
        mock_append_event,
        _mock_record_metrics,
    ):
        mock_registry_run_checks.return_value = [
            Finding(
                severity="error",
                category="security",
                file="secret.py",
                line=1,
                message="Secret detected",
                tool="bandit",
                rule_id="B105",
            )
        ]

        worker_run.process_repo("demo-repo", "all", True)

        mock_create_themed_prs.assert_not_called()
        mock_append_event.assert_any_call(
            {
                "type": "pr_suppressed",
                "repo": "demo-repo",
                "branch": "test-branch",
                "categories": ["security"],
                "reason": "all_findings_filtered",
            }
        )

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

    def test_build_pr_body_no_findings_with_review_includes_review_section(self):
        """When findings is empty but a review is present, the review section must appear."""
        from lib.llm.review import ReviewResult

        review = ReviewResult(
            summary="Diff sieht sauber aus.",
            risk_overall="low",
            uncertainty={"level": 0.1, "sources": [], "productive": False},
            suggestions=[],
            raw_response="{}",
            model="test-model",
            provider="ollama",
        )

        body = worker_run.build_pr_body("demo-repo", findings=[], review=review)

        self.assertIn("Repository: demo-repo", body)
        self.assertIn("Keine strukturierten Findings", body)
        # The LLM review section must still appear
        self.assertIn("Diff sieht sauber aus.", body)
        self.assertIn("🟢", body)  # low-risk badge from to_pr_section()

    def test_build_pr_body_no_findings_no_review_is_minimal(self):
        """When neither findings nor review are present, body stays minimal."""
        body = worker_run.build_pr_body("demo-repo", findings=[], review=None)

        self.assertIn("Keine strukturierten Findings", body)
        keine_idx = body.index("Keine")
        self.assertNotIn("##", body[keine_idx:])

    @patch("apps.worker.run.append_event")
    def test_filter_findings_for_prs_suppresses_drift_by_default_and_logs_event(self, mock_append_event):
        findings = [
            Finding(
                severity="warning",
                category="drift",
                file="requirements.txt",
                line=None,
                message="Versionsdrift",
                tool="drift",
                rule_id="version_mismatch",
            ),
            Finding(
                severity="error",
                category="correctness",
                file="apps/main.py",
                line=10,
                message="Undefined name",
                tool="ruff",
                rule_id="F821",
            ),
        ]

        filtered = worker_run._filter_findings_for_prs(
            findings,
            {"drift": {"create_pr": False}},
            {},
            repo="demo-repo",
        )

        self.assertEqual([finding.category for finding in filtered], ["correctness"])
        mock_append_event.assert_any_call(
            {"type": "drift_findings_suppressed", "repo": "demo-repo", "count": 1}
        )

    @patch("apps.worker.run.notify_internal")
    @patch("apps.worker.run.append_event")
    def test_filter_findings_for_prs_suppresses_security_when_configured(self, mock_append_event, mock_notify_internal):
        findings = [
            Finding(
                severity="error",
                category="security",
                file="auth.py",
                line=4,
                message="Potential secret",
                tool="bandit",
                rule_id="B105",
            ),
            Finding(
                severity="warning",
                category="style",
                file="auth.py",
                line=8,
                message="Line too long",
                tool="ruff",
                rule_id="E501",
            ),
        ]

        filtered = worker_run._filter_findings_for_prs(
            findings,
            {},
            {"suppress_pr": True},
            repo="demo-repo",
        )

        self.assertEqual([finding.category for finding in filtered], ["style"])
        mock_append_event.assert_any_call(
            {"type": "security_findings_suppressed", "repo": "demo-repo", "count": 1}
        )
        mock_notify_internal.assert_called_once_with(
            "Sichter: demo-repo – 1 Security-Finding(s) per Policy unterdrückt"
        )

    @patch("apps.worker.run.append_event")
    def test_filter_findings_for_prs_handles_non_dict_policy_values(self, mock_append_event):
        findings = [
            Finding(
                severity="warning",
                category="drift",
                file="requirements.txt",
                line=None,
                message="Versionsdrift",
                tool="drift",
                rule_id="version_mismatch",
            ),
            Finding(
                severity="error",
                category="security",
                file="auth.py",
                line=4,
                message="Potential secret",
                tool="bandit",
                rule_id="B105",
            ),
        ]

        filtered = worker_run._filter_findings_for_prs(
            findings,
            "kaputt",
            "auch-kaputt",
            repo="demo-repo",
        )

        self.assertEqual([finding.category for finding in filtered], ["security"])
        mock_append_event.assert_any_call(
            {"type": "drift_findings_suppressed", "repo": "demo-repo", "count": 1}
        )

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={"k": []})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.create_themed_prs", return_value=1)
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.fresh_branch", return_value="test-branch")
    @patch("apps.worker.run.prepare_repo_base", return_value=True)
    @patch("apps.worker.run.has_commit_candidates", return_value=True)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks")
    @patch("apps.worker.run.is_git_repository", return_value=True)
    @patch("apps.worker.run.ensure_repo", return_value=Path("/fake/repo"))
    @patch("apps.worker.run.append_event")
    def test_process_repo_filters_findings_before_llm_review_and_pr_body(
        self,
        _mock_append_event,
        _mock_ensure_repo,
        _mock_is_git_repository,
        mock_registry_run_checks,
        _mock_registry_run_autofixes,
        mock_llm_review,
        _mock_has_commit_candidates,
        _mock_prepare_repo_base,
        _mock_fresh_branch,
        _mock_commit_if_changes,
        mock_create_themed_prs,
        _mock_run_heuristics,
        _mock_dedupe_findings,
        _mock_record_snapshot,
        _mock_record_metrics,
    ):
        security_finding = Finding(
            severity="error",
            category="security",
            file="secret.py",
            line=1,
            message="Secret detected",
            tool="bandit",
            rule_id="B105",
        )
        style_finding = Finding(
            severity="warning",
            category="style",
            file="style.py",
            line=2,
            message="Line too long",
            tool="ruff",
            rule_id="E501",
        )
        mock_registry_run_checks.return_value = [security_finding, style_finding]

        with patch("apps.worker.run.POLICY.checks", {"drift": {"create_pr": False}}), \
             patch("apps.worker.run.POLICY.security", {"suppress_pr": True}):
            worker_run.process_repo("demo-repo", "all", True)

        mock_llm_review.assert_called_once()
        llm_findings = mock_llm_review.call_args[0][2]
        self.assertEqual([finding.category for finding in llm_findings], ["style"])

        mock_create_themed_prs.assert_called_once()
        pr_findings = mock_create_themed_prs.call_args[0][4]
        self.assertEqual([finding.category for finding in pr_findings], ["style"])

    def test_build_pr_body_includes_affected_files_table_and_verification_hints(self):
        findings = [
            Finding(
                severity="question",
                category="maintainability",
                file="docs/guide.md",
                line=7,
                message="Need clarification",
                tool="docs",
                rule_id="DOC1",
            ),
            Finding(
                severity="critical",
                category="security",
                file="src/app.py",
                line=12,
                message="Credential leak",
                tool="bandit",
                rule_id="B105",
            ),
            Finding(
                severity="warning",
                category="security",
                file="src/app.py",
                line=20,
                message="Weak entropy",
                tool="bandit",
                rule_id="B311",
            ),
            Finding(
                severity="warning",
                category="drift",
                file="requirements.txt",
                line=None,
                message="Pinned versions diverge",
                tool="drift",
                rule_id="version_mismatch",
            ),
            Finding(
                severity="info",
                category="correctness",
                file="",
                line=None,
                message="No file attached",
                tool="meta",
                rule_id="META1",
            ),
        ]

        body = worker_run.build_pr_body("demo-repo", findings)

        self.assertIn("### Betroffene Dateien", body)
        self.assertIn("| src/app.py | 2 | critical |", body)
        self.assertIn("| docs/guide.md | 1 | question |", body)
        self.assertIn("| requirements.txt | 1 | warning |", body)
        self.assertNotIn("|  |", body)
        self.assertIn("### Verifikationshinweise", body)
        self.assertIn("- **drift**: ✓ Versionsquellen und gewünschte Pinning-Strategie abgleichen", body)
        self.assertIn("- **security**: ✓ Keine Credentials, Secrets oder sensitiven Daten in Code prüfen", body)
        self.assertIn("- **maintainability**: ✓ Leserbarkeit, Duplikationen, Dokumentation überprüfen", body)

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
             patch("lib.llm.factory.get_provider") as mock_get_provider, \
             patch("lib.llm.budget.ReviewBudget") as mock_budget_cls:
            mock_budget_cls.return_value.allow_review.return_value = True
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
             patch("apps.worker.run.append_event"), \
             patch("apps.worker.run.persist_review_result"), \
             patch("lib.llm.budget.ReviewBudget") as mock_budget_cls:
            mock_budget = mock_budget_cls.return_value
            mock_budget.allow_review.return_value = True
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
        mock_budget.record_review.assert_called_once()

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
             patch("apps.worker.run.append_event"), \
             patch("apps.worker.run.persist_review_result"), \
             patch("lib.llm.budget.ReviewBudget") as mock_budget_cls:
            mock_budget_cls.return_value.allow_review.return_value = True
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

    @patch("apps.worker.run.append_event")
    def test_llm_review_skips_when_rate_limit_reached(self, mock_append_event):
        with patch("apps.worker.run.POLICY") as mock_policy, \
             patch("lib.llm.budget.ReviewBudget") as mock_budget_cls, \
             patch("lib.llm.factory.get_provider") as mock_get_provider:
            mock_policy.llm = {"enabled": True, "max_reviews_per_hour": 1}
            mock_budget = mock_budget_cls.return_value
            mock_budget.allow_review.return_value = False
            mock_budget.reviews_in_last_hour.return_value = 1

            result = worker_run.llm_review("repo", Path("/fake/repo"), findings=[
                Finding(
                    severity="warning",
                    category="correctness",
                    file="f.py",
                    line=1,
                    message="m",
                    tool="ruff",
                    rule_id="E1",
                )
            ])

        self.assertIsNone(result)
        mock_get_provider.assert_not_called()
        event = mock_append_event.call_args_list[0][0][0]
        self.assertEqual(event.get("type"), "llm_review_skipped")
        self.assertEqual(event.get("reason"), "rate_limit")

    @patch("apps.worker.run.run_cmd")
    def test_llm_review_invalid_max_reviews_falls_back_to_default(self, mock_run_cmd):
        """Non-numeric max_reviews_per_hour must not crash or disable reviews."""
        mock_run_cmd.return_value.stdout = "diff --git a/x.py b/x.py\n+line"
        mock_run_cmd.return_value.returncode = 0

        provider = unittest.mock.Mock()
        provider.complete.return_value = (
            '{"summary":"ok","risk_overall":"low",'
            '"uncertainty":{"level":0.1,"sources":[],"productive":false},'
            '"suggestions":[]}',
            10,
        )
        provider.model = "llama3"
        provider.provider_name = "ollama"

        with patch("apps.worker.run.POLICY") as mock_policy, \
             patch("lib.llm.factory.get_provider", return_value=provider), \
             patch("apps.worker.run.append_event"), \
             patch("apps.worker.run.persist_review_result"), \
             patch("lib.llm.budget.ReviewBudget") as mock_budget_cls:
            mock_budget = mock_budget_cls.return_value
            mock_budget.allow_review.return_value = True
            mock_policy.llm = {
                "enabled": True,
                "max_reviews_per_hour": "not-a-number",
            }

            result = worker_run.llm_review("repo", Path("/fake/repo"), findings=[])

        # Should succeed using default of 20; allow_review called with 20
        mock_budget.allow_review.assert_called_once_with(max_reviews_per_hour=20)
        self.assertIsNotNone(result)

    @patch("apps.worker.run.run_cmd")
    def test_llm_review_invalid_max_tokens_falls_back_to_default(self, mock_run_cmd):
        """Non-numeric max_tokens_per_review must not crash; falls back to 4000."""
        mock_run_cmd.return_value.stdout = "diff --git a/x.py b/x.py\n+line"
        mock_run_cmd.return_value.returncode = 0

        provider = unittest.mock.Mock()
        provider.complete.return_value = (
            '{"summary":"ok","risk_overall":"low",'
            '"uncertainty":{"level":0.1,"sources":[],"productive":false},'
            '"suggestions":[]}',
            10,
        )
        provider.model = "llama3"
        provider.provider_name = "ollama"

        with patch("apps.worker.run.POLICY") as mock_policy, \
             patch("lib.llm.factory.get_provider", return_value=provider), \
             patch("apps.worker.run.append_event"), \
             patch("apps.worker.run.persist_review_result"), \
             patch("lib.llm.budget.ReviewBudget") as mock_budget_cls:
            mock_budget = mock_budget_cls.return_value
            mock_budget.allow_review.return_value = True
            mock_policy.llm = {
                "enabled": True,
                "max_tokens_per_review": "bad",
            }

            result = worker_run.llm_review("repo", Path("/fake/repo"), findings=[])

        # Should succeed using default of 4000 tokens
        provider.complete.assert_called_once()
        _, call_kwargs = provider.complete.call_args
        self.assertEqual(call_kwargs.get("max_tokens"), 4000)
        self.assertIsNotNone(result)

    @patch("apps.worker.run.run_cmd")
    def test_llm_review_uses_fallback_provider_on_error(self, mock_run_cmd):
        mock_run_cmd.return_value.stdout = "diff --git a/x.py b/x.py\n+line"
        mock_run_cmd.return_value.returncode = 0

        primary_provider = unittest.mock.Mock()
        primary_provider.complete.side_effect = RuntimeError("primary down")
        primary_provider.model = "qwen"
        primary_provider.provider_name = "ollama"

        fallback_provider = unittest.mock.Mock()
        fallback_provider.complete.return_value = (
            '{"summary":"ok","risk_overall":"low",'
            '"uncertainty":{"level":0.1,"sources":[],"productive":false},'
            '"suggestions":[]}',
            42,
        )
        fallback_provider.model = "gpt-4o-mini"
        fallback_provider.provider_name = "openai"

        with patch("apps.worker.run.POLICY") as mock_policy, \
             patch("lib.llm.factory.get_provider", side_effect=[primary_provider, fallback_provider]), \
             patch("apps.worker.run.append_event") as mock_append_event, \
             patch("apps.worker.run.persist_review_result"), \
             patch("lib.llm.budget.ReviewBudget") as mock_budget_cls:
            mock_budget = mock_budget_cls.return_value
            mock_budget.allow_review.return_value = True
            mock_policy.llm = {
                "enabled": True,
                "provider": "ollama",
                "fallback": {"provider": "openai", "model": "gpt-4o-mini"},
            }

            result = worker_run.llm_review("repo", Path("/fake/repo"), findings=[])

        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.provider_switched)
        self.assertEqual(result.provider, "openai")
        fallback_events = [
            c[0][0]
            for c in mock_append_event.call_args_list
            if c[0] and isinstance(c[0][0], dict) and c[0][0].get("type") == "llm_provider_fallback"
        ]
        self.assertEqual(len(fallback_events), 1)

    # ------------------------------------------------------------------
    # Cache-key correctness: mode="changed" must bypass cache
    # ------------------------------------------------------------------

    @patch("apps.worker.run.cache_set")
    @patch("apps.worker.run.cache_get")
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.commit_if_changes", return_value=False)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.fresh_branch", return_value="b")
    @patch("apps.worker.run.ensure_repo")
    def test_process_repo_changed_mode_skips_cache(
        self,
        mock_ensure_repo,
        _fresh_branch,
        _checks,
        _autofixes,
        _llm,
        _commit,
        _heuristics,
        mock_cache_get,
        mock_cache_set,
    ):
        """mode='changed' must never read from or write to the findings cache."""
        from pathlib import Path as _Path
        import tempfile, os

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = _Path(tmpdir)
            git_dir = repo_dir / ".git"
            git_dir.mkdir()
            mock_ensure_repo.return_value = repo_dir

            with patch("apps.worker.run.get_changed_files", return_value=[repo_dir / "a.py"]):
                worker_run.process_repo("test_repo", "changed", False)

        mock_cache_get.assert_not_called()
        mock_cache_set.assert_not_called()

    @patch("apps.worker.run.cache_set")
    @patch("apps.worker.run.cache_get", return_value=None)
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.commit_if_changes", return_value=False)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.fresh_branch", return_value="b")
    @patch("apps.worker.run.ensure_repo")
    def test_process_repo_all_mode_uses_cache(
        self,
        mock_ensure_repo,
        _fresh_branch,
        _checks,
        _autofixes,
        _llm,
        _commit,
        _heuristics,
        mock_cache_get,
        mock_cache_set,
    ):
        """mode='all' (changed_files=None) on a real git repo SHOULD attempt cache read/write."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)
            (repo_dir / ".git").mkdir()
            mock_ensure_repo.return_value = repo_dir

            worker_run.process_repo("test_repo", "all", False)

        mock_cache_get.assert_called_once()
        # cache_set called because cache_get returned None (miss) and git repo exists
        mock_cache_set.assert_called_once()

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.commit_if_changes", return_value=False)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"ruff": 1, "eslint": 0, "shfmt": 0})
    @patch("apps.worker.run.registry_run_checks")
    @patch("apps.worker.run.fresh_branch", return_value="b")
    @patch("apps.worker.run.ensure_repo")
    @patch("apps.worker.run.current_commit", return_value="abc123")
    @patch("apps.worker.run.cache_set")
    @patch("apps.worker.run.cache_get", return_value=None)
    def test_process_repo_keeps_cache_bound_to_pre_autofix_commit_state(
        self,
        mock_cache_get,
        mock_cache_set,
        _mock_current_commit,
        mock_ensure_repo,
        _fresh_branch,
        mock_registry_run_checks,
        _autofixes,
        _llm,
        _commit,
        _heuristics,
        _dedupe,
        _record_snapshot,
        _record_metrics,
    ):
        """Post-autofix re-scan must not overwrite the commit-keyed pre-fix cache entry."""
        before_fix = Finding(
            severity="warning",
            category="correctness",
            file="src/app.py",
            line=1,
            message="Import unused",
            tool="ruff",
            rule_id="F401",
            fix_available=True,
        )
        after_fix = Finding(
            severity="warning",
            category="maintainability",
            file="README.md",
            line=1,
            message="Residual note",
            tool="docs",
            rule_id="DOC1",
        )
        mock_registry_run_checks.side_effect = [[before_fix], [after_fix]]

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_dir = Path(tmpdir)
            (repo_dir / ".git").mkdir()
            mock_ensure_repo.return_value = repo_dir

            worker_run.process_repo("test_repo", "all", False)

        mock_cache_get.assert_called_once()
        mock_cache_set.assert_called_once()
        self.assertEqual(
            mock_cache_set.call_args.args[1],
            {"findings": worker_run.serialize_findings([before_fix])},
        )
        self.assertEqual(mock_registry_run_checks.call_count, 2)

    # ------------------------------------------------------------------
    # Repo deduplication before parallel dispatch
    # ------------------------------------------------------------------

    @patch("apps.worker.run.process_repo")
    def test_handle_job_deduplicates_repos_before_parallel(self, mock_process_repo):
        """Duplicate repo entries in a job must not produce duplicate process_repo calls."""
        job = {"repos": ["org/a", "org/b", "org/a"], "mode": "all"}
        worker_run.handle_job(job)

        called_repos = [c[0][0] for c in mock_process_repo.call_args_list]
        self.assertEqual(called_repos.count("org/a"), 1)
        self.assertEqual(called_repos.count("org/b"), 1)

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.create_themed_prs")
    @patch("apps.worker.run.commit_if_changes")
    @patch("apps.worker.run.fresh_branch")
    @patch("apps.worker.run.has_commit_candidates", return_value=False)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.prepare_repo_base")
    @patch("apps.worker.run.is_git_repository", return_value=True)
    @patch("apps.worker.run.ensure_repo", return_value=Path("/fake/repo"))
    def test_process_repo_nochange_does_not_create_branch(
        self,
        _mock_ensure_repo,
        _mock_is_git_repository,
        _mock_prepare_repo_base,
        _mock_registry_run_checks,
        _mock_registry_run_autofixes,
        _mock_llm_review,
        _mock_has_commit_candidates,
        mock_fresh_branch,
        mock_commit_if_changes,
        mock_create_themed_prs,
        _mock_run_heuristics,
        _mock_dedupe_findings,
        _mock_record_snapshot,
        mock_append_event,
        _mock_record_metrics,
    ):
        worker_run.process_repo("demo-repo", "all", True)

        mock_fresh_branch.assert_not_called()
        _mock_prepare_repo_base.assert_not_called()
        mock_commit_if_changes.assert_not_called()
        mock_create_themed_prs.assert_not_called()
        mock_append_event.assert_any_call({"type": "noop", "repo": "demo-repo", "branch": "-"})

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.create_themed_prs", return_value=1)
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.fresh_branch", return_value="sichter/autofix-x")
    @patch("apps.worker.run.has_commit_candidates", return_value=True)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.prepare_repo_base")
    @patch("apps.worker.run.is_git_repository", return_value=True)
    @patch("apps.worker.run.ensure_repo", return_value=Path("/fake/repo"))
    def test_process_repo_creates_branch_only_after_change_detection(
        self,
        _mock_ensure_repo,
        _mock_is_git_repository,
        _mock_prepare_repo_base,
        _mock_registry_run_checks,
        _mock_registry_run_autofixes,
        _mock_llm_review,
        _mock_has_commit_candidates,
        mock_fresh_branch,
        mock_commit_if_changes,
        mock_create_themed_prs,
        _mock_run_heuristics,
        _mock_dedupe_findings,
        _mock_record_snapshot,
        _mock_append_event,
        _mock_record_metrics,
    ):
        worker_run.process_repo("demo-repo", "all", True)

        _mock_prepare_repo_base.assert_called_once_with(Path("/fake/repo"))
        mock_fresh_branch.assert_called_once_with(Path("/fake/repo"))
        mock_commit_if_changes.assert_called_once_with(
            Path("/fake/repo"),
            stage_all=True,
            excludes=(),
        )
        mock_create_themed_prs.assert_called_once()

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.create_themed_prs")
    @patch("apps.worker.run.commit_if_changes")
    @patch("apps.worker.run.fresh_branch")
    @patch("apps.worker.run.has_commit_candidates", return_value=False)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.prepare_repo_base")
    @patch("apps.worker.run.is_git_repository", return_value=True)
    @patch("apps.worker.run.ensure_repo", return_value=Path("/fake/repo"))
    def test_process_repo_excludes_self_runtime_logs_from_commit_candidates(
        self,
        _mock_ensure_repo,
        _mock_is_git_repository,
        _mock_prepare_repo_base,
        _mock_registry_run_checks,
        _mock_registry_run_autofixes,
        _mock_llm_review,
        mock_has_commit_candidates,
        _mock_fresh_branch,
        _mock_commit_if_changes,
        _mock_create_themed_prs,
        _mock_run_heuristics,
        _mock_dedupe_findings,
        _mock_record_snapshot,
        _mock_record_metrics,
    ):
        worker_run.process_repo("sichter", "all", True)
        args = mock_has_commit_candidates.call_args[0]
        self.assertEqual(args[0], Path("/fake/repo"))
        self.assertEqual(tuple(args[1]), ("logs/**",))

    @patch("apps.worker.run.run_cmd")
    def test_has_commit_candidates_detects_untracked_file(self, mock_run_cmd):
        mock_run_cmd.return_value = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="?? new-file.py\0",
            stderr="",
        )

        self.assertTrue(worker_run.has_commit_candidates(Path("/fake/repo")))

    @patch("apps.worker.run.run_cmd")
    def test_has_commit_candidates_returns_false_for_excluded_only_changes(self, mock_run_cmd):
        mock_run_cmd.return_value = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="?? logs/run.md\0",
            stderr="",
        )

        self.assertFalse(
            worker_run.has_commit_candidates(
                Path("/fake/repo"),
                excludes=("logs/**",),
            )
        )

    @patch("apps.worker.run.run_cmd")
    def test_has_commit_candidates_detects_rename_target(self, mock_run_cmd):
        mock_run_cmd.return_value = subprocess.CompletedProcess(
            args=["git", "status"],
            returncode=0,
            stdout="R  old-name.py\0new-name.py\0",
            stderr="",
        )

        self.assertTrue(worker_run.has_commit_candidates(Path("/fake/repo")))

    @patch("apps.worker.run.process_repo")
    @patch("apps.worker.run.list_repos_local", return_value=["sichter", "repo-a", ".idea", "exports", "repo-a"])
    def test_handle_job_discovery_excludes_self_by_default(self, _mock_list_local, mock_process_repo):
        worker_run.handle_job({"mode": "changed"})

        called_repos = [c[0][0] for c in mock_process_repo.call_args_list]
        self.assertEqual(called_repos, ["repo-a"])

    @patch("apps.worker.run.process_repo")
    @patch("apps.worker.run.list_repos_local", return_value=["sichter", "repo-a"])
    def test_handle_job_include_self_allows_self_repo(self, _mock_list_local, mock_process_repo):
        worker_run.handle_job({"mode": "changed", "include_self": True})

        called_repos = [c[0][0] for c in mock_process_repo.call_args_list]
        self.assertIn("sichter", called_repos)
        self.assertIn("repo-a", called_repos)

    # ------------------------------------------------------------------
    # Base preparation gating: branch creation only after verified base
    # ------------------------------------------------------------------

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.create_themed_prs", return_value=1)
    @patch("apps.worker.run.commit_if_changes", return_value=True)
    @patch("apps.worker.run.fresh_branch", return_value="sichter/autofix-x")
    @patch("apps.worker.run.has_commit_candidates", return_value=True)
    @patch("apps.worker.run.prepare_repo_base", return_value=False)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.is_git_repository", return_value=True)
    @patch("apps.worker.run.ensure_repo", return_value=Path("/fake/repo"))
    def test_process_repo_skips_branch_on_base_prep_failure(
        self,
        _mock_ensure_repo,
        _mock_is_git_repository,
        _mock_registry_run_checks,
        _mock_registry_run_autofixes,
        _mock_llm_review,
        mock_prepare_repo_base,
        mock_has_commit_candidates,
        mock_fresh_branch,
        mock_commit_if_changes,
        mock_create_themed_prs,
        _mock_run_heuristics,
        _mock_dedupe_findings,
        _mock_record_snapshot,
        mock_append_event,
        _mock_record_metrics,
    ):
        """When base preparation fails, no branch/commit/PR should be created."""
        worker_run.process_repo("demo-repo", "all", True)

        # Change was detected
        mock_has_commit_candidates.assert_called_once()
        # Base preparation was attempted
        mock_prepare_repo_base.assert_called_once_with(Path("/fake/repo"))
        # But branch/commit/PR creation skipped due to base prep failure
        mock_fresh_branch.assert_not_called()
        mock_commit_if_changes.assert_not_called()
        mock_create_themed_prs.assert_not_called()

        # Verify that a "skipped" event was logged
        mock_append_event.assert_any_call(
            {
                "type": "skipped",
                "repo": "demo-repo",
                "reason": "base_preparation_failed",
                "message": "Changes detected in demo-repo aber Base-Detach fehlgeschlagen; branch creation skipped",
            }
        )

    @patch("apps.worker.run.record_metrics")
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.record_findings_snapshot")
    @patch("apps.worker.run.dedupe_findings", return_value={})
    @patch("apps.worker.run.run_heuristics", return_value=[])
    @patch("apps.worker.run.create_themed_prs")
    @patch("apps.worker.run.commit_if_changes")
    @patch("apps.worker.run.fresh_branch")
    @patch("apps.worker.run.has_commit_candidates", return_value=False)
    @patch("apps.worker.run.llm_review", return_value=None)
    @patch("apps.worker.run.registry_run_autofixes", return_value={"shfmt": 0})
    @patch("apps.worker.run.registry_run_checks", return_value=[])
    @patch("apps.worker.run.prepare_repo_base")
    @patch("apps.worker.run.is_git_repository", return_value=False)
    @patch("apps.worker.run.ensure_repo", return_value=Path("/fake/repo"))
    def test_process_repo_nongit_no_operations(
        self,
        _mock_ensure_repo,
        mock_is_git_repository,
        _mock_prepare_repo_base,
        _mock_registry_run_checks,
        _mock_registry_run_autofixes,
        _mock_llm_review,
        _mock_has_commit_candidates,
        _mock_fresh_branch,
        _mock_commit_if_changes,
        _mock_create_themed_prs,
        _mock_run_heuristics,
        _mock_dedupe_findings,
        _mock_record_snapshot,
        _mock_append_event,
        _mock_record_metrics,
    ):
        """Non-git repos must not trigger any Git operations."""
        worker_run.process_repo("non-git-repo", "all", True)

        # has_commit_candidates should never be called for non-git repos
        _mock_has_commit_candidates.assert_not_called()
        # prepare_repo_base should never be called
        _mock_prepare_repo_base.assert_not_called()
        # No branch/commit operations
        _mock_fresh_branch.assert_not_called()
        _mock_commit_if_changes.assert_not_called()
        _mock_create_themed_prs.assert_not_called()

    # ------------------------------------------------------------------
    # Rate-limit detection: "403" alone must NOT trigger backoff
    # ------------------------------------------------------------------

    @patch("apps.worker.run.time")
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.run_cmd")
    def test_run_gh_with_backoff_ignores_plain_403(self, mock_run_cmd, mock_append_event, mock_time):
        """A plain 403 (permission/auth denial) must not trigger exponential backoff sleep."""
        class _Res:
            returncode = 1
            stdout = ""
            stderr = "error: 403 Forbidden – repository access denied"

        mock_run_cmd.return_value = _Res()
        worker_run.run_gh_with_backoff(["gh", "pr", "view", "branch"], Path("/fake"))

        mock_time.sleep.assert_not_called()
        mock_append_event.assert_not_called()

    @patch("apps.worker.run.time")
    @patch("apps.worker.run.append_event")
    @patch("apps.worker.run.run_cmd")
    def test_run_gh_with_backoff_triggers_on_rate_limit(self, mock_run_cmd, mock_append_event, mock_time):
        """'rate limit' in stderr must trigger at least one backoff sleep."""
        call_count = {"n": 0}

        class _Res:
            returncode = 1
            stdout = ""
            stderr = "error: secondary rate limit exceeded"

        mock_run_cmd.return_value = _Res()
        worker_run.run_gh_with_backoff(["gh", "pr", "view", "branch"], Path("/fake"))

        # sleep must have been invoked at least once
        mock_time.sleep.assert_called()
        mock_append_event.assert_called()


if __name__ == "__main__":
    unittest.main()

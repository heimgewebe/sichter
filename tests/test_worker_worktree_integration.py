from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from apps.worker import run as worker_run


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    effective = cmd
    if cmd and cmd[0] == "git":
        effective = ["git", "-c", "core.hooksPath=/dev/null", *cmd[1:]]
    return subprocess.run(effective, cwd=cwd, text=True, capture_output=True, check=True)


def test_worker_process_repo_keeps_primary_head_and_reflog_clean(tmp_path: Path):
    origin = tmp_path / "origin.git"
    _run(["git", "init", "--bare", str(origin)], tmp_path)

    seed = tmp_path / "seed"
    _run(["git", "clone", str(origin), str(seed)], tmp_path)
    _run(["git", "checkout", "-b", "main"], seed)
    _run(["git", "config", "user.name", "Test"], seed)
    _run(["git", "config", "user.email", "test@example.com"], seed)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _run(["git", "add", "README.md"], seed)
    _run(["git", "commit", "-m", "seed"], seed)
    _run(["git", "push", "-u", "origin", "main"], seed)

    target = tmp_path / "demo-repo"
    _run(["git", "clone", str(origin), str(target)], tmp_path)
    _run(["git", "checkout", "main"], target)
    _run(["git", "config", "user.name", "Test"], target)
    _run(["git", "config", "user.email", "test@example.com"], target)

    before_head = _run(["git", "rev-parse", "HEAD"], target).stdout.strip()
    before_reflog_lines = _run(["git", "reflog", "--format=%gs"], target).stdout.splitlines()

    def _autofix_side_effect(repo_dir: Path, *_args, **_kwargs):
        readme = repo_dir / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "worker change\n", encoding="utf-8")
        return {"shfmt": 1}

    with patch("apps.worker.run.ensure_repo", return_value=target), patch(
        "apps.worker.run.registry_run_checks", return_value=[]
    ), patch("apps.worker.run.registry_run_autofixes", side_effect=_autofix_side_effect), patch(
        "apps.worker.run.run_heuristics", return_value=[]
    ), patch("apps.worker.run.llm_review", return_value=None), patch(
        "apps.worker.run.dedupe_findings", return_value={}
    ), patch("apps.worker.run.record_findings_snapshot"), patch("apps.worker.run.record_metrics"):
        worker_run.process_repo("demo-repo", "all", False)

    after_head = _run(["git", "rev-parse", "HEAD"], target).stdout.strip()
    after_branch = _run(["git", "symbolic-ref", "--short", "HEAD"], target).stdout.strip()
    after_reflog_lines = _run(["git", "reflog", "--format=%gs"], target).stdout.splitlines()
    reflog_delta = after_reflog_lines[: max(0, len(after_reflog_lines) - len(before_reflog_lines))]

    assert after_head == before_head
    assert after_branch == "main"
    assert all("checkout" not in line and "switch" not in line for line in reflog_delta)

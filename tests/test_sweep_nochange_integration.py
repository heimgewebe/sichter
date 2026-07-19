from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _git_test_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = (base or os.environ).copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Sichter Tests",
            "GIT_AUTHOR_EMAIL": "tests@example.invalid",
            "GIT_COMMITTER_NAME": "Sichter Tests",
            "GIT_COMMITTER_EMAIL": "tests@example.invalid",
        }
    )
    return env


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    effective_cmd = cmd
    effective_env = env
    if cmd and cmd[0] == "git":
        effective_cmd = ["git", "-c", "core.hooksPath=/dev/null", *cmd[1:]]
        effective_env = _git_test_env(env)
    return subprocess.run(
        effective_cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=True,
        env=effective_env,
    )


def test_sichter_pr_sweep_changed_nochange_creates_no_autofix_ref(tmp_path: Path):
    home = tmp_path / "home"
    repos_dir = home / "repos"
    repos_dir.mkdir(parents=True)

    origin = tmp_path / "origin.git"
    _run(["git", "init", "--bare", str(origin)], tmp_path)

    seed = tmp_path / "seed"
    _run(["git", "clone", str(origin), str(seed)], tmp_path)
    _run(["git", "checkout", "-b", "main"], seed)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _run(["git", "add", "README.md"], seed)
    _run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "seed"], seed)
    _run(["git", "push", "-u", "origin", "main"], seed)

    target = repos_dir / "demo-repo"
    _run(["git", "clone", str(origin), str(target)], tmp_path)
    _run(["git", "checkout", "main"], target)

    hook_dir = home / "sichter" / "hooks"
    hook_dir.mkdir(parents=True)
    hook = hook_dir / "post-run"
    hook.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    script = Path(__file__).resolve().parents[1] / "bin" / "sichter-pr-sweep"
    env = _git_test_env()
    env["HOME"] = str(home)
    env["SICHTER_SELF_REPO_NAME"] = "sichter"
    env["SICHTER_INCLUDE_SELF_REPO"] = "false"
    env["SICHTER_AUTO_PR"] = "0"

    result = subprocess.run(
        [str(script), "--changed"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )

    refs = _run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/sichter/autofix-*"], target)
    reflog = _run(["git", "reflog", "--date=iso"], target)
    assert refs.stdout.strip() == ""
    assert "branch=-" in result.stdout
    assert "sichter/autofix-" not in reflog.stdout


def test_sichter_pr_sweep_changed_untracked_file_is_not_skipped(tmp_path: Path):
    home = tmp_path / "home"
    repos_dir = home / "repos"
    repos_dir.mkdir(parents=True)

    origin = tmp_path / "origin.git"
    _run(["git", "init", "--bare", str(origin)], tmp_path)

    seed = tmp_path / "seed"
    _run(["git", "clone", str(origin), str(seed)], tmp_path)
    _run(["git", "checkout", "-b", "main"], seed)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _run(["git", "add", "README.md"], seed)
    _run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "seed"], seed)
    _run(["git", "push", "-u", "origin", "main"], seed)

    target = repos_dir / "demo-repo"
    _run(["git", "clone", str(origin), str(target)], tmp_path)
    _run(["git", "checkout", "main"], target)
    (target / "new-file.txt").write_text("local only\n", encoding="utf-8")

    hook_dir = home / "sichter" / "hooks"
    hook_dir.mkdir(parents=True)
    hook = hook_dir / "post-run"
    hook.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    script = Path(__file__).resolve().parents[1] / "bin" / "sichter-pr-sweep"
    env = _git_test_env()
    env["HOME"] = str(home)
    env["SICHTER_SELF_REPO_NAME"] = "sichter"
    env["SICHTER_INCLUDE_SELF_REPO"] = "false"
    env["SICHTER_AUTO_PR"] = "0"

    result = subprocess.run(
        [str(script), "--changed"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )

    refs = _run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/sichter/autofix-*"], target)
    assert "no_relevant_changes" not in result.stdout
    assert "[RESULT][COMMIT] repo=demo-repo branch=sichter/autofix-" in result.stdout
    branch = refs.stdout.strip()
    assert branch.startswith("sichter/autofix-")
    committed_new_file = _run(["git", "show", f"{branch}:new-file.txt"], target)
    assert committed_new_file.stdout == "local only\n"


def test_sichter_pr_sweep_changed_tracked_working_tree_change_is_not_skipped(tmp_path: Path):
    home = tmp_path / "home"
    repos_dir = home / "repos"
    repos_dir.mkdir(parents=True)

    origin = tmp_path / "origin.git"
    _run(["git", "init", "--bare", str(origin)], tmp_path)

    seed = tmp_path / "seed"
    _run(["git", "clone", str(origin), str(seed)], tmp_path)
    _run(["git", "checkout", "-b", "main"], seed)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _run(["git", "add", "README.md"], seed)
    _run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "seed"], seed)
    _run(["git", "push", "-u", "origin", "main"], seed)

    target = repos_dir / "demo-repo"
    _run(["git", "clone", str(origin), str(target)], tmp_path)
    _run(["git", "checkout", "main"], target)
    (target / "README.md").write_text("seed\ntracked local change\n", encoding="utf-8")

    hook_dir = home / "sichter" / "hooks"
    hook_dir.mkdir(parents=True)
    hook = hook_dir / "post-run"
    hook.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    script = Path(__file__).resolve().parents[1] / "bin" / "sichter-pr-sweep"
    env = _git_test_env()
    env["HOME"] = str(home)
    env["SICHTER_SELF_REPO_NAME"] = "sichter"
    env["SICHTER_INCLUDE_SELF_REPO"] = "false"
    env["SICHTER_AUTO_PR"] = "0"

    result = subprocess.run(
        [str(script), "--changed"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )

    refs = _run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/sichter/autofix-*"], target)
    assert "no_relevant_changes" not in result.stdout
    assert "[RESULT][COMMIT] repo=demo-repo branch=sichter/autofix-" in result.stdout
    branch = refs.stdout.strip()
    assert branch.startswith("sichter/autofix-")
    committed_readme = _run(["git", "show", f"{branch}:README.md"], target)
    assert committed_readme.stdout == "seed\ntracked local change\n"


def test_sichter_pr_sweep_dry_run_observes_changes_without_refs_or_remote_effects(tmp_path: Path):
    home = tmp_path / "home"
    repos_dir = home / "repos"
    repos_dir.mkdir(parents=True)

    origin = tmp_path / "origin.git"
    _run(["git", "init", "--bare", str(origin)], tmp_path)

    seed = tmp_path / "seed"
    _run(["git", "clone", str(origin), str(seed)], tmp_path)
    _run(["git", "checkout", "-b", "main"], seed)
    (seed / "README.md").write_text("seed\n", encoding="utf-8")
    _run(["git", "add", "README.md"], seed)
    _run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "seed"], seed)
    _run(["git", "push", "-u", "origin", "main"], seed)

    target = repos_dir / "demo-repo"
    _run(["git", "clone", str(origin), str(target)], tmp_path)
    _run(["git", "checkout", "main"], target)
    (target / "new-file.txt").write_text("local only\n", encoding="utf-8")
    source_head = _run(["git", "rev-parse", "HEAD"], target).stdout.strip()

    hook_dir = home / "sichter" / "hooks"
    hook_dir.mkdir(parents=True)
    hook = hook_dir / "post-run"
    hook.write_text("#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n", encoding="utf-8")
    hook.chmod(0o755)

    script = Path(__file__).resolve().parents[1] / "bin" / "sichter-pr-sweep"
    env = _git_test_env()
    env["HOME"] = str(home)
    env["SICHTER_SELF_REPO_NAME"] = "sichter"
    env["SICHTER_INCLUDE_SELF_REPO"] = "false"
    env["SICHTER_AUTO_PR"] = "1"
    env["SICHTER_DRY_RUN"] = "1"

    result = subprocess.run(
        [str(script), "--changed"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )

    local_refs = _run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/sichter/autofix-*"], target)
    remote_refs = _run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/sichter/autofix-*"], origin)
    assert "[RESULT][DRYRUN] repo=demo-repo branch=-" in result.stdout
    assert "dry_run=1" in result.stdout
    assert local_refs.stdout.strip() == ""
    assert remote_refs.stdout.strip() == ""
    assert _run(["git", "rev-parse", "HEAD"], target).stdout.strip() == source_head
    assert (target / "new-file.txt").read_text(encoding="utf-8") == "local only\n"
    assert _run(["git", "status", "--short"], target).stdout == "?? new-file.txt\n"


def test_sichter_pr_sweep_all_dry_run_does_not_clone_missing_repositories(tmp_path: Path):
    home = tmp_path / "home"
    (home / "repos").mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    clone_marker = tmp_path / "clone-called"
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"$1 $2\" == \"repo list\" ]]; then\n"
        "  printf '%s\\n' demo-missing\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"$1 $2\" == \"repo clone\" ]]; then\n"
        f"  : > {clone_marker!s}\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    script = Path(__file__).resolve().parents[1] / "bin" / "sichter-pr-sweep"
    env = _git_test_env()
    env["HOME"] = str(home)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["SICHTER_SELF_REPO_NAME"] = "sichter"
    env["SICHTER_INCLUDE_SELF_REPO"] = "false"
    env["SICHTER_DRY_RUN"] = "1"

    result = subprocess.run(
        [str(script), "--all"],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
        check=True,
        env=env,
    )

    assert "dry_run_missing_local_checkout" in result.stdout
    assert not clone_marker.exists()
    assert not (home / "repos" / "demo-missing").exists()

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
  effective_cmd = cmd
  if cmd and cmd[0] == "git":
    effective_cmd = ["git", "-c", "core.hooksPath=/dev/null", *cmd[1:]]
  return subprocess.run(effective_cmd, cwd=cwd, text=True, capture_output=True, check=True, env=env)


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
  env = os.environ.copy()
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
  hook.write_text("#!/usr/bin/env bash\nset -euo pipefail\nprintf 'hook-ran\\n' > hook-output.txt\n", encoding="utf-8")
  hook.chmod(0o755)

  script = Path(__file__).resolve().parents[1] / "bin" / "sichter-pr-sweep"
  env = os.environ.copy()
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
  assert refs.stdout.strip().startswith("sichter/autofix-")


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
  hook.write_text("#!/usr/bin/env bash\nset -euo pipefail\nprintf 'hook-ran\\n' > hook-output.txt\n", encoding="utf-8")
  hook.chmod(0o755)

  script = Path(__file__).resolve().parents[1] / "bin" / "sichter-pr-sweep"
  env = os.environ.copy()
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
  assert refs.stdout.strip().startswith("sichter/autofix-")

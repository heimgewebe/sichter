from __future__ import annotations

import atexit
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

from lib.config import (
  DEFAULT_BRANCH,
  DEFAULT_ORG,
  EVENTS,
  HOME,
  PR_LABEL_AUTOMATION,
  PR_LABEL_SICHTER,
  QUEUE,
  STATE,
  ensure_directories,
)

PID_FILE = STATE / "worker.pid"
LOG_DIR = HOME / "sichter/logs"

ensure_directories()
LOG_DIR.mkdir(parents=True, exist_ok=True)

_NOW = datetime.now(timezone.utc)
LOG_FILE = LOG_DIR / f"worker-{_NOW.strftime('%Y%m%d-%H%M%S')}.log"


def log(line: str) -> None:
  """Log a message to both stdout and the worker log file.

  Args:
    line: Log message
  """
  timestamp = datetime.now(timezone.utc).isoformat()
  message = f"[{timestamp}] {line}"
  print(message)
  with LOG_FILE.open("a", encoding="utf-8") as handle:
    handle.write(message + "\n")


def append_event(event: dict) -> None:
  """Append an event to the daily event log.

  Args:
    event: Event data dictionary
  """
  now = datetime.now(timezone.utc)
  event_file = EVENTS / f"worker-{now.strftime('%Y%m%d')}.jsonl"
  record = {"ts": now.isoformat(), **event}
  with event_file.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def is_process_alive(pid: int) -> bool:
  """Check if a process with given PID is alive.

  Args:
    pid: Process ID to check

  Returns:
    True if process is alive, False otherwise
  """
  try:
    os.kill(pid, 0)
  except ProcessLookupError:
    return False
  except PermissionError:
    return True
  else:
    return True


def acquire_pid_lock() -> None:
  """Acquire PID lock to ensure only one worker instance runs.

  Exits if another worker is already running.
  Cleans up PID file on exit.
  """
  if PID_FILE.exists():
    try:
      existing_pid = int(PID_FILE.read_text().strip())
    except ValueError:
      existing_pid = None
    if existing_pid and is_process_alive(existing_pid):
      log(f"Worker bereits aktiv (pid={existing_pid}), beende mich")
      raise SystemExit(0)
  PID_FILE.unlink(missing_ok=True)
  PID_FILE.write_text(str(os.getpid()))
  atexit.register(lambda: PID_FILE.unlink(missing_ok=True))


@dataclass
class Policy:
  auto_pr: bool = True
  sweep_on_omnipull: bool = True
  run_mode: str = "deep"
  org: str = DEFAULT_ORG
  llm: dict | None = None
  checks: dict | None = None
  excludes: Iterable[str] = ()

  @classmethod
  def load(cls) -> Policy:
    from lib.config import get_policy_path, load_yaml

    policy_path = get_policy_path()
    data = load_yaml(policy_path) if policy_path.exists() else {}

    return cls(
      auto_pr=bool(data.get("auto_pr", True)),
      sweep_on_omnipull=bool(data.get("sweep_on_omnipull", True)),
      run_mode=str(data.get("run_mode", "deep")),
      org=str(data.get("org", DEFAULT_ORG)),
      llm=data.get("llm", {}),
      checks=data.get("checks", {}),
      excludes=data.get("excludes", []) or [],
    )


POLICY = Policy.load()


def iter_paths(repo_dir: Path, pattern: str, excludes: Iterable[str]) -> Iterable[Path]:
  """Iterate over files matching pattern, excluding specified patterns.

  Args:
    repo_dir: Repository directory
    pattern: File glob pattern
    excludes: Exclude patterns

  Yields:
    Matching file paths
  """
  for path in repo_dir.rglob(pattern):
    rel = path.relative_to(repo_dir)
    if any(fnmatch(str(rel), ex) for ex in excludes):
      continue
    yield path


def run_cmd(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
  """Run a command and return the result.

  Args:
    cmd: Command and arguments
    cwd: Working directory
    check: Whether to raise exception on non-zero exit

  Returns:
    Completed process result
  """
  return subprocess.run(cmd, cwd=cwd, text=True, capture_output=True, check=check)


def run_shellcheck(repo_dir: Path) -> None:
  """Run shellcheck on all shell scripts if enabled in policy.

  Args:
    repo_dir: Repository directory
  """
  if not POLICY.checks or not POLICY.checks.get("shellcheck", False):
    return
  if not shutil.which("shellcheck"):
    log("shellcheck nicht gefunden - überspringe")
    return
  for script in iter_paths(repo_dir, "*.sh", POLICY.excludes):
    result = run_cmd(["shellcheck", "-x", str(script)], repo_dir, check=False)
    if result.returncode != 0:
      log(f"shellcheck: {script}: {result.stdout or result.stderr}")


def run_yamllint(repo_dir: Path) -> None:
  """Run yamllint on all YAML files if enabled in policy.

  Args:
    repo_dir: Repository directory
  """
  if not POLICY.checks or not POLICY.checks.get("yamllint", False):
    return
  if not shutil.which("yamllint"):
    log("yamllint nicht gefunden - überspringe")
    return
  for doc in iter_paths(repo_dir, "*.yml", POLICY.excludes):
    result = run_cmd(["yamllint", "-s", str(doc)], repo_dir, check=False)
    if result.returncode != 0:
      log(f"yamllint: {doc}: {result.stdout or result.stderr}")
  for doc in iter_paths(repo_dir, "*.yaml", POLICY.excludes):
    result = run_cmd(["yamllint", "-s", str(doc)], repo_dir, check=False)
    if result.returncode != 0:
      log(f"yamllint: {doc}: {result.stdout or result.stderr}")


def llm_review(repo: str, repo_dir: Path) -> None:
  """Run LLM-based code review if enabled in policy.

  Args:
    repo: Repository name
    repo_dir: Repository directory
  """
  if POLICY.run_mode != "deep":
    log(f"LLM-Review übersprungen (run_mode={POLICY.run_mode})")
    return
  provider = (POLICY.llm or {}).get("provider")
  log(f"LLM-Review placeholder für {repo} (provider={provider})")


def fresh_branch(repo_dir: Path) -> str:
  run_cmd(["git", "fetch", "origin", "--prune", "--tags"], repo_dir)
  base_branch = f"origin/{DEFAULT_BRANCH}"
  result = run_cmd(["git", "switch", "--detach", base_branch], repo_dir, check=False)
  if result.returncode != 0:
    run_cmd(["git", "checkout", "--detach", base_branch], repo_dir)
  branch = f"sichter/autofix-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
  result = run_cmd(["git", "switch", "-C", branch], repo_dir, check=False)
  if result.returncode != 0:
    run_cmd(["git", "checkout", "-B", branch], repo_dir)
  return branch


def commit_if_changes(repo_dir: Path) -> bool:
  run_cmd(["git", "add", "-A"], repo_dir)
  result = run_cmd(["git", "diff", "--cached", "--quiet"], repo_dir, check=False)
  if result.returncode != 0:
    run_cmd(["git", "commit", "-m", "sichter: autofix"], repo_dir)
    return True
  return False


def ensure_repo(repo: str) -> Path | None:
  """Ensure repository exists locally, cloning if necessary.

  Args:
    repo: Repository name (without org prefix)

  Returns:
    Path to repository directory, or None if clone failed
  """
  repo_dir = HOME / "repos" / repo
  if not (repo_dir / ".git").exists():
    try:
      result = run_cmd(["gh", "repo", "clone", f"{POLICY.org}/{repo}", str(repo_dir)], HOME, check=False)
      if result.returncode != 0:
        log(f"clone fehlgeschlagen für {repo}: {result.stderr}")
        return None
    except (subprocess.SubprocessError, OSError) as exc:
      log(f"clone fehlgeschlagen für {repo}: {exc}")
      return None
  return repo_dir


def create_or_update_pr(repo: str, repo_dir: Path, branch: str, auto_pr: bool) -> None:
  """Create or update a pull request for the changes.

  Args:
    repo: Repository name
    repo_dir: Path to repository directory
    branch: Branch name with changes
    auto_pr: Whether to automatically create PR
  """
  if not auto_pr:
    log(f"Auto-PR deaktiviert, Änderungen verbleiben lokal ({repo})")
    append_event({"type": "commit", "repo": repo, "branch": branch, "auto_pr": False})
    return

  try:
    run_cmd(["git", "push", "--set-upstream", "origin", branch, "--force-with-lease"], repo_dir)
  except subprocess.CalledProcessError as exc:
    log(f"Push fehlgeschlagen für {repo}/{branch}: {exc}")
    append_event({"type": "push_failed", "repo": repo, "branch": branch, "error": str(exc)})
    return

  # Check if PR already exists
  view = run_cmd(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"], repo_dir, check=False)
  if view.returncode != 0 or not view.stdout.strip():
    try:
      run_cmd(
        [
          "gh",
          "pr",
          "create",
          "--base",
          DEFAULT_BRANCH,
          "--fill",
          "--title",
          f"Sichter: auto PR ({repo})",
          "--label",
          PR_LABEL_SICHTER,
          "--label",
          PR_LABEL_AUTOMATION,
        ],
        repo_dir,
      )
    except subprocess.CalledProcessError as exc:
      log(f"PR-Erstellung fehlgeschlagen für {repo}/{branch}: {exc}")
      append_event({"type": "pr_failed", "repo": repo, "branch": branch, "error": str(exc)})
      return

  view = run_cmd(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"], repo_dir, check=False)
  url = view.stdout.strip() if view.stdout else ""
  append_event({"type": "pr", "repo": repo, "branch": branch, "url": url})
  log(f"PR {repo}: {url or 'unbekannt'}")


def handle_job(job: dict) -> None:
  mode = job.get("mode", "changed")
  repo_one = job.get("repo")
  auto_pr = job.get("auto_pr", POLICY.auto_pr)
  log(f"Job erhalten: mode={mode} repo={repo_one} auto_pr={auto_pr}")

  repos: Iterable[str]
  if repo_one:
    repos = [repo_one]
  elif mode == "all":
    repos = job.get("repos") or list_repos_remote()
  else:
    repos = list_repos_local()

  for repo in repos:
    repo_dir = ensure_repo(repo)
    if not repo_dir:
      continue
    branch = fresh_branch(repo_dir)
    run_shellcheck(repo_dir)
    run_yamllint(repo_dir)
    llm_review(repo, repo_dir)
    if commit_if_changes(repo_dir):
      create_or_update_pr(repo, repo_dir, branch, auto_pr)
    else:
      log(f"Keine Änderungen für {repo}")
      append_event({"type": "noop", "repo": repo, "branch": branch})


def list_repos_local() -> list[str]:
  base = HOME / "repos"
  if not base.exists():
    return []
  return [p.name for p in base.iterdir() if (p / ".git").exists()]


def list_repos_remote() -> list[str]:
  result = run_cmd(
    ["gh", "repo", "list", POLICY.org, "--limit", "100", "--json", "name", "-q", ".[].name"],
    HOME,
    check=False,
  )
  if result.returncode != 0:
    log("gh repo list fehlgeschlagen")
    return list_repos_local()
  return [line for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
  acquire_pid_lock()
  log("Worker gestartet")
  append_event({"type": "start", "message": f"Worker gestartet (pid={os.getpid()})"})
  try:
    while True:
      job_files = sorted(QUEUE.glob("*.json"))
      if not job_files:
        time.sleep(2)
        continue
      for job_file in job_files:
        try:
          job = json.loads(job_file.read_text(encoding="utf-8"))
          handle_job(job)
        except Exception as exc: # pragma: no cover
          log(f"Fehler bei {job_file.name}: {exc}")
          append_event(
            {"type": "error", "message": f"Job {job_file.name} failed: {exc}"}
          )
        finally:
          job_file.unlink(missing_ok=True)
  except KeyboardInterrupt:
    log("Worker beendet (KeyboardInterrupt)")
    append_event({"type": "stop", "message": "KeyboardInterrupt"})
    return 0


if __name__ == "__main__":
  sys.exit(main())

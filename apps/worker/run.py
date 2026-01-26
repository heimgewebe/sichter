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

from apps.worker.dedupe import dedupe_findings
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
from lib.findings import Finding, Severity

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

  @staticmethod
  def _bool_with_default(value: object, default: bool) -> bool:
    """Return boolean value while respecting explicit ``None`` as unset."""

    if value is None:
      return default
    if isinstance(value, bool):
      return value
    if isinstance(value, str):
      normalized = value.strip().lower()
      if normalized in {"true", "1", "yes", "y", "on"}:
        return True
      if normalized in {"false", "0", "no", "n", "off"}:
        return False
      log(
        "Ungültiger boolescher Wert in Policy gefunden: "
        f"{value!r} (verwende Default={default})"
      )
      return default
    return bool(value)

  @classmethod
  def load(cls) -> Policy:
    from lib.config import get_policy_path, load_yaml

    policy_path = get_policy_path()
    data = load_yaml(policy_path) if policy_path.exists() else {}

    auto_pr = cls._bool_with_default(data.get("auto_pr"), True)
    sweep_on_omnipull = cls._bool_with_default(data.get("sweep_on_omnipull"), True)

    return cls(
      auto_pr=auto_pr,
      sweep_on_omnipull=sweep_on_omnipull,
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


def get_changed_files(repo_dir: Path, base: str, excludes: Iterable[str]) -> list[Path]:
  """Return changed files since base, filtered by excludes.

  Falls zurück auf leere Liste, wenn git diff fehlschlägt.
  """
  result = run_cmd(["git", "diff", "--name-only", "--diff-filter=ACMRT", base], repo_dir, check=False)
  if result.returncode != 0:
    log(f"git diff failed for base={base}: {result.stderr.strip()}")
    return []
  
  # Resolve repo_dir once for consistent symlink checking
  try:
    repo_root = repo_dir.resolve()
  except (OSError, RuntimeError):
    repo_root = repo_dir
  
  files: list[Path] = []
  for line in result.stdout.splitlines():
    rel_path_str = line.strip()
    if not rel_path_str:
      continue
    path = repo_dir / rel_path_str
    if not path.exists():
      continue
    
    # Check that resolved path stays within repo (catches symlinks pointing outside)
    try:
      resolved = path.resolve(strict=False)
      # Verify resolved path is under repo root
      resolved.relative_to(repo_root)
    except (ValueError, OSError, RuntimeError):
      # Skip paths that resolve outside the repository
      log(f"Skipping {rel_path_str}: resolves outside repository")
      continue
    
    # Check excludes against the original relative path
    try:
      rel = path.relative_to(repo_dir)
    except ValueError:
      continue
    
    if any(fnmatch(str(rel), ex) for ex in excludes):
      continue
    files.append(path)
  return files


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


def normalize_severity(severity: str) -> Severity:
  """Normalize severity string to valid Finding severity literal.
  
  Args:
    severity: Severity string from linter output
  
  Returns:
    Normalized severity: "info", "warning", "error", "critical", or "question"
  """
  severity_lower = severity.lower()
  if severity_lower in {"info", "warning", "error", "critical", "question"}:
    return severity_lower  # type: ignore
  return "warning"


def run_shellcheck(repo_dir: Path, files: Iterable[Path] | None = None) -> list[Finding]:
  """Run shellcheck on all shell scripts if enabled in policy.

  Args:
    repo_dir: Repository directory
    files: Optional list of files to check; if None, checks all .sh files
  
  Returns:
    List of Finding objects, one per shellcheck diagnostic
  """
  if not POLICY.checks or not POLICY.checks.get("shellcheck", False):
    return []
  if not shutil.which("shellcheck"):
    log("shellcheck nicht gefunden - überspringe")
    return []
  findings: list[Finding] = []
  candidates = files if files is not None else iter_paths(repo_dir, "*.sh", POLICY.excludes)
  for script in candidates:
    if script.suffix != ".sh":
      continue
    # Use gcc format for single-line, parseable output: path:line:col: severity: message [SCxxxx]
    result = run_cmd(["shellcheck", "-f", "gcc", "-x", str(script)], repo_dir, check=False)
    if result.returncode != 0:
      output = result.stdout or result.stderr
      for line in (output or "").splitlines():
        line = line.strip()
        if not line:
          continue
        # Parse gcc format: path:line:col: severity: message [SCxxxx]
        # Example: script.sh:10:5: warning: Use $(...) instead of legacy `...` [SC2006]
        parts = line.split(":", 3)
        if len(parts) >= 4:
          file_path = parts[0]
          line_num = parts[1]
          # col = parts[2]
          rest = parts[3].strip()
          # Extract severity and message
          if ": " in rest:
            severity_msg = rest.split(": ", 1)
            severity = severity_msg[0].lower()
            message = severity_msg[1] if len(severity_msg) > 1 else rest
          else:
            severity = "warning"
            message = rest
          # Extract rule_id (SCxxxx) from message
          rule_id = None
          if "[SC" in message and "]" in message:
            rule_start = message.rfind("[SC")
            rule_end = message.find("]", rule_start)
            if rule_end > rule_start:
              rule_id = message[rule_start + 1 : rule_end]
              # Remove the [SCxxxx] marker from message to avoid duplication
              message = message[:rule_start].rstrip()
          # Convert to int or None
          try:
            line_int = int(line_num)
          except ValueError:
            line_int = None
          # Normalize file_path to repo-relative
          try:
            file_path_obj = Path(file_path)
            if file_path_obj.is_absolute():
              file_rel = str(file_path_obj.relative_to(repo_dir))
            else:
              file_rel = file_path
          except (ValueError, OSError):
            file_rel = file_path
          findings.append(
            Finding(
              severity=normalize_severity(severity),
              category="correctness",
              file=file_rel,
              line=line_int,
              message=message,
              tool="shellcheck",
              rule_id=rule_id,
            )
          )
        else:
          # Fallback for unparseable lines
          log(f"shellcheck: {script}: unparseable line: {line}")
  return findings


def run_yamllint(repo_dir: Path, files: Iterable[Path] | None = None) -> list[Finding]:
  """Run yamllint on all YAML files if enabled in policy.

  Args:
    repo_dir: Repository directory
    files: Optional list of files to check; if None, checks all .yml/.yaml files
  
  Returns:
    List of Finding objects, one per yamllint diagnostic
  """
  if not POLICY.checks or not POLICY.checks.get("yamllint", False):
    return []
  if not shutil.which("yamllint"):
    log("yamllint nicht gefunden - überspringe")
    return []
  findings: list[Finding] = []
  if files is None:
    candidates = list(iter_paths(repo_dir, "*.yml", POLICY.excludes))
    candidates.extend(iter_paths(repo_dir, "*.yaml", POLICY.excludes))
  else:
    candidates = [p for p in files if p.suffix in {".yml", ".yaml"}]
  for doc in candidates:
    # Use parseable format for single-line output: path:line:col: [severity] message (rule-name)
    result = run_cmd(["yamllint", "-f", "parsable", str(doc)], repo_dir, check=False)
    if result.returncode != 0:
      output = result.stdout or result.stderr
      for line in (output or "").splitlines():
        line = line.strip()
        if not line:
          continue
        # Parse format: path:line:col: [severity] message (rule-name)
        # Example: file.yml:10:5: [error] trailing spaces (trailing-spaces)
        parts = line.split(":", 3)
        if len(parts) >= 4:
          file_path = parts[0]
          line_num = parts[1]
          # col = parts[2]
          rest = parts[3].strip()
          # Extract severity and message
          severity = "warning"
          message = rest
          rule_id = None
          if rest.startswith("["):
            bracket_end = rest.find("]")
            if bracket_end > 0:
              severity = rest[1:bracket_end].lower()
              message = rest[bracket_end + 1 :].strip()
          # Extract rule_id from message (rule-name)
          if "(" in message and ")" in message:
            paren_start = message.rfind("(")
            paren_end = message.find(")", paren_start)
            if paren_end > paren_start:
              rule_id = message[paren_start + 1 : paren_end]
              message = message[:paren_start].strip()
          # Convert line to int or None
          try:
            line_int = int(line_num)
          except ValueError:
            line_int = None
          # Normalize file_path to repo-relative
          try:
            file_path_obj = Path(file_path)
            if file_path_obj.is_absolute():
              file_rel = str(file_path_obj.relative_to(repo_dir))
            else:
              file_rel = file_path
          except (ValueError, OSError):
            file_rel = file_path
          findings.append(
            Finding(
              severity=normalize_severity(severity),
              category="correctness",
              file=file_rel,
              line=line_int,
              message=message,
              tool="yamllint",
              rule_id=rule_id,
            )
          )
        else:
          # Fallback for unparseable lines
          log(f"yamllint: {doc}: unparseable line: {line}")
  return findings


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
  auto_pr_job = job.get("auto_pr")
  if "auto_pr" not in job or auto_pr_job is None:
    auto_pr = POLICY.auto_pr
  elif isinstance(auto_pr_job, bool):
    auto_pr = auto_pr_job
  else:
    log(
      "auto_pr wird als bool erwartet (z. B. aus JSON). "
      f"Unerwarteter Typ {type(auto_pr_job).__name__}, verwende Policy-Default."
    )
    auto_pr = POLICY.auto_pr
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
    changed_files: list[Path] | None
    if mode == "changed":
      changed_files = get_changed_files(repo_dir, f"origin/{DEFAULT_BRANCH}", POLICY.excludes)
      if not changed_files:
        log(f"Keine geänderten Dateien für {repo} (mode=changed)")
    else:
      changed_files = None
    findings: list[Finding] = []
    findings.extend(run_shellcheck(repo_dir, changed_files))
    findings.extend(run_yamllint(repo_dir, changed_files))
    grouped = dedupe_findings(findings)
    if findings:
      log(f"{repo}: {len(findings)} Findings ({len(grouped)} dedupliziert)")
      append_event(
        {
          "type": "findings",
          "repo": repo,
          "count": len(findings),
          "deduped": len(grouped),
        }
      )
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

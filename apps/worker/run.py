from __future__ import annotations

import atexit
import json
import os
import select
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from lib.checks.base import compile_excludes, is_excluded
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from lib.llm.review import ReviewResult

from apps.worker.dedupe import dedupe_findings
from lib.cache import cache_get, cache_set, make_check_key, policy_hash as cache_policy_hash
from lib.checks import run_autofixes as registry_run_autofixes
from lib.checks import run_checks as registry_run_checks
from lib.checks.base import policy_check_enabled
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
from lib.heuristics import run_drift_check, run_hotspot_check, run_redundancy_check
from lib.metrics import ReviewMetrics, record_findings_snapshot, record_metrics

REPO_ROOT = Path(__file__).resolve().parents[2]
NOTIFY_SCRIPT = REPO_ROOT / "bin" / "hauski-notify"
NOTIFY_TIMEOUT_SECONDS = 5
PID_FILE = STATE / "worker.pid"
LOG_DIR = HOME / "sichter/logs"
REVIEW_DIR = STATE / "reviews"
REVIEW_BUDGET_FILE = STATE / "llm_review_budget.jsonl"

ensure_directories()
LOG_DIR.mkdir(parents=True, exist_ok=True)
REVIEW_DIR.mkdir(parents=True, exist_ok=True)

_NOW = datetime.now(timezone.utc)
LOG_FILE = LOG_DIR / f"worker-{_NOW.strftime('%Y%m%d-%H%M%S')}.log"
LOCAL_DISCOVERY_EXCLUDE = {".idea", "merges", "exports", "_mirror"}
SELF_REPO_NAME = "sichter"


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


def notify_internal(message: str) -> None:
  """Best-effort internal notification that must never block worker progress."""
  if not NOTIFY_SCRIPT.exists():
    log(f"Interne Benachrichtigung übersprungen: Script fehlt ({NOTIFY_SCRIPT})")
    return

  try:
    result = subprocess.run(
      [str(NOTIFY_SCRIPT), message],
      cwd=REPO_ROOT,
      text=True,
      capture_output=True,
      check=False,
      timeout=NOTIFY_TIMEOUT_SECONDS,
    )
  except subprocess.TimeoutExpired:
    log(
      "Interne Benachrichtigung abgebrochen: "
      f"Timeout nach {NOTIFY_TIMEOUT_SECONDS}s"
    )
    return
  except OSError as exc:
    log(f"Interne Benachrichtigung fehlgeschlagen (OSError): {exc}")
    return

  if result.returncode != 0:
    stderr = (result.stderr or "").strip()
    log(
      "Interne Benachrichtigung fehlgeschlagen "
      f"(exit={result.returncode}): {stderr}"
    )


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
  security: dict | None = None
  max_parallel_repos: int = 4
  include_self_repo: bool = False

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
    include_self_repo = cls._bool_with_default(data.get("include_self_repo"), False)
    try:
      max_parallel_repos = int(data.get("max_parallel_repos", 4))
    except (TypeError, ValueError):
      max_parallel_repos = 4
    if max_parallel_repos <= 0:
      max_parallel_repos = 1

    return cls(
      auto_pr=auto_pr,
      sweep_on_omnipull=sweep_on_omnipull,
      run_mode=str(data.get("run_mode", "deep")),
      org=str(data.get("org", DEFAULT_ORG)),
      llm=data.get("llm", {}),
      checks=data.get("checks", {}),
      excludes=data.get("excludes", []) or [],
      security=data.get("security", {}),
      max_parallel_repos=max_parallel_repos,
      include_self_repo=include_self_repo,
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
  compiled_re = compile_excludes(tuple(excludes))
  for path in repo_dir.rglob(pattern):
    rel = path.relative_to(repo_dir)
    if is_excluded(str(rel), compiled_re):
      continue
    yield path


def get_changed_files(
  repo_dir: Path,
  base: str | None = None,
  excludes: Iterable[str] = (),
) -> list[Path]:
  """Return changed files since base, filtered by excludes.

  Notes:
    - Defaults base to origin/{DEFAULT_BRANCH}.
    - Returns [] if git diff fails.
    - Skips paths that resolve outside the repository (symlinks/outside traversal).
  """
  if base is None:
    base = f"origin/{DEFAULT_BRANCH}"

  result = run_cmd(
    ["git", "diff", "--name-only", "--diff-filter=ACMRT", base],
    repo_dir,
    check=False,
  )
  if result.returncode != 0:
    log(f"git diff failed for base={base}: {result.stderr.strip()}")
    return []

  try:
    repo_root = repo_dir.resolve()
  except (OSError, RuntimeError):
    repo_root = repo_dir

  files: list[Path] = []
  skipped_outside: list[str] = []
  compiled_re = compile_excludes(tuple(excludes))

  for raw in result.stdout.splitlines():
    rel_path_str = raw.strip()
    if not rel_path_str:
      continue

    path = repo_dir / rel_path_str
    if not path.exists():
      continue

    # Ensure resolved target stays inside repo_root (catches symlinks pointing outside)
    try:
      resolved = path.resolve(strict=False)
      resolved.relative_to(repo_root)
    except (ValueError, OSError, RuntimeError):
      skipped_outside.append(rel_path_str)
      continue

    try:
      rel = path.relative_to(repo_dir)
    except ValueError:
      continue

    if is_excluded(str(rel), compiled_re):
      continue

    files.append(path)

  if skipped_outside:
    max_displayed = 3
    examples = ", ".join(skipped_outside[:max_displayed])
    suffix = "..." if len(skipped_outside) > max_displayed else ""
    log(
      "Skipped "
      f"{len(skipped_outside)} file(s) that resolve outside repository: "
      f"{examples}{suffix}"
    )

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


def run_gh_with_backoff(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
  """Run `gh` commands with exponential backoff on rate limits."""
  wait_seconds = 15
  for _attempt in range(3):
    result = run_cmd(cmd, cwd, check=False)
    if result.returncode == 0:
      return result
    stderr = (result.stderr or "").lower()
    if not any(token in stderr for token in ("rate limit", "secondary rate limit", "429")):
      return result
    log(f"GitHub-Rate-Limit erkannt für {' '.join(cmd[:3])}, warte {wait_seconds}s")
    append_event({"type": "github_rate_limit", "wait_seconds": wait_seconds, "command": cmd[:3]})
    time.sleep(wait_seconds)
    wait_seconds *= 2
  return result


def is_git_repository(repo_dir: Path) -> bool:
  """Return True only for usable git worktrees."""
  if not isinstance(repo_dir, Path):
    return False
  if not repo_dir.exists():
    return False
  try:
    result = run_cmd(["git", "rev-parse", "--is-inside-work-tree"], repo_dir, check=False)
  except (OSError, subprocess.SubprocessError, ValueError, TypeError):
    return False
  return result.returncode == 0


def current_commit(repo_dir: Path) -> str:
  if not repo_dir.exists():
    return "unknown"
  try:
    result = run_cmd(["git", "rev-parse", "HEAD"], repo_dir, check=False)
  except OSError:
    return "unknown"
  return (result.stdout or "").strip() or "unknown"


def serialize_findings(findings: Iterable[Finding]) -> list[dict]:
  return [
    {
      "severity": finding.severity,
      "category": finding.category,
      "file": finding.file,
      "line": finding.line,
      "message": finding.message,
      "evidence": finding.evidence,
      "fix_available": finding.fix_available,
      "dedupe_key": finding.dedupe_key,
      "uncertainty": finding.uncertainty,
      "tool": finding.tool,
      "rule_id": finding.rule_id,
    }
    for finding in findings
  ]


def deserialize_findings(items: Iterable[dict]) -> list[Finding]:
  findings: list[Finding] = []
  for item in items:
    findings.append(
      Finding(
        severity=item.get("severity", "warning"),
        category=item.get("category", "correctness"),
        file=item.get("file", ""),
        line=item.get("line"),
        message=item.get("message", ""),
        evidence=item.get("evidence"),
        fix_available=bool(item.get("fix_available", False)),
        dedupe_key=item.get("dedupe_key", ""),
        uncertainty=item.get("uncertainty"),
        tool=item.get("tool"),
        rule_id=item.get("rule_id"),
      )
    )
  return findings


def _select_autofix_targets(findings: Iterable[Finding]) -> tuple[set[str], dict[str, list[Path]]]:
  """Select autofix-capable tools and affected files from current findings."""
  autofix_tools: set[str] = set()
  target_files_by_tool: dict[str, list[Path]] = {}

  for finding in findings:
    if not finding.fix_available:
      continue

    tool_name = (finding.tool or "").strip().lower()
    if tool_name not in {"ruff", "eslint"}:
      continue

    autofix_tools.add(tool_name)
    if not finding.file:
      continue

    file_path = Path(finding.file)
    targets = target_files_by_tool.setdefault(tool_name, [])
    if file_path not in targets:
      targets.append(file_path)

  return autofix_tools, target_files_by_tool


def run_heuristics(repo_dir: Path, changed_files: list[Path] | None) -> list[Finding]:
  if not isinstance(repo_dir, Path):
    return []

  findings: list[Finding] = []
  if repo_dir.exists() and (repo_dir / ".git").exists():
    findings.extend(run_hotspot_check(repo_dir, changed_files, POLICY.checks, run_cmd, log))
  findings.extend(run_drift_check(repo_dir, POLICY.checks, log))
  findings.extend(run_redundancy_check(repo_dir, changed_files, POLICY.checks, log))
  return findings


def _escape_md_cell(s: str) -> str:
  """Escape pipe characters and newlines so they don't break a Markdown table cell."""
  return str(s).replace("|", "\\|").replace("\n", " ")


def _filter_findings_for_prs(
  findings: Iterable[Finding],
  checks_cfg: dict | None,
  security_cfg: dict | None,
  repo: str = "",
) -> list[Finding]:
  """Filter findings based on policy create_pr flags.

  Categories can be suppressed from PR creation via policy flags:
  - checks.drift.create_pr: false (default) → drift findings won't create PRs
  - security.suppress_pr: true → security findings won't create PRs

  Args:
    findings: All findings to filter.
    checks_cfg: Policy checks structure.
    repo: Repository name (for logging).

  Returns:
    Filtered findings that should be considered for PR creation.
  """
  result: list[Finding] = []
  checks_dict = checks_cfg if isinstance(checks_cfg, dict) else {}
  security_dict = security_cfg if isinstance(security_cfg, dict) else {}
  suppressed_counts: dict[str, int] = {}

  for finding in findings:
    # Drift config follows the same checks.drift path used by run_drift_check.
    if finding.category == "drift":
      drift_cfg = checks_dict.get("drift", {})
      if isinstance(drift_cfg, dict):
        create_pr = drift_cfg.get("create_pr", False)  # default: False
        if not create_pr:
          suppressed_counts["drift"] = suppressed_counts.get("drift", 0) + 1
          continue  # skip this finding for PR creation

    # Security config is loaded as top-level POLICY.security.
    if finding.category == "security":
      if isinstance(security_dict, dict):
        suppress_pr = security_dict.get("suppress_pr", False)
        if suppress_pr:
          suppressed_counts["security"] = suppressed_counts.get("security", 0) + 1
          continue  # skip this finding for PR creation

    result.append(finding)

  # Log suppression events
  for category, count in suppressed_counts.items():
    append_event({
      "type": f"{category}_findings_suppressed",
      "repo": repo,
      "count": count,
    })

  security_count = suppressed_counts.get("security", 0)
  if security_count > 0:
    notify_internal(
      f"Sichter: {repo} – {security_count} Security-Finding(s) per Policy unterdrückt"
    )

  return result


def add_inline_pr_comments(repo: str, repo_dir: Path, branch: str, findings: Iterable[Finding]) -> None:
  """Post a compact review comment with line-addressable findings."""
  inline_candidates = [finding for finding in findings if finding.file and finding.line is not None][:10]
  if not inline_candidates:
    return
  lines = [
    "### Sichter Inline-Hinweise",
    "",
    "| Datei | Zeile | Severity | Regel | Nachricht |",
    "| --- | --- | --- | --- | --- |",
  ]
  for finding in inline_candidates:
    rule = finding.rule_id or finding.tool or ""
    lines.append(
      f"| {_escape_md_cell(finding.file)} | {finding.line} | {finding.severity}"
      f" | {_escape_md_cell(rule)} | {_escape_md_cell(finding.message)} |"
    )
  result = run_gh_with_backoff(
    ["gh", "pr", "review", branch, "--comment", "--body", "\n".join(lines)],
    repo_dir,
  )
  if result.returncode != 0:
    log(f"Inline-Review-Kommentar fehlgeschlagen für {repo}/{branch}")


def normalize_severity(severity: str) -> Severity:
  """Normalize severity string to valid Finding severity literal."""
  severity_lower = severity.lower()
  if severity_lower in {"info", "warning", "error", "critical", "question"}:
    return cast(Severity, severity_lower)
  return "warning"


def persist_review_result(repo: str, result: ReviewResult) -> None:
  """Persist parsed LLM review results as JSONL records."""
  now = datetime.now(timezone.utc)
  target = REVIEW_DIR / f"reviews-{now.strftime('%Y%m%d')}.jsonl"
  record = {
    "ts": now.isoformat(),
    "repo": repo,
    "summary": result.summary,
    "risk_overall": result.risk_overall,
    "uncertainty": result.uncertainty,
    "suggestions": [
      {
        "theme": suggestion.theme,
        "recommendation": suggestion.recommendation,
        "risk": suggestion.risk,
        "why": suggestion.why,
        "files": suggestion.files,
      }
      for suggestion in result.suggestions
    ],
    "model": result.model,
    "provider": result.provider,
    "provider_switched": result.provider_switched,
    "tokens_used": result.tokens_used,
  }
  try:
    with target.open("a", encoding="utf-8") as handle:
      handle.write(json.dumps(record, ensure_ascii=False) + "\n")
  except OSError as exc:
    log(f"Konnte LLM-Review nicht persistieren ({repo}): {exc}")


def is_check_enabled(name: str) -> bool:
  """Return whether a check is enabled in policy.

  Supports boolean flags and nested dictionaries with `enabled` / `autofix`.
  """
  return policy_check_enabled(name, POLICY.checks)


def run_shellcheck(repo_dir: Path, files: Iterable[Path] | None = None) -> list[Finding]:
  """Compatibility wrapper around the extracted shellcheck module."""
  from lib.checks.shellcheck import run_shellcheck as _run_shellcheck

  return _run_shellcheck(repo_dir, files, POLICY.excludes, POLICY.checks, run_cmd, log)


def run_yamllint(repo_dir: Path, files: Iterable[Path] | None = None) -> list[Finding]:
  """Compatibility wrapper around the extracted yamllint module."""
  from lib.checks.yamllint import run_yamllint as _run_yamllint

  return _run_yamllint(repo_dir, files, POLICY.excludes, POLICY.checks, run_cmd, log)


def run_ruff(repo_dir: Path, files: Iterable[Path] | None = None) -> list[Finding]:
  """Compatibility wrapper around the extracted ruff module."""
  from lib.checks.ruff import run_ruff as _run_ruff

  return _run_ruff(repo_dir, files, POLICY.excludes, POLICY.checks, run_cmd, log)


def run_shfmt(repo_dir: Path, files: Iterable[Path] | None = None) -> int:
  """Compatibility wrapper around the extracted shfmt module."""
  from lib.checks.shfmt import run_shfmt as _run_shfmt

  return _run_shfmt(repo_dir, files, POLICY.excludes, POLICY.checks, run_cmd, log)


def llm_review(
  repo: str,
  repo_dir: Path,
  findings: list[Finding] | None = None,
) -> ReviewResult | None:
  """Run LLM-based code review if enabled in policy.

  Args:
    repo: Repository name.
    repo_dir: Repository directory.
    findings: Static findings to include as context for the LLM.

  Returns:
    Parsed ``ReviewResult``, or ``None`` if LLM review is skipped or fails.
  """
  llm_cfg = POLICY.llm or {}
  enabled = bool(llm_cfg.get("enabled", False))
  if not enabled:
    log(f"LLM-Review übersprungen (llm.enabled={enabled!r})")
    return None

  from lib.llm.factory import get_provider
  from lib.llm.prompts import build_review_prompt
  from lib.llm.review import parse_review_response
  from lib.llm.budget import ReviewBudget

  try:
    budget = ReviewBudget(REVIEW_BUDGET_FILE)
    try:
      max_reviews_per_hour = int(llm_cfg.get("max_reviews_per_hour", 20))
      if max_reviews_per_hour <= 0:
        raise ValueError("max_reviews_per_hour must be positive")
    except (TypeError, ValueError):
      max_reviews_per_hour = 20
    if not budget.allow_review(max_reviews_per_hour=max_reviews_per_hour):
      used = budget.reviews_in_last_hour()
      log(
        f"LLM-Review übersprungen – Rate-Limit erreicht "
        f"({used}/{max_reviews_per_hour} pro Stunde)"
      )
      append_event(
        {
          "type": "llm_review_skipped",
          "repo": repo,
          "reason": "rate_limit",
          "used": used,
          "limit": max_reviews_per_hour,
        }
      )
      return None

    provider = get_provider(llm_cfg)
    diff_result = run_cmd(
      ["git", "diff", f"origin/{DEFAULT_BRANCH}"],
      repo_dir,
      check=False,
    )
    diff = diff_result.stdout or ""

    if not findings and not diff.strip():
      log(f"LLM-Review übersprungen – kein Diff und keine Findings für {repo}")
      return None

    denylist_patterns_cfg = llm_cfg.get("denylist_patterns", [])
    denylist_patterns = (
      [str(p) for p in denylist_patterns_cfg]
      if isinstance(denylist_patterns_cfg, list)
      else []
    )

    prompt = build_review_prompt(
      repo,
      diff,
      findings or [],
      denylist_patterns=denylist_patterns,
    )
    try:
      max_tokens = int(llm_cfg.get("max_tokens_per_review", 4000))
      if max_tokens <= 0:
        raise ValueError("max_tokens_per_review must be positive")
    except (TypeError, ValueError):
      max_tokens = 4000
    active_provider = provider
    provider_switched = False
    try:
      raw, tokens = provider.complete(prompt, max_tokens=max_tokens)
    except Exception as provider_exc:  # noqa: BLE001
      fallback_cfg = llm_cfg.get("fallback")
      if not isinstance(fallback_cfg, dict):
        raise provider_exc

      merged_cfg = {**llm_cfg, **fallback_cfg}
      active_provider = get_provider(merged_cfg)
      raw, tokens = active_provider.complete(prompt, max_tokens=max_tokens)
      provider_switched = True
      append_event(
        {
          "type": "llm_provider_fallback",
          "repo": repo,
          "from_provider": provider.provider_name,
          "from_model": provider.model,
          "to_provider": active_provider.provider_name,
          "to_model": active_provider.model,
          "reason": str(provider_exc),
        }
      )

    result = parse_review_response(
      raw,
      model=active_provider.model,
      provider=active_provider.provider_name,
      tokens_used=tokens,
    )
    result.provider_switched = provider_switched
    budget.record_review(repo=repo, tokens_used=tokens)
    persist_review_result(repo, result)

    log(f"LLM-Review {repo}: risk={result.risk_overall}, tokens={tokens}")
    append_event(
      {
        "type": "llm_review",
        "repo": repo,
        "risk": result.risk_overall,
        "tokens": tokens,
        "provider": active_provider.provider_name,
        "model": active_provider.model,
        "provider_switched": provider_switched,
      }
    )
    return result
  except Exception as exc:  # noqa: BLE001 — catch-all intentional: LLM errors must not abort the job
    log(f"LLM-Review fehlgeschlagen für {repo}: {exc}")
    append_event({"type": "error", "repo": repo, "message": f"llm_review failed: {exc}"})
    return None


def build_pr_body(
  repo: str,
  findings: Iterable[Finding] | None = None,
  review: ReviewResult | None = None,
) -> str:
  """Build a concise PR body with finding summary, affected files, verification hints, and optional LLM review."""
  findings_list = list(findings or [])
  if not findings_list:
    lines: list[str] = [
      "## Sichter Auto-Review",
      "",
      f"Repository: {repo}",
      "",
      "Keine strukturierten Findings gemeldet. Diese PR enthält nur automatische Änderungen.",
    ]
    if review is not None:
      lines.extend(["", review.to_pr_section()])
    return "\n".join(lines)

  severity_order = ["critical", "error", "warning", "info", "question"]
  severity_counts = {sev: 0 for sev in severity_order}
  for finding in findings_list:
    severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1

  lines: list[str] = [
    "## Sichter Auto-Review",
    "",
    f"Repository: {repo}",
    "",
    "### Findings",
    "",
  ]
  for sev in severity_order:
    count = severity_counts.get(sev, 0)
    if count:
      lines.append(f"- {sev}: {count}")

  lines.extend(["", "### Top Hinweise", ""])
  grouped = dedupe_findings(findings_list)
  for bucket in list(grouped.values())[:5]:
    first = bucket[0]
    location = f"{first.file}:{first.line}" if first.line is not None else first.file
    rule = f" ({first.rule_id})" if first.rule_id else ""
    lines.append(f"- [{first.severity}] {first.message}{rule} in {location}")

  # **5.2** Betroffene Dateien mit Zählern (Top 10)
  lines.extend(["", "### Betroffene Dateien", ""])
  severity_order_map = {sev: idx for idx, sev in enumerate(severity_order)}
  file_stats: dict[str, tuple[int, Severity]] = {}
  for finding in findings_list:
    if not finding.file:
      continue
    count, max_sev = file_stats.get(finding.file, (0, finding.severity))
    sev_idx = severity_order_map.get(finding.severity, 999)
    max_sev_idx = severity_order_map.get(max_sev, 999)
    new_max_sev = finding.severity if sev_idx < max_sev_idx else max_sev
    file_stats[finding.file] = (count + 1, cast(Severity, new_max_sev))

  if file_stats:
    sorted_files = sorted(file_stats.items(), key=lambda x: (-x[1][0], severity_order.index(x[1][1]) if x[1][1] in severity_order else 999))[:10]
    lines.append("| Datei | Findings | Top-Severity |")
    lines.append("| --- | --- | --- |")
    for file_name, (count, max_sev) in sorted_files:
      lines.append(f"| {_escape_md_cell(file_name)} | {count} | {max_sev} |")

  # **5.2** Verifikationshinweise pro Category
  categories_in_findings = set(finding.category for finding in findings_list if finding.category)
  if categories_in_findings:
    lines.extend(["", "### Verifikationshinweise", ""])
    
    verification_hints: dict[str, str] = {
      "style": "✓ Formatierung prüfen (Code-Style, imports, naming-conventions)",
      "correctness": "✓ Logik und Semantik des Diff überprüfen, besonders Grenzfälle",
      "security": "✓ Keine Credentials, Secrets oder sensitiven Daten in Code prüfen",
      "drift": "✓ Versionsquellen und gewünschte Pinning-Strategie abgleichen",
      "maintainability": "✓ Leserbarkeit, Duplikationen, Dokumentation überprüfen",
      "performance": "✓ Performance-Auswirkungen auf Latenz und Speicher prüfen",
    }
    
    for category in sorted(categories_in_findings):
      hint = verification_hints.get(category, "✓ Manuell prüfen")
      lines.append(f"- **{category}**: {hint}")

  if review is not None:
    lines.extend(["", review.to_pr_section()])

  return "\n".join(lines)


def prepare_repo_base(repo_dir: Path) -> bool:
  """Prepare repo at verifiable base (origin/DEFAULT_BRANCH).
  
  Returns True only if worktree successfully detached at origin/DEFAULT_BRANCH.
  Fetch failure is tolerated (soft fail); detach failure is hard gate.
  """
  fetch = run_cmd(["git", "fetch", "origin", "--prune", "--tags"], repo_dir, check=False)
  if fetch.returncode != 0:
    log(f"git fetch fehlgeschlagen in {repo_dir}; arbeite mit lokalem Stand weiter")
  
  base_branch = f"origin/{DEFAULT_BRANCH}"
  # Try switch first (faster), then fallback to checkout
  result = run_cmd(["git", "switch", "--detach", base_branch], repo_dir, check=False)
  if result.returncode != 0:
    result = run_cmd(["git", "checkout", "--detach", base_branch], repo_dir, check=False)
  
  if result.returncode != 0:
    log(f"base-Detach fehlgeschlagen in {repo_dir}: konnte nicht auf {base_branch} detachen")
    return False
  
  return True


def fresh_branch(repo_dir: Path) -> str:
  branch = f"sichter/autofix-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
  result = run_cmd(["git", "switch", "-C", branch], repo_dir, check=False)
  if result.returncode != 0:
    run_cmd(["git", "checkout", "-B", branch], repo_dir)
  return branch


def runtime_artifact_excludes(repo: str) -> tuple[str, ...]:
  """Return runtime artifact globs that must never drive PR creation."""
  if repo.strip() == SELF_REPO_NAME:
    return ("logs/**",)
  return ()


def has_commit_candidates(repo_dir: Path, excludes: Iterable[str] = ()) -> bool:
  """Read-only preflight check for commitable changes.

  Uses porcelain status output and applies exclusion globs without touching index
  or HEAD. This keeps NOCHANGE sweeps state-light.
  """
  result = run_cmd(
    ["git", "status", "--porcelain", "-z", "--untracked-files=all"],
    repo_dir,
    check=False,
  )
  if result.returncode != 0:
    log(f"git status preflight fehlgeschlagen in {repo_dir}")
    return False

  compiled_re = compile_excludes(tuple(excludes))
  fields = result.stdout.split("\0")
  i = 0
  while i < len(fields):
    entry = fields[i]
    if not entry:
      i += 1
      continue

    # Porcelain v1 entry: XY<space>path
    status = entry[:2]
    path = entry[3:] if len(entry) > 3 else ""

    # Renames/copies in -z output are two consecutive path fields.
    if "R" in status or "C" in status:
      i += 1
      new_path = fields[i] if i < len(fields) else ""
      if new_path and not is_excluded(new_path, compiled_re):
        return True
      i += 1
      continue

    if path and not is_excluded(path, compiled_re):
      return True
    i += 1

  return False


def commit_if_changes(
  repo_dir: Path,
  *,
  stage_all: bool = True,
  excludes: Iterable[str] = (),
) -> bool:
  if stage_all:
    add = run_cmd(["git", "add", "-A"], repo_dir, check=False)
    if add.returncode != 0:
      log(f"git add -A fehlgeschlagen in {repo_dir}")
      return False
    for pattern in excludes:
      run_cmd(["git", "reset", "-q", "HEAD", "--", pattern], repo_dir, check=False)

  result = run_cmd(["git", "diff", "--cached", "--quiet"], repo_dir, check=False)
  if result.returncode == 1:
    run_cmd(["git", "commit", "-m", "sichter: autofix"], repo_dir)
    return True
  if result.returncode != 0:
    log(f"git diff --cached --quiet fehlgeschlagen in {repo_dir}")
  return False


def _filter_discovered_repos(repos: Iterable[str], include_self: bool) -> list[str]:
  """Filter discovered repositories for obvious non-targets."""
  filtered: list[str] = []
  for raw in repos:
    repo = str(raw).strip()
    if not repo:
      continue
    name = repo.split("/")[-1]
    if name.startswith("."):
      continue
    if name in LOCAL_DISCOVERY_EXCLUDE:
      continue
    if not include_self and name == SELF_REPO_NAME:
      continue
    filtered.append(repo)
  return filtered


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
      result = run_cmd(
        ["gh", "repo", "clone", f"{POLICY.org}/{repo}", str(repo_dir)],
        HOME,
        check=False,
      )
      if result.returncode != 0:
        log(f"clone fehlgeschlagen für {repo}: {result.stderr}")
        return None
    except (subprocess.SubprocessError, OSError) as exc:
      log(f"clone fehlgeschlagen für {repo}: {exc}")
      return None
  return repo_dir


def create_or_update_pr(
  repo: str,
  repo_dir: Path,
  branch: str,
  auto_pr: bool,
  findings: Iterable[Finding] | None = None,
  review: ReviewResult | None = None,
  pr_title: str | None = None,
  is_security: bool | None = None,
) -> bool:
  """Create or update a pull request for the changes.

  Args:
    repo: Repository name.
    repo_dir: Path to repository directory.
    branch: Branch name with changes.
    auto_pr: Whether to automatically create PR.
    findings: Linter findings to include in PR body.
    review: Optional LLM review to append to PR body.
    pr_title: Optional custom PR title.
    is_security: Override for security-only PR handling.
  """
  if not auto_pr:
    log(f"Auto-PR deaktiviert, Änderungen verbleiben lokal ({repo})")
    append_event({"type": "commit", "repo": repo, "branch": branch, "auto_pr": False})
    return False

  findings_list = list(findings or [])
  security_pr = is_security if is_security is not None else any(
    finding.category == "security" for finding in findings_list
  )
  security_cfg = POLICY.security or {}
  draft_security = security_pr and not bool(security_cfg.get("findings_public", False))

  pr_body = build_pr_body(repo, findings_list, review)
  effective_title = pr_title or f"Sichter: auto PR ({repo})"

  try:
    run_cmd(["git", "push", "--set-upstream", "origin", branch, "--force-with-lease"], repo_dir)
  except subprocess.CalledProcessError as exc:
    log(f"Push fehlgeschlagen für {repo}/{branch}: {exc}")
    append_event({"type": "push_failed", "repo": repo, "branch": branch, "error": str(exc)})
    return False

  view = run_gh_with_backoff(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"], repo_dir)
  if view.returncode != 0 or not view.stdout.strip():
    create_cmd = [
      "gh",
      "pr",
      "create",
      "--base",
      DEFAULT_BRANCH,
      "--title",
      effective_title,
      "--body",
      pr_body,
      "--label",
      PR_LABEL_SICHTER,
      "--label",
      PR_LABEL_AUTOMATION,
    ]
    if draft_security:
      create_cmd.append("--draft")
    create_result = run_gh_with_backoff(create_cmd, repo_dir)
    if create_result.returncode != 0:
      log(f"PR-Erstellung fehlgeschlagen für {repo}/{branch}")
      append_event(
        {
          "type": "pr_failed",
          "repo": repo,
          "branch": branch,
          "error": (create_result.stderr or "").strip(),
        }
      )
      return False

  edit_result = run_gh_with_backoff(
    ["gh", "pr", "edit", branch, "--title", effective_title, "--body", pr_body],
    repo_dir,
  )
  if edit_result.returncode != 0:
    log(f"PR-Metadaten konnten nicht aktualisiert werden für {repo}/{branch}")

  view = run_gh_with_backoff(["gh", "pr", "view", branch, "--json", "url", "-q", ".url"], repo_dir)
  url = view.stdout.strip() if view.stdout else ""
  append_event({"type": "pr", "repo": repo, "branch": branch, "url": url, "draft": draft_security})
  log(f"PR {repo}: {url or 'unbekannt'}")
  add_inline_pr_comments(repo, repo_dir, branch, findings_list)
  return True


def _sanitize_branch_segment(value: str) -> str:
  """Return a conservative git-branch-safe slug segment."""
  lowered = value.strip().lower()
  cleaned = re.sub(r"[^a-z0-9._-]+", "-", lowered)
  cleaned = re.sub(r"-{2,}", "-", cleaned).strip(".-")
  return cleaned or "misc"


def _build_themed_branch_name(category: str, shortsha: str) -> str:
  """Build themed branch names like ``sichter/<category>/<date>-<shortsha>``."""
  stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
  segment = _sanitize_branch_segment(category)
  return f"sichter/{segment}/{stamp}-{shortsha}"


def create_themed_prs(
  repo: str,
  repo_dir: Path,
  source_branch: str,
  auto_pr: bool,
  findings: Iterable[Finding] | None = None,
  review: ReviewResult | None = None,
) -> int:
  """Create one PR per finding category by projecting changes from source branch.

  If findings are missing or all findings map to a single category, this falls back
  to a single PR on the source branch.
  """
  findings_list = list(findings or [])
  categories = sorted({finding.category for finding in findings_list})
  if len(categories) <= 1:
    return 1 if create_or_update_pr(
      repo,
      repo_dir,
      source_branch,
      auto_pr,
      findings_list,
      review=review,
    ) else 0

  # Keep only categories that can be mapped to concrete files.
  category_files: dict[str, list[str]] = {}
  for finding in findings_list:
    if not finding.file:
      continue
    category_files.setdefault(finding.category, []).append(finding.file)

  actionable_categories = [cat for cat in categories if category_files.get(cat)]
  if not actionable_categories:
    return 1 if create_or_update_pr(
      repo,
      repo_dir,
      source_branch,
      auto_pr,
      findings_list,
      review=review,
    ) else 0

  if len(actionable_categories) == 1:
    single = actionable_categories[0]
    themed_title = f"Sichter: {single} auto PR ({repo})"
    themed_findings = [f for f in findings_list if f.category == single]
    created = create_or_update_pr(
      repo,
      repo_dir,
      source_branch,
      auto_pr,
      themed_findings,
      review=review,
      pr_title=themed_title,
    )
    return 1 if created else 0

  # Guard: if any file appears in more than one category, a multi-PR split would
  # produce overlapping branches with conflicting changes.  Fall back to a single PR.
  file_categories: dict[str, set[str]] = {}
  for finding in findings_list:
    if finding.file:
      file_categories.setdefault(finding.file, set()).add(finding.category)
  if any(len(cats) > 1 for cats in file_categories.values()):
    log(
      f"{repo}: Überlappende Dateien in mehreren Kategorien – "
      "Fallback auf einzelne PR"
    )
    return 1 if create_or_update_pr(
      repo,
      repo_dir,
      source_branch,
      auto_pr,
      findings_list,
      review=review,
    ) else 0

  rev = run_cmd(["git", "rev-parse", "--short", source_branch], repo_dir, check=False)
  shortsha = (rev.stdout or "").strip() if rev.returncode == 0 else "manual"
  if not shortsha:
    shortsha = "manual"

  base_ref = f"origin/{DEFAULT_BRANCH}"
  pr_count = 0
  for category in actionable_categories:
    files = sorted(set(category_files.get(category, [])))
    if not files:
      continue

    themed_branch = _build_themed_branch_name(category, shortsha)
    result = run_cmd(["git", "switch", "--detach", base_ref], repo_dir, check=False)
    if result.returncode != 0:
      run_cmd(["git", "checkout", "--detach", base_ref], repo_dir)

    result = run_cmd(["git", "switch", "-C", themed_branch], repo_dir, check=False)
    if result.returncode != 0:
      run_cmd(["git", "checkout", "-B", themed_branch], repo_dir)

    checkout = run_cmd(["git", "checkout", source_branch, "--", *files], repo_dir, check=False)
    if checkout.returncode != 0:
      log(f"{repo}: Kategorie {category} konnte nicht projiziert werden")
      continue

    if not commit_if_changes(repo_dir):
      log(f"{repo}: Keine Änderungen für Kategorie {category}")
      append_event(
        {
          "type": "noop",
          "repo": repo,
          "branch": themed_branch,
          "category": category,
        }
      )
      continue

    category_findings = [finding for finding in findings_list if finding.category == category]
    themed_title = f"Sichter: {category} auto PR ({repo})"
    created = create_or_update_pr(
      repo,
      repo_dir,
      themed_branch,
      auto_pr,
      category_findings,
      review=None,  # global review covers the full diff; don't attach it to a partial themed PR
      pr_title=themed_title,
      is_security=(category == "security"),
    )
    if created:
      pr_count += 1
  return pr_count


def process_repo(repo: str, mode: str, auto_pr: bool) -> None:
  """Process a single repository end-to-end."""
  started = time.monotonic()
  cache_hits = 0
  prs_created = 0

  repo_dir = ensure_repo(repo)
  if not repo_dir:
    return

  repo_has_git = is_git_repository(repo_dir)

  branch = "-"
  changed_files: list[Path] | None
  if mode == "changed":
    changed_files = get_changed_files(repo_dir, base=None, excludes=POLICY.excludes)
    if not changed_files:
      log(f"Keine geänderten Dateien für {repo} (mode=changed)")
  else:
    changed_files = None

  policy_hash = cache_policy_hash(
    POLICY.checks if isinstance(POLICY.checks, dict) else {},
    list(POLICY.excludes),
  )
  findings_key = make_check_key(repo, current_commit(repo_dir), "registry", policy_hash)
  # Cache is only valid for full-repo scans; changed-file mode produces a different
  # subset of findings so we must not serve a full-scan cache entry for it.
  cache_allowed = (
    changed_files is None
    and isinstance(repo_dir, Path)
    and repo_dir.exists()
    and (repo_dir / ".git").exists()
  )
  cached = cache_get(findings_key) if cache_allowed else None
  if cached and isinstance(cached.get("findings"), list):
    findings = deserialize_findings(cached["findings"])
    cache_hits += 1
    log(f"{repo}: Check-Ergebnisse aus Cache geladen")
  else:
    findings = registry_run_checks(
      repo_dir,
      changed_files,
      POLICY.checks,
      POLICY.excludes,
      run_cmd,
      log,
    )
    if cache_allowed:
      # The cache key is anchored to the starting HEAD commit. Keep the cached
      # payload bound to that commit's raw findings; post-autofix re-scan results
      # belong to a dirty worktree (and later a different commit after commit_if_changes).
      cache_set(findings_key, {"findings": serialize_findings(findings)})

  autofix_tools, target_files_by_tool = _select_autofix_targets(findings)

  autofix = registry_run_autofixes(
    repo_dir,
    changed_files,
    POLICY.checks,
    POLICY.excludes,
    run_cmd,
    log,
    only_tools=autofix_tools,
    target_files_by_tool=target_files_by_tool,
  )
  autofix_applied = False
  for tool_name, changed in autofix.items():
    changed_int = int(changed)
    if changed_int <= 0:
      continue
    autofix_applied = True
    log(f"{repo}: {tool_name} hat {changed_int} Datei(en) angepasst")
    append_event(
      {
        "type": "autofix",
        "repo": repo,
        "tool": tool_name,
        "changed": changed_int,
      }
    )

  if autofix_applied:
    # Re-scan for downstream artefacts (snapshot, LLM review, PR body) so they
    # reflect the post-fix working tree. Do not overwrite the commit-based cache
    # with this state because it no longer corresponds to findings_key.
    findings = registry_run_checks(
      repo_dir,
      changed_files,
      POLICY.checks,
      POLICY.excludes,
      run_cmd,
      log,
    )

  heuristic_findings = run_heuristics(repo_dir, changed_files)
  if heuristic_findings:
    append_event({"type": "heuristics", "repo": repo, "count": len(heuristic_findings)})
  findings = findings + heuristic_findings

  grouped = dedupe_findings(findings)
  record_findings_snapshot(repo, findings)
  if findings:
    log(f"{repo}: {len(findings)} Findings ({len(grouped)} dedupliziert)")
    findings_by_file: dict[str, int] = {}
    finding_items: list[dict] = []
    for finding in findings:
      if finding.file:
        findings_by_file[finding.file] = findings_by_file.get(finding.file, 0) + 1
      if len(finding_items) < 100:
        finding_items.append(
          {
            "severity": finding.severity,
            "category": finding.category,
            "file": finding.file,
            "line": finding.line,
            "message": finding.message,
            "rule_id": finding.rule_id,
          }
        )
    append_event(
      {
        "type": "findings",
        "repo": repo,
        "count": len(findings),
        "deduped": len(grouped),
        "files": sorted(
          (
            {"path": path, "count": count}
            for path, count in findings_by_file.items()
          ),
          key=lambda item: (-item["count"], item["path"]),
        )[:100],
        "items": finding_items,
      }
    )

  # Filter policy-suppressed findings before review/PR generation so they do not
  # leak into the LLM prompt or the resulting PR body.
  findings_for_prs = _filter_findings_for_prs(findings, POLICY.checks, POLICY.security, repo)
  review = llm_review(repo, repo_dir, findings_for_prs)

  if repo_has_git:
    commit_excludes = runtime_artifact_excludes(repo)
    has_changes = has_commit_candidates(repo_dir, commit_excludes)
    if has_changes:
      base_ok = prepare_repo_base(repo_dir)
      if base_ok:
        branch = fresh_branch(repo_dir)
        committed = commit_if_changes(repo_dir, stage_all=True, excludes=commit_excludes)
      else:
        # Change detected but base preparation failed: skip branch/PR creation
        append_event(
          {
            "type": "skipped",
            "repo": repo,
            "reason": "base_preparation_failed",
            "message": f"Changes detected in {repo} aber Base-Detach fehlgeschlagen; branch creation skipped",
          }
        )
        committed = False
    else:
      committed = False
  else:
    # Non-git paths must not trigger Git operations in production.
    # If this path is hit in real deployment, it indicates a configuration error.
    committed = False

  if committed:
    if findings and not findings_for_prs:
      suppressed_categories = sorted({finding.category for finding in findings if finding.category})
      log(f"{repo}: Alle Findings für PR-Erzeugung unterdrückt ({', '.join(suppressed_categories)})")
      append_event(
        {
          "type": "pr_suppressed",
          "repo": repo,
          "branch": branch,
          "categories": suppressed_categories,
          "reason": "all_findings_filtered",
        }
      )
    else:
      prs_created = create_themed_prs(repo, repo_dir, branch, auto_pr, findings_for_prs, review)
  else:
    log(f"Keine Änderungen für {repo}")
    append_event({"type": "noop", "repo": repo, "branch": branch})

  findings_by_severity: dict[str, int] = {}
  for finding in findings:
    findings_by_severity[finding.severity] = findings_by_severity.get(finding.severity, 0) + 1

  try:
    llm_tokens_used = int(getattr(review, "tokens_used", 0)) if review is not None else 0
  except (TypeError, ValueError):
    llm_tokens_used = 0
  try:
    prs_created_int = int(prs_created)
  except (TypeError, ValueError):
    prs_created_int = 0

  record_metrics(
    ReviewMetrics(
      repo=repo,
      duration_seconds=round(time.monotonic() - started, 2),
      findings_count=len(findings),
      findings_by_severity=findings_by_severity,
      llm_tokens_used=llm_tokens_used,
      cache_hits=cache_hits,
      prs_created=prs_created_int,
    )
  )


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

  include_self = Policy._bool_with_default(job.get("include_self"), POLICY.include_self_repo)

  repos: list[str]
  if repo_one:
    repos = [repo_one]
  elif mode == "all":
    repos = list(job.get("repos") or _filter_discovered_repos(list_repos_remote(), include_self))
  else:
    repos = _filter_discovered_repos(list_repos_local(), include_self)

  # Deduplicate while preserving order to prevent concurrent git operations on the
  # same worktree when the caller accidentally supplies duplicate repo entries.
  seen: set[str] = set()
  repos = [r for r in repos if not (r in seen or seen.add(r))]  # type: ignore[func-returns-value]

  if len(repos) <= 1:
    for repo in repos:
      process_repo(repo, mode, auto_pr)
    return

  max_workers = max(1, min(POLICY.max_parallel_repos, len(repos)))
  with ThreadPoolExecutor(max_workers=max_workers) as executor:
    future_map = {executor.submit(process_repo, repo, mode, auto_pr): repo for repo in repos}
    for future in as_completed(future_map):
      repo = future_map[future]
      try:
        future.result()
      except Exception as exc:  # pragma: no cover
        log(f"Fehler bei Repo {repo}: {exc}")
        append_event({"type": "error", "repo": repo, "message": str(exc)})


def list_repos_local() -> list[str]:
  base = HOME / "repos"
  if not base.exists():
    return []
  return [
    p.name
    for p in base.iterdir()
    if (p / ".git").exists()
    and not p.name.startswith(".")
    and p.name not in LOCAL_DISCOVERY_EXCLUDE
  ]


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


def get_sorted_jobs(queue_dir: Path) -> list[Path]:
  """Return sorted list of job files in queue with priority support."""
  files: list[str] = []
  try:
    with os.scandir(queue_dir) as it:
      for entry in it:
        if not entry.name.endswith(".json"):
          continue
        # Check is_file with no symlink following for safety/consistency
        try:
          is_file = entry.is_file(follow_symlinks=False)
        except TypeError:
          # Fallback for older Python versions
          is_file = entry.is_file()
        except OSError:
          continue

        if is_file:
          files.append(entry.path)
  except OSError:
    return []

  files.sort()
  priority_rank = {"high": 0, "normal": 1, "low": 2}

  def file_priority(path_str: str) -> int:
    try:
      data = json.loads(Path(path_str).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
      return 1
    return priority_rank.get(str(data.get("priority", "normal")).lower(), 1)

  files.sort(key=file_priority)
  return [Path(p) for p in files]


def wait_for_changes(queue_dir: Path) -> None:
  """Wait for file changes using inotifywait or fallback to sleep.

  Uses inotifywait if available to block until a file is created or moved in,
  avoiding busy polling loops.
  """
  if not shutil.which("inotifywait"):
    time.sleep(2)
    return

  proc = None
  try:
    # Start inotifywait in background
    # -q: quiet (less output)
    # -e create -e moved_to: wait for file creation or move-in
    proc = subprocess.Popen(
      ["inotifywait", "-q", "-e", "create", "-e", "moved_to", str(queue_dir)],
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      text=True,
    )

    # Wait for "Watches established" to ensure we don't miss events
    # that happen between our last check and the watch start.
    # Use select with timeout to avoid hanging if stderr logic fails.
    if proc.stderr and hasattr(select, "poll"):
      poll_obj = select.poll()
      poll_obj.register(proc.stderr, select.POLLIN)
      try:
        start_time = time.time()
        while time.time() - start_time < 1.0:
          if proc.poll() is not None:
            break
          if poll_obj.poll(100):  # 100ms timeout
            line = proc.stderr.readline()
            if line and "Watches established" in line:
              break
      finally:
        try:
          poll_obj.unregister(proc.stderr)
        except (OSError, ValueError, KeyError):
          pass

    # Double-check if files arrived while we were starting up.
    # This check AFTER starting the watch significantly reduces the race window.
    if get_sorted_jobs(queue_dir):
      return

    # Block until event occurs or process exits
    exit_code = proc.wait()

    # If inotifywait failed (e.g. exit code 1), sleep to prevent busy loop
    if exit_code != 0:
      time.sleep(2)

  except (OSError, subprocess.SubprocessError):
    time.sleep(2)
  finally:
    if proc:
      # Ensure process is terminated
      # NOTE: this function may return early (jobs arrived); cleanup is handled here.
      if proc.poll() is None:
        proc.terminate()
        try:
          proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
          proc.kill()

      # Ensure streams are closed to prevent FD leaks
      if proc.stdout:
        proc.stdout.close()
      if proc.stderr:
        proc.stderr.close()


def main() -> int:
  acquire_pid_lock()
  log("Worker gestartet")
  append_event({"type": "start", "message": f"Worker gestartet (pid={os.getpid()})"})
  try:
    while True:
      job_files = get_sorted_jobs(QUEUE)
      if not job_files:
        wait_for_changes(QUEUE)
        continue
      for job_file in job_files:
        try:
          job = json.loads(job_file.read_text(encoding="utf-8"))
          handle_job(job)
        except Exception as exc:  # pragma: no cover
          log(f"Fehler bei {job_file.name}: {exc}")
          append_event({"type": "error", "message": f"Job {job_file.name} failed: {exc}"})
        finally:
          job_file.unlink(missing_ok=True)
  except KeyboardInterrupt:
    log("Worker beendet (KeyboardInterrupt)")
    append_event({"type": "stop", "message": "KeyboardInterrupt"})
    return 0


if __name__ == "__main__":
  sys.exit(main())

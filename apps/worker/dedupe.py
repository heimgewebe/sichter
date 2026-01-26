from __future__ import annotations

from collections import OrderedDict
from typing import Iterable

from lib.findings import Finding


def dedupe_findings(findings: Iterable[Finding]) -> dict[str, list[Finding]]:
  """Group findings by dedupe_key while preserving order."""
  grouped: OrderedDict[str, list[Finding]] = OrderedDict()
  for finding in findings:
    key = finding.dedupe_key or ""
    if key not in grouped:
      grouped[key] = []
    grouped[key].append(finding)
  return dict(grouped)


def should_create_pr(findings: Iterable[Finding]) -> bool:
  """Return True if there are any actionable findings.
  
  Note: This function converts the iterable to a list to avoid consuming
  an iterator that might be reused by the caller.
  """
  findings_list = list(findings) if not isinstance(findings, (list, tuple)) else findings
  return bool(findings_list)

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable

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
  
  Actionable findings are those with severity "error" or "critical", 
  or findings that have an available fix.
  
  Note: This function converts iterables to a list, which will consume
  iterator inputs. Callers that need to reuse an iterator should materialize
  it (e.g., with list(...)) before calling this function.
  """
  findings_list = list(findings)
  return any(
    f.severity in {"error", "critical"} or f.fix_available
    for f in findings_list
  )

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Severity = Literal["info", "warning", "error", "critical", "question"]
Category = Literal["style", "correctness", "security", "maintainability", "drift"]


@dataclass
class Finding:
  severity: Severity
  category: Category
  file: str
  line: int | None
  message: str
  evidence: str | None = None
  fix_available: bool = False
  dedupe_key: str = ""
  uncertainty: dict | None = None
  tool: str | None = None
  rule_id: str | None = None

  def __post_init__(self) -> None:
    if not self.dedupe_key:
      tool = (self.tool or "unknown").strip().lower()
      rule = (self.rule_id or "").strip().lower()

      if rule:
        self.dedupe_key = f"{tool}:{rule}:{self.file}"
        return

      line = self.line if self.line is not None else 0
      location = f"{self.file}:{line}"
      normalized_message = " ".join(self.message.strip().lower().split())[:80]
      self.dedupe_key = f"{tool}:{self.category}:{location}:{normalized_message}"

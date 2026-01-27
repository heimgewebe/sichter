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
      rule = self.rule_id or ""
      self.dedupe_key = f"{self.category}:{self.file}:{rule}:{self.message[:50]}"

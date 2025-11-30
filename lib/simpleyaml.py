"""Minimal YAML helpers used as fallback when PyYAML is unavailable."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Iterable


@dataclass
class _ParserState:
 lines: list[str]
 index: int = 0

 def peek(self) -> str | None:
  while self.index < len(self.lines):
   line = self.lines[self.index]
   if not line.strip() or line.lstrip().startswith("#"):
    self.index += 1
    continue
   return line
  return None

 def pop(self) -> str | None:
  line = self.peek()
  if line is None:
   return None
  value = self.lines[self.index]
  self.index += 1
  return value


def _parse_scalar(text: str) -> Any:
 lowered = text.lower()
 if lowered == "true":
  return True
 if lowered == "false":
  return False
 if lowered in {"null", "none"}:
  return None
 if text.startswith("'") and text.endswith("'"):
  return text[1:-1]
 if text.startswith('"') and text.endswith('"'):
  return text[1:-1]
 try:
  return int(text)
 except ValueError:
  pass
 try:
  return float(text)
 except ValueError:
  pass
 return text


def _parse_block(state: _ParserState, indent: int) -> Any:
 first_line = state.peek()
 if first_line is None:
  return {}
 if first_line.strip().startswith("- "):
  items: list[Any] = []
  while True:
   line = state.peek()
   if line is None:
    break
   current_indent = len(line) - len(line.lstrip(" "))
   if current_indent < indent:
    break
   if not line.strip().startswith("- "):
    break
   state.pop()
   payload = line.strip()[2:].strip()
   if payload:
    items.append(_parse_scalar(payload))
   else:
    items.append(_parse_block(state, indent + 2))
  return items
 mapping: dict[str, Any] = {}
 while True:
  line = state.peek()
  if line is None:
   break
  current_indent = len(line) - len(line.lstrip(" "))
  if current_indent < indent:
   break
  state.pop()
  stripped = line.strip()
  if ":" not in stripped:
   continue
  key, _, rest = stripped.partition(":")
  key = key.strip()
  rest = rest.strip()
  if rest:
   mapping[key] = _parse_scalar(rest)
  else:
   mapping[key] = _parse_block(state, indent + 2)
 return mapping


def load(path: Path) -> dict[str, Any]:
 text = path.read_text(encoding="utf-8")
 lines = text.splitlines()
 state = _ParserState(lines)
 result = _parse_block(state, 0)
 if isinstance(result, dict):
  return result
 return {"_": result}


def _format_scalar(value: Any) -> str:
 if isinstance(value, bool):
  return "true" if value else "false"
 if value is None:
  return "null"
 return str(value)


def _dump_lines(value: Any, indent: int) -> Iterable[str]:
 prefix = " " * indent
 if isinstance(value, dict):
  for key, val in value.items():
   if isinstance(val, (dict, list)):
    yield f"{prefix}{key}:"
    yield from _dump_lines(val, indent + 2)
   else:
    yield f"{prefix}{key}: {_format_scalar(val)}"
 elif isinstance(value, list):
  for item in value:
   if isinstance(item, (dict, list)):
    yield f"{prefix}-"
    yield from _dump_lines(item, indent + 2)
   else:
    yield f"{prefix}- {_format_scalar(item)}"
 else:
  yield f"{prefix}{_format_scalar(value)}"


def dump(data: dict[str, Any]) -> str:
 return "\n".join(_dump_lines(data, 0)) + "\n"

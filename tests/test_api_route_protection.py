import ast
from pathlib import Path

def test_routes_are_protected():
  api_main = Path("apps/api/main.py")
  tree = ast.parse(api_main.read_text())

  # Sensitive routes we expect to find
  sensitive_routes = {
    "/jobs/submit",
    "/events/tail",
    "/events/recent",
    "/overview",
    "/repos/findings",
    "/repos/findings/detail",
    "/repos/status",
    "/settings/policy",
    "/events/stream",
    "/repos/findings/detail",
    "/metrics/trends",
    "/metrics/prometheus",
    "/alerts",
    "/metrics/review-quality",
  }

  found_routes = set()
  unprotected_routes = []

  for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
      for decorator in node.decorator_list:
        # Check if it's a route decorator @app.get, @app.post, etc. or @app.websocket
        is_route = False
        route_path = None

        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
          if isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app":
            is_route = True
            if decorator.args:
              arg = decorator.args[0]
              if isinstance(arg, ast.Constant):
                route_path = arg.value
              elif isinstance(arg, ast.Str): # Support older versions just in case
                route_path = arg.s

        if not is_route or route_path == "/healthz":
          continue

        if route_path in sensitive_routes:
          found_routes.add(route_path)

          # Check for Depends(verify_api_key)
          protected = False

          # 1. Check decorator keywords for dependencies=[...] (standard for HTTP routes)
          for kw in decorator.keywords:
            if kw.arg == "dependencies":
              if isinstance(kw.value, ast.List):
                for elt in kw.value.elts:
                  if isinstance(elt, ast.Call) and isinstance(elt.func, ast.Name) and elt.func.id == "Depends":
                    if elt.args and isinstance(elt.args[0], ast.Name) and elt.args[0].id == "verify_api_key":
                      protected = True
                      break

          # 2. Check function arguments for Depends(verify_api_key) (standard for WebSockets)
          # We need to find if any argument has Depends(verify_api_key) as default
          # node.args.defaults contains defaults for the last n arguments.
          num_defaults = len(node.args.defaults)
          if num_defaults > 0:
            for i in range(num_defaults):
              default = node.args.defaults[i]
              if isinstance(default, ast.Call) and isinstance(default.func, ast.Name) and default.func.id == "Depends":
                if default.args and isinstance(default.args[0], ast.Name) and default.args[0].id == "verify_api_key":
                  protected = True

          if not protected:
            unprotected_routes.append(f"{node.name} ({route_path})")

  missing_routes = sensitive_routes - found_routes
  assert not missing_routes, f"Could not find all expected routes in apps/api/main.py: {missing_routes}. Found: {found_routes}"
  assert not unprotected_routes, f"Found unprotected routes in apps/api/main.py: {unprotected_routes}"


def test_job_model_supports_priority_field():
  tree = ast.parse(Path("apps/api/main.py").read_text())

  job_class = None
  for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "Job":
      job_class = node
      break

  assert job_class is not None, "Class Job not found in apps/api/main.py"

  priority_field = None
  for node in job_class.body:
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "priority":
      priority_field = node
      break

  assert priority_field is not None, "Job.priority field is missing"
  assert isinstance(priority_field.value, ast.Constant) and priority_field.value.value == "normal", (
    "Job.priority default must be 'normal'"
  )


def test_queue_state_exposes_priority():
  tree = ast.parse(Path("apps/api/main.py").read_text())

  queue_state_fn = None
  for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == "_queue_state":
      queue_state_fn = node
      break

  assert queue_state_fn is not None, "Function _queue_state not found in apps/api/main.py"

  priority_key_found = False
  for node in ast.walk(queue_state_fn):
    if not isinstance(node, ast.Dict):
      continue
    for key in node.keys:
      if isinstance(key, ast.Constant) and key.value == "priority":
        priority_key_found = True
        break
    if priority_key_found:
      break

  assert priority_key_found, "_queue_state() must include 'priority' in returned queue items"


def _extract_normalize_priority():
  """Extract and exec _normalize_priority from apps/api/main.py.

  Uses ast.unparse so the function runs standalone without any fastapi/pydantic
  imports — the function body is pure Python with no external dependencies.
  """
  import ast as _ast

  tree = _ast.parse(Path("apps/api/main.py").read_text())
  fn_node = next(
    (n for n in tree.body if isinstance(n, _ast.FunctionDef) and n.name == "_normalize_priority"),
    None,
  )
  assert fn_node is not None, "_normalize_priority not found in apps/api/main.py"
  ns: dict = {}
  exec(_ast.unparse(fn_node), ns)  # noqa: S102
  return ns["_normalize_priority"]


def test_normalize_priority_valid_values_pass_through():
  """_normalize_priority: high/normal/low — and their uppercase variants — are returned as canonical lowercase."""
  normalize = _extract_normalize_priority()
  assert normalize("high") == "high"
  assert normalize("normal") == "normal"
  assert normalize("low") == "low"
  assert normalize("HIGH") == "high"
  assert normalize("Normal") == "normal"


def test_normalize_priority_invalid_and_none_become_normal():
  """_normalize_priority: unknown string, None, non-string, empty string → 'normal'."""
  normalize = _extract_normalize_priority()
  assert normalize("urgent") == "normal"
  assert normalize(None) == "normal"
  assert normalize(7) == "normal"
  assert normalize("") == "normal"


def test_queue_state_normalizes_priority_at_runtime():
  """Runtime: _queue_state() reads a real queue file with priority='urgent' → returns 'normal'.

  Proof that the API read-path calls _normalize_priority() on the actual payload,
  not just that the helper works in isolation.  Uses the same AST+exec pattern as
  _extract_normalize_priority() to stay within the minimal test-venv dependencies.
  """
  import ast as _ast
  import functools as _functools
  import json as _json
  import logging as _logging
  import os as _os
  import tempfile
  import time as _time
  from datetime import datetime as _datetime
  from datetime import timezone as _timezone

  source = Path("apps/api/main.py").read_text()
  tree = _ast.parse(source)

  needed = {"_normalize_priority", "_read_queue_item_cached", "_queue_state"}
  fn_nodes = {
    node.name: node
    for node in tree.body
    if isinstance(node, _ast.FunctionDef) and node.name in needed
  }
  assert needed == fn_nodes.keys(), f"Missing functions in apps/api/main.py: {needed - fn_nodes.keys()}"

  with tempfile.TemporaryDirectory() as tmp:
    queue_dir = Path(tmp)
    (queue_dir / "1700000000-runtime-test.json").write_text(
      _json.dumps({"type": "ScanAll", "mode": "changed", "priority": "urgent"}),
      encoding="utf-8",
    )

    ns: dict = {
      "os": _os,
      "json": _json,
      "functools": _functools,
      "logging": _logging,
      "time": _time,
      "datetime": _datetime,
      "timezone": _timezone,
      "Path": Path,
      "QUEUE": queue_dir,
      "logger": _logging.getLogger("test._queue_state"),
    }
    for name in ("_normalize_priority", "_read_queue_item_cached", "_queue_state"):
      exec(_ast.unparse(fn_nodes[name]), ns)  # noqa: S102

    state = ns["_queue_state"]()

  assert state["size"] == 1, f"Expected 1 queue item, got {state['size']}"
  assert len(state["items"]) == 1
  assert state["items"][0]["priority"] == "normal", (
    f"Expected 'normal' but got {state['items'][0]['priority']!r}: "
    "_queue_state() must normalise 'urgent' via _normalize_priority()"
  )

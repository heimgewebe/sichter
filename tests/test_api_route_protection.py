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
    "/repos/status",
    "/settings/policy",
    "/events/stream"
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

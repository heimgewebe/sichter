import ast
import os
from pathlib import Path

# Helper function to parse _build_allowed_origins logic directly from the file
# for testing without importing (to avoid dependency issues with PyYAML/FastAPI).
def get_build_allowed_origins_logic_node():
    api_main = Path("apps/api/main.py")
    tree = ast.parse(api_main.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_build_allowed_origins":
            return node
    return None

def test_routes_are_protected_by_middleware_static():
    """Verify via AST that the middleware is correctly applied in the code."""
    api_main = Path("apps/api/main.py")
    tree = ast.parse(api_main.read_text())

    found_middleware = False
    allow_origins_expr = None
    allow_credentials_val = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_middleware":
                # Check if first arg is CORSMiddleware
                if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "CORSMiddleware":
                    found_middleware = True
                    for kw in node.keywords:
                        if kw.arg == "allow_origins":
                            # It should now be calling _build_allowed_origins()
                            if isinstance(kw.value, ast.Call) and isinstance(kw.value.func, ast.Name):
                                allow_origins_expr = kw.value.func.id
                        if kw.arg == "allow_credentials":
                            if isinstance(kw.value, ast.Constant):
                                allow_credentials_val = kw.value.value

    assert found_middleware, "CORSMiddleware not found in apps/api/main.py"
    assert allow_origins_expr == "_build_allowed_origins", f"Expected allow_origins=_build_allowed_origins(), found {allow_origins_expr}"
    assert allow_credentials_val is True, "allow_credentials should be True"

def test_build_allowed_origins_logic_execution():
    """Extract and execute the _build_allowed_origins function logic to verify its behavior."""
    node = get_build_allowed_origins_logic_node()
    assert node is not None, "_build_allowed_origins function not found"

    # We compile and execute the function definition in an isolated namespace
    # to avoid dependency issues with the rest of apps/api/main.py
    code = compile(ast.Module(body=[node], type_ignores=[]), "<string>", "exec")

    # Mock 'os' for the function to use
    class MockOs:
        environ = {}
        @staticmethod
        def get(key, default=None):
            return MockOs.environ.get(key, default)

    namespace = {"os": MockOs}
    exec(code, namespace)
    _func = namespace["_build_allowed_origins"]

    # 1. Test defaults
    defaults = _func(None)
    assert "http://localhost:5173" in defaults
    assert "http://127.0.0.1:4173" in defaults
    assert len(defaults) == 4

    # 2. Test environment overrides with normalization
    raw = " https://dashboard.io/ , http://prod.local, *, invalid-protocol, http://dup.com, http://dup.com/ "
    origins = _func(raw)

    assert "https://dashboard.io" in origins  # Trimmed and trailing slash removed
    assert "http://prod.local" in origins
    assert "*" not in origins                 # Security: wildcard rejected
    assert "invalid-protocol" not in origins  # Security: protocol enforced
    assert origins.count("http://dup.com") == 1 # Deduplication

    # 3. Test empty inputs
    assert len(_func("")) == 4
    assert len(_func(" , , ")) == 4

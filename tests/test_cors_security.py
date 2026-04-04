import ast
import os
from pathlib import Path
from unittest.mock import patch

# --- Logic Extraction for Isolated Testing ------------------------------------

def extract_build_allowed_origins():
    """Extracts _build_allowed_origins from apps/api/main.py via AST.

    This technique allows testing the core logic in isolation without triggering
    unrelated module side-effects or requiring external dependencies (FastAPI, PyYAML)
    in the test environment.
    """
    api_main = Path("apps/api/main.py")
    tree = ast.parse(api_main.read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_build_allowed_origins")

    # Compile in a namespace that includes 'os' for env access
    namespace = {"os": os}
    code = compile(ast.Module(body=[node], type_ignores=[]), "<string>", "exec")
    exec(code, namespace)
    return namespace["_build_allowed_origins"]

# --- Tests ------------------------------------

def test_middleware_uses_build_allowed_origins_static():
    """Verify via AST that the middleware uses our helper and has credentials enabled."""
    api_main = Path("apps/api/main.py")
    tree = ast.parse(api_main.read_text())

    found_middleware = False
    allow_origins_expr = None
    allow_credentials_val = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_middleware":
                if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "CORSMiddleware":
                    found_middleware = True
                    for kw in node.keywords:
                        if kw.arg == "allow_origins":
                            if isinstance(kw.value, ast.Call) and isinstance(kw.value.func, ast.Name):
                                allow_origins_expr = kw.value.func.id
                        if kw.arg == "allow_credentials":
                            if isinstance(kw.value, ast.Constant):
                                allow_credentials_val = kw.value.value

    assert found_middleware, "CORSMiddleware not found"
    assert allow_origins_expr == "_build_allowed_origins"
    assert allow_credentials_val is True

def test_build_allowed_origins_logic():
    """Verify logic behavior with various parameter inputs, ensuring env independence."""
    _func = extract_build_allowed_origins()

    with patch.dict(os.environ, {}, clear=True):
        # 1. Defaults
        defaults = _func(None)
        assert len(defaults) == 4
        assert "http://localhost:5173" in defaults
        assert "http://127.0.0.1:4173" in defaults

        # 2. Parameter-based overrides (normalization + security)
        # Input: trailing slash, wildcard, non-http, duplicate, empty
        raw = " https://dashboard.io/ , http://api.local, *, invalid-protocol, http://api.local "
        origins = _func(raw)

        assert "https://dashboard.io" in origins  # Stripped trailing slash
        assert "http://api.local" in origins      # Included
        assert origins.count("http://api.local") == 1  # Deduplicated
        assert "*" not in origins                 # Security: wildcard rejected
        assert "invalid-protocol" not in origins  # Security: protocol enforced

        # 3. Empty/Malformed inputs
        assert len(_func("")) == 4
        assert len(_func(" , , ")) == 4
        assert len(_func(None)) == 4

def test_build_allowed_origins_env_fallback():
    """Verify the real environment variable fallback path."""
    _func = extract_build_allowed_origins()

    with patch.dict(os.environ, {"SICHTER_ALLOWED_ORIGINS": "https://env.io"}, clear=True):
        # Passing None triggers the env lookup path in the function
        origins_env = _func(None)
        assert "https://env.io" in origins_env
        assert "http://localhost:5173" in origins_env
        assert len(origins_env) == 5

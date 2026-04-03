import ast
from pathlib import Path

def test_cors_policy_restricted():
    api_main = Path("apps/api/main.py")
    tree = ast.parse(api_main.read_text())

    found_middleware = False
    allow_origins_val = None
    allow_credentials_val = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "add_middleware":
                # Check if first arg is CORSMiddleware
                if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "CORSMiddleware":
                    found_middleware = True
                    for kw in node.keywords:
                        if kw.arg == "allow_origins":
                            if isinstance(kw.value, ast.Name):
                                allow_origins_val = kw.value.id
                            elif isinstance(kw.value, ast.List):
                                allow_origins_val = [elt.value for elt in kw.value.elts if isinstance(elt, ast.Constant)]
                        if kw.arg == "allow_credentials":
                            if isinstance(kw.value, ast.Constant):
                                allow_credentials_val = kw.value.value

    assert found_middleware, "CORSMiddleware not found in apps/api/main.py"
    assert allow_origins_val != ["*"], "CORSMiddleware still allows all origins ['*']"
    assert allow_origins_val == "allowed_origins", f"Expected allow_origins=allowed_origins, found {allow_origins_val}"
    assert allow_credentials_val is True, "allow_credentials should be True"

def test_allowed_origins_definition():
    api_main = Path("apps/api/main.py")
    tree = ast.parse(api_main.read_text())

    found_definition = False
    default_origins = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "allowed_origins":
                    found_definition = True
                    if isinstance(node.value, ast.List):
                        default_origins = [elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)]

    assert found_definition, "Variable 'allowed_origins' not found in apps/api/main.py"
    assert "http://localhost:5173" in default_origins
    assert "http://127.0.0.1:5173" in default_origins
    assert "http://localhost:4173" in default_origins

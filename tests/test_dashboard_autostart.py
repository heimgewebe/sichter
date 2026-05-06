import re
import subprocess
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1] / "bin" / "sichter-dashboard"


def read_dashboard() -> str:
    return DASHBOARD.read_text()


def assert_dispatches(source: str, menu_number: str, function_name: str, action: str) -> None:
    pattern = rf"(^|\n)\s*{re.escape(menu_number)}\)\s+{re.escape(function_name)}\s+{re.escape(action)}\s*;;"
    assert re.search(pattern, source, re.S), f"missing dispatch {menu_number}) {function_name} {action}"


def test_worker_autostart_menu_entries_exist() -> None:
    source = read_dashboard()

    assert "6) Worker Autostart Status" in source
    assert "7) Worker Autostart AN" in source
    assert "8) Worker Autostart AUS" in source


def test_worker_autostart_function_and_systemctl_actions_exist() -> None:
    source = read_dashboard()

    assert "control_worker_autostart()" in source
    assert 'systemctl --user enable "$WORKER_SERVICE"' in source
    assert 'systemctl --user disable "$WORKER_SERVICE"' in source
    assert 'systemctl --user is-enabled "$WORKER_SERVICE"' in source


def test_worker_autostart_dispatch_is_separate_from_runtime_control() -> None:
    source = read_dashboard()

    assert_dispatches(source, "6", "control_worker_autostart", "is-enabled")
    assert_dispatches(source, "7", "control_worker_autostart", "enable")
    assert_dispatches(source, "8", "control_worker_autostart", "disable")
    assert_dispatches(source, "3", "control_worker", "start")
    assert_dispatches(source, "4", "control_worker", "stop")
    assert_dispatches(source, "5", "control_worker", "status")


def test_dashboard_shell_syntax_is_valid() -> None:
    subprocess.run(["bash", "-n", str(DASHBOARD)], check=True)

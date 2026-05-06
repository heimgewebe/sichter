import subprocess
from pathlib import Path


DASHBOARD = Path(__file__).resolve().parents[1] / "bin" / "sichter-dashboard"


def read_dashboard() -> str:
    return DASHBOARD.read_text()


def test_worker_autostart_menu_entries_exist() -> None:
    source = read_dashboard()

    assert "Worker Autostart Status" in source
    assert "Worker Autostart AN" in source
    assert "Worker Autostart AUS" in source


def test_worker_autostart_function_and_systemctl_actions_exist() -> None:
    source = read_dashboard()

    assert "control_worker_autostart()" in source
    assert 'systemctl --user enable "$WORKER_SERVICE"' in source
    assert 'systemctl --user disable "$WORKER_SERVICE"' in source
    assert 'systemctl --user is-enabled "$WORKER_SERVICE"' in source


def test_worker_autostart_dispatch_is_separate_from_runtime_control() -> None:
    source = read_dashboard()

    assert "6) control_worker_autostart is-enabled ;;" in source
    assert "7) control_worker_autostart enable ;;" in source
    assert "8) control_worker_autostart disable ;;" in source
    assert "3) control_worker start ;;" in source
    assert "4) control_worker stop ;;" in source
    assert "5) control_worker status ;;" in source


def test_dashboard_shell_syntax_is_valid() -> None:
    subprocess.run(["bash", "-n", str(DASHBOARD)], check=True)

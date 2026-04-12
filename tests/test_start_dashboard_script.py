from pathlib import Path


def test_start_dashboard_has_ui_mode_split():
    script = Path("scripts/start-dashboard.sh").read_text(encoding="utf-8")
    assert "SICHTER_UI_MODE" in script
    assert "web)" in script
    assert "tui)" in script


def test_start_dashboard_healthcheck_only_for_web():
    script = Path("scripts/start-dashboard.sh").read_text(encoding="utf-8")
    assert "wait_for_health" in script
    assert "curl is required in web mode" in script
    assert "exec \"$TUI_BIN\"" in script

"""
Behavioral integration tests for scripts/start-dashboard.sh.

These tests actually run the shell script as a subprocess with controlled
mock binaries and check real exit codes, process behavior, and output.
They are intentionally slow (up to ~5 s per test) but provide genuine
execution evidence that the string-guard tests in
test_start_dashboard_script.py cannot give.
"""

import os
import signal
import socket
import subprocess
import tempfile
from pathlib import Path

SCRIPT = str(Path(__file__).parent.parent / "scripts" / "start-dashboard.sh")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_http_mock(tmpdir: str, port: int) -> Path:
    """Create an executable that serves HTTP 200 on any path (including /healthz)."""
    p = Path(tmpdir) / "mock-web-bin"
    p.write_text(
        "#!/usr/bin/env python3\n"
        "import http.server\n"
        "class H(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200)\n"
        "        self.end_headers()\n"
        "    def log_message(self, *a): pass\n"
        f"http.server.HTTPServer(('127.0.0.1', {port}), H).serve_forever()\n"
    )
    p.chmod(0o755)
    return p


def _make_silent_mock(tmpdir: str, name: str = "mock-silent-bin") -> Path:
    """Create an executable that starts but never responds to HTTP.
    Uses exec so $web_pid == the sleep process directly — ensures SIGTERM
    from the script cleanly terminates it without a wrapper-shell delay.
    """
    p = Path(tmpdir) / name
    p.write_text("#!/bin/bash\nexec sleep 30\n")
    p.chmod(0o755)
    return p


def _env_for(port: int, mode: str, **extra) -> dict:
    base = dict(os.environ)
    base.update({
        "SICHTER_UI_MODE": mode,
        "HOST": "127.0.0.1",
        "PORT": str(port),
        # Use the same port for kill-check; it's freshly allocated so lsof
        # finds nothing and the kill is a harmless no-op.
        "SICHTER_HEALTH_TIMEOUT_SECONDS": "5",
        "SICHTER_HEALTH_INTERVAL_SECONDS": "1",
    })
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Web mode: healthy path
# ---------------------------------------------------------------------------

def test_integration_web_mode_healthy_exits_zero():
    """
    Web mode with a mock server that responds 200 on /healthz.
    The script must exit 0 and log 'Health check passed'.
    """
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        web_bin = _make_http_mock(tmpdir, port)
        web_log = Path(tmpdir) / "web.out"
        env = _env_for(port, "web", SICHTER_DASHBOARD_WEB_BIN=str(web_bin))
        env["SICHTER_WEB_STDOUT"] = str(web_log)
        env["SICHTER_WEB_STDERR"] = str(web_log)
        result = subprocess.run(
            ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=20
        )

        # Healthy web mode intentionally leaves the service running; terminate
        # the mock process to keep the test process tree clean.
        if "Web dashboard running (pid=" in result.stdout:
            pid_text = result.stdout.split("Web dashboard running (pid=")[-1].split(")", 1)[0]
            pid = int(pid_text)
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    assert result.returncode == 0, (
        f"Expected rc=0, got rc={result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "Health check passed" in result.stdout, (
        f"Expected health-check log in stdout:\n{result.stdout}"
    )


# ---------------------------------------------------------------------------
# Web mode: unhealthy path (mock never responds)
# ---------------------------------------------------------------------------

def test_integration_web_mode_unhealthy_fails_within_timeout():
    """
    Web mode with a mock server that never responds.
    The script must exit non-zero and emit the 'failed health check' error
    within the configured timeout — not hang indefinitely.
    """
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        web_bin = _make_silent_mock(tmpdir)
        env = _env_for(
            port, "web",
            SICHTER_DASHBOARD_WEB_BIN=str(web_bin),
            SICHTER_HEALTH_TIMEOUT_SECONDS="3",
        )
        result = subprocess.run(
            ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=10
        )

    assert result.returncode != 0, (
        f"Expected failure, got rc={result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "failed health check" in result.stderr, (
        f"Expected 'failed health check' in stderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# TUI mode: no curl, exec replaces shell
# ---------------------------------------------------------------------------

def test_integration_tui_mode_exits_zero_no_curl():
    """
    TUI mode exec's the mock binary directly.
    No curl must be invoked; the script must exit 0.
    """
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        tui_bin = Path(tmpdir) / "mock-tui"
        tui_bin.write_text("#!/bin/bash\nexit 0\n")
        tui_bin.chmod(0o755)

        env = _env_for(port, "tui", SICHTER_DASHBOARD_TUI_BIN=str(tui_bin))
        result = subprocess.run(
            ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=5
        )

    assert result.returncode == 0, (
        f"Expected rc=0, got rc={result.returncode}\n"
        f"stderr: {result.stderr}"
    )
    # TUI mode must never touch curl
    assert "curl" not in result.stdout
    assert "curl" not in result.stderr


# ---------------------------------------------------------------------------
# Invalid mode: fail-fast
# ---------------------------------------------------------------------------

def test_integration_invalid_mode_fails_immediately():
    """Invalid SICHTER_UI_MODE must exit non-zero with an informative error."""
    port = _find_free_port()
    env = _env_for(port, "invalid-mode")
    result = subprocess.run(
        ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=5
    )

    assert result.returncode != 0
    assert "invalid-mode" in result.stderr.lower() or "invalid" in result.stderr.lower()


def test_integration_web_mode_refuses_killing_unknown_listener_by_default():
    """If another process listens on the port, script must fail without killing it."""
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        foreign_bin = _make_http_mock(tmpdir, port)
        foreign_proc = subprocess.Popen([str(foreign_bin)])
        try:
            web_bin = _make_silent_mock(tmpdir, name="mock-owned-web-bin")
            env = _env_for(
                port,
                "web",
                SICHTER_DASHBOARD_WEB_BIN=str(web_bin),
                SICHTER_HEALTH_TIMEOUT_SECONDS="2",
            )
            result = subprocess.run(
                ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=8
            )

            assert result.returncode != 0, "Expected failure when port is already in use"
            assert "refusing to kill unknown listeners" in result.stderr
            assert foreign_proc.poll() is None, "Foreign listener should still be running"
        finally:
            foreign_proc.terminate()
            foreign_proc.wait(timeout=5)

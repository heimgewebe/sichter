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
import time
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


def _wait_until_listening(port: int, timeout_seconds: float = 5.0) -> None:
    """Wait until a local TCP listener accepts connections on the target port."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for listener on port {port}")


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
            _wait_until_listening(port)
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


def test_integration_web_start_status_stop_lifecycle():
    """Web lifecycle should support start -> status -> stop via tracked PID file."""
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        web_bin = _make_http_mock(tmpdir, port)
        run_dir = Path(tmpdir) / "run"
        web_log = Path(tmpdir) / "web.out"
        pid_file = run_dir / "web-dashboard.pid"

        start_env = _env_for(
            port,
            "web",
            SICHTER_DASHBOARD_WEB_BIN=str(web_bin),
            SICHTER_RUN_DIR=str(run_dir),
            SICHTER_WEB_STDOUT=str(web_log),
            SICHTER_WEB_STDERR=str(web_log),
        )
        start_result = subprocess.run(
            ["bash", SCRIPT], env=start_env, capture_output=True, text=True, timeout=20
        )
        assert start_result.returncode == 0, start_result.stderr
        assert pid_file.exists(), "Expected PID file after successful web start"

        # Extract PID from metadata (format: pid|started_at|cmd_basename)
        metadata = pid_file.read_text().strip()
        tracked_pid = int(metadata.split("|")[0])

        # Status and stop must use the same WEB_BIN to verify identity
        status_env = _env_for(
            port,
            "web",
            SICHTER_UI_ACTION="status",
            SICHTER_RUN_DIR=str(run_dir),
            SICHTER_DASHBOARD_WEB_BIN=str(web_bin),
        )
        status_result = subprocess.run(
            ["bash", SCRIPT], env=status_env, capture_output=True, text=True, timeout=8
        )
        assert status_result.returncode == 0, f"Status failed: {status_result.stderr}"
        assert "is running" in status_result.stdout

        stop_env = _env_for(
            port,
            "web",
            SICHTER_UI_ACTION="stop",
            SICHTER_RUN_DIR=str(run_dir),
            SICHTER_DASHBOARD_WEB_BIN=str(web_bin),
        )
        stop_result = subprocess.run(
            ["bash", SCRIPT], env=stop_env, capture_output=True, text=True, timeout=8
        )
        assert stop_result.returncode == 0, stop_result.stderr
        assert not pid_file.exists(), "Expected PID file removal after stop"

        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(tracked_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            assert False, f"Expected tracked PID {tracked_pid} to be terminated"


def test_integration_web_status_unknown_listener_returns_two():
    """Status should distinguish unknown listeners from a clean stopped state."""
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        foreign_bin = _make_http_mock(tmpdir, port)
        foreign_proc = subprocess.Popen([str(foreign_bin)])
        try:
            _wait_until_listening(port)
            env = _env_for(
                port,
                "web",
                SICHTER_UI_ACTION="status",
                SICHTER_RUN_DIR=str(Path(tmpdir) / "run"),
            )
            result = subprocess.run(
                ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=8
            )

            assert result.returncode == 2
            assert "unknown listener" in result.stdout.lower()
        finally:
            foreign_proc.terminate()
            foreign_proc.wait(timeout=5)


def test_integration_web_status_removes_stale_pid_file_for_non_listener_process():
    """Status should log detached ownership and remove stale PID file."""
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        pid_file = run_dir / "web-dashboard.pid"

        sleeper = subprocess.Popen(["bash", "-lc", "exec sleep 30"])
        try:
            # Write metadata claiming to be uvicorn-app, but process is actually sleep
            import time
            started_at = str(int(time.time()))
            pid_file.write_text(f"{sleeper.pid}|{started_at}|uvicorn-app\n", encoding="utf-8")

            env = _env_for(
                port,
                "web",
                SICHTER_UI_ACTION="status",
                SICHTER_RUN_DIR=str(run_dir),
            )
            result = subprocess.run(
                ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=8
            )

            # Process is alive but command doesn't match, so identity verification fails
            # Status should report "not running" and remove stale PID file
            assert result.returncode == 1, f"Expected exit 1, got {result.returncode}: {result.stdout}"
            assert "not running" in result.stdout.lower()
            assert not pid_file.exists(), "Expected stale PID file to be removed"
        finally:
            sleeper.terminate()
            sleeper.wait(timeout=5)


def test_integration_web_mode_without_lsof_fails_clearly():
    """Web lifecycle must fail clearly when lsof is unavailable."""
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        path_dir = Path(tmpdir) / "bin"
        path_dir.mkdir(parents=True, exist_ok=True)
        env = _env_for(
            port,
            "web",
            PATH=str(path_dir),
        )
        result = subprocess.run(
            ["/bin/bash", SCRIPT], env=env, capture_output=True, text=True, timeout=8
        )

    assert result.returncode != 0
    assert "lsof is required for web dashboard port checks" in result.stderr


def test_integration_web_status_rejects_reused_pid_without_matching_cmd():
    """Status should reject a stale PID file if the process no longer runs the web binary."""
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        run_dir = Path(tmpdir) / "run"
        run_dir.mkdir(parents=True, exist_ok=True)
        pid_file = run_dir / "web-dashboard.pid"
        
        # Start a sleep process (not the web binary)
        sleeper = subprocess.Popen(["bash", "-lc", "exec sleep 30"])
        try:
            # Write a fake PID file with metadata claiming it's uvicorn-app, but pointing to sleep
            import time
            started_at = str(int(time.time()))
            pid_file.write_text(f"{sleeper.pid}|{started_at}|uvicorn-app\n", encoding="utf-8")
            
            env = _env_for(
                port,
                "web",
                SICHTER_UI_ACTION="status",
                SICHTER_RUN_DIR=str(run_dir),
            )
            result = subprocess.run(
                ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=8
            )
            
            # Status should reject the reused PID (cmd doesn't match) and report not running
            assert result.returncode == 1
            assert "not running" in result.stdout.lower()
            assert not pid_file.exists(), "Expected stale PID file to be removed"
        finally:
            sleeper.terminate()
            sleeper.wait(timeout=5)


def test_integration_web_status_rejects_stale_started_at_for_matching_cmd():
    """Status must reject tracked ownership when started_at metadata does not match live process age."""
    port = _find_free_port()
    with tempfile.TemporaryDirectory() as tmpdir:
        web_bin = _make_http_mock(tmpdir, port)
        run_dir = Path(tmpdir) / "run"
        web_log = Path(tmpdir) / "web.out"
        pid_file = run_dir / "web-dashboard.pid"

        start_env = _env_for(
            port,
            "web",
            SICHTER_DASHBOARD_WEB_BIN=str(web_bin),
            SICHTER_RUN_DIR=str(run_dir),
            SICHTER_WEB_STDOUT=str(web_log),
            SICHTER_WEB_STDERR=str(web_log),
        )
        start_result = subprocess.run(
            ["bash", SCRIPT], env=start_env, capture_output=True, text=True, timeout=20
        )
        assert start_result.returncode == 0, start_result.stderr
        assert pid_file.exists(), "Expected PID file after successful web start"

        metadata = pid_file.read_text(encoding="utf-8").strip()
        tracked_pid = int(metadata.split("|")[0])

        # Tamper started_at to be far older than the live process runtime.
        fake_started_at = str(int(time.time()) - 3600)
        pid_file.write_text(f"{tracked_pid}|{fake_started_at}|{web_bin.name}\n", encoding="utf-8")

        status_env = _env_for(
            port,
            "web",
            SICHTER_UI_ACTION="status",
            SICHTER_RUN_DIR=str(run_dir),
            SICHTER_DASHBOARD_WEB_BIN=str(web_bin),
        )
        status_result = subprocess.run(
            ["bash", SCRIPT], env=status_env, capture_output=True, text=True, timeout=8
        )

        # Identity must fail; listener is still there, so it is unknown (exit 2).
        assert status_result.returncode == 2
        assert "unknown listener" in status_result.stdout.lower()
        assert not pid_file.exists(), "Expected stale PID file to be removed"

        # Cleanup the still-running mock web process.
        os.kill(tracked_pid, signal.SIGTERM)
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                os.kill(tracked_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)

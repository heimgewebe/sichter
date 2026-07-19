from pathlib import Path
import os
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "bin" / "sichter-pr-sweep"


def _run(tmp_path: Path, *args: str, mode: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    if mode is None:
        env.pop("MODE", None)
    else:
        env["MODE"] = mode
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _assert_no_runtime_state(tmp_path: Path) -> None:
    assert not (tmp_path / "home" / "sichter").exists()
    assert not (tmp_path / "state" / "sichter").exists()


def test_help_is_read_only(tmp_path: Path) -> None:
    result = _run(tmp_path, "--help")
    assert result.returncode == 0
    assert "Usage: sichter-pr-sweep" in result.stdout
    assert result.stderr == ""
    _assert_no_runtime_state(tmp_path)


def test_unknown_argument_fails_closed_before_runtime_setup(tmp_path: Path) -> None:
    result = _run(tmp_path, "--definitely-unknown")
    assert result.returncode == 64
    assert result.stdout == ""
    assert "unbekanntes Argument" in result.stderr
    assert "Usage: sichter-pr-sweep" in result.stderr
    _assert_no_runtime_state(tmp_path)


def test_multiple_arguments_fail_closed(tmp_path: Path) -> None:
    result = _run(tmp_path, "--changed", "--all")
    assert result.returncode == 64
    assert "zu viele Argumente" in result.stderr
    _assert_no_runtime_state(tmp_path)


def test_invalid_mode_environment_fails_closed(tmp_path: Path) -> None:
    result = _run(tmp_path, mode="dangerous-default")
    assert result.returncode == 64
    assert "ungültiger MODE-Wert" in result.stderr
    _assert_no_runtime_state(tmp_path)


def test_version_advertises_argument_guard(tmp_path: Path) -> None:
    result = _run(tmp_path, "--version")
    assert result.returncode == 0
    assert "unknown-args-fail-closed" in result.stdout
    assert "dry-run-no-clone-branch-commit-push-pr" in result.stdout
    assert result.stderr == ""
    _assert_no_runtime_state(tmp_path)


def test_invalid_dry_run_environment_fails_closed(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["HOME"] = str(tmp_path / "home")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    env["SICHTER_DRY_RUN"] = "maybe-mutating"
    result = subprocess.run(
        [str(SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 64
    assert result.stdout == ""
    assert "ungültiger SICHTER_DRY_RUN-Wert" in result.stderr
    _assert_no_runtime_state(tmp_path)

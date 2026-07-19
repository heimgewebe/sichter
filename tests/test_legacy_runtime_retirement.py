from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
LEGACY_UNITS = (
    "sichter-api.service",
    "sichter-worker.service",
    "sichter-ws-selftest.timer",
)


def _assert_default_runtime_contract(script_name: str) -> None:
    source = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
    guard = 'if [ "${SICHTER_ENABLE_LEGACY_QUEUE:-0}" = "1" ]; then'
    assert guard in source
    guard_offset = source.index(guard)
    assert source.count("enable --now sichter-autoreview.timer") == 1

    for unit in LEGACY_UNITS:
        enable = f"enable --now {unit}"
        disable = f"disable --now {unit}"
        assert source.count(enable) == 1
        assert source.index(enable) > guard_offset
        assert source.count(disable) == 1
        assert source.index(disable) > source.index("else", guard_offset)


def test_install_defaults_to_direct_review_sweep() -> None:
    _assert_default_runtime_contract("install.sh")


def test_bootstrap_defaults_to_direct_review_sweep() -> None:
    _assert_default_runtime_contract("bootstrap.sh")


def test_operator_docs_mark_legacy_plane_as_opt_in() -> None:
    for relative in ("README.md", "docs/OPERATIONS.md", "docs/GETTING_STARTED.md"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert "SICHTER_ENABLE_LEGACY_QUEUE=1" in source
        assert "sichter-autoreview.timer" in source


def test_incompatible_job_queue_clients_fail_closed() -> None:
    for relative in ("bin/hauski-watch", "bin/hauski-work"):
        script = ROOT / relative
        source = script.read_text(encoding="utf-8")
        assert "$HOME/sichter/queue" not in source
        assert ".job" in source
        assert "bin/sichter-pr-sweep --all" in source
        assert "exit 78" in source

        result = subprocess.run(
            [str(script)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert result.returncode == 78
        assert result.stdout == ""
        assert "inkompatible .job-Queuepfad ist stillgelegt" in result.stderr
        assert "bin/sichter-pr-sweep --all" in result.stderr

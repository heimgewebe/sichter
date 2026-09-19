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


def test_hauski_named_runtime_surface_is_removed() -> None:
    assert not list((ROOT / "bin").glob("hauski-*"))
    assert not list((ROOT / "systemd").glob("hauski-*"))
    assert not (ROOT / "env.sh").exists()
    assert not (ROOT / "autostart.env").exists()
    assert not (ROOT / "bin/pr-review").exists()
    assert not (ROOT / "bin/pr-policy-wrapper").exists()


def test_neutral_status_and_notify_entrypoints_exist() -> None:
    for relative in ("bin/sichter-status", "bin/sichter-notify"):
        path = ROOT / relative
        assert path.is_file()
        assert path.stat().st_mode & 0o111

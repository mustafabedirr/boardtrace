from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts.validate_host_hardening import HostHardeningError, validate

ROOT = Path(__file__).resolve().parents[2] / "infrastructure/production/ssh"


def copy_policy(tmp_path: Path) -> Path:
    target = tmp_path / "ssh"
    shutil.copytree(ROOT, target)
    return target


def replace(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")


def test_repository_host_hardening_passes() -> None:
    validate(ROOT)


def test_bootstrap_and_finalization_preserve_safe_two_session_sequence() -> None:
    installer = (ROOT / "install-host-hardening.sh").read_text(encoding="utf-8")
    finalizer = (ROOT / "finalize-host-hardening.sh").read_text(encoding="utf-8")
    rollback = (ROOT / "rollback-host-hardening.sh").read_text(encoding="utf-8")
    assert "delete allow 22" not in installer
    assert "boardtrace-second-session-verified" in finalizer
    assert "state established" in finalizer
    assert "delete allow 22" in finalizer
    assert "allow 22/tcp" in rollback


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("PasswordAuthentication no", "PasswordAuthentication yes", "passwordauthentication"),
        ("PermitRootLogin no", "PermitRootLogin yes", "permitrootlogin"),
        ("Port 48227", "Port 22", "port"),
        ("PubkeyAuthentication yes", "PubkeyAuthentication no", "pubkeyauthentication"),
    ],
)
def test_unsafe_ssh_values_fail(tmp_path: Path, old: str, new: str, match: str) -> None:
    root = copy_policy(tmp_path)
    replace(root / "sshd_config.d/60-boardtrace-production.conf", old, new)
    with pytest.raises(HostHardeningError, match=match):
        validate(root)


def test_absent_fail2ban_fails(tmp_path: Path) -> None:
    root = copy_policy(tmp_path)
    (root / "fail2ban/boardtrace-sshd.local").unlink()
    with pytest.raises(OSError):
        validate(root)


def test_unsafe_bypass_fails(tmp_path: Path) -> None:
    root = copy_policy(tmp_path)
    path = root / "install-host-hardening.sh"
    path.write_text(path.read_text(encoding="utf-8") + "\n--skip-validation\n", encoding="utf-8")
    with pytest.raises(HostHardeningError, match="bypass"):
        validate(root)

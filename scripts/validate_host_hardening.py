"""Static fail-closed validation for BoardTrace production host-hardening artifacts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class HostHardeningError(ValueError):
    pass


def _directives(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(" ")
        if not separator or key.lower() in values:
            raise HostHardeningError(f"invalid or duplicate SSH directive: {key}")
        values[key.lower()] = value.strip().lower()
    return values


def validate(root: Path) -> None:
    ssh = _directives(root / "sshd_config.d/60-boardtrace-production.conf")
    required = {
        "port": "48227",
        "permitrootlogin": "no",
        "passwordauthentication": "no",
        "kbdinteractiveauthentication": "no",
        "pubkeyauthentication": "yes",
        "permitemptypasswords": "no",
        "maxauthtries": "3",
        "x11forwarding": "no",
        "allowagentforwarding": "no",
        "allowtcpforwarding": "local",
        "permittunnel": "no",
    }
    for key, expected in required.items():
        if ssh.get(key) != expected:
            raise HostHardeningError(f"unsafe SSH setting: {key}")
    if "22" in {value for key, value in ssh.items() if key == "port"}:
        raise HostHardeningError("port 22 must not be configured")

    bootstrap_text = (root / "sshd_config.d/59-boardtrace-bootstrap.conf").read_text(
        encoding="utf-8"
    )
    for required_port in ("Port 22", "Port 48227"):
        if required_port not in bootstrap_text:
            raise HostHardeningError("bootstrap policy must preserve both SSH ports")

    jail = (root / "fail2ban/boardtrace-sshd.local").read_text(encoding="utf-8")
    for pattern in (r"(?m)^enabled\s*=\s*true$", r"(?m)^port\s*=\s*48227$"):
        if re.search(pattern, jail) is None:
            raise HostHardeningError("Fail2ban SSH policy is incomplete")

    installer = (root / "install-host-hardening.sh").read_text(encoding="utf-8")
    required_guards = ("authorized_keys", "sshd -t", "sshd -T", "visudo -cf")
    if any(guard not in installer for guard in required_guards):
        raise HostHardeningError("installer lacks a mandatory pre-reload guard")
    forbidden = ("--force-unsafe", "--skip-validation", "PasswordAuthentication yes")
    if any(marker in installer for marker in forbidden):
        raise HostHardeningError("unsafe host-hardening bypass is present")
    if "delete allow 22" in installer:
        raise HostHardeningError("bootstrap installer must not close port 22")

    finalizer = (root / "finalize-host-hardening.sh").read_text(encoding="utf-8")
    for guard in (
        "boardtrace-second-session-verified",
        "state established",
        "sshd -t",
        "sshd -T",
        "delete allow 22",
    ):
        if guard not in finalizer:
            raise HostHardeningError("finalizer lacks second-session or port-closure guard")

    rollback = (root / "rollback-host-hardening.sh").read_text(encoding="utf-8")
    if "59-boardtrace-bootstrap.conf" not in rollback or "allow 22/tcp" not in rollback:
        raise HostHardeningError("rollback does not restore safe key-only bootstrap access")

    recovery = (root / "boardtrace-recovery").read_text(encoding="utf-8")
    for prohibited in ("docker compose build", "docker compose push", "docker login", "bash -c"):
        if prohibited in recovery:
            raise HostHardeningError("secondary recovery wrapper exceeds approved scope")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path("infrastructure/production/ssh"))
    args = parser.parse_args(argv)
    try:
        validate(args.root)
    except (OSError, HostHardeningError) as error:
        print(f"host hardening validation failed: {error}", file=sys.stderr)
        return 1
    print("host hardening validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Single manual-deployment entry gate; this script performs no deployment."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MAPPING = "docs/production/decisions/boardtrace-production-decision-package.v1.0-pilot.json"


def main() -> int:
    from scripts.validate_host_hardening import main as validate_host
    from scripts.validate_production_decisions import main as validate_decisions
    from scripts.validate_production_environment import main as validate_environment
    from scripts.validate_provisioning_manifest import main as validate_manifest

    gates: tuple[tuple[str, Callable[[], int]], ...] = (
        ("decision package", lambda: validate_decisions(["--require-decision-complete", MAPPING])),
        ("host hardening artifacts", lambda: validate_host([])),
        ("provisioning manifest", lambda: validate_manifest([])),
        ("production environment", lambda: validate_environment([])),
    )
    for name, gate in gates:
        if gate() != 0:
            print(f"deployment preflight blocked at: {name}", file=sys.stderr)
            return 1
    print("repository preflight passed; external verification is still required")
    return 0


if __name__ == "__main__":
    sys.exit(main())

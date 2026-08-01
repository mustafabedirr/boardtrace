"""Assert that authenticated API traffic fails closed while Redis is unavailable."""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def validate() -> None:
    request = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/health/ready",
        headers={"Authorization": "Bearer production-like-probe", "Host": "api"},
    )
    try:
        urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read())
        assert exc.code == 503
        assert exc.headers.get("Retry-After") == "60"
        assert payload["error"]["code"] == "rate_limit_state_unavailable"
        return
    raise AssertionError("authenticated request did not fail closed while Redis was unavailable")


if __name__ == "__main__":
    validate()
    print("Redis-unavailable fail-closed validation passed")

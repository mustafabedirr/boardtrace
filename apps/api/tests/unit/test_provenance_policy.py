from __future__ import annotations

import pytest

from boardtrace_api.provenance import (
    ProvenanceValidationError,
    canonical_source_checksum,
    validate_source,
)


def test_supported_source_checksum_is_stable() -> None:
    first = canonical_source_checksum(" LICHESS ", "AbCd1234", ["E2E4", "e7e5"])
    second = canonical_source_checksum("lichess", "AbCd1234", ["e2e4", "e7e5"])
    assert first == second
    assert len(first) == 64


def test_supported_extension_source_is_accepted() -> None:
    checksum = canonical_source_checksum("lichess", "AbCd1234", ["e2e4"])
    assert (
        validate_source(
            platform="lichess",
            source_game_id="AbCd1234",
            acquisition_method="browser_extension",
            moves=["e2e4"],
            supplied_checksum=checksum,
            require_checksum=True,
        )
        == checksum
    )


@pytest.mark.parametrize(
    ("platform", "method", "checksum", "match"),
    [
        ("manual-pgn", "browser_extension", None, "unsupported source"),
        ("lichess", "manual_pgn", None, "acquisition"),
        ("lichess", "browser_extension", "0" * 64, "mismatch"),
        ("lichess", "browser_extension", None, "required"),
    ],
)
def test_unsupported_mismatched_or_unverified_source_fails_closed(
    platform: str, method: str, checksum: str | None, match: str
) -> None:
    with pytest.raises(ProvenanceValidationError, match=match):
        validate_source(
            platform=platform,
            source_game_id="AbCd1234",
            acquisition_method=method,
            moves=["e2e4"],
            supplied_checksum=checksum,
            require_checksum=True,
        )

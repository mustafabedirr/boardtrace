"""Version-controlled, fail-closed completed-game provenance policy."""

from __future__ import annotations

from hashlib import sha256
from json import dumps

SUPPORTED_SOURCE_PLATFORMS = frozenset({"lichess"})
ACQUISITION_METHOD = "browser_extension"


class ProvenanceValidationError(ValueError):
    pass


def canonical_source_checksum(platform: str, source_game_id: str, moves: list[str]) -> str:
    canonical = dumps(
        [
            platform.strip().lower(),
            source_game_id.strip(),
            [move.strip().lower() for move in moves],
        ],
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def validate_source(
    *,
    platform: str,
    source_game_id: str,
    acquisition_method: str,
    moves: list[str],
    supplied_checksum: str | None,
    require_checksum: bool,
) -> str:
    normalized_platform = platform.strip().lower()
    if normalized_platform not in SUPPORTED_SOURCE_PLATFORMS:
        raise ProvenanceValidationError("unsupported source platform")
    if acquisition_method != ACQUISITION_METHOD:
        raise ProvenanceValidationError("unsupported acquisition method")
    if not source_game_id.strip():
        raise ProvenanceValidationError("source game identity is missing")
    calculated = canonical_source_checksum(normalized_platform, source_game_id, moves)
    if require_checksum and supplied_checksum is None:
        raise ProvenanceValidationError("source checksum is required")
    if supplied_checksum is not None and supplied_checksum != calculated:
        raise ProvenanceValidationError("source checksum mismatch")
    return calculated

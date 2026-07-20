from dataclasses import dataclass
from datetime import timedelta
from secrets import randbelow
from typing import Protocol


class JitterSource(Protocol):
    def seconds(self, upper_bound: int) -> int: ...


@dataclass(frozen=True)
class ZeroJitter:
    def seconds(self, upper_bound: int) -> int:
        return 0


@dataclass(frozen=True)
class SecureJitter:
    def seconds(self, upper_bound: int) -> int:
        return 0 if upper_bound == 0 else randbelow(upper_bound + 1)


@dataclass(frozen=True)
class RetryPolicy:
    base_delay_seconds: int
    max_delay_seconds: int
    max_jitter_seconds: int

    def __post_init__(self) -> None:
        if self.base_delay_seconds < 1 or self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("retry delays must be positive and ordered")
        if self.max_jitter_seconds < 0:
            raise ValueError("retry jitter must not be negative")

    def delay_for_attempt(self, attempt: int, jitter: JitterSource) -> timedelta:
        if attempt < 1:
            raise ValueError("attempt must be positive")
        exponential = self.base_delay_seconds * (2 ** min(attempt - 1, 30))
        delay = min(self.max_delay_seconds, exponential)
        bounded_jitter = min(jitter.seconds(self.max_jitter_seconds), self.max_jitter_seconds)
        if bounded_jitter < 0:
            raise ValueError("jitter source returned a negative delay")
        return timedelta(seconds=delay + bounded_jitter)

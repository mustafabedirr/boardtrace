from enum import StrEnum


class GameStatus(StrEnum):
    CREATED = "CREATED"
    CAPTURING = "CAPTURING"
    FINISH_PENDING = "FINISH_PENDING"
    FINISHED = "FINISHED"
    DEEP_ANALYSIS_RUNNING = "DEEP_ANALYSIS_RUNNING"
    ANALYSIS_AVAILABLE = "ANALYSIS_AVAILABLE"
    FAILED = "FAILED"


class PlayerColor(StrEnum):
    WHITE = "WHITE"
    BLACK = "BLACK"
    UNKNOWN = "UNKNOWN"


class GameResult(StrEnum):
    WHITE_WIN = "WHITE_WIN"
    BLACK_WIN = "BLACK_WIN"
    DRAW = "DRAW"
    UNKNOWN = "UNKNOWN"


class PositionValidationStatus(StrEnum):
    PENDING = "PENDING"
    VALID = "VALID"
    INVALID = "INVALID"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class AnalysisType(StrEnum):
    FAST = "FAST"
    DEEP = "DEEP"


class AnalysisJobType(StrEnum):
    VISION = "VISION"
    ENGINE_FAST = "ENGINE_FAST"
    ENGINE_DEEP = "ENGINE_DEEP"
    REPORT = "REPORT"


class AnalysisJobStatus(StrEnum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AnalysisOutboxStatus(StrEnum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"


class AnalysisRunStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"

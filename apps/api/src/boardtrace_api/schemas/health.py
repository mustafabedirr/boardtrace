from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    service: str
    version: str


class MinimumHealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    checks: dict[str, str]

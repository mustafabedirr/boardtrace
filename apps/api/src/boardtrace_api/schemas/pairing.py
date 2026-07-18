from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from boardtrace_api.auth.tokens import EXTENSION_SCOPES


class PairingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    extension_id: str = Field(min_length=1, max_length=128)
    scopes: list[str] = Field(min_length=1, max_length=2)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or not set(value) <= EXTENSION_SCOPES:
            raise ValueError("Scopes must be unique and allowlisted")
        return sorted(value)


class PairingCodeResponse(BaseModel):
    code: str = Field(repr=False)
    expires_at: datetime


class PairingExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=32, max_length=256, repr=False)
    extension_id: str = Field(min_length=1, max_length=128)


class ExtensionTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

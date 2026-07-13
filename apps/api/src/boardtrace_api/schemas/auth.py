from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(
        min_length=12,
        max_length=256,
        repr=False,
        json_schema_extra={"writeOnly": True},
    )
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(RegisterRequest):
    display_name: str | None = Field(default=None, exclude=True)


class RefreshTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    refresh_token: str = Field(
        min_length=32,
        max_length=512,
        repr=False,
        json_schema_extra={"writeOnly": True},
    )


class LogoutRequest(RefreshTokenRequest):
    pass


class LogoutResponse(BaseModel):
    success: bool = True


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    is_active: bool
    email_verified: bool
    created_at: datetime


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

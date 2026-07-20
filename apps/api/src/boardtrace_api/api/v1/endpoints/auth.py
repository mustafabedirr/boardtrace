from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.auth.passwords import PasswordService
from boardtrace_api.auth.service import AuthenticationError, AuthenticationService
from boardtrace_api.auth.tokens import TokenError, TokenScopeError, TokenService
from boardtrace_api.core.errors import ApiError
from boardtrace_api.db.dependencies import get_db_session
from boardtrace_api.models import User
from boardtrace_api.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    LogoutResponse,
    RefreshTokenRequest,
    RegisterRequest,
    TokenPairResponse,
    UserResponse,
)
from boardtrace_api.schemas.errors import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False, bearerFormat="JWT")
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

NO_STORE_HEADERS = {
    "Cache-Control": {
        "description": "Responses containing authentication material must not be cached.",
        "schema": {"type": "string", "const": "no-store"},
    },
    "Pragma": {
        "description": "Legacy cache-control compatibility header.",
        "schema": {"type": "string", "const": "no-cache"},
    },
}


def get_auth_service(request: Request, session: SessionDep) -> AuthenticationService:
    return AuthenticationService(
        session,
        PasswordService(),
        TokenService(request.app.state.settings),
    )


AuthServiceDep = Annotated[AuthenticationService, Depends(get_auth_service)]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


@router.post(
    "/register",
    response_model=TokenPairResponse,
    responses={
        200: {"headers": NO_STORE_HEADERS},
        409: {"model": ErrorResponse, "description": "Email is already registered."},
        422: {"model": ErrorResponse, "description": "Request validation failed."},
    },
)
async def register(
    payload: RegisterRequest,
    response: Response,
    auth: AuthServiceDep,
) -> TokenPairResponse:
    try:
        _, pair = await auth.register(str(payload.email), payload.password, payload.display_name)
        await auth._session.commit()
    except AuthenticationError as error:
        raise ApiError("email_conflict", "Registration could not be completed.", 409) from error
    no_store(response)
    return pair


@router.post(
    "/login",
    response_model=TokenPairResponse,
    responses={
        200: {"headers": NO_STORE_HEADERS},
        401: {"model": ErrorResponse, "description": "Authentication failed."},
        422: {"model": ErrorResponse, "description": "Request validation failed."},
    },
)
async def login(
    payload: LoginRequest,
    response: Response,
    auth: AuthServiceDep,
) -> TokenPairResponse:
    try:
        pair = await auth.login(str(payload.email), payload.password)
        await auth._session.commit()
    except AuthenticationError as error:
        raise ApiError("invalid_credentials", "Authentication failed.", 401) from error
    no_store(response)
    return pair


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    responses={
        200: {"headers": NO_STORE_HEADERS},
        401: {"model": ErrorResponse, "description": "Refresh token is invalid."},
        422: {"model": ErrorResponse, "description": "Request validation failed."},
    },
)
async def refresh(
    payload: RefreshTokenRequest,
    response: Response,
    auth: AuthServiceDep,
) -> TokenPairResponse:
    try:
        pair = await auth.refresh(payload.refresh_token)
        await auth._session.commit()
    except AuthenticationError as error:
        await auth._session.commit()
        raise ApiError("invalid_refresh_token", "Authentication failed.", 401) from error
    no_store(response)
    return pair


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: AuthServiceDep,
) -> User:
    if credentials is None:
        raise ApiError("authentication_required", "Authentication failed.", 401)
    try:
        return await auth.current_user(credentials.credentials)
    except (AuthenticationError, TokenError) as error:
        raise ApiError("authentication_required", "Authentication failed.", 401) from error


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def _get_extension_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: AuthServiceDep,
    required_scope: str,
) -> User:
    if credentials is None:
        raise ApiError("authentication_required", "Authentication failed.", 401)
    try:
        return await auth.extension_user(credentials.credentials, required_scope)
    except TokenScopeError as error:
        raise ApiError("insufficient_scope", "Authorization failed.", 403) from error
    except (AuthenticationError, TokenError) as error:
        raise ApiError("authentication_required", "Authentication failed.", 401) from error


async def get_extension_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: AuthServiceDep,
) -> User:
    """Compatibility dependency; endpoint routes use explicit scope dependencies below."""
    return await _get_extension_user(credentials, auth, "games:ingest")


async def get_extension_ingest_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: AuthServiceDep,
) -> User:
    return await _get_extension_user(credentials, auth, "games:ingest")


async def get_extension_status_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: AuthServiceDep,
) -> User:
    return await _get_extension_user(credentials, auth, "games:read-status")


async def get_analysis_status_reader(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    auth: AuthServiceDep,
) -> User:
    if credentials is None:
        raise ApiError("authentication_required", "Authentication failed.", 401)
    try:
        return await auth.current_user(credentials.credentials)
    except (AuthenticationError, TokenError):
        try:
            return await auth.extension_user(credentials.credentials, "games:read-status")
        except TokenScopeError as error:
            raise ApiError("insufficient_scope", "Authorization failed.", 403) from error
        except (AuthenticationError, TokenError) as error:
            raise ApiError("authentication_required", "Authentication failed.", 401) from error


ExtensionIngestUserDep = Annotated[User, Depends(get_extension_ingest_user)]
ExtensionStatusUserDep = Annotated[User, Depends(get_extension_status_user)]
AnalysisStatusReaderDep = Annotated[User, Depends(get_analysis_status_reader)]
ExtensionUserDep = Annotated[User, Depends(get_extension_user)]


@router.post(
    "/logout",
    response_model=LogoutResponse,
    responses={
        200: {"headers": NO_STORE_HEADERS},
        422: {"model": ErrorResponse, "description": "Request validation failed."},
    },
)
async def logout(
    payload: LogoutRequest,
    response: Response,
    auth: AuthServiceDep,
) -> LogoutResponse:
    await auth.revoke(payload.refresh_token)
    await auth._session.commit()
    no_store(response)
    return LogoutResponse()


@router.post(
    "/logout-all",
    response_model=LogoutResponse,
    responses={
        200: {"headers": NO_STORE_HEADERS},
        401: {"model": ErrorResponse, "description": "Bearer authentication failed."},
    },
)
async def logout_all(
    response: Response,
    user: CurrentUserDep,
    auth: AuthServiceDep,
) -> LogoutResponse:
    await auth.revoke_all(user.id)
    await auth._session.commit()
    no_store(response)
    return LogoutResponse()


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorResponse, "description": "Bearer authentication failed."}},
)
async def me(user: CurrentUserDep) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        email_verified=user.email_verified,
        created_at=user.created_at,
    )

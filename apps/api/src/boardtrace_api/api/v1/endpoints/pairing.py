from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from boardtrace_api.api.v1.endpoints.auth import CurrentUserDep
from boardtrace_api.core.errors import ApiError
from boardtrace_api.db.dependencies import get_db_session
from boardtrace_api.schemas.errors import ErrorResponse
from boardtrace_api.schemas.pairing import (
    ExtensionTokenResponse,
    PairingCodeResponse,
    PairingCreateRequest,
    PairingExchangeRequest,
)
from boardtrace_api.services.pairing import PairingError, PairingService

router = APIRouter(prefix="/extension-pairings", tags=["extension-pairing"])
SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("", response_model=PairingCodeResponse, responses={401: {"model": ErrorResponse}})
async def create_pairing(
    response: Response,
    request: Request,
    payload: PairingCreateRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> PairingCodeResponse:
    code, expires_at = await PairingService(session, request.app.state.settings).create(
        user.id, payload.extension_id, tuple(payload.scopes)
    )
    await session.commit()
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return PairingCodeResponse(code=code, expires_at=expires_at)


@router.post(
    "/exchange", response_model=ExtensionTokenResponse, responses={401: {"model": ErrorResponse}}
)
async def exchange_pairing(
    payload: PairingExchangeRequest, response: Response, request: Request, session: SessionDep
) -> ExtensionTokenResponse:
    service = PairingService(session, request.app.state.settings)
    try:
        token = await service.exchange(payload.code, payload.extension_id)
        await session.commit()
    except PairingError as error:
        await session.rollback()
        raise ApiError("invalid_pairing_code", "Pairing could not be completed.", 401) from error
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return ExtensionTokenResponse(
        access_token=token,
        expires_in=request.app.state.settings.extension_access_token_lifetime_seconds,
    )

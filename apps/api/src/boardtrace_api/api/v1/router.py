from fastapi import APIRouter

from boardtrace_api.api.v1.endpoints.auth import router as auth_router
from boardtrace_api.api.v1.endpoints.health import router as health_router
from boardtrace_api.api.v1.endpoints.ingestion import router as ingestion_router
from boardtrace_api.api.v1.endpoints.pairing import router as pairing_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(health_router)
router.include_router(ingestion_router)
router.include_router(pairing_router)

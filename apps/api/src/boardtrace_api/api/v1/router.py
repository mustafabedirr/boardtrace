from fastapi import APIRouter

from boardtrace_api.api.v1.endpoints.health import router as health_router

router = APIRouter()
router.include_router(health_router)

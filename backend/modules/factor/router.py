from fastapi import APIRouter

from .endpoints import factor_router

router = APIRouter(prefix="/admin/factor")

router.include_router(factor_router)

__all__ = ["router"]

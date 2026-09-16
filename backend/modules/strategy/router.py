from fastapi import APIRouter

from .endpoints import strategy_router, position_router, stats_router

router = APIRouter(prefix="/admin/strategy")

router.include_router(position_router)
router.include_router(stats_router)
router.include_router(strategy_router)

__all__ = ["router"]

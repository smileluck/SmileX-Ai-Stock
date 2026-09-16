from fastapi import APIRouter

from .endpoints import backtest_router

router = APIRouter(prefix="/admin/backtest")

router.include_router(backtest_router)

__all__ = ["router"]

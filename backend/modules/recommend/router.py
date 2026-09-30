from fastapi import APIRouter

from .endpoints import recommend_router

router = APIRouter(prefix="/admin/recommend")

router.include_router(recommend_router)

__all__ = ["router"]

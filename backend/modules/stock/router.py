#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
A股行情模块路由
"""
from fastapi import APIRouter

from .endpoints import (
    market_router,
    board_router,
    limit_up_router,
    stock_hot_router,
    block_trade_router,
    rotation_router,
)

router = APIRouter(prefix="/admin/stock")

router.include_router(market_router)
router.include_router(board_router)
router.include_router(limit_up_router)
router.include_router(stock_hot_router)
router.include_router(block_trade_router)
router.include_router(rotation_router)

__all__ = ["router"]

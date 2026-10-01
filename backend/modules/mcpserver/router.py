#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import APIRouter

from .endpoints.mcp_server import mcp_server_router

router = APIRouter(prefix="/admin/mcp-server")

router.include_router(mcp_server_router)

__all__ = ["router"]

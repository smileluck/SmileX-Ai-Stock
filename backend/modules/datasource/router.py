#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import APIRouter

from .endpoints.datasource import datasource_router

router = APIRouter(prefix="/admin/datasource")

router.include_router(datasource_router)

__all__ = ["router"]

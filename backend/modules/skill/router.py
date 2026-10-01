#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from fastapi import APIRouter

from .endpoints.skill import skill_router

router = APIRouter(prefix="/admin/skill")

router.include_router(skill_router)

__all__ = ["router"]

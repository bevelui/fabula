# -*- coding: utf-8 -*-
"""Shared FastAPI dependencies.

Auth is a placeholder for the scaffold: the caller identifies via an X-User-Id
header (defaults to 'demo'). Phase 2 replaces this with real hosted auth
(Supabase/Clerk) that yields the same user id — routers don't change.
"""
from fastapi import Header, Query
from typing import Optional


def current_user(x_user_id: Optional[str] = Header(default=None),
                 uid: Optional[str] = Query(default=None)) -> str:
    # fetch() calls send the header; plain download links send ?uid=… instead
    return x_user_id or uid or "demo"

# -*- coding: utf-8 -*-
"""Shared FastAPI dependencies.

Auth is a placeholder for the scaffold: the caller identifies via an X-User-Id
header (defaults to 'demo'). Phase 2 replaces this with real hosted auth
(Supabase/Clerk) that yields the same user id — routers don't change.
"""
from fastapi import Header


def current_user(x_user_id: str = Header(default="demo")) -> str:
    return x_user_id

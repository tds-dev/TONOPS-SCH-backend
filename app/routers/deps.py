"""Shared request dependencies."""
from fastapi import Header

from app.core.config import get_settings


def current_user(x_user_email: str | None = Header(default=None)) -> str:
    """Who is acting. No authentication yet: an optional X-User-Email header,
    else the configured default user. Replaced by Firebase auth later."""
    return x_user_email or get_settings().default_user

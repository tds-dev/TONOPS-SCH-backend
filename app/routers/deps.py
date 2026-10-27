"""リクエスト共通の依存関係。"""
from fastapi import Header

from app.core.config import get_settings


def current_user(x_user_email: str | None = Header(default=None)) -> str:
    """操作者。認証は未実装: 任意の X-User-Email ヘッダー、なければ
    設定の既定ユーザー。後で Firebase 認証に置き換える。"""
    return x_user_email or get_settings().default_user

"""Dependências compartilhadas do FastAPI."""
from typing import Optional
from fastapi import Header
from app.models.base import get_db


def get_user_id(x_user_id: Optional[int] = Header(default=None, alias="x-user-id")) -> Optional[int]:
    """Lê o usuário ativo do header X-User-Id enviado pelo frontend."""
    return x_user_id


__all__ = ["get_db", "get_user_id"]

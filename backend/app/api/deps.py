"""Dependências compartilhadas do FastAPI."""
from typing import Optional
from fastapi import Header
from sqlalchemy.orm import Session
from app.models.base import get_db


def get_user_id(x_user_id: Optional[int] = Header(default=None, alias="x-user-id")) -> Optional[int]:
    """Lê o usuário ativo do header X-User-Id enviado pelo frontend."""
    return x_user_id


def get_portfolio_ativo(user, db: Session):
    """
    Retorna o portfólio ativo do usuário.
    Respeita user.portfolio_ativo_id se definido e válido.
    Fallback: primeiro portfolio do usuário (comportamento legado).
    """
    from app.models import Portfolio
    if user.portfolio_ativo_id:
        p = db.query(Portfolio).filter(
            Portfolio.id == user.portfolio_ativo_id,
            Portfolio.user_id == user.id,
        ).first()
        if p:
            return p
    return db.query(Portfolio).filter(Portfolio.user_id == user.id).first()


__all__ = ["get_db", "get_user_id", "get_portfolio_ativo"]

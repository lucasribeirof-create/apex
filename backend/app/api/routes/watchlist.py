"""Rota de Watchlist — gestão de ativos monitorados."""
import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id, get_portfolio_ativo
from app.models import User, Portfolio
from app.models.watchlist import Watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])
logger = logging.getLogger(__name__)


class WatchlistCreate(BaseModel):
    ticker: str
    nome: Optional[str] = None
    setor: Optional[str] = None
    score: float = 0.0
    source_motor: str = "alpha"
    trigger_tipo: Optional[str] = None
    trigger_valor: Optional[float] = None
    trigger_descricao: Optional[str] = None


@router.get("")
async def listar_watchlist(
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Lista todos os itens ativos na watchlist."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    items = db.query(Watchlist).filter(
        Watchlist.portfolio_id == portfolio.id,
        Watchlist.ativa == True,
    ).order_by(Watchlist.score.desc()).all()

    return [
        {
            "id": w.id,
            "ticker": w.ticker,
            "nome": w.nome,
            "setor": w.setor,
            "score": w.score,
            "source_motor": w.source_motor,
            "trigger_tipo": w.trigger_tipo,
            "trigger_valor": w.trigger_valor,
            "trigger_descricao": w.trigger_descricao,
            "pilares": json.loads(w.pilares_json) if w.pilares_json else None,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        }
        for w in items
    ]


@router.post("")
async def adicionar_watchlist(
    item: WatchlistCreate,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Adiciona um ativo à watchlist."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    # Verifica duplicata
    existing = db.query(Watchlist).filter(
        Watchlist.portfolio_id == portfolio.id,
        Watchlist.ticker == item.ticker.upper(),
        Watchlist.ativa == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"{item.ticker} já está na watchlist")

    w = Watchlist(
        portfolio_id=portfolio.id,
        ticker=item.ticker.upper(),
        nome=item.nome,
        setor=item.setor,
        score=item.score,
        source_motor=item.source_motor,
        trigger_tipo=item.trigger_tipo,
        trigger_valor=item.trigger_valor,
        trigger_descricao=item.trigger_descricao,
    )
    db.add(w)
    db.commit()
    db.refresh(w)

    return {"id": w.id, "ticker": w.ticker, "message": f"{w.ticker} adicionado à watchlist"}


@router.delete("/{item_id}")
async def remover_watchlist(
    item_id: int,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Remove um item da watchlist (soft delete)."""
    w = db.query(Watchlist).filter(Watchlist.id == item_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="Item não encontrado")

    w.ativa = False
    w.motivo_remocao = "Removido pelo usuário"
    db.commit()

    return {"message": f"{w.ticker} removido da watchlist"}

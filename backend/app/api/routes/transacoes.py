"""
Rotas de transações por posição — compras, vendas parciais, DCA, bonificações.
Cada transação recalcula automaticamente PM, quantidade e P&L da posição.
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_user_id, get_portfolio_ativo
from app.models import User, Position
from app.models.transacao import Transacao

router = APIRouter(prefix="/portfolio", tags=["transacoes"])

TIPOS_COMPRA = {"compra", "dca", "bonificacao", "split", "aporte"}
TIPOS_VENDA = {"venda_parcial", "venda_total"}


# ─── Schema ──────────────────────────────────────────────────────────────────

class TransacaoBody(BaseModel):
    tipo: str          # compra | dca | venda_parcial | venda_total | split | bonificacao | amortizacao
    data: str          # ISO 8601 date string, ex: "2025-03-15T00:00:00"
    quantidade: float
    preco: float
    taxas: float = 0.0
    observacao: Optional[str] = None


# ─── Helper: recalcular posição a partir do histórico ────────────────────────

def _recalcular_posicao(db: Session, position: Position) -> None:
    """
    Recalcula PM, quantidade atual, valor investido e data de abertura
    com base em todas as transações registradas para a posição.
    Usa custo médio ponderado (não FIFO).
    """
    transacoes = (
        db.query(Transacao)
        .filter(Transacao.position_id == position.id)
        .order_by(Transacao.data)
        .all()
    )

    if not transacoes:
        return

    qtd_compras = 0.0
    custo_compras = 0.0
    qtd_vendas = 0.0
    data_abertura = None

    for t in transacoes:
        if t.tipo in TIPOS_COMPRA:
            qtd_compras += t.quantidade
            custo_compras += t.quantidade * t.preco
            if data_abertura is None:
                data_abertura = t.data
        elif t.tipo in TIPOS_VENDA:
            qtd_vendas += t.quantidade

    qtd_atual = max(0.0, qtd_compras - qtd_vendas)
    pm = (custo_compras / qtd_compras) if qtd_compras > 0 else position.preco_medio
    valor_investido = qtd_atual * pm

    position.quantidade = qtd_atual
    position.preco_medio = pm
    position.valor_investido = valor_investido

    if data_abertura:
        position.data_abertura = data_abertura

    if qtd_atual == 0 and qtd_vendas >= qtd_compras:
        position.ativa = False

    # Atualiza valor atual e P&L se tiver preço atual
    preco_ref = position.preco_atual or pm
    if preco_ref and pm > 0 and qtd_atual > 0:
        position.valor_atual = qtd_atual * preco_ref
        position.pl_reais = position.valor_atual - valor_investido
        position.pl_percentual = ((preco_ref / pm) - 1) * 100


# ─── GET /portfolio/posicoes/{id}/transacoes ────────────────────────────────

@router.get("/posicoes/{position_id}/transacoes")
def listar_transacoes(
    position_id: int,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    position = db.query(Position).filter(
        Position.id == position_id,
        Position.portfolio_id == portfolio.id,
    ).first()
    if not position:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    transacoes = (
        db.query(Transacao)
        .filter(Transacao.position_id == position_id)
        .order_by(Transacao.data)
        .all()
    )

    return [
        {
            "id": t.id,
            "tipo": t.tipo,
            "data": t.data.isoformat() if t.data else None,
            "quantidade": t.quantidade,
            "preco": t.preco,
            "valor_total": t.quantidade * t.preco,
            "taxas": t.taxas or 0.0,
            "observacao": t.observacao,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in transacoes
    ]


# ─── POST /portfolio/posicoes/{id}/transacoes ───────────────────────────────

@router.post("/posicoes/{position_id}/transacoes")
def adicionar_transacao(
    position_id: int,
    body: TransacaoBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    position = db.query(Position).filter(
        Position.id == position_id,
        Position.portfolio_id == portfolio.id,
    ).first()
    if not position:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    tipos_validos = list(TIPOS_COMPRA | TIPOS_VENDA) + ["amortizacao"]
    if body.tipo not in tipos_validos:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {', '.join(tipos_validos)}")

    # Parse da data
    try:
        data_dt = datetime.fromisoformat(body.data.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        data_dt = datetime.utcnow()

    nova = Transacao(
        portfolio_id=portfolio.id,
        position_id=position_id,
        tipo=body.tipo,
        data=data_dt,
        quantidade=body.quantidade,
        preco=body.preco,
        valor_total=body.quantidade * body.preco,
        taxas=body.taxas,
        observacao=body.observacao,
    )
    db.add(nova)
    db.flush()

    # Recalcula posição
    _recalcular_posicao(db, position)
    db.commit()

    return {
        "transacao_id": nova.id,
        "posicao_atualizada": {
            "quantidade": position.quantidade,
            "preco_medio": position.preco_medio,
            "valor_investido": position.valor_investido,
            "data_abertura": position.data_abertura.isoformat() if position.data_abertura else None,
            "ativa": position.ativa,
        },
    }


# ─── DELETE /portfolio/transacoes/{id} ───────────────────────────────────────

@router.delete("/transacoes/{transacao_id}")
def deletar_transacao(
    transacao_id: int,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    transacao = db.query(Transacao).filter(Transacao.id == transacao_id).first()
    if not transacao:
        raise HTTPException(status_code=404, detail="Transação não encontrada")

    # Verifica que a posição pertence ao portfolio ativo do usuário
    portfolio = get_portfolio_ativo(user, db)
    if transacao.portfolio_id != portfolio.id:
        raise HTTPException(status_code=403, detail="Sem permissão")

    position = db.query(Position).filter(Position.id == transacao.position_id).first()
    db.delete(transacao)
    db.flush()

    # Recalcula posição após remover transação
    if position:
        position.ativa = True  # Reativa temporariamente para recalcular
        _recalcular_posicao(db, position)

    db.commit()
    return {"ok": True}

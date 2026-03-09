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
from app.models.trade_journal import TradeJournal

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
    destino: Optional[str] = None  # "caixa" | "saque" (só para vendas)


# ─── Helper: recalcular posição a partir do histórico ────────────────────────

def _recalcular_posicao(db: Session, position: Position) -> None:
    """
    Recalcula PM, quantidade atual, valor investido e data de abertura
    com base em todas as transações registradas para a posição.
    Usa custo médio ponderado (não FIFO).

    Backward compat: se a posição não tem nenhuma transação de compra mas tem
    vendas, cria uma transação sintética "compra" a partir dos dados originais
    da posição para garantir consistência.
    """
    transacoes = (
        db.query(Transacao)
        .filter(Transacao.position_id == position.id)
        .order_by(Transacao.data)
        .all()
    )

    if not transacoes:
        return

    # Backward compat: se só existem vendas (posição criada sem tx de compra),
    # gera a compra sintética a partir dos dados originais da posição.
    tem_compra = any(t.tipo in TIPOS_COMPRA for t in transacoes)
    tem_venda = any(t.tipo in TIPOS_VENDA for t in transacoes)

    if not tem_compra and tem_venda:
        # Reconstrói a quantidade original = qtd_atual_da_pos + total já vendido
        total_vendido = sum(t.quantidade for t in transacoes if t.tipo in TIPOS_VENDA)
        qtd_original = position.quantidade + total_vendido
        pm_original = position.preco_medio or 0.0

        if qtd_original > 0 and pm_original > 0:
            sintetica = Transacao(
                portfolio_id=position.portfolio_id,
                position_id=position.id,
                tipo="compra",
                data=position.data_abertura or position.data_entrada or datetime.utcnow(),
                quantidade=qtd_original,
                preco=pm_original,
                valor_total=qtd_original * pm_original,
                taxas=0.0,
                observacao="Compra sintética (migração automática)",
            )
            db.add(sintetica)
            db.flush()
            # Recarrega transações incluindo a sintética
            transacoes = (
                db.query(Transacao)
                .filter(Transacao.position_id == position.id)
                .order_by(Transacao.data)
                .all()
            )

    qtd_compras = 0.0
    custo_compras = 0.0
    qtd_vendas = 0.0
    receita_vendas = 0.0
    data_abertura = None

    for t in transacoes:
        if t.tipo in TIPOS_COMPRA:
            qtd_compras += t.quantidade
            custo_compras += t.quantidade * t.preco
            if data_abertura is None:
                data_abertura = t.data
        elif t.tipo in TIPOS_VENDA:
            qtd_vendas += t.quantidade
            receita_vendas += t.quantidade * t.preco

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
        position.data_saida = datetime.utcnow()
        # Calcula P&L de saída
        custo_total = qtd_vendas * pm  # custo das unidades vendidas
        if custo_total > 0:
            position.pl_reais = receita_vendas - custo_total
            position.pl_percentual = ((receita_vendas / custo_total) - 1) * 100
    else:
        position.ativa = True

    # Atualiza valor atual e P&L se tiver preço atual e posição aberta
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

    # ── Cálculo running: PM, saldo e P&L por transação ──────────────────
    resultado = []
    qtd_acum = 0.0
    custo_acum = 0.0  # custo total acumulado (qtd × PM)
    total_comprado = 0.0
    total_vendido = 0.0
    total_taxas = 0.0
    pl_realizado_total = 0.0

    for t in transacoes:
        vt = t.quantidade * t.preco
        tx = t.taxas or 0.0
        total_taxas += tx
        pm_antes = (custo_acum / qtd_acum) if qtd_acum > 0 else 0.0
        pl_tx = None  # P&L desta transação (só vendas)

        if t.tipo in TIPOS_COMPRA:
            total_comprado += vt
            qtd_acum += t.quantidade
            custo_acum += vt
        elif t.tipo in TIPOS_VENDA:
            total_vendido += vt
            if pm_antes > 0:
                pl_tx = round((t.preco - pm_antes) * t.quantidade - tx, 2)
                pl_realizado_total += pl_tx
            qtd_acum = max(0.0, qtd_acum - t.quantidade)
            custo_acum = qtd_acum * pm_antes  # custo remanescente
        elif t.tipo == "amortizacao":
            # Amortização reduz custo sem alterar quantidade
            custo_acum = max(0.0, custo_acum - vt)

        pm_apos = (custo_acum / qtd_acum) if qtd_acum > 0 else 0.0

        resultado.append({
            "id": t.id,
            "tipo": t.tipo,
            "data": t.data.isoformat() if t.data else None,
            "quantidade": t.quantidade,
            "preco": t.preco,
            "valor_total": vt,
            "valor_liquido": t.valor_liquido,
            "taxas": tx,
            "destino": t.destino,
            "observacao": t.observacao,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            # ── Campos enriquecidos ──
            "qtd_apos": round(qtd_acum, 6),
            "pm_apos": round(pm_apos, 4),
            "pl_realizado": pl_tx,
        })

    # ── Resumo agregado ──────────────────────────────────────────────────
    pm_atual = (custo_acum / qtd_acum) if qtd_acum > 0 else 0.0
    custo_remanescente = round(custo_acum, 2)
    preco_atual = position.preco_atual or pm_atual
    pl_nao_realizado = round((preco_atual - pm_atual) * qtd_acum, 2) if qtd_acum > 0 else 0.0

    # Breakeven: preço que zera P&L total considerando lucro já realizado
    # Se pl_realizado > 0, breakeven é menor que PM (já "pagou" parte)
    preco_breakeven = pm_atual
    if qtd_acum > 0 and pl_realizado_total != 0:
        preco_breakeven = pm_atual - (pl_realizado_total / qtd_acum)

    resumo = {
        "total_comprado": round(total_comprado, 2),
        "total_vendido": round(total_vendido, 2),
        "total_taxas": round(total_taxas, 2),
        "pl_realizado_total": round(pl_realizado_total, 2),
        "pl_nao_realizado": pl_nao_realizado,
        "pl_total": round(pl_realizado_total + pl_nao_realizado, 2),
        "qtd_atual": round(qtd_acum, 6),
        "pm_atual": round(pm_atual, 4),
        "custo_remanescente": custo_remanescente,
        "preco_breakeven": round(preco_breakeven, 4),
        "preco_atual": preco_atual,
    }

    return {"transacoes": resultado, "resumo": resumo}


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

    # Validação de venda: não pode vender mais do que tem
    if body.tipo in TIPOS_VENDA:
        if body.quantidade > position.quantidade:
            raise HTTPException(
                status_code=400,
                detail=f"Quantidade insuficiente. Disponível: {position.quantidade}, solicitado: {body.quantidade}",
            )
        if body.tipo == "venda_total" and body.quantidade != position.quantidade:
            raise HTTPException(
                status_code=400,
                detail=f"Venda total deve ser da quantidade exata. Disponível: {position.quantidade}",
            )

    # Parse da data
    try:
        data_dt = datetime.fromisoformat(body.data.replace("Z", "+00:00").replace("+00:00", ""))
    except ValueError:
        data_dt = datetime.utcnow()

    valor_total = body.quantidade * body.preco
    valor_liquido = valor_total - (body.taxas or 0.0)

    # Destino da venda (só para vendas)
    destino = None
    if body.tipo in TIPOS_VENDA and body.destino in ("caixa", "saque"):
        destino = body.destino

    nova = Transacao(
        portfolio_id=portfolio.id,
        position_id=position_id,
        tipo=body.tipo,
        data=data_dt,
        quantidade=body.quantidade,
        preco=body.preco,
        valor_total=valor_total,
        valor_liquido=valor_liquido if body.tipo in TIPOS_VENDA else None,
        taxas=body.taxas,
        destino=destino,
        observacao=body.observacao,
    )
    db.add(nova)
    db.flush()

    # Recalcula posição
    _recalcular_posicao(db, position)

    # Se venda com destino=caixa, adiciona ao CAIXA
    if destino == "caixa" and valor_liquido > 0:
        caixa = db.query(Position).filter(
            Position.portfolio_id == portfolio.id,
            Position.ticker == "CAIXA",
            Position.ativa == True,
        ).first()
        if caixa:
            caixa.quantidade = round(caixa.quantidade + valor_liquido, 2)
            caixa.valor_investido = round(caixa.valor_investido + valor_liquido, 2)
            caixa.valor_atual = caixa.valor_investido
        else:
            db.add(Position(
                portfolio_id=portfolio.id,
                ticker="CAIXA",
                nome="Reserva de Liquidez",
                tipo="CAIXA",
                modulo="caixa",
                quantidade=round(valor_liquido, 2),
                preco_medio=1.0,
                preco_atual=1.0,
                valor_investido=round(valor_liquido, 2),
                valor_atual=round(valor_liquido, 2),
                pl_reais=0.0,
                pl_percentual=0.0,
                moeda="BRL",
                data_entrada=data_dt,
            ))

    # TradeJournal: registra saída quando posição é encerrada
    if not position.ativa and body.tipo in TIPOS_VENDA:
        duracao = None
        if position.data_abertura and position.data_saida:
            duracao = (position.data_saida - position.data_abertura).days
        elif position.data_entrada and position.data_saida:
            duracao = (position.data_saida - position.data_entrada).days

        db.add(TradeJournal(
            portfolio_id=portfolio.id,
            position_id=position.id,
            ticker=position.ticker,
            tipo_operacao="SAIDA",
            motivo=body.observacao or "Venda registrada",
            preco=body.preco,
            quantidade=body.quantidade,
            valor_total=valor_total,
            resultado_pct=position.pl_percentual,
            resultado_reais=position.pl_reais,
            duracao_dias=duracao,
            modulo=position.modulo,
        ))

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

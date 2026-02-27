"""Rota do Dashboard — patrimônio, alocação, performance."""
from typing import Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Position
from app.data import get_quotes, get_macro_br, get_macro_global

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/")
async def get_dashboard(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Dados completos do dashboard — chamado ao abrir o app."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user or not user.onboarding_completo:
        raise HTTPException(status_code=400, detail="Onboarding não concluído")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    # Auto-save patrimônio de referência (ontem / início do mês)
    hoje = date.today()
    ultimo_acesso = portfolio.updated_at.date() if portfolio.updated_at else None
    if ultimo_acesso and ultimo_acesso < hoje:
        # Novo dia — salva ontem com o patrimônio total registrado
        portfolio.patrimonio_ontem = portfolio.patrimonio_total or 0.0
        # Novo mês — reseta referência mensal
        if ultimo_acesso.month != hoje.month or ultimo_acesso.year != hoje.year:
            portfolio.patrimonio_mes_inicio = portfolio.patrimonio_total or 0.0
        db.commit()

    # Buscar posições ativas
    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()

    # Atualizar cotações em tempo real
    tickers = [p.ticker for p in posicoes if p.tipo in ("ACAO", "FII", "ETF", "BDR")]
    cotacoes = await get_quotes(tickers) if tickers else {}

    # Calcular patrimônio atual
    patrimonio_atual = 0.0
    posicoes_data = []
    for p in posicoes:
        cotacao = cotacoes.get(p.ticker, {})
        preco_atual = cotacao.get("regularMarketPrice", p.preco_atual or p.preco_medio)
        valor_atual = preco_atual * p.quantidade
        pl_reais = valor_atual - p.valor_investido
        pl_pct = (pl_reais / p.valor_investido * 100) if p.valor_investido > 0 else 0

        patrimonio_atual += valor_atual
        posicoes_data.append({
            "id": p.id,
            "ticker": p.ticker,
            "nome": p.nome,
            "tipo": p.tipo,
            "modulo": p.modulo,
            "quantidade": p.quantidade,
            "preco_medio": p.preco_medio,
            "preco_atual": round(preco_atual, 2),
            "valor_atual": round(valor_atual, 2),
            "pl_reais": round(pl_reais, 2),
            "pl_percentual": round(pl_pct, 2),
            "stop_loss": p.stop_loss,
            "apex_score": p.apex_score,
        })

    # Alocação atual por módulo
    alocacao_atual = _calcular_alocacao_atual(posicoes_data, patrimonio_atual)
    alocacao_alvo = {
        "etfs": portfolio.alvo_etfs,
        "fiis": portfolio.alvo_fiis,
        "renda_fixa": portfolio.alvo_renda_fixa,
        "momentum": portfolio.alvo_momentum,
        "wheel": portfolio.alvo_wheel,
        "alpha": portfolio.alvo_alpha,
        "dividendos": getattr(portfolio, "alvo_dividendos", 0.0) or 0.0,
        "teses": getattr(portfolio, "alvo_teses", 0.0) or 0.0,
        "caixa": portfolio.alvo_caixa,
    }

    # Dados macro
    macro_br, macro_global = await get_macro_br(), await get_macro_global()

    return {
        "user": {"nome": user.name, "estrategia": user.estrategia},
        "patrimonio": {
            "atual": round(patrimonio_atual, 2),
            "ontem": portfolio.patrimonio_ontem,
            "var_dia_pct": round(
                (patrimonio_atual / portfolio.patrimonio_ontem - 1) * 100, 2
            ) if portfolio.patrimonio_ontem else 0,
            "var_mes_pct": round(
                (patrimonio_atual / portfolio.patrimonio_mes_inicio - 1) * 100, 2
            ) if portfolio.patrimonio_mes_inicio else 0,
            "inicio": portfolio.patrimonio_inicio,
            "total_pct": round(
                (patrimonio_atual / portfolio.patrimonio_inicio - 1) * 100, 2
            ) if portfolio.patrimonio_inicio else 0,
        },
        "alocacao": {
            "atual": alocacao_atual,
            "alvo": alocacao_alvo,
            "desvios": _calcular_desvios(alocacao_atual, alocacao_alvo),
        },
        "regime": portfolio.regime or "MISTO",
        "posicoes": posicoes_data,
        "macro": {**macro_br, **macro_global},
    }


def _calcular_alocacao_atual(posicoes: list[dict], patrimonio: float) -> dict:
    modulos = {"etfs": 0, "fiis": 0, "renda_fixa": 0, "momentum": 0, "wheel": 0, "alpha": 0, "dividendos": 0, "teses": 0, "caixa": 0}
    for p in posicoes:
        modulo = p.get("modulo", "caixa")
        if modulo in modulos and patrimonio > 0:
            modulos[modulo] += (p["valor_atual"] / patrimonio) * 100
    return {k: round(v, 1) for k, v in modulos.items()}


def _calcular_desvios(atual: dict, alvo: dict) -> dict:
    """Retorna desvio e semáforo (verde/amarelo/vermelho) por módulo."""
    result = {}
    for modulo in alvo:
        desvio = atual.get(modulo, 0) - alvo.get(modulo, 0)
        if abs(desvio) <= 2:
            semaforo = "verde"
        elif abs(desvio) <= 5:
            semaforo = "amarelo"
        else:
            semaforo = "vermelho"
        result[modulo] = {"desvio": round(desvio, 1), "semaforo": semaforo}
    return result

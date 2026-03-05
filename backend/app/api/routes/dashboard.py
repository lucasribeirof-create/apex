"""Rota do Dashboard — patrimônio, alocação, performance, macro, risco."""
from typing import Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id, get_portfolio_ativo
from app.models import User, Portfolio, Position
from app.data import get_quotes, get_macro_br, get_macro_global, get_history_global
from app.data.cache import cache as _market_cache
from app.core.regime import calcular_regime
from app.logger import logger

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/")
async def get_dashboard(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Dados completos do dashboard — chamado ao abrir o app."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
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
        # CAIXA: preço fixo 1.0, valor = quantidade — nunca buscar cotação
        if p.ticker == "CAIXA":
            preco_atual = 1.0
            valor_atual = p.quantidade
            pl_reais = 0.0
            pl_pct = 0.0
            # Corrige se estiver corrompido no banco
            if p.preco_atual != 1.0 or p.valor_atual != p.quantidade:
                p.preco_atual = 1.0
                p.valor_atual = p.quantidade
                p.valor_investido = p.quantidade
                p.pl_reais = 0.0
                p.pl_percentual = 0.0
        else:
            cotacao = cotacoes.get(p.ticker, {})
            preco_atual = cotacao.get("regularMarketPrice", p.preco_atual or p.preco_medio)
            valor_atual = preco_atual * p.quantidade
            pl_reais = valor_atual - p.valor_investido
            pl_pct = (pl_reais / p.valor_investido * 100) if p.valor_investido > 0 else 0

            # Atualizar posição no banco com preço live
            if preco_atual != p.preco_atual:
                p.preco_atual = preco_atual
                p.valor_atual = valor_atual
                p.pl_reais = pl_reais
                p.pl_percentual = round(pl_pct, 2)

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

    # ── Inicializar referências patrimoniais se nunca foram setadas ────────
    _ref_changed = False
    if (not portfolio.patrimonio_ontem or portfolio.patrimonio_ontem == 0) and patrimonio_atual > 0:
        portfolio.patrimonio_ontem = patrimonio_atual
        _ref_changed = True
    if (not portfolio.patrimonio_mes_inicio or portfolio.patrimonio_mes_inicio == 0) and patrimonio_atual > 0:
        portfolio.patrimonio_mes_inicio = patrimonio_atual
        _ref_changed = True
    if (not portfolio.patrimonio_inicio or portfolio.patrimonio_inicio == 0) and patrimonio_atual > 0:
        portfolio.patrimonio_inicio = patrimonio_atual
        _ref_changed = True
    if patrimonio_atual > 0:
        portfolio.patrimonio_total = patrimonio_atual
        _ref_changed = True
    if _ref_changed:
        db.commit()

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

    # ── Regime de mercado: calcula e persiste no portfolio ─────────────────────
    # Usa o cache compartilhado com /market/regime (TTL 1h) para não reprocessar
    _REGIME_KEY = "market:regime"
    _cached_regime = _market_cache.get(_REGIME_KEY)
    from app.core.regime import RegimeInfo as _RegimeInfo
    regime_info = None
    if _cached_regime:
        if isinstance(_cached_regime, _RegimeInfo):
            regime_atual = str(_cached_regime.regime)
            regime_info = _cached_regime
        else:
            regime_atual = str(_cached_regime.get("regime", "MISTO"))
    else:
        # Tenta calcular com dados macro enriquecidos
        macro_ctx = None
        try:
            from app.cerebro.macro import montar_macro
            macro_ctx = await montar_macro()
        except Exception:
            pass

        ibov_data = await get_history_global("^BVSP", period="1y", interval="1d")
        if ibov_data and len(ibov_data) >= 50:
            closes = [r["close"] for r in ibov_data if r.get("close") is not None]
            _res = calcular_regime(closes, macro_context=macro_ctx)
            regime_atual = str(_res.regime)
            regime_info = _res
            _market_cache.set(_REGIME_KEY, _res, ttl=3600)
        else:
            regime_atual = portfolio.regime or "MISTO"

    if portfolio.regime != regime_atual:
        portfolio.regime = regime_atual
        portfolio.regime_atualizado_em = datetime.utcnow()
        db.commit()

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
        "regime": regime_atual,
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


# ─── Dashboard V2 — Endpoints enriquecidos ────────────────────────────────────

@router.get("/macro")
async def get_macro_dashboard():
    """Painel macro completo — VIX, DXY, yields, commodities, Brasil."""
    try:
        from app.cerebro.macro import montar_macro
        macro = await montar_macro()
        return {
            "global": {
                "treasury_10y": macro.treasury_10y,
                "vix": macro.vix,
                "dxy": macro.dxy,
                "sp500": macro.sp500,
                "sp500_var_pct": macro.sp500_var_pct,
                "petroleo_wti": macro.petroleo_wti,
                "petroleo_brent": macro.petroleo_brent,
                "ouro": macro.ouro,
            },
            "brasil": {
                "selic": macro.selic,
                "ipca_12m": macro.ipca_12m,
                "ipca_expectativa": macro.ipca_expectativa,
                "selic_expectativa": macro.selic_expectativa,
                "juro_real": macro.juro_real,
                "dolar_brl": macro.dolar_brl,
                "dolar_var_pct": macro.dolar_var_pct,
                "ibov": macro.ibov,
                "ibov_var_pct": macro.ibov_var_pct,
            },
            "flags": macro.flags,
            "atualizado_em": macro.atualizado_em,
        }
    except Exception as e:
        logger.error("dashboard/macro falhou: %s", e)
        raise HTTPException(status_code=503, detail="Dados macro indisponíveis")


@router.get("/correlacao")
async def get_correlacao(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Mapa de correlação entre posições do portfólio."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()

    posicoes_dict = [
        {"ticker": p.ticker, "tipo": p.tipo, "modulo": p.modulo,
         "valor_atual": p.valor_atual or 0}
        for p in posicoes
    ]

    try:
        from app.cerebro.risco import calcular_correlacao
        resultado = await calcular_correlacao(posicoes_dict)
        return resultado
    except Exception as e:
        logger.error("dashboard/correlacao falhou: %s", e)
        return {"matriz": {}, "clusters": [], "alertas": []}


@router.get("/teses")
async def get_teses_status(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Status das teses de investimento do portfólio."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    try:
        from app.cerebro.teses import monitorar_teses
        status = await monitorar_teses(db, portfolio.id)
        return status
    except Exception as e:
        logger.error("dashboard/teses falhou: %s", e)
        return {"total": 0, "ativas": 0, "enfraquecidas": 0, "invalidadas": 0, "alertas": []}


@router.get("/performance")
def get_performance(periodo: int = 90, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Performance de trading no período (dias)."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    try:
        from app.cerebro.aprendizado import analisar_performance
        return analisar_performance(db, portfolio.id, periodo_dias=periodo)
    except Exception as e:
        logger.error("dashboard/performance falhou: %s", e)
        return {"total_trades": 0, "win_rate": 0, "rr_medio": 0}


@router.get("/stress")
async def get_stress_test(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Stress test do portfólio."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()

    posicoes_dict = [
        {"ticker": p.ticker, "tipo": p.tipo, "modulo": p.modulo,
         "valor_atual": p.valor_atual or 0}
        for p in posicoes
    ]
    patrimonio = portfolio.patrimonio_total or sum(p.get("valor_atual", 0) for p in posicoes_dict)

    try:
        from app.cerebro.risco import stress_test
        return await stress_test(posicoes_dict, patrimonio)
    except Exception as e:
        logger.error("dashboard/stress falhou: %s", e)
        return []

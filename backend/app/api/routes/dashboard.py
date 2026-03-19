"""Rota do Dashboard — patrimônio, alocação, performance, macro, risco."""
from typing import Optional
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id, get_portfolio_ativo
from app.models import User, Portfolio, Position
from app.models.portfolio_snapshot import PortfolioSnapshot
from app.data import get_quotes, get_macro_br, get_macro_global, get_history_global
from app.data.cache import cache as _market_cache
from app.core.regime import calcular_regime
from app.logger import logger
from fastapi.responses import JSONResponse
import json

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class _NumpySafeEncoder(json.JSONEncoder):
    """JSON encoder que converte tipos numpy para tipos Python nativos."""
    def default(self, obj):
        try:
            import numpy as np
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def _sanitize(obj):
    """Serializa via JSON com encoder numpy-safe e retorna dict limpo."""
    return json.loads(json.dumps(obj, cls=_NumpySafeEncoder, default=str))


@router.get("/")
async def get_dashboard(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Dados completos do dashboard — chamado ao abrir o app."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user or not user.onboarding_completo:
        raise HTTPException(status_code=400, detail="Onboarding não concluído")

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

    # Inicializar patrimônio de referência se ainda for 0 (1º acesso)
    _pat_changed = False
    pat_total = portfolio.patrimonio_total or 0.0
    if not portfolio.patrimonio_ontem and pat_total > 0:
        portfolio.patrimonio_ontem = pat_total
        _pat_changed = True
    if not portfolio.patrimonio_mes_inicio and pat_total > 0:
        portfolio.patrimonio_mes_inicio = pat_total
        _pat_changed = True
    if not portfolio.patrimonio_inicio and pat_total > 0:
        portfolio.patrimonio_inicio = pat_total
        _pat_changed = True
    if _pat_changed:
        db.commit()

    # Buscar posições ativas
    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()

    # Atualizar cotações em tempo real
    tickers = [p.ticker for p in posicoes if p.tipo in ("ACAO", "FII", "ETF", "BDR")]
    cotacoes = await get_quotes(tickers) if tickers else {}

    # Fallback yfinance (quando BRAPI não está configurada)
    if tickers and not cotacoes:
        from app.data.yfinance_client import get_quotes_yf
        cotacoes = await get_quotes_yf(tickers)

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
        # Variação diária do ativo (BRAPI)
        change_day_pct = cotacao.get("regularMarketChangePercent", 0) or 0
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
            "var_dia_pct": round(change_day_pct, 2),
            "stop_loss": p.stop_loss,
            "apex_score": p.apex_score,
        })

    # Persiste patrimônio ao vivo para referências futuras (ontem, mês, etc.)
    if patrimonio_atual > 0 and patrimonio_atual != portfolio.patrimonio_total:
        portfolio.patrimonio_total = round(patrimonio_atual, 2)
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

    # ── Regime de mercado: usa cache ou persiste valor existente ────────────────
    # O cálculo pesado (montar_macro + ibov history) é delegado ao /market/regime.
    # Aqui usamos cache ou fallback do portfolio para não duplicar o trabalho.
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
        # Fallback: usa o regime salvo no portfolio (será atualizado pelo /market/regime chamado em paralelo)
        regime_atual = portfolio.regime or "MISTO"

    if portfolio.regime != regime_atual:
        portfolio.regime = regime_atual
        portfolio.regime_atualizado_em = datetime.utcnow()
        db.commit()

    # Dados macro
    macro_br, macro_global = await get_macro_br(), await get_macro_global()

    # ── Renda mensal projetada ─────────────────────────────────────────────────
    # Estima dividendos/proventos mensais usando DY das cotações BRAPI
    renda_anual_projetada = 0.0
    valor_investido_total = 0.0
    for p in posicoes:
        vi = p.valor_investido or 0.0
        valor_investido_total += vi
        cot = cotacoes.get(p.ticker, {})
        dy = cot.get("dividendYield")  # decimal (ex: 0.08 = 8%)
        if dy and p.tipo in ("ACAO", "FII", "BDR"):
            preco = cot.get("regularMarketPrice", p.preco_atual or p.preco_medio)
            renda_anual_projetada += preco * p.quantidade * (dy if dy < 1 else dy / 100)
        elif p.tipo == "RF" and p.preco_atual and p.quantidade:
            # Renda fixa: estimativa conservadora = Selic × valor / 100
            _selic = macro_br.get("selic") or 0
            renda_anual_projetada += p.preco_atual * p.quantidade * _selic / 100

    renda_mes = round(renda_anual_projetada / 12, 2) if renda_anual_projetada > 0 else None
    yoc = round(renda_anual_projetada / valor_investido_total * 100, 2) if valor_investido_total > 0 and renda_anual_projetada > 0 else None

    # ── Retornos baseados em P&L real (não patrimônio delta, que infla com depósitos) ──
    # Variação diária: usa regularMarketChangePercent da BRAPI por posição
    var_dia_reais = 0.0
    for p_data in posicoes_data:
        cot = cotacoes.get(p_data["ticker"], {})
        change_pct = cot.get("regularMarketChangePercent", 0) or 0
        # change_pct vem em % (ex: 2.5 = +2.5%)
        var_dia_reais += p_data["valor_atual"] * change_pct / 100
    var_dia_reais = round(var_dia_reais, 2)
    var_dia_pct = round(var_dia_reais / patrimonio_atual * 100, 2) if patrimonio_atual > 0 else 0

    # Retorno total e mensal baseados em P&L / valor investido
    pl_total = patrimonio_atual - valor_investido_total
    total_pct = round(pl_total / valor_investido_total * 100, 2) if valor_investido_total > 0 else 0

    # Retorno no mês: usa snapshot do 1º dia do mês, ou patrimonio_mes_inicio
    var_mes_pct = None
    primeiro_dia_mes = hoje.replace(day=1)
    snap_mes = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.portfolio_id == portfolio.id,
        PortfolioSnapshot.date >= primeiro_dia_mes,
    ).order_by(PortfolioSnapshot.date.asc()).first()

    if snap_mes and snap_mes.custo_total and snap_mes.custo_total > 0:
        # Retorno baseado em P&L: (pl_atual - pl_inicio_mes) / custo_inicio_mes
        pl_inicio_mes = snap_mes.patrimonio - snap_mes.custo_total
        pl_atual = patrimonio_atual - valor_investido_total
        delta_pl = pl_atual - pl_inicio_mes
        var_mes_pct = round(delta_pl / snap_mes.custo_total * 100, 2)
    elif portfolio.patrimonio_mes_inicio and portfolio.patrimonio_mes_inicio > 0:
        mes_pct_raw = (patrimonio_atual / portfolio.patrimonio_mes_inicio - 1) * 100
        # Sanidade: se parece razoável (<20% mensal), usa
        if abs(mes_pct_raw) < 20:
            var_mes_pct = round(mes_pct_raw, 2)

    # vs CDI: CDI mensal estimado a partir da Selic
    _selic_anual = macro_br.get("selic") or 0
    cdi_mes_pct = round(((1 + _selic_anual / 100) ** (1 / 12) - 1) * 100, 2) if _selic_anual > 0 else None
    vs_cdi = round(var_mes_pct - cdi_mes_pct, 2) if cdi_mes_pct is not None and var_mes_pct is not None else None

    resp = {
        "user": {"nome": user.name, "estrategia": user.estrategia},
        "patrimonio": {
            "atual": round(patrimonio_atual, 2),
            "ontem": portfolio.patrimonio_ontem,
            "var_dia_pct": var_dia_pct,
            "var_dia_reais": var_dia_reais,
            "var_mes_pct": var_mes_pct,
            "cdi_mes_pct": cdi_mes_pct,
            "vs_cdi": vs_cdi,
            "inicio": portfolio.patrimonio_inicio,
            "total_pct": total_pct,
            "valor_investido_total": round(valor_investido_total, 2),
        },
        "renda": {
            "renda_mes": renda_mes,
            "renda_anual_projetada": round(renda_anual_projetada, 2) if renda_anual_projetada > 0 else None,
            "yoc": yoc,
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
    return JSONResponse(content=_sanitize(resp))


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


# ─── Retorno por período ──────────────────────────────────────────────────────

@router.get("/retorno")
def get_retorno_periodo(
    periodo: str = "1m",
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Retorno do portfólio por período usando snapshots.
    periodo: 1s (semana), 1m, 3m, 6m, 1a, inicio
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(400, "Usuário não encontrado")
    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(404, "Portfólio não encontrado")

    hoje = date.today()
    periodos = {
        "1s": timedelta(days=7),
        "1m": timedelta(days=30),
        "3m": timedelta(days=90),
        "6m": timedelta(days=180),
        "1a": timedelta(days=365),
    }

    if periodo == "inicio":
        data_inicio = date(2020, 1, 1)
    else:
        delta = periodos.get(periodo, timedelta(days=30))
        data_inicio = hoje - delta

    snaps = db.query(PortfolioSnapshot).filter(
        PortfolioSnapshot.portfolio_id == portfolio.id,
        PortfolioSnapshot.date >= data_inicio,
    ).order_by(PortfolioSnapshot.date.asc()).all()

    if len(snaps) < 2:
        return {"periodo": periodo, "retorno_pct": None, "cdi_pct": None, "msg": "Dados insuficientes"}

    primeiro = snaps[0]
    ultimo = snaps[-1]

    # Retorno baseado em P&L (imune a depósitos)
    pl_inicio = primeiro.patrimonio - primeiro.custo_total if primeiro.custo_total else 0
    pl_fim = ultimo.patrimonio - ultimo.custo_total if ultimo.custo_total else 0
    base = primeiro.custo_total or primeiro.patrimonio
    retorno_pct = round((pl_fim - pl_inicio) / base * 100, 2) if base > 0 else 0

    # CDI no período
    cdi_pct = round((ultimo.cdi_acumulado or 0) - (primeiro.cdi_acumulado or 0), 2)

    # Série para gráfico
    serie = []
    for s in snaps:
        pl_s = s.patrimonio - s.custo_total if s.custo_total else 0
        pct_s = round((pl_s - pl_inicio) / base * 100, 2) if base > 0 else 0
        cdi_s = round((s.cdi_acumulado or 0) - (primeiro.cdi_acumulado or 0), 2)
        serie.append({"date": s.date.isoformat(), "retorno_pct": pct_s, "cdi_pct": cdi_s})

    return {
        "periodo": periodo,
        "retorno_pct": retorno_pct,
        "cdi_pct": cdi_pct,
        "vs_cdi": round(retorno_pct - cdi_pct, 2) if cdi_pct is not None else None,
        "serie": serie,
    }


# ─── Top Movers por período ──────────────────────────────────────────────────

@router.get("/movers")
async def get_top_movers(
    periodo: str = "1m",
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Top movers por período (1m, 3m, 6m, 1a)."""
    periodos_yf = {"1m": "1mo", "3m": "3mo", "6m": "6mo", "1a": "1y"}
    yf_period = periodos_yf.get(periodo)
    if not yf_period:
        raise HTTPException(400, f"Período inválido: {periodo}")

    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(400, "Usuário não encontrado")
    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(404, "Portfólio não encontrado")

    tickers = [p.ticker for p in db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
        Position.tipo.in_(["ACAO", "FII", "ETF", "BDR"]),
    ).all()]

    if not tickers:
        return {"periodo": periodo, "movers": []}

    from app.data.yfinance_client import get_period_returns_yf
    returns = await get_period_returns_yf(tickers, yf_period)

    movers = [{"ticker": t, "var_pct": returns.get(t, 0)} for t in tickers if t in returns]
    movers.sort(key=lambda x: x["var_pct"], reverse=True)

    return {"periodo": periodo, "movers": movers}


# ─── Dashboard V2 — Endpoints enriquecidos ────────────────────────────────────

@router.get("/macro")
async def get_macro_dashboard():
    """Painel macro completo — VIX, DXY, yields, commodities, Brasil."""
    try:
        from app.cerebro.macro import montar_macro
        macro = await montar_macro()
        return JSONResponse(content=_sanitize({
            "global": {
                "treasury_10y": macro.treasury_10y,
                "treasury_5y": macro.treasury_5y,
                "treasury_30y": macro.treasury_30y,
                "yield_spread_2y10y": macro.yield_spread_2y10y,
                "yield_spread_2y30y": macro.yield_spread_2y30y,
                "vix": macro.vix,
                "dxy": macro.dxy,
                "sp500": macro.sp500,
                "sp500_var_pct": macro.sp500_var_pct,
                "dow_jones": macro.dow_jones,
                "dow_jones_var_pct": macro.dow_jones_var_pct,
                "petroleo_wti": macro.petroleo_wti,
                "petroleo_brent": macro.petroleo_brent,
                "ouro": macro.ouro,
                "sp500_futures": macro.sp500_futures,
                "sp500_futures_var_pct": macro.sp500_futures_var_pct,
                "nasdaq_futures": macro.nasdaq_futures,
                "nasdaq_futures_var_pct": macro.nasdaq_futures_var_pct,
                # Commodities
                "cobre": macro.cobre,
                "soja": macro.soja,
                "milho": macro.milho,
                "minerio_ferro": macro.minerio_ferro,
                # Moedas cross
                "usdjpy": macro.usdjpy,
                "eurusd": macro.eurusd,
                "usdcny": macro.usdcny,
                # Credit
                "hyg": macro.hyg,
                "lqd": macro.lqd,
                "credit_spread": macro.credit_spread,
                # Sentiment
                "btc": macro.btc,
                "btc_var_pct": macro.btc_var_pct,
                # China
                "hang_seng": macro.hang_seng,
                "hang_seng_var_pct": macro.hang_seng_var_pct,
                # EWZ
                "ewz": macro.ewz,
                "ewz_var_pct": macro.ewz_var_pct,
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
                "ifix": macro.ifix,
                "ifix_var_pct": macro.ifix_var_pct,
                # Curva DI
                "di_1ano": macro.di_1ano,
                "di_2anos": macro.di_2anos,
                "di_3anos": macro.di_3anos,
                "di_5anos": macro.di_5anos,
                "inclinacao_di": macro.inclinacao_di,
            },
            "flags": macro.flags,
            "atualizado_em": macro.atualizado_em,
        }))
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
        return JSONResponse(content=_sanitize(resultado))
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
        return JSONResponse(content=_sanitize(status))
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
        return JSONResponse(content=_sanitize(analisar_performance(db, portfolio.id, periodo_dias=periodo)))
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
        return JSONResponse(content=_sanitize(await stress_test(posicoes_dict, patrimonio)))
    except Exception as e:
        logger.error("dashboard/stress falhou: %s", e)
        return []


@router.get("/dividendos")
async def get_proximos_dividendos(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Próximos dividendos projetados para posições em carteira."""
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
        Position.tipo.in_(["ACAO", "FII", "ETF", "BDR"]),
    ).all()

    if not posicoes:
        return {"proximos": [], "total_projetado_mes": 0}

    try:
        from app.data.brapi import get_fundamentals

        hoje = datetime.now()
        proximos = []

        for pos in posicoes:
            fund = await get_fundamentals(pos.ticker)
            if not fund:
                continue
            divs = fund.get("_raw_dividends") or []
            if not divs:
                continue

            # Pegar os últimos 12 meses de dividendos para estimar próximos
            # Só conta dividendos pagos APÓS a data de compra da posição
            recentes = []
            cutoff_12m = hoje - timedelta(days=365)
            entrada_dt = pos.data_entrada.replace(tzinfo=None) if pos.data_entrada else None
            for d in divs:
                try:
                    dt = datetime.fromisoformat(d.get("paymentDate", "2000-01-01T00:00:00.000Z").replace("Z", ""))
                    if dt > cutoff_12m:
                        if entrada_dt and dt < entrada_dt:
                            continue
                        recentes.append({"date": dt, "rate": d.get("rate", 0)})
                except Exception:
                    pass

            if not recentes:
                continue

            # Média por evento dos últimos 12 meses
            media_por_evento = sum(r["rate"] for r in recentes) / len(recentes)
            total_12m = sum(r["rate"] for r in recentes)

            # Estimar próximo pagamento: último pagamento + intervalo médio
            recentes.sort(key=lambda x: x["date"])
            ultimo = recentes[-1]["date"]
            if len(recentes) >= 2:
                gaps = [(recentes[i]["date"] - recentes[i-1]["date"]).days for i in range(1, len(recentes))]
                intervalo_medio = sum(gaps) / len(gaps)
            else:
                # FII geralmente mensal, ações trimestrais
                intervalo_medio = 30 if pos.tipo == "FII" else 90

            proximo_dt = ultimo + timedelta(days=intervalo_medio)
            # Se a data estimada já passou, avançar um intervalo
            while proximo_dt < hoje:
                proximo_dt += timedelta(days=intervalo_medio)

            valor_estimado = media_por_evento * (pos.quantidade or 0)

            proximos.append({
                "ticker": pos.ticker,
                "tipo": pos.tipo,
                "data_estimada": proximo_dt.strftime("%Y-%m-%d"),
                "dias_restantes": (proximo_dt - hoje).days,
                "valor_por_cota": round(media_por_evento, 4),
                "quantidade": pos.quantidade or 0,
                "valor_estimado": round(valor_estimado, 2),
                "dy_12m": round(total_12m / (pos.preco_atual or 1) * 100, 2) if pos.preco_atual else 0,
                "frequencia": "mensal" if intervalo_medio < 45 else ("trimestral" if intervalo_medio < 100 else "semestral"),
            })

        proximos.sort(key=lambda x: x["dias_restantes"])

        total_projetado_mes = sum(
            p["valor_estimado"] for p in proximos
            if p["dias_restantes"] <= 31
        )

        return {
            "proximos": proximos,
            "total_projetado_mes": round(total_projetado_mes, 2),
        }
    except Exception as e:
        logger.error("dashboard/dividendos falhou: %s", e)
        return {"proximos": [], "total_projetado_mes": 0}

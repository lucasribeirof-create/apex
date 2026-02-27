"""Rota de dados de mercado — cotações, busca, macro."""
from fastapi import APIRouter, HTTPException
from app.data import get_quote, get_quotes, get_history, search_tickers, get_macro_br, get_macro_global
from app.data.yfinance_client import get_history_global
from app.data.cache import cache
from app.core.regime import calcular_regime, get_acoes_permitidas_regime

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/quote/{ticker}")
async def cotacao(ticker: str):
    """Cotação atual de um ativo."""
    data = await get_quote(ticker.upper())
    if not data:
        raise HTTPException(status_code=404, detail=f"Ativo {ticker} não encontrado")
    return data


@router.get("/history/{ticker}")
async def historico(ticker: str, period: str = "1y", interval: str = "1d"):
    """Histórico de preços de um ativo."""
    data = await get_history(ticker.upper(), period=period, interval=interval)
    if not data:
        raise HTTPException(status_code=404, detail=f"Histórico de {ticker} não disponível")
    return data


@router.get("/search")
async def buscar_ativos(q: str):
    """Busca ativos por nome ou ticker."""
    return await search_tickers(q)


@router.get("/macro")
async def macro():
    """Dados macro: dólar, IBOV, VIX, S&P500."""
    br, global_ = await get_macro_br(), await get_macro_global()
    return {**br, **global_}


@router.get("/regime")
async def regime_mercado():
    """Regime atual do mercado: BULL, MISTO ou BEAR."""
    TTL = 3600  # 1 hora
    cache_key = "market:regime"
    cached = cache.get(cache_key)
    if cached:
        return cached

    data = await get_history_global("^BVSP", period="1y", interval="1d")
    if not data:
        raise HTTPException(status_code=503, detail="Dados do IBOV indisponíveis")

    closes = [r["close"] for r in data if r.get("close") is not None]
    resultado = calcular_regime(closes)
    acoes = get_acoes_permitidas_regime(resultado["regime"])

    resposta = {
        "regime": resultado["regime"],
        "motivo": resultado["motivo"],
        "detalhes": resultado["detalhes"],
        "acoes": acoes,
    }
    cache.set(cache_key, resposta, ttl=TTL)
    return resposta


@router.get("/cache/stats")
def cache_stats():
    """Estatísticas do cache em memória (debug)."""
    return cache.stats()

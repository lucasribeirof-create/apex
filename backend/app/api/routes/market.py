"""Rota de dados de mercado — cotações, busca, macro."""
from fastapi import APIRouter, HTTPException
from app.data import get_quote, get_quotes, get_history, search_tickers, get_macro_br, get_macro_global
from app.data.cache import cache

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


@router.get("/cache/stats")
def cache_stats():
    """Estatísticas do cache em memória (debug)."""
    return cache.stats()

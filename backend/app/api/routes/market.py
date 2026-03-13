"""Rota de dados de mercado — cotações, busca, macro."""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from app.data import get_quote, get_quotes, get_history, search_tickers, get_macro_br, get_macro_global
from app.data.yfinance_client import get_history_global
from app.data.cache import cache
from app.core.regime import calcular_regime, get_acoes_permitidas_regime


class _NumpySafeEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            import numpy as np
            if isinstance(obj, np.bool_): return bool(obj)
            if isinstance(obj, np.integer): return int(obj)
            if isinstance(obj, np.floating): return float(obj)
            if isinstance(obj, np.ndarray): return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def _sanitize(obj):
    return json.loads(json.dumps(obj, cls=_NumpySafeEncoder, default=str))


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
    """Histórico de preços de um ativo. Tenta BRAPI, fallback para yfinance."""
    data = await get_history(ticker.upper(), period=period, interval=interval)
    if not data:
        # Fallback yfinance: adiciona .SA para tickers B3
        yf_ticker = ticker.upper() if any(c in ticker for c in ["^", "."]) else ticker.upper() + ".SA"
        data = await get_history_global(yf_ticker, period=period, interval=interval)
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
        return JSONResponse(content=_sanitize(cached))

    data = await get_history_global("^BVSP", period="1y", interval="1d")
    if not data:
        raise HTTPException(status_code=503, detail="Dados do IBOV indisponíveis")

    closes = [r["close"] for r in data if r.get("close") is not None]

    # Tenta enriquecer com MacroContext se disponível
    macro_ctx = None
    try:
        from app.cerebro.macro import montar_macro
        macro_ctx = await montar_macro()
    except Exception:
        pass

    resultado = calcular_regime(closes, macro_context=macro_ctx)
    acoes = get_acoes_permitidas_regime(resultado.regime)

    resposta = {
        "regime": resultado.regime.value if hasattr(resultado.regime, 'value') else str(resultado.regime),
        "motivo": resultado.regime_motivo,
        "detalhes": resultado.detalhes,
        "sinais": resultado.sinais,
        "flags": resultado.flags,
        "acoes": acoes,
    }
    cache.set(cache_key, resposta, ttl=TTL)
    return JSONResponse(content=_sanitize(resposta))


@router.get("/cache/stats")
def cache_stats():
    """Estatísticas do cache em memória (debug)."""
    return cache.stats()

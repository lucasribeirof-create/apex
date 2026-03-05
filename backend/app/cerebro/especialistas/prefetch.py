"""
Pre-fetch centralizado — busca dados de mercado UMA VEZ e compartilha com todos os motores.

Problema resolvido:
  Quando 7 motores rodam em paralelo, yfinance é chamado N vezes para o mesmo ticker.
  Momentum busca PETR4, Alpha busca PETR4, Dividendos busca PETR4 — 3 chamadas separadas.

Solução:
  prefetch.buscar(tickers) → cache em memória com TTL de 5 minutos.
  Cada motor chama prefetch.get(ticker) em vez de yfinance diretamente.

Dados pré-buscados por ticker:
  - preco: preço de fechamento mais recente
  - hist: DataFrame com histórico de 1 ano (OHLCV)
  - info: dict yfinance info (fundamentals)
  - dividends_12m: soma dos dividendos nos últimos 12 meses
  - dy_12m: dividend yield real trailing 12 meses
  - p_vp: preço sobre valor patrimonial (book value)

Uso:
    from app.cerebro.especialistas.prefetch import buscar, get

    # No orquestrador (portfolio.py), ANTES de disparar os motores:
    await buscar(todos_os_tickers)

    # Dentro de cada motor:
    dados = get("PETR4")  # instantâneo, do cache
"""

import asyncio
import time
from typing import Optional
from dataclasses import dataclass, field

import yfinance as yf

from app.logger import logger


# ─── Estrutura do cache ──────────────────────────────────────────────────────

@dataclass
class TickerData:
    """Dados pré-buscados de um ticker."""
    ticker: str
    preco: float = 0.0
    hist: Optional[object] = None       # pd.DataFrame (1y OHLCV)
    info: dict = field(default_factory=dict)
    dividends_12m: float = 0.0
    dy_12m: float = 0.0                 # dividend yield trailing 12m (%)
    p_vp: Optional[float] = None        # preço / valor patrimonial
    payout_ratio: Optional[float] = None
    nome: str = ""
    setor: str = ""
    sucesso: bool = False               # True = dados válidos


_cache: dict[str, TickerData] = {}
_cache_ts: float = 0.0
_CACHE_TTL = 300  # 5 minutos

_fail_cache: dict[str, float] = {}
_FAIL_CACHE_TTL = 3600  # 1h — não re-busca tickers que falharam


def _is_stale() -> bool:
    return time.time() - _cache_ts > _CACHE_TTL


def _is_known_fail(ticker: str) -> bool:
    ts = _fail_cache.get(ticker.upper())
    if ts is None:
        return False
    if time.time() - ts > _FAIL_CACHE_TTL:
        del _fail_cache[ticker.upper()]
        return False
    return True


def get(ticker: str) -> Optional[TickerData]:
    """Retorna dados do cache ou None se não disponível."""
    return _cache.get(ticker.upper())


def get_preco(ticker: str) -> Optional[float]:
    """Atalho: retorna só o preço ou None."""
    d = _cache.get(ticker.upper())
    return d.preco if d and d.sucesso and d.preco > 0 else None


def get_hist(ticker: str):
    """Atalho: retorna o DataFrame de histórico ou None."""
    d = _cache.get(ticker.upper())
    return d.hist if d and d.sucesso else None


def get_dy(ticker: str) -> Optional[float]:
    """Atalho: retorna DY trailing 12m (%) ou None."""
    d = _cache.get(ticker.upper())
    return d.dy_12m if d and d.sucesso and d.dy_12m > 0 else None


def get_pvp(ticker: str) -> Optional[float]:
    """Atalho: retorna P/VP ou None."""
    d = _cache.get(ticker.upper())
    return d.p_vp if d and d.sucesso else None


# ─── Fetch individual (thread-safe, roda em thread pool) ─────────────────────

def _fetch_one(ticker: str) -> TickerData:
    """Busca todos os dados de um ticker via yfinance. Roda em thread."""
    result = TickerData(ticker=ticker.upper())

    try:
        yf_suffix = ticker.upper()
        if not yf_suffix.endswith(".SA"):
            yf_suffix += ".SA"

        t = yf.Ticker(yf_suffix)

        # Histórico 1 ano
        hist = t.history(period="1y", auto_adjust=False)
        if hist is None or hist.empty:
            return result

        preco = float(hist["Close"].iloc[-1])
        if preco <= 0:
            return result

        result.preco = round(preco, 2)
        result.hist = hist

        # Dividendos 12m
        if "Dividends" in hist.columns:
            divs = hist["Dividends"]
            result.dividends_12m = round(float(divs.sum()), 4)
            if preco > 0 and result.dividends_12m > 0:
                result.dy_12m = round(result.dividends_12m / preco * 100, 2)

        # Info (fundamentals) — pode ser lento, mas vale ter
        try:
            info = t.info
            if info:
                result.info = info
                result.nome = str(info.get("shortName") or info.get("longName") or ticker)
                result.setor = str(info.get("sector") or "")

                # P/VP
                bv = info.get("bookValue")
                if bv and bv > 0:
                    result.p_vp = round(preco / bv, 2)

                # Payout
                pr = info.get("payoutRatio")
                if pr is not None:
                    result.payout_ratio = round(float(pr) * 100, 1)
        except Exception:
            pass  # info é bonus, não crítico

        result.sucesso = True

    except Exception as e:
        logger.debug("prefetch: falha ao buscar %s: %s", ticker, e)

    return result


# ─── Interface pública ────────────────────────────────────────────────────────

async def buscar(tickers: list[str], force: bool = False) -> dict[str, TickerData]:
    """
    Busca dados de todos os tickers em paralelo (thread pool).
    Resultados ficam em cache por 5 minutos.

    Args:
        tickers: lista de tickers B3 (sem .SA)
        force: ignora cache e busca tudo de novo

    Returns:
        dict ticker → TickerData
    """
    global _cache, _cache_ts

    tickers_upper = list({t.upper() for t in tickers})

    # Filtra tickers com falha conhecida (não re-busca por _FAIL_CACHE_TTL)
    skipped = [t for t in tickers_upper if _is_known_fail(t)]
    tickers_upper = [t for t in tickers_upper if not _is_known_fail(t)]
    if skipped:
        logger.info("prefetch: pulando %d tickers com falha recente: %s", len(skipped), ", ".join(skipped[:5]))

    # Se cache está fresco e tem todos os tickers, retorna direto
    if not force and not _is_stale():
        faltam = [t for t in tickers_upper if t not in _cache]
        if not faltam:
            return _cache
        tickers_upper = faltam

    logger.info("prefetch: buscando %d tickers...", len(tickers_upper))
    t0 = time.time()

    tarefas = [asyncio.to_thread(_fetch_one, t) for t in tickers_upper]
    resultados = await asyncio.gather(*tarefas, return_exceptions=True)

    for ticker, res in zip(tickers_upper, resultados):
        if isinstance(res, TickerData):
            _cache[ticker] = res
            if not res.sucesso:
                _fail_cache[ticker] = time.time()
        else:
            logger.debug("prefetch: exceção ao buscar %s: %s", ticker, res)
            _cache[ticker] = TickerData(ticker=ticker, sucesso=False)
            _fail_cache[ticker] = time.time()

    _cache_ts = time.time()
    sucesso = sum(1 for r in _cache.values() if r.sucesso)
    logger.info("prefetch: %d/%d tickers com sucesso (%.1fs)", sucesso, len(tickers_upper), time.time() - t0)

    return _cache


def limpar_cache():
    """Limpa o cache de pre-fetch (útil em testes)."""
    global _cache, _cache_ts, _fail_cache
    _cache = {}
    _cache_ts = 0.0
    _fail_cache = {}

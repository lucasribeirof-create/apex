"""
Timing DCA — RSI(14) + MA50 para ajuste de aporte por ativo.

Camada 3 do DCA Inteligente (Edelson / Value Averaging):
  - RSI < 30 → mercado sobrevendido → multiplicar aporte
  - RSI > 75 → mercado sobrecomprado → reduzir/acumular caixa tático
  - Abaixo da MA50 → confirmação de desconto → bônus extra

Tabela de multiplicadores:
  RSI       | Abaixo MA50 | Acima MA50
  ----------|-------------|----------
  < 30      | 2.00x       | 1.50x
  30 – 45   | 1.50x       | 1.25x
  45 – 65   | 1.00x       | 1.00x
  65 – 75   | 0.75x       | 0.50x
  > 75      | 0.50x       | 0.00x
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import yfinance as yf

logger = logging.getLogger(__name__)

# ─── Cache simples em memória (TTL 5 min) ─────────────────────────────────

_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 300  # segundos


def _cache_get(ticker: str) -> Optional[dict]:
    entry = _cache.get(ticker)
    if entry and (time.time() - entry[0]) < _CACHE_TTL:
        return entry[1]
    return None


def _cache_set(ticker: str, data: dict) -> None:
    _cache[ticker] = (time.time(), data)


# ─── RSI ──────────────────────────────────────────────────────────────────

def calcular_rsi(precos: list[float], periodo: int = 14) -> Optional[float]:
    """Calcula RSI(periodo) a partir de lista de preços de fechamento."""
    if len(precos) < periodo + 1:
        return None
    deltas = [precos[i] - precos[i - 1] for i in range(1, len(precos))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:periodo]) / periodo
    avg_loss = sum(losses[:periodo]) / periodo

    for i in range(periodo, len(gains)):
        avg_gain = (avg_gain * (periodo - 1) + gains[i]) / periodo
        avg_loss = (avg_loss * (periodo - 1) + losses[i]) / periodo

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


# ─── Multiplicador ────────────────────────────────────────────────────────

def _multiplicador(rsi: float, abaixo_ma50: bool) -> float:
    """Retorna multiplicador de aporte baseado em RSI + posição vs MA50."""
    if rsi < 30:
        return 2.00 if abaixo_ma50 else 1.50
    elif rsi < 45:
        return 1.50 if abaixo_ma50 else 1.25
    elif rsi < 65:
        return 1.00
    elif rsi < 75:
        return 0.75 if abaixo_ma50 else 0.50
    else:
        return 0.50 if abaixo_ma50 else 0.00


def _sinal_texto(rsi: float, abaixo_ma50: bool, mult: float) -> str:
    """Gera texto descritivo do sinal de timing."""
    if mult >= 1.5:
        sinal = "COMPRA FORTE"
    elif mult > 1.0:
        sinal = "COMPRA"
    elif mult == 1.0:
        sinal = "NEUTRO"
    elif mult > 0:
        sinal = "CAUTELA"
    else:
        sinal = "ACUMULAR CAIXA"

    ma_txt = "abaixo MA50" if abaixo_ma50 else "acima MA50"
    return f"{sinal} — RSI {rsi:.0f}, {ma_txt} ({mult:.2f}x)"


# ─── Cálculo principal ───────────────────────────────────────────────────

def calcular_timing_dca(ticker: str) -> dict:
    """
    Busca histórico via yfinance e retorna dados de timing para o ativo.

    Returns:
        {
            "rsi14": float | None,
            "ma50": float | None,
            "preco": float | None,
            "abaixo_ma50": bool,
            "multiplicador": float,
            "sinal": str,
        }
    """
    cached = _cache_get(ticker)
    if cached:
        return cached

    default = {
        "rsi14": None,
        "ma50": None,
        "preco": None,
        "abaixo_ma50": False,
        "multiplicador": 1.0,
        "sinal": "NEUTRO — sem dados",
    }

    try:
        # Precisamos de ~70 dias para MA50 + RSI14
        # Ativos brasileiros precisam do sufixo .SA para yfinance
        yf_ticker = ticker if "." in ticker else f"{ticker}.SA"
        tk = yf.Ticker(yf_ticker)
        hist = tk.history(period="4mo", auto_adjust=True)
        if hist.empty or len(hist) < 30:
            _cache_set(ticker, default)
            return default

        closes = hist["Close"].tolist()
        preco_atual = closes[-1]

        # MA50
        ma50 = None
        abaixo_ma50 = False
        if len(closes) >= 50:
            ma50 = round(sum(closes[-50:]) / 50, 2)
            abaixo_ma50 = preco_atual < ma50

        # RSI14
        rsi14 = calcular_rsi(closes, 14)

        if rsi14 is not None:
            mult = _multiplicador(rsi14, abaixo_ma50)
            sinal = _sinal_texto(rsi14, abaixo_ma50, mult)
        else:
            mult = 1.0
            sinal = "NEUTRO — RSI indisponível"

        result = {
            "rsi14": rsi14,
            "ma50": ma50,
            "preco": round(preco_atual, 2),
            "abaixo_ma50": abaixo_ma50,
            "multiplicador": mult,
            "sinal": sinal,
        }
        _cache_set(ticker, result)
        return result

    except Exception as e:
        logger.warning(f"Timing DCA falhou para {ticker}: {e}")
        _cache_set(ticker, default)
        return default

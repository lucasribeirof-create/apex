"""
Scanner APEX — varredura completa do universo de ativos.

Fluxo por ativo:
  yFinance OHLCV (1y, .SA suffix) → 5 filtros sequenciais → score 0-100
  Score ≥ 75 → trade: entry, stop, alvo, sizing
  Score 50-74 → monitor
  Score < 50  → out

Resultado cacheado por 4h (scan é custoso: ~80 downloads).
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.core.filters import aplicar_filtros
from app.core.score import calcular_score, calcular_atr, calcular_sizing
from app.core.regime import calcular_regime
from app.core.universe import get_universe, get_setor_proxy
from app.data.yfinance_client import get_history_global
from app.data.cache import cache

# TTL do scan completo: 4 horas
_CACHE_TTL_SCAN = 4 * 3600

# Semáforo lazy — criado no primeiro uso, dentro do event loop
_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    """Retorna o semáforo, criando-o se necessário (lazy — garante event loop ativo)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(8)  # máximo 8 downloads yFinance simultâneos
    return _semaphore


# ─── Helpers de dados ────────────────────────────────────────────────────────

async def _fetch_br(ticker: str, period: str = "1y") -> Optional[list]:
    """
    Busca histórico de ativo B3 via yFinance.
    Adiciona sufixo .SA automaticamente (PETR4 → PETR4.SA).
    Índices (^BVSP) e tickers já com .SA passam direto.
    """
    if ticker.startswith("^") or "." in ticker:
        ticker_yf = ticker
    else:
        ticker_yf = ticker + ".SA"

    async with _get_semaphore():
        return await get_history_global(ticker_yf, period=period)


def _extrair_series(records: list[dict]) -> tuple[list, list, list, list]:
    """Extrai closes, highs, lows, volumes de uma lista de records OHLCV."""
    closes  = [r["close"]  for r in records]
    highs   = [r["high"]   for r in records]
    lows    = [r["low"]    for r in records]
    volumes = [r["volume"] for r in records]
    return closes, highs, lows, volumes


def _retorno_63d(closes: list[float]) -> float:
    """Retorno percentual nos últimos 63 pregões (≈ 3 meses úteis)."""
    if len(closes) < 64:
        return 0.0
    return (closes[-1] / closes[-64] - 1) * 100


def _motivo_falha(filtros: list[dict], filtro_falhou: Optional[int]) -> str:
    nomes = {
        1: "Preço abaixo da MM200 (ou < 10 pregões consecutivos acima)",
        2: "MM50 não alinhada acima da MM200 com inclinação positiva",
        3: "Sem rompimento da máxima dos últimos 60 dias",
        4: "Volume insuficiente (< 50% acima da média de 20d)",
        5: "Setor sem força relativa positiva vs IBOV nos últimos 63d",
    }
    return nomes.get(filtro_falhou, "Dados insuficientes") if filtro_falhou else "Dados insuficientes"


# ─── Análise por ativo ────────────────────────────────────────────────────────

async def _analisar_ativo(
    ativo: dict,
    retorno_ibov_63d: float,
    proxies_63d: dict[str, float],
    patrimonio: float,
    risco_pct: float,
) -> dict:
    """
    Analisa um ativo completo:
    busca histórico → extrai séries → aplica 5 filtros → calcula score → gera trade setup.
    """
    ticker = ativo["ticker"]
    setor  = ativo.get("setor", "outro")
    base   = {
        "ticker":  ticker,
        "nome":    ativo.get("nome", ticker),
        "tipo":    ativo.get("tipo"),
        "setor":   setor,
    }

    # Mínimo de 210 registros para cobrir MM200 + folga
    records = await _fetch_br(ticker)
    if not records or len(records) < 210:
        return {**base, "score": 0, "classificacao": "out",
                "motivo": "Histórico insuficiente (< 210 pregões)", "filtros": []}

    closes, highs, lows, volumes = _extrair_series(records)
    preco_atual = closes[-1]

    # Força relativa setorial — Filtro 5
    proxy          = get_setor_proxy(setor)
    retorno_setor  = proxies_63d.get(proxy, retorno_ibov_63d)  # fallback para IBOV

    # ── Aplicar os 5 filtros sequenciais ─────────────────────────────────────
    resultado = aplicar_filtros(
        closes=closes,
        highs=highs,
        volumes=volumes,
        retorno_setor_63d=retorno_setor,
        retorno_ibov_63d=retorno_ibov_63d,
    )

    if not resultado["aprovado"]:
        filtro_falhou = resultado.get("filtro_falhou")
        # Score parcial: 1 ponto por filtro passado (apenas para ordenação interna)
        score_parcial = sum(1 for f in resultado["filtros"] if f.get("passou")) * 9
        return {
            **base,
            "preco":        round(preco_atual, 2),
            "score":        min(score_parcial, 49),
            "classificacao": "out",
            "filtro_falhou": filtro_falhou,
            "motivo":       _motivo_falha(resultado["filtros"], filtro_falhou),
            "filtros":      resultado["filtros"],
        }

    # ── Passou todos os filtros → score real ─────────────────────────────────
    score = calcular_score(resultado["filtros"])
    atr   = calcular_atr(highs, lows, closes)

    # Trade setup: só para score ≥ 75 com patrimônio e ATR válidos
    trade_setup = None
    if score >= 75 and atr and patrimonio > 0:
        trade_setup = calcular_sizing(
            patrimonio=patrimonio,
            preco_entrada=preco_atual,
            atr=atr,
            risco_por_trade_pct=risco_pct,
        )

    return {
        **base,
        "preco":         round(preco_atual, 2),
        "score":         score,
        "classificacao": "trade" if score >= 75 else "monitor",
        "filtros":       resultado["filtros"],
        "trade_setup":   trade_setup,
        "atr":           round(atr, 2) if atr else None,
    }


# ─── Scan completo ────────────────────────────────────────────────────────────

async def executar_scan(
    patrimonio: float = 100_000.0,
    estrategia: str = "CORE",
    tipos: Optional[list[str]] = None,
    forcar_atualizacao: bool = False,
) -> dict:
    """
    Executa a varredura completa do universo APEX.

    Args:
        patrimonio:         valor do portfólio para calcular sizing (default 100k)
        estrategia:         CORE (risco 1%/trade) | ALPHA (risco 1.5%/trade)
        tipos:              ["ACAO"] | ["ETF"] | ["FII"] | None = todos
        forcar_atualizacao: ignora cache e refaz o scan

    Returns:
        {
          trades:           [...],   # score ≥ 75, com trade_setup completo
          monitor:          [...],   # score 50-74
          out:              [...],   # score < 50 ou falhou filtro
          regime:           str,     # BULL | MISTO | BEAR
          regime_motivo:    str,
          total_analisados: int,
          timestamp:        str,
        }
    """
    tipos_key   = ",".join(sorted(tipos)) if tipos else "ALL"
    cache_key   = f"scanner:scan:{estrategia}:{tipos_key}"

    if not forcar_atualizacao:
        cached = cache.get(cache_key)
        if cached:
            return cached

    risco_pct = 1.5 if estrategia == "ALPHA" else 1.0
    universe  = get_universe(tipos)

    # ── 1. IBOV: regime + benchmark setorial ─────────────────────────────────
    ibov_records = await _fetch_br("^BVSP", period="1y")
    if ibov_records and len(ibov_records) >= 200:
        ibov_closes      = [r["close"] for r in ibov_records]
        retorno_ibov_63d = _retorno_63d(ibov_closes)
        regime_resultado = calcular_regime(ibov_closes)
    else:
        ibov_closes      = []
        retorno_ibov_63d = 0.0
        regime_resultado = {"regime": "MISTO", "motivo": "Dados IBOV insuficientes", "detalhes": {}}

    regime_str = (
        regime_resultado["regime"].value
        if hasattr(regime_resultado["regime"], "value")
        else str(regime_resultado["regime"])
    )

    # ── 2. Proxies setoriais: busca histórico único por setor ─────────────────
    setores_presentes   = {a.get("setor", "outro") for a in universe}
    proxies_necessarios = {get_setor_proxy(s) for s in setores_presentes}
    proxies_necessarios.discard("^BVSP")  # IBOV já foi buscado

    async def _retorno_proxy(proxy: str) -> tuple[str, float]:
        records = await _fetch_br(proxy)
        if records and len(records) >= 64:
            return proxy, _retorno_63d([r["close"] for r in records])
        return proxy, retorno_ibov_63d  # fallback: usa retorno do IBOV

    proxy_resultados = await asyncio.gather(*[_retorno_proxy(p) for p in proxies_necessarios])
    proxies_63d: dict[str, float] = dict(proxy_resultados)

    # ── 3. Análise de todos os ativos em paralelo ─────────────────────────────
    tasks      = [
        _analisar_ativo(ativo, retorno_ibov_63d, proxies_63d, patrimonio, risco_pct)
        for ativo in universe
    ]
    resultados = await asyncio.gather(*tasks)

    # ── 4. Classificação e ordenação ─────────────────────────────────────────
    trades  = sorted([r for r in resultados if r["score"] >= 75],  key=lambda x: x["score"], reverse=True)
    monitor = sorted([r for r in resultados if 50 <= r["score"] < 75], key=lambda x: x["score"], reverse=True)
    out     = sorted([r for r in resultados if r["score"] < 50], key=lambda x: x["score"], reverse=True)

    resultado_final = {
        "trades":           trades,
        "monitor":          monitor,
        "out":              out,
        "regime":           regime_str,
        "regime_motivo":    regime_resultado.get("motivo", ""),
        "total_analisados": len(resultados),
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    }

    cache.set(cache_key, resultado_final, ttl=_CACHE_TTL_SCAN)
    return resultado_final

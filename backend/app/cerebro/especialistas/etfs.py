"""
APEX Motor — ETFs (IA-Driven)

Motor de seleção de ETFs da B3 usando análise MACRO + IA.

Filosofia:
  ETFs são o NÚCLEO ESTRATÉGICO do portfólio — diversificação instantânea,
  baixo custo, exposição a teses macro. A seleção NÃO é fixa: depende do
  cenário global (dólar, juros, commodities, tendências setoriais).

Fluxo:
  1. Busca preços reais de ~35 ETFs do universo expandido (ETFS_UNIVERSE)
  2. Pre-filtra: remove sem preço ou sem liquidez
  3. Envia candidatos enriquecidos + macro para IA especialista
  4. IA seleciona 3-6 ETFs com pesos baseados em análise macro
  5. Fallback: alocação por perfil se IA não disponível

O cérebro é UM SÓ — usa APEX_BRAIN + expertise de ETFs para pensar como
um gestor que analisa macro, prevê tendências e escolhe a melhor composição.
"""

import asyncio
import logging
from typing import Optional

import yfinance as yf

from app.cerebro.especialistas import SugestaoMotor
from app.cerebro.especialistas import prefetch as _pf
from app.cerebro.especialistas.watchlist import ETFS_UNIVERSE

logger = logging.getLogger("apex.motor_etfs")

# ── Fallback estático (usado quando IA não está configurada) ─────────────────
_PERFIL_ALOCACAO_FALLBACK = {
    "ALPHA": [("BOVA11", 0.35), ("IVVB11", 0.35), ("SMAL11", 0.20), ("NASD11", 0.10)],
    "RENDA": [("BOVA11", 0.40), ("DIVO11", 0.30), ("IVVB11", 0.20), ("IMAB11", 0.10)],
    "CORE":  [("BOVA11", 0.50), ("IVVB11", 0.30), ("SMAL11", 0.20)],
    "CUSTOM": [("BOVA11", 0.45), ("IVVB11", 0.35), ("SMAL11", 0.20)],
}


def _fetch_preco(ticker: str) -> Optional[float]:
    """Busca preço via prefetch ou yfinance direto."""
    p = _pf.get_preco(ticker)
    if p is not None:
        return p
    try:
        t = yf.Ticker(ticker + ".SA")
        hist = t.history(period="5d", auto_adjust=True)
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def _construir_fallback(capital: float, estrategia: str) -> list[SugestaoMotor]:
    """Fallback algorítmico: alocação estática por perfil (comportamento antigo)."""
    alocacao = _PERFIL_ALOCACAO_FALLBACK.get(estrategia, _PERFIL_ALOCACAO_FALLBACK["CORE"])
    saida: list[SugestaoMotor] = []
    for ticker, pct in alocacao:
        preco = _fetch_preco(ticker)
        if not preco or preco <= 0:
            continue
        capital_etf = capital * pct
        qtd = max(1, int(capital_etf / preco))
        valor = round(qtd * preco, 2)
        meta = ETFS_UNIVERSE.get(ticker, {})
        saida.append(SugestaoMotor(
            modulo="etfs", ticker=ticker,
            nome=meta.get("nome", ticker), tipo="ETF",
            quantidade=float(qtd), preco_atual=round(preco, 2),
            valor_total=valor, score=pct * 100,
            justificativa=f"Alocação padrão {pct*100:.0f}% para perfil {estrategia} (fallback sem IA).",
            dados_extras={"peso_alocacao_pct": pct * 100, "taxa_adm_aa": meta.get("taxa_adm", 0.5), "perfil": estrategia},
        ))
    return saida


async def rodar(
    capital: float,
    estrategia: str = "CORE",
    n_ativos: Optional[int] = None,
    macro_context: Optional[object] = None,
) -> list[SugestaoMotor]:
    """
    Seleciona os melhores ETFs usando IA + análise macro.

    Args:
        capital:       Capital disponível para o módulo ETFs.
        estrategia:    Estratégia do perfil (CORE | ALPHA | RENDA | CUSTOM).
        n_ativos:      Número desejado de ETFs (padrão: 4-6).
        macro_context: MacroContext com dados macro reais (regime, Selic, VIX, etc.)

    Returns:
        Lista de SugestaoMotor, um por ETF selecionado pela IA.
    """
    if capital < 500:
        return []

    estrategia = (estrategia or "CORE").upper()
    n_ativos = n_ativos or (5 if estrategia == "ALPHA" else 4)

    # ── Step 1: Buscar preços de TODOS os ETFs do universo ────────────────
    tickers = list(ETFS_UNIVERSE.keys())
    tarefas = [asyncio.to_thread(_fetch_preco, t) for t in tickers]
    precos = await asyncio.gather(*tarefas, return_exceptions=True)

    # ── Step 2: Construir candidatos enriched ─────────────────────────────
    candidatos_enriched: list[dict] = []
    for ticker, preco in zip(tickers, precos):
        if not isinstance(preco, (int, float)) or preco is None or preco <= 0:
            continue
        meta = ETFS_UNIVERSE[ticker]
        candidatos_enriched.append({
            "ticker": ticker,
            "nome": meta["nome"],
            "tipo": "ETF",
            "preco": round(float(preco), 2),
            "exposicao": meta["exposicao"],
            "taxa_adm": meta["taxa_adm"],
            "categoria": meta["categoria"],
            "dados_extras": {
                "taxa_adm_aa": meta["taxa_adm"],
                "categoria": meta["categoria"],
                "exposicao": meta["exposicao"],
            },
        })

    if not candidatos_enriched:
        logger.warning("motor_etfs: nenhum ETF com preço — usando fallback")
        return _construir_fallback(capital, estrategia)

    # ── Step 3: Construir fallback (para graceful degradation) ────────────
    fallback = _construir_fallback(capital, estrategia)

    # ── Step 4: Obter resumo macro ────────────────────────────────────────
    macro_resumo = ""
    if macro_context and hasattr(macro_context, "resumo_texto"):
        macro_resumo = macro_context.resumo_texto()
    else:
        try:
            from app.cerebro.macro import montar_macro
            ctx = await montar_macro()
            macro_resumo = ctx.resumo_texto()
        except Exception:
            macro_resumo = "Dados macro indisponíveis."

    # ── Step 5: Chamar IA especialista ────────────────────────────────────
    from app.cerebro.especialistas._ai_motor import selecionar_com_ia
    from app.cerebro.prompts import build_motor_prompt

    resultado = await selecionar_com_ia(
        modulo="etfs",
        candidatos_enriched=candidatos_enriched,
        macro_resumo=macro_resumo,
        estrategia=estrategia,
        capital=capital,
        motor_system_prompt=build_motor_prompt("etfs"),
        n_ativos=n_ativos,
        max_tokens=3000,
        fallback_candidatos=fallback,
    )

    return resultado if resultado else fallback

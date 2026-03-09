"""
Narrativa Macro — Texto denso diário gerado pela IA.

Substitui a ideia de "cenários com probabilidades" (LLMs não atribuem
probabilidades de forma confiável). Em vez disso, gera um texto analítico
de 500-800 palavras sobre o contexto macro e como afeta o portfólio.

Cache de 12h — atualiza 1x por dia útil ou sob demanda.
Custo estimado: ~$0.05/geração = ~$1.50/mês.
"""

from __future__ import annotations

from datetime import datetime

from app.data.cache import cache
from app.cerebro.prompts import build_narrativa_prompt
from app.logger import logger

CACHE_TTL_NARRATIVA = 43200  # 12h


_SYSTEM_NARRATIVA = build_narrativa_prompt()


async def gerar_narrativa(macro_context, regime_info=None, posicoes_resumo: str = "") -> str:
    """
    Gera a narrativa macro diária.

    Args:
        macro_context: MacroContext com dados completos
        regime_info: RegimeInfo com regime + sinais + flags
        posicoes_resumo: texto resumido da carteira (opcional)
    """
    key = "cerebro:narrativa:diaria"
    cached = cache.get(key)
    if cached:
        return cached

    from app.cerebro.client import chat

    user_content = f"DATA: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    user_content += "=== DADOS MACRO ===\n"
    user_content += macro_context.resumo_texto()

    if regime_info:
        user_content += f"\n\n=== REGIME DE MERCADO ===\n"
        user_content += regime_info.resumo_texto()

    if posicoes_resumo:
        user_content += f"\n\n=== CARTEIRA ATUAL (RESUMO) ===\n{posicoes_resumo}"

    user_content += "\n\nEscreva a NARRATIVA MACRO seguindo a estrutura definida."

    try:
        narrativa = await chat(
            system=_SYSTEM_NARRATIVA,
            messages=[{"role": "user", "content": user_content}],
            max_tokens=1500,
        )
        if narrativa:
            cache.set(key, narrativa, ttl=CACHE_TTL_NARRATIVA)
            return narrativa
    except Exception as e:
        logger.error("narrativa.gerar_narrativa falhou: %s", e)

    return _fallback_narrativa(macro_context)


def _fallback_narrativa(macro_context) -> str:
    """Narrativa básica sem IA — dados crus formatados."""
    mc = macro_context
    partes = ["NARRATIVA MACRO (modo offline — dados crus)\n"]

    partes.append("GLOBAL:")
    if mc.vix is not None:
        nivel = "pânico" if mc.vix > 35 else "elevado" if mc.vix > 25 else "controlado"
        partes.append(f"  VIX em {mc.vix:.1f} ({nivel})")
    if mc.treasury_10y is not None:
        partes.append(f"  Treasury 10Y em {mc.treasury_10y:.2f}%")
    if mc.dxy is not None:
        partes.append(f"  DXY em {mc.dxy:.2f}")
    if mc.petroleo_wti is not None:
        partes.append(f"  Petróleo WTI em ${mc.petroleo_wti:.2f}")

    partes.append("\nBRASIL:")
    if mc.selic is not None:
        partes.append(f"  Selic Meta: {mc.selic:.2f}%")
    if mc.juro_real is not None:
        nivel = "alto" if mc.juro_real > 6 else "moderado" if mc.juro_real > 3 else "baixo"
        partes.append(f"  Juro Real: {mc.juro_real:.2f}% ({nivel})")
    if mc.ibov is not None:
        partes.append(f"  IBOV: {mc.ibov:,.0f}")

    return "\n".join(partes)

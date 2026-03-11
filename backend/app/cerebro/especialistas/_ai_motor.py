"""
APEX Motor — Camada de IA para Motores Especialistas

Módulo compartilhado que permite a QUALQUER motor usar IA para selecionar ativos.
O cérebro é UM SÓ — cada motor herda APEX_BRAIN + expertise específica do módulo.

Fluxo:
  Dados reais (preço, fundamentals, técnico) → Pre-filtro algorítmico →
  IA Especialista (APEX_BRAIN + motor_prompt) → Seleção inteligente →
  list[SugestaoMotor]

Se IA falhar (sem chave, timeout, erro), retorna fallback algorítmico.
"""

import json
import re
import logging
from typing import Optional

from app.cerebro.especialistas import SugestaoMotor

logger = logging.getLogger("apex.motor_ia")


async def selecionar_com_ia(
    *,
    modulo: str,
    candidatos_enriched: list[dict],
    macro_resumo: str,
    estrategia: str,
    capital: float,
    motor_system_prompt: str,
    n_ativos: int = 5,
    max_tokens: int = 3000,
    fallback_candidatos: Optional[list[SugestaoMotor]] = None,
) -> list[SugestaoMotor]:
    """
    Usa IA para selecionar os melhores ativos de um pool de candidatos enriched.

    Args:
        modulo:               Nome do módulo (etfs, fiis, alpha, etc.)
        candidatos_enriched:  Lista de dicts com dados reais de cada candidato
        macro_resumo:         Texto do MacroContext.resumo_texto()
        estrategia:           Perfil do investidor (CORE, ALPHA, RENDA, CUSTOM)
        capital:              Capital disponível para este módulo
        motor_system_prompt:  System prompt = APEX_BRAIN + expertise do motor
        n_ativos:             Número desejado de ativos
        max_tokens:           Limite de tokens da resposta IA
        fallback_candidatos:  SugestaoMotor list para retornar se IA falhar

    Returns:
        list[SugestaoMotor] — seleção da IA, ou fallback algorítmico
    """
    from app.cerebro.client import chat, is_ai_configured

    if not is_ai_configured():
        logger.info("motor_%s: IA não configurada — usando fallback algorítmico", modulo)
        return fallback_candidatos or []

    # ── Montar USER prompt ────────────────────────────────────────────────
    user_msg = (
        f"MÓDULO: {modulo.upper()}\n"
        f"ESTRATÉGIA DO INVESTIDOR: {estrategia}\n"
        f"CAPITAL DISPONÍVEL: R$ {capital:,.2f}\n"
        f"NÚMERO DESEJADO DE ATIVOS: {n_ativos}\n\n"
        f"{macro_resumo}\n\n"
        f"=== CANDIDATOS DISPONÍVEIS ({len(candidatos_enriched)} ativos) ===\n"
        f"{json.dumps(candidatos_enriched, ensure_ascii=False, indent=2)}\n\n"
        "Com base no contexto macro, na estratégia do investidor e nos dados reais acima, "
        f"selecione os {n_ativos} melhores ativos para este módulo.\n\n"
        "Responda EXCLUSIVAMENTE em JSON válido, sem markdown, no formato:\n"
        "{\n"
        '  "selecionados": [\n'
        "    {\n"
        '      "ticker": "XXXX11",\n'
        '      "peso_pct": 30,\n'
        '      "justificativa": "3-5 linhas detalhadas com dados concretos"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "REGRAS:\n"
        "- peso_pct é a % do capital deste módulo (soma deve ser ~100)\n"
        "- justificativa DEVE citar dados concretos dos candidatos (preço, DY, P/L, etc.)\n"
        "- Escolha com base em ANÁLISE MACRO + FUNDAMENTALISTA + papel no portfólio\n"
        "- Se nenhum candidato for bom, retorne lista vazia com justificativa"
    )

    try:
        resposta_raw = await chat(
            system=motor_system_prompt,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=max_tokens,
        )
        return _parsear_resposta_ia(
            resposta_raw=resposta_raw,
            modulo=modulo,
            candidatos_enriched=candidatos_enriched,
            capital=capital,
        )
    except Exception as e:
        logger.warning("motor_%s: IA falhou (%s) — usando fallback algorítmico", modulo, e)
        return fallback_candidatos or []


def _parsear_resposta_ia(
    resposta_raw: str,
    modulo: str,
    candidatos_enriched: list[dict],
    capital: float,
) -> list[SugestaoMotor]:
    """Parseia a resposta JSON da IA e constrói list[SugestaoMotor]."""

    # Limpa markdown code fences se presentes
    texto = resposta_raw.strip()
    texto = re.sub(r"^```(?:json)?\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)

    try:
        data = json.loads(texto)
    except json.JSONDecodeError:
        # Tenta extrair JSON de texto misto
        match = re.search(r"\{[\s\S]*\}", texto)
        if match:
            data = json.loads(match.group(0))
        else:
            logger.warning("motor_%s: resposta IA não é JSON válido", modulo)
            return []

    selecionados = data.get("selecionados", [])
    if not selecionados:
        return []

    # Mapa ticker → dados enriched para lookup rápido
    cand_map = {c["ticker"]: c for c in candidatos_enriched}

    saida: list[SugestaoMotor] = []
    for item in selecionados:
        ticker = item.get("ticker", "").upper()
        peso_pct = float(item.get("peso_pct", 0))
        justificativa = item.get("justificativa", "")

        if not ticker or peso_pct <= 0:
            continue

        cand = cand_map.get(ticker)
        if not cand:
            logger.debug("motor_%s: IA selecionou %s que não está nos candidatos — ignorando", modulo, ticker)
            continue

        preco = cand.get("preco", 0)
        if not preco or preco <= 0:
            continue

        capital_ativo = capital * peso_pct / 100
        tipo = cand.get("tipo", "ETF")

        # Para RF, quantidade = valor nominal
        if tipo == "RF":
            qtd = capital_ativo
        else:
            qtd = max(1, int(capital_ativo / preco))

        valor = round(qtd * preco, 2) if tipo != "RF" else round(capital_ativo, 2)

        saida.append(SugestaoMotor(
            modulo=modulo,
            ticker=ticker,
            nome=cand.get("nome", ticker),
            tipo=tipo,
            quantidade=float(qtd),
            preco_atual=round(preco, 2) if tipo != "RF" else 1.0,
            valor_total=valor,
            justificativa=justificativa,
            score=peso_pct,
            dados_extras=cand.get("dados_extras", {}),
        ))

    return saida

"""
APEX Motor — Renda Fixa

Motor de alocação em renda fixa brasileira.

Filosofia:
  Renda fixa NÃO é "jogar dinheiro na Selic e esquecer" — é uma alocação
  estratégica baseada na curva de juros, expectativas de inflação e duração.

Lógica de alocação:
  A carteira RF é dividida em 3 vértices conforme o cenário macro:

  1. SELIC (pós-fixado) — liquidez e carregamento no juro curto
     Usar quando: taxa alta + incerteza + precisa de liquidez
     Instrumentos: Tesouro Selic, CDB DI, LCI/LCA DI

  2. IPCA+ (indexado inflação, médio prazo) — proteção real
     Usar quando: IPCA elevado ou perspectiva de inflação persistente
     Instrumentos: Tesouro IPCA+, CRI/CRA IPCA

  3. PREFIXADO (longo prazo) — captura de taxa alta ao travar
     Usar quando: ciclo de queda de juros se aproximando (taxa pré elevada)
     Instrumentos: Tesouro Prefixado, CDB Pré, LCI/LCA Pré

Parâmetros macro (atualizar conforme Copom/Focus):
  Selic atual: 13.75% a.a.
  IPCA 12m: 4.8%
  IPCA Focus (12m à frente): 4.5%
  Curva pré (LTN 2yr): 13.1%

Mix base por cenário:
  Ciclo de alta (como agora): 60% SELIC | 30% IPCA+ | 10% PRÉ
  Ciclo de corte (previsto):  30% SELIC | 40% IPCA+ | 30% PRÉ
"""

import asyncio
import logging
from typing import Optional, Dict

from app.cerebro.especialistas import SugestaoMotor
from app.data.bcb_client import get_selic, get_ipca

logger = logging.getLogger("apex.motor_rf")

# ── Constantes FALLBACK (usadas SOMENTE quando BCB offline) ──────────────────
_SELIC_FALLBACK = 14.75   # % a.a. — atualizar periodicamente
_IPCA_FALLBACK  = 5.5     # % acumulado 12m
_PRE_2Y_FALLBACK = 14.5   # % taxa prefixada LTN 2 anos

# ── Cenário atual: Selic em patamar elevado, cortes previstos para 2026 ──────
# Mix: mais SELIC por ora, IPCA como proteção, pouco PRÉ até ciclo de corte iniciar
_MIX_BASE = {
    "RF-SELIC": 0.60,
    "RF-IPCA":  0.30,
    "RF-PRE":   0.10,
}

# Info estática (nomes, descrições) — taxas são resolvidas em rodar() com dados live
_RF_INFO = {
    "RF-SELIC": {
        "nome":          "Renda Fixa — Pós-Fixado (Selic)",
        "tipo":          "RF",
        "descricao":     "Tesouro Selic / CDB DI / LCI DI",
        "liquidez":      "D+0 a D+1 (alta liquidez)",
        "risco":         "baixíssimo — soberano",
    },
    "RF-IPCA": {
        "nome":          "Renda Fixa — IPCA+ (indexado inflação)",
        "tipo":          "RF",
        "descricao":     "Tesouro IPCA+ 2029 / CRI IPCA / CRA IPCA",
        "liquidez":      "D+2 (via mercado secundário ou vencimento)",
        "risco":         "baixo — soberano ou crédito high grade",
    },
    "RF-PRE": {
        "nome":          "Renda Fixa — Prefixado",
        "tipo":          "RF",
        "descricao":     "Tesouro Prefixado 2027 / CDB Pré / LCA Pré",
        "liquidez":      "D+2 (via mercado secundário ou vencimento)",
        "risco":         "baixo — soberano | risco de marcação a mercado",
    },
}


def _justificativa_rf(ticker: str, pct: float, selic_atual: float,
                      ipca_focus_atual: float, pre_2y: float) -> str:
    info = _RF_INFO[ticker]
    partes = []

    if ticker == "RF-SELIC":
        partes.append(
            f"Pós-fixado Selic {selic_atual:.2f}%/ano é o carrego base da carteira: "
            f"maior taxa em {min(15, int(selic_atual))} anos, sem risco de marcação a mercado"
        )
        partes.append(
            f"alocação de {pct*100:.0f}% mantém liquidez máxima enquanto o ciclo de corte "
            f"não está confirmado pelo Copom"
        )
        partes.append(f"instrumentos: {info['descricao']}")

    elif ticker == "RF-IPCA":
        taxa = round(ipca_focus_atual + 6.5, 2)
        partes.append(
            f"IPCA+ {taxa:.1f}%/ano = IPCA + 6.5% de spread real — "
            f"garante poder de compra independente da inflação"
        )
        partes.append(
            f"com IPCA projetado em {ipca_focus_atual:.1f}% pelo Focus, a taxa real supera a Selic bruta "
            f"em cenário de inflação acima do teto da meta"
        )
        partes.append(f"instrumentos: {info['descricao']}")

    else:  # PRÉ
        partes.append(
            f"Prefixado {pre_2y:.1f}%/ano trava a taxa atual: para cada R$100 aplicados, "
            f"você sabe exatamente quanto terá no vencimento"
        )
        partes.append(
            f"alocação menor ({pct*100:.0f}%) pois cortes de Selic ainda não iniciados — "
            f"aumentar quando ciclo de corte estiver confirmado (prefixado valoriza com queda de juros)"
        )
        partes.append(f"instrumentos: {info['descricao']}")

    return ". ".join(partes) + "."


async def rodar(
    capital: float,
    mix: Optional[Dict[str, float]] = None,
    estrategia: str = "CORE",
    n_ativos: int = 3,
    macro_context: object | None = None,
) -> list[SugestaoMotor]:
    """
    Aloca o capital em renda fixa com IA decidindo o mix SELIC/IPCA+/PRÉ.

    A IA analisa: ciclo Selic, IPCA projetado, curva de juros, regime macro.
    Fallback: mix estático por perfil se IA não disponível.
    """
    if capital < 500:
        return []
    # Busca Selic e IPCA reais do BCB (com fallback para constantes)
    selic_live, ipca_live = await asyncio.gather(
        get_selic(),
        get_ipca(),
        return_exceptions=True,
    )
    selic_atual = float(selic_live) if isinstance(selic_live, (int, float)) else _SELIC_FALLBACK
    ipca_atual  = float(ipca_live)  if isinstance(ipca_live,  (int, float)) else _IPCA_FALLBACK
    ipca_focus_atual = round(ipca_atual * 0.95, 2)
    pre_2y = round(selic_atual + 0.5, 2) if selic_atual > 0 else _PRE_2Y_FALLBACK

    # ── Candidatos RF para IA ─────────────────────────────────────────────
    candidatos_enriched = [
        {
            "ticker": "RF-SELIC", "nome": "Renda Fixa — Pós-Fixado (Selic)", "tipo": "RF",
            "preco": 1.0,
            "taxa_referencia_aa": selic_atual,
            "descricao": "Tesouro Selic / CDB DI / LCI DI",
            "liquidez": "D+0 a D+1 (alta liquidez)",
            "risco": "baixíssimo — soberano",
            "dados_extras": {"taxa_referencia_aa": selic_atual, "liquidez": "D+0 a D+1"},
        },
        {
            "ticker": "RF-IPCA", "nome": "Renda Fixa — IPCA+ (indexado inflação)", "tipo": "RF",
            "preco": 1.0,
            "taxa_referencia_aa": round(ipca_focus_atual + 6.5, 2),
            "descricao": "Tesouro IPCA+ 2029 / CRI IPCA / CRA IPCA",
            "liquidez": "D+2 (via mercado secundário ou vencimento)",
            "risco": "baixo — soberano ou crédito high grade",
            "ipca_projetado": ipca_focus_atual,
            "spread_real": 6.5,
            "dados_extras": {"taxa_referencia_aa": round(ipca_focus_atual + 6.5, 2), "liquidez": "D+2"},
        },
        {
            "ticker": "RF-PRE", "nome": "Renda Fixa — Prefixado", "tipo": "RF",
            "preco": 1.0,
            "taxa_referencia_aa": pre_2y,
            "descricao": "Tesouro Prefixado 2027 / CDB Pré / LCA Pré",
            "liquidez": "D+2 (via mercado secundário ou vencimento)",
            "risco": "baixo — soberano | risco de marcação a mercado",
            "dados_extras": {"taxa_referencia_aa": pre_2y, "liquidez": "D+2"},
        },
    ]

    # ── Fallback estático ─────────────────────────────────────────────────
    fallback_alocacao = mix or dict(_MIX_BASE)
    if estrategia == "RENDA":
        fallback_alocacao = {"RF-SELIC": 0.40, "RF-IPCA": 0.45, "RF-PRE": 0.15}
    elif estrategia == "ALPHA":
        fallback_alocacao = {"RF-SELIC": 0.80, "RF-IPCA": 0.20, "RF-PRE": 0.00}
        fallback_alocacao = {k: v for k, v in fallback_alocacao.items() if v > 0}

    fallback = _construir_saida_rf(fallback_alocacao, capital, selic_atual, ipca_focus_atual, pre_2y)

    # ── Obter resumo macro ────────────────────────────────────────────────
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

    # ── Chamar IA especialista ────────────────────────────────────────────
    from app.cerebro.especialistas._ai_motor import selecionar_com_ia
    from app.cerebro.prompts import build_motor_prompt

    resultado = await selecionar_com_ia(
        modulo="renda_fixa",
        candidatos_enriched=candidatos_enriched,
        macro_resumo=macro_resumo,
        estrategia=estrategia,
        capital=capital,
        motor_system_prompt=build_motor_prompt("renda_fixa"),
        n_ativos=n_ativos,
        max_tokens=2000,
        fallback_candidatos=fallback,
    )

    return resultado if resultado else fallback


def _construir_saida_rf(
    alocacao: dict, capital: float,
    selic_atual: float, ipca_focus_atual: float, pre_2y: float,
) -> list[SugestaoMotor]:
    """Constrói lista SugestaoMotor a partir de uma alocação RF."""
    saida: list[SugestaoMotor] = []

    for ticker, pct in alocacao.items():
        if pct <= 0 or ticker not in _RF_INFO:
            continue

        info   = _RF_INFO[ticker]
        valor  = round(capital * pct, 2)

        if ticker == "RF-SELIC":
            taxa_ref = selic_atual
        elif ticker == "RF-IPCA":
            taxa_ref = round(ipca_focus_atual + 6.5, 2)
        else:
            taxa_ref = pre_2y

        saida.append(SugestaoMotor(
            modulo="renda_fixa",
            ticker=ticker,
            nome=info["nome"],
            tipo="RF",
            quantidade=valor,
            preco_atual=1.0,
            valor_total=valor,
            justificativa=_justificativa_rf(ticker, pct, selic_atual, ipca_focus_atual, pre_2y),
            score=pct * 100,
            dados_extras={
                "taxa_referencia_aa": taxa_ref,
                "peso_pct": pct * 100,
                "descricao": info["descricao"],
                "liquidez": info["liquidez"],
                "risco": info["risco"],
                "rendimento_mensal_est": round(valor * taxa_ref / 100 / 12, 2),
                "rendimento_anual_est": round(valor * taxa_ref / 100, 2),
                "selic_atual": selic_atual,
                "ipca_focus_12m": ipca_focus_atual,
            },
        ))

    return saida

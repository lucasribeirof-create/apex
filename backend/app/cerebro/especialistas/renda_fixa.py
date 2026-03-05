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
from typing import Optional, Dict

from app.cerebro.especialistas import SugestaoMotor
from app.data.bcb_client import get_selic, get_ipca
from app.cerebro.focus_bcb import get_focus_ipca, get_focus_selic
from app.logger import logger

# Sem fallbacks hardcoded — se BCB offline e sem last_known, o motor retorna []

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
        partes.append(
            f"IPCA+ indexado à inflação (IPCA projetado: {ipca_focus_atual:.1f}%) — "
            f"garante poder de compra independente da inflação"
        )
        partes.append(
            f"com IPCA Focus em {ipca_focus_atual:.1f}%, o rendimento real protege o patrimônio "
            f"contra cenários de inflação acima da meta"
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
) -> list[SugestaoMotor]:
    """
    Aloca o capital em renda fixa seguindo o mix adequado ao cenário.

    Args:
        capital:    Capital em R$ disponível para o módulo Renda Fixa.
        mix:        Sobrescreve o mix padrão ({ticker: pct}) — soma deve ser 1.0.
        estrategia: Perfil do investidor (RENDA prioriza IPCA+; ALPHA reduz RF).
        n_ativos:   Máximo de vértices (padrão: 3 — SELIC, IPCA, PRÉ).

    Returns:
        Lista de SugestaoMotor, um por vértice de renda fixa.
    """
    if capital < 500:
        return []
    selic_live, ipca_live, focus_ipca_live, focus_selic_live = await asyncio.gather(
        get_selic(),
        get_ipca(),
        get_focus_ipca(),
        get_focus_selic(),
        return_exceptions=True,
    )
    # Selic e IPCA REAIS — se indisponíveis, motor não opera
    if not isinstance(selic_live, (int, float)) or selic_live is None:
        logger.error("renda_fixa: Selic BCB totalmente indisponível — motor não pode operar sem dados reais")
        return []
    if not isinstance(ipca_live, (int, float)) or ipca_live is None:
        logger.error("renda_fixa: IPCA BCB totalmente indisponível — motor não pode operar sem dados reais")
        return []

    selic_atual = float(selic_live)
    ipca_atual = float(ipca_live)

    # IPCA Focus real via API Olinda (mediana Top 5 analistas)
    if isinstance(focus_ipca_live, (int, float)) and focus_ipca_live > 0:
        ipca_focus_atual = round(float(focus_ipca_live), 2)
    else:
        logger.warning("renda_fixa: Focus IPCA indisponível — usando IPCA realizado (dado real BCB)")
        ipca_focus_atual = ipca_atual

    # Taxa prefixada 2 anos: baseada em Selic Focus real (quando disponível)
    if isinstance(focus_selic_live, (int, float)) and focus_selic_live > 0:
        pre_2y = round(float(focus_selic_live), 2)
        pre_2y_fonte = "Focus BCB"
    else:
        logger.warning("renda_fixa: Focus Selic indisponível — usando Selic real como referência para prefixado")
        pre_2y = selic_atual
        pre_2y_fonte = "Selic real BCB"
    alocacao = mix or dict(_MIX_BASE)

    # Ajuste por perfil
    if estrategia == "RENDA":
        # Renda: mais IPCA+ pois quer rendimento real consistente
        alocacao = {"RF-SELIC": 0.40, "RF-IPCA": 0.45, "RF-PRE": 0.15}
    elif estrategia == "ALPHA":
        # Alpha: RF é o 'colchão' — tudo em Selic para máxima liquidez
        alocacao = {"RF-SELIC": 0.80, "RF-IPCA": 0.20, "RF-PRE": 0.00}
        alocacao = {k: v for k, v in alocacao.items() if v > 0}

    saida: list[SugestaoMotor] = []

    for ticker, pct in alocacao.items():
        if pct <= 0 or ticker not in _RF_INFO:
            continue

        info     = _RF_INFO[ticker]
        valor    = round(capital * pct, 2)

        if ticker == "RF-SELIC":
            taxa_ref = selic_atual
            fonte_taxa = "Selic BCB"
        elif ticker == "RF-IPCA":
            taxa_ref = ipca_focus_atual
            fonte_taxa = "IPCA Focus BCB"
        else:
            taxa_ref = pre_2y
            fonte_taxa = pre_2y_fonte

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
                "taxa_referencia_aa":     taxa_ref,
                "fonte_taxa":             fonte_taxa,
                "peso_pct":               pct * 100,
                "descricao":              info["descricao"],
                "liquidez":              info["liquidez"],
                "risco":                 info["risco"],
                "rendimento_mensal_est": round(valor * taxa_ref / 100 / 12, 2),
                "rendimento_anual_est":  round(valor * taxa_ref / 100, 2),
                "selic_atual":           selic_atual,
                "ipca_focus_12m":        ipca_focus_atual,
            },
        ))

    return saida

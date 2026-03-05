"""
APEX Motor — ETFs

Motor de alocação em ETFs da B3. Filosofia:
  ETFs são o núcleo de eficiência da carteira — baixo custo, diversificação
  instantânea, sem risco de seleção individual. A alocação entre ETFs depende
  do perfil e do capital disponível.

Lógica de alocação:
  1. Núcleo BR (BOVA11) — sempre presente, representa o mercado brasileiro
  2. Internacional (IVVB11) — exposição ao S&P 500 / dólar
  3. Small Cap (SMAL11) — diversificação fora do IBOV  
  4. Setoriais/Temáticos — dependendo do perfil
  5. Renda Fixa ETF (IMAB11) — para perfis mais conservadores

Pesos base por perfil:
  CORE:  BOVA11 50% | IVVB11 30% | SMAL11 20%
  ALPHA: BOVA11 35% | IVVB11 35% | SMAL11 20% | NASD11 10%
  RENDA: BOVA11 40% | IVVB11 20% | DIVO11 30% | IMAB11 10%

O motor busca o preço real de cada ETF via yfinance e calcula a quantidade.
Justificativa explica o papel de cada ETF na carteira.
"""

import asyncio
from typing import Optional

import yfinance as yf

from app.cerebro.especialistas import SugestaoMotor
from app.cerebro.especialistas import prefetch as _pf

# ── Configuração de ETFs por perfil ─────────────────────────────────────────

_ETF_INFO = {
    "BOVA11": {
        "nome": "iShares IBOVESPA",
        "papel": "núcleo da carteira BR — as 84 maiores ações da B3 em um único ativo",
        "taxa_adm": 0.10,
    },
    "IVVB11": {
        "nome": "iShares S&P 500 (BRL)",
        "papel": "exposição ao mercado americano e hedge natural em dólar",
        "taxa_adm": 0.23,
    },
    "SMAL11": {
        "nome": "iShares Small Cap BR",
        "papel": "diversificação fora do IBOV — small caps com maior potencial de crescimento",
        "taxa_adm": 0.50,
    },
    "NASD11": {
        "nome": "Hashdex Nasdaq",
        "papel": "exposição concentrada em tecnologia e crescimento global (Nasdaq)",
        "taxa_adm": 0.40,
    },
    "DIVO11": {
        "nome": "It Now Dividendos",
        "papel": "ações com maior histórico de pagamento de dividendos na B3",
        "taxa_adm": 0.40,
    },
    "IMAB11": {
        "nome": "iShares IMA-B (IPCA+)",
        "papel": "título IPCA+ via ETF — proteção real contra inflação com liquidez de ETF",
        "taxa_adm": 0.20,
    },
    "ISUS11": {
        "nome": "iShares ESG BR",
        "papel": "exposição ao mercado BR com filtro ESG",
        "taxa_adm": 0.30,
    },
}

_PERFIL_ALOCACAO = {
    "ALPHA": [
        ("BOVA11", 0.35),
        ("IVVB11", 0.35),
        ("SMAL11", 0.20),
        ("NASD11", 0.10),
    ],
    "RENDA": [
        ("BOVA11", 0.40),
        ("DIVO11", 0.30),
        ("IVVB11", 0.20),
        ("IMAB11", 0.10),
    ],
    "CORE": [
        ("BOVA11", 0.50),
        ("IVVB11", 0.30),
        ("SMAL11", 0.20),
    ],
    "CUSTOM": [
        ("BOVA11", 0.45),
        ("IVVB11", 0.35),
        ("SMAL11", 0.20),
    ],
}


def _fetch_preco(ticker: str) -> Optional[float]:
    p = _pf.get_preco(ticker)
    if p is not None:
        return p
    try:
        t = yf.Ticker(ticker + ".SA")
        hist = t.history(period="5d", auto_adjust=True)
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        from app.logger import logger
        logger.warning("etfs: falha ao buscar preco %s via yfinance: %s", ticker, e)
    return None


def _justificativa_etf(ticker: str, pct: float, perfil: str) -> str:
    info = _ETF_INFO.get(ticker, {"nome": ticker, "papel": "diversificação global", "taxa_adm": 0.5})
    partes = [
        f"{info['nome']} — {info['papel']}",
        f"alocação de {pct*100:.0f}% do módulo ETFs para perfil {perfil}",
        f"taxa de administração de apenas {info['taxa_adm']:.2f}%/ano (eficiência máxima)",
    ]
    return ". ".join(partes) + "."


async def rodar(
    capital: float,
    estrategia: str = "CORE",
    n_ativos: Optional[int] = None,
) -> list[SugestaoMotor]:
    """
    Aloca o capital nos ETFs adequados para a estratégia informada.

    Args:
        capital:    Capital disponível para o módulo ETFs.
        estrategia: Estratégia do perfil (CORE | ALPHA | RENDA | CUSTOM).
        n_ativos:   Ignorado para ETFs — quantidade determinada pelo perfil.

    Returns:
        Lista de SugestaoMotor, um por ETF da alocação.
    """
    if capital < 500:
        return []

    estrategia = (estrategia or "CORE").upper()
    alocacao = _PERFIL_ALOCACAO.get(estrategia, _PERFIL_ALOCACAO["CORE"])

    # Busca preços em paralelo
    tarefas = [asyncio.to_thread(_fetch_preco, ticker) for ticker, _ in alocacao]
    precos  = await asyncio.gather(*tarefas, return_exceptions=True)

    saida: list[SugestaoMotor] = []

    for (ticker, pct), preco in zip(alocacao, precos):
        if not isinstance(preco, float) or preco is None or preco <= 0:
            continue

        capital_etf = capital * pct
        qtd = max(1, int(capital_etf / preco))
        valor = round(qtd * preco, 2)

        info = _ETF_INFO.get(ticker, {"nome": ticker, "papel": "", "taxa_adm": 0.5})

        saida.append(SugestaoMotor(
            modulo="etfs",
            ticker=ticker,
            nome=info["nome"],
            tipo="ETF",
            quantidade=float(qtd),
            preco_atual=round(preco, 2),
            valor_total=valor,
            justificativa=_justificativa_etf(ticker, pct, estrategia),
            score=pct * 100,  # peso = score
            dados_extras={
                "peso_alocacao_pct": pct * 100,
                "taxa_adm_aa":       info["taxa_adm"],
                "perfil":            estrategia,
            },
        ))

    return saida

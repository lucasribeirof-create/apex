"""
Análise de Risco do Portfólio — APEX Manager.

Módulo responsável por:
- Matriz de correlação entre ativos
- Verificação de limites de concentração
- Stress testing com cenários macroeconômicos
- Resumo textual para injeção em prompts LLM
"""

from __future__ import annotations

import hashlib
import json
from itertools import combinations
from typing import Any

import numpy as np

from app.data.cache import cache
from app.data.yfinance_client import get_history_global, _run_sync
from app.logger import logger


# ─── TTL de cache (4 horas) ──────────────────────────────────────────────────
_CACHE_TTL_RISCO = 4 * 60 * 60

# ─── Mapeamento ticker → setor ───────────────────────────────────────────────
SETOR_MAP: dict[str, str] = {
    # Energia / Petróleo
    "PETR4": "energia", "PETR3": "energia", "PRIO3": "energia",
    "RECV3": "energia", "VBBR3": "energia", "CSAN3": "energia",
    # Mineração / Siderurgia
    "VALE3": "mineracao", "GGBR4": "mineracao", "CSNA3": "mineracao",
    "USIM5": "mineracao",
    # Financeiro
    "ITUB4": "financeiro", "BBDC4": "financeiro", "BBAS3": "financeiro",
    "BPAC11": "financeiro", "SANB11": "financeiro", "B3SA3": "financeiro",
    "ITSA4": "financeiro",
    # Consumo
    "ABEV3": "consumo", "LREN3": "consumo", "BRFS3": "consumo",
    "JBSS32": "consumo", "MGLU3": "consumo", "PCAR3": "consumo",
    # Saúde
    "RDOR3": "saude", "RADL3": "saude", "HYPE3": "saude",
    "FLRY3": "saude",
    # Tecnologia / Telecom
    "TOTS3": "tecnologia", "VIVT3": "tecnologia", "TIMS3": "tecnologia",
    # Industrial
    "WEGE3": "industrial", "EMBJ3": "industrial", "RENT3": "industrial",
    # Utilidades Públicas
    "EGIE3": "utilidades", "EQTL3": "utilidades", "CMIG4": "utilidades",
    "ELET3": "utilidades", "TAEE11": "utilidades", "CPFE3": "utilidades",
    "SBSP3": "utilidades",
    # Papel & Celulose
    "SUZB3": "papel_celulose", "KLBN11": "papel_celulose",
}

# Tickers exportadores (beneficiados por alta do dólar)
_EXPORTADORES = {"PETR4", "PETR3", "VALE3", "SUZB3", "KLBN11", "JBSS32", "EMBJ3"}

# Tickers ligados a petróleo
_PETROLEIRAS = {"PETR4", "PETR3", "PRIO3", "RECV3", "VBBR3", "CSAN3"}

# Limites de concentração por estratégia
_LIMITE_ATIVO: dict[str, float] = {
    "CORE": 15.0,
    "RENDA": 15.0,
    "ALPHA": 20.0,
    "CUSTOM": 20.0,
}

_LIMITE_SETOR = 30.0  # % máximo por setor


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _ticker_yf(ticker: str, tipo: str) -> str:
    """Converte ticker brasileiro para formato yfinance (.SA)."""
    if tipo in ("RF", "CAIXA"):
        return ticker
    if ticker.endswith(".SA"):
        return ticker
    if tipo in ("ACAO", "FII", "ETF_BR") or (
        not ticker.startswith("^") and "." not in ticker
    ):
        return f"{ticker}.SA"
    return ticker


def _portfolio_hash(posicoes: list[dict]) -> str:
    tickers = sorted(p.get("ticker", "") for p in posicoes)
    raw = json.dumps(tickers, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _beta_estimado(tipo: str, ticker: str) -> float:
    """Beta aproximado por tipo de ativo."""
    if tipo == "RF" or tipo == "CAIXA":
        return 0.0
    if tipo == "FII":
        return 0.5
    if tipo == "ETF_BR":
        if ticker in ("BOVA11", "BOVV11"):
            return 1.0
        if ticker in ("IVVB11", "SPXI11"):
            return 0.9
        if ticker in ("IMAB11",):
            return 0.2
        return 0.7
    return 1.1  # ações


def _sensibilidade_selic(tipo: str) -> float:
    """Impacto estimado de +1pp na Selic sobre o preço do ativo (em %)."""
    if tipo == "RF" or tipo == "CAIXA":
        return 0.5   # RF se beneficia
    if tipo == "FII":
        return -3.0   # FIIs sofrem bastante
    return -1.5       # ações sofrem moderadamente


def _sensibilidade_dolar(ticker: str) -> float:
    """Impacto estimado de +1% no dólar sobre o ativo (em %)."""
    base = ticker.replace(".SA", "")
    if base in _EXPORTADORES:
        return 0.6
    return -0.3


def _sensibilidade_petroleo(ticker: str) -> float:
    """Impacto estimado de +1% no petróleo sobre o ativo (em %)."""
    base = ticker.replace(".SA", "")
    if base in _PETROLEIRAS:
        return 0.8
    return 0.0


# ─── 1. Correlação ──────────────────────────────────────────────────────────

async def calcular_correlacao(posicoes: list[dict]) -> dict:
    """
    Calcula matriz de correlação entre ativos do portfólio
    usando retornos diários de 63 pregões (~3 meses).
    """
    filtradas = [
        p for p in posicoes
        if p.get("tipo") not in ("RF", "CAIXA") and p.get("ticker")
    ]

    if len(filtradas) < 2:
        return {"matriz": {}, "clusters": [], "alertas": []}

    phash = _portfolio_hash(filtradas)
    cache_key = f"risco:correlacao:{phash}"
    cached = cache.get(cache_key)
    if cached:
        logger.info("Correlação: cache hit (%s)", cache_key)
        return cached

    tickers_raw = [p["ticker"] for p in filtradas]
    tipos = {p["ticker"]: p.get("tipo", "ACAO") for p in filtradas}
    tickers_yf = [_ticker_yf(t, tipos[t]) for t in tickers_raw]
    ticker_map = dict(zip(tickers_yf, tickers_raw))

    closes: dict[str, list[float]] = {}

    for tyf, traw in zip(tickers_yf, tickers_raw):
        try:
            hist = await get_history_global(tyf, period="3mo", interval="1d")
            if hist and len(hist) >= 10:
                closes[traw] = [r["close"] for r in hist]
        except Exception as e:
            logger.warning("Correlação: falha ao obter histórico de %s: %s", traw, e)

    if len(closes) < 2:
        return {"matriz": {}, "clusters": [], "alertas": []}

    tickers_ok = list(closes.keys())
    min_len = min(len(v) for v in closes.values())
    price_matrix = np.array([closes[t][-min_len:] for t in tickers_ok])

    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.diff(price_matrix, axis=1) / price_matrix[:, :-1]
        returns = np.nan_to_num(returns, nan=0.0, posinf=0.0, neginf=0.0)

    if returns.shape[1] < 5:
        return {"matriz": {}, "clusters": [], "alertas": []}

    corr_matrix = np.corrcoef(returns)
    corr_matrix = np.nan_to_num(corr_matrix, nan=0.0)

    matriz: dict[str, dict[str, float]] = {}
    for i, t1 in enumerate(tickers_ok):
        matriz[t1] = {}
        for j, t2 in enumerate(tickers_ok):
            matriz[t1][t2] = round(float(corr_matrix[i, j]), 3)

    clusters: list[dict] = []
    alertas: list[str] = []
    visitados: set[tuple[str, str]] = set()

    for i, j in combinations(range(len(tickers_ok)), 2):
        t1, t2 = tickers_ok[i], tickers_ok[j]
        corr = float(corr_matrix[i, j])
        if corr > 0.7 and (t1, t2) not in visitados:
            visitados.add((t1, t2))
            setor1 = SETOR_MAP.get(t1, "outros")
            setor2 = SETOR_MAP.get(t2, "outros")
            alerta_txt = _descrever_correlacao(t1, t2, setor1, setor2, corr)
            clusters.append({
                "tickers": [t1, t2],
                "correlacao_media": round(corr, 2),
                "alerta": alerta_txt,
            })
            alertas.append(
                f"{t1} + {t2} = correlação {corr:.2f} — posições se movem juntas"
            )

    resultado = {"matriz": matriz, "clusters": clusters, "alertas": alertas}
    cache.set(cache_key, resultado, ttl=_CACHE_TTL_RISCO)
    logger.info("Correlação calculada para %d ativos, %d clusters", len(tickers_ok), len(clusters))
    return resultado


def _descrever_correlacao(t1: str, t2: str, s1: str, s2: str, corr: float) -> str:
    if s1 == s2 and s1 != "outros":
        nomes_setor = {
            "energia": "petróleo/energia",
            "mineracao": "mineração/siderurgia",
            "financeiro": "setor financeiro",
            "consumo": "consumo",
            "saude": "saúde",
            "tecnologia": "tecnologia",
            "industrial": "indústria",
            "utilidades": "utilidades públicas",
            "papel_celulose": "papel e celulose",
        }
        nome = nomes_setor.get(s1, s1)
        return f"Exposição duplicada a {nome}"
    if corr > 0.85:
        return f"Correlação muito alta ({corr:.0%}) — praticamente o mesmo risco"
    return f"Correlação elevada ({corr:.0%}) — diversificação limitada"


# ─── 2. Concentração ────────────────────────────────────────────────────────

def verificar_concentracao(
    posicoes: list[dict],
    patrimonio: float,
    estrategia: str,
) -> dict:
    """
    Verifica se o portfólio respeita limites de concentração
    por ativo, por setor e por módulo.
    """
    if patrimonio <= 0:
        return {"violacoes": [], "alertas": [], "ok": True}

    limite_ativo = _LIMITE_ATIVO.get(estrategia.upper(), 15.0)
    violacoes: list[dict] = []
    alertas: list[str] = []

    # ── Concentração por ativo ────────────────────────────────────────────
    for p in posicoes:
        ticker = p.get("ticker", "?")
        valor = abs(p.get("valor_atual", 0.0))
        pct = (valor / patrimonio) * 100
        if pct > limite_ativo:
            violacoes.append({
                "tipo": "ativo",
                "ticker": ticker,
                "pct_atual": round(pct, 1),
                "limite": limite_ativo,
            })
            alertas.append(
                f"{ticker} ocupa {pct:.1f}% do portfólio (limite: {limite_ativo:.0f}%)"
            )

    # ── Concentração por setor ────────────────────────────────────────────
    exposicao_setor: dict[str, float] = {}
    for p in posicoes:
        ticker = p.get("ticker", "?")
        setor = SETOR_MAP.get(ticker, "outros")
        valor = abs(p.get("valor_atual", 0.0))
        exposicao_setor[setor] = exposicao_setor.get(setor, 0.0) + valor

    for setor, total in exposicao_setor.items():
        if setor == "outros":
            continue
        pct = (total / patrimonio) * 100
        if pct > _LIMITE_SETOR:
            violacoes.append({
                "tipo": "setor",
                "setor": setor,
                "pct_atual": round(pct, 1),
                "limite": _LIMITE_SETOR,
            })
            alertas.append(
                f"Setor '{setor}' ocupa {pct:.1f}% do portfólio (limite: {_LIMITE_SETOR:.0f}%)"
            )

    # ── Concentração por módulo ───────────────────────────────────────────
    alocacao_alvo = _alocacao_alvo(estrategia)
    exposicao_modulo: dict[str, float] = {}
    for p in posicoes:
        modulo = p.get("modulo", "outros")
        valor = abs(p.get("valor_atual", 0.0))
        exposicao_modulo[modulo] = exposicao_modulo.get(modulo, 0.0) + valor

    for modulo, total in exposicao_modulo.items():
        pct = (total / patrimonio) * 100
        alvo = alocacao_alvo.get(modulo)
        if alvo is not None:
            desvio = pct - alvo
            tolerancia = 10.0  # ±10pp
            if abs(desvio) > tolerancia:
                violacoes.append({
                    "tipo": "modulo",
                    "modulo": modulo,
                    "pct_atual": round(pct, 1),
                    "alvo": alvo,
                    "desvio_pp": round(desvio, 1),
                })
                direcao = "acima" if desvio > 0 else "abaixo"
                alertas.append(
                    f"Módulo '{modulo}' está {abs(desvio):.1f}pp {direcao} do alvo "
                    f"({pct:.1f}% vs {alvo:.0f}%)"
                )

    return {
        "violacoes": violacoes,
        "alertas": alertas,
        "ok": len(violacoes) == 0,
    }


def _alocacao_alvo(estrategia: str) -> dict[str, float]:
    """Alocação-alvo por módulo (%) de cada estratégia."""
    mapa = {
        "CORE": {"acoes": 40, "fiis": 20, "rf": 30, "internacional": 10},
        "ALPHA": {"acoes": 60, "fiis": 10, "rf": 15, "internacional": 15},
        "RENDA": {"acoes": 20, "fiis": 35, "rf": 35, "internacional": 10},
        "CUSTOM": {"acoes": 40, "fiis": 20, "rf": 30, "internacional": 10},
    }
    return mapa.get(estrategia.upper(), mapa["CORE"])


# ─── 3. Stress Test ─────────────────────────────────────────────────────────

async def stress_test(posicoes: list[dict], patrimonio: float) -> list[dict]:
    """
    Simula cenários macroeconômicos adversos e estima impacto no portfólio.
    """
    if patrimonio <= 0 or not posicoes:
        return []

    cenarios = [
        _cenario_ibov_queda(posicoes, patrimonio),
        _cenario_selic_alta(posicoes, patrimonio),
        _cenario_dolar_alta(posicoes, patrimonio),
        _cenario_petroleo_queda(posicoes, patrimonio),
    ]

    return cenarios


def _cenario_ibov_queda(posicoes: list[dict], patrimonio: float) -> dict:
    """IBOV -20%: impacto beta-ajustado em cada posição."""
    choque = -20.0
    impactos: list[dict[str, Any]] = []
    total_impacto = 0.0

    for p in posicoes:
        ticker = p.get("ticker", "?")
        tipo = p.get("tipo", "ACAO")
        valor = abs(p.get("valor_atual", 0.0))
        beta = _beta_estimado(tipo, ticker)
        impacto_pct = choque * beta
        impacto_reais = valor * (impacto_pct / 100)
        total_impacto += impacto_reais
        if abs(impacto_pct) > 0.1:
            impactos.append({"ticker": ticker, "impacto_pct": round(impacto_pct, 1)})

    impactos.sort(key=lambda x: x["impacto_pct"])
    return {
        "cenario": "IBOV -20%",
        "impacto_estimado_pct": round((total_impacto / patrimonio) * 100, 1) if patrimonio else 0,
        "impacto_reais": round(total_impacto, 2),
        "posicoes_mais_afetadas": impactos[:5],
    }


def _cenario_selic_alta(posicoes: list[dict], patrimonio: float) -> dict:
    """Selic +2pp: negativo para ações/FIIs, positivo para RF."""
    choque_pp = 2.0
    impactos: list[dict[str, Any]] = []
    total_impacto = 0.0

    for p in posicoes:
        ticker = p.get("ticker", "?")
        tipo = p.get("tipo", "ACAO")
        valor = abs(p.get("valor_atual", 0.0))
        sens = _sensibilidade_selic(tipo)
        impacto_pct = sens * choque_pp
        impacto_reais = valor * (impacto_pct / 100)
        total_impacto += impacto_reais
        if abs(impacto_pct) > 0.1:
            impactos.append({"ticker": ticker, "impacto_pct": round(impacto_pct, 1)})

    impactos.sort(key=lambda x: x["impacto_pct"])
    return {
        "cenario": "Selic +2pp",
        "impacto_estimado_pct": round((total_impacto / patrimonio) * 100, 1) if patrimonio else 0,
        "impacto_reais": round(total_impacto, 2),
        "posicoes_mais_afetadas": impactos[:5],
    }


def _cenario_dolar_alta(posicoes: list[dict], patrimonio: float) -> dict:
    """Dólar +15%: positivo para exportadores, negativo para demais."""
    choque = 15.0
    impactos: list[dict[str, Any]] = []
    total_impacto = 0.0

    for p in posicoes:
        ticker = p.get("ticker", "?")
        tipo = p.get("tipo", "ACAO")
        valor = abs(p.get("valor_atual", 0.0))
        if tipo in ("RF", "CAIXA"):
            impacto_pct = 0.0
        else:
            sens = _sensibilidade_dolar(ticker)
            impacto_pct = sens * choque
        impacto_reais = valor * (impacto_pct / 100)
        total_impacto += impacto_reais
        if abs(impacto_pct) > 0.1:
            impactos.append({"ticker": ticker, "impacto_pct": round(impacto_pct, 1)})

    impactos.sort(key=lambda x: x["impacto_pct"])
    return {
        "cenario": "Dólar +15%",
        "impacto_estimado_pct": round((total_impacto / patrimonio) * 100, 1) if patrimonio else 0,
        "impacto_reais": round(total_impacto, 2),
        "posicoes_mais_afetadas": impactos[:5],
    }


def _cenario_petroleo_queda(posicoes: list[dict], patrimonio: float) -> dict:
    """Petróleo -30%: impacto pesado em petroleiras."""
    choque = -30.0
    impactos: list[dict[str, Any]] = []
    total_impacto = 0.0

    for p in posicoes:
        ticker = p.get("ticker", "?")
        tipo = p.get("tipo", "ACAO")
        valor = abs(p.get("valor_atual", 0.0))
        if tipo in ("RF", "CAIXA"):
            impacto_pct = 0.0
        else:
            sens = _sensibilidade_petroleo(ticker)
            impacto_pct = sens * choque
        impacto_reais = valor * (impacto_pct / 100)
        total_impacto += impacto_reais
        if abs(impacto_pct) > 0.1:
            impactos.append({"ticker": ticker, "impacto_pct": round(impacto_pct, 1)})

    impactos.sort(key=lambda x: x["impacto_pct"])
    return {
        "cenario": "Petróleo -30%",
        "impacto_estimado_pct": round((total_impacto / patrimonio) * 100, 1) if patrimonio else 0,
        "impacto_reais": round(total_impacto, 2),
        "posicoes_mais_afetadas": impactos[:5],
    }


# ─── 4. Resumo Textual ──────────────────────────────────────────────────────

def resumo_risco_texto(
    correlacao: dict,
    concentracao: dict,
    stress: list[dict],
) -> str:
    """
    Gera resumo textual conciso da análise de risco,
    pronto para injeção em prompts LLM.
    """
    linhas: list[str] = ["## Análise de Risco do Portfólio\n"]

    # Concentração
    if concentracao.get("ok"):
        linhas.append("**Concentração:** Dentro dos limites.")
    else:
        linhas.append("**Concentração — VIOLAÇÕES:**")
        for alerta in concentracao.get("alertas", []):
            linhas.append(f"  • {alerta}")

    # Correlação
    clusters = correlacao.get("clusters", [])
    if clusters:
        linhas.append(f"\n**Correlação:** {len(clusters)} par(es) com correlação >0.7:")
        for c in clusters:
            tks = " + ".join(c["tickers"])
            linhas.append(f"  • {tks} (ρ={c['correlacao_media']:.2f}) — {c['alerta']}")
    else:
        linhas.append("\n**Correlação:** Sem pares com correlação crítica.")

    # Stress
    if stress:
        linhas.append("\n**Stress Test:**")
        for s in stress:
            sinal = "+" if s["impacto_estimado_pct"] >= 0 else ""
            linhas.append(
                f"  • {s['cenario']}: {sinal}{s['impacto_estimado_pct']:.1f}% "
                f"(R$ {s['impacto_reais']:,.0f})"
            )
            if s.get("posicoes_mais_afetadas"):
                top = s["posicoes_mais_afetadas"][0]
                linhas.append(
                    f"    Mais afetado: {top['ticker']} ({top['impacto_pct']:+.1f}%)"
                )

    return "\n".join(linhas)

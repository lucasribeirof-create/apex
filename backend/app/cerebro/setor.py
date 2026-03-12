"""
APEX Sector Engine — Ranking setorial top-down.

Pontua cada setor (equity) de 0 a 100 com base em três pilares:
  1. Alinhamento macro (40%) — regras determinísticas: condições macro → setores beneficiados/prejudicados
  2. Momentum setorial (30%) — retorno 63d do proxy ticker vs IBOV
  3. Valuation relativo (30%) — P/L do proxy vs referência (15×)

Entrada: MacroContext (de macro.py)
Saída:   RankingSetorial com lista ordenada, favorecidos, evitar

Setores usam a taxonomia canônica de core/universe.py (SETOR_PROXY).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

import yfinance as yf

from app.core.universe import SETOR_PROXY
from app.data.cache import cache
from app.data.yfinance_client import _run_sync
from app.logger import logger


# ─── Configurações ──────────────────────────────────────────────────────────

CACHE_TTL_SETOR = 1800  # 30 min

# Setores equity (ignoramos etf, fii e outro — não são "setores" propriamente)
_SETORES_EQUITY = [
    "energia", "mineracao", "financeiro", "consumo", "utilidades",
    "saude", "tecnologia", "industrial", "imobiliario", "agro",
]

# Pesos dos pilares
_PESO_MACRO     = 0.40
_PESO_MOMENTUM  = 0.30
_PESO_VALUATION = 0.30

# P/L de referência (múltiplo "justo" para mercado BR)
_PL_REFERENCIA = 15.0

# Limiares para classificar favorecidos/evitar
_LIMIAR_FAVORECIDO = 60   # score >= 60 → favorecido
_LIMIAR_EVITAR     = 35   # score < 35  → evitar


# ─── Dataclass de saída ───────────────────────────────────────────────────────

@dataclass
class SetorScore:
    """Score detalhado de um setor."""
    setor: str
    score_total: int           # 0-100
    score_macro: int           # 0-100 (antes do peso)
    score_momentum: int        # 0-100 (antes do peso)
    score_valuation: int       # 0-100 (antes do peso)
    ticker_proxy: str
    retorno_63d_pct: Optional[float] = None
    pl_proxy: Optional[float] = None
    motivos: list[str] = field(default_factory=list)


@dataclass
class RankingSetorial:
    """Ranking completo de setores para o contexto do cérebro."""
    setores: list[SetorScore]           # Ordenado por score_total desc
    favorecidos: list[str]              # Setores com score >= limiar
    evitar: list[str]                   # Setores com score < limiar
    atualizado_em: str = ""

    def resumo_texto(self) -> str:
        """Texto para injetar no prompt da IA."""
        partes = ["=== RANKING SETORIAL ==="]
        for s in self.setores:
            tag = "⭐" if s.setor in self.favorecidos else ("⛔" if s.setor in self.evitar else "  ")
            partes.append(
                f"  {tag} {s.setor:14s} score {s.score_total:3d}/100  "
                f"(macro {s.score_macro}, mom {s.score_momentum}, val {s.score_valuation})"
            )
            if s.motivos:
                for m in s.motivos:
                    partes.append(f"      → {m}")
        partes.append(f"\nFavorecidos: {', '.join(self.favorecidos) or 'nenhum'}")
        partes.append(f"Evitar:      {', '.join(self.evitar) or 'nenhum'}")
        return "\n".join(partes)


# ─── Harmonização de setores (dividendos motor → taxonomia canônica) ─────────

_SETOR_MAP_HARMONIZE: dict[str, str] = {
    # _DIV_META usa nomes diferentes — mapeamos para a taxonomia canônica
    "bancário":   "financeiro",
    "bancario":   "financeiro",
    "petróleo":   "energia",
    "petroleo":   "energia",
    "mineração":  "mineracao",
    "mineracao":  "mineracao",
    "telecom":    "tecnologia",
    "elétrico":   "utilidades",
    "eletrico":   "utilidades",
    "seguros":    "financeiro",
    # Já canônicos
    "energia":      "energia",
    "financeiro":   "financeiro",
    "consumo":      "consumo",
    "utilidades":   "utilidades",
    "saude":        "saude",
    "tecnologia":   "tecnologia",
    "industrial":   "industrial",
    "imobiliario":  "imobiliario",
    "agro":         "agro",
    "etf":          "etf",
    "fii":          "fii",
    "outro":        "outro",
}


def harmonizar_setor(setor_raw: str) -> str:
    """Converte qualquer nome de setor para a taxonomia canônica."""
    return _SETOR_MAP_HARMONIZE.get(setor_raw.lower().strip(), "outro")


# ─── Coleta de dados setoriais ───────────────────────────────────────────────

def _fetch_setor_data_batch() -> dict[str, dict]:
    """
    Coleta retorno 63d e P/L para cada proxy setorial + IBOV.
    Executa SEQUENCIALMENTE (yf.download não é thread-safe).
    """
    # Primeiro: IBOV para benchmark
    ibov_ret_63d = None
    try:
        df = yf.download("^BVSP", period="6mo", interval="1d", progress=False)
        if not df.empty and len(df) >= 63:
            closes = df["Close"].values.flatten()
            ibov_ret_63d = (closes[-1] / closes[-63] - 1) * 100
    except Exception as e:
        logger.debug("setor: IBOV 63d falhou: %s", e)

    resultados: dict[str, dict] = {}

    for setor in _SETORES_EQUITY:
        proxy = SETOR_PROXY[setor]
        ticker_yf = proxy + ".SA"
        data: dict = {"retorno_63d": None, "pl": None}

        try:
            # Retorno 63d
            df = yf.download(ticker_yf, period="6mo", interval="1d", progress=False)
            if not df.empty and len(df) >= 63:
                closes = df["Close"].values.flatten()
                ret_proxy = (closes[-1] / closes[-63] - 1) * 100
                data["retorno_63d"] = round(ret_proxy, 2)
                if ibov_ret_63d is not None:
                    data["retorno_vs_ibov"] = round(ret_proxy - ibov_ret_63d, 2)
                else:
                    data["retorno_vs_ibov"] = 0.0
        except Exception as e:
            logger.debug("setor: %s retorno falhou: %s", setor, e)

        try:
            # P/L trailing
            info = yf.Ticker(ticker_yf).fast_info
            pe = getattr(info, "last_price", None)
            # fast_info não tem P/E diretamente — usamos .info
            info_full = yf.Ticker(ticker_yf).info
            trail_pe = info_full.get("trailingPE")
            if trail_pe and isinstance(trail_pe, (int, float)) and trail_pe > 0:
                data["pl"] = round(float(trail_pe), 1)
        except Exception as e:
            logger.debug("setor: %s P/L falhou: %s", setor, e)

        resultados[setor] = data

    return resultados


# ─── Scoring: Alinhamento Macro ─────────────────────────────────────────────

def _score_macro_alinhamento(setor: str, macro) -> tuple[int, list[str]]:
    """
    Pontua 0-100 o alinhamento do setor com o contexto macro atual.
    Usa regras quantitativas baseadas nos campos de MacroContext.
    Retorna (score, [motivos]).
    """
    pontos = 50  # base neutra
    motivos = []

    fase_selic = getattr(macro, "fase_selic", "TRANSICAO")
    dolar = getattr(macro, "dolar_brl", None)
    petroleo = getattr(macro, "petroleo_wti", None)
    regime = getattr(macro, "regime_macro", "NEUTRO")
    juro_real = getattr(macro, "juro_real", None)
    vix = getattr(macro, "vix", None)

    # ── Fase Selic ────────────────────────────────────────────────────────
    if fase_selic in ("QUEDA", "VALE"):
        # Juros caindo beneficia: imob, consumo, utilidades, FIIs (via imob)
        if setor in ("imobiliario", "consumo", "utilidades"):
            pontos += 20
            motivos.append(f"Selic em {fase_selic} beneficia {setor}")
        elif setor == "financeiro":
            pontos -= 10
            motivos.append("Selic caindo reduz margem bancária")
    elif fase_selic in ("ALTA", "PICO"):
        # Juros altos beneficia financeiro, prejudica consumo/imob
        if setor == "financeiro":
            pontos += 15
            motivos.append("Selic alta favorece margem bancária")
        elif setor in ("imobiliario", "consumo"):
            pontos -= 15
            motivos.append(f"Selic alta pressiona {setor}")

    # ── Dólar ─────────────────────────────────────────────────────────────
    if dolar is not None:
        if dolar > 5.80:
            # Dólar alto → exportadoras
            if setor in ("energia", "mineracao", "agro"):
                pontos += 15
                motivos.append(f"Dólar alto (R${dolar:.2f}) favorece exportadoras")
            elif setor in ("consumo", "tecnologia"):
                pontos -= 10
                motivos.append("Dólar alto pressiona importações/consumo")
        elif dolar < 4.80:
            # Dólar baixo → consumo interno
            if setor in ("consumo", "saude", "tecnologia"):
                pontos += 10
                motivos.append(f"Dólar baixo (R${dolar:.2f}) favorece mercado doméstico")
            elif setor in ("energia", "mineracao", "agro"):
                pontos -= 10
                motivos.append("Dólar baixo reduz receita de exportadoras")

    # ── Petróleo ──────────────────────────────────────────────────────────
    if petroleo is not None:
        if petroleo > 80:
            if setor == "energia":
                pontos += 15
                motivos.append(f"Petróleo alto (${petroleo:.0f}) favorece energia")
            elif setor in ("consumo", "industrial"):
                pontos -= 5
                motivos.append("Petróleo alto pressiona custos")
        elif petroleo < 55:
            if setor == "energia":
                pontos -= 15
                motivos.append(f"Petróleo baixo (${petroleo:.0f}) pressiona lucratividade")
            elif setor in ("consumo", "industrial"):
                pontos += 5
                motivos.append("Petróleo baixo reduz custos operacionais")

    # ── Regime macro ──────────────────────────────────────────────────────
    if regime == "RISK_OFF":
        # Defensivos sobem
        if setor in ("utilidades", "saude"):
            pontos += 15
            motivos.append("Regime RISK_OFF favorece defensivos")
        elif setor in ("tecnologia", "consumo", "industrial"):
            pontos -= 10
            motivos.append("Regime RISK_OFF pressiona cíclicos")
    elif regime == "RISK_ON_FORTE":
        # Cíclicos sobem
        if setor in ("industrial", "tecnologia", "financeiro", "consumo"):
            pontos += 10
            motivos.append("Regime RISK_ON_FORTE favorece cíclicos")
        elif setor == "utilidades":
            pontos -= 5
            motivos.append("Regime RISK_ON pode reduzir demanda por defensivos")

    # ── Juro real ─────────────────────────────────────────────────────────
    if juro_real is not None:
        if juro_real > 8:
            if setor == "imobiliario":
                pontos -= 15
                motivos.append(f"Juro real muito alto ({juro_real:.1f}%) pressiona imobiliário")
        elif juro_real < 4:
            if setor == "imobiliario":
                pontos += 10
                motivos.append(f"Juro real baixo ({juro_real:.1f}%) favorece imobiliário")

    # ── VIX (medo global) ────────────────────────────────────────────────
    if vix is not None and vix > 25:
        if setor in ("utilidades", "saude"):
            pontos += 5
            motivos.append("VIX elevado favorece setores defensivos")
        elif setor in ("tecnologia", "consumo"):
            pontos -= 5

    # ── Commodities (novos indicadores) ───────────────────────────────────
    cobre = getattr(macro, "cobre", None)
    soja = getattr(macro, "soja", None)
    milho = getattr(macro, "milho", None)
    minerio = getattr(macro, "minerio_ferro", None)

    # Cobre alto = expansão industrial global
    if cobre is not None:
        if cobre > 4.5:
            if setor in ("mineracao", "industrial"):
                pontos += 10
                motivos.append(f"Cobre alto (${cobre:.2f}/lb) sinaliza expansão global — favorece {setor}")
        elif cobre < 3.5:
            if setor in ("mineracao", "industrial"):
                pontos -= 10
                motivos.append(f"Cobre baixo (${cobre:.2f}/lb) sinaliza contração — pressiona {setor}")

    # Soja/milho altos = bom para agro
    if soja is not None:
        if soja > 1400:
            if setor == "agro":
                pontos += 10
                motivos.append(f"Soja em alta (${soja:.0f}/bu) favorece agro")
        elif soja < 1000:
            if setor == "agro":
                pontos -= 10
                motivos.append(f"Soja em baixa (${soja:.0f}/bu) pressiona agro")

    # Curva DI (juros futuros) — novo indicador setorial
    inclinacao_di = getattr(macro, "inclinacao_di", None)
    if inclinacao_di is not None:
        if inclinacao_di > 1.0:
            # Mercado espera mais juros → bom pra financeiro, ruim pra imob/consumo
            if setor == "financeiro":
                pontos += 10
                motivos.append(f"Curva DI inclinando (+{inclinacao_di:.1f}pp) — margem bancária deve subir")
            elif setor in ("imobiliario", "consumo"):
                pontos -= 10
                motivos.append(f"Curva DI inclinando — mercado precifica mais juros, pressiona {setor}")
        elif inclinacao_di < -1.0:
            # Mercado espera queda de juros → bom pra imob/consumo, ruim pra financeiro
            if setor in ("imobiliario", "consumo", "utilidades"):
                pontos += 10
                motivos.append(f"Curva DI invertendo ({inclinacao_di:.1f}pp) — mercado precifica queda de juros, favorece {setor}")
            elif setor == "financeiro":
                pontos -= 5
                motivos.append("Curva DI invertendo — margem bancária pode cair")

    # China (Hang Seng) — afeta mineração/agro diretamente
    hang_seng_var = getattr(macro, "hang_seng_var_pct", None)
    if hang_seng_var is not None:
        if hang_seng_var < -2:
            if setor in ("mineracao", "agro"):
                pontos -= 10
                motivos.append(f"Hang Seng caindo {hang_seng_var:.1f}% — risco China afeta exportadores de commodities")
        elif hang_seng_var > 2:
            if setor in ("mineracao", "agro"):
                pontos += 5
                motivos.append("China em alta — positivo para exportadores de commodities")

    return max(0, min(100, pontos)), motivos


# ─── Scoring: Momentum setorial ─────────────────────────────────────────────

def _score_momentum(retorno_vs_ibov: Optional[float]) -> int:
    """
    Pontua 0-100 baseado no retorno relativo do setor vs IBOV em 63 dias.
    Retorno relativo positivo = setor está outperformando.
    """
    if retorno_vs_ibov is None:
        return 50  # sem dados → neutro

    # Mapeia retorno relativo para score
    # -20% ou pior → 0, 0% → 50, +20% ou mais → 100
    score = 50 + retorno_vs_ibov * 2.5
    return max(0, min(100, int(score)))


# ─── Scoring: Valuation relativo ─────────────────────────────────────────────

def _score_valuation(pl: Optional[float]) -> int:
    """
    Pontua 0-100 baseado no P/L do proxy ticker vs referência.
    P/L baixo → score alto (barato). P/L alto → score baixo (caro).
    """
    if pl is None or pl <= 0:
        return 50  # sem dados → neutro

    # P/L 5 → 100, P/L 15 → 50, P/L 30 → 0
    score = 100 - (pl - 5) * (100 / 25)
    return max(0, min(100, int(score)))


# ─── Entry point principal ───────────────────────────────────────────────────

async def montar_ranking(macro_context) -> RankingSetorial:
    """
    Calcula o ranking setorial completo.

    Args:
        macro_context: MacroContext de macro.py (precisa ter fase_selic, dolar_brl, etc.)

    Returns:
        RankingSetorial com setores ordenados, favorecidos e evitar.
    """
    from datetime import datetime, timezone

    cache_key = "cerebro:ranking_setorial"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Coleta dados de mercado (sequencial — thread-safe)
    dados_mercado = await _run_sync(_fetch_setor_data_batch)

    setores_scores: list[SetorScore] = []

    for setor in _SETORES_EQUITY:
        dados = dados_mercado.get(setor, {})

        # Pilar 1: Alinhamento macro
        macro_pts, motivos = _score_macro_alinhamento(setor, macro_context)

        # Pilar 2: Momentum
        mom_pts = _score_momentum(dados.get("retorno_vs_ibov"))

        # Pilar 3: Valuation
        val_pts = _score_valuation(dados.get("pl"))

        # Score final ponderado
        total = int(macro_pts * _PESO_MACRO + mom_pts * _PESO_MOMENTUM + val_pts * _PESO_VALUATION)
        total = max(0, min(100, total))

        setores_scores.append(SetorScore(
            setor=setor,
            score_total=total,
            score_macro=macro_pts,
            score_momentum=mom_pts,
            score_valuation=val_pts,
            ticker_proxy=SETOR_PROXY[setor],
            retorno_63d_pct=dados.get("retorno_63d"),
            pl_proxy=dados.get("pl"),
            motivos=motivos,
        ))

    # Ordena por score total desc
    setores_scores.sort(key=lambda s: s.score_total, reverse=True)

    favorecidos = [s.setor for s in setores_scores if s.score_total >= _LIMIAR_FAVORECIDO]
    evitar = [s.setor for s in setores_scores if s.score_total < _LIMIAR_EVITAR]

    ranking = RankingSetorial(
        setores=setores_scores,
        favorecidos=favorecidos,
        evitar=evitar,
        atualizado_em=datetime.now(timezone.utc).isoformat(),
    )

    cache.set(cache_key, ranking, ttl=CACHE_TTL_SETOR)
    return ranking

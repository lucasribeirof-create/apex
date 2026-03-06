"""
MacroEngine — Visão de mundo completa para o Cérebro APEX.

Coleta dados macro globais e brasileiros de fontes confiáveis e gratuitas,
consolidando tudo em um MacroContext que alimenta o CEO Brain, Regime,
Narrativa e todos os módulos de decisão.

Fontes:
  Global: yFinance  (^TNX, ^VIX, DX-Y.NYB, CL=F, BZ=F, ^GSPC, GC=F)
  Brasil: BCB/SGS   (Selic 1178, IPCA 433)
          Olinda/BCB (Focus — expectativas Selic e IPCA futuros)
          yFinance   (USDBRL=X, ^BVSP)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import yfinance as yf

from app.data.cache import cache
from app.data.bcb_client import get_selic, get_ipca
from app.data.yfinance_client import _run_sync
from app.logger import logger


CACHE_TTL_MACRO_GLOBAL = 1800   # 30 min
CACHE_TTL_MACRO_BR = 600        # 10 min


# ─── Dataclass principal ────────────────────────────────────────────────────

# ─── Regime 4-estados ──────────────────────────────────────────────────────

class RegimeMacro:
    """Regime macro em 4 estados com score numérico."""
    RISK_ON_FORTE = "RISK_ON_FORTE"
    RISK_ON_MODERADO = "RISK_ON_MODERADO"
    NEUTRO = "NEUTRO"
    RISK_OFF = "RISK_OFF"


class FaseSelic:
    """Fase do ciclo de juros doméstico."""
    ALTA = "ALTA"               # Selic subindo
    PICO = "PICO"               # Última alta, pausa
    TRANSICAO = "TRANSICAO"     # Pausa prolongada, mercado espera corte
    QUEDA = "QUEDA"             # Selic caindo
    VALE = "VALE"               # Última queda, Selic estável no fundo


# ─── Guardrails por regime ──────────────────────────────────────────────────

GUARDRAILS_POR_REGIME: dict[str, dict] = {
    RegimeMacro.RISK_ON_FORTE: {
        "equity_max_pct": 60,
        "rf_min_pct": 10,
        "caixa_min_pct": 5,
        "descricao": "Cenário favorável — máxima exposição a risco permitida",
    },
    RegimeMacro.RISK_ON_MODERADO: {
        "equity_max_pct": 45,
        "rf_min_pct": 20,
        "caixa_min_pct": 10,
        "descricao": "Cenário positivo com ressalvas — exposição moderada",
    },
    RegimeMacro.NEUTRO: {
        "equity_max_pct": 30,
        "rf_min_pct": 25,
        "caixa_min_pct": 15,
        "descricao": "Cenário indefinido — postura conservadora",
    },
    RegimeMacro.RISK_OFF: {
        "equity_max_pct": 15,
        "rf_min_pct": 30,
        "caixa_min_pct": 40,
        "descricao": "Cenário hostil — preservação de capital",
    },
}


@dataclass
class MacroContext:
    """Snapshot macro completo — global + Brasil + regime + confiança."""

    # Global
    treasury_10y: Optional[float] = None       # US Treasury 10Y yield (%)
    treasury_2y: Optional[float] = None        # US Treasury 2Y yield (%)
    yield_spread: Optional[float] = None       # 10Y - 2Y (negativo = curva invertida)
    vix: Optional[float] = None                # Índice de volatilidade
    dxy: Optional[float] = None                # Dollar Index
    dxy_mm50: Optional[float] = None           # DXY MM50 (para flag "dólar forte")
    petroleo_wti: Optional[float] = None       # WTI (USD/barril)
    petroleo_brent: Optional[float] = None     # Brent (USD/barril)
    sp500: Optional[float] = None              # S&P 500 preço
    sp500_var_pct: Optional[float] = None      # S&P 500 variação dia (%)
    sp500_mm50: Optional[float] = None         # S&P 500 MM50
    sp500_mm200: Optional[float] = None        # S&P 500 MM200
    ouro: Optional[float] = None               # Ouro (USD/oz)

    # Calendário econômico (dados reais)
    calendario_eventos: list = field(default_factory=list)

    # Brasil
    selic: Optional[float] = None              # Meta Selic (% a.a.)
    ipca_12m: Optional[float] = None           # IPCA acumulado 12 meses (%)
    ipca_expectativa: Optional[float] = None   # IPCA esperado 12 meses (Focus)
    selic_expectativa: Optional[float] = None  # Selic esperada fim do ano (Focus)
    juro_real: Optional[float] = None          # Selic - IPCA expectativa
    dolar_brl: Optional[float] = None          # USD/BRL
    dolar_var_pct: Optional[float] = None      # USD/BRL variação dia (%)
    ibov: Optional[float] = None               # IBOVESPA pontos
    ibov_var_pct: Optional[float] = None       # IBOVESPA variação dia (%)

    # ── Regime & inteligência macro (NOVO — Fase 1 Cérebro Híbrido) ──────
    regime_macro: str = RegimeMacro.NEUTRO     # 4-estados: RISK_ON_FORTE / MOD / NEUTRO / OFF
    regime_score: int = 50                     # 0-100 (> 70 = risk-on forte, < 25 = risk-off)
    confianca: int = 50                        # 0-100 — quanto os indicadores concordam
    fase_selic: str = FaseSelic.TRANSICAO      # Fase do ciclo de juros BR
    guardrails: dict = field(default_factory=dict)  # equity_max, rf_min, caixa_min

    # Metadata
    atualizado_em: Optional[str] = None

    # Flags macro (preenchidas por _calcular_flags)
    flags: list[str] = field(default_factory=list)

    def resumo_texto(self) -> str:
        """Texto denso para injetar no prompt da IA."""
        partes = []

        partes.append("=== MACRO GLOBAL ===")
        if self.treasury_10y is not None:
            partes.append(f"US Treasury 10Y: {self.treasury_10y:.2f}%")
        if self.vix is not None:
            partes.append(f"VIX: {self.vix:.1f}")
        if self.dxy is not None:
            txt = f"DXY (Dollar Index): {self.dxy:.2f}"
            if self.dxy_mm50:
                rel = "acima" if self.dxy > self.dxy_mm50 else "abaixo"
                txt += f" ({rel} da MM50 {self.dxy_mm50:.2f})"
            partes.append(txt)
        if self.sp500 is not None:
            txt = f"S&P 500: {self.sp500:,.0f}"
            if self.sp500_var_pct is not None:
                txt += f" ({self.sp500_var_pct:+.2f}%)"
            partes.append(txt)
        if self.petroleo_wti is not None:
            partes.append(f"Petróleo WTI: ${self.petroleo_wti:.2f}")
        if self.petroleo_brent is not None:
            partes.append(f"Petróleo Brent: ${self.petroleo_brent:.2f}")
        if self.ouro is not None:
            partes.append(f"Ouro: ${self.ouro:,.0f}/oz")

        partes.append("\n=== MACRO BRASIL ===")
        if self.selic is not None:
            partes.append(f"Selic Meta: {self.selic:.2f}% a.a.")
        if self.ipca_12m is not None:
            partes.append(f"IPCA 12m: {self.ipca_12m:.2f}%")
        if self.selic_expectativa is not None:
            partes.append(f"Selic Esperada (Focus): {self.selic_expectativa:.2f}%")
        if self.ipca_expectativa is not None:
            partes.append(f"IPCA Esperado 12m (Focus): {self.ipca_expectativa:.2f}%")
        if self.juro_real is not None:
            partes.append(f"Juro Real: {self.juro_real:.2f}%")
        if self.dolar_brl is not None:
            txt = f"Dólar: R${self.dolar_brl:.2f}"
            if self.dolar_var_pct is not None:
                txt += f" ({self.dolar_var_pct:+.2f}%)"
            partes.append(txt)
        if self.ibov is not None:
            txt = f"IBOV: {self.ibov:,.0f}"
            if self.ibov_var_pct is not None:
                txt += f" ({self.ibov_var_pct:+.2f}%)"
            partes.append(txt)

        # Regime & Confiança
        partes.append("\n=== REGIME MACRO ===")
        partes.append(f"Regime: {self.regime_macro} (score {self.regime_score}/100, confiança {self.confianca}/100)")
        partes.append(f"Fase Selic: {self.fase_selic}")
        if self.yield_spread is not None:
            estado = "INVERTIDA ⚠" if self.yield_spread < 0 else "normal"
            partes.append(f"Curva de Juros EUA (10Y-2Y): {self.yield_spread:+.2f}pp ({estado})")
        if self.guardrails:
            partes.append(f"Guardrails: equity max {self.guardrails.get('equity_max_pct')}% | RF min {self.guardrails.get('rf_min_pct')}% | caixa min {self.guardrails.get('caixa_min_pct')}%")

        if self.flags:
            partes.append("\n=== ALERTAS MACRO ===")
            for flag in self.flags:
                partes.append(f"⚠ {flag}")

        if self.calendario_eventos:
            partes.append("\n=== CALENDÁRIO ECONÔMICO (DADOS REAIS — HOJE + 7 DIAS) ===")
            partes.append("ATENÇÃO: Estes eventos foram obtidos de API em tempo real. Use EXCLUSIVAMENTE estes dados para a seção de calendário. NÃO use seu conhecimento de treinamento para datas.")
            from app.data.calendar_client import formatar_para_prompt
            partes.append(formatar_para_prompt(self.calendario_eventos))

        return "\n".join(partes)


# ─── Coleta de dados globais ────────────────────────────────────────────────

async def _get_yf_price(symbol: str) -> Optional[float]:
    """Busca last_price de um ticker yFinance."""
    try:
        ticker = await _run_sync(lambda s=symbol: yf.Ticker(s))
        info = await _run_sync(lambda t=ticker: t.fast_info)
        return float(info.last_price)
    except Exception as e:
        logger.debug("macro._get_yf_price(%s) falhou: %s", symbol, e)
        return None


async def _get_yf_price_and_change(symbol: str) -> tuple[Optional[float], Optional[float]]:
    """Busca last_price e variação % de um ticker yFinance."""
    try:
        ticker = await _run_sync(lambda s=symbol: yf.Ticker(s))
        info = await _run_sync(lambda t=ticker: t.fast_info)
        price = float(info.last_price)
        prev = float(info.previous_close)
        change = (price - prev) / prev * 100 if prev else None
        return price, change
    except Exception as e:
        logger.debug("macro._get_yf_price_and_change(%s) falhou: %s", symbol, e)
        return None, None


async def _get_yf_mm(symbol: str, period: int = 50) -> Optional[float]:
    """Calcula MM de N períodos para um ticker yFinance."""
    try:
        # period="1y" garante ~252 pregões (suficiente para MM200)
        df = await _run_sync(
            lambda s=symbol: yf.download(s, period="1y", interval="1d", progress=False)
        )
        if df.empty or len(df) < period:
            return None
        closes = df["Close"].values.flatten()
        return float(sum(closes[-period:]) / period)
    except Exception:
        return None


def _calcular_mms_batch() -> dict:
    """
    Calcula todas as MMs necessárias de forma SEQUENCIAL em um único thread.
    yf.download NÃO é thread-safe — chamadas paralelas misturam dados.
    """
    resultado = {}
    for symbol, period, key in [
        ("DX-Y.NYB", 50, "dxy_mm50"),
        ("^GSPC", 50, "sp500_mm50"),
        ("^GSPC", 200, "sp500_mm200"),
    ]:
        try:
            df = yf.download(symbol, period="1y", interval="1d", progress=False)
            if df.empty or len(df) < period:
                resultado[key] = None
                continue
            closes = df["Close"].values.flatten()
            resultado[key] = float(sum(closes[-period:]) / period)
        except Exception:
            resultado[key] = None
    return resultado


async def _coletar_global() -> dict:
    """Coleta todos os dados globais em paralelo."""
    key = "macro:engine:global"
    cached = cache.get(key)
    if cached:
        return cached

    (
        treasury, treasury_2y, vix, dxy, wti, brent, (sp500, sp500_var), ouro,
        mms,
    ) = await asyncio.gather(
        _get_yf_price("^TNX"),
        _get_yf_price("^IRX"),     # Treasury 2Y (13-week proxy via ^IRX)
        _get_yf_price("^VIX"),
        _get_yf_price("DX-Y.NYB"),
        _get_yf_price("CL=F"),
        _get_yf_price("BZ=F"),
        _get_yf_price_and_change("^GSPC"),
        _get_yf_price("GC=F"),
        _run_sync(_calcular_mms_batch),  # MMs sequenciais em 1 thread (thread-safe)
    )

    dxy_mm50 = mms.get("dxy_mm50")
    sp500_mm50 = mms.get("sp500_mm50")
    sp500_mm200 = mms.get("sp500_mm200")

    # Yield spread (curva de juros) — negativo = invertida = sinal de recessão
    yield_spread = None
    if treasury is not None and treasury_2y is not None:
        yield_spread = round(treasury - treasury_2y, 3)

    result = {
        "treasury_10y": treasury,
        "treasury_2y": treasury_2y,
        "yield_spread": yield_spread,
        "vix": vix,
        "dxy": dxy,
        "dxy_mm50": dxy_mm50,
        "petroleo_wti": wti,
        "petroleo_brent": brent,
        "sp500": sp500,
        "sp500_var_pct": sp500_var,
        "sp500_mm50": sp500_mm50,
        "sp500_mm200": sp500_mm200,
        "ouro": ouro,
    }
    cache.set(key, result, ttl=CACHE_TTL_MACRO_GLOBAL)
    return result


async def _coletar_brasil() -> dict:
    """Coleta dados macro Brasil em paralelo."""
    key = "macro:engine:brasil"
    cached = cache.get(key)
    if cached:
        return cached

    from app.data.yfinance_client import get_dolar_yf, get_ibov_yf

    selic, ipca, dolar_yf, ibov_yf = await asyncio.gather(
        get_selic(),
        get_ipca(),
        get_dolar_yf(),
        get_ibov_yf(),
    )

    # Focus BCB (Olinda) — importa inline para evitar dependência circular
    from app.cerebro.focus_bcb import get_focus_selic, get_focus_ipca
    selic_exp, ipca_exp = await asyncio.gather(
        get_focus_selic(),
        get_focus_ipca(),
    )

    juro_real = None
    if selic is not None and ipca_exp is not None:
        juro_real = selic - ipca_exp

    result = {
        "selic": selic,
        "ipca_12m": ipca,
        "ipca_expectativa": ipca_exp,
        "selic_expectativa": selic_exp,
        "juro_real": juro_real,
        "dolar_brl": dolar_yf.get("price") if dolar_yf else None,
        "dolar_var_pct": dolar_yf.get("change_pct") if dolar_yf else None,
        "ibov": ibov_yf.get("price") if ibov_yf else None,
        "ibov_var_pct": ibov_yf.get("change_pct") if ibov_yf else None,
    }
    cache.set(key, result, ttl=CACHE_TTL_MACRO_BR)
    return result


# ─── Regime macro 4-estados (scoring) ────────────────────────────────────────

def _calcular_regime_macro(ctx: MacroContext) -> tuple[str, int, int]:
    """
    Calcula regime macro baseado em pontuação de indicadores.
    Retorna (regime_4state, score 0-100, confiança 0-100).

    Cada indicador contribui com pontos positivos (risk-on) ou negativos (risk-off).
    Score final é normalizado para 0-100.
    Confiança mede o quanto os sinais concordam entre si.
    """
    sinais: list[int] = []  # +1 = risk-on, -1 = risk-off, 0 = neutro

    pontos = 50  # base neutra

    # --- VIX ---
    if ctx.vix is not None:
        if ctx.vix < 15:
            pontos += 15; sinais.append(1)
        elif ctx.vix < 20:
            pontos += 5; sinais.append(1)
        elif ctx.vix < 25:
            sinais.append(0)
        elif ctx.vix < 30:
            pontos -= 10; sinais.append(-1)
        else:
            pontos -= 20; sinais.append(-1)

    # --- DXY vs MM50 ---
    if ctx.dxy is not None and ctx.dxy_mm50 is not None:
        if ctx.dxy < ctx.dxy_mm50:
            pontos += 10; sinais.append(1)   # dólar fraco = bom p/ emergentes
        else:
            pontos -= 10; sinais.append(-1)

    # --- Juro real BR ---
    if ctx.juro_real is not None:
        if ctx.juro_real < 4:
            pontos += 10; sinais.append(1)
        elif ctx.juro_real < 6:
            sinais.append(0)
        else:
            pontos -= 15; sinais.append(-1)

    # --- Treasury 10Y ---
    if ctx.treasury_10y is not None:
        if ctx.treasury_10y < 4:
            pontos += 10; sinais.append(1)
        elif ctx.treasury_10y < 5:
            sinais.append(0)
        else:
            pontos -= 10; sinais.append(-1)

    # --- Yield spread (curva de juros) ---
    if ctx.yield_spread is not None:
        if ctx.yield_spread > 0:
            pontos += 10; sinais.append(1)
        else:
            pontos -= 15; sinais.append(-1)  # curva invertida

    # --- S&P 500 vs MM200 ---
    if ctx.sp500 is not None and ctx.sp500_mm200 is not None:
        if ctx.sp500 > ctx.sp500_mm200:
            pontos += 10; sinais.append(1)
        else:
            pontos -= 10; sinais.append(-1)

    # --- IBOV direction ---
    if ctx.ibov_var_pct is not None:
        if ctx.ibov_var_pct > 0:
            pontos += 5; sinais.append(1)
        elif ctx.ibov_var_pct < -1:
            pontos -= 5; sinais.append(-1)
        else:
            sinais.append(0)

    # --- Petróleo ---
    if ctx.petroleo_wti is not None:
        if 60 <= ctx.petroleo_wti <= 90:
            pontos += 5; sinais.append(1)
        elif ctx.petroleo_wti > 100:
            pontos -= 5; sinais.append(-1)
        else:
            sinais.append(0)

    # Clamp score entre 0 e 100
    score = max(0, min(100, pontos))

    # Confiança: mede concordância dos sinais
    if sinais:
        positivos = sum(1 for s in sinais if s > 0)
        negativos = sum(1 for s in sinais if s < 0)
        total = len(sinais)
        maioria = max(positivos, negativos)
        confianca = int((maioria / total) * 100)
    else:
        confianca = 0

    # Classificar regime
    if score >= 70:
        regime = RegimeMacro.RISK_ON_FORTE
    elif score >= 45:
        regime = RegimeMacro.RISK_ON_MODERADO
    elif score >= 25:
        regime = RegimeMacro.NEUTRO
    else:
        regime = RegimeMacro.RISK_OFF

    return regime, score, confianca


def _classificar_fase_selic(selic: Optional[float], selic_exp: Optional[float]) -> str:
    """
    Classifica a fase do ciclo Selic com base na taxa atual vs expectativa Focus.

    - ALTA:      mercado espera Selic subir (exp > atual + 0.5)
    - PICO:      Selic alta (~12%+) e estável (exp ≈ atual)
    - TRANSICAO: indefinido ou dados insuficientes
    - QUEDA:     mercado espera Selic cair (exp < atual - 0.5)
    - VALE:      Selic baixa (~8%-) e estável (exp ≈ atual)
    """
    if selic is None or selic_exp is None:
        return FaseSelic.TRANSICAO

    diff = selic_exp - selic

    if diff >= 0.5:
        return FaseSelic.ALTA
    elif diff <= -0.5:
        return FaseSelic.QUEDA
    else:
        # Selic e expectativa próximas — estável
        if selic >= 12:
            return FaseSelic.PICO
        elif selic <= 8:
            return FaseSelic.VALE
        else:
            return FaseSelic.TRANSICAO


# ─── Flags macro automáticas ────────────────────────────────────────────────

def _calcular_flags(ctx: MacroContext) -> list[str]:
    """Gera alertas baseados nos dados macro."""
    flags = []

    if ctx.vix is not None and ctx.vix > 25:
        flags.append(f"VIX elevado ({ctx.vix:.1f}) — mercado em modo de cautela")
    if ctx.vix is not None and ctx.vix > 35:
        flags.append(f"VIX em nível de pânico ({ctx.vix:.1f}) — risco extremo")

    if ctx.dxy is not None and ctx.dxy_mm50 is not None and ctx.dxy > ctx.dxy_mm50:
        flags.append("Dólar global forte (DXY acima da MM50) — pressão sobre emergentes")

    if ctx.juro_real is not None and ctx.juro_real > 6:
        flags.append(
            f"Juro real alto ({ctx.juro_real:.1f}%) — renda fixa atrativa vs bolsa"
        )

    if ctx.treasury_10y is not None and ctx.treasury_10y > 5:
        flags.append(
            f"Treasury 10Y em {ctx.treasury_10y:.2f}% — custo global de capital elevado"
        )

    if ctx.petroleo_wti is not None and ctx.petroleo_wti > 100:
        flags.append(f"Petróleo WTI acima de $100 — pressão inflacionária global")
    if ctx.petroleo_wti is not None and ctx.petroleo_wti < 50:
        flags.append(f"Petróleo WTI abaixo de $50 — risco para PETR4/PRIO3/RECV3")

    return flags


# ─── Coleta de calendário econômico ────────────────────────────────────────

async def _coletar_calendario() -> list:
    """Busca eventos econômicos reais via calendar_client (Finnhub + BCB)."""
    try:
        from app.data.calendar_client import get_eventos_semana
        return await get_eventos_semana()
    except Exception as e:
        logger.warning("MacroEngine._coletar_calendario falhou: %s", e)
        return []


# ─── Entry point público ────────────────────────────────────────────────────

async def montar_macro() -> MacroContext:
    """
    Monta o MacroContext completo — ponto de entrada para todos os módulos.
    Chamadas paralelas para global e Brasil.
    """
    key = "macro:engine:full"
    cached = cache.get(key)
    if cached:
        return cached

    try:
        global_data, brasil_data, calendario = await asyncio.gather(
            _coletar_global(),
            _coletar_brasil(),
            _coletar_calendario(),
        )
    except Exception as e:
        logger.error("MacroEngine falhou: %s", e)
        global_data, brasil_data, calendario = {}, {}, []

    ctx = MacroContext(
        treasury_10y=global_data.get("treasury_10y"),
        treasury_2y=global_data.get("treasury_2y"),
        yield_spread=global_data.get("yield_spread"),
        vix=global_data.get("vix"),
        dxy=global_data.get("dxy"),
        dxy_mm50=global_data.get("dxy_mm50"),
        petroleo_wti=global_data.get("petroleo_wti"),
        petroleo_brent=global_data.get("petroleo_brent"),
        sp500=global_data.get("sp500"),
        sp500_var_pct=global_data.get("sp500_var_pct"),
        sp500_mm50=global_data.get("sp500_mm50"),
        sp500_mm200=global_data.get("sp500_mm200"),
        ouro=global_data.get("ouro"),
        selic=brasil_data.get("selic"),
        ipca_12m=brasil_data.get("ipca_12m"),
        ipca_expectativa=brasil_data.get("ipca_expectativa"),
        selic_expectativa=brasil_data.get("selic_expectativa"),
        juro_real=brasil_data.get("juro_real"),
        dolar_brl=brasil_data.get("dolar_brl"),
        dolar_var_pct=brasil_data.get("dolar_var_pct"),
        ibov=brasil_data.get("ibov"),
        ibov_var_pct=brasil_data.get("ibov_var_pct"),
        calendario_eventos=calendario,
        atualizado_em=datetime.now(timezone.utc).isoformat(),
    )

    # ── Regime macro 4-estados + fase Selic + guardrails ──
    regime, score, confianca = _calcular_regime_macro(ctx)
    ctx.regime_macro = regime
    ctx.regime_score = score
    ctx.confianca = confianca
    ctx.fase_selic = _classificar_fase_selic(ctx.selic, ctx.selic_expectativa)
    ctx.guardrails = GUARDRAILS_POR_REGIME.get(regime, GUARDRAILS_POR_REGIME[RegimeMacro.NEUTRO])

    ctx.flags = _calcular_flags(ctx)

    cache.set(key, ctx, ttl=CACHE_TTL_MACRO_BR)
    return ctx

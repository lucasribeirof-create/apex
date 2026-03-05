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


# Cache TTL dinâmico — mais curto durante pregão para dados frescos
# Se force_fresh=True (briefing), ignora cache e busca dados novos
CACHE_TTL_MACRO_GLOBAL = 600    # 10 min (era 30 min)
CACHE_TTL_MACRO_BR = 300         # 5 min (era 10 min)


# ─── Dataclass principal ────────────────────────────────────────────────────

@dataclass
class MacroContext:
    """Snapshot macro completo — global + Brasil."""

    # Global
    treasury_10y: Optional[float] = None       # US Treasury 10Y yield (%)
    vix: Optional[float] = None                # Índice de volatilidade
    dxy: Optional[float] = None                # Dollar Index
    dxy_mm50: Optional[float] = None           # DXY MM50 (para flag "dólar forte")
    dxy_ytd_pct: Optional[float] = None        # DXY variação YTD (%)
    petroleo_wti: Optional[float] = None       # WTI (USD/barril)
    petroleo_brent: Optional[float] = None     # Brent (USD/barril)
    petroleo_wti_ytd_pct: Optional[float] = None  # WTI variação YTD (%)
    sp500: Optional[float] = None              # S&P 500 preço
    sp500_var_pct: Optional[float] = None      # S&P 500 variação dia (%)
    sp500_ytd_pct: Optional[float] = None      # S&P 500 variação YTD (%)
    sp500_mm50: Optional[float] = None         # S&P 500 MM50
    sp500_mm200: Optional[float] = None        # S&P 500 MM200
    nasdaq: Optional[float] = None             # Nasdaq Composite preço
    nasdaq_var_pct: Optional[float] = None     # Nasdaq variação dia (%)
    nasdaq_ytd_pct: Optional[float] = None     # Nasdaq variação YTD (%)
    ouro: Optional[float] = None               # Ouro (USD/oz)
    ouro_ytd_pct: Optional[float] = None       # Ouro variação YTD (%)
    bitcoin: Optional[float] = None            # Bitcoin (USD)
    bitcoin_var_pct: Optional[float] = None    # Bitcoin variação dia (%)
    bitcoin_ytd_pct: Optional[float] = None    # Bitcoin variação YTD (%)

    # Brasil
    selic: Optional[float] = None              # Meta Selic (% a.a.)
    ipca_12m: Optional[float] = None           # IPCA acumulado 12 meses (%)
    ipca_expectativa: Optional[float] = None   # IPCA esperado 12 meses (Focus)
    selic_expectativa: Optional[float] = None  # Selic esperada fim do ano (Focus)
    juro_real: Optional[float] = None          # Selic - IPCA expectativa
    dolar_brl: Optional[float] = None          # USD/BRL
    dolar_var_pct: Optional[float] = None      # USD/BRL variação dia (%)
    dolar_ytd_pct: Optional[float] = None      # USD/BRL variação YTD (%)
    ibov: Optional[float] = None               # IBOVESPA pontos
    ibov_var_pct: Optional[float] = None       # IBOVESPA variação dia (%)
    ibov_ytd_pct: Optional[float] = None       # IBOVESPA variação YTD (%)

    # Metadata
    atualizado_em: Optional[str] = None

    # Narrativa automática do mercado
    narrativa: Optional[str] = None

    # Flags macro (preenchidas por _calcular_flags)
    flags: list[str] = field(default_factory=list)

    def resumo_texto(self) -> str:
        """Texto denso para injetar no prompt da IA."""
        partes = []

        partes.append("=== MERCADO GLOBAL ===")
        if self.sp500 is not None:
            txt = f"S&P 500: {self.sp500:,.0f}"
            if self.sp500_var_pct is not None:
                txt += f" (dia: {self.sp500_var_pct:+.2f}%)"
            if self.sp500_ytd_pct is not None:
                txt += f" (YTD: {self.sp500_ytd_pct:+.1f}%)"
            partes.append(txt)
        if self.nasdaq is not None:
            txt = f"Nasdaq: {self.nasdaq:,.0f}"
            if self.nasdaq_var_pct is not None:
                txt += f" (dia: {self.nasdaq_var_pct:+.2f}%)"
            if self.nasdaq_ytd_pct is not None:
                txt += f" (YTD: {self.nasdaq_ytd_pct:+.1f}%)"
            partes.append(txt)
        if self.treasury_10y is not None:
            partes.append(f"US Treasury 10Y: {self.treasury_10y:.2f}%")
        if self.vix is not None:
            partes.append(f"VIX: {self.vix:.1f}")
        if self.dxy is not None:
            txt = f"DXY (Dollar Index): {self.dxy:.2f}"
            if self.dxy_mm50:
                rel = "acima" if self.dxy > self.dxy_mm50 else "abaixo"
                txt += f" ({rel} da MM50 {self.dxy_mm50:.2f})"
            if self.dxy_ytd_pct is not None:
                txt += f" (YTD: {self.dxy_ytd_pct:+.1f}%)"
            partes.append(txt)
        if self.petroleo_wti is not None:
            txt = f"Petróleo WTI: ${self.petroleo_wti:.2f}"
            if self.petroleo_wti_ytd_pct is not None:
                txt += f" (YTD: {self.petroleo_wti_ytd_pct:+.1f}%)"
            partes.append(txt)
        if self.petroleo_brent is not None:
            partes.append(f"Petróleo Brent: ${self.petroleo_brent:.2f}")
        if self.ouro is not None:
            txt = f"Ouro: ${self.ouro:,.0f}/oz"
            if self.ouro_ytd_pct is not None:
                txt += f" (YTD: {self.ouro_ytd_pct:+.1f}%)"
            partes.append(txt)
        if self.bitcoin is not None:
            txt = f"Bitcoin: ${self.bitcoin:,.0f}"
            if self.bitcoin_var_pct is not None:
                txt += f" (dia: {self.bitcoin_var_pct:+.2f}%)"
            if self.bitcoin_ytd_pct is not None:
                txt += f" (YTD: {self.bitcoin_ytd_pct:+.1f}%)"
            partes.append(txt)

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
                txt += f" (dia: {self.dolar_var_pct:+.2f}%)"
            if self.dolar_ytd_pct is not None:
                txt += f" (YTD: {self.dolar_ytd_pct:+.1f}%)"
            partes.append(txt)
        if self.ibov is not None:
            txt = f"IBOV: {self.ibov:,.0f}"
            if self.ibov_var_pct is not None:
                txt += f" (dia: {self.ibov_var_pct:+.2f}%)"
            if self.ibov_ytd_pct is not None:
                txt += f" (YTD: {self.ibov_ytd_pct:+.1f}%)"
            partes.append(txt)

        if self.narrativa:
            partes.append(f"\n=== NARRATIVA DE MERCADO ===\n{self.narrativa}")

        if self.flags:
            partes.append("\n=== ALERTAS MACRO ===")
            for flag in self.flags:
                partes.append(f"⚠ {flag}")

        return "\n".join(partes)


# ─── Coleta de dados globais ────────────────────────────────────────────────

async def _coletar_global_e_ytd() -> tuple[dict, dict]:
    """Coleta TODOS os dados yfinance em UM ÚNICO batch download (thread-safe).
    Retorna (global_data, ytd_data).
    yfinance NÃO é thread-safe em chamadas paralelas — download batch único.
    """
    g_key = "macro:engine:global"
    y_key = "macro:engine:ytd"
    g_cached = cache.get(g_key)
    y_cached = cache.get(y_key)
    if g_cached and y_cached:
        return g_cached, y_cached

    # Todos os tickers que precisamos
    symbols = [
        "^TNX",       # US Treasury 10Y
        "^VIX",       # Volatility Index
        "DX-Y.NYB",   # Dollar Index
        "CL=F",       # WTI Oil
        "BZ=F",       # Brent Oil
        "^GSPC",      # S&P 500
        "GC=F",       # Gold
        "^IXIC",      # Nasdaq
        "BTC-USD",    # Bitcoin
        "USDBRL=X",   # USD/BRL (Dólar)
        "^BVSP",      # IBOVESPA
    ]

    try:
        df = await _run_sync(
            lambda: yf.download(symbols, period="1y", interval="1d", progress=False)
        )
    except Exception as e:
        logger.error("macro._coletar_global_e_ytd batch download falhou: %s", e)
        return {}, {}

    if df.empty:
        logger.error("macro._coletar_global_e_ytd: DataFrame vazio")
        return {}, {}

    # ── Helper functions ──
    def _safe_last(symbol: str) -> Optional[float]:
        try:
            s = df["Close"][symbol].dropna()
            return float(s.iloc[-1]) if len(s) > 0 else None
        except Exception:
            return None

    def _safe_change(symbol: str) -> Optional[float]:
        try:
            s = df["Close"][symbol].dropna()
            if len(s) < 2:
                return None
            last, prev = float(s.iloc[-1]), float(s.iloc[-2])
            return (last - prev) / prev * 100 if prev != 0 else None
        except Exception:
            return None

    def _safe_mm(symbol: str, period: int) -> Optional[float]:
        try:
            s = df["Close"][symbol].dropna()
            return float(s.values[-period:].mean()) if len(s) >= period else None
        except Exception:
            return None

    def _safe_ytd(symbol: str) -> Optional[float]:
        """YTD = (last_close - first_close_of_year) / first_close_of_year * 100"""
        try:
            s = df["Close"][symbol].dropna()
            from datetime import date
            year_start = f"{date.today().year}-01-01"
            year_data = s[s.index >= year_start]
            if year_data.empty or len(year_data) < 2:
                return None
            first, last = float(year_data.iloc[0]), float(year_data.iloc[-1])
            return round((last - first) / first * 100, 2) if first != 0 else None
        except Exception:
            return None

    # ── Global data ──
    global_data = {
        "treasury_10y":   _safe_last("^TNX"),
        "vix":            _safe_last("^VIX"),
        "dxy":            _safe_last("DX-Y.NYB"),
        "dxy_mm50":       _safe_mm("DX-Y.NYB", 50),
        "petroleo_wti":   _safe_last("CL=F"),
        "petroleo_brent": _safe_last("BZ=F"),
        "sp500":          _safe_last("^GSPC"),
        "sp500_var_pct":  _safe_change("^GSPC"),
        "sp500_mm50":     _safe_mm("^GSPC", 50),
        "sp500_mm200":    _safe_mm("^GSPC", 200),
        "ouro":           _safe_last("GC=F"),
        "nasdaq":         _safe_last("^IXIC"),
        "nasdaq_var_pct": _safe_change("^IXIC"),
        "bitcoin":        _safe_last("BTC-USD"),
        "bitcoin_var_pct": _safe_change("BTC-USD"),
        "dolar_brl":      _safe_last("USDBRL=X"),
        "dolar_var_pct":  _safe_change("USDBRL=X"),
        "ibov":           _safe_last("^BVSP"),
        "ibov_var_pct":   _safe_change("^BVSP"),
    }

    # ── YTD data ──
    ytd_data = {
        "sp500_ytd_pct":         _safe_ytd("^GSPC"),
        "nasdaq_ytd_pct":        _safe_ytd("^IXIC"),
        "ibov_ytd_pct":          _safe_ytd("^BVSP"),
        "dolar_ytd_pct":         _safe_ytd("USDBRL=X"),
        "dxy_ytd_pct":           _safe_ytd("DX-Y.NYB"),
        "ouro_ytd_pct":          _safe_ytd("GC=F"),
        "petroleo_wti_ytd_pct":  _safe_ytd("CL=F"),
        "bitcoin_ytd_pct":       _safe_ytd("BTC-USD"),
    }

    cache.set(g_key, global_data, ttl=CACHE_TTL_MACRO_GLOBAL)
    cache.set(y_key, ytd_data, ttl=CACHE_TTL_MACRO_GLOBAL)

    logger.info("yFinance batch: %d campos globais, %d YTDs preenchidos",
                sum(1 for v in global_data.values() if v is not None),
                sum(1 for v in ytd_data.values() if v is not None))
    return global_data, ytd_data
    return result


async def _coletar_brasil() -> dict:
    """Coleta dados macro Brasil (BCB + Focus, sem yfinance)."""
    key = "macro:engine:brasil"
    cached = cache.get(key)
    if cached:
        return cached

    selic, ipca = await asyncio.gather(
        get_selic(),
        get_ipca(),
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
    }
    cache.set(key, result, ttl=CACHE_TTL_MACRO_BR)
    return result


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

    # ── Flags YTD ──
    if ctx.ibov_ytd_pct is not None and ctx.ibov_ytd_pct > 20:
        flags.append(f"IBOV em rali excepcional ({ctx.ibov_ytd_pct:+.1f}% YTD) — cuidado com euforia, manter stops")
    if ctx.ibov_ytd_pct is not None and ctx.ibov_ytd_pct < -15:
        flags.append(f"IBOV em bear market ({ctx.ibov_ytd_pct:+.1f}% YTD) — oportunidade de compra para longo prazo")

    if ctx.sp500_ytd_pct is not None and ctx.sp500_ytd_pct < -10:
        flags.append(f"S&P 500 em correção ({ctx.sp500_ytd_pct:+.1f}% YTD) — cautela com ativos correlacionados")

    if ctx.ouro_ytd_pct is not None and ctx.ouro_ytd_pct > 20:
        flags.append(f"Ouro em rali ({ctx.ouro_ytd_pct:+.1f}% YTD) — sinal de busca por segurança global")

    if ctx.sp500 is not None and ctx.sp500_mm200 is not None and ctx.sp500 < ctx.sp500_mm200:
        flags.append("S&P 500 abaixo da MM200 — tendência de longo prazo comprometida")

    if ctx.dolar_ytd_pct is not None and ctx.dolar_ytd_pct > 10:
        flags.append(f"Real desvalorizando forte ({ctx.dolar_ytd_pct:+.1f}% YTD) — risco cambial elevado")

    return flags


def _gerar_narrativa(ctx: MacroContext) -> str:
    """Gera narrativa automática do mercado com base nos dados coletados."""
    partes = []

    # ── Mercado americano ──
    if ctx.sp500_ytd_pct is not None:
        if ctx.sp500_ytd_pct > 15:
            partes.append(f"Mercado americano em forte rali no ano (S&P 500 {ctx.sp500_ytd_pct:+.1f}% YTD), indicando apetite por risco global")
        elif ctx.sp500_ytd_pct > 5:
            partes.append(f"Mercado americano positivo no ano (S&P 500 {ctx.sp500_ytd_pct:+.1f}% YTD)")
        elif ctx.sp500_ytd_pct > -5:
            partes.append(f"Mercado americano lateralizado no ano (S&P 500 {ctx.sp500_ytd_pct:+.1f}% YTD)")
        else:
            partes.append(f"Mercado americano em correção no ano (S&P 500 {ctx.sp500_ytd_pct:+.1f}% YTD), sinalizando aversão a risco")

    # ── Tech/Growth vs Broad Market ──
    if ctx.nasdaq_ytd_pct is not None and ctx.sp500_ytd_pct is not None:
        diff = ctx.nasdaq_ytd_pct - ctx.sp500_ytd_pct
        if diff > 5:
            partes.append(f"Setor de tecnologia liderando (Nasdaq {ctx.nasdaq_ytd_pct:+.1f}% vs S&P {ctx.sp500_ytd_pct:+.1f}% YTD) — rotação para growth")
        elif diff < -5:
            partes.append(f"Mercado amplo superando tech (Nasdaq {ctx.nasdaq_ytd_pct:+.1f}% vs S&P {ctx.sp500_ytd_pct:+.1f}% YTD) — rotação para value/defensivos")

    # ── Volatilidade ──
    if ctx.vix is not None:
        if ctx.vix < 15:
            partes.append(f"Volatilidade muito baixa (VIX {ctx.vix:.0f}) — ambiente de risk-on")
        elif ctx.vix > 30:
            partes.append(f"Volatilidade extrema (VIX {ctx.vix:.0f}) — modo de crise, proteção de capital é prioridade")
        elif ctx.vix > 25:
            partes.append(f"Volatilidade elevada (VIX {ctx.vix:.0f}) — mercado em modo de cautela")

    # ── Juros americanos ──
    if ctx.treasury_10y is not None:
        if ctx.treasury_10y > 5:
            partes.append(f"Juros longos americanos muito altos (Treasury 10Y {ctx.treasury_10y:.2f}%) — pressão sobre ativos de risco e emergentes")
        elif ctx.treasury_10y > 4.5:
            partes.append(f"Juros longos americanos elevados (Treasury 10Y {ctx.treasury_10y:.2f}%) — competição com renda variável")
        elif ctx.treasury_10y < 3.5:
            partes.append(f"Juros americanos em queda (Treasury 10Y {ctx.treasury_10y:.2f}%) — favorável para mercados emergentes")

    # ── Bolsa brasileira ──
    if ctx.ibov_ytd_pct is not None:
        if ctx.ibov_ytd_pct > 15:
            partes.append(f"Bolsa brasileira em forte alta no ano (IBOV {ctx.ibov_ytd_pct:+.1f}% YTD), fluxo estrangeiro provável")
        elif ctx.ibov_ytd_pct > 5:
            partes.append(f"Bolsa brasileira em alta no ano (IBOV {ctx.ibov_ytd_pct:+.1f}% YTD)")
        elif ctx.ibov_ytd_pct > -5:
            partes.append(f"Bolsa brasileira estável no ano (IBOV {ctx.ibov_ytd_pct:+.1f}% YTD)")
        else:
            partes.append(f"Bolsa brasileira em queda no ano (IBOV {ctx.ibov_ytd_pct:+.1f}% YTD) — momento defensivo")

    # ── Dólar / Câmbio ──
    if ctx.dolar_brl is not None and ctx.dolar_ytd_pct is not None:
        if ctx.dolar_ytd_pct > 5:
            partes.append(f"Real desvalorizando no ano (USD/BRL R${ctx.dolar_brl:.2f}, {ctx.dolar_ytd_pct:+.1f}% YTD) — favorece exportadoras e hedge cambial")
        elif ctx.dolar_ytd_pct < -5:
            partes.append(f"Real valorizando no ano (USD/BRL R${ctx.dolar_brl:.2f}, {ctx.dolar_ytd_pct:+.1f}% YTD) — favorece consumo interno")
        else:
            partes.append(f"Câmbio estável no ano (USD/BRL R${ctx.dolar_brl:.2f}, {ctx.dolar_ytd_pct:+.1f}% YTD)")

    # ── Juros Brasil ──
    if ctx.selic is not None:
        if ctx.selic >= 13:
            partes.append(f"Selic em patamar restritivo ({ctx.selic:.1f}% a.a.) — RF pós-fixada muito atrativa, pressiona valuations de ações e FIIs")
        elif ctx.selic >= 10:
            partes.append(f"Selic alta ({ctx.selic:.1f}% a.a.) — CDI competitivo com renda variável")
        elif ctx.selic < 8:
            partes.append(f"Selic baixa ({ctx.selic:.1f}% a.a.) — favorável para renda variável e FIIs")

        if ctx.selic_expectativa is not None:
            diff = ctx.selic_expectativa - ctx.selic
            if diff < -1:
                partes.append(f"Mercado precifica cortes (Selic esperada {ctx.selic_expectativa:.1f}%) — ciclo de afrouxamento favorece prefixados, FIIs e ações")
            elif diff > 1:
                partes.append(f"Mercado precifica altas (Selic esperada {ctx.selic_expectativa:.1f}%) — aperto monetário adiante, cautela com duration")

    # ── Commodities ──
    if ctx.ouro_ytd_pct is not None:
        if ctx.ouro_ytd_pct > 10:
            partes.append(f"Ouro em forte alta ({ctx.ouro_ytd_pct:+.1f}% YTD) — busca por proteção/hedge global")
        elif ctx.ouro_ytd_pct < -5:
            partes.append(f"Ouro em queda ({ctx.ouro_ytd_pct:+.1f}% YTD) — dólar forte desfavorece metais")

    if ctx.petroleo_wti is not None and ctx.petroleo_wti_ytd_pct is not None:
        if ctx.petroleo_wti_ytd_pct > 10:
            partes.append(f"Petróleo em alta ({ctx.petroleo_wti_ytd_pct:+.1f}% YTD, WTI ${ctx.petroleo_wti:.0f}) — favorece PETR4/PRIO3, pressiona inflação")
        elif ctx.petroleo_wti_ytd_pct < -10:
            partes.append(f"Petróleo em queda ({ctx.petroleo_wti_ytd_pct:+.1f}% YTD) — alívio inflacionário mas pressão sobre petroleiras")

    # ── Bitcoin / Crypto ──
    if ctx.bitcoin is not None and ctx.bitcoin_ytd_pct is not None:
        if ctx.bitcoin_ytd_pct > 30:
            partes.append(f"Bitcoin em forte alta (${ctx.bitcoin:,.0f}, {ctx.bitcoin_ytd_pct:+.1f}% YTD) — apetite por risco/especulação elevado")
        elif ctx.bitcoin_ytd_pct < -20:
            partes.append(f"Bitcoin em queda (${ctx.bitcoin:,.0f}, {ctx.bitcoin_ytd_pct:+.1f}% YTD) — aversão a risco cripto")

    if not partes:
        return "Dados insuficientes para gerar narrativa de mercado."

    return ". ".join(partes) + "."


# ─── Entry point público ────────────────────────────────────────────────────

async def montar_macro(force_fresh: bool = False) -> MacroContext:
    """
    Monta o MacroContext completo — ponto de entrada para todos os módulos.
    Chamadas paralelas para global e Brasil.
    
    Args:
        force_fresh: Se True, ignora TODO o cache e busca dados novos.
                     Usar na geração de briefing para garantir dados do momento.
    """
    key = "macro:engine:full"
    if not force_fresh:
        cached = cache.get(key)
        if cached:
            return cached
    else:
        # Limpa caches intermediários para forçar coleta nova
        cache.delete(key)
        cache.delete("macro:engine:global")
        cache.delete("macro:engine:ytd")
        cache.delete("macro:engine:brasil")

    try:
        # yfinance em UM ÚNICO batch (thread-safe) + BCB em paralelo (API diferente)
        (global_data, ytd_data), brasil_data = await asyncio.gather(
            _coletar_global_e_ytd(),
            _coletar_brasil(),
        )
    except Exception as e:
        logger.error("MacroEngine falhou: %s", e)
        global_data, brasil_data, ytd_data = {}, {}, {}

    ctx = MacroContext(
        treasury_10y=global_data.get("treasury_10y"),
        vix=global_data.get("vix"),
        dxy=global_data.get("dxy"),
        dxy_mm50=global_data.get("dxy_mm50"),
        dxy_ytd_pct=ytd_data.get("dxy_ytd_pct"),
        petroleo_wti=global_data.get("petroleo_wti"),
        petroleo_brent=global_data.get("petroleo_brent"),
        petroleo_wti_ytd_pct=ytd_data.get("petroleo_wti_ytd_pct"),
        sp500=global_data.get("sp500"),
        sp500_var_pct=global_data.get("sp500_var_pct"),
        sp500_ytd_pct=ytd_data.get("sp500_ytd_pct"),
        sp500_mm50=global_data.get("sp500_mm50"),
        sp500_mm200=global_data.get("sp500_mm200"),
        nasdaq=global_data.get("nasdaq"),
        nasdaq_var_pct=global_data.get("nasdaq_var_pct"),
        nasdaq_ytd_pct=ytd_data.get("nasdaq_ytd_pct"),
        ouro=global_data.get("ouro"),
        ouro_ytd_pct=ytd_data.get("ouro_ytd_pct"),
        bitcoin=global_data.get("bitcoin"),
        bitcoin_var_pct=global_data.get("bitcoin_var_pct"),
        bitcoin_ytd_pct=ytd_data.get("bitcoin_ytd_pct"),
        selic=brasil_data.get("selic"),
        ipca_12m=brasil_data.get("ipca_12m"),
        ipca_expectativa=brasil_data.get("ipca_expectativa"),
        selic_expectativa=brasil_data.get("selic_expectativa"),
        juro_real=brasil_data.get("juro_real"),
        dolar_brl=global_data.get("dolar_brl"),
        dolar_var_pct=global_data.get("dolar_var_pct"),
        dolar_ytd_pct=ytd_data.get("dolar_ytd_pct"),
        ibov=global_data.get("ibov"),
        ibov_var_pct=global_data.get("ibov_var_pct"),
        ibov_ytd_pct=ytd_data.get("ibov_ytd_pct"),
        atualizado_em=datetime.now(timezone.utc).isoformat(),
    )
    ctx.flags = _calcular_flags(ctx)
    _sanity_check(ctx)   # Anula valores absurdos ANTES de gerar narrativa/flags
    ctx.narrativa = _gerar_narrativa(ctx)

    cache.set(key, ctx, ttl=CACHE_TTL_MACRO_BR)
    return ctx


# ─── Sanity checks ──────────────────────────────────────────────────────────

# Faixas razoáveis — se fora, o dado provavelmente é lixo de API.
# Valores baseados em extremos históricos com margem. Ex: SP500 nunca foi < 1000.
_SANITY_RANGES: dict[str, tuple[float, float]] = {
    "sp500":           (1000, 20000),
    "sp500_mm50":      (1000, 20000),
    "sp500_mm200":     (1000, 20000),
    "nasdaq":          (1000, 40000),
    "vix":             (5, 100),
    "treasury_10y":    (0, 20),
    "dxy":             (50, 150),
    "dxy_mm50":        (50, 150),
    "petroleo_wti":    (5, 300),
    "petroleo_brent":  (5, 300),
    "ouro":            (500, 15000),
    "bitcoin":         (1000, 1000000),
    "selic":           (0, 30),
    "ipca_12m":        (0, 30),
    "ipca_expectativa": (0, 30),
    "selic_expectativa": (0, 30),
    "juro_real":       (-10, 25),
    "dolar_brl":       (1, 15),
    "ibov":            (20000, 400000),
}
# Variações diárias > ±25% ou YTD > ±80% são quase certamente erros.
_VAR_DIA_MAX = 25.0
_VAR_YTD_MAX = 80.0


def _sanity_check(ctx: MacroContext) -> None:
    """Anula campos com valores absurdos para impedir dados errados no prompt."""
    for field_name, (lo, hi) in _SANITY_RANGES.items():
        val = getattr(ctx, field_name, None)
        if val is not None and (val < lo or val > hi):
            logger.warning(
                "SANITY FAIL: %s = %s (faixa válida: %s-%s). Anulando.",
                field_name, val, lo, hi,
            )
            setattr(ctx, field_name, None)

    # Variações diárias
    for field_name in ("sp500_var_pct", "nasdaq_var_pct", "dolar_var_pct",
                       "ibov_var_pct", "bitcoin_var_pct"):
        val = getattr(ctx, field_name, None)
        if val is not None and abs(val) > _VAR_DIA_MAX:
            logger.warning(
                "SANITY FAIL: %s = %.2f%% (máx: ±%.0f%%). Anulando.",
                field_name, val, _VAR_DIA_MAX,
            )
            setattr(ctx, field_name, None)

    # Variações YTD
    for field_name in ("sp500_ytd_pct", "nasdaq_ytd_pct", "ibov_ytd_pct",
                       "dolar_ytd_pct", "dxy_ytd_pct", "ouro_ytd_pct",
                       "petroleo_wti_ytd_pct", "bitcoin_ytd_pct"):
        val = getattr(ctx, field_name, None)
        if val is not None and abs(val) > _VAR_YTD_MAX:
            logger.warning(
                "SANITY FAIL: %s = %.2f%% (máx: ±%.0f%%). Anulando.",
                field_name, val, _VAR_YTD_MAX,
            )
            setattr(ctx, field_name, None)

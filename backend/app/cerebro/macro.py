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

@dataclass
class MacroContext:
    """Snapshot macro completo — global + Brasil."""

    # Global
    treasury_10y: Optional[float] = None       # US Treasury 10Y yield (%)
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

        if self.flags:
            partes.append("\n=== ALERTAS MACRO ===")
            for flag in self.flags:
                partes.append(f"⚠ {flag}")

        return "\n".join(partes)


# ─── Coleta de dados globais ────────────────────────────────────────────────

async def _get_yf_price(symbol: str) -> Optional[float]:
    """Busca last_price de um ticker yFinance."""
    try:
        ticker = await _run_sync(lambda: yf.Ticker(symbol))
        info = await _run_sync(lambda: ticker.fast_info)
        return float(info.last_price)
    except Exception as e:
        logger.debug("macro._get_yf_price(%s) falhou: %s", symbol, e)
        return None


async def _get_yf_price_and_change(symbol: str) -> tuple[Optional[float], Optional[float]]:
    """Busca last_price e variação % de um ticker yFinance."""
    try:
        ticker = await _run_sync(lambda: yf.Ticker(symbol))
        info = await _run_sync(lambda: ticker.fast_info)
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
        df = await _run_sync(
            lambda: yf.download(symbol, period="6mo", interval="1d", progress=False)
        )
        if df.empty or len(df) < period:
            return None
        closes = df["Close"].values.flatten()
        return float(sum(closes[-period:]) / period)
    except Exception:
        return None


async def _coletar_global() -> dict:
    """Coleta todos os dados globais em paralelo."""
    key = "macro:engine:global"
    cached = cache.get(key)
    if cached:
        return cached

    (
        treasury, vix, dxy, wti, brent, (sp500, sp500_var), ouro,
        dxy_mm50, sp500_mm50, sp500_mm200,
    ) = await asyncio.gather(
        _get_yf_price("^TNX"),
        _get_yf_price("^VIX"),
        _get_yf_price("DX-Y.NYB"),
        _get_yf_price("CL=F"),
        _get_yf_price("BZ=F"),
        _get_yf_price_and_change("^GSPC"),
        _get_yf_price("GC=F"),
        _get_yf_mm("DX-Y.NYB", 50),
        _get_yf_mm("^GSPC", 50),
        _get_yf_mm("^GSPC", 200),
    )

    result = {
        "treasury_10y": treasury,
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
        global_data, brasil_data = await asyncio.gather(
            _coletar_global(),
            _coletar_brasil(),
        )
    except Exception as e:
        logger.error("MacroEngine falhou: %s", e)
        global_data, brasil_data = {}, {}

    ctx = MacroContext(
        treasury_10y=global_data.get("treasury_10y"),
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
        atualizado_em=datetime.now(timezone.utc).isoformat(),
    )
    ctx.flags = _calcular_flags(ctx)

    cache.set(key, ctx, ttl=CACHE_TTL_MACRO_BR)
    return ctx

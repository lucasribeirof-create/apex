"""
MacroEngine — Visão de mundo completa para o Cérebro APEX.

Coleta dados macro globais e brasileiros de fontes confiáveis e gratuitas,
consolidando tudo em um MacroContext que alimenta o CEO Brain, Regime,
Narrativa e todos os módulos de decisão.

Fontes:
  Global: yFinance  (^TNX, ^FVX, ^TYX, ^VIX, DX-Y.NYB, CL=F, BZ=F, ^GSPC,
                      GC=F, HG=F, ZS=F, ZC=F, ES=F, NQ=F, EWZ, BTC-USD,
                      HYG, LQD, ^HSI, USDJPY=X, EURUSD=X, USDCNY=X)
  Brasil: BCB/SGS   (Selic 1178, IPCA 433)
          Olinda/BCB (Focus — expectativas Selic e IPCA futuros)
          ANBIMA     (Curva DI pré-fixada — juros futuros)
          yFinance   (USDBRL=X, ^BVSP, IFIX11.SA)
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
    dow_jones: Optional[float] = None           # Dow Jones preço
    dow_jones_var_pct: Optional[float] = None   # Dow Jones variação dia (%)
    ouro: Optional[float] = None               # Ouro (USD/oz)
    sp500_futures: Optional[float] = None       # ES=F — S&P 500 E-mini futures
    sp500_futures_var_pct: Optional[float] = None  # ES=F variação (%)
    nasdaq_futures: Optional[float] = None      # NQ=F — Nasdaq 100 E-mini futures
    nasdaq_futures_var_pct: Optional[float] = None  # NQ=F variação (%)

    # Curva de juros EUA completa
    treasury_5y: Optional[float] = None        # US Treasury 5Y yield (%)
    treasury_30y: Optional[float] = None       # US Treasury 30Y yield (%)
    yield_spread_2y10y: Optional[float] = None # 10Y - 2Y (mesma que yield_spread, alias)
    yield_spread_2y30y: Optional[float] = None # 30Y - 2Y (steepness)

    # Commodities
    cobre: Optional[float] = None              # HG=F — Cobre (USD/lb) — "Dr. Copper"
    soja: Optional[float] = None               # ZS=F — Soja (USD/bushel)
    milho: Optional[float] = None              # ZC=F — Milho (USD/bushel)
    minerio_ferro: Optional[float] = None      # Minério de ferro (proxy ou GX=F)

    # Moedas cross (carry trade & risk)
    usdjpy: Optional[float] = None             # USD/JPY — yen forte = carry unwind
    eurusd: Optional[float] = None             # EUR/USD — fluxo US vs Europa
    usdcny: Optional[float] = None             # USD/CNY — China desvalorizando?

    # Credit spreads
    hyg: Optional[float] = None                # High Yield Bond ETF
    lqd: Optional[float] = None                # Investment Grade Bond ETF
    credit_spread: Optional[float] = None      # HYG yield - LQD yield (spread abrindo = risco)

    # Sentimento / Risk-on
    btc: Optional[float] = None                # BTC-USD preço
    btc_var_pct: Optional[float] = None        # BTC variação dia (%)

    # China
    hang_seng: Optional[float] = None          # ^HSI — Hang Seng Index
    hang_seng_var_pct: Optional[float] = None  # Hang Seng variação dia (%)

    # Brasil EWZ (como gringo vê o Brasil)
    ewz: Optional[float] = None                # EWZ ETF preço
    ewz_var_pct: Optional[float] = None        # EWZ variação dia (%)

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

    # Brasil — IFIX (FIIs)
    ifix: Optional[float] = None               # IFIX11.SA preço
    ifix_var_pct: Optional[float] = None       # IFIX variação dia (%)

    # Brasil — Curva DI (juros futuros)
    di_1ano: Optional[float] = None            # DI pré 1 ano (% a.a.)
    di_2anos: Optional[float] = None           # DI pré 2 anos (% a.a.)
    di_3anos: Optional[float] = None           # DI pré 3 anos (% a.a.)
    di_5anos: Optional[float] = None           # DI pré 5 anos (% a.a.)
    inclinacao_di: Optional[float] = None      # DI 5a - DI 1a (positivo = mercado espera alta)

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
        # Curva de juros EUA
        if self.treasury_10y is not None:
            partes.append(f"US Treasury 10Y: {self.treasury_10y:.2f}%")
        if self.treasury_2y is not None:
            partes.append(f"US Treasury 2Y (proxy): {self.treasury_2y:.2f}%")
        if self.treasury_5y is not None:
            partes.append(f"US Treasury 5Y: {self.treasury_5y:.2f}%")
        if self.treasury_30y is not None:
            partes.append(f"US Treasury 30Y: {self.treasury_30y:.2f}%")
        if self.yield_spread is not None:
            estado = "INVERTIDA ⚠" if self.yield_spread < 0 else "normal"
            partes.append(f"Curva de Juros EUA (10Y-2Y): {self.yield_spread:+.2f}pp ({estado})")
        if self.yield_spread_2y30y is not None:
            partes.append(f"Spread 30Y-2Y: {self.yield_spread_2y30y:+.2f}pp")

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
        if self.dow_jones is not None:
            txt = f"Dow Jones: {self.dow_jones:,.0f}"
            if self.dow_jones_var_pct is not None:
                txt += f" ({self.dow_jones_var_pct:+.2f}%)"
            partes.append(txt)

        # Commodities
        if self.petroleo_wti is not None:
            partes.append(f"Petróleo WTI: ${self.petroleo_wti:.2f}")
        if self.petroleo_brent is not None:
            partes.append(f"Petróleo Brent: ${self.petroleo_brent:.2f}")
        if self.ouro is not None:
            partes.append(f"Ouro: ${self.ouro:,.0f}/oz")
        if self.cobre is not None:
            partes.append(f"Cobre (Dr. Copper): ${self.cobre:.2f}/lb")
        if self.soja is not None:
            partes.append(f"Soja: ${self.soja:.0f}/bu")
        if self.milho is not None:
            partes.append(f"Milho: ${self.milho:.0f}/bu")
        if self.minerio_ferro is not None:
            partes.append(f"Minério de Ferro: ${self.minerio_ferro:.1f}/ton")

        # Moedas cross
        moedas = []
        if self.usdjpy is not None:
            moedas.append(f"USD/JPY {self.usdjpy:.1f}")
        if self.eurusd is not None:
            moedas.append(f"EUR/USD {self.eurusd:.4f}")
        if self.usdcny is not None:
            moedas.append(f"USD/CNY {self.usdcny:.3f}")
        if moedas:
            partes.append(f"Moedas: {' | '.join(moedas)}")

        # Credit spreads
        if self.hyg is not None and self.lqd is not None:
            partes.append(f"Credit: HYG ${self.hyg:.1f} | LQD ${self.lqd:.1f}")
            if self.credit_spread is not None:
                partes.append(f"Credit Spread (proxy): {self.credit_spread:.2f}%")

        # Sentimento
        if self.btc is not None:
            txt = f"Bitcoin: ${self.btc:,.0f}"
            if self.btc_var_pct is not None:
                txt += f" ({self.btc_var_pct:+.2f}%)"
            partes.append(txt)

        # China
        if self.hang_seng is not None:
            txt = f"Hang Seng: {self.hang_seng:,.0f}"
            if self.hang_seng_var_pct is not None:
                txt += f" ({self.hang_seng_var_pct:+.2f}%)"
            partes.append(txt)

        # EWZ
        if self.ewz is not None:
            txt = f"EWZ (Brasil visto de fora): ${self.ewz:.2f}"
            if self.ewz_var_pct is not None:
                txt += f" ({self.ewz_var_pct:+.2f}%)"
            partes.append(txt)

        # Futuros
        futuros = []
        if self.sp500_futures is not None:
            txt = f"ES=F {self.sp500_futures:,.0f}"
            if self.sp500_futures_var_pct is not None:
                txt += f" ({self.sp500_futures_var_pct:+.2f}%)"
            futuros.append(txt)
        if self.nasdaq_futures is not None:
            txt = f"NQ=F {self.nasdaq_futures:,.0f}"
            if self.nasdaq_futures_var_pct is not None:
                txt += f" ({self.nasdaq_futures_var_pct:+.2f}%)"
            futuros.append(txt)
        if futuros:
            partes.append(f"Futuros: {' | '.join(futuros)}")

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
        if self.ifix is not None:
            txt = f"IFIX: {self.ifix:,.0f}"
            if self.ifix_var_pct is not None:
                txt += f" ({self.ifix_var_pct:+.2f}%)"
            partes.append(txt)

        # Curva DI
        di_partes = []
        if self.di_1ano is not None:
            di_partes.append(f"1A: {self.di_1ano:.2f}%")
        if self.di_2anos is not None:
            di_partes.append(f"2A: {self.di_2anos:.2f}%")
        if self.di_3anos is not None:
            di_partes.append(f"3A: {self.di_3anos:.2f}%")
        if self.di_5anos is not None:
            di_partes.append(f"5A: {self.di_5anos:.2f}%")
        if di_partes:
            partes.append(f"Curva DI Pré: {' | '.join(di_partes)}")
            if self.inclinacao_di is not None:
                direcao = "mercado espera alta" if self.inclinacao_di > 0 else "mercado espera queda"
                partes.append(f"Inclinação DI (5A-1A): {self.inclinacao_di:+.2f}pp ({direcao})")

        # Regime & Confiança
        partes.append("\n=== REGIME MACRO ===")
        partes.append(f"Regime: {self.regime_macro} (score {self.regime_score}/100, confiança {self.confianca}/100)")
        partes.append(f"Fase Selic: {self.fase_selic}")
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
        treasury, treasury_2y, treasury_5y, treasury_30y,
        vix, dxy, wti, brent,
        (sp500, sp500_var), (dow, dow_var), ouro,
        (es_fut, es_fut_var), (nq_fut, nq_fut_var),
        # Commodities
        cobre, soja, milho,
        # Moedas cross
        usdjpy, eurusd, usdcny,
        # Credit & Sentiment
        hyg, lqd, (btc, btc_var),
        # China & EWZ
        (hang_seng, hang_seng_var), (ewz, ewz_var),
        # MMs (sequencial em 1 thread)
        mms,
    ) = await asyncio.gather(
        _get_yf_price("^TNX"),                  # Treasury 10Y
        _get_yf_price("^IRX"),                  # Treasury 3M (proxy 2Y)
        _get_yf_price("^FVX"),                  # Treasury 5Y
        _get_yf_price("^TYX"),                  # Treasury 30Y
        _get_yf_price("^VIX"),
        _get_yf_price("DX-Y.NYB"),
        _get_yf_price("CL=F"),                  # WTI
        _get_yf_price("BZ=F"),                  # Brent
        _get_yf_price_and_change("^GSPC"),       # S&P 500
        _get_yf_price_and_change("^DJI"),        # Dow Jones
        _get_yf_price("GC=F"),                  # Ouro
        _get_yf_price_and_change("ES=F"),        # S&P Futures
        _get_yf_price_and_change("NQ=F"),        # Nasdaq Futures
        # Commodities
        _get_yf_price("HG=F"),                  # Cobre
        _get_yf_price("ZS=F"),                  # Soja
        _get_yf_price("ZC=F"),                  # Milho
        # Moedas cross
        _get_yf_price("JPY=X"),                 # USD/JPY
        _get_yf_price("EURUSD=X"),              # EUR/USD
        _get_yf_price("CNY=X"),                 # USD/CNY
        # Credit spreads & Sentiment
        _get_yf_price("HYG"),                   # High Yield ETF
        _get_yf_price("LQD"),                   # Investment Grade ETF
        _get_yf_price_and_change("BTC-USD"),     # Bitcoin
        # China & Brasil exterior
        _get_yf_price_and_change("^HSI"),        # Hang Seng
        _get_yf_price_and_change("EWZ"),         # iShares Brazil
        _run_sync(_calcular_mms_batch),
    )

    dxy_mm50 = mms.get("dxy_mm50")
    sp500_mm50 = mms.get("sp500_mm50")
    sp500_mm200 = mms.get("sp500_mm200")

    # Yield spreads
    yield_spread = None
    yield_spread_2y30y = None
    if treasury is not None and treasury_2y is not None:
        yield_spread = round(treasury - treasury_2y, 3)
    if treasury_30y is not None and treasury_2y is not None:
        yield_spread_2y30y = round(treasury_30y - treasury_2y, 3)

    # Credit spread (proxy: diferença de preço HYG vs LQD normalizada)
    credit_spread = None
    if hyg is not None and lqd is not None and lqd > 0:
        credit_spread = round((lqd - hyg) / lqd * 100, 2)

    result = {
        "treasury_10y": treasury,
        "treasury_2y": treasury_2y,
        "treasury_5y": treasury_5y,
        "treasury_30y": treasury_30y,
        "yield_spread": yield_spread,
        "yield_spread_2y30y": yield_spread_2y30y,
        "vix": vix,
        "dxy": dxy,
        "dxy_mm50": dxy_mm50,
        "petroleo_wti": wti,
        "petroleo_brent": brent,
        "sp500": sp500,
        "sp500_var_pct": sp500_var,
        "sp500_mm50": sp500_mm50,
        "sp500_mm200": sp500_mm200,
        "dow_jones": dow,
        "dow_jones_var_pct": dow_var,
        "ouro": ouro,
        "sp500_futures": es_fut,
        "sp500_futures_var_pct": es_fut_var,
        "nasdaq_futures": nq_fut,
        "nasdaq_futures_var_pct": nq_fut_var,
        "cobre": cobre,
        "soja": soja,
        "milho": milho,
        "usdjpy": usdjpy,
        "eurusd": eurusd,
        "usdcny": usdcny,
        "hyg": hyg,
        "lqd": lqd,
        "credit_spread": credit_spread,
        "btc": btc,
        "btc_var_pct": btc_var,
        "hang_seng": hang_seng,
        "hang_seng_var_pct": hang_seng_var,
        "ewz": ewz,
        "ewz_var_pct": ewz_var,
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
    from app.data.di_curve_client import get_curva_di

    selic, ipca, dolar_yf, ibov_yf, (ifix, ifix_var), curva_di = await asyncio.gather(
        get_selic(),
        get_ipca(),
        get_dolar_yf(),
        get_ibov_yf(),
        _get_yf_price_and_change("IFIX11.SA"),   # IFIX (índice de FIIs)
        get_curva_di(),                            # Curva DI pré (BCB/SGS)
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
        "ifix": ifix,
        "ifix_var_pct": ifix_var,
        # Curva DI
        "di_1ano": curva_di.get("di_1ano"),
        "di_2anos": curva_di.get("di_2anos"),
        "di_3anos": curva_di.get("di_3anos"),
        "di_5anos": curva_di.get("di_5anos"),
        "inclinacao_di": curva_di.get("inclinacao_di"),
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

    # --- Cobre (Dr. Copper = saúde da economia global) ---
    if ctx.cobre is not None:
        if ctx.cobre > 4.5:
            pontos += 5; sinais.append(1)   # expansão global
        elif ctx.cobre < 3.5:
            pontos -= 5; sinais.append(-1)  # contração global
        else:
            sinais.append(0)

    # --- Credit spread (HYG vs LQD — spread abrindo = risco) ---
    if ctx.credit_spread is not None:
        if ctx.credit_spread < 15:
            pontos += 5; sinais.append(1)   # spread comprimido = complacência
        elif ctx.credit_spread > 20:
            pontos -= 10; sinais.append(-1)  # spread abrindo = stress crédito
        else:
            sinais.append(0)

    # --- EWZ (gringo saindo do Brasil?) ---
    if ctx.ewz_var_pct is not None:
        if ctx.ewz_var_pct > 1:
            pontos += 5; sinais.append(1)   # fluxo estrangeiro positivo
        elif ctx.ewz_var_pct < -1.5:
            pontos -= 5; sinais.append(-1)  # estrangeiro saindo

    # --- USD/JPY (carry trade unwind — yen forte = risco global) ---
    if ctx.usdjpy is not None:
        if ctx.usdjpy < 140:
            pontos -= 5; sinais.append(-1)   # carry trade desmontando
        elif ctx.usdjpy > 155:
            pontos += 5; sinais.append(1)    # carry trade estável

    # --- Curva DI Brasil (mercado precificando juros futuros) ---
    if ctx.inclinacao_di is not None:
        if ctx.inclinacao_di < -1.0:
            pontos += 5; sinais.append(1)   # mercado espera queda de juros = bom p/ bolsa
        elif ctx.inclinacao_di > 1.0:
            pontos -= 5; sinais.append(-1)  # mercado espera mais alta = ruim p/ bolsa

    # --- BTC (sentimento risk-on global) ---
    if ctx.btc_var_pct is not None:
        if ctx.btc_var_pct > 3:
            pontos += 3; sinais.append(1)
        elif ctx.btc_var_pct < -5:
            pontos -= 3; sinais.append(-1)

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

    # Curva de juros EUA invertida
    if ctx.yield_spread is not None and ctx.yield_spread < 0:
        flags.append(f"Curva de juros EUA INVERTIDA ({ctx.yield_spread:+.2f}pp) — sinal histórico de recessão")

    # Credit spread estressado
    if ctx.credit_spread is not None and ctx.credit_spread > 20:
        flags.append(f"Credit spread elevado ({ctx.credit_spread:.1f}%) — stress no mercado de crédito")

    # Cobre colapsando
    if ctx.cobre is not None and ctx.cobre < 3.5:
        flags.append(f"Cobre abaixo de $3.50/lb — sinal de desaceleração global")

    # Yen forte (carry trade unwind)
    if ctx.usdjpy is not None and ctx.usdjpy < 140:
        flags.append(f"USD/JPY em {ctx.usdjpy:.0f} — carry trade desmontando, risco para ativos de risco")

    # Curva DI inclinando (mercado espera mais juros)
    if ctx.inclinacao_di is not None and ctx.inclinacao_di > 1.5:
        flags.append(f"Curva DI inclinando (+{ctx.inclinacao_di:.2f}pp) — mercado espera alta de juros, pressão sobre FIIs e consumo")

    # DI curto muito alto
    if ctx.di_1ano is not None and ctx.di_1ano > 14:
        flags.append(f"DI 1 ano em {ctx.di_1ano:.2f}% — juros futuros elevados, RF muito competitiva")

    # EWZ caindo forte (gringo saindo)
    if ctx.ewz_var_pct is not None and ctx.ewz_var_pct < -3:
        flags.append(f"EWZ caindo {ctx.ewz_var_pct:.1f}% — estrangeiro vendendo Brasil")

    # Hang Seng despencando (China em crise)
    if ctx.hang_seng_var_pct is not None and ctx.hang_seng_var_pct < -3:
        flags.append(f"Hang Seng caindo {ctx.hang_seng_var_pct:.1f}% — estresse na China, risco para commodities")

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
        treasury_5y=global_data.get("treasury_5y"),
        treasury_30y=global_data.get("treasury_30y"),
        yield_spread=global_data.get("yield_spread"),
        yield_spread_2y10y=global_data.get("yield_spread"),
        yield_spread_2y30y=global_data.get("yield_spread_2y30y"),
        vix=global_data.get("vix"),
        dxy=global_data.get("dxy"),
        dxy_mm50=global_data.get("dxy_mm50"),
        petroleo_wti=global_data.get("petroleo_wti"),
        petroleo_brent=global_data.get("petroleo_brent"),
        sp500=global_data.get("sp500"),
        sp500_var_pct=global_data.get("sp500_var_pct"),
        sp500_mm50=global_data.get("sp500_mm50"),
        sp500_mm200=global_data.get("sp500_mm200"),
        dow_jones=global_data.get("dow_jones"),
        dow_jones_var_pct=global_data.get("dow_jones_var_pct"),
        ouro=global_data.get("ouro"),
        sp500_futures=global_data.get("sp500_futures"),
        sp500_futures_var_pct=global_data.get("sp500_futures_var_pct"),
        nasdaq_futures=global_data.get("nasdaq_futures"),
        nasdaq_futures_var_pct=global_data.get("nasdaq_futures_var_pct"),
        cobre=global_data.get("cobre"),
        soja=global_data.get("soja"),
        milho=global_data.get("milho"),
        usdjpy=global_data.get("usdjpy"),
        eurusd=global_data.get("eurusd"),
        usdcny=global_data.get("usdcny"),
        hyg=global_data.get("hyg"),
        lqd=global_data.get("lqd"),
        credit_spread=global_data.get("credit_spread"),
        btc=global_data.get("btc"),
        btc_var_pct=global_data.get("btc_var_pct"),
        hang_seng=global_data.get("hang_seng"),
        hang_seng_var_pct=global_data.get("hang_seng_var_pct"),
        ewz=global_data.get("ewz"),
        ewz_var_pct=global_data.get("ewz_var_pct"),
        selic=brasil_data.get("selic"),
        ipca_12m=brasil_data.get("ipca_12m"),
        ipca_expectativa=brasil_data.get("ipca_expectativa"),
        selic_expectativa=brasil_data.get("selic_expectativa"),
        juro_real=brasil_data.get("juro_real"),
        dolar_brl=brasil_data.get("dolar_brl"),
        dolar_var_pct=brasil_data.get("dolar_var_pct"),
        ibov=brasil_data.get("ibov"),
        ibov_var_pct=brasil_data.get("ibov_var_pct"),
        ifix=brasil_data.get("ifix"),
        ifix_var_pct=brasil_data.get("ifix_var_pct"),
        di_1ano=brasil_data.get("di_1ano"),
        di_2anos=brasil_data.get("di_2anos"),
        di_3anos=brasil_data.get("di_3anos"),
        di_5anos=brasil_data.get("di_5anos"),
        inclinacao_di=brasil_data.get("inclinacao_di"),
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

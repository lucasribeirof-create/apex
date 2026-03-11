"""
APEX Motor — Momentum (Trend Following)

Motor de seleção de ações em tendência de alta para a estratégia Momentum.

Filosofia:
  Momentum NÃO é "comprar o que subiu" — é comprar o que está em TENDÊNCIA
  CONFIRMADA e ainda tem espaço. O motor rejeita ativos em máxima histórica
  esticada (RSI > 75 + >25% acima MM200) e prioriza:
    - Tendência estrutural confirmada (MM50 > MM200 — Golden Cross)
    - Momento técnico forte mas não exausto (RSI 50-70)
    - Breakout de range OU continuação de tendência com volume acima da média
    - Força relativa positiva vs IBOV

Para cada ativo selecionado, o motor define:
  - Entrada: próximo da cotação atual (ou pullback ao nível de MM7/suporte)
  - Alvo: baseado em resistência técnica e múltiplo de ATR (+15% a +30%)
  - Stop: abaixo da MM20 ou suporte pivot, mínimo -5% máximo -10%
  - Risco/Retorno mínimo: 2:1

Dados extras por sugestão:
  - alvo: preço alvo
  - stop: preço de stop loss
  - rr: risco/retorno da operação
  - rsi: RSI(14)
  - macd_sinal: positivo/negativo/cruzamento
  - dist_mm200: % acima da MM200
  - força_relativa_ibov: % vs índice
  - momentum_score: score composto do motor
"""

import asyncio
import logging
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from app.cerebro.especialistas import SugestaoMotor
from app.cerebro.especialistas.watchlist import MOMENTUM_WATCHLIST
from app.cerebro.especialistas import prefetch as _pf
from app.cerebro.especialistas.candles import detectar_padroes, resumo_padroes
from app.cerebro.especialistas.fibonacci import calcular_fibonacci

logger = logging.getLogger("apex.motor_momentum")

# ── Parâmetros do motor ──────────────────────────────────────────────────────
MIN_RR           = 2.0    # risco/retorno mínimo para incluir
RSI_MIN          = 45.0   # RSI mínimo (abaixo = sem força compradora)
RSI_MAX          = 78.0   # RSI máximo (acima = sobrecomprado demais)
DIST_MM200_MAX   = 35.0   # % máximo acima da MM200 (acima = esticado demais)
STOP_ATR_MULT    = 1.5    # stop = preço - 1.5× ATR
ALVO_ATR_MULT    = 3.0    # alvo inicial = preço + 3.0× ATR
CAPITAL_MIN      = 1_000  # mínimo por posição

_IBOV_HIST: Optional[pd.Series] = None  # cache IBOV para força relativa
_ibov_cache: dict = {"valor": None, "ts": 0.0}  # cache de retorno IBOV 20d
_IBOV_CACHE_TTL = 300.0  # 5 minutos

# Cache semanal por ticker (TTL 5min, mesma janela do prefetch)
_weekly_cache: dict[str, dict] = {}
_weekly_cache_ts: float = 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  ANÁLISE SEMANAL (Multi-Timeframe)
# ══════════════════════════════════════════════════════════════════════════════

def _verificar_tendencia_semanal(ticker: str) -> dict:
    """
    Verifica a tendência semanal do ticker.
    Regra: NUNCA comprar no diário se o semanal está em tendência de baixa.

    Returns:
        dict com:
          - semanal_ok: True se tendência semanal é compatível com compra
          - mm40w: float — MM40 semanal (≈ MM200 diária)
          - mm10w: float — MM10 semanal (≈ MM50 diária)
          - acima_mm40w: bool
          - tendencia_semanal: "alta" | "baixa" | "neutra"
    """
    import time
    now = time.monotonic()
    cache_key = ticker.upper()

    # Cache check
    if cache_key in _weekly_cache and (now - _weekly_cache_ts) < _IBOV_CACHE_TTL:
        return _weekly_cache[cache_key]

    resultado = {
        "semanal_ok": True,
        "mm40w": 0.0,
        "mm10w": 0.0,
        "acima_mm40w": True,
        "tendencia_semanal": "neutra",
    }

    try:
        yf_ticker = ticker.upper()
        if not yf_ticker.endswith(".SA"):
            yf_ticker += ".SA"

        t = yf.Ticker(yf_ticker)
        weekly = t.history(period="2y", interval="1wk", auto_adjust=True)
        if weekly is None or len(weekly) < 40:
            return resultado  # dados insuficientes → não bloqueia

        close_w = weekly["Close"]
        preco_w = float(close_w.iloc[-1])

        mm40w = float(close_w.rolling(40, min_periods=20).mean().iloc[-1])
        mm10w = float(close_w.rolling(10, min_periods=5).mean().iloc[-1])

        acima_mm40w = preco_w > mm40w
        acima_mm10w = preco_w > mm10w

        if acima_mm40w and acima_mm10w:
            tendencia = "alta"
            semanal_ok = True
        elif acima_mm40w:
            tendencia = "neutra"
            semanal_ok = True  # pullback dentro da tendência → ok
        else:
            tendencia = "baixa"
            semanal_ok = False  # abaixo da MM40 semanal → NÃO comprar

        resultado = {
            "semanal_ok": semanal_ok,
            "mm40w": round(mm40w, 2),
            "mm10w": round(mm10w, 2),
            "acima_mm40w": acima_mm40w,
            "tendencia_semanal": tendencia,
        }

    except Exception:
        pass  # falha silenciosa → não bloqueia a análise

    _weekly_cache[cache_key] = resultado
    return resultado


# ══════════════════════════════════════════════════════════════════════════════
#  CÁLCULOS TÉCNICOS
# ══════════════════════════════════════════════════════════════════════════════

def _calcular_ibov_retorno_20d() -> float:
    """Retorna o retorno do IBOV nos últimos 20 pregões. Cacheado por 5min."""
    import time
    now = time.monotonic()
    if _ibov_cache["valor"] is not None and (now - _ibov_cache["ts"]) < _IBOV_CACHE_TTL:
        return _ibov_cache["valor"]
    try:
        ibov = yf.Ticker("^BVSP").history(period="3mo")["Close"]
        if ibov is not None and len(ibov) >= 21:
            ret = float((ibov.iloc[-1] - ibov.iloc[-21]) / ibov.iloc[-21] * 100)
            _ibov_cache["valor"] = ret
            _ibov_cache["ts"] = now
            return ret
    except Exception:
        pass
    return 0.0


def _analisar_momentum(ticker: str, ibov_ret_20d: float) -> Optional[dict]:
    """
    Analisa todos os indicadores técnicos de momentum para um ticker.
    Retorna None se não houver dados suficientes ou o ativo não passar nos filtros.
    Fase 6: inclui filtro semanal, Fibonacci e padrões de candle.
    """
    # ── FILTRO SEMANAL (Multi-Timeframe — Fase 6) ─────────────────────────
    weekly = _verificar_tendencia_semanal(ticker)
    if not weekly["semanal_ok"]:
        return None  # tendência semanal de baixa → NÃO comprar

    hist = None
    # Tenta prefetch primeiro
    pf = _pf.get(ticker)
    if pf and pf.sucesso and pf.hist is not None and len(pf.hist) >= 50:
        hist = pf.hist
    else:
        try:
            t = yf.Ticker(ticker + ".SA")
            hist = t.history(period="1y", auto_adjust=True)
            if hist is None or len(hist) < 50:
                return None
        except Exception:
            return None

    if hist is None or len(hist) < 50:
        return None

    close  = hist["Close"]
    high   = hist["High"]
    low    = hist["Low"]
    volume = hist["Volume"]
    preco  = float(close.iloc[-1])

    # ── RSI(14) ──────────────────────────────────────────────────────────────
    delta = close.diff()
    ganho = delta.clip(lower=0).rolling(14).mean()
    perda = (-delta.clip(upper=0)).rolling(14).mean()
    rsi   = float(100 - 100 / (1 + ganho.iloc[-1] / max(perda.iloc[-1], 1e-9)))

    # ── MACD (12, 26, 9) ─────────────────────────────────────────────────────
    ema12    = close.ewm(span=12, adjust=False).mean()
    ema26    = close.ewm(span=26, adjust=False).mean()
    macd     = ema12 - ema26
    sinal    = macd.ewm(span=9, adjust=False).mean()
    hist_m   = macd - sinal
    macd_val = float(macd.iloc[-1])
    sinal_val = float(sinal.iloc[-1])
    hist_val  = float(hist_m.iloc[-1])
    hist_prev = float(hist_m.iloc[-2]) if len(hist_m) >= 2 else 0.0
    macd_cruzando_alta = hist_val > 0 and hist_prev <= 0
    macd_positivo      = hist_val > 0

    # ── Médias móveis ─────────────────────────────────────────────────────────
    mm7   = float(close.rolling(7).mean().iloc[-1])
    mm20  = float(close.rolling(20, min_periods=10).mean().iloc[-1])
    mm50  = float(close.rolling(50, min_periods=25).mean().iloc[-1])
    mm200 = float(close.rolling(200, min_periods=50).mean().iloc[-1])
    golden_cross = mm50 > mm200
    dist_mm200   = (preco - mm200) / mm200 * 100
    acima_mm20   = preco > mm20
    acima_mm50   = preco > mm50

    # ── Momentum ─────────────────────────────────────────────────────────────
    preco_20d   = float(close.iloc[-21]) if len(close) >= 21 else float(close.iloc[0])
    preco_5d    = float(close.iloc[-6])  if len(close) >= 6  else preco
    momentum_20 = (preco - preco_20d) / preco_20d * 100
    momentum_5  = (preco - preco_5d) / preco_5d * 100

    # ── Volume ───────────────────────────────────────────────────────────────
    vol_media_20d = float(volume.tail(20).mean())
    vol_hoje      = float(volume.iloc[-1])
    vol_acima_med = vol_hoje > vol_media_20d * 1.2

    # ── Range 52 semanas ─────────────────────────────────────────────────────
    ult252    = close.tail(252)
    min_52s   = float(ult252.min())
    max_52s   = float(ult252.max())
    range_pct = (preco - min_52s) / (max_52s - min_52s) * 100 if max_52s > min_52s else 50.0

    # ── ATR(14) ───────────────────────────────────────────────────────────────
    prev_cl = close.shift(1)
    tr = pd.concat([high - low, (high - prev_cl).abs(), (low - prev_cl).abs()], axis=1).max(axis=1)
    atr14 = float(tr.rolling(14).mean().iloc[-1])

    # ── Força relativa vs IBOV ────────────────────────────────────────────────
    forca_relativa = round(momentum_20 - ibov_ret_20d, 1)

    # ── Resistência (pivot highs) ─────────────────────────────────────────────
    resistencia = None
    highs_arr = high.values
    n, wing = len(highs_arr), 5
    pivots_high = []
    for i in range(wing, n - wing):
        v = highs_arr[i]
        if all(v >= highs_arr[i-j] for j in range(1, wing+1)) and all(v >= highs_arr[i+j] for j in range(1, wing+1)):
            pivots_high.append(float(v))
    acima = [v for v in pivots_high if v > preco * 1.005]
    if acima:
        resistencia = round(min(acima), 2)

    # ── Suporte (pivot lows) ──────────────────────────────────────────────────
    suporte = None
    lows_arr = low.values
    pivots_low = []
    for i in range(wing, n - wing):
        v = lows_arr[i]
        if all(v <= lows_arr[i-j] for j in range(1, wing+1)) and all(v <= lows_arr[i+j] for j in range(1, wing+1)):
            pivots_low.append(float(v))
    abaixo = [v for v in pivots_low if v < preco * 0.995]
    if abaixo:
        suporte = round(max(abaixo), 2)

    # ── Stop e Alvo ───────────────────────────────────────────────────────────
    stop_atr  = round(preco - STOP_ATR_MULT * atr14, 2)
    stop_mm20 = round(mm20 * 0.99, 2)  # 1% abaixo da MM20
    stop      = max(stop_atr, stop_mm20)  # stop mais próximo = mais seguro

    # Alvo: resistência se disponível e realista; caso contrário, ATR múltiplo
    alvo_atr    = round(preco + ALVO_ATR_MULT * atr14, 2)
    if resistencia and resistencia < alvo_atr:
        alvo = resistencia
    else:
        alvo = alvo_atr

    risco   = preco - stop
    retorno = alvo - preco
    rr      = round(retorno / risco, 2) if risco > 0 else 0.0

    # ── Fibonacci Retracements (Fase 6) ───────────────────────────────────
    fib = calcular_fibonacci(
        hist, preco, suporte=suporte, mm20=mm20, mm50=mm50,
        lookback=60, tolerancia=0.02,
    )
    fib_score = fib.score_fib if fib else 0

    # ── Padrões de Candle (Fase 6) ────────────────────────────────────────
    candle_padroes = detectar_padroes(
        hist, suporte=suporte, resistencia=resistencia, mm20=mm20, n_ultimas=5,
    )
    candle_resumo = resumo_padroes(candle_padroes)
    candle_score = max(min(candle_resumo["score_candles"], 15), -15)  # cap ±15

    # ── Filtros eliminatórios ─────────────────────────────────────────────────
    if not golden_cross:         return None   # sem tendência estrutural
    if rsi < RSI_MIN:            return None   # sem força compradora
    if rsi > RSI_MAX:            return None   # sobrecomprado demais
    if dist_mm200 > DIST_MM200_MAX: return None  # ação esticada demais
    if not acima_mm20:           return None   # abaixo da MM20 = fraqueza de curto prazo
    if not acima_mm50:           return None   # abaixo da MM50 = tendência intermediária enfraquecida
    if rr < MIN_RR:              return None   # risco/retorno ruim
    if momentum_20 < 0:          return None   # perdendo no mês — sem momentum

    # ── Score composto ────────────────────────────────────────────────────────
    score = 0.0

    # RSI na zona ideal (55-68 = força sem exaustão)
    if   55 <= rsi <= 68: score += 30
    elif 50 <= rsi <  55: score += 20
    elif 68 <  rsi <= 75: score += 10

    # MACD
    if macd_cruzando_alta: score += 25
    elif macd_positivo:    score += 15

    # Força relativa vs IBOV
    if   forca_relativa >= 10: score += 20
    elif forca_relativa >= 5:  score += 12
    elif forca_relativa >= 0:  score += 5

    # Momentum recente
    if   momentum_20 >= 10: score += 15
    elif momentum_20 >= 5:  score += 8
    else:                   score += 3

    # Volume confirmando
    if vol_acima_med: score += 10

    # R/R qualidade
    if   rr >= 3.5: score += 10
    elif rr >= 2.5: score += 6
    else:           score += 2

    # Fibonacci (Fase 6) — 0 a 15 pontos
    score += fib_score

    # Candle patterns (Fase 6) — -15 a +15 pontos
    score += candle_score

    # Tendência semanal bonus (Fase 6) — semanal em alta = +5
    if weekly.get("tendencia_semanal") == "alta":
        score += 5

    return {
        "ticker":          ticker,
        "preco":           round(preco, 2),
        "rsi":             round(rsi, 1),
        "macd_val":        round(macd_val, 4),
        "macd_positivo":   macd_positivo,
        "macd_cruzando":   macd_cruzando_alta,
        "golden_cross":    golden_cross,
        "dist_mm200":      round(dist_mm200, 1),
        "mm20":            round(mm20, 2),
        "mm50":            round(mm50, 2),
        "mm200":           round(mm200, 2),
        "momentum_20":     round(momentum_20, 1),
        "momentum_5":      round(momentum_5, 1),
        "atr14":           round(atr14, 2),
        "range_pct":       round(range_pct, 1),
        "forca_relativa":  forca_relativa,
        "vol_acima_med":   vol_acima_med,
        "stop":            stop,
        "alvo":            alvo,
        "rr":              rr,
        "resistencia":     resistencia,
        "suporte":         suporte,
        "score":           round(score, 1),
        # Phase 6 — Multi-Timeframe
        "tendencia_semanal": weekly.get("tendencia_semanal", "neutra"),
        "mm40w":             weekly.get("mm40w", 0.0),
        "mm10w":             weekly.get("mm10w", 0.0),
        # Phase 6 — Fibonacci
        "fib_zona":          fib.zona_atual if fib else None,
        "fib_confluencia":   fib.confluencia_desc if fib and fib.confluencia else None,
        "fib_score":         fib_score,
        "fib_niveis":        {"38.2": fib.nivel_382, "50": fib.nivel_500, "61.8": fib.nivel_618} if fib else None,
        # Phase 6 — Candle Patterns
        "candle_padroes_alta":  candle_resumo["padroes_alta"],
        "candle_padroes_baixa": candle_resumo["padroes_baixa"],
        "candle_score":         candle_score,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  JUSTIFICATIVA
# ══════════════════════════════════════════════════════════════════════════════

def _justificativa(d: dict) -> str:
    partes = []

    # Por que este ativo foi selecionado
    if d["macd_cruzando"]:
        partes.append(f"{d['ticker']} com cruzamento MACD confirmando nova perna de alta")
    elif d["macd_positivo"]:
        partes.append(f"{d['ticker']} em tendência de alta com MACD positivo")

    # Tendência estrutural
    partes.append(
        f"Golden Cross ativo (MM50 > MM200) — tendência estrutural de alta confirmada"
    )

    # Tendência semanal (Fase 6)
    tend_w = d.get("tendencia_semanal", "neutra")
    if tend_w == "alta":
        partes.append("tendência semanal em alta (acima MM40w e MM10w) — confluência multi-timeframe")
    elif tend_w == "neutra":
        partes.append("semanal neutro (pullback acima MM40w) — aceitável para entrada")

    # RSI
    rsi = d["rsi"]
    if 55 <= rsi <= 68:
        partes.append(f"RSI {rsi:.0f} — zona de força sem sobrecompra, comprador presente")
    elif rsi < 55:
        partes.append(f"RSI {rsi:.0f} — pullback dentro da tendência, assimetria favorável")
    else:
        partes.append(f"RSI {rsi:.0f} — atenção ao sobrecompra, position size reduzido")

    # Força relativa
    fr = d["forca_relativa"]
    if fr >= 5:
        partes.append(f"ação superando IBOV em {fr:+.1f}% nos últimos 20 pregões — liderança setorial")
    elif fr >= 0:
        partes.append(f"força relativa neutra vs IBOV ({fr:+.1f}%)")

    # Fibonacci (Fase 6)
    if d.get("fib_confluencia"):
        partes.append(d["fib_confluencia"])
    elif d.get("fib_zona"):
        partes.append(f"preço em zona Fibonacci {d['fib_zona']}% — retração saudável")

    # Candle patterns (Fase 6)
    candle_alta = d.get("candle_padroes_alta", [])
    if candle_alta:
        partes.append(f"padrão(ões) altista(s): {', '.join(candle_alta[:2])}")

    # Posição vs MM200
    partes.append(
        f"cotação {d['dist_mm200']:+.1f}% acima da MM200 — "
        f"{'confortável, ainda com espaço' if d['dist_mm200'] < 20 else 'esticando, position size menor'}"
    )

    # Operacional
    partes.append(
        f"entrada: R${d['preco']:.2f} | alvo: R${d['alvo']:.2f} ({(d['alvo']/d['preco']-1)*100:.1f}%) | "
        f"stop: R${d['stop']:.2f} ({(d['stop']/d['preco']-1)*100:.1f}%) | "
        f"R/R: {d['rr']}:1"
    )

    return ". ".join(partes) + "."


# ══════════════════════════════════════════════════════════════════════════════
#  INTERFACE PÚBLICA DO MOTOR
# ══════════════════════════════════════════════════════════════════════════════

async def rodar(
    capital: float,
    watchlist: Optional[list[str]] = None,
    n_ativos: int = 4,
    excluir_tickers: list[str] | None = None,
    ranking_setorial: object | None = None,
    patrimonio_total: float = 0.0,
    regime: str = "NEUTRO",
    cb_modifier: float = 1.0,
    macro_context: object | None = None,
) -> list[SugestaoMotor]:
    """
    Motor Momentum com camada de convicção IA.
    Análise técnica completa (RSI, MACD, MMs, Fibonacci, candles) → IA reordena
    por convicção considerando contexto macro. Fallback: ranking algorítmico.
    """
    if capital < CAPITAL_MIN:
        return []

    _excluir = set(t.upper() for t in (excluir_tickers or []))
    tickers = [t for t in (watchlist or MOMENTUM_WATCHLIST) if t.upper() not in _excluir]
    n_ativos = min(n_ativos, 8)

    # Retorno do IBOV para força relativa
    ibov_ret = await asyncio.to_thread(_calcular_ibov_retorno_20d)

    # Analisa cada ticker em paralelo
    tarefas  = [asyncio.to_thread(_analisar_momentum, t, ibov_ret) for t in tickers]
    resultados = await asyncio.gather(*tarefas, return_exceptions=True)

    candidatos = [r for r in resultados if isinstance(r, dict) and r is not None]

    # Ajuste setorial
    if ranking_setorial:
        for c in candidatos:
            c["score"] = _aplicar_ajuste_setor(c["ticker"], c["score"], ranking_setorial)

    candidatos.sort(key=lambda x: x["score"], reverse=True)

    if not candidatos:
        return []

    # ── Fallback algorítmico (top-N por score técnico) ────────────────────
    fallback = _construir_fallback_momentum(candidatos, n_ativos, capital, patrimonio_total, regime, cb_modifier)

    # ── Enriquecer candidatos para IA ─────────────────────────────────────
    candidatos_enriched = []
    for c in candidatos:
        candidatos_enriched.append({
            "ticker": c["ticker"],
            "nome": c["ticker"],
            "tipo": "ACAO",
            "preco": c["preco"],
            "rsi": c["rsi"],
            "macd_positivo": c["macd_positivo"],
            "macd_cruzando": c["macd_cruzando"],
            "golden_cross": c["golden_cross"],
            "dist_mm200_pct": c["dist_mm200"],
            "momentum_20d": c["momentum_20"],
            "forca_relativa_ibov": c["forca_relativa"],
            "alvo": c["alvo"],
            "stop": c["stop"],
            "rr": c["rr"],
            "atr14": c["atr14"],
            "tendencia_semanal": c.get("tendencia_semanal", "neutra"),
            "fib_zona": c.get("fib_zona"),
            "fib_confluencia": c.get("fib_confluencia"),
            "candle_padroes_alta": c.get("candle_padroes_alta", []),
            "candle_padroes_baixa": c.get("candle_padroes_baixa", []),
            "score_tecnico": round(c["score"], 1),
            "setor": _get_setor_ticker(c["ticker"]),
            "dados_extras": {
                "alvo": c["alvo"], "stop": c["stop"], "rr": c["rr"],
                "rsi": c["rsi"], "atr14": c["atr14"],
                "setor": _get_setor_ticker(c["ticker"]),
            },
        })

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
        modulo="momentum",
        candidatos_enriched=candidatos_enriched,
        macro_resumo=macro_resumo,
        estrategia="ALPHA",
        capital=capital,
        motor_system_prompt=build_motor_prompt("momentum"),
        n_ativos=n_ativos,
        max_tokens=3000,
        fallback_candidatos=fallback,
    )

    return resultado if resultado else fallback


def _construir_fallback_momentum(
    candidatos: list[dict], n_ativos: int, capital: float,
    patrimonio_total: float, regime: str, cb_modifier: float,
) -> list[SugestaoMotor]:
    """Fallback algorítmico: top-N por score técnico com ATR sizing."""
    selecionados = candidatos[:n_ativos]
    if not selecionados:
        return []

    from app.cerebro.sizing import sizing_lote, ATR_STOP_MULT_MOMENTUM
    _patrim = patrimonio_total if patrimonio_total > 0 else capital
    sizing_results = sizing_lote(
        selecionados, capital, _patrim,
        regime=regime, atr_mult=ATR_STOP_MULT_MOMENTUM, cb_modifier=cb_modifier,
    )
    sizing_map = {s.ticker: s for s in sizing_results}

    saida: list[SugestaoMotor] = []

    for d in selecionados:
        preco = d["preco"]
        sz = sizing_map.get(d["ticker"])
        if sz and sz.qtd > 0:
            qtd = sz.qtd
            valor = sz.valor
        else:
            qtd = max(1, int(capital / len(selecionados) / preco))
            valor = round(qtd * preco, 2)

        saida.append(SugestaoMotor(
            modulo="momentum",
            ticker=d["ticker"],
            nome=d["ticker"],
            tipo="ACAO",
            quantidade=float(qtd),
            preco_atual=preco,
            valor_total=valor,
            justificativa=_justificativa(d),
            score=d["score"],
            dados_extras={
                "alvo": d["alvo"], "stop": d["stop"], "rr": d["rr"],
                "rsi": d["rsi"], "macd_positivo": d["macd_positivo"],
                "macd_cruzando": d["macd_cruzando"], "golden_cross": d["golden_cross"],
                "dist_mm200": d["dist_mm200"], "momentum_20d": d["momentum_20"],
                "forca_relativa_ibov": d["forca_relativa"], "atr14": d["atr14"],
                "range_52s_pct": d["range_pct"],
                "suporte": d["suporte"], "resistencia": d["resistencia"],
                "upside_pct": round((d["alvo"] / preco - 1) * 100, 1),
                "downside_pct": round((d["stop"] / preco - 1) * 100, 1),
                "setor": _get_setor_ticker(d["ticker"]),
                "risco_pct_patrimonio": sz.risco_pct_patrimonio if sz else None,
                "sizing_method": "ATR" if (sz and sz.atr14 > 0) else "equal_weight",
                "tendencia_semanal": d.get("tendencia_semanal", "neutra"),
                "mm40w": d.get("mm40w", 0.0),
                "fib_zona": d.get("fib_zona"),
                "fib_confluencia": d.get("fib_confluencia"),
                "fib_score": d.get("fib_score", 0),
                "fib_niveis": d.get("fib_niveis"),
                "candle_padroes_alta": d.get("candle_padroes_alta", []),
                "candle_padroes_baixa": d.get("candle_padroes_baixa", []),
                "candle_score": d.get("candle_score", 0),
            },
        ))

    return saida


def _aplicar_ajuste_setor(ticker: str, score: float, ranking_setorial) -> float:
    """Aplica bonus/penalty ao score baseado no ranking setorial."""
    from app.core.universe import get_ticker_info
    info = get_ticker_info(ticker)
    setor = info.get("setor", "outro") if info else "outro"
    if setor in getattr(ranking_setorial, "favorecidos", []):
        score += 12
    elif setor in getattr(ranking_setorial, "evitar", []):
        score -= 15
    return max(score, 0.0)


def _get_setor_ticker(ticker: str) -> str:
    """Retorna o setor canônico de um ticker."""
    from app.core.universe import get_ticker_info
    info = get_ticker_info(ticker)
    return info.get("setor", "outro") if info else "outro"

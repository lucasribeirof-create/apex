"""
Position Sizing por Risco — APEX Cérebro (Fase 4).

Substitui o naive `capital / n_ativos` por sizing baseado em risco:
  posição = (capital × risco_por_operação) / (preço - stop)

Onde:
  - risco_por_operação = 1-2% do capital (configurável por regime)
  - stop = preço - N × ATR(14) (calculado aqui ou recebido do motor)
  - ATR mais alto → posição menor (ativo volátil), ATR baixo → posição maior

Inclui também:
  - Circuit breaker: perda mensal ≥ 5% → sizing÷2, ≥8% → pausa 10 pregões, ≥10% → pausa mês
  - Heat máximo: soma de risco% de todas posições ativas ≤ 6% do patrimônio
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import yfinance as yf

from app.cerebro.especialistas import prefetch as _pf


# ── Parâmetros configuráveis ─────────────────────────────────────────────────

# Risco por operação: % do capital que se aceita perder por posição
_RISCO_POR_REGIME: dict[str, float] = {
    "RISK_ON_FORTE":    0.020,   # 2.0%
    "RISK_ON_MODERADO": 0.015,   # 1.5%
    "NEUTRO":           0.012,   # 1.2%
    "RISK_OFF":         0.008,   # 0.8%
}
_RISCO_PADRAO = 0.012  # 1.2% default

# Multiplicador ATR para stop implícito (quando motor não fornece stop)
ATR_STOP_MULT_ALPHA = 2.0       # Alpha: mais largo (fundamentalista, tolera oscilação)
ATR_STOP_MULT_MOMENTUM = 1.5    # Momentum: mais apertado (técnico, sai rápido)
ATR_STOP_MULT_DIVIDENDOS = 2.5  # Dividendos: o mais largo (buy & hold income)

# Heat máximo: % total do patrimônio em risco simultâneo
HEAT_MAX_PCT = 6.0

# Circuit breaker: thresholds de perda mensal (em %)
CB_NIVEL_1 = -5.0    # sizing ÷ 2
CB_NIVEL_2 = -8.0    # pausa 10 pregões
CB_NIVEL_3 = -10.0   # pausa até próximo mês

# Posição mínima e máxima como % do capital do motor
_POS_MIN_PCT = 0.05   # 5% mínimo em cada posição
_POS_MAX_PCT = 0.35   # 35% máximo em cada posição


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class SizingResult:
    """Resultado do cálculo de position sizing para um ativo."""
    ticker: str
    preco: float
    stop: float
    atr14: float
    risco_por_op_pct: float   # % do capital arriscado nesta operação
    qtd: int                  # quantidade de cotas/ações
    valor: float              # qtd × preço
    pct_capital: float        # % do capital alocado nesta posição
    risco_reais: float        # quanto se perde se bater stop (R$)
    risco_pct_patrimonio: float  # risco desta posição como % do patrimônio total


@dataclass
class CircuitBreakerState:
    """Estado do circuit breaker baseado em P&L mensal."""
    pl_mes_pct: float = 0.0         # P&L do mês em %
    nivel: int = 0                  # 0=normal, 1=sizing÷2, 2=pausa 10d, 3=pausa mês
    sizing_modifier: float = 1.0    # multiplicador aplicado ao sizing (1.0, 0.5, ou 0.0)
    motivo: str = ""
    ativo: bool = False


@dataclass
class HeatState:
    """Estado de heat (risco total em aberto)."""
    heat_pct: float = 0.0           # % do patrimônio em risco
    heat_reais: float = 0.0         # R$ em risco total
    pode_operar: bool = True        # False se heat > HEAT_MAX_PCT
    detalhes: list[dict] = field(default_factory=list)  # {ticker, risco_pct, risco_reais}


# ── ATR ──────────────────────────────────────────────────────────────────────

def calcular_atr14(ticker: str) -> float | None:
    """Calcula ATR(14) para um ticker brasileiro. Retorna None se falhar."""
    # Tenta prefetch primeiro
    pf = _pf.get(ticker)
    hist = None
    if pf and pf.sucesso and pf.hist is not None and len(pf.hist) >= 20:
        hist = pf.hist

    if hist is None:
        try:
            t = yf.Ticker(ticker + ".SA")
            hist = t.history(period="3mo", auto_adjust=True)
            if hist is None or len(hist) < 20:
                return None
        except Exception:
            return None

    try:
        high = hist["High"]
        low = hist["Low"]
        close = hist["Close"]
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()

        import pandas as pd
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        return round(atr, 2) if atr > 0 else None
    except Exception:
        return None


# ── Circuit Breaker ──────────────────────────────────────────────────────────

def avaliar_circuit_breaker(pl_mes_pct: float) -> CircuitBreakerState:
    """Avalia o estado do circuit breaker baseado em P&L mensal."""
    if pl_mes_pct <= CB_NIVEL_3:
        return CircuitBreakerState(
            pl_mes_pct=pl_mes_pct,
            nivel=3,
            sizing_modifier=0.0,
            motivo=f"PAUSA TOTAL: perda de {pl_mes_pct:.1f}% no mês (≤{CB_NIVEL_3}%)",
            ativo=True,
        )
    elif pl_mes_pct <= CB_NIVEL_2:
        return CircuitBreakerState(
            pl_mes_pct=pl_mes_pct,
            nivel=2,
            sizing_modifier=0.0,
            motivo=f"PAUSA 10 PREGÕES: perda de {pl_mes_pct:.1f}% no mês (≤{CB_NIVEL_2}%)",
            ativo=True,
        )
    elif pl_mes_pct <= CB_NIVEL_1:
        return CircuitBreakerState(
            pl_mes_pct=pl_mes_pct,
            nivel=1,
            sizing_modifier=0.5,
            motivo=f"SIZING ÷2: perda de {pl_mes_pct:.1f}% no mês (≤{CB_NIVEL_1}%)",
            ativo=True,
        )
    return CircuitBreakerState(pl_mes_pct=pl_mes_pct)


# ── Heat ─────────────────────────────────────────────────────────────────────

def calcular_heat(posicoes: list[dict], patrimonio: float) -> HeatState:
    """Calcula o heat total (risco em aberto) do portfólio.

    Cada posição contribui com: valor_posição × dist_ao_stop%.
    Se stop não está definido, usa estimativa de 5% para ações / 3% para FIIs.
    """
    if patrimonio <= 0:
        return HeatState()

    detalhes = []
    total_risco = 0.0

    for pos in posicoes:
        tipo = pos.get("tipo", "ACAO")
        if tipo in ("RF", "CAIXA"):
            continue

        valor_pos = pos.get("valor_atual") or pos.get("valor_total") or 0
        if valor_pos <= 0:
            continue

        preco_atual = pos.get("preco_atual") or 0
        stop = pos.get("stop") or pos.get("dados_extras", {}).get("stop")

        if stop and preco_atual and preco_atual > 0:
            dist_stop_pct = abs(preco_atual - stop) / preco_atual
        else:
            # Estimativa default por tipo
            dist_stop_pct = 0.03 if tipo == "FII" else 0.05

        risco = valor_pos * dist_stop_pct
        risco_pct = risco / patrimonio * 100

        detalhes.append({
            "ticker": pos.get("ticker", "?"),
            "risco_pct": round(risco_pct, 2),
            "risco_reais": round(risco, 2),
        })
        total_risco += risco

    heat_pct = total_risco / patrimonio * 100
    return HeatState(
        heat_pct=round(heat_pct, 2),
        heat_reais=round(total_risco, 2),
        pode_operar=heat_pct < HEAT_MAX_PCT,
        detalhes=detalhes,
    )


# ── Position Sizing Principal ────────────────────────────────────────────────

def calcular_sizing(
    ticker: str,
    preco: float,
    capital_motor: float,
    patrimonio_total: float,
    regime: str = "NEUTRO",
    stop: float | None = None,
    atr14: float | None = None,
    atr_mult: float = ATR_STOP_MULT_ALPHA,
    cb_modifier: float = 1.0,
    n_ativos: int = 1,
) -> SizingResult:
    """Calcula position sizing baseado em risco.

    Lógica:
      1. Se motor fornece stop → usa distância ao stop
      2. Senão → calcula stop implícito via ATR × mult
      3. Aplica: qtd = (capital × risco%) / (preço - stop)
      4. Clamp entre POS_MIN e POS_MAX do capital do motor
      5. Aplica circuit breaker modifier

    Args:
        ticker:           Código do ativo
        preco:            Preço atual
        capital_motor:    Capital disponível neste motor
        patrimonio_total: Patrimônio total do usuário (para risco%)
        regime:           Regime macro (define % de risco por operação)
        stop:             Stop-loss já definido pelo motor (opcional)
        atr14:            ATR(14) pré-calculado (opcional, senão calcula)
        atr_mult:         Multiplicador de ATR para stop implícito
        cb_modifier:      Circuit breaker: 1.0=normal, 0.5=nível 1, 0.0=pausado
        n_ativos:         Número de ativos selecionados (para fallback equal-weight)
    """
    if preco <= 0 or capital_motor <= 0:
        return SizingResult(ticker=ticker, preco=preco, stop=0, atr14=0,
                            risco_por_op_pct=0, qtd=0, valor=0,
                            pct_capital=0, risco_reais=0, risco_pct_patrimonio=0)

    # Risco por operação baseado no regime
    risco_pct = _RISCO_POR_REGIME.get(regime, _RISCO_PADRAO)

    # Se não temos stop, calcular via ATR
    if stop is None or stop <= 0 or stop >= preco:
        if atr14 is None or atr14 <= 0:
            atr14 = calcular_atr14(ticker)
        if atr14 and atr14 > 0:
            stop = round(preco - atr_mult * atr14, 2)
        else:
            # Fallback: equal-weight se não conseguimos calcular ATR
            val = capital_motor / max(n_ativos, 1) * cb_modifier
            val = max(val, 0)
            qtd = max(1, int(val / preco)) if val >= preco else 0
            return SizingResult(
                ticker=ticker, preco=preco, stop=round(preco * 0.90, 2),
                atr14=0, risco_por_op_pct=risco_pct * 100, qtd=qtd,
                valor=round(qtd * preco, 2), pct_capital=round(qtd * preco / capital_motor * 100, 1) if capital_motor else 0,
                risco_reais=round(qtd * preco * 0.10, 2),
                risco_pct_patrimonio=round(qtd * preco * 0.10 / patrimonio_total * 100, 2) if patrimonio_total else 0,
            )
    else:
        if atr14 is None or atr14 <= 0:
            atr14 = calcular_atr14(ticker) or 0

    # Distância ao stop
    dist_stop = preco - stop
    if dist_stop <= 0:
        dist_stop = preco * 0.05  # fallback 5%
        stop = round(preco - dist_stop, 2)

    # Position sizing: quanto capital alocar para arriscar exatamente risco_pct
    # capital_base = patrimônio total (risco é sobre patrimônio, não sobre capital do motor)
    capital_base = patrimonio_total if patrimonio_total > 0 else capital_motor
    risco_reais_desejado = capital_base * risco_pct
    valor_posicao = risco_reais_desejado / dist_stop * preco

    # Aplicar circuit breaker modifier
    valor_posicao *= cb_modifier

    # Clamp entre POS_MIN e POS_MAX do capital do motor
    pos_min = capital_motor * _POS_MIN_PCT
    pos_max = capital_motor * _POS_MAX_PCT
    valor_posicao = max(pos_min, min(pos_max, valor_posicao))

    # Também não pode exceder o capital do motor
    valor_posicao = min(valor_posicao, capital_motor)

    qtd = max(1, int(valor_posicao / preco))
    valor_final = round(qtd * preco, 2)
    risco_real = round(qtd * dist_stop, 2)

    return SizingResult(
        ticker=ticker,
        preco=preco,
        stop=stop,
        atr14=atr14 or 0,
        risco_por_op_pct=round(risco_pct * 100, 2),
        qtd=qtd,
        valor=valor_final,
        pct_capital=round(valor_final / capital_motor * 100, 1) if capital_motor else 0,
        risco_reais=risco_real,
        risco_pct_patrimonio=round(risco_real / patrimonio_total * 100, 2) if patrimonio_total > 0 else 0,
    )


# ── Sizing em lote (para um motor com N selecionados) ────────────────────────

def sizing_lote(
    selecionados: list[dict],
    capital_motor: float,
    patrimonio_total: float,
    regime: str = "NEUTRO",
    atr_mult: float = ATR_STOP_MULT_ALPHA,
    cb_modifier: float = 1.0,
) -> list[SizingResult]:
    """Calcula sizing para uma lista de ativos selecionados por um motor.

    Cada dict em selecionados precisa ter: 'ticker', 'preco'.
    Opcionalmente: 'stop', 'atr14'.

    Distribui o capital respeitando o risco individual de cada ativo.
    Se a soma exceder o capital disponível, normaliza proporcionalmente.
    """
    if not selecionados or capital_motor <= 0:
        return []

    resultados = []
    n = len(selecionados)

    for d in selecionados:
        r = calcular_sizing(
            ticker=d["ticker"],
            preco=d["preco"],
            capital_motor=capital_motor,
            patrimonio_total=patrimonio_total,
            regime=regime,
            stop=d.get("stop"),
            atr14=d.get("atr14"),
            atr_mult=atr_mult,
            cb_modifier=cb_modifier,
            n_ativos=n,
        )
        resultados.append(r)

    # Verificar se soma total excede o capital do motor
    soma_valor = sum(r.valor for r in resultados)
    if soma_valor > capital_motor and soma_valor > 0:
        # Normalizar proporcionalmente
        fator = capital_motor / soma_valor
        novos = []
        for r in resultados:
            novo_valor = r.valor * fator
            novo_qtd = max(1, int(novo_valor / r.preco)) if r.preco > 0 else 0
            novo_valor_real = round(novo_qtd * r.preco, 2)
            dist_stop = r.preco - r.stop if r.stop < r.preco else r.preco * 0.05
            novo_risco = round(novo_qtd * dist_stop, 2)
            novos.append(SizingResult(
                ticker=r.ticker, preco=r.preco, stop=r.stop, atr14=r.atr14,
                risco_por_op_pct=r.risco_por_op_pct, qtd=novo_qtd, valor=novo_valor_real,
                pct_capital=round(novo_valor_real / capital_motor * 100, 1) if capital_motor else 0,
                risco_reais=novo_risco,
                risco_pct_patrimonio=round(novo_risco / patrimonio_total * 100, 2) if patrimonio_total > 0 else 0,
            ))
        return novos

    return resultados

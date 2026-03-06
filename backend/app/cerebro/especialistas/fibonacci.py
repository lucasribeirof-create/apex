"""
APEX — Análise de Fibonacci Retracements

Identifica swing high/low recente e calcula níveis de retração:
  - 38.2% — retração rasa (tendência forte)
  - 50.0% — retração intermediária
  - 61.8% — retração profunda (golden ratio)

Confluência:
  Nível Fibonacci perto de MA ou suporte = zona de compra forte.
  Usado pelo motor Momentum para bonus no score e melhor timing de entrada.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class FibAnalise:
    """Resultado da análise de Fibonacci."""
    swing_high: float           # topo do swing
    swing_low: float            # fundo do swing
    nivel_382: float            # retração 38.2%
    nivel_500: float            # retração 50%
    nivel_618: float            # retração 61.8%
    zona_atual: str | None      # "38.2" | "50" | "61.8" | None
    em_zona_fib: bool           # preço está em alguma zona Fibonacci
    confluencia: bool           # zona Fib coincide com MA ou suporte
    confluencia_desc: str       # descrição da confluência
    score_fib: int              # 0-15 pontos de bonus


def calcular_fibonacci(
    df: pd.DataFrame,
    preco_atual: float,
    suporte: float | None = None,
    mm20: float | None = None,
    mm50: float | None = None,
    lookback: int = 60,
    tolerancia: float = 0.02,
) -> FibAnalise | None:
    """
    Calcula níveis de Fibonacci retracement a partir do swing high/low recente.

    Args:
        df: DataFrame com High, Low, Close
        preco_atual: preço de fechamento mais recente
        suporte: nível de suporte para confluência
        mm20: MM20 para confluência
        mm50: MM50 para confluência
        lookback: barras para buscar swing high/low (default 60 = ~3 meses)
        tolerancia: % de tolerância para considerar "em zona" (default 2%)

    Returns:
        FibAnalise ou None se dados insuficientes
    """
    if df is None or len(df) < lookback // 2:
        return None

    high = df["High"].values
    low = df["Low"].values
    close = df["Close"].values

    # Limita ao lookback
    n = min(len(high), lookback)
    high_window = high[-n:]
    low_window = low[-n:]

    # Encontra swing high e swing low
    swing_high_idx = np.argmax(high_window)
    swing_low_idx = np.argmin(low_window)

    swing_high = float(high_window[swing_high_idx])
    swing_low = float(low_window[swing_low_idx])

    if swing_high <= swing_low or swing_high <= 0:
        return None

    amplitude = swing_high - swing_low

    # Fibonacci é retração DESDE O TOPO para uma tendência de alta
    # Níveis = high - amplitude * ratio
    # (em pullback altista: preço cai do topo e retrai para esses níveis)

    # Determina a direção do swing
    # Se o topo veio DEPOIS do fundo → tendência de alta → retração é pullback
    if swing_high_idx > swing_low_idx:
        # Tendência de alta → níveis de retração são suportes
        nivel_382 = round(swing_high - amplitude * 0.382, 2)
        nivel_500 = round(swing_high - amplitude * 0.500, 2)
        nivel_618 = round(swing_high - amplitude * 0.618, 2)
    else:
        # Topo veio antes do fundo → tendência de baixa → Fibonacci de rally
        # Níveis são resistências de retração do rally
        nivel_382 = round(swing_low + amplitude * 0.382, 2)
        nivel_500 = round(swing_low + amplitude * 0.500, 2)
        nivel_618 = round(swing_low + amplitude * 0.618, 2)

    # Verifica se preço está em alguma zona Fibonacci
    zona_atual = None
    em_zona = False

    for nivel_nome, nivel_val in [("38.2", nivel_382), ("50", nivel_500), ("61.8", nivel_618)]:
        if abs(preco_atual - nivel_val) / preco_atual <= tolerancia:
            zona_atual = nivel_nome
            em_zona = True
            break

    # Confluência: Fibonacci + (suporte ou MA)
    confluencia = False
    confluencia_desc = ""

    if em_zona:
        nivel_ref = {"38.2": nivel_382, "50": nivel_500, "61.8": nivel_618}.get(zona_atual, 0)
        conf_parts = []

        if suporte and abs(nivel_ref - suporte) / preco_atual <= 0.03:
            confluencia = True
            conf_parts.append("suporte pivô")

        if mm20 and abs(nivel_ref - mm20) / preco_atual <= 0.02:
            confluencia = True
            conf_parts.append("MM20")

        if mm50 and abs(nivel_ref - mm50) / preco_atual <= 0.02:
            confluencia = True
            conf_parts.append("MM50")

        if conf_parts:
            confluencia_desc = f"Fib {zona_atual}% confluente com {' + '.join(conf_parts)}"

    # Score Fibonacci (0-15)
    score = 0
    if em_zona:
        score += 5  # em zona Fibonacci
        if zona_atual == "61.8":
            score += 3  # golden ratio = zona mais forte
        elif zona_atual == "50":
            score += 2
        elif zona_atual == "38.2":
            score += 1  # retração rasa (tendência muito forte)
        if confluencia:
            score += 7  # confluência é o sinal mais forte

    return FibAnalise(
        swing_high=swing_high,
        swing_low=swing_low,
        nivel_382=nivel_382,
        nivel_500=nivel_500,
        nivel_618=nivel_618,
        zona_atual=zona_atual,
        em_zona_fib=em_zona,
        confluencia=confluencia,
        confluencia_desc=confluencia_desc,
        score_fib=score,
    )

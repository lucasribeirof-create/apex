"""
APEX — Reconhecimento de Padrões de Candles

Detecta os padrões mais confiáveis em contexto:
  - Martelo / Hammer (reversão altista em suporte)
  - Engolfo de Alta (bullish engulfing)
  - Engolfo de Baixa (bearish engulfing)
  - Estrela Cadente / Shooting Star (reversão baixista em resistência)
  - Doji (indecisão — contexto decide)
  - Inside Bar (compressão de volatilidade → breakout)

Cada padrão é avaliado COM CONTEXTO:
  - Posição relativa (perto de suporte/resistência/MA)
  - Volume (confirmação)
  - Tendência recente (5 barras anteriores)
Padrão isolado = fraco. Padrão em contexto = sinal forte.
"""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class PadraoCandle:
    """Resultado de detecção de padrão."""
    nome: str               # ex: "martelo", "engolfo_alta"
    forca: int              # 1 = fraco, 2 = médio, 3 = forte
    direcao: str            # "alta" | "baixa" | "neutro"
    contexto: str           # descrição do contexto (ex: "martelo em suporte com volume")
    barra_idx: int          # index da barra onde ocorre


def detectar_padroes(
    df: pd.DataFrame,
    suporte: float | None = None,
    resistencia: float | None = None,
    mm20: float | None = None,
    n_ultimas: int = 5,
) -> list[PadraoCandle]:
    """
    Detecta padrões de candle nas últimas n_ultimas barras.

    Args:
        df: DataFrame com Open, High, Low, Close, Volume
        suporte: nível de suporte mais próximo
        resistencia: nível de resistência mais próximo
        mm20: média móvel de 20 períodos
        n_ultimas: quantas barras recentes analisar

    Returns:
        Lista de PadraoCandle encontrados, ordenados por força (maior primeiro)
    """
    if df is None or len(df) < 10:
        return []

    padroes: list[PadraoCandle] = []
    o = df["Open"].values
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    v = df["Volume"].values

    vol_media = float(np.mean(v[-20:])) if len(v) >= 20 else float(np.mean(v))

    start = max(1, len(df) - n_ultimas)

    for i in range(start, len(df)):
        body = c[i] - o[i]
        body_abs = abs(body)
        range_total = h[i] - l[i]
        if range_total < 1e-6:
            continue

        alta = body > 0
        sombra_inf = min(o[i], c[i]) - l[i]
        sombra_sup = h[i] - max(o[i], c[i])
        preco = c[i]

        # Volume relativo
        vol_rel = v[i] / vol_media if vol_media > 0 else 1.0

        # Tendência recente (5 barras antes)
        if i >= 5:
            tend_recente = (c[i-1] - c[i-5]) / c[i-5] * 100 if c[i-5] > 0 else 0
        else:
            tend_recente = 0

        # Proximidade a suporte/resistência
        perto_suporte = (suporte is not None and preco > 0 and
                         abs(preco - suporte) / preco < 0.03)
        perto_resistencia = (resistencia is not None and preco > 0 and
                             abs(preco - resistencia) / preco < 0.03)
        perto_mm20 = (mm20 is not None and preco > 0 and
                      abs(preco - mm20) / preco < 0.02)

        # ── MARTELO (Hammer) ──────────────────────────────────────────
        # Corpo pequeno no topo, sombra inferior longa (≥2x corpo)
        if (sombra_inf >= 2 * body_abs and
                sombra_sup <= body_abs and
                body_abs < range_total * 0.35 and
                tend_recente < -2):  # após queda

            forca = 1
            ctx_parts = ["martelo"]
            if perto_suporte:
                forca += 1
                ctx_parts.append("em suporte")
            if perto_mm20:
                forca += 1
                ctx_parts.append("na MM20")
            if vol_rel > 1.3:
                forca = min(forca + 1, 3)
                ctx_parts.append("com volume")

            padroes.append(PadraoCandle(
                nome="martelo", forca=min(forca, 3), direcao="alta",
                contexto=" ".join(ctx_parts), barra_idx=i,
            ))

        # ── ESTRELA CADENTE (Shooting Star) ───────────────────────────
        # Corpo pequeno na base, sombra superior longa (≥2x corpo)
        if (sombra_sup >= 2 * body_abs and
                sombra_inf <= body_abs and
                body_abs < range_total * 0.35 and
                tend_recente > 2):  # após alta

            forca = 1
            ctx_parts = ["estrela cadente"]
            if perto_resistencia:
                forca += 1
                ctx_parts.append("em resistência")
            if vol_rel > 1.3:
                forca = min(forca + 1, 3)
                ctx_parts.append("com volume")

            padroes.append(PadraoCandle(
                nome="estrela_cadente", forca=min(forca, 3), direcao="baixa",
                contexto=" ".join(ctx_parts), barra_idx=i,
            ))

        # ── ENGOLFO DE ALTA (Bullish Engulfing) ──────────────────────
        if i >= 1:
            body_prev = c[i-1] - o[i-1]
            if (body_prev < 0 and body > 0 and  # prev baixa, atual alta
                    body_abs > abs(body_prev) * 1.0 and  # corpo atual ≥ anterior
                    o[i] <= c[i-1] and c[i] >= o[i-1]):  # engolfa

                forca = 1
                ctx_parts = ["engolfo de alta"]
                if perto_suporte:
                    forca += 1
                    ctx_parts.append("em suporte")
                if vol_rel > 1.2:
                    forca = min(forca + 1, 3)
                    ctx_parts.append("com volume")
                if tend_recente < -3:
                    forca = min(forca + 1, 3)
                    ctx_parts.append("após queda")

                padroes.append(PadraoCandle(
                    nome="engolfo_alta", forca=min(forca, 3), direcao="alta",
                    contexto=" ".join(ctx_parts), barra_idx=i,
                ))

        # ── ENGOLFO DE BAIXA (Bearish Engulfing) ─────────────────────
        if i >= 1:
            body_prev = c[i-1] - o[i-1]
            if (body_prev > 0 and body < 0 and  # prev alta, atual baixa
                    body_abs > abs(body_prev) * 1.0 and
                    o[i] >= c[i-1] and c[i] <= o[i-1]):

                forca = 1
                ctx_parts = ["engolfo de baixa"]
                if perto_resistencia:
                    forca += 1
                    ctx_parts.append("em resistência")
                if vol_rel > 1.2:
                    forca = min(forca + 1, 3)
                    ctx_parts.append("com volume")

                padroes.append(PadraoCandle(
                    nome="engolfo_baixa", forca=min(forca, 3), direcao="baixa",
                    contexto=" ".join(ctx_parts), barra_idx=i,
                ))

        # ── DOJI ──────────────────────────────────────────────────────
        # Corpo muito pequeno (< 10% do range)
        if body_abs < range_total * 0.10 and range_total > 0:
            direcao = "neutro"
            forca = 1
            ctx_parts = ["doji"]

            if perto_suporte and tend_recente < -2:
                direcao = "alta"
                forca = 2
                ctx_parts.append("em suporte após queda")
            elif perto_resistencia and tend_recente > 2:
                direcao = "baixa"
                forca = 2
                ctx_parts.append("em resistência após alta")

            padroes.append(PadraoCandle(
                nome="doji", forca=forca, direcao=direcao,
                contexto=" ".join(ctx_parts), barra_idx=i,
            ))

        # ── INSIDE BAR ─────────────────────────────────────────────────
        # Range completamente dentro da barra anterior
        if i >= 1 and h[i] <= h[i-1] and l[i] >= l[i-1]:
            forca = 1
            ctx_parts = ["inside bar"]
            # Compressão = potencial breakout
            compressao = range_total / (h[i-1] - l[i-1]) if (h[i-1] - l[i-1]) > 0 else 1
            if compressao < 0.5:
                forca = 2
                ctx_parts.append("alta compressão")

            # Direção depende da tendência
            direcao = "alta" if tend_recente > 0 else ("baixa" if tend_recente < 0 else "neutro")
            padroes.append(PadraoCandle(
                nome="inside_bar", forca=forca, direcao=direcao,
                contexto=" ".join(ctx_parts), barra_idx=i,
            ))

    # Ordenar por força (maior primeiro)
    padroes.sort(key=lambda p: p.forca, reverse=True)
    return padroes


def resumo_padroes(padroes: list[PadraoCandle]) -> dict:
    """
    Resume os padrões detectados para dados_extras.

    Returns:
        dict com:
          - padroes_alta: nomes dos padrões altistas detectados
          - padroes_baixa: nomes dos padrões baixistas
          - forca_max_alta: maior força altista (0-3)
          - forca_max_baixa: maior força baixista (0-3)
          - score_candles: pontuação (positivo = altista, negativo = baixista)
    """
    if not padroes:
        return {
            "padroes_alta": [],
            "padroes_baixa": [],
            "forca_max_alta": 0,
            "forca_max_baixa": 0,
            "score_candles": 0,
        }

    alta = [p for p in padroes if p.direcao == "alta"]
    baixa = [p for p in padroes if p.direcao == "baixa"]

    score = 0
    for p in alta:
        score += p.forca * 5  # +5 a +15 por padrão altista
    for p in baixa:
        score -= p.forca * 5  # -5 a -15 por padrão baixista

    return {
        "padroes_alta": [p.contexto for p in alta],
        "padroes_baixa": [p.contexto for p in baixa],
        "forca_max_alta": max((p.forca for p in alta), default=0),
        "forca_max_baixa": max((p.forca for p in baixa), default=0),
        "score_candles": score,
    }

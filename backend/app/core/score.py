"""
Score APEX 0-100.
Calculado por ponderação dos 5 filtros — só ativos que passaram os 5 filtros recebem score.
"""
import numpy as np
from typing import Optional
from app.core.filters import calcular_mm

# ─── Pesos por pilar ──────────────────────────────────────────────────────────
PESO_MM200 = 25       # Posição vs MM200
PESO_MEDIAS = 20      # Alinhamento de médias
PESO_ROMPIMENTO = 25  # Rompimento
PESO_VOLUME = 15      # Volume
PESO_FORCA = 15       # Força relativa setorial


def score_mm200(detalhe: dict) -> float:
    """
    0-25 pontos. Baseado em:
    - Dias consecutivos acima da MM200 (max 15 dias = máximo ponderado)
    - Distância percentual acima da MM200
    """
    dias = min(detalhe.get("dias_acima_mm200", 0), 20)
    distancia = min(max(detalhe.get("distancia_pct", 0), 0), 20)

    pts_dias = (dias / 20) * 15        # até 15 pts por dias
    pts_dist = (distancia / 20) * 10   # até 10 pts por distância
    return min(pts_dias + pts_dist, PESO_MM200)


def score_medias(detalhe: dict) -> float:
    """
    0-20 pontos. Baseado em:
    - MM50 vs MM200 (spread percentual)
    - Ambas com inclinação positiva
    """
    mm50 = detalhe.get("mm50", 0)
    mm200 = detalhe.get("mm200", 1)
    spread = max((mm50 / mm200 - 1) * 100, 0) if mm200 > 0 else 0
    spread_pts = min(spread / 5 * 10, 10)  # até 5% de spread = 10 pts

    incl_pts = 0
    if detalhe.get("inclinacao_mm50_positiva"):
        incl_pts += 5
    if detalhe.get("inclinacao_mm200_positiva"):
        incl_pts += 5

    return min(spread_pts + incl_pts, PESO_MEDIAS)


def score_rompimento(detalhe: dict) -> float:
    """
    0-25 pontos. Baseado no percentual de rompimento acima da máxima 60d.
    """
    rompimento_pct = max(detalhe.get("rompimento_pct", 0), 0)
    pts = min(rompimento_pct / 3 * PESO_ROMPIMENTO, PESO_ROMPIMENTO)
    return pts


def score_volume(detalhe: dict) -> float:
    """
    0-15 pontos. Baseado no multiplicador volume atual vs média 20d.
    Mínimo para passar o filtro é 1.5x — pontuação começa a partir daí.
    """
    mult = detalhe.get("multiplicador", 0)
    if mult < 1.5:
        return 0
    # 1.5x = 0 pts, 3.0x = 15 pts
    pts = min((mult - 1.5) / 1.5 * PESO_VOLUME, PESO_VOLUME)
    return pts


def score_forca(detalhe: dict) -> float:
    """
    0-15 pontos. Baseado na força relativa do setor vs IBOV.
    """
    fr = detalhe.get("forca_relativa", 0)
    if fr <= 0:
        return 0
    pts = min(fr / 10 * PESO_FORCA, PESO_FORCA)
    return pts


def calcular_score(filtros: list[dict]) -> int:
    """
    Calcula o score APEX (0-100) a partir dos detalhes dos filtros.
    Só chamar após confirmar que o ativo passou os 5 filtros.
    """
    # Mapear filtros por número
    por_filtro = {f["filtro"]: f for f in filtros}

    pts = 0
    pts += score_mm200(por_filtro.get(1, {}))
    pts += score_medias(por_filtro.get(2, {}))
    pts += score_rompimento(por_filtro.get(3, {}))
    pts += score_volume(por_filtro.get(4, {}))
    pts += score_forca(por_filtro.get(5, {}))

    return int(round(pts))


def calcular_atr(highs: list[float], lows: list[float], closes: list[float], periodo: int = 14) -> Optional[float]:
    """Average True Range — usado para calcular stop e sizing."""
    if len(highs) < periodo + 1:
        return None

    trs = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    return float(np.mean(trs[-periodo:]))


def calcular_sizing(
    patrimonio: float,
    preco_entrada: float,
    atr: float,
    risco_por_trade_pct: float = 1.0,  # CORE=1%, ALPHA=1.5%
) -> dict:
    """
    Calcula tamanho de posição baseado em risco fixo por operação.
    Stop = 2x ATR abaixo da entrada.
    """
    risco_reais = patrimonio * (risco_por_trade_pct / 100)
    stop_loss = preco_entrada - (2 * atr)
    risco_por_acao = preco_entrada - stop_loss

    if risco_por_acao <= 0:
        return {"erro": "ATR maior que preço de entrada"}

    quantidade = int(risco_reais / risco_por_acao)
    valor_posicao = quantidade * preco_entrada
    pct_patrimonio = (valor_posicao / patrimonio) * 100

    return {
        "quantidade": quantidade,
        "preco_entrada": round(preco_entrada, 2),
        "stop_loss": round(stop_loss, 2),
        "alvo_1": round(preco_entrada + (2 * risco_por_acao), 2),  # 2R
        "alvo_2": round(preco_entrada + (3 * risco_por_acao), 2),  # 3R
        "valor_posicao": round(valor_posicao, 2),
        "pct_patrimonio": round(pct_patrimonio, 2),
        "risco_reais": round(risco_reais, 2),
        "atr": round(atr, 2),
    }

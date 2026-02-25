"""
Os 5 Filtros APEX Sequenciais.
Se um ativo falhar em qualquer filtro, é descartado imediatamente.
"""
import numpy as np
from typing import Optional

# ─── Parâmetros dos filtros ───────────────────────────────────────────────────
MM200_MIN_DIAS = 10     # Filtro 1: mínimo de dias consecutivos acima da MM200
MM_VOLUME_DIAS = 20     # Filtro 4: base de cálculo do volume médio
VOLUME_MIN_MULT = 1.5   # Filtro 4: volume mínimo = 1.5x a média (50% acima)
FORÇA_JANELA = 63       # Filtro 5: janela de força relativa setorial (pregões)
MAX_HISTORICO = 63      # dias históricos mínimos necessários


def calcular_mm(precos: list[float], periodo: int) -> Optional[np.ndarray]:
    """Média Móvel Simples."""
    if len(precos) < periodo:
        return None
    arr = np.array(precos, dtype=float)
    mm = np.convolve(arr, np.ones(periodo) / periodo, mode="valid")
    return mm


def filtro_1_mm200(closes: list[float]) -> tuple[bool, dict]:
    """
    Filtro 1: Preço acima da MM200 por pelo menos 10 pregões consecutivos.
    """
    mm200 = calcular_mm(closes, 200)
    if mm200 is None:
        return False, {"filtro": 1, "passou": False, "motivo": "Histórico insuficiente (< 200 dias)"}

    # Quantos dias consecutivos o preço está acima da MM200
    dias_acima = 0
    for i in range(len(mm200) - 1, -1, -1):
        preco_idx = i + 200 - 1
        if preco_idx < len(closes) and closes[preco_idx] > mm200[i]:
            dias_acima += 1
        else:
            break

    passou = dias_acima >= MM200_MIN_DIAS
    return passou, {
        "filtro": 1,
        "passou": passou,
        "dias_acima_mm200": dias_acima,
        "mm200_atual": float(mm200[-1]),
        "preco_atual": float(closes[-1]),
        "distancia_pct": round((closes[-1] / mm200[-1] - 1) * 100, 2),
    }


def filtro_2_alinhamento_medias(closes: list[float]) -> tuple[bool, dict]:
    """
    Filtro 2: MM50 acima da MM200 com inclinação positiva em ambas.
    """
    mm50 = calcular_mm(closes, 50)
    mm200 = calcular_mm(closes, 200)

    if mm50 is None or mm200 is None or len(mm50) < 5 or len(mm200) < 5:
        return False, {"filtro": 2, "passou": False, "motivo": "Histórico insuficiente"}

    # Alinhamento: MM50 > MM200
    mm50_atual = mm50[-1]
    mm200_atual = mm200[-1]
    alinhado = mm50_atual > mm200_atual

    # Inclinação: comparar últimos 5 dias
    incl_mm50 = mm50[-1] > mm50[-5]
    incl_mm200 = mm200[-1] > mm200[-5]

    passou = alinhado and incl_mm50 and incl_mm200
    return passou, {
        "filtro": 2,
        "passou": passou,
        "mm50": round(mm50_atual, 2),
        "mm200": round(mm200_atual, 2),
        "mm50_acima_mm200": alinhado,
        "inclinacao_mm50_positiva": incl_mm50,
        "inclinacao_mm200_positiva": incl_mm200,
    }


def filtro_3_rompimento(closes: list[float], highs: list[float]) -> tuple[bool, dict]:
    """
    Filtro 3: Rompimento da máxima dos últimos 60 dias confirmado.
    """
    if len(highs) < 61:
        return False, {"filtro": 3, "passou": False, "motivo": "Histórico insuficiente"}

    maxima_60 = max(highs[-61:-1])  # máxima dos 60 dias ANTERIORES ao dia atual
    preco_atual = closes[-1]

    passou = preco_atual > maxima_60
    return passou, {
        "filtro": 3,
        "passou": passou,
        "maxima_60d": round(maxima_60, 2),
        "preco_atual": round(preco_atual, 2),
        "rompimento_pct": round((preco_atual / maxima_60 - 1) * 100, 2),
    }


def filtro_4_volume(volumes: list[float]) -> tuple[bool, dict]:
    """
    Filtro 4: Volume no dia do rompimento >= 50% acima da média de 20 dias.
    """
    if len(volumes) < MM_VOLUME_DIAS + 1:
        return False, {"filtro": 4, "passou": False, "motivo": "Histórico insuficiente"}

    media_20d = np.mean(volumes[-MM_VOLUME_DIAS - 1:-1])
    volume_hoje = volumes[-1]
    multiplicador = volume_hoje / media_20d if media_20d > 0 else 0

    passou = multiplicador >= VOLUME_MIN_MULT
    return passou, {
        "filtro": 4,
        "passou": passou,
        "volume_hoje": int(volume_hoje),
        "media_20d": int(media_20d),
        "multiplicador": round(multiplicador, 2),
    }


def filtro_5_forca_setorial(
    retorno_setor_63d: float,
    retorno_ibov_63d: float,
) -> tuple[bool, dict]:
    """
    Filtro 5: Força relativa do setor positiva contra IBOV nos últimos 63 dias.
    Recebe os retornos percentuais já calculados externamente.
    """
    forca_relativa = retorno_setor_63d - retorno_ibov_63d
    passou = forca_relativa > 0

    return passou, {
        "filtro": 5,
        "passou": passou,
        "retorno_setor_63d": round(retorno_setor_63d, 2),
        "retorno_ibov_63d": round(retorno_ibov_63d, 2),
        "forca_relativa": round(forca_relativa, 2),
    }


def aplicar_filtros(
    closes: list[float],
    highs: list[float],
    volumes: list[float],
    retorno_setor_63d: float,
    retorno_ibov_63d: float,
) -> dict:
    """
    Aplica os 5 filtros sequencialmente.
    Retorna resultado completo com detalhes de cada filtro.
    """
    resultados = []

    # Filtro 1
    passou1, det1 = filtro_1_mm200(closes)
    resultados.append(det1)
    if not passou1:
        return {"aprovado": False, "filtro_falhou": 1, "filtros": resultados}

    # Filtro 2
    passou2, det2 = filtro_2_alinhamento_medias(closes)
    resultados.append(det2)
    if not passou2:
        return {"aprovado": False, "filtro_falhou": 2, "filtros": resultados}

    # Filtro 3
    passou3, det3 = filtro_3_rompimento(closes, highs)
    resultados.append(det3)
    if not passou3:
        return {"aprovado": False, "filtro_falhou": 3, "filtros": resultados}

    # Filtro 4
    passou4, det4 = filtro_4_volume(volumes)
    resultados.append(det4)
    if not passou4:
        return {"aprovado": False, "filtro_falhou": 4, "filtros": resultados}

    # Filtro 5
    passou5, det5 = filtro_5_forca_setorial(retorno_setor_63d, retorno_ibov_63d)
    resultados.append(det5)
    if not passou5:
        return {"aprovado": False, "filtro_falhou": 5, "filtros": resultados}

    return {"aprovado": True, "filtro_falhou": None, "filtros": resultados}

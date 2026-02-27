"""
Classificador de Regime de Mercado: BULL / MISTO / BEAR
Baseado no IBOV: MM200, MM50, breadth (% de ações acima da MM200).
"""
from enum import Enum
from typing import Optional
from app.core.filters import calcular_mm


class Regime(str, Enum):
    BULL = "BULL"
    MISTO = "MISTO"
    BEAR = "BEAR"


def calcular_regime(
    closes_ibov: list[float],
    breadth_pct: Optional[float] = None,  # % de ações do IBOV acima da MM200 (0-100)
) -> dict:
    """
    Classifica o regime de mercado.

    BULL:  IBOV acima da MM200, MM50 acima da MM200, breadth > 60%
    MISTO: IBOV abaixo da MM200 mas acima da MM50, ou breadth se deteriorando
    BEAR:  IBOV abaixo da MM200 com volume crescente, ou queda >= 15% em 30 dias
    """
    if len(closes_ibov) < 200:
        return {
            "regime": Regime.MISTO,
            "motivo": "Histórico insuficiente — usando MISTO como padrão conservador",
            "detalhes": {},
        }

    mm200 = calcular_mm(closes_ibov, 200)
    mm50 = calcular_mm(closes_ibov, 50)

    ibov_atual = closes_ibov[-1]
    mm200_atual = mm200[-1]
    mm50_atual = mm50[-1] if mm50 is not None and len(mm50) > 0 else None

    acima_mm200 = ibov_atual > mm200_atual
    mm50_acima_mm200 = (mm50_atual > mm200_atual) if mm50_atual else False

    # Variação 30 dias
    var_30d = ((ibov_atual / closes_ibov[-31]) - 1) * 100 if len(closes_ibov) >= 31 else 0

    detalhes = {
        "ibov_atual": round(ibov_atual, 0),
        "mm200": round(mm200_atual, 0),
        "mm50": round(mm50_atual, 0) if mm50_atual else None,
        "acima_mm200": acima_mm200,
        "mm50_acima_mm200": mm50_acima_mm200,
        "var_30d_pct": round(var_30d, 2),
        "breadth_pct": breadth_pct,
    }

    # ─── Classificação ────────────────────────────────────────────────────────

    # BEAR: queda forte ou abaixo da MM200 com deterioração
    if var_30d <= -15:
        return {
            "regime": Regime.BEAR,
            "motivo": f"Queda de {var_30d:.1f}% em 30 dias",
            "detalhes": detalhes,
        }

    if not acima_mm200 and not mm50_acima_mm200:
        return {
            "regime": Regime.BEAR,
            "motivo": "IBOV abaixo da MM200 e MM50 abaixo da MM200",
            "detalhes": detalhes,
        }

    # BULL: tudo alinhado E breadth confirmado >= 60%
    # Sem dados de breadth (None) → conservador: classifica como MISTO
    if acima_mm200 and mm50_acima_mm200 and breadth_pct is not None and breadth_pct >= 60:
        return {
            "regime": Regime.BULL,
            "motivo": f"IBOV acima da MM200, MM50 acima da MM200, breadth {breadth_pct:.0f}%",
            "detalhes": detalhes,
        }

    # MISTO: demais casos (inclui quando breadth é None ou < 60%)
    if not acima_mm200:
        motivo = "IBOV abaixo da MM200"
    elif breadth_pct is None:
        motivo = "IBOV acima da MM200 e MM50 — breadth não disponível (conservador: MISTO)"
    elif breadth_pct < 60:
        motivo = f"IBOV acima das médias mas breadth fraco ({breadth_pct:.0f}% das ações acima da MM200)"
    else:
        motivo = "IBOV em zona intermediária"

    return {
        "regime": Regime.MISTO,
        "motivo": motivo,
        "detalhes": detalhes,
    }


def get_acoes_permitidas_regime(regime: str) -> dict:
    """
    Retorna quais ações cada módulo pode tomar conforme o regime atual.
    Usado para bloquear entradas, redirecionar aportes, etc.
    """
    if regime == Regime.BULL:
        return {
            "momentum_novas_entradas": True,
            "wheel_renovacao": True,
            "etfs_aportes": True,
            "caixa_pct_aporte": 0,
            "descricao": "Todos os módulos operando em plena capacidade.",
        }
    elif regime == Regime.MISTO:
        return {
            "momentum_novas_entradas": False,
            "wheel_renovacao": True,
            "etfs_aportes": True,
            "caixa_pct_aporte": 30,
            "descricao": "Novas entradas momentum pausadas. 30% dos aportes direcionados para caixa.",
        }
    else:  # BEAR
        return {
            "momentum_novas_entradas": False,
            "wheel_renovacao": False,
            "etfs_aportes": False,
            "caixa_pct_aporte": 100,
            "descricao": "Regime BEAR. 100% dos aportes em caixa e renda fixa. Aguardando melhora.",
        }

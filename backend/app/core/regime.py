"""
Classificador de Regime de Mercado: BULL / MISTO / BEAR

Versão 2.0 — Enriquecido com sinais macro.
Mantém classificação categórica (o CEO Brain é LLM, não precisa de falsa
precisão numérica), mas incorpora sinais de VIX, DXY, juro real e Treasury
para decisões mais informadas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.core.filters import calcular_mm


class Regime(str, Enum):
    BULL = "BULL"
    MISTO = "MISTO"
    BEAR = "BEAR"


@dataclass
class RegimeInfo:
    """Regime de mercado + sinais enriquecidos."""

    regime: str                             # BULL | MISTO | BEAR
    regime_motivo: str                      # Texto explicativo
    sinais: dict = field(default_factory=dict)  # Dados brutos (VIX, DXY, etc.)
    flags: list[str] = field(default_factory=list)  # Alertas macro ativos
    detalhes: dict = field(default_factory=dict)  # Detalhes técnicos do IBOV

    def to_dict(self) -> dict:
        return {
            "regime": self.regime,
            "regime_motivo": self.regime_motivo,
            "sinais": self.sinais,
            "flags": self.flags,
            "detalhes": self.detalhes,
        }

    def resumo_texto(self) -> str:
        """Texto para injetar no prompt da IA."""
        partes = [f"Regime: {self.regime} — {self.regime_motivo}"]
        if self.flags:
            for f in self.flags:
                partes.append(f"  ⚠ {f}")
        return "\n".join(partes)


def calcular_regime(
    closes_ibov: list[float],
    breadth_pct: Optional[float] = None,
    macro_context=None,
) -> RegimeInfo:
    """
    Classifica o regime de mercado.

    Classificação base (categórica):
      BULL:  IBOV acima da MM200, MM50 acima da MM200, var_30d > 0
      MISTO: Casos intermediários
      BEAR:  Queda >= 15% em 30d, ou IBOV + MM50 abaixo da MM200

    Sinais macro (enriquecem a decisão sem alterar a classificação):
      VIX > 25 = cautela
      DXY forte (acima da MM50) = pressão sobre emergentes
      Juro real > 6% = renda fixa atrativa vs bolsa
      Treasury 10Y subindo = pressão global
    """
    if len(closes_ibov) < 200:
        return RegimeInfo(
            regime=Regime.MISTO,
            regime_motivo="Histórico insuficiente — usando MISTO como padrão conservador",
        )

    mm200 = calcular_mm(closes_ibov, 200)
    mm50 = calcular_mm(closes_ibov, 50)

    ibov_atual = closes_ibov[-1]
    mm200_atual = mm200[-1]
    mm50_atual = mm50[-1] if mm50 is not None and len(mm50) > 0 else None

    acima_mm200 = ibov_atual > mm200_atual
    mm50_acima_mm200 = (mm50_atual > mm200_atual) if mm50_atual else False

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

    # ── Sinais macro enriquecidos ──────────────────────────────────────────
    sinais = {}
    flags = []

    if macro_context is not None:
        mc = macro_context
        if mc.vix is not None:
            sinais["vix"] = mc.vix
            if mc.vix > 35:
                flags.append(f"VIX em nível de pânico ({mc.vix:.1f})")
            elif mc.vix > 25:
                flags.append(f"VIX elevado ({mc.vix:.1f}) — mercado em cautela")

        if mc.dxy is not None:
            sinais["dxy"] = mc.dxy
            if mc.dxy_mm50 and mc.dxy > mc.dxy_mm50:
                sinais["dxy_acima_mm50"] = True
                flags.append("DXY acima da MM50 — dólar global forte, pressão sobre emergentes")

        if mc.juro_real is not None:
            sinais["juro_real"] = mc.juro_real
            if mc.juro_real > 6:
                flags.append(f"Juro real alto ({mc.juro_real:.1f}%) — renda fixa mais atrativa")

        if mc.treasury_10y is not None:
            sinais["treasury_10y"] = mc.treasury_10y
            if mc.treasury_10y > 5:
                flags.append(f"Treasury 10Y em {mc.treasury_10y:.2f}% — custo global de capital elevado")

        if mc.petroleo_wti is not None:
            sinais["petroleo_wti"] = mc.petroleo_wti
        if mc.sp500 is not None:
            sinais["sp500"] = mc.sp500
        if mc.ouro is not None:
            sinais["ouro"] = mc.ouro

    # ── Classificação base (categórica) ────────────────────────────────────

    if var_30d <= -15:
        return RegimeInfo(
            regime=Regime.BEAR,
            regime_motivo=f"Queda de {var_30d:.1f}% em 30 dias",
            sinais=sinais, flags=flags, detalhes=detalhes,
        )

    if not acima_mm200 and not mm50_acima_mm200:
        return RegimeInfo(
            regime=Regime.BEAR,
            regime_motivo="IBOV abaixo da MM200 e MM50 abaixo da MM200",
            sinais=sinais, flags=flags, detalhes=detalhes,
        )

    if acima_mm200 and mm50_acima_mm200 and var_30d > 0:
        return RegimeInfo(
            regime=Regime.BULL,
            regime_motivo=f"IBOV acima da MM200, MM50 acima da MM200, {var_30d:+.1f}% em 30 dias",
            sinais=sinais, flags=flags, detalhes=detalhes,
        )

    if not acima_mm200:
        motivo = "IBOV abaixo da MM200"
    elif not mm50_acima_mm200:
        motivo = "MM50 abaixo da MM200 — tendência de médio prazo enfraquecida"
    elif var_30d <= 0:
        motivo = f"IBOV acima das médias mas sem força ({var_30d:+.1f}% em 30 dias)"
    else:
        motivo = "IBOV em zona intermediária"

    return RegimeInfo(
        regime=Regime.MISTO,
        regime_motivo=motivo,
        sinais=sinais, flags=flags, detalhes=detalhes,
    )


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

"""
Motor de Aportes Inteligentes — DCA Adaptativo com Rebalanceamento

Combina três estratégias comprovadas:
  1. Rebalancing DCA  — direciona aportes para módulos abaixo do alvo
  2. Regime-Adaptive   — respeita regime macro (BULL/MISTO/BEAR)
  3. Value Averaging   — prioriza módulos com maior valor a recuperar

Fluxo:
  aporte_mensal → filtro regime (caixa_pct) → capital investível
  → distribuição por desvio ponderado → semáforo por módulo → resultado

Semáforo:
  🟢 VERDE  — Módulo recebendo aportes normalmente
  🟡 AMARELO — Módulo pausado ou reduzido pelo regime/guardrails
  🔴 VERMELHO — Módulo bloqueado (kill switch, CB, ou atinge limite)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ─── Tipos de resultado ───────────────────────────────────────────────────────

@dataclass
class AporteModulo:
    """Distribuição de aporte para um módulo específico."""
    modulo: str
    valor: float                  # R$ destinado ao módulo
    pct_do_aporte: float          # % do aporte total
    semaforo: str                 # VERDE | AMARELO | VERMELHO
    motivo: str                   # Justificativa curta
    desvio_pp: float              # desvio real-alvo em pp (negativo = abaixo)
    alvo_pct: float               # % alvo configurado
    real_pct: float               # % real atual

    def to_dict(self) -> dict:
        return {
            "modulo": self.modulo,
            "valor": round(self.valor, 2),
            "pct_do_aporte": round(self.pct_do_aporte, 1),
            "semaforo": self.semaforo,
            "motivo": self.motivo,
            "desvio_pp": round(self.desvio_pp, 1),
            "alvo_pct": round(self.alvo_pct, 1),
            "real_pct": round(self.real_pct, 1),
        }


@dataclass
class ResultadoAporte:
    """Resultado completo do cálculo de aporte inteligente."""
    aporte_total: float           # R$ total do mês
    capital_investivel: float     # R$ após filtro regime (deduz caixa)
    capital_caixa: float          # R$ direcionado para caixa por regime
    regime: str                   # BULL | MISTO | BEAR
    regime_descricao: str
    modulos: list[AporteModulo] = field(default_factory=list)
    resumo: str = ""              # Texto descritivo do plano
    alertas: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "aporte_total": round(self.aporte_total, 2),
            "capital_investivel": round(self.capital_investivel, 2),
            "capital_caixa": round(self.capital_caixa, 2),
            "regime": self.regime,
            "regime_descricao": self.regime_descricao,
            "modulos": [m.to_dict() for m in self.modulos],
            "resumo": self.resumo,
            "alertas": self.alertas,
        }


# ─── Constantes ───────────────────────────────────────────────────────────────

# Módulos que recebem aportes automaticamente (exceto teses = convicção manual)
MODULOS_AUTO = ["etfs", "fiis", "renda_fixa", "momentum", "wheel", "alpha", "dividendos"]

# Módulos defensivos (recebem prioridade em BEAR/MISTO)
MODULOS_DEFENSIVOS = {"renda_fixa", "fiis", "caixa"}

# Módulos agressivos (pausados em BEAR)
MODULOS_AGRESSIVOS = {"momentum", "wheel", "alpha"}

# Peso extra para módulos mais distantes do alvo (convexidade)
EXPOENTE_DESVIO = 1.5


# ─── Motor principal ──────────────────────────────────────────────────────────

def calcular_aporte_inteligente(
    aporte_mensal: float,
    alocacao_real: dict[str, float],
    alocacao_alvo: dict[str, float],
    regime: str = "MISTO",
    kill_switch_ativo: bool = False,
    kill_switch_nivel: int = 0,
    cb_modifier: float = 1.0,
    guardrails: Optional[dict] = None,
) -> ResultadoAporte:
    """
    Calcula a distribuição inteligente do aporte mensal.

    Args:
        aporte_mensal: Valor em R$ do aporte do mês
        alocacao_real: % real por módulo (de contexto.py)
        alocacao_alvo: % alvo por módulo (configuração do portfólio)
        regime: BULL | MISTO | BEAR
        kill_switch_ativo: Se True, bloqueia todos os módulos agressivos
        kill_switch_nivel: 0=normal, 1=alerta, 2+=pausa total
        cb_modifier: Multiplicador do circuit breaker (1.0=normal, 0.5=reduzido)
        guardrails: Guardrails macro (equity_max_pct, rf_min_pct, caixa_min_pct)
    """
    from app.core.regime import get_acoes_permitidas_regime

    if aporte_mensal <= 0:
        return ResultadoAporte(
            aporte_total=0,
            capital_investivel=0,
            capital_caixa=0,
            regime=regime,
            regime_descricao="Sem aporte configurado.",
            resumo="Configure um valor de aporte mensal para receber sugestões.",
        )

    alertas: list[str] = []

    # ── 1. Kill Switch check ───────────────────────────────────────────
    if kill_switch_ativo and kill_switch_nivel >= 2:
        return ResultadoAporte(
            aporte_total=aporte_mensal,
            capital_investivel=0,
            capital_caixa=aporte_mensal,
            regime=regime,
            regime_descricao="Kill Switch ativo — todos os aportes em caixa/renda fixa.",
            modulos=[AporteModulo(
                modulo="caixa",
                valor=aporte_mensal,
                pct_do_aporte=100,
                semaforo="VERMELHO",
                motivo="Kill Switch macro nível 2+ — capital preservado em caixa",
                desvio_pp=0, alvo_pct=0, real_pct=0,
            )],
            resumo=f"⛔ Kill Switch macro ativo. 100% do aporte (R${aporte_mensal:,.0f}) direcionado para caixa.",
            alertas=["Kill Switch macro nível 2+ ativado — aportes em risco pausados"],
        )

    # ── 2. Regime filter — quanto vai para caixa ──────────────────────
    acoes_regime = get_acoes_permitidas_regime(regime)
    caixa_pct = acoes_regime.get("caixa_pct_aporte", 0) / 100
    capital_caixa = aporte_mensal * caixa_pct
    capital_investivel = aporte_mensal - capital_caixa

    # Apply circuit breaker modifier
    if cb_modifier < 1.0:
        reducao = capital_investivel * (1 - cb_modifier)
        capital_caixa += reducao
        capital_investivel *= cb_modifier
        alertas.append(f"Circuit Breaker reduzindo exposição em {(1-cb_modifier)*100:.0f}%")

    # Kill switch nível 1 = alerta (continua mas avisa)
    if kill_switch_ativo and kill_switch_nivel == 1:
        alertas.append("Kill Switch nível 1 (alerta) — considere reduzir exposição")

    regime_desc = acoes_regime.get("descricao", f"Regime {regime}")

    # ── 3. Identificar módulos ativos (alvo > 0) ─────────────────────
    modulos_ativos = {
        m: alvo for m, alvo in alocacao_alvo.items()
        if alvo > 0 and m != "caixa"
    }

    if not modulos_ativos:
        return ResultadoAporte(
            aporte_total=aporte_mensal,
            capital_investivel=0,
            capital_caixa=aporte_mensal,
            regime=regime,
            regime_descricao=regime_desc,
            modulos=[AporteModulo(
                modulo="caixa",
                valor=aporte_mensal,
                pct_do_aporte=100,
                semaforo="AMARELO",
                motivo="Nenhum módulo com alocação alvo configurada",
                desvio_pp=0, alvo_pct=0, real_pct=0,
            )],
            resumo="Configure alvos de alocação nas configurações para receber sugestões inteligentes.",
        )

    # ── 4. Calcular desvios e pesos ──────────────────────────────────
    # Módulos abaixo do alvo recebem peso proporcional ao desvio^1.5
    # Módulos ACIMA do alvo não recebem aportes (peso zero)
    pesos: dict[str, float] = {}
    semaforos: dict[str, tuple[str, str]] = {}  # modulo -> (semaforo, motivo)

    for modulo, alvo in modulos_ativos.items():
        real = alocacao_real.get(modulo, 0)
        desvio = real - alvo  # positivo = acima, negativo = abaixo

        # Regime blocks
        is_agressivo = modulo in MODULOS_AGRESSIVOS
        is_defensivo = modulo in MODULOS_DEFENSIVOS

        # BEAR: bloqueia módulos agressivos
        if regime == "BEAR" and is_agressivo:
            pesos[modulo] = 0
            semaforos[modulo] = ("VERMELHO", f"Regime BEAR — {modulo} pausado")
            continue

        # MISTO: bloqueia novas entradas em momentum
        if regime == "MISTO" and modulo == "momentum":
            if not acoes_regime.get("momentum_novas_entradas", True):
                pesos[modulo] = 0
                semaforos[modulo] = ("AMARELO", "Regime MISTO — novas entradas momentum pausadas")
                continue

        # Já no alvo ou acima: não recebe aporte
        if desvio >= 0:
            pesos[modulo] = 0
            semaforos[modulo] = ("VERDE", f"No alvo ou acima (+{desvio:.1f}pp)")
            continue

        # Quanto mais abaixo do alvo, maior o peso (convexidade)
        peso = abs(desvio) ** EXPOENTE_DESVIO

        # Boost defensivo em regimes adversos
        if regime in ("BEAR", "MISTO") and is_defensivo:
            peso *= 1.3

        pesos[modulo] = peso
        semaforos[modulo] = ("VERDE", f"Abaixo do alvo ({desvio:+.1f}pp)")

    # ── 5. Se ninguém precisa de aporte, distribui proporcionalmente ──
    total_peso = sum(pesos.values())

    if total_peso == 0:
        # Todos no alvo ou acima: distribui pro-rata pelos alvos
        total_alvo = sum(modulos_ativos.values())
        resultado_modulos = []
        for modulo, alvo in modulos_ativos.items():
            frac = alvo / total_alvo if total_alvo > 0 else 0
            valor = capital_investivel * frac
            real = alocacao_real.get(modulo, 0)
            desvio = real - alvo
            sem, mot = semaforos.get(modulo, ("VERDE", "Pro-rata"))
            resultado_modulos.append(AporteModulo(
                modulo=modulo,
                valor=valor,
                pct_do_aporte=round((valor / aporte_mensal * 100) if aporte_mensal > 0 else 0, 1),
                semaforo=sem,
                motivo=mot + " — aporte pro-rata",
                desvio_pp=round(desvio, 1),
                alvo_pct=alvo,
                real_pct=real,
            ))
    else:
        # ── 6. Distribuir capital investível pelo peso dos desvios ────
        resultado_modulos = []
        for modulo, alvo in modulos_ativos.items():
            peso = pesos.get(modulo, 0)
            frac = peso / total_peso if total_peso > 0 else 0
            valor = capital_investivel * frac
            real = alocacao_real.get(modulo, 0)
            desvio = real - alvo
            sem, mot = semaforos.get(modulo, ("VERDE", ""))
            resultado_modulos.append(AporteModulo(
                modulo=modulo,
                valor=valor,
                pct_do_aporte=round((valor / aporte_mensal * 100) if aporte_mensal > 0 else 0, 1),
                semaforo=sem,
                motivo=mot,
                desvio_pp=round(desvio, 1),
                alvo_pct=alvo,
                real_pct=real,
            ))

    # ── 7. Adicionar parcela caixa ────────────────────────────────────
    if capital_caixa > 0:
        caixa_alvo = alocacao_alvo.get("caixa", 0)
        caixa_real = alocacao_real.get("caixa", 0)
        caixa_desvio = caixa_real - caixa_alvo
        sem_caixa = "AMARELO" if regime in ("MISTO", "BEAR") else "VERDE"
        mot_caixa = f"Regime {regime} — {caixa_pct*100:.0f}% do aporte em caixa"
        resultado_modulos.append(AporteModulo(
            modulo="caixa",
            valor=capital_caixa,
            pct_do_aporte=round((capital_caixa / aporte_mensal * 100) if aporte_mensal > 0 else 0, 1),
            semaforo=sem_caixa,
            motivo=mot_caixa,
            desvio_pp=round(caixa_desvio, 1),
            alvo_pct=caixa_alvo,
            real_pct=caixa_real,
        ))

    # ── 8. Teses (lembrete — DCA manual por convicção) ────────────────
    teses_alvo = alocacao_alvo.get("teses", 0)
    if teses_alvo > 0:
        teses_real = alocacao_real.get("teses", 0)
        resultado_modulos.append(AporteModulo(
            modulo="teses",
            valor=0,
            pct_do_aporte=0,
            semaforo="AMARELO",
            motivo="DCA manual — aporte por convicção pessoal",
            desvio_pp=round(teses_real - teses_alvo, 1),
            alvo_pct=teses_alvo,
            real_pct=teses_real,
        ))

    # Ordenar por valor (maior primeiro), depois por módulo
    resultado_modulos.sort(key=lambda m: (-m.valor, m.modulo))

    # ── 9. Gerar resumo ──────────────────────────────────────────────
    recebem = [m for m in resultado_modulos if m.valor > 0 and m.modulo != "caixa"]
    resumo_parts = [f"Aporte de R${aporte_mensal:,.0f} no regime {regime}."]

    if capital_caixa > 0:
        resumo_parts.append(f"R${capital_caixa:,.0f} ({caixa_pct*100:.0f}%) direcionado para caixa por regime.")

    if recebem:
        top3 = recebem[:3]
        destaques = ", ".join(f"{m.modulo} (R${m.valor:,.0f})" for m in top3)
        resumo_parts.append(f"Principais destinos: {destaques}.")

    bloqueados = [m for m in resultado_modulos if m.semaforo == "VERMELHO"]
    if bloqueados:
        nomes = ", ".join(m.modulo for m in bloqueados)
        resumo_parts.append(f"Módulos bloqueados: {nomes}.")

    return ResultadoAporte(
        aporte_total=aporte_mensal,
        capital_investivel=capital_investivel,
        capital_caixa=capital_caixa,
        regime=regime,
        regime_descricao=regime_desc,
        modulos=resultado_modulos,
        resumo=" ".join(resumo_parts),
        alertas=alertas,
    )


# ─── Simulação de projeação com DCA ──────────────────────────────────────────

def projetar_patrimonio_dca(
    patrimonio_atual: float,
    aporte_mensal: float,
    taxa_anual_pct: float = 12.0,
    meses: int = 60,
) -> list[dict]:
    """
    Projeta evolução do patrimônio com aportes mensais regulares.

    Retorna lista de snapshots mensais:
      {mes, patrimonio_sem_aporte, patrimonio_com_aporte, aporte_acumulado}
    """
    taxa_mensal = (1 + taxa_anual_pct / 100) ** (1 / 12) - 1

    sem_aporte = patrimonio_atual
    com_aporte = patrimonio_atual
    aporte_acumulado = 0.0

    pontos = [{
        "mes": 0,
        "patrimonio_sem_aporte": round(sem_aporte, 2),
        "patrimonio_com_aporte": round(com_aporte, 2),
        "aporte_acumulado": 0,
    }]

    for m in range(1, meses + 1):
        sem_aporte *= (1 + taxa_mensal)
        com_aporte = (com_aporte + aporte_mensal) * (1 + taxa_mensal)
        aporte_acumulado += aporte_mensal

        pontos.append({
            "mes": m,
            "patrimonio_sem_aporte": round(sem_aporte, 2),
            "patrimonio_com_aporte": round(com_aporte, 2),
            "aporte_acumulado": round(aporte_acumulado, 2),
        })

    return pontos

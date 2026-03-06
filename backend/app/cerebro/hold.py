"""
Hold & Watchlist — Classificação inteligente de posições (Fase 5).

Três categorias de posição:
  TRADE    — posição com stop fixo, alvo definido, horizonte curto/médio
  HOLD     — posição de longo prazo, sem stop fixo, revisão trimestral
  WATCHLIST — ativo monitorado com trigger de entrada

Critérios HOLD:
  - Score fundamentalista ≥ 80
  - ROE ≥ 15%
  - DL/EBITDA < 2.5 (saúde financeira sólida)
  - FCF positivo
  - Nenhuma red flag eliminatória
  - Posição limitada a 3-8% do patrimônio

Kill Switch Macro:
  - RISK_OFF + confiança ≥ 70% → alerta urgente de redução
  - RISK_OFF + confiança ≥ 85% → pausa obrigatória (CEO não pode entrar)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ─── Classificação Hold ──────────────────────────────────────────────────────

HOLD_SCORE_MIN = 80
HOLD_ROE_MIN = 15.0          # %
HOLD_DL_EBITDA_MAX = 2.5
HOLD_POS_MIN_PCT = 3.0       # % do patrimônio
HOLD_POS_MAX_PCT = 8.0       # % do patrimônio

# Watchlist: score entre estes limites → monitorar
WATCH_SCORE_MIN = 45
WATCH_SCORE_MAX = 70


@dataclass
class HoldClassification:
    """Resultado da avaliação de elegibilidade HOLD."""
    ticker: str
    elegivel: bool
    motivo: str
    score: float
    criterios: dict               # detalhamento de cada critério
    posicao_max_pct: float = HOLD_POS_MAX_PCT
    revisao: str = "trimestral"   # periodicidade da reavaliação


@dataclass
class WatchlistCandidate:
    """Ativo que não foi selecionado mas merece monitoramento."""
    ticker: str
    nome: str
    score: float
    setor: str
    trigger_tipo: str             # PRECO | BALANCO | MACRO | MOMENTUM
    trigger_descricao: str        # texto descritivo do trigger
    trigger_valor: Optional[float] = None   # preço-alvo de entrada
    dados_extras: dict = field(default_factory=dict)


@dataclass
class KillSwitchState:
    """Estado do kill switch macro."""
    ativo: bool
    nivel: int                    # 0=normal, 1=alerta, 2=pausa
    motivo: str
    regime: str
    confianca: int
    recomendacao: str


# ─── Avaliação Hold ──────────────────────────────────────────────────────────

def avaliar_hold(dados: dict, score: float, red_flags: list[str]) -> HoldClassification:
    """
    Avalia se um ativo é elegível para classificação HOLD.

    Args:
        dados: dict com indicadores fundamentais (output de _fetch_fundamentals)
        score: score total 0-100 dos 4 pilares
        red_flags: lista de flags do _check_red_flags
    """
    criterios = {}
    motivos_falha = []

    # 1. Score mínimo
    criterios["score"] = {"valor": score, "minimo": HOLD_SCORE_MIN, "ok": score >= HOLD_SCORE_MIN}
    if score < HOLD_SCORE_MIN:
        motivos_falha.append(f"score {score:.0f} < {HOLD_SCORE_MIN}")

    # 2. ROE mínimo
    roe = dados.get("roe")
    roe_ok = roe is not None and roe >= HOLD_ROE_MIN
    criterios["roe"] = {"valor": roe, "minimo": HOLD_ROE_MIN, "ok": roe_ok}
    if not roe_ok:
        motivos_falha.append(f"ROE {roe or 'N/A'}% < {HOLD_ROE_MIN}%")

    # 3. DL/EBITDA saudável
    dl = dados.get("dl_ebitda")
    dl_ok = dl is None or dl < HOLD_DL_EBITDA_MAX  # None = banco/seguradora, OK
    criterios["dl_ebitda"] = {"valor": dl, "maximo": HOLD_DL_EBITDA_MAX, "ok": dl_ok}
    if not dl_ok:
        motivos_falha.append(f"DL/EBITDA {dl:.1f}x > {HOLD_DL_EBITDA_MAX}x")

    # 4. FCF positivo
    fcf = dados.get("fcf")
    fcf_ok = fcf is None or fcf > 0  # None = banco, OK
    criterios["fcf"] = {"valor": fcf, "ok": fcf_ok}
    if not fcf_ok:
        motivos_falha.append("FCF negativo")

    # 5. Sem red flags eliminatórias
    eliminatorias = [f for f in red_flags if f.startswith("ELIMINAR")]
    no_elim = len(eliminatorias) == 0
    criterios["red_flags"] = {"eliminatorias": eliminatorias, "ok": no_elim}
    if not no_elim:
        motivos_falha.append(f"red flags: {', '.join(eliminatorias)}")

    elegivel = len(motivos_falha) == 0

    if elegivel:
        # Format FCF string
        if fcf and fcf > 1e9:
            fcf_str = f"R${fcf / 1e9:.1f}B"
        elif fcf:
            fcf_str = f"R${fcf / 1e6:.0f}M"
        else:
            fcf_str = "N/A"

        # Format DL/EBITDA string
        if dl is not None and dl < 0:
            dl_str = "caixa líquido"
        elif dl is not None:
            dl_str = f"DL/EBITDA {dl:.1f}x"
        else:
            dl_str = "sem dívida"

        motivo = f"HOLD elegível: score {score:.0f}/100, ROE {roe:.0f}%, {dl_str}, FCF {fcf_str}"
    else:
        motivo = f"Não elegível: {'; '.join(motivos_falha)}"

    return HoldClassification(
        ticker=dados.get("ticker", "?"),
        elegivel=elegivel,
        motivo=motivo,
        score=score,
        criterios=criterios,
    )


# ─── Geração de watchlist candidates ────────────────────────────────────────

def gerar_watchlist_candidates(
    candidatos_todos: list[dict],
    selecionados_tickers: set[str],
    n_max: int = 5,
) -> list[WatchlistCandidate]:
    """
    Gera candidatos à watchlist: ativos com score 45-70 que não
    foram selecionados para a carteira.
    """
    watch = []
    for d in candidatos_todos:
        ticker = d.get("ticker", "")
        score = d.get("score", 0)

        # Pula os que já entraram na carteira
        if ticker in selecionados_tickers:
            continue

        # Faixa de watchlist
        if not (WATCH_SCORE_MIN <= score <= WATCH_SCORE_MAX):
            continue

        # Determina trigger baseado no perfil do ativo
        trigger_tipo, trigger_desc, trigger_valor = _determinar_trigger(d)

        watch.append(WatchlistCandidate(
            ticker=ticker,
            nome=d.get("nome", ticker),
            score=score,
            setor=d.get("setor", "outro") if "setor" in d else _get_setor(ticker),
            trigger_tipo=trigger_tipo,
            trigger_descricao=trigger_desc,
            trigger_valor=trigger_valor,
            dados_extras={
                "pl": d.get("pl"),
                "roe": d.get("roe"),
                "momentum_6m": d.get("momentum_6m"),
                "pilares": d.get("_breakdown", {}),
            },
        ))

    watch.sort(key=lambda w: w.score, reverse=True)
    return watch[:n_max]


def _determinar_trigger(d: dict) -> tuple[str, str, float | None]:
    """Determina o tipo de trigger mais adequado para o ativo."""
    preco = d.get("preco", 0)
    mom = d.get("momentum_6m", 0)
    mm200 = d.get("mm200")
    pl = d.get("pl")
    cr = d.get("cresc_receita")

    # Se momentum negativo mas fundamentos ok → esperar reversão
    if mom < -10 and mm200 and preco < mm200:
        target = round(mm200 * 0.98, 2)  # entrar perto da MM200
        return (
            "MOMENTUM",
            f"Entrar quando preço cruzar MM200 (R${mm200:.2f}) com volume",
            target,
        )

    # Se P/L alto mas crescendo → esperar balanço
    if pl and pl > 18 and cr and cr > 10:
        return (
            "BALANCO",
            f"Aguardar próximo balanço confirmar crescimento de {cr:.0f}% (P/L atual {pl:.0f}x alto)",
            None,
        )

    # Se preço caiu mas fundamentos bons → zona de compra por preço
    if mom < 0 and preco > 0:
        target = round(preco * 0.92, 2)  # 8% abaixo do preço atual
        return (
            "PRECO",
            f"Entrar se preço recuar para R${target:.2f} (-8% do atual R${preco:.2f})",
            target,
        )

    # Default: macro favorável
    return (
        "MACRO",
        "Entrar quando cenário macro favorecer o setor",
        None,
    )


def _get_setor(ticker: str) -> str:
    try:
        from app.core.universe import get_ticker_info
        info = get_ticker_info(ticker)
        return info.get("setor", "outro") if info else "outro"
    except Exception:
        return "outro"


# ─── Kill Switch Macro ───────────────────────────────────────────────────────

KILL_SWITCH_ALERTA_CONFIANCA = 70    # confiança mínima para alerta
KILL_SWITCH_PAUSA_CONFIANCA = 85     # confiança mínima para pausa

def avaliar_kill_switch(regime: str, confianca: int, regime_score: int) -> KillSwitchState:
    """
    Avalia se o kill switch macro deve ser ativado.

    O kill switch é ativado quando o regime é RISK_OFF com alta confiança,
    indicando que o cenário macro é inequivocamente hostil.

    Níveis:
      0 — Normal: operação livre
      1 — Alerta: RISK_OFF + confiança ≥ 70% → alertar + recomendar redução
      2 — Pausa:  RISK_OFF + confiança ≥ 85% → bloquear novas entradas em equity
    """
    if regime != "RISK_OFF":
        return KillSwitchState(
            ativo=False,
            nivel=0,
            motivo="Regime não é RISK_OFF",
            regime=regime,
            confianca=confianca,
            recomendacao="Operação normal",
        )

    if confianca >= KILL_SWITCH_PAUSA_CONFIANCA:
        return KillSwitchState(
            ativo=True,
            nivel=2,
            motivo=(
                f"RISK_OFF com confiança {confianca}% (≥{KILL_SWITCH_PAUSA_CONFIANCA}%) "
                f"e score {regime_score}/100 — cenário macro inequivocamente hostil"
            ),
            regime=regime,
            confianca=confianca,
            recomendacao=(
                "PAUSA OBRIGATÓRIA: zero novas entradas em equity. "
                "Reduzir posições existentes para mínimo. "
                "Priorizar RF pós-fixada e caixa."
            ),
        )

    if confianca >= KILL_SWITCH_ALERTA_CONFIANCA:
        return KillSwitchState(
            ativo=True,
            nivel=1,
            motivo=(
                f"RISK_OFF com confiança {confianca}% (≥{KILL_SWITCH_ALERTA_CONFIANCA}%) "
                f"e score {regime_score}/100 — cenário macro hostil"
            ),
            regime=regime,
            confianca=confianca,
            recomendacao=(
                "ALERTA: reduzir exposição a equity para mínimo dos guardrails. "
                "Novas entradas apenas com convicção excepcional. "
                "Priorizar proteção de capital."
            ),
        )

    return KillSwitchState(
        ativo=False,
        nivel=0,
        motivo=f"RISK_OFF mas confiança {confianca}% < {KILL_SWITCH_ALERTA_CONFIANCA}% — sinais conflitantes",
        regime=regime,
        confianca=confianca,
        recomendacao="Cautela recomendada — monitorar evolução dos sinais",
    )

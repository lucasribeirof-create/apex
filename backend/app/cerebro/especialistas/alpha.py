"""
APEX Motor — Alpha (Ações com Assimetria / Convicção)

Motor de seleção de ações para a estratégia ALPHA — posições concentradas
em empresas com potencial de retorno acima do mercado.

Filosofia Alpha:
  NÃO é comprar o que está na moda. É encontrar:
  1. Desconto fundamentalista — empresa boa sendo negociada barato vs histórico
  2. Crescimento não precificado — mercado não pagou ainda pelo crescimento futuro
  3. Reversão à média — empresa com fundamentos sólidos em momento adverso temporário
  4. Tese temática — exposição a macro favorável (exportação + dólar, desinflação, crédito)

Score por 4 pilares × 25pts cada (total 0-100):
  - Valuation (25):   P/L + P/VP + EV/EBITDA + DY
  - Rentabilidade (25): ROE + Margem EBITDA + ROIC
  - Saúde (25):        DL/EBITDA + Cobertura juros + FCF
  - Crescimento (25):  Revenue growth + Earnings growth + Momentum/MMs

Red flags (eliminadores automáticos):
  - DL/EBITDA > 4.0 → ELIMINAR
  - Margem líquida negativa → ELIMINAR
  - Receita caindo > 10% → ELIMINAR
  - FCF negativo → ALERTA (penaliza mas não elimina)

Dados extras: 15+ indicadores por sugestão.
"""

import asyncio
import logging
from typing import Optional

import yfinance as yf

from app.cerebro.especialistas import SugestaoMotor
from app.cerebro.especialistas.watchlist import ALPHA_WATCHLIST
from app.cerebro.especialistas import prefetch as _pf

logger = logging.getLogger("apex.motor_alpha")


# ── Ajuste setorial ──────────────────────────────────────────────────────────

def _aplicar_ajuste_setor(ticker: str, score: float, ranking_setorial) -> float:
    """Aplica bonus/penalty ao score baseado no ranking setorial."""
    if not ranking_setorial:
        return score
    from app.core.universe import get_ticker_info
    info = get_ticker_info(ticker)
    setor = info.get("setor", "outro") if info else "outro"
    if setor in getattr(ranking_setorial, "favorecidos", []):
        score += 12
    elif setor in getattr(ranking_setorial, "evitar", []):
        score -= 15
    return max(score, 0.0)

# ── Parâmetros de filtro fundamental ─────────────────────────────────────────
PL_MAXIMO         = 25.0
PVP_MAXIMO        = 4.0
DIVIDA_LIQ_MAX    = 4.0   # Dívida Líquida / EBITDA
_TAXA_IR_BR       = 0.34  # taxa efetiva IR+CSLL Brasil (aprox.)


def _fetch_fundamentals(ticker: str) -> Optional[dict]:
    """Busca dados fundamentais via prefetch cache (ou yfinance direto).
    Retorna dict com 15+ indicadores ou None se dados insuficientes."""
    info = None
    hist = None

    # Tenta prefetch primeiro
    pf = _pf.get(ticker)
    if pf and pf.sucesso and pf.preco > 0 and pf.hist is not None:
        hist = pf.hist
        info = pf.info if pf.info else None

    # Fallback direto
    if info is None or hist is None:
        try:
            from app.data.brapi import _resolve_yf_ticker
            yf_ticker = _resolve_yf_ticker(ticker)
            t = yf.Ticker(yf_ticker)
            info = t.info
            hist = t.history(period="1y", auto_adjust=True)
            if not info or hist.empty:
                return None
        except Exception:
            return None

    try:
        preco = float(hist["Close"].iloc[-1])
        if preco <= 0:
            return None

        # ── Campos básicos ────────────────────────────────────────────
        pl            = info.get("trailingPE")
        p_vp          = info.get("priceToBook")
        receita_ant   = info.get("revenueGrowth")      # fração: 0.15 = 15%
        margem_bruta  = info.get("grossMargins")        # fração
        margem_op     = info.get("operatingMargins")    # fração
        mkt_cap       = info.get("marketCap")
        divida_bruta  = info.get("totalDebt", 0) or 0
        caixa         = info.get("totalCash", 0) or 0
        ebitda        = info.get("ebitda", 0) or 0
        nome          = info.get("shortName") or info.get("longName") or ticker

        # ── Novos indicadores (Phase 3) ───────────────────────────────
        ev            = info.get("enterpriseValue")
        roe           = info.get("returnOnEquity")       # fração
        fcf           = info.get("freeCashflow")
        margem_liq    = info.get("profitMargins")        # fração
        earnings_growth = info.get("earningsGrowth")     # fração
        dy            = info.get("dividendYield")        # fração
        interest_exp  = info.get("interestExpense", 0) or 0
        ebit          = info.get("ebit", 0) or 0
        equity        = info.get("totalStockholderEquity", 0) or 0

        # ── Cálculos derivados ────────────────────────────────────────
        dl = divida_bruta - caixa
        dl_ebitda = (dl / ebitda) if ebitda and ebitda > 0 else None

        # EV/EBITDA
        ev_ebitda = (ev / ebitda) if ev and ebitda and ebitda > 0 else None

        # ROIC = EBIT × (1-IR) / Capital Investido
        net_debt = max(dl, 0)  # não conta caixa líquido como capital negativo
        invested_capital = equity + net_debt
        roic = (ebit * (1 - _TAXA_IR_BR) / invested_capital) if ebit and invested_capital > 0 else None

        # Cobertura de juros = EBITDA / |juros|
        cobertura_juros = (ebitda / abs(interest_exp)) if interest_exp and ebitda else None

        # Crescimento receita (yf retorna fração: 0.15 = 15%)
        cresc_receita_pct = float(receita_ant) * 100 if receita_ant is not None else None
        cresc_lucro_pct   = float(earnings_growth) * 100 if earnings_growth is not None else None

        # Preço nas médias (tendência)
        close = hist["Close"]
        mm50  = float(close.rolling(50, min_periods=25).mean().iloc[-1]) if len(close) >= 25 else None
        mm200 = float(close.rolling(200, min_periods=50).mean().iloc[-1]) if len(close) >= 50 else None

        # Momentum 6 meses
        preco_6m  = float(close.iloc[-126]) if len(close) >= 126 else float(close.iloc[0])
        mom_6m    = (preco - preco_6m) / preco_6m * 100

        return {
            "ticker":          ticker,
            "nome":            str(nome),
            "preco":           round(preco, 2),
            # Valuation
            "pl":              round(float(pl), 1) if pl else None,
            "p_vp":            round(float(p_vp), 2) if p_vp else None,
            "ev_ebitda":       round(float(ev_ebitda), 1) if ev_ebitda else None,
            "dy":              round(float(dy) * 100, 2) if dy else None,
            # Rentabilidade
            "roe":             round(float(roe) * 100, 1) if roe else None,
            "roic":            round(float(roic) * 100, 1) if roic else None,
            "margem_op":       round(float(margem_op) * 100, 1) if margem_op else None,
            "margem_bruta":    round(float(margem_bruta) * 100, 1) if margem_bruta else None,
            # Saúde
            "dl_ebitda":       round(float(dl_ebitda), 2) if dl_ebitda is not None else None,
            "cobertura_juros": round(float(cobertura_juros), 1) if cobertura_juros else None,
            "fcf":             fcf,
            "margem_liq":      round(float(margem_liq) * 100, 1) if margem_liq else None,
            # Crescimento
            "cresc_receita":   round(cresc_receita_pct, 1) if cresc_receita_pct is not None else None,
            "cresc_lucro":     round(cresc_lucro_pct, 1) if cresc_lucro_pct is not None else None,
            # Técnico
            "mkt_cap":         mkt_cap,
            "momentum_6m":     round(mom_6m, 1),
            "mm50":            round(mm50, 2) if mm50 else None,
            "mm200":           round(mm200, 2) if mm200 else None,
            "acima_mm50":      preco > mm50 if mm50 else None,
            "acima_mm200":     preco > mm200 if mm200 else None,
        }
    except Exception:
        return None


# ── Red Flags (eliminadores automáticos) ─────────────────────────────────────

def _check_red_flags(d: dict) -> list[str]:
    """Verifica red flags eliminatórias. Retorna lista de flags (vazia = OK)."""
    flags: list[str] = []

    dl = d.get("dl_ebitda")
    if dl is not None and dl > DIVIDA_LIQ_MAX:
        flags.append(f"ELIMINAR: DL/EBITDA {dl:.1f}× > {DIVIDA_LIQ_MAX}")

    ml = d.get("margem_liq")
    if ml is not None and ml < 0:
        flags.append(f"ELIMINAR: Margem líquida negativa ({ml:.1f}%)")

    cr = d.get("cresc_receita")
    if cr is not None and cr < -10:
        flags.append(f"ELIMINAR: Receita caindo {cr:.1f}%")

    fcf = d.get("fcf")
    if fcf is not None and fcf < 0:
        flags.append(f"ALERTA: FCF negativo (R${fcf / 1e6:,.0f}M)")

    mom = d.get("momentum_6m", 0)
    if mom < -30:
        flags.append(f"ELIMINAR: Queda severa de {mom:.0f}% em 6m")

    return flags


def _is_eliminado(flags: list[str]) -> bool:
    """Retorna True se alguma flag é eliminatória."""
    return any(f.startswith("ELIMINAR") for f in flags)


# ── Scoring por 4 pilares × 25pts ────────────────────────────────────────────

def _score_valuation(d: dict) -> float:
    """Pilar Valuation: P/L + P/VP + EV/EBITDA + DY (máx 25pts)."""
    pts = 0.0

    # P/L (0-8 pts)
    pl = d.get("pl")
    if pl:
        if   pl < 8:   pts += 8
        elif pl < 12:  pts += 6
        elif pl < 16:  pts += 4
        elif pl < 20:  pts += 2
        elif pl <= 25: pts += 1

    # P/VP (0-6 pts)
    pvp = d.get("p_vp")
    if pvp:
        if   pvp < 1.0: pts += 6
        elif pvp < 1.5: pts += 5
        elif pvp < 2.0: pts += 3
        elif pvp < 3.0: pts += 1

    # EV/EBITDA (0-6 pts)
    ev = d.get("ev_ebitda")
    if ev:
        if   ev < 5:   pts += 6
        elif ev < 8:   pts += 5
        elif ev < 10:  pts += 3
        elif ev < 13:  pts += 1

    # DY (0-5 pts)
    dy = d.get("dy")
    if dy:
        if   dy >= 8:  pts += 5
        elif dy >= 5:  pts += 4
        elif dy >= 3:  pts += 2
        elif dy >= 1:  pts += 1

    return min(pts, 25.0)


def _score_rentabilidade(d: dict) -> float:
    """Pilar Rentabilidade: ROE + Margem EBITDA + ROIC (máx 25pts)."""
    pts = 0.0

    # ROE (0-10 pts)
    roe = d.get("roe")
    if roe:
        if   roe >= 25: pts += 10
        elif roe >= 18: pts += 8
        elif roe >= 12: pts += 6
        elif roe >= 8:  pts += 4
        elif roe >= 0:  pts += 1

    # Margem operacional como proxy de margem EBITDA (0-8 pts)
    marg = d.get("margem_op")
    if marg:
        if   marg >= 30: pts += 8
        elif marg >= 20: pts += 6
        elif marg >= 12: pts += 4
        elif marg >= 5:  pts += 2

    # ROIC (0-7 pts)
    roic = d.get("roic")
    if roic:
        if   roic >= 20: pts += 7
        elif roic >= 15: pts += 5
        elif roic >= 10: pts += 3
        elif roic >= 5:  pts += 1

    return min(pts, 25.0)


def _score_saude(d: dict) -> float:
    """Pilar Saúde: DL/EBITDA + Cobertura juros + FCF (máx 25pts)."""
    pts = 0.0

    # DL/EBITDA (0-10 pts) — menor = melhor
    dl = d.get("dl_ebitda")
    if dl is not None:
        if   dl < 0:   pts += 10   # caixa líquido
        elif dl < 1.0: pts += 8
        elif dl < 2.0: pts += 6
        elif dl < 3.0: pts += 3
        elif dl <= 4.0: pts += 1

    # Cobertura de juros (0-8 pts) — maior = melhor
    cob = d.get("cobertura_juros")
    if cob:
        if   cob >= 10: pts += 8
        elif cob >= 5:  pts += 6
        elif cob >= 3:  pts += 4
        elif cob >= 1.5: pts += 2

    # FCF (0-7 pts) — positivo e crescente
    fcf = d.get("fcf")
    if fcf is not None:
        if   fcf > 1e9:  pts += 7    # > R$1B
        elif fcf > 500e6: pts += 5
        elif fcf > 100e6: pts += 3
        elif fcf > 0:     pts += 1

    return min(pts, 25.0)


def _score_crescimento(d: dict) -> float:
    """Pilar Crescimento: Revenue growth + Earnings growth + Momentum/MMs (máx 25pts)."""
    pts = 0.0

    # Crescimento receita (0-10 pts)
    cr = d.get("cresc_receita")
    if cr is not None:
        if   cr >= 20: pts += 10
        elif cr >= 10: pts += 8
        elif cr >= 5:  pts += 5
        elif cr >= 0:  pts += 2

    # Crescimento lucro (0-8 pts)
    cl = d.get("cresc_lucro")
    if cl is not None:
        if   cl >= 30: pts += 8
        elif cl >= 15: pts += 6
        elif cl >= 5:  pts += 4
        elif cl >= 0:  pts += 2

    # Momentum 6m + tendência MMs (0-7 pts)
    mom = d.get("momentum_6m", 0)
    if   mom >= 20: pts += 3
    elif mom >= 5:  pts += 2
    elif mom >= 0:  pts += 1

    if d.get("acima_mm200"):
        pts += 2
    if d.get("acima_mm50"):
        pts += 2

    return min(pts, 25.0)


def _score_alpha(d: dict) -> tuple[float, dict]:
    """Pontua 4 pilares × 25pts = 0-100. Retorna (score_total, breakdown)."""
    v = _score_valuation(d)
    r = _score_rentabilidade(d)
    s = _score_saude(d)
    c = _score_crescimento(d)
    total = v + r + s + c
    breakdown = {
        "valuation": round(v, 1),
        "rentabilidade": round(r, 1),
        "saude": round(s, 1),
        "crescimento": round(c, 1),
    }
    return total, breakdown


def _justificativa_alpha(d: dict, upside_est: float, breakdown: dict, red_flags: list[str]) -> str:
    partes = []

    # Tese principal
    pl  = d.get("pl")
    pvp = d.get("p_vp")
    cr  = d.get("cresc_receita")
    roe = d.get("roe")

    if pl and pl < 12:
        partes.append(
            f"{d['ticker']} negociado a {pl}× lucros — desconto significativo vs "
            f"múltiplos históricos do setor, criando assimetria favorável"
        )
    elif cr and cr >= 15:
        partes.append(
            f"{d['ticker']} com crescimento de receita de {cr:.0f}% no último ano — "
            f"expansão não totalmente precificada pelo mercado"
        )
    elif pvp and pvp < 1.0:
        partes.append(
            f"{d['ticker']} a P/VP {pvp:.2f} — cotas abaixo do valor contábil, "
            f"margem de segurança estrutural"
        )
    elif roe and roe >= 20:
        partes.append(
            f"{d['ticker']} com ROE de {roe:.0f}% — rentabilidade superior sobre patrimônio"
        )
    else:
        partes.append(f"{d['ticker']} com fundamentos sólidos e potencial de rerating")

    # 4 pilares
    pilares_txt = (
        f"4 pilares: Valuation {breakdown['valuation']:.0f}/25 | "
        f"Rentab. {breakdown['rentabilidade']:.0f}/25 | "
        f"Saúde {breakdown['saude']:.0f}/25 | "
        f"Cresc. {breakdown['crescimento']:.0f}/25"
    )
    partes.append(pilares_txt)

    # Dados quantitativos principais
    metricas = []
    if pl:    metricas.append(f"P/L {pl:.1f}×")
    if pvp:   metricas.append(f"P/VP {pvp:.2f}")
    ev = d.get("ev_ebitda")
    if ev:    metricas.append(f"EV/EBITDA {ev:.1f}×")
    if roe:   metricas.append(f"ROE {roe:.0f}%")
    roic = d.get("roic")
    if roic:  metricas.append(f"ROIC {roic:.0f}%")
    dl = d.get("dl_ebitda")
    if dl is not None:
        metricas.append(f"DL/EBITDA {dl:.1f}×" if dl >= 0 else "caixa líquido")
    if metricas:
        partes.append(f"métricas: {' | '.join(metricas)}")

    # Upside estimado
    if upside_est > 0:
        partes.append(f"upside estimado de {upside_est:.0f}% em cenário base")

    # Red flags (alertas, não eliminatórios — os eliminatórios já filtraram)
    alertas = [f for f in red_flags if f.startswith("ALERTA")]
    if alertas:
        partes.append("⚠ " + "; ".join(alertas))

    return ". ".join(partes) + "."


async def rodar(
    capital: float,
    watchlist: Optional[list[str]] = None,
    n_ativos: int = 3,
    excluir_tickers: list[str] | None = None,
    ranking_setorial: object | None = None,
    patrimonio_total: float = 0.0,
    regime: str = "NEUTRO",
    cb_modifier: float = 1.0,
    macro_context: object | None = None,
) -> list[SugestaoMotor]:
    """
    Seleciona ações com maior potencial de assimetria usando IA + dados fundamentais.
    Dados reais (4 pilares × 25pts) → Red flags → IA seleciona com visão macro.
    Fallback: top-N por score algorítmico se IA falhar.
    """
    if capital < 2_000:
        return []

    _excluir = set(t.upper() for t in (excluir_tickers or []))
    tickers  = [t for t in (watchlist or ALPHA_WATCHLIST) if t.upper() not in _excluir]
    n_ativos = min(n_ativos, 5)

    # Busca fundamentais em paralelo
    tarefas   = [asyncio.to_thread(_fetch_fundamentals, t) for t in tickers]
    resultados = await asyncio.gather(*tarefas, return_exceptions=True)

    candidatos = []
    for r in resultados:
        if not isinstance(r, dict) or r is None:
            continue

        # Red flags — eliminadores automáticos
        flags = _check_red_flags(r)
        if _is_eliminado(flags):
            continue

        score, breakdown = _score_alpha(r)
        if score > 0:
            score = _aplicar_ajuste_setor(r["ticker"], score, ranking_setorial)
            candidatos.append({**r, "score": score, "_breakdown": breakdown, "_red_flags": flags})

    candidatos.sort(key=lambda x: x["score"], reverse=True)

    if not candidatos:
        return []

    # ── Fallback algorítmico (top-N por score) ───────────────────────────
    fallback = _construir_fallback_alpha(candidatos, n_ativos, capital, patrimonio_total, regime, cb_modifier)

    # ── Enriquecer candidatos para IA ─────────────────────────────────────
    candidatos_enriched = []
    for c in candidatos:
        candidatos_enriched.append({
            "ticker": c["ticker"],
            "nome": c["nome"],
            "tipo": "ACAO",
            "preco": c["preco"],
            "pl": c.get("pl"),
            "p_vp": c.get("p_vp"),
            "ev_ebitda": c.get("ev_ebitda"),
            "dy_pct": c.get("dy"),
            "roe_pct": c.get("roe"),
            "roic_pct": c.get("roic"),
            "margem_op_pct": c.get("margem_op"),
            "dl_ebitda": c.get("dl_ebitda"),
            "cresc_receita_pct": c.get("cresc_receita"),
            "cresc_lucro_pct": c.get("cresc_lucro"),
            "momentum_6m": c.get("momentum_6m"),
            "acima_mm200": c.get("acima_mm200"),
            "score_algoritmico": round(c["score"], 1),
            "pilares": c["_breakdown"],
            "red_flags": c["_red_flags"],
            "setor": _get_setor_ticker(c["ticker"]),
            "dados_extras": {
                "pl": c.get("pl"),
                "p_vp": c.get("p_vp"),
                "ev_ebitda": c.get("ev_ebitda"),
                "dy_pct": c.get("dy"),
                "roe_pct": c.get("roe"),
                "roic_pct": c.get("roic"),
                "pilares": c["_breakdown"],
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
        modulo="alpha",
        candidatos_enriched=candidatos_enriched,
        macro_resumo=macro_resumo,
        estrategia="ALPHA",
        capital=capital,
        motor_system_prompt=build_motor_prompt("alpha"),
        n_ativos=n_ativos,
        max_tokens=3000,
        fallback_candidatos=fallback,
    )

    return resultado if resultado else fallback


def _construir_fallback_alpha(
    candidatos: list[dict], n_ativos: int, capital: float,
    patrimonio_total: float, regime: str, cb_modifier: float,
) -> list[SugestaoMotor]:
    """Fallback algorítmico: top-N por score com sizing ATR."""
    selecionados = candidatos[:n_ativos]
    if not selecionados:
        return []

    # Phase 5: Hold classification + Watchlist candidates
    from app.cerebro.hold import avaliar_hold, gerar_watchlist_candidates
    _hold_map: dict[str, object] = {}
    for d in selecionados:
        hc = avaliar_hold(d, d["score"], d.get("_red_flags", []))
        _hold_map[d["ticker"]] = hc

    _sel_tickers = {d["ticker"] for d in selecionados}
    _watchlist_cands = gerar_watchlist_candidates(candidatos, _sel_tickers, n_max=5)

    # ATR-based position sizing (Phase 4)
    from app.cerebro.sizing import sizing_lote, ATR_STOP_MULT_ALPHA
    _patrim = patrimonio_total if patrimonio_total > 0 else capital
    sizing_results = sizing_lote(
        selecionados, capital, _patrim,
        regime=regime, atr_mult=ATR_STOP_MULT_ALPHA, cb_modifier=cb_modifier,
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

        pl = d.get("pl")
        upside_est = round((15.0 / pl - 1) * 100, 1) if pl and 0 < pl < 15 else 0.0

        breakdown = d["_breakdown"]
        flags = d["_red_flags"]
        hold_info = _hold_map.get(d["ticker"])
        classificacao = "HOLD" if (hold_info and hold_info.elegivel) else "TRADE"

        saida.append(SugestaoMotor(
            modulo="alpha",
            ticker=d["ticker"],
            nome=d["nome"],
            tipo="ACAO",
            quantidade=float(qtd),
            preco_atual=preco,
            valor_total=valor,
            justificativa=_justificativa_alpha(d, upside_est, breakdown, flags),
            score=d["score"],
            dados_extras={
                "pl": d.get("pl"), "p_vp": d.get("p_vp"),
                "ev_ebitda": d.get("ev_ebitda"), "dy_pct": d.get("dy"),
                "roe_pct": d.get("roe"), "roic_pct": d.get("roic"),
                "margem_operacional": d.get("margem_op"),
                "margem_bruta": d.get("margem_bruta"),
                "margem_liquida": d.get("margem_liq"),
                "dl_ebitda": d.get("dl_ebitda"),
                "cobertura_juros": d.get("cobertura_juros"),
                "fcf": d.get("fcf"),
                "crescimento_receita": d.get("cresc_receita"),
                "crescimento_lucro": d.get("cresc_lucro"),
                "momentum_6m": d.get("momentum_6m"),
                "acima_mm200": d.get("acima_mm200"),
                "pilares": breakdown,
                "upside_estimado_pct": upside_est,
                "red_flags": flags,
                "setor": _get_setor_ticker(d["ticker"]),
                "atr14": sz.atr14 if sz else None,
                "stop_atr": sz.stop if sz else None,
                "risco_pct_patrimonio": sz.risco_pct_patrimonio if sz else None,
                "sizing_method": "ATR" if (sz and sz.atr14 > 0) else "equal_weight",
                "classificacao": classificacao,
                "hold_elegivel": hold_info.elegivel if hold_info else False,
                "hold_motivo": hold_info.motivo if hold_info else "",
            },
        ))

    if saida and _watchlist_cands:
        saida[0].dados_extras["_watchlist_candidates"] = [
            {
                "ticker": w.ticker, "nome": w.nome, "score": w.score,
                "setor": w.setor, "trigger_tipo": w.trigger_tipo,
                "trigger_descricao": w.trigger_descricao, "trigger_valor": w.trigger_valor,
            }
            for w in _watchlist_cands
        ]

    return saida


def _get_setor_ticker(ticker: str) -> str:
    """Retorna o setor canônico de um ticker."""
    from app.core.universe import get_ticker_info
    info = get_ticker_info(ticker)
    return info.get("setor", "outro") if info else "outro"

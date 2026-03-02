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

Critérios de seleção (yfinance fundamentals):
  - P/L < 20 (ou setor específico com P/L justificável)
  - P/VP < 3.0
  - Crescimento receita 1 ano > 0 (empresa ainda crescendo)
  - Margem EBITDA sólida para o setor
  - Dívida controlada (D/L < 3.0 para não-financeiras)
  - Stock em tendência neutra a positiva (não em queda livre)

Dados extras por sugestão:
  - pl: P/L atual
  - p_vp: P/VP atual
  - crescimento_receita: % crescimento receita último ano
  - margem_ebitda: margem EBITDA estimada
  - tese: texto da tese de investimento (gerada pelo motor)
  - upside_estimado: % upside estimado vs preço justo
"""

import asyncio
from typing import Optional

import yfinance as yf

from app.cerebro.especialistas import SugestaoMotor
from app.cerebro.especialistas.watchlist import ALPHA_WATCHLIST
from app.cerebro.especialistas import prefetch as _pf

# ── Parâmetros de filtro fundamental ─────────────────────────────────────────
PL_MAXIMO         = 25.0
PVP_MAXIMO        = 4.0
DIVIDA_LIQ_MAX    = 4.0   # Dívida Líquida / EBITDA


def _fetch_fundamentals(ticker: str) -> Optional[dict]:
    """Busca dados fundamentais via prefetch cache (ou yfinance direto)."""
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
            t = yf.Ticker(ticker + ".SA")
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

        # Extrair campos com fallbacks
        pl            = info.get("trailingPE")
        p_vp          = info.get("priceToBook")
        receita       = info.get("totalRevenue")
        receita_ant   = info.get("revenueGrowth")  # yf retorna como fraction
        margem_bruta  = info.get("grossMargins")
        margem_op     = info.get("operatingMargins")
        mkt_cap       = info.get("marketCap")
        divida_bruta  = info.get("totalDebt", 0) or 0
        caixa         = info.get("totalCash", 0) or 0
        ebitda        = info.get("ebitda", 0) or 0
        nome          = info.get("shortName") or info.get("longName") or ticker

        # Dívida Líquida / EBITDA
        dl = divida_bruta - caixa
        dl_ebitda = (dl / ebitda) if ebitda and ebitda > 0 else None

        # Crescimento receita (yf retorna fração: 0.15 = 15%)
        cresc_receita_pct = float(receita_ant) * 100 if receita_ant is not None else None

        # Preço nas médias (tendência)
        close = hist["Close"]
        mm50  = float(close.rolling(50, min_periods=25).mean().iloc[-1]) if len(close) >= 25 else None
        mm200 = float(close.rolling(200, min_periods=50).mean().iloc[-1]) if len(close) >= 50 else None

        # Momentum 6 meses (para evitar ação em queda libre)
        preco_6m  = float(close.iloc[-126]) if len(close) >= 126 else float(close.iloc[0])
        mom_6m    = (preco - preco_6m) / preco_6m * 100

        return {
            "ticker":          ticker,
            "nome":            str(nome),
            "preco":           round(preco, 2),
            "pl":              round(float(pl), 1) if pl else None,
            "p_vp":            round(float(p_vp), 2) if p_vp else None,
            "cresc_receita":   round(cresc_receita_pct, 1) if cresc_receita_pct is not None else None,
            "margem_bruta":    round(float(margem_bruta) * 100, 1) if margem_bruta else None,
            "margem_op":       round(float(margem_op) * 100, 1) if margem_op else None,
            "mkt_cap":         mkt_cap,
            "dl_ebitda":       round(float(dl_ebitda), 2) if dl_ebitda is not None else None,
            "mm50":            round(mm50, 2) if mm50 else None,
            "mm200":           round(mm200, 2) if mm200 else None,
            "momentum_6m":     round(mom_6m, 1),
            "acima_mm50":      preco > mm50 if mm50 else None,
            "acima_mm200":     preco > mm200 if mm200 else None,
        }
    except Exception:
        return None


def _score_alpha(d: dict) -> float:
    """Pontua o ativo por qualidade fundamentalista e potencial de assimetria."""
    score = 0.0

    # P/L (0-25 pts) — desconto vs média histórica
    pl = d.get("pl")
    if pl:
        if   pl < 8:   score += 25   # muito barato
        elif pl < 12:  score += 20
        elif pl < 16:  score += 15
        elif pl < 20:  score += 8
        elif pl <= 25: score += 3
        else:          return 0.0    # caro demais para alpha

    # P/VP (0-20 pts)
    pvp = d.get("p_vp")
    if pvp:
        if   pvp < 1.0:  score += 20   # abaixo do valor patrimonial
        elif pvp < 1.5:  score += 15
        elif pvp < 2.0:  score += 10
        elif pvp < 3.0:  score += 5
        else:            score += 0

    # Crescimento de receita (0-20 pts)
    cr = d.get("cresc_receita")
    if cr is not None:
        if   cr >= 20: score += 20
        elif cr >= 10: score += 15
        elif cr >=  5: score += 10
        elif cr >=  0: score += 5
        else:          score -= 5   # receita caindo é penalidade

    # Alavancagem (0-15 pts)
    dl = d.get("dl_ebitda")
    if dl is not None:
        if   dl < 0:   score += 15   # caixa líquido — excelente
        elif dl < 1.0: score += 12
        elif dl < 2.0: score += 8
        elif dl < 3.0: score += 4
        elif dl > 4.0: score -= 10   # muito alavancado

    # Margem operacional (0-10 pts)
    marg = d.get("margem_op")
    if marg:
        if   marg >= 25: score += 10
        elif marg >= 15: score += 7
        elif marg >= 8:  score += 4
        elif marg >= 0:  score += 1
        else:            score -= 5  # prejuízo operacional

    # Não em queda livre (momentum 6m)
    mom = d.get("momentum_6m", 0)
    if   mom < -30: return 0.0    # queda severa = foge do filtro
    elif mom < -15: score -= 10
    elif mom >= 0:  score += 5

    # Tendência (posição nas médias)
    if d.get("acima_mm200"):
        score += 5
    if d.get("acima_mm50"):
        score += 3

    return max(score, 0.0)


def _justificativa_alpha(d: dict, upside_est: float) -> str:
    partes = []

    # Tese principal
    pl  = d.get("pl")
    pvp = d.get("p_vp")
    cr  = d.get("cresc_receita")

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
    else:
        partes.append(f"{d['ticker']} com fundamentos sólidos e potencial de rerating")

    # Dados quantitativos
    metricas = []
    if pl:    metricas.append(f"P/L {pl:.1f}×")
    if pvp:   metricas.append(f"P/VP {pvp:.2f}")
    if cr is not None: metricas.append(f"receita +{cr:.0f}%/ano")
    dl = d.get("dl_ebitda")
    if dl is not None:
        metricas.append(f"DL/EBITDA {dl:.1f}×" if dl >= 0 else "caixa líquido")
    if metricas:
        partes.append(f"métricas: {' | '.join(metricas)}")

    # Upside estimado
    if upside_est > 0:
        partes.append(f"upside estimado de {upside_est:.0f}% em cenário base")

    # Risco
    dl = d.get("dl_ebitda", 0) or 0
    if dl > 3.0:
        partes.append(f"⚠ alavancagem elevada (DL/EBITDA {dl:.1f}×) — position size conservador")

    return ". ".join(partes) + "."


async def rodar(
    capital: float,
    watchlist: Optional[list[str]] = None,
    n_ativos: int = 3,
    excluir_tickers: list[str] | None = None,
) -> list[SugestaoMotor]:
    """
    Seleciona ações com maior potencial de assimetria na watchlist Alpha.

    Args:
        capital:          Capital em R$ disponível para o módulo Alpha.
        watchlist:        Lista de tickers candidatos (default: ALPHA_WATCHLIST).
        n_ativos:         Número de posições (concentração = convicção).
        excluir_tickers:  Tickers já na carteira — não serão sugeridos.

    Returns:
        Lista de SugestaoMotor com as melhores teses de alpha.
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
        score = _score_alpha(r)
        if score > 0:
            candidatos.append({**r, "score": score})

    candidatos.sort(key=lambda x: x["score"], reverse=True)
    selecionados = candidatos[:n_ativos]

    if not selecionados:
        return []

    capital_por_ativo = capital / len(selecionados)
    saida: list[SugestaoMotor] = []

    for d in selecionados:
        preco = d["preco"]
        qtd   = max(1, int(capital_por_ativo / preco))
        valor = round(qtd * preco, 2)

        # Upside estimado via múltiplo alvo (P/L alvo = 15× para value plays)
        pl = d.get("pl")
        upside_est = 0.0
        if pl and 0 < pl < 15:
            upside_est = round((15.0 / pl - 1) * 100, 1)

        saida.append(SugestaoMotor(
            modulo="alpha",
            ticker=d["ticker"],
            nome=d["nome"],
            tipo="ACAO",
            quantidade=float(qtd),
            preco_atual=preco,
            valor_total=valor,
            justificativa=_justificativa_alpha(d, upside_est),
            score=d["score"],
            dados_extras={
                "pl":               d.get("pl"),
                "p_vp":             d.get("p_vp"),
                "crescimento_receita": d.get("cresc_receita"),
                "margem_operacional":  d.get("margem_op"),
                "dl_ebitda":        d.get("dl_ebitda"),
                "momentum_6m":      d.get("momentum_6m"),
                "upside_estimado_pct": upside_est,
                "acima_mm200":      d.get("acima_mm200"),
            },
        ))

    return saida

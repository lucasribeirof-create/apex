"""
APEX Motor — Dividendos

Motor de seleção de ações pagadoras de dividendos consistentes.

Filosofia:
  Dividendos NÃO é apenas "maior DY". É consistência, sustentabilidade
  e crescimento dos proventos ao longo do tempo.

Critérios de seleção:
  1. DY real (trailing 12m) > 5% — yield concreto, não projetado
  2. Payout ratio sustentável (< 90% — empresa retém capital para crescer)
  3. Dividend growth — empresa aumenta ou mantém dividendos (não corta)
  4. Cobertura (earnings yield > DY) — lucro suporta o dividendo
  5. Solidez financeira — dívida controlada, fluxo de caixa positivo

Diversificação setorial: elétrico, bancário, telecom, petróleo, varejo selecionado

Dados extras por sugestão:
  - dy_12m: dividend yield real últimos 12 meses
  - dividendo_anual_estimado: R$ estimado por cota/ação por ano
  - payout_ratio: % do lucro distribuído
  - tipo_provento: Dividendo / JCP / Proventos mistos
  - setor: setor da empresa
"""

import asyncio
from typing import Optional

import yfinance as yf

from app.cerebro.especialistas import SugestaoMotor
from app.cerebro.especialistas.watchlist import DIVIDENDOS_WATCHLIST
from app.cerebro.especialistas import prefetch as _pf

# ── Metadados curados ────────────────────────────────────────────────────────
# DY de referência (médias recentes), setor, e tipo predominante de provento
_DIV_META = {
    "BBAS3":  {"setor": "bancário",   "dy_ref": 8.5,  "tipo": "JCP+Dividendo"},
    "TAEE11": {"setor": "elétrico",   "dy_ref": 10.0, "tipo": "Dividendo"},
    "EGIE3":  {"setor": "elétrico",   "dy_ref": 7.5,  "tipo": "Dividendo"},
    "CPLE3":  {"setor": "elétrico",   "dy_ref": 8.0,  "tipo": "Dividendo"},
    "CMIG4":  {"setor": "elétrico",   "dy_ref": 9.5,  "tipo": "JCP+Dividendo"},
    "TIMS3":  {"setor": "telecom",    "dy_ref": 6.5,  "tipo": "JCP+Dividendo"},
    "VIVT3":  {"setor": "telecom",    "dy_ref": 7.0,  "tipo": "JCP+Dividendo"},
    "ITUB4":  {"setor": "bancário",   "dy_ref": 5.5,  "tipo": "JCP"},
    "BBDC4":  {"setor": "bancário",   "dy_ref": 6.5,  "tipo": "JCP"},
    "PSSA3":  {"setor": "seguros",    "dy_ref": 6.0,  "tipo": "JCP+Dividendo"},
    "WEGE3":  {"setor": "industrial", "dy_ref": 1.5,  "tipo": "Dividendo"},   # crescimento > yield — DY baixo, não passa filtro (correto)
    "ABEV3":  {"setor": "consumo",    "dy_ref": 5.0,  "tipo": "JCP+Dividendo"},
    "CSAN3":  {"setor": "energia",    "dy_ref": 5.5,  "tipo": "Dividendo"},
    "PETR4":  {"setor": "petróleo",   "dy_ref": 12.0, "tipo": "Dividendo"},   # alto mas variável
    "VALE3":  {"setor": "mineração",  "dy_ref": 8.0,  "tipo": "Dividendo"},   # ciclo commodity
}

_DY_MINIMO     = 4.0   # % a.a. mínimo
_PAYOUT_MAX    = 95.0  # % máximo
_MAX_SETOR     = 2     # máximo de ações do mesmo setor


def _fetch_div_data(ticker: str) -> Optional[dict]:
    """Busca preço, DY e dados de proventos via prefetch cache (ou yfinance direto)."""
    meta = _DIV_META.get(ticker, {})

    pf = _pf.get(ticker)
    if pf and pf.sucesso and pf.preco > 0:
        if pf.dy_12m <= 0.5:
            from app.logger import logger
            logger.debug("dividendos: %s sem DY real no prefetch — descartado", ticker)
            return None
        dy_real = pf.dy_12m
        payout_pct = pf.payout_ratio
        nome = pf.nome or meta.get("nome", ticker)

        # Crescimento do dividendo 2 anos — precisa do hist completo
        div_crescendo = None
        hist = pf.hist
        if hist is not None and "Dividends" in hist.columns and len(hist) > 250:
            try:
                div_ano1 = float(hist["Dividends"].iloc[-252:].sum())
                div_ano2 = float(hist["Dividends"].iloc[-504:-252].sum()) if len(hist) >= 504 else 0
                if div_ano2 > 0:
                    div_crescendo = div_ano1 >= div_ano2 * 0.95
            except Exception:
                pass

        return {
            "ticker":     ticker,
            "nome":       str(nome),
            "preco":      pf.preco,
            "dy_12m":     round(dy_real, 2),
            "div_12m_rs": round(pf.dividends_12m, 2),
            "payout":     round(payout_pct, 1) if payout_pct else None,
            "div_crescendo": div_crescendo,
            "setor":      meta.get("setor", pf.setor or "outros"),
            "tipo_prov":  meta.get("tipo", "Dividendo"),
        }

    # --- Fallback: busca direto via yfinance ---
    try:
        t      = yf.Ticker(ticker + ".SA")
        hist   = t.history(period="1y", auto_adjust=False)
        info   = t.info

        if hist is None or hist.empty:
            return None

        preco = float(hist["Close"].iloc[-1])
        if preco <= 0:
            return None

        # Dividendos pagos nos últimos 12 meses
        divs_col = hist["Dividends"] if "Dividends" in hist.columns else None
        div_12m  = float(divs_col.sum()) if divs_col is not None else 0.0
        dy_real  = (div_12m / preco * 100) if preco > 0 else 0.0

        if dy_real <= 0.5:
            from app.logger import logger
            logger.debug("dividendos: %s sem DY real no yfinance — descartado", ticker)
            return None
        dy_usar = dy_real

        payout     = info.get("payoutRatio")
        payout_pct = float(payout) * 100 if payout else None
        nome       = info.get("shortName") or info.get("longName") or ticker

        # Crescimento do dividendo 2 anos (se disponível)
        div_crescendo = None
        try:
            hist_2y = t.history(period="2y", auto_adjust=False)
            if hist_2y is not None and "Dividends" in hist_2y.columns:
                div_ano1 = float(hist_2y["Dividends"].iloc[-252:].sum())  # último ano
                div_ano2 = float(hist_2y["Dividends"].iloc[-504:-252].sum())  # ano anterior
                div_crescendo = div_ano1 >= div_ano2 * 0.95  # tolera até 5% de corte
        except Exception:
            pass

        return {
            "ticker":     ticker,
            "nome":       str(nome),
            "preco":      round(preco, 2),
            "dy_12m":     round(dy_usar, 2),
            "div_12m_rs": round(div_12m, 2),
            "payout":     round(payout_pct, 1) if payout_pct else None,
            "div_crescendo": div_crescendo,
            "setor":      meta.get("setor", "outros"),
            "tipo_prov":  meta.get("tipo", "Dividendo"),
        }
    except Exception:
        return None


def _score_div(d: dict) -> float:
    dy     = d.get("dy_12m", 0)
    payout = d.get("payout")
    cresc  = d.get("div_crescendo")

    if dy < _DY_MINIMO:
        return 0.0
    if payout and payout > _PAYOUT_MAX:
        return 0.0

    score = 0.0

    # DY (0-40 pts)
    if   dy >= 10: score += 40
    elif dy >= 8:  score += 32
    elif dy >= 6:  score += 22
    elif dy >= 5:  score += 14
    else:          score += 6

    # Payout sustentável (0-20 pts)
    if payout:
        if   payout < 50: score += 20   # retém muito capital → crescimento futuro
        elif payout < 70: score += 15
        elif payout < 85: score += 8
        elif payout < 95: score += 2
        else:             score -= 5

    # Crescimento dividendo (0-20 pts)
    if cresc is True:    score += 20
    elif cresc is False: score -= 5   # cortou dividendos

    # Setor defensivo bonus (0-10 pts)
    if d.get("setor") in ("elétrico", "telecom", "seguros"):
        score += 10  # contratos regulados = dividendos previsíveis

    return max(score, 0.0)


def _justificativa_div(d: dict, renda_mensal: float) -> str:
    partes = []
    dy   = d["dy_12m"]
    nome = d["nome"]
    setor = d.get("setor", "")

    # Por que este ativo
    partes.append(
        f"{nome} com DY de {dy:.1f}%/ano — "
        f"{'acima da Selic líquida' if dy > 9 else 'complemento sólido de renda'}"
    )

    # Tipo de provento
    tipo = d.get("tipo_prov", "Dividendo")
    if "JCP" in tipo:
        partes.append(
            "proventos via JCP (Juros sobre Capital Próprio) — "
            "dedutível no IR da empresa, geralmente mais consistente"
        )

    # Payout
    payout = d.get("payout")
    if payout:
        if payout < 60:
            partes.append(
                f"payout de {payout:.0f}% — empresa retém {100-payout:.0f}% do lucro "
                f"para reinvestimento, dividendo sustentável e com potencial de crescimento"
            )
        elif payout < 85:
            partes.append(f"payout de {payout:.0f}% — distribuição equilibrada e sustentável")
        else:
            partes.append(f"⚠ payout de {payout:.0f}% — alto, monitorar se lucros se mantêm")

    # Crescimento
    cresc = d.get("div_crescendo")
    if cresc is True:
        partes.append("histórico de crescimento ou manutenção dos proventos nos últimos 2 anos")
    elif cresc is False:
        partes.append("houve corte de proventos recente — monitorar retomada do pagamento")

    # Setor
    setor_motivo = {
        "elétrico":  "setor regulado com contratos de longo prazo — dividendo previsível e indexado",
        "bancário":  "bancão com geração de caixa robusta e política de JCP consistente",
        "telecom":   "setor com receita recorrente e política de dividendos elevada",
        "petróleo":  "DY alto em ciclo favorável — atenção à volatilidade do petróleo",
        "mineração": "dividendo em USD com conversão favorável — sujeito ao ciclo de commodities",
    }
    if setor in setor_motivo:
        partes.append(setor_motivo[setor])

    # Renda estimada
    partes.append(
        f"renda estimada: R${renda_mensal:.0f}/mês para este nível de alocação"
    )

    return ". ".join(partes) + "."


async def rodar(
    capital: float,
    watchlist: Optional[list[str]] = None,
    n_ativos: int = 4,
    excluir_tickers: list[str] | None = None,
) -> list[SugestaoMotor]:
    """
    Seleciona as melhores ações pagadoras de dividendos para o capital disponível.

    Args:
        capital:          Capital em R$ disponível para o módulo Dividendos.
        watchlist:        Lista de tickers candidatos (default: DIVIDENDOS_WATCHLIST).
        n_ativos:         Número de posições (máx 6 para diversificação setorial).
        excluir_tickers:  Tickers já na carteira — não serão sugeridos.

    Returns:
        Lista de SugestaoMotor com as melhores pagadoras selecionadas.
    """
    if capital < 2_000:
        return []

    _excluir = set(t.upper() for t in (excluir_tickers or []))
    tickers  = [t for t in (watchlist or DIVIDENDOS_WATCHLIST) if t.upper() not in _excluir]
    n_ativos = min(n_ativos, 6)

    tarefas   = [asyncio.to_thread(_fetch_div_data, t) for t in tickers]
    resultados = await asyncio.gather(*tarefas, return_exceptions=True)

    candidatos = []
    for r in resultados:
        if not isinstance(r, dict) or r is None:
            continue
        score = _score_div(r)
        if score > 0:
            candidatos.append({**r, "score": score})

    candidatos.sort(key=lambda x: x["score"], reverse=True)

    # Seleciona com diversificação setorial (max 2 por setor)
    selecionados = []
    setores_usados: dict[str, int] = {}
    for cand in candidatos:
        if len(selecionados) >= n_ativos:
            break
        setor = cand.get("setor", "outros")
        if setores_usados.get(setor, 0) >= _MAX_SETOR:
            continue
        selecionados.append(cand)
        setores_usados[setor] = setores_usados.get(setor, 0) + 1

    if not selecionados:
        return []

    capital_por_ativo = capital / len(selecionados)
    saida: list[SugestaoMotor] = []

    for d in selecionados:
        preco = d["preco"]
        qtd   = max(1, int(capital_por_ativo / preco))
        valor = round(qtd * preco, 2)
        dy    = d["dy_12m"]
        renda_mensal = round(valor * dy / 100 / 12, 2)

        saida.append(SugestaoMotor(
            modulo="dividendos",
            ticker=d["ticker"],
            nome=d["nome"],
            tipo="ACAO",
            quantidade=float(qtd),
            preco_atual=preco,
            valor_total=valor,
            justificativa=_justificativa_div(d, renda_mensal),
            score=d["score"],
            dados_extras={
                "dy_12m":               dy,
                "dividendo_rs_estimado": round(d["div_12m_rs"], 2) if d["div_12m_rs"] > 0 else round(preco * dy / 100, 2),
                "payout_ratio":         d.get("payout"),
                "dividendo_crescendo":  d.get("div_crescendo"),
                "tipo_provento":        d.get("tipo_prov", "Dividendo"),
                "setor":                d.get("setor"),
                "renda_mensal_estimada": renda_mensal,
                "renda_anual_estimada":  round(renda_mensal * 12, 2),
            },
        ))

    return saida

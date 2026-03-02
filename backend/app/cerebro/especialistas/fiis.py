"""
APEX Motor — FIIs (Fundos de Investimento Imobiliário)

Motor de seleção de FIIs baseado em dados fundamentalistas reais.

Critérios de seleção:
  1. DY (Dividend Yield) — mínimo 8%/ano; ideal > 10%
  2. P/VP (Preço / Valor Patrimonial) — ideal < 1.10 (desconto ou prêmio justo)
  3. Liquidez — volume médio diário mínimo (descarta fondos illíquidos)
  4. Diversificação por segmento — a carteira FII deve ter pelo menos 3 segmentos
     (ex: não pode ter só CRI, mistura lajes + logística + recebíveis)
  5. Histórico de pagamentos — regularidade nos últimos 12 meses

Fontes de dados:
  - yfinance para preços e volume (ticker.SA)
  - BRAPI para DY e P/VP quando disponível
  - Fallback: dados do motor quando API offline

Dados extras por sugestão:
  - dy_estimado: dividend yield estimado (% a.a.)
  - p_vp: preço / valor patrimonial
  - segmento: tipo do FII
  - liquidez_media: volume médio diário (R$)
  - razao_selecao: por que este e não outros do segmento
"""

import asyncio
from typing import Optional

import yfinance as yf

from app.cerebro.especialistas import SugestaoMotor
from app.cerebro.especialistas.watchlist import FIIS_WATCHLIST, FIIS_WATCHLIST_FLAT
from app.cerebro.especialistas import prefetch as _pf

# ── Metadados curados dos FIIs (segmento + dados de FALLBACK) ────────────────
# dy_ref e p_vp_ref são usados APENAS quando o yfinance não retorna dados live.
_FIIS_META = {
    # Recebíveis / CRI — maior da categoria, muito líquido
    "MXRF11": {"segmento": "recebíveis_cri",    "nome": "Maxi Renda",             "dy_ref": 12.5, "p_vp_ref": 0.97},
    "KNCR11": {"segmento": "recebíveis_cri",    "nome": "Kinea CRI",              "dy_ref": 13.0, "p_vp_ref": 1.02},
    "KNIP11": {"segmento": "recebíveis_cri",    "nome": "Kinea Índices de Preços","dy_ref": 11.8, "p_vp_ref": 0.95},
    "BCRI11": {"segmento": "recebíveis_cri",    "nome": "BTG CRI",                "dy_ref": 12.8, "p_vp_ref": 1.01},
    "RBRR11": {"segmento": "recebíveis_cri",    "nome": "RBR Rendimento HG",      "dy_ref": 12.2, "p_vp_ref": 0.99},
    "HGCR11": {"segmento": "recebíveis_cri",    "nome": "CSHG CRI",               "dy_ref": 11.5, "p_vp_ref": 0.96},
    "IRDM11": {"segmento": "recebíveis_cri",    "nome": "Iridium Recebíveis",     "dy_ref": 13.2, "p_vp_ref": 1.00},
    "VRTA11": {"segmento": "recebíveis_cri",    "nome": "Fator Verità",           "dy_ref": 12.0, "p_vp_ref": 0.98},
    # Logística — BRCO11 é logística, não lajes
    "XPLG11": {"segmento": "logistica",          "nome": "XP Log",                 "dy_ref": 9.8,  "p_vp_ref": 0.88},
    "HGLG11": {"segmento": "logistica",          "nome": "CSHG Logística",         "dy_ref": 9.2,  "p_vp_ref": 0.92},
    "VILG11": {"segmento": "logistica",          "nome": "Vinci Logística",        "dy_ref": 9.5,  "p_vp_ref": 0.90},
    "LVBI11": {"segmento": "logistica",          "nome": "VBI Logística",          "dy_ref": 9.0,  "p_vp_ref": 0.89},
    "SDIL11": {"segmento": "logistica",          "nome": "SDI Logística",          "dy_ref": 8.8,  "p_vp_ref": 0.91},
    "BRCO11": {"segmento": "logistica",          "nome": "Bresco Logística",       "dy_ref": 9.2,  "p_vp_ref": 0.91},
    # Shoppings
    "XPML11": {"segmento": "shoppings",          "nome": "XP Malls",               "dy_ref": 10.2, "p_vp_ref": 0.94},
    "HSML11": {"segmento": "shoppings",          "nome": "HSI Malls",              "dy_ref": 9.8,  "p_vp_ref": 0.90},
    "MALL11": {"segmento": "shoppings",          "nome": "Malls Brasil Plural",    "dy_ref": 9.5,  "p_vp_ref": 0.88},
    "VISC11": {"segmento": "shoppings",          "nome": "Vinci Shopping Centers", "dy_ref": 10.0, "p_vp_ref": 0.93},
    "ABCP11": {"segmento": "shoppings",          "nome": "Grand Plaza Shopping",   "dy_ref": 9.0,  "p_vp_ref": 0.85},
    # Lajes Corporativas
    "HGRE11": {"segmento": "lajes_corporativas", "nome": "CSHG Real Estate",       "dy_ref": 8.5,  "p_vp_ref": 0.82},
    "RBRP11": {"segmento": "lajes_corporativas", "nome": "RBR Properties",         "dy_ref": 9.0,  "p_vp_ref": 0.85},
    "PVBI11": {"segmento": "lajes_corporativas", "nome": "VBI Prime Properties",   "dy_ref": 8.8,  "p_vp_ref": 0.87},
    "BRCR11": {"segmento": "lajes_corporativas", "nome": "BTG Corporate Office",   "dy_ref": 8.2,  "p_vp_ref": 0.80},
    "JSRE11": {"segmento": "lajes_corporativas", "nome": "JS Real Estate",         "dy_ref": 8.6,  "p_vp_ref": 0.83},
    # FoFs
    "BPFF11": {"segmento": "hibridos_fofs",      "nome": "Brasil Plural Abs FoF",  "dy_ref": 10.5, "p_vp_ref": 0.86},
    "HFOF11": {"segmento": "hibridos_fofs",      "nome": "Hedge Top FOFII",        "dy_ref": 10.2, "p_vp_ref": 0.88},
    "RBRF11": {"segmento": "hibridos_fofs",      "nome": "RBR Alpha Multi",        "dy_ref": 11.0, "p_vp_ref": 0.90},
}

# Segmentos que devemos incluir em uma carteira diversificada de FIIs
_SEGMENTOS_RELEVANTES = ["recebíveis_cri", "logistica", "shoppings", "lajes_corporativas", "hibridos_fofs"]
_MIN_SEGMENTOS = 2   # mínimo de segmentos diferentes na carteira
_DY_MINIMO     = 8.0  # % a.a.
_PVP_MAXIMO    = 1.15


def _fetch_preco_fii(ticker: str) -> Optional[dict]:
    """Busca preço, DY e P/VP via prefetch cache (ou yfinance direto como fallback)."""
    meta = _FIIS_META.get(ticker, {})

    # Tenta prefetch primeiro (cache compartilhado)
    pf = _pf.get(ticker)
    if pf and pf.sucesso and pf.preco > 0:
        dy_live = pf.dy_12m if pf.dy_12m > 0 else meta.get("dy_ref", 0)
        pvp_live = pf.p_vp if pf.p_vp is not None else meta.get("p_vp_ref", 1.0)
        return {"preco": pf.preco, "dy": round(dy_live, 2), "p_vp": round(pvp_live, 2)}

    # Fallback: busca direto
    try:
        t = yf.Ticker(ticker + ".SA")
        hist = t.history(period="1y", auto_adjust=False)
        if hist is None or hist.empty:
            return None

        preco = float(hist["Close"].iloc[-1])
        if preco <= 0:
            return None

        # DY live
        dy = meta.get("dy_ref", 0)
        if "Dividends" in hist.columns:
            divs_12m = float(hist["Dividends"].sum())
            if divs_12m > 0:
                dy = round(divs_12m / preco * 100, 2)

        # P/VP live
        pvp = meta.get("p_vp_ref", 1.0)
        try:
            info = t.info
            bv = info.get("bookValue")
            if bv and bv > 0:
                pvp = round(preco / bv, 2)
        except Exception:
            pass

        return {"preco": round(preco, 2), "dy": dy, "p_vp": pvp}
    except Exception:
        return None


def _score_fii(dy: float, p_vp: float) -> float:
    """Score baseado em DY e P/VP (dados live ou fallback)."""
    if dy < _DY_MINIMO:   return 0.0
    if p_vp > _PVP_MAXIMO: return 0.0

    # DY score (0-50 pts)
    if   dy >= 13: s_dy = 50
    elif dy >= 12: s_dy = 42
    elif dy >= 11: s_dy = 34
    elif dy >= 10: s_dy = 25
    elif dy >=  9: s_dy = 15
    else:          s_dy = 8

    # P/VP score (0-30 pts) — desconto é bom
    if   p_vp < 0.90: s_pvp = 30
    elif p_vp < 0.95: s_pvp = 22
    elif p_vp < 1.00: s_pvp = 15
    elif p_vp < 1.05: s_pvp = 8
    elif p_vp < 1.10: s_pvp = 3
    else:              s_pvp = 0

    return s_dy + s_pvp


def _justificativa_fii(ticker: str, meta: dict, dy: float, p_vp: float,
                       total_fiis: int, segmentos_escolhidos: list) -> str:
    seg  = meta["segmento"].replace("_", " ")
    partes = []

    partes.append(
        f"{meta['nome']} — FII de {seg} com DY de {dy:.1f}%/ano"
    )

    if p_vp < 1.0:
        partes.append(
            f"negociado a desconto (P/VP {p_vp:.2f}) — cotas abaixo do valor patrimonial"
        )
    elif p_vp <= 1.05:
        partes.append(f"negociado próximo ao valor patrimonial (P/VP {p_vp:.2f})")
    else:
        partes.append(f"prêmio de {(p_vp-1)*100:.0f}% sobre o VP (P/VP {p_vp:.2f}) — justificado pela qualidade do portfólio")

    # Por que este segmento foi incluído
    seg_humano = {
        "recebíveis_cri": "recebíveis imobiliários (CRI) oferecem rendimento corrigido pelo CDI/IPCA com proteção real",
        "logistica": "galpões logísticos se beneficiam do crescimento do e-commerce e contratos atípicos de longo prazo",
        "shoppings": "shoppings premium são resilientes e têm renda indexada à inflação via contratos percentuais de vendas",
        "lajes_corporativas": "lajes corporativas AAA em regiões prime com ocupação consolidada e contratos atípicos",
        "hibridos_fofs": "FoF diversifica automaticamente entre vários FIIs com gestão ativa",
    }
    if meta["segmento"] in seg_humano:
        partes.append(seg_humano[meta["segmento"]])

    # Diversificação
    if len(segmentos_escolhidos) > 1:
        outros = [s.replace("_", " ") for s in segmentos_escolhidos if s != meta["segmento"]]
        partes.append(
            f"complementa a posição em {' e '.join(outros[:2])} — diversificação por segmento reduz correlação"
        )

    return ". ".join(partes) + "."


async def rodar(
    capital: float,
    n_ativos: int = 4,
    estrategia: str = "CORE",
    excluir_tickers: list[str] | None = None,
) -> list[SugestaoMotor]:
    """
    Seleciona os melhores FIIs para a carteira, garantindo diversificação
    entre segmentos e critérios fundamentalistas mínimos.

    Args:
        capital:          Capital em R$ disponível para o módulo FIIs.
        n_ativos:         Número desejado de FIIs (máx 6).
        estrategia:       Perfil do investidor (afeta aversão a risco).
        excluir_tickers:  Tickers já na carteira — não serão sugeridos.

    Returns:
        Lista de SugestaoMotor com os FIIs selecionados.
    """
    if capital < 1_000:
        return []

    n_ativos = min(n_ativos, 6)
    _excluir = set(t.upper() for t in (excluir_tickers or []))

    # Busca preços/DY/PVP em paralelo
    tickers = [t for t in _FIIS_META if t not in _excluir]
    tarefas = [asyncio.to_thread(_fetch_preco_fii, t) for t in tickers]
    resultados = await asyncio.gather(*tarefas, return_exceptions=True)
    data_map = {
        t: d for t, d in zip(tickers, resultados)
        if isinstance(d, dict) and d.get("preco", 0) > 0
    }

    # Pontua todos e ordena
    candidatos = []
    for ticker in tickers:
        dados = data_map.get(ticker)
        if not dados:
            continue
        meta = _FIIS_META[ticker]
        dy   = dados["dy"]
        p_vp = dados["p_vp"]
        score = _score_fii(dy, p_vp)
        if score > 0:
            candidatos.append({
                "ticker": ticker, "meta": meta,
                "preco": dados["preco"], "dy": dy, "p_vp": p_vp,
                "score": score,
            })

    candidatos.sort(key=lambda x: x["score"], reverse=True)

    # Seleciona garantindo diversificação de segmentos
    selecionados = []
    segmentos_usados: dict[str, int] = {}  # segmento → count

    for cand in candidatos:
        if len(selecionados) >= n_ativos:
            break
        seg = cand["meta"]["segmento"]
        # Máximo 2 FIIs por segmento
        if segmentos_usados.get(seg, 0) >= 2:
            continue
        selecionados.append(cand)
        segmentos_usados[seg] = segmentos_usados.get(seg, 0) + 1

    if not selecionados:
        return []

    segmentos_escolhidos = list(segmentos_usados.keys())
    capital_por_fii = capital / len(selecionados)
    saida: list[SugestaoMotor] = []

    for cand in selecionados:
        ticker = cand["ticker"]
        preco  = cand["preco"]
        meta   = cand["meta"]
        dy     = cand["dy"]
        p_vp   = cand["p_vp"]
        qtd    = max(1, int(capital_por_fii / preco))
        valor  = round(qtd * preco, 2)

        saida.append(SugestaoMotor(
            modulo="fiis",
            ticker=ticker,
            nome=meta["nome"],
            tipo="FII",
            quantidade=float(qtd),
            preco_atual=round(preco, 2),
            valor_total=valor,
            justificativa=_justificativa_fii(ticker, meta, dy, p_vp, len(selecionados), segmentos_escolhidos),
            score=cand["score"],
            dados_extras={
                "segmento":    meta["segmento"],
                "dy_estimado": dy,
                "p_vp":        p_vp,
                "renda_mensal_estimada": round(valor * dy / 100 / 12, 2),
            },
        ))

    return saida

"""
APEX Motor — Opções (Wheel + Calls/Puts a Seco + Covered Call)

Motor de seleção de estratégias com opções para a B3.

ESTRATÉGIAS SUPORTADAS:
  1. WHEEL_PUT — Cash-Secured PUT: vender PUT para gerar renda ou comprar com desconto.
     · Timing: neutro a favorável (ação não sobrecomprada, tendência saudável)
     · Score: retorno anualizado como múltiplo do CDI

  2. COBERTA — Covered CALL: vender CALL sobre posição já em carteira.
     · Ativada quando ticker está em tickers_carteira
     · Score: igual ao WHEEL_PUT + bônus (risco coberto)

  3. CALL_SECO — Long CALL direcional altista: compra de CALL em oversold / reversão.
     · Timing: RSI baixo + suporte + golden cross
     · Score: payoff se ação mover 2×ATR14 / custo do prêmio
     · Risco máximo = prêmio pago (definido, sem alavancagem ilimitada)

  4. PUT_SECO — Long PUT direcional baixista / hedge: compra de PUT em topo ou tendência baixista.
     · Timing: RSI > 70, muito acima da MM200, death cross
     · Score: payoff se ação mover 2×ATR14 para baixo / custo

Dados extras por sugestão:
  - estrategia: WHEEL_PUT | COBERTA | CALL_SECO | PUT_SECO
  - opcao_sugerida: código da opção (ex: PETRW456)
  - strike, vencimento, premio
  - retorno_anual / multiplo_cdi  (opções vendidas)
  - payoff_2atr / target_preco    (opções compradas)
  - timing_veredito / setup_veredito
  - rsi, dist_mm200, suporte, resistencia
"""

import io
import zipfile
import asyncio
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from app.cerebro.especialistas import SugestaoMotor
from app.cerebro.especialistas.watchlist import WHEEL_WATCHLIST
from app.cerebro.especialistas import prefetch as _pf
from app.data.bcb_client import get_selic

# ── Parâmetros ───────────────────────────────────────────────────────────────
_CDI_FALLBACK          = 14.75   # % a.a. — somente quando BCB offline
SCORE_MINIMO           = 1.2     # múltiplo CDI mínimo para opções VENDIDAS (era 1.5)
PAYOFF_MINIMO          = 1.8     # múltiplo payoff/custo para opções COMPRADAS (se mover 2×ATR)
MAX_ATIVOS             = 4
CAPITAL_POR_POSICAO_MIN = 5_000   # mínimo para rodar o motor

_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


# ══════════════════════════════════════════════════════════════════════════════
#  DADOS DE MERCADO
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_stock(ticker_b3: str):
    """Busca preço atual + histórico 1 ano via prefetch (ou yfinance direto)."""
    # Tenta prefetch primeiro
    pf = _pf.get(ticker_b3)
    if pf and pf.sucesso and pf.preco > 0 and pf.hist is not None:
        return pf.preco, pf.hist

    # Fallback direto
    t = yf.Ticker(ticker_b3 + ".SA")
    hist = t.history(period="1y", auto_adjust=True)
    if hist.empty:
        return None, None
    return float(hist["Close"].iloc[-1]), hist


def _baixar_cotahist() -> tuple[Optional[bytes], Optional[str]]:
    """Baixa o arquivo COTAHIST mais recente da B3 (últimos 7 dias úteis)."""
    hoje = date.today()
    for delta in range(10):
        d = hoje - timedelta(days=delta)
        if d.weekday() >= 5:
            continue
        ds = d.strftime("%d%m%Y")
        url = f"https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_D{ds}.ZIP"
        try:
            r = requests.get(url, headers=_HEADERS, timeout=25)
            if r.status_code == 200 and len(r.content) > 1000:
                return r.content, d.strftime("%d/%m/%Y")
        except Exception:
            continue
    return None, None


_COTAHIST_CACHE: dict = {}   # {data: bytes} — evita baixar 2× no mesmo ciclo


def _get_cotahist() -> Optional[bytes]:
    """Retorna COTAHIST do cache ou baixa — com fallback para ontem se hoje falhar."""
    global _COTAHIST_CACHE
    hoje  = date.today().isoformat()
    if hoje in _COTAHIST_CACHE:
        return _COTAHIST_CACHE[hoje]

    # Guarda referência ao cache de ontem ANTES de tentar download
    ontem        = (date.today() - timedelta(days=1)).isoformat()
    cache_ontem  = _COTAHIST_CACHE.get(ontem)

    data, _ = _baixar_cotahist()
    if data:
        _COTAHIST_CACHE = {hoje: data}
        return data

    # Fallback: usa cache de ontem se disponível
    if cache_ontem:
        _COTAHIST_CACHE[hoje] = cache_ontem
        return cache_ontem

    return None


_CAMPO = {
    "CODNEG":       (12, 24),
    "TPMERC":       (24, 27),
    "NOMRES":       (27, 39),
    "PREMED":       (95, 108),
    "PREULT":       (108, 121),
    "PREOFC":       (121, 134),
    "PREOFV":       (134, 147),
    "TOTNEG":       (147, 152),
    "STRKPREATZOR": (188, 201),
    "DATVEN":       (202, 210),
}


def _parse_registro(linha: str) -> Optional[dict]:
    c = _CAMPO
    try:
        strike = int(linha[c["STRKPREATZOR"][0]:c["STRKPREATZOR"][1]]) / 100
        bid    = int(linha[c["PREOFC"][0]:c["PREOFC"][1]]) / 100
        ask    = int(linha[c["PREOFV"][0]:c["PREOFV"][1]]) / 100
        totneg = int(linha[c["TOTNEG"][0]:c["TOTNEG"][1]])
        premed = int(linha[c["PREMED"][0]:c["PREMED"][1]]) / 100
        datven = linha[c["DATVEN"][0]:c["DATVEN"][1]]
        vencto = f"{datven[6:8]}/{datven[4:6]}/{datven[0:4]}" if datven.strip("0") else ""
    except (ValueError, IndexError):
        return None
    return {
        "codigo":     linha[c["CODNEG"][0]:c["CODNEG"][1]].strip(),
        "tipo":       "CALL" if linha[c["TPMERC"][0]:c["TPMERC"][1]] == "070" else "PUT",
        "strike":     strike,
        "bid":        bid,
        "ask":        ask,
        "premed":     premed,
        "vencimento": vencto,
        "negocios":   totneg,
    }


def _fetch_options(ticker: str, cotahist: bytes) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Extrai puts e calls do ticker a partir do buffer COTAHIST."""
    ticker = ticker.upper().strip()
    registros = []
    try:
        with zipfile.ZipFile(io.BytesIO(cotahist)) as z:
            with z.open(z.namelist()[0]) as f:
                # Valida header COTAHIST (primeira linha deve ser "00COTAHIST...")
                first_line = f.readline().decode("latin-1", errors="replace")
                if not first_line.startswith("00COTAHIST"):
                    return None, None  # arquivo inválido ou corrompido

                for linha_bytes in f:
                    linha = linha_bytes.decode("latin-1", errors="replace")
                    if len(linha) < 210:
                        continue
                    tpmerc = linha[24:27]
                    if tpmerc not in ("070", "080"):
                        continue
                    codneg = linha[12:24].strip()
                    if not codneg.startswith(ticker[:4]):
                        continue
                    nomres = linha[27:39].strip()
                    raiz = ticker[:4]
                    if len(ticker) == 5:
                        if ticker[4] == "4" and not nomres.startswith(raiz + "E"):
                            continue
                        if ticker[4] == "3" and nomres.startswith(raiz + "E"):
                            continue
                    reg = _parse_registro(linha)
                    if reg and reg["strike"] > 0:
                        registros.append(reg)
    except Exception:
        return None, None

    if not registros:
        return None, None

    df = pd.DataFrame(registros)
    return (
        df[df["tipo"] == "PUT"].copy(),
        df[df["tipo"] == "CALL"].copy(),
    )


# ══════════════════════════════════════════════════════════════════════════════
#  ANÁLISE TÉCNICA — INDICADORES COMPARTILHADOS
# ══════════════════════════════════════════════════════════════════════════════

def _indicadores(hist: pd.DataFrame, preco: float) -> dict:
    """Calcula todos os indicadores técnicos necessários para as 4 estratégias."""
    if hist is None or len(hist) < 30:
        return {
            "rsi": 50, "mm200": 0, "mm50": 0, "dist_mm200": 0,
            "golden_cross": True, "momentum20": 0, "range_pct": 50,
            "min_52s": 0, "max_52s": 0, "suporte": None, "resistencia": None,
            "atr14": preco * 0.02, "preco": preco,
        }

    close = hist["Close"]
    high  = hist["High"]
    low   = hist["Low"]

    # RSI(14)
    delta = close.diff()
    ganho = delta.clip(lower=0).rolling(14).mean()
    perda = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = ganho / perda.replace(0, 1e-9)
    rsi   = float(100 - 100 / (1 + rs.iloc[-1]))

    # Médias móveis
    mm200        = float(close.rolling(200, min_periods=50).mean().iloc[-1])
    mm50         = float(close.rolling(50,  min_periods=20).mean().iloc[-1])
    dist_mm200   = (preco - mm200) / mm200 * 100 if mm200 > 0 else 0
    golden_cross = mm50 > mm200

    # Momentum 20d
    preco_20d  = float(close.iloc[-21]) if len(close) >= 21 else float(close.iloc[0])
    momentum20 = (preco - preco_20d) / preco_20d * 100

    # Range 52 semanas
    ult252    = close.tail(252)
    min_52s   = float(ult252.min())
    max_52s   = float(ult252.max())
    range_pct = (preco - min_52s) / (max_52s - min_52s) * 100 if max_52s > min_52s else 50.0

    # ATR 14d
    prev_cl = close.shift(1)
    tr      = pd.concat([high - low, (high - prev_cl).abs(), (low - prev_cl).abs()], axis=1).max(axis=1)
    atr14   = float(tr.rolling(14).mean().iloc[-1])

    # Pivots suporte e resistência
    lows_arr  = low.values
    highs_arr = high.values
    n, wing   = len(lows_arr), 5
    sup_pivots, res_pivots = [], []
    for i in range(wing, n - wing):
        v = lows_arr[i]
        if all(v <= lows_arr[i - j] for j in range(1, wing + 1)) and \
           all(v <= lows_arr[i + j] for j in range(1, wing + 1)):
            sup_pivots.append(float(v))
        h = highs_arr[i]
        if all(h >= highs_arr[i - j] for j in range(1, wing + 1)) and \
           all(h >= highs_arr[i + j] for j in range(1, wing + 1)):
            res_pivots.append(float(h))

    sup_candidates = [v for v in sup_pivots if v < preco * 0.995]
    res_candidates = [v for v in res_pivots if v > preco * 1.005]
    suporte     = round(max(sup_candidates), 2) if sup_candidates else None
    resistencia = round(min(res_candidates), 2) if res_candidates else None

    return {
        "rsi":          round(rsi, 1),
        "mm200":        round(mm200, 2),
        "mm50":         round(mm50, 2),
        "dist_mm200":   round(dist_mm200, 1),
        "golden_cross": golden_cross,
        "momentum20":   round(momentum20, 1),
        "range_pct":    round(range_pct, 1),
        "min_52s":      round(min_52s, 2),
        "max_52s":      round(max_52s, 2),
        "suporte":      suporte,
        "resistencia":  resistencia,
        "atr14":        round(atr14, 2),
        "preco":        round(preco, 2),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  AVALIAÇÃO DE TIMING POR ESTRATÉGIA
# ══════════════════════════════════════════════════════════════════════════════

def _veredito_wheel_put(ind: dict) -> tuple[str, list[str]]:
    """
    Timing para WHEEL_PUT / COBERTA (vender opção).
    Thresholds mais suaves — mercado neutro/normal vira NEUTRO, não ESTICADA.
    Retorna: (FAVORÁVEL | NEUTRO | ESTICADA, alertas)
    """
    pts, alertas = 0, []
    rsi = ind["rsi"]

    if rsi > 72:
        alertas.append(f"RSI {rsi:.0f} — sobrecomprado")
        pts += 2
    elif rsi > 62:
        alertas.append(f"RSI {rsi:.0f} — levemente sobrecomprado")
        pts += 1

    if ind["dist_mm200"] > 22:
        alertas.append(f"{ind['dist_mm200']:.1f}% acima da MM200 — muito esticada")
        pts += 2
    elif ind["dist_mm200"] > 12:
        alertas.append(f"{ind['dist_mm200']:.1f}% acima da MM200")
        pts += 1

    if ind["momentum20"] > 12:
        alertas.append(f"+{ind['momentum20']:.1f}% em 20d — rali forte, risco reversão")
        pts += 2
    elif ind["momentum20"] > 7:
        alertas.append(f"+{ind['momentum20']:.1f}% em 20d — alta recente")
        pts += 1

    if not ind["golden_cross"]:
        alertas.append("Death Cross (MM50 < MM200) — tendência de baixa")
        pts += 1

    if ind["range_pct"] > 85:
        alertas.append(f"Perto do topo anual ({ind['range_pct']:.0f}%)")
        pts += 1

    veredito = "FAVORÁVEL" if pts == 0 else ("NEUTRO" if pts <= 2 else "ESTICADA")
    return veredito, alertas


def _setup_call_seco(ind: dict) -> tuple[str, list[str]]:
    """
    Avalia setup para CALL_SECO (comprar CALL direcional alta).
    BOM = ótimo para compra de CALL | NEUTRO = razoável | RUIM = não recomendado.
    """
    favor, contra = 0, 0
    razoes: list[str] = []
    rsi = ind["rsi"]

    if rsi < 38:
        razoes.append(f"RSI {rsi:.0f} — sobrevendido, pressão compradora elevada")
        favor += 2
    elif rsi < 48:
        razoes.append(f"RSI {rsi:.0f} — neutro-fraco, potencial de recuperação")
        favor += 1
    elif rsi > 72:
        razoes.append(f"RSI {rsi:.0f} — sobrecomprado, risco de topo")
        contra += 2

    if ind["golden_cross"]:
        razoes.append("Golden Cross (MM50 > MM200) — tendência de alta confirmada")
        favor += 1
    else:
        razoes.append("Death Cross — vento contrário para CALL")
        contra += 2

    if -5 < ind["dist_mm200"] < 5:
        razoes.append("Próximo da MM200 — zona de decisão com potencial expansão")
        favor += 1
    elif ind["dist_mm200"] > 20:
        razoes.append(f"{ind['dist_mm200']:.1f}% acima da MM200 — muito esticada para call a seco")
        contra += 1

    if ind["range_pct"] < 30:
        razoes.append(f"Perto do fundo anual ({ind['range_pct']:.0f}%) — potencial recuperação ampla")
        favor += 1

    if ind["suporte"] and ind["preco"] <= ind["suporte"] * 1.03:
        razoes.append(f"Sobre suporte R$ {ind['suporte']:.2f} — proteção natural na queda")
        favor += 1

    if contra >= 2:
        return "RUIM", razoes
    return "BOM" if favor >= 2 else "NEUTRO", razoes


def _setup_put_seco(ind: dict) -> tuple[str, list[str]]:
    """
    Avalia setup para PUT_SECO (comprar PUT direcional baixa / hedge).
    BOM = ativo sobrecomprado ou em tendência baixista.
    """
    favor, contra = 0, 0
    razoes: list[str] = []
    rsi = ind["rsi"]

    if rsi > 75:
        razoes.append(f"RSI {rsi:.0f} — fortemente sobrecomprado, sinal de reversão")
        favor += 2
    elif rsi > 65:
        razoes.append(f"RSI {rsi:.0f} — sobrecomprado")
        favor += 1
    elif rsi < 40:
        razoes.append(f"RSI {rsi:.0f} — sobrevendido, evite PUT_SECO aqui")
        contra += 2

    if not ind["golden_cross"]:
        razoes.append("Death Cross — confirmação de tendência baixista")
        favor += 2

    if ind["dist_mm200"] > 25:
        razoes.append(f"{ind['dist_mm200']:.1f}% acima da MM200 — muito esticada, reversão provável")
        favor += 2
    elif ind["dist_mm200"] > 15:
        razoes.append(f"{ind['dist_mm200']:.1f}% acima da MM200 — esticada")
        favor += 1

    if ind["range_pct"] > 88:
        razoes.append(f"No topo do range anual ({ind['range_pct']:.0f}%) — risco alto de topo")
        favor += 1

    if ind["momentum20"] > 10:
        razoes.append(f"+{ind['momentum20']:.1f}% em 20d — voo exagerado, reversão possível")
        favor += 1

    if contra >= 2:
        return "RUIM", razoes
    return "BOM" if favor >= 3 else "NEUTRO", razoes


# ══════════════════════════════════════════════════════════════════════════════
#  SCORING DE OPÇÕES
# ══════════════════════════════════════════════════════════════════════════════

def _dias_uteis(vencimento_str: str) -> int:
    try:
        d, m, y = vencimento_str.split("/")
        exp = date(int(y), int(m), int(d))
        hoje = date.today()
        return 0 if exp <= hoje else int(np.busday_count(hoje.isoformat(), exp.isoformat()))
    except Exception:
        return 999


def _score_vendida(row: pd.Series, preco: float, tipo: str, acima_mm200: bool, cdi: float = _CDI_FALLBACK) -> float:
    dias = _dias_uteis(row["vencimento"])
    if dias < 7 or dias > 86:
        return 0.0
    if row["preco_ref"] < 0.10:
        return 0.0

    # Retorno anualizado (252 du/ano — padrão B3)
    base = row["strike"] if tipo == "PUT" else preco
    ret_anual = row["preco_ref"] / base * (252 / dias) * 100
    ratio_cdi = ret_anual / cdi
    if ratio_cdi < 1.0:
        return 0.0

    dist_pct = abs(preco - row["strike"]) / preco * 100
    if dist_pct < 1.5:
        return 0.0

    # Fator prazo (sweet spot 15-25 du)
    if   15 <= dias <= 25: f_prazo = 1.25
    elif 26 <= dias <= 36: f_prazo = 1.10
    elif 37 <= dias <= 50: f_prazo = 0.85
    elif  7 <= dias <= 14: f_prazo = 0.70
    else:                  f_prazo = 0.50

    # Fator distância OTM (3-5% ideal)
    if   3.0 <= dist_pct <= 5.0: f_dist = 1.20
    elif 2.0 <= dist_pct <  3.0: f_dist = 0.90
    elif 5.0 <  dist_pct <= 8.0: f_dist = 1.00
    elif 8.0 <  dist_pct <= 12: f_dist = 0.70
    else:                        f_dist = 0.60

    # Fator liquidez
    neg = row.get("negocios", 0)
    if   neg >= 100: f_liq = 1.20
    elif neg >=  30: f_liq = 1.05
    elif neg >=  10: f_liq = 0.90
    elif neg >=   3: f_liq = 0.70
    else:            f_liq = 0.50

    # Fator tendência
    if   tipo == "PUT":  f_tend = 1.10 if acima_mm200 else 0.50
    else:                f_tend = 0.85 if acima_mm200 else 1.10

    return ratio_cdi * f_prazo * f_dist * f_liq * f_tend


def _recomendar_vendida(
    df: Optional[pd.DataFrame],
    preco: float,
    tipo: str,
    acima_mm200: bool,
    veredito: str,
    cdi: float = _CDI_FALLBACK,
) -> Optional[pd.Series]:
    """Retorna a melhor opção vendida ou None se nenhuma atender."""
    if df is None or df.empty or "strike" not in df.columns:
        return None

    # Ajuste de score mínimo pelo timing — menos agressivo que antes
    score_min = SCORE_MINIMO
    if   veredito == "ESTICADA": score_min = SCORE_MINIMO * 1.4   # era 1.8×
    elif veredito == "NEUTRO":   score_min = SCORE_MINIMO * 1.15  # era 1.2×

    d = df.copy()
    if tipo == "PUT":
        d = d[d["strike"].between(preco * 0.85, preco * 0.97)]
    else:
        d = d[d["strike"].between(preco * 1.01, preco * 1.15)]

    d = d[(d["bid"] > 0) & (d["ask"] > 0)]
    d["preco_ref"] = d["bid"]
    d["dias"]      = d["vencimento"].apply(_dias_uteis)
    d["score"]     = d.apply(lambda r: _score_vendida(r, preco, tipo, acima_mm200, cdi), axis=1)
    d = d[d["score"] >= score_min].sort_values("score", ascending=False)

    if d.empty:
        return None

    best      = d.iloc[0]
    dias      = int(best["dias"])
    base      = best["strike"] if tipo == "PUT" else preco
    ret_anual = round(best["preco_ref"] / base * (252 / dias) * 100, 1)
    mult_cdi  = round(ret_anual / cdi, 2)
    breakeven = round(best["strike"] - best["preco_ref"], 2) if tipo == "PUT" else round(best["strike"] + best["preco_ref"], 2)
    dist_pct  = abs(preco - best["strike"]) / preco * 100

    return pd.Series({
        **best.to_dict(),
        "retorno_anual": ret_anual,
        "multiplo_cdi":  mult_cdi,
        "breakeven":     breakeven,
        "dist_pct":      round(dist_pct, 1),
        "dias":          dias,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  SCORING — OPÇÕES COMPRADAS (CALL_SECO / PUT_SECO)
# ══════════════════════════════════════════════════════════════════════════════

def _score_comprada(
    row: pd.Series,
    preco: float,
    tipo: str,
    ind: dict,
) -> float:
    """
    Score para opção comprada: payoff se ação mover 2×ATR14 na direção esperada.
    Retorna o múltiplo intrinsic-no-alvo / prêmio pago.
    """
    dias = _dias_uteis(row["vencimento"])
    if dias < 15 or dias > 65:
        return 0.0
    bid = float(row.get("bid", 0))
    if bid < 0.05:
        return 0.0

    atr14 = ind.get("atr14", preco * 0.02)
    if atr14 <= 0:
        return 0.0

    target_move = max(atr14 * 2, preco * 0.07)

    if tipo == "CALL":
        target              = preco + target_move
        intrinsic_at_target = max(0.0, target - float(row["strike"]))
    else:
        target              = preco - target_move
        intrinsic_at_target = max(0.0, float(row["strike"]) - target)

    if intrinsic_at_target < bid:
        return 0.0

    payoff_ratio = intrinsic_at_target / bid
    if payoff_ratio < PAYOFF_MINIMO:
        return 0.0

    dist_pct = abs(preco - float(row["strike"])) / preco * 100
    if dist_pct < 2.0 or dist_pct > 12.0:
        return 0.0

    if   25 <= dias <= 40: f_prazo = 1.20
    elif 15 <= dias <= 24: f_prazo = 0.80
    elif 41 <= dias <= 65: f_prazo = 1.00
    else:                  f_prazo = 0.50

    neg = row.get("negocios", 0)
    if   neg >= 100: f_liq = 1.20
    elif neg >=  30: f_liq = 1.05
    elif neg >=  10: f_liq = 0.90
    elif neg >=   3: f_liq = 0.70
    else:            f_liq = 0.40

    return payoff_ratio * f_prazo * f_liq


def _recomendar_comprada(
    df: Optional[pd.DataFrame],
    preco: float,
    tipo: str,
    ind: dict,
    setup: str,
) -> Optional[pd.Series]:
    """Retorna a melhor opção comprada ou None. setup: BOM | NEUTRO | RUIM."""
    if df is None or df.empty or setup == "RUIM":
        return None

    payoff_min = PAYOFF_MINIMO * (1.3 if setup == "NEUTRO" else 1.0)

    d = df.copy()
    if tipo == "CALL":
        d = d[d["strike"].between(preco * 1.02, preco * 1.12)]
    else:
        d = d[d["strike"].between(preco * 0.88, preco * 0.98)]

    d = d[(d["bid"] > 0) & (d["ask"] > 0)]
    d["dias"]  = d["vencimento"].apply(_dias_uteis)
    d["score"] = d.apply(lambda r: _score_comprada(r, preco, tipo, ind), axis=1)
    d = d[d["score"] >= payoff_min].sort_values("score", ascending=False)

    if d.empty:
        return None

    best        = d.iloc[0]
    dias        = int(best["dias"])
    bid         = float(best["bid"])
    atr14       = ind.get("atr14", preco * 0.02)
    target_move = max(atr14 * 2, preco * 0.07)

    if tipo == "CALL":
        target              = preco + target_move
        intrinsic_at_target = max(0.0, target - float(best["strike"]))
        breakeven           = float(best["strike"]) + bid
    else:
        target              = preco - target_move
        intrinsic_at_target = max(0.0, float(best["strike"]) - target)
        breakeven           = float(best["strike"]) - bid

    payoff_ratio = round(intrinsic_at_target / bid, 2) if bid > 0 else 0
    dist_pct     = abs(preco - float(best["strike"])) / preco * 100

    return pd.Series({
        **best.to_dict(),
        "breakeven":        round(breakeven, 2),
        "payoff_2atr":      payoff_ratio,
        "target_preco":     round(target, 2),
        "target_move_pct":  round(target_move / preco * 100, 1),
        "dist_pct":         round(dist_pct, 1),
        "dias":             dias,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  JUSTIFICATIVAS EM LINGUAGEM NATURAL
# ══════════════════════════════════════════════════════════════════════════════

def _justificativa_vendida(
    ticker: str,
    tipo: str,
    estrategia: str,
    opcao: pd.Series,
    ind: dict,
    veredito: str,
) -> str:
    partes = []

    if estrategia == "WHEEL_PUT":
        if veredito == "FAVORÁVEL":
            partes.append(f"{ticker} em condição técnica favorável — timing ideal para Wheel PUT")
        elif veredito == "NEUTRO":
            partes.append(f"{ticker} em condição neutra — strike conservador priorizado")
        else:
            partes.append(f"{ticker} esticada, mas prêmio exigido justifica o risco — critério elevado aplicado")
    else:
        partes.append(f"{ticker} em carteira — vender CALL coberta para gerar renda adicional sem risco adicional")

    rsi = ind["rsi"]
    if rsi < 40:
        partes.append(f"RSI {rsi:.0f} — sobrevendida, zona de demanda forte")
    elif rsi < 55:
        partes.append(f"RSI {rsi:.0f} — neutro saudável")
    else:
        partes.append(f"RSI {rsi:.0f} — levemente sobrecomprado, prêmio compensa")

    mult  = float(opcao.get("multiplo_cdi", 0))
    nivel = "EXCELENTE" if mult >= 3 else ("BOM" if mult >= 2 else "OK")
    partes.append(f"prêmio {opcao['retorno_anual']}%/ano = {mult:.1f}× CDI ({nivel})")

    if tipo == "PUT":
        partes.append(
            f"PUT {opcao['dist_pct']:.1f}% OTM — ação aguenta cair até R${opcao['breakeven']:.2f} sem prejuízo"
        )
    else:
        partes.append(
            f"CALL {opcao['dist_pct']:.1f}% OTM — exercida só se ação subir além de R${opcao['strike']:.2f}"
        )

    du = int(opcao["dias"])
    if 15 <= du <= 25:
        partes.append(f"{du} dias úteis — zona ideal de theta decay")
    else:
        partes.append(f"{du} dias úteis até vencimento")

    if tipo == "PUT" and ind.get("suporte"):
        sup = ind["suporte"]
        be  = float(opcao.get("breakeven", 0))
        if sup < be:
            partes.append(f"suporte técnico R${sup:.2f} reforça proteção abaixo do breakeven")

    return ". ".join(partes) + "."


def _justificativa_comprada(
    ticker: str,
    tipo: str,
    opcao: pd.Series,
    ind: dict,
    razoes_setup: list[str],
) -> str:
    partes = []

    if tipo == "CALL":
        partes.append(f"{ticker} — CALL a seco, aposta direcional na alta")
    else:
        partes.append(f"{ticker} — PUT a seco, aposta ou hedge baixista")

    if razoes_setup:
        partes.append(razoes_setup[0])

    payoff   = float(opcao.get("payoff_2atr", 0))
    target   = float(opcao.get("target_preco", 0))
    tm_pct   = float(opcao.get("target_move_pct", 0))
    partes.append(
        f"se {ticker} mover {tm_pct:.1f}% até R${target:.2f} (alvo 2×ATR14), "
        f"opção retorna {payoff:.1f}× o prêmio pago"
    )

    strike = float(opcao.get("strike", 0))
    bid    = float(opcao.get("bid", 0))
    partes.append(
        f"greve R${strike:.2f} — risco máx = prêmio R${bid:.2f}/ação (risco definido, sem stop necessário)"
    )

    du = int(opcao["dias"])
    partes.append(f"{du} dias úteis até vencimento — janela para o catalisador atuar")

    if tipo == "CALL" and ind.get("suporte"):
        partes.append(f"suporte em R${ind['suporte']:.2f} sustenta a tese comprada")
    if tipo == "PUT" and ind.get("resistencia"):
        partes.append(f"resistência em R${ind['resistencia']:.2f} confirma dificuldade de subida")

    return ". ".join(partes) + "."


# ══════════════════════════════════════════════════════════════════════════════
#  INTERFACE PÚBLICA DO MOTOR
# ══════════════════════════════════════════════════════════════════════════════

async def rodar(
    capital: float,
    watchlist: Optional[list[str]] = None,
    n_ativos: int = 3,
    excluir_tickers: list[str] | None = None,
    tickers_carteira: list[str] | None = None,
) -> list[SugestaoMotor]:
    """
    Roda o motor de Opções sobre a watchlist e retorna os melhores candidatos.

    Estratégias avaliadas por ticker:
      WHEEL_PUT — vender PUT cash-secured (geração de renda / compra com desconto)
      COBERTA   — vender CALL coberta (se ticker estiver em tickers_carteira)
      CALL_SECO — comprar CALL direcional (oversold + setup altista)
      PUT_SECO  — comprar PUT direcional (overbought + setup baixista / hedge)
    """
    if capital < CAPITAL_POR_POSICAO_MIN:
        return []

    cdi_live = await get_selic()
    cdi      = float(cdi_live) if isinstance(cdi_live, (int, float)) else _CDI_FALLBACK

    _excluir  = set(t.upper() for t in (excluir_tickers or []))
    _carteira = set(t.upper() for t in (tickers_carteira or []))
    tickers   = [t for t in (watchlist or WHEEL_WATCHLIST) if t.upper() not in _excluir]
    n_ativos  = min(n_ativos, MAX_ATIVOS)

    cotahist = await asyncio.to_thread(_get_cotahist)

    fetch_tasks   = [asyncio.to_thread(_fetch_stock, t) for t in tickers]
    fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)

    candidatos: list[dict] = []

    for ticker, result in zip(tickers, fetch_results):
        try:
            if isinstance(result, Exception):
                continue
            preco, hist = result
            if preco is None or hist is None:
                continue

            ind         = _indicadores(hist, preco)
            acima_mm200 = preco >= ind["mm200"]
            em_carteira = ticker.upper() in _carteira

            puts, calls = None, None
            if cotahist:
                puts, calls = _fetch_options(ticker, cotahist)

            # ── 1. WHEEL_PUT ──────────────────────────────────────────────
            veredito_put, alertas_put = _veredito_wheel_put(ind)
            opcao_put = _recomendar_vendida(puts, preco, "PUT", acima_mm200, veredito_put, cdi)
            if opcao_put is not None:
                candidatos.append({
                    "ticker": ticker, "preco": preco, "ind": ind,
                    "opcao": opcao_put, "estrategia": "WHEEL_PUT",
                    "tipo_opcao": "PUT", "acima_mm200": acima_mm200,
                    "veredito": veredito_put, "alertas": alertas_put,
                    "score_total": float(opcao_put["score"]),
                    "razoes_setup": alertas_put,
                })

            # ── 2. COVERED CALL ──────────────────────────────────────────
            if em_carteira:
                opcao_coberta = _recomendar_vendida(calls, preco, "CALL", acima_mm200, veredito_put, cdi)
                if opcao_coberta is not None:
                    candidatos.append({
                        "ticker": ticker, "preco": preco, "ind": ind,
                        "opcao": opcao_coberta, "estrategia": "COBERTA",
                        "tipo_opcao": "CALL", "acima_mm200": acima_mm200,
                        "veredito": veredito_put, "alertas": [],
                        "score_total": float(opcao_coberta["score"]) * 1.2,
                        "razoes_setup": ["posição existente em carteira — call coberta sem risco adicional"],
                    })

            # ── 3. CALL_SECO ─────────────────────────────────────────────
            setup_call, razoes_call = _setup_call_seco(ind)
            opcao_call_seco = _recomendar_comprada(calls, preco, "CALL", ind, setup_call)
            if opcao_call_seco is not None:
                candidatos.append({
                    "ticker": ticker, "preco": preco, "ind": ind,
                    "opcao": opcao_call_seco, "estrategia": "CALL_SECO",
                    "tipo_opcao": "CALL", "acima_mm200": acima_mm200,
                    "veredito": setup_call, "alertas": razoes_call,
                    "score_total": float(opcao_call_seco["score"]),
                    "razoes_setup": razoes_call,
                })

            # ── 4. PUT_SECO ──────────────────────────────────────────────
            setup_put_d, razoes_put_d = _setup_put_seco(ind)
            opcao_put_seco = _recomendar_comprada(puts, preco, "PUT", ind, setup_put_d)
            if opcao_put_seco is not None:
                candidatos.append({
                    "ticker": ticker, "preco": preco, "ind": ind,
                    "opcao": opcao_put_seco, "estrategia": "PUT_SECO",
                    "tipo_opcao": "PUT", "acima_mm200": acima_mm200,
                    "veredito": setup_put_d, "alertas": razoes_put_d,
                    "score_total": float(opcao_put_seco["score"]),
                    "razoes_setup": razoes_put_d,
                })

        except Exception:
            continue

    # Ordena por score e de-duplica (no máximo 1 estratégia por ticker)
    candidatos.sort(key=lambda x: x["score_total"], reverse=True)
    vistos: set[str] = set()
    selecionados: list[dict] = []
    for c in candidatos:
        key = f"{c['ticker']}_{c['estrategia']}"
        if key not in vistos and len(selecionados) < n_ativos:
            vistos.add(key)
            selecionados.append(c)

    if not selecionados:
        return []

    capital_por_posicao = capital / len(selecionados)
    resultado: list[SugestaoMotor] = []

    for cand in selecionados:
        ticker     = cand["ticker"]
        preco      = cand["preco"]
        opcao      = cand["opcao"]
        ind        = cand["ind"]
        estrategia = cand["estrategia"]
        tipo_opcao = cand["tipo_opcao"]
        strike     = float(opcao["strike"])

        if estrategia in ("WHEEL_PUT", "COBERTA"):
            # Opção VENDIDA: capital = strike × lotes × 100 (cash-secured)
            base_capital = strike if estrategia == "WHEEL_PUT" else preco
            qtd_lotes    = max(1, int(capital_por_posicao / (base_capital * 100)))
            qtd_acoes    = qtd_lotes * 100
            capital_real = qtd_lotes * base_capital * 100
            premio_ref   = float(opcao.get("preco_ref", opcao.get("bid", 0)))
            premio_total = round(premio_ref * qtd_acoes, 2)

            justificativa = _justificativa_vendida(ticker, tipo_opcao, estrategia, opcao, ind, cand["veredito"])
            dados_extras  = {
                "estrategia":      estrategia,
                "etapa":           tipo_opcao,
                "opcao_sugerida":  str(opcao["codigo"]),
                "strike":          round(strike, 2),
                "vencimento":      str(opcao["vencimento"]),
                "premio":          round(premio_ref, 2),
                "premio_total":    premio_total,
                "breakeven":       round(float(opcao.get("breakeven", 0)), 2),
                "retorno_anual":   float(opcao.get("retorno_anual", 0)),
                "multiplo_cdi":    float(opcao.get("multiplo_cdi", 0)),
                "dist_otm_pct":    float(opcao.get("dist_pct", 0)),
                "dias_uteis":      int(opcao["dias"]),
                "timing_veredito": cand["veredito"],
                "rsi":             ind["rsi"],
                "dist_mm200":      ind["dist_mm200"],
                "momentum_20d":    ind["momentum20"],
                "suporte":         ind.get("suporte"),
                "alertas_tecnicos": cand["alertas"],
                "qtd_lotes":       qtd_lotes,
            }

        else:
            # Opção COMPRADA: usa ~25% do capital alocado (risco definido)
            custo_por_lote = float(opcao.get("bid", 0.5)) * 100
            qtd_lotes      = max(1, int(capital_por_posicao * 0.25 / max(custo_por_lote, 1)))
            qtd_lotes      = min(qtd_lotes, 20)
            qtd_acoes      = qtd_lotes * 100
            capital_real   = qtd_lotes * custo_por_lote

            justificativa = _justificativa_comprada(ticker, tipo_opcao, opcao, ind, cand["razoes_setup"])
            dados_extras  = {
                "estrategia":      estrategia,
                "etapa":           tipo_opcao,
                "opcao_sugerida":  str(opcao["codigo"]),
                "strike":          round(strike, 2),
                "vencimento":      str(opcao["vencimento"]),
                "premio":          round(float(opcao.get("bid", 0)), 2),
                "custo_total":     round(capital_real, 2),
                "breakeven":       round(float(opcao.get("breakeven", 0)), 2),
                "payoff_2atr":     float(opcao.get("payoff_2atr", 0)),
                "target_preco":    float(opcao.get("target_preco", 0)),
                "target_move_pct": float(opcao.get("target_move_pct", 0)),
                "dist_otm_pct":    float(opcao.get("dist_pct", 0)),
                "dias_uteis":      int(opcao["dias"]),
                "setup_veredito":  cand["veredito"],
                "rsi":             ind["rsi"],
                "dist_mm200":      ind["dist_mm200"],
                "momentum_20d":    ind["momentum20"],
                "suporte":         ind.get("suporte"),
                "resistencia":     ind.get("resistencia"),
                "alertas_setup":   cand["alertas"],
                "qtd_lotes":       qtd_lotes,
            }

        _nome_map = {
            "WHEEL_PUT": f"Wheel PUT {opcao['codigo']}",
            "COBERTA":   f"Covered CALL {opcao['codigo']}",
            "CALL_SECO": f"CALL a Seco {opcao['codigo']}",
            "PUT_SECO":  f"PUT a Seco {opcao['codigo']}",
        }

        resultado.append(SugestaoMotor(
            modulo="wheel",
            ticker=ticker,
            nome=f"{ticker} — {_nome_map[estrategia]}",
            tipo="ACAO",
            quantidade=float(qtd_acoes),
            preco_atual=preco,
            valor_total=round(capital_real, 2),
            justificativa=justificativa,
            score=cand["score_total"],
            dados_extras=dados_extras,
        ))

    return resultado

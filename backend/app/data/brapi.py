"""
Cliente BRAPI — cotações brasileiras em tempo real.
Documentação: https://brapi.dev/docs
Cache automático via MemoryCache (sem Redis).

Se BRAPI_TOKEN não estiver configurado (vazio ou placeholder),
todas as funções retornam None/{}/[] imediatamente e o sistema
usa yfinance como fonte principal — sem chamadas HTTP desperdiçadas.
"""
import httpx
from typing import Optional
from app.config import BRAPI_TOKEN, BRAPI_BASE_URL, CACHE_TTL_QUOTES, CACHE_TTL_INDICATORS
from app.data.cache import cache
from app.logger import logger
import asyncio

# ---------- detecção automática de token ----------
_PLACEHOLDER_TOKENS = {"seu_token_aqui", "your_token_here", "TOKEN_AQUI", ""}
_BRAPI_CONFIGURED = bool(BRAPI_TOKEN) and BRAPI_TOKEN.strip() not in _PLACEHOLDER_TOKENS

if not _BRAPI_CONFIGURED:
    logger.info(
        "BRAPI token não configurado — usando yfinance como fonte principal de dados."
    )


def _headers() -> dict:
    if _BRAPI_CONFIGURED:
        return {"Authorization": f"Bearer {BRAPI_TOKEN}"}
    return {}


async def get_quote(ticker: str) -> Optional[dict]:
    """Cotação atual de um ativo. Cache 60s."""
    if not _BRAPI_CONFIGURED:
        return None

    key = f"quote:{ticker}"
    cached = cache.get(key)
    if cached:
        return cached

    url = f"{BRAPI_BASE_URL}/quote/{ticker}"
    params = {"fundamental": "false", "dividends": "false"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params=params, headers=_headers())
            response.raise_for_status()
            data = response.json()
            if data.get("results"):
                result = data["results"][0]
                cache.set(key, result, ttl=CACHE_TTL_QUOTES)
                return result
        except Exception as e:
            logger.warning("brapi.get_quote %s falhou: %s", ticker, e)
            return None
    return None


def _resolve_yf_ticker(ticker: str) -> str:
    """Resolve o ticker correto para yfinance. BDRs usam o ticker US subjacente."""
    from app.data.tecnico import _bdr_to_us_ticker
    us = _bdr_to_us_ticker(ticker)
    if us:
        return us  # BDR → ticker US direto (sem .SA)
    return ticker if "." in ticker else f"{ticker}.SA"


async def _enrich_from_yfinance(ticker: str, fund: dict) -> dict:
    """Enriquece dict fundamentalista com dados do yfinance quando BRAPI modules falham.
    Executa em thread separada (yfinance é síncrono/bloqueante).
    Só preenche campos que ainda não existem no dict.
    """
    import yfinance as yf

    yf_ticker = _resolve_yf_ticker(ticker)

    def _fetch():
        try:
            t = yf.Ticker(yf_ticker)
            return t.info
        except Exception as e:
            logger.warning("yfinance enrich %s falhou: %s", yf_ticker, e)
            return {}

    info = await asyncio.to_thread(_fetch)
    if not info:
        return fund

    # Mapeamento: campo_fund → chave_yfinance
    _MAP = {
        # Valuation
        "priceToBookRatio":        "priceToBook",
        "enterpriseValueEbitda":   "enterpriseToEbitda",
        "enterpriseValueRevenue":  "enterpriseToRevenue",
        "pegRatio":                "pegRatio",
        # Dividendos (yfinance retorna em %, ex: 3.46 → converte para decimal 0.0346)
        # Tratado separadamente abaixo
        # Rentabilidade
        "returnOnEquity":          "returnOnEquity",
        "returnOnAssets":          "returnOnAssets",
        # Margens
        "netMargin":               "profitMargins",
        "grossMargin":             "grossMargins",
        "ebitdaMargin":            "ebitdaMargins",
        "operatingMargin":         "operatingMargins",
        # Endividamento
        "debtToEquity":            "debtToEquity",
        "currentLiquidity":        "currentRatio",
        # Absolutos
        "bookValuePerShare":       "bookValue",
        "ebitda":                  "ebitda",
        "totalRevenue":            "totalRevenue",
        "netIncome":               "netIncomeToCommon",
        "freeCashflow":            "freeCashflow",
        # Crescimento
        "earningsGrowth":          "earningsGrowth",
        "revenueGrowth":           "revenueGrowth",
        # Payout
        "payoutRatio":             "payoutRatio",
    }

    for fund_key, yf_key in _MAP.items():
        if fund_key not in fund:
            val = info.get(yf_key)
            if val is not None:
                # yfinance debtToEquity vem em % (ex: 173.4 = 1.734x), normalizar para ratio
                if fund_key == "debtToEquity" and val > 10:
                    val = val / 100
                fund[fund_key] = val

    # DY: preferir trailingAnnualDividendYield (baseado em pagamentos reais)
    # yfinance 'dividendYield' pode ser forward/declarado e geralmente incorreto
    if "dividendYield" not in fund:
        dy_yf = info.get("trailingAnnualDividendYield")
        if dy_yf is None:
            dy_yf = info.get("dividendYield")
        if dy_yf is not None:
            fund["dividendYield"] = dy_yf / 100 if dy_yf > 1 else dy_yf

    # Info
    if "sector" not in fund:
        fund["sector"] = info.get("sector")
    if "industry" not in fund:
        fund["industry"] = info.get("industry")
    if "marketCap" not in fund:
        fund["marketCap"] = info.get("marketCap")

    # ---------- Dados de analistas / volume / earnings (SEMPRE sobrescreve — BRAPI não tem) ----------
    _ANALYST_FIELDS = {
        "targetMeanPrice":    "targetMeanPrice",
        "targetHighPrice":    "targetHighPrice",
        "targetLowPrice":     "targetLowPrice",
        "numberOfAnalysts":   "numberOfAnalystOpinions",
        "recommendationKey":  "recommendationKey",
        "avgDailyVolume10d":  "averageDailyVolume10Day",
        "fiftyTwoWeekHigh":   "fiftyTwoWeekHigh",
        "fiftyTwoWeekLow":    "fiftyTwoWeekLow",
    }
    for fund_key, yf_key in _ANALYST_FIELDS.items():
        val = info.get(yf_key)
        if val is not None:
            fund[fund_key] = val

    # earningsDate: yfinance retorna timestamp Unix ou lista — converter para ISO string
    earnings_raw = info.get("earningsDate")
    if earnings_raw:
        from datetime import datetime as _dt
        try:
            if isinstance(earnings_raw, (list, tuple)) and len(earnings_raw) > 0:
                ts = earnings_raw[0]
            else:
                ts = earnings_raw
            if isinstance(ts, (int, float)):
                fund["earningsDate"] = _dt.fromtimestamp(ts).strftime("%d/%b/%Y")
            elif isinstance(ts, str):
                fund["earningsDate"] = ts
        except Exception:
            pass

    # Remove None values que possam ter sido inseridos
    fund = {k: v for k, v in fund.items() if v is not None}

    logger.info("yfinance enriqueceu %s com %d campos extras", ticker,
                len(fund) - len({k: v for k, v in fund.items() if k in _MAP or k in ("dividendYield", "sector", "industry", "marketCap")}))

    return fund


async def _get_fundamentals_yfinance(ticker: str) -> Optional[dict]:
    """Fallback: busca dados fundamentalistas diretamente via yfinance quando BRAPI não está configurado."""
    key = f"fundamentals:{ticker}"
    cached = cache.get(key)
    if cached:
        return cached

    fund = await _enrich_from_yfinance(ticker, {})
    if not fund:
        return None

    # yfinance info também pode trazer P/L e LPA diretamente
    import yfinance as yf
    yf_ticker = _resolve_yf_ticker(ticker)

    def _fetch_extra():
        try:
            t = yf.Ticker(yf_ticker)
            info = t.info
            return {
                "priceEarnings": info.get("trailingPE"),
                "earningsPerShare": info.get("trailingEps"),
                "shortName": info.get("shortName"),
                "longName": (info.get("longName") or "")[:100],
                "regularMarketPrice": info.get("currentPrice") or info.get("regularMarketPrice"),
            }
        except Exception:
            return {}

    extra = await asyncio.to_thread(_fetch_extra)
    for k, v in extra.items():
        if v is not None and k not in fund:
            fund[k] = v

    fund = {k: v for k, v in fund.items() if v is not None}
    if fund:
        cache.set(key, fund, ttl=3600)
    return fund if fund else None


async def get_fundamentals(ticker: str) -> Optional[dict]:
    """Dados fundamentalistas de um ativo via BRAPI (modules=financialData,defaultKeyStatistics,summaryProfile).
    Fallback: se modules retornam 400 (ex: bancos), busca sem modules (P/L, LPA, MarketCap) + summaryProfile.
    Se BRAPI não configurado, usa yfinance diretamente.
    Cache 1h.
    """
    if not _BRAPI_CONFIGURED:
        return await _get_fundamentals_yfinance(ticker)

    key = f"fundamentals:{ticker}"
    cached = cache.get(key)
    if cached:
        return cached

    url = f"{BRAPI_BASE_URL}/quote/{ticker}"
    # Token exclusivamente como query param para endpoints de fundamental
    # (Bearer header causa 403/400 em certos tickers como BBAS3)
    base_params = {
        "token": BRAPI_TOKEN,
        "fundamental": "true",
        "dividends": "true",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        raw = None
        modules_ok = False

        # Tentativa 1: com todos os modules
        try:
            params_full = {**base_params, "modules": "financialData,defaultKeyStatistics,summaryProfile"}
            resp = await client.get(url, params=params_full)
            resp.raise_for_status()
            data = resp.json()
            if data.get("results"):
                raw = data["results"][0]
                modules_ok = True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                logger.info("brapi.get_fundamentals %s: modules indisponíveis, tentando sem modules", ticker)
            else:
                logger.warning("brapi.get_fundamentals %s falhou: %s", ticker, e)
                return None
        except Exception as e:
            logger.warning("brapi.get_fundamentals %s falhou: %s", ticker, e)
            return None

        # Tentativa 2 (fallback): sem modules e sem dividends — pega P/L, LPA, MarketCap basicos
        if raw is None:
            try:
                params_basic = {"token": BRAPI_TOKEN, "fundamental": "true"}
                resp = await client.get(url, params=params_basic)
                resp.raise_for_status()
                data = resp.json()
                if data.get("results"):
                    raw = data["results"][0]
            except Exception as e:
                logger.warning("brapi.get_fundamentals %s fallback falhou: %s", ticker, e)
                return None

        if raw is None:
            return None

        # Tentativa 3: summaryProfile separado (se não veio nos modules)
        sp = raw.get("summaryProfile") or {}
        if not sp and not modules_ok:
            try:
                params_sp = {"token": BRAPI_TOKEN, "fundamental": "true", "modules": "summaryProfile"}
                resp = await client.get(url, params=params_sp)
                resp.raise_for_status()
                data_sp = resp.json()
                if data_sp.get("results"):
                    sp = data_sp["results"][0].get("summaryProfile") or {}
            except Exception:
                pass  # summaryProfile é bonus, não essencial

        # Sub-objetos retornados pelos modules (vazios se modules falharam)
        fd = raw.get("financialData") or {}
        ks = raw.get("defaultKeyStatistics") or {}

        # Calcular DY a partir dos dividendos reais dos últimos 12 meses
        # (BRAPI retorna dividendYield às vezes defasado/incorreto — preferir cálculo próprio)
        dy = None
        price = raw.get("regularMarketPrice")
        divs = (raw.get("dividendsData") or {}).get("cashDividends") or []
        if price and price > 0 and divs:
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=365)
            total_12m = 0.0
            for d_item in divs:
                try:
                    dt = datetime.fromisoformat(d_item.get("paymentDate", "2000-01-01T00:00:00.000Z").replace("Z", ""))
                    if dt > cutoff:
                        total_12m += d_item.get("rate", 0)
                except Exception:
                    pass
            if total_12m > 0:
                dy = total_12m / price  # decimal (ex: 0.089 = 8.9%)

        # Fallback: usar valor nativo do BRAPI se não conseguimos calcular
        if dy is None:
            dy = raw.get("dividendYield")

        # Extrai e normaliza os campos fundamentalistas relevantes
        fund = {
            # Valuation (defaultKeyStatistics + raiz)
            "priceEarnings": raw.get("priceEarnings") or ks.get("trailingPE"),   # P/L
            "earningsPerShare": raw.get("earningsPerShare") or ks.get("trailingEps"),  # LPA
            "priceToBookRatio": ks.get("priceToBook"),                    # P/VP
            "enterpriseValueEbitda": ks.get("enterpriseToEbitda"),         # EV/EBITDA
            "enterpriseValueRevenue": ks.get("enterpriseToRevenue"),       # EV/Receita
            "pegRatio": ks.get("pegRatio"),                               # PEG

            # Dividendos
            "dividendYield": dy,                                          # DY (decimal, ex: 0.089 = 8.9%)

            # Rentabilidade (financialData)
            "returnOnEquity": fd.get("returnOnEquity"),                   # ROE (decimal, ex: 0.18)
            "returnOnAssets": fd.get("returnOnAssets"),                    # ROA (decimal)

            # Margens (financialData)
            "netMargin": fd.get("profitMargins") or ks.get("profitMargins"),  # Margem Líquida (decimal)
            "grossMargin": fd.get("grossMargins"),                        # Margem Bruta (decimal)
            "ebitdaMargin": fd.get("ebitdaMargins"),                      # Margem EBITDA (decimal)
            "operatingMargin": fd.get("operatingMargins"),                # Margem Operacional (decimal)

            # Endividamento (financialData)
            "debtToEquity": fd.get("debtToEquity"),                       # Dívida/PL (ex: 1.57)
            "currentLiquidity": fd.get("currentRatio"),                   # Liquidez Corrente

            # Absolutos
            "bookValuePerShare": ks.get("bookValue"),                     # VPA
            "ebitda": fd.get("ebitda"),                                   # EBITDA absoluto
            "totalRevenue": fd.get("totalRevenue"),                       # Receita total
            "netIncome": ks.get("netIncomeToCommon"),                     # Lucro líquido
            "freeCashflow": fd.get("freeCashflow"),                       # FCF

            # Crescimento
            "earningsGrowth": fd.get("earningsGrowth"),                   # Crescimento lucros YoY
            "revenueGrowth": fd.get("revenueGrowth"),                     # Crescimento receita YoY

            # Info
            "sector": sp.get("sector") or raw.get("sector"),
            "industry": sp.get("industry") or raw.get("industry"),
            "shortName": raw.get("shortName"),
            "longName": raw.get("longName") or sp.get("longBusinessSummary", "")[:100],
            "marketCap": raw.get("marketCap") or ks.get("marketCap"),
            "regularMarketPrice": raw.get("regularMarketPrice"),
        }
        # Remove None values
        fund = {k: v for k, v in fund.items() if v is not None}

        # ---------- Enriquecimento via yfinance ----------
        # SEMPRE chama: além de campos-chave de margens/endividamento,
        # yfinance é a única fonte de preço-alvo analistas, earnings date e volume médio.
        fund = await _enrich_from_yfinance(ticker, fund)

        # Guardar dividendos brutos para endpoint /dashboard/dividendos
        if divs:
            fund["_raw_dividends"] = divs

        cache.set(key, fund, ttl=3600)  # Cache 1h
        return fund if fund else None


def formatar_fundamentalista_para_prompt(f: Optional[dict], tipo: str = "ACAO") -> str:
    """Formata dados fundamentalistas em texto para injeção no prompt da IA."""
    if not f:
        return "DADOS FUNDAMENTALISTAS:\nIndisponíveis"

    def _pct(v):
        """Converte decimal (0.18) para % (18.0). Se já vier >1 assume que já é %."""
        if v is None:
            return None
        return v * 100 if abs(v) < 1 else v

    def _fmt_money(v):
        """Formata valor absoluto: bilhões ou milhões."""
        if v is None:
            return None
        v = float(v)
        if abs(v) >= 1e9:
            return f"R$ {v / 1e9:.1f}B"
        if abs(v) >= 1e6:
            return f"R$ {v / 1e6:.0f}M"
        return f"R$ {v:,.0f}"

    linhas = []

    # Identificação da empresa
    ident_parts = []
    if f.get("shortName"):
        ident_parts.append(f["shortName"])
    if f.get("sector"):
        ident_parts.append(f"Setor: {f['sector']}")
    if f.get("industry"):
        ident_parts.append(f"Indústria: {f['industry']}")
    if ident_parts:
        linhas.append(" | ".join(ident_parts))

    # Market Cap
    if f.get("marketCap"):
        mc = _fmt_money(f["marketCap"])
        if mc:
            linhas.append(f"Valor de mercado: {mc}")

    # Valuation
    vals = []
    if f.get("priceEarnings") is not None:
        vals.append(f"P/L={f['priceEarnings']:.1f}")
    if f.get("priceToBookRatio") is not None:
        vals.append(f"P/VP={f['priceToBookRatio']:.2f}")
    if f.get("enterpriseValueEbitda") is not None:
        vals.append(f"EV/EBITDA={f['enterpriseValueEbitda']:.1f}")
    if f.get("enterpriseValueRevenue") is not None:
        vals.append(f"EV/Receita={f['enterpriseValueRevenue']:.2f}")
    if vals:
        linhas.append("Valuation: " + " | ".join(vals))

    # Dividendos
    dy_parts = []
    if f.get("dividendYield") is not None:
        dy = _pct(f["dividendYield"])
        dy_parts.append(f"DY={dy:.2f}%")
    if f.get("payoutRatio") is not None:
        pr = _pct(f["payoutRatio"])
        dy_parts.append(f"Payout={pr:.0f}%")
    if dy_parts:
        linhas.append("Dividendos: " + " | ".join(dy_parts))

    # Rentabilidade
    rents = []
    roe = _pct(f.get("returnOnEquity"))
    roa = _pct(f.get("returnOnAssets"))
    if roe is not None:
        rents.append(f"ROE={roe:.1f}%")
    if roa is not None:
        rents.append(f"ROA={roa:.1f}%")
    if rents:
        linhas.append("Rentabilidade: " + " | ".join(rents))

    # Margens
    margens = []
    ml = _pct(f.get("netMargin"))
    mb = _pct(f.get("grossMargin"))
    me = _pct(f.get("ebitdaMargin"))
    mo = _pct(f.get("operatingMargin"))
    if ml is not None:
        margens.append(f"Líquida={ml:.1f}%")
    if mb is not None:
        margens.append(f"Bruta={mb:.1f}%")
    if me is not None:
        margens.append(f"EBITDA={me:.1f}%")
    if mo is not None:
        margens.append(f"Operacional={mo:.1f}%")
    if margens:
        linhas.append("Margens: " + " | ".join(margens))

    # Endividamento
    divida = []
    if f.get("debtToEquity") is not None:
        divida.append(f"Dív/PL={f['debtToEquity']:.2f}")
    if f.get("currentLiquidity") is not None:
        divida.append(f"Liq.Corrente={f['currentLiquidity']:.2f}")
    if divida:
        linhas.append("Endividamento: " + " | ".join(divida))

    # Crescimento
    cresc = []
    rg = _pct(f.get("revenueGrowth"))
    eg = _pct(f.get("earningsGrowth"))
    if rg is not None:
        cresc.append(f"Receita YoY={rg:+.1f}%")
    if eg is not None:
        cresc.append(f"Lucro YoY={eg:+.1f}%")
    if cresc:
        linhas.append("Crescimento: " + " | ".join(cresc))

    # Financials absolutos
    abs_parts = []
    for label, key in [("EBITDA", "ebitda"), ("Receita", "totalRevenue"), ("Lucro", "netIncome"), ("FCF", "freeCashflow")]:
        val = _fmt_money(f.get(key))
        if val:
            abs_parts.append(f"{label}={val}")
    if abs_parts:
        linhas.append("Absolutos: " + " | ".join(abs_parts))

    # Analistas (preço-alvo)
    analistas_parts = []
    if f.get("targetMeanPrice") is not None:
        tp = f"Preço-alvo médio=R$ {f['targetMeanPrice']:.2f}"
        if f.get("targetLowPrice") is not None and f.get("targetHighPrice") is not None:
            tp += f" (faixa R$ {f['targetLowPrice']:.2f} ~ R$ {f['targetHighPrice']:.2f})"
        analistas_parts.append(tp)
    if f.get("numberOfAnalysts") is not None:
        analistas_parts.append(f"{f['numberOfAnalysts']} analistas")
    rec = f.get("recommendationKey")
    if rec:
        _REC_MAP = {"strongBuy": "COMPRA FORTE", "buy": "COMPRA", "hold": "MANTER", "sell": "VENDA", "strongSell": "VENDA FORTE"}
        analistas_parts.append(f"Recomendação: {_REC_MAP.get(rec, rec.upper())}")
    if analistas_parts:
        linhas.append("Analistas: " + " | ".join(analistas_parts))

    # Volume médio
    if f.get("avgDailyVolume10d") is not None:
        vol = f["avgDailyVolume10d"]
        if vol >= 1e6:
            linhas.append(f"Volume médio 10d: {vol / 1e6:.1f}M")
        elif vol >= 1e3:
            linhas.append(f"Volume médio 10d: {vol / 1e3:.0f}K")

    # Próximo balanço
    if f.get("earningsDate"):
        linhas.append(f"Próximo balanço: {f['earningsDate']}")

    if not linhas:
        return "DADOS FUNDAMENTALISTAS:\nIndisponíveis para este ativo"

    return "DADOS FUNDAMENTALISTAS:\n" + "\n".join(linhas)


async def get_quotes(tickers: list[str]) -> dict[str, dict]:
    """Cotações de múltiplos ativos de uma vez. Cache individual por ticker."""
    if not _BRAPI_CONFIGURED:
        return {}

    # Verifica cache primeiro
    result = {}
    missing = []
    for t in tickers:
        cached = cache.get(f"quote:{t}")
        if cached:
            result[t] = cached
        else:
            missing.append(t)

    if not missing:
        return result

    tickers_str = ",".join(missing)
    url = f"{BRAPI_BASE_URL}/quote/{tickers_str}"

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url, headers=_headers())
            response.raise_for_status()
            data = response.json()
            for item in data.get("results", []):
                t = item.get("symbol", "")
                cache.set(f"quote:{t}", item, ttl=CACHE_TTL_QUOTES)
                result[t] = item
        except Exception as e:
            logger.warning("brapi.get_quotes %s falhou: %s", tickers_str, e)

    return result


async def get_history(ticker: str, period: str = "1y", interval: str = "1d") -> Optional[list]:
    """
    Histórico de preços.
    period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y
    interval: 1d, 1wk, 1mo
    """
    key = f"history:{ticker}:{period}:{interval}"
    cached = cache.get(key)
    if cached:
        return cached

    if not _BRAPI_CONFIGURED:
        return None

    url = f"{BRAPI_BASE_URL}/quote/{ticker}"
    params = {
        "range": period,
        "interval": interval,
        "fundamental": "false",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            response = await client.get(url, params=params, headers=_headers())
            response.raise_for_status()
            data = response.json()
            if data.get("results"):
                hist = data["results"][0].get("historicalDataPrice", [])
                cache.set(key, hist, ttl=CACHE_TTL_INDICATORS)
                return hist
        except Exception:
            return None
    return None


async def search_tickers(query: str) -> list[dict]:
    """Busca de ativos por nome ou ticker."""
    if not _BRAPI_CONFIGURED:
        return []

    key = f"search:{query.lower()}"
    cached = cache.get(key)
    if cached:
        return cached

    url = f"{BRAPI_BASE_URL}/available"
    params = {"search": query}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(url, params=params, headers=_headers())
            response.raise_for_status()
            data = response.json()
            results = data.get("stocks", [])[:20]
            cache.set(key, results, ttl=300)
            return results
        except Exception:
            return []


async def get_ibov() -> Optional[dict]:
    """Cotação do IBOVESPA (^BVSP)."""
    return await get_quote("^BVSP")


async def get_macro_br() -> dict:
    """Dados macro brasileiros — dólar, IBOV, Selic e IPCA."""
    key = "macro:br"
    cached = cache.get(key)
    if cached:
        return cached

    from app.data.bcb_client import get_selic, get_ipca
    from app.data.yfinance_client import get_dolar_yf, get_ibov_yf
    ibov_brapi, selic, ipca, dolar_yf, ibov_yf = await asyncio.gather(
        get_ibov(),
        get_selic(),
        get_ipca(),
        get_dolar_yf(),
        get_ibov_yf(),
    )

    # IBOV: preferir brapi, fallback yfinance
    ibov_price = (ibov_brapi.get("regularMarketPrice") if ibov_brapi else None) or (ibov_yf.get("price") if ibov_yf else None)
    ibov_var = (ibov_brapi.get("regularMarketChangePercent") if ibov_brapi else None) or (ibov_yf.get("change_pct") if ibov_yf else None)

    result = {
        "dolar": dolar_yf.get("price") if dolar_yf else None,
        "dolar_variacao": dolar_yf.get("change_pct") if dolar_yf else None,
        "ibov": ibov_price,
        "ibov_variacao": ibov_var,
        "selic": selic,
        "ipca": ipca,
    }

    cache.set(key, result, ttl=60)
    return result

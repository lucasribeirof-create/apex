"""
Cliente Focus/BCB — Expectativas de mercado via API Olinda.

Endpoint real (NÃO é SGS 432/433):
  https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/

Busca a mediana das expectativas dos Top 5 analistas para:
  - Selic Meta fim do ano corrente
  - IPCA acumulado 12 meses
"""

import httpx
from typing import Optional
from datetime import datetime

from app.data.cache import cache
from app.logger import logger

_OLINDA_BASE = (
    "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/"
)
CACHE_TTL_FOCUS = 3600  # 1h — Focus atualiza 1x/dia


async def get_focus_selic() -> Optional[float]:
    """
    Expectativa da Selic Meta no fim do ano corrente.
    Usa a mediana Top 5 (mais recente disponível).
    """
    key = "focus:selic"
    cached = cache.get(key)
    if cached is not None:
        return cached

    ano = datetime.now().year
    url = (
        f"{_OLINDA_BASE}ExpectativasMercadoTop5Anuais"
        f"?$filter=Indicador eq 'Selic'"
        f" and DataReferencia eq '{ano}'"
        f"&$orderby=Data desc"
        f"&$top=1"
        f"&$select=Mediana"
        f"&$format=json"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("value", [])
            if items and items[0].get("Mediana") is not None:
                valor = float(items[0]["Mediana"])
                cache.set(key, valor, ttl=CACHE_TTL_FOCUS)
                return valor
    except Exception as e:
        logger.warning("focus_bcb.get_focus_selic falhou: %s", e)

    return None


async def get_focus_ipca() -> Optional[float]:
    """
    Expectativa do IPCA acumulado para os próximos 12 meses.
    Usa a mediana Top 5 (mais recente disponível).
    """
    key = "focus:ipca"
    cached = cache.get(key)
    if cached is not None:
        return cached

    ano = datetime.now().year
    url = (
        f"{_OLINDA_BASE}ExpectativasMercadoTop5Anuais"
        f"?$filter=Indicador eq 'IPCA'"
        f" and DataReferencia eq '{ano}'"
        f"&$orderby=Data desc"
        f"&$top=1"
        f"&$select=Mediana"
        f"&$format=json"
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("value", [])
            if items and items[0].get("Mediana") is not None:
                valor = float(items[0]["Mediana"])
                cache.set(key, valor, ttl=CACHE_TTL_FOCUS)
                return valor
    except Exception as e:
        logger.warning("focus_bcb.get_focus_ipca falhou: %s", e)

    return None

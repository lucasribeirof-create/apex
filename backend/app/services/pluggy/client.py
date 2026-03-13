"""
Pluggy Open Finance — Client para integração com corretoras brasileiras.
Usa a API REST do Pluggy (https://docs.pluggy.ai) para:
  - Autenticação via client_id + client_secret
  - Geração do Connect Widget token
  - Busca de itens (conexões) e investimentos
"""
import json
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import httpx

from app.config import DATA_DIR

PLUGGY_BASE_URL = "https://api.pluggy.ai"
PLUGGY_SETTINGS_FILE = DATA_DIR / "pluggy_settings.json"

# ─── Cache de token ────────────────────────────────────────────────────────────
_token_cache: dict = {"access_token": "", "expires_at": 0}


def _load_pluggy_settings() -> dict:
    """Carrega client_id e client_secret do arquivo de settings."""
    if not PLUGGY_SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(PLUGGY_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_pluggy_settings(data: dict) -> None:
    """Salva settings do Pluggy."""
    PLUGGY_SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_pluggy_credentials() -> tuple[str, str]:
    """Retorna (client_id, client_secret) ou ('', '')."""
    s = _load_pluggy_settings()
    return s.get("client_id", ""), s.get("client_secret", "")


def save_pluggy_credentials(client_id: str, client_secret: str) -> None:
    """Salva credenciais do Pluggy."""
    data = _load_pluggy_settings()
    data["client_id"] = client_id
    data["client_secret"] = client_secret
    _save_pluggy_settings(data)


def is_pluggy_configured() -> bool:
    """Verifica se as credenciais estão configuradas."""
    cid, csec = get_pluggy_credentials()
    return bool(cid and csec)


def get_connected_items() -> list[dict]:
    """Retorna a lista de items (conexões) salvos localmente."""
    s = _load_pluggy_settings()
    return s.get("items", [])


def save_connected_item(item: dict) -> None:
    """Salva um item conectado na lista."""
    s = _load_pluggy_settings()
    items = s.get("items", [])
    # Evita duplicatas
    items = [i for i in items if i.get("id") != item.get("id")]
    items.append(item)
    s["items"] = items
    _save_pluggy_settings(s)


def remove_connected_item(item_id: str) -> None:
    """Remove um item conectado."""
    s = _load_pluggy_settings()
    s["items"] = [i for i in s.get("items", []) if i.get("id") != item_id]
    _save_pluggy_settings(s)


# ─── API REST ──────────────────────────────────────────────────────────────────

def _get_access_token() -> str:
    """Obtém access_token do Pluggy, usando cache se válido."""
    global _token_cache
    if _token_cache["access_token"] and time.time() < _token_cache["expires_at"] - 60:
        return _token_cache["access_token"]

    client_id, client_secret = get_pluggy_credentials()
    if not client_id or not client_secret:
        raise ValueError("Pluggy não configurado. Configure client_id e client_secret.")

    resp = httpx.post(
        f"{PLUGGY_BASE_URL}/auth",
        json={"clientId": client_id, "clientSecret": client_secret},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache = {
        "access_token": data["apiKey"],
        "expires_at": time.time() + 7200,  # token dura ~2h
    }
    return _token_cache["access_token"]


def _headers() -> dict:
    token = _get_access_token()
    return {"X-API-KEY": token, "Content-Type": "application/json"}


def test_credentials(client_id: str, client_secret: str) -> tuple[bool, str]:
    """Testa credenciais do Pluggy sem salvar. Retorna (ok, mensagem)."""
    try:
        resp = httpx.post(
            f"{PLUGGY_BASE_URL}/auth",
            json={"clientId": client_id, "clientSecret": client_secret},
            timeout=15,
        )
        if resp.status_code == 200:
            return True, "Credenciais válidas!"
        return False, f"Erro {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, f"Erro de conexão: {str(e)}"


def create_connect_token(item_id: Optional[str] = None) -> dict:
    """
    Cria um token para o Pluggy Connect Widget.
    Se item_id for fornecido, permite reconectar/atualizar.
    """
    body: dict = {}
    if item_id:
        body["itemId"] = item_id

    resp = httpx.post(
        f"{PLUGGY_BASE_URL}/connect_token",
        json=body,
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def get_item(item_id: str) -> dict:
    """Busca detalhes de um item (conexão) do Pluggy."""
    resp = httpx.get(
        f"{PLUGGY_BASE_URL}/items/{item_id}",
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def delete_item(item_id: str) -> None:
    """Deleta um item (conexão) do Pluggy."""
    resp = httpx.delete(
        f"{PLUGGY_BASE_URL}/items/{item_id}",
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()


def get_investments(item_id: str) -> list[dict]:
    """Busca investimentos de um item. Retorna lista de investments do Pluggy."""
    results = []
    page = 1
    while True:
        resp = httpx.get(
            f"{PLUGGY_BASE_URL}/investments",
            params={"itemId": item_id, "pageSize": 100, "page": page},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        if len(results) >= data.get("total", 0):
            break
        page += 1
    return results


def get_transactions(item_id: str) -> list[dict]:
    """Busca transações de investimento de um item."""
    results = []
    page = 1
    while True:
        resp = httpx.get(
            f"{PLUGGY_BASE_URL}/investment-transactions",
            params={"itemId": item_id, "pageSize": 100, "page": page},
            headers=_headers(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        if len(results) >= data.get("total", 0):
            break
        page += 1
    return results


# ─── Mapeamento Pluggy → APEX ──────────────────────────────────────────────────

_COMMODITY_BDRS = {"BSLV39", "GOLD39", "USDB39", "BIAU39", "BGLD39", "BSLY39"}

PLUGGY_TYPE_MAP = {
    "EQUITY": "ACAO",
    "MUTUAL_FUND": "FII",   # pode ser FII ou fundo — refinamos pelo ticker
    "ETF": "ETF",
    "BDR": "BDR",
    "FIXED_INCOME": "RF",
    "TREASURY_BOND": "RF",
    "COE": "RF",
    "REAL_ESTATE_FUND": "FII",
    "OPTION": "OPCAO",
    "PENSION": "RF",
}


def map_investment_to_position(inv: dict) -> Optional[dict]:
    """
    Mapeia um investment do Pluggy para o formato de posição APEX.
    Retorna None se não for mapeável.
    """
    tipo_pluggy = inv.get("type", "")
    tipo_apex = PLUGGY_TYPE_MAP.get(tipo_pluggy, None)

    # Se tipo desconhecido, tenta pelo código
    ticker = inv.get("code") or inv.get("number") or ""
    ticker = ticker.strip().upper()

    if not tipo_apex:
        # Heurística pelo ticker
        if ticker and re.match(r'^[A-Z]{4}11[A-Z]?$', ticker):
            tipo_apex = "FII"
        elif ticker and re.match(r'^[A-Z]{4}3[4-9]$', ticker):
            tipo_apex = "BDR"
        else:
            tipo_apex = "ACAO"

    # Refinar: mutual_fund com ticker tipo KNHF11 é FII, não fundo
    if tipo_pluggy == "MUTUAL_FUND" and ticker:
        if re.match(r'^[A-Z]{4}11[A-Z]?$', ticker):
            tipo_apex = "FII"

    amount = inv.get("amount") or inv.get("quantity") or 0
    balance = inv.get("balance", 0) or 0
    value = inv.get("value", 0) or balance

    if not ticker and not inv.get("name"):
        return None

    # Se não tem ticker, usar o nome como fallback
    if not ticker:
        ticker = (inv.get("name", "") or "").strip()[:20].upper().replace(" ", "_")

    modulo_map = {
        "FII": "fiis",
        "ETF": "etfs",
        "RF": "renda_fixa",
        "BDR": "alpha",
        "ACAO": "dividendos",
        "OPCAO": "wheel",
    }

    # Commodity BDRs vão para módulo etfs, não alpha
    if tipo_apex == "BDR" and ticker in _COMMODITY_BDRS:
        modulo_map_result = "etfs"
    else:
        modulo_map_result = modulo_map.get(tipo_apex, "alpha")

    return {
        "ticker": ticker,
        "nome": inv.get("name", ""),
        "tipo": tipo_apex,
        "modulo": modulo_map_result,
        "quantidade": float(amount),
        "valor_atualizado": float(value),
        "preco_fechamento": float(value) / float(amount) if amount else 0,
        "isin": inv.get("isin") or "",
        "source": "pluggy",
        "external_id": inv.get("id", ""),
        "indexador": inv.get("fixedAnnualRate", {}).get("indexer", "") if isinstance(inv.get("fixedAnnualRate"), dict) else "",
        "taxa": inv.get("fixedAnnualRate", {}).get("rate", 0) if isinstance(inv.get("fixedAnnualRate"), dict) else 0,
    }


def compute_pm_from_transactions(transactions: list[dict]) -> dict[str, float]:
    """
    Calcula preço médio real por ticker a partir das transações do Pluggy.
    Retorna {ticker: preco_medio}.

    Lógica: método da média ponderada com ajuste em vendas parciais.
    - BUY → acumula custo e quantidade
    - SELL → reduz quantidade proporcional, mantém PM
    """
    # Agrupar por investmentId → ticker
    inv_tickers: dict[str, str] = {}
    for tx in transactions:
        inv_id = tx.get("investmentId", "")
        code = (tx.get("code") or tx.get("ticker") or "").strip().upper()
        if inv_id and code:
            inv_tickers[inv_id] = code

    # Calcular PM por ticker
    pm_data: dict[str, dict] = defaultdict(lambda: {"qty": 0.0, "cost": 0.0})

    for tx in transactions:
        tx_type = (tx.get("type") or "").upper()
        inv_id = tx.get("investmentId", "")
        ticker = inv_tickers.get(inv_id, (tx.get("code") or "").strip().upper())
        if not ticker:
            continue

        qty = abs(float(tx.get("quantity", 0) or 0))
        unit_price = abs(float(tx.get("unitPrice", 0) or tx.get("value", 0) or 0))
        if qty == 0:
            continue

        entry = pm_data[ticker]

        if tx_type == "BUY":
            entry["cost"] += qty * unit_price
            entry["qty"] += qty
        elif tx_type == "SELL":
            if entry["qty"] > 0:
                # Reduz custo proporcional ao PM atual
                pm_atual = entry["cost"] / entry["qty"]
                sold_qty = min(qty, entry["qty"])
                entry["cost"] -= sold_qty * pm_atual
                entry["qty"] -= sold_qty

    result: dict[str, float] = {}
    for ticker, data in pm_data.items():
        if data["qty"] > 0:
            result[ticker] = data["cost"] / data["qty"]
    return result

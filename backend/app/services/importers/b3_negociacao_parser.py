"""
Parser do XLSX de Negociação da B3 (Área do Investidor).
Histórico de compras e vendas executadas — usado para calcular preço médio exato.
Colunas: Data do Negócio | Tipo de Movimentação | Mercado | Prazo/Vencimento |
         Instituição | Código de Negociação | Quantidade | Preço | Valor
"""
from datetime import datetime
from io import BytesIO
from typing import Any
from openpyxl import load_workbook


def _parse_float(val: Any) -> float:
    if val is None or val == "-" or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_date(val: Any) -> str:
    """Converte data para string ISO. Aceita 'dd/mm/yyyy' ou datetime."""
    if val is None or val == "-":
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    # dd/mm/yyyy
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return s


def _normalizar_ticker(codigo: str) -> str:
    return codigo.strip().upper()


def _detectar_tipo_transacao(tipo_mov: str) -> str:
    """Mapeia tipo de movimentação da B3 → tipo APEX."""
    t = tipo_mov.strip().lower()
    if t == "compra":
        return "compra"
    if t == "venda":
        return "venda"
    return t  # fallback


def _detectar_tipo_ativo(ticker: str, mercado: str) -> str:
    """Detecta tipo do ativo pelo ticker e mercado."""
    mercado_lower = mercado.lower() if mercado else ""
    # Opções
    if "opção" in mercado_lower or "opcao" in mercado_lower:
        return "OPCAO"
    # Futuros — skip (mini dólar, mini índice)
    if "futuro" in mercado_lower:
        return "FUTURO"
    # BDR: sufixo 34, 39
    if ticker and len(ticker) > 2 and ticker[-2:] in ("34", "39"):
        return "BDR"
    # ETF: sufixo 11 com nomes conhecidos
    if ticker and ticker.endswith("11"):
        # Heurística: ETFs conhecidos
        etf_prefixes = [
            "BOVA", "IVVB", "HASH", "QBTC", "COIN", "GOLD", "CHIP",
            "DIVD", "TECK", "USTK", "WRLD", "SPYI", "DIVO", "SMAL",
            "XFIX", "KNSC", "KDIF", "NDIV", "NASD", "SHOT",
        ]
        for prefix in etf_prefixes:
            if ticker.startswith(prefix):
                return "ETF"
        # FIIs conhecidos
        fii_prefixes = [
            "BTLG", "HGBS", "HGLG", "HGRU", "KNCR", "KNHF", "MXRF",
            "PVBI", "RBRR", "RBRX", "VGHF", "VGIP", "XPML", "XPLG",
            "BODB", "CDII", "JMBI", "TAEE", "KLBN", "SANB",
        ]
        for prefix in fii_prefixes:
            if ticker.startswith(prefix):
                return "FII"
        return "ETF"  # Default para 11
    # Ações: sufixo 3, 4, 5, 6
    if ticker and len(ticker) > 1 and ticker[-1] in "3456":
        return "ACAO"
    return "ACAO"


def _nome_curto_corretora(nome_completo: str) -> str:
    mapa = {
        "BANCO BTG PACTUAL S/A": "BTG",
        "XP INVESTIMENTOS CCTVM S/A": "XP",
        "BANCO SANTANDER (BRASIL) SA": "Santander",
        "ITAU UNIBANCO S.A.": "Itaú",
    }
    if nome_completo in mapa:
        return mapa[nome_completo]
    nome_upper = nome_completo.upper()
    for key, val in mapa.items():
        if key.upper() in nome_upper:
            return val
    parts = nome_completo.split()
    if len(parts) >= 2 and parts[0].upper() == "BANCO":
        return parts[1].title()
    return parts[0].title() if parts else nome_completo


def parse_b3_negociacao(file_bytes: bytes, skip_futuros: bool = True) -> dict:
    """
    Parse do XLSX de Negociação da B3.
    Retorna: {
        "tipo": "b3_negociacao",
        "corretoras": {
            "BANCO BTG PACTUAL S/A": {
                "nome_curto": "BTG",
                "transacoes": [
                    {"data": "2026-03-11", "tipo": "compra", "ticker": "BBAS3",
                     "mercado": "Mercado à Vista", "quantidade": 400.0,
                     "preco": 25.58, "valor": 10232.0, "hash": "..."},
                    ...
                ]
            },
            ...
        },
        "totais": {"transacoes": 455, "corretoras": 1, "compras": 200, "vendas": 150}
    }
    """
    wb = load_workbook(BytesIO(file_bytes), read_only=False, data_only=True)

    corretoras: dict[str, dict] = {}
    total_compras = 0
    total_vendas = 0

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            continue

        headers = [str(h).strip() if h else "" for h in rows[0]]

        # Mapear colunas
        col_map = {}
        for i, h in enumerate(headers):
            h_lower = h.lower()
            if "data" in h_lower and "negócio" in h_lower:
                col_map["data"] = i
            elif "tipo" in h_lower and "moviment" in h_lower:
                col_map["tipo"] = i
            elif h_lower == "mercado":
                col_map["mercado"] = i
            elif "prazo" in h_lower or "vencimento" in h_lower:
                col_map["vencimento"] = i
            elif "institui" in h_lower:
                col_map["instituicao"] = i
            elif "código" in h_lower and "negoci" in h_lower:
                col_map["ticker"] = i
            elif h_lower == "quantidade":
                col_map["quantidade"] = i
            elif "preço" in h_lower:
                col_map["preco"] = i
            elif h_lower == "valor":
                col_map["valor"] = i

        for row in rows[1:]:
            if not row or not row[0]:
                continue

            data = _parse_date(row[col_map.get("data", 0)])
            if not data:
                continue

            tipo_mov = str(row[col_map.get("tipo", 1)]).strip() if col_map.get("tipo") is not None and row[col_map.get("tipo")] else ""
            mercado = str(row[col_map.get("mercado", 2)]).strip() if col_map.get("mercado") is not None and row[col_map.get("mercado")] else ""
            instituicao = str(row[col_map.get("instituicao", 4)]).strip() if col_map.get("instituicao") is not None and row[col_map.get("instituicao")] else ""
            instituicao = instituicao.replace("S.A.", "S/A").replace("S/A.", "S/A").rstrip(".")
            ticker = _normalizar_ticker(str(row[col_map.get("ticker", 5)])) if col_map.get("ticker") is not None and row[col_map.get("ticker")] else ""
            quantidade = _parse_float(row[col_map.get("quantidade", 6)])
            preco = _parse_float(row[col_map.get("preco", 7)])
            valor = _parse_float(row[col_map.get("valor", 8)])

            if not ticker or not tipo_mov:
                continue

            # Detectar tipo do ativo
            tipo_ativo = _detectar_tipo_ativo(ticker, mercado)

            # Skip futuros (day trade de mini dólar/índice)
            if skip_futuros and tipo_ativo == "FUTURO":
                continue

            tipo_transacao = _detectar_tipo_transacao(tipo_mov)

            # Hash para detecção de duplicatas
            import hashlib
            hash_str = f"{data}|{ticker}|{tipo_transacao}|{quantidade}|{preco}|{valor}"
            tx_hash = hashlib.md5(hash_str.encode()).hexdigest()[:16]

            transacao = {
                "data": data,
                "tipo": tipo_transacao,
                "ticker": ticker,
                "tipo_ativo": tipo_ativo,
                "mercado": mercado,
                "quantidade": quantidade,
                "preco": preco,
                "valor": valor,
                "hash": tx_hash,
            }

            if instituicao not in corretoras:
                corretoras[instituicao] = {
                    "nome_curto": _nome_curto_corretora(instituicao),
                    "transacoes": [],
                }
            corretoras[instituicao]["transacoes"].append(transacao)

            if tipo_transacao == "compra":
                total_compras += 1
            elif tipo_transacao == "venda":
                total_vendas += 1

    wb.close()

    total_transacoes = sum(len(c["transacoes"]) for c in corretoras.values())

    return {
        "tipo": "b3_negociacao",
        "corretoras": corretoras,
        "totais": {
            "transacoes": total_transacoes,
            "corretoras": len(corretoras),
            "compras": total_compras,
            "vendas": total_vendas,
        },
    }

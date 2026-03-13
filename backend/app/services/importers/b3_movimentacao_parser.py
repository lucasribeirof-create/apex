"""
Parser do XLSX de Movimentação da B3 (Área do Investidor).
Colunas: Entrada/Saída | Data | Movimentação | Produto | Instituição | Quantidade | Preço unitário | Valor da Operação

Tipos relevantes para o APEX:
- Dividendo, Juros Sobre Capital Próprio, Rendimento → proventos
- Bonificação em Ativos, Desdobro → eventos corporativos
- Compra, Venda → transações (mas Negociação é melhor para isso)
- Transferência, Empréstimo → informativo, não afeta P&L
"""
import hashlib
import re
from datetime import datetime
from io import BytesIO
from typing import Any
from openpyxl import load_workbook


# Tipos de movimentação que representam proventos (dividendos/JCP/rendimentos)
TIPOS_PROVENTO = {
    "dividendo", "juros sobre capital próprio", "rendimento",
    "dividendo - transferido", "juros sobre capital próprio - transferido",
    "rendimento - transferido", "reembolso",
    "pagamento de juros", "pagamento de prêmio/rendimentos",
}

# Tipos de movimentação que representam eventos corporativos
TIPOS_EVENTO = {
    "bonificação em ativos", "desdobro", "fração em ativos",
    "cessão de direitos", "direito de subscrição",
    "direitos de subscrição - não exercido", "leilão de fração",
}

# Tipos que representam compra/venda (o Negociação é melhor para isso)
TIPOS_TRANSACAO = {
    "compra", "venda", "compra / venda",
    "compra/venda definitiva/cessao",
    "mda compra/venda definitiva mercado primario",
}

# Tipos de renda fixa
TIPOS_RF = {
    "aplicação", "resgate", "resgate antecipado",
    "vencimento", "vencimento/resgate saldo em conta", "atualização",
}

# Skip: transferências internas, empréstimos (não afetam P&L real)
TIPOS_SKIP = {
    "transferência", "transferência - liquidação", "empréstimo",
}


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
    if val is None or val == "-":
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return s


def _extrair_ticker_do_produto(produto: str) -> str:
    """Extrai ticker de 'BBAS3 - BANCO DO BRASIL S/A' ou 'CDB - CDB1267NAD6 - BANCO XP S/A'"""
    if not produto:
        return ""
    produto = produto.strip()
    # CDB/Debênture: 'CDB - CDB1267NAD6 - BANCO XP S/A'
    if produto.upper().startswith(("CDB", "LCI", "LCA", "DEB", "CRI", "CRA", "LC ")):
        # Retornar o código: ex CDB1267NAD6
        parts = produto.split(" - ")
        if len(parts) >= 2:
            return parts[1].strip()
        return produto
    # Ações/ETF/FII: 'BBAS3 - BANCO DO BRASIL S/A'
    match = re.match(r"^(\w+)\s*-", produto)
    return match.group(1).strip().upper() if match else produto.split()[0].upper()


def _nome_curto_corretora(nome_completo: str) -> str:
    # Normalizar variações S/A, S.A., S/A. etc.
    nome_norm = nome_completo.replace("S.A.", "S/A").replace("S/A.", "S/A").rstrip(".")
    mapa = {
        "BANCO BTG PACTUAL S/A": "BTG",
        "XP INVESTIMENTOS CCTVM S/A": "XP",
        "BANCO SANTANDER (BRASIL) SA": "Santander",
        "ITAU UNIBANCO S/A": "Itaú",
    }
    if nome_norm in mapa:
        return mapa[nome_norm]
    nome_upper = nome_norm.upper()
    for key, val in mapa.items():
        if key.upper() in nome_upper:
            return val
    parts = nome_completo.split()
    if len(parts) >= 2 and parts[0].upper() == "BANCO":
        return parts[1].title()
    return parts[0].title() if parts else nome_completo


def _categorizar_movimentacao(tipo_mov: str) -> str:
    """Categoriza o tipo de movimentação em: provento | evento | transacao | rf | skip"""
    t = tipo_mov.strip().lower()
    if t in TIPOS_PROVENTO:
        return "provento"
    if t in TIPOS_EVENTO:
        return "evento"
    if t in TIPOS_TRANSACAO:
        return "transacao"
    if t in TIPOS_RF:
        return "rf"
    if t in TIPOS_SKIP:
        return "skip"
    return "outro"


def parse_b3_movimentacao(file_bytes: bytes) -> dict:
    """
    Parse do XLSX de Movimentação da B3.
    Retorna: {
        "tipo": "b3_movimentacao",
        "corretoras": {
            "BANCO BTG PACTUAL S/A": {
                "nome_curto": "BTG",
                "movimentacoes": [
                    {"data": "2026-03-11", "tipo_mov": "Dividendo",
                     "categoria": "provento", "direcao": "Credito",
                     "ticker": "BBAS3", "quantidade": 700.0,
                     "preco": 0.07, "valor": 40.5, "hash": "..."},
                    ...
                ]
            },
            ...
        },
        "resumo": {
            "proventos": 150, "eventos": 10, "transacoes": 50,
            "total_proventos_valor": 12345.67
        }
    }
    """
    wb = load_workbook(BytesIO(file_bytes), read_only=False, data_only=True)

    corretoras: dict[str, dict] = {}
    resumo = {"proventos": 0, "eventos": 0, "transacoes": 0, "rf": 0,
              "total_proventos_valor": 0.0, "skipped": 0}

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
            if "entrada" in h_lower or "saída" in h_lower:
                col_map["direcao"] = i
            elif h_lower == "data":
                col_map["data"] = i
            elif "movimentação" in h_lower:
                col_map["tipo_mov"] = i
            elif "produto" in h_lower:
                col_map["produto"] = i
            elif "institui" in h_lower:
                col_map["instituicao"] = i
            elif "quantidade" in h_lower:
                col_map["quantidade"] = i
            elif "preço" in h_lower:
                col_map["preco"] = i
            elif "valor" in h_lower:
                col_map["valor"] = i

        for row in rows[1:]:
            if not row or not row[0]:
                continue

            direcao = str(row[col_map.get("direcao", 0)]).strip() if col_map.get("direcao") is not None else ""
            data = _parse_date(row[col_map.get("data", 1)])
            tipo_mov = str(row[col_map.get("tipo_mov", 2)]).strip() if col_map.get("tipo_mov") is not None and row[col_map.get("tipo_mov")] else ""
            produto = str(row[col_map.get("produto", 3)]).strip() if col_map.get("produto") is not None and row[col_map.get("produto")] else ""
            instituicao = str(row[col_map.get("instituicao", 4)]).strip() if col_map.get("instituicao") is not None and row[col_map.get("instituicao")] else ""
            # Normalizar variações S/A vs S.A.
            instituicao = instituicao.replace("S.A.", "S/A").replace("S/A.", "S/A").rstrip(".")
            quantidade = _parse_float(row[col_map.get("quantidade", 5)])
            preco = _parse_float(row[col_map.get("preco", 6)])
            valor = _parse_float(row[col_map.get("valor", 7)])

            if not data or not tipo_mov:
                continue

            categoria = _categorizar_movimentacao(tipo_mov)

            if categoria == "skip":
                resumo["skipped"] += 1
                continue

            ticker = _extrair_ticker_do_produto(produto)

            # Hash para duplicatas
            hash_str = f"{data}|{ticker}|{tipo_mov}|{direcao}|{quantidade}|{valor}"
            tx_hash = hashlib.md5(hash_str.encode()).hexdigest()[:16]

            movimentacao = {
                "data": data,
                "tipo_mov": tipo_mov,
                "categoria": categoria,
                "direcao": direcao,
                "ticker": ticker,
                "produto": produto,
                "quantidade": quantidade,
                "preco": preco,
                "valor": valor,
                "hash": tx_hash,
            }

            if instituicao not in corretoras:
                corretoras[instituicao] = {
                    "nome_curto": _nome_curto_corretora(instituicao),
                    "movimentacoes": [],
                }
            corretoras[instituicao]["movimentacoes"].append(movimentacao)

            # Contadores
            if categoria == "provento":
                resumo["proventos"] += 1
                resumo["total_proventos_valor"] += valor
            elif categoria == "evento":
                resumo["eventos"] += 1
            elif categoria == "transacao":
                resumo["transacoes"] += 1
            elif categoria == "rf":
                resumo["rf"] += 1

    wb.close()

    resumo["total_proventos_valor"] = round(resumo["total_proventos_valor"], 2)

    return {
        "tipo": "b3_movimentacao",
        "corretoras": corretoras,
        "resumo": resumo,
    }

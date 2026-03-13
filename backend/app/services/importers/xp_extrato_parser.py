"""
Parser do XLSX de Extrato da XP Investimentos.
Arquivo: Extrato XXXXXXX (...).xlsx — sheet "Planilha1"

Estrutura:
- Header row 14: Movimentação, Liquidação, Lançamento, _, Valor (R$), Saldo (R$)
- Data rows from 15+: date, date, description, _, value, balance
- Tipos: RENDIMENTOS DE CLIENTES (proventos), OPERAÇÕES EM BOLSA (trades),
         RESGATE CDB (RF), IR - RESGATE (imposto), Pgto Juros (cupom RF)

Retorna o mesmo formato do B3 movimentacao parser para compatibilidade.
"""
import hashlib
import re
from datetime import datetime
from io import BytesIO
from typing import Any
from openpyxl import load_workbook


def _parse_date(val: Any) -> str:
    if val is None or val == "" or val == "-":
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val).strip()
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            return f"{parts[2]}-{parts[1]}-{parts[0]}"
    return s


def _classify_lancamento(desc: str) -> dict | None:
    """
    Classifica a descrição do lançamento do extrato XP.
    Retorna dict com tipo/ticker/info ou None para skip.
    """
    desc = desc.strip()

    # RENDIMENTOS DE CLIENTES XPML11 S/ 450
    m = re.match(r'RENDIMENTOS DE CLIENTES\s+(\w+)\s+S/\s+([\d.,]+)', desc)
    if m:
        ticker = m.group(1).strip()
        # Quantidade no texto é informativa
        return {
            "tipo_mov": "provento",
            "ticker": ticker,
            "descricao": desc,
            "subtipo": "rendimento",
        }

    # Crédito Ref. Taxa de Remuneração BTC TECK → aluguel de ação
    m = re.match(r'Crédito Ref\. Taxa de Remuneração BTC\s+(\w+)', desc)
    if m:
        return {
            "tipo_mov": "provento",
            "ticker": m.group(1).strip(),
            "descricao": desc,
            "subtipo": "aluguel",
        }

    # OPERAÇÕES EM BOLSA PR dd/mm/yyyy NOTA Nº XXXXXXXX → trade (skip - details in nota)
    if desc.startswith("OPERAÇÕES EM BOLSA"):
        return {
            "tipo_mov": "operacao_bolsa",
            "ticker": "",
            "descricao": desc,
            "subtipo": "bolsa",
        }

    # RESGATE CDB... → resgate de renda fixa
    m = re.match(r'RESGATE\s+(\S+)\s*\|\s*(.+)', desc)
    if m:
        return {
            "tipo_mov": "resgate_rf",
            "ticker": m.group(1).strip(),
            "descricao": desc,
            "subtipo": "resgate",
            "nome_titulo": m.group(2).strip(),
        }

    # IR - RESGATE CDB... → imposto sobre resgate
    m = re.match(r'IR - RESGATE\s+(\S+)\s*\|\s*(.+)', desc)
    if m:
        return {
            "tipo_mov": "ir_resgate",
            "ticker": m.group(1).strip(),
            "descricao": desc,
            "subtipo": "ir",
            "nome_titulo": m.group(2).strip(),
        }

    # Pgto Juros XXXXXX | NTN-B - AGO/2026 → cupom de renda fixa
    m = re.match(r'Pgto Juros\s+(\S+)\s*\|\s*(.+)', desc)
    if m:
        return {
            "tipo_mov": "cupom_rf",
            "ticker": m.group(1).strip(),
            "descricao": desc,
            "subtipo": "cupom",
            "nome_titulo": m.group(2).strip(),
        }

    # IR - Pgto Juros XXXXXX | NTN-B
    m = re.match(r'IR - Pgto Juros\s+(\S+)\s*\|\s*(.+)', desc)
    if m:
        return {
            "tipo_mov": "ir_cupom",
            "ticker": m.group(1).strip(),
            "descricao": desc,
            "subtipo": "ir_cupom",
            "nome_titulo": m.group(2).strip(),
        }

    # Aplicação / Depósito / TED → skip
    return None


def parse_xp_extrato(file_bytes: bytes) -> dict:
    """
    Parse do XLSX de Extrato da XP.
    Retorna formato compatível com b3_movimentacao:
    {
        "tipo": "b3_movimentacao",
        "corretoras": {
            "XP INVESTIMENTOS CCTVM S/A": {
                "nome_curto": "XP",
                "movimentacoes": [...]
            }
        },
        "resumo": {...}
    }
    """
    wb = load_workbook(BytesIO(file_bytes), read_only=False, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    movimentacoes = []

    # Encontrar header row (procurar "Movimentação" + "Liquidação")
    header_row_idx = None
    for i, row in enumerate(rows):
        vals = [str(v).strip().lower() if v else "" for v in row]
        if "movimentação" in vals and "liquidação" in vals:
            header_row_idx = i
            break

    if header_row_idx is None:
        # Fallback: começar na row 14 (padrão XP)
        header_row_idx = 13

    # Processar rows de dados
    for row in rows[header_row_idx + 1:]:
        # Cols: _, Movimentação(date), Liquidação(date), Lançamento(desc), _, Valor, Saldo
        if not row or len(row) < 7:
            continue

        data_mov = row[1]
        data_liq = row[2]
        lancamento = row[3]
        valor = row[5]
        saldo = row[6]

        if data_mov is None or lancamento is None:
            continue
        if not isinstance(data_mov, datetime) and not str(data_mov).strip():
            continue

        desc = str(lancamento).strip()
        if not desc or desc == "Não há lançamentos para o período":
            continue

        classificacao = _classify_lancamento(desc)
        if classificacao is None:
            continue

        data_str = _parse_date(data_mov)
        data_liq_str = _parse_date(data_liq)
        valor_f = float(valor) if isinstance(valor, (int, float)) else 0.0

        # Hash para dedup
        hash_str = hashlib.md5(f"{data_str}|{desc}|{valor_f}".encode()).hexdigest()[:16]

        # Mapear tipo_mov XP → categoria compatível com _confirm_movimentacao
        tipo_mov_raw = classificacao["tipo_mov"]
        cat_map = {
            "provento": "provento",
            "operacao_bolsa": "transacao",
            "resgate_rf": "rf",
            "ir_resgate": "rf",
            "cupom_rf": "provento",
            "ir_cupom": "rf",
        }
        categoria = cat_map.get(tipo_mov_raw, "outro")
        direcao = "Credito" if valor_f > 0 else "Debito"

        mov = {
            "data": data_str,
            "tipo_mov": classificacao.get("subtipo", tipo_mov_raw),
            "categoria": categoria,
            "direcao": direcao,
            "ticker": classificacao["ticker"],
            "produto": desc,
            "quantidade": 0.0,
            "preco": 0.0,
            "valor": abs(valor_f),
            "hash": hash_str,
        }

        movimentacoes.append(mov)

    # Resumo
    proventos = [m for m in movimentacoes if m["categoria"] == "provento"]
    valor_proventos = sum(m["valor"] for m in proventos)
    operacoes = [m for m in movimentacoes if m["categoria"] == "transacao"]
    valor_operacoes = sum(m["valor"] for m in operacoes)

    return {
        "tipo": "b3_movimentacao",  # Compatível com pipeline
        "corretoras": {
            "XP INVESTIMENTOS CCTVM S/A": {
                "nome_curto": "XP",
                "movimentacoes": movimentacoes,
            }
        },
        "resumo": {
            "total_movimentacoes": len(movimentacoes),
            "proventos": len(proventos),
            "valor_proventos": valor_proventos,
            "operacoes_bolsa": len(operacoes),
            "valor_operacoes": valor_operacoes,
        }
    }

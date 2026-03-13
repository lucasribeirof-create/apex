"""
Parser do XLSX de Posição Detalhada da XP Investimentos.
Arquivo: PosicaoDetalhada.xlsx — sheet "Sua carteira"

Estrutura:
- Seções separadas por tipo de ativo: Fundos Imobiliários, Ações, Renda Fixa, Fundos de Investimentos
- Cada seção tem seu próprio header (row com nomes de colunas)
- Valores em formato brasileiro: "R$ 51.121,00"

Retorna o mesmo formato do B3 parser para compatibilidade com o pipeline de import.
"""
import re
from io import BytesIO
from typing import Any
from openpyxl import load_workbook


def _parse_brl(val: Any) -> float:
    """Converte 'R$ 51.121,00' ou '5,92%' → float."""
    if val is None or val == "-" or val == "" or val == "Indefinido":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    s = s.replace("R$", "").replace("%", "").strip()
    # "51.121,00" → "51121.00"
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _detectar_tipo_ativo(ticker: str, secao: str) -> str:
    """Detecta tipo APEX baseado na seção e ticker."""
    secao_lower = secao.lower()
    if "fundo" in secao_lower and "imobili" in secao_lower:
        return "FII"
    if "fundo" in secao_lower and "investimento" in secao_lower:
        return "FUNDO"
    if "ações" in secao_lower or "renda variável" in secao_lower:
        # ETFs terminam em 11 geralmente mas são ETFs conhecidos
        etf_tickers = {"BOVA11", "IVVB11", "SMAL11", "HASH11", "DIVO11", "FIND11",
                       "WRLD11", "CHIP11", "GOLD11", "SPYI11", "TECK11", "USTK11",
                       "DIVD11", "NASD11", "XINA11", "EURP11", "MATB11", "ECOO11"}
        if ticker in etf_tickers or ticker.endswith("11"):
            # BDR de ETF: geralmente termina em 39
            if ticker.endswith("39"):
                return "BDR"
            # Check known ETFs or 11-suffix in Ações section
            if ticker in etf_tickers:
                return "ETF"
        if ticker.endswith("39") or ticker.endswith("34"):
            return "BDR"
        return "ACAO"
    if "renda fixa" in secao_lower or "inflação" in secao_lower or "pós-fixado" in secao_lower or "prefixado" in secao_lower:
        return "RF"
    return "ACAO"


def _detectar_modulo(tipo: str, ticker: str = "") -> str:
    # BDRs de commodities/índices internacionais → módulo etfs
    _COMMODITY_BDRS = {"BSLV39", "GOLD39", "USDB39", "BIAU39", "BGLD39", "BSLY39"}
    if tipo == "BDR" and ticker.upper() in _COMMODITY_BDRS:
        return "etfs"
    modulo_map = {
        "FII": "fiis",
        "ETF": "etfs",
        "RF": "renda_fixa",
        "BDR": "alpha",
        "ACAO": "dividendos",
        "FUNDO": "alpha",
    }
    return modulo_map.get(tipo, "alpha")


def _is_section_header(val: str) -> str | None:
    """Retorna nome da seção se a row é um header de seção, ou None."""
    if not val:
        return None
    s = val.strip()
    section_keywords = [
        "Fundos Imobiliários",
        "Fundos de Investimentos",
        "Ações",
        "Renda Fixa",
        "Dividendos",
        "Proventos",
        "Custódia Remunerada",
    ]
    for kw in section_keywords:
        if s.startswith(kw):
            return kw
    return None


def _is_subsection_header(row: tuple) -> bool:
    """Verifica se é uma sub-seção header (ex: '46,2% | Fundos Listados', 'Posição', ...)"""
    if not row or not row[0]:
        return False
    val = str(row[0]).strip()
    # Padrão: "XX,X% | Nome" ou headers conhecidos como "Posição", etc
    if re.match(r'^\d+[.,]\d+%\s*\|', val):
        return True
    return False


def _is_rf_subsection_header(row: tuple) -> bool:
    """Verifica se é um sub-header de Renda Fixa (Inflação, Pós-Fixado, Prefixado)."""
    if not row or not row[0]:
        return False
    val = str(row[0]).strip()
    if re.match(r'^\d+[.,]\d+%\s*\|\s*(Inflação|Pós-Fixado|Prefixado)', val):
        return True
    return False


def _is_empty_row(row: tuple) -> bool:
    """Verifica se row é vazia ou só espaços."""
    return all(v is None or str(v).strip() in ("", " ") for v in row)


def parse_xp_posicao(file_bytes: bytes) -> dict:
    """
    Parse do XLSX de Posição da XP.
    Retorna formato idêntico ao B3 parser:
    {
        "tipo": "b3_posicao",
        "corretoras": {
            "XP INVESTIMENTOS": {
                "nome_curto": "XP",
                "posicoes": [...]
            }
        },
        "totais": {"posicoes": N, "corretoras": 1, "valor_total": X}
    }
    """
    wb = load_workbook(BytesIO(file_bytes), read_only=False, data_only=True)

    # XP tem sheet "Sua carteira"
    ws = None
    for name in wb.sheetnames:
        if "carteira" in name.lower():
            ws = wb[name]
            break
    if ws is None:
        ws = wb[wb.sheetnames[0]]

    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    posicoes = []
    current_section = None
    current_subsection = None
    i = 0

    while i < len(rows):
        row = rows[i]
        if _is_empty_row(row):
            i += 1
            continue

        val0 = str(row[0]).strip() if row[0] else ""

        # Detectar seção principal
        section = _is_section_header(val0)
        if section:
            current_section = section
            current_subsection = None
            i += 1
            continue

        # Skip headers de informação do cliente (row 1-4)
        if "patrimônio" in val0.lower() or "Total investido" in val0 or "Conta:" in str(row[5] if len(row) > 5 and row[5] else ""):
            i += 1
            continue

        # Detectar sub-seção header (tem colunas headers)
        if _is_subsection_header(row):
            current_subsection = val0
            i += 1
            continue

        # Se não temos seção, ignorar
        if not current_section:
            i += 1
            continue

        # Skip seções de dividendos/proventos/custódia (não são posições)
        if current_section in ("Dividendos", "Proventos", "Custódia Remunerada"):
            i += 1
            continue

        # Parse da row de dados baseado na seção
        if current_section == "Fundos Imobiliários" and current_subsection:
            # Cols: ticker, Posição, % Alocação, Rent c/ proventos, Rent Bruta, PM abertura, Última cotação, Qtd Cotas
            ticker = val0
            if not ticker or ticker.startswith("Total") or "%" in ticker[:5]:
                i += 1
                continue
            posicao_val = _parse_brl(row[1]) if len(row) > 1 else 0
            preco_medio = _parse_brl(row[5]) if len(row) > 5 else 0
            ultimo_preco = _parse_brl(row[6]) if len(row) > 6 else 0
            quantidade = _parse_brl(row[7]) if len(row) > 7 else 0
            if quantidade <= 0:
                i += 1
                continue
            posicoes.append({
                "ticker": ticker,
                "nome": ticker,
                "tipo": "FII",
                "modulo": "fiis",
                "quantidade": quantidade,
                "preco_medio": preco_medio,
                "preco_fechamento": ultimo_preco,
                "valor_atualizado": posicao_val,
                "sheet": "FII",
            })

        elif current_section == "Ações" and current_subsection:
            # Cols: ticker, Posição, % Alocação, Rentabilidade (%), Preço médio, Último preço, Qtd. total
            ticker = val0
            if not ticker or ticker.startswith("Total") or "%" in ticker[:5]:
                i += 1
                continue
            posicao_val = _parse_brl(row[1]) if len(row) > 1 else 0
            preco_medio = _parse_brl(row[4]) if len(row) > 4 else 0
            ultimo_preco = _parse_brl(row[5]) if len(row) > 5 else 0
            quantidade = _parse_brl(row[6]) if len(row) > 6 else 0
            if quantidade <= 0:
                i += 1
                continue
            tipo = _detectar_tipo_ativo(ticker, current_section)
            posicoes.append({
                "ticker": ticker,
                "nome": ticker,
                "tipo": tipo,
                "modulo": _detectar_modulo(tipo, ticker),
                "quantidade": quantidade,
                "preco_medio": preco_medio,
                "preco_fechamento": ultimo_preco,
                "valor_atualizado": posicao_val,
                "sheet": "Ações",
            })

        elif current_section == "Renda Fixa":
            # Cols: nome título, Posição a mercado, %, Valor aplicado, Valor aplicado original, 
            #        Taxa a mercado, Data aplicação, Data vencimento, Quantidade, Preço Unitário, IR, IOF, Valor Líquido
            nome_titulo = val0
            if not nome_titulo or nome_titulo.startswith("Total") or "%" in nome_titulo[:5]:
                i += 1
                continue
            # Detect RF sub-type header
            if _is_rf_subsection_header(row):
                current_subsection = val0
                i += 1
                continue

            posicao_mercado = _parse_brl(row[1]) if len(row) > 1 else 0
            valor_aplicado = _parse_brl(row[3]) if len(row) > 3 else 0
            taxa = str(row[5]).strip() if len(row) > 5 and row[5] else ""
            data_aplicacao = str(row[6]).strip() if len(row) > 6 and row[6] else ""
            data_vencimento = str(row[7]).strip() if len(row) > 7 and row[7] else ""
            quantidade = _parse_brl(row[8]) if len(row) > 8 else 0
            preco_unitario = _parse_brl(row[9]) if len(row) > 9 else 0
            valor_liquido = _parse_brl(row[12]) if len(row) > 12 else 0

            if posicao_mercado <= 0 and valor_liquido <= 0:
                i += 1
                continue

            # Gerar ticker sintético para RF
            ticker_rf = re.sub(r'[^A-Z0-9]', '', nome_titulo.upper().split('-')[0].strip())[:12]
            if not ticker_rf:
                ticker_rf = "RF"

            # Detectar indexador
            indexador = ""
            if "IPC" in taxa.upper() or "IPCA" in taxa.upper():
                indexador = "IPCA"
            elif "CDI" in taxa.upper():
                indexador = "CDI"
            elif taxa.startswith("+") or re.match(r'^\d', taxa):
                indexador = "PRE"

            posicoes.append({
                "ticker": ticker_rf,
                "nome": nome_titulo,
                "tipo": "RF",
                "modulo": "renda_fixa",
                "quantidade": quantidade if quantidade > 0 else 1,
                "preco_medio": preco_unitario if preco_unitario > 0 else valor_aplicado,
                "preco_fechamento": preco_unitario if preco_unitario > 0 else posicao_mercado,
                "valor_atualizado": posicao_mercado if posicao_mercado > 0 else valor_liquido,
                "valor_aplicado": valor_aplicado,
                "valor_liquido": valor_liquido,
                "indexador": indexador,
                "taxa": taxa,
                "data_aplicacao": data_aplicacao,
                "data_vencimento": data_vencimento,
                "sheet": "RF",
            })

        elif current_section == "Fundos de Investimentos" and current_subsection:
            # Cols: nome fundo, Posição, % Alocação, Rent Líquida, Rent Bruta, Valor aplicado, Valor líquido
            nome_fundo = val0
            if not nome_fundo or nome_fundo.startswith("Total") or "%" in nome_fundo[:5]:
                i += 1
                continue
            posicao_val = _parse_brl(row[1]) if len(row) > 1 else 0
            valor_aplicado = _parse_brl(row[5]) if len(row) > 5 else 0
            valor_liquido = _parse_brl(row[6]) if len(row) > 6 else 0

            if posicao_val <= 0 and valor_liquido <= 0:
                i += 1
                continue

            # Ticker sintético para fundos
            ticker_fundo = re.sub(r'[^A-Z0-9]', '', nome_fundo.upper().split('-')[0].strip())[:12]
            if not ticker_fundo:
                ticker_fundo = "FUNDO"

            posicoes.append({
                "ticker": ticker_fundo,
                "nome": nome_fundo,
                "tipo": "FUNDO",
                "modulo": "alpha",
                "quantidade": 1,
                "preco_medio": valor_aplicado if valor_aplicado > 0 else posicao_val,
                "preco_fechamento": posicao_val,
                "valor_atualizado": posicao_val,
                "valor_aplicado": valor_aplicado,
                "valor_liquido": valor_liquido,
                "sheet": "Fundos",
            })

        i += 1

    valor_total = sum(p["valor_atualizado"] for p in posicoes)

    return {
        "tipo": "b3_posicao",  # Compatível com pipeline existente
        "corretoras": {
            "XP INVESTIMENTOS CCTVM S/A": {
                "nome_curto": "XP",
                "posicoes": posicoes,
            }
        },
        "totais": {
            "posicoes": len(posicoes),
            "corretoras": 1,
            "valor_total": valor_total,
        }
    }

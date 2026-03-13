"""
Parser do XLSX de Posição da B3 (Área do Investidor).
Lê todas as sheets (Acoes, BDR, ETF, Fundo de Investimento, Opções, Renda Fixa, Empréstimos)
e agrupa por Instituição para separar corretoras.
"""
import re
from io import BytesIO
from typing import Any
from openpyxl import load_workbook


# Mapeamento sheet → tipo APEX
SHEET_TIPO_MAP = {
    "Acoes": "ACAO",
    "BDR": "BDR",
    "ETF": "ETF",
    "Fundo de Investimento": "FII",  # FIIs + FI-Infra na B3 ficam nessa sheet
    "Opções": "OPCAO",
    "Renda Fixa": "RF",
    "Empréstimos": None,  # Empréstimos de ativos — skip (são posições temporárias)
}


def _normalizar_ticker(codigo: str) -> str:
    """Remove espaços e normaliza o ticker."""
    return codigo.strip().upper()


def _detectar_tipo(ticker: str, sheet_tipo: str, subtipo: str = "", isin: str = "") -> str:
    """Detecta tipo APEX baseado na sheet + subtipo + ticker + ISIN.
    FIIs podem aparecer na sheet 'Acoes' (ex: KNHF11, HGLG11) — detectar via ISIN ou ticker."""
    if sheet_tipo == "FII":
        return "FII"
    if sheet_tipo == "ETF":
        return "ETF"
    if sheet_tipo == "BDR":
        return "BDR"
    if sheet_tipo == "ACAO":
        # FIIs na sheet Ações: ISIN começa com "BRFII" ou ticker é FII conhecido (11 no final + padrão FII)
        if isin and isin.startswith("BR") and "FII" in isin.upper():
            return "FII"
        # Tickers FII: 4 letras + 11 (ex: KNHF11, HGLG11, MXRF11, XPML11)
        # Excluir UNITs (TAEE11, KLBN11, SAPR11) que são ações — UNITs têm ISIN com "ACNOR" ou "UNT"
        if re.match(r'^[A-Z]{4}11$', ticker):
            # Se tem ISIN e contém "UNT" ou "UNIT", é UNIT (ação)
            if isin and ("UNT" in isin.upper() or "UNIT" in isin.upper()):
                return "ACAO"
            # Se tem ISIN e contém "FII" ou "CRI" ou "CRA", é FII
            if isin and any(x in isin.upper() for x in ("FII", "CRI", "CRA")):
                return "FII"
            # Sem ISIN: usar subtipo — se "CI" (Cotas de Investimento) = FII
            if subtipo and subtipo.upper() in ("CI", "COTAS"):
                return "FII"
            # Heurística final: tickers FII geralmente têm certas letras — retorna ACAO como safe default
            # (melhor classificar como ACAO do que errar FII para UNITs)
            return "ACAO"
        return "ACAO"
    return sheet_tipo


def _detectar_modulo(tipo: str, ticker: str = "") -> str:
    """Sugere módulo baseado no tipo."""
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
        "OPCAO": "wheel",
    }
    return modulo_map.get(tipo, "alpha")


def _parse_float(val: Any) -> float:
    """Converte valor para float, tratando '-', None e strings."""
    if val is None or val == "-" or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    # String: remover pontos de milhar, trocar vírgula por ponto
    s = str(val).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _extrair_ticker_do_produto(produto: str) -> str:
    """Extrai ticker do campo Produto. Ex: 'BBSE3 - BB SEGURIDADE...' → 'BBSE3'"""
    if not produto:
        return ""
    # Para opções: 'Opção de Compra - BBASD252' → 'BBASD252'
    if produto.startswith("Opção"):
        match = re.search(r"- (\w+)", produto)
        return match.group(1).strip() if match else ""
    # Para ações/BDR/ETF/FII: 'BBSE3 - BB SEGURIDADE...'
    parts = produto.split(" - ", 1)
    return parts[0].strip() if parts else ""


def _extrair_nome_do_produto(produto: str) -> str:
    """Extrai nome do campo Produto. Ex: 'BBSE3 - BB SEGURIDADE...' → 'BB SEGURIDADE...'"""
    if not produto:
        return ""
    parts = produto.split(" - ", 1)
    return parts[1].strip() if len(parts) > 1 else parts[0].strip()


def _find_column(headers: list[str], *candidates: str) -> int | None:
    """Encontra índice da coluna pelo nome (case-insensitive, parcial).
    Busca candidatos em ordem de prioridade — retorna o primeiro match."""
    for c in candidates:
        c_lower = c.lower()
        for i, h in enumerate(headers):
            if not h:
                continue
            if c_lower in h.lower().strip():
                return i
    return None


def parse_b3_posicao(file_bytes: bytes) -> dict:
    """
    Parse do XLSX de Posição da B3.
    Retorna: {
        "tipo": "b3_posicao",
        "corretoras": {
            "BANCO BTG PACTUAL S/A": {
                "nome_curto": "BTG",
                "posicoes": [
                    {"ticker": "BBSE3", "nome": "BB SEGURIDADE...", "tipo": "ACAO",
                     "modulo": "dividendos", "quantidade": 773.0,
                     "preco_fechamento": 34.66, "valor_atualizado": 26792.18,
                     "isin": "BRBBSEACNOR5", "sheet": "Acoes"},
                    ...
                ]
            },
            ...
        },
        "totais": {"posicoes": 58, "corretoras": 2, "valor_total": 1234567.89}
    }
    """
    wb = load_workbook(BytesIO(file_bytes), read_only=False, data_only=True)

    corretoras: dict[str, dict] = {}

    for sheet_name in wb.sheetnames:
        tipo_apex = SHEET_TIPO_MAP.get(sheet_name)
        if tipo_apex is None:
            continue  # Skip Empréstimos

        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if len(rows) < 2:
            continue  # Só header, sem dados

        headers = [str(h).strip() if h else "" for h in rows[0]]

        # Encontrar colunas
        col_produto = _find_column(headers, "Produto")
        col_instituicao = _find_column(headers, "Instituição")
        col_codigo = _find_column(headers, "Código de Negociação")
        if col_codigo is None:
            # RF sheet has just "Código" (unique per CDB, e.g. CDBC25DMSJH)
            col_codigo = _find_column(headers, "Código")
        col_quantidade = _find_column(headers, "Quantidade")
        col_preco = _find_column(headers, "Preço de Fechamento", "Preço Atualizado CURVA", "Preço Atualizado MTM")
        col_valor = _find_column(headers, "Valor Atualizado CURVA", "Valor Atualizado FECHAMENTO", "Valor Atualizado MTM", "Valor Atualizado")
        col_isin = _find_column(headers, "Código ISIN")
        col_tipo_sub = _find_column(headers, "Tipo")

        # Renda Fixa: colunas extras
        col_indexador = _find_column(headers, "Indexador")
        col_emissor = _find_column(headers, "Emissor")
        col_vencimento = _find_column(headers, "Vencimento")

        # Opções: colunas extras
        col_strike = _find_column(headers, "Strike")
        col_venc_opcao = _find_column(headers, "Vencimento")
        col_tipo_opcao = _find_column(headers, "Tipo de opção")
        col_condicao = _find_column(headers, "Condição")

        for row in rows[1:]:
            # Pular linhas vazias e linhas de total
            if not row or not row[0]:
                continue
            produto = str(row[0]).strip() if row[0] else ""
            if not produto or produto.startswith("Total"):
                continue

            # Instituição
            instituicao = str(row[col_instituicao]).strip() if col_instituicao is not None and row[col_instituicao] else "DESCONHECIDA"
            instituicao = instituicao.replace("S.A.", "S/A").replace("S/A.", "S/A").rstrip(".")

            # Ticker
            ticker = ""
            if col_codigo is not None and row[col_codigo] and str(row[col_codigo]).strip() != "-":
                ticker = _normalizar_ticker(str(row[col_codigo]))
            if not ticker:
                ticker = _extrair_ticker_do_produto(produto)
            if not ticker:
                continue

            # Nome
            nome = _extrair_nome_do_produto(produto)

            # Subtipo (ON, PN, UNIT, Cotas, BDR, Commodity, etc.)
            subtipo = str(row[col_tipo_sub]).strip() if col_tipo_sub is not None and row[col_tipo_sub] and str(row[col_tipo_sub]).strip() != "-" else ""

            # ISIN (extrair antes do tipo para usar na detecção)
            isin = ""
            if col_isin is not None and row[col_isin]:
                raw_isin = str(row[col_isin]).strip()
                # Pode vir como "BRBBSEACNOR5 - 128" → pegar só o código
                isin = raw_isin.split(" - ")[0].strip() if " - " in raw_isin else raw_isin

            # Tipo APEX (usa ISIN para distinguir FIIs de UNITs na sheet Ações)
            tipo = _detectar_tipo(ticker, tipo_apex, subtipo, isin)

            # Quantidade
            quantidade = _parse_float(row[col_quantidade]) if col_quantidade is not None else 0.0

            # Filtrar posições zeradas (já vendidas/encerradas)
            if quantidade == 0:
                continue

            # Preço e valor
            preco = _parse_float(row[col_preco]) if col_preco is not None else 0.0
            valor = _parse_float(row[col_valor]) if col_valor is not None else 0.0

            # Posição base
            posicao = {
                "ticker": ticker,
                "nome": nome,
                "tipo": tipo,
                "modulo": _detectar_modulo(tipo, ticker),
                "quantidade": quantidade,
                "preco_fechamento": preco,
                "valor_atualizado": valor,
                "isin": isin,
                "sheet": sheet_name,
                "subtipo": subtipo,
            }

            # Renda Fixa: dados extras
            if tipo_apex == "RF":
                posicao["indexador"] = str(row[col_indexador]).strip() if col_indexador is not None and row[col_indexador] and str(row[col_indexador]).strip() != "-" else ""
                posicao["emissor"] = str(row[col_emissor]).strip() if col_emissor is not None and row[col_emissor] else ""
                posicao["vencimento"] = str(row[col_vencimento]).strip() if col_vencimento is not None and row[col_vencimento] else ""
                # Para RF, nome é mais descritivo
                posicao["nome"] = produto

            # Opções: dados extras
            if tipo_apex == "OPCAO":
                posicao["strike"] = _parse_float(row[col_strike]) if col_strike is not None else 0.0
                posicao["vencimento_opcao"] = str(row[col_venc_opcao]).strip() if col_venc_opcao is not None and row[col_venc_opcao] else ""
                posicao["tipo_opcao_raw"] = str(row[col_tipo_opcao]).strip() if col_tipo_opcao is not None and row[col_tipo_opcao] else ""
                posicao["condicao"] = str(row[col_condicao]).strip() if col_condicao is not None and row[col_condicao] else ""
                # Mapear: "Compra" + "Comprador" = CALL comprada, "Venda" + "Lançador" = PUT vendida
                if "compra" in posicao["tipo_opcao_raw"].lower():
                    posicao["tipo_opcao"] = "CALL"
                elif "venda" in posicao["tipo_opcao_raw"].lower():
                    posicao["tipo_opcao"] = "PUT"
                else:
                    posicao["tipo_opcao"] = ""

            # Agregar por corretora — merge posições do mesmo ticker na mesma corretora
            if instituicao not in corretoras:
                corretoras[instituicao] = {
                    "nome_curto": _nome_curto_corretora(instituicao),
                    "posicoes": [],
                }
            # Verificar se já existe esse ticker (pode ter 2 contas, ex: MSFT34 em 2 contas BTG)
            existing = next((p for p in corretoras[instituicao]["posicoes"] if p["ticker"] == ticker and p["tipo"] == tipo), None)
            if existing:
                existing["quantidade"] += quantidade
                existing["valor_atualizado"] += valor
            else:
                corretoras[instituicao]["posicoes"].append(posicao)

    wb.close()

    # Totais
    total_posicoes = sum(len(c["posicoes"]) for c in corretoras.values())
    total_valor = sum(
        sum(p["valor_atualizado"] for p in c["posicoes"])
        for c in corretoras.values()
    )

    return {
        "tipo": "b3_posicao",
        "corretoras": corretoras,
        "totais": {
            "posicoes": total_posicoes,
            "corretoras": len(corretoras),
            "valor_total": round(total_valor, 2),
        },
    }


def _nome_curto_corretora(nome_completo: str) -> str:
    """Mapeia nome oficial da B3 → nome curto para portfolio."""
    mapa = {
        "BANCO BTG PACTUAL S/A": "BTG",
        "BTG PACTUAL CTVM S/A": "BTG",
        "XP INVESTIMENTOS CCTVM S/A": "XP",
        "BANCO SANTANDER (BRASIL) SA": "Santander",
        "BANCO SANTANDER (BRASIL) S.A.": "Santander",
        "ITAU UNIBANCO S.A.": "Itaú",
        "ITAU CV S/A": "Itaú",
        "BANCO DO BRASIL S/A": "BB",
        "RICO INVESTIMENTOS": "Rico",
        "CLEAR CORRETORA": "Clear",
        "NU INVEST CORRETORA DE VALORES S.A.": "Nubank",
        "INTER DTVM LTDA": "Inter",
        "GENIAL INVESTIMENTOS CVM S.A.": "Genial",
        "ÁGORA CTVM S/A": "Ágora",
        "GUIDE INVESTIMENTOS S.A. CORRETORA DE VALORES": "Guide",
        "ÓRAMA DTVM S/A": "Órama",
        "MODAL DTVM LTDA": "Modal",
        "TERRA INVESTIMENTOS DISTRIBUIDORA DE TIT E VAL MOB LTDA": "Terra",
    }
    # Tentar match exato
    if nome_completo in mapa:
        return mapa[nome_completo]
    # Tentar match parcial
    nome_upper = nome_completo.upper()
    for key, val in mapa.items():
        if key.upper() in nome_upper or val.upper() in nome_upper:
            return val
    # Fallback: pegar primeira palavra significativa
    parts = nome_completo.split()
    if len(parts) >= 2 and parts[0].upper() == "BANCO":
        return parts[1].title()
    return parts[0].title() if parts else nome_completo

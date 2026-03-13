"""
Rotas de importação de extratos B3 — upload, preview e confirmação.
Suporta: Posição (snapshot), Negociação (compras/vendas), Movimentação (proventos/eventos).
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Position
from app.models.transacao import Transacao
from app.services.importers.b3_posicao_parser import parse_b3_posicao, _detectar_modulo as _modulo_from_tipo
from app.services.importers.b3_negociacao_parser import parse_b3_negociacao
from app.services.importers.b3_movimentacao_parser import parse_b3_movimentacao
from app.services.importers.xp_posicao_parser import parse_xp_posicao
from app.services.importers.xp_extrato_parser import parse_xp_extrato
from openpyxl import load_workbook
from io import BytesIO

router = APIRouter(prefix="/import", tags=["import"])

# ─── Cache de preview (em memória, por user_id) ──────────────────────────────
# Armazena o último parse para confirmar sem re-upload
_preview_cache: dict[int, dict] = {}


def _detectar_tipo_arquivo(file_bytes: bytes) -> str:
    """Detecta o tipo do arquivo (B3 ou corretora) pelas sheets e conteúdo do XLSX."""
    wb = load_workbook(BytesIO(file_bytes), read_only=False, data_only=True)
    sheets = [s.lower() for s in wb.sheetnames]

    # --- B3 (Área do Investidor) ---
    if any(s in sheets for s in ["acoes", "ações", "bdr", "etf", "renda fixa", "fundo de investimento"]):
        wb.close()
        return "b3_posicao"
    if any("negociação" in s or "negociacao" in s for s in sheets):
        wb.close()
        return "b3_negociacao"
    if any("movimentação" in s or "movimentacao" in s for s in sheets):
        wb.close()
        return "b3_movimentacao"

    # --- XP Investimentos ---
    # Posição: sheet "Sua carteira" com layout patrimônio
    if any("carteira" in s for s in sheets):
        ws = wb[wb.sheetnames[sheets.index(next(s for s in sheets if "carteira" in s))]]
        # Verificar se tem padrões XP: "patrimônio" ou "Posição" ou "% Alocação"
        for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
            for cell in row:
                if cell and any(kw in str(cell).lower() for kw in ["patrimônio", "total investido", "saldo disponível"]):
                    wb.close()
                    return "xp_posicao"
        wb.close()
        return "xp_posicao"  # Sheet "carteira" é strong signal

    # Extrato XP: sheet "Planilha1" com "Extrato da conta" ou colunas Movimentação/Liquidação
    if "planilha1" in sheets:
        ws = wb[wb.sheetnames[sheets.index("planilha1")]]
        for row in ws.iter_rows(min_row=1, max_row=15, values_only=True):
            for cell in row:
                if cell and "extrato da conta" in str(cell).lower():
                    wb.close()
                    return "xp_extrato"
            vals = [str(v).strip().lower() if v else "" for v in row]
            if "movimentação" in vals and "liquidação" in vals:
                wb.close()
                return "xp_extrato"

    wb.close()
    return "desconhecido"


@router.post("/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    user_id: int = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Upload de 1 a 3 arquivos XLSX da B3 (posição, negociação, movimentação).
    Auto-detecta o tipo de cada arquivo pelas sheets internas.
    Retorna preview combinado. Nada é salvo — precisa confirmar via /import/confirm.
    """
    if not user_id:
        raise HTTPException(400, "Header x-user-id obrigatório")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    resultados = []
    tipos_detectados = []

    for file in files:
        if not file.filename or not file.filename.lower().endswith(".xlsx"):
            raise HTTPException(400, f"Arquivo '{file.filename}' não é .xlsx")

        file_bytes = await file.read()
        if len(file_bytes) > 50 * 1024 * 1024:
            raise HTTPException(400, f"Arquivo '{file.filename}' muito grande (máximo 50MB)")

        tipo = _detectar_tipo_arquivo(file_bytes)
        if tipo == "desconhecido":
            raise HTTPException(422, f"Não foi possível identificar o tipo do arquivo '{file.filename}'. Certifique-se de que é um extrato da B3 ou de uma corretora suportada (XP, BTG, etc).")

        # Normalizar tipo para evitar duplicatas (xp_posicao → b3_posicao no pipeline)
        tipo_pipeline = tipo
        if tipo == "xp_posicao":
            tipo_pipeline = "b3_posicao"
        elif tipo == "xp_extrato":
            tipo_pipeline = "b3_movimentacao"

        if tipo_pipeline in tipos_detectados:
            raise HTTPException(400, f"Dois arquivos do mesmo tipo ({tipo_pipeline.replace('b3_', '')}). Envie apenas 1 de cada.")

        try:
            if tipo == "b3_posicao":
                result = parse_b3_posicao(file_bytes)
            elif tipo == "b3_negociacao":
                result = parse_b3_negociacao(file_bytes)
            elif tipo == "b3_movimentacao":
                result = parse_b3_movimentacao(file_bytes)
            elif tipo == "xp_posicao":
                result = parse_xp_posicao(file_bytes)
            elif tipo == "xp_extrato":
                result = parse_xp_extrato(file_bytes)
            else:
                result = parse_b3_movimentacao(file_bytes)
        except Exception as e:
            raise HTTPException(422, f"Erro ao ler '{file.filename}': {str(e)}")

        result["arquivo"] = file.filename
        resultados.append(result)
        tipos_detectados.append(tipo_pipeline)

    # Cache combinado
    combined = {
        "arquivos": resultados,
        "tipos": tipos_detectados,
    }
    _preview_cache[user_id] = combined

    return combined


@router.post("/confirm")
async def confirm_import(
    user_id: int = Depends(get_user_id),
    db: Session = Depends(get_db),
    corretoras_selecionadas: Optional[list[str]] = Body(None, embed=True),
):
    """
    Confirma o import do último preview.
    Cria portfolios por corretora e insere posições/transações.
    Se corretoras_selecionadas for fornecido, importa apenas essas corretoras.
    """
    if not user_id:
        raise HTTPException(400, "Header x-user-id obrigatório")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    preview = _preview_cache.get(user_id)
    if not preview:
        raise HTTPException(400, "Nenhum preview pendente. Faça upload primeiro.")

    # Filtrar corretoras se seleção fornecida
    filtro = set(corretoras_selecionadas) if corretoras_selecionadas else None

    resultado = {"portfolios_criados": [], "posicoes_criadas": 0, "transacoes_criadas": 0, "duplicatas_ignoradas": 0, "mensagem": ""}

    try:
        # Processar cada arquivo do preview combinado
        for arq in preview.get("arquivos", []):
            # Se há filtro, criar versão filtrada do arquivo
            if filtro:
                arq_filtrado = {**arq, "corretoras": {
                    k: v for k, v in arq.get("corretoras", {}).items() if k in filtro
                }}
            else:
                arq_filtrado = arq

            if not arq_filtrado.get("corretoras"):
                continue

            tipo = arq_filtrado.get("tipo")
            if tipo == "b3_posicao":
                _confirm_posicao(user, arq_filtrado, db, resultado)
            elif tipo == "b3_negociacao":
                _confirm_negociacao(user, arq_filtrado, db, resultado)
            elif tipo == "b3_movimentacao":
                _confirm_movimentacao(user, arq_filtrado, db, resultado)

        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Erro ao confirmar import: {str(e)}")

    # Limpar cache
    _preview_cache.pop(user_id, None)

    # Mensagem resumo
    parts = []
    if resultado["posicoes_criadas"]:
        parts.append(f"{resultado['posicoes_criadas']} posições importadas")
    if resultado["transacoes_criadas"]:
        parts.append(f"{resultado['transacoes_criadas']} transações importadas")
    if resultado["duplicatas_ignoradas"]:
        parts.append(f"{resultado['duplicatas_ignoradas']} duplicatas ignoradas")
    n_port = len(resultado["portfolios_criados"])
    if n_port:
        nomes = ", ".join(p["nome"] for p in resultado["portfolios_criados"])
        parts.append(f"{n_port} carteira(s): {nomes}")
    resultado["mensagem"] = " · ".join(parts) if parts else "Import concluído."

    return resultado


def _get_or_create_portfolio(user: User, corretora_nome: str, nome_curto: str, db: Session) -> Portfolio:
    """Busca portfolio existente pela corretora ou cria novo."""
    portfolio = db.query(Portfolio).filter(
        Portfolio.user_id == user.id,
        Portfolio.corretora == corretora_nome,
    ).first()

    if not portfolio:
        portfolio = Portfolio(
            user_id=user.id,
            nome=nome_curto,
            tipo="real",
            corretora=corretora_nome,
        )
        db.add(portfolio)
        db.flush()  # Gera o ID

    return portfolio


def _confirm_posicao(user: User, preview: dict, db: Session, resultado: dict):
    """Confirma import de Posição — cria portfolios + posições."""
    seen_portfolios = set()
    for corretora_nome, data in preview.get("corretoras", {}).items():
        nome_curto = data.get("nome_curto", corretora_nome)
        portfolio = _get_or_create_portfolio(user, corretora_nome, nome_curto, db)

        if corretora_nome not in seen_portfolios:
            seen_portfolios.add(corretora_nome)
            resultado["portfolios_criados"].append({
                "nome": portfolio.nome,
                "corretora": corretora_nome,
                "id": portfolio.id,
            })

        for pos_data in data.get("posicoes", []):
            ticker = pos_data["ticker"]
            tipo = pos_data["tipo"]

            # Upsert: verificar se posição já existe
            existing = db.query(Position).filter(
                Position.portfolio_id == portfolio.id,
                Position.ticker == ticker,
                Position.ativa == True,
            ).first()

            if existing:
                # Atualizar quantidade e valor
                existing.quantidade = pos_data["quantidade"]
                existing.preco_atual = pos_data["preco_fechamento"]
                existing.valor_atual = pos_data["valor_atualizado"]
                if pos_data.get("preco_medio"):
                    existing.preco_medio = pos_data["preco_medio"]
                # Recalcular valor_investido e P&L
                pm = existing.preco_medio or pos_data["preco_fechamento"]
                qty = existing.quantidade
                if tipo == "RF":
                    existing.valor_investido = pos_data.get("valor_aplicado", pm * qty)
                else:
                    existing.valor_investido = round(pm * qty, 2)
                existing.pl_reais = round(existing.valor_atual - existing.valor_investido, 2)
                existing.pl_percentual = round(existing.pl_reais / existing.valor_investido * 100, 2) if existing.valor_investido else 0.0
                existing.updated_at = datetime.utcnow()
            else:
                # Criar nova posição
                pm = pos_data.get("preco_medio") or pos_data["preco_fechamento"]
                qty = pos_data["quantidade"]
                if tipo == "RF":
                    valor_inv = pos_data.get("valor_aplicado", pm * qty)
                else:
                    valor_inv = round(pm * qty, 2)
                valor_at = pos_data["valor_atualizado"]
                pl_r = round(valor_at - valor_inv, 2)
                pl_p = round(pl_r / valor_inv * 100, 2) if valor_inv else 0.0
                pos = Position(
                    portfolio_id=portfolio.id,
                    ticker=ticker,
                    nome=pos_data.get("nome", ""),
                    tipo=tipo,
                    modulo=pos_data.get("modulo", "alpha"),
                    mercado="B3",
                    moeda="BRL",
                    quantidade=qty,
                    preco_medio=pm,
                    valor_investido=valor_inv,
                    preco_atual=pos_data["preco_fechamento"],
                    valor_atual=valor_at,
                    pl_reais=pl_r,
                    pl_percentual=pl_p,
                    source="b3_import",
                    external_id=pos_data.get("isin", ""),
                    ativa=True,
                    data_entrada=datetime.utcnow(),
                )

                # Renda Fixa extras
                if tipo == "RF":
                    indexador_map = {"DI": "CDI", "IPCA": "IPCA", "PREFIXADO": "PRE"}
                    pos.indexador = indexador_map.get(pos_data.get("indexador", "").upper(), pos_data.get("indexador", ""))

                # Opções extras
                if tipo == "OPCAO":
                    pos.strike = pos_data.get("strike", 0.0)
                    pos.tipo_opcao = pos_data.get("tipo_opcao", "")

                db.add(pos)
                resultado["posicoes_criadas"] += 1


def _confirm_negociacao(user: User, preview: dict, db: Session, resultado: dict):
    """Confirma import de Negociação — cria transações + recalcula preço médio."""
    for corretora_nome, data in preview.get("corretoras", {}).items():
        nome_curto = data.get("nome_curto", corretora_nome)
        portfolio = _get_or_create_portfolio(user, corretora_nome, nome_curto, db)

        if portfolio.nome not in [r["nome"] for r in resultado["portfolios_criados"]]:
            resultado["portfolios_criados"].append({
                "nome": portfolio.nome,
                "corretora": corretora_nome,
                "id": portfolio.id,
            })

        # Agrupar transações por ticker para recalcular preço médio
        transacoes_por_ticker: dict[str, list] = {}

        for tx_data in data.get("transacoes", []):
            ticker = tx_data["ticker"]
            tx_hash = tx_data["hash"]

            # Verificar duplicata pelo hash na observacao
            existing_tx = db.query(Transacao).filter(
                Transacao.portfolio_id == portfolio.id,
                Transacao.observacao.contains(tx_hash),
            ).first()
            if existing_tx:
                resultado["duplicatas_ignoradas"] += 1
                continue

            # Buscar ou criar posição
            pos = db.query(Position).filter(
                Position.portfolio_id == portfolio.id,
                Position.ticker == ticker,
                Position.ativa == True,
            ).first()

            pos_already_existed = pos is not None

            if not pos:
                # Criar posição nova (será populada pelas transações)
                tipo_ativo = tx_data.get("tipo_ativo", "ACAO")
                pos = Position(
                    portfolio_id=portfolio.id,
                    ticker=ticker,
                    nome="",
                    tipo=tipo_ativo,
                    modulo=_modulo_from_tipo(tipo_ativo, ticker),
                    mercado="B3",
                    moeda="BRL",
                    quantidade=0,
                    preco_medio=0,
                    valor_investido=0,
                    source="b3_import",
                    ativa=True,
                    data_entrada=datetime.utcnow(),
                )
                db.add(pos)
                db.flush()

            # Mapear tipo de transação
            tipo_apex = "compra" if tx_data["tipo"] == "compra" else "venda_parcial"

            # Criar transação
            data_tx = datetime.strptime(tx_data["data"], "%Y-%m-%d") if tx_data["data"] else datetime.utcnow()
            transacao = Transacao(
                portfolio_id=portfolio.id,
                position_id=pos.id,
                tipo=tipo_apex,
                data=data_tx,
                quantidade=tx_data["quantidade"],
                preco=tx_data["preco"],
                valor_total=tx_data["valor"],
                observacao=f"B3 import | hash:{tx_hash}",
            )
            db.add(transacao)
            resultado["transacoes_criadas"] += 1

            # Acumular para recálculo de PM (apenas posições novas)
            if ticker not in transacoes_por_ticker:
                transacoes_por_ticker[ticker] = {"pos": pos, "txs": [], "existed": pos_already_existed}
            transacoes_por_ticker[ticker]["txs"].append(tx_data)

        # Recalcular preço médio apenas para posições criadas pelo negociação.
        # Posições que já existiam (ex: importadas via posição da corretora)
        # têm PM real — não devemos sobrescrever com cálculo parcial de trades.
        for ticker, info in transacoes_por_ticker.items():
            if not info["existed"]:
                _recalcular_preco_medio(info["pos"], info["txs"], db)


def _recalcular_preco_medio(pos: Position, novas_txs: list, db: Session):
    """
    Recalcula preço médio considerando TODAS as transações da posição.
    Usa método de média ponderada: PM = total_investido / total_quantidade.
    """
    # Buscar TODAS as transações da posição, ordenadas por data
    todas_txs = db.query(Transacao).filter(
        Transacao.position_id == pos.id,
    ).order_by(Transacao.data).all()

    qtd = 0.0
    custo_total = 0.0

    for tx in todas_txs:
        if tx.tipo in ("compra", "dca"):
            qtd += tx.quantidade
            custo_total += tx.quantidade * tx.preco
        elif tx.tipo in ("venda_parcial", "venda_total"):
            if qtd > 0:
                pm_antes = custo_total / qtd
                qtd -= tx.quantidade
                custo_total = pm_antes * qtd if qtd > 0 else 0
        elif tx.tipo == "bonificacao":
            qtd += tx.quantidade
            # Bonificação não altera custo total (preço = 0)
        elif tx.tipo == "split":
            if tx.preco > 0:
                fator = tx.preco
                qtd *= fator
                # Custo total não muda, apenas PM diminui

    pos.quantidade = max(qtd, 0)
    pos.preco_medio = custo_total / qtd if qtd > 0 else 0
    pos.valor_investido = custo_total if qtd > 0 else 0
    pos.updated_at = datetime.utcnow()


def _confirm_movimentacao(user: User, preview: dict, db: Session, resultado: dict):
    """Confirma import de Movimentação — proventos e eventos corporativos."""
    for corretora_nome, data in preview.get("corretoras", {}).items():
        nome_curto = data.get("nome_curto", corretora_nome)
        portfolio = _get_or_create_portfolio(user, corretora_nome, nome_curto, db)

        if portfolio.nome not in [r["nome"] for r in resultado["portfolios_criados"]]:
            resultado["portfolios_criados"].append({
                "nome": portfolio.nome,
                "corretora": corretora_nome,
                "id": portfolio.id,
            })

        for mov_data in data.get("movimentacoes", []):
            tx_hash = mov_data["hash"]
            ticker = mov_data["ticker"]
            categoria = mov_data["categoria"]

            # Verificar duplicata
            existing = db.query(Transacao).filter(
                Transacao.portfolio_id == portfolio.id,
                Transacao.observacao.contains(tx_hash),
            ).first()
            if existing:
                resultado["duplicatas_ignoradas"] += 1
                continue

            # Buscar posição do ticker
            pos = db.query(Position).filter(
                Position.portfolio_id == portfolio.id,
                Position.ticker == ticker,
                Position.ativa == True,
            ).first()

            if not pos:
                # Criar posição se não existir (pode ter sido vendida mas teve provento)
                tipo_ativo = mov_data.get("tipo_ativo", "ACAO")
                pos = Position(
                    portfolio_id=portfolio.id,
                    ticker=ticker,
                    nome="",
                    tipo=tipo_ativo,
                    modulo=_modulo_from_tipo(tipo_ativo, ticker),
                    mercado="B3",
                    moeda="BRL",
                    quantidade=0,
                    preco_medio=0,
                    valor_investido=0,
                    source="b3_import",
                    ativa=True,
                    data_entrada=datetime.utcnow(),
                )
                db.add(pos)
                db.flush()

            # Mapear categoria → tipo transação APEX
            tipo_mov_lower = mov_data["tipo_mov"].lower()
            tipo_map = {
                "provento": "dividendo" if "dividendo" in tipo_mov_lower else "jcp" if "juros" in tipo_mov_lower else "rendimento",
                "evento": "bonificacao" if "bonificação" in tipo_mov_lower else "split" if "desdobro" in tipo_mov_lower else "outro",
                "transacao": "compra" if mov_data.get("direcao") == "Credito" else "venda_parcial",
                "rf": "aplicacao" if "aplicação" in tipo_mov_lower else "resgate",
            }
            tipo_tx = tipo_map.get(categoria, "outro")

            data_tx = datetime.strptime(mov_data["data"], "%Y-%m-%d") if mov_data["data"] else datetime.utcnow()

            transacao = Transacao(
                portfolio_id=portfolio.id,
                position_id=pos.id,
                tipo=tipo_tx,
                data=data_tx,
                quantidade=mov_data["quantidade"],
                preco=mov_data["preco"],
                valor_total=mov_data["valor"],
                observacao=f"B3 mov | {mov_data['tipo_mov']} | hash:{tx_hash}",
            )
            db.add(transacao)
            resultado["transacoes_criadas"] += 1

"""Rota de posições — CRUD de posições do portfólio."""
import asyncio
import io
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id, get_portfolio_ativo
from app.models import User, Portfolio, Position
from app.models.transacao import Transacao
from app.data import get_quotes, get_quote, get_fundamentals
from app.data.cache import cache as _portfolio_cache
from app.data.tecnico import get_dados_tecnicos

router = APIRouter(prefix="/portfolio", tags=["portfolio"])
logger = logging.getLogger(__name__)

MODULOS_VALIDOS = {"etfs", "fiis", "renda_fixa", "momentum", "wheel", "alpha", "dividendos", "teses", "caixa"}
ESTRATEGIAS_VALIDAS = {"CORE", "ALPHA", "RENDA", "CUSTOM"}

class NovaPosicao(BaseModel):
    ticker: str
    nome: str | None = None
    tipo: str                   # ACAO | FII | ETF | BDR | RF | OPCAO | CAIXA | DIVIDENDO
    modulo: str                 # momentum | wheel | etfs | fiis | renda_fixa | alpha | dividendos | caixa
    quantidade: float
    preco_medio: float
    stop_loss: float | None = None
    # Opções
    strike: float | None = None
    vencimento: str | None = None
    tipo_opcao: str | None = None
    premio_recebido: float | None = None
    # RF
    indexador: str | None = None
    taxa: float | None = None
    # Justificativa / tese de entrada
    justificativa_entrada: str | None = None

    @field_validator('ticker')
    @classmethod
    def ticker_valido(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError('Ticker não pode ser vazio')
        return v

    @field_validator('quantidade', 'preco_medio')
    @classmethod
    def deve_ser_positivo(cls, v: float) -> float:
        if v <= 0:
            raise ValueError('Deve ser maior que zero')
        return v


@router.get("/posicoes")
async def listar_posicoes(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Lista todas as posições ativas com cotação atualizada."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()

    tickers = [p.ticker for p in posicoes if p.tipo in ("ACAO", "FII", "ETF", "BDR")]
    cotacoes = await get_quotes(tickers) if tickers else {}

    resultado = []
    for p in posicoes:
        # CAIXA: preço é sempre 1.0, valor = quantidade
        if p.ticker == "CAIXA":
            preco_atual = 1.0
            valor_atual = p.quantidade
            pl_reais = 0.0
            pl_pct = 0.0
        else:
            cotacao = cotacoes.get(p.ticker, {})
            preco_atual = cotacao.get("regularMarketPrice", p.preco_atual or p.preco_medio)
            valor_atual = preco_atual * p.quantidade
            pl_reais = valor_atual - p.valor_investido
            pl_pct = (pl_reais / p.valor_investido * 100) if p.valor_investido > 0 else 0

        resultado.append({
            "id": p.id,
            "ticker": p.ticker,
            "nome": p.nome or p.ticker,
            "tipo": p.tipo,
            "modulo": p.modulo,
            "quantidade": p.quantidade,
            "preco_medio": p.preco_medio,
            "preco_atual": round(preco_atual, 2),
            "valor_investido": p.valor_investido,
            "valor_atual": round(valor_atual, 2),
            "pl_reais": round(pl_reais, 2),
            "pl_percentual": round(pl_pct, 2),
            "stop_loss": p.stop_loss,
            "alvo_1": p.alvo_1,
            "apex_score": p.apex_score,
            "data_entrada": p.data_entrada,
            # Tese / justificativa
            "tese": p.tese,
            "justificativa_entrada": p.justificativa_entrada,
            # Wheel
            "strike": p.strike,
            "vencimento": p.vencimento,
            "tipo_opcao": p.tipo_opcao,
            "premio_recebido": p.premio_recebido,
        })

    # Caixa disponível: capital declarado - soma dos valores atuais investidos
    capital_declarado = getattr(portfolio, "capital_declarado", None)
    soma_posicoes = sum(r["valor_atual"] for r in resultado)
    caixa_disponivel = round(capital_declarado - soma_posicoes, 2) if capital_declarado else None

    return {
        "posicoes": resultado,
        "capital_declarado": capital_declarado,
        "caixa_disponivel": caixa_disponivel,
    }


@router.post("/posicoes")
async def adicionar_posicao(body: NovaPosicao, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Adiciona uma nova posição ao portfólio. Busca cotação atual automaticamente."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    # Buscar cotação atual para ativos de mercado
    preco_atual = None
    ticker_upper = body.ticker.upper()
    if body.tipo in ("ACAO", "FII", "ETF", "BDR"):
        cotacao = await get_quote(ticker_upper)
        if cotacao:
            preco_atual = cotacao.get("regularMarketPrice")
        # Fallback yfinance se BRAPI não retornou
        if preco_atual is None:
            try:
                from app.data.yfinance_client import get_preco_atual_yf
                preco_atual = await get_preco_atual_yf(ticker_upper)
            except Exception:
                pass

        # Validar que o ticker existe — BRAPI e yfinance falharam
        if preco_atual is None:
            raise HTTPException(
                status_code=422,
                detail=f"Ticker '{ticker_upper}' não encontrado. Verifique se o código está correto.",
            )

    valor_investido = body.quantidade * body.preco_medio
    vencimento = datetime.fromisoformat(body.vencimento) if body.vencimento else None

    preco_live = preco_atual if preco_atual is not None else body.preco_medio
    valor_atual = preco_live * body.quantidade
    pl_reais = valor_atual - valor_investido
    pl_pct = (pl_reais / valor_investido * 100) if valor_investido > 0 else 0

    # Deriva mercado a partir do tipo
    mercado = "BDR" if body.tipo == "BDR" else "B3"

    posicao = Position(
        portfolio_id=portfolio.id,
        ticker=ticker_upper,
        nome=body.nome,
        tipo=body.tipo,
        modulo=body.modulo,
        mercado=mercado,
        quantidade=body.quantidade,
        preco_medio=body.preco_medio,
        preco_atual=round(preco_live, 2),
        valor_investido=valor_investido,
        valor_atual=round(valor_atual, 2),
        pl_reais=round(pl_reais, 2),
        pl_percentual=round(pl_pct, 2),
        stop_loss=body.stop_loss,
        strike=body.strike,
        vencimento=vencimento,
        tipo_opcao=body.tipo_opcao,
        premio_recebido=body.premio_recebido,
        indexador=body.indexador,
        taxa=body.taxa,
        justificativa_entrada=body.justificativa_entrada,
    )
    db.add(posicao)
    db.commit()
    db.refresh(posicao)

    return {"id": posicao.id, "mensagem": f"Posição {body.ticker} adicionada com sucesso."}


@router.delete("/posicoes/{posicao_id}")
def encerrar_posicao(posicao_id: int, motivo: str = "Encerrado manualmente", user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Marca uma posição como encerrada. Verifica que pertence ao portfólio do usuário logado."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    # Filtra por id E portfolio_id — garante ownership
    posicao = db.query(Position).filter(
        Position.id == posicao_id,
        Position.portfolio_id == portfolio.id,
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    posicao.ativa = False
    posicao.data_saida = datetime.now(timezone.utc)
    posicao.motivo_saida = motivo
    db.commit()

    return {"mensagem": f"Posição {posicao.ticker} encerrada."}


@router.get("/posicoes/{posicao_id}/fundamentals")
async def fundamentals_posicao(posicao_id: int, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Retorna dados fundamentalistas (P/L, P/VP, DY, ROE…) de uma posição."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicao = db.query(Position).filter(
        Position.id == posicao_id,
        Position.portfolio_id == portfolio.id,
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    tipos_com_fundamentos = {"ACAO", "FII", "ETF", "BDR"}
    if posicao.tipo not in tipos_com_fundamentos:
        return {"dados": None, "mensagem": f"Dados fundamentalistas não se aplicam a {posicao.tipo}"}

    dados = await get_fundamentals(posicao.ticker)
    if not dados:
        return {"dados": None, "mensagem": "Dados fundamentalistas indisponíveis para este ticker"}

    return {"dados": dados, "ticker": posicao.ticker}


# ─── CAIXA: editar saldo e excluir ───────────────────────────────────────────

class CaixaUpdate(BaseModel):
    quantidade: float  # Novo saldo em R$

@router.patch("/caixa")
def editar_caixa(body: CaixaUpdate, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Edita o saldo da posição CAIXA (Reserva de Liquidez)."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")
    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    caixa = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ticker == "CAIXA",
        Position.ativa == True,
    ).first()

    if not caixa:
        raise HTTPException(status_code=404, detail="Posição CAIXA não encontrada")

    novo = round(max(body.quantidade, 0), 2)
    caixa.quantidade = novo
    caixa.valor_investido = novo
    caixa.valor_atual = novo
    caixa.preco_medio = 1.0
    caixa.preco_atual = 1.0
    caixa.pl_reais = 0.0
    caixa.pl_percentual = 0.0
    _reconciliar_patrimonio(db, portfolio)
    db.commit()
    return {"mensagem": f"Caixa atualizado para R$ {novo:,.2f}", "quantidade": novo}


@router.delete("/caixa")
def excluir_caixa(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Remove a posição CAIXA (Reserva de Liquidez)."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")
    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    caixa = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ticker == "CAIXA",
        Position.ativa == True,
    ).first()

    if not caixa:
        raise HTTPException(status_code=404, detail="Posição CAIXA não encontrada")

    caixa.ativa = False
    caixa.data_saida = datetime.now(timezone.utc)
    caixa.motivo_saida = "CAIXA removido manualmente"
    _reconciliar_patrimonio(db, portfolio)
    db.commit()
    return {"mensagem": "Posição CAIXA removida."}


# ─── Helpers internos: CAIXA e reconciliação ──────────────────────────────────

def _atualizar_caixa(db: Session, portfolio_id: int, delta: float):
    """Adiciona ou subtrai do saldo CAIXA. Cria a posição se não existir."""
    caixa = db.query(Position).filter(
        Position.portfolio_id == portfolio_id,
        Position.ticker == "CAIXA",
        Position.ativa == True,
    ).first()

    if caixa:
        novo = round(max(caixa.quantidade + delta, 0), 2)
        caixa.quantidade = novo
        caixa.valor_investido = novo
        caixa.valor_atual = novo
        caixa.preco_medio = 1.0
        caixa.preco_atual = 1.0
    elif delta > 0:
        db.add(Position(
            portfolio_id=portfolio_id,
            ticker="CAIXA", nome="Reserva de Liquidez",
            tipo="CAIXA", modulo="caixa",
            quantidade=round(delta, 2),
            preco_medio=1.0, preco_atual=1.0,
            valor_investido=round(delta, 2),
            valor_atual=round(delta, 2),
            pl_reais=0.0, pl_percentual=0.0,
            moeda="BRL",
            data_entrada=datetime.now(timezone.utc),
        ))


def _reconciliar_patrimonio(db: Session, portfolio: Portfolio):
    """Atualiza patrimonio_total = soma(posições ativas × valor_atual)."""
    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()
    total = sum(p.valor_atual or 0 for p in posicoes)
    portfolio.patrimonio_total = round(total, 2)


def _registrar_journal(db: Session, portfolio_id: int, position_id: int | None,
                       ticker: str, tipo_op: str, acao: str, motivo: str,
                       preco: float, quantidade: float, valor_total: float,
                       modulo: str | None = None):
    """Wrapper seguro para registrar_decisao — não falha se der erro."""
    try:
        from app.cerebro.aprendizado import registrar_decisao
        registrar_decisao(
            db=db, portfolio_id=portfolio_id, ticker=ticker,
            tipo_operacao=tipo_op, acao_framework=acao, motivo=motivo,
            preco=preco, quantidade=quantidade, valor_total=valor_total,
            modulo=modulo, position_id=position_id,
        )
    except Exception as e:
        logger.warning("TradeJournal falhou para %s %s: %s", tipo_op, ticker, e)


def _atualizar_alvos_de_alocacao(db: Session, portfolio: Portfolio):
    """Recalcula os alvo_* do portfólio com base nas posições ativas atuais.

    Chamada após aplicar sugestões ou rebalanceamento — garante que os targets
    reflitam a distribuição real resultante, não os valores do onboarding.
    """
    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()
    patrimonio = sum(p.valor_atual or 0 for p in posicoes)
    if patrimonio <= 0:
        return  # sem posições → não mexe nos alvos

    # Soma valor por módulo
    por_modulo: dict[str, float] = {}
    for p in posicoes:
        mod = p.modulo or "caixa"
        por_modulo[mod] = por_modulo.get(mod, 0) + (p.valor_atual or 0)

    # Mapeia módulo → campo alvo_*
    MODULO_CAMPO = {
        "etfs": "alvo_etfs",
        "fiis": "alvo_fiis",
        "renda_fixa": "alvo_renda_fixa",
        "momentum": "alvo_momentum",
        "wheel": "alvo_wheel",
        "alpha": "alvo_alpha",
        "dividendos": "alvo_dividendos",
        "teses": "alvo_teses",
        "caixa": "alvo_caixa",
    }

    for modulo, campo in MODULO_CAMPO.items():
        pct = round((por_modulo.get(modulo, 0) / patrimonio) * 100, 1)
        setattr(portfolio, campo, pct)

    logger.info("Alvos atualizados para portfolio %s: %s",
                portfolio.id, {m: getattr(portfolio, c) for m, c in MODULO_CAMPO.items()})


# ─── POST /posicoes/{id}/encerrar — Modal inteligente de saída ───────────────

class EncerrarPosicaoBody(BaseModel):
    preco_venda: float                          # Preço de execução da venda
    quantidade_vendida: float                   # Qtd vendida (parcial ou total)
    destino_capital: str = "caixa"              # "caixa" | "saque"
    motivo: str = "Encerrado manualmente"


@router.post("/posicoes/{posicao_id}/encerrar")
def encerrar_posicao_inteligente(
    posicao_id: int,
    body: EncerrarPosicaoBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Encerra (total ou parcial) uma posição com captura de preço de venda,
    destino do capital, registro de Transação e TradeJournal.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicao = db.query(Position).filter(
        Position.id == posicao_id,
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    qtd_vendida = min(body.quantidade_vendida, posicao.quantidade)
    valor_venda = round(qtd_vendida * body.preco_venda, 2)
    pl_realizado = round((body.preco_venda - (posicao.preco_medio or 0)) * qtd_vendida, 2)
    venda_total = qtd_vendida >= posicao.quantidade

    # ── 1) Registrar Transação ──
    tipo_tx = "venda_total" if venda_total else "venda_parcial"
    db.add(Transacao(
        portfolio_id=portfolio.id,
        position_id=posicao.id,
        tipo=tipo_tx,
        data=datetime.now(timezone.utc),
        quantidade=qtd_vendida,
        preco=body.preco_venda,
        valor_total=valor_venda,
        observacao=body.motivo,
    ))

    # ── 2) Atualizar posição ──
    if venda_total:
        posicao.ativa = False
        posicao.data_saida = datetime.now(timezone.utc)
        posicao.motivo_saida = body.motivo
    else:
        nova_qtd = round(posicao.quantidade - qtd_vendida, 6)
        posicao.quantidade = nova_qtd
        posicao.valor_investido = round(nova_qtd * posicao.preco_medio, 2)
        posicao.valor_atual = round(nova_qtd * (posicao.preco_atual or body.preco_venda), 2)
        posicao.pl_reais = round(posicao.valor_atual - posicao.valor_investido, 2)
        if posicao.valor_investido > 0:
            posicao.pl_percentual = round(
                (posicao.valor_atual / posicao.valor_investido - 1) * 100, 2
            )

    # ── 3) Destino do capital ──
    if body.destino_capital == "caixa":
        _atualizar_caixa(db, portfolio.id, valor_venda)
    else:
        # Saque — reduz patrimônio declarado
        if portfolio.capital_declarado:
            portfolio.capital_declarado = round(
                max(portfolio.capital_declarado - valor_venda, 0), 2
            )

    # ── 4) Reconciliar patrimônio ──
    _reconciliar_patrimonio(db, portfolio)

    # ── 5) TradeJournal ──
    _registrar_journal(
        db, portfolio.id, posicao.id, posicao.ticker,
        tipo_op="SAIDA" if venda_total else "REDUCAO",
        acao="SAIR" if venda_total else "REDUZIR",
        motivo=body.motivo,
        preco=body.preco_venda, quantidade=qtd_vendida, valor_total=valor_venda,
        modulo=posicao.modulo,
    )

    db.commit()

    return {
        "mensagem": f"{'Posição encerrada' if venda_total else 'Venda parcial registrada'}: {posicao.ticker}",
        "ticker": posicao.ticker,
        "venda_total": venda_total,
        "valor_venda": valor_venda,
        "pl_realizado": pl_realizado,
        "destino_capital": body.destino_capital,
    }


class AtualizarPosicao(BaseModel):
    tese: str | None = None           # Nova tese de investimento
    stop_loss: float | None = None    # Novo stop
    alvo_1: float | None = None       # Novo alvo 1
    alvo_2: float | None = None       # Novo alvo 2
    nome: str | None = None           # Renomear
    quantidade: float | None = None   # Nova quantidade
    preco_medio: float | None = None  # Novo preço médio
    modulo: str | None = None         # Novo módulo


@router.patch("/posicoes/{posicao_id}")
def atualizar_posicao(posicao_id: int, body: AtualizarPosicao, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Atualiza campos editáveis de uma posição: tese, stop, alvo.
    Usado após conversa com a IA — salva o consenso alcançado.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicao = db.query(Position).filter(
        Position.id == posicao_id,
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    if body.tese is not None:
        posicao.tese = body.tese.strip() or None
    if body.stop_loss is not None:
        posicao.stop_loss = body.stop_loss if body.stop_loss > 0 else None
    if body.alvo_1 is not None:
        posicao.alvo_1 = body.alvo_1 if body.alvo_1 > 0 else None
    if body.alvo_2 is not None:
        posicao.alvo_2 = body.alvo_2 if body.alvo_2 > 0 else None
    if body.nome is not None:
        posicao.nome = body.nome.strip() or posicao.nome
    if body.modulo is not None:
        posicao.modulo = body.modulo.strip().lower() or posicao.modulo

    # Recalcula P&L se quantidade ou PM mudaram
    recalc = False
    if body.quantidade is not None and body.quantidade > 0:
        posicao.quantidade = round(body.quantidade, 6)
        recalc = True
    if body.preco_medio is not None and body.preco_medio > 0:
        posicao.preco_medio = round(body.preco_medio, 4)
        recalc = True
    if recalc:
        posicao.valor_investido = round(posicao.quantidade * posicao.preco_medio, 2)
        preco = posicao.preco_atual or posicao.preco_medio
        posicao.valor_atual = round(posicao.quantidade * preco, 2)
        posicao.pl_reais = round(posicao.valor_atual - posicao.valor_investido, 2)
        if posicao.valor_investido > 0:
            posicao.pl_percentual = round((posicao.valor_atual / posicao.valor_investido - 1) * 100, 2)
        _reconciliar_patrimonio(db, portfolio)

    db.commit()
    db.refresh(posicao)

    return {
        "mensagem": "Posição atualizada.",
        "ticker": posicao.ticker,
        "quantidade": posicao.quantidade,
        "preco_medio": posicao.preco_medio,
        "valor_investido": posicao.valor_investido,
        "valor_atual": posicao.valor_atual,
        "pl_reais": posicao.pl_reais,
        "pl_percentual": posicao.pl_percentual,
        "stop_loss": posicao.stop_loss,
        "alvo_1": posicao.alvo_1,
        "alvo_2": posicao.alvo_2,
        "tese": posicao.tese,
        "modulo": posicao.modulo,
    }


@router.post("/refresh-prices")
async def refresh_prices(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Busca cotação ao vivo para TODAS as posições ativas (B3 + NYSE + NASDAQ + BDR)
    e persiste preco_atual, valor_atual, pl_reais, pl_percentual no banco.
    Também atualiza patrimonio_total do portfólio.
    Chamado pelo frontend ao abrir a página de Posições.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()

    if not posicoes:
        return {"atualizadas": 0, "patrimonio_total": 0}

    # Filtra CAIXA — preço fixo 1.0, nunca buscar cotação
    for pos in posicoes:
        if pos.ticker == "CAIXA":
            pos.preco_atual = 1.0
            pos.valor_atual = pos.quantidade
            pos.valor_investido = pos.quantidade
            pos.pl_reais = 0.0
            pos.pl_percentual = 0.0

    posicoes_cotaveis = [p for p in posicoes if p.ticker != "CAIXA"]

    # Busca cotações em paralelo para todos os ativos
    tarefas = [
        get_dados_tecnicos(
            p.ticker,
            getattr(p, "mercado", None) or ("BDR" if p.tipo == "BDR" else "B3")
        )
        for p in posicoes_cotaveis
    ]
    resultados = await asyncio.gather(*tarefas, return_exceptions=True)

    atualizadas = 0
    patrimonio = 0.0

    # Inclui CAIXA no patrimônio (valor = quantidade, preço fixo 1.0)
    for pos in posicoes:
        if pos.ticker == "CAIXA":
            patrimonio += (pos.quantidade or 0)

    for pos, resultado in zip(posicoes_cotaveis, resultados):
        # Ignora erros ou ativos sem cotação disponível (RF, Opções, Caixa)
        if isinstance(resultado, Exception) or not isinstance(resultado, dict):
            patrimonio += (pos.valor_atual or pos.valor_investido or 0)
            continue

        preco_live = resultado.get("preco_atual")
        if not preco_live:
            patrimonio += (pos.valor_atual or pos.valor_investido or 0)
            continue

        moeda = getattr(pos, "moeda", "BRL") or "BRL"
        if moeda == "USD":
            # Para ativos USD: atualiza preco_atual mas não recalcula P&L em reais
            # (precisaria da cotação USD/BRL no momento da entrada)
            pos.preco_atual = round(preco_live, 2)
        else:
            valor_atual = preco_live * (pos.quantidade or 0)
            pl_reais = valor_atual - (pos.valor_investido or 0)
            pl_pct = (pl_reais / pos.valor_investido * 100) if (pos.valor_investido or 0) > 0 else 0
            pos.preco_atual = round(preco_live, 2)
            pos.valor_atual = round(valor_atual, 2)
            pos.pl_reais = round(pl_reais, 2)
            pos.pl_percentual = round(pl_pct, 2)
            patrimonio += valor_atual

        atualizadas += 1

    # Atualiza patrimonio do portfólio (apenas ativos BRL)
    if patrimonio > 0:
        portfolio.patrimonio_total = round(patrimonio, 2)

    db.commit()
    return {"atualizadas": atualizadas, "patrimonio_total": round(patrimonio, 2)}

class AtualizarAlocacao(BaseModel):
    nova_estrategia: str | None = None          # CORE | ALPHA | RENDA | CUSTOM
    nova_alocacao: dict[str, float] | None = None  # ex: {"etfs": 30, "fiis": 25, ...}


@router.patch("/alocacao")
def atualizar_alocacao(body: AtualizarAlocacao, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Atualiza estratégia e/ou alvos de alocação do portfólio.
    Chamado após aprovação de proposta do gestor IA.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    if body.nova_estrategia:
        if body.nova_estrategia not in ESTRATEGIAS_VALIDAS:
            raise HTTPException(status_code=400, detail=f"Estratégia inválida: {body.nova_estrategia}")
        user.estrategia = body.nova_estrategia
        db.add(user)

    if body.nova_alocacao:
        total = sum(body.nova_alocacao.values())
        if not (99.0 <= total <= 101.0):
            raise HTTPException(status_code=400, detail=f"Alocação deve somar 100%. Atual: {total:.1f}%")
        for modulo, valor in body.nova_alocacao.items():
            col = f"alvo_{modulo}"
            if hasattr(portfolio, col):
                setattr(portfolio, col, valor)
        # Se mudou alocação, marca como CUSTOM se não foi passada estratégia explícita
        if not body.nova_estrategia and user.estrategia not in ("CUSTOM",):
            user.estrategia = "CUSTOM"

    db.commit()

    # Invalida cache de sugestões do portfólio (alocação mudou)
    _portfolio_cache.delete(f"sugerir_portfolio:{portfolio.id}")

    return {
        "mensagem": "Alocação atualizada com sucesso.",
        "estrategia": user.estrategia,
        "nova_alocacao": {
            "etfs": portfolio.alvo_etfs,
            "fiis": portfolio.alvo_fiis,
            "renda_fixa": portfolio.alvo_renda_fixa,
            "momentum": portfolio.alvo_momentum,
            "wheel": portfolio.alvo_wheel,
            "alpha": portfolio.alvo_alpha,
            "dividendos": portfolio.alvo_dividendos,
            "caixa": portfolio.alvo_caixa,
        },
    }


# ─── Multi-Portfolio: listagem, ativação, criação ─────────────────────────────

@router.get("/listar")
def listar_portfolios(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Lista todos os portfólios do usuário com indicação de qual está ativo."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user.id).all()
    ativo_id = user.portfolio_ativo_id or (portfolios[0].id if portfolios else None)

    return [
        {
            "id": p.id,
            "nome": p.nome or "Carteira Real",
            "tipo": p.tipo or "real",
            "patrimonio_total": p.patrimonio_total or 0,
            "ativo": p.id == ativo_id,
        }
        for p in portfolios
    ]


@router.post("/ativar/{portfolio_id}")
def ativar_portfolio(portfolio_id: int, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Define o portfólio ativo do usuário."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = db.query(Portfolio).filter(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == user.id,
    ).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    user.portfolio_ativo_id = portfolio_id
    db.commit()
    return {"mensagem": f"Portfólio '{portfolio.nome}' ativado.", "portfolio_id": portfolio_id, "tipo": portfolio.tipo}


class CriarSimuladaBody(BaseModel):
    nome: str = "Carteira Simulada APEX"
    origem: str = "zero"    # "zero" | "copia" (copia do portfolio atual)


@router.post("/criar-simulada")
async def criar_carteira_simulada(body: CriarSimuladaBody, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Cria uma nova carteira simulada.
    origem='zero': carteira simulada vazia com os mesmos alvos do portfolio atual.
    origem='copia': clona todas as posições ativas do portfolio atual com preços do momento.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio_origem = get_portfolio_ativo(user, db)
    if not portfolio_origem:
        raise HTTPException(status_code=404, detail="Portfólio de origem não encontrado")

    # Cria novo portfolio simulado com os mesmos alvos
    novo = Portfolio(
        user_id=user.id,
        nome=body.nome,
        tipo="simulada",
        patrimonio_total=portfolio_origem.patrimonio_total or 0,
        patrimonio_inicio=portfolio_origem.patrimonio_total or 0,
        alvo_etfs=portfolio_origem.alvo_etfs,
        alvo_fiis=portfolio_origem.alvo_fiis,
        alvo_renda_fixa=portfolio_origem.alvo_renda_fixa,
        alvo_momentum=portfolio_origem.alvo_momentum,
        alvo_wheel=portfolio_origem.alvo_wheel,
        alvo_alpha=portfolio_origem.alvo_alpha,
        alvo_dividendos=getattr(portfolio_origem, "alvo_dividendos", 0.0) or 0.0,
        alvo_teses=getattr(portfolio_origem, "alvo_teses", 0.0) or 0.0,
        alvo_caixa=portfolio_origem.alvo_caixa,
    )
    db.add(novo)
    db.flush()  # garante novo.id antes de criar posições

    if body.origem == "copia":
        # Busca posições ativas do portfolio de origem
        posicoes_origem = db.query(Position).filter(
            Position.portfolio_id == portfolio_origem.id,
            Position.ativa == True,
        ).all()

        for p in posicoes_origem:
            copia = Position(
                portfolio_id=novo.id,
                ticker=p.ticker,
                nome=p.nome,
                tipo=p.tipo,
                modulo=p.modulo,
                quantidade=p.quantidade,
                preco_medio=p.preco_atual or p.preco_medio,   # entra ao preço atual
                preco_atual=p.preco_atual or p.preco_medio,
                valor_investido=(p.preco_atual or p.preco_medio) * p.quantidade,
                valor_atual=p.valor_atual or p.valor_investido,
                pl_reais=0.0,       # P&L começa do zero a partir deste momento
                pl_percentual=0.0,
                stop_loss=p.stop_loss,
                alvo_1=p.alvo_1,
                alvo_2=p.alvo_2,
                tese=p.tese,
                mercado=getattr(p, "mercado", None),
                moeda=getattr(p, "moeda", "BRL"),
                apex_score=p.apex_score,
            )
            db.add(copia)

    # Ativa a nova carteira
    user.portfolio_ativo_id = novo.id
    db.commit()

    return {
        "mensagem": f"Carteira simulada '{body.nome}' criada com sucesso.",
        "portfolio_id": novo.id,
        "tipo": "simulada",
        "origem": body.origem,
    }


@router.post("/criar-teste")
async def criar_carteira_teste(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Cria uma carteira real pré-alocada para testes.
    Usa posições representativas de uma estratégia APEX CORE com R$ 100.000.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    CAPITAL_TESTE = 100_000.0

    # Alvos: APEX CORE
    novo = Portfolio(
        user_id=user.id,
        nome="Carteira Alocada Teste",
        tipo="real",
        patrimonio_total=CAPITAL_TESTE,
        patrimonio_inicio=CAPITAL_TESTE,
        alvo_etfs=30.0,
        alvo_fiis=20.0,
        alvo_renda_fixa=15.0,
        alvo_momentum=15.0,
        alvo_dividendos=10.0,
        alvo_caixa=10.0,
        alvo_wheel=0.0,
        alvo_alpha=0.0,
        alvo_teses=0.0,
    )
    db.add(novo)
    db.flush()

    # Posições de teste — preços aproximados de fevereiro 2026
    _POSICOES_TESTE = [
        # ETFs (30% = R$ 30.000)
        dict(ticker="BOVA11", nome="iShares IBOVESPA ETF", tipo="ETF", modulo="etfs",
             quantidade=140, preco_medio=125.0, stop_loss=112.0),
        dict(ticker="IVVB11", nome="iShares S&P500 ETF", tipo="ETF", modulo="etfs",
             quantidade=25, preco_medio=500.0, stop_loss=450.0),
        # FIIs (20% = R$ 20.000)
        dict(ticker="KNRI11", nome="Kinea Renda Imobiliária", tipo="FII", modulo="fiis",
             quantidade=100, preco_medio=98.0, stop_loss=88.0),
        dict(ticker="HGLG11", nome="CSHG Logística FII", tipo="FII", modulo="fiis",
             quantidade=58, preco_medio=175.0, stop_loss=157.0),
        # Momentum (15% = R$ 15.000)
        dict(ticker="PETR4", nome="Petrobras PN", tipo="ACAO", modulo="momentum",
             quantidade=220, preco_medio=36.0, stop_loss=32.0),
        dict(ticker="VALE3", nome="Vale ON", tipo="ACAO", modulo="momentum",
             quantidade=130, preco_medio=55.0, stop_loss=49.0),
        # Dividendos (10% = R$ 10.000)
        dict(ticker="ITUB4", nome="Itaú Unibanco PN", tipo="ACAO", modulo="dividendos",
             quantidade=150, preco_medio=35.0, stop_loss=31.0),
        dict(ticker="WEGE3", nome="WEG ON", tipo="ACAO", modulo="dividendos",
             quantidade=110, preco_medio=43.0, stop_loss=38.0),
        # Renda Fixa (15% = R$ 15.000)
        dict(ticker="RF-SELIC", nome="Tesouro Selic 2029", tipo="RF", modulo="renda_fixa",
             quantidade=1, preco_medio=15000.0, stop_loss=None),
        # Caixa (10% = R$ 10.000)
        dict(ticker="CAIXA", nome="Caixa / Liquidez", tipo="CAIXA", modulo="caixa",
             quantidade=1, preco_medio=10000.0, stop_loss=None),
    ]

    for p in _POSICOES_TESTE:
        valor_investido = p["quantidade"] * p["preco_medio"]
        posicao = Position(
            portfolio_id=novo.id,
            ticker=p["ticker"],
            nome=p["nome"],
            tipo=p["tipo"],
            modulo=p["modulo"],
            quantidade=p["quantidade"],
            preco_medio=p["preco_medio"],
            preco_atual=p["preco_medio"],
            valor_investido=valor_investido,
            valor_atual=valor_investido,
            pl_reais=0.0,
            pl_percentual=0.0,
            stop_loss=p.get("stop_loss"),
            moeda="BRL",
        )
        db.add(posicao)

    # Ativa a nova carteira
    user.portfolio_ativo_id = novo.id
    db.commit()

    return {
        "mensagem": "Carteira Alocada Teste criada com sucesso! 10 posições de teste adicionadas.",
        "portfolio_id": novo.id,
        "tipo": "real",
        "capital": CAPITAL_TESTE,
        "posicoes": len(_POSICOES_TESTE),
    }


class CriarTeseBody(BaseModel):
    nome: str = "Carteira Tese"


@router.post("/criar-tese")
async def criar_carteira_tese(
    body: CriarTeseBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Cria uma carteira do tipo 'tese' — começa vazia,
    destinada a testar teses de investimento isoladas.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio_origem = get_portfolio_ativo(user, db)

    novo = Portfolio(
        user_id=user.id,
        nome=body.nome,
        tipo="tese",
        patrimonio_total=0.0,
        patrimonio_inicio=0.0,
        alvo_etfs=getattr(portfolio_origem, "alvo_etfs", 0.0) or 0.0,
        alvo_fiis=getattr(portfolio_origem, "alvo_fiis", 0.0) or 0.0,
        alvo_renda_fixa=getattr(portfolio_origem, "alvo_renda_fixa", 0.0) or 0.0,
        alvo_momentum=getattr(portfolio_origem, "alvo_momentum", 0.0) or 0.0,
        alvo_wheel=getattr(portfolio_origem, "alvo_wheel", 0.0) or 0.0,
        alvo_alpha=getattr(portfolio_origem, "alvo_alpha", 0.0) or 0.0,
        alvo_dividendos=getattr(portfolio_origem, "alvo_dividendos", 0.0) or 0.0,
        alvo_teses=getattr(portfolio_origem, "alvo_teses", 0.0) or 0.0,
        alvo_caixa=getattr(portfolio_origem, "alvo_caixa", 0.0) or 0.0,
    )
    db.add(novo)

    # Ativa a nova carteira
    user.portfolio_ativo_id = novo.id
    db.commit()

    return {
        "mensagem": f"Carteira tese '{body.nome}' criada com sucesso.",
        "portfolio_id": novo.id,
        "tipo": "tese",
    }


class CriarRealBody(BaseModel):
    nome: str = "Nova Carteira Real"
    capital_declarado: Optional[float] = None


@router.post("/criar-real")
def criar_carteira_real(
    body: CriarRealBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Cria uma nova carteira real vazia e a ativa."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio_origem = get_portfolio_ativo(user, db)

    novo = Portfolio(
        user_id=user.id,
        nome=body.nome.strip() or "Nova Carteira Real",
        tipo="real",
        patrimonio_total=0.0,
        patrimonio_inicio=0.0,
        capital_declarado=body.capital_declarado,
        alvo_etfs=getattr(portfolio_origem, "alvo_etfs", 0.0) or 0.0,
        alvo_fiis=getattr(portfolio_origem, "alvo_fiis", 0.0) or 0.0,
        alvo_renda_fixa=getattr(portfolio_origem, "alvo_renda_fixa", 0.0) or 0.0,
        alvo_momentum=getattr(portfolio_origem, "alvo_momentum", 0.0) or 0.0,
        alvo_wheel=getattr(portfolio_origem, "alvo_wheel", 0.0) or 0.0,
        alvo_alpha=getattr(portfolio_origem, "alvo_alpha", 0.0) or 0.0,
        alvo_dividendos=getattr(portfolio_origem, "alvo_dividendos", 0.0) or 0.0,
        alvo_teses=getattr(portfolio_origem, "alvo_teses", 0.0) or 0.0,
        alvo_caixa=getattr(portfolio_origem, "alvo_caixa", 0.0) or 0.0,
    )
    db.add(novo)
    user.portfolio_ativo_id = None
    db.flush()
    user.portfolio_ativo_id = novo.id
    db.commit()

    return {
        "mensagem": f"Carteira real '{novo.nome}' criada com sucesso.",
        "portfolio_id": novo.id,
        "tipo": "real",
    }


class CapitalBody(BaseModel):
    capital_declarado: float


@router.patch("/capital")
def atualizar_capital(
    body: CapitalBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Atualiza o capital declarado da carteira ativa (usado para calcular caixa disponível)."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")
    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")
    portfolio.capital_declarado = body.capital_declarado
    db.commit()
    return {"capital_declarado": portfolio.capital_declarado}


@router.delete("/all")
def deletar_todos_portfolios(
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Remove TODOS os portfólios do usuário — posições e transações incluídas.
    O usuário em si é preservado.
    Após a operação o usuário fica sem portfólio ativo (portfolio_ativo_id = None).
    """
    from app.models import Transacao, Briefing

    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user.id).all()

    total = len(portfolios)
    for portfolio in portfolios:
        # Briefings do portfólio
        db.query(Briefing).filter(Briefing.portfolio_id == portfolio.id).delete()
        # Posições e transações
        posicoes = db.query(Position).filter(Position.portfolio_id == portfolio.id).all()
        for pos in posicoes:
            db.query(Transacao).filter(Transacao.position_id == pos.id).delete()
            db.delete(pos)
        db.delete(portfolio)

    user.portfolio_ativo_id = None
    db.commit()

    return {
        "mensagem": f"{total} portfólio(s) deletado(s). Usuário mantido.",
        "portfolios_deletados": total,
    }


@router.delete("/{portfolio_id}")
def deletar_portfolio(
    portfolio_id: int,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Remove um portfólio do usuário.
    - Não permite deletar se for o único portfólio.
    - Se o portfólio deletado estiver ativo, ativa automaticamente outro.
    - Cascade: deleta todas as posições e transações do portfólio.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user.id).all()
    if len(portfolios) <= 1:
        raise HTTPException(status_code=400, detail="Não é possível deletar o único portfólio. Crie outro antes.")

    portfolio = next((p for p in portfolios if p.id == portfolio_id), None)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    era_ativo = (user.portfolio_ativo_id == portfolio_id)

    # Se era o ativo, ativa o próximo disponível
    if era_ativo:
        outro = next((p for p in portfolios if p.id != portfolio_id), None)
        user.portfolio_ativo_id = outro.id if outro else None

    # Cascade delete: posições e transações
    from app.models import Transacao
    posicoes = db.query(Position).filter(Position.portfolio_id == portfolio_id).all()
    for pos in posicoes:
        db.query(Transacao).filter(Transacao.position_id == pos.id).delete()
        db.delete(pos)

    db.delete(portfolio)
    db.commit()

    return {
        "mensagem": f"Portfólio '{portfolio.nome}' deletado com sucesso.",
        "novo_ativo_id": user.portfolio_ativo_id,
    }


# ─── Sugerir alocação para Carteira Simulada (perfil + capital) ───────────────

class SugerirAlocacaoBody(BaseModel):
    capital: float
    answers: dict   # mesmo formato do onboarding: volatility, liquidity, income, experience, time_available, objective, horizon


@router.post("/sugerir-alocacao")
async def sugerir_alocacao(body: SugerirAlocacaoBody):
    """
    Calcula o score de perfil e retorna a alocação recomendada + explicação.
    Reutiliza a mesma lógica do onboarding — não salva nada no banco.
    """
    from app.api.routes.onboarding import _calcular_score, _get_alocacao, _get_ai_explanation

    a = body.answers
    respostas = {
        "volatilidade": a.get("volatility"),
        "liquidez": a.get("liquidity"),
        "renda": a.get("income"),
        "experiencia": a.get("experience", []),
        "tempo": a.get("time_available"),
        "objetivo": a.get("objective"),
        "horizonte": a.get("horizon"),
    }

    score = _calcular_score(respostas)
    objetivo_declarado = a.get("goal_type", "")
    if objetivo_declarado == "renda":
        estrategia = "RENDA"
    elif score >= 11:
        estrategia = "ALPHA"
    else:
        estrategia = "CORE"

    alocacao = _get_alocacao(estrategia)

    return {
        "score": score,
        "estrategia": estrategia,
        "alocacao": alocacao,
        "explicacao": _get_ai_explanation(estrategia, score),
    }


class CriarSimuladaPerfilBody(BaseModel):
    nome: str = "Carteira Simulada APEX"
    capital: float
    alocacao: dict   # {etfs: 35, fiis: 20, renda_fixa: 20, momentum: 15, wheel: 0, alpha: 0, dividendos: 0, caixa: 10}


@router.post("/criar-simulada-perfil")
async def criar_carteira_simulada_perfil(
    body: CriarSimuladaPerfilBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Cria uma nova carteira simulada com capital e alocação definidos
    a partir do questionário de perfil (wizard SetupSimulada).
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    a = body.alocacao
    novo = Portfolio(
        user_id=user.id,
        nome=body.nome,
        tipo="simulada",
        patrimonio_total=body.capital,
        patrimonio_inicio=body.capital,
        alvo_etfs=float(a.get("etfs", 0)),
        alvo_fiis=float(a.get("fiis", 0)),
        alvo_renda_fixa=float(a.get("renda_fixa", 0)),
        alvo_momentum=float(a.get("momentum", 0)),
        alvo_wheel=float(a.get("wheel", 0)),
        alvo_alpha=float(a.get("alpha", 0)),
        alvo_dividendos=float(a.get("dividendos", 0)),
        alvo_teses=float(a.get("teses", 0)),
        alvo_caixa=float(a.get("caixa", 0)),
    )
    db.add(novo)
    user.portfolio_ativo_id = None  # será atualizado após flush
    db.flush()
    user.portfolio_ativo_id = novo.id
    db.commit()

    return {
        "mensagem": f"Carteira simulada '{body.nome}' criada com alocação personalizada.",
        "portfolio_id": novo.id,
        "tipo": "simulada",
        "capital": body.capital,
    }


# ─── Fase 1: Análise Estratégica (rápida, sem motores) ─────────────────────────

class AnalisarEstrategiaBody(BaseModel):
    portfolio_id: Optional[int] = None
    force_refresh: bool = False


@router.post("/analisar-estrategia")
async def analisar_estrategia(
    body: AnalisarEstrategiaBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Fase 1 do fluxo: gera análise executiva + plano estratégico com 3 cenários.
    NÃO roda motores, NÃO gera carteira — é rápido (~30-60s).
    O investidor escolhe o cenário desejado, depois chama sugerir-portfolio (Fase 2).
    """
    from app.cerebro import gestor as gestor_geral
    from app.data.cache import cache as _global_cache
    from app.cerebro.contexto import montar as montar_contexto

    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    if body.portfolio_id:
        portfolio = db.query(Portfolio).filter(
            Portfolio.id == body.portfolio_id,
            Portfolio.user_id == user.id,
        ).first()
    else:
        portfolio = get_portfolio_ativo(user, db)

    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    capital = portfolio.patrimonio_total or 0
    if capital <= 0:
        raise HTTPException(status_code=400, detail="Capital da carteira é zero.")

    # Cache separado da sugestão de carteira (TTL 1h)
    _CACHE_KEY = f"analise_estrategia:{portfolio.id}"
    _CACHE_TTL = 3600
    if not body.force_refresh:
        _cached = _portfolio_cache.get(_CACHE_KEY)
        if _cached:
            return _cached

    estrategia = (user.estrategia or "CORE").upper()

    # Contexto (posições existentes, macro)
    try:
        _ctx_cerebro = await montar_contexto(db, user_id=user.id)
    except Exception as _ctx_err:
        logger.warning("analisar-estrategia: falha contexto (%s)", _ctx_err)
        _ctx_cerebro = None

    _regime_cached = _global_cache.get("market:regime")
    _regime_str = str(_regime_cached.get("regime", "MISTO")) if _regime_cached else "MISTO"
    _score_perfil = getattr(user, "onboarding_score", None) or 7

    _user_data = {
        "nome": user.name,
        "objetivo_tipo": getattr(user, "objetivo_tipo", None),
        "objetivo_valor": getattr(user, "objetivo_valor", None),
        "objetivo_descricao": getattr(user, "objetivo_descricao", None),
        "objetivo_prazo": getattr(user, "objetivo_prazo", None),
        "aporte_mensal": getattr(user, "aporte_mensal", None),
        "onboarding_respostas": getattr(user, "onboarding_respostas", None),
    }

    resultado = await gestor_geral.analisar_estrategia(
        capital=capital,
        estrategia=estrategia,
        regime=_regime_str,
        score_perfil=_score_perfil,
        contexto=_ctx_cerebro,
        user_data=_user_data,
    )

    # Se o CEO recomendou plano, salva no banco
    if resultado.plano_estrategico:
        user.plano_estrategico = resultado.plano_estrategico
        if resultado.plano_estrategico.get("estrategia_recomendada"):
            _nova_est = resultado.plano_estrategico["estrategia_recomendada"]
            if _nova_est != user.estrategia:
                from app.api.routes.onboarding import _get_alocacao as _get_aloc
                user.estrategia = _nova_est
                _nova_aloc = _get_aloc(_nova_est)
                for k, v in _nova_aloc.items():
                    setattr(portfolio, f"alvo_{k}", v)
        db.commit()

    resposta = {
        "portfolio_id": portfolio.id,
        "capital_total": capital,
        "estrategia": estrategia,
        "gestor_analise": {
            "analise": resultado.analise,
            "alertas": resultado.alertas,
            "score_portfolio": resultado.score_perfil_mercado,
            "usou_ia": resultado.usou_ia,
            "regime": resultado.regime,
            "ajustes_realizados": [],
        },
        "plano_estrategico": resultado.plano_estrategico,
    }

    # Só cacheamos se a IA respondeu com sucesso — fallback não deve ser cacheado
    if resultado.usou_ia:
        _portfolio_cache.set(_CACHE_KEY, resposta, ttl=_CACHE_TTL)
    return resposta


# ─── Fase 2: Sugestão de portfólio completo via IA ───────────────────────────

class SugerirPortfolioBody(BaseModel):
    portfolio_id: Optional[int] = None   # None = usa carteira ativa
    force_refresh: bool = False          # True = ignora cache e recalcula
    modo: str = "inicial"                # "inicial" | "rebalanceamento"
    cenario_escolhido: Optional[str] = None  # "Conservador" | "Recomendado" | "Agressivo"


@router.post("/sugerir-portfolio")
async def sugerir_portfolio(
    body: SugerirPortfolioBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Sugere um portfólio completo usando os MOTORES de estratégia APEX.

    Cada módulo é processado por seu motor dedicado que usa dados reais de mercado:
      - ETFs:       motor_etfs     → alocação por perfil com preços yfinance
      - FIIs:       motor_fiis     → screener DY/P-VP com diversificação por segmento
      - Renda Fixa: motor_renda_fixa → mix SELIC/IPCA+/PRÉ por cenário macro
      - Momentum:   motor_momentum → screener RSI+MACD+MM com alvo e stop reais
      - Wheel:      motor_wheel    → COTAHIST B3 + scoring de opções + timing de entrada
      - Alpha:      motor_alpha    → screener fundamentalista P/L, P/VP, crescimento
      - Dividendos: motor_dividendos → DY real, payout, consistência, diversificação setorial
      - Caixa:      posição direta sem motor

    Os motores são os mesmos para carteira real e simulada — não existe diferença
    de lógica, apenas o destino do capital.
    """
    import asyncio
    from app.cerebro.especialistas import etfs as motor_etfs, fiis as motor_fiis, renda_fixa as motor_renda_fixa
    from app.cerebro.especialistas import momentum as motor_momentum, wheel as motor_wheel, alpha as motor_alpha, dividendos as motor_dividendos
    from app.cerebro.especialistas import prefetch as motor_prefetch
    from app.cerebro.especialistas.watchlist import (
        FIIS_WATCHLIST_FLAT, DIVIDENDOS_WATCHLIST, MOMENTUM_WATCHLIST,
        WHEEL_WATCHLIST, ALPHA_WATCHLIST, ETFS_WATCHLIST_FLAT,
    )

    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    if body.portfolio_id:
        portfolio = db.query(Portfolio).filter(
            Portfolio.id == body.portfolio_id,
            Portfolio.user_id == user.id,
        ).first()
    else:
        portfolio = get_portfolio_ativo(user, db)

    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    capital = portfolio.patrimonio_total or 0
    if capital <= 0:
        raise HTTPException(status_code=400, detail="Capital da carteira é zero. Ajuste o patrimônio antes.")

    # ── Cache: evita rodar todos os motores (2-5 min) a cada clique ──────────
    _cenario_tag = (body.cenario_escolhido or "Recomendado").strip().lower()
    _CACHE_KEY = f"sugerir_portfolio:{portfolio.id}:{_cenario_tag}"
    _CACHE_TTL = 1800  # 30 minutos
    if not body.force_refresh:
        _cached = _portfolio_cache.get(_CACHE_KEY)
        if _cached:
            return _cached

    estrategia = (user.estrategia or "CORE").upper()

    # ── Capital por módulo ────────────────────────────────────────────────────
    def _cap(pct_attr: str) -> float:
        pct = getattr(portfolio, pct_attr, 0) or 0
        return round(capital * pct / 100, 2)

    cap_etfs       = _cap("alvo_etfs")
    cap_fiis       = _cap("alvo_fiis")
    cap_rf         = _cap("alvo_renda_fixa")
    cap_momentum   = _cap("alvo_momentum")
    cap_wheel      = _cap("alvo_wheel")
    cap_alpha      = _cap("alvo_alpha")
    cap_dividendos = _cap("alvo_dividendos")
    cap_caixa      = _cap("alvo_caixa")

    # ── Dispara todos os motores com capital > 0 em paralelo ─────────────────

    _all_tickers: set[str] = set()
    if cap_etfs > 0:       _all_tickers.update(ETFS_WATCHLIST_FLAT)
    if cap_fiis > 0:       _all_tickers.update(FIIS_WATCHLIST_FLAT)
    if cap_dividendos > 0: _all_tickers.update(DIVIDENDOS_WATCHLIST)
    if cap_momentum > 0:   _all_tickers.update(MOMENTUM_WATCHLIST)
    if cap_wheel > 0:      _all_tickers.update(WHEEL_WATCHLIST)
    if cap_alpha > 0:      _all_tickers.update(ALPHA_WATCHLIST)
    if _all_tickers:
        try:
            await motor_prefetch.buscar(list(_all_tickers))
        except Exception as _pf_err:
            logger.warning("sugerir-portfolio: prefetch falhou (%s) — motores usarão fallback direto", _pf_err)

    # Tickers já em carteira: no modo inicial, motores não devem sugeri-los de novo.
    # No modo rebalanceamento, motores RE-AVALIAM tickers existentes para que o CEO
    # tenha scores atualizados e possa decidir MANTER/SAIR com evidência.
    _posicoes_db = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all() if portfolio else []
    _is_rebalanceamento = (body.modo == "rebalanceamento")
    _excluir_tickers = [] if _is_rebalanceamento else [
        p.ticker for p in _posicoes_db if p.ticker and p.ticker != "CAIXA"
    ]

    tarefas: list = []
    labels:  list = []

    if cap_etfs > 0:
        tarefas.append(motor_etfs.rodar(cap_etfs, estrategia=estrategia))
        labels.append("etfs")
    if cap_fiis > 0:
        tarefas.append(motor_fiis.rodar(cap_fiis, estrategia=estrategia, excluir_tickers=_excluir_tickers))
        labels.append("fiis")
    if cap_rf > 0:
        tarefas.append(motor_renda_fixa.rodar(cap_rf, estrategia=estrategia))
        labels.append("renda_fixa")
    if cap_momentum > 0:
        tarefas.append(motor_momentum.rodar(cap_momentum, excluir_tickers=_excluir_tickers))
        labels.append("momentum")
    if cap_wheel > 0:
        tarefas.append(motor_wheel.rodar(cap_wheel, excluir_tickers=_excluir_tickers, tickers_carteira=_excluir_tickers))
        labels.append("wheel")
    if cap_alpha > 0:
        tarefas.append(motor_alpha.rodar(cap_alpha, excluir_tickers=_excluir_tickers))
        labels.append("alpha")
    if cap_dividendos > 0:
        tarefas.append(motor_dividendos.rodar(cap_dividendos, excluir_tickers=_excluir_tickers))
        labels.append("dividendos")

    # Teses: módulo de convicção manual — capital é reservado e exibido para entrada manual
    cap_teses = _cap("alvo_teses")

    if not tarefas:
        raise HTTPException(status_code=400, detail="Nenhum módulo com alocação > 0%.")

    resultados = await asyncio.gather(*tarefas, return_exceptions=True)

    # ── Coleta todas as sugestões ─────────────────────────────────────────────
    sugestoes_raw = []
    motores_sem_resultado = []

    for label, resultado in zip(labels, resultados):
        if isinstance(resultado, Exception) or resultado is None:
            motores_sem_resultado.append(label)
            continue
        if not resultado:
            motores_sem_resultado.append(label)
            continue
        for item in resultado:
            sugestoes_raw.append(item)

    # ── Caixa explícito: entrega ao CEO como candidato com peso definido ──────
    from app.cerebro.especialistas import SugestaoMotor as _SM
    if cap_caixa > 0:
        sugestoes_raw.append(_SM(
            modulo="caixa", ticker="CAIXA", nome="Reserva de Liquidez",
            tipo="CAIXA", quantidade=cap_caixa, preco_atual=1.0, valor_total=cap_caixa,
            justificativa=(
                f"Caixa de {portfolio.alvo_caixa or 0:.0f}% configurado na estratégia "
                f"({cap_caixa:,.2f} de capital). Reserva para oportunidades e proteção."
            ),
            score=0.0, dados_extras={"tipo": "liquidez_imediata"},
        ))

    # ── CEO Brain: Gestor Geral analisa todos os candidatos e decide o portfólio final ──
    from app.cerebro import gestor as gestor_geral
    from app.data.cache import cache as _global_cache
    from app.cerebro.contexto import montar as montar_contexto

    # Contexto unificado — CEO vê as posições existentes para evitar duplicar teses
    try:
        _ctx_cerebro = await montar_contexto(db, user_id=user.id)
    except Exception as _ctx_err:
        logger.warning("sugerir-portfolio: falha ao montar ContextoCerebro (%s) — CEO opera sem histórico", _ctx_err)
        _ctx_cerebro = None

    # Regime do mercado — do cache compartilhado com o dashboard (TTL 1h)
    _regime_cached = _global_cache.get("market:regime")
    _regime_str = str(_regime_cached.get("regime", "MISTO")) if _regime_cached else "MISTO"

    # Score de perfil de risco do usuário (0-15, do onboarding)
    _score_perfil = getattr(user, "onboarding_score", None) or 7  # default: moderado

    # Capital que o CEO gerencia = total menos teses (teses são manuais, CEO não interfere)
    _capital_ceo = round(capital - cap_teses, 2)

    _user_data = {
        "nome": user.name,
        "objetivo_tipo": getattr(user, "objetivo_tipo", None),
        "objetivo_valor": getattr(user, "objetivo_valor", None),
        "objetivo_descricao": getattr(user, "objetivo_descricao", None),
        "objetivo_prazo": getattr(user, "objetivo_prazo", None),
        "aporte_mensal": getattr(user, "aporte_mensal", None),
        "onboarding_respostas": getattr(user, "onboarding_respostas", None),
    }

    resultado_ceo = await gestor_geral.analisar(
        candidatos=sugestoes_raw,
        capital=_capital_ceo,
        estrategia=estrategia,
        regime=_regime_str,
        score_perfil=_score_perfil,
        contexto=_ctx_cerebro,
        modo=body.modo,
        user_data=_user_data,
        cenario_escolhido=body.cenario_escolhido,
    )

    # Se o CEO gerou plano estratégico (primeiro portfólio), salva no banco
    if resultado_ceo.plano_estrategico:
        user.plano_estrategico = resultado_ceo.plano_estrategico
        if resultado_ceo.plano_estrategico.get("estrategia_recomendada"):
            _nova_est = resultado_ceo.plano_estrategico["estrategia_recomendada"]
            if _nova_est != user.estrategia:
                from app.api.routes.onboarding import _get_alocacao as _get_aloc
                user.estrategia = _nova_est
                _nova_aloc = _get_aloc(_nova_est)
                for k, v in _nova_aloc.items():
                    setattr(portfolio, f"alvo_{k}", v)
        db.commit()

    # ── Converte sugestões assinadas pelo CEO → dict compatível com o frontend ──
    sugestoes_enriquecidas = []
    for s in resultado_ceo.sugestoes_finais:
        sugestoes_enriquecidas.append({
            "modulo":        s.modulo,
            "ticker":        s.ticker,
            "nome":          s.nome,
            "tipo":          s.tipo,
            "quantidade":    s.quantidade,
            "preco_atual":   s.preco_atual,
            "valor_total":   s.valor_total,
            "justificativa": s.justificativa,
            "score":         s.score,
            "dados_extras":  s.dados_extras,
        })

    # ── Teses: capital reservado para gestão manual — CEO não interfere ───────
    if cap_teses > 0:
        sugestoes_enriquecidas.append({
            "modulo":    "teses",
            "ticker":    "TESES",
            "nome":      "Capital para Teses (Gestão Manual)",
            "tipo":      "CAIXA",
            "quantidade": cap_teses,
            "preco_atual": 1.0,
            "valor_total": cap_teses,
            "justificativa": (
                f"R${cap_teses:,.2f} reservados para o módulo Teses ({portfolio.alvo_teses or 0:.0f}% da carteira). "
                "Posições de convicção construídas manualmente — sem algoritmo de seleção automática."
            ),
            "score": 0,
            "dados_extras": {"tipo": "capital_reservado_gestao_manual"},
        })

    total_sugerido   = sum(s["valor_total"] for s in sugestoes_enriquecidas)
    capital_restante = max(round(capital - total_sugerido, 2), 0)

    resultado = {
        "portfolio_id":          portfolio.id,
        "capital_total":         capital,
        "total_sugerido":        round(total_sugerido, 2),
        "capital_restante":      capital_restante,
        "sugestoes":             sugestoes_enriquecidas,
        "observacao":            resultado_ceo.analise,
        "estrategia":            estrategia,
        "motores_executados":    labels,
        "motores_sem_resultado": motores_sem_resultado,
        # ── Análise assinada pelo Gestor Geral ──────────────────────────────
        "gestor_analise": {
            "analise":            resultado_ceo.analise,
            "alertas":            resultado_ceo.alertas,
            "ajustes_realizados": resultado_ceo.ajustes_realizados,
            "score_portfolio":    resultado_ceo.score_portfolio,
            "usou_ia":            resultado_ceo.usou_ia,
            "regime":             _regime_str,
        },
    }

    # ── Snapshot das posições atuais (para o frontend comparar antes × depois) ─
    if _is_rebalanceamento and _posicoes_db:
        resultado["posicoes_atuais"] = [
            {
                "ticker":        p.ticker,
                "nome":          p.nome or p.ticker,
                "tipo":          p.tipo,
                "modulo":        p.modulo,
                "quantidade":    p.quantidade,
                "preco_medio":   p.preco_medio,
                "preco_atual":   p.preco_atual or p.preco_medio,
                "valor_atual":   p.valor_atual or (p.quantidade * (p.preco_atual or p.preco_medio)),
                "pl_percentual": p.pl_percentual or 0,
                "stop_loss":     p.stop_loss,
                "data_entrada":  str(p.data_entrada) if p.data_entrada else None,
            }
            for p in _posicoes_db
        ]
    if resultado_ceo.plano_estrategico:
        resultado["plano_estrategico"] = resultado_ceo.plano_estrategico
    elif user and getattr(user, "plano_estrategico", None):
        # Plano já existe no banco (gerado em sessão anterior) — sempre reenviar
        resultado["plano_estrategico"] = user.plano_estrategico

    _portfolio_cache.set(_CACHE_KEY, resultado, ttl=_CACHE_TTL)
    return resultado


# ─── Aplicar sugestões aprovadas como posições reais ─────────────────────────

class SugestaoAplicarItem(BaseModel):
    ticker: str
    nome: str
    tipo: str
    modulo: str
    quantidade: float
    preco_atual: float
    justificativa: Optional[str] = None
    stop_loss: Optional[float] = None
    alvo_1: Optional[float] = None
    alvo_2: Optional[float] = None
    apex_score: Optional[int] = None


class AplicarSugestoesBody(BaseModel):
    portfolio_id: Optional[int] = None
    sugestoes: list[SugestaoAplicarItem]
    capital_caixa: float = 0.0   # capital de sugestões rejeitadas → vai para caixa


@router.post("/aplicar-sugestoes")
async def aplicar_sugestoes(
    body: AplicarSugestoesBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Aplica as sugestões aprovadas como posições reais na carteira simulada,
    usando os preços atuais de mercado. Capital de sugestões rejeitadas vai para caixa.
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    if body.portfolio_id:
        portfolio = db.query(Portfolio).filter(
            Portfolio.id == body.portfolio_id,
            Portfolio.user_id == user.id,
        ).first()
    else:
        portfolio = get_portfolio_ativo(user, db)

    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    # ── Prevenção de duplicatas: se já existem posições (exceto CAIXA), bloqueia ──
    posicoes_existentes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ticker != "CAIXA",
        Position.ativa == True,
    ).count()
    if posicoes_existentes > 0 and len(body.sugestoes) > 0:
        raise HTTPException(
            status_code=409,
            detail=f"Este portfólio já possui {posicoes_existentes} posição(ões). "
                   "Use rebalanceamento para ajustar."
        )

    criadas = []
    for s in body.sugestoes:
        # Usa sempre o preço da sugestão para garantir que a soma das posições
        # não ultrapasse o capital alocado (as quantidades foram calculadas com esses preços)
        preco_exec = s.preco_atual

        valor_inv = round(preco_exec * s.quantidade, 2)

        posicao = Position(
            portfolio_id=portfolio.id,
            ticker=s.ticker,
            nome=s.nome,
            tipo=s.tipo,
            modulo=s.modulo,
            quantidade=s.quantidade,
            preco_medio=round(preco_exec, 2),
            preco_atual=round(preco_exec, 2),
            valor_investido=valor_inv,
            valor_atual=valor_inv,
            pl_reais=0.0,
            pl_percentual=0.0,
            moeda="BRL",
            data_entrada=datetime.now(timezone.utc),
            justificativa_entrada=s.justificativa,
            stop_loss=s.stop_loss,
            alvo_1=s.alvo_1,
            alvo_2=s.alvo_2,
            apex_score=s.apex_score,
        )
        db.add(posicao)
        db.flush()  # gera o ID para o journal
        criadas.append(s.ticker)

        # TradeJournal: registrar entrada
        _registrar_journal(
            db, portfolio.id, posicao.id, s.ticker,
            tipo_op="ENTRADA", acao="ENTRAR",
            motivo=s.justificativa or "Sugestão inicial aceita",
            preco=preco_exec, quantidade=s.quantidade, valor_total=valor_inv,
            modulo=s.modulo,
        )

    # Capital rejeitado → adiciona/atualiza posição CAIXA
    if body.capital_caixa > 0.5:
        _atualizar_caixa(db, portfolio.id, body.capital_caixa)

    # Reconciliar patrimônio e atualizar alvos de alocação
    _reconciliar_patrimonio(db, portfolio)
    _atualizar_alvos_de_alocacao(db, portfolio)

    db.commit()

    return {
        "mensagem": f"{len(criadas)} posição(ões) criada(s) com sucesso.",
        "posicoes_criadas": criadas,
        "capital_caixa": body.capital_caixa,
    }


# ─── Aplicar rebalanceamento — MANTER / ENTRAR / SAIR / AJUSTAR ─────────────

class RebalAtivoItem(BaseModel):
    """Um ativo na carteira rebalanceada."""
    ticker: str
    nome: str
    tipo: str
    modulo: str
    quantidade: float
    preco_atual: float
    acao: str                               # MANTER | ENTRAR | AUMENTAR | REDUZIR
    justificativa: Optional[str] = None
    stop_loss: Optional[float] = None
    alvo_1: Optional[float] = None
    alvo_2: Optional[float] = None
    apex_score: Optional[int] = None


class SaidaItem(BaseModel):
    """Ativo removido na rebalanceamento."""
    ticker: str
    motivo: str


class AplicarRebalanceamentoBody(BaseModel):
    portfolio_id: Optional[int] = None
    ativos: list[RebalAtivoItem]            # carteira final (MANTER + ENTRAR + AJUSTAR)
    saidas: list[SaidaItem] = []            # ativos a desativar
    capital_caixa: float = 0.0              # sobra → caixa


@router.post("/aplicar-rebalanceamento")
async def aplicar_rebalanceamento(
    body: AplicarRebalanceamentoBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Aplica o rebalanceamento sugerido pelo CEO Brain (SOMENTE carteira simulada).
    Carteira real deve usar /gerar-plano-rebalanceamento para exportar PDF.
      - MANTER: não altera a posição
      - ENTRAR: cria nova posição
      - AUMENTAR/REDUZIR: atualiza quantidade e valores
      - SAÍDAS: marca posições como inativas, capital liberado → caixa
    """
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    if body.portfolio_id:
        portfolio = db.query(Portfolio).filter(
            Portfolio.id == body.portfolio_id,
            Portfolio.user_id == user.id,
        ).first()
    else:
        portfolio = get_portfolio_ativo(user, db)

    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    # ── Guard: carteira real não pode usar auto-apply ──
    if portfolio.tipo == "real":
        raise HTTPException(
            status_code=400,
            detail="Carteira real: use o Plano de Ação (PDF) para executar "
                   "na corretora e registre manualmente no app.",
        )

    # Mapa de posições atuais por ticker
    _posicoes_atuais = {
        p.ticker: p
        for p in db.query(Position).filter(
            Position.portfolio_id == portfolio.id,
            Position.ativa == True,
        ).all()
    }

    mantidas = []
    entradas = []
    ajustadas = []
    capital_liberado = 0.0       # capital que volta por REDUZIR / SAÍDA

    for a in body.ativos:
        if a.ticker == "CAIXA":
            continue  # caixa tratada separadamente abaixo

        existente = _posicoes_atuais.get(a.ticker)

        if a.acao == "MANTER" and existente:
            # Apenas atualiza justificativa se fornecida (mantém posição intacta)
            if a.justificativa:
                existente.justificativa_entrada = a.justificativa
            mantidas.append(a.ticker)

        elif a.acao == "ENTRAR" or not existente:
            # Nova posição
            valor_inv = round(a.preco_atual * a.quantidade, 2)
            nova_pos = Position(
                portfolio_id=portfolio.id,
                ticker=a.ticker,
                nome=a.nome,
                tipo=a.tipo,
                modulo=a.modulo,
                quantidade=a.quantidade,
                preco_medio=round(a.preco_atual, 2),
                preco_atual=round(a.preco_atual, 2),
                valor_investido=valor_inv,
                valor_atual=valor_inv,
                pl_reais=0.0,
                pl_percentual=0.0,
                moeda="BRL",
                data_entrada=datetime.now(timezone.utc),
                justificativa_entrada=a.justificativa,
                stop_loss=a.stop_loss,
                alvo_1=a.alvo_1,
                alvo_2=a.alvo_2,
                apex_score=a.apex_score,
            )
            db.add(nova_pos)
            db.flush()
            entradas.append(a.ticker)
            _registrar_journal(
                db, portfolio.id, nova_pos.id, a.ticker,
                tipo_op="ENTRADA", acao="ENTRAR",
                motivo=a.justificativa or "Rebalanceamento",
                preco=a.preco_atual, quantidade=a.quantidade, valor_total=valor_inv,
                modulo=a.modulo,
            )

        elif a.acao in ("AUMENTAR", "REDUZIR") and existente:
            # Ajusta quantidade e recalcula valores
            nova_qtd = a.quantidade
            if a.acao == "AUMENTAR":
                # Recalcula preço médio ponderado
                valor_antigo = existente.valor_investido or 0
                valor_novo = round(a.preco_atual * (nova_qtd - (existente.quantidade or 0)), 2)
                existente.valor_investido = round(valor_antigo + max(valor_novo, 0), 2)
                existente.quantidade = nova_qtd
                if nova_qtd > 0:
                    existente.preco_medio = round(existente.valor_investido / nova_qtd, 2)
            else:  # REDUZIR
                qtd_reduzida = (existente.quantidade or 0) - nova_qtd
                valor_liberado_pos = round(qtd_reduzida * a.preco_atual, 2)
                capital_liberado += max(valor_liberado_pos, 0)
                existente.quantidade = nova_qtd
                existente.valor_investido = round(nova_qtd * (existente.preco_medio or a.preco_atual), 2)

            existente.preco_atual = round(a.preco_atual, 2)
            existente.valor_atual = round(nova_qtd * a.preco_atual, 2)
            existente.pl_reais = round(existente.valor_atual - existente.valor_investido, 2)
            if existente.valor_investido > 0:
                existente.pl_percentual = round(
                    (existente.valor_atual / existente.valor_investido - 1) * 100, 2
                )
            if a.justificativa:
                existente.justificativa_entrada = a.justificativa
            if a.stop_loss is not None:
                existente.stop_loss = a.stop_loss
            if a.alvo_1 is not None:
                existente.alvo_1 = a.alvo_1
            ajustadas.append(f"{a.acao} {a.ticker}")

            _registrar_journal(
                db, portfolio.id, existente.id, a.ticker,
                tipo_op="AUMENTO" if a.acao == "AUMENTAR" else "REDUCAO",
                acao=a.acao,
                motivo=a.justificativa or "Rebalanceamento",
                preco=a.preco_atual, quantidade=a.quantidade,
                valor_total=round(a.preco_atual * a.quantidade, 2),
                modulo=a.modulo,
            )

    # Processar saídas
    saidas_executadas = []
    for s in body.saidas:
        pos = _posicoes_atuais.get(s.ticker)
        if pos and pos.ticker != "CAIXA":
            valor_saida = pos.valor_atual or round((pos.preco_atual or 0) * pos.quantidade, 2)
            capital_liberado += valor_saida
            pos.ativa = False
            pos.data_saida = datetime.now(timezone.utc)
            pos.motivo_saida = s.motivo
            saidas_executadas.append(s.ticker)

            _registrar_journal(
                db, portfolio.id, pos.id, s.ticker,
                tipo_op="SAIDA", acao="SAIR", motivo=s.motivo,
                preco=pos.preco_atual or 0, quantidade=pos.quantidade,
                valor_total=valor_saida, modulo=pos.modulo,
            )

    # ── Atualizar caixa: capital liberado de reduções/saídas + sobra do frontend ──
    caixa_total = capital_liberado + body.capital_caixa
    caixa_existente = _posicoes_atuais.get("CAIXA")
    if caixa_total > 0.5 or caixa_existente:
        novo_saldo_caixa = round(caixa_total, 2)
        if caixa_existente:
            caixa_existente.quantidade = novo_saldo_caixa
            caixa_existente.valor_investido = novo_saldo_caixa
            caixa_existente.valor_atual = novo_saldo_caixa
            caixa_existente.preco_medio = 1.0
            caixa_existente.preco_atual = 1.0
        elif novo_saldo_caixa > 0.5:
            db.add(Position(
                portfolio_id=portfolio.id,
                ticker="CAIXA",
                nome="Reserva de Liquidez",
                tipo="CAIXA",
                modulo="caixa",
                quantidade=novo_saldo_caixa,
                preco_medio=1.0,
                preco_atual=1.0,
                valor_investido=novo_saldo_caixa,
                valor_atual=novo_saldo_caixa,
                pl_reais=0.0,
                pl_percentual=0.0,
                moeda="BRL",
                data_entrada=datetime.now(timezone.utc),
            ))

    # Reconciliar patrimônio e atualizar alvos de alocação
    _reconciliar_patrimonio(db, portfolio)
    _atualizar_alvos_de_alocacao(db, portfolio)

    db.commit()

    return {
        "mensagem": "Rebalanceamento aplicado com sucesso.",
        "mantidas": mantidas,
        "entradas": entradas,
        "ajustadas": ajustadas,
        "saidas": saidas_executadas,
        "capital_caixa": round(caixa_total, 2),
    }


# ─── PDF do Plano de Rebalanceamento (carteira real) ─────────────────────────

class PlanoRebalItem(BaseModel):
    ticker: str
    nome: str
    tipo: str
    modulo: str
    acao: str                   # MANTER | ENTRAR | AUMENTAR | REDUZIR
    quantidade: float
    preco_atual: float
    valor_total: float
    quantidade_atual: Optional[float] = None   # para AUMENTAR/REDUZIR
    valor_atual_antes: Optional[float] = None


class PlanoSaidaItem(BaseModel):
    ticker: str
    motivo: str
    quantidade: Optional[float] = None
    valor_atual: Optional[float] = None


class GerarPlanoBody(BaseModel):
    portfolio_id: Optional[int] = None
    nome_carteira: str = "Carteira"
    ativos: list[PlanoRebalItem]
    saidas: list[PlanoSaidaItem] = []
    capital_caixa: float = 0.0


@router.post("/gerar-plano-rebalanceamento")
def gerar_plano_pdf(
    body: GerarPlanoBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Gera PDF com plano de ação para rebalanceamento de carteira real."""
    from fpdf import FPDF

    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    agora = datetime.now(timezone.utc)
    data_str = agora.strftime("%d/%m/%Y %H:%M")

    # ── Classificar itens ──
    compras = [a for a in body.ativos if a.acao in ("ENTRAR", "AUMENTAR")]
    vendas_parciais = [a for a in body.ativos if a.acao == "REDUZIR"]
    mantidos = [a for a in body.ativos if a.acao == "MANTER"]
    saidas = body.saidas

    total_compras = sum(a.valor_total for a in compras)
    total_vendas = sum(
        round((a.quantidade_atual or 0) * a.preco_atual - a.valor_total, 2) for a in vendas_parciais
    ) + sum(s.valor_atual or 0 for s in saidas)

    def fmt(v: float) -> str:
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    # ── Construir PDF ──
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Cabeçalho
    pdf.set_fill_color(15, 23, 42)       # slate-900
    pdf.rect(0, 0, 210, 35, 'F')
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(241, 245, 249)
    pdf.set_y(8)
    pdf.cell(0, 10, "APEX - Plano de Rebalanceamento", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 6, f"{body.nome_carteira}  |  Gerado em {data_str} UTC", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)

    def _tabela_header(cols: list[tuple[str, int]]):
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(148, 163, 184)
        for label, w in cols:
            pdf.cell(w, 7, label, border=0, fill=True, align="C")
        pdf.ln()

    def _tabela_row(cells: list[tuple[str, int]], bold: bool = False):
        pdf.set_font("Helvetica", "B" if bold else "", 8)
        pdf.set_text_color(30, 41, 59)
        for txt, w in cells:
            pdf.cell(w, 6, txt, border=0, align="C")
        pdf.ln()

    # ── Seção: COMPRAS ──
    if compras:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(0, 150, 50)
        pdf.cell(0, 8, f"COMPRAS ({len(compras)} ativos)", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        cols = [("Ticker", 25), ("Nome", 45), ("Acao", 22), ("Qtd", 20),
                ("Preco", 25), ("Valor", 30), ("Modulo", 25)]
        _tabela_header(cols)
        for a in compras:
            qtd_str = f"{a.quantidade:.0f}" if a.quantidade == int(a.quantidade) else f"{a.quantidade:.2f}"
            _tabela_row([
                (a.ticker, 25), (a.nome[:20], 45), (a.acao, 22), (qtd_str, 20),
                (fmt(a.preco_atual), 25), (fmt(a.valor_total), 30), (a.modulo, 25),
            ])
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 150, 50)
        pdf.cell(0, 7, f"Total Compras: {fmt(total_compras)}", align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    # ── Seção: VENDAS PARCIAIS (REDUZIR) ──
    if vendas_parciais:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(255, 152, 0)
        pdf.cell(0, 8, f"VENDAS PARCIAIS ({len(vendas_parciais)} ativos)", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        cols = [("Ticker", 25), ("Nome", 45), ("Qtd Antes", 22), ("Qtd Depois", 22),
                ("Preco", 25), ("Valor Depois", 30)]
        _tabela_header(cols)
        for a in vendas_parciais:
            qtd_antes = f"{a.quantidade_atual:.0f}" if a.quantidade_atual and a.quantidade_atual == int(a.quantidade_atual) else f"{(a.quantidade_atual or 0):.2f}"
            qtd_depois = f"{a.quantidade:.0f}" if a.quantidade == int(a.quantidade) else f"{a.quantidade:.2f}"
            _tabela_row([
                (a.ticker, 25), (a.nome[:20], 45), (qtd_antes, 22), (qtd_depois, 22),
                (fmt(a.preco_atual), 25), (fmt(a.valor_total), 30),
            ])
        pdf.ln(4)

    # ── Seção: SAÍDAS (vender tudo) ──
    if saidas:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(255, 82, 82)
        pdf.cell(0, 8, f"SAIDAS COMPLETAS ({len(saidas)} ativos)", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        cols = [("Ticker", 25), ("Motivo", 80), ("Qtd", 22), ("Valor Aprox.", 30)]
        _tabela_header(cols)
        for s in saidas:
            qtd_str = f"{s.quantidade:.0f}" if s.quantidade and s.quantidade == int(s.quantidade) else f"{(s.quantidade or 0):.2f}"
            _tabela_row([
                (s.ticker, 25), (s.motivo[:40], 80), (qtd_str, 22),
                (fmt(s.valor_atual or 0), 30),
            ])
        pdf.ln(4)

    # ── Seção: MANTER ──
    if mantidos:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 8, f"MANTER SEM ALTERACAO ({len(mantidos)} ativos)", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        cols = [("Ticker", 25), ("Nome", 55), ("Qtd", 22), ("Preco", 25), ("Valor", 30)]
        _tabela_header(cols)
        for a in mantidos:
            qtd_str = f"{a.quantidade:.0f}" if a.quantidade == int(a.quantidade) else f"{a.quantidade:.2f}"
            _tabela_row([
                (a.ticker, 25), (a.nome[:25], 55), (qtd_str, 22),
                (fmt(a.preco_atual), 25), (fmt(a.valor_total), 30),
            ])
        pdf.ln(4)

    # ── Resumo financeiro ──
    pdf.ln(3)
    pdf.set_draw_color(148, 163, 184)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(0, 7, f"Total a Comprar: {fmt(total_compras)}     |     "
                    f"Total a Vender: {fmt(total_vendas)}     |     "
                    f"Caixa: {fmt(body.capital_caixa)}",
             align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Rodapé ──
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 5,
             f"Gerado por APEX em {data_str} — Este é um plano sugestivo, não uma ordem de operação.",
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5,
             "Execute as operações na sua corretora e registre no app conforme executado.",
             align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Retornar PDF ──
    buf = io.BytesIO(pdf.output())
    buf.seek(0)
    filename = f"APEX_Plano_Rebalanceamento_{agora.strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

"""Rota de posições — CRUD de posições do portfólio."""
import asyncio
import logging
from datetime import datetime, timezone, date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id, get_portfolio_ativo
from app.models import User, Portfolio, Position
from app.models.transacao import Transacao
from app.data import get_quotes, get_fundamentals
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
    data_entrada: str | None = None  # ISO date string, ex: "2025-06-15"
    # Opções
    strike: float | None = None
    vencimento: str | None = None
    tipo_opcao: str | None = None
    premio_recebido: float | None = None
    # RF
    indexador: str | None = None
    taxa: float | None = None

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

    # Limpar análises IA de dias anteriores
    hoje = date.today()
    analises_limpas = False
    for p in posicoes:
        if p.analise_ia_at and p.analise_ia_at.date() < hoje:
            p.analise_ia = None
            p.analise_ia_at = None
            analises_limpas = True
    if analises_limpas:
        db.commit()

    tickers = [p.ticker for p in posicoes if p.tipo in ("ACAO", "FII", "ETF", "BDR")]
    cotacoes = await get_quotes(tickers) if tickers else {}

    # Para tickers sem cotação BRAPI, busca via get_dados_tecnicos (yfinance fallback)
    sem_cotacao = [p for p in posicoes if p.tipo in ("ACAO", "FII", "ETF", "BDR") and not cotacoes.get(p.ticker)]
    if sem_cotacao:
        tarefas = [get_dados_tecnicos(p.ticker, getattr(p, "mercado", None) or "B3") for p in sem_cotacao]
        resultados_yf = await asyncio.gather(*tarefas, return_exceptions=True)
        for p, res in zip(sem_cotacao, resultados_yf):
            if isinstance(res, dict) and res.get("preco_atual"):
                cotacoes[p.ticker] = {"regularMarketPrice": res["preco_atual"]}

    resultado = []
    preco_mudou = False
    for p in posicoes:
        cotacao = cotacoes.get(p.ticker, {})
        preco_atual = cotacao.get("regularMarketPrice", p.preco_atual or p.preco_medio)
        valor_atual = preco_atual * p.quantidade
        pl_reais = valor_atual - p.valor_investido
        pl_pct = (pl_reais / p.valor_investido * 100) if p.valor_investido > 0 else 0

        # Persistir preços atualizados no banco
        if cotacao.get("regularMarketPrice") and cotacao["regularMarketPrice"] != p.preco_atual:
            p.preco_atual = round(preco_atual, 2)
            p.valor_atual = round(valor_atual, 2)
            p.pl_reais = round(pl_reais, 2)
            p.pl_percentual = round(pl_pct, 2)
            preco_mudou = True

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
            "alvo_2": p.alvo_2,
            "apex_score": p.apex_score,
            "data_entrada": p.data_entrada,
            "data_abertura": p.data_abertura,
            "mercado": p.mercado,
            "moeda": p.moeda,
            # Tese
            "tese": p.tese,
            # Análise AI
            "analise_ia": p.analise_ia,
            "analise_ia_at": p.analise_ia_at.isoformat() if p.analise_ia_at else None,
            "justificativa_entrada": p.justificativa_entrada,
            # Wheel
            "strike": p.strike,
            "vencimento": p.vencimento,
            "tipo_opcao": p.tipo_opcao,
            "premio_recebido": p.premio_recebido,
        })

    if preco_mudou:
        db.commit()

    # Caixa disponível: capital declarado - soma dos valores atuais investidos
    capital_declarado = getattr(portfolio, "capital_declarado", None)
    soma_posicoes = sum(r["valor_atual"] for r in resultado)
    caixa_disponivel = round(capital_declarado - soma_posicoes, 2) if capital_declarado else None

    return {
        "posicoes": resultado,
        "capital_declarado": capital_declarado,
        "caixa_disponivel": caixa_disponivel,
    }


@router.get("/posicoes/historico")
def listar_posicoes_historico(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Lista posições encerradas (ativa=False) com P&L de saída."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == False,
    ).order_by(Position.data_saida.desc()).all()

    resultado = []
    for p in posicoes:
        # Duração do trade
        duracao_dias = None
        if p.data_abertura and p.data_saida:
            duracao_dias = (p.data_saida - p.data_abertura).days
        elif p.data_entrada and p.data_saida:
            duracao_dias = (p.data_saida - p.data_entrada).days

        resultado.append({
            "id": p.id,
            "ticker": p.ticker,
            "nome": p.nome or p.ticker,
            "tipo": p.tipo,
            "modulo": p.modulo,
            "quantidade": p.quantidade,
            "preco_medio": p.preco_medio,
            "preco_atual": p.preco_atual,
            "valor_investido": p.valor_investido,
            "pl_reais": p.pl_reais,
            "pl_percentual": p.pl_percentual,
            "data_abertura": p.data_abertura.isoformat() if p.data_abertura else (p.data_entrada.isoformat() if p.data_entrada else None),
            "data_saida": p.data_saida.isoformat() if p.data_saida else None,
            "motivo_saida": p.motivo_saida,
            "duracao_dias": duracao_dias,
        })

    return {"posicoes": resultado}


@router.delete("/posicoes/{posicao_id}/permanente")
def deletar_posicao_permanente(posicao_id: int, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Remove permanentemente uma posição encerrada (e suas transações) do histórico."""
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
    if posicao.ativa:
        raise HTTPException(status_code=400, detail="Só é possível deletar posições encerradas")

    # Remove transações associadas
    db.query(Transacao).filter(Transacao.position_id == posicao_id).delete()
    # Remove trade journal entries
    from app.models.trade_journal import TradeJournal
    db.query(TradeJournal).filter(TradeJournal.position_id == posicao_id).delete()
    # Remove posição
    db.delete(posicao)
    db.commit()

    return {"mensagem": f"Posição {posicao.ticker} removida do histórico."}


@router.post("/posicoes")
def adicionar_posicao(body: NovaPosicao, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Adiciona uma nova posição ao portfólio."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    valor_investido = body.quantidade * body.preco_medio
    vencimento = datetime.fromisoformat(body.vencimento) if body.vencimento else None

    # Data de entrada: usa a fornecida pelo usuário ou default=agora
    data_entrada = None
    if body.data_entrada:
        try:
            data_entrada = datetime.fromisoformat(body.data_entrada)
        except Exception:
            data_entrada = None

    posicao = Position(
        portfolio_id=portfolio.id,
        ticker=body.ticker.upper(),
        nome=body.nome,
        tipo=body.tipo,
        modulo=body.modulo,
        quantidade=body.quantidade,
        preco_medio=body.preco_medio,
        valor_investido=valor_investido,
        stop_loss=body.stop_loss,
        strike=body.strike,
        vencimento=vencimento,
        tipo_opcao=body.tipo_opcao,
        premio_recebido=body.premio_recebido,
        indexador=body.indexador,
        taxa=body.taxa,
    )
    if data_entrada:
        posicao.data_entrada = data_entrada
        posicao.data_abertura = data_entrada
    db.add(posicao)
    db.flush()

    # Auto-cria transação inicial de compra
    db.add(Transacao(
        portfolio_id=portfolio.id,
        position_id=posicao.id,
        tipo="compra",
        data=data_entrada or posicao.data_entrada or datetime.now(timezone.utc),
        quantidade=body.quantidade,
        preco=body.preco_medio,
        valor_total=valor_investido,
        taxas=0.0,
        observacao="Compra inicial (posição criada manualmente)",
    ))
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

    # Calcula P&L de saída usando preço atual vs preço médio
    preco_saida = posicao.preco_atual or posicao.preco_medio
    if posicao.preco_medio and posicao.preco_medio > 0 and posicao.quantidade > 0:
        posicao.pl_reais = (preco_saida - posicao.preco_medio) * posicao.quantidade
        posicao.pl_percentual = ((preco_saida / posicao.preco_medio) - 1) * 100

    posicao.ativa = False
    posicao.data_saida = datetime.now(timezone.utc)
    posicao.motivo_saida = motivo
    db.commit()

    return {
        "mensagem": f"Posição {posicao.ticker} encerrada.",
        "pl_reais": posicao.pl_reais,
        "pl_percentual": posicao.pl_percentual,
    }


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


class AtualizarPosicao(BaseModel):
    tese: str | None = None           # Nova tese de investimento
    stop_loss: float | None = None    # Novo stop
    alvo_1: float | None = None       # Novo alvo 1
    alvo_2: float | None = None       # Novo alvo 2
    nome: str | None = None           # Renomear
    quantidade: float | None = None   # Editar quantidade
    preco_medio: float | None = None  # Editar preço médio
    modulo: str | None = None         # Trocar módulo
    analise_ia: str | None = None     # Salvar análise AI
    data_abertura: str | None = None  # Editar data de abertura (ISO)


@router.patch("/posicoes/{posicao_id}")
def atualizar_posicao(posicao_id: int, body: AtualizarPosicao, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Atualiza campos editáveis de uma posição: tese, stop, alvo, quantidade, PM, módulo, análise IA.
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
        posicao.stop_loss = body.stop_loss if body.stop_loss != 0 else None
    if body.alvo_1 is not None:
        posicao.alvo_1 = body.alvo_1 if body.alvo_1 != 0 else None
    if body.alvo_2 is not None:
        posicao.alvo_2 = body.alvo_2 if body.alvo_2 != 0 else None
    if body.nome is not None:
        posicao.nome = body.nome.strip() or posicao.nome
    if body.modulo is not None:
        posicao.modulo = body.modulo
    if body.data_abertura is not None:
        try:
            posicao.data_abertura = datetime.fromisoformat(body.data_abertura)
            posicao.data_entrada = posicao.data_abertura
        except (ValueError, TypeError):
            pass
    if body.analise_ia is not None:
        posicao.analise_ia = body.analise_ia.strip() or None
        posicao.analise_ia_at = datetime.now(timezone.utc)

    # Recalcula P&L se quantidade ou preço médio mudaram
    recalc = False
    if body.quantidade is not None and body.quantidade > 0:
        posicao.quantidade = body.quantidade
        recalc = True
    if body.preco_medio is not None and body.preco_medio > 0:
        posicao.preco_medio = body.preco_medio
        recalc = True
    if recalc:
        posicao.valor_investido = posicao.quantidade * posicao.preco_medio
        preco_at = posicao.preco_atual or posicao.preco_medio
        posicao.valor_atual = posicao.quantidade * preco_at
        posicao.pl_reais = posicao.valor_atual - posicao.valor_investido
        posicao.pl_percentual = (posicao.pl_reais / posicao.valor_investido * 100) if posicao.valor_investido > 0 else 0

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
        "modulo": posicao.modulo,
        "analise_ia": posicao.analise_ia,
        "analise_ia_at": posicao.analise_ia_at.isoformat() if posicao.analise_ia_at else None,
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

    # Busca cotações em paralelo para todos os ativos
    tarefas = [
        get_dados_tecnicos(
            p.ticker,
            getattr(p, "mercado", None) or "B3"
        )
        for p in posicoes
    ]
    resultados = await asyncio.gather(*tarefas, return_exceptions=True)

    atualizadas = 0
    patrimonio = 0.0

    for pos, resultado in zip(posicoes, resultados):
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


class AtualizarPortfolioNomeBody(BaseModel):
    nome: str


def _atualizar_nome_portfolio_impl(portfolio_id: int, body: AtualizarPortfolioNomeBody, user_id: Optional[int], db: Session):
    """Lógica compartilhada para PATCH e POST."""
    nome = (body.nome or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome da carteira não pode ser vazio.")
    if len(nome) > 100:
        raise HTTPException(status_code=400, detail="Nome deve ter no máximo 100 caracteres.")
    user = (db.query(User).filter(User.id == user_id).first() if user_id else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")
    portfolio = db.query(Portfolio).filter(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == user.id,
    ).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")
    portfolio.nome = nome
    db.commit()
    db.refresh(portfolio)
    return {"ok": True, "nome": portfolio.nome}


@router.patch("/{portfolio_id}/nome")
def atualizar_nome_portfolio(
    portfolio_id: int,
    body: AtualizarPortfolioNomeBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """Atualiza o nome de um portfólio."""
    return _atualizar_nome_portfolio_impl(portfolio_id, body, user_id, db)


@router.post("/{portfolio_id}/atualizar-nome")
def atualizar_nome_portfolio_post(
    portfolio_id: int,
    body: AtualizarPortfolioNomeBody,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db)
):
    """Atualiza o nome de um portfólio (alias POST para compatibilidade)."""
    return _atualizar_nome_portfolio_impl(portfolio_id, body, user_id, db)


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
        db.flush()

        # Auto-cria transação inicial de compra
        db.add(Transacao(
            portfolio_id=novo.id,
            position_id=posicao.id,
            tipo="compra",
            data=datetime.now(timezone.utc),
            quantidade=p["quantidade"],
            preco=p["preco_medio"],
            valor_total=valor_investido,
            taxas=0.0,
            observacao="Compra inicial (carteira teste)",
        ))

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


# ─── Sugestão de portfólio completo via IA ────────────────────────────────────

class SugerirPortfolioBody(BaseModel):
    portfolio_id: Optional[int] = None   # None = usa carteira ativa
    force_refresh: bool = False          # True = ignora cache e recalcula
    modo: str = "inicial"                # "inicial" | "rebalanceamento"


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
        WHEEL_WATCHLIST, ALPHA_WATCHLIST,
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
    _CACHE_KEY = f"sugerir_portfolio:{portfolio.id}"
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

    # ── Kill Switch pre-check (Fase 5/7) ─────────────────────────────────
    # Se kill switch nível ≥ 2 (PAUSA TOTAL), NÃO roda motores — preserva capital
    try:
        from app.cerebro.macro import montar_macro as _montar_macro_ks
        from app.cerebro.hold import avaliar_kill_switch
        _macro_ks = await _montar_macro_ks()
        _regime_ks = getattr(_macro_ks, "regime_macro", "NEUTRO") or "NEUTRO"
        _confianca_ks = getattr(_macro_ks, "confianca", 50)
        _score_ks = getattr(_macro_ks, "regime_score", 50)
        _ks = avaliar_kill_switch(_regime_ks, _confianca_ks, _score_ks)
        if _ks.ativo and _ks.nivel >= 2:
            logger.warning("sugerir-portfolio: KILL SWITCH nível %d — BLOQUEANDO motores. %s", _ks.nivel, _ks.motivo)
            return {
                "portfolio_id": portfolio.id,
                "capital_total": capital,
                "total_sugerido": 0,
                "capital_restante": capital,
                "sugestoes": [],
                "analise_ceo": (
                    f"⚠️ KILL SWITCH MACRO ATIVO (nível {_ks.nivel} — PAUSA TOTAL)\n\n"
                    f"**Motivo:** {_ks.motivo}\n\n"
                    f"**Recomendação:** {_ks.recomendacao}\n\n"
                    "Os motores de seleção foram **bloqueados** enquanto o kill switch estiver ativo. "
                    "Nenhuma nova posição de risco deve ser aberta. "
                    "Mantenha as posições existentes em monitoramento e priorize renda fixa e caixa."
                ),
                "alertas": [f"KILL SWITCH nível {_ks.nivel}: {_ks.motivo}"],
                "motores_sem_resultado": [],
                "score_portfolio": 0,
            }
        elif _ks.ativo and _ks.nivel == 1:
            logger.warning("sugerir-portfolio: KILL SWITCH nível 1 (ALERTA) — motores rodam com warning")
    except Exception as _ks_err:
        logger.debug("sugerir-portfolio: kill switch check falhou (%s) — prosseguindo", _ks_err)

    # Pre-fetch: busca dados de mercado UMA VEZ antes de disparar os motores
    # Isso evita que 7 motores chamem yfinance para os mesmos tickers
    _all_tickers: set[str] = set()
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

    # Tickers já em carteira: motores não devem sugeri-los de novo
    _posicoes_db = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all() if portfolio else []
    _excluir_tickers = [p.ticker for p in _posicoes_db if p.ticker and p.ticker != "CAIXA"]

    tarefas: list = []
    labels:  list = []

    # ── Ranking setorial (Fase 2 — bonus/penalty nos motores equity) ──────
    _ranking_setorial = None
    _regime = "NEUTRO"
    try:
        from app.cerebro.setor import montar_ranking
        from app.cerebro.macro import montar_macro
        _macro_ctx = await montar_macro()
        _ranking_setorial = await montar_ranking(_macro_ctx)
        _regime = getattr(_macro_ctx, "regime_macro", "NEUTRO") or "NEUTRO"
    except Exception as _rs_err:
        logger.warning("sugerir-portfolio: ranking setorial falhou (%s) — motores sem ajuste", _rs_err)

    # ── Circuit breaker + Heat (Fase 4) ───────────────────────────────────
    _cb_modifier = 1.0
    try:
        from app.cerebro.sizing import avaliar_circuit_breaker, calcular_heat
        _patrim_inicio_mes = portfolio.patrimonio_mes_inicio or capital
        _pl_mes_pct = ((capital - _patrim_inicio_mes) / _patrim_inicio_mes * 100) if _patrim_inicio_mes > 0 else 0.0
        _cb = avaliar_circuit_breaker(_pl_mes_pct)
        _cb_modifier = _cb.sizing_modifier
        if _cb.ativo:
            logger.warning("sugerir-portfolio: CIRCUIT BREAKER ATIVO — %s", _cb.motivo)
    except Exception as _cb_err:
        logger.warning("sugerir-portfolio: circuit breaker falhou (%s)", _cb_err)

    # Parâmetros compartilhados para sizing
    _sizing_kwargs = {
        "patrimonio_total": capital,
        "regime": _regime,
        "cb_modifier": _cb_modifier,
    }

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
        tarefas.append(motor_momentum.rodar(cap_momentum, excluir_tickers=_excluir_tickers, ranking_setorial=_ranking_setorial, **_sizing_kwargs))
        labels.append("momentum")
    if cap_wheel > 0:
        tarefas.append(motor_wheel.rodar(cap_wheel, excluir_tickers=_excluir_tickers, tickers_carteira=_excluir_tickers))
        labels.append("wheel")
    if cap_alpha > 0:
        tarefas.append(motor_alpha.rodar(cap_alpha, excluir_tickers=_excluir_tickers, ranking_setorial=_ranking_setorial, **_sizing_kwargs))
        labels.append("alpha")
    if cap_dividendos > 0:
        tarefas.append(motor_dividendos.rodar(cap_dividendos, excluir_tickers=_excluir_tickers, ranking_setorial=_ranking_setorial, **_sizing_kwargs))
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

    resultado_ceo = await gestor_geral.analisar(
        candidatos=sugestoes_raw,
        capital=_capital_ceo,
        estrategia=estrategia,
        regime=_regime_str,
        score_perfil=_score_perfil,
        contexto=_ctx_cerebro,
        modo=body.modo,
    )

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
        )
        db.add(posicao)
        db.flush()

        # Auto-cria transação inicial de compra
        db.add(Transacao(
            portfolio_id=portfolio.id,
            position_id=posicao.id,
            tipo="compra",
            data=datetime.now(timezone.utc),
            quantidade=s.quantidade,
            preco=round(preco_exec, 2),
            valor_total=valor_inv,
            taxas=0.0,
            observacao="Compra inicial (sugestão aceita)",
        ))
        criadas.append(s.ticker)

    # Capital rejeitado → adiciona/atualiza posição CAIXA
    if body.capital_caixa > 0.5:
        caixa_existente = db.query(Position).filter(
            Position.portfolio_id == portfolio.id,
            Position.ticker == "CAIXA",
            Position.ativa == True,
        ).first()

        if caixa_existente:
            caixa_existente.quantidade = round(caixa_existente.quantidade + body.capital_caixa, 2)
            caixa_existente.preco_medio = 1.0
            caixa_existente.preco_atual = 1.0
            caixa_existente.valor_investido = round(caixa_existente.valor_investido + body.capital_caixa, 2)
            caixa_existente.valor_atual = caixa_existente.valor_investido
        else:
            db.add(Position(
                portfolio_id=portfolio.id,
                ticker="CAIXA",
                nome="Reserva de Liquidez",
                tipo="CAIXA",
                modulo="caixa",
                quantidade=body.capital_caixa,
                preco_medio=1.0,
                preco_atual=1.0,
                valor_investido=body.capital_caixa,
                valor_atual=body.capital_caixa,
                pl_reais=0.0,
                pl_percentual=0.0,
                moeda="BRL",
                data_entrada=datetime.now(timezone.utc),
            ))

    db.commit()

    return {
        "mensagem": f"{len(criadas)} posição(ões) criada(s) com sucesso.",
        "posicoes_criadas": criadas,
        "capital_caixa": body.capital_caixa,
    }


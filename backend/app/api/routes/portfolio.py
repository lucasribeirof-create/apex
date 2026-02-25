"""Rota de posições — CRUD de posições do portfólio."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Position
from app.data import get_quotes

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

MODULOS_VALIDOS = {"etfs", "fiis", "renda_fixa", "momentum", "wheel", "alpha", "dividendos", "caixa"}
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


@router.get("/posicoes")
async def listar_posicoes(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Lista todas as posições ativas com cotação atualizada."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
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
            # Wheel
            "strike": p.strike,
            "vencimento": p.vencimento,
            "tipo_opcao": p.tipo_opcao,
            "premio_recebido": p.premio_recebido,
        })

    return resultado


@router.post("/posicoes")
def adicionar_posicao(body: NovaPosicao, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Adiciona uma nova posição ao portfólio."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    valor_investido = body.quantidade * body.preco_medio
    vencimento = datetime.fromisoformat(body.vencimento) if body.vencimento else None

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
    db.add(posicao)
    db.commit()
    db.refresh(posicao)

    return {"id": posicao.id, "mensagem": f"Posição {body.ticker} adicionada com sucesso."}


@router.delete("/posicoes/{posicao_id}")
def encerrar_posicao(posicao_id: int, motivo: str = "Encerrado manualmente", db: Session = Depends(get_db)):
    """Marca uma posição como encerrada."""
    posicao = db.query(Position).filter(Position.id == posicao_id).first()
    if not posicao:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    posicao.ativa = False
    posicao.data_saida = datetime.utcnow()
    posicao.motivo_saida = motivo
    db.commit()

    return {"mensagem": f"Posição {posicao.ticker} encerrada."}


# ─── Gestão de estratégia e alocação ─────────────────────────────────────────

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

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
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


"""Módulo Teses — Buy & Hold por convicção com histórico de DCA."""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Position, Aporte
from app.data import get_quotes
from app.data.yfinance_client import get_dolar_yf

router = APIRouter(prefix="/teses", tags=["teses"])

MERCADOS_VALIDOS = {"B3", "BDR", "NYSE", "NASDAQ", "AMEX"}

# ─── Schemas ──────────────────────────────────────────────────────────────────

class NovaTese(BaseModel):
    ticker: str
    nome: str | None = None
    tese: str                         # convicção escrita pelo usuário
    tipo: str = "ACAO"                # ACAO | ETF | BDR | FII
    mercado: str = "B3"               # B3 | BDR | NYSE | NASDAQ | AMEX
    moeda: str = "BRL"                # BRL | USD
    # Primeiro aporte
    quantidade: float
    preco_medio: float                # em BRL se moeda=BRL, em USD se moeda=USD
    data_entrada: str | None = None   # ISO date string, default hoje
    nota_aporte: str | None = None

class NovoAporte(BaseModel):
    quantidade: float
    preco: float                      # em BRL ou USD conforme moeda da posição
    data: str | None = None           # ISO date string, default hoje
    nota: str | None = None

class AtualizarTese(BaseModel):
    tese: str | None = None
    nome: str | None = None

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_portfolio(user_id: int | None, db: Session) -> Portfolio:
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")
    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")
    return portfolio

async def _preco_atual(ticker: str, moeda: str) -> float | None:
    """Busca preço atual — B3/BDR via brapi, US direto via yfinance ticker."""
    if moeda == "USD":
        # Ação americana — usa yfinance diretamente com sufixo removido
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            p = t.fast_info.last_price
            return float(p) if p else None
        except Exception:
            return None
    else:
        cotacoes = await get_quotes([ticker])
        return cotacoes.get(ticker, {}).get("regularMarketPrice")

# ─── Rotas ────────────────────────────────────────────────────────────────────

@router.get("")
async def listar_teses(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Lista todas as posições do módulo Teses com cotação atual."""
    portfolio = _get_portfolio(user_id, db)

    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.modulo == "teses",
        Position.ativa == True,
    ).all()

    # Busca cotações
    tickers_brl = [p.ticker for p in posicoes if (p.moeda or "BRL") == "BRL"]
    tickers_usd = [p.ticker for p in posicoes if (p.moeda or "BRL") == "USD"]

    cotacoes_brl = await get_quotes(tickers_brl) if tickers_brl else {}

    # Para USD, busca individualmente via yfinance
    cotacoes_usd: dict[str, float] = {}
    for ticker in tickers_usd:
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            p = t.fast_info.last_price
            if p:
                cotacoes_usd[ticker] = float(p)
        except Exception:
            pass

    # Dólar atual para conversão
    dolar_info = await get_dolar_yf()
    dolar_brl = dolar_info.get("price", 5.0) if dolar_info else 5.0

    resultado = []
    for p in posicoes:
        moeda = p.moeda or "BRL"
        if moeda == "USD":
            preco_usd = cotacoes_usd.get(p.ticker, p.preco_medio_usd or p.preco_medio)
            preco_brl = preco_usd * dolar_brl
            valor_investido_brl = (p.valor_investido_usd or p.valor_investido) * dolar_brl
        else:
            preco_brl = cotacoes_brl.get(p.ticker, {}).get("regularMarketPrice", p.preco_atual or p.preco_medio)
            preco_usd = None
            valor_investido_brl = p.valor_investido

        valor_atual_brl = preco_brl * p.quantidade
        pl_reais = valor_atual_brl - valor_investido_brl
        pl_pct = (pl_reais / valor_investido_brl * 100) if valor_investido_brl > 0 else 0

        # Conta aportes
        num_aportes = db.query(Aporte).filter(Aporte.position_id == p.id).count()

        resultado.append({
            "id": p.id,
            "ticker": p.ticker,
            "nome": p.nome or p.ticker,
            "tipo": p.tipo,
            "mercado": p.mercado or "B3",
            "moeda": moeda,
            "tese": p.tese,
            "quantidade": p.quantidade,
            "preco_medio": p.preco_medio,
            "preco_medio_usd": p.preco_medio_usd,
            "preco_atual_brl": round(preco_brl, 4),
            "preco_atual_usd": round(preco_usd, 4) if preco_usd else None,
            "valor_investido_brl": round(valor_investido_brl, 2),
            "valor_atual_brl": round(valor_atual_brl, 2),
            "pl_reais": round(pl_reais, 2),
            "pl_percentual": round(pl_pct, 2),
            "dolar_brl": round(dolar_brl, 4),
            "num_aportes": num_aportes,
            "data_entrada": p.data_entrada,
        })

    return resultado


@router.post("", status_code=201)
async def adicionar_tese(
    dados: NovaTese,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Cria nova posição no módulo Teses e registra o primeiro aporte."""
    if dados.mercado not in MERCADOS_VALIDOS:
        raise HTTPException(status_code=400, detail=f"Mercado inválido. Use: {MERCADOS_VALIDOS}")

    portfolio = _get_portfolio(user_id, db)
    moeda = dados.moeda.upper()

    # Calcula valores
    valor_total = dados.quantidade * dados.preco_medio
    data_entrada = (datetime.fromisoformat(dados.data_entrada)
                    if dados.data_entrada else datetime.utcnow())

    position = Position(
        portfolio_id=portfolio.id,
        ticker=dados.ticker.upper(),
        nome=dados.nome,
        tipo=dados.tipo.upper(),
        modulo="teses",
        tese=dados.tese,
        mercado=dados.mercado.upper(),
        moeda=moeda,
        quantidade=dados.quantidade,
        preco_medio=dados.preco_medio if moeda == "BRL" else 0.0,
        preco_medio_usd=dados.preco_medio if moeda == "USD" else None,
        valor_investido=valor_total if moeda == "BRL" else 0.0,
        valor_investido_usd=valor_total if moeda == "USD" else None,
        data_entrada=data_entrada,
        ativa=True,
    )
    db.add(position)
    db.flush()  # pega o id gerado

    # Registra primeiro aporte
    aporte = Aporte(
        position_id=position.id,
        data=data_entrada,
        quantidade=dados.quantidade,
        preco=dados.preco_medio,
        moeda=moeda,
        valor_total=valor_total,
        nota=dados.nota_aporte,
    )
    db.add(aporte)
    db.commit()
    db.refresh(position)

    return {"id": position.id, "ticker": position.ticker, "message": "Tese adicionada com sucesso"}


@router.post("/{position_id}/aportes", status_code=201)
def adicionar_aporte(
    position_id: int,
    dados: NovoAporte,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Registra novo aporte DCA em posição existente do módulo Teses."""
    portfolio = _get_portfolio(user_id, db)

    position = db.query(Position).filter(
        Position.id == position_id,
        Position.portfolio_id == portfolio.id,
        Position.modulo == "teses",
        Position.ativa == True,
    ).first()
    if not position:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    moeda = position.moeda or "BRL"
    data_aporte = (datetime.fromisoformat(dados.data) if dados.data else datetime.utcnow())
    valor_total_aporte = dados.quantidade * dados.preco

    # Registra aporte
    aporte = Aporte(
        position_id=position.id,
        data=data_aporte,
        quantidade=dados.quantidade,
        preco=dados.preco,
        moeda=moeda,
        valor_total=valor_total_aporte,
        nota=dados.nota,
    )
    db.add(aporte)

    # Recalcula preço médio ponderado a partir de todos os aportes
    aportes_existentes = db.query(Aporte).filter(Aporte.position_id == position.id).all()
    qtd_total = sum(a.quantidade for a in aportes_existentes) + dados.quantidade
    valor_total_acum = sum(a.valor_total for a in aportes_existentes) + valor_total_aporte
    novo_pm = valor_total_acum / qtd_total if qtd_total > 0 else dados.preco

    if moeda == "USD":
        position.preco_medio_usd = round(novo_pm, 6)
        position.valor_investido_usd = round(valor_total_acum, 2)
    else:
        position.preco_medio = round(novo_pm, 4)
        position.valor_investido = round(valor_total_acum, 2)

    position.quantidade = round(qtd_total, 8)
    position.updated_at = datetime.utcnow()

    db.commit()

    return {
        "message": "Aporte registrado",
        "nova_quantidade": position.quantidade,
        "novo_preco_medio": position.preco_medio_usd if moeda == "USD" else position.preco_medio,
        "valor_investido_total": position.valor_investido_usd if moeda == "USD" else position.valor_investido,
    }


@router.get("/{position_id}/aportes")
def listar_aportes(
    position_id: int,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Retorna histórico completo de aportes de uma posição."""
    portfolio = _get_portfolio(user_id, db)

    position = db.query(Position).filter(
        Position.id == position_id,
        Position.portfolio_id == portfolio.id,
        Position.modulo == "teses",
    ).first()
    if not position:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    aportes = (db.query(Aporte)
               .filter(Aporte.position_id == position_id)
               .order_by(Aporte.data.asc())
               .all())

    return {
        "ticker": position.ticker,
        "moeda": position.moeda or "BRL",
        "aportes": [
            {
                "id": a.id,
                "data": a.data,
                "quantidade": a.quantidade,
                "preco": a.preco,
                "valor_total": a.valor_total,
                "nota": a.nota,
            }
            for a in aportes
        ],
    }


@router.patch("/{position_id}")
def atualizar_tese(
    position_id: int,
    dados: AtualizarTese,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Atualiza texto da tese ou nome da posição."""
    portfolio = _get_portfolio(user_id, db)

    position = db.query(Position).filter(
        Position.id == position_id,
        Position.portfolio_id == portfolio.id,
        Position.modulo == "teses",
    ).first()
    if not position:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    if dados.tese is not None:
        position.tese = dados.tese
    if dados.nome is not None:
        position.nome = dados.nome
    position.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Tese atualizada"}


@router.delete("/{position_id}")
def encerrar_tese(
    position_id: int,
    motivo: str | None = None,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Encerra (desativa) uma posição do módulo Teses."""
    portfolio = _get_portfolio(user_id, db)

    position = db.query(Position).filter(
        Position.id == position_id,
        Position.portfolio_id == portfolio.id,
        Position.modulo == "teses",
    ).first()
    if not position:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    position.ativa = False
    position.data_saida = datetime.utcnow()
    position.motivo_saida = motivo
    position.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Posição encerrada"}

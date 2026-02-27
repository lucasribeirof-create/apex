"""Rota do Morning Briefing."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Briefing
from app.tasks import gerar_briefing_portfolio
router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/hoje")
async def get_briefing_hoje(force: bool = False, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Retorna o briefing do dia. Se não existir (ou force=True), gera na hora."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user or not user.onboarding_completo:
        raise HTTPException(status_code=400, detail="Onboarding não concluído")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    from datetime import datetime, date
    hoje = date.today()

    briefing = None
    if not force:
        briefing = (
            db.query(Briefing)
            .filter(Briefing.portfolio_id == portfolio.id)
            .filter(Briefing.data >= datetime.combine(hoje, datetime.min.time()))
            .order_by(Briefing.created_at.desc())
            .first()
        )

    if not briefing:
        # Gerar agora se não existir
        try:
            conteudo = await gerar_briefing_portfolio(portfolio.id, db)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception:
            raise HTTPException(status_code=503, detail="Erro ao gerar o briefing. Verifique a configuração da IA em Configurações.")
        briefing = db.query(Briefing).filter(
            Briefing.portfolio_id == portfolio.id
        ).order_by(Briefing.created_at.desc()).first()

    if not briefing:
        raise HTTPException(status_code=503, detail="Não foi possível gerar o briefing")

    # Marcar como lido
    if not briefing.lido:
        briefing.lido = True
        db.commit()

    return {
        "id": briefing.id,
        "data": briefing.data,
        "conteudo": briefing.conteudo,
        "regime": briefing.regime,
        "macro": {
            "dolar": briefing.dolar,
            "ibov": briefing.ibov,
            "ibov_variacao": briefing.ibov_variacao,
        },
    }


@router.get("/historico")
def get_historico_briefings(limit: int = 10, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Lista os últimos N briefings."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    briefings = (
        db.query(Briefing)
        .filter(Briefing.portfolio_id == portfolio.id)
        .order_by(Briefing.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "id": b.id,
            "data": b.data,
            "conteudo": b.conteudo[:200] + "..." if len(b.conteudo) > 200 else b.conteudo,
            "lido": b.lido,
            "regime": b.regime,
        }
        for b in briefings
    ]

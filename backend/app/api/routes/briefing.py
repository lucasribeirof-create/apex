"""Rota do Morning Briefing."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id, get_portfolio_ativo
from app.models import User, Portfolio, Briefing
from app.tasks import gerar_briefing_portfolio
router = APIRouter(prefix="/briefing", tags=["briefing"])


@router.get("/hoje")
async def get_briefing_hoje(force: bool = False, check_only: bool = False, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Retorna o briefing do dia. check_only=True só verifica sem gerar. force=True regenera sempre."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user or not user.onboarding_completo:
        raise HTTPException(status_code=400, detail="Onboarding não concluído")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    from datetime import datetime, timezone as _tz
    hoje_utc = datetime.now(_tz.utc).date()
    inicio_dia_utc = datetime.combine(hoje_utc, datetime.min.time())

    briefing = None
    if not force:
        briefing = (
            db.query(Briefing)
            .filter(Briefing.portfolio_id == portfolio.id)
            .filter(Briefing.data >= inicio_dia_utc)
            .order_by(Briefing.created_at.desc())
            .first()
        )

    # Se só estamos verificando existência, retorna 404 sem gerar
    if check_only and not briefing:
        raise HTTPException(status_code=404, detail="Nenhum briefing gerado hoje")

    if not briefing:
        # Gerar agora se não existir
        try:
            conteudo = await gerar_briefing_portfolio(portfolio.id, db)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception:
            raise HTTPException(status_code=503, detail="Erro ao gerar o briefing. Verifique a configuração da IA em Configurações.")

        if conteudo is None:
            # Portfolio novo / sem posições — salva briefing de boas-vindas
            from datetime import datetime, timezone as _tz
            from app.models import Briefing as _Briefing
            briefing = _Briefing(
                portfolio_id=portfolio.id,
                data=datetime.now(_tz.utc),
                tipo="morning",
                conteudo=(
                    f"**Bem-vindo ao APEX, {user.name or 'Investidor'}!** 🎯\n\n"
                    "Sua carteira ainda não tem posições. Para começar:\n"
                    "• Use o menu **Sugestões da IA** para deixar o cérebro montar sua alocação inicial.\n"
                    "• Ou acesse **Posições** para adicionar seus ativos manualmente.\n\n"
                    "Assim que você tiver posições, voltarei aqui com análise completa de mercado e da sua carteira."
                ),
                regime="MISTO",
            )
            db.add(briefing)
            db.commit()
            db.refresh(briefing)

        if not briefing:
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


@router.get("/stream")
async def stream_briefing_hoje(
    force: bool = False,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Gera o morning briefing via SSE streaming — o texto aparece token a token no frontend."""
    import json as _json
    from fastapi.responses import StreamingResponse
    from app.tasks.morning_briefing import gerar_briefing_portfolio_stream

    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user or not user.onboarding_completo:
        raise HTTPException(status_code=400, detail="Onboarding não concluído")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    from datetime import datetime, timezone as _tz
    hoje_utc = datetime.now(_tz.utc).date()
    inicio_dia_utc = datetime.combine(hoje_utc, datetime.min.time())

    # Se já existe briefing hoje e não forçamos — retorna o existente instantaneamente
    if not force:
        existing = (
            db.query(Briefing)
            .filter(Briefing.portfolio_id == portfolio.id)
            .filter(Briefing.data >= inicio_dia_utc)
            .order_by(Briefing.created_at.desc())
            .first()
        )
        if existing:
            if not existing.lido:
                existing.lido = True
                db.commit()
            briefing_dict = {
                "id": existing.id,
                "data": existing.data.isoformat(),
                "conteudo": existing.conteudo,
                "regime": existing.regime,
                "macro": {"dolar": existing.dolar, "ibov": existing.ibov, "ibov_variacao": existing.ibov_variacao},
            }

            async def send_existing():
                # Manda em blocos de ~5 chars para um efeito suave sem flood de eventos
                texto = existing.conteudo
                chunk_size = 5
                for i in range(0, len(texto), chunk_size):
                    yield f"data: {_json.dumps({'chunk': texto[i:i+chunk_size]}, ensure_ascii=False)}\n\n"
                yield f"data: {_json.dumps({'done': True, 'briefing': briefing_dict}, ensure_ascii=False)}\n\n"

            return StreamingResponse(
                send_existing(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    async def generate():
        try:
            async for chunk, briefing_data in gerar_briefing_portfolio_stream(portfolio.id, db):
                if chunk is not None:
                    yield f"data: {_json.dumps({'chunk': chunk}, ensure_ascii=False)}\n\n"
                if briefing_data is not None:
                    briefing_data["done"] = True
                    yield f"data: {_json.dumps(briefing_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {_json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/historico")
def get_historico_briefings(limit: int = 10, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Lista os últimos N briefings."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
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

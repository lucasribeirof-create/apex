"""
Morning Briefing automático com APScheduler.
Substitui Celery + Redis — roda direto no processo do FastAPI.
"""
import asyncio
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import SessionLocal, Portfolio, Briefing, Position, User
from app.ai import chat, build_briefing_prompt
from app.data import get_macro_br, get_macro_global
from app.core import calcular_regime


async def gerar_briefing_portfolio(portfolio_id: int, db: Session) -> str | None:
    """Gera e salva o morning briefing para um portfólio."""
    portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
    if not portfolio:
        return None

    user = db.query(User).filter(User.id == portfolio.user_id).first()
    if not user:
        return None

    # Buscar posições ativas
    posicoes_db = db.query(Position).filter(
        Position.portfolio_id == portfolio_id,
        Position.ativa == True,
    ).all()

    posicoes = [
        {
            "ticker": p.ticker,
            "tipo": p.tipo,
            "modulo": p.modulo,
            "preco_medio": p.preco_medio,
            "preco_atual": p.preco_atual or p.preco_medio,
            "pl_percentual": p.pl_percentual or 0,
            "stop_loss": p.stop_loss,
        }
        for p in posicoes_db
    ]

    # Dados macro
    macro_br, macro_global = await asyncio.gather(get_macro_br(), get_macro_global())
    macro = {**macro_br, **macro_global}

    # Data de hoje formatada em português
    from datetime import date
    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except Exception:
        pass
    data_hoje = datetime.now().strftime("%A, %d de %B de %Y")

    # System prompt
    system = build_briefing_prompt(
        user_name=user.name,
        estrategia=user.estrategia or "CORE",
        posicoes=posicoes,
        regime=portfolio.regime or "MISTO",
        macro=macro,
        data_hoje=data_hoje,
    )

    # Gerar briefing com IA
    conteudo = await chat(
        system=system,
        messages=[{"role": "user", "content": "Gere o morning call de hoje."}],
        max_tokens=5000,
    )

    # Salvar no banco
    briefing = Briefing(
        portfolio_id=portfolio_id,
        data=datetime.now(timezone.utc),
        tipo="morning",
        conteudo=conteudo,
        dolar=macro.get("dolar"),
        ibov=macro.get("ibov"),
        ibov_variacao=macro.get("ibov_variacao"),
        regime=portfolio.regime,
    )
    db.add(briefing)
    db.commit()

    return conteudo


async def tarefa_morning_briefing():
    """Tarefa agendada — roda todo dia útil antes das 9h."""
    db = SessionLocal()
    try:
        portfolios = db.query(Portfolio).all()
        for portfolio in portfolios:
            try:
                await gerar_briefing_portfolio(portfolio.id, db)
            except Exception as e:
                print(f"Erro ao gerar briefing para portfolio {portfolio.id}: {e}")
    finally:
        db.close()

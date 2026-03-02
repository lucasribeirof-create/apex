"""
Morning Briefing automático com APScheduler.
Substitui Celery + Redis — roda direto no processo do FastAPI.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import SessionLocal, Portfolio, Briefing
from app.cerebro import chat, build_briefing_prompt, montar_contexto
from app.logger import logger


async def gerar_briefing_portfolio(portfolio_id: int, db: Session) -> str | None:
    """Gera e salva o morning briefing para um portfólio."""

    # Cérebro monta TUDO: perfil, macro, posições, regime, alertas — de uma vez
    try:
        ctx = await montar_contexto(db, portfolio_id=portfolio_id)
    except ValueError as e:
        logger.warning("briefing: portfolio %s ignorado — %s", portfolio_id, e)
        return None

    # Data de hoje formatada em português
    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except Exception:
        pass
    data_hoje = datetime.now().strftime("%A, %d de %B de %Y")

    # Alertas pré-computados pelo Cérebro — enriquece o briefing
    alertas_criticos = ctx.alertas_criticos()

    # System prompt — alimentado 100% pelo ContextoCerebro
    system = build_briefing_prompt(
        user_name=ctx.user_name,
        estrategia=ctx.estrategia,
        posicoes=ctx.posicoes,
        regime=ctx.regime,
        macro=ctx.macro,
        data_hoje=data_hoje,
    )

    # ── Briefing 2.0: enriquecer com narrativa macro, status de teses e ações prioritárias ──
    user_prompt = "Gere o morning call de hoje."

    # Narrativa macro do dia
    if ctx.narrativa_macro:
        user_prompt += f"\n\nNARRATIVA MACRO DO DIA:\n{ctx.narrativa_macro[:1500]}"

    # Alertas macro (flags do MacroContext/RegimeInfo)
    macro_flags = []
    if ctx.regime_info and hasattr(ctx.regime_info, "flags"):
        macro_flags = ctx.regime_info.flags
    elif ctx.macro_context and hasattr(ctx.macro_context, "flags"):
        macro_flags = ctx.macro_context.flags
    if macro_flags:
        user_prompt += "\n\nALERTAS MACRO:\n" + "\n".join(f"- ⚠ {f}" for f in macro_flags)

    # Status das teses de investimento
    try:
        from app.cerebro.teses import monitorar_teses
        status_teses = await monitorar_teses(db, portfolio_id)
        if status_teses.get("total", 0) > 0:
            user_prompt += f"\n\nSTATUS DAS TESES ({status_teses['total']} total):"
            user_prompt += f"\n  Ativas: {status_teses.get('ativas', 0)}"
            user_prompt += f"\n  Enfraquecidas: {status_teses.get('enfraquecidas', 0)}"
            user_prompt += f"\n  Invalidadas: {status_teses.get('invalidadas', 0)}"
            if status_teses.get("alertas"):
                for alerta in status_teses["alertas"][:5]:
                    user_prompt += f"\n  ⚠ {alerta}"
    except Exception as e:
        logger.debug("briefing: teses indisponíveis: %s", e)

    if alertas_criticos:
        alertas_str = "\n".join(f"- {a}" for a in alertas_criticos)
        user_prompt += f"\n\nALERTAS PRIORITÁRIOS DO SISTEMA:\n{alertas_str}\n\nAborde estes alertas explicitamente no briefing."

    user_prompt += "\n\nInclua ao final uma seção AÇÕES PRIORITÁRIAS HOJE com itens acionáveis ordenados por urgência."

    # Gerar briefing com IA — o Cérebro executa a chamada
    conteudo = await chat(
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=2000,
    )

    # Salvar no banco
    briefing = Briefing(
        portfolio_id=portfolio_id,
        data=datetime.now(timezone.utc),
        tipo="morning",
        conteudo=conteudo,
        dolar=ctx.macro.get("dolar"),
        ibov=ctx.macro.get("ibov"),
        ibov_variacao=ctx.macro.get("ibov_variacao"),
        regime=ctx.regime,
    )
    db.add(briefing)
    db.commit()

    return conteudo


async def gerar_briefing_portfolio_stream(portfolio_id: int, db: Session):
    """
    Versão streaming de gerar_briefing_portfolio.
    Yields (chunk: str, None) para cada fragmento de texto.
    Yields (None, briefing_dict) no final após salvar no banco.
    """
    from app.cerebro import chat_stream

    try:
        ctx = await montar_contexto(db, portfolio_id=portfolio_id)
    except ValueError as e:
        logger.warning("briefing stream: portfolio %s ignorado — %s", portfolio_id, e)
        return

    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except Exception:
        pass
    data_hoje = datetime.now().strftime("%A, %d de %B de %Y")

    alertas_criticos = ctx.alertas_criticos()

    system = build_briefing_prompt(
        user_name=ctx.user_name,
        estrategia=ctx.estrategia,
        posicoes=ctx.posicoes,
        regime=ctx.regime,
        macro=ctx.macro,
        data_hoje=data_hoje,
    )

    # ── Briefing 2.0 stream: mesma lógica de enriquecimento ──
    user_prompt = "Gere o morning call de hoje."

    if ctx.narrativa_macro:
        user_prompt += f"\n\nNARRATIVA MACRO DO DIA:\n{ctx.narrativa_macro[:1500]}"

    macro_flags = []
    if ctx.regime_info and hasattr(ctx.regime_info, "flags"):
        macro_flags = ctx.regime_info.flags
    elif ctx.macro_context and hasattr(ctx.macro_context, "flags"):
        macro_flags = ctx.macro_context.flags
    if macro_flags:
        user_prompt += "\n\nALERTAS MACRO:\n" + "\n".join(f"- ⚠ {f}" for f in macro_flags)

    try:
        from app.cerebro.teses import monitorar_teses
        status_teses = await monitorar_teses(db, portfolio_id)
        if status_teses.get("total", 0) > 0:
            user_prompt += f"\n\nSTATUS DAS TESES ({status_teses['total']} total):"
            user_prompt += f"\n  Ativas: {status_teses.get('ativas', 0)}"
            user_prompt += f"\n  Enfraquecidas: {status_teses.get('enfraquecidas', 0)}"
            user_prompt += f"\n  Invalidadas: {status_teses.get('invalidadas', 0)}"
            if status_teses.get("alertas"):
                for alerta in status_teses["alertas"][:5]:
                    user_prompt += f"\n  ⚠ {alerta}"
    except Exception as e:
        logger.debug("briefing stream: teses indisponíveis: %s", e)

    if alertas_criticos:
        alertas_str = "\n".join(f"- {a}" for a in alertas_criticos)
        user_prompt += f"\n\nALERTAS PRIORITÁRIOS DO SISTEMA:\n{alertas_str}\n\nAborde estes alertas explicitamente no briefing."

    user_prompt += "\n\nInclua ao final uma seção AÇÕES PRIORITÁRIAS HOJE com itens acionáveis ordenados por urgência."

    conteudo = ""
    async for chunk in chat_stream(
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=2000,
    ):
        conteudo += chunk
        yield (chunk, None)

    # Salva no banco após streaming completo
    briefing = Briefing(
        portfolio_id=portfolio_id,
        data=datetime.now(timezone.utc),
        tipo="morning",
        conteudo=conteudo,
        dolar=ctx.macro.get("dolar"),
        ibov=ctx.macro.get("ibov"),
        ibov_variacao=ctx.macro.get("ibov_variacao"),
        regime=ctx.regime,
        lido=True,
    )
    db.add(briefing)
    db.commit()
    db.refresh(briefing)

    yield (None, {
        "id": briefing.id,
        "data": briefing.data.isoformat(),
        "conteudo": briefing.conteudo,
        "regime": briefing.regime,
        "macro": {
            "dolar": briefing.dolar,
            "ibov": briefing.ibov,
            "ibov_variacao": briefing.ibov_variacao,
        },
    })


async def tarefa_morning_briefing():
    """Tarefa agendada — roda todo dia útil antes das 9h."""
    db = SessionLocal()
    try:
        portfolios = db.query(Portfolio).all()
        for portfolio in portfolios:
            try:
                await gerar_briefing_portfolio(portfolio.id, db)
            except Exception as e:
                logger.error("briefing: erro no portfolio %s: %s", portfolio.id, e)
    finally:
        db.close()


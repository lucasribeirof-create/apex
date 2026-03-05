"""
Morning Briefing automático com APScheduler.
Substitui Celery + Redis — roda direto no processo do FastAPI.

v3 — Dados frescos (force_fresh), headlines reais, anti-alucinação.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import SessionLocal, Portfolio, Briefing
from app.cerebro import chat, build_briefing_prompt, montar_contexto
from app.logger import logger


async def _coletar_noticias_safe() -> str:
    """Coleta headlines reais. Se falhar, retorna string vazia (nunca bloqueia briefing)."""
    try:
        from app.data.news_collector import coletar_noticias
        snap = await coletar_noticias()
        return snap.para_prompt()
    except Exception as e:
        logger.warning("briefing: coleta de notícias falhou: %s", e)
        return ""


def _montar_user_prompt(ctx, alertas_criticos: list[str], news_text: str, teses_text: str = "") -> str:
    """Monta o user prompt enriquecido com seções isoladas por domínio."""
    parts = ["Gere o morning call de hoje."]

    # ══ SEÇÃO 1: DADOS DE MERCADO ══
    if ctx.macro_context and hasattr(ctx.macro_context, "resumo_texto"):
        parts.append(
            "\n══════════════════════════════════════════════════════════════"
            "\nSEÇÃO: DADOS MACRO DE MERCADO (taxas, índices, câmbio)"
            "\nTodos os números abaixo são INDICADORES MACROECONÔMICOS."
            "\n══════════════════════════════════════════════════════════════"
            f"\n{ctx.macro_context.resumo_texto()}"
        )

    # ══ SEÇÃO 2: NARRATIVA ══
    if ctx.narrativa_macro:
        parts.append(f"\nNARRATIVA MACRO DO DIA:\n{ctx.narrativa_macro[:1500]}")

    # ══ SEÇÃO 3: HEADLINES ══
    if news_text:
        parts.append(f"\n{news_text}")
        parts.append(
            "\nIMPORTANTE: Use as headlines acima para identificar os DRIVERS reais do mercado hoje. "
            "Se houver notícias sobre guerras, crises, decisões políticas — mencione-as explicitamente."
        )

    # ══ SEÇÃO 4: ALERTAS DE MERCADO (flags macro + regime) ══
    # Merge both flag sources — regime_info.flags AND macro_context.flags
    macro_flags = []
    if ctx.regime_info and hasattr(ctx.regime_info, "flags") and ctx.regime_info.flags:
        macro_flags.extend(ctx.regime_info.flags)
    if ctx.macro_context and hasattr(ctx.macro_context, "flags") and ctx.macro_context.flags:
        for f in ctx.macro_context.flags:
            if f not in macro_flags:  # dedup
                macro_flags.append(f)
    if macro_flags:
        parts.append(
            "\n══════════════════════════════════════════════════════════════"
            "\nSEÇÃO: ALERTAS MACRO (sinais de mercado — NÃO são dados de carteira)"
            "\n══════════════════════════════════════════════════════════════"
            "\n" + "\n".join(f"- ⚠ {f}" for f in macro_flags)
        )

    # ══ SEÇÃO 5: ALERTAS DA CARTEIRA DO INVESTIDOR ══
    if alertas_criticos:
        alertas_str = "\n".join(f"- [CARTEIRA] {a}" for a in alertas_criticos)
        parts.append(
            "\n══════════════════════════════════════════════════════════════"
            "\nSEÇÃO: ALERTAS DA CARTEIRA (posições e alocação do PORTFÓLIO)"
            "\nNúmeros aqui são % DO PATRIMÔNIO ou P&L de posições."
            "\nNÃO são taxas de juros, NÃO são rentabilidade, NÃO são a Selic."
            "\n══════════════════════════════════════════════════════════════"
            f"\n{alertas_str}"
            "\n\nAborde estes alertas explicitamente no briefing."
        )

    # ══ SEÇÃO 6: TESES DE INVESTIMENTO ══
    if teses_text:
        parts.append(
            "\n══════════════════════════════════════════════════════════════"
            "\nSEÇÃO: TESES DE INVESTIMENTO (status de fundamentos, NÃO posições)"
            "\n'Tese Ativa' = fundamento intacto. 'Enfraquecida' = fundamento deteriorando."
            "\nIsso é análise fundamentalista, NÃO confunda com status de preço/P&L."
            "\n══════════════════════════════════════════════════════════════"
            f"\n{teses_text}"
        )

    parts.append("\nInclua ao final uma seção AÇÕES PRIORITÁRIAS HOJE com itens acionáveis ordenados por urgência.")

    return "\n".join(parts)


async def gerar_briefing_portfolio(portfolio_id: int, db: Session) -> str | None:
    """Gera e salva o morning briefing para um portfólio."""

    # force_fresh=True — SEMPRE busca dados novos, nunca usa cache velho
    try:
        ctx = await montar_contexto(db, portfolio_id=portfolio_id, force_fresh=True)
    except ValueError as e:
        logger.warning("briefing: portfolio %s ignorado — %s", portfolio_id, e)
        return None

    # Data e hora de hoje formatadas em português
    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except Exception:
        pass
    agora = datetime.now()
    data_hoje = agora.strftime("%A, %d de %B de %Y")
    hora_atual = agora.strftime("%H:%M")

    # Coleta notícias reais em paralelo
    import asyncio
    news_text = await _coletar_noticias_safe()

    alertas_criticos = ctx.alertas_criticos()

    system = build_briefing_prompt(
        user_name=ctx.user_name,
        estrategia=ctx.estrategia,
        posicoes=ctx.posicoes,
        regime=ctx.regime,
        macro=ctx.macro,
        data_hoje=data_hoje,
        hora_atual=hora_atual,
    )

    # Coleta teses de investimento (estruturada separadamente)
    teses_text = ""
    try:
        from app.cerebro.teses import monitorar_teses
        status_teses = await monitorar_teses(db, portfolio_id)
        if status_teses.get("total", 0) > 0:
            teses_text = f"Teses Ativas (fundamento intacto): {status_teses.get('ativas', 0)}"
            teses_text += f"\nTeses Enfraquecidas (fundamento deteriorando): {status_teses.get('enfraquecidas', 0)}"
            teses_text += f"\nTeses Invalidadas: {status_teses.get('invalidadas', 0)}"
            if status_teses.get("alertas"):
                for alerta in status_teses["alertas"][:5]:
                    teses_text += f"\n  [TESE] {alerta}"
    except Exception as e:
        logger.debug("briefing: teses indisponíveis: %s", e)

    user_prompt = _montar_user_prompt(ctx, alertas_criticos, news_text, teses_text)

    conteudo = await chat(
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=4096,
    )

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

    # force_fresh=True — dados do momento exato da geração
    try:
        ctx = await montar_contexto(db, portfolio_id=portfolio_id, force_fresh=True)
    except ValueError as e:
        logger.warning("briefing stream: portfolio %s ignorado — %s", portfolio_id, e)
        return

    import locale
    try:
        locale.setlocale(locale.LC_TIME, 'pt_BR.UTF-8')
    except Exception:
        pass
    agora = datetime.now()
    data_hoje = agora.strftime("%A, %d de %B de %Y")
    hora_atual = agora.strftime("%H:%M")

    # Coleta notícias reais
    news_text = await _coletar_noticias_safe()

    alertas_criticos = ctx.alertas_criticos()

    system = build_briefing_prompt(
        user_name=ctx.user_name,
        estrategia=ctx.estrategia,
        posicoes=ctx.posicoes,
        regime=ctx.regime,
        macro=ctx.macro,
        data_hoje=data_hoje,
        hora_atual=hora_atual,
    )

    # Coleta teses de investimento (estruturada separadamente)
    teses_text = ""
    try:
        from app.cerebro.teses import monitorar_teses
        status_teses = await monitorar_teses(db, portfolio_id)
        if status_teses.get("total", 0) > 0:
            teses_text = f"Teses Ativas (fundamento intacto): {status_teses.get('ativas', 0)}"
            teses_text += f"\nTeses Enfraquecidas (fundamento deteriorando): {status_teses.get('enfraquecidas', 0)}"
            teses_text += f"\nTeses Invalidadas: {status_teses.get('invalidadas', 0)}"
            if status_teses.get("alertas"):
                for alerta in status_teses["alertas"][:5]:
                    teses_text += f"\n  [TESE] {alerta}"
    except Exception as e:
        logger.debug("briefing stream: teses indisponíveis: %s", e)

    user_prompt = _montar_user_prompt(ctx, alertas_criticos, news_text, teses_text)

    conteudo = ""
    async for chunk in chat_stream(
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=4096,
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


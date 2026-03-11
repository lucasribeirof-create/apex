"""
Morning Briefing automático com APScheduler.
Substitui Celery + Redis — roda direto no processo do FastAPI.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import SessionLocal, Portfolio, Briefing
from app.cerebro import chat, build_briefing_prompt, montar_contexto
from app.data import get_dados_tecnicos, formatar_tecnico_para_prompt, get_fundamentals, formatar_fundamentalista_para_prompt
from app.data.news_collector import coletar_noticias, coletar_noticias_ativo, formatar_noticias_ativo
from app.data.web_search import buscar_contexto_web, buscar_macro_web
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

    # ── Notícias macro FRESCAS (sem cache) — primeiro para ter contexto global ──
    import asyncio
    from app.data.cache import cache as _data_cache
    # Bust cache para garantir notícias frescas ao gerar briefing
    _data_cache.delete("news:snapshot")

    news_snapshot, macro_web = await asyncio.gather(
        coletar_noticias(),
        buscar_macro_web(),
        return_exceptions=True,
    )
    if not isinstance(news_snapshot, Exception) and news_snapshot:
        user_prompt += f"\n\n{news_snapshot.para_prompt(max_brasil=10, max_global=8, max_geo=5)}"
    if not isinstance(macro_web, Exception) and macro_web:
        user_prompt += f"\n\n{macro_web}"

    # ── Dados ao vivo das posições: técnicos + notícias + web search ──
    tickers_posicoes = []
    for p in (ctx.posicoes or []):
        t = p.get("ticker")
        m = p.get("mercado", "B3") or "B3"
        if t:
            tickers_posicoes.append((t, m))

    if tickers_posicoes:
        # Busca técnicos, fundamentalistas, notícias por ativo e web search em paralelo
        tarefas_tec = [get_dados_tecnicos(t, m) for t, m in tickers_posicoes]
        tarefas_fund = [get_fundamentals(t) for t, _ in tickers_posicoes]
        tarefas_news = [coletar_noticias_ativo(t) for t, _ in tickers_posicoes]
        # Web search para os 3 primeiros tickers (não só o primeiro)
        tarefas_web = [buscar_contexto_web(t, m) for t, m in tickers_posicoes[:3]]

        todos = await asyncio.gather(
            *tarefas_tec, *tarefas_fund, *tarefas_news, *tarefas_web,
            return_exceptions=True,
        )
        n = len(tickers_posicoes)
        nw = len(tarefas_web)
        resultados_tec = todos[:n]
        resultados_fund = todos[n:2*n]
        resultados_news = todos[2*n:3*n]
        resultados_web = todos[3*n:3*n+nw]

        # Montar resumo técnico das posições
        blocos_tec = []
        for (ticker, _mercado), tec in zip(tickers_posicoes, resultados_tec):
            if isinstance(tec, Exception) or not isinstance(tec, dict):
                blocos_tec.append(f"  • {ticker}: dados técnicos indisponíveis")
            else:
                blocos_tec.append(f"--- {ticker} ---\n{formatar_tecnico_para_prompt(tec)}")
        user_prompt += f"\n\nANÁLISE TÉCNICA AO VIVO:\n" + "\n\n".join(blocos_tec)

        # Montar resumo fundamentalista das posições
        blocos_fund = []
        for (ticker, _), fund in zip(tickers_posicoes, resultados_fund):
            if isinstance(fund, Exception) or not fund:
                continue
            txt = formatar_fundamentalista_para_prompt(fund)
            if txt:
                blocos_fund.append(f"--- {ticker} ---\n{txt}")
        if blocos_fund:
            user_prompt += "\n\nDADOS FUNDAMENTALISTAS:\n" + "\n\n".join(blocos_fund)

        # Montar notícias de todas as posições
        todas_noticias = []
        for (ticker, _), news in zip(tickers_posicoes, resultados_news):
            if not isinstance(news, Exception) and news:
                txt = formatar_noticias_ativo(news, ticker)
                if txt:
                    todas_noticias.append(txt)
        if todas_noticias:
            user_prompt += "\n\n" + "\n\n".join(todas_noticias[:5])

        # Web search por ativo
        for web_ctx in resultados_web:
            if not isinstance(web_ctx, Exception) and web_ctx:
                user_prompt += f"\n\n{web_ctx}"

    # Calendário econômico real (ForexFactory + Copom) — injetar antes da narrativa
    if ctx.macro_context and hasattr(ctx.macro_context, "calendario_eventos") and ctx.macro_context.calendario_eventos:
        from app.data.calendar_client import formatar_para_prompt
        cal_txt = formatar_para_prompt(ctx.macro_context.calendario_eventos)
        user_prompt += f"\n\nCALENDÁRIO ECONÔMICO (DADOS REAIS — HOJE + 7 DIAS):\n{cal_txt}\nUSE EXCLUSIVAMENTE estes dados para a seção de calendário. NÃO invente datas."

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

    # Kill switch macro (Phase 5) — seção urgente
    if hasattr(ctx, "kill_switch") and ctx.kill_switch and ctx.kill_switch.ativo:
        ks = ctx.kill_switch
        urgencia = "PAUSA OBRIGATÓRIA" if ks.nivel >= 2 else "ALERTA URGENTE"
        user_prompt += (
            f"\n\n⚠️ KILL SWITCH MACRO ({urgencia}):\n"
            f"  Regime: {ks.regime} | Confiança: {ks.confianca}%\n"
            f"  Motivo: {ks.motivo}\n"
            f"  Recomendação: {ks.recomendacao}\n"
            f"OBRIGATÓRIO: Comece o briefing com uma seção de ALERTA sobre o kill switch. "
            f"Recomende ações concretas de redução de risco."
        )

    # Circuit Breaker (Phase 4/7) — status de risco mensal
    if hasattr(ctx, "circuit_breaker") and ctx.circuit_breaker:
        cb = ctx.circuit_breaker
        if cb.ativo:
            user_prompt += (
                f"\n\n🔴 CIRCUIT BREAKER ATIVO (nível {cb.nivel}):\n"
                f"  P&L mês: {cb.pl_mes_pct:+.1f}% | Sizing modifier: {cb.sizing_modifier}\n"
                f"  {cb.motivo}\n"
                f"Mencione o circuit breaker no briefing — novas alocações estão restringidas."
            )
        else:
            user_prompt += f"\n\nCircuit Breaker: normal (P&L mês: {cb.pl_mes_pct:+.1f}%)"

    # Heat (Phase 4/7) — risco simultâneo
    if hasattr(ctx, "heat") and ctx.heat:
        ht = ctx.heat
        if not ht.pode_operar:
            user_prompt += (
                f"\n\n🔴 HEAT ALTO: {ht.heat_pct:.1f}% do patrimônio em risco — NÃO PODE OPERAR.\n"
                f"Inclua alerta sobre excesso de risco aberto."
            )
        else:
            user_prompt += f"\n\nHeat: {ht.heat_pct:.1f}% do patrimônio em risco (dentro do limite)."

    # Guardrails (Phase 1/7) — compliance macro
    if hasattr(ctx, "guardrails") and ctx.guardrails:
        g = ctx.guardrails
        user_prompt += (
            f"\n\nGuardrails Macro: equity máx {g.get('equity_max_pct', '?')}% | "
            f"RF mín {g.get('rf_min_pct', '?')}% | caixa mín {g.get('caixa_min_pct', '?')}%"
        )

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

    # ── Notícias macro FRESCAS (sem cache) — primeiro para ter contexto global ──
    import asyncio
    from app.data.cache import cache as _data_cache
    _data_cache.delete("news:snapshot")

    news_snapshot, macro_web = await asyncio.gather(
        coletar_noticias(),
        buscar_macro_web(),
        return_exceptions=True,
    )
    if not isinstance(news_snapshot, Exception) and news_snapshot:
        user_prompt += f"\n\n{news_snapshot.para_prompt(max_brasil=10, max_global=8, max_geo=5)}"
    if not isinstance(macro_web, Exception) and macro_web:
        user_prompt += f"\n\n{macro_web}"

    # ── Dados ao vivo das posições: técnicos + notícias + web search ──
    tickers_posicoes = []
    for p in (ctx.posicoes or []):
        t = p.get("ticker")
        m = p.get("mercado", "B3") or "B3"
        if t:
            tickers_posicoes.append((t, m))

    if tickers_posicoes:
        tarefas_tec = [get_dados_tecnicos(t, m) for t, m in tickers_posicoes]
        tarefas_fund = [get_fundamentals(t) for t, _ in tickers_posicoes]
        tarefas_news = [coletar_noticias_ativo(t) for t, _ in tickers_posicoes]
        tarefas_web = [buscar_contexto_web(t, m) for t, m in tickers_posicoes[:3]]

        todos = await asyncio.gather(
            *tarefas_tec, *tarefas_fund, *tarefas_news, *tarefas_web,
            return_exceptions=True,
        )
        n = len(tickers_posicoes)
        nw = len(tarefas_web)
        resultados_tec = todos[:n]
        resultados_fund = todos[n:2*n]
        resultados_news = todos[2*n:3*n]
        resultados_web = todos[3*n:3*n+nw]

        blocos_tec = []
        for (ticker, _mercado), tec in zip(tickers_posicoes, resultados_tec):
            if isinstance(tec, Exception) or not isinstance(tec, dict):
                blocos_tec.append(f"  • {ticker}: dados técnicos indisponíveis")
            else:
                blocos_tec.append(f"--- {ticker} ---\n{formatar_tecnico_para_prompt(tec)}")
        user_prompt += f"\n\nANÁLISE TÉCNICA AO VIVO:\n" + "\n\n".join(blocos_tec)

        blocos_fund = []
        for (ticker, _), fund in zip(tickers_posicoes, resultados_fund):
            if isinstance(fund, Exception) or not fund:
                continue
            txt = formatar_fundamentalista_para_prompt(fund)
            if txt:
                blocos_fund.append(f"--- {ticker} ---\n{txt}")
        if blocos_fund:
            user_prompt += "\n\nDADOS FUNDAMENTALISTAS:\n" + "\n\n".join(blocos_fund)

        todas_noticias = []
        for (ticker, _), news in zip(tickers_posicoes, resultados_news):
            if not isinstance(news, Exception) and news:
                txt = formatar_noticias_ativo(news, ticker)
                if txt:
                    todas_noticias.append(txt)
        if todas_noticias:
            user_prompt += "\n\n" + "\n\n".join(todas_noticias[:5])

        for web_ctx in resultados_web:
            if not isinstance(web_ctx, Exception) and web_ctx:
                user_prompt += f"\n\n{web_ctx}"

    # Calendário econômico real (ForexFactory + Copom)
    if ctx.macro_context and hasattr(ctx.macro_context, "calendario_eventos") and ctx.macro_context.calendario_eventos:
        from app.data.calendar_client import formatar_para_prompt
        cal_txt = formatar_para_prompt(ctx.macro_context.calendario_eventos)
        user_prompt += f"\n\nCALENDÁRIO ECONÔMICO (DADOS REAIS — HOJE + 7 DIAS):\n{cal_txt}\nUSE EXCLUSIVAMENTE estes dados para a seção de calendário. NÃO invente datas."

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

    # Kill switch macro (Phase 5) — seção urgente
    if hasattr(ctx, "kill_switch") and ctx.kill_switch and ctx.kill_switch.ativo:
        ks = ctx.kill_switch
        urgencia = "PAUSA OBRIGATÓRIA" if ks.nivel >= 2 else "ALERTA URGENTE"
        user_prompt += (
            f"\n\n⚠️ KILL SWITCH MACRO ({urgencia}):\n"
            f"  Regime: {ks.regime} | Confiança: {ks.confianca}%\n"
            f"  Motivo: {ks.motivo}\n"
            f"  Recomendação: {ks.recomendacao}\n"
            f"OBRIGATÓRIO: Comece o briefing com uma seção de ALERTA sobre o kill switch. "
            f"Recomende ações concretas de redução de risco."
        )

    # Circuit Breaker (Phase 4/7) — status de risco mensal
    if hasattr(ctx, "circuit_breaker") and ctx.circuit_breaker:
        cb = ctx.circuit_breaker
        if cb.ativo:
            user_prompt += (
                f"\n\n🔴 CIRCUIT BREAKER ATIVO (nível {cb.nivel}):\n"
                f"  P&L mês: {cb.pl_mes_pct:+.1f}% | Sizing modifier: {cb.sizing_modifier}\n"
                f"  {cb.motivo}\n"
                f"Mencione o circuit breaker no briefing — novas alocações estão restringidas."
            )
        else:
            user_prompt += f"\n\nCircuit Breaker: normal (P&L mês: {cb.pl_mes_pct:+.1f}%)"

    # Heat (Phase 4/7) — risco simultâneo
    if hasattr(ctx, "heat") and ctx.heat:
        ht = ctx.heat
        if not ht.pode_operar:
            user_prompt += (
                f"\n\n🔴 HEAT ALTO: {ht.heat_pct:.1f}% do patrimônio em risco — NÃO PODE OPERAR.\n"
                f"Inclua alerta sobre excesso de risco aberto."
            )
        else:
            user_prompt += f"\n\nHeat: {ht.heat_pct:.1f}% do patrimônio em risco (dentro do limite)."

    # Guardrails (Phase 1/7) — compliance macro
    if hasattr(ctx, "guardrails") and ctx.guardrails:
        g = ctx.guardrails
        user_prompt += (
            f"\n\nGuardrails Macro: equity máx {g.get('equity_max_pct', '?')}% | "
            f"RF mín {g.get('rf_min_pct', '?')}% | caixa mín {g.get('caixa_min_pct', '?')}%"
        )

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


"""Rota do chat com o gestor IA."""
import asyncio
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id
from app.models import Position
from app.cerebro import chat_stream, build_portfolio_prompt
from app.cerebro.prompts import build_analyst_prompt, build_ceo_monitor_prompt
from app.cerebro.contexto import montar as montar_contexto
from app.data import get_dados_tecnicos, formatar_tecnico_para_prompt, get_fundamentals, formatar_fundamentalista_para_prompt
from app.data.news_collector import coletar_noticias_ativo, formatar_noticias_ativo
from app.data.web_search import buscar_contexto_web

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMensagem(BaseModel):
    mensagem: str
    historico: list[dict] = []
    modulo: Optional[str] = None





@router.post("/")
async def chat_com_gestor(body: ChatMensagem, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Streaming de chat com o gestor IA com contexto completo do portfólio (v2)."""
    ctx, system = await _build_context(db, user_id)

    # Se veio de uma análise de posição, usa o system prompt APEX Analyst
    if body.modulo:
        system = build_analyst_prompt(body.modulo.lower(), patrimonio=ctx.patrimonio_total)

    # Chat V2: injeta contexto enriquecido na mensagem do usuário
    contexto_extra = await _montar_contexto_chat(ctx, db)
    mensagem_user = body.mensagem

    # Detecta ticker na mensagem para enriquecer com web search + notícias
    import re as _re
    # Tickers BR (PETR4, VALE3) e US (AAPL, MSFT, NVDA, etc.)
    _ticker_match = _re.findall(r'\b([A-Z]{4}\d{1,2}(?:\.SA)?)\b', body.mensagem.upper())
    if not _ticker_match:
        _ticker_match = _re.findall(r'\b([A-Z]{2,5})\b', body.mensagem.upper())
        # Filtra palavras comuns que não são tickers
        _stop_words = {'COMO', 'VOCE', 'PARA', 'MINHA', 'MINHA', 'QUAL', 'SOBRE', 'AINDA', 'MAIS',
                        'PODE', 'QUER', 'DEVO', 'ESTA', 'ESSE', 'ESSA', 'ISSO', 'ELES', 'DELA',
                        'DELE', 'OQUE', 'QUERO', 'ACHA', 'FAÇA', 'FACA', 'OLHE', 'VEJA', 'AQUI',
                        'AGORA', 'HOJE', 'MEUS', 'SUAS', 'SERA', 'SAIR', 'ACHO', 'FAZER', 'POST',
                        'BODY', 'TRUE', 'NULL', 'JSON', 'HTTP', 'CHAT', 'APEX', 'MODO', 'TIPO',
                        'RISK', 'HIGH', 'LOW', 'SELL', 'BUY', 'HOLD', 'LONG', 'SHORT', 'STOP',
                        'ALVO', 'RISCO', 'TESE', 'FIIS', 'ETFS'}
        _ticker_match = [t for t in _ticker_match if t not in _stop_words and len(t) >= 2]
    web_extra = ""
    if _ticker_match:
        _ticker = _ticker_match[0]
        _mercado = "US" if "." not in _ticker and not _ticker[-1].isdigit() else "B3"
        try:
            _web, _news, _tec, _fund = await asyncio.gather(
                buscar_contexto_web(_ticker, _mercado),
                coletar_noticias_ativo(_ticker),
                get_dados_tecnicos(_ticker, _mercado),
                get_fundamentals(_ticker),
            )
            if _web:
                web_extra += f"\n\n{_web}"
            if _news:
                _news_txt = formatar_noticias_ativo(_news, _ticker)
                if _news_txt:
                    web_extra += f"\n\n{_news_txt}"
            if isinstance(_tec, dict) and _tec:
                _tec_txt = formatar_tecnico_para_prompt(_tec)
                if _tec_txt:
                    web_extra += f"\n\nANÁLISE TÉCNICA ({_ticker}):\n{_tec_txt}"
            if _fund:
                _fund_txt = formatar_fundamentalista_para_prompt(_fund)
                if _fund_txt:
                    web_extra += f"\n\nDADOS FUNDAMENTALISTAS ({_ticker}):\n{_fund_txt}"
        except Exception:
            pass

    if contexto_extra or web_extra:
        mensagem_user = f"{body.mensagem}\n\n---\n[CONTEXTO AUTOMÁTICO — não mencione que recebeu isto]\n{contexto_extra}{web_extra}"

    # Gestão de janela de contexto — mantém histórico dentro do budget de tokens
    historico_trimmed = _trim_historico(body.historico)
    messages = historico_trimmed + [{"role": "user", "content": mensagem_user}]
    tokens = 8000 if body.modulo else 4000

    async def gerador():
        async for trecho in chat_stream(system=system, messages=messages, max_tokens=tokens, track_usage=True):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")


@router.get("/analisar-posicao/{position_id}")
async def analisar_posicao(position_id: int, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Streaming: CEO Brain diagnostica uma posição com cotação ao vivo e técnicos reais.
    Sem rodar motores — monitoramento puro da posição existente.
    """
    ctx, _ = await _build_context(db, user_id)

    pos_db = db.query(Position).filter(
        Position.id == position_id,
        Position.portfolio_id == ctx.portfolio_id,
        Position.ativa == True,
    ).first()
    if not pos_db:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    mercado = getattr(pos_db, "mercado", "B3") or "B3"
    moeda = getattr(pos_db, "moeda", "BRL") or "BRL"
    moeda_str = "US$" if moeda == "USD" else "R$"
    modulo = (pos_db.modulo or "alpha").lower()

    # Detecta se posição é recente (< 24h) — usa data_entrada real, não created_at
    pos_age_hours = None
    ref_date = pos_db.data_entrada or pos_db.data_abertura or pos_db.created_at
    if ref_date:
        pos_age_hours = (datetime.utcnow() - ref_date).total_seconds() / 3600
    is_fresh = pos_age_hours is not None and pos_age_hours < 24

    async def gerador():
        yield f"🔍 Buscando dados ao vivo de {pos_db.ticker}...\n\n"

        # Busca cotação, técnicos, fundamentalistas, notícias e web em paralelo
        tecnico, fundamentos, noticias, web_contexto = await asyncio.gather(
            get_dados_tecnicos(pos_db.ticker, mercado),
            get_fundamentals(pos_db.ticker),
            coletar_noticias_ativo(pos_db.ticker),
            buscar_contexto_web(pos_db.ticker, mercado),
        )
        tec_texto = formatar_tecnico_para_prompt(tecnico, moeda=moeda_str)
        fund_texto = formatar_fundamentalista_para_prompt(fundamentos) if fundamentos else ""
        news_texto = formatar_noticias_ativo(noticias, pos_db.ticker)

        # ── Validação: aborta cedo se dados críticos falharam (economiza tokens) ──
        preco_check = tecnico.get("preco_atual")
        tem_erro_tec = bool(tecnico.get("erro"))
        tem_fund = bool(fundamentos)

        if not preco_check and tem_erro_tec and not tem_fund:
            yield f"❌ Não foi possível obter dados de {pos_db.ticker}. As APIs de cotação não retornaram dados suficientes.\n\n"
            yield "💡 Tente novamente em alguns minutos — pode ser instabilidade temporária da BRAPI ou yFinance.\n"
            return

        # Indicador de qualidade dos dados técnicos
        tec_aviso = ""
        rsi_check = tecnico.get("rsi14")
        if not preco_check or not rsi_check:
            tec_aviso = "\n⚠️ AVISO: Dados técnicos incompletos — a API não retornou todos os indicadores. NÃO invente valores."

        # Header com preço ao vivo
        if preco_check:
            yield f"💰 {pos_db.ticker.upper()}: {moeda_str} {preco_check:,.2f}\n"

        pm = pos_db.preco_medio or 0
        pm_usd = getattr(pos_db, "preco_medio_usd", None)
        preco_live = tecnico.get("preco_atual") or pos_db.preco_atual or pm
        pl_pct = ((preco_live - pm) / pm * 100) if pm > 0 else (pos_db.pl_percentual or 0)

        tese = pos_db.tese or "Sem tese registrada"
        stop = pos_db.stop_loss
        alvo = pos_db.alvo_1

        stop_info = ""
        if stop and preco_live:
            dist_stop = ((preco_live - stop) / preco_live) * 100
            stop_info = f"\nStop: {moeda_str} {stop:,.2f} ({dist_stop:+.1f}% do preço atual)"

        alvo_info = ""
        if alvo and preco_live:
            dist_alvo = ((alvo - preco_live) / preco_live) * 100
            alvo_info = f"\nAlvo: {moeda_str} {alvo:,.2f} ({dist_alvo:+.1f}% do preço atual)"

        plano_resumo = ""
        if ctx.plano_estrategico:
            p = ctx.plano_estrategico
            plano_resumo = f"\nPlano: {p.get('objetivo', '')} | Horizonte: {p.get('horizonte', '')} | Perfil: {ctx.estrategia}"

        macro_str = ""
        if ctx.macro:
            m = ctx.macro
            macro_str = f"\nMacro: Selic {m.get('selic_atual', '?')}% | VIX {m.get('vix', '?')} | Regime: {ctx.regime or '—'}"

        fresh_clause = ""
        if is_fresh:
            fresh_clause = """
CONTEXTO IMPORTANTE: Esta posição foi montada há menos de 24 horas.
NÃO gere red flags sobre itens que já foram avaliados na montagem (stops, alocação, tese).
Foque em confirmar a configuração e validar que a execução está conforme o planejado.
Uma posição recém-criada com P&L próximo de zero é NORMAL."""

        # Detecta se posição é HOLD (Fase 5 — classificação Hold)
        _dados_extras = {}
        if hasattr(pos_db, "dados_extras") and isinstance(pos_db.dados_extras, dict):
            _dados_extras = pos_db.dados_extras
        is_hold = bool(_dados_extras.get("hold_elegivel"))

        # System prompt especializado por tipo de investimento + hold override
        SYSTEM = build_analyst_prompt(modulo, is_fresh=is_fresh, is_hold=is_hold, patrimonio=ctx.patrimonio_total)

        pm_str = f"PM: {moeda_str} {pm:,.2f}"
        if pm_usd:
            pm_str += f" (US$ {pm_usd:,.2f})"

        age_str = ""
        if is_fresh and pos_age_hours is not None:
            age_str = f"\n⏱️ POSIÇÃO RECÉM-CRIADA (há {pos_age_hours:.0f}h) — avalie como revisão pós-montagem, não como correção."

        USER = f"""## POSIÇÃO: {pos_db.ticker.upper()} [{modulo.upper()}]{' [HOLD]' if is_hold else ''}{age_str}
- Tese de entrada: {tese}
- {pm_str}
- P&L atual: {pl_pct:+.1f}%{stop_info}{alvo_info}
{plano_resumo}
{fresh_clause}

## CONTEXTO MACRO{macro_str if macro_str else chr(10) + 'Sem dados macro disponíveis.'}

## ANÁLISE TÉCNICA (gráfico diário, 1 ano de histórico){tec_aviso}
{tec_texto}

## DADOS FUNDAMENTALISTAS
{fund_texto if fund_texto else 'Sem dados fundamentalistas disponíveis.'}

## {news_texto}

## PESQUISA WEB
{web_contexto if web_contexto else 'Sem resultados de pesquisa web.'}

## CONTEXTO CÉREBRO (decisões anteriores do sistema)
{_injetar_cerebro_completo(ctx, excluir_guardrails=True)}

Analise esta posição usando as 7 camadas. Devo APORTAR MAIS, MANTER, REDUZIR ou ZERAR?"""

        yield "✅ Dados ao vivo coletados — APEX Analyst analisando...\n\n"

        async for trecho in chat_stream(
            system=SYSTEM,
            messages=[{"role": "user", "content": USER}],
            max_tokens=6000,
            track_usage=True,
        ):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")


@router.get("/analisar-carteira")
async def analisar_carteira(
    modulo: Optional[str] = None,
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Streaming: CEO Brain monitora a carteira com cotações ao vivo.
    Sem rodar motores — análise de saúde pura do que já existe.
    """
    ctx, _ = await _build_context(db, user_id)

    if not ctx.posicoes:
        async def vazio():
            yield "Nenhuma posição encontrada na carteira."
        return StreamingResponse(vazio(), media_type="text/plain")

    posicoes_filtradas = ctx.posicoes
    if modulo and modulo != "todos":
        posicoes_filtradas = [p for p in ctx.posicoes if (p.get("modulo") or "").lower() == modulo.lower()]

    # Detecta se carteira é recém-criada (posição mais antiga < 24h)
    _agora = datetime.utcnow()
    _idades = []
    for p in posicoes_filtradas:
        ca = p.get("created_at")
        if ca:
            try:
                dt = datetime.fromisoformat(ca) if isinstance(ca, str) else ca
                _idades.append((_agora - dt).total_seconds() / 3600)
            except Exception:
                pass
    carteira_recente = bool(_idades) and max(_idades) < 24

    async def gerador():
        n = len(posicoes_filtradas)
        yield f"📡 Buscando cotações ao vivo de {n} posições...\n\n"

        # Busca técnicos, fundamentalistas, notícias e web search em paralelo
        tarefas_tec = [
            get_dados_tecnicos(p["ticker"], p.get("mercado", "B3") or "B3")
            for p in posicoes_filtradas
        ]
        tarefas_fund = [
            get_fundamentals(p["ticker"])
            for p in posicoes_filtradas
        ]
        tarefas_news = [
            coletar_noticias_ativo(p["ticker"])
            for p in posicoes_filtradas
        ]
        # Web search: busca contexto do primeiro ticker (representància)
        primeiro_ticker = posicoes_filtradas[0]["ticker"]
        primeiro_mercado = posicoes_filtradas[0].get("mercado", "B3") or "B3"
        tarefa_web = buscar_contexto_web(primeiro_ticker, primeiro_mercado)

        todos = await asyncio.gather(
            *tarefas_tec, *tarefas_fund, *tarefas_news, tarefa_web,
            return_exceptions=True,
        )
        resultados = todos[:n]
        resultados_fund = todos[n:2*n]
        resultados_news = todos[2*n:3*n]
        web_contexto = todos[3*n] if not isinstance(todos[3*n], Exception) else ""

        linhas_pos = []
        stops_proximos = []

        for pos, tec in zip(posicoes_filtradas, resultados):
            ticker = pos.get("ticker", "?")
            moeda = pos.get("moeda", "BRL") or "BRL"
            moeda_str = "US$" if moeda == "USD" else "R$"
            pm = pos.get("preco_medio") or 0
            stop = pos.get("stop_loss")
            modulo_pos = pos.get("modulo", "-")

            if isinstance(tec, Exception) or not isinstance(tec, dict):
                preco_live = pos.get("preco_atual") or pm
                tec_resumo = "dados técnicos indisponíveis"
            else:
                preco_live = tec.get("preco_atual") or pos.get("preco_atual") or pm
                tendencia = tec.get("tendencia", "—")
                rsi = tec.get("rsi14")
                dist_ma20 = tec.get("dist_ma20", "?")
                tec_resumo = f"Tendência: {tendencia} | RSI: {rsi} | vs MA20: {dist_ma20}"

            pl = ((preco_live - pm) / pm * 100) if pm > 0 else 0

            linha = f"  • {ticker} [{modulo_pos}]: PM {moeda_str}{pm:,.2f} → {moeda_str}{preco_live:,.2f} | P&L {pl:+.1f}%"
            if stop and preco_live:
                dist_stop = ((preco_live - stop) / preco_live) * 100
                linha += f" | stop {moeda_str}{stop:,.2f} ({dist_stop:+.1f}%)"
                if abs(dist_stop) < 5:
                    stops_proximos.append(f"{ticker} ({dist_stop:+.1f}% do stop)")
            linha += f"\n    {tec_resumo}"
            linhas_pos.append(linha)

        macro_str = ""
        if ctx.macro:
            m = ctx.macro
            macro_str = (
                f"\nMacro: Selic {m.get('selic_atual', '?')}% | "
                f"IPCA 12m {m.get('ipca_12m', '?')}% | "
                f"VIX {m.get('vix', '?')} | "
                f"Regime: {ctx.regime or '—'}"
            )

        plano_str = ""
        if ctx.plano_estrategico:
            p = ctx.plano_estrategico
            plano_str = f"\nPlano: {p.get('objetivo', '')} | Horizonte: {p.get('horizonte', '')} | Perfil: {ctx.estrategia}"

        stops_alerta = ""
        if stops_proximos:
            stops_alerta = "\n⚠️ STOPS PRÓXIMOS (< 5%): " + ", ".join(stops_proximos)

        SYSTEM = build_ceo_monitor_prompt(is_recent=carteira_recente)

        age_cart = ""
        if carteira_recente and _idades:
            age_cart = f"\n⏱️ CARTEIRA RECÉM-MONTADA (posição mais antiga: {max(_idades):.0f}h atrás)"

        # Patrimônio e módulos: scope ao módulo se filtrado
        is_module_filter = bool(modulo and modulo != "todos")
        if is_module_filter:
            patrimonio_ctx = sum(p.get("valor_atual") or p.get("valor_investido") or 0 for p in posicoes_filtradas)
            modulos_str = modulo.upper()
        else:
            patrimonio_ctx = ctx.patrimonio_total or sum(p.get("valor_atual") or p.get("valor_investido") or 0 for p in posicoes_filtradas)
            modulos_str = ', '.join(ctx.modulos_ativos or [])

        tickers_filter = {p.get("ticker", "") for p in posicoes_filtradas} if is_module_filter else None

        USER = f"""MONITORAMENTO DE CARTEIRA{' — módulo ' + modulo.upper() if modulo else ''}{age_cart}

POSIÇÕES COM COTAÇÃO AO VIVO:
{chr(10).join(linhas_pos)}{stops_alerta}{plano_str}{macro_str}

Patrimônio{' do módulo' if is_module_filter else ' total'}: R$ {patrimonio_ctx:,.0f}
Módulos: {modulos_str}

{_injetar_cerebro_completo(ctx, excluir_guardrails=is_module_filter, tickers_filter=tickers_filter)}

Faça o diagnóstico de saúde desta carteira. Foque nos riscos imediatos e desvios do plano."""

        # Injetar notícias das posições
        noticias_bloco = []
        for pos, news in zip(posicoes_filtradas, resultados_news):
            ticker = pos.get("ticker", "?")
            if not isinstance(news, Exception) and news:
                txt = formatar_noticias_ativo(news, ticker)
                if txt:
                    noticias_bloco.append(txt)
        if noticias_bloco:
            USER += "\n\n" + "\n\n".join(noticias_bloco[:5])

        # Injetar fundamentalistas das posições
        fund_bloco = []
        for pos, fund in zip(posicoes_filtradas, resultados_fund):
            ticker = pos.get("ticker", "?")
            if not isinstance(fund, Exception) and fund:
                txt = formatar_fundamentalista_para_prompt(fund)
                if txt:
                    fund_bloco.append(f"--- {ticker} ---\n{txt}")
        if fund_bloco:
            USER += "\n\nDADOS FUNDAMENTALISTAS:\n" + "\n\n".join(fund_bloco)

        # Injetar web search
        if web_contexto:
            USER += f"\n\n{web_contexto}"

        yield "✅ Dados ao vivo coletados — CEO Brain analisando...\n\n"

        async for trecho in chat_stream(
            system=SYSTEM,
            messages=[{"role": "user", "content": USER}],
            max_tokens=6000,
            track_usage=True,
        ):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")




# ─── Helpers ──────────────────────────────────────────────────────────────────

def _injetar_cerebro_completo(ctx, excluir_guardrails: bool = False, tickers_filter: set | None = None) -> str:
    """Gera bloco padronizado com TODOS os dados do Cérebro (Fases 1-6) para injeção em prompts.
    Se tickers_filter fornecido, filtra alertas apenas para os tickers do módulo."""
    secoes: list[str] = []

    # 1. Kill Switch (Fase 5)
    if hasattr(ctx, "kill_switch") and ctx.kill_switch and ctx.kill_switch.ativo:
        ks = ctx.kill_switch
        urgencia = "PAUSA TOTAL" if ks.nivel >= 2 else "ALERTA"
        secoes.append(
            f"⚠️ KILL SWITCH MACRO ({urgencia} — nível {ks.nivel}):\n"
            f"  Motivo: {ks.motivo}\n"
            f"  Recomendação: {ks.recomendacao}"
        )

    # 2. Circuit Breaker (Fase 4)
    if hasattr(ctx, "circuit_breaker") and ctx.circuit_breaker:
        cb = ctx.circuit_breaker
        if cb.ativo:
            secoes.append(
                f"🔴 CIRCUIT BREAKER ATIVO (nível {cb.nivel}):\n"
                f"  P&L mês: {cb.pl_mes_pct:+.1f}% | Sizing modifier: {cb.sizing_modifier}\n"
                f"  {cb.motivo}"
            )
        else:
            secoes.append(f"CIRCUIT BREAKER: normal (P&L mês: {cb.pl_mes_pct:+.1f}%)")

    # 3. Heat (Fase 4)
    if hasattr(ctx, "heat") and ctx.heat:
        ht = ctx.heat
        status_heat = "🔴 NÃO PODE OPERAR" if not ht.pode_operar else "✅ OK"
        secoes.append(f"HEAT: {ht.heat_pct:.1f}% do patrimônio em risco — {status_heat}")

    # 4. Regime Macro 4-States (Fase 1)
    if hasattr(ctx, "regime_macro") and ctx.regime_macro:
        secoes.append(
            f"REGIME MACRO: {ctx.regime_macro} (score {ctx.regime_score}/100, "
            f"confiança {ctx.confianca_macro}%) | Fase Selic: {ctx.fase_selic or '—'}"
        )

    # 5. Guardrails (Fase 1) — só para análise de carteira, não individual
    if not excluir_guardrails and hasattr(ctx, "guardrails") and ctx.guardrails:
        g = ctx.guardrails
        secoes.append(
            f"GUARDRAILS MACRO: equity máx {g.get('equity_max_pct', '?')}% | "
            f"RF mín {g.get('rf_min_pct', '?')}% | caixa mín {g.get('caixa_min_pct', '?')}%"
        )

    # 6. Ranking Setorial (Fase 2)
    if hasattr(ctx, "ranking_setorial") and ctx.ranking_setorial:
        rs = ctx.ranking_setorial
        fav = ", ".join(rs.favorecidos[:5]) if rs.favorecidos else "—"
        evit = ", ".join(rs.evitar[:5]) if rs.evitar else "—"
        secoes.append(f"SETORES FAVORECIDOS: {fav}\nSETORES A EVITAR: {evit}")

    # 7. Alocação real vs guardrails (só mostra se o usuário configurou alvos e não é análise individual)
    if not excluir_guardrails and ctx.alocacao_real and ctx.guardrails and getattr(ctx, 'alocacao_configurada', False):
        equity_mods = ["etfs", "fiis", "momentum", "alpha", "dividendos", "wheel"]
        equity_real = sum(ctx.alocacao_real.get(m, 0) for m in equity_mods)
        rf_real = ctx.alocacao_real.get("renda_fixa", 0)
        caixa_real = ctx.alocacao_real.get("caixa", 0)
        g = ctx.guardrails
        secoes.append(
            f"ALOCAÇÃO REAL: equity {equity_real:.0f}% (máx {g.get('equity_max_pct', '?')}%) | "
            f"RF {rf_real:.0f}% (mín {g.get('rf_min_pct', '?')}%) | "
            f"caixa {caixa_real:.0f}% (mín {g.get('caixa_min_pct', '?')}%)"
        )

    # 8. Alertas críticos (filtrados por tickers se módulo específico)
    try:
        alertas = ctx.alertas_criticos()
        if tickers_filter:
            alertas = [a for a in alertas if any(t in a for t in tickers_filter)]
        if alertas:
            secoes.append("ALERTAS CRÍTICOS:\n" + "\n".join(f"  • {a}" for a in alertas[:8]))
    except Exception:
        pass

    if not secoes:
        return ""
    return "━━━ CONTEXTO CÉREBRO COMPLETO ━━━\n" + "\n\n".join(secoes)


async def _build_context(db: Session, user_id: Optional[int] = None):
    """Monta ContextoCerebro e o system prompt — fonte única de verdade para todos os endpoints."""
    try:
        ctx = await montar_contexto(db, user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not ctx:
        raise HTTPException(status_code=400, detail="Não foi possível montar o contexto")

    macro_flags = []
    if ctx.regime_info and hasattr(ctx.regime_info, "flags"):
        macro_flags = ctx.regime_info.flags
    elif ctx.macro_context and hasattr(ctx.macro_context, "flags"):
        macro_flags = ctx.macro_context.flags

    system = build_portfolio_prompt(
        user_name=ctx.user_name,
        estrategia=ctx.estrategia,
        patrimonio=ctx.patrimonio_total,
        modulos_ativos=ctx.modulos_ativos,
        tolerancia_drawdown=ctx.drawdown_tolerado,
        perfil_resumo=ctx.perfil_resumo,
        posicoes=ctx.posicoes,
        regime=ctx.regime,
        macro=ctx.macro,
        narrativa_macro=ctx.narrativa_macro,
        macro_flags=macro_flags,
        alocacao_real=ctx.alocacao_real,
        alocacao_alvo=ctx.alocacao_alvo,
        racional=ctx.racional_portfolio,
    )

    return ctx, system


def _trim_historico(historico: list[dict], max_chars: int = 80_000) -> list[dict]:
    """Mantém as mensagens mais recentes dentro do budget de caracteres (~20K tokens)."""
    if not historico:
        return historico
    total = sum(len(m.get("content", "")) for m in historico)
    if total <= max_chars:
        return historico
    # Remove mensagens antigas mantendo as mais recentes
    trimmed = []
    running = 0
    for msg in reversed(historico):
        msg_len = len(msg.get("content", ""))
        if running + msg_len > max_chars:
            break
        trimmed.insert(0, msg)
        running += msg_len
    return trimmed


async def _montar_contexto_chat(ctx, db) -> str:
    """Monta contexto enriquecido para o Chat V2 — macro, teses, correlação, histórico + Cérebro completo."""
    partes = []

    # Narrativa macro
    if ctx.narrativa_macro:
        partes.append(f"NARRATIVA MACRO:\n{ctx.narrativa_macro[:1000]}")

    # Alertas macro
    macro_flags = []
    if ctx.regime_info and hasattr(ctx.regime_info, "flags"):
        macro_flags = ctx.regime_info.flags
    elif ctx.macro_context and hasattr(ctx.macro_context, "flags"):
        macro_flags = ctx.macro_context.flags
    if macro_flags:
        partes.append("ALERTAS MACRO: " + " | ".join(macro_flags))

    # Status das teses (agora async — funciona corretamente)
    try:
        from app.cerebro.teses import monitorar_teses
        status = await monitorar_teses(db, ctx.portfolio_id)
        if status.get("total", 0) > 0:
            teses_txt = f"TESES: {status['total']} total, {status.get('ativas', 0)} ativas"
            if status.get("enfraquecidas"):
                teses_txt += f", {status['enfraquecidas']} enfraquecidas"
            if status.get("alertas"):
                teses_txt += "\n  " + "\n  ".join(status["alertas"][:3])
            partes.append(teses_txt)
    except Exception:
        pass

    # Performance recente
    try:
        from app.cerebro.aprendizado import analisar_performance, resumo_performance_texto
        perf = analisar_performance(db, ctx.portfolio_id, periodo_dias=90)
        if perf.get("total_trades", 0) > 0:
            partes.append(f"PERFORMANCE 90d: {resumo_performance_texto(perf)}")
    except Exception:
        pass

    # ── Cérebro Completo (Fases 1-6) ─────────────────────────────────────
    cerebro_bloco = _injetar_cerebro_completo(ctx)
    if cerebro_bloco:
        partes.append(cerebro_bloco)

    return "\n\n".join(partes)

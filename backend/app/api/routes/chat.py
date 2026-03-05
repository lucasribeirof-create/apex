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
from app.cerebro.contexto import montar as montar_contexto
from app.data import get_dados_tecnicos, formatar_tecnico_para_prompt, get_fundamentals, formatar_fundamentalista_para_prompt

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMensagem(BaseModel):
    mensagem: str
    historico: list[dict] = []





@router.post("/")
async def chat_com_gestor(body: ChatMensagem, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Streaming de chat com o gestor IA com contexto completo do portfólio (v2)."""
    ctx, system = await _build_context(db, user_id)

    # Chat V2: injeta contexto enriquecido na mensagem do usuário
    contexto_extra = _montar_contexto_chat(ctx, db)
    mensagem_user = body.mensagem
    if contexto_extra:
        mensagem_user = f"{body.mensagem}\n\n---\n[CONTEXTO AUTOMÁTICO — não mencione que recebeu isto]\n{contexto_extra}"

    messages = body.historico + [{"role": "user", "content": mensagem_user}]

    async def gerador():
        async for trecho in chat_stream(system=system, messages=messages, max_tokens=4000):
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

    mercado = getattr(pos_db, "mercado", None) or ("BDR" if pos_db.tipo == "BDR" else "B3")
    moeda = getattr(pos_db, "moeda", "BRL") or "BRL"
    moeda_str = "US$" if moeda == "USD" else "R$"
    modulo = (pos_db.modulo or "alpha").lower()

    # Detecta se posição é recente (< 24h)
    pos_age_hours = None
    if pos_db.created_at:
        pos_age_hours = (datetime.utcnow() - pos_db.created_at).total_seconds() / 3600
    is_fresh = pos_age_hours is not None and pos_age_hours < 24

    async def gerador():
        yield f"🔍 Buscando dados ao vivo de {pos_db.ticker}...\n\n"

        # Busca cotação, dados técnicos e fundamentalistas ao vivo
        tecnico, fundamentos = await asyncio.gather(
            get_dados_tecnicos(pos_db.ticker, mercado),
            get_fundamentals(pos_db.ticker),
        )
        tec_texto = formatar_tecnico_para_prompt(tecnico, moeda=moeda_str)
        fund_texto = formatar_fundamentalista_para_prompt(fundamentos, tipo=pos_db.tipo)

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

        SYSTEM = f"""\
Você é o CEO Brain APEX — gestor sênior com visão completa do portfólio.
Sua missão é diagnosticar esta posição com dados reais ao vivo.
{fresh_clause}
FRAMEWORK DE DIAGNÓSTICO:
  APORTAR MAIS  → tese sólida, preço representa oportunidade, técnicos favoráveis
  MANTER        → posição ok, sem catalisador para mudar, risco controlado
  REDUZIR       → risco/retorno desfavorável, posição acima do peso ideal
  ZERAR         → fundamento deteriorado, stop rompido ou tese invalidada

PRINCÍPIOS:
1. Use os dados técnicos e fundamentalistas ao vivo como evidência — não especule.
2. Analise o stop com precisão: está próximo? foi rompido?
3. A tese de entrada ainda é válida dado o preço atual?
4. Selic alta = renda fixa competitiva — o retorno esperado justifica o risco?
5. Avalie valuation (P/L, P/VP), rentabilidade (ROE, ROIC), margens e endividamento quando disponíveis.
6. Seja específico: mostre os números. Evite respostas vagas.
7. Retorne markdown limpo. Sem JSON, sem blocos de código."""

        pm_str = f"PM: {moeda_str} {pm:,.2f}"
        if pm_usd:
            pm_str += f" (US$ {pm_usd:,.2f})"

        age_str = ""
        if is_fresh and pos_age_hours is not None:
            age_str = f"\n⏱️ POSIÇÃO RECÉM-CRIADA (há {pos_age_hours:.0f}h) — avalie como revisão pós-montagem, não como correção."

        USER = f"""DIAGNÓSTICO DE POSIÇÃO — {pos_db.ticker.upper()} [{modulo.upper()}]{age_str}

Tese de entrada: {tese}
{pm_str}
P&L atual: {pl_pct:+.1f}%{stop_info}{alvo_info}
{plano_resumo}{macro_str}

DADOS TÉCNICOS AO VIVO:
{tec_texto}

{fund_texto}

Diagnostique esta posição. Devo APORTAR MAIS, MANTER, REDUZIR ou ZERAR?
Seja direto e use os dados acima como base."""

        yield "✅ Dados ao vivo coletados — CEO Brain analisando...\n\n"

        async for trecho in chat_stream(
            system=SYSTEM,
            messages=[{"role": "user", "content": USER}],
            max_tokens=2500,
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

        # Tickers que NÃO são ativos negociados — não têm dados técnicos
        _TICKERS_NOMINAIS = {"RF-SELIC", "CAIXA", "TESES"}

        # Busca técnicos apenas de posições que são ativos reais de mercado
        tarefas = []
        indices_reais = []  # índice das posições que têm ticker real
        for i, p in enumerate(posicoes_filtradas):
            tk = p.get("ticker", "")
            tipo = (p.get("tipo") or "").upper()
            if tk in _TICKERS_NOMINAIS or tipo in ("RF", "CAIXA"):
                continue
            tarefas.append(get_dados_tecnicos(tk, p.get("mercado", "B3") or "B3"))
            indices_reais.append(i)
        resultados_reais = await asyncio.gather(*tarefas, return_exceptions=True)

        # Monta mapa: índice da posição → resultado técnico
        mapa_tec: dict[int, dict] = {}
        for idx_pos, tec in zip(indices_reais, resultados_reais):
            if not isinstance(tec, Exception) and isinstance(tec, dict):
                mapa_tec[idx_pos] = tec

        linhas_pos = []
        stops_proximos = []

        for i, pos in enumerate(posicoes_filtradas):
            ticker = pos.get("ticker", "?")
            moeda = pos.get("moeda", "BRL") or "BRL"
            moeda_str = "US$" if moeda == "USD" else "R$"
            pm = pos.get("preco_medio") or 0
            stop = pos.get("stop_loss")
            modulo_pos = pos.get("modulo", "-")
            tipo = (pos.get("tipo") or "").upper()

            # Posições nominais (RF, CAIXA, TESES): não têm preço de mercado
            if ticker in _TICKERS_NOMINAIS or tipo in ("RF", "CAIXA"):
                val = pos.get("valor_atual") or pos.get("valor_investido") or 0
                pl_reais = pos.get("pl_reais") or 0
                vi = pos.get("valor_investido") or 0
                pl_pct = (pl_reais / vi * 100) if vi > 0 else 0
                linha = f"  • {ticker} [{modulo_pos}]: Valor {moeda_str}{val:,.0f} | P&L {pl_pct:+.1f}%"
                linha += "\n    Posição nominal — sem dados técnicos de mercado"
                linhas_pos.append(linha)
                continue

            tec = mapa_tec.get(i)
            if tec:
                preco_live = tec.get("preco_atual") or pos.get("preco_atual") or pm
                tendencia = tec.get("tendencia", "—")
                rsi = tec.get("rsi14")
                dist_ma20 = tec.get("dist_ma20", "?")
                tec_resumo = f"Tendência: {tendencia} | RSI: {rsi} | vs MA20: {dist_ma20}"
            else:
                preco_live = pos.get("preco_atual") or pm
                tec_resumo = "dados técnicos indisponíveis"

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

        fresh_cart = ""
        if carteira_recente:
            fresh_cart = """
CONTEXTO IMPORTANTE: Esta carteira foi montada há menos de 24 horas pelo próprio sistema.
As posições, stops, alvos e alocações foram escolhidos com base no perfil e nos motores especializados.
NÃO critique decisões recém-tomadas — P&L próximo de zero é ESPERADO. Stops configurados pelo sistema são intencionais.
Foque em: confirmar que a montagem está coerente com o plano, e apontar APENAS riscos externos ou mudanças macro que ocorreram APÓS a montagem."""

        SYSTEM = f"""\
Você é o CEO Brain APEX — gestor sênior com visão completa do portfólio.
Sua missão é monitorar a saúde da carteira com dados reais ao vivo.

ESTA É UMA ANÁLISE DE MONITORAMENTO — não de reconstrução. A carteira já foi montada.
Seu papel: identificar riscos imediatos, desvios do plano e posições que merecem atenção.
{fresh_cart}

PERGUNTAS QUE DEVE RESPONDER:
1. Algum stop está prestes a ser atingido? Qual a urgência?
2. O P&L de cada posição está saudável para o tempo de vida esperado?
3. A alocação real está desviando do plano estratégico?
4. O cenário macro atual afeta alguma posição específica?
5. Alguma posição perdeu a tese? O que fazer?

FORMATO DE RESPOSTA:
- **Saúde Geral:** [ÓTIMA / BOA / ATENÇÃO / CRÍTICA]
- Destaques positivos
- Alertas e riscos imediatos
- Posições que merecem revisão (com dados)
- Recomendação de curto prazo

Use markdown limpo. Sem JSON. Seja direto e baseado nos dados."""

        age_cart = ""
        if carteira_recente and _idades:
            age_cart = f"\n⏱️ CARTEIRA RECÉM-MONTADA (posição mais antiga: {max(_idades):.0f}h atrás)"

        USER = f"""MONITORAMENTO DE CARTEIRA{' — módulo ' + modulo.upper() if modulo else ''}{age_cart}

POSIÇÕES COM COTAÇÃO AO VIVO:
{chr(10).join(linhas_pos)}{stops_alerta}{plano_str}{macro_str}

Patrimônio total: R$ {(ctx.patrimonio_total or 0):,.0f}
Módulos ativos: {', '.join(ctx.modulos_ativos or [])}

Faça o diagnóstico de saúde desta carteira. Foque nos riscos imediatos e desvios do plano."""

        yield "✅ Dados ao vivo coletados — CEO Brain analisando...\n\n"

        async for trecho in chat_stream(
            system=SYSTEM,
            messages=[{"role": "user", "content": USER}],
            max_tokens=4000,
        ):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")




# ─── Helpers ──────────────────────────────────────────────────────────────────

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
    )

    return ctx, system


def _montar_contexto_chat(ctx, db) -> str:
    """Monta contexto enriquecido para o Chat V2 — macro, teses, correlação, histórico."""
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

    # Status das teses
    try:
        from app.cerebro.teses import monitorar_teses
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            pass  # monitorar é async, skip se não pudermos aguardar
        else:
            status = loop.run_until_complete(monitorar_teses(db, ctx.portfolio_id))
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

    return "\n\n".join(partes)

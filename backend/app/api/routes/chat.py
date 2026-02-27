"""Rota do chat com o gestor IA."""
import asyncio
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Position
from app.ai import chat_stream, build_portfolio_prompt, chat
from app.data import get_macro_br, get_macro_global, get_dados_tecnicos, formatar_tecnico_para_prompt

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMensagem(BaseModel):
    mensagem: str
    historico: list[dict] = []


class PropostaMudanca(BaseModel):
    descricao: str   # o que o usuário quer mudar, em linguagem livre


@router.post("/")
async def chat_com_gestor(body: ChatMensagem, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Streaming de chat com o gestor IA com contexto completo do portfólio."""
    user, portfolio, posicoes, macro, system = await _build_context(db, user_id)
    messages = body.historico + [{"role": "user", "content": body.mensagem}]

    async def gerador():
        async for trecho in chat_stream(system=system, messages=messages, max_tokens=4000):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")


@router.get("/analisar-posicao/{position_id}")
async def analisar_posicao(position_id: int, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Streaming: análise focada de uma posição individual.
    Adapta o framework automaticamente ao módulo (tese DCA vs trade tático vs renda).
    """
    user, portfolio, posicoes, macro, system = await _build_context(db, user_id)

    # Busca a posição específica
    pos_db = db.query(Position).filter(
        Position.id == position_id,
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).first()
    if not pos_db:
        raise HTTPException(status_code=404, detail="Posição não encontrada")

    modulo = pos_db.modulo or "—"
    ticker = pos_db.ticker
    moeda = getattr(pos_db, "moeda", "BRL") or "BRL"

    # Monta contexto específico da posição
    if moeda == "USD":
        pm_usd = getattr(pos_db, "preco_medio_usd", None) or pos_db.preco_medio
        preco_info = f"Preço médio: US$ {pm_usd:,.2f} | Moeda: USD"
    else:
        preco_atual = pos_db.preco_atual or pos_db.preco_medio
        pl = pos_db.pl_percentual or 0
        preco_info = f"Preço médio: R$ {pos_db.preco_medio:,.2f} | Atual: R$ {preco_atual:,.2f} | P&L: {pl:+.1f}%"

    tese_str = f"\nTese registrada: \"{pos_db.tese}\"" if getattr(pos_db, "tese", None) else ""
    stop_str = f"\nStop atual: R$ {pos_db.stop_loss:,.2f}" if pos_db.stop_loss else ""
    alvo_str = f"\nAlvo 1: R$ {pos_db.alvo_1:,.2f}" if pos_db.alvo_1 else ""
    mercado_str = f" | Mercado: {pos_db.mercado}" if getattr(pos_db, "mercado", None) else ""

    from datetime import datetime
    data_atual = datetime.now().strftime("%d/%m/%Y")

    # Busca dados técnicos em tempo real
    mercado_cod = getattr(pos_db, "mercado", None) or "B3"
    tecnico = await get_dados_tecnicos(ticker, mercado_cod)
    bloco_tecnico = formatar_tecnico_para_prompt(
        tecnico,
        moeda="US$" if moeda == "USD" else "R$"
    )

    # Atualiza preco_info com cotação ao vivo se disponível
    preco_live = tecnico.get("preco_atual")
    if preco_live and moeda != "USD":
        pl_live = ((preco_live - pos_db.preco_medio) / pos_db.preco_medio * 100) if pos_db.preco_medio else 0
        preco_info = f"Preço médio: R$ {pos_db.preco_medio:,.2f} | Cotação ao vivo: R$ {preco_live:,.2f} | P&L agora: {pl_live:+.1f}%"

    prompt = f"""DATA DE HOJE: {data_atual}. Use esta data como referência para todas as suas análises, projeções e recomendações. Nunca cite datas anteriores a esta como futuras.

Analise a posição abaixo de forma objetiva e completa. Não repita o que eu disse — adicione informação.

POSIÇÃO: {ticker} | Módulo: {modulo}{mercado_str}
{preco_info}{tese_str}{stop_str}{alvo_str}

ANÁLISE TÉCNICA (dados em tempo real):
{bloco_tecnico}

Aplique o framework correto para o módulo:

{"— É uma posição de TESE (DCA de convicção). Avalie: (1) o fundamento original ainda se sustenta dado o cenário macro atual? (2) o preço atual fortalece ou enfraquece a convicção — é oportunidade de aportar mais ou sinal de deterioração? (3) há algo no cenário macroeconômico atual (juros, câmbio, setor) que invalida ou reforça a tese? Diga claramente: MANTER, APORTAR MAIS ou TESE INVALIDADA — e justifique." if modulo == "teses" else
"— É uma posição TÁTICA. Avalie: (1) o setup original ainda está válido? (2) o stop atual está adequado ou precisa ser ajustado? (3) o alvo segue sendo realista? (4) há razão para aumentar, reduzir ou zerar a posição agora? Seja específico." if modulo in ("momentum", "alpha") else
"— É uma posição de RENDA. Avalie: (1) o yield atual é compatível com a taxa de juros vigente? (2) há risco de corte de dividendo/distribuição? (3) a posição está bem alocada dentro do portfólio? Recomende manter, aumentar ou reduzir."}

Contexto macro relevante: {_formatar_macro_simples(macro)}
Regime: {portfolio.regime}"""

    async def gerador():
        async for trecho in chat_stream(system=system, messages=[{"role": "user", "content": prompt}], max_tokens=2500):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")


@router.get("/analisar-carteira")
async def analisar_carteira(
    modulo: Optional[str] = None,  # None = tudo, ou "teses", "momentum", "fiis", etc.
    user_id: Optional[int] = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """
    Streaming: análise completa da carteira (ou de um módulo específico).
    Produz diagnóstico + ação recomendada para cada posição.
    """
    from datetime import datetime
    user, portfolio, posicoes, macro, system = await _build_context(db, user_id)
    data_atual = datetime.now().strftime("%d/%m/%Y")

    # Filtra por módulo se solicitado
    if modulo and modulo != "todos":
        posicoes_filtradas = [p for p in posicoes if (p.get("modulo") or "").lower() == modulo.lower()]
    else:
        posicoes_filtradas = posicoes

    if not posicoes_filtradas:
        async def vazio():
            yield "Nenhuma posição encontrada para este filtro."
        return StreamingResponse(vazio(), media_type="text/plain")

    # Busca cotações ao vivo para todas as posições de forma paralela
    tarefas_tecnico = [
        get_dados_tecnicos(p.get("ticker", ""), p.get("mercado") or "B3")
        for p in posicoes_filtradas
    ]
    resultados_tecnicos = await asyncio.gather(*tarefas_tecnico, return_exceptions=True)

    # Formata cada posição com todos os dados disponíveis
    linhas = []
    for i, p in enumerate(posicoes_filtradas):
        ticker = p.get("ticker", "?")
        tipo = p.get("tipo", "-")
        mod = p.get("modulo") or "-"
        pm = p.get("preco_medio") or 0
        moeda = p.get("moeda") or "BRL"
        mercado = p.get("mercado") or "B3"
        stop = p.get("stop_loss")
        tese = p.get("tese")
        pm_usd = p.get("preco_medio_usd")

        # Usa cotação ao vivo se disponível
        tec = resultados_tecnicos[i] if not isinstance(resultados_tecnicos[i], Exception) else {}
        preco_live = tec.get("preco_atual") if isinstance(tec, dict) else None

        if moeda == "USD":
            # Para posições em dólar NÃO mistura preços — usa P&L armazenado
            pl = p.get("pl_percentual") or 0
            preco_live_str = f" → US${preco_live:,.2f} [live]" if preco_live else ""
            pm_ref = f"US${pm_usd:,.2f}" if pm_usd else f"R${pm:,.2f}"
            linha = f"- {ticker} ({tipo}, {mod}, {mercado}): PM {pm_ref}{preco_live_str} | P&L {pl:+.1f}%"
        else:
            atual = preco_live or p.get("preco_atual") or pm
            pl = ((atual - pm) / pm * 100) if (pm and atual) else (p.get("pl_percentual") or 0)
            fonte = "live" if preco_live else "bd"
            linha = f"- {ticker} ({tipo}, {mod}): PM R${pm:,.2f} → R${atual:,.2f} [{fonte}] | P&L {pl:+.1f}%"

        # Indicadores técnicos compactos
        if isinstance(tec, dict) and not tec.get("erro"):
            rsi = tec.get("rsi14")
            tend = tec.get("tendencia", "")
            macd_d = tec.get("macd")
            tech_parts = []
            if rsi:
                tech_parts.append(f"RSI={rsi}")
            if tend:
                tech_parts.append(tend.split(" (")[0])  # só a palavra chave
            if macd_d:
                tech_parts.append(f"MACD={macd_d['cruzamento']}")
            if tech_parts:
                linha += f" | {' | '.join(tech_parts)}"

        if stop:
            linha += f" | stop R${stop:,.2f}"
        if tese:
            linha += f"\n  Tese: \"{tese[:120]}{'...' if len(tese) > 120 else ''}\""
        linhas.append(linha)

    posicoes_str = "\n".join(linhas)
    filtro_label = f"Módulo: {modulo.upper()}" if (modulo and modulo != "todos") else "Carteira completa"

    prompt = f"""DATA DE HOJE: {data_atual}. Use esta data em todas as projeções — nunca cite datas passadas como futuras.

Faça o DIAGNÓSTICO COMPLETO DA CARTEIRA abaixo. Você tem visão do portfólio inteiro — use isso.

{filtro_label} | {len(posicoes_filtradas)} posições

POSIÇÕES:
{posicoes_str}

MACRO ATUAL: {_formatar_macro_simples(macro)}
Regime: {portfolio.regime}

---

ESTRUTURA OBRIGATÓRIA:

**DIAGNÓSTICO GERAL** (4-5 linhas)
Saúde da carteira: P&L agregado, concentração de risco, exposição ao macro atual. Há posições correlacionadas que aumentam o risco sem que o investidor perceba? O portfólio está adequado ao regime {portfolio.regime}?

**ANÁLISE POR POSIÇÃO**
Para cada posição, uma linha de ação clara:

Formato obrigatório por posição:
**[TICKER]** → [AÇÃO EM MAIÚSCULA] — justificativa em 1-2 linhas

Ações possíveis: APORTAR MAIS | MANTER | REDUZIR | ZERAR | AJUSTAR STOP | AJUSTAR ALVO | TESE INVALIDADA

Framework por tipo:
- Teses (DCA): fundamento ainda válido? Preço é oportunidade ou deterioração? Selic {macro.get('selic', '?')}% compete com esse ativo?
- Momentum/Alpha: stop adequado? Alvo realista? Setup ainda ativo?
- FIIs/Renda: yield vs curva de juros. Manter, aumentar ou reduzir exposição?

**TOP 3 PRIORIDADES AGORA**
As 3 ações mais urgentes desta carteira, em ordem de prioridade. Seja específico — ticker + número concreto quando aplicável."""

    async def gerador():
        async for trecho in chat_stream(system=system, messages=[{"role": "user", "content": prompt}], max_tokens=4000):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")


async def propor_mudanca(body: PropostaMudanca, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Analisa uma proposta de mudança estrutural no portfólio.
    Não streaming — retorna JSON com análise + ação proposta para confirmação.
    """
    user, portfolio, posicoes, macro, system = await _build_context(db, user_id)

    # Alocação REAL: calculada a partir das posições abertas, não dos alvos
    patrimonio_calc = sum(p["valor_atual"] for p in posicoes)
    alocacao_atual = _calcular_alocacao_real(posicoes, patrimonio_calc)

    prompt_analise = f"""O investidor está solicitando a seguinte mudança no portfólio:

"{body.descricao}"

Alocação atual: {alocacao_atual}
Estratégia atual: APEX {user.estrategia}

Analise esta proposta considerando:
1. O perfil do investidor e sua tolerância declarada ao risco
2. O regime de mercado atual ({portfolio.regime})
3. Se a mudança é prudente e bem fundamentada
4. Quais riscos e oportunidades ela traz

Depois da análise, proponha a nova alocação em JSON no formato exato abaixo (obrigatório, ao final da resposta):

PROPOSTA_JSON:{{
  "tipo": "rebalancear" | "ativar_modulo" | "desativar_modulo" | "mudar_estrategia",
  "descricao_curta": "Resumo em 1 linha",
  "nova_estrategia": "CORE|ALPHA|RENDA|CUSTOM ou null",
  "nova_alocacao": {{"etfs": X, "fiis": X, "renda_fixa": X, "momentum": X, "wheel": X, "alpha": X, "dividendos": X, "caixa": X}},
  "pode_aplicar": true | false,
  "motivo_bloqueio": "Se pode_aplicar=false, explicar por quê"
}}

Seja direto e honesto. Se a mudança não fizer sentido para o perfil, diga claramente."""

    resposta = await chat(
        system=system,
        messages=[{"role": "user", "content": prompt_analise}],
        max_tokens=1200,
    )

    # Extrai o bloco JSON da resposta
    import json, re
    analise = resposta
    acao_proposta = None

    match = re.search(r"PROPOSTA_JSON:(\{.*?\})\s*$", resposta, re.DOTALL)
    if match:
        analise = resposta[:match.start()].strip()
        try:
            acao_proposta = json.loads(match.group(1))
        except Exception:
            acao_proposta = None

    return {
        "analise": analise,
        "acao_proposta": acao_proposta,
        "requer_confirmacao": acao_proposta is not None and acao_proposta.get("pode_aplicar", False),
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _build_context(db: Session, user_id: Optional[int] = None):
    """Monta contexto completo de portfólio para injetar no prompt."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user or not user.onboarding_completo:
        raise HTTPException(status_code=400, detail="Onboarding não concluído")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicoes_db = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()
    posicoes = [
        {
            "ticker": p.ticker, "tipo": p.tipo, "modulo": p.modulo,
            "preco_medio": p.preco_medio,
            "preco_atual": p.preco_atual or p.preco_medio,
            "pl_percentual": p.pl_percentual or 0,
            "stop_loss": p.stop_loss,
            "quantidade": p.quantidade or 0,
            "valor_investido": p.valor_investido or 0,
            "valor_atual": (p.preco_atual or p.preco_medio or 0) * (p.quantidade or 0),
            # Módulo Teses
            "tese": p.tese or None,
            "mercado": p.mercado or None,
            "moeda": p.moeda or "BRL",
            "preco_medio_usd": getattr(p, 'preco_medio_usd', None),
        }
        for p in posicoes_db
    ]

    macro_br, macro_global = await get_macro_br(), await get_macro_global()
    macro = {**macro_br, **macro_global}

    drawdown_map = {"CORE": 15, "RENDA": 10, "ALPHA": 30, "CUSTOM": 20}

    system = build_portfolio_prompt(
        user_name=user.name,
        estrategia=user.estrategia or "CORE",
        patrimonio=portfolio.patrimonio_total or 0,
        modulos_ativos=_get_modulos_ativos(portfolio),
        tolerancia_drawdown=drawdown_map.get(user.estrategia or "CORE", 15),
        perfil_resumo=user.estrategia_resumo or "Perfil definido no onboarding.",
        posicoes=posicoes,
        regime=portfolio.regime or "MISTO",
        macro=macro,
    )

    return user, portfolio, posicoes, macro, system


def _get_modulos_ativos(portfolio: Portfolio) -> list[str]:
    modulos = []
    if portfolio.alvo_etfs > 0: modulos.append("ETFs")
    if portfolio.alvo_fiis > 0: modulos.append("FIIs")
    if portfolio.alvo_renda_fixa > 0: modulos.append("Renda Fixa")
    if portfolio.alvo_momentum > 0: modulos.append("Momentum")
    if portfolio.alvo_wheel > 0: modulos.append("Wheel")
    if getattr(portfolio, "alvo_dividendos", 0) > 0: modulos.append("Dividendos")
    if portfolio.alvo_alpha > 0: modulos.append("Convicção ALPHA")
    if getattr(portfolio, "alvo_teses", 0) > 0: modulos.append("Teses")
    return modulos


def _calcular_alocacao_real(posicoes: list[dict], patrimonio: float) -> dict:
    """Calcula a alocação REAL em % por módulo a partir das posições abertas."""
    modulos = {"etfs": 0.0, "fiis": 0.0, "renda_fixa": 0.0, "momentum": 0.0,
               "wheel": 0.0, "alpha": 0.0, "dividendos": 0.0, "caixa": 0.0}
    if patrimonio <= 0:
        return modulos
    for p in posicoes:
        modulo = (p.get("modulo") or "caixa").lower()
        if modulo in modulos:
            modulos[modulo] += (p["valor_atual"] / patrimonio) * 100
    return {k: round(v, 1) for k, v in modulos.items()}


def _formatar_macro_simples(macro: dict) -> str:
    partes = []
    if macro.get("selic"):
        partes.append(f"Selic {macro['selic']}%")
    if macro.get("ipca"):
        partes.append(f"IPCA {macro['ipca']}%")
    if macro.get("dolar"):
        partes.append(f"USD/BRL {macro['dolar']}")
    if macro.get("sp500"):
        partes.append(f"S&P500 {macro['sp500']}")
    if macro.get("vix"):
        partes.append(f"VIX {macro['vix']}")
    return " | ".join(partes) if partes else "dados não disponíveis"

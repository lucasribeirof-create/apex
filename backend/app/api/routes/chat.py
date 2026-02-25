"""Rota do chat com o gestor IA."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Position
from app.ai import chat_stream, build_portfolio_prompt, chat
from app.data import get_macro_br, get_macro_global

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
        async for trecho in chat_stream(system=system, messages=messages, max_tokens=1500):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")


@router.post("/proposta")
async def propor_mudanca(body: PropostaMudanca, user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """
    Analisa uma proposta de mudança estrutural no portfólio.
    Não streaming — retorna JSON com análise + ação proposta para confirmação.
    """
    user, portfolio, posicoes, macro, system = await _build_context(db, user_id)

    alocacao_atual = {
        "etfs": portfolio.alvo_etfs,
        "fiis": portfolio.alvo_fiis,
        "renda_fixa": portfolio.alvo_renda_fixa,
        "momentum": portfolio.alvo_momentum,
        "wheel": portfolio.alvo_wheel,
        "alpha": portfolio.alvo_alpha,
        "dividendos": portfolio.alvo_dividendos,
        "caixa": portfolio.alvo_caixa,
    }

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
            "preco_medio": p.preco_medio, "preco_atual": p.preco_atual or p.preco_medio,
            "pl_percentual": p.pl_percentual or 0, "stop_loss": p.stop_loss,
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
    return modulos


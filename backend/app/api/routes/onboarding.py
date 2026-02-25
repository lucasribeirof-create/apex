"""
Rota de onboarding — conversa guiada pela IA para definir o perfil do investidor.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Position, Briefing
from app.ai import chat_stream, build_onboarding_prompt, chat

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class OnboardingMensagem(BaseModel):
    mensagem: str
    historico: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


class StartOnboarding(BaseModel):
    name: str


class FinalizeOnboarding(BaseModel):
    user_id: int | None = None
    name: str | None = None        # optional, used as fallback if user not found by id
    answers: dict
    total_patrimony: float


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/usuarios")
def listar_usuarios(db: Session = Depends(get_db)):
    """Lista todos os usuários com onboarding concluído (para o seletor de carteiras)."""
    users = (
        db.query(User)
        .filter(User.onboarding_completo == True)
        .order_by(User.created_at.desc())
        .all()
    )
    return [
        {
            "id": u.id,
            "name": u.name,
            "estrategia": u.estrategia,
            "patrimonio": u.patrimonio_total,
            "created_at": u.created_at,
        }
        for u in users
    ]


@router.delete("/usuarios/{user_id}")
def deletar_usuario(user_id: int, db: Session = Depends(get_db)):
    """Remove uma carteira e todos os dados relacionados (cascade manual)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Carteira não encontrada")

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user_id).first()
    if portfolio:
        # Briefings ligados ao portfolio
        db.query(Briefing).filter(Briefing.portfolio_id == portfolio.id).delete()
        # Posições ligadas ao portfolio
        db.query(Position).filter(Position.portfolio_id == portfolio.id).delete()
        db.delete(portfolio)

    db.delete(user)
    db.commit()
    return {"ok": True}


@router.post("/start")
def start_onboarding(body: StartOnboarding, db: Session = Depends(get_db)):
    """Cria um novo usuário no início do onboarding. Sempre cria novo — não reusa."""
    user = User(name=body.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user_id": user.id}


@router.post("/finalize")
def finalize_onboarding(body: FinalizeOnboarding, db: Session = Depends(get_db)):
    """
    Finaliza o onboarding mapeando as respostas do formulário frontend
    para o modelo interno de scoring APEX.
    """
    a = body.answers
    # Mapeia chaves do frontend → chaves internas do scoring
    respostas = {
        "volatilidade": a.get("volatility"),
        "liquidez": a.get("liquidity"),
        "renda": a.get("income"),
        "experiencia": a.get("experience", []),
        "tempo": a.get("time_available"),
        "objetivo": a.get("objective"),
        "horizonte": a.get("horizon"),
    }

    score = _calcular_score(respostas)

    # Classificação: RENDA tem prioridade se objetivo explícito for renda passiva
    objetivo_declarado = a.get("goal_type", "")
    if objetivo_declarado == "renda":
        estrategia = "RENDA"
    elif score >= 11:
        estrategia = "ALPHA"
    else:
        estrategia = "CORE"

    alocacao = _get_alocacao(estrategia)

    user = (db.query(User).filter(User.id == body.user_id).first()
            if body.user_id else db.query(User).first())
    if user:
        user.patrimonio_total = body.total_patrimony
        user.objetivo_tipo = a.get("goal_type", "crescimento")
        user.objetivo_valor = a.get("goal_value")
        user.objetivo_prazo = a.get("horizon")
        user.onboarding_respostas = respostas
        user.onboarding_score = score
        user.onboarding_completo = True
        user.estrategia = estrategia
    else:
        user = User(
            name=body.name or "Investidor",
            patrimonio_total=body.total_patrimony,
            objetivo_tipo=a.get("goal_type", "crescimento"),
            objetivo_valor=a.get("goal_value"),
            objetivo_prazo=a.get("horizon"),
            onboarding_respostas=respostas,
            onboarding_score=score,
            onboarding_completo=True,
            estrategia=estrategia,
        )
        db.add(user)
        db.flush()

    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not portfolio:
        portfolio = Portfolio(
            user_id=user.id,
            patrimonio_total=body.total_patrimony,
            patrimonio_inicio=body.total_patrimony,
            **{f"alvo_{k}": v for k, v in alocacao.items()},
        )
        db.add(portfolio)
    else:
        portfolio.patrimonio_total = body.total_patrimony
        for k, v in alocacao.items():
            setattr(portfolio, f"alvo_{k}", v)

    db.commit()
    db.refresh(user)
    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()

    return {
        "user_id": user.id,
        "portfolio_id": portfolio.id if portfolio else None,
        "strategy_type": estrategia,
        "risk_score": score,
        "allocation": alocacao,
        "ai_explanation": _get_ai_explanation(estrategia, score),
    }


class OnboardingRespostas(BaseModel):
    nome: str
    patrimonio_total: float
    objetivo_tipo: str
    objetivo_valor: float | None = None
    objetivo_prazo: str | None = None
    respostas: dict


class OnboardingScore(BaseModel):
    respostas: dict


@router.post("/chat")
async def onboarding_chat(body: OnboardingMensagem):
    """
    Streaming de conversa do onboarding.
    O frontend exibe o texto com efeito typewriter conforme chega.
    """
    system = build_onboarding_prompt()
    messages = body.historico + [{"role": "user", "content": body.mensagem}]

    async def gerador():
        async for trecho in chat_stream(system=system, messages=messages, max_tokens=800):
            yield trecho

    return StreamingResponse(gerador(), media_type="text/plain")


@router.post("/calcular-score")
def calcular_score_onboarding(body: OnboardingScore):
    """
    Calcula o score do onboarding e retorna a estratégia recomendada.
    Pontuação baseada nas respostas — >= 11 pts = ALPHA, < 11 = CORE.
    """
    score = _calcular_score(body.respostas)
    estrategia = "ALPHA" if score >= 11 else "CORE"

    alocacao = _get_alocacao(estrategia)

    return {
        "score": score,
        "estrategia": estrategia,
        "alocacao": alocacao,
    }


@router.post("/salvar")
def salvar_onboarding(body: OnboardingRespostas, db: Session = Depends(get_db)):
    """Salva o perfil do usuário e cria o portfólio inicial."""
    score = _calcular_score(body.respostas)
    estrategia = "ALPHA" if score >= 11 else "CORE"
    alocacao = _get_alocacao(estrategia)

    # Verificar se já existe usuário (app single user por enquanto)
    user = db.query(User).first()
    if user:
        # Atualizar perfil existente
        user.name = body.nome
        user.patrimonio_total = body.patrimonio_total
        user.objetivo_tipo = body.objetivo_tipo
        user.objetivo_valor = body.objetivo_valor
        user.objetivo_prazo = body.objetivo_prazo
        user.onboarding_respostas = body.respostas
        user.onboarding_score = score
        user.onboarding_completo = True
        user.estrategia = estrategia
    else:
        user = User(
            name=body.nome,
            patrimonio_total=body.patrimonio_total,
            objetivo_tipo=body.objetivo_tipo,
            objetivo_valor=body.objetivo_valor,
            objetivo_prazo=body.objetivo_prazo,
            onboarding_respostas=body.respostas,
            onboarding_score=score,
            onboarding_completo=True,
            estrategia=estrategia,
        )
        db.add(user)
        db.flush()

    # Criar ou atualizar portfólio
    portfolio = db.query(Portfolio).filter(Portfolio.user_id == user.id).first()
    if not portfolio:
        portfolio = Portfolio(
            user_id=user.id,
            patrimonio_total=body.patrimonio_total,
            patrimonio_inicio=body.patrimonio_total,
            **{f"alvo_{k}": v for k, v in alocacao.items()},
        )
        db.add(portfolio)
    else:
        for k, v in alocacao.items():
            setattr(portfolio, f"alvo_{k}", v)

    db.commit()
    db.refresh(user)

    return {
        "user_id": user.id,
        "portfolio_id": portfolio.id,
        "estrategia": estrategia,
        "score": score,
        "alocacao": alocacao,
        "mensagem": f"Bem-vindo ao APEX Manager, {body.nome}! Estratégia APEX {estrategia} configurada.",
    }


@router.get("/status")
def status_onboarding(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Verifica se o onboarding foi concluído."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user or not user.onboarding_completo:
        return {"completo": False}
    return {
        "completo": True,
        "user_id": user.id,
        "nome": user.name,
        "estrategia": user.estrategia,
    }


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_ai_explanation(estrategia: str, score: int) -> str:
    """Gera texto explicativo sobre a classsificação do investidor."""
    textos = {
        "CORE": (
            f"Com score {score}/15, seu perfil é equilibrado. A estratégia APEX CORE combina "
            "crescimento consistente com gestão de risco, diversificando entre ETFs, FIIs e Renda Fixa."
        ),
        "ALPHA": (
            f"Com score {score}/15, você tem perfil agressivo e experiente. A estratégia APEX ALPHA "
            "busca alfa real com posições concentradas em Momentum, Wheel e convicção."
        ),
        "RENDA": (
            "Seu objetivo principal é gerar renda passiva. A estratégia APEX RENDA foca em FIIs, "
            "dividendos e renda fixa para entregar fluxo de caixa consistente e crescente."
        ),
        "CUSTOM": (
            "Seu perfil tem características únicas. A estratégia APEX CUSTOM permite personalização "
            "total da alocação com validação contínua do gestor IA."
        ),
    }
    return textos.get(estrategia, "Estratégia definida com base no seu perfil.")


def _calcular_score(respostas: dict) -> int:
    """
    Score de classificação CORE vs ALPHA.
    Baseado nas 7 dimensões do questionário.
    """
    score = 0
    pontos = {
        # Volatilidade (0-3 pts)
        "volatilidade": {
            "vende_tudo": 0, "vende_parte": 1, "mantem": 2, "compra_mais": 3
        },
        # Liquidez nos próximos 12 meses (0-2 pts)
        "liquidez": {
            "mais_30pct": 0, "10_30pct": 1, "menos_10pct": 2, "nenhuma": 2
        },
        # Fonte de renda (0-2 pts)
        "renda": {
            "depende_portfolio": 0, "parcial": 1, "ativa": 2
        },
        # Experiência (0-3 pts — multi-select)
        # calculado separadamente
        # Objetivo principal (0-1 pt)
        "objetivo": {
            "preservacao": 0, "renda_passiva": 0, "equilibrio": 1, "crescimento": 1
        },
        # Horizonte temporal (0-2 pts)
        "horizonte": {
            "ate_2anos": 0, "2_5anos": 1, "5_10anos": 2, "mais_10anos": 2
        },
        # Tempo disponível (0-2 pts)
        "tempo": {
            "menos_1h": 0, "1_3h": 1, "3_5h": 2, "mais_5h": 2
        },
    }

    for campo, opcoes in pontos.items():
        valor = respostas.get(campo)
        if valor and valor in opcoes:
            score += opcoes[valor]

    # Experiência: multi-select (0-3 pts)
    experiencia = respostas.get("experiencia", [])
    if isinstance(experiencia, list):
        exp_score = 0
        if "acoes_br" in experiencia:
            exp_score += 1
        if "opcoes" in experiencia:
            exp_score += 1
        if any(x in experiencia for x in ["exterior", "etfs", "bdrs"]):
            exp_score += 1
        score += min(exp_score, 3)

    return score


def _get_alocacao(estrategia: str) -> dict:
    if estrategia == "ALPHA":
        return {
            "etfs": 25.0, "fiis": 10.0, "renda_fixa": 10.0,
            "momentum": 20.0, "wheel": 10.0, "alpha": 10.0,
            "dividendos": 0.0, "caixa": 5.0,
        }
    elif estrategia == "RENDA":
        return {
            "etfs": 10.0, "fiis": 35.0, "renda_fixa": 30.0,
            "momentum": 0.0, "wheel": 0.0, "alpha": 0.0,
            "dividendos": 20.0, "caixa": 5.0,
        }
    else:  # CORE
        return {
            "etfs": 35.0, "fiis": 20.0, "renda_fixa": 20.0,
            "momentum": 15.0, "wheel": 0.0, "alpha": 0.0,
            "dividendos": 0.0, "caixa": 10.0,
        }

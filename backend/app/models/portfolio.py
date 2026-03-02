from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, JSON
from app.models.base import Base


class Portfolio(Base):
    __tablename__ = "portfolios"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Identificação do portfólio
    nome = Column(String(100), default="Carteira Real")
    tipo = Column(String(20), default="real")     # real | simulada

    # Patrimônio snapshot (atualizado quando o usuário acessa o app)
    patrimonio_total = Column(Float, default=0.0)
    patrimonio_ontem = Column(Float, default=0.0)
    patrimonio_mes_inicio = Column(Float, default=0.0)
    patrimonio_ano_inicio = Column(Float, default=0.0)
    patrimonio_inicio = Column(Float, default=0.0)        # desde o início

    # Capital declarado pelo usuário (carteira real)
    # Used to compute caixa_disponivel = capital_declarado - soma_posicoes
    capital_declarado = Column(Float, nullable=True)      # None = não declarado

    # Alocação alvo (%) por módulo — definida no onboarding
    alvo_etfs = Column(Float, default=0.0)
    alvo_fiis = Column(Float, default=0.0)
    alvo_renda_fixa = Column(Float, default=0.0)
    alvo_momentum = Column(Float, default=0.0)
    alvo_wheel = Column(Float, default=0.0)
    alvo_alpha = Column(Float, default=0.0)
    alvo_dividendos = Column(Float, default=0.0)   # módulo Dividendos (ações pagadoras)
    alvo_teses = Column(Float, default=0.0)        # módulo Teses (buy & hold por convicção)
    alvo_caixa = Column(Float, default=0.0)

    # Regime de mercado atual
    regime = Column(String(10), default="MISTO")          # BULL | MISTO | BEAR
    regime_atualizado_em = Column(DateTime, nullable=True)

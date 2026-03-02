from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text

from app.models.base import Base


class TeseInvestimento(Base):
    __tablename__ = "teses_investimento"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    tipo = Column(String(20), default="COMPRA")
    tese_resumo = Column(String(200))
    tese_completa = Column(Text)
    catalisadores = Column(Text)
    riscos = Column(Text)
    condicao_invalidacao = Column(Text)
    alvo_preco = Column(Float, nullable=True)
    stop_preco = Column(Float, nullable=True)
    prazo_estimado = Column(String(50), nullable=True)
    status = Column(String(20), default="ATIVA")
    score_conviccao = Column(Integer, default=5)
    ultima_revisao = Column(DateTime, nullable=True)
    historico_revisoes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

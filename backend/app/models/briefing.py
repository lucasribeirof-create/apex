from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean
from app.models.base import Base


class Briefing(Base):
    __tablename__ = "briefings"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    data = Column(DateTime, default=datetime.utcnow, index=True)
    tipo = Column(String(20), default="morning")       # morning | manual
    conteudo = Column(Text, nullable=False)            # Texto gerado pelo Claude
    lido = Column(Boolean, default=False)

    # Snapshot macro no momento do briefing
    selic = Column(Float, nullable=True)
    dolar = Column(Float, nullable=True)
    ibov = Column(Float, nullable=True)
    ibov_variacao = Column(Float, nullable=True)
    regime = Column(String(10), nullable=True)         # BULL | MISTO | BEAR

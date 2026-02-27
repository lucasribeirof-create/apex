from datetime import datetime
from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from app.models.base import Base


class Aporte(Base):
    """Histórico de aportes DCA para posições do módulo Teses."""
    __tablename__ = "aportes"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    data = Column(DateTime, nullable=False, default=datetime.utcnow)
    quantidade = Column(Float, nullable=False)
    preco = Column(Float, nullable=False)       # preço no momento do aporte
    moeda = Column(String(5), default="BRL")   # BRL | USD
    valor_total = Column(Float, nullable=False) # quantidade * preco
    nota = Column(String(200), nullable=True)   # observação opcional

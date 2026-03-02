from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from app.models.base import Base


class Transacao(Base):
    """
    Registro histórico de transações por posição.
    tipos: compra | dca | venda_parcial | venda_total | split | bonificacao | amortizacao
    """
    __tablename__ = "transacoes"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    tipo = Column(String(30), nullable=False)   # compra | dca | venda_parcial | venda_total | split | bonificacao
    data = Column(DateTime, nullable=False, default=datetime.utcnow)

    quantidade = Column(Float, nullable=False)
    preco = Column(Float, nullable=False)
    valor_total = Column(Float, nullable=True)   # calculado: quantidade * preco
    taxas = Column(Float, default=0.0)
    observacao = Column(Text, nullable=True)

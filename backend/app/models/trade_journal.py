from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text

from app.models.base import Base


class TradeJournal(Base):
    __tablename__ = "trade_journal"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=True, index=True)
    tese_id = Column(Integer, nullable=True, index=True)
    ticker = Column(String(20), nullable=False)
    tipo_operacao = Column(String(20), nullable=False)  # ENTRADA | SAIDA | AUMENTO | REDUCAO
    acao_framework = Column(String(20), nullable=True)  # ENTRAR | MANTER | SAIR | AUMENTAR | REDUZIR
    motivo = Column(Text, nullable=True)
    preco = Column(Float, nullable=True)
    quantidade = Column(Float, nullable=True)
    valor_total = Column(Float, nullable=True)
    resultado_pct = Column(Float, nullable=True)
    resultado_reais = Column(Float, nullable=True)
    rr_realizado = Column(Float, nullable=True)
    duracao_dias = Column(Integer, nullable=True)
    modulo = Column(String(20), nullable=True)  # momentum | wheel | alpha | etc.
    notas_post_mortem = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

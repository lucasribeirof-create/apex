"""Modelo para cache local de dividendos (merge BRAPI + yFinance)."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint
from app.models.base import Base


class DividendEvent(Base):
    """
    Cache persistente de eventos de dividendo por ticker.
    Cada linha = 1 pagamento de provento (real ou projetado).
    Merge de BRAPI (paymentDate, rate, type) + yFinance (ex-date).
    """
    __tablename__ = "dividend_events"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Datas do evento
    ex_date = Column(DateTime, nullable=True)        # Data-ex (yFinance)
    payment_date = Column(DateTime, nullable=True)    # Data de pagamento (BRAPI)

    # Valores
    rate = Column(Float, nullable=False)              # Valor por cota (R$)
    tipo_provento = Column(String(30), default="DIVIDENDO")  # DIVIDENDO | JCP | RENDIMENTO

    # Metadados de merge
    source = Column(String(20), default="brapi")      # brapi | yfinance | merged
    confidence = Column(Float, default=1.0)            # 1.0 = match exato, 0.5 = apenas 1 fonte

    # Evita duplicatas por ticker + ex_date + payment_date + rate
    __table_args__ = (
        UniqueConstraint("ticker", "ex_date", "payment_date", "rate", name="uq_dividend_event"),
    )

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from app.models.base import Base


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Ativo
    ticker = Column(String(20), nullable=False, index=True)
    nome = Column(String(100), nullable=True)
    setor = Column(String(30), nullable=True)
    score = Column(Float, default=0.0)
    source_motor = Column(String(20), default="alpha")  # alpha | momentum | dividendos

    # Trigger de entrada
    trigger_tipo = Column(String(20), nullable=True)     # PRECO | BALANCO | MACRO | MOMENTUM
    trigger_valor = Column(Float, nullable=True)          # preço-alvo (se tipo PRECO)
    trigger_descricao = Column(Text, nullable=True)       # descrição do trigger

    # Dados extras (JSON-like armazenado como texto)
    pilares_json = Column(Text, nullable=True)            # breakdown de pilares

    # Status
    ativa = Column(Boolean, default=True)
    motivo_remocao = Column(Text, nullable=True)

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, JSON
from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Perfil do onboarding
    patrimonio_total = Column(Float, nullable=True)       # R$
    objetivo_tipo = Column(String(50), nullable=True)     # valor_alvo | percentual | renda | livre
    objetivo_valor = Column(Float, nullable=True)          # R$ ou %
    objetivo_prazo = Column(String(20), nullable=True)    # 3, 5, 10, +10 anos

    # Respostas do questionário (armazenadas como JSON)
    onboarding_respostas = Column(JSON, nullable=True)
    onboarding_score = Column(Integer, nullable=True)     # 0-15
    onboarding_completo = Column(Boolean, default=False)

    # Estratégia definida
    estrategia = Column(String(20), nullable=True)        # CORE | ALPHA
    estrategia_resumo = Column(Text, nullable=True)       # Texto gerado pela IA

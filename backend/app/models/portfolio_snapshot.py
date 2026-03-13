"""Snapshot diário de patrimônio para gráfico de evolução Carteira vs CDI."""
from datetime import date as _date
from sqlalchemy import Column, Integer, Float, Date, ForeignKey, UniqueConstraint
from app.models.base import Base


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False)
    date = Column(Date, nullable=False)
    patrimonio = Column(Float, nullable=False)       # valor de mercado total (R$)
    custo_total = Column(Float, nullable=False)       # soma valor_investido (R$)
    cdi_acumulado = Column(Float, default=0.0)        # CDI acumulado desde 1º snapshot (%)

    __table_args__ = (
        UniqueConstraint("portfolio_id", "date", name="uq_snapshot_portfolio_date"),
    )

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from app.models.base import Base


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    portfolio_id = Column(Integer, ForeignKey("portfolios.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Identificação
    ticker = Column(String(20), nullable=False, index=True)
    nome = Column(String(100), nullable=True)
    tipo = Column(String(20), nullable=False)  # ACAO | FII | ETF | BDR | RF | OPCAO | CAIXA
    modulo = Column(String(20), nullable=True)  # momentum | wheel | etfs | fiis | renda_fixa | alpha | teses | caixa

    # Módulo Teses
    tese = Column(Text, nullable=True)                    # tese de investimento escrita pelo usuário
    mercado = Column(String(10), nullable=True)           # B3 | BDR | NYSE | NASDAQ | AMEX
    moeda = Column(String(5), default="BRL")              # BRL | USD
    preco_medio_usd = Column(Float, nullable=True)        # preço médio em USD (para posições USD)
    valor_investido_usd = Column(Float, nullable=True)    # valor investido em USD

    # Posição
    quantidade = Column(Float, default=0.0)
    preco_medio = Column(Float, default=0.0)
    valor_investido = Column(Float, default=0.0)

    # Preço atual (atualizado em tempo real via BRAPI)
    preco_atual = Column(Float, nullable=True)
    valor_atual = Column(Float, nullable=True)
    pl_reais = Column(Float, nullable=True)      # P&L em R$
    pl_percentual = Column(Float, nullable=True)  # P&L em %
    cotacao_atualizada_em = Column(DateTime, nullable=True)

    # Gestão de risco (para momentum e alpha)
    stop_loss = Column(Float, nullable=True)
    alvo_1 = Column(Float, nullable=True)
    alvo_2 = Column(Float, nullable=True)
    trailing_stop = Column(Float, nullable=True)
    apex_score = Column(Integer, nullable=True)   # Score APEX 0-100 no momento da entrada

    # Opções Wheel
    strike = Column(Float, nullable=True)
    vencimento = Column(DateTime, nullable=True)
    tipo_opcao = Column(String(10), nullable=True)  # PUT | CALL
    premio_recebido = Column(Float, nullable=True)
    delta = Column(Float, nullable=True)

    # Renda Fixa
    indexador = Column(String(20), nullable=True)  # CDI | IPCA | PRE
    taxa = Column(Float, nullable=True)
    duration = Column(Float, nullable=True)

    # Justificativa do CEO na entrada (memória para rebalanceamento)
    justificativa_entrada = Column(Text, nullable=True)

    # Status
    ativa = Column(Boolean, default=True)
    data_abertura = Column(DateTime, nullable=True)   # data da primeira compra / entrada
    data_entrada = Column(DateTime, default=datetime.utcnow)
    data_saida = Column(DateTime, nullable=True)
    motivo_saida = Column(Text, nullable=True)

"""Base SQLAlchemy para SQLite — sem PostgreSQL por enquanto"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import DATABASE_URL

# SQLite: connect_args necessário para uso com threads no FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# WAL mode — evita "database is locked" em escritas simultâneas (ex: duas abas)
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Dependency do FastAPI — abre e fecha sessão automaticamente."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    """Cria todas as tabelas no banco (SQLite cria o arquivo se não existir)."""
    Base.metadata.create_all(bind=engine)


def migrate_db():
    """Aplica migrações incrementais via ALTER TABLE (SQLite não tem IF NOT EXISTS)."""
    _migrations = [
        # Módulo Teses — colunas na tabela positions
        "ALTER TABLE positions ADD COLUMN tese TEXT",
        "ALTER TABLE positions ADD COLUMN mercado VARCHAR(10)",
        "ALTER TABLE positions ADD COLUMN moeda VARCHAR(5) DEFAULT 'BRL'",
        "ALTER TABLE positions ADD COLUMN preco_medio_usd FLOAT",
        "ALTER TABLE positions ADD COLUMN valor_investido_usd FLOAT",
        # alvo_teses — tabela portfolios
        "ALTER TABLE portfolios ADD COLUMN alvo_teses FLOAT DEFAULT 0.0",
        # Multi-portfolio — tipo e nome do portfolio
        "ALTER TABLE portfolios ADD COLUMN tipo VARCHAR(20) DEFAULT 'real'",
        "ALTER TABLE portfolios ADD COLUMN nome VARCHAR(100) DEFAULT 'Carteira Real'",
        # Aportes regulares declarados no onboarding
        "ALTER TABLE users ADD COLUMN aporte_mensal FLOAT",
        # Multi-portfolio — portfolio ativo no usuário
        "ALTER TABLE users ADD COLUMN portfolio_ativo_id INTEGER",
        # Posição — data abertura
        "ALTER TABLE positions ADD COLUMN data_abertura TIMESTAMP",
        # Portfolio — capital declarado (carteira real)
        "ALTER TABLE portfolios ADD COLUMN capital_declarado FLOAT",
        # Índice de performance — queries de posições por portfolio_id
        "CREATE INDEX IF NOT EXISTS idx_positions_portfolio_id ON positions (portfolio_id)",
        # Plano estratégico do Estrategista (cerebro/plano.py)
        "ALTER TABLE users ADD COLUMN plano_estrategico JSON",
        # Descrição livre do objetivo (texto do investidor)
        "ALTER TABLE users ADD COLUMN objetivo_descricao TEXT",
        # TeseInvestimento — tabela criada via create_tables(), migrações para colunas futuras aqui
        # TradeJournal — tabela criada via create_tables(), migrações para colunas futuras aqui
        # Análise IA persistida
        "ALTER TABLE positions ADD COLUMN analise_ia TEXT",
        "ALTER TABLE positions ADD COLUMN analise_ia_at TIMESTAMP",
        # Phase 5: Hold classification + Watchlist
        "ALTER TABLE positions ADD COLUMN classificacao VARCHAR(10) DEFAULT 'TRADE'",
        # Transaction system improvements — destino da venda e valor líquido
        "ALTER TABLE transacoes ADD COLUMN destino VARCHAR(10)",
        "ALTER TABLE transacoes ADD COLUMN valor_liquido FLOAT",
        # Import B3 — corretora no portfolio, source/external_id na position
        "ALTER TABLE portfolios ADD COLUMN corretora VARCHAR(100)",
        "ALTER TABLE positions ADD COLUMN source VARCHAR(30) DEFAULT 'manual'",
        "ALTER TABLE positions ADD COLUMN external_id VARCHAR(100)",
    ]
    with engine.connect() as conn:
        for sql in _migrations:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
            except Exception:
                # Coluna já existe — ignora
                pass

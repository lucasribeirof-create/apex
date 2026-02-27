"""Base SQLAlchemy para SQLite — sem PostgreSQL por enquanto"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import DATABASE_URL

# SQLite: connect_args necessário para uso com threads no FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
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
    ]
    with engine.connect() as conn:
        for sql in _migrations:
            try:
                conn.execute(__import__("sqlalchemy").text(sql))
                conn.commit()
            except Exception:
                # Coluna já existe — ignora
                pass

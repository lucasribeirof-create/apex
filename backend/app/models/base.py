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

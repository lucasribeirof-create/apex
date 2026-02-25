"""
Configurações do APEX Manager
Fase atual: SQLite local (Windows) — sem Docker, sem PostgreSQL, sem Redis
Migração futura: trocar DATABASE_URL para PostgreSQL no .env
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── Diretórios ───────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # raiz do projeto
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# ─── Banco de dados ───────────────────────────────────────────────────────────
# Fase atual: SQLite — arquivo local na pasta /data
# Migração futura: definir DATABASE_URL=postgresql://... no .env
_db_url = os.getenv("DATABASE_URL", "").strip()
DATABASE_URL = _db_url if _db_url else f"sqlite:///{DATA_DIR}/apex.db"

# ─── Anthropic (Claude) ───────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")

# ─── BRAPI (cotações brasileiras) ─────────────────────────────────────────────
BRAPI_TOKEN = os.getenv("BRAPI_TOKEN", "")
BRAPI_BASE_URL = "https://brapi.dev/api"

# ─── Cache em memória ──────────────────────────────────────────────────────────
# Fase atual: dicionário Python com TTL manual (sem Redis)
# Migração futura: substituir por Redis com CACHE_URL=redis://...
CACHE_TTL_QUOTES = 60        # segundos — cotações em tempo real
CACHE_TTL_INDICATORS = 300   # segundos — indicadores técnicos (MM, ATR)
CACHE_TTL_MACRO = 600        # segundos — dados macro (Selic, câmbio)

# ─── App ──────────────────────────────────────────────────────────────────────
APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "true").lower() == "true"

# ─── Morning Briefing ─────────────────────────────────────────────────────────
# Fase atual: APScheduler — sem Celery/Redis
BRIEFING_HOUR = int(os.getenv("BRIEFING_HOUR", "8"))
BRIEFING_MINUTE = int(os.getenv("BRIEFING_MINUTE", "45"))

"""
APEX Manager — Backend FastAPI
Fase atual: SQLite local + APScheduler (sem Docker, sem PostgreSQL, sem Redis)
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import APP_HOST, APP_PORT, DEBUG, BRIEFING_HOUR, BRIEFING_MINUTE
from app.models import create_tables, migrate_db
from app.tasks import tarefa_morning_briefing
from app.api.routes import onboarding, dashboard, chat, briefing, portfolio, market, settings, scanner, teses, transacoes, watchlist, dividendos

# ─── Scheduler (APScheduler — substitui Celery/Redis nesta fase) ───────────────
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Executado na inicialização e no encerramento do servidor."""
    # Startup
    create_tables()
    migrate_db()
    print("[OK] Banco de dados SQLite inicializado: data/apex.db")

    # Agendar morning briefing (dias úteis, segunda a sexta)
    scheduler.add_job(
        tarefa_morning_briefing,
        CronTrigger(hour=BRIEFING_HOUR, minute=BRIEFING_MINUTE, day_of_week="mon-fri", timezone="America/Sao_Paulo"),
        id="morning_briefing",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[OK] Scheduler iniciado — briefing agendado para {BRIEFING_HOUR:02d}:{BRIEFING_MINUTE:02d} (seg-sex)")

    yield

    # Shutdown
    scheduler.shutdown()
    print("[--] Scheduler encerrado")


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="APEX Manager",
    description="Sistema de gestão ativa de portfólio com IA integrada",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — permite o frontend React acessar a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Rotas ────────────────────────────────────────────────────────────────────
app.include_router(settings.router)
app.include_router(onboarding.router)
app.include_router(dashboard.router)
app.include_router(chat.router)
app.include_router(briefing.router)
app.include_router(portfolio.router)
app.include_router(market.router)
app.include_router(scanner.router)
app.include_router(teses.router)
app.include_router(transacoes.router)
app.include_router(watchlist.router)
app.include_router(dividendos.router)

from app.api.routes import import_b3, pluggy
app.include_router(import_b3.router)
app.include_router(pluggy.router)


@app.get("/health")
def health():
    """Endpoint de saúde — confirma que o servidor está rodando."""
    return {
        "status": "ok",
        "app": "APEX Manager",
        "banco": "SQLite (local)",
        "cache": "memória",
        "scheduler": "APScheduler",
    }


# ─── Entrypoint ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=APP_HOST, port=APP_PORT, reload=DEBUG)

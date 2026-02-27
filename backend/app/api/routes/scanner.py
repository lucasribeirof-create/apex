"""Rota do Scanner APEX — varredura do universo de ativos com os 5 filtros."""
from typing import Optional
from fastapi import APIRouter, Query
from app.core.scanner import executar_scan

router = APIRouter(prefix="/scanner", tags=["scanner"])


@router.get("/scan")
async def scan(
    patrimonio: float = Query(
        default=100_000.0,
        description="Patrimônio total para cálculo de sizing (R$)",
    ),
    estrategia: str = Query(
        default="CORE",
        description="CORE (risco 1%/trade) ou ALPHA (risco 1.5%/trade)",
    ),
    tipos: Optional[str] = Query(
        default=None,
        description="Filtrar por tipos separados por vírgula: ACAO,ETF,FII (vazio = todos)",
    ),
    forcar: bool = Query(
        default=False,
        description="Forçar nova varredura ignorando cache de 4h",
    ),
):
    """
    Executa o Scanner APEX: varre ~80 ativos com os 5 filtros sequenciais,
    calcula o score 0-100 e retorna trades (≥75), monitor (50-74) e out (<50).
    Resultado cacheado por 4h — use forcar=true para refresh imediato.
    """
    tipos_list = [t.strip().upper() for t in tipos.split(",")] if tipos else None
    return await executar_scan(
        patrimonio=patrimonio,
        estrategia=estrategia.upper(),
        tipos=tipos_list,
        forcar_atualizacao=forcar,
    )

"""
Rotas Pluggy — configuração, Connect Widget e sincronização de investimentos.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.api.deps import get_db, get_user_id
from app.models import User, Portfolio, Position
from app.services.pluggy.client import (
    get_pluggy_credentials, save_pluggy_credentials, is_pluggy_configured,
    test_credentials, create_connect_token, get_item, get_investments,
    delete_item, save_connected_item, remove_connected_item, get_connected_items,
    map_investment_to_position, get_transactions, compute_pm_from_transactions,
)

router = APIRouter(prefix="/pluggy", tags=["pluggy"])


# ─── Models ────────────────────────────────────────────────────────────────────

class PluggyCredentials(BaseModel):
    client_id: str
    client_secret: str


class ItemCallback(BaseModel):
    item_id: str


# ─── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings")
def get_settings():
    """Retorna status de configuração do Pluggy."""
    cid, csec = get_pluggy_credentials()
    items = get_connected_items()
    return {
        "configured": is_pluggy_configured(),
        "client_id_hint": f"...{cid[-6:]}" if len(cid) > 6 else ("***" if cid else ""),
        "items": items,
    }


@router.post("/settings/test")
def test_pluggy(body: PluggyCredentials):
    """Testa credenciais do Pluggy sem salvar."""
    if not body.client_id.strip() or not body.client_secret.strip():
        raise HTTPException(400, "client_id e client_secret são obrigatórios")
    ok, msg = test_credentials(body.client_id.strip(), body.client_secret.strip())
    return {"ok": ok, "message": msg}


@router.post("/settings")
def save_settings(body: PluggyCredentials):
    """Salva credenciais do Pluggy."""
    if not body.client_id.strip() or not body.client_secret.strip():
        raise HTTPException(400, "client_id e client_secret são obrigatórios")
    ok, msg = test_credentials(body.client_id.strip(), body.client_secret.strip())
    if not ok:
        raise HTTPException(400, f"Credenciais inválidas: {msg}")
    save_pluggy_credentials(body.client_id.strip(), body.client_secret.strip())
    return {"ok": True, "message": "Credenciais salvas!"}


# ─── Connect Widget ───────────────────────────────────────────────────────────

@router.post("/connect-token")
def get_connect_token(item_id: Optional[str] = None):
    """Gera token para o Pluggy Connect Widget."""
    if not is_pluggy_configured():
        raise HTTPException(400, "Pluggy não configurado. Salve client_id e client_secret primeiro.")
    try:
        data = create_connect_token(item_id)
        return {"accessToken": data.get("accessToken")}
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar connect token: {str(e)}")


# ─── Item Callback ─────────────────────────────────────────────────────────────

@router.post("/item-connected")
def item_connected(body: ItemCallback):
    """Callback quando um item é conectado via Connect Widget. Salva o item."""
    if not is_pluggy_configured():
        raise HTTPException(400, "Pluggy não configurado")
    try:
        item = get_item(body.item_id)
        save_connected_item({
            "id": item["id"],
            "connector": item.get("connector", {}).get("name", "Desconhecido"),
            "connector_id": item.get("connectorId"),
            "status": item.get("status"),
            "connected_at": datetime.utcnow().isoformat(),
        })
        return {"ok": True, "item": item}
    except Exception as e:
        raise HTTPException(500, f"Erro ao registrar item: {str(e)}")


# ─── Sync Investments ─────────────────────────────────────────────────────────

@router.post("/sync/{item_id}")
def sync_investments(
    item_id: str,
    user_id: int = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Sincroniza investimentos de um item do Pluggy com o portfolio APEX."""
    if not user_id:
        raise HTTPException(400, "Header x-user-id obrigatório")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuário não encontrado")

    try:
        # Buscar item info para nome da corretora
        item = get_item(item_id)
        connector_name = item.get("connector", {}).get("name", "Pluggy")

        # Buscar investimentos
        investments = get_investments(item_id)

        # Buscar transações para calcular PM real
        try:
            transactions = get_transactions(item_id)
            pm_map = compute_pm_from_transactions(transactions)
        except Exception:
            transactions = []
            pm_map = {}

        # Buscar ou criar portfolio baseado no connector
        portfolio = db.query(Portfolio).filter(
            Portfolio.user_id == user.id,
            Portfolio.corretora == connector_name,
        ).first()

        if not portfolio:
            portfolio = Portfolio(
                user_id=user.id,
                nome=connector_name,
                tipo="real",
                corretora=connector_name,
            )
            db.add(portfolio)
            db.flush()

        # Mapear e upsert posições
        created = 0
        updated = 0
        skipped = 0

        for inv in investments:
            mapped = map_investment_to_position(inv)
            if not mapped or mapped["quantidade"] == 0:
                skipped += 1
                continue

            # Buscar posição existente
            existing = db.query(Position).filter(
                Position.portfolio_id == portfolio.id,
                Position.ticker == mapped["ticker"],
                Position.ativa == True,
            ).first()

            if existing:
                existing.quantidade = mapped["quantidade"]
                existing.preco_atual = mapped["preco_fechamento"]
                existing.valor_atual = mapped["valor_atualizado"]
                # Atualizar PM se temos dados de transações
                pm_real = pm_map.get(mapped["ticker"])
                if pm_real and pm_real > 0:
                    existing.preco_medio = pm_real
                    existing.valor_investido = pm_real * mapped["quantidade"]
                existing.updated_at = datetime.utcnow()
                existing.source = "pluggy"
                existing.external_id = mapped["external_id"]
                updated += 1
            else:
                # Usar PM real das transações se disponível
                pm_real = pm_map.get(mapped["ticker"])
                preco_medio = pm_real if pm_real and pm_real > 0 else mapped["preco_fechamento"]
                valor_investido = preco_medio * mapped["quantidade"]

                pos = Position(
                    portfolio_id=portfolio.id,
                    ticker=mapped["ticker"],
                    nome=mapped.get("nome", ""),
                    tipo=mapped["tipo"],
                    modulo=mapped.get("modulo", "alpha"),
                    mercado="B3",
                    moeda="BRL",
                    quantidade=mapped["quantidade"],
                    preco_medio=preco_medio,
                    valor_investido=valor_investido,
                    preco_atual=mapped["preco_fechamento"],
                    valor_atual=mapped["valor_atualizado"],
                    source="pluggy",
                    external_id=mapped["external_id"],
                    ativa=True,
                    data_entrada=datetime.utcnow(),
                )
                if mapped["tipo"] == "RF":
                    pos.indexador = mapped.get("indexador", "")
                    pos.taxa = mapped.get("taxa", 0)
                db.add(pos)
                created += 1

        db.commit()

        return {
            "ok": True,
            "portfolio": {"id": portfolio.id, "nome": portfolio.nome},
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "total": len(investments),
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Erro ao sincronizar: {str(e)}")


# ─── Disconnect ────────────────────────────────────────────────────────────────

@router.delete("/item/{item_id}")
def disconnect_item(item_id: str):
    """Desconecta e deleta um item do Pluggy."""
    try:
        delete_item(item_id)
        remove_connected_item(item_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"Erro ao desconectar: {str(e)}")


# ─── Preview (without saving) ─────────────────────────────────────────────────

@router.get("/preview/{item_id}")
def preview_investments(item_id: str):
    """Preview dos investimentos de um item sem importar."""
    try:
        item = get_item(item_id)
        investments = get_investments(item_id)
        connector_name = item.get("connector", {}).get("name", "Pluggy")

        # Tentar obter PM real das transações
        try:
            transactions = get_transactions(item_id)
            pm_map = compute_pm_from_transactions(transactions)
        except Exception:
            pm_map = {}

        positions = []
        for inv in investments:
            mapped = map_investment_to_position(inv)
            if mapped and mapped["quantidade"] > 0:
                pm_real = pm_map.get(mapped["ticker"])
                if pm_real and pm_real > 0:
                    mapped["preco_medio"] = pm_real
                    mapped["valor_investido"] = pm_real * mapped["quantidade"]
                    mapped["tem_pm_real"] = True
                else:
                    mapped["preco_medio"] = mapped["preco_fechamento"]
                    mapped["valor_investido"] = mapped["valor_atualizado"]
                    mapped["tem_pm_real"] = False
                positions.append(mapped)

        return {
            "connector": connector_name,
            "item_id": item_id,
            "positions": positions,
            "total": len(positions),
            "total_value": sum(p["valor_atualizado"] for p in positions),
        }
    except Exception as e:
        raise HTTPException(500, f"Erro ao buscar preview: {str(e)}")

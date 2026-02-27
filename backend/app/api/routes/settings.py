"""
Configurações de IA do APEX Manager.
GET  /settings/ai        → provedor ativo + todos configurados
POST /settings/ai        → salva chave de um provedor e ativa ele
PATCH /settings/ai/ativo → troca provedor ativo (sem redigitar chave)
DELETE /settings/ai      → limpa tudo
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.ai.client import (
    load_ai_settings, save_ai_settings, set_active_provider,
    is_ai_configured, load_all_providers, DEFAULT_MODELS, SETTINGS_FILE,
    testar_chave_api,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class AISettingsBody(BaseModel):
    provider: str   # "anthropic" | "openai" | "gemini"
    api_key: str
    model: str = ""


class SwitchProviderBody(BaseModel):
    provider: str


@router.get("/ai")
def get_ai_settings():
    """Retorna provedor ativo e todos os provedores já configurados."""
    s = load_ai_settings()
    provider = s.get("provider", "")
    key = s.get("api_key", "")
    return {
        "configured": is_ai_configured(),
        "provider": provider,
        "model": s.get("model") or DEFAULT_MODELS.get(provider, ""),
        "key_hint": f"...{key[-6:]}" if len(key) > 6 else ("***" if key else ""),
        "all_providers": load_all_providers(),
    }


@router.post("/ai/test")
async def test_ai_key(body: AISettingsBody):
    """Testa se uma chave de API é válida sem salvar. Retorna {ok, erro}."""
    if body.provider not in ("anthropic", "openai", "gemini", "groq", "grok"):
        raise HTTPException(status_code=400, detail="Provedor inválido")
    if not body.api_key.strip():
        raise HTTPException(status_code=400, detail="Chave vazia")
    result = await testar_chave_api(body.provider, body.api_key.strip())
    return result


@router.post("/ai/test-saved")
async def test_saved_ai_key():
    """Testa a chave do provedor ativo atualmente salvo. Não exige passar a chave."""
    s = load_ai_settings()
    provider = s.get("provider", "")
    api_key = s.get("api_key", "")
    if not provider or not api_key:
        raise HTTPException(status_code=400, detail="Nenhum provedor configurado")
    result = await testar_chave_api(provider, api_key)
    return {**result, "provider": provider, "model": s.get("model", "")}


@router.post("/ai")
async def set_ai_settings(body: AISettingsBody):
    """Valida a chave de API e salva se válida. Preserva chaves dos outros provedores."""
    if body.provider not in ("anthropic", "openai", "gemini", "groq", "grok"):
        raise HTTPException(status_code=400, detail="Provedor inválido. Use: anthropic, openai, gemini, groq ou grok")
    if not body.api_key.strip():
        raise HTTPException(status_code=400, detail="Chave de API não pode ser vazia")

    result = await testar_chave_api(body.provider, body.api_key.strip())
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["erro"])

    save_ai_settings(body.provider, body.api_key.strip(), body.model)
    return {"ok": True, "provider": body.provider}


@router.patch("/ai/ativo")
def switch_active_provider(body: SwitchProviderBody):
    """Troca o provedor ativo sem precisar redigitar a chave."""
    if body.provider not in ("anthropic", "openai", "gemini", "groq", "grok"):
        raise HTTPException(status_code=400, detail="Provedor inválido")
    ok = set_active_provider(body.provider)
    if not ok:
        raise HTTPException(status_code=400, detail="Provedor não configurado ainda. Adicione a chave primeiro.")
    return {"ok": True, "provider": body.provider}


@router.delete("/ai")
def clear_ai_settings():
    """Remove toda a configuração de IA."""
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()
    return {"ok": True}

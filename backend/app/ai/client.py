"""
Motor de IA do APEX Manager.
Suporta: Anthropic Claude · OpenAI GPT · Google Gemini · Groq (gratuito)
Provedor configurado via /settings/ai e salvo em data/ai_settings.json
"""
import json
import asyncio
from typing import AsyncIterator
from app.config import DATA_DIR

# ─── Configuração padrão por provedor ─────────────────────────────────────────
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "grok": "grok-2-1212",
}

# Base URL para Groq (compatível com OpenAI)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Base URL para Grok (xAI — compatível com OpenAI)
GROK_BASE_URL = "https://api.x.ai/v1"

SETTINGS_FILE = DATA_DIR / "ai_settings.json"


# ─── Persistência ─────────────────────────────────────────────────────────────
# Formato do ai_settings.json:
# {
#   "active": "gemini",
#   "providers": {
#     "gemini":    {"api_key": "AIzaSy...", "model": "gemini-2.0-flash"},
#     "anthropic": {"api_key": "sk-ant-...", "model": "claude-sonnet-4-5"}
#   }
# }

def _load_raw() -> dict:
    """Carrega o arquivo cru, migrando formato antigo se necessário."""
    if not SETTINGS_FILE.exists():
        # fallback legado: ANTHROPIC_API_KEY no .env
        from app.config import ANTHROPIC_API_KEY
        if ANTHROPIC_API_KEY and ANTHROPIC_API_KEY.startswith("sk-ant-"):
            return {"active": "anthropic", "providers": {
                "anthropic": {"api_key": ANTHROPIC_API_KEY, "model": ""}
            }}
        return {"active": "", "providers": {}}

    data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))

    # Migração: formato antigo tinha {provider, api_key, model} no topo
    if "providers" not in data and data.get("provider"):
        provider = data["provider"]
        data = {"active": provider, "providers": {
            provider: {"api_key": data.get("api_key", ""), "model": data.get("model", "")}
        }}
        _write_raw(data)

    return data


def _write_raw(data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_ai_settings() -> dict:
    """Retorna configuração do provedor ATIVO no formato {provider, api_key, model}."""
    raw = _load_raw()
    active = raw.get("active", "")
    pdata = raw.get("providers", {}).get(active, {})
    return {"provider": active, "api_key": pdata.get("api_key", ""), "model": pdata.get("model", "")}


def load_all_providers() -> dict:
    """Retorna todos os provedores configurados com hint da chave."""
    raw = _load_raw()
    result = {}
    for pid, pdata in raw.get("providers", {}).items():
        key = pdata.get("api_key", "")
        result[pid] = {
            "configured": bool(key),
            "model": pdata.get("model") or DEFAULT_MODELS.get(pid, ""),
            "key_hint": f"...{key[-6:]}" if len(key) > 6 else "",
        }
    return result


def save_ai_settings(provider: str, api_key: str, model: str = "") -> None:
    """Salva chave do provedor e define como ativo. Preserva chaves dos outros."""
    raw = _load_raw()
    if "providers" not in raw:
        raw["providers"] = {}
    raw["providers"][provider] = {"api_key": api_key, "model": model or DEFAULT_MODELS.get(provider, "")}
    raw["active"] = provider
    _write_raw(raw)


def set_active_provider(provider: str) -> bool:
    """Troca o provedor ativo (só se já tiver chave salva). Retorna True se ok."""
    raw = _load_raw()
    if provider not in raw.get("providers", {}):
        return False
    raw["active"] = provider
    _write_raw(raw)
    return True


def is_ai_configured() -> bool:
    s = load_ai_settings()
    return bool(s.get("provider") and s.get("api_key"))


# ─── Interface pública ────────────────────────────────────────────────────────

async def chat(system: str, messages: list[dict], max_tokens: int = 2048) -> str:
    """Chamada simples — retorna texto completo."""
    s = load_ai_settings()
    provider = s.get("provider", "anthropic")
    api_key = s.get("api_key", "")
    model = s.get("model") or DEFAULT_MODELS.get(provider, "")

    try:
        if provider == "anthropic":
            return await _chat_anthropic(api_key, model, system, messages, max_tokens)
        elif provider == "openai":
            return await _chat_openai(api_key, model, system, messages, max_tokens)
        elif provider == "gemini":
            return await _chat_gemini(api_key, model, system, messages, max_tokens)
        elif provider == "groq":
            return await _chat_groq(api_key, model, system, messages, max_tokens)
        elif provider == "grok":
            return await _chat_grok_xai(api_key, model, system, messages, max_tokens)
        raise ValueError(f"Provedor de IA não configurado: {provider}")
    except Exception as e:
        msg = str(e)
        if "credit balance is too low" in msg.lower():
            raise RuntimeError(f"Saldo de créditos insuficiente na conta Anthropic. Adicione créditos em console.anthropic.com → Billing.")
        if "401" in msg or "authentication" in msg.lower():
            raise RuntimeError(f"Chave de API inválida ({provider}). Vá em Configurações → Trocar IA e atualize sua chave.")
        if "429" in msg:
            if "limit: 0" in msg or "free_tier" in msg.lower():
                raise RuntimeError(f"Cota gratuita do {provider} esgotada. Habilite billing no painel do provedor ou troque de IA em Configurações.")
            raise RuntimeError(f"Limite de requisições da IA atingido. Aguarde um momento e tente novamente.")
        raise


async def chat_stream(
    system: str, messages: list[dict], max_tokens: int = 2048
) -> AsyncIterator[str]:
    """Streaming — usado no chat e no efeito typewriter do onboarding."""
    s = load_ai_settings()
    provider = s.get("provider", "anthropic")
    api_key = s.get("api_key", "")
    model = s.get("model") or DEFAULT_MODELS.get(provider, "")

    try:
        if provider == "anthropic":
            async for chunk in _stream_anthropic(api_key, model, system, messages, max_tokens):
                yield chunk
        elif provider == "openai":
            async for chunk in _stream_openai(api_key, model, system, messages, max_tokens):
                yield chunk
        elif provider == "gemini":
            async for chunk in _stream_gemini(api_key, model, system, messages, max_tokens):
                yield chunk
        elif provider == "groq":
            async for chunk in _stream_groq(api_key, model, system, messages, max_tokens):
                yield chunk
        elif provider == "grok":
            async for chunk in _stream_grok_xai(api_key, model, system, messages, max_tokens):
                yield chunk
    except Exception as e:
        msg = str(e)
        if "401" in msg or "authentication" in msg.lower():
            yield f"\n\n⚠️ Chave de API inválida ({provider}). Vá em Configurações → Trocar IA e atualize sua chave."
        elif "403" in msg or "permission" in msg.lower() or "credits or licenses" in msg.lower():
            if "credits" in msg.lower() or "licenses" in msg.lower():
                yield f"\n\n⚠️ Sua conta xAI ainda não tem créditos. Acesse https://console.x.ai para adicionar créditos ou escolha outro provedor em Configurações → Trocar IA."
            else:
                yield f"\n\n⚠️ Acesso negado pela API do {provider}. Verifique as permissões da chave em Configurações → Trocar IA."
        elif "429" in msg and ("limit: 0" in msg or "free_tier" in msg.lower()):
            yield f"\n\n⚠️ Cota gratuita do {provider} esgotada. Habilite billing no painel do provedor ou troque de IA em Configurações."
        elif "429" in msg:
            yield "\n\n⚠️ Limite de requisições atingido. Aguarde um momento e tente novamente."
        else:
            yield f"\n\n⚠️ Erro na IA ({provider}): {msg[:150]}"


# ─── Anthropic ────────────────────────────────────────────────────────────────

async def _chat_anthropic(api_key, model, system, messages, max_tokens) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=api_key)
    resp = await client.messages.create(
        model=model, max_tokens=max_tokens, system=system, messages=messages
    )
    return resp.content[0].text


async def _stream_anthropic(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=api_key)
    async with client.messages.stream(
        model=model, max_tokens=max_tokens, system=system, messages=messages
    ) as stream:
        async for text in stream.text_stream:
            yield text


# ─── OpenAI ───────────────────────────────────────────────────────────────────

async def _chat_openai(api_key, model, system, messages, max_tokens) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)
    full = [{"role": "system", "content": system}] + messages
    resp = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=full)
    return resp.choices[0].message.content


async def _stream_openai(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)
    full = [{"role": "system", "content": system}] + messages
    stream = await client.chat.completions.create(
        model=model, max_tokens=max_tokens, messages=full, stream=True
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ─── Groq ────────────────────────────────────────────────────────────────────

async def _chat_groq(api_key, model, system, messages, max_tokens) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
    full = [{"role": "system", "content": system}] + messages
    resp = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=full)
    return resp.choices[0].message.content


async def _stream_groq(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
    full = [{"role": "system", "content": system}] + messages
    stream = await client.chat.completions.create(
        model=model, max_tokens=max_tokens, messages=full, stream=True
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ─── Grok (xAI) ─────────────────────────────────────────────────────────────

async def _chat_grok_xai(api_key, model, system, messages, max_tokens) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=GROK_BASE_URL)
    full = [{"role": "system", "content": system}] + messages
    resp = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=full)
    return resp.choices[0].message.content


async def _stream_grok_xai(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=GROK_BASE_URL)
    full = [{"role": "system", "content": system}] + messages
    stream = await client.chat.completions.create(
        model=model, max_tokens=max_tokens, messages=full, stream=True
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ─── Gemini ───────────────────────────────────────────────────────────────────

def _gemini_contents(messages: list[dict]):
    """Converte messages para o formato google.genai.types.Content."""
    from google.genai import types
    return [
        types.Content(
            role="user" if m["role"] == "user" else "model",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]


async def _chat_gemini(api_key, model, system, messages, max_tokens) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
    )
    # Gemini 2.5+ são "thinking models" — tokens de raciocínio consomem
    # o budget de max_output_tokens, truncando a resposta real.
    # Desabilitar thinking garante que todo o budget vai para a saída.
    if "2.5" in model:
        config.thinking_config = types.ThinkingConfig(thinking_budget=0)
    resp = await client.aio.models.generate_content(
        model=model, contents=_gemini_contents(messages), config=config
    )
    return resp.text or ""


async def _stream_gemini(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    """Gemini: streaming assíncrono nativo via google-genai."""
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
    )
    # Gemini 2.5+ são "thinking models" — desabilitar thinking para
    # evitar que tokens de raciocínio consumam o budget de saída.
    if "2.5" in model:
        config.thinking_config = types.ThinkingConfig(thinking_budget=0)
    # generate_content_stream é uma coroutine — precisa ser awaited antes de iterar
    stream = await client.aio.models.generate_content_stream(
        model=model, contents=_gemini_contents(messages), config=config
    )
    async for chunk in stream:
        if chunk.text:
            yield chunk.text


# ─── Validação de chave ───────────────────────────────────────────────────────

async def testar_chave_api(provider: str, api_key: str) -> dict:
    """
    Testa se uma chave de API é válida fazendo uma chamada mínima.
    Retorna {"ok": True} ou {"ok": False, "erro": "mensagem"}.
    """
    model = DEFAULT_MODELS.get(provider, "")
    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            await client.messages.create(
                model=model, max_tokens=10, system="test",
                messages=[{"role": "user", "content": "hi"}],
            )

        elif provider == "openai":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key)
            await client.chat.completions.create(
                model=model, max_tokens=10,
                messages=[{"role": "user", "content": "hi"}],
            )

        elif provider == "gemini":
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=api_key)
            config = types.GenerateContentConfig(max_output_tokens=10)
            await client.aio.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=[types.Part(text="hi")])],
                config=config,
            )

        elif provider == "groq":
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
            await client.chat.completions.create(
                model=model, max_tokens=10,
                messages=[{"role": "user", "content": "hi"}],
            )

        elif provider == "grok":
            # xAI pode retornar 403 para certos modelos dependendo do plano.
            # Validamos o formato da chave em vez de fazer chamada live.
            if not api_key.startswith("xai-"):
                return {"ok": False, "erro": "Chave Grok inválida. Deve começar com xai-"}
            return {"ok": True}

        else:
            return {"ok": False, "erro": f"Provedor desconhecido: {provider}"}

        return {"ok": True}

    except Exception as e:
        msg = str(e)
        # Extrair mensagem mais legível
        if "credit balance is too low" in msg.lower() or "credit" in msg.lower() and "low" in msg.lower():
            return {"ok": False, "erro": "Saldo de créditos insuficiente. Adicione créditos em console.anthropic.com → Billing."}
        if "401" in msg or "authentication" in msg.lower() or ("invalid" in msg.lower() and "key" in msg.lower()):
            return {"ok": False, "erro": "Chave inválida ou sem permissão. Verifique se copiou corretamente."}
        if "403" in msg:
            return {"ok": False, "erro": "Acesso negado. Verifique se a chave tem permissões suficientes."}
        if "429" in msg:
            if "limit: 0" in msg or "free_tier" in msg.lower() or "resource_exhausted" in msg.lower() or "RESOURCE_EXHAUSTED" in msg:
                return {"ok": False, "erro": "Cota Gemini esgotada ou zero. O projeto Google Cloud precisa ter faturamento configurado para liberar a cota gratuita. Alternativa mais simples: use o Groq (100% gratuito, sem cartão)."}

            return {"ok": False, "erro": "Limite de requisições atingido. Aguarde alguns segundos e tente novamente."}
        if "quota" in msg.lower():
            return {"ok": False, "erro": "Cota da API esgotada. Verifique seu plano no painel do provedor."}
        return {"ok": False, "erro": f"Erro ao validar: {msg[:120]}"}


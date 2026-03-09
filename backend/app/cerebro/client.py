"""
Motor de IA do APEX Manager.
Suporta: Anthropic Claude · OpenAI GPT · Google Gemini · Groq (gratuito)
Provedor configurado via /settings/ai e salvo em data/ai_settings.json
"""
import json
import asyncio
import time
from typing import AsyncIterator
from app.config import DATA_DIR

# ─── Configuração padrão por provedor ─────────────────────────────────────────
DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-5",
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

# ─── Cache de settings e clientes SDK ──────────────────────────────────────────
# Evita re-ler disco e recriar clientes a cada chamada
_settings_cache: dict = {"data": None, "ts": 0.0}
_SETTINGS_TTL = 60.0  # segundos

_client_cache: dict[str, object] = {}  # chave: "provider:key_hash" → client SDK


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
    """Retorna configuração do provedor ATIVO no formato {provider, api_key, model}. Cacheado por 60s."""
    now = time.monotonic()
    if _settings_cache["data"] is not None and (now - _settings_cache["ts"]) < _SETTINGS_TTL:
        return _settings_cache["data"]

    raw = _load_raw()
    active = raw.get("active", "")
    pdata = raw.get("providers", {}).get(active, {})
    result = {"provider": active, "api_key": pdata.get("api_key", ""), "model": pdata.get("model", "")}
    _settings_cache["data"] = result
    _settings_cache["ts"] = now
    return result


def _invalidate_settings_cache() -> None:
    """Limpa cache de settings (chamar após save_ai_settings/set_active_provider)."""
    _settings_cache["data"] = None
    _settings_cache["ts"] = 0.0
    _client_cache.clear()  # clientes antigos podem ter chave/provider diferente


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
    _invalidate_settings_cache()


def set_active_provider(provider: str) -> bool:
    """Troca o provedor ativo (só se já tiver chave salva). Retorna True se ok."""
    raw = _load_raw()
    if provider not in raw.get("providers", {}):
        return False
    raw["active"] = provider
    _write_raw(raw)
    _invalidate_settings_cache()
    return True


def is_ai_configured() -> bool:
    s = load_ai_settings()
    return bool(s.get("provider") and s.get("api_key"))


def _get_client(provider: str, api_key: str, base_url: str | None = None):
    """Retorna cliente SDK cacheado por provider+api_key (evita recriar a cada chamada)."""
    cache_key = f"{provider}:{hash(api_key)}"
    if cache_key in _client_cache:
        return _client_cache[cache_key]

    if provider == "anthropic":
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    elif provider == "gemini":
        from google import genai
        client = genai.Client(api_key=api_key)
    elif provider in ("openai", "groq", "grok"):
        from openai import AsyncOpenAI
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = AsyncOpenAI(**kwargs)
    else:
        return None

    _client_cache[cache_key] = client
    return client


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
    system: str, messages: list[dict], max_tokens: int = 2048,
    track_usage: bool = False,
) -> AsyncIterator[str]:
    """Streaming — usado no chat e no efeito typewriter do onboarding.
    Se track_usage=True, inclui tag <!-- APEX_USAGE:... --> no final do stream."""
    s = load_ai_settings()
    provider = s.get("provider", "anthropic")
    api_key = s.get("api_key", "")
    model = s.get("model") or DEFAULT_MODELS.get(provider, "")

    try:
        if provider == "anthropic":
            gen = _stream_anthropic(api_key, model, system, messages, max_tokens)
        elif provider == "openai":
            gen = _stream_openai(api_key, model, system, messages, max_tokens)
        elif provider == "gemini":
            gen = _stream_gemini(api_key, model, system, messages, max_tokens)
        elif provider == "groq":
            gen = _stream_groq(api_key, model, system, messages, max_tokens)
        elif provider == "grok":
            gen = _stream_grok_xai(api_key, model, system, messages, max_tokens)
        else:
            yield f"\n\n⚠️ Provedor de IA não configurado: {provider}. Vá em Configurações → Motor de IA."
            return

        if track_usage:
            async for chunk in gen:
                yield chunk
        else:
            # Buffer one chunk behind to strip usage tag from last chunk
            prev = None
            async for chunk in gen:
                if prev is not None:
                    yield prev
                prev = chunk
            if prev is not None:
                tag_idx = prev.find("\n<!-- APEX_USAGE:")
                yield prev[:tag_idx] if tag_idx >= 0 else prev
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


# ─── Custo por provedor (USD por 1M tokens) ─────────────────────────────────
_PRICING: dict[str, tuple[float, float]] = {
    # (input_per_1M, output_per_1M)
    "groq":      (0.0, 0.0),
    "gemini":    (0.0, 0.0),
    "anthropic": (3.0, 15.0),
    "openai":    (0.15, 0.60),
    "grok":      (2.0, 10.0),
}

# ─── Limites e info por provedor ──────────────────────────────────────────────
_PROVIDER_INFO: dict[str, dict] = {
    "groq": {
        "tier": "free",
        "req_min": 30,
        "req_day": 14400,
        "tokens_min": 20000,
        "context_window": 128000,
        "nota": "Llama 3.3 70B · API gratuita com limites generosos",
    },
    "gemini": {
        "tier": "free",
        "req_min": 15,
        "req_day": 1500,
        "tokens_min": 1000000,
        "context_window": 1048576,
        "nota": "Gemini 2.0 Flash · API gratuita do Google",
    },
    "anthropic": {
        "tier": "paid",
        "req_min": 1000,
        "req_day": None,
        "tokens_min": 80000,
        "context_window": 200000,
        "nota": "Claude Sonnet 4.5 · $3/M input, $15/M output",
    },
    "openai": {
        "tier": "paid",
        "req_min": 500,
        "req_day": None,
        "tokens_min": 200000,
        "context_window": 128000,
        "nota": "GPT-4o Mini · $0.15/M input, $0.60/M output",
    },
    "grok": {
        "tier": "paid",
        "req_min": 60,
        "req_day": None,
        "tokens_min": 100000,
        "context_window": 131072,
        "nota": "Grok 2 · $2/M input, $10/M output",
    },
}


def get_provider_limits(provider: str) -> dict:
    """Retorna info de limites/preço de um provedor para o frontend."""
    info = _PROVIDER_INFO.get(provider, {})
    inp, out = _PRICING.get(provider, (0.0, 0.0))
    return {
        "tier": info.get("tier", "unknown"),
        "req_min": info.get("req_min"),
        "req_day": info.get("req_day"),
        "tokens_min": info.get("tokens_min"),
        "context_window": info.get("context_window"),
        "pricing_input": inp,
        "pricing_output": out,
        "nota": info.get("nota", ""),
    }


def _calc_cost(provider: str, input_tokens: int, output_tokens: int) -> float:
    inp, out = _PRICING.get(provider, (0.0, 0.0))
    return round(input_tokens * inp / 1_000_000 + output_tokens * out / 1_000_000, 6)


def _estimate_tokens(text: str) -> int:
    """Estimativa rápida: ~4 chars por token (funciona razoavelmente para PT-BR/EN)."""
    return max(1, len(text) // 4)


def _usage_tag(provider: str, model: str, input_tokens: int, output_tokens: int) -> str:
    cost = _calc_cost(provider, input_tokens, output_tokens)
    payload = {"in": input_tokens, "out": output_tokens, "cost": cost, "provider": provider, "model": model}
    return f"\n<!-- APEX_USAGE:{json.dumps(payload)} -->"


# ─── Anthropic ────────────────────────────────────────────────────────────────

async def _chat_anthropic(api_key, model, system, messages, max_tokens) -> str:
    client = _get_client("anthropic", api_key)
    resp = await client.messages.create(
        model=model, max_tokens=max_tokens, system=system, messages=messages
    )
    return resp.content[0].text


async def _stream_anthropic(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    client = _get_client("anthropic", api_key)
    output_text = ""
    usage_info = None
    async with client.messages.stream(
        model=model, max_tokens=max_tokens, system=system, messages=messages
    ) as stream:
        async for text in stream.text_stream:
            output_text += text
            yield text
        try:
            msg = stream.get_final_message()
            if msg and hasattr(msg, 'usage') and msg.usage:
                usage_info = (msg.usage.input_tokens, msg.usage.output_tokens)
        except Exception:
            pass
    # Yield fora do async with para evitar problemas de context manager + generator
    if usage_info:
        yield _usage_tag("anthropic", model, usage_info[0], usage_info[1])
    else:
        inp_est = _estimate_tokens(system + " ".join(m["content"] for m in messages))
        out_est = _estimate_tokens(output_text)
        yield _usage_tag("anthropic", model, inp_est, out_est)


# ─── OpenAI ───────────────────────────────────────────────────────────────────

async def _chat_openai(api_key, model, system, messages, max_tokens) -> str:
    client = _get_client("openai", api_key)
    full = [{"role": "system", "content": system}] + messages
    resp = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=full)
    return resp.choices[0].message.content


async def _stream_openai(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    client = _get_client("openai", api_key)
    full = [{"role": "system", "content": system}] + messages
    try:
        stream = await client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=full, stream=True,
            stream_options={"include_usage": True},
        )
    except Exception:
        stream = await client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=full, stream=True,
        )
    usage = None
    output_text = ""
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            delta = chunk.choices[0].delta.content
            output_text += delta
            yield delta
        if hasattr(chunk, 'usage') and chunk.usage:
            usage = (getattr(chunk.usage, 'prompt_tokens', 0) or 0,
                     getattr(chunk.usage, 'completion_tokens', 0) or 0)
    if usage and (usage[0] or usage[1]):
        yield _usage_tag("openai", model, usage[0], usage[1])
    else:
        inp_est = _estimate_tokens(" ".join(m["content"] for m in full))
        out_est = _estimate_tokens(output_text)
        yield _usage_tag("openai", model, inp_est, out_est)


# ─── Groq ────────────────────────────────────────────────────────────────────

async def _chat_groq(api_key, model, system, messages, max_tokens) -> str:
    client = _get_client("groq", api_key, GROQ_BASE_URL)
    full = [{"role": "system", "content": system}] + messages
    resp = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=full)
    return resp.choices[0].message.content


async def _stream_groq(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    client = _get_client("groq", api_key, GROQ_BASE_URL)
    full = [{"role": "system", "content": system}] + messages
    # Groq suporta stream_options mas pode falhar em versões antigas
    try:
        stream = await client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=full, stream=True,
            stream_options={"include_usage": True},
        )
    except Exception:
        stream = await client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=full, stream=True,
        )
    usage = None
    output_text = ""
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            delta = chunk.choices[0].delta.content
            output_text += delta
            yield delta
        if hasattr(chunk, 'usage') and chunk.usage:
            usage = (getattr(chunk.usage, 'prompt_tokens', 0) or 0,
                     getattr(chunk.usage, 'completion_tokens', 0) or 0)
    if usage and (usage[0] or usage[1]):
        yield _usage_tag("groq", model, usage[0], usage[1])
    else:
        # Fallback: estima tokens pelo texto
        inp_est = _estimate_tokens(" ".join(m["content"] for m in full))
        out_est = _estimate_tokens(output_text)
        yield _usage_tag("groq", model, inp_est, out_est)


# ─── Grok (xAI) ─────────────────────────────────────────────────────────────

async def _chat_grok_xai(api_key, model, system, messages, max_tokens) -> str:
    client = _get_client("grok", api_key, GROK_BASE_URL)
    full = [{"role": "system", "content": system}] + messages
    resp = await client.chat.completions.create(model=model, max_tokens=max_tokens, messages=full)
    return resp.choices[0].message.content


async def _stream_grok_xai(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    client = _get_client("grok", api_key, GROK_BASE_URL)
    full = [{"role": "system", "content": system}] + messages
    try:
        stream = await client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=full, stream=True,
            stream_options={"include_usage": True},
        )
    except Exception:
        stream = await client.chat.completions.create(
            model=model, max_tokens=max_tokens, messages=full, stream=True,
        )
    usage = None
    output_text = ""
    async for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            delta = chunk.choices[0].delta.content
            output_text += delta
            yield delta
        if hasattr(chunk, 'usage') and chunk.usage:
            usage = (getattr(chunk.usage, 'prompt_tokens', 0) or 0,
                     getattr(chunk.usage, 'completion_tokens', 0) or 0)
    if usage and (usage[0] or usage[1]):
        yield _usage_tag("grok", model, usage[0], usage[1])
    else:
        inp_est = _estimate_tokens(" ".join(m["content"] for m in full))
        out_est = _estimate_tokens(output_text)
        yield _usage_tag("grok", model, inp_est, out_est)


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
    from google.genai import types
    client = _get_client("gemini", api_key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
    )
    resp = await client.aio.models.generate_content(
        model=model, contents=_gemini_contents(messages), config=config
    )
    return resp.text or ""


async def _stream_gemini(api_key, model, system, messages, max_tokens) -> AsyncIterator[str]:
    """Gemini: streaming assíncrono nativo via google-genai."""
    from google.genai import types
    client = _get_client("gemini", api_key)
    config = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
    )
    # generate_content_stream é uma coroutine — precisa ser awaited antes de iterar
    stream = await client.aio.models.generate_content_stream(
        model=model, contents=_gemini_contents(messages), config=config
    )
    usage = None
    output_text = ""
    async for chunk in stream:
        if chunk.text:
            output_text += chunk.text
            yield chunk.text
        if hasattr(chunk, 'usage_metadata') and chunk.usage_metadata:
            um = chunk.usage_metadata
            usage = (getattr(um, 'prompt_token_count', 0) or 0, getattr(um, 'candidates_token_count', 0) or 0)
    if usage and (usage[0] or usage[1]):
        yield _usage_tag("gemini", model, usage[0], usage[1])
    else:
        inp_est = _estimate_tokens(system + " ".join(m["content"] for m in messages))
        out_est = _estimate_tokens(output_text)
        yield _usage_tag("gemini", model, inp_est, out_est)


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


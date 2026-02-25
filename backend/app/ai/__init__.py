from app.ai.client import (
    chat, chat_stream, is_ai_configured,
    load_ai_settings, save_ai_settings, set_active_provider, load_all_providers
)
from app.ai.prompts import (
    GESTOR_BASE,
    build_portfolio_prompt,
    build_onboarding_prompt,
    build_briefing_prompt,
)

__all__ = [
    "chat", "chat_stream", "is_ai_configured",
    "load_ai_settings", "save_ai_settings", "set_active_provider", "load_all_providers",
    "GESTOR_BASE", "build_portfolio_prompt", "build_onboarding_prompt", "build_briefing_prompt",
]

"""
Cérebro APEX — sistema nervoso central da plataforma.

Estrutura:
  cerebro/
  ├── client.py          Motor de IA (Anthropic · OpenAI · Gemini · Groq · Grok)
  ├── prompts.py         System prompts base
  ├── contexto.py        ContextoCerebro — dossiê unificado (perfil + mercado + carteira)
  ├── gestor.py          Gestor Geral / CEO Brain — decisão final do portfólio
  ├── macro.py           MacroEngine — dados macro globais e BR (v2)
  ├── focus_bcb.py       Focus BCB via Olinda API (expectativas Selic/IPCA)
  ├── narrativa.py       Narrativa Macro diária (texto IA, sem cenários)
  ├── teses.py           Geração e revisão de teses de investimento
  ├── risco.py           Correlação, concentração, stress test
  ├── radar.py           Radar de oportunidades e custo de oportunidade
  ├── aprendizado.py     Trade journal, post-mortem, performance
  └── especialistas/     7 motores especializados + SugestaoMotor
      ├── alpha.py
      ├── dividendos.py
      ├── etfs.py
      ├── fiis.py
      ├── momentum.py
      ├── renda_fixa.py
      ├── wheel.py
      └── watchlist.py

Uso rápido:
    from app.cerebro import chat, chat_stream, montar_contexto, ContextoCerebro
    from app.cerebro.especialistas import etfs, fiis, SugestaoMotor
    from app.cerebro import gestor
    from app.cerebro.macro import montar_macro, MacroContext
    from app.cerebro.teses import gerar_tese, revisar_tese, monitorar_teses
    from app.cerebro.risco import calcular_correlacao, stress_test
"""

# ── Motor de IA ───────────────────────────────────────────────────────────────
from app.cerebro.client import (
    chat,
    chat_stream,
    is_ai_configured,
    load_ai_settings,
    save_ai_settings,
    set_active_provider,
    load_all_providers,
)

# ── Prompts ───────────────────────────────────────────────────────────────────
from app.cerebro.prompts import (
    APEX_BRAIN,
    GESTOR_BASE,
    build_portfolio_prompt,
    build_onboarding_prompt,
    build_briefing_prompt,
    build_analyst_prompt,
    build_cio_prompt,
    build_ceo_eval_prompt,
    build_ceo_monitor_prompt,
    build_narrativa_prompt,
    build_tese_gerar_prompt,
    build_tese_revisar_prompt,
    build_radar_prompt,
    build_plano_prompt,
    build_postmortem_prompt,
)

# ── Contexto unificado ────────────────────────────────────────────────────────
from app.cerebro.contexto import ContextoCerebro, montar as montar_contexto

# ── Plano Estratégico (Estrategista) ──────────────────────────────
from app.cerebro.plano import diagnosticar as diagnosticar_plano, PlanoEstrategico

__all__ = [
    # IA
    "chat", "chat_stream", "is_ai_configured",
    "load_ai_settings", "save_ai_settings", "set_active_provider", "load_all_providers",
    # Prompts
    "APEX_BRAIN", "GESTOR_BASE",
    "build_portfolio_prompt", "build_onboarding_prompt", "build_briefing_prompt",
    "build_analyst_prompt", "build_cio_prompt", "build_ceo_eval_prompt",
    "build_ceo_monitor_prompt", "build_narrativa_prompt",
    "build_tese_gerar_prompt", "build_tese_revisar_prompt",
    "build_radar_prompt", "build_plano_prompt", "build_postmortem_prompt",
    # Contexto
    "ContextoCerebro", "montar_contexto",
    # Plano
    "diagnosticar_plano", "PlanoEstrategico",
]

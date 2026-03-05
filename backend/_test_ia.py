"""Test analisar_estrategia directly to see what error occurs."""
import asyncio
import sys
import os
sys.path.insert(0, r"e:\Dropbox\apps_criados\APEX\backend")
os.environ.setdefault("DATABASE_URL", "")

async def main():
    from app.cerebro.client import is_ai_configured, load_ai_settings
    print("AI configured:", is_ai_configured())
    print("Settings:", {**load_ai_settings(), "api_key": "***" if load_ai_settings().get("api_key") else ""})

    from app.cerebro import gestor
    print("\nCalling analisar_estrategia...")
    try:
        result = await gestor.analisar_estrategia(
            capital=1500000.0,
            estrategia="ALPHA",
            regime="MISTO",
            score_perfil=7,
        )
        print(f"\nResult:")
        print(f"  usou_ia: {result.usou_ia}")
        print(f"  analise[:200]: {result.analise[:200]}")
        print(f"  alertas: {result.alertas}")
        print(f"  plano_estrategico keys: {list(result.plano_estrategico.keys()) if result.plano_estrategico else None}")
        cenarios = (result.plano_estrategico or {}).get("cenarios", [])
        print(f"  cenarios count: {len(cenarios)}")
        if cenarios:
            print(f"  cenarios[0]: {cenarios[0].get('nome')}")
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(main())

import asyncio, time, sys
sys.path.insert(0, '.')
from app.ai.client import chat, is_ai_configured, load_ai_settings

async def test():
    s = load_ai_settings()
    print(f"Provedor: {s['provider']} | Modelo: {s['model']}")
    print(f"IA configurada: {is_ai_configured()}")
    start = time.time()
    try:
        resp = await asyncio.wait_for(
            chat(
                system="You are a helpful assistant. Reply only with valid JSON.",
                messages=[{"role": "user", "content": "Return this JSON: {\"ok\": true}"}],
                max_tokens=50
            ),
            timeout=30.0
        )
        elapsed = time.time() - start
        print(f"Resposta em {elapsed:.1f}s: {resp[:100]}")
    except asyncio.TimeoutError:
        print(f"TIMEOUT apos {time.time()-start:.1f}s")
    except Exception as e:
        print(f"ERRO: {e}")

asyncio.run(test())

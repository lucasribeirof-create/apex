import asyncio, time, sys, traceback
sys.path.insert(0, '.')

async def test_plano():
    print("Importando...")
    from app.cerebro.plano import diagnosticar
    print("Importado OK. Chamando diagnosticar()...")
    start = time.time()
    try:
        plano = await diagnosticar(
            nome="Lucas",
            patrimonio_atual=1_000_000,
            objetivo_tipo="renda",
            objetivo_valor=30_000,
            objetivo_prazo="5_10anos",
            estrategia_atual="CORE",
            onboarding_respostas={
                "volatilidade": "mantem",
                "liquidez": "menos_10pct",
                "renda": "ativa",
                "objetivo": "renda_passiva",
                "horizonte": "5_10anos",
                "tempo": "1_3h",
                "experiencia": ["acoes_br", "fiis", "renda_fixa"],
            },
            onboarding_score=9,
            aporte_mensal=5000,
        )
        elapsed = time.time() - start
        print(f"SUCESSO em {elapsed:.1f}s")
        print(f"usou_ia: {plano.usou_ia}")
        print(f"cenarios: {len(plano.cenarios)}")
        print(f"modulos_sugeridos: {len(plano.modulos_sugeridos)}")
        print(f"riscos_e_tradeoffs: {len(plano.riscos_e_tradeoffs)}")
        print(f"diagnostico: {plano.diagnostico[:300]}")
    except BaseException as e:
        elapsed = time.time() - start
        print(f"ERRO em {elapsed:.1f}s: {type(e).__name__}: {e}")
        traceback.print_exc()

try:
    asyncio.run(test_plano())
except BaseException as e:
    print(f"asyncio.run FALHOU: {type(e).__name__}: {e}")
    traceback.print_exc()

print("SCRIPT FINALIZADO")

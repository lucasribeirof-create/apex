import asyncio, time, sys
sys.path.insert(0, '.')

async def test_plano():
    from app.cerebro.plano import diagnosticar
    print("Chamando diagnosticar() com dados de teste...")
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
        print(f"\n✅ Plano gerado em {elapsed:.1f}s")
        print(f"usou_ia: {plano.usou_ia}")
        print(f"diagnostico: {plano.diagnostico[:200]}...")
        print(f"cenarios: {len(plano.cenarios)}")
        for c in plano.cenarios:
            print(f"  - {c.nome}: {c.tempo_meta} | {c.rentabilidade_esperada}")
        print(f"modulos_sugeridos: {len(plano.modulos_sugeridos)}")
        print(f"riscos_e_tradeoffs: {len(plano.riscos_e_tradeoffs)}")
        print(f"marcos: {len(plano.marcos)}")
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n❌ ERRO em {elapsed:.1f}s: {e}")

asyncio.run(test_plano())

"""Test the new unbiased prompt with the exact user scenario."""
import asyncio, json, time

async def test():
    from app.cerebro.plano import diagnosticar
    
    start = time.time()
    plano = await diagnosticar(
        nome='Lucas',
        patrimonio_atual=1_000_000,
        objetivo_tipo='livre',
        objetivo_valor=30000,
        objetivo_prazo='5_10anos',
        objetivo_descricao='quero aproveitar os próximos 5 anos para maximizar crescimento patrimonial agressivo! daqui 5 anos quero aposentar e viver de renda de pelo menos 30mil por mês',
        estrategia_atual='CORE',
        onboarding_respostas={
            'volatilidade': 'compra_mais',
            'liquidez': 'nenhuma',
            'renda': 'ativa',
            'objetivo': 'crescimento',
            'horizonte': '5_10anos',
            'tempo': '3_5h',
            'experiencia': ['acoes_br', 'etfs', 'opcoes', 'fiis', 'bdrs'],
            'goal_type': 'livre',
            'goal_value': 30000,
            'goal_description': 'quero aproveitar os próximos 5 anos para maximizar crescimento patrimonial agressivo! daqui 5 anos quero aposentar e viver de renda de pelo menos 30mil por mês',
        },
        onboarding_score=13,
        aporte_mensal=5000,
    )
    elapsed = time.time() - start
    
    print(f'Tempo: {elapsed:.1f}s | usou_ia: {plano.usou_ia}')
    print(f'Fase: {plano.fase_atual}')
    print(f'Estrategia recomendada: {plano.estrategia_recomendada}')
    print(f'Gap: R$ {plano.gap_patrimonio:,.0f}')
    print(f'Cenarios: {len(plano.cenarios)}')
    for c in plano.cenarios:
        print(f'  {c.nome}: {c.rentabilidade_esperada} | modulos: {c.modulos} | tempo: {c.tempo_meta}')
    print(f'Modulos Sugeridos: {len(plano.modulos_sugeridos)}')
    for m in plano.modulos_sugeridos:
        print(f'  {m.nome} ({m.peso_sugerido}): {m.por_que}')
    print(f'\n=== DIAGNOSTICO ===')
    print(plano.diagnostico)
    print(f'\n=== ESTRATEGIA RAZAO ===')
    print(plano.estrategia_razao)

asyncio.run(test())

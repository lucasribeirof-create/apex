"""Audit script — validar todos os dados macro."""
import asyncio
from app.data.cache import cache
from app.cerebro.macro import montar_macro

async def full_audit():
    # Limpa cache
    cache.clear()
    print('Cache limpo!\n')

    ctx = await montar_macro()

    checks = [
        ('SP500',        ctx.sp500,            '~6000-8000 pts'),
        ('SP500_mm50',   ctx.sp500_mm50,       '~5500-7500'),
        ('SP500_mm200',  ctx.sp500_mm200,      '~5000-7000'),
        ('SP500_dia%',   ctx.sp500_var_pct,     '+-5%'),
        ('SP500_ytd%',   ctx.sp500_ytd_pct,     '+-30%'),
        ('Nasdaq',       ctx.nasdaq,            '~15000-25000'),
        ('Nasdaq_ytd%',  ctx.nasdaq_ytd_pct,    '+-30%'),
        ('VIX',          ctx.vix,               '10-80'),
        ('Treasury10Y',  ctx.treasury_10y,      '1-8%'),
        ('DXY',          ctx.dxy,               '80-120'),
        ('DXY_mm50',     ctx.dxy_mm50,          '80-120'),
        ('WTI',          ctx.petroleo_wti,      '$30-150'),
        ('WTI_ytd%',     ctx.petroleo_wti_ytd_pct, '+-50%'),
        ('Brent',        ctx.petroleo_brent,    '$30-150'),
        ('Ouro',         ctx.ouro,              '$1500-10000'),
        ('Ouro_ytd%',    ctx.ouro_ytd_pct,      '+-40%'),
        ('Bitcoin',      ctx.bitcoin,           '$10k-500k'),
        ('Bitcoin_ytd%', ctx.bitcoin_ytd_pct,   '+-60%'),
        ('---',          None,                  '--- BRASIL ---'),
        ('Selic',        ctx.selic,             '2-20%'),
        ('IPCA_12m',     ctx.ipca_12m,          '2-15%'),
        ('IPCA_expect',  ctx.ipca_expectativa,  '2-10%'),
        ('Selic_expect', ctx.selic_expectativa,  '5-20%'),
        ('Juro_real',    ctx.juro_real,          '-5 a 15%'),
        ('Dolar_BRL',    ctx.dolar_brl,         'R$3-10'),
        ('Dolar_ytd%',   ctx.dolar_ytd_pct,     '+-20%'),
        ('IBOV',         ctx.ibov,              '80000-300000'),
        ('IBOV_dia%',    ctx.ibov_var_pct,      '+-10%'),
        ('IBOV_ytd%',    ctx.ibov_ytd_pct,      '+-40%'),
    ]

    hdr = f"{'Campo':<15} {'Valor':<20} {'Faixa':<18} Status"
    print(hdr)
    print('-' * 68)
    erros = 0
    for nome, val, faixa in checks:
        if nome == '---':
            print(f'\n{faixa}')
            continue
        if val is None:
            status = '** NONE **'
            erros += 1
        else:
            status = 'OK'
        val_str = f'{val:.2f}' if isinstance(val, float) else str(val)
        print(f'{nome:<15} {val_str[:20]:<20} {faixa:<18} {status}')

    print(f'\nTotal NONE: {erros}')

    print(f'\nFlags ({len(ctx.flags)}):')
    for f in ctx.flags:
        print(f'  {f}')

    print(f'\nNarrativa ({len(ctx.narrativa)} chars):')
    print(ctx.narrativa[:600])

    print(f'\n=== RESUMO COMPLETO ===')
    print(ctx.resumo_texto())

asyncio.run(full_audit())

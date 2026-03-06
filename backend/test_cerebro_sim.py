"""
Simulação completa do Cérebro APEX interpretando o mercado HOJE.
Coleta dados reais via yFinance + BCB e executa toda a pipeline:
  1. Coleta macro global + Brasil
  2. Calcula regime macro 4-estados (scoring)
  3. Classifica fase do ciclo Selic
  4. Define guardrails de composição
  5. Gera flags/alertas automáticos
"""

import asyncio
import sys
import os

# Adiciona backend ao path
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime


async def simular():
    print("=" * 70)
    print("  SIMULAÇÃO CÉREBRO APEX — INTERPRETAÇÃO DO MERCADO HOJE")
    print(f"  {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print("=" * 70)

    # Limpa cache pra pegar dados frescos
    from app.data.cache import cache
    cache.clear()

    print("\n⏳ Coletando dados macro reais (yFinance + BCB)...")
    from app.cerebro.macro import montar_macro, GUARDRAILS_POR_REGIME
    ctx = await montar_macro()
    print("✅ Dados coletados!\n")

    # ── DADOS GLOBAIS ──────────────────────────────────────────────────
    print("─" * 50)
    print("  📊 DADOS GLOBAIS")
    print("─" * 50)
    if ctx.treasury_10y is not None:
        print(f"  Treasury 10Y:   {ctx.treasury_10y:.2f}%")
    if ctx.treasury_2y is not None:
        print(f"  Treasury 2Y:    {ctx.treasury_2y:.2f}%")
    if ctx.yield_spread is not None:
        curva = "⚠ INVERTIDA" if ctx.yield_spread < 0 else "normal"
        print(f"  Yield Spread:   {ctx.yield_spread:+.3f}pp ({curva})")
    if ctx.vix is not None:
        nivel = "🟢 calmo" if ctx.vix < 15 else ("🟡 atenção" if ctx.vix < 25 else "🔴 medo")
        print(f"  VIX:            {ctx.vix:.1f} ({nivel})")
    if ctx.dxy is not None:
        print(f"  DXY:            {ctx.dxy:.2f}", end="")
        if ctx.dxy_mm50:
            rel = "↑ acima MM50" if ctx.dxy > ctx.dxy_mm50 else "↓ abaixo MM50"
            print(f" ({rel} {ctx.dxy_mm50:.2f})")
        else:
            print()
    if ctx.sp500 is not None:
        var = f" ({ctx.sp500_var_pct:+.2f}%)" if ctx.sp500_var_pct else ""
        print(f"  S&P 500:        {ctx.sp500:,.0f}{var}", end="")
        if ctx.sp500_mm200:
            rel = "↑ acima" if ctx.sp500 > ctx.sp500_mm200 else "↓ abaixo"
            print(f" [{rel} MM200 {ctx.sp500_mm200:,.0f}]")
        else:
            print()
    if ctx.petroleo_wti is not None:
        print(f"  Petróleo WTI:   US${ctx.petroleo_wti:.2f}")
    if ctx.petroleo_brent is not None:
        print(f"  Petróleo Brent: US${ctx.petroleo_brent:.2f}")
    if ctx.ouro is not None:
        print(f"  Ouro:           US${ctx.ouro:,.0f}/oz")

    # ── DADOS BRASIL ───────────────────────────────────────────────────
    print(f"\n{'─' * 50}")
    print("  🇧🇷 DADOS BRASIL")
    print("─" * 50)
    if ctx.selic is not None:
        print(f"  Selic Meta:     {ctx.selic:.2f}% a.a.")
    if ctx.selic_expectativa is not None:
        print(f"  Selic Exp:      {ctx.selic_expectativa:.2f}%")
    if ctx.ipca_12m is not None:
        print(f"  IPCA 12m:       {ctx.ipca_12m:.2f}%")
    if ctx.ipca_expectativa is not None:
        print(f"  IPCA Exp 12m:   {ctx.ipca_expectativa:.2f}%")
    if ctx.juro_real is not None:
        atrativo = " (RF atrativa!)" if ctx.juro_real > 6 else ""
        print(f"  Juro Real:      {ctx.juro_real:.2f}%{atrativo}")
    if ctx.dolar_brl is not None:
        var = f" ({ctx.dolar_var_pct:+.2f}%)" if ctx.dolar_var_pct else ""
        print(f"  Dólar:          R${ctx.dolar_brl:.2f}{var}")
    if ctx.ibov is not None:
        var = f" ({ctx.ibov_var_pct:+.2f}%)" if ctx.ibov_var_pct else ""
        print(f"  IBOV:           {ctx.ibov:,.0f}{var}")

    # ── REGIME MACRO 4-ESTADOS ─────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  🧠 REGIME MACRO 4-ESTADOS (CÉREBRO HÍBRIDO)")
    print("=" * 70)

    regime_emoji = {
        "RISK_ON_FORTE": "🟢🟢",
        "RISK_ON_MODERADO": "🟢",
        "NEUTRO": "🟡",
        "RISK_OFF": "🔴",
    }
    regime_desc = {
        "RISK_ON_FORTE": "Todos os sinais apontam para ambiente favorável",
        "RISK_ON_MODERADO": "Cenário positivo com algumas ressalvas",
        "NEUTRO": "Sinais conflitantes — cautela recomendada",
        "RISK_OFF": "Ambiente hostil — preservação de capital é prioridade",
    }

    emoji = regime_emoji.get(ctx.regime_macro, "")
    print(f"\n  Regime:      {emoji} {ctx.regime_macro}")
    print(f"               {regime_desc.get(ctx.regime_macro, '')}")

    # Score bar
    blocks = ctx.regime_score // 5
    print(f"\n  Score:       {ctx.regime_score}/100 [{'█' * blocks}{'░' * (20 - blocks)}]")

    # Confiança bar
    cblocks = ctx.confianca // 5
    print(f"  Confiança:   {ctx.confianca}%   [{'█' * cblocks}{'░' * (20 - cblocks)}]")

    # ── FASE SELIC ─────────────────────────────────────────────────────
    fase_emoji = {
        "ALTA": "📈",
        "PICO": "🏔️",
        "TRANSICAO": "↔️",
        "QUEDA": "📉",
        "VALE": "🏜️",
    }
    fase_desc = {
        "ALTA": "Selic subindo — RF pós-fixada atrativa, RV sob pressão",
        "PICO": "Selic no topo — momento de travar prefixados longos",
        "TRANSICAO": "Mercado indefinido sobre direção dos juros",
        "QUEDA": "Selic caindo — FIIs, ações e prefixados se beneficiam",
        "VALE": "Selic no fundo — máximo apetite por risco",
    }
    print(f"\n  Fase Selic:  {fase_emoji.get(ctx.fase_selic, '')} {ctx.fase_selic}")
    print(f"               {fase_desc.get(ctx.fase_selic, '')}")
    if ctx.selic and ctx.selic_expectativa:
        diff = ctx.selic_expectativa - ctx.selic
        print(f"               (Selic {ctx.selic:.2f}% → Exp {ctx.selic_expectativa:.2f}% = {diff:+.2f}pp)")

    # ── GUARDRAILS ─────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  🛡️ GUARDRAILS DE COMPOSIÇÃO")
    print("=" * 70)
    g = ctx.guardrails
    eq = g.get("equity_max_pct", 0)
    rf = g.get("rf_min_pct", 0)
    cx = g.get("caixa_min_pct", 0)
    livre = 100 - eq - rf - cx

    print(f"\n  Equity MAX:  {eq}% ({'🟢' * (eq // 10)})")
    print(f"  RF MIN:      {rf}%")
    print(f"  Caixa MIN:   {cx}%")
    print(f"  Livre:       {livre}% (pode ser equity, RF ou caixa)")
    print(f"  Razão:       {g.get('descricao', '')}")

    # Barra visual de composição
    print(f"\n  ┌{'─' * 50}┐")
    eq_bars = int(eq / 2)
    rf_bars = int(rf / 2)
    cx_bars = int(cx / 2)
    lv_bars = 50 - eq_bars - rf_bars - cx_bars
    print(f"  │{'▓' * eq_bars}{'▒' * rf_bars}{'░' * cx_bars}{'·' * lv_bars}│")
    print(f"  └{'─' * 50}┘")
    print(f"   ▓=Equity({eq}%)  ▒=RF({rf}%)  ░=Caixa({cx}%)  ·=Livre({livre}%)")

    # Exemplo com capital de R$100k
    capital = 100_000
    print(f"\n  📌 Exemplo com R${capital:,.0f}:")
    print(f"     Equity: até R${capital * eq / 100:,.0f}")
    print(f"     RF:     mínimo R${capital * rf / 100:,.0f}")
    print(f"     Caixa:  mínimo R${capital * cx / 100:,.0f}")

    # ── ALERTAS MACRO ──────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  ⚠️ ALERTAS MACRO AUTOMÁTICOS")
    print("=" * 70)
    if ctx.flags:
        for f in ctx.flags:
            print(f"  ⚠ {f}")
    else:
        print("  ✅ Nenhum alerta macro ativo.")

    # ── SCORING DETALHADO ──────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  📋 DETALHAMENTO DO SCORING (como cada indicador contribuiu)")
    print("=" * 70)

    detalhes = []
    base = 50
    total = base

    if ctx.vix is not None:
        if ctx.vix < 15:
            pts = +15; sinal = "🟢 risk-on"
        elif ctx.vix < 20:
            pts = +5; sinal = "🟢 leve risk-on"
        elif ctx.vix < 25:
            pts = 0; sinal = "🟡 neutro"
        elif ctx.vix < 30:
            pts = -10; sinal = "🔴 risk-off"
        else:
            pts = -20; sinal = "🔴🔴 pânico"
        total += pts
        detalhes.append(f"  VIX {ctx.vix:.1f}:".ljust(30) + f"{pts:+3d}pts  {sinal}")

    if ctx.dxy is not None and ctx.dxy_mm50 is not None:
        if ctx.dxy < ctx.dxy_mm50:
            pts = +10; sinal = "🟢 dólar fraco (bom p/ emergentes)"
        else:
            pts = -10; sinal = "🔴 dólar forte (pressão)"
        total += pts
        detalhes.append(f"  DXY vs MM50:".ljust(30) + f"{pts:+3d}pts  {sinal}")

    if ctx.juro_real is not None:
        if ctx.juro_real < 4:
            pts = +10; sinal = "🟢 juro real baixo"
        elif ctx.juro_real < 6:
            pts = 0; sinal = "🟡 neutro"
        else:
            pts = -15; sinal = "🔴 juro real alto (RF >> RV)"
        total += pts
        detalhes.append(f"  Juro Real {ctx.juro_real:.1f}%:".ljust(30) + f"{pts:+3d}pts  {sinal}")

    if ctx.treasury_10y is not None:
        if ctx.treasury_10y < 4:
            pts = +10; sinal = "🟢 custo global baixo"
        elif ctx.treasury_10y < 5:
            pts = 0; sinal = "🟡 neutro"
        else:
            pts = -10; sinal = "🔴 custo elevado"
        total += pts
        detalhes.append(f"  Treasury 10Y {ctx.treasury_10y:.2f}%:".ljust(30) + f"{pts:+3d}pts  {sinal}")

    if ctx.yield_spread is not None:
        if ctx.yield_spread > 0:
            pts = +10; sinal = "🟢 curva normal"
        else:
            pts = -15; sinal = "🔴 curva invertida (recessão?)"
        total += pts
        detalhes.append(f"  Yield Spread {ctx.yield_spread:+.2f}:".ljust(30) + f"{pts:+3d}pts  {sinal}")

    if ctx.sp500 is not None and ctx.sp500_mm200 is not None:
        if ctx.sp500 > ctx.sp500_mm200:
            pts = +10; sinal = "🟢 tendência de alta"
        else:
            pts = -10; sinal = "🔴 abaixo da média"
        total += pts
        detalhes.append(f"  S&P500 vs MM200:".ljust(30) + f"{pts:+3d}pts  {sinal}")

    if ctx.ibov_var_pct is not None:
        if ctx.ibov_var_pct > 0:
            pts = +5; sinal = "🟢 IBOV positivo"
        elif ctx.ibov_var_pct < -1:
            pts = -5; sinal = "🔴 IBOV em queda"
        else:
            pts = 0; sinal = "🟡 neutro"
        total += pts
        detalhes.append(f"  IBOV {ctx.ibov_var_pct:+.2f}%:".ljust(30) + f"{pts:+3d}pts  {sinal}")

    if ctx.petroleo_wti is not None:
        if 60 <= ctx.petroleo_wti <= 90:
            pts = +5; sinal = "🟢 faixa saudável"
        elif ctx.petroleo_wti > 100:
            pts = -5; sinal = "🔴 pressão inflacionária"
        else:
            pts = 0; sinal = "🟡 neutro"
        total += pts
        detalhes.append(f"  WTI US${ctx.petroleo_wti:.0f}:".ljust(30) + f"{pts:+3d}pts  {sinal}")

    print(f"\n  Base inicial:".ljust(30) + f" {base}pts")
    for d in detalhes:
        print(d)
    print(f"  {'─' * 45}")
    total_clamped = max(0, min(100, total))
    print(f"  TOTAL (clamped 0-100):".ljust(30) + f" {total_clamped}pts → {ctx.regime_macro}")

    # ── RESUMO PARA A IA ───────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  💬 TEXTO INJETADO NO PROMPT DA IA (resumo_texto()):")
    print("=" * 70)
    resumo = ctx.resumo_texto()
    for l in resumo.split("\n"):
        if "CALENDÁRIO" in l.upper():
            print(f"  {l}")
            print("  (...eventos do calendário omitidos na simulação...)")
            break
        print(f"  {l}")

    print(f"\n{'=' * 70}")
    print("  ✅ SIMULAÇÃO COMPLETA — TODAS AS FUNÇÕES DO CÉREBRO OK")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(simular())

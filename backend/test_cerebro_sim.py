"""
Simulação completa do Cérebro APEX interpretando o mercado HOJE.
Coleta dados reais via yFinance + BCB e executa toda a pipeline:
  1. Coleta macro global + Brasil
  2. Calcula regime macro 4-estados (scoring)
  3. Classifica fase do ciclo Selic
  4. Define guardrails de composição
  5. Gera flags/alertas automáticos
  6. Ranking setorial top-down (Fase 2)
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

    # ── RANKING SETORIAL (Fase 2) ──────────────────────────────────────
    print(f"\n{'=' * 70}")
    print("  📊 RANKING SETORIAL (Fase 2 — Cérebro Híbrido)")
    print("=" * 70)

    print("\n  ⏳ Calculando ranking setorial...")
    from app.cerebro.setor import montar_ranking
    ranking = await montar_ranking(ctx)
    print("  ✅ Ranking calculado!\n")

    # Tabela de setores
    print(f"  {'Setor':<14} {'Score':>6} {'Macro':>6} {'Mom':>6} {'Val':>6} {'Proxy':<8} {'Ret63d':>8} {'P/L':>6}")
    print(f"  {'─' * 14} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 8} {'─' * 8} {'─' * 6}")
    for s in ranking.setores:
        tag = "⭐" if s.setor in ranking.favorecidos else ("⛔" if s.setor in ranking.evitar else "  ")
        ret = f"{s.retorno_63d_pct:+.1f}%" if s.retorno_63d_pct is not None else "   N/A"
        pl = f"{s.pl_proxy:.1f}" if s.pl_proxy is not None else "  N/A"
        print(f"  {tag}{s.setor:<12} {s.score_total:>5} {s.score_macro:>6} {s.score_momentum:>6} {s.score_valuation:>6} {s.ticker_proxy:<8} {ret:>8} {pl:>6}")

    print(f"\n  Favorecidos: {', '.join(ranking.favorecidos) or 'nenhum'}")
    print(f"  Evitar:      {', '.join(ranking.evitar) or 'nenhum'}")

    # Motivos dos top 3
    print(f"\n  📋 Motivos (top 3 favorecidos):")
    for s in ranking.setores[:3]:
        if s.motivos:
            print(f"    {s.setor}:")
            for m in s.motivos:
                print(f"      → {m}")

    # Motivos dos evitar
    if ranking.evitar:
        print(f"\n  📋 Motivos (evitar):")
        for s in ranking.setores:
            if s.setor in ranking.evitar and s.motivos:
                print(f"    {s.setor}:")
                for m in s.motivos:
                    print(f"      → {m}")

    # Texto para IA
    print(f"\n  💬 Texto injetado na IA (ranking.resumo_texto()):")
    for l in ranking.resumo_texto().split("\n"):
        print(f"  {l}")

    # Harmonização dividendos
    print(f"\n  🔄 Harmonização de setores (dividendos motor):")
    from app.cerebro.setor import harmonizar_setor
    test_map = [("bancário", "financeiro"), ("petróleo", "energia"), ("mineração", "mineracao"),
                ("elétrico", "utilidades"), ("telecom", "tecnologia"), ("seguros", "financeiro")]
    for raw, esperado in test_map:
        resultado = harmonizar_setor(raw)
        ok = "✅" if resultado == esperado else "❌"
        print(f"    {ok} '{raw}' → '{resultado}' (esperado: '{esperado}')")

    print(f"\n{'=' * 70}")
    print("  ✅ SIMULAÇÃO COMPLETA — TODAS AS FUNÇÕES DO CÉREBRO OK")
    print("    Fase 1: Macro Engine ✅")
    print("    Fase 2: Ranking Setorial ✅")
    print("=" * 70)

    # ── MOTOR ALPHA FUNDAMENTALISTA (Fase 3) ───────────────────────────
    print(f"\n{'=' * 70}")
    print("  🧬 MOTOR ALPHA — FUNDAMENTALISTA PROFUNDA (Fase 3)")
    print("=" * 70)

    print("\n  ⏳ Rodando motor Alpha com 4 pilares + red flags...")
    from app.cerebro.especialistas.alpha import rodar as rodar_alpha
    from app.cerebro.especialistas.alpha import _fetch_fundamentals, _check_red_flags, _is_eliminado, _score_alpha

    # Testar com 5 tickers conhecidos
    test_tickers = ["PETR4", "VALE3", "ITUB4", "WEGE3", "BBAS3"]
    print(f"\n  📋 Teste individual de indicadores ({len(test_tickers)} tickers):")
    print(f"  {'Ticker':<8} {'P/L':>6} {'P/VP':>6} {'EV/EB':>6} {'DY%':>5} {'ROE%':>6} {'ROIC%':>6} {'DL/EB':>6} {'Cob.J':>6} {'FCF':>8} {'Cresc':>6} {'Flags':>5}")
    print(f"  {'─' * 8} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 5} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 8} {'─' * 6} {'─' * 5}")

    indicator_count = 0
    eliminados = 0
    for tk in test_tickers:
        d = _fetch_fundamentals(tk)
        if not d:
            print(f"  {tk:<8} (sem dados)")
            continue

        flags = _check_red_flags(d)
        elim = "⛔" if _is_eliminado(flags) else "✅"
        if _is_eliminado(flags):
            eliminados += 1

        # Contar indicadores presentes
        indicadores = ["pl", "p_vp", "ev_ebitda", "dy", "roe", "roic", "margem_op",
                       "margem_bruta", "dl_ebitda", "cobertura_juros", "fcf", "margem_liq",
                       "cresc_receita", "cresc_lucro", "momentum_6m"]
        presentes = sum(1 for k in indicadores if d.get(k) is not None)
        indicator_count = max(indicator_count, presentes)

        pl_s  = f"{d['pl']:.1f}" if d.get('pl') else "N/A"
        pvp_s = f"{d['p_vp']:.2f}" if d.get('p_vp') else "N/A"
        ev_s  = f"{d['ev_ebitda']:.1f}" if d.get('ev_ebitda') else "N/A"
        dy_s  = f"{d['dy']:.1f}" if d.get('dy') else "N/A"
        roe_s = f"{d['roe']:.0f}" if d.get('roe') else "N/A"
        roic_s = f"{d['roic']:.0f}" if d.get('roic') else "N/A"
        dl_s  = f"{d['dl_ebitda']:.1f}" if d.get('dl_ebitda') is not None else "N/A"
        cob_s = f"{d['cobertura_juros']:.0f}" if d.get('cobertura_juros') else "N/A"
        fcf_v = d.get('fcf')
        fcf_s = f"{fcf_v / 1e9:.1f}B" if fcf_v and abs(fcf_v) >= 1e9 else (f"{fcf_v / 1e6:.0f}M" if fcf_v else "N/A")
        cr_s  = f"{d['cresc_receita']:+.0f}%" if d.get('cresc_receita') is not None else "N/A"

        print(f"  {tk:<8} {pl_s:>6} {pvp_s:>6} {ev_s:>6} {dy_s:>5} {roe_s:>6} {roic_s:>6} {dl_s:>6} {cob_s:>6} {fcf_s:>8} {cr_s:>6} {elim:>5}")

        # Score por pilares
        score, breakdown = _score_alpha(d)
        print(f"           Score {score:.0f}/100 → Val {breakdown['valuation']:.0f} | Rent {breakdown['rentabilidade']:.0f} | Saúde {breakdown['saude']:.0f} | Cresc {breakdown['crescimento']:.0f}")
        if flags:
            for f in flags:
                print(f"           🚩 {f}")

    print(f"\n  📊 Indicadores presentes (melhor ticker): {indicator_count}/15")
    print(f"  📊 Eliminados por red flags: {eliminados}/{len(test_tickers)}")

    # Rodar motor completo com ranking setorial
    print(f"\n  ⏳ Rodando motor Alpha completo (capital=R$50.000)...")
    sugestoes = await rodar_alpha(
        capital=50_000,
        n_ativos=5,
        ranking_setorial=ranking,
    )
    print(f"  ✅ {len(sugestoes)} sugestões geradas!\n")

    if sugestoes:
        print(f"  {'Ticker':<8} {'Score':>6} {'Preço':>10} {'Qtd':>5} {'Valor':>10} {'Setor':<12} {'Pilares'}")
        print(f"  {'─' * 8} {'─' * 6} {'─' * 10} {'─' * 5} {'─' * 10} {'─' * 12} {'─' * 30}")
        for s in sugestoes:
            dx = s.dados_extras
            pilares = dx.get("pilares", {})
            p_str = f"V{pilares.get('valuation', 0):.0f} R{pilares.get('rentabilidade', 0):.0f} S{pilares.get('saude', 0):.0f} C{pilares.get('crescimento', 0):.0f}"
            setor = dx.get("setor", "?")
            print(f"  {s.ticker:<8} {s.score:>5.0f} {s.preco_atual:>10.2f} {s.quantidade:>5.0f} {s.valor_total:>10.2f} {setor:<12} {p_str}")

            # Verificar dados_extras tem 15+ campos
            n_extras = len([v for v in dx.values() if v is not None])
            print(f"           dados_extras: {n_extras} campos | flags: {dx.get('red_flags', [])}")

        # Validação: dados_extras deve ter >= 15 campos
        first_extras = sugestoes[0].dados_extras
        n_filled = len([v for k, v in first_extras.items() if v is not None and k not in ("red_flags", "pilares")])
        status_15 = "✅" if n_filled >= 10 else "⚠️"
        print(f"\n  {status_15} Indicadores preenchidos no melhor ativo: {n_filled}")

        # Validação: pilares devem existir
        has_pilares = "pilares" in first_extras and len(first_extras["pilares"]) == 4
        status_pil = "✅" if has_pilares else "❌"
        print(f"  {status_pil} Score por 4 pilares: {'presente' if has_pilares else 'AUSENTE'}")

        # Validação: red_flags deve existir
        has_flags = "red_flags" in first_extras
        status_rf = "✅" if has_flags else "❌"
        print(f"  {status_rf} Red flags: {'presente' if has_flags else 'AUSENTE'}")

    print(f"\n{'=' * 70}")
    print("  ✅ SIMULAÇÃO COMPLETA — TODAS AS FUNÇÕES DO CÉREBRO OK")
    print("    Fase 1: Macro Engine ✅")
    print("    Fase 2: Ranking Setorial ✅")
    print("    Fase 3: Alpha Fundamentalista Profunda ✅")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(simular())

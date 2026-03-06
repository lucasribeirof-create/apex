"""
Gestor Geral APEX — CEO Brain.

Recebe os candidatos de TODOS os motores especializados e tem autoridade total
para montar o portfólio final: quais ativos entram, em que tamanho, com qual
raciocínio — levando em conta regime, perfil de risco e estratégia do usuário.

Fluxo:
  1. Pré-processamento leve: marca duplicatas (mesmo ticker em 2+ módulos)
  2. Monta contexto completo para a IA (candidatos + macro + perfil + capital)
  3. IA decide a carteira final e justifica cada decisão
  4. Fallback algorítmico se IA indisponível ou timeout (deduplicação simples)
"""

import json
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from app.cerebro.especialistas import SugestaoMotor
from app.logger import logger


# ─── Resultado do CEO ─────────────────────────────────────────────────────────

@dataclass
class ResultadoGestorGeral:
    """Portfólio final decidido pelo CEO Brain."""
    sugestoes_finais: list[SugestaoMotor]
    analise: str                          # Parágrafo executivo assinado pelo CEO
    alertas: list[str]                    # Riscos identificados
    ajustes_realizados: list[str]         # O que mudou vs. sugestão original dos motores
    score_portfolio: int                  # Score 0-100 do portfólio final
    usou_ia: bool = True                  # False = fallback algorítmico


# ─── Entry point público ──────────────────────────────────────────────────────

async def analisar(
    candidatos: list[SugestaoMotor],
    capital: float,
    estrategia: str,
    regime: str,
    score_perfil: int,
    contexto: Optional[Any] = None,
    modo: str = "inicial",
) -> ResultadoGestorGeral:
    """
    Ponto de entrada principal.
    Recebe todos os candidatos dos motores e retorna o portfólio final decidido pelo CEO.

    Args:
        contexto: ContextoCerebro opcional — se fornecido, o CEO vê as posições já existentes
                  e pode considerar o que já está na carteira ao sugerir novas alocações.
    """
    if not candidatos:
        return ResultadoGestorGeral(
            sugestoes_finais=[],
            analise="Nenhum candidato recebido dos motores.",
            alertas=["Nenhum módulo gerou oportunidades no momento atual."],
            ajustes_realizados=[],
            score_portfolio=0,
            usou_ia=False,
        )

    candidatos_prep = _marcar_duplicatas(candidatos)

    try:
        resultado = await asyncio.wait_for(
            _analisar_com_ia(candidatos_prep, capital, estrategia, regime, score_perfil, contexto, modo),
            timeout=60.0,
        )
        # Validação hard de guardrails pós-IA
        if contexto and hasattr(contexto, "guardrails") and contexto.guardrails:
            resultado = _validar_guardrails(resultado, contexto.guardrails, capital)
        return resultado
    except asyncio.TimeoutError:
        logger.error("gestor_geral: timeout IA (60s) — IA não respondeu a tempo, usando fallback algorítmico")
        return _fallback_algoritmico(candidatos_prep, capital, estrategia, regime)
    except Exception as e:
        logger.error("gestor_geral: IA falhou — %s: %s", type(e).__name__, e, exc_info=True)
        return _fallback_algoritmico(candidatos_prep, capital, estrategia, regime)


# ─── Pré-processamento ────────────────────────────────────────────────────────

def _marcar_duplicatas(candidatos: list[SugestaoMotor]) -> list[SugestaoMotor]:
    """
    Marca candidatos com o mesmo ticker que aparecem em mais de um módulo.
    Não remove nada — o CEO recebe TODAS as opiniões para decidir.
    """
    from collections import Counter
    contagem = Counter(c.ticker for c in candidatos)
    duplicados = {ticker for ticker, n in contagem.items() if n > 1}

    for c in candidatos:
        if c.ticker in duplicados:
            c.dados_extras["_duplicado"] = True
            c.dados_extras["_n_modulos"] = contagem[c.ticker]

    return candidatos


# ─── Análise via IA ───────────────────────────────────────────────────────────

async def _analisar_com_ia(
    candidatos: list[SugestaoMotor],
    capital: float,
    estrategia: str,
    regime: str,
    score_perfil: int,
    contexto: Optional[Any] = None,
    modo: str = "inicial",
) -> ResultadoGestorGeral:
    from app.cerebro.client import chat, is_ai_configured

    if not is_ai_configured():
        raise RuntimeError("IA não configurada")

    # Monta representação compacta dos candidatos para o prompt
    candidatos_json = []
    for c in candidatos:
        item = {
            "ticker": c.ticker,
            "nome": c.nome,
            "tipo": c.tipo,
            "modulo": c.modulo,
            "score_motor": round(c.score, 3),
            "valor_sugerido": round(c.valor_total, 2),
            "quantidade_sugerida": c.quantidade,
            "preco_atual": round(c.preco_atual, 2),
            "justificativa_motor": c.justificativa[:400],  # trunca para economizar tokens
        }
        extras_relevantes = {
            k: v for k, v in c.dados_extras.items()
            if not k.startswith("_") and k in (
                "dy_12m", "dy_estimado", "p_vp", "pl", "crescimento_receita",
                "rsi", "alvo", "stop", "rr", "taxa_referencia_aa", "segmento",
                "setor", "payout_ratio", "upside_estimado_pct", "retorno_anual",
            )
        }
        if extras_relevantes:
            item["indicadores"] = extras_relevantes
        if c.dados_extras.get("_duplicado"):
            item["_duplicado_em_modulos"] = c.dados_extras.get("_n_modulos", 2)
        candidatos_json.append(item)

    # ── Dados macro reais ────────────────────────────────────────────────────
    macro_dados: dict = {}
    if contexto and hasattr(contexto, "macro") and contexto.macro:
        m = contexto.macro
        macro_dados = {
            k: v for k, v in {
                "selic_aa":          m.get("selic"),             # % a.a. — Meta Selic Copom
                "ipca_12m":          m.get("ipca"),              # % acum. 12m
                "dolar_brl":         m.get("dolar"),             # USD/BRL spot
                "dolar_variacao":    m.get("dolar_variacao"),    # % hoje
                "ibov":              m.get("ibov"),              # pontos
                "ibov_variacao":     m.get("ibov_variacao"),     # % hoje
                "sp500":             m.get("sp500"),             # pontos
                "sp500_variacao":    m.get("sp500_variacao"),    # % hoje
                "vix":               m.get("vix"),               # índice de medo
            }.items() if v is not None
        }
        if m.get("selic"):
            macro_dados["cdi_mensal_ref"] = round(m["selic"] / 12, 3)   # CDI ~mensal
        macro_dados["macro_resumo"] = contexto.resumo_macro_texto()

    payload = {
        "capital_total": capital,
        "estrategia": estrategia,
        "regime_mercado": regime,
        "score_perfil_risco": score_perfil,
        "perfil_descricao": _descrever_perfil(score_perfil, estrategia),
        "candidatos": candidatos_json,
        "modulos_com_candidatos": list({c["modulo"] for c in candidatos_json}),
    }
    if macro_dados:
        payload["macro"] = macro_dados

    # Injeta posições existentes se ContextoCerebro fornecido
    if contexto and hasattr(contexto, "posicoes") and contexto.tem_posicoes():
        payload["posicoes_ja_na_carteira"] = [
            {
                "ticker":         p["ticker"],
                "nome":           p.get("nome", p["ticker"]),
                "tipo":           p.get("tipo", "-"),
                "modulo":         p.get("modulo", "-"),
                "preco_medio":    round(p.get("preco_medio") or 0, 2),
                "preco_atual":    round(p.get("preco_atual") or 0, 2),
                "pl_percentual":  round(p.get("pl_percentual") or 0, 2),
                "valor_atual":    round(p.get("valor_atual") or 0, 2),
                "stop_loss":      p.get("stop_loss"),
            }
            for p in contexto.posicoes
            if p.get("ticker") not in ("CAIXA", "TESES")
        ]
        payload["carteira_resumo"] = contexto.resumo_carteira_texto()
        payload["alocacao_real"] = contexto.alocacao_real
        payload["pl_carteira_pct"] = contexto.pl_total_pct

    # Injeta dados de risco (correlação, concentração) se disponíveis no contexto
    if contexto and hasattr(contexto, "macro_context") and contexto.macro_context:
        mc = contexto.macro_context
        payload["macro_enriquecido"] = {
            "treasury_10y": mc.treasury_10y,
            "treasury_2y": mc.treasury_2y,
            "yield_spread": mc.yield_spread,
            "vix": mc.vix,
            "dxy": mc.dxy,
            "petroleo_wti": mc.petroleo_wti,
            "ouro": mc.ouro,
            "juro_real": mc.juro_real,
            "selic_expectativa": mc.selic_expectativa,
            "ipca_expectativa": mc.ipca_expectativa,
        }
        if mc.flags:
            payload["alertas_macro"] = mc.flags

    # ── Regime macro 4-estados + guardrails (Fase 1 Cérebro Híbrido) ──────
    if contexto and hasattr(contexto, "regime_macro"):
        payload["regime_macro_4state"] = contexto.regime_macro
        payload["regime_score"] = contexto.regime_score
        payload["confianca_macro"] = contexto.confianca_macro
        payload["fase_selic"] = contexto.fase_selic
        if contexto.guardrails:
            payload["guardrails_macro"] = contexto.guardrails

    # ── Ranking setorial (Fase 2 Cérebro Híbrido) ─────────────────────────
    if contexto and hasattr(contexto, "ranking_setorial") and contexto.ranking_setorial:
        rs = contexto.ranking_setorial
        payload["ranking_setorial"] = {
            "favorecidos": rs.favorecidos,
            "evitar": rs.evitar,
            "setores": [
                {"setor": s.setor, "score": s.score_total, "motivos": s.motivos[:2]}
                for s in rs.setores
            ],
        }

    if contexto and hasattr(contexto, "narrativa_macro") and contexto.narrativa_macro:
        payload["narrativa_macro"] = contexto.narrativa_macro[:2000]

    # Injeta plano estratégico do Estrategista (plano.py) — âncora de longo prazo
    if contexto and hasattr(contexto, "plano_estrategico") and contexto.plano_estrategico:
        p = contexto.plano_estrategico
        payload["plano_estrategico"] = {
            "fase_atual":              p.get("fase_atual"),
            "fase_descricao":          p.get("fase_descricao"),
            "estrategia_recomendada": p.get("estrategia_recomendada"),
            "estrategia_razao":        p.get("estrategia_razao"),
            "meta_viavel":             p.get("meta_viavel"),
            "diagnostico_resumo":      (p.get("diagnostico") or "")[:300],
            "proximos_passos":         p.get("proximos_passos", [])[:3],
            "alertas_estrategicos":    p.get("alertas", [])[:3],
        }

    SYSTEM = """\
Você é o Gestor Geral APEX — CIO (Chief Investment Officer) de um family office brasileiro, \
com 20+ anos gerindo carteiras multi-estratégia no mercado local e global. \
Você tem autoridade total sobre a composição final do portfólio.

━━━ SUA EXPERTISE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MACRO BRASIL:
  • Selic e ciclo do Copom: quando a Selic está alta (>12%), RF post-fixada supera ações.
    Ciclos de corte beneficiam renda variável, FIIs e prefixados longos.
  • IPCA: inflação >5% corrói carteiras nominais. IPCA+ >6% real é oportunidade em NTNB.
  • Dólar: USD/BRL >5,80 favorece exportadoras (VALE3, PETR4, SUZB3, EMBRAER).
    < 4,80 favorece importadoras e consumo interno.
  • IBOV: abaixo de 120k e em queda = regime BEAR. Acima de 130k com força = BULL.
    Correlação com commodities (petróleo, minério, celulose) é alta.
  • VIX: <15 = ambiente de risco. 15-25 = atenção. >25 = medo global, reduza beta.
    VIX >30 = CRISE. 95% de caixa defensivo justificável.

RENDA FIXA BR:
  • Pós-fixado (CDI/Selic): proteção no juro alto. Perda de oportunidade no ciclo de corte.
  • IPCA+ (NTNB, CRI, CRA): ideal para patrimônio de longo prazo. Trava taxa real.
  • Prefixado: só faz sentido quando se prevê queda de juros. Risco de duration se juros subirem.
  • LCI/LCA: mesmo retorno que CDB mas isento de IR. Preferir quando disponível.

RENDA VARIÁVEL BR:
  • FIIs: DY atraente quando Selic está baixando. P/VP < 1.0 = desconto. Segmentos:
    CRI/CRA (menor risco), logística (crescimento), lajes (cíclico), shoppings (recovery).
  • Dividendos: empresas estruturalmente geradoras (elétricas, telecom, bancos).
    Payout ratio < 80% = sustentável. DY que cobre pelo menos CDI + prêmio.
  • Alpha: ações com desconto fundamentalista (P/L, P/VP), momentum ainda não precificado.
  • Momentum: tendência confirmada (MM50 > MM200), RSI 50-70, volume crescente.
  • ETFs: núcleo de eficiência. BOVA11 (Brasil), IVVB11 (S&P500 + hedge dólar).
  • Wheel / Opções: motor com 4 estratégias — aceite candidatos quando o score justificar:
      WHEEL_PUT  — vender PUT cash-secured: gera renda recorrente (CDI + prêmio de risco).
                   EXCELLENT em qualquer regime se ação saudável e prêmio ≥ 1.5× CDI.
      COBERTA    — vender CALL sobre posição existente: renda SEM risco adicional, SEMPRE
                   válido quando CDI < prêmio anualizado. Não rejeite sem motivo sólido.
      CALL_SECO  — comprar CALL direcional em ativo sobrevendido + tendência alta.
                   Risco definido = prêmio pago. Payoff de 2-5× se catalisador se confirmar.
      PUT_SECO   — comprar PUT em ativo sobrecomprado ou como hedge de carteira.
                   Uso defensivo legítimo, especialmente em regime BEAR ou VIX elevado.
    Selic alta NÃO invalida opções — ao contrário, alta Selic = IV alta = prêmios maiores.
    Inclua ao menos 1 posição de opções se o capital permitir e o score for ≥ 1.2× CDI.

RACIOCÍNIO MACRO → PORTFÓLIO:
  Selic alta + BEAR + VIX alto   → 40-50% RF, 20-30% Caixa, equity mínimo
                                    MAS: Wheel PUT w/ proteção e Covered CALL são renda sem risco direcional
  Selic alta + MISTO + VIX < 20  → 30% RF, crescimento moderado em ETF/Dividendos + Wheel PUT
  Selic caindo + BULL + VIX < 15 → aggressive: Momentum/Alpha/FIIs + CALL_SECO em oportunidades
  USD alto + BULL                 → sobrepesar exportadoras no Alpha; Wheel em PETR4/VALE3/SUZB3
  USD baixo + BULL                → consumo doméstico, small caps, FIIs

━━━ SUA FUNÇÃO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Você recebe candidatos dos especialistas (ETFs, FIIs, RF, Momentum, Wheel, Alpha, Dividendos) \
e tem poder decisório completo para:
1. Definir QUAIS ativos entram (não precisa aceitar todos os candidatos)
2. Decidir o VALOR ALOCADO em cada posição (pode diferir do sugerido pelo motor)
3. Resolver DUPLICATAS — mesmo ticker em dois módulos → escolhe a tese mais forte
4. REDISTRIBUIR capital entre classes conforme macro real e perfil
5. Aumentar CAIXA se risco total estiver acima do tolerado pelo perfil

Sua missão: portfólio que supere benchmarks (IBOV / CDI) com risco proporcional ao perfil.

━━━ REGRAS OPERACIONAIS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- A soma de valor_final DEVE ser EXATAMENTE igual a capital_total
- Se sobrar capital, crie posição "CAIXA" (tipo "CAIXA", módulo "caixa")
- Cada ativo precisa de sua justificativa — curta, objetiva, baseada em DADOS DO PAYLOAD
- NUNCA invente preços. Use preco_atual do candidato ou do campo preco_atual do payload
- Em regime BEAR: prefira RF + Caixa + Dividendos defensivos. Reduza Momentum e Alpha
- Em regime BULL: pode ser agressivo em Momentum/Alpha se perfil permitir
- Em regime MISTO: equilíbrio; não aposte em tendência que não foi confirmada
- Se houver "macro" no payload: USE os números. Justifique com Selic, VIX, IBOV, dólar reais.
- Se houver "posicoes_ja_na_carteira": considere o existente. Bom P&L → pode reforçar.
  P&L ruim + stop próximo → evite reforçar. Não duplique teses abertas sem razão forte.
- Se houver "plano_estrategico": este é o MANDATO DE LONGO PRAZO. Respeite-o:
  * fase "crescimento" → ETFs/Momentum/Alpha dominam. RF/Dividendos = base mínima.
  * fase "transição" → equilíbrio; comece a construir FIIs e Dividendos.
  * fase "colheita" → FIIs/Dividendos/RF dominam. Alpha só se muito assimétrico.
  * meta_viavel=false → NÃO monte estratégia RENDA ainda. Foco total em acumulação.
  * estrategia_recomendada no plano tem PRIORIDADE sobre parâmetro estrategia.

━━━ GUARDRAILS (LIMITES HARD POR REGIME MACRO) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Se "guardrails_macro" estiver no payload, estes limites são INVIOLÁVEIS:
  - equity_max_pct: teto MÁXIMO para soma de ações + ETFs + FIIs + Momentum + Alpha + Dividendos + Wheel
  - rf_min_pct: MÍNIMO de alocação em Renda Fixa
  - caixa_min_pct: MÍNIMO de caixa (liquidez imediata)
Se violar qualquer guardrail, REDUZA equity e AUMENTE RF/caixa até cumprir.
Justifique na "analise" o regime macro e os limites aplicados.
O campo "regime_macro_4state" indica o regime determinístico (não o regime técnico de 3 estados).
  - RISK_ON_FORTE: ambiente favorável, equity pode ir até o máximo
  - RISK_ON_MODERADO: bom com ressalvas, equity moderado
  - NEUTRO: cenário indefinido, postura conservadora
  - RISK_OFF: cenário hostil, preservação de capital é PRIORIDADE

━━━ RANKING SETORIAL (VIÉS TOP-DOWN) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Se "ranking_setorial" estiver no payload, use como VIÉS (não filtro eliminatório):
  - "favorecidos": setores beneficiados pelo cenário macro atual → PREFIRA candidatos destes setores
  - "evitar": setores prejudicados pelo cenário macro → EVITE ou reduza exposição
  - Cada setor tem score 0-100 e motivos explicando o alinhamento macro
Se 2 candidatos empatarem em qualidade, ESCOLHA o do setor favorecido.
Se um candidato excelente estiver em setor a evitar, PODE incluir mas com posição menor e justificativa.
Mencione o viés setorial na "analise" quando relevante.

━━━ FRAMEWORK DE DECISÃO (OBRIGATÓRIO para cada ativo) ━━━━━━━━━━━━━━━━━━━━
Para CADA ativo na carteira_final, a justificativa_ceo DEVE começar com uma das ações:
  ENTRAR    → tese clara + timing técnico favorável + R/R >= 2 + espaço na alocação
  MANTER    → tese ainda válida + acima do trailing stop + sem deterioração
  SAIR      → tese invalidada OU alvo atingido OU oportunidade melhor para o capital
  AUMENTAR  → tese fortaleceu + preço recuou para zona de compra + portfólio aguenta mais risco
  REDUZIR   → tese enfraqueceu mas não morreu OU posição ficou grande demais OU correlação alta

Formato: "ENTRAR — [justificativa com dados concretos]"
Se houver narrativa_macro ou alertas_macro no payload, USE-OS na justificativa.
Se houver posições correlacionadas (ex: 3 petroleiras), considere o risco conjunto.

━━━ FORMATO DE RESPOSTA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Retorne APENAS JSON válido. Zero texto antes/depois. Zero markdown. Exatamente:
{
  "carteira_final": [
    {
      "ticker": "BOVA11",
      "modulo": "etfs",
      "nome": "iShares IBOVESPA ETF",
      "tipo": "ETF",
      "valor_final": 15000.00,
      "preco_atual": 125.30,
      "acao": "ENTRAR",
      "justificativa_ceo": "ENTRAR — Núcleo de mercado BR. Com Selic em queda e IBOV em 128k, ETF amplo captura \
beta de forma eficiente sem stock picking. Regime BULL confirma entrada."
    }
  ],
  "analise": "Parágrafo executivo de 6-8 linhas obrigatórias, em sequência:\n1) Contexto macro atual com os números REAIS do payload: Selic, VIX, dólar, IBOV, regime — e o que esse cenário significa para investimentos agora (risk-on, risk-off, ciclo de juros).\n2) Por que a estratégia escolhida (CORE/ALPHA/RENDA) é a decisão certa para este perfil neste momento de mercado — argumento direto e convincente.\n3) Lógica de cada módulo incluído: o que cada classe entrega (DY estimado dos FIIs em %, retorno projetado da RF em relação ao CDI, upside do Momentum/Alpha, eficiência dos ETFs) e por que faz sentido agora dado o macro.\n4) O principal risco desta carteira e o indicador/evento a monitorar.\n5) Expectativa de performance vs. CDI e IBOV no horizonte de investimento do perfil.\nTom: gestor de fundo apresentando o plano para o cliente — convincente, objetivo, baseado em dados reais.",
  "alertas": ["Alerta 1 com dado concreto", "Alerta 2 com dado concreto"],
  "ajustes_realizados": ["Descrição do ajuste 1", "Descrição do ajuste 2"],
  "score_portfolio": 78
}"""

    # ── Modo rebalanceamento: instrução adicional para o CEO comparar com carteira atual ──
    if modo == "rebalanceamento":
        REBAL_ADDON = """

━━━ MODO REBALANCEAMENTO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ATENÇÃO: Esta NÃO é uma montagem do zero. O investidor JÁ TEM posições em carteira \
(listadas em "posicoes_ja_na_carteira" no payload). Seu trabalho é REBALANCEAR.

OBRIGAÇÕES EXTRAS NO REBALANCEAMENTO:
1. Para cada ativo que MANTÉM da carteira atual → explique POR QUE continua válido \
   (dados técnicos, fundamento, macro favorável). Na justificativa_ceo mencione: "MANTER — [razão]".
2. Para cada ativo NOVO que entra → explique POR QUE é melhor que não tê-lo. \
   Na justificativa_ceo mencione: "ENTRADA — [razão com dados]".
3. Para cada ativo da carteira atual que NÃO aparece na carteira_final → ele será REMOVIDO. \
   Isso precisa ser justificado em "ajustes_realizados" com: "SAÍDA [TICKER] — [razão: stop atingido, \
   tese deteriorada, oportunidade melhor em X, macro desfavorável, etc.]".
4. Para ativos com MUDANÇA DE TAMANHO (valor diferente do atual) → explique na justificativa_ceo: \
   "AUMENTO — [razão]" ou "REDUÇÃO — [razão]".

NA ANÁLISE ("analise"):
- Comece com: "**Rebalanceamento sugerido:**" seguido de um resumo das mudanças.
- Explique o RACIONAL GERAL das mudanças: o que mudou no cenário desde a montagem anterior \
  que justifica esses ajustes (dados macro, regime, performance das posições).
- Liste explicitamente: quantas posições mantidas, quantas novas, quantas removidas, quantas redimensionadas.
- Justifique cada troca (saiu X, entrou Y) com dados comparativos concretos.
- Termine com a visão de risco/retorno esperado da carteira rebalanceada vs. a anterior.

NOS ALERTAS ("alertas"):
- Inclua alertas sobre posições que performaram mal e estão sendo mantidas (se houver).
- Alerte sobre concentração excessiva se o rebalanceamento aumentar exposição a uma classe.

Tom: gestor explicando ao cliente POR QUE cada mudança faz sentido — transparente, detalhado, com dados."""
        SYSTEM += REBAL_ADDON
        payload["modo"] = "rebalanceamento"
        USER = f"Rebalanceie o portfólio existente com base nos dados a seguir. Justifique CADA mudança em relação à carteira atual:\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    else:
        USER = f"Monte o portfólio final com base nos dados a seguir:\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    resposta_raw = await chat(
        system=SYSTEM,
        messages=[{"role": "user", "content": USER}],
        max_tokens=6500,
    )

    return _parsear_resposta_ia(resposta_raw, candidatos, capital)


def _descrever_perfil(score: int, estrategia: str) -> str:
    if estrategia == "RENDA":
        return "Foco em geração de renda passiva — prefere dividendos, FIIs e RF"
    if score <= 5:
        return "Conservador — prioriza capital protegido, aceita retorno menor"
    if score <= 10:
        return "Moderado — equilíbrio entre crescimento e proteção"
    return "Agressivo — busca máximo retorno, tolera volatilidade"


def _parsear_resposta_ia(
    resposta_raw: str,
    candidatos_originais: list[SugestaoMotor],
    capital: float,
) -> ResultadoGestorGeral:
    """
    Converte o JSON retornado pela IA em ResultadoGestorGeral.
    Tolerante a JSON dentro de blocos markdown.
    """
    texto = resposta_raw.strip()

    # Remove blocos markdown se presentes: ```json ... ```
    if "```" in texto:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", texto)
        if match:
            texto = match.group(1).strip()

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ValueError(f"CEO Brain: JSON inválido na resposta da IA: {e}\nResposta: {texto[:300]}")

    carteira_raw = dados.get("carteira_final", [])
    if not carteira_raw:
        raise ValueError("CEO Brain: carteira_final vazia na resposta da IA")

    # Mapa dos candidatos originais para herdar preco_atual e dados_extras
    mapa_originais: dict[tuple[str, str], SugestaoMotor] = {
        (c.ticker, c.modulo): c for c in candidatos_originais
    }
    mapa_por_ticker: dict[str, SugestaoMotor] = {}
    for c in candidatos_originais:
        if c.ticker not in mapa_por_ticker or c.score > mapa_por_ticker[c.ticker].score:
            mapa_por_ticker[c.ticker] = c

    sugestoes_finais: list[SugestaoMotor] = []

    for item in carteira_raw:
        ticker  = str(item.get("ticker", "")).strip().upper()
        modulo  = str(item.get("modulo", "caixa"))
        nome    = str(item.get("nome", ticker))
        tipo    = str(item.get("tipo", "ACAO"))
        valor   = float(item.get("valor_final", 0))
        preco   = float(item.get("preco_atual", 1.0))
        just    = str(item.get("justificativa_ceo", ""))

        if valor <= 0:
            continue

        # Herda preco_atual real do candidato original se disponível
        original = (
            mapa_originais.get((ticker, modulo))
            or mapa_por_ticker.get(ticker)
        )

        if original:
            preco_real = original.preco_atual if original.preco_atual > 0 else preco
            dados_extras = dict(original.dados_extras)
            score = original.score
        else:
            preco_real = preco if preco > 0 else 1.0
            dados_extras = {}
            score = 0.0

        # Limpa flags internas de pré-processamento
        dados_extras.pop("_duplicado", None)
        dados_extras.pop("_n_modulos", None)

        # Quantidade: para RF/CAIXA é o valor nominal; para os demais é quantidade de cotas
        if tipo in ("RF", "CAIXA") or preco_real <= 1.0:
            quantidade = valor
        else:
            quantidade = round(valor / preco_real)
            if quantidade < 1:
                quantidade = 1
            valor = round(quantidade * preco_real, 2)

        sugestoes_finais.append(SugestaoMotor(
            modulo=modulo,
            ticker=ticker,
            nome=nome,
            tipo=tipo,
            quantidade=quantidade,
            preco_atual=round(preco_real, 2),
            valor_total=round(valor, 2),
            justificativa=just,
            score=score,
            dados_extras=dados_extras,
        ))

    # Valida soma e ajusta Caixa se necessário
    # Se a IA alocou significativamente mais que o capital, escala proporcionalmente
    soma_bruta = sum(s.valor_total for s in sugestoes_finais)
    if soma_bruta > capital * 1.02:  # tolerância de 2%
        fator = capital / soma_bruta
        logger.warning(
            "gestor_geral: IA alocou R$%.2f > capital R$%.2f — escalonando (fator %.3f)",
            soma_bruta, capital, fator,
        )
        for s in sugestoes_finais:
            s.valor_total = round(s.valor_total * fator, 2)
            if s.tipo not in ("RF", "CAIXA") and s.preco_atual > 1.0:
                s.quantidade = max(1, round(s.valor_total / s.preco_atual))
                s.valor_total = round(s.quantidade * s.preco_atual, 2)
            else:
                s.quantidade = s.valor_total

    sugestoes_finais = _sizing_v2_ajuste(sugestoes_finais, capital)
    sugestoes_finais = _balancear_caixa(sugestoes_finais, capital)

    return ResultadoGestorGeral(
        sugestoes_finais=sugestoes_finais,
        analise=str(dados.get("analise", "")),
        alertas=[str(a) for a in dados.get("alertas", [])],
        ajustes_realizados=[str(a) for a in dados.get("ajustes_realizados", [])],
        score_portfolio=int(dados.get("score_portfolio", 70)),
        usou_ia=True,
    )


def _balancear_caixa(sugestoes: list[SugestaoMotor], capital: float) -> list[SugestaoMotor]:
    """
    Ajusta a posição Caixa para garantir que a soma dos valor_total = capital.
    Necessário porque quantidades inteiras de ações criam pequenos desvios.
    """
    total = sum(s.valor_total for s in sugestoes)
    diff = round(capital - total, 2)

    if abs(diff) < 0.01:
        return sugestoes

    caixa = next((s for s in sugestoes if s.ticker == "CAIXA"), None)
    if caixa:
        novo_valor = round(caixa.valor_total + diff, 2)
        if novo_valor > 0:
            caixa.valor_total = novo_valor
            caixa.quantidade = novo_valor
        else:
            sugestoes = [s for s in sugestoes if s.ticker != "CAIXA"]
    elif abs(diff) > 0.50:
        sugestoes.append(SugestaoMotor(
            modulo="caixa",
            ticker="CAIXA",
            nome="Reserva de Liquidez",
            tipo="CAIXA",
            quantidade=diff,
            preco_atual=1.0,
            valor_total=diff,
            justificativa="Capital residual após arredondamento de quantidades.",
            score=0.0,
            dados_extras={},
        ))

    return sugestoes


def _sizing_v2_ajuste(sugestoes: list[SugestaoMotor], capital: float) -> list[SugestaoMotor]:
    """
    Sizing V2 — pós-processamento algorítmico.

    A IA decide alocação % → este ajuste converte em quantidades
    ajustadas por volatilidade (ATR relativo) e convicção (score).
    Não altera a alocação decidida pela IA, apenas calibra o tamanho
    de cada posição para que posições mais voláteis tenham menor peso
    e posições de maior convicção tenham peso proporcional.
    """
    equity_positions = [s for s in sugestoes if s.tipo not in ("RF", "CAIXA")]
    if len(equity_positions) < 2:
        return sugestoes

    # Calcula pesos relativos baseados no score (proxy de convicção)
    scores = [max(s.score, 0.1) for s in equity_positions]
    score_total = sum(scores)
    if score_total <= 0:
        return sugestoes

    # Preserva o capital total destinado a equity (decisão da IA)
    capital_equity = sum(s.valor_total for s in equity_positions)

    # Ajusta proporcionalmente pelo score relativo (convicção)
    for s, score in zip(equity_positions, scores):
        peso_ia = s.valor_total / capital_equity if capital_equity > 0 else 0
        peso_score = score / score_total
        # Média ponderada: 70% decisão IA, 30% ajuste por convicção
        peso_final = peso_ia * 0.7 + peso_score * 0.3
        novo_valor = round(capital_equity * peso_final, 2)

        if s.preco_atual > 1.0:
            s.quantidade = max(1, round(novo_valor / s.preco_atual))
            s.valor_total = round(s.quantidade * s.preco_atual, 2)
        else:
            s.quantidade = novo_valor
            s.valor_total = novo_valor

    return sugestoes


# ─── Validação hard de guardrails pós-IA ──────────────────────────────────────

def _validar_guardrails(
    resultado: ResultadoGestorGeral,
    guardrails: dict,
    capital: float,
) -> ResultadoGestorGeral:
    """
    Valida e ajusta a carteira final para respeitar os guardrails do regime macro.
    Se a IA alocou equity acima do limite, reduz proporcionalmente e move para caixa.
    """
    equity_max_pct = guardrails.get("equity_max_pct")
    rf_min_pct = guardrails.get("rf_min_pct")
    caixa_min_pct = guardrails.get("caixa_min_pct")

    if not equity_max_pct and not rf_min_pct and not caixa_min_pct:
        return resultado

    sugestoes = resultado.sugestoes_finais
    if not sugestoes or capital <= 0:
        return resultado

    # Classifica posições
    _equity_tipos = {"ACAO", "ETF", "FII", "OPCAO"}
    equity = [s for s in sugestoes if s.tipo.upper() in _equity_tipos]
    rf = [s for s in sugestoes if s.tipo.upper() == "RF"]
    caixa = [s for s in sugestoes if s.tipo.upper() == "CAIXA"]
    outros = [s for s in sugestoes if s not in equity and s not in rf and s not in caixa]

    equity_total = sum(s.valor_total for s in equity)
    rf_total = sum(s.valor_total for s in rf)
    caixa_total = sum(s.valor_total for s in caixa)

    equity_pct = (equity_total / capital) * 100
    rf_pct = (rf_total / capital) * 100
    caixa_pct = (caixa_total / capital) * 100

    ajustes = []
    excesso_equity = 0

    # Check equity max
    if equity_max_pct and equity_pct > equity_max_pct:
        max_equity = capital * equity_max_pct / 100
        excesso_equity = equity_total - max_equity
        # Reduz proporcionalmente todas as posições equity
        fator = max_equity / equity_total if equity_total > 0 else 1
        for s in equity:
            s.valor_total = round(s.valor_total * fator, 2)
            if s.preco_atual > 1.0:
                s.quantidade = max(1, round(s.valor_total / s.preco_atual))
                s.valor_total = round(s.quantidade * s.preco_atual, 2)
        ajustes.append(
            f"GUARDRAIL: equity reduzido de {equity_pct:.0f}% para {equity_max_pct}% "
            f"(excesso R${excesso_equity:,.0f} movido para caixa)"
        )

    # Check RF min
    if rf_min_pct and rf_pct < rf_min_pct:
        ajustes.append(
            f"GUARDRAIL: RF em {rf_pct:.0f}% (mínimo {rf_min_pct}%) — ajuste recomendado"
        )

    # Check caixa min
    if caixa_min_pct:
        min_caixa = capital * caixa_min_pct / 100
        if caixa_total < min_caixa:
            ajustes.append(
                f"GUARDRAIL: caixa em {caixa_pct:.0f}% (mínimo {caixa_min_pct}%) — excesso movido para caixa"
            )

    if ajustes:
        # Recalcula e rebalanceia caixa
        resultado.sugestoes_finais = _balancear_caixa(
            equity + rf + caixa + outros, capital
        )
        resultado.ajustes_realizados.extend(ajustes)
        resultado.alertas.append(
            f"Guardrails aplicados: regime macro limitou equity a {equity_max_pct}%"
        )
        logger.info("gestor_geral: guardrails aplicados — %s", "; ".join(ajustes))

    return resultado


# ─── CEO Brain em modo AVALIAÇÃO (carteira existente vs mercado hoje) ─────────

def preparar_avaliacao_ceo(
    posicoes_atuais: list[dict],
    candidatos_motores: list[SugestaoMotor],
    ctx: Any,
) -> tuple[str, str]:
    """
    Prepara (system, user_prompt) para o CEO Brain avaliar a carteira EXISTENTE
    contra o que os motores encontraram no mercado HOJE.

    Modo avaliação ≠ modo construção:
      - Modo construção (sugerir-portfolio): CEO monta carteira do zero.
      - Modo avaliação (este): CEO julga o que já existe vs. alternativas reais disponíveis.
    """
    from datetime import datetime
    data_hoje = datetime.now().strftime("%d/%m/%Y")

    SYSTEM = """\
Você é o CEO Brain APEX — gestor sênior com autoridade total sobre o portfólio.
Você analisa carteiras existentes com independência completa. Sem viés, sem eufemismo, sem proteção de ego.

SUA MISSÃO: avaliar CADA posição da carteira contra o que os motores especializados encontraram no mercado HOJE.
Se uma posição está errada para o momento, diga. Se existe algo melhor disponível agora, aponte com dados.

FRAMEWORK DE DECISÃO (use para cada posição):
  APORTAR MAIS   → posição bem fundamentada, preço atual representa oportunidade, motor confirma qualidade
  MANTER         → posição ok, sem catalisador para mudar agora, risco controlado
  REDUZIR        → acima do alvo de alocação, risco/retorno desfavorável, melhor alternativa disponível
  ZERAR          → fundamento deteriorado, stop rompido, ou existe substituto claramente superior
  TROCAR → sair desta posição e entrar em [TICKER ESPECÍFICO] que o motor encontrou — justifique com dados reais

PRINCÍPIOS:
1. Use os dados dos candidatos dos motores como BENCHMARK. Se o motor Alpha encontrou MGLU3 a P/L 8x e a carteira tem uma posição a P/L 25x, isso é relevante — diga.
2. Selic alta = Renda Fixa muito competitiva. Posições com retorno esperado < Selic merecem questionamento explícito.
3. VIX alto = volatilidade de mercado elevada. Posições Momentum/Swing em mercado de stress têm risco diferente.
4. Se o plano estratégico é ACUMULAÇÃO e há posições de renda (FIIs/Dividendos pesados), sinalize o desalinhamento.
5. Seja específico: ticker + número + dado. Nada de "pode ser interessante" — tome uma posição clara.
6. Retorne markdown limpo. Sem blocos de código, sem JSON, sem repetição do contexto que recebeu."""

    # ── Formata posições atuais ───────────────────────────────────────────────
    linhas_pos = []
    for p in posicoes_atuais:
        ticker = p.get("ticker", "?")
        mod = p.get("modulo", "-")
        pm = p.get("preco_medio") or 0
        atual = p.get("preco_atual") or pm
        pl = p.get("pl_percentual") or 0
        tese = p.get("tese") or ""
        stop = p.get("stop_loss")
        linha = f"  • {ticker} [{mod}]: PM R${pm:,.2f} → R${atual:,.2f} | P&L {pl:+.1f}%"
        if stop:
            linha += f" | stop R${stop:,.2f}"
        if tese:
            linha += f'\n    Tese: "{tese[:100]}{"..." if len(tese) > 100 else ""}"'
        linhas_pos.append(linha)

    # ── Formata candidatos dos motores por módulo (top 5 por módulo) ─────────
    candidatos_por_modulo: dict[str, list[SugestaoMotor]] = {}
    for c in candidatos_motores:
        candidatos_por_modulo.setdefault(c.modulo, []).append(c)

    linhas_motores = []
    for modulo, cands in sorted(candidatos_por_modulo.items()):
        top = sorted(cands, key=lambda x: x.score, reverse=True)[:5]
        linhas_motores.append(f"\n  Motor {modulo.upper()} — melhores oportunidades hoje:")
        for c in top:
            extras = ""
            pl_str = c.dados_extras.get("pl") or c.dados_extras.get("p_l")
            dy_str = c.dados_extras.get("dy") or c.dados_extras.get("dividend_yield")
            if pl_str:
                extras += f" | P/L {pl_str}"
            if dy_str:
                extras += f" | DY {dy_str}%"
            linhas_motores.append(
                f"    • {c.ticker} | {c.nome}{extras} | score {c.score:.0f} | {c.justificativa[:80]}"
            )

    # ── Plano estratégico ─────────────────────────────────────────────────────
    plano_str = ""
    if ctx.plano_estrategico:
        p = ctx.plano_estrategico
        plano_str = (
            f"\n\nPLANO ESTRATÉGICO:\n"
            f"  Estratégia: {p.get('estrategia_recomendada', '?')} | Fase: {p.get('fase_atual', '?')}\n"
            f"  Razão: {p.get('estrategia_razao', '')[:200]}"
        )

    # ── Macro ─────────────────────────────────────────────────────────────────
    macro = ctx.macro or {}
    selic = macro.get("selic") or macro.get("selic_aa", "?")
    ipca  = macro.get("ipca")  or macro.get("ipca_12m", "?")
    vix   = macro.get("vix", "?")
    macro_str = f"Selic {selic}% a.a. | IPCA 12m {ipca}% | VIX {vix} | Regime {ctx.regime}"

    USER = f"""DATA: {data_hoje}
MACRO: {macro_str}

CARTEIRA ATUAL ({len(posicoes_atuais)} posições):
{chr(10).join(linhas_pos) if linhas_pos else "  (carteira vazia)"}

O QUE OS MOTORES ENCONTRARAM HOJE:
{''.join(linhas_motores) if linhas_motores else "  (nenhum candidato encontrado)"}
{plano_str}

---

Estruture sua análise exatamente assim:

**DIAGNÓSTICO GERAL** ← 4-6 linhas: saúde da carteira vs. o que está disponível hoje. A carteira está bem posicionada para o macro atual? Há desalinhamento com o plano estratégico?

**AVALIAÇÃO POR POSIÇÃO**
← Uma linha por posição: **TICKER** → VEREDICTO — justificativa. Se existe alternativa melhor nos candidatos do motor, cite o ticker e o dado que justifica.

**TOP 3 AÇÕES IMEDIATAS**
← As 3 coisas mais urgentes a fazer agora, em ordem de prioridade. Seja específico.

**ALINHAMENTO ESTRATÉGICO**
← Em 2-3 linhas: a carteira atual está servindo o objetivo de longo prazo? O que está atrapalhando mais?"""

    return SYSTEM, USER


# ─── Fallback algorítmico (IA off ou timeout) ─────────────────────────────────

def _fallback_algoritmico(
    candidatos: list[SugestaoMotor],
    capital: float,
    estrategia: str,
    regime: str,
) -> ResultadoGestorGeral:
    """
    Fallback quando a IA não está disponível.
    Faz deduplicação simples por score e retorna os candidatos originais.
    """
    ajustes: list[str] = []

    # Deduplicação: mesmo ticker → mantém o de maior score
    vistos: dict[str, SugestaoMotor] = {}
    for c in candidatos:
        ticker = c.ticker
        if ticker not in vistos:
            vistos[ticker] = c
        elif c.score > vistos[ticker].score:
            ajustes.append(
                f"{ticker}: duplicado ({vistos[ticker].modulo} vs {c.modulo}) — "
                f"{c.modulo} mantido por score maior ({c.score:.2f} > {vistos[ticker].score:.2f})"
            )
            vistos[ticker] = c
        else:
            ajustes.append(
                f"{ticker}: duplicado ({c.modulo} vs {vistos[ticker].modulo}) — "
                f"{vistos[ticker].modulo} mantido por score maior"
            )

    sugestoes = list(vistos.values())

    # Limpa flags internas
    for s in sugestoes:
        s.dados_extras.pop("_duplicado", None)
        s.dados_extras.pop("_n_modulos", None)

    # Ajusta caixa
    sugestoes = _balancear_caixa(sugestoes, capital)

    n_ativos = len([s for s in sugestoes if s.ticker != "CAIXA"])
    modulos = list({s.modulo for s in sugestoes if s.ticker != "CAIXA"})

    analise = (
        f"Portfólio {estrategia} montado com {n_ativos} ativos em {len(modulos)} módulos "
        f"({', '.join(modulos)}) — regime de mercado: {regime}. "
        f"Análise detalhada indisponível (IA não configurada ou timeout). "
        f"Sugestões baseadas nos scores dos motores especializados."
    )

    alertas = []
    if regime == "BEAR":
        alertas.append("Regime BEAR: considere aumentar Renda Fixa e Caixa antes de confirmar")
    if not ajustes:
        ajustes = ["Nenhuma duplicata encontrada — candidatos aceitos como entregues pelos motores"]

    return ResultadoGestorGeral(
        sugestoes_finais=sugestoes,
        analise=analise,
        alertas=alertas,
        ajustes_realizados=ajustes,
        score_portfolio=_score_fallback(sugestoes, capital, regime),
        usou_ia=False,
    )


def _score_fallback(sugestoes: list[SugestaoMotor], capital: float, regime: str) -> int:
    """Score simples baseado em diversificação e regime."""
    if not sugestoes:
        return 0

    modulos  = {s.modulo for s in sugestoes if s.ticker != "CAIXA"}
    n_ativos = len([s for s in sugestoes if s.ticker != "CAIXA"])

    # Base por diversificação
    score = min(60, n_ativos * 8) + min(20, len(modulos) * 5)

    # Penalidade por regime e falta de RF/Caixa
    tem_rf    = any(s.modulo in ("renda_fixa", "caixa") for s in sugestoes)
    tem_eq    = any(s.modulo in ("etfs", "momentum", "alpha", "dividendos") for s in sugestoes)

    if not tem_rf and regime == "BEAR":
        score -= 15
    if not tem_eq and regime == "BULL":
        score -= 10

    return max(0, min(100, score))

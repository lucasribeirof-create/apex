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
from datetime import datetime, timezone
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
    plano_estrategico: Optional[dict] = None  # Gerado pelo CEO quando modo=inicial sem plano prévio


@dataclass
class ResultadoAnaliseEstrategica:
    """Resultado da Fase 1 — análise estratégica SEM carteira (rápido, ~30-60s)."""
    analise: str                          # Parágrafo executivo sobre o cenário macro + perfil
    alertas: list[str]                    # Riscos do cenário atual
    score_perfil_mercado: int             # 0-100: compatibilidade perfil vs. macro
    plano_estrategico: Optional[dict] = None  # Cenários, diagnóstico, recomendação
    regime: str = "MISTO"
    usou_ia: bool = True


# ─── Análise estratégica (Fase 1 — sem motores, rápida) ──────────────────────

async def analisar_estrategia(
    capital: float,
    estrategia: str,
    regime: str,
    score_perfil: int,
    contexto: Optional[Any] = None,
    user_data: Optional[dict] = None,
) -> ResultadoAnaliseEstrategica:
    """
    Fase 1 do fluxo: gera análise executiva + plano estratégico com 3 cenários.
    NÃO roda motores, NÃO gera carteira — é rápido (~30-60s).
    O investidor escolhe o cenário desejado, e SÓ DEPOIS a Fase 2 gera a carteira.
    """
    IA_TIMEOUT = 180.0
    try:
        logger.info("analisar_estrategia: chamando CEO Brain (capital R$%.0f, %s, %s)", capital, estrategia, regime)
        resultado = await asyncio.wait_for(
            _analisar_estrategia_ia(capital, estrategia, regime, score_perfil, contexto, user_data),
            timeout=IA_TIMEOUT,
        )
        resultado.regime = regime
        logger.info("analisar_estrategia: CEO Brain respondeu — cenarios=%d", len((resultado.plano_estrategico or {}).get("cenarios", [])))
        return resultado
    except asyncio.TimeoutError:
        logger.error("analisar_estrategia: timeout IA (%.0fs)", IA_TIMEOUT)
    except Exception as e:
        logger.error("analisar_estrategia: IA falhou — %s: %s", type(e).__name__, e, exc_info=True)

    # Fallback mínimo
    return ResultadoAnaliseEstrategica(
        analise=f"Análise estratégica temporariamente indisponível. Capital: R${capital:,.2f}, estratégia: {estrategia}, regime: {regime}.",
        alertas=["IA não disponível — análise baseada apenas em parâmetros básicos."],
        score_perfil_mercado=50,
        regime=regime,
        usou_ia=False,
    )


async def _analisar_estrategia_ia(
    capital: float,
    estrategia: str,
    regime: str,
    score_perfil: int,
    contexto: Optional[Any] = None,
    user_data: Optional[dict] = None,
) -> ResultadoAnaliseEstrategica:
    """Chamada IA leve: apenas análise + plano estratégico (sem candidatos de motores)."""
    from app.cerebro.client import chat, is_ai_configured

    if not is_ai_configured():
        raise RuntimeError("IA não configurada")

    # Monta dados macro
    macro_dados: dict = {}
    if contexto and hasattr(contexto, "macro") and contexto.macro:
        m = contexto.macro
        macro_dados = {
            k: v for k, v in {
                "selic_aa": m.get("selic"),
                "ipca_12m": m.get("ipca"),
                "dolar_brl": m.get("dolar"),
                "ibov": m.get("ibov"),
                "ibov_variacao": m.get("ibov_variacao"),
                "sp500": m.get("sp500"),
                "vix": m.get("vix"),
            }.items() if v is not None
        }

    # Busca macro enriquecido
    if not macro_dados:
        try:
            from app.cerebro.macro import montar_macro
            _mc = await montar_macro()
            macro_dados = {k: v for k, v in {
                "selic_aa": _mc.selic,
                "ipca_12m": _mc.ipca_12m,
                "ipca_expectativa": _mc.ipca_expectativa,
                "selic_expectativa": _mc.selic_expectativa,
                "juro_real": _mc.juro_real,
                "dolar_brl": _mc.dolar_brl,
                "dolar_variacao_dia": _mc.dolar_var_pct,
                "dolar_ytd_pct": _mc.dolar_ytd_pct,
                "ibov": _mc.ibov,
                "ibov_variacao_dia": _mc.ibov_var_pct,
                "ibov_ytd_pct": _mc.ibov_ytd_pct,
                "sp500": _mc.sp500,
                "sp500_variacao_dia": _mc.sp500_var_pct,
                "sp500_ytd_pct": _mc.sp500_ytd_pct,
                "nasdaq": _mc.nasdaq,
                "nasdaq_ytd_pct": _mc.nasdaq_ytd_pct,
                "vix": _mc.vix,
                "treasury_10y": _mc.treasury_10y,
                "dxy": _mc.dxy,
                "dxy_ytd_pct": _mc.dxy_ytd_pct,
                "ouro_usd": _mc.ouro,
                "ouro_ytd_pct": _mc.ouro_ytd_pct,
                "petroleo_wti": _mc.petroleo_wti,
                "petroleo_wti_ytd_pct": _mc.petroleo_wti_ytd_pct,
                "bitcoin_usd": _mc.bitcoin,
                "bitcoin_ytd_pct": _mc.bitcoin_ytd_pct,
            }.items() if v is not None}
            if _mc.flags:
                macro_dados["alertas_macro"] = _mc.flags
            if _mc.narrativa:
                macro_dados["narrativa_mercado"] = _mc.narrativa
            macro_dados["resumo_macro"] = _mc.resumo_texto()
            # Bloco pré-formatado para a AI citar — impossível confundir dia vs YTD
            macro_dados["DADOS_CHAVE_PARA_CITAR"] = _montar_dados_chave(_mc)
        except Exception as _e:
            logger.warning("analisar_estrategia: MacroEngine falhou: %s", _e)

    payload = {
        "capital_total": capital,
        "estrategia": estrategia,
        "regime_mercado": regime,
        "score_perfil_risco": score_perfil,
        "perfil_descricao": _descrever_perfil(score_perfil, estrategia),
    }
    if macro_dados:
        payload["macro"] = macro_dados

    # Posições existentes (resumo)
    if contexto and hasattr(contexto, "posicoes") and contexto.tem_posicoes():
        payload["carteira_resumo"] = contexto.resumo_carteira_texto()
        payload["alocacao_real"] = contexto.alocacao_real
        payload["pl_carteira_pct"] = contexto.pl_total_pct

    if user_data:
        payload["objetivo_investidor"] = {
            "nome": user_data.get("nome"),
            "tipo": user_data.get("objetivo_tipo"),
            "valor": user_data.get("objetivo_valor"),
            "descricao": user_data.get("objetivo_descricao"),
            "prazo": user_data.get("objetivo_prazo"),
            "aporte_mensal": user_data.get("aporte_mensal"),
            "onboarding_respostas": user_data.get("onboarding_respostas"),
        }

    SYSTEM = """\
Você é o Gestor Geral APEX — CIO (Chief Investment Officer) de um family office brasileiro, \
com 20+ anos gerindo carteiras multi-estratégia.

━━━ SUA MISSÃO AGORA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Analisar o cenário macro atual + perfil do investidor e produzir:
1. Uma ANÁLISE EXECUTIVA do momento de mercado e como ele afeta este investidor
2. Um PLANO ESTRATÉGICO com 3 cenários (Conservador / Recomendado / Agressivo)
3. Score de compatibilidade perfil × mercado

Você NÃO está montando uma carteira agora. Você está PREPARANDO A ESTRATÉGIA \
para que o investidor escolha o cenário, e só depois a carteira será montada.

━━━ EXPERTISE MACRO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Selic alta (>12%): RF post-fixada supera ações. Ciclos de corte beneficiam RV, FIIs, prefixados.
- IPCA >5%: IPCA+ >6% real é oportunidade em NTNB.
- Dólar >5,80: favorece exportadoras. <4,80: favorece consumo interno.
- VIX <15: risk-on. 15-25: atenção. >25: medo global. >30: crise.
- IBOV <120k + queda: BEAR. >130k + força: BULL.
- Dados YTD disponíveis: use-os para contextualizar tendências do ano (S&P, Nasdaq, IBOV, dólar, ouro, petróleo, crypto).
- Nasdaq vs S&P: diferença indica rotação growth↔value.
- Ouro em alta forte: sinal de busca por proteção global.
- Bitcoin: termômetro de apetite por risco/especulação.
- Se houver "narrativa_mercado" no payload, USE-A como âncora da análise.

━━━ REGRA CRÍTICA: DIA ≠ YTD ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O payload contém DOIS tipos de variação — NÃO CONFUNDA:
  • "*_variacao_dia" = variação de HOJE APENAS (1 pregão). Ex: ibov caiu -3% HOJE.
  • "*_ytd_pct" = variação ACUMULADA NO ANO (desde 1/jan). Ex: ibov sobe +13% NO ANO.
Quando disser "no ano" ou "YTD", cite APENAS campos *_ytd_pct.
Quando disser "hoje" ou "no dia", cite APENAS campos *_variacao_dia.
O bloco "DADOS_CHAVE_PARA_CITAR" tem os valores prontos — COPIE DE LÁ.

━━━ FORMATO DE RESPOSTA ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Retorne APENAS JSON válido:
{
  "analise": "OBRIGATÓRIO: 4 parágrafos separados por \\n\\n, cada um com label em **NEGRITO** no início:\\n\\n**MACRO ATUAL:** Selic X%, VIX Y, dólar R$Z, IBOV (YTD%), S&P 500 (YTD%) — contexto real e impacto no perfil. Use APENAS dados do payload.\\n\\n**POR QUE [ESTRATEGIA] AGORA:** Por que esta estratégia faz sentido para este investidor neste momento macro.\\n\\n**LÓGICA DOS MÓDULOS:** Quais módulos fazem sentido e por quê (RF, ETFs, Momentum, Alpha, Wheel, FIIs) com dados concretos.\\n\\n**RISCO PRINCIPAL:** Principal risco do cenário atual e como se proteger.",
  "alertas": ["Alerta 1 com dado concreto", "Alerta 2"],
  "score_perfil_mercado": 72,
  "plano_estrategico": {
    "diagnostico": "3-5 parágrafos: analise a meta declarada, calcule viabilidade (patrimônio, aporte, retorno composto), identifique fase (crescimento/transição/colheita), justifique com macro. Use **negrito** para dados-chave.",
    "meta_viavel": true,
    "gap_patrimonio": 0.0,
    "fase_atual": "crescimento|transição|colheita",
    "fase_descricao": "1-2 frases",
    "estrategia_recomendada": "CORE|ALPHA|RENDA",
    "estrategia_razao": "1-2 frases",
    "cenarios": [
      {"nome":"Conservador","descricao":"2-3 frases","modulos":["RF","ETFs"],"alocacao_resumo":"50% RF · 30% ETFs · 20% FIIs","rentabilidade_esperada":"10-14% a.a.","tempo_meta":"~X anos","risco_principal":"1 frase"},
      {"nome":"Recomendado","descricao":"2-3 frases","modulos":["ETFs","Momentum"],"alocacao_resumo":"...","rentabilidade_esperada":"...","tempo_meta":"...","risco_principal":"..."},
      {"nome":"Agressivo","descricao":"2-3 frases","modulos":["Momentum","Alpha"],"alocacao_resumo":"...","rentabilidade_esperada":"...","tempo_meta":"...","risco_principal":"..."}
    ],
    "modulos_sugeridos": [{"nome":"ETFs","por_que":"1 frase","peso_sugerido":"~30%"}],
    "riscos_e_tradeoffs": ["Risco 1","Risco 2","Risco 3"],
    "marcos": [{"patrimonio":2000000,"renda_mensal_possivel":10000,"estimativa_anos":3.5,"descricao":"..."}],
    "proximos_passos": ["Ação 1","Ação 2"],
    "alertas": [],
    "revisao_quando": "em 12 meses ou quando patrimônio variar ±20%"
  }
}

USE os dados macro REAIS do payload (Selic, VIX, dólar, IBOV, S&P 500, YTDs) para calibrar cenários. \
Cenários devem ter alocações e retornos REALMENTE DIFERENTES entre si.

REGRA ABSOLUTA ANTI-ALUCINAÇÃO: Use APENAS os dados numéricos fornecidos no payload. \
NUNCA invente, estime ou extrapole percentuais, variações YTD ou tendências que NÃO estejam \
explicitamente nos dados. Se um dado não está no payload, NÃO mencione um número — diga \
"dado não disponível" se necessário. Números inventados são INADMISSÍVEIS.

ATENÇÃO REDOBRADA: Ao escrever "IBOV YTD" ou "S&P YTD", confirme que está usando o campo \
*_ytd_pct e NÃO o campo *_variacao_dia. Confundir dia com YTD é erro GRAVÍSSIMO."""

    USER = f"Analise o cenário e produza a estratégia com 3 cenários para este investidor:\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    resposta_raw = await chat(
        system=SYSTEM,
        messages=[{"role": "user", "content": USER}],
        max_tokens=3000,
    )

    return _parsear_analise_estrategica(resposta_raw, capital)


def _parsear_analise_estrategica(resposta_raw: str, capital: float) -> ResultadoAnaliseEstrategica:
    """Parseia a resposta JSON da IA para ResultadoAnaliseEstrategica."""
    texto = resposta_raw.strip()
    if "```" in texto:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", texto)
        if match:
            texto = match.group(1).strip()

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as e:
        raise ValueError(f"Análise estratégica: JSON inválido — {e}\nResposta: {texto[:300]}")

    plano = dados.get("plano_estrategico")
    if plano:
        plano["usou_ia"] = True
        from datetime import datetime, timezone
        plano["gerado_em"] = datetime.now(timezone.utc).isoformat()
        plano["patrimonio_na_criacao"] = capital

    return ResultadoAnaliseEstrategica(
        analise=str(dados.get("analise", "")),
        alertas=[str(a) for a in dados.get("alertas", [])],
        score_perfil_mercado=int(dados.get("score_perfil_mercado", 60)),
        plano_estrategico=plano,
        usou_ia=True,
    )


# ─── Entry point público ──────────────────────────────────────────────────────

async def analisar(
    candidatos: list[SugestaoMotor],
    capital: float,
    estrategia: str,
    regime: str,
    score_perfil: int,
    contexto: Optional[Any] = None,
    modo: str = "inicial",
    user_data: Optional[dict] = None,
    cenario_escolhido: Optional[str] = None,
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

    # Timeout: payload grande + IA gera até ~10000 tokens quando inclui plano estratégico
    IA_TIMEOUT = 300.0

    try:
        logger.info("gestor_geral: chamando CEO Brain via IA (%d candidatos, capital R$%.0f, %s, %s)", len(candidatos_prep), capital, estrategia, regime)
        resultado = await asyncio.wait_for(
            _analisar_com_ia(candidatos_prep, capital, estrategia, regime, score_perfil, contexto, modo, user_data, cenario_escolhido),
            timeout=IA_TIMEOUT,
        )
        logger.info("gestor_geral: CEO Brain respondeu com IA — %d ativos, score %d", len(resultado.sugestoes_finais), resultado.score_portfolio)
        return resultado
    except asyncio.TimeoutError:
        logger.error("gestor_geral: timeout IA (%.0fs) — IA nao respondeu a tempo", IA_TIMEOUT)
    except Exception as e:
        logger.error("gestor_geral: IA falhou — %s: %s", type(e).__name__, e, exc_info=True)

    # Fallback: NUNCA deveria chegar aqui em operacao normal.
    # Loga warning critico para que o problema seja investigado.
    logger.warning("gestor_geral: FALLBACK ALGORITMICO ATIVADO — portfolio sera montado sem analise da IA")
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
    user_data: Optional[dict] = None,
    cenario_escolhido: Optional[str] = None,
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

    # Flags de disponibilidade para o CEO saber o que está faltando
    _has_macro = bool(macro_dados)
    _has_macro_enrich = bool(contexto and hasattr(contexto, "macro_context") and contexto.macro_context)
    _has_narrativa = bool(contexto and hasattr(contexto, "narrativa_macro") and contexto.narrativa_macro)
    _has_plano = bool(contexto and hasattr(contexto, "plano_estrategico") and contexto.plano_estrategico)
    _has_posicoes = bool(contexto and hasattr(contexto, "posicoes") and contexto.tem_posicoes())

    payload = {
        "capital_total": capital,
        "estrategia": estrategia,
        "regime_mercado": regime,
        "score_perfil_risco": score_perfil,
        "perfil_descricao": _descrever_perfil(score_perfil, estrategia),
        "candidatos": candidatos_json,
        "modulos_com_candidatos": list({c["modulo"] for c in candidatos_json}),
        "dados_disponiveis": {
            "macro": _has_macro,
            "macro_enriquecido": _has_macro_enrich,
            "narrativa_macro": _has_narrativa,
            "plano_estrategico": _has_plano,
            "posicoes_existentes": _has_posicoes,
        },
    }
    if macro_dados:
        payload["macro"] = macro_dados

    # Injeta posições existentes se ContextoCerebro fornecido
    if contexto and hasattr(contexto, "posicoes") and contexto.tem_posicoes():
        _agora = datetime.now(timezone.utc)
        _posicoes_enriquecidas = []
        for p in contexto.posicoes:
            if p.get("ticker") in ("CAIXA", "TESES"):
                continue
            # Calcula dias na carteira
            _data_entrada_str = p.get("data_entrada")
            _dias_na_carteira = None
            if _data_entrada_str:
                try:
                    _dt = datetime.fromisoformat(_data_entrada_str)
                    if _dt.tzinfo is None:
                        _dt = _dt.replace(tzinfo=timezone.utc)
                    _dias_na_carteira = (_agora - _dt).days
                except (ValueError, TypeError):
                    pass
            _posicoes_enriquecidas.append({
                "ticker":                p["ticker"],
                "nome":                  p.get("nome", p["ticker"]),
                "tipo":                  p.get("tipo", "-"),
                "modulo":                p.get("modulo", "-"),
                "preco_medio":           round(p.get("preco_medio") or 0, 2),
                "preco_atual":           round(p.get("preco_atual") or 0, 2),
                "pl_percentual":         round(p.get("pl_percentual") or 0, 2),
                "valor_atual":           round(p.get("valor_atual") or 0, 2),
                "stop_loss":             p.get("stop_loss"),
                "alvo_1":               p.get("alvo_1"),
                "alvo_2":               p.get("alvo_2"),
                "data_entrada":          _data_entrada_str,
                "dias_na_carteira":      _dias_na_carteira,
                "justificativa_entrada": p.get("justificativa_entrada"),
            })
        payload["posicoes_ja_na_carteira"] = _posicoes_enriquecidas
        payload["carteira_resumo"] = contexto.resumo_carteira_texto()
        payload["alocacao_real"] = contexto.alocacao_real
        payload["pl_carteira_pct"] = contexto.pl_total_pct

    # Se não tem macro enriquecido no contexto, busca direto do MacroEngine
    if not _has_macro_enrich:
        try:
            from app.cerebro.macro import montar_macro
            _mc = await montar_macro()
            payload["macro_enriquecido"] = {k: v for k, v in {
                "treasury_10y": _mc.treasury_10y,
                "vix": _mc.vix,
                "dxy": _mc.dxy,
                "dxy_ytd_pct": _mc.dxy_ytd_pct,
                "petroleo_wti": _mc.petroleo_wti,
                "petroleo_wti_ytd_pct": _mc.petroleo_wti_ytd_pct,
                "ouro": _mc.ouro,
                "ouro_ytd_pct": _mc.ouro_ytd_pct,
                "juro_real": _mc.juro_real,
                "selic_expectativa": _mc.selic_expectativa,
                "ipca_expectativa": _mc.ipca_expectativa,
                "selic": _mc.selic,
                "ipca_12m": _mc.ipca_12m,
                "dolar_brl": _mc.dolar_brl,
                "dolar_ytd_pct": _mc.dolar_ytd_pct,
                "ibov": _mc.ibov,
                "ibov_ytd_pct": _mc.ibov_ytd_pct,
                "sp500": _mc.sp500,
                "sp500_ytd_pct": _mc.sp500_ytd_pct,
                "nasdaq": _mc.nasdaq,
                "nasdaq_ytd_pct": _mc.nasdaq_ytd_pct,
                "bitcoin": _mc.bitcoin,
                "bitcoin_ytd_pct": _mc.bitcoin_ytd_pct,
            }.items() if v is not None}
            if _mc.flags:
                payload["alertas_macro"] = _mc.flags
            if _mc.narrativa:
                payload["narrativa_macro"] = _mc.narrativa
            payload["macro_resumo_completo"] = _mc.resumo_texto()
            payload["DADOS_CHAVE_PARA_CITAR"] = _montar_dados_chave(_mc)
            _has_macro_enrich = True
        except Exception as _macro_err:
            logger.warning("gestor_geral: MacroEngine falhou: %s", _macro_err)

    if contexto and hasattr(contexto, "macro_context") and contexto.macro_context:
        mc = contexto.macro_context
        # Merge campos do contexto SEM sobrescrever o dict completo
        # (o bloco anterior já populou macro_enriquecido com todos os campos + YTD)
        existing = payload.get("macro_enriquecido", {})
        extra = {
            "treasury_10y": mc.treasury_10y,
            "vix": mc.vix,
            "dxy": mc.dxy,
            "petroleo_wti": mc.petroleo_wti,
            "ouro": mc.ouro,
            "juro_real": mc.juro_real,
            "selic_expectativa": mc.selic_expectativa,
            "ipca_expectativa": mc.ipca_expectativa,
        }
        for k, v in extra.items():
            if v is not None and k not in existing:
                existing[k] = v
        payload["macro_enriquecido"] = existing
        if mc.flags:
            payload["alertas_macro"] = mc.flags

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
- VERIFIQUE "dados_disponiveis" no payload. Se macro=false, avise que a análise macro não está disponível \
  e seja mais conservador (aumente RF/Caixa). Se narrativa_macro=false, prossiga com dados quantitativos.
- A soma de valor_final DEVE ser EXATAMENTE igual a capital_total
- Se sobrar capital, crie posição "CAIXA" (tipo "CAIXA", módulo "caixa")
- Cada ativo precisa de sua justificativa — curta, objetiva, baseada em DADOS DO PAYLOAD
- NUNCA invente preços. Use preco_atual do candidato ou do campo preco_atual do payload
- REGRA ABSOLUTA ANTI-ALUCINAÇÃO: Use APENAS dados do payload. NUNCA invente variações %, \
  YTDs ou tendências não fornecidas. Se o dado não existe no payload, NÃO cite um número.
- REGRA CRÍTICA DIA ≠ YTD: "*_variacao_dia" = variação de HOJE (1 dia). "*_ytd_pct" = acumulado NO ANO. \
  NÃO CONFUNDA. Ao citar YTD use APENAS *_ytd_pct. Use "DADOS_CHAVE_PARA_CITAR" como referência.
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

    # ── Modo inicial SEM plano: CEO também cria a análise estratégica ──────────
    _gerar_plano = (modo == "inicial" and not _has_plano)
    if _gerar_plano:
        PLANO_ADDON = """

━━━ ANÁLISE ESTRATÉGICA (OBRIGATÓRIA — PRIMEIRO PORTFÓLIO) ━━━━━━━━━━━━━━━
Este é o PRIMEIRO portfólio do investidor. Além de montar a carteira, você DEVE \
produzir a análise estratégica completa. Inclua no JSON uma chave "plano_estrategico" com:

{
  "plano_estrategico": {
    "diagnostico": "3-5 parágrafos densos: analise a meta declarada, calcule viabilidade com números reais (patrimônio, aporte, retorno esperado composto), identifique a fase do investidor (crescimento/transição/colheita), e justifique a estratégia escolhida com base no macro atual. Use **negrito** para dados-chave.",
    "meta_viavel": true/false,
    "gap_patrimonio": 0.0,
    "fase_atual": "crescimento|transição|colheita",
    "fase_descricao": "1-2 frases explicando a fase",
    "estrategia_recomendada": "CORE|ALPHA|RENDA",
    "estrategia_razao": "1-2 frases",
    "cenarios": [
      {"nome":"Conservador","descricao":"2-3 frases","modulos":["RF","ETFs"],"alocacao_resumo":"50% RF · 30% ETFs · 20% FIIs","rentabilidade_esperada":"10-14% a.a.","tempo_meta":"~X anos","risco_principal":"1 frase"},
      {"nome":"Recomendado","descricao":"2-3 frases","modulos":["ETFs","Momentum"],"alocacao_resumo":"...","rentabilidade_esperada":"...","tempo_meta":"...","risco_principal":"..."},
      {"nome":"Agressivo","descricao":"2-3 frases","modulos":["Momentum","Alpha"],"alocacao_resumo":"...","rentabilidade_esperada":"...","tempo_meta":"...","risco_principal":"..."}
    ],
    "modulos_sugeridos": [{"nome":"ETFs","por_que":"1 frase","peso_sugerido":"~30%"}],
    "riscos_e_tradeoffs": ["Risco 1","Risco 2","Risco 3"],
    "marcos": [{"patrimonio":2000000,"renda_mensal_possivel":10000,"estimativa_anos":3.5,"descricao":"..."}],
    "proximos_passos": ["Ação 1","Ação 2"],
    "alertas": [],
    "revisao_quando": "em 12 meses ou quando patrimônio variar ±20%"
  }
}

USE os dados macro reais para calibrar cenários. Selic alta → retornos de RF mais altos nos cenários. \
VIX alto → cenário Conservador com mais RF/Caixa. Os cenários devem ter alocações e retornos REALMENTE DIFERENTES."""
        SYSTEM += PLANO_ADDON
        if user_data:
            payload["objetivo_investidor"] = {
                "nome": user_data.get("nome"),
                "tipo": user_data.get("objetivo_tipo"),
                "valor": user_data.get("objetivo_valor"),
                "descricao": user_data.get("objetivo_descricao"),
                "prazo": user_data.get("objetivo_prazo"),
                "aporte_mensal": user_data.get("aporte_mensal"),
                "onboarding_respostas": user_data.get("onboarding_respostas"),
            }

    # ── Modo rebalanceamento: instrução adicional para o CEO comparar com carteira atual ──
    if modo == "rebalanceamento":
        REBAL_ADDON = """

━━━ MODO REBALANCEAMENTO ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ATENÇÃO: Esta NÃO é uma montagem do zero. O investidor JÁ TEM posições em carteira \
(listadas em "posicoes_ja_na_carteira" no payload). Seu trabalho é REBALANCEAR.

━━━ REGRA DE ESTABILIDADE TEMPORAL (OBRIGATÓRIA) ━━━━━━━━━━━━━━━━━━━━━━━━━━
Cada posição tem campo "dias_na_carteira" (0 = criada hoje) e "justificativa_entrada" \
(a razão original pela qual foi incluída na carteira).

VIÉS FORTE PARA MANTER POSIÇÕES RECENTES:
• dias_na_carteira < 7   → BENEFÍCIO DA DÚVIDA MÁXIMO. Só sugira SAÍDA se a tese \
  estiver CLARAMENTE invalidada com dados concretos (stop atingido, fundamento quebrado, \
  regime mudou drasticamente). "Encontrei algo melhor" NÃO é justificativa suficiente.
• dias_na_carteira 7-30  → Benefício moderado. Mudanças precisam de evidência concreta.
• dias_na_carteira > 30  → Avaliação normal. Pode sugerir trocas se houver dados.
• dias_na_carteira = 0   → FOI CRIADA HOJE PELO MESMO SISTEMA (você). Manter OBRIGATÓRIO \
  a menos que um stop loss tenha sido atingido ou um dado catastrófico tenha surgido.

REGRA DE CONSISTÊNCIA:
Compare a "justificativa_entrada" (campo no payload) com o cenário ATUAL.
Se NADA mudou materialmente desde a entrada → MANTER é OBRIGATÓRIO.
Citar "encontrei oportunidade melhor" ou "rebalancear para otimizar" sem evidência \
de deterioração da posição atual é PROIBIDO.

REGRA DE EVIDÊNCIA (para cada SAÍDA ou TROCA):
Você DEVE citar o dado ESPECÍFICO que mudou desde a entrada. Exemplos aceitáveis:
  "Stop loss em R$X atingido (preço atual R$Y)"
  "P/L subiu de 8x para 15x — tese de valor não se sustenta mais"
  "Regime mudou de BULL para BEAR — momentum não opera em regime BEAR"
  "Fundamento deteriorou: receita caiu 20% no último trimestre"
Exemplos PROIBIDOS:
  "Há alternativa melhor no mercado" (sem evidência de deterioração)
  "Para diversificar melhor" (sem citação de risco concreto)
  "Otimização de carteira" (vazio — proibido)

OBRIGAÇÕES NO REBALANCEAMENTO:
1. Para cada ativo que MANTÉM → "MANTER — [razão: tese intacta + dados]".
2. Para cada ativo NOVO → "ENTRAR — [razão com dados + por que este módulo precisa deste ativo]".
3. Para cada ativo que SAI → em "ajustes_realizados": "SAÍDA [TICKER] — [dado concreto que mudou]".
4. Para MUDANÇA DE TAMANHO → "AUMENTO — [razão]" ou "REDUÇÃO — [razão]".

NA ANÁLISE ("analise"):
- Comece com: "**Rebalanceamento sugerido:**" seguido de um resumo das mudanças.
- Explique o RACIONAL GERAL: o que mudou CONCRETAMENTE no cenário desde a montagem anterior.
- Liste: quantas mantidas, novas, removidas, redimensionadas.
- Se TODAS as posições foram mantidas: "Carteira alinhada — nenhuma mudança necessária neste momento."
- Termine com risco/retorno esperado da carteira rebalanceada vs. anterior.

NOS ALERTAS ("alertas"):
- Alerte sobre posições com P&L negativo que estão sendo mantidas (se houver).
- Alerte sobre concentração excessiva se o rebalanceamento aumentar exposição a uma classe.

Tom: gestor explicando ao cliente POR QUE cada mudança faz sentido — transparente, detalhado, com dados. \
Se não há razão para mudar, DIGA ISSO com confiança."""
        SYSTEM += REBAL_ADDON
        payload["modo"] = "rebalanceamento"
        USER = f"Rebalanceie o portfólio existente com base nos dados a seguir. Justifique CADA mudança em relação à carteira atual:\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    else:
        USER = f"Monte o portfólio final com base nos dados a seguir:\n\n{json.dumps(payload, ensure_ascii=False, indent=2)}"

    # ── Cenário escolhido pelo investidor (Fase 2 do fluxo) ─────────────────
    if cenario_escolhido:
        CENARIO_ADDON = f"""

━━━ CENÁRIO ESCOLHIDO PELO INVESTIDOR ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
O investidor analisou a estratégia e ESCOLHEU o cenário: **{cenario_escolhido}**

OBRIGAÇÃO: Alinhe a composição da carteira ao perfil de risco/retorno deste cenário.
- Se "Conservador": priorize RF, ETFs core, FIIs de renda, menos Momentum/Alpha.
- Se "Recomendado": equilíbrio conforme estratégia base do perfil.
- Se "Agressivo": mais Momentum, Alpha, Wheel; aceitar maior volatilidade.

As alocações percentuais entre módulos devem REFLETIR a escolha do investidor."""
        SYSTEM += CENARIO_ADDON
        payload["cenario_escolhido"] = cenario_escolhido

    # Quando precisa gerar plano, resposta é maior
    _max_tokens = 5500 if _gerar_plano else 4500

    resposta_raw = await chat(
        system=SYSTEM,
        messages=[{"role": "user", "content": USER}],
        max_tokens=_max_tokens,
    )

    return _parsear_resposta_ia(resposta_raw, candidatos, capital, extrair_plano=_gerar_plano)


def _montar_dados_chave(mc) -> dict:
    """Monta bloco pré-formatado com dados-chave que a AI deve citar literalmente.
    Separa claramente variação DIA vs YTD para evitar confusão."""
    def _fmt(v, suffix="%"):
        return f"{v:+.1f}{suffix}" if v is not None else "N/D"

    return {
        "IBOV_pontos": f"{mc.ibov:,.0f}" if mc.ibov else "N/D",
        "IBOV_variacao_HOJE": _fmt(mc.ibov_var_pct),
        "IBOV_variacao_NO_ANO_YTD": _fmt(mc.ibov_ytd_pct),
        "SP500_pontos": f"{mc.sp500:,.0f}" if mc.sp500 else "N/D",
        "SP500_variacao_HOJE": _fmt(mc.sp500_var_pct),
        "SP500_variacao_NO_ANO_YTD": _fmt(mc.sp500_ytd_pct),
        "Nasdaq_variacao_NO_ANO_YTD": _fmt(mc.nasdaq_ytd_pct),
        "Dolar_BRL": f"R${mc.dolar_brl:.2f}" if mc.dolar_brl else "N/D",
        "Dolar_variacao_HOJE": _fmt(mc.dolar_var_pct),
        "Dolar_variacao_NO_ANO_YTD": _fmt(mc.dolar_ytd_pct),
        "Selic": f"{mc.selic:.1f}%" if mc.selic else "N/D",
        "VIX": f"{mc.vix:.1f}" if mc.vix else "N/D",
        "Ouro_variacao_NO_ANO_YTD": _fmt(mc.ouro_ytd_pct),
        "Bitcoin_variacao_NO_ANO_YTD": _fmt(mc.bitcoin_ytd_pct),
    }


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
    extrair_plano: bool = False,
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
        acao    = str(item.get("acao", "ENTRAR")).upper()  # ENTRAR|MANTER|AUMENTAR|REDUZIR

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

        # Preserva ação do CEO (ENTRAR/MANTER/AUMENTAR/REDUZIR) para o frontend
        dados_extras["acao_ceo"] = acao

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

    plano = None
    if extrair_plano and dados.get("plano_estrategico"):
        plano = dados["plano_estrategico"]
        plano["usou_ia"] = True
        from datetime import datetime, timezone
        plano["gerado_em"] = datetime.now(timezone.utc).isoformat()
        plano["patrimonio_na_criacao"] = capital
        logger.info("gestor_geral: plano estrategico extraido do CEO Brain (cenarios=%d)", len(plano.get("cenarios", [])))

    return ResultadoGestorGeral(
        sugestoes_finais=sugestoes_finais,
        analise=str(dados.get("analise", "")),
        alertas=[str(a) for a in dados.get("alertas", [])],
        ajustes_realizados=[str(a) for a in dados.get("ajustes_realizados", [])],
        score_portfolio=int(dados.get("score_portfolio", 70)),
        usou_ia=True,
        plano_estrategico=plano,
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

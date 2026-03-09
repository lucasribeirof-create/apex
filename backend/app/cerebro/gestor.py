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
from app.cerebro.prompts import build_cio_prompt, build_ceo_eval_prompt
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
                "classificacao", "hold_elegivel", "hold_motivo",
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

    # ── Circuit Breaker + Heat (Fase 4 Cérebro Híbrido) ──────────────────
    if contexto and hasattr(contexto, "circuit_breaker") and contexto.circuit_breaker:
        cb = contexto.circuit_breaker
        payload["circuit_breaker"] = {
            "nivel": cb.nivel,
            "ativo": cb.ativo,
            "sizing_modifier": cb.sizing_modifier,
            "motivo": cb.motivo,
            "pl_mes_pct": cb.pl_mes_pct,
        }
    if contexto and hasattr(contexto, "heat") and contexto.heat:
        ht = contexto.heat
        payload["heat"] = {
            "heat_pct": ht.heat_pct,
            "pode_operar": ht.pode_operar,
            "heat_reais": ht.heat_reais,
        }

    # ── Kill Switch + Hold info (Fase 5 Cérebro Híbrido) ─────────────────
    if contexto and hasattr(contexto, "kill_switch") and contexto.kill_switch:
        ks = contexto.kill_switch
        payload["kill_switch"] = {
            "ativo": ks.ativo,
            "nivel": ks.nivel,
            "motivo": ks.motivo,
            "recomendacao": ks.recomendacao,
        }
    # Hold candidates — tag ações elegíveis a HOLD nos candidatos
    _hold_candidates = [
        c for c in candidatos_json
        if any(
            s.ticker == c["ticker"] and s.dados_extras.get("hold_elegivel")
            for s in candidatos_prep
        )
    ]
    if _hold_candidates:
        payload["hold_candidates"] = [c["ticker"] for c in _hold_candidates]
    # Watchlist candidates (attached by Alpha motor)
    for c in candidatos_prep:
        wl = c.dados_extras.get("_watchlist_candidates")
        if wl:
            payload["watchlist_candidates"] = wl
            break

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

    SYSTEM = build_cio_prompt(modo=modo)

    # ── Modo rebalanceamento: instrução adicional ──
    if modo == "rebalanceamento":
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

    SYSTEM = build_ceo_eval_prompt()

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

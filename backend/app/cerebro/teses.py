"""
Motor de Teses de Investimento APEX.

Gera, revisa e monitora teses de investimento usando IA generativa.
Cada tese é uma análise estruturada de por que entrar (ou sair) de um ativo,
com catalisadores, riscos, alvos e condições de invalidação.
"""

import json
from datetime import datetime

from app.cerebro.client import chat
from app.logger import logger
from app.models.tese_investimento import TeseInvestimento


# ─── Geração de tese ──────────────────────────────────────────────────────────

SYSTEM_GERAR = """\
Você é um analista de investimentos sênior de um family office brasileiro.
Sua tarefa é produzir uma tese de investimento completa e estruturada para o ativo solicitado.

A tese deve ser fundamentada nos dados fornecidos (preço, múltiplos, setor, contexto macro) \
e escrita de forma objetiva, sem eufemismos.

Retorne APENAS JSON válido, sem markdown, sem texto antes ou depois. Formato exato:
{
  "tese_resumo": "Frase curta de até 200 caracteres resumindo a tese",
  "tese_completa": "Análise detalhada em 3-5 parágrafos: fundamento, timing, assimetria risco/retorno",
  "catalisadores": ["catalisador 1", "catalisador 2", "catalisador 3"],
  "riscos": ["risco 1", "risco 2", "risco 3"],
  "condicao_invalidacao": "Condições explícitas que, se ocorrerem, invalidam a tese e justificam saída",
  "alvo_preco": 45.00,
  "stop_preco": 28.00,
  "prazo_estimado": "3-6 meses",
  "score_conviccao": 7
}

REGRAS:
- score_conviccao: 1 (baixíssima convicção) a 10 (altíssima convicção)
- alvo_preco e stop_preco devem ser números reais baseados nos dados fornecidos
- catalisadores: pelo menos 2, no máximo 5 itens concretos
- riscos: pelo menos 2, no máximo 5 itens concretos
- condicao_invalidacao: seja específico (ex: "perda do suporte de R$28 com volume acima da média")
- prazo_estimado: use formato como "1-3 meses", "6-12 meses", "12+ meses"
- tese_completa: inclua dados quantitativos do payload (P/L, DY, crescimento, etc.)"""


async def gerar_tese(
    ticker: str,
    dados_ativo: dict,
    macro_context: dict,
    contexto: str,
    db,
    portfolio_id: int,
) -> TeseInvestimento:
    """Gera uma tese de investimento completa via IA e persiste no banco."""

    payload = {
        "ticker": ticker,
        "dados_ativo": dados_ativo,
        "macro": macro_context,
        "contexto_adicional": contexto,
    }

    user_msg = (
        f"Gere uma tese de investimento completa para {ticker}.\n\n"
        f"Dados:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    logger.info("teses: gerando tese para %s (portfolio %d)", ticker, portfolio_id)

    resposta_raw = await chat(
        system=SYSTEM_GERAR,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=2000,
    )

    dados = _extrair_json(resposta_raw)

    tese = TeseInvestimento(
        portfolio_id=portfolio_id,
        ticker=ticker.upper(),
        tipo="COMPRA",
        tese_resumo=str(dados.get("tese_resumo", ""))[:200],
        tese_completa=str(dados.get("tese_completa", "")),
        catalisadores=json.dumps(dados.get("catalisadores", []), ensure_ascii=False),
        riscos=json.dumps(dados.get("riscos", []), ensure_ascii=False),
        condicao_invalidacao=str(dados.get("condicao_invalidacao", "")),
        alvo_preco=_safe_float(dados.get("alvo_preco")),
        stop_preco=_safe_float(dados.get("stop_preco")),
        prazo_estimado=str(dados.get("prazo_estimado", "")),
        status="ATIVA",
        score_conviccao=max(1, min(10, int(dados.get("score_conviccao", 5)))),
        historico_revisoes=json.dumps([], ensure_ascii=False),
    )

    db.add(tese)
    db.commit()
    db.refresh(tese)

    logger.info(
        "teses: tese #%d criada para %s — convicção %d/10, alvo R$%s, stop R$%s",
        tese.id, ticker, tese.score_conviccao, tese.alvo_preco, tese.stop_preco,
    )

    return tese


# ─── Revisão de tese ──────────────────────────────────────────────────────────

SYSTEM_REVISAR = """\
Você é um analista de investimentos sênior revisando uma tese de investimento existente.

Sua tarefa é avaliar se a tese original ainda é válida com base nos dados atuais do ativo e do mercado.

Retorne APENAS JSON válido, sem markdown. Formato exato:
{
  "status": "ATIVA",
  "score_conviccao": 7,
  "comentario_revisao": "Análise de 2-4 linhas explicando a decisão de manter/enfraquecer/invalidar",
  "catalisadores_atualizados": ["catalisador 1", "catalisador 2"],
  "riscos_atualizados": ["risco 1", "risco 2"],
  "alvo_preco": 45.00,
  "stop_preco": 28.00
}

REGRAS:
- status DEVE ser exatamente: "ATIVA", "ENFRAQUECIDA" ou "INVALIDADA"
- ATIVA: tese intacta, fundamentos confirmados, catalisadores no caminho
- ENFRAQUECIDA: sinais de deterioração, mas ainda não invalidada — monitorar de perto
- INVALIDADA: condição de invalidação atingida, fundamento quebrado, ou risco materializado → sair
- Se invalidar, explique claramente por quê no comentario_revisao
- alvo_preco e stop_preco podem ser ajustados se os dados justificarem
- score_conviccao: reavalie de 1 a 10 com base nos dados atuais"""


async def revisar_tese(
    tese: TeseInvestimento,
    dados_atuais: dict,
    macro_context: dict,
    db,
) -> TeseInvestimento:
    """Reavalia uma tese existente com dados atuais e atualiza o registro."""

    historico = _carregar_lista_json(tese.historico_revisoes)

    tese_snapshot = {
        "ticker": tese.ticker,
        "tese_resumo": tese.tese_resumo,
        "tese_completa": tese.tese_completa,
        "catalisadores": _carregar_lista_json(tese.catalisadores),
        "riscos": _carregar_lista_json(tese.riscos),
        "condicao_invalidacao": tese.condicao_invalidacao,
        "alvo_preco": tese.alvo_preco,
        "stop_preco": tese.stop_preco,
        "status_atual": tese.status,
        "score_conviccao_atual": tese.score_conviccao,
        "criada_em": tese.created_at.isoformat() if tese.created_at else None,
    }

    payload = {
        "tese_original": tese_snapshot,
        "dados_atuais": dados_atuais,
        "macro": macro_context,
    }

    user_msg = (
        f"Revise a tese de investimento de {tese.ticker}.\n\n"
        f"Dados:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )

    logger.info("teses: revisando tese #%d (%s)", tese.id, tese.ticker)

    resposta_raw = await chat(
        system=SYSTEM_REVISAR,
        messages=[{"role": "user", "content": user_msg}],
        max_tokens=1500,
    )

    dados = _extrair_json(resposta_raw)

    novo_status = dados.get("status", "ATIVA").upper()
    if novo_status not in ("ATIVA", "ENFRAQUECIDA", "INVALIDADA"):
        novo_status = "ATIVA"

    revisao_entry = {
        "data": datetime.utcnow().isoformat(),
        "status_anterior": tese.status,
        "status_novo": novo_status,
        "score_anterior": tese.score_conviccao,
        "score_novo": max(1, min(10, int(dados.get("score_conviccao", tese.score_conviccao)))),
        "comentario": str(dados.get("comentario_revisao", "")),
    }
    historico.append(revisao_entry)

    tese.status = novo_status
    tese.score_conviccao = revisao_entry["score_novo"]
    tese.ultima_revisao = datetime.utcnow()
    tese.historico_revisoes = json.dumps(historico, ensure_ascii=False)

    if dados.get("alvo_preco") is not None:
        tese.alvo_preco = _safe_float(dados["alvo_preco"])
    if dados.get("stop_preco") is not None:
        tese.stop_preco = _safe_float(dados["stop_preco"])

    catalisadores = dados.get("catalisadores_atualizados")
    if catalisadores and isinstance(catalisadores, list):
        tese.catalisadores = json.dumps(catalisadores, ensure_ascii=False)

    riscos = dados.get("riscos_atualizados")
    if riscos and isinstance(riscos, list):
        tese.riscos = json.dumps(riscos, ensure_ascii=False)

    db.commit()
    db.refresh(tese)

    logger.info(
        "teses: tese #%d (%s) revisada — %s → %s (convicção %d/10)",
        tese.id, tese.ticker, revisao_entry["status_anterior"],
        novo_status, tese.score_conviccao,
    )

    return tese


# ─── Monitoramento leve (sem IA) ─────────────────────────────────────────────

async def monitorar_teses(db, portfolio_id: int) -> dict:
    """
    Verificação leve de todas as teses ativas de um portfolio.
    Compara preço atual com stop/alvo sem chamar a IA.
    Retorna resumo com contagens e alertas.
    """

    teses = (
        db.query(TeseInvestimento)
        .filter(
            TeseInvestimento.portfolio_id == portfolio_id,
            TeseInvestimento.status.in_(["ATIVA", "ENFRAQUECIDA"]),
        )
        .all()
    )

    from app.models.position import Position

    resumo = {
        "total": len(teses),
        "ativas": 0,
        "enfraquecidas": 0,
        "invalidadas": 0,
        "alertas": [],
    }

    for tese in teses:
        if tese.status == "ATIVA":
            resumo["ativas"] += 1
        elif tese.status == "ENFRAQUECIDA":
            resumo["enfraquecidas"] += 1

        posicao = (
            db.query(Position)
            .filter(Position.ticker == tese.ticker, Position.portfolio_id == portfolio_id, Position.ativa == True)
            .first()
        )

        preco_atual = posicao.preco_atual if posicao and posicao.preco_atual else None

        if preco_atual is None:
            continue

        if tese.stop_preco and preco_atual <= tese.stop_preco:
            resumo["alertas"].append(
                f"⚠️ {tese.ticker}: preço R${preco_atual:.2f} atingiu stop R${tese.stop_preco:.2f} — considerar saída"
            )

        if tese.alvo_preco and preco_atual >= tese.alvo_preco:
            resumo["alertas"].append(
                f"🎯 {tese.ticker}: preço R${preco_atual:.2f} atingiu alvo R${tese.alvo_preco:.2f} — considerar realização"
            )

        if tese.stop_preco and tese.alvo_preco and tese.stop_preco < tese.alvo_preco:
            distancia_stop_pct = ((preco_atual - tese.stop_preco) / preco_atual) * 100
            if 0 < distancia_stop_pct <= 5:
                resumo["alertas"].append(
                    f"⚡ {tese.ticker}: apenas {distancia_stop_pct:.1f}% acima do stop — atenção redobrada"
                )

        if tese.status == "ENFRAQUECIDA":
            resumo["alertas"].append(
                f"🔶 {tese.ticker}: tese ENFRAQUECIDA (convicção {tese.score_conviccao}/10) — revisão recomendada"
            )

    logger.info(
        "teses: monitoramento portfolio %d — %d teses (%d ativas, %d enfraquecidas, %d alertas)",
        portfolio_id, resumo["total"], resumo["ativas"],
        resumo["enfraquecidas"], len(resumo["alertas"]),
    )

    return resumo


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _extrair_json(texto: str) -> dict:
    """Extrai JSON da resposta da IA, tolerando blocos markdown."""
    texto = texto.strip()

    if "```" in texto:
        import re
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", texto)
        if match:
            texto = match.group(1).strip()

    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        logger.error("teses: falha ao parsear JSON da IA: %s — resposta: %s", e, texto[:300])
        raise ValueError(f"Resposta da IA não é JSON válido: {e}")


def _safe_float(val) -> float | None:
    """Converte valor para float de forma segura, retornando None se impossível."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _carregar_lista_json(texto: str | None) -> list:
    """Carrega lista JSON de um campo Text, retornando lista vazia se inválido."""
    if not texto:
        return []
    try:
        result = json.loads(texto)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []

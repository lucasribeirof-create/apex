"""
Radar de Oportunidades APEX — custo de oportunidade em tempo real.

Combina o scanner existente com análise de custo de oportunidade:
  - Identifica posições em risco (score baixo no scanner)
  - Encontra oportunidades de entrada (score alto fora da carteira)
  - Sugere trocas quando há alternativas melhores

Roda sob demanda para controlar custo de tokens.
"""
from datetime import datetime, timezone

from app.cerebro.client import chat
from app.core.scanner import executar_scan
from app.data.cache import cache
from app.logger import logger

_CACHE_TTL_RADAR = 2 * 3600  # 2 horas

_SYSTEM_PROMPT = (
    "Você é o radar de oportunidades APEX. "
    "Analise as oportunidades encontradas vs a carteira atual. "
    "Seja direto e objetivo. "
    "Foque em custo de oportunidade: o capital em X renderia mais em Y? "
    "Responda em português. Máximo 500 palavras."
)

_SCORE_RISCO = 50
_SCORE_OPORTUNIDADE = 75


def _tickers_por_posicao(posicoes: list[dict]) -> dict[str, dict]:
    """Mapeia ticker → posição para lookup rápido."""
    mapa: dict[str, dict] = {}
    for p in posicoes:
        ticker = p.get("ticker", "").upper().strip()
        if ticker:
            mapa[ticker] = p
    return mapa


def _todos_ativos_scan(resultado_scan: dict) -> list[dict]:
    """Consolida trades + monitor + out em lista única."""
    return (
        resultado_scan.get("trades", [])
        + resultado_scan.get("monitor", [])
        + resultado_scan.get("out", [])
    )


def _encontrar_posicoes_risco(
    posicoes_map: dict[str, dict],
    ativos_scan: list[dict],
) -> list[dict]:
    """Posições na carteira com score abaixo do limiar de risco."""
    risco = []
    scan_map = {a["ticker"]: a for a in ativos_scan}

    for ticker, posicao in posicoes_map.items():
        ativo = scan_map.get(ticker)
        if ativo is None:
            continue
        score = ativo.get("score", 0)
        if score < _SCORE_RISCO:
            risco.append({
                "ticker": ticker,
                "score": score,
                "motivo": ativo.get("motivo", "Score abaixo do limiar"),
            })

    return sorted(risco, key=lambda x: x["score"])


def _encontrar_oportunidades_entrada(
    posicoes_map: dict[str, dict],
    ativos_scan: list[dict],
) -> list[dict]:
    """Ativos com score alto que NÃO estão na carteira."""
    entradas = []
    for ativo in ativos_scan:
        ticker = ativo.get("ticker", "")
        score = ativo.get("score", 0)
        if score >= _SCORE_OPORTUNIDADE and ticker not in posicoes_map:
            motivo_parts = []
            filtros = ativo.get("filtros", [])
            for f in filtros:
                detalhe = f.get("detalhe", "")
                if detalhe:
                    motivo_parts.append(detalhe)

            trade_setup = ativo.get("trade_setup")
            if trade_setup and trade_setup.get("rr"):
                motivo_parts.append(f"R/R {trade_setup['rr']}:1")

            motivo = ", ".join(motivo_parts[:3]) if motivo_parts else f"Score {score} — passou todos os filtros"

            entradas.append({
                "ticker": ticker,
                "score": score,
                "motivo": motivo,
            })

    return sorted(entradas, key=lambda x: x["score"], reverse=True)


def _sugerir_trocas(
    posicoes_risco: list[dict],
    oportunidades_entrada: list[dict],
) -> list[dict]:
    """Para cada posição em risco, sugere a melhor oportunidade de entrada."""
    trocas = []
    entradas_disponiveis = list(oportunidades_entrada)

    for risco in posicoes_risco:
        if not entradas_disponiveis:
            break
        melhor = entradas_disponiveis[0]
        trocas.append({
            "sair": risco["ticker"],
            "entrar": melhor["ticker"],
            "motivo": (
                f"{melhor['ticker']} score {melhor['score']} vs "
                f"{risco['ticker']} score {risco['score']} no mesmo universo"
            ),
        })
        entradas_disponiveis = entradas_disponiveis[1:]

    return trocas


def _build_user_prompt(
    posicoes: list[dict],
    oportunidades_entrada: list[dict],
    posicoes_risco: list[dict],
    trocas_sugeridas: list[dict],
    patrimonio: float,
    regime: str,
    macro_context: str | None,
) -> str:
    """Monta o prompt do usuário para a análise da IA."""
    partes = [f"Patrimônio: R$ {patrimonio:,.2f} | Regime de mercado: {regime}"]

    if macro_context:
        partes.append(f"\nContexto macro:\n{macro_context}")

    if posicoes:
        linhas = [f"  - {p.get('ticker', '?')}" for p in posicoes[:20]]
        partes.append(f"\nCarteira atual ({len(posicoes)} posições):\n" + "\n".join(linhas))

    if posicoes_risco:
        linhas = [f"  - {r['ticker']} (score {r['score']}): {r['motivo']}" for r in posicoes_risco[:10]]
        partes.append(f"\nPosições em risco:\n" + "\n".join(linhas))

    if oportunidades_entrada:
        linhas = [f"  - {o['ticker']} (score {o['score']}): {o['motivo']}" for o in oportunidades_entrada[:10]]
        partes.append(f"\nOportunidades de entrada:\n" + "\n".join(linhas))

    if trocas_sugeridas:
        linhas = [f"  - Sair {t['sair']} → Entrar {t['entrar']}: {t['motivo']}" for t in trocas_sugeridas[:5]]
        partes.append(f"\nTrocas sugeridas:\n" + "\n".join(linhas))

    partes.append(
        "\nAnalise as oportunidades e posições em risco acima. "
        "Foque em custo de oportunidade e priorize as ações mais relevantes."
    )

    return "\n".join(partes)


async def rastrear_oportunidades(
    posicoes: list[dict],
    patrimonio: float,
    estrategia: str,
    macro_context: str | None = None,
    regime: str = "MISTO",
) -> dict:
    """
    Radar completo de oportunidades: scanner + custo de oportunidade + análise IA.

    Args:
        posicoes:      lista de posições atuais (cada uma com ao menos 'ticker')
        patrimonio:    valor total do portfólio
        estrategia:    CORE ou ALPHA
        macro_context: resumo macro opcional para enriquecer a análise
        regime:        regime de mercado (BULL / MISTO / BEAR)

    Returns:
        dict com oportunidades_entrada, posicoes_em_risco, trocas_sugeridas,
        analise_ia, total_oportunidades e atualizado_em.
    """
    cache_key = f"radar:{estrategia}:{len(posicoes)}:{int(patrimonio)}"
    cached = cache.get(cache_key)
    if cached:
        logger.info("Radar: retornando resultado cacheado")
        return cached

    logger.info("Radar: iniciando varredura de oportunidades (estratégia=%s)", estrategia)

    try:
        resultado_scan = await executar_scan(
            patrimonio=patrimonio,
            estrategia=estrategia,
        )
    except Exception as exc:
        logger.error("Radar: falha no scanner — %s", exc)
        return _resultado_vazio(erro=f"Scanner indisponível: {exc}")

    if not resultado_scan:
        logger.warning("Radar: scanner retornou resultado vazio")
        return _resultado_vazio(erro="Scanner não retornou dados")

    ativos_scan = _todos_ativos_scan(resultado_scan)
    if not ativos_scan:
        logger.warning("Radar: nenhum ativo analisado pelo scanner")
        return _resultado_vazio(erro="Nenhum ativo analisado")

    regime_scan = resultado_scan.get("regime", regime)
    posicoes_map = _tickers_por_posicao(posicoes)

    posicoes_risco = _encontrar_posicoes_risco(posicoes_map, ativos_scan)
    oportunidades_entrada = _encontrar_oportunidades_entrada(posicoes_map, ativos_scan)
    trocas_sugeridas = _sugerir_trocas(posicoes_risco, oportunidades_entrada)

    total = len(oportunidades_entrada) + len(posicoes_risco) + len(trocas_sugeridas)

    analise_ia = ""
    if total > 0:
        analise_ia = await _gerar_analise_ia(
            posicoes=posicoes,
            oportunidades_entrada=oportunidades_entrada,
            posicoes_risco=posicoes_risco,
            trocas_sugeridas=trocas_sugeridas,
            patrimonio=patrimonio,
            regime=regime_scan,
            macro_context=macro_context,
        )

    resultado = {
        "oportunidades_entrada": oportunidades_entrada,
        "posicoes_em_risco": posicoes_risco,
        "trocas_sugeridas": trocas_sugeridas,
        "analise_ia": analise_ia,
        "total_oportunidades": total,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }

    cache.set(cache_key, resultado, ttl=_CACHE_TTL_RADAR)
    logger.info(
        "Radar: concluído — %d entradas, %d riscos, %d trocas",
        len(oportunidades_entrada), len(posicoes_risco), len(trocas_sugeridas),
    )
    return resultado


async def _gerar_analise_ia(
    posicoes: list[dict],
    oportunidades_entrada: list[dict],
    posicoes_risco: list[dict],
    trocas_sugeridas: list[dict],
    patrimonio: float,
    regime: str,
    macro_context: str | None,
) -> str:
    """Chama a LLM para gerar análise textual das oportunidades."""
    user_prompt = _build_user_prompt(
        posicoes=posicoes,
        oportunidades_entrada=oportunidades_entrada,
        posicoes_risco=posicoes_risco,
        trocas_sugeridas=trocas_sugeridas,
        patrimonio=patrimonio,
        regime=regime,
        macro_context=macro_context,
    )

    try:
        resposta = await chat(
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=1000,
        )
        return resposta.strip()
    except Exception as exc:
        logger.error("Radar: falha na análise IA — %s", exc)
        return f"Análise IA indisponível: {exc}"


def _resultado_vazio(erro: str = "") -> dict:
    """Retorna estrutura padrão vazia para cenários de falha."""
    return {
        "oportunidades_entrada": [],
        "posicoes_em_risco": [],
        "trocas_sugeridas": [],
        "analise_ia": erro or "Sem dados para análise",
        "total_oportunidades": 0,
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
    }


def resumo_radar_texto(resultado: dict) -> str:
    """Formata o resultado do radar como texto legível para uso em prompts."""
    if not resultado:
        return "Radar: sem dados disponíveis."

    partes = ["=== RADAR DE OPORTUNIDADES APEX ==="]
    partes.append(f"Atualizado em: {resultado.get('atualizado_em', 'N/A')}")
    partes.append(f"Total de oportunidades identificadas: {resultado.get('total_oportunidades', 0)}")

    entradas = resultado.get("oportunidades_entrada", [])
    if entradas:
        partes.append(f"\n--- OPORTUNIDADES DE ENTRADA ({len(entradas)}) ---")
        for o in entradas:
            partes.append(f"  {o['ticker']:8s} | Score {o['score']:3d} | {o.get('motivo', '')}")

    riscos = resultado.get("posicoes_em_risco", [])
    if riscos:
        partes.append(f"\n--- POSIÇÕES EM RISCO ({len(riscos)}) ---")
        for r in riscos:
            partes.append(f"  {r['ticker']:8s} | Score {r['score']:3d} | {r.get('motivo', '')}")

    trocas = resultado.get("trocas_sugeridas", [])
    if trocas:
        partes.append(f"\n--- TROCAS SUGERIDAS ({len(trocas)}) ---")
        for t in trocas:
            partes.append(f"  Sair {t['sair']} -> Entrar {t['entrar']} | {t.get('motivo', '')}")

    analise = resultado.get("analise_ia", "")
    if analise:
        partes.append(f"\n--- ANÁLISE IA ---\n{analise}")

    return "\n".join(partes)

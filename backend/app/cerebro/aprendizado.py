"""
Módulo de Aprendizado — Trade Journal & Performance Analytics.

Registra decisões, gera post-mortem via IA e analisa performance histórica.
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.logger import logger
from app.models.trade_journal import TradeJournal


def registrar_decisao(
    db: Session,
    portfolio_id: int,
    ticker: str,
    tipo_operacao: str,
    acao_framework: str,
    motivo: str,
    preco: float,
    quantidade: float,
    valor_total: float,
    modulo: str | None = None,
    position_id: int | None = None,
    tese_id: int | None = None,
) -> TradeJournal:
    """Cria uma entrada no Trade Journal. Se for SAIDA, preenche resultado."""
    entry = TradeJournal(
        portfolio_id=portfolio_id,
        position_id=position_id,
        tese_id=tese_id,
        ticker=ticker,
        tipo_operacao=tipo_operacao,
        acao_framework=acao_framework,
        motivo=motivo,
        preco=preco,
        quantidade=quantidade,
        valor_total=valor_total,
        modulo=modulo,
    )

    if tipo_operacao == "SAIDA" and position_id:
        entrada = (
            db.query(TradeJournal)
            .filter(
                and_(
                    TradeJournal.position_id == position_id,
                    TradeJournal.tipo_operacao == "ENTRADA",
                )
            )
            .order_by(TradeJournal.created_at.asc())
            .first()
        )
        if entrada and entrada.preco and entrada.preco > 0:
            entry.resultado_pct = ((preco - entrada.preco) / entrada.preco) * 100
            entry.resultado_reais = valor_total - (entrada.quantidade or quantidade) * entrada.preco

            stop = None
            if position_id:
                from app.models.position import Position
                pos = db.query(Position).filter(Position.id == position_id).first()
                if pos and pos.stop_loss and pos.stop_loss > 0:
                    stop = pos.stop_loss
            if stop and entrada.preco != stop:
                risco = abs(entrada.preco - stop)
                retorno = preco - entrada.preco
                entry.rr_realizado = retorno / risco if risco > 0 else None

            delta = datetime.utcnow() - entrada.created_at
            entry.duracao_dias = delta.days

    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info("Trade journal: %s %s %s @ %.2f", tipo_operacao, ticker, acao_framework or "", preco or 0)
    return entry


async def gerar_post_mortem(db: Session, trade_id: int) -> str:
    """Gera análise post-mortem via IA para um trade encerrado (SAIDA)."""
    from app.cerebro.client import chat
    from app.cerebro.prompts import build_postmortem_prompt

    entry = db.query(TradeJournal).filter(TradeJournal.id == trade_id).first()
    if not entry:
        logger.warning("Post-mortem: trade_id=%d não encontrado", trade_id)
        return ""

    if entry.tipo_operacao != "SAIDA":
        logger.info("Post-mortem ignorado: trade_id=%d não é SAIDA (tipo=%s)", trade_id, entry.tipo_operacao)
        return ""

    entrada = None
    if entry.position_id:
        entrada = (
            db.query(TradeJournal)
            .filter(
                and_(
                    TradeJournal.position_id == entry.position_id,
                    TradeJournal.tipo_operacao == "ENTRADA",
                )
            )
            .order_by(TradeJournal.created_at.asc())
            .first()
        )

    detalhes = (
        f"Ticker: {entry.ticker}\n"
        f"Módulo: {entry.modulo or 'N/A'}\n"
        f"Preço de saída: R$ {entry.preco or 0:.2f}\n"
        f"Quantidade: {entry.quantidade or 0}\n"
        f"Valor total da saída: R$ {entry.valor_total or 0:.2f}\n"
        f"Resultado: {entry.resultado_pct or 0:.2f}% / R$ {entry.resultado_reais or 0:.2f}\n"
        f"R/R realizado: {entry.rr_realizado or 'N/A'}\n"
        f"Duração: {entry.duracao_dias or 'N/A'} dias\n"
        f"Motivo da saída: {entry.motivo or 'N/A'}\n"
        f"Ação do framework: {entry.acao_framework or 'N/A'}\n"
    )
    if entrada:
        detalhes += (
            f"\n--- Entrada ---\n"
            f"Preço de entrada: R$ {entrada.preco or 0:.2f}\n"
            f"Data de entrada: {entrada.created_at.strftime('%d/%m/%Y') if entrada.created_at else 'N/A'}\n"
            f"Motivo da entrada: {entrada.motivo or 'N/A'}\n"
            f"Ação do framework na entrada: {entrada.acao_framework or 'N/A'}\n"
        )

    system = build_postmortem_prompt()
    messages = [{"role": "user", "content": detalhes}]

    try:
        analise = await chat(system=system, messages=messages, max_tokens=1000)
    except Exception as e:
        logger.error("Erro ao gerar post-mortem para trade_id=%d: %s", trade_id, e)
        return ""

    entry.notas_post_mortem = analise
    db.commit()
    logger.info("Post-mortem gerado para trade_id=%d (%s)", trade_id, entry.ticker)
    return analise


def analisar_performance(db: Session, portfolio_id: int, periodo_dias: int = 90) -> dict:
    """Analisa performance do Trade Journal num período (default 90 dias)."""
    desde = datetime.utcnow() - timedelta(days=periodo_dias)

    trades = (
        db.query(TradeJournal)
        .filter(
            and_(
                TradeJournal.portfolio_id == portfolio_id,
                TradeJournal.tipo_operacao == "SAIDA",
                TradeJournal.created_at >= desde,
            )
        )
        .all()
    )

    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "rr_medio": 0.0,
            "melhor_trade": None,
            "pior_trade": None,
            "resultado_total_reais": 0.0,
            "por_modulo": {},
        }

    total = len(trades)
    wins = sum(1 for t in trades if (t.resultado_pct or 0) > 0)
    win_rate = (wins / total) * 100 if total else 0.0

    rrs = [t.rr_realizado for t in trades if t.rr_realizado is not None]
    rr_medio = sum(rrs) / len(rrs) if rrs else 0.0

    melhor = max(trades, key=lambda t: t.resultado_pct or float("-inf"))
    pior = min(trades, key=lambda t: t.resultado_pct or float("inf"))

    resultado_total = sum(t.resultado_reais or 0 for t in trades)

    por_modulo: dict[str, dict] = {}
    for t in trades:
        mod = t.modulo or "sem_modulo"
        if mod not in por_modulo:
            por_modulo[mod] = {"trades": 0, "wins": 0, "resultado_soma": 0.0}
        por_modulo[mod]["trades"] += 1
        if (t.resultado_pct or 0) > 0:
            por_modulo[mod]["wins"] += 1
        por_modulo[mod]["resultado_soma"] += t.resultado_pct or 0

    por_modulo_final = {}
    for mod, data in por_modulo.items():
        n = data["trades"]
        por_modulo_final[mod] = {
            "trades": n,
            "win_rate": (data["wins"] / n) * 100 if n else 0.0,
            "resultado_medio": data["resultado_soma"] / n if n else 0.0,
        }

    return {
        "total_trades": total,
        "win_rate": round(win_rate, 1),
        "rr_medio": round(rr_medio, 2),
        "melhor_trade": {"ticker": melhor.ticker, "resultado_pct": melhor.resultado_pct},
        "pior_trade": {"ticker": pior.ticker, "resultado_pct": pior.resultado_pct},
        "resultado_total_reais": round(resultado_total, 2),
        "por_modulo": por_modulo_final,
    }


def resumo_performance_texto(performance: dict) -> str:
    """Formata o dict de performance como texto legível para uso em prompts LLM."""
    if performance["total_trades"] == 0:
        return "Nenhum trade encerrado no período analisado."

    linhas = [
        f"Total de trades: {performance['total_trades']}",
        f"Win rate: {performance['win_rate']}%",
        f"R/R médio: {performance['rr_medio']}",
        f"Resultado total: R$ {performance['resultado_total_reais']:.2f}",
    ]

    melhor = performance.get("melhor_trade")
    if melhor:
        linhas.append(f"Melhor trade: {melhor['ticker']} ({melhor['resultado_pct']:.1f}%)")

    pior = performance.get("pior_trade")
    if pior:
        linhas.append(f"Pior trade: {pior['ticker']} ({pior['resultado_pct']:.1f}%)")

    por_modulo = performance.get("por_modulo", {})
    if por_modulo:
        linhas.append("\nPerformance por módulo:")
        for mod, data in por_modulo.items():
            linhas.append(
                f"  {mod}: {data['trades']} trades, "
                f"win rate {data['win_rate']:.1f}%, "
                f"resultado médio {data['resultado_medio']:.2f}%"
            )

    return "\n".join(linhas)

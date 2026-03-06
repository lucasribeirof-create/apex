"""
ContextoCerebro — O dossiê unificado do Cérebro APEX.

É o "sistema nervoso" da gestora: monta UMA VEZ o estado completo do mundo
e o distribui para todos os módulos que precisam dele — CEO Brain, Risk Manager,
Chat, Briefing, Análise de Posição.

Sem este módulo, cada função busca dados sozinha, de formas diferentes,
com campos diferentes. Com ele, todos falam a mesma língua.

Uso:
    ctx = await ContextoCerebro.montar(user_id=1, db=db)
    # Agora CEO, Chat, Briefing, Risk Manager recebem o mesmo ctx
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.logger import logger


# ─── Dataclass principal ──────────────────────────────────────────────────────

@dataclass
class ContextoCerebro:
    """
    Dossiê completo do estado do portfólio + mercado + perfil.
    Imutável após construção — todos os módulos leem, ninguém escreve.
    """

    # ── Perfil do investidor ───────────────────────────────────────────────
    user_id: int
    user_name: str
    estrategia: str                # CORE | ALPHA | RENDA | CUSTOM
    score_perfil: int              # 0–15 (onboarding_score)
    drawdown_tolerado: float       # % max drawdown aceito
    perfil_resumo: str             # texto livre do onboarding

    # ── Mandato (benchmarks) ──────────────────────────────────────────────
    benchmark_primario: str        # ex: "IBOV" ou "CDI"
    benchmark_secundario: str      # ex: "CDI" ou "IPCA+5"

    # ── Mercado atual ─────────────────────────────────────────────────────
    regime: str                    # BULL | MISTO | BEAR
    regime_motivo: str             # explicação do classificador
    macro: dict                    # selic, ipca, dolar, ibov, sp500, vix, ...

    # ── Carteira atual ────────────────────────────────────────────────────
    portfolio_id: int
    patrimonio_total: float
    patrimonio_inicio: float       # para cálculo de retorno total
    posicoes: list[dict]           # posições abertas com todos os campos

    alocacao_real: dict            # % real por módulo (calculado das posições)
    alocacao_alvo: dict            # % alvo por módulo (configuração do portfólio)
    desvios_alocacao: dict         # real - alvo por módulo (positivo = acima do alvo)

    pl_total_reais: float          # P&L total em R$
    pl_total_pct: float            # P&L total em %
    retorno_total_pct: float       # retorno desde patrimonio_inicio

    # ── Alertas pré-computados (input pronto para Risk Manager) ───────────
    stops_proximos: list[dict]     # {ticker, preco_atual, stop, distancia_pct}
    modulos_acima_alvo: list[str]  # módulos com alocacao_real > alvo + 5pp
    modulos_abaixo_alvo: list[str] # módulos com alocacao_real < alvo - 5pp
    posicoes_no_vermelho: list[dict]  # posições com P&L < -10%

    # ── Plano Estratégico (Estrategista) ──────────────────────────────────
    plano_estrategico: Optional[dict] = field(default=None)  # saída do plano.py

    # ── Macro enriquecido (v2) ──────────────────────────────────────────
    macro_context: Optional[object] = field(default=None)   # MacroContext completo
    regime_info: Optional[object] = field(default=None)     # RegimeInfo com sinais e flags
    narrativa_macro: str = ""                               # Narrativa diária gerada pela IA

    # ── Regime macro 4-estados (Fase 1 Cérebro Híbrido) ──────────────────
    regime_macro: str = "NEUTRO"          # RISK_ON_FORTE / MOD / NEUTRO / RISK_OFF
    regime_score: int = 50                # 0-100
    confianca_macro: int = 50             # 0-100
    fase_selic: str = "TRANSICAO"         # ALTA / PICO / TRANSICAO / QUEDA / VALE
    guardrails: dict = field(default_factory=dict)  # equity_max_pct, rf_min_pct, caixa_min_pct

    # ── Ranking setorial (Fase 2 Cérebro Híbrido) ────────────────────────
    ranking_setorial: Optional[object] = field(default=None)  # RankingSetorial de setor.py
    # ── Risco & Sizing (Fase 4 Cérebro Híbrido) ─────────────────────────────
    circuit_breaker: Optional[object] = field(default=None)   # CircuitBreakerState
    heat: Optional[object] = field(default=None)              # HeatState
    cb_modifier: float = 1.0     # sizing modifier (1.0=normal, 0.5=CB nível 1, 0.0=pausa)
    # ── Hold & Kill Switch (Fase 5 Cérebro Híbrido) ──────────────────────
    kill_switch: Optional[object] = field(default=None)       # KillSwitchState
    watchlist_candidates: list = field(default_factory=list)   # WatchlistCandidate summaries
    # ── Metadados ─────────────────────────────────────────────────────────
    gerado_em: str = ""            # ISO timestamp de quando o contexto foi montado
    modulos_ativos: list[str] = field(default_factory=list)  # módulos configurados com alvo > 0

    # ─── Métodos de conveniência ──────────────────────────────────────────

    def tem_posicoes(self) -> bool:
        return len(self.posicoes) > 0

    def posicoes_por_modulo(self, modulo: str) -> list[dict]:
        return [p for p in self.posicoes if (p.get("modulo") or "").lower() == modulo.lower()]

    def resumo_carteira_texto(self) -> str:
        """Texto compacto da carteira para injetar em prompts."""
        if not self.posicoes:
            return "Carteira vazia — nenhuma posição aberta."
        linhas = []
        for p in self.posicoes:
            modulo = p.get("modulo") or "-"
            pl = p.get("pl_percentual") or 0
            ticker = p.get("ticker") or "?"
            tipo = p.get("tipo") or "-"
            preco_med = p.get("preco_medio") or 0
            preco_atual = p.get("preco_atual") or preco_med
            moeda = p.get("moeda") or "BRL"
            mercado = p.get("mercado") or ""

            if moeda == "USD":
                pm_usd = p.get("preco_medio_usd") or preco_med
                linha = f"- {ticker} ({tipo}, {modulo}{', ' + mercado if mercado else ''}): PM US${pm_usd:,.2f}"
            else:
                linha = (f"- {ticker} ({tipo}, {modulo}): "
                         f"R${preco_med:,.2f} → R${preco_atual:,.2f} ({pl:+.1f}%)")
                if p.get("stop_loss"):
                    linha += f" | stop R${p['stop_loss']:,.2f}"

            tese = p.get("tese")
            if tese:
                linha += f'\n  Tese: "{tese[:80]}{"..." if len(tese) > 80 else ""}"'
            linhas.append(linha)
        return "\n".join(linhas)

    def resumo_macro_texto(self) -> str:
        """Texto de macro para injetar em prompts — usa MacroContext se disponível."""
        if self.macro_context and hasattr(self.macro_context, "resumo_texto"):
            return self.macro_context.resumo_texto()

        m = self.macro
        partes = []
        if m.get("selic") is not None:
            partes.append(f"Selic {m['selic']:.2f}%")
        if m.get("ipca") is not None:
            partes.append(f"IPCA {m['ipca']:.2f}%")
        if m.get("dolar"):
            partes.append(f"USD/BRL {m['dolar']:.2f}")
        if m.get("ibov"):
            partes.append(f"IBOV {m['ibov']:,.0f} ({m.get('ibov_variacao', 0):+.2f}%)")
        if m.get("sp500"):
            partes.append(f"S&P500 {m['sp500']:,.0f} ({m.get('sp500_variacao', 0):+.2f}%)")
        if m.get("vix"):
            partes.append(f"VIX {m['vix']:.1f}")
        return " | ".join(partes) if partes else "macro indisponível"

    def alertas_criticos(self) -> list[str]:
        """Lista de alertas urgentes em linguagem natural."""
        alertas = []

        # Kill switch macro (Phase 5) — mais urgente, vem primeiro
        if self.kill_switch and self.kill_switch.ativo:
            ks = self.kill_switch
            urgencia = "PAUSA OBRIGATÓRIA" if ks.nivel >= 2 else "ALERTA"
            alertas.append(
                f"🚨 KILL SWITCH MACRO ({urgencia}): {ks.motivo} — {ks.recomendacao}"
            )

        # Circuit breaker (Phase 4)
        if self.circuit_breaker and hasattr(self.circuit_breaker, "nivel") and self.circuit_breaker.nivel >= 2:
            alertas.append(
                f"🔴 CIRCUIT BREAKER NÍVEL {self.circuit_breaker.nivel}: {self.circuit_breaker.motivo}"
            )

        # Heat (Phase 4)
        if self.heat and hasattr(self.heat, "pode_operar") and not self.heat.pode_operar:
            alertas.append(
                f"🔴 HEAT {self.heat.heat_pct:.1f}% — OPERAÇÕES BLOQUEADAS (limite 6%)"
            )

        for s in self.stops_proximos:
            alertas.append(
                f"{s['ticker']} a {s['distancia_pct']:.1f}% do stop "
                f"(atual R${s['preco_atual']:.2f} / stop R${s['stop']:.2f})"
            )
        for m in self.modulos_acima_alvo:
            real = self.alocacao_real.get(m, 0)
            alvo = self.alocacao_alvo.get(m, 0)
            alertas.append(f"Módulo {m} acima do alvo: {real:.1f}% real vs {alvo:.1f}% alvo (+{real-alvo:.1f}pp)")
        for p in self.posicoes_no_vermelho:
            alertas.append(
                f"{p['ticker']} com perda de {p['pl_percentual']:.1f}% "
                f"(R${abs(p.get('pl_reais', 0)):,.0f} negativos)"
            )
        return alertas


# ─── Factory assíncrono ───────────────────────────────────────────────────────

async def montar(
    db: Session,
    user_id: Optional[int] = None,
    portfolio_id: Optional[int] = None,
) -> ContextoCerebro:
    """
    Monta o ContextoCerebro completo de forma assíncrona.
    Paralleliza as chamadas de dados onde possível.

    Args:
        db: sessão SQLAlchemy
        user_id: ID do usuário (None = primeiro usuário, modo dev)
        portfolio_id: força um portfólio específico (None = portfólio ativo)
    """
    from app.models import User, Portfolio, Position
    from app.api.deps import get_portfolio_ativo
    from app.data import get_macro_br, get_macro_global
    from app.data.cache import cache as _cache

    # ── Usuário e portfólio ──────────────────────────────────────────────
    # Quando só portfolio_id é passado (ex: morning briefing), deriva o usuário
    # a partir do dono do portfólio para evitar falsos "Portfólio não encontrado".
    if user_id:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("Usuário não encontrado")
        if portfolio_id:
            portfolio = db.query(Portfolio).filter(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == user.id,
            ).first()
        else:
            portfolio = get_portfolio_ativo(user, db)
    elif portfolio_id:
        portfolio = db.query(Portfolio).filter(Portfolio.id == portfolio_id).first()
        if not portfolio:
            raise ValueError("Portfólio não encontrado")
        user = db.query(User).filter(User.id == portfolio.user_id).first()
        if not user:
            raise ValueError("Usuário não encontrado")
    else:
        user = db.query(User).first()
        if not user:
            raise ValueError("Usuário não encontrado")
        portfolio = get_portfolio_ativo(user, db)

    if not portfolio:
        raise ValueError("Portfólio não encontrado")

    # ── Posições ─────────────────────────────────────────────────────────
    posicoes_db = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
    ).all()

    posicoes = [
        {
            "id":              p.id,
            "ticker":          p.ticker,
            "nome":            getattr(p, "nome", p.ticker),
            "tipo":            p.tipo,
            "modulo":          p.modulo,
            "quantidade":      p.quantidade or 0,
            "preco_medio":     p.preco_medio or 0,
            "preco_atual":     p.preco_atual or p.preco_medio or 0,
            "valor_investido": p.valor_investido or 0,
            "valor_atual":     p.valor_atual or ((p.preco_atual or p.preco_medio or 0) * (p.quantidade or 0)),
            "pl_reais":        p.pl_reais or 0,
            "pl_percentual":   p.pl_percentual or 0,
            "stop_loss":       p.stop_loss,
            "alvo_1":          p.alvo_1,
            "alvo_2":          p.alvo_2,
            "tese":            getattr(p, "tese", None),
            "mercado":         getattr(p, "mercado", None),
            "moeda":           getattr(p, "moeda", "BRL") or "BRL",
            "preco_medio_usd": getattr(p, "preco_medio_usd", None),
            "apex_score":      getattr(p, "apex_score", None),
            "created_at":      p.created_at.isoformat() if p.created_at else None,
            "data_entrada":    p.data_entrada.isoformat() if getattr(p, "data_entrada", None) else None,
        }
        for p in posicoes_db
    ]

    # ── Macro enriquecido (v2) — MacroEngine ─────────────────────────────
    from app.cerebro.macro import montar_macro, MacroContext

    macro_context_obj: Optional[MacroContext] = None
    try:
        macro_context_obj = await montar_macro()
    except Exception as e:
        logger.warning("contexto_cerebro: MacroEngine falhou: %s", e)

    # Macro legado (dict) — manter compatibilidade com código existente
    macro_br_task = asyncio.create_task(get_macro_br())
    macro_global_task = asyncio.create_task(get_macro_global())
    macro_br, macro_global = await asyncio.gather(macro_br_task, macro_global_task, return_exceptions=True)

    if isinstance(macro_br, Exception):
        logger.warning("contexto_cerebro: macro_br falhou: %s", macro_br)
        macro_br = {}
    if isinstance(macro_global, Exception):
        logger.warning("contexto_cerebro: macro_global falhou: %s", macro_global)
        macro_global = {}

    macro = {**(macro_br or {}), **(macro_global or {})}

    # ── Regime enriquecido (v2) ────────────────────────────────────────────
    from app.core.regime import RegimeInfo as _RegimeInfo
    regime_info_obj: Optional[_RegimeInfo] = None

    _regime_cached = _cache.get("market:regime")
    regime_str = "MISTO"
    regime_motivo = "Regime não calculado ainda"
    if _regime_cached:
        if isinstance(_regime_cached, _RegimeInfo):
            regime_info_obj = _regime_cached
            regime_str = str(regime_info_obj.regime)
            regime_motivo = regime_info_obj.regime_motivo
        else:
            regime_str = str(_regime_cached.get("regime", "MISTO"))
            regime_motivo = str(_regime_cached.get("motivo", ""))

    if regime_str == "MISTO" and getattr(portfolio, "regime", None):
        regime_str = portfolio.regime

    # ── Narrativa macro (cache 12h) ─────────────────────────────────────
    narrativa = ""
    if macro_context_obj:
        try:
            from app.cerebro.narrativa import gerar_narrativa
            narrativa = await gerar_narrativa(
                macro_context_obj,
                regime_info=regime_info_obj,
            )
        except Exception as e:
            logger.debug("contexto_cerebro: narrativa macro falhou: %s", e)

    # ── P&L total ─────────────────────────────────────────────────────────
    pl_total_reais = sum(p["pl_reais"] for p in posicoes)
    patrimonio = portfolio.patrimonio_total or 0
    patrimonio_inicio = getattr(portfolio, "patrimonio_inicio", None) or patrimonio
    pl_total_pct = (pl_total_reais / patrimonio_inicio * 100) if patrimonio_inicio > 0 else 0
    retorno_total_pct = ((patrimonio - patrimonio_inicio) / patrimonio_inicio * 100) if patrimonio_inicio > 0 else 0

    # ── Alocação real vs alvo ─────────────────────────────────────────────
    alocacao_real = _calcular_alocacao_real(posicoes, patrimonio)
    alocacao_alvo = _extrair_alocacao_alvo(portfolio)
    desvios = {m: round(alocacao_real.get(m, 0) - alocacao_alvo.get(m, 0), 1) for m in alocacao_alvo}

    # ── Alertas pré-computados ────────────────────────────────────────────
    stops_proximos = _detectar_stops_proximos(posicoes, limiar_pct=5.0)
    modulos_acima = [m for m, d in desvios.items() if d > 5.0]
    modulos_abaixo = [m for m, d in desvios.items() if d < -5.0]
    posicoes_vermelho = [
        p for p in posicoes
        if p["pl_percentual"] < -10 and p["ticker"] not in ("CAIXA", "TESES")
    ]

    # ── Benchmarks por estratégia ─────────────────────────────────────────
    _benchmarks = {
        "CORE":   ("IBOV", "CDI"),
        "ALPHA":  ("IBOV", "IBOV+5%"),
        "RENDA":  ("CDI",  "IPCA+5%"),
        "CUSTOM": ("IBOV", "CDI"),
    }
    estrategia = (user.estrategia or "CORE").upper()
    bench_prim, bench_sec = _benchmarks.get(estrategia, ("IBOV", "CDI"))

    # ── Drawdown tolerado ────────────────────────────────────────────────
    _drawdown_map = {"CORE": 15.0, "RENDA": 10.0, "ALPHA": 30.0, "CUSTOM": 20.0}

    # ── Plano estratégico do Estrategista ──────────────────────────────────
    plano_estrategico = getattr(user, "plano_estrategico", None)

    # Auto-refresh: verifica se o plano precisa ser atualizado.
    # Dispara em background para NÃO bloquear o contexto (evita +50s de latência).
    # O plano atualizado será usado na PRÓXIMA chamada.
    try:
        from app.cerebro.plano import deve_atualizar_plano

        if deve_atualizar_plano(plano_estrategico, patrimonio):
            logger.info("contexto_cerebro: plano estratégico stale — disparando refresh em background")
            _disparar_refresh_plano_bg(
                user_id=user.id,
                patrimonio=patrimonio,
                estrategia=estrategia,
                user_name=user.name or "Investidor",
                objetivo_tipo=getattr(user, "objetivo_tipo", None) or "livre",
                objetivo_valor=getattr(user, "objetivo_valor", None),
                objetivo_prazo=getattr(user, "objetivo_prazo", None),
                onboarding_respostas=getattr(user, "onboarding_respostas", None) or {},
                onboarding_score=getattr(user, "onboarding_score", None) or 7,
            )
    except ImportError:
        pass

    # ── Regime macro 4-estados (do MacroContext) ─────────────────────────
    _regime_macro = "NEUTRO"
    _regime_score = 50
    _confianca = 50
    _fase_selic = "TRANSICAO"
    _guardrails = {}
    if macro_context_obj:
        _regime_macro = getattr(macro_context_obj, "regime_macro", "NEUTRO")
        _regime_score = getattr(macro_context_obj, "regime_score", 50)
        _confianca = getattr(macro_context_obj, "confianca", 50)
        _fase_selic = getattr(macro_context_obj, "fase_selic", "TRANSICAO")
        _guardrails = getattr(macro_context_obj, "guardrails", {})

    # ── Ranking setorial (Fase 2 — depende de MacroContext) ─────────────
    _ranking_setorial = None
    if macro_context_obj:
        try:
            from app.cerebro.setor import montar_ranking
            _ranking_setorial = await montar_ranking(macro_context_obj)
        except Exception as e:
            logger.warning("contexto_cerebro: ranking setorial falhou: %s", e)

    # ── Kill Switch macro (Fase 5) ──────────────────────────────────────
    _kill_switch = None
    try:
        from app.cerebro.hold import avaliar_kill_switch
        _kill_switch = avaliar_kill_switch(_regime_macro, _confianca, _regime_score)
    except Exception as e:
        logger.warning("contexto_cerebro: kill switch falhou: %s", e)

    return ContextoCerebro(
        # Perfil
        user_id=user.id,
        user_name=user.name or "Investidor",
        estrategia=estrategia,
        score_perfil=getattr(user, "onboarding_score", None) or 7,
        drawdown_tolerado=_drawdown_map.get(estrategia, 15.0),
        perfil_resumo=getattr(user, "estrategia_resumo", None) or f"Perfil {estrategia}",
        # Mandato
        benchmark_primario=bench_prim,
        benchmark_secundario=bench_sec,
        # Mercado
        regime=regime_str,
        regime_motivo=regime_motivo,
        macro=macro,
        # Macro enriquecido (v2)
        macro_context=macro_context_obj,
        regime_info=regime_info_obj,
        narrativa_macro=narrativa or "",
        # Regime macro 4-estados
        regime_macro=_regime_macro,
        regime_score=_regime_score,
        confianca_macro=_confianca,
        fase_selic=_fase_selic,
        guardrails=_guardrails,
        # Ranking setorial (Fase 2)
        ranking_setorial=_ranking_setorial,
        # Kill Switch (Fase 5)
        kill_switch=_kill_switch,
        # Carteira
        portfolio_id=portfolio.id,
        patrimonio_total=patrimonio,
        patrimonio_inicio=patrimonio_inicio,
        posicoes=posicoes,
        alocacao_real=alocacao_real,
        alocacao_alvo=alocacao_alvo,
        desvios_alocacao=desvios,
        pl_total_reais=round(pl_total_reais, 2),
        pl_total_pct=round(pl_total_pct, 2),
        retorno_total_pct=round(retorno_total_pct, 2),
        # Alertas
        stops_proximos=stops_proximos,
        modulos_acima_alvo=modulos_acima,
        modulos_abaixo_alvo=modulos_abaixo,
        posicoes_no_vermelho=posicoes_vermelho,
        # Plano estratégico
        plano_estrategico=plano_estrategico,
        # Meta
        gerado_em=datetime.now(timezone.utc).isoformat(),
        modulos_ativos=_get_modulos_ativos(portfolio),
    )


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _calcular_alocacao_real(posicoes: list[dict], patrimonio: float) -> dict:
    modulos = {
        "etfs": 0.0, "fiis": 0.0, "renda_fixa": 0.0, "momentum": 0.0,
        "wheel": 0.0, "alpha": 0.0, "dividendos": 0.0, "teses": 0.0, "caixa": 0.0,
    }
    if patrimonio <= 0:
        return modulos
    for p in posicoes:
        modulo = (p.get("modulo") or "caixa").lower()
        valor = p.get("valor_atual") or p.get("valor_investido") or 0
        if modulo in modulos:
            modulos[modulo] += (valor / patrimonio) * 100
    return {k: round(v, 1) for k, v in modulos.items()}


def _extrair_alocacao_alvo(portfolio) -> dict:
    return {
        "etfs":       getattr(portfolio, "alvo_etfs", 0) or 0,
        "fiis":       getattr(portfolio, "alvo_fiis", 0) or 0,
        "renda_fixa": getattr(portfolio, "alvo_renda_fixa", 0) or 0,
        "momentum":   getattr(portfolio, "alvo_momentum", 0) or 0,
        "wheel":      getattr(portfolio, "alvo_wheel", 0) or 0,
        "alpha":      getattr(portfolio, "alvo_alpha", 0) or 0,
        "dividendos": getattr(portfolio, "alvo_dividendos", 0) or 0,
        "teses":      getattr(portfolio, "alvo_teses", 0) or 0,
        "caixa":      getattr(portfolio, "alvo_caixa", 0) or 0,
    }


def _get_modulos_ativos(portfolio) -> list[str]:
    modulos = []
    if getattr(portfolio, "alvo_etfs", 0) > 0:       modulos.append("ETFs")
    if getattr(portfolio, "alvo_fiis", 0) > 0:        modulos.append("FIIs")
    if getattr(portfolio, "alvo_renda_fixa", 0) > 0:  modulos.append("Renda Fixa")
    if getattr(portfolio, "alvo_momentum", 0) > 0:    modulos.append("Momentum")
    if getattr(portfolio, "alvo_wheel", 0) > 0:       modulos.append("Wheel")
    if getattr(portfolio, "alvo_alpha", 0) > 0:       modulos.append("Alpha")
    if getattr(portfolio, "alvo_dividendos", 0) > 0:  modulos.append("Dividendos")
    if getattr(portfolio, "alvo_teses", 0) > 0:       modulos.append("Teses")
    return modulos


def _detectar_stops_proximos(posicoes: list[dict], limiar_pct: float = 5.0) -> list[dict]:
    """Posições onde o preço atual está dentro de `limiar_pct`% do stop loss."""
    resultado = []
    for p in posicoes:
        stop = p.get("stop_loss")
        preco = p.get("preco_atual") or p.get("preco_medio") or 0
        if not stop or not preco or stop <= 0 or preco <= 0:
            continue
        distancia_pct = ((preco - stop) / preco) * 100
        if 0 <= distancia_pct <= limiar_pct:
            resultado.append({
                "ticker":         p["ticker"],
                "modulo":         p.get("modulo", ""),
                "preco_atual":    preco,
                "stop":           stop,
                "distancia_pct":  round(distancia_pct, 2),
                "urgente":        distancia_pct <= 2.0,
            })
    return sorted(resultado, key=lambda x: x["distancia_pct"])


# ─── Background refresh do plano estratégico ──────────────────────────────────

_refresh_task: asyncio.Task | None = None  # evita disparos duplicados


def _disparar_refresh_plano_bg(**kwargs) -> None:
    """Dispara o refresh do plano em background (fire-and-forget, sem bloquear o contexto)."""
    global _refresh_task
    # Não dispara se já tem um refresh rodando
    if _refresh_task is not None and not _refresh_task.done():
        logger.debug("contexto_cerebro: refresh do plano já em andamento, ignorando")
        return
    _refresh_task = asyncio.create_task(_refresh_plano_background(**kwargs))


async def _refresh_plano_background(
    user_id: int,
    patrimonio: float,
    estrategia: str,
    user_name: str,
    objetivo_tipo: str,
    objetivo_valor: float | None,
    objetivo_prazo: str | None,
    onboarding_respostas: dict,
    onboarding_score: int,
) -> None:
    """Task background que regenera o plano e persiste no DB."""
    try:
        from app.cerebro.plano import diagnosticar as _diagnosticar_plano

        novo_plano = await asyncio.wait_for(
            _diagnosticar_plano(
                nome=user_name,
                patrimonio_atual=patrimonio,
                objetivo_tipo=objetivo_tipo,
                objetivo_valor=objetivo_valor,
                objetivo_prazo=objetivo_prazo,
                estrategia_atual=estrategia,
                onboarding_respostas=onboarding_respostas,
                onboarding_score=onboarding_score,
            ),
            timeout=50.0,
        )

        # Persiste no DB (sessão nova — não interfere com a sessão do request)
        from app.models.base import SessionLocal
        from app.models import User

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.plano_estrategico = novo_plano.to_dict()
                db.commit()
                logger.info("contexto_cerebro: plano estratégico atualizado em background (user %s)", user_id)
        finally:
            db.close()
    except Exception as e:
        logger.warning("contexto_cerebro: refresh background do plano falhou: %s", e)

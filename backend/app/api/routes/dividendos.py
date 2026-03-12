"""Rotas de Dividendos — resumo, ativos, histórico e calendário.
Usa dividend_merger para cruzar BRAPI (payment_date, tipo) + yFinance (ex_date).
Dados persistidos em SQLite (tabela dividend_events) como cache durável.
"""
from typing import Optional
from datetime import datetime, timedelta
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.api.deps import get_db, get_user_id, get_portfolio_ativo
from app.models import User, Position
from app.data.dividend_merger import get_merged_dividends
from app.logger import logger
import json

router = APIRouter(prefix="/dividendos", tags=["dividendos"])


class _NumpySafeEncoder(json.JSONEncoder):
    def default(self, obj):
        try:
            import numpy as np
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj) if not (obj != obj) else None
            if isinstance(obj, np.ndarray):
                return obj.tolist()
        except ImportError:
            pass
        return super().default(obj)


def _sanitize(obj):
    return json.loads(json.dumps(obj, cls=_NumpySafeEncoder, default=str))


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", ""))
    except Exception:
        return None


async def _get_positions_with_merged_divs(db: Session, user_id):
    """Retorna posições ativas com dividendos mergeados (BRAPI + yFinance)."""
    user = (db.query(User).filter(User.id == user_id).first() if user_id
            else db.query(User).first())
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado")

    portfolio = get_portfolio_ativo(user, db)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfólio não encontrado")

    posicoes = db.query(Position).filter(
        Position.portfolio_id == portfolio.id,
        Position.ativa == True,
        Position.tipo.in_(["ACAO", "FII", "ETF", "BDR"]),
    ).all()

    from app.data.brapi import get_fundamentals

    result = []
    for pos in posicoes:
        # Buscar dividendos mergeados (BRAPI + yFinance → SQLite)
        divs = await get_merged_dividends(pos.ticker, db)

        # Setor vem dos fundamentals (cache 1h na BRAPI)
        fund = await get_fundamentals(pos.ticker)
        sector = "Outros"
        if fund:
            sector = fund.get("sector") or fund.get("sectorKey") or "Outros"

        result.append({
            "pos": pos,
            "divs": divs,  # lista de dicts com ex_date, payment_date, rate, tipo_provento, source, confidence
            "sector": sector,
        })
    return result


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _div_effective_date(d: dict) -> Optional[datetime]:
    """Data efetiva de um evento (payment_date preferido, fallback ex_date)."""
    return _parse_date(d.get("payment_date")) or _parse_date(d.get("ex_date"))


def _divs_12m(divs: list[dict], hoje: datetime) -> list[dict]:
    """Filtra dividendos dos últimos 12 meses."""
    cutoff = hoje - timedelta(days=365)
    result = []
    for d in divs:
        dt = _div_effective_date(d)
        if dt and dt > cutoff:
            result.append({**d, "_dt": dt})
    result.sort(key=lambda x: x["_dt"])
    return result


def _estimate_frequency(recentes: list[dict], tipo: str) -> tuple[float, str]:
    """Retorna (intervalo_medio_dias, label_frequencia)."""
    if len(recentes) >= 2:
        gaps = [(recentes[i]["_dt"] - recentes[i-1]["_dt"]).days for i in range(1, len(recentes))]
        intervalo = sum(gaps) / len(gaps)
    else:
        intervalo = 30.0 if tipo == "FII" else 90.0

    if intervalo < 45:
        label = "mensal"
    elif intervalo < 100:
        label = "trimestral"
    elif intervalo < 200:
        label = "semestral"
    else:
        label = "anual"
    return intervalo, label


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/resumo")
async def get_dividendos_resumo(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Cards de resumo: total 12m, projeção mensal, yield on cost, DY médio."""
    try:
        data = await _get_positions_with_merged_divs(db, user_id)
        if not data:
            return JSONResponse(content=_sanitize({
                "total_12m": 0, "projecao_mensal": 0, "yield_on_cost": 0,
                "dy_medio": 0, "ativos_pagadores": 0, "total_ativos": 0,
            }))

        hoje = datetime.now()
        total_12m = 0
        total_investido = 0
        total_dy_peso = 0
        total_peso = 0
        ativos_pagadores = 0

        for item in data:
            pos = item["pos"]
            recentes = _divs_12m(item["divs"], hoje)

            rates = [d["rate"] for d in recentes]
            if rates:
                ativos_pagadores += 1
                total_div = sum(rates) * (pos.quantidade or 0)
                total_12m += total_div

                if pos.preco_atual and pos.quantidade:
                    dy = sum(rates) / pos.preco_atual * 100
                    peso = pos.preco_atual * pos.quantidade
                    total_dy_peso += dy * peso
                    total_peso += peso

            total_investido += pos.valor_investido or 0

        projecao_mensal = total_12m / 12 if total_12m else 0
        yield_on_cost = (total_12m / total_investido * 100) if total_investido else 0
        dy_medio = (total_dy_peso / total_peso) if total_peso else 0

        return JSONResponse(content=_sanitize({
            "total_12m": round(total_12m, 2),
            "projecao_mensal": round(projecao_mensal, 2),
            "yield_on_cost": round(yield_on_cost, 2),
            "dy_medio": round(dy_medio, 2),
            "ativos_pagadores": ativos_pagadores,
            "total_ativos": len(data),
        }))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("dividendos/resumo falhou: %s", e)
        return JSONResponse(content=_sanitize({
            "total_12m": 0, "projecao_mensal": 0, "yield_on_cost": 0,
            "dy_medio": 0, "ativos_pagadores": 0, "total_ativos": 0,
        }))


@router.get("/ativos")
async def get_dividendos_ativos(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Ativos que pagam dividendo agrupados por setor, com ex-date e payment-date."""
    try:
        data = await _get_positions_with_merged_divs(db, user_id)
        if not data:
            return JSONResponse(content=_sanitize({"setores": []}))

        hoje = datetime.now()
        setores_map = defaultdict(list)

        for item in data:
            pos = item["pos"]
            sector = item["sector"]
            recentes = _divs_12m(item["divs"], hoje)

            if not recentes:
                continue

            total_12m = sum(r["rate"] for r in recentes)
            dy_12m = (total_12m / pos.preco_atual * 100) if pos.preco_atual else 0
            ultimo = recentes[-1]
            intervalo, freq = _estimate_frequency(recentes, pos.tipo)

            # Contar sources e calcular confiança média
            merged_count = sum(1 for r in recentes if r.get("source") == "merged")
            avg_confidence = sum(r.get("confidence", 0.5) for r in recentes) / len(recentes) if recentes else 0

            setores_map[sector].append({
                "ticker": pos.ticker,
                "nome": pos.nome or pos.ticker,
                "tipo": pos.tipo,
                "quantidade": pos.quantidade or 0,
                "preco_atual": round(pos.preco_atual or 0, 2),
                "valor_posicao": round((pos.preco_atual or 0) * (pos.quantidade or 0), 2),
                "dy_12m": round(dy_12m, 2),
                "total_12m_por_cota": round(total_12m, 4),
                "total_12m_reais": round(total_12m * (pos.quantidade or 0), 2),
                "ultimo_pagamento": ultimo.get("payment_date"),
                "ultimo_ex_date": ultimo.get("ex_date"),
                "ultimo_valor": round(ultimo["rate"], 4),
                "ultimo_tipo": ultimo.get("tipo_provento", "DIVIDENDO"),
                "frequencia": freq,
                "pagamentos_12m": len(recentes),
                "dados_cruzados": merged_count,
                "confianca": round(avg_confidence * 100),
            })

        setores = []
        for setor_nome, ativos in sorted(setores_map.items()):
            total_setor = sum(a["total_12m_reais"] for a in ativos)
            ativos.sort(key=lambda x: x["dy_12m"], reverse=True)
            setores.append({
                "setor": setor_nome,
                "ativos": ativos,
                "total_12m": round(total_setor, 2),
                "quantidade_ativos": len(ativos),
            })

        setores.sort(key=lambda x: x["total_12m"], reverse=True)
        return JSONResponse(content=_sanitize({"setores": setores}))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("dividendos/ativos falhou: %s", e)
        return JSONResponse(content=_sanitize({"setores": []}))


@router.get("/historico")
async def get_dividendos_historico(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Histórico de dividendos recebidos agrupado por mês/ano, com ex-date."""
    try:
        data = await _get_positions_with_merged_divs(db, user_id)
        if not data:
            return JSONResponse(content=_sanitize({"meses": [], "anos": []}))

        meses_map = defaultdict(lambda: {"total": 0, "detalhes": []})

        for item in data:
            pos = item["pos"]
            for d in item["divs"]:
                dt = _div_effective_date(d)
                if not dt:
                    continue
                rate = d.get("rate", 0)
                valor = rate * (pos.quantidade or 0)
                chave_mes = dt.strftime("%Y-%m")

                meses_map[chave_mes]["total"] += valor
                meses_map[chave_mes]["detalhes"].append({
                    "ticker": pos.ticker,
                    "tipo": pos.tipo,
                    "payment_date": d.get("payment_date"),
                    "ex_date": d.get("ex_date"),
                    "tipo_provento": d.get("tipo_provento", "DIVIDENDO"),
                    "valor_por_cota": round(rate, 4),
                    "quantidade": pos.quantidade or 0,
                    "valor_total": round(valor, 2),
                    "source": d.get("source", "brapi"),
                })

        meses = []
        for chave, info in sorted(meses_map.items(), reverse=True):
            info["detalhes"].sort(key=lambda x: x.get("payment_date") or x.get("ex_date") or "", reverse=True)
            meses.append({
                "mes": chave,
                "total": round(info["total"], 2),
                "detalhes": info["detalhes"],
            })

        anos_map = defaultdict(float)
        for m in meses:
            ano = m["mes"][:4]
            anos_map[ano] += m["total"]

        anos = [{"ano": a, "total": round(t, 2)} for a, t in sorted(anos_map.items(), reverse=True)]

        return JSONResponse(content=_sanitize({"meses": meses, "anos": anos}))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("dividendos/historico falhou: %s", e)
        return JSONResponse(content=_sanitize({"meses": [], "anos": []}))


@router.get("/calendario")
async def get_dividendos_calendario(user_id: Optional[int] = Depends(get_user_id), db: Session = Depends(get_db)):
    """Calendário de próximos dividendos projetados, com ex-date real quando disponível."""
    try:
        data = await _get_positions_with_merged_divs(db, user_id)
        if not data:
            return JSONResponse(content=_sanitize({"proximos": [], "total_projetado_30d": 0}))

        hoje = datetime.now()
        proximos = []

        for item in data:
            pos = item["pos"]
            recentes = _divs_12m(item["divs"], hoje)

            if not recentes:
                continue

            media_rate = sum(r["rate"] for r in recentes) / len(recentes)
            total_12m = sum(r["rate"] for r in recentes)
            ultimo = recentes[-1]
            intervalo, freq = _estimate_frequency(recentes, pos.tipo)

            # Projetar próximo: usar ex_date se disponível, senão payment_date
            base_date = _parse_date(ultimo.get("ex_date")) or ultimo["_dt"]
            proximo_dt = base_date + timedelta(days=intervalo)
            while proximo_dt < hoje:
                proximo_dt += timedelta(days=intervalo)

            # Estimar payment_date (~5 dias após ex_date para BR)
            proximo_payment = proximo_dt + timedelta(days=5) if freq != "anual" else proximo_dt + timedelta(days=30)

            valor_estimado = media_rate * (pos.quantidade or 0)
            dy_12m = (total_12m / pos.preco_atual * 100) if pos.preco_atual else 0

            # Confiança: merged = alta, single-source = média
            merged_pct = sum(1 for r in recentes if r.get("source") == "merged") / len(recentes)

            proximos.append({
                "ticker": pos.ticker,
                "tipo": pos.tipo,
                "data_ex_estimada": proximo_dt.strftime("%Y-%m-%d"),
                "data_pagamento_estimada": proximo_payment.strftime("%Y-%m-%d"),
                "dias_restantes": (proximo_dt - hoje).days,
                "valor_por_cota": round(media_rate, 4),
                "quantidade": pos.quantidade or 0,
                "valor_estimado": round(valor_estimado, 2),
                "dy_12m": round(dy_12m, 2),
                "frequencia": freq,
                "confianca": "alta" if merged_pct > 0.5 else "media",
                "ultimo_tipo": ultimo.get("tipo_provento", "DIVIDENDO"),
            })

        proximos.sort(key=lambda x: x["dias_restantes"])
        total_30d = sum(p["valor_estimado"] for p in proximos if p["dias_restantes"] <= 30)

        return JSONResponse(content=_sanitize({"proximos": proximos, "total_projetado_30d": round(total_30d, 2)}))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("dividendos/calendario falhou: %s", e)
        return JSONResponse(content=_sanitize({"proximos": [], "total_projetado_30d": 0}))

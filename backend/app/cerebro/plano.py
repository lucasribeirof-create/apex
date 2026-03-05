"""
Estrategista do Cérebro APEX — Raciocínio de Metas e Fases.

Este módulo é o "pensador de longo prazo" do cérebro. Ele:
1. Recebe o perfil completo do usuário em linguagem natural (sem template rígido)
2. Analisa a viabilidade real da meta declarada
3. Identifica a fase atual do investidor (crescimento / transição / colheita)
4. Define a estratégia correta para a fase — não para o perfil de risco isolado
5. Traça marcos concretos de patrimônio vs. renda possível
6. Gera um plano narrativo que orienta TODAS as decisões futuras do CEO

O plano gerado fica salvo em User.plano_estrategico e é injetado no CEO Brain
a cada tomada de decisão de portfólio.

Diferença fundamental vs. o CEO Brain:
  - CEO Brain: operacional — monta a carteira da semana/mês
  - Estrategista: estratégico — define PARA ONDE estamos indo e POR QUÊ

Uso:
    plano = await diagnosticar(user_id=1, db=db)
    # plano.fase_atual, plano.estrategia_recomendada, plano.diagnostico, etc.
"""

from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Any

from app.logger import logger


# ─── Resultado do Estrategista ────────────────────────────────────────────────

@dataclass
class MarcoPatrimonio:
    patrimonio: float           # R$ necessário para esse marco
    renda_mensal_possivel: float  # renda passiva sustentável nesse nível
    estimativa_anos: float      # anos estimados para chegar (com aportes)
    descricao: str              # ex: "Fase de colheita parcial"


@dataclass
class CenarioEstrategico:
    """Um cenário de investimento comparável."""
    nome: str                    # "Conservador" | "Recomendado" | "Agressivo"
    descricao: str               # 2-3 frases: o que é esse caminho
    modulos: list[str]           # ["RF Pós-fixada", "IPCA+", "FIIs"]
    alocacao_resumo: str         # "60% RF · 25% FIIs · 15% Ações" (texto livre)
    rentabilidade_esperada: str  # "12-14% a.a. nominal"
    tempo_meta: str              # "~5.2 anos" ou "meta inviável neste cenário"
    risco_principal: str         # 1 frase: o risco mais relevante


@dataclass
class ModuloSugerido:
    """Módulo APEX sugerido para o investidor."""
    nome: str                    # "RF Pós-fixada", "FIIs", etc.
    por_que: str                 # 1 frase: por que incluir esse módulo
    peso_sugerido: str           # "~30%" ou "15-20%"


@dataclass
class PlanoEstrategico:
    """Plano de longo prazo gerado pelo Estrategista."""

    # ── Diagnóstico da meta ───────────────────────────────────────────────
    diagnostico: str            # análise completa da viabilidade da meta
    meta_viavel: bool           # a meta é atingível no prazo declarado?
    gap_patrimonio: float       # patrimônio extra necessário para cumprir a meta (R$0 se já viável)

    # ── Fase atual ────────────────────────────────────────────────────────
    fase_atual: str             # "crescimento" | "transição" | "colheita"
    fase_descricao: str         # por que o investidor está nessa fase

    # ── Estratégia recomendada ────────────────────────────────────────────
    estrategia_recomendada: str  # CORE | ALPHA | RENDA | CUSTOM
    estrategia_razao: str        # por que ESSA estratégia para ESSE momento

    # ── Marcos de progresso ───────────────────────────────────────────────
    marcos: list[MarcoPatrimonio]

    # ── Ação imediata ─────────────────────────────────────────────────────
    proximos_passos: list[str]  # o que fazer AGORA
    alertas: list[str]          # riscos ou inconsistências identificadas

    # ── Revisão ───────────────────────────────────────────────────────────
    revisao_quando: str         # "quando patrimônio atingir R$X" ou "em 12 meses"
    # ── Cenários comparáveis (novo) ───────────────────────────────────
    cenarios: list[CenarioEstrategico] = field(default_factory=list)

    # ── Módulos sugeridos (novo) ──────────────────────────────────────
    modulos_sugeridos: list[ModuloSugerido] = field(default_factory=list)

    # ── Riscos e tradeoffs (novo) ─────────────────────────────────────
    riscos_e_tradeoffs: list[str] = field(default_factory=list)
    # ── Metadados ─────────────────────────────────────────────────────────
    usou_ia: bool = True
    gerado_em: str = ""
    patrimonio_na_criacao: float = 0.0   # patrimônio que a IA viu ao gerar o plano
    def to_dict(self) -> dict:
        return {
            "diagnostico": self.diagnostico,
            "meta_viavel": self.meta_viavel,
            "gap_patrimonio": self.gap_patrimonio,
            "fase_atual": self.fase_atual,
            "fase_descricao": self.fase_descricao,
            "estrategia_recomendada": self.estrategia_recomendada,
            "estrategia_razao": self.estrategia_razao,
            "marcos": [
                {
                    "patrimonio": m.patrimonio,
                    "renda_mensal_possivel": m.renda_mensal_possivel,
                    "estimativa_anos": m.estimativa_anos,
                    "descricao": m.descricao,
                }
                for m in self.marcos
            ],
            "proximos_passos": self.proximos_passos,
            "alertas": self.alertas,
            "revisao_quando": self.revisao_quando,
            "cenarios": [
                {
                    "nome": c.nome,
                    "descricao": c.descricao,
                    "modulos": c.modulos,
                    "alocacao_resumo": c.alocacao_resumo,
                    "rentabilidade_esperada": c.rentabilidade_esperada,
                    "tempo_meta": c.tempo_meta,
                    "risco_principal": c.risco_principal,
                }
                for c in self.cenarios
            ],
            "modulos_sugeridos": [
                {
                    "nome": m.nome,
                    "por_que": m.por_que,
                    "peso_sugerido": m.peso_sugerido,
                }
                for m in self.modulos_sugeridos
            ],
            "riscos_e_tradeoffs": self.riscos_e_tradeoffs,
            "usou_ia": self.usou_ia,
            "gerado_em": self.gerado_em,
            "patrimonio_na_criacao": self.patrimonio_na_criacao,
        }


# ─── Entry point público ──────────────────────────────────────────────────────

async def diagnosticar(
    nome: str,
    patrimonio_atual: float,
    objetivo_tipo: str,           # valor_alvo | percentual | renda | livre
    objetivo_valor: Optional[float],  # R$ mensal (renda) ou R$ total (valor) ou % (percentual)
    objetivo_prazo: Optional[str],    # ate_2anos | 2_5anos | 5_10anos | mais_10anos
    objetivo_descricao: Optional[str] = None,  # texto livre do objetivo
    estrategia_atual: str = "CORE",        # CORE | ALPHA | RENDA | CUSTOM
    onboarding_respostas: dict = None,   # respostas completas do questionário
    onboarding_score: int = 0,        # 0-15
    aporte_mensal: Optional[float] = None,  # aporte mensal declarado (se houver)
) -> PlanoEstrategico:
    """
    Ponto de entrada principal do Estrategista.
    Envia o perfil completo para a LLM raciocinar livremente e gera o plano.
    """
    if onboarding_respostas is None:
        onboarding_respostas = {}
    try:
        logger.info("plano: iniciando diagnostico IA para %s (patrimonio=%s)", nome, patrimonio_atual)
        plano = await asyncio.wait_for(
            _raciocinar_com_ia(
                nome=nome,
                patrimonio_atual=patrimonio_atual,
                objetivo_tipo=objetivo_tipo,
                objetivo_valor=objetivo_valor,
                objetivo_prazo=objetivo_prazo,
                objetivo_descricao=objetivo_descricao,
                estrategia_atual=estrategia_atual,
                onboarding_respostas=onboarding_respostas,
                onboarding_score=onboarding_score,
                aporte_mensal=aporte_mensal,
            ),
            timeout=240.0,
        )
        logger.info("plano: diagnostico IA concluido com sucesso (cenarios=%d)", len(plano.cenarios))
        return plano
    except asyncio.TimeoutError:
        logger.error("plano: TIMEOUT IA (240s) — caindo para fallback analitico")
        return _fallback_analitico(
            nome, patrimonio_atual, objetivo_tipo, objetivo_valor,
            objetivo_prazo, estrategia_atual, onboarding_score,
        )
    except Exception as e:
        logger.error("plano: IA falhou — %s: %s", type(e).__name__, e, exc_info=True)
        return _fallback_analitico(
            nome, patrimonio_atual, objetivo_tipo, objetivo_valor,
            objetivo_prazo, estrategia_atual, onboarding_score,
        )


# ─── Raciocínio via IA ────────────────────────────────────────────────────────

async def _raciocinar_com_ia(
    nome: str,
    patrimonio_atual: float,
    objetivo_tipo: str,
    objetivo_valor: Optional[float],
    objetivo_prazo: Optional[str],
    objetivo_descricao: Optional[str],
    estrategia_atual: str,
    onboarding_respostas: dict,
    onboarding_score: int,
    aporte_mensal: Optional[float],
) -> PlanoEstrategico:
    from app.cerebro.client import chat, is_ai_configured

    if not is_ai_configured():
        raise RuntimeError("IA não configurada")

    # ── MacroEngine completo — mesma visão que o CEO Brain ────────────────
    from app.cerebro.macro import montar_macro, MacroContext

    macro_ctx: Optional[MacroContext] = None
    try:
        import time as _time
        _t0 = _time.monotonic()
        macro_ctx = await montar_macro()
        logger.info("plano: MacroEngine OK em %.1fs", _time.monotonic() - _t0)
    except Exception as e:
        logger.warning("plano: MacroEngine falhou: %s", e)

    # ── Monta o brief narrativo do investidor ─────────────────────────────
    prazo_texto = _prazo_para_texto(objetivo_prazo)
    objetivo_texto = _objetivo_para_texto(objetivo_tipo, objetivo_valor, objetivo_descricao)
    perfil_texto = _perfil_para_texto(onboarding_respostas, onboarding_score)
    aporte_texto = f"Aporte mensal planejado: R$ {aporte_mensal:,.0f}" if aporte_mensal else "Aporte mensal: não declarado"

    # ── Contexto macro completo para o prompt ──────────────────────────────
    macro_texto = ""
    if macro_ctx:
        macro_texto = macro_ctx.resumo_texto()
    if not macro_texto:
        macro_texto = "DADOS MACRO: indisponíveis — seja conservador nas projeções"

    SYSTEM = """\
Você é o Estrategista APEX — planejador financeiro sênior brasileiro.
Retorne APENAS JSON válido, sem markdown, sem texto fora do JSON.

SUA MISSÃO: analisar o perfil completo do investidor e criar a MELHOR estratégia possível para o objetivo DELE — não uma genérica.

PRINCÍPIOS FUNDAMENTAIS:
1. LEIA ATENTAMENTE o objetivo declarado pelo investidor. Se ele escreveu em texto livre, CADA PALAVRA importa.
2. IDENTIFIQUE A FASE CORRETA:
   - Se o investidor quer CRESCER patrimônio → fase de ACUMULAÇÃO. Priorize retorno total, NÃO dividendos/renda.
   - Se o investidor quer RENDA agora → fase de COLHEITA. Priorize yield e fluxo de caixa.
   - Se o investidor quer CRESCER agora e RENDA no futuro → fase de ACUMULAÇÃO com transição planejada.
3. NÃO RECOMENDE dividendos/FIIs/renda passiva para quem está em fase de ACUMULAÇÃO — esses ativos sacrificam crescimento.
4. Para crescimento agressivo, use Growth BR, ETFs Internacionais, Momentum/Swing. Ações de crescimento reinvestem lucros → compound effect.
5. Se o retorno projetado do cenário "Recomendado" for parecido com a Selic, a estratégia é RUIM. Renda fixa pura não precisa de gestor.
6. Cada cenário DEVE ter retorno esperado SIGNIFICATIVAMENTE diferente. Não faça 3 cenários com retornos parecidos.
7. O cenário "Agressivo" DEVE buscar retornos altos (18-25%+ a.a.) com módulos de growth e momentum.
8. Use **bold** (duplo asterisco) nas conclusões-chave do diagnostico.

RACIOCÍNIO SOBRE METAS:
- Meta de renda futura: patrimônio_necessário = renda_mensal ÷ 0,005 (6% a.a.). MAS o foco AGORA é crescer até lá, não gerar renda.
- Meta de crescimento: calcule retorno necessário e compare com benchmarks. Se exige >25% a.a., sinalize como difícil/arriscado mas possível.
- Se o prazo for insuficiente para a meta, diga claramente com números — mas proponha alternativas (contribuição maior, horizonte estendido, etc).

MÓDULOS APEX (nomes exatos):
  RF Pós-fixada | IPCA+ | FIIs | Dividendos BR | Growth BR | ETFs Internacionais | Momentum/Swing | Caixa

BENCHMARKS REAIS (nominal):
  RF Pós: ~Selic | IPCA+: inflação + 6-7% a.a. | FIIs: DY 9-12% a.a. + valorização
  Dividendos BR: 8-12% a.a. total | Growth BR: 15-25% a.a. (with higher vol)
  ETFs Internacionais: 12-18% a.a. em BRL (SP500 + câmbio) | Momentum/Swing: 20-35% a.a. (requer dedicação)
  Estratégia CORE: 12-16% a.a. | Estratégia ALPHA: 18-28% a.a.
  Renda sustentável: 0,5%/mês do patrimônio (6% a.a.)

REGRA: Não inclua TODOS os módulos em cada cenário. Escolha 2-4 módulos que FAZEM SENTIDO para aquele nível de risco e fase.

AJUSTE DE ALOCAÇÃO POR MACRO REAL (OBRIGATÓRIO):
Você recebe o MacroEngine completo. CADA dado muda pesos de alocação:

BRASIL:
- Selic alta (>12% a.a.) → RF Pós e IPCA+ muito atraentes. Custo de oportunidade alto para sair da RF.
- Selic baixa (<7% a.a.) → RF não bate inflação. Force mais risco (Growth, ETFs).
- Juro real alto (>6%) → IPCA+ longa (NTN-B) vira ativo estratégico.
- Selic Focus < Selic atual → ciclo de corte à vista. Prefixados e FIIs se beneficiam.
- Selic Focus > Selic atual → juros subindo. RF pós-fixada domina.
- Dólar forte (>5.50) → favorece exportadoras (VALE3, PETR4, SUZB3). Desfavorece importadoras.
- Dólar fraco (<4.80) → favorece consumo interno, small caps, FIIs.
- IBOV em queda + VIX alto → modo defensivo. Mais RF, Caixa, Dividendos defensivos.

GLOBAL:
- VIX > 25 → mercado em stress. Reduza Momentum/Swing, aumente proteção.
- VIX < 18 → ambiente favorável. Pode ser agressivo em Growth e ETFs.
- Treasury 10Y > 5% → custo global de capital extremo. Pressiona TODOS os ativos de risco.
- Treasury 10Y > 4% → emergentes sob pressão. Ajuste retorno esperado de ETFs internacionais.
- DXY acima da MM50 → dólar global forte. Pressão sobre emergentes e commodities em USD.
- Petróleo WTI > $100 → pressão inflacionária. Bom para petroleiras, ruim para consumo.
- Petróleo WTI < $50 → risco para PETR4/PRIO3. Reduza peso em petróleo.
- S&P 500 acima da MM200 → tendência de alta global. ETFs internacionais favorecidos.
- S&P 500 abaixo da MM200 → tendência de baixa. Reduza exposição internacional.
- Ouro em alta → aversão a risco. Confirma postura defensiva.

USE os dados reais do payload. Cite números concretos na justificativa de cada cenário.
Se macro indisponível, seja conservador nas projeções e diga que dados estavam indisponíveis.

CENÁRIOS: exatamente 3 — Conservador, Recomendado, Agressivo — com alocações e retornos REALMENTE DIFERENTES e ajustados ao macro atual."""

    USER = f"""PERFIL COMPLETO DO INVESTIDOR:
Nome: {nome}
Patrimônio atual: R$ {patrimonio_atual:,.0f}
Objetivo declarado: {objetivo_texto}
Prazo declarado: {prazo_texto}
{aporte_texto}

CONTEXTO MACROECONÔMICO COMPLETO (MacroEngine — dados reais de hoje):
{macro_texto}

RESPOSTAS DO QUESTIONÁRIO DE PERFIL:
{perfil_texto}

INSTRUÇÕES PARA O DIAGNÓSTICO:
1. Comece pelo que o investidor QUER — use as palavras dele.
2. Calcule o patrimônio alvo (se meta = renda: renda ÷ 0,005; se meta = valor: o valor declarado).
3. Calcule o gap: alvo − patrimônio atual.
4. Para cada cenário, calcule o tempo real considerando aportes + rentabilidade composta.
5. Se o investidor declarou que quer crescimento agressivo, o cenário Recomendado DEVE ser agressivo.
6. NÃO recomende FIIs/Dividendos como forma de "crescimento" — esses são para fase de renda.
7. USE OS DADOS MACRO REAIS COMPLETOS (acima) para definir os pesos de alocação. Cite números concretos: "Selic a X%, VIX a Y, Treasury 10Y a Z%". Os pesos devem refletir o cenário de HOJE — não um cenário genérico. Se DXY forte + Treasury alto + VIX elevado, isso muda tudo.

JSON a retornar:
{{
  "diagnostico": "string — 4-8 frases. Comece pelo objetivo declarado pelo investidor. Mostre as contas: patrimônio necessário, gap, tempo estimado com aportes. Use **bold** nas conclusões-chave. Se prazo é apertado, diga com números.",
  "meta_viavel": true,
  "gap_patrimonio": 0.0,
  "fase_atual": "crescimento | transição | colheita",
  "fase_descricao": "2 frases justificando a fase — baseado no objetivo e prazo, não só no patrimônio.",
  "estrategia_recomendada": "CORE | ALPHA | RENDA",
  "estrategia_razao": "2-3 frases explicando POR QUE esta estratégia é a certa PARA ESTE investidor NESTE momento.",
  "cenarios": [
    {{"nome":"Conservador","descricao":"2-3 frases.","modulos":["..."],"alocacao_resumo":"...","rentabilidade_esperada":"X-Y% a.a.","tempo_meta":"~N anos para R$Z","risco_principal":"1 frase."}},
    {{"nome":"Recomendado","descricao":"2-3 frases.","modulos":["..."],"alocacao_resumo":"...","rentabilidade_esperada":"X-Y% a.a.","tempo_meta":"~N anos para R$Z","risco_principal":"1 frase."}},
    {{"nome":"Agressivo","descricao":"2-3 frases.","modulos":["..."],"alocacao_resumo":"...","rentabilidade_esperada":"X-Y% a.a.","tempo_meta":"~N anos para R$Z","risco_principal":"1 frase."}}
  ],
  "modulos_sugeridos": [
    {{"nome":"NomeExato","por_que":"1 frase com número.","peso_sugerido":"~X%"}}
  ],
  "riscos_e_tradeoffs": ["Risco 1","Risco 2","Risco 3"],
  "marcos": [
    {{"patrimonio":N,"renda_mensal_possivel":N,"estimativa_anos":N,"descricao":"..."}}
  ],
  "proximos_passos": ["Ação 1","Ação 2"],
  "alertas": ["..."],
  "revisao_quando": "..."
}}"""

    _t1 = _time.monotonic()
    logger.info("plano: chamando IA (max_tokens=4000)...")
    resposta_raw = await chat(
        system=SYSTEM,
        messages=[{"role": "user", "content": USER}],
        max_tokens=4000,
    )
    logger.info("plano: IA respondeu em %.1fs (tamanho=%d chars)", _time.monotonic() - _t1, len(resposta_raw))

    return _parsear_resposta(resposta_raw, patrimonio_atual=patrimonio_atual)


def _parsear_resposta(resposta_raw: str, patrimonio_atual: float = 0.0) -> PlanoEstrategico:
    """Converte o JSON da IA em PlanoEstrategico."""
    from datetime import datetime, timezone

    texto = resposta_raw.strip()

    # Remove markdown se presente (fences com ou sem fechamento — resposta pode ser truncada)
    if "```" in texto:
        import re
        # Tenta com fechamento
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", texto)
        if match:
            texto = match.group(1).strip()
        else:
            # Sem fechamento (resposta truncada): remove apenas a abertura
            texto = re.sub(r"^```(?:json)?\s*", "", texto).strip()

    # Garante que começa no { ou [ (descarta texto antes do JSON)
    for brace in ('{', '['):
        idx = texto.find(brace)
        if idx >= 0:
            texto = texto[idx:]
            break

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError as e:
        logger.error("plano: JSON invalido da IA: %s\nResposta (500 chars): %s", e, texto[:500])
        raise ValueError(f"Estrategista: JSON inválido na resposta da IA: {e}")

    marcos = []
    for m in dados.get("marcos", []):
        marcos.append(MarcoPatrimonio(
            patrimonio=float(m.get("patrimonio", 0)),
            renda_mensal_possivel=float(m.get("renda_mensal_possivel", 0)),
            estimativa_anos=float(m.get("estimativa_anos", 0)),
            descricao=str(m.get("descricao", "")),
        ))

    cenarios = []
    for c in dados.get("cenarios", []):
        cenarios.append(CenarioEstrategico(
            nome=str(c.get("nome", "")),
            descricao=str(c.get("descricao", "")),
            modulos=[str(x) for x in c.get("modulos", [])],
            alocacao_resumo=str(c.get("alocacao_resumo", "")),
            rentabilidade_esperada=str(c.get("rentabilidade_esperada", "")),
            tempo_meta=str(c.get("tempo_meta", "")),
            risco_principal=str(c.get("risco_principal", "")),
        ))

    modulos_sugeridos = []
    for ms in dados.get("modulos_sugeridos", []):
        modulos_sugeridos.append(ModuloSugerido(
            nome=str(ms.get("nome", "")),
            por_que=str(ms.get("por_que", "")),
            peso_sugerido=str(ms.get("peso_sugerido", "")),
        ))

    return PlanoEstrategico(
        diagnostico=str(dados.get("diagnostico", "")),
        meta_viavel=bool(dados.get("meta_viavel", True)),
        gap_patrimonio=float(dados.get("gap_patrimonio", 0)),
        fase_atual=str(dados.get("fase_atual", "crescimento")),
        fase_descricao=str(dados.get("fase_descricao", "")),
        estrategia_recomendada=str(dados.get("estrategia_recomendada", "CORE")),
        estrategia_razao=str(dados.get("estrategia_razao", "")),
        marcos=marcos,
        proximos_passos=[str(p) for p in dados.get("proximos_passos", [])],
        alertas=[str(a) for a in dados.get("alertas", [])],
        revisao_quando=str(dados.get("revisao_quando", "em 12 meses")),
        cenarios=cenarios,
        modulos_sugeridos=modulos_sugeridos,
        riscos_e_tradeoffs=[str(r) for r in dados.get("riscos_e_tradeoffs", [])],
        usou_ia=True,
        gerado_em=datetime.now(timezone.utc).isoformat(),
        patrimonio_na_criacao=patrimonio_atual if patrimonio_atual > 0 else float(dados.get("patrimonio_na_criacao", 0)),
    )


# ─── Fallback analítico (sem IA) ─────────────────────────────────────────────

def _fallback_analitico(
    nome: str,
    patrimonio: float,
    objetivo_tipo: str,
    objetivo_valor: Optional[float],
    objetivo_prazo: Optional[str],
    estrategia_atual: str,
    score: int,
) -> PlanoEstrategico:
    """
    Análise determinística quando a IA não está disponível.
    Usa os benchmarks padrão para calcular viabilidade.
    """
    from datetime import datetime, timezone

    # ── Calcular renda possível hoje ──────────────────────────────────────
    # Yield sustentável conservador: 0.5% ao mês = 6% a.a.
    renda_atual_possivel = patrimonio * 0.005

    # ── Verificar viabilidade da meta ─────────────────────────────────────
    meta_viavel = True
    gap_patrimonio = 0.0
    diagnostico = ""

    if objetivo_tipo == "renda" and objetivo_valor:
        patrimonio_necessario = objetivo_valor / 0.005  # 0.5% ao mês
        gap_patrimonio = max(0, patrimonio_necessario - patrimonio)

        if gap_patrimonio > 0:
            meta_viavel = False
            diagnostico = (
                f"Meta de R$ {objetivo_valor:,.0f}/mês requer patrimônio de aproximadamente "
                f"R$ {patrimonio_necessario:,.0f} — você tem R$ {patrimonio:,.0f}. "
                f"Gap de R$ {gap_patrimonio:,.0f} ({gap_patrimonio/patrimonio*100:.0f}x o patrimônio atual). "
                f"Com CORE (~12% a.a.), alcançar esse patrimônio levaria "
                f"~{_anos_para_crescer(patrimonio, patrimonio_necessario, 0.12):.0f} anos sem aportes, "
                f"ou menos com aportes mensais consistentes. "
                f"A meta é atingível, mas o prazo real é mais longo do que o declarado."
            )
        else:
            diagnostico = (
                f"Meta de R$ {objetivo_valor:,.0f}/mês é viável — seu patrimônio atual de "
                f"R$ {patrimonio:,.0f} pode gerar essa renda com yield de 6% a.a."
            )

    elif objetivo_tipo == "valor" and objetivo_valor:
        if patrimonio >= objetivo_valor:
            meta_viavel = True
            diagnostico = f"Meta de R$ {objetivo_valor:,.0f} já atingida. Foco em proteção e renda."
        else:
            anos = _anos_para_crescer(patrimonio, objetivo_valor, 0.12)
            meta_viavel = anos <= _prazo_para_anos(objetivo_prazo)
            diagnostico = (
                f"Meta de R$ {objetivo_valor:,.0f} requer crescimento de "
                f"{(objetivo_valor/patrimonio - 1)*100:.0f}%. "
                f"Com CORE (~12% a.a.): ~{anos:.0f} anos sem aportes."
            )
    else:
        diagnostico = (
            f"Com patrimônio de R$ {patrimonio:,.0f}, você pode gerar "
            f"~R$ {renda_atual_possivel:,.0f}/mês em renda passiva sustentável. "
            f"Foque em crescimento para ampliar essa capacidade."
        )

    # ── Definir fase ──────────────────────────────────────────────────────
    if patrimonio < 500_000:
        fase = "crescimento"
        fase_desc = "Patrimônio ainda em construção — crescimento é o foco prioritário."
    elif patrimonio < 2_000_000:
        fase = "crescimento"
        fase_desc = "Fase de aceleração — você tem massa crítica mas ainda precisa crescer para gerar renda expressiva."
    elif patrimonio < 5_000_000:
        fase = "transição"
        fase_desc = "Fase de transição — começa a fazer sentido migrar parte para ativos de renda."
    else:
        fase = "colheita"
        fase_desc = "Fase de colheita — patrimônio suficiente para estratégia orientada a renda."

    # ── Estratégia recomendada ────────────────────────────────────────────
    if fase == "colheita" or (objetivo_tipo == "renda" and meta_viavel):
        estrategia_rec = "RENDA"
        estrategia_razao = "Patrimônio suficiente para estratégia de renda passiva sustentável."
    elif score >= 11 and fase == "crescimento":
        estrategia_rec = "ALPHA"
        estrategia_razao = "Perfil agressivo em fase de crescimento — ALPHA maximiza o acúmulo de patrimônio."
    else:
        estrategia_rec = "CORE"
        estrategia_razao = "Equilíbrio entre crescimento e proteção — adequado à fase atual."

    # ── Marcos ───────────────────────────────────────────────────────────
    marcos = _calcular_marcos(patrimonio, objetivo_tipo, objetivo_valor)

    return PlanoEstrategico(
        diagnostico=diagnostico,
        meta_viavel=meta_viavel,
        gap_patrimonio=gap_patrimonio,
        fase_atual=fase,
        fase_descricao=fase_desc,
        estrategia_recomendada=estrategia_rec,
        estrategia_razao=estrategia_razao,
        marcos=marcos,
        proximos_passos=[
            f"Configure a IA (Configurações → Motor de IA) para análise personalizada.",
            f"Declare seu capital disponível para investimento imediato.",
            f"Revise a alocação alvo nos módulos da carteira.",
        ],
        alertas=[] if meta_viavel else [
            f"Meta requer patrimônio ~{gap_patrimonio/patrimonio:.1f}x maior que o atual.",
            "Considere aumentar aportes mensais para reduzir o prazo.",
        ],
        revisao_quando="em 12 meses ou quando patrimônio variar ±20%",
        usou_ia=False,
        gerado_em=datetime.now(timezone.utc).isoformat(),
        patrimonio_na_criacao=patrimonio,
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _anos_para_crescer(inicial: float, alvo: float, taxa_anual: float) -> float:
    """Calcula anos necessários para crescer de inicial até alvo com taxa a.a. (sem aportes)."""
    if inicial <= 0 or alvo <= inicial:
        return 0.0
    import math
    return math.log(alvo / inicial) / math.log(1 + taxa_anual)


def _prazo_para_anos(prazo: Optional[str]) -> float:
    mapa = {"ate_2anos": 2, "2_5anos": 5, "5_10anos": 10, "mais_10anos": 20}
    return float(mapa.get(prazo or "", 10))


def _prazo_para_texto(prazo: Optional[str]) -> str:
    mapa = {
        "ate_2anos": "até 2 anos",
        "2_5anos": "2 a 5 anos",
        "5_10anos": "5 a 10 anos",
        "mais_10anos": "mais de 10 anos",
    }
    return mapa.get(prazo or "", "não declarado")


def _objetivo_para_texto(tipo: str, valor: Optional[float], descricao: Optional[str] = None) -> str:
    if tipo == "renda" and valor:
        base = f"Renda passiva de R$ {valor:,.0f}/mês"
        if descricao:
            base += f"\n  Descrição do investidor: \"{descricao}\""
        return base
    if tipo == "valor" and valor:
        base = f"Patrimônio total de R$ {valor:,.0f}"
        if descricao:
            base += f"\n  Descrição do investidor: \"{descricao}\""
        return base
    if tipo == "percentual" and valor:
        base = f"Retorno de {valor:.1f}% ao ano"
        if descricao:
            base += f"\n  Descrição do investidor: \"{descricao}\""
        return base
    if tipo == "livre" and descricao:
        return f"(Nas palavras do investidor): \"{descricao}\""
    if descricao:
        return f"Tipo: {tipo}. Descrição do investidor: \"{descricao}\""
    return "Não declarou objetivo específico"


def _perfil_para_texto(respostas: dict, score: int) -> str:
    """Converte respostas do onboarding em texto narrativo para a LLM.
    NÃO inclui classificação de estratégia — a IA deve decidir livremente."""
    linhas = [f"Score de perfil: {score}/15 (quanto maior, mais agressivo/experiente)"]

    mapa = {
        "volatilidade": {
            "vende_tudo": "Em queda, venderia tudo",
            "vende_parte": "Em queda, venderia parte",
            "mantem": "Em queda, manteria posição",
            "compra_mais": "Em queda, compraria mais",
        },
        "liquidez": {
            "mais_30pct": "Pode precisar de +30% do patrimônio em 12 meses",
            "10_30pct": "Pode precisar de 10-30% do patrimônio em 12 meses",
            "menos_10pct": "Pode precisar de menos de 10% do patrimônio em 12 meses",
            "nenhuma": "Não precisará de nenhum saque em 12 meses",
        },
        "renda": {
            "depende_portfolio": "Depende do portfólio como renda principal",
            "parcial": "Renda ativa cobre parcialmente as despesas",
            "ativa": "Tem renda ativa suficiente, portfólio é crescimento",
        },
        "objetivo": {
            "preservacao": "Objetivo: preservar capital",
            "renda_passiva": "Objetivo: gerar renda passiva",
            "equilibrio": "Objetivo: equilíbrio crescimento/renda",
            "crescimento": "Objetivo: máximo crescimento",
        },
        "horizonte": {
            "ate_2anos": "Horizonte curto (até 2 anos)",
            "2_5anos": "Horizonte médio (2-5 anos)",
            "5_10anos": "Horizonte longo (5-10 anos)",
            "mais_10anos": "Horizonte muito longo (+10 anos)",
        },
        "tempo": {
            "menos_1h": "Disponibilidade: menos de 1h/semana para o portfólio",
            "1_3h": "Disponibilidade: 1-3h/semana para o portfólio",
            "3_5h": "Disponibilidade: 3-5h/semana para o portfólio",
            "mais_5h": "Disponibilidade: mais de 5h/semana para o portfólio",
        },
    }

    for campo, opcoes in mapa.items():
        valor = respostas.get(campo)
        if valor and valor in opcoes:
            linhas.append(f"- {opcoes[valor]}")

    exp = respostas.get("experiencia", [])
    if isinstance(exp, list) and exp:
        exp_texto = {
            "acoes_br": "ações BR", "opcoes": "opções", "exterior": "renda variável exterior",
            "etfs": "ETFs", "bdrs": "BDRs", "fiis": "FIIs", "renda_fixa": "renda fixa",
        }
        exp_lista = [exp_texto.get(e, e) for e in exp]
        linhas.append(f"- Experiência com: {', '.join(exp_lista)}")

    # Inclui descrição livre do objetivo se existir nas respostas
    goal_desc = respostas.get("goal_description")
    if goal_desc:
        linhas.append(f"- Objetivo descrito pelo investidor: \"{goal_desc}\"")

    return "\n".join(linhas)


def _calcular_marcos(
    patrimonio: float,
    objetivo_tipo: str,
    objetivo_valor: Optional[float],
) -> list[MarcoPatrimonio]:
    """Gera marcos de progresso baseados no patrimônio atual."""
    marcos = []

    # Marco 1: próximo nível (2x ou meta intermediária)
    if patrimonio < 1_000_000:
        marcos.append(MarcoPatrimonio(
            patrimonio=1_000_000,
            renda_mensal_possivel=5_000,
            estimativa_anos=round(_anos_para_crescer(patrimonio, 1_000_000, 0.12), 1),
            descricao="1 milhão — primeiro marco psicológico importante",
        ))

    if patrimonio < 2_000_000:
        marcos.append(MarcoPatrimonio(
            patrimonio=2_000_000,
            renda_mensal_possivel=10_000,
            estimativa_anos=round(_anos_para_crescer(max(patrimonio, 1), 2_000_000, 0.12), 1),
            descricao="2 milhões — renda passiva de R$10k/mês é viável",
        ))

    if patrimonio < 5_000_000:
        marcos.append(MarcoPatrimonio(
            patrimonio=5_000_000,
            renda_mensal_possivel=25_000,
            estimativa_anos=round(_anos_para_crescer(max(patrimonio, 1), 5_000_000, 0.12), 1),
            descricao="5 milhões — renda passiva consistente de R$25k/mês",
        ))

    # Marco da meta, se for renda e ainda não atingida
    if objetivo_tipo == "renda" and objetivo_valor and objetivo_valor > 0:
        patrimonio_meta = objetivo_valor / 0.005
        if patrimonio_meta > patrimonio:
            marcos.append(MarcoPatrimonio(
                patrimonio=patrimonio_meta,
                renda_mensal_possivel=objetivo_valor,
                estimativa_anos=round(_anos_para_crescer(max(patrimonio, 1), patrimonio_meta, 0.12), 1),
                descricao=f"Meta declarada — R$ {objetivo_valor:,.0f}/mês de renda passiva",
            ))

    # Ordena por patrimônio crescente e remove duplicatas
    marcos_unicos = []
    vistos = set()
    for m in sorted(marcos, key=lambda x: x.patrimonio):
        if m.patrimonio not in vistos:
            vistos.add(m.patrimonio)
            marcos_unicos.append(m)

    return marcos_unicos[:4]  # máximo 4 marcos


# ─── Auto-refresh: verifica se o plano precisa ser atualizado ─────────────────

_PLANO_MAX_AGE_DAYS = 90          # revalida a cada 90 dias
_PLANO_PATRIMONIO_DELTA = 0.30    # revalida se patrimônio variar ±30%


def deve_atualizar_plano(
    plano_dict: dict | None,
    patrimonio_atual: float,
) -> bool:
    """
    Retorna True se o plano estratégico deve ser regenerado.

    Condições:
      1. Não existe plano (nunca gerado ou apagado)
      2. Plano tem mais de 90 dias
      3. Patrimônio mudou > 30% desde o que o plano viu no diagnóstico
    """
    if not plano_dict:
        return True

    # ── Idade do plano ────────────────────────────────────────────────────
    gerado_em = plano_dict.get("gerado_em")
    if gerado_em:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(gerado_em)
            idade_dias = (datetime.now(timezone.utc) - dt).days
            if idade_dias >= _PLANO_MAX_AGE_DAYS:
                logger.info("plano: auto-refresh — plano tem %d dias (max %d)", idade_dias, _PLANO_MAX_AGE_DAYS)
                return True
        except (ValueError, TypeError):
            # gerado_em inválido → melhor regenerar
            return True
    else:
        # Sem timestamp → plano antigo, regenerar
        return True

    # ── Variação de patrimônio ────────────────────────────────────────────
    patrimonio_na_criacao = plano_dict.get("patrimonio_na_criacao", 0)
    if patrimonio_na_criacao > 0 and patrimonio_atual > 0:
        variacao = abs(patrimonio_atual - patrimonio_na_criacao) / patrimonio_na_criacao
        if variacao >= _PLANO_PATRIMONIO_DELTA:
            logger.info(
                "plano: auto-refresh — patrimônio variou %.0f%% (limiar %.0f%%)",
                variacao * 100, _PLANO_PATRIMONIO_DELTA * 100,
            )
            return True

    return False

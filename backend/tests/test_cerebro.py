"""
Suite de testes do Cérebro APEX
================================
Cobre:
  1. SugestaoMotor — criação, to_dict(), defaults
  2. gestor._marcar_duplicatas — marcação de tickers repetidos
  3. gestor._balancear_caixa — garantia de que a soma == capital
  4. gestor._fallback_algoritmico — deduplicação por score, sem IA
  5. gestor.analisar — candidatos vazios, fallback quando IA falha, e com IA mockada
  6. client.is_ai_configured — sem arquivo de config
  7. prompts.build_portfolio_prompt / build_briefing_prompt — geração de prompts
  8. Integração — fluxo completo com resposta da IA simulada

Rodar:
    cd backend
    pytest tests/test_cerebro.py -v
"""

import json
import asyncio
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Garante que o import acha o pacote app/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── helpers ─────────────────────────────────────────────────────────────────

def _sugestao(
    ticker: str = "BOVA11",
    modulo: str = "etfs",
    tipo: str = "ETF",
    score: float = 0.8,
    preco: float = 100.0,
    quantidade: float = 10,
) -> "SugestaoMotor":
    from app.cerebro.especialistas import SugestaoMotor

    return SugestaoMotor(
        modulo=modulo,
        ticker=ticker,
        nome=f"Fundo {ticker}",
        tipo=tipo,
        quantidade=quantidade,
        preco_atual=preco,
        valor_total=round(quantidade * preco, 2),
        justificativa=f"Boa oportunidade em {ticker}",
        score=score,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SugestaoMotor
# ═══════════════════════════════════════════════════════════════════════════════

class TestSugestaoMotor:
    def test_criacao_basica(self):
        from app.cerebro.especialistas import SugestaoMotor

        s = SugestaoMotor(
            modulo="etfs",
            ticker="BOVA11",
            nome="iShares IBOVESPA",
            tipo="ETF",
            quantidade=10,
            preco_atual=120.50,
            valor_total=1205.00,
            justificativa="Exposição ampla ao IBOV",
        )

        assert s.ticker == "BOVA11"
        assert s.modulo == "etfs"
        assert s.tipo == "ETF"
        assert s.score == 0.0          # default
        assert s.dados_extras == {}    # default

    def test_to_dict_contem_campos_esperados(self):
        s = _sugestao("PETR4", modulo="alpha", tipo="ACAO", score=0.75)
        d = s.to_dict()

        assert d["ticker"] == "PETR4"
        assert d["modulo"] == "alpha"
        assert d["tipo"] == "ACAO"
        assert d["score"] == 0.75
        assert "justificativa" in d
        assert "valor_total" in d
        assert "dados_extras" in d

    def test_dados_extras_independentes(self):
        """Cada SugestaoMotor deve ter seu próprio dict de dados_extras."""
        s1 = _sugestao("PETR4")
        s2 = _sugestao("VALE3")

        s1.dados_extras["rsi"] = 45
        assert "rsi" not in s2.dados_extras

    def test_valor_total_arredondado_no_to_dict(self):
        from app.cerebro.especialistas import SugestaoMotor

        s = SugestaoMotor(
            modulo="fiis",
            ticker="MXRF11",
            nome="Maxi Renda",
            tipo="FII",
            quantidade=50,
            preco_atual=10.123456,
            valor_total=506.1728,
            justificativa="FII de papel",
        )
        d = s.to_dict()
        # deve estar arredondado a 2 casas
        assert d["valor_total"] == round(506.1728, 2)
        assert d["preco_atual"] == round(10.123456, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. gestor._marcar_duplicatas
# ═══════════════════════════════════════════════════════════════════════════════

class TestMarcarDuplicatas:
    def test_sem_duplicatas(self):
        from app.cerebro import gestor

        candidatos = [
            _sugestao("BOVA11", modulo="etfs"),
            _sugestao("PETR4", modulo="alpha"),
        ]
        resultado = gestor._marcar_duplicatas(candidatos)

        for c in resultado:
            assert "_duplicado" not in c.dados_extras

    def test_com_duplicata_marca_ambos(self):
        from app.cerebro import gestor

        candidatos = [
            _sugestao("PETR4", modulo="alpha"),
            _sugestao("PETR4", modulo="momentum"),
            _sugestao("BOVA11", modulo="etfs"),
        ]
        resultado = gestor._marcar_duplicatas(candidatos)

        petr_candidatos = [c for c in resultado if c.ticker == "PETR4"]
        assert len(petr_candidatos) == 2
        for c in petr_candidatos:
            assert c.dados_extras.get("_duplicado") is True
            assert c.dados_extras.get("_n_modulos") == 2

        bova = next(c for c in resultado if c.ticker == "BOVA11")
        assert "_duplicado" not in bova.dados_extras

    def test_tres_ocorrencias_mesmo_ticker(self):
        from app.cerebro import gestor

        candidatos = [
            _sugestao("VALE3", modulo="etfs"),
            _sugestao("VALE3", modulo="alpha"),
            _sugestao("VALE3", modulo="dividendos"),
        ]
        resultado = gestor._marcar_duplicatas(candidatos)

        for c in resultado:
            assert c.dados_extras.get("_n_modulos") == 3


# ═══════════════════════════════════════════════════════════════════════════════
# 3. gestor._balancear_caixa
# ═══════════════════════════════════════════════════════════════════════════════

class TestBalancearCaixa:
    def test_soma_exata_sem_alteracao(self):
        from app.cerebro import gestor
        from app.cerebro.especialistas import SugestaoMotor

        s = SugestaoMotor(
            modulo="etfs", ticker="BOVA11", nome="BOVA", tipo="ETF",
            quantidade=10, preco_atual=100.0, valor_total=1000.0,
            justificativa=""
        )
        resultado = gestor._balancear_caixa([s], capital=1000.0)
        assert sum(r.valor_total for r in resultado) == pytest.approx(1000.0, abs=0.02)

    def test_sobra_cria_caixa(self):
        from app.cerebro import gestor
        from app.cerebro.especialistas import SugestaoMotor

        s = SugestaoMotor(
            modulo="etfs", ticker="BOVA11", nome="BOVA", tipo="ETF",
            quantidade=9, preco_atual=100.0, valor_total=900.0,
            justificativa=""
        )
        resultado = gestor._balancear_caixa([s], capital=1000.0)
        tickers = [r.ticker for r in resultado]
        assert "CAIXA" in tickers
        assert sum(r.valor_total for r in resultado) == pytest.approx(1000.0, abs=0.02)

    def test_sobra_ajusta_caixa_existente(self):
        from app.cerebro import gestor
        from app.cerebro.especialistas import SugestaoMotor

        ativo = SugestaoMotor(
            modulo="etfs", ticker="BOVA11", nome="BOVA", tipo="ETF",
            quantidade=9, preco_atual=100.0, valor_total=900.0,
            justificativa=""
        )
        caixa = SugestaoMotor(
            modulo="caixa", ticker="CAIXA", nome="Caixa", tipo="CAIXA",
            quantidade=50.0, preco_atual=1.0, valor_total=50.0,
            justificativa=""
        )
        resultado = gestor._balancear_caixa([ativo, caixa], capital=1000.0)
        caixa_final = next(r for r in resultado if r.ticker == "CAIXA")
        assert caixa_final.valor_total == pytest.approx(100.0, abs=0.02)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. gestor._fallback_algoritmico
# ═══════════════════════════════════════════════════════════════════════════════

class TestFallbackAlgoritmico:
    def test_deduplicacao_mantem_maior_score(self):
        from app.cerebro import gestor

        c1 = _sugestao("PETR4", modulo="alpha",    score=0.9, preco=35.0, quantidade=10)
        c2 = _sugestao("PETR4", modulo="momentum", score=0.6, preco=35.0, quantidade=10)

        resultado = gestor._fallback_algoritmico(
            [c1, c2], capital=350.0, estrategia="CORE", regime="MISTO"
        )
        petr = [s for s in resultado.sugestoes_finais if s.ticker == "PETR4"]
        assert len(petr) == 1
        assert petr[0].modulo == "alpha"  # maior score

    def test_sem_ia(self):
        from app.cerebro import gestor

        resultado = gestor._fallback_algoritmico(
            [_sugestao("BOVA11")], capital=1000.0, estrategia="CORE", regime="BULL"
        )
        assert resultado.usou_ia is False

    def test_capital_balanceado(self):
        from app.cerebro import gestor

        candidatos = [
            _sugestao("BOVA11", preco=100.0, quantidade=7),   # 700
            _sugestao("PETR4", modulo="alpha", preco=35.0, quantidade=5),  # 175
        ]
        resultado = gestor._fallback_algoritmico(
            candidatos, capital=1000.0, estrategia="CORE", regime="BULL"
        )
        total = sum(s.valor_total for s in resultado.sugestoes_finais)
        assert total == pytest.approx(1000.0, abs=0.10)

    def test_regime_bear_adiciona_alerta(self):
        from app.cerebro import gestor

        resultado = gestor._fallback_algoritmico(
            [_sugestao("BOVA11")], capital=1000.0, estrategia="CORE", regime="BEAR"
        )
        assert any("BEAR" in a for a in resultado.alertas)


# ═══════════════════════════════════════════════════════════════════════════════
# 5. gestor.analisar
# ═══════════════════════════════════════════════════════════════════════════════

class TestGestorAnalisar:
    def test_candidatos_vazios_retorna_resultado_sem_sugestoes(self):
        from app.cerebro import gestor

        resultado = asyncio.run(
            gestor.analisar(
                candidatos=[],
                capital=10_000.0,
                estrategia="CORE",
                regime="BULL",
                score_perfil=8,
            )
        )
        assert resultado.sugestoes_finais == []
        assert resultado.usou_ia is False
        assert resultado.score_portfolio == 0

    def test_fallback_quando_ia_nao_configurada(self):
        from app.cerebro import gestor

        candidatos = [_sugestao("BOVA11")]

        with patch("app.cerebro.client.is_ai_configured", return_value=False):
            resultado = asyncio.run(
                gestor.analisar(
                    candidatos=candidatos,
                    capital=1000.0,
                    estrategia="CORE",
                    regime="BULL",
                    score_perfil=8,
                )
            )

        assert resultado.usou_ia is False

    def test_fallback_quando_ia_gera_excecao(self):
        from app.cerebro import gestor

        candidatos = [_sugestao("BOVA11")]

        with patch("app.cerebro.gestor._analisar_com_ia", side_effect=RuntimeError("IA off")):
            resultado = asyncio.run(
                gestor.analisar(
                    candidatos=candidatos,
                    capital=1000.0,
                    estrategia="CORE",
                    regime="BULL",
                    score_perfil=8,
                )
            )

        assert resultado.usou_ia is False
        assert len(resultado.sugestoes_finais) >= 1

    def test_com_ia_mockada_retorna_resultado_completo(self):
        """Simula uma resposta válida da IA e verifica o parsing completo."""
        from app.cerebro import gestor

        candidatos = [
            _sugestao("BOVA11", preco=125.0, quantidade=8),
            _sugestao("PETR4", modulo="alpha", preco=35.0, quantidade=5),
        ]
        capital = 1200.0

        resposta_ia = json.dumps({
            "carteira_final": [
                {
                    "ticker": "BOVA11",
                    "modulo": "etfs",
                    "nome": "iShares IBOVESPA ETF",
                    "tipo": "ETF",
                    "valor_final": 875.0,
                    "preco_atual": 125.0,
                    "justificativa_ceo": "Core do portfólio em regime BULL.",
                },
                {
                    "ticker": "PETR4",
                    "modulo": "alpha",
                    "nome": "Petrobras PN",
                    "tipo": "ACAO",
                    "valor_final": 325.0,
                    "preco_atual": 35.0,
                    "justificativa_ceo": "Setup assimétrico claro com alvo definido.",
                },
            ],
            "analise": "Portfólio equilibrado em regime de alta.",
            "alertas": ["Atenção ao stop de PETR4"],
            "ajustes_realizados": ["Mantido BOVA11 como base"],
            "score_portfolio": 82,
        })

        with patch("app.cerebro.client.is_ai_configured", return_value=True), \
             patch("app.cerebro.client.chat", new_callable=AsyncMock, return_value=resposta_ia):

            resultado = asyncio.run(
                gestor.analisar(
                    candidatos=candidatos,
                    capital=capital,
                    estrategia="CORE",
                    regime="BULL",
                    score_perfil=8,
                )
            )

        assert resultado.usou_ia is True
        assert resultado.score_portfolio == 82
        assert "equilibrado" in resultado.analise.lower()
        tickers = [s.ticker for s in resultado.sugestoes_finais]
        assert "BOVA11" in tickers
        assert "PETR4" in tickers

    def test_ia_com_json_invalido_usa_fallback(self):
        """Se a IA retornar JSON mal formado, o gestor usa fallback."""
        from app.cerebro import gestor

        candidatos = [_sugestao("BOVA11")]

        with patch("app.cerebro.client.is_ai_configured", return_value=True), \
             patch("app.cerebro.client.chat", new_callable=AsyncMock, return_value="RESPOSTA INVÁLIDA"):

            resultado = asyncio.run(
                gestor.analisar(
                    candidatos=candidatos,
                    capital=1000.0,
                    estrategia="CORE",
                    regime="BULL",
                    score_perfil=8,
                )
            )

        # Deve cair no fallback algorítmico
        assert resultado.usou_ia is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. client.is_ai_configured
# ═══════════════════════════════════════════════════════════════════════════════

class TestClientIsAiConfigured:
    def test_sem_settings_file_nem_env_retorna_false(self, tmp_path):
        from app.cerebro import client
        import pathlib

        # Aponta SETTINGS_FILE para path temporário inexistente
        original = client.SETTINGS_FILE
        client.SETTINGS_FILE = tmp_path / "ai_settings.json"
        client._invalidate_settings_cache()

        # Garante que não há variável de ambiente de API key no ambiente
        with patch.dict(os.environ, {}, clear=False):
            with patch("app.config.ANTHROPIC_API_KEY", ""):
                result = client.is_ai_configured()

        client.SETTINGS_FILE = original

        # Sem arquivo e sem API key → False
        assert result is False

    def test_com_settings_valido_retorna_true(self, tmp_path):
        from app.cerebro import client

        settings = {
            "active": "openai",
            "providers": {
                "openai": {"api_key": "sk-test-1234", "model": "gpt-4o-mini"}
            }
        }
        settings_file = tmp_path / "ai_settings.json"
        settings_file.write_text(json.dumps(settings), encoding="utf-8")

        original = client.SETTINGS_FILE
        client.SETTINGS_FILE = settings_file
        client._invalidate_settings_cache()

        result = client.is_ai_configured()

        client.SETTINGS_FILE = original
        assert result is True


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Prompts
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrompts:
    def test_build_portfolio_prompt_contem_gestor_base(self):
        from app.cerebro.prompts import build_portfolio_prompt, GESTOR_BASE

        prompt = build_portfolio_prompt(
            user_name="João",
            estrategia="CORE",
            patrimonio=50_000.0,
            modulos_ativos=["etfs", "fiis"],
            tolerancia_drawdown=15.0,
            perfil_resumo="Moderado, 35 anos",
            posicoes=[],
            regime="BULL",
            macro={"selic": 10.5, "ibov": 125000},
        )

        assert GESTOR_BASE in prompt
        assert "CORE" in prompt
        assert "BULL" in prompt
        assert "João" in prompt

    def test_build_portfolio_prompt_estrategia_renda_tem_foco_yield(self):
        from app.cerebro.prompts import build_portfolio_prompt

        prompt = build_portfolio_prompt(
            user_name="Maria",
            estrategia="RENDA",
            patrimonio=100_000.0,
            modulos_ativos=["fiis", "renda_fixa"],
            tolerancia_drawdown=10.0,
            perfil_resumo="Conservadora",
            posicoes=[],
            regime="MISTO",
            macro={},
        )

        assert "yield" in prompt.lower() or "renda" in prompt.lower()

    def test_build_briefing_prompt_retorna_string(self):
        from app.cerebro.prompts import build_briefing_prompt

        prompt = build_briefing_prompt(
            user_name="Carlos",
            estrategia="ALPHA",
            posicoes=[],
            regime="BULL",
            macro={"selic": 10.5},
            data_hoje="2026-02-27",
        )

        assert isinstance(prompt, str)
        assert len(prompt) > 100
        assert "BULL" in prompt          # regime injetado
        assert "10.50" in prompt         # selic formatada


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Integração — fluxo completo do Cérebro
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegracaoCerebro:
    """
    Testa o pipeline completo:
      Especialistas → gestor.analisar → ResultadoGestorGeral
    Usa IA mockada para não depender de API real.
    """

    def test_pipeline_multi_modulo_resolve_duplicatas_e_retorna_portfolio(self):
        from app.cerebro import gestor

        # Simula candidatos de 3 especialistas, com 1 ticker duplicado (PETR4)
        candidatos = [
            _sugestao("BOVA11",  modulo="etfs",       preco=125.0,  quantidade=8),
            _sugestao("MXRF11",  modulo="fiis",        preco=10.5,   quantidade=100),
            _sugestao("PETR4",   modulo="alpha",       preco=36.0,   quantidade=10, score=0.9),
            _sugestao("PETR4",   modulo="momentum",    preco=36.0,   quantidade=8,  score=0.7),
            _sugestao("IMAB11",  modulo="renda_fixa",  preco=95.0,   quantidade=5),
        ]
        capital = 5_000.0

        # Monta a resposta esperada da IA com os 4 ativos únicos
        resposta_ia = json.dumps({
            "carteira_final": [
                {"ticker": "BOVA11", "modulo": "etfs",      "nome": "BOVA",   "tipo": "ETF",
                 "valor_final": 1250.0,  "preco_atual": 125.0, "justificativa_ceo": "Core BULL"},
                {"ticker": "MXRF11", "modulo": "fiis",      "nome": "MXRF",   "tipo": "FII",
                 "valor_final": 1050.0,  "preco_atual": 10.5,  "justificativa_ceo": "Renda FII"},
                {"ticker": "PETR4",  "modulo": "alpha",     "nome": "PETR4",  "tipo": "ACAO",
                 "valor_final": 1440.0,  "preco_atual": 36.0,  "justificativa_ceo": "Alpha tese clara"},
                {"ticker": "IMAB11", "modulo": "renda_fixa","nome": "IMAB11", "tipo": "ETF",
                 "valor_final": 1260.0,  "preco_atual": 95.0,  "justificativa_ceo": "Proteção inflação"},
            ],
            "analise": "Portfólio diversificado em 4 módulos.",
            "alertas": [],
            "ajustes_realizados": ["PETR4: mantido em Alpha por maior score"],
            "score_portfolio": 80,
        })

        with patch("app.cerebro.client.is_ai_configured", return_value=True), \
             patch("app.cerebro.client.chat", new_callable=AsyncMock, return_value=resposta_ia):

            resultado = asyncio.run(
                gestor.analisar(
                    candidatos=candidatos,
                    capital=capital,
                    estrategia="CORE",
                    regime="BULL",
                    score_perfil=10,
                )
            )

        assert resultado.usou_ia is True
        tickers = [s.ticker for s in resultado.sugestoes_finais]
        assert "PETR4" in tickers
        assert "BOVA11" in tickers

        # Apenas 1 PETR4 no resultado (CEO resolveu a duplicata)
        assert tickers.count("PETR4") == 1

        # Score válido
        assert 0 <= resultado.score_portfolio <= 100

        # Soma total próxima do capital (tolerância de R$1 por arredondamento)
        total = sum(s.valor_total for s in resultado.sugestoes_finais)
        assert total == pytest.approx(capital, abs=1.0)

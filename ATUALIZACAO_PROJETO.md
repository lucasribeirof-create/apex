# APEX Manager — Atualização do Projeto

**Data:** 02/03/2026

---

## Visão geral

O **APEX Manager** é um app de gestão de portfólio com IA: onboarding de perfil, estratégia (CORE/ALPHA/RENDA), motores especializados por classe de ativo e um **CEO Brain** (Gestor Geral) que decide a carteira final.

- **Backend:** FastAPI + SQLAlchemy + SQLite (`backend/app`)
- **Frontend:** React 18 + TypeScript + Vite + Zustand (`frontend/src`)
- **IA:** Anthropic, OpenAI, Gemini, Groq ou Grok (configurável em Configurações → Motor de IA)

---

## Estrutura principal

### Backend (`backend/app`)

| Área | O que faz |
|------|-----------|
| **`cerebro/`** | Cérebro do app: `gestor.py` (CEO Brain), `macro.py` (MacroEngine), `contexto.py` (ContextoCerebro), `plano.py` (Estrategista), `narrativa.py`, `teses.py`, `risco.py`, `radar.py`, `aprendizado.py` |
| **`cerebro/especialistas/`** | Motores: ETFs, FIIs, Renda Fixa, Momentum, Wheel, Alpha, Dividendos + `prefetch.py` (yFinance em lote), `watchlist.py` |
| **`api/routes/`** | Rotas: onboarding, dashboard, portfolio, market, briefing, chat, scanner, teses, transacoes, settings |
| **`models/`** | User, Portfolio, Position, Transacao, Aporte, Briefing, TeseInvestimento, TradeJournal |
| **`data/`** | yfinance, BCB, BRAPI, cache, bcb_client, brapi, tecnico, news_collector |
| **`core/`** | regime.py, universe.py, scanner.py, filters.py, score.py |

### Frontend (`frontend/src`)

| Página | Função |
|--------|--------|
| **Onboarding** | Wizard de perfil (13 passos) → estratégia + alocação alvo → escolha "Já tenho investimentos" ou "Criar do zero" |
| **Briefing** | Resumo diário; botões para "Criar carteira do zero" e "Já tenho investimentos" (ir para posições) |
| **SugestoesAlocacao** | Tela após "APEX analisando portfólio...": mostra análise do Gestor Geral + lista de ativos sugeridos para aprovar |
| **Positions** | Posições da carteira |
| **Dashboard** | Métricas, alocação, regime, macro |
| **Scanner, Teses, Chat, Settings, AISetup** | Demais funcionalidades |

---

## Fluxo "Criar carteira do zero"

1. Usuário faz onboarding → finaliza com estratégia e alocação alvo.
2. Na tela de resultado do onboarding, escolhe **"Estou começando do zero"**.
3. Frontend navega para **SugestoesAlocacao** com `portfolioId` e `modo: 'inicial'`.
4. **SugestoesAlocacao** chama `POST /portfolio/sugerir-portfolio` (portfolio_id, modo).
5. Backend: prefetch de tickers → motores em paralelo → **montar_contexto** (macro, narrativa, regime) → **CEO Brain** (`gestor.analisar`) → resposta com `gestor_analise` + `sugestoes`.
6. Frontend exibe: card **Gestor Geral** (análise, alertas, score, regime) + **lista de ativos** por módulo. Usuário aprova/rejeita e aplica.

---

## O que aparece hoje em SugestoesAlocacao

- **Sim:** análise do CEO (`gestor_analise.analise`), alertas, ajustes realizados, score do portfólio, regime, e a lista de ativos sugeridos (carteira).
- **Não:** não existe na API nem na tela um bloco dedicado de **"análise macro"** (ex.: resumo Selic, VIX, dólar, cenário) nem de **"sugestão real de estratégia"** (diagnóstico, cenários, marcos, riscos) como conteúdo separado.

O CEO Brain já usa macro e contexto dentro do backend (via `ContextoCerebro` e `montar_contexto`), mas isso só vira o **parágrafo de análise** (`analise`) e as decisões nos ativos. Não há um "plano estratégico" (diagnóstico, cenários, riscos) sendo retornado por `sugerir-portfolio` nem exibido na tela.

---

## CEO Brain e tempo de resposta

- **Timeout atual:** 60 s em `gestor.analisar`. Se a IA não responder a tempo ou der erro, cai no **fallback algorítmico** (carteira sem análise da IA).
- **Ordem de grandeza do fluxo:** prefetch (2–60 s) → motores (5–30 s) → contexto (2–25 s, inclui narrativa IA) → CEO Brain (até 60 s). Total típico: de ~1 a 3 minutos.
- **Plano de otimização** (já discutido em sessão anterior): corrigir parser JSON da resposta da IA (evitar fallback por markdown), paralelizar prefetch + contexto, reduzir payload e adicionar logs de tempo.

---

## Dados e integrações

- **Preços e histórico:** yFinance (sufixo `.SA` para B3).
- **Macro Brasil:** BCB/SGS (Selic, IPCA), Olinda (Focus), yFinance (dólar, IBOV).
- **Macro global:** yFinance (Treasury 10Y, VIX, DXY, S&P 500, ouro, petróleo).
- **Cache:** em memória (TTLs por tipo); sem Redis — perde ao reiniciar o servidor.

---

## Como rodar

- **Tudo:** `INICIAR.bat` (backend + frontend).
- **Só frontend (backend no Cursor):** `INICIAR_DEV.bat`.
- **Backend manual:** `cd backend` → `python -m uvicorn app.main:app --reload`.
- **Frontend:** normalmente em `http://localhost:3000` ou 5173.

---

## Documentos de contexto

- **SESSAO_CONTEXTO.md** — Sprint A (concluído), Sprint B (Wheel) planejado; bugs e features da sessão de 25–26/02.
- **Briefing/** — Instruções e briefing do projeto para a IA.

Se quiser que a tela após "APEX analisando portfólio" mostre **análise macro** e **sugestão de estratégia** (plano com diagnóstico/cenários) como blocos separados, isso exigiria: (1) o backend passar a gerar/retornar esse plano (ex.: no CEO quando `modo=inicial` ou reutilizando o Estrategista) e (2) o frontend exibir esse bloco em **SugestoesAlocacao**, antes ou junto do card do Gestor Geral.

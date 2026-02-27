# APEX — Contexto da Sessão (continuar daqui)

**Data:** 26/02/2026  
**Status:** Sprint A ✅ COMPLETO — Sprint B pronto para iniciar

---

## Sprint A — O que foi feito (tudo ✅)

### Bugs corrigidos

| Bug | Arquivo | Descrição |
|-----|---------|-----------|
| 1 | `backend/app/api/routes/chat.py` | `/proposta` usava `portfolio.alvo_etfs` (alvos) em vez da alocação real → criado `_calcular_alocacao_real()` |
| 2 | `backend/app/core/regime.py` | BULL declarado mesmo sem dados de breadth → agora `breadth_pct is None` retorna MISTO |
| 3 | `backend/app/ai/prompts.py` | Crash quando `preco_atual` era None em `_formatar_posicoes()` → fallback para `preco_medio` |
| 4 | `backend/app/api/routes/portfolio.py` | `encerrar_posicao()` sem verificação de ownership → filtro por `Position.portfolio_id == portfolio.id` |
| 5 | `backend/app/tasks/morning_briefing.py` + `portfolio.py` | `datetime.utcnow()` deprecated → `datetime.now(timezone.utc)` |

### Features entregues

| Tarefa | Arquivo(s) | Descrição |
|--------|-----------|-----------|
| 1 | `backend/app/data/bcb_client.py` *(NOVO)* | Cliente BCB/SGS: `get_selic()` (série 1178) + `get_ipca()` (série 433), TTL 600s. Injetado em `get_macro_br()` via `asyncio.gather`. |
| 2 | `backend/app/core/universe.py` *(NOVO)* | 82 ativos: 50 ações + 13 ETFs + 15 FIIs + 4 outros. `SETOR_PROXY` map (11 setores). Funções: `get_universe()`, `get_tickers()`, `get_setor_proxy()`, `get_ticker_info()`. |
| 3 | `backend/app/core/scanner.py` *(NOVO)* + `backend/app/api/routes/scanner.py` *(NOVO)* | Pipeline completo de scan: IBOV → regime → proxies setoriais → 82 ativos (semaphore 8) → filtros → score → trade_setup. Endpoint `GET /scanner/scan`. Registrado em `main.py`. |
| 4 | `backend/app/api/routes/market.py` | Novo endpoint `GET /market/regime`: busca IBOV via `get_history_global("^BVSP")`, chama `calcular_regime()` + `get_acoes_permitidas_regime()`. Cache 1h. |
| 5 | `frontend/src/pages/Dashboard.tsx` | Substituídos todos os mocks por dados reais: `GET /dashboard/` (patrimônio, alocação), `GET /market/regime` (regime + motivo). Loading state com spinner. |

---

## Sprint B — Módulo Wheel (próximo)

### Fonte: `E:\Dropbox\apps_criados\wheel`

Estrutura relevante (ignorar `venv`, `wheel_bkp_*`):

```
wheel/
├── web/
│   ├── fetch_b3_options.py   ← cadeia de opções via B3 COTAHIST (gratuito, oficial)
│   ├── fetch_stock_price.py  ← preço + MM50/200/ATR/RSI/força relativa vs IBOV
│   ├── analise_rolagem.py    ← lógica de rolagem de puts/calls
│   ├── posicoes.py           ← CRUD de posições do Wheel no SQLite
│   └── database.py           ← schema SQLite do Wheel standalone
├── visualization/
│   └── plot_chart.py         ← gráficos (não portar — frontend usa Recharts)
├── app_web.py                ← FastAPI standalone do Wheel (referência para rotas)
├── app_gui.py                ← GUI Tkinter (ignorar)
├── main.py                   ← entry point standalone
└── wheel.db                  ← banco standalone (ignorar — usar apex.db)
```

### O que portar para o APEX

| Componente | De onde | Para onde |
|-----------|---------|-----------|
| B3 COTAHIST (opções) | `web/fetch_b3_options.py` | `backend/app/data/b3_options.py` |
| Indicadores técnicos aprimorados | `web/fetch_stock_price.py` | Funções adicionais em `backend/app/data/yfinance_client.py` ou `b3_options.py` |
| Lógica de rolagem | `web/analise_rolagem.py` | `backend/app/core/wheel.py` |
| Endpoints Wheel | `app_web.py` | `backend/app/api/routes/wheel.py` |
| Modelo de dados | `web/database.py` | Adicionar `WheelPosition` em `backend/app/models.py` |

### Tarefas Sprint B (ordem sugerida)

1. **Leitura dos arquivos fonte** — ler `fetch_b3_options.py`, `fetch_stock_price.py`, `analise_rolagem.py`, `posicoes.py`, `app_web.py` para mapear o que exatamente existe
2. **Modelo `WheelPosition`** — adicionar em `models.py` (ativo, strike, vencimento, tipo PUT/CALL, prêmio, status, etc.)
3. **`b3_options.py`** — portar lógica COTAHIST adaptada para async + cache
4. **`core/wheel.py`** — portar `analise_rolagem.py`: análise de rolagem, seleção de strike, cálculo de yield
5. **`api/routes/wheel.py`** — endpoints: `GET /wheel/candidatos`, `POST /wheel/iniciar`, `GET /wheel/posicoes`, `POST /wheel/rolar`, `POST /wheel/encerrar`
6. **`frontend/src/pages/Wheel.tsx`** — página já existe? Verificar e adaptar

### Regras do Sprint B (mesmas do A)

- Uma tarefa por vez: mostrar plano → esperar aprovação → implementar → aprovação → avançar
- **NÃO reescrever** o que já existe funcionando no APEX
- **NÃO implementar**: Backtest, Relatórios, Docker, PostgreSQL, Redis, testes

---

## Referências técnicas

- **Backend:** FastAPI + SQLAlchemy + SQLite em `E:\Dropbox\apps_criados\APEX\data\apex.db`
- **yFinance B3:** sufixo `.SA` para ações (ex: `PETR4` → `PETR4.SA`), `^` para índices (`^BVSP`)
- **`get_history_global(ticker, period, interval)`** → retorna `list[{date, open, high, low, close, volume}]`
- **`get_history(ticker, period, interval)`** (BRAPI) → retorna `list` de candles (formato diferente — usar yFinance para indicadores)
- **BCB API:** `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json`
- **B3 COTAHIST:** download diário gratuito — `bvmf.bmfbovespa.com.br` (já implementado no Wheel standalone)
- **Score thresholds:** ≥75 = trade (com trade_setup), 50–74 = monitor, <50 = fora
- **Cache TTLs:** quotes=60s, indicators=300s, macro=600s, scan=4h (14400s), regime=3600s
- **Semaphore scanner:** lazy-init `asyncio.Semaphore(8)` (evita erro de event loop no import)

---

## Como retomar

1. Abrir este arquivo
2. Dizer: **"Leia o SESSAO_CONTEXTO.md e leia os arquivos do Wheel para mapear o Sprint B"**
3. O assistente lerá os 5 arquivos fonte do Wheel e apresentará o plano detalhado da Tarefa 1 do Sprint B


**Data:** 25/02/2026  
**Status:** Sprint A em andamento — Tarefas 4 e 5 pendentes

---

## O que foi feito nesta sessão

### Bugs corrigidos (todos ✅)

| Bug | Arquivo | Descrição |
|-----|---------|-----------|
| 1 | `backend/app/api/routes/chat.py` | `/proposta` usava `portfolio.alvo_etfs` (alvos) em vez da alocação real → criado `_calcular_alocacao_real()` |
| 2 | `backend/app/core/regime.py` | BULL declarado mesmo sem dados de breadth → agora `breadth_pct is None` retorna MISTO |
| 3 | `backend/app/ai/prompts.py` | Crash quando `preco_atual` era None em `_formatar_posicoes()` → fallback para `preco_medio` |
| 4 | `backend/app/api/routes/portfolio.py` | `encerrar_posicao()` sem verificação de ownership → filtro por `Position.portfolio_id == portfolio.id` |
| 5 | `backend/app/tasks/morning_briefing.py` + `portfolio.py` | `datetime.utcnow()` deprecated → `datetime.now(timezone.utc)` |

### Features entregues (todas ✅)

| Tarefa | Arquivo(s) | Descrição |
|--------|-----------|-----------|
| 1 | `backend/app/data/bcb_client.py` *(NOVO)* | Cliente BCB/SGS: `get_selic()` (série 1178) + `get_ipca()` (série 433), TTL 600s. Injetado em `get_macro_br()` via `asyncio.gather`. |
| 2 | `backend/app/core/universe.py` *(NOVO)* | 82 ativos: 50 ações + 13 ETFs + 15 FIIs + 4 outros. `SETOR_PROXY` map (11 setores). Funções: `get_universe()`, `get_tickers()`, `get_setor_proxy()`, `get_ticker_info()`. |
| 3 | `backend/app/core/scanner.py` *(NOVO)* + `backend/app/api/routes/scanner.py` *(NOVO)* | Pipeline completo de scan: IBOV → regime → proxies setoriais → 82 ativos (semaphore 8) → filtros → score → trade_setup. Endpoint `GET /scanner/scan`. Registrado em `main.py`. |

### Arquivos modificados (além dos novos)

- `backend/app/data/brapi.py` — import asyncio + `get_macro_br()` paralelo com BCB
- `backend/app/data/__init__.py` — exports `get_selic`, `get_ipca`
- `backend/app/core/__init__.py` — exports `get_universe`, `get_tickers`, `get_setor_proxy`, `get_ticker_info`, `executar_scan`
- `backend/app/api/routes/__init__.py` — export `scanner`
- `backend/app/main.py` — import + `app.include_router(scanner.router)`

---

## O que falta (próximas tarefas)

### ❌ Tarefa 4 — `GET /market/regime`

**Arquivo:** `backend/app/api/routes/market.py`

**O que fazer:**
1. Buscar histórico do IBOV via yFinance (`^BVSP`) — precisa de ~200 dias de fechamentos
2. Chamar `calcular_regime(closes)` do `backend/app/core/regime.py`
3. Chamar `get_acoes_permitidas_regime(regime)` para o dict de ações permitidas
4. Retornar JSON: `{ regime: "BULL"|"MISTO"|"BEAR", motivo: str, detalhes: dict, acoes: dict }`

**Atenção:** a função se chama `calcular_regime()` (não `classificar_regime()`).  
**Atenção:** verificar assinatura exata de `calcular_regime()` em `regime.py` antes de implementar.

---

### ❌ Tarefa 5 — `Dashboard.tsx` com dados reais

**Arquivo:** `frontend/src/pages/Dashboard.tsx`

**O que fazer:**
- `useEffect` na montagem → `GET /dashboard/` (resumo do portfolio)
- `GET /market/macro` → dados macro (dólar, IBOV, Selic, IPCA)
- `GET /market/regime` → badge de regime (depende da Tarefa 4)
- Substituir TODOS os valores mock (ex: "R$ 485.200", "+4,8%") por dados reais
- Manter layout, animações e estilos — só trocar a fonte dos dados
- Mostrar loading state enquanto carrega

---

## Regras desta sessão (não mudar)

- Uma tarefa por vez: mostrar código → esperar aprovação → avançar
- **NÃO reescrever** arquivos existentes que já funcionam: `brapi.py`, `yfinance_client.py`, `cache.py`, `filters.py`, `score.py`, `regime.py`, `prompts.py`, `ai/client.py`
- **NÃO implementar** nesta fase: Wheel, Backtest, Relatórios, Docker, PostgreSQL, Redis, testes

---

## Referências técnicas

- **Backend:** FastAPI + SQLAlchemy + SQLite em `E:\Dropbox\apps_criados\APEX\data\apex.db`
- **yFinance B3:** sufixo `.SA` para ações (ex: `PETR4` → `PETR4.SA`), `^` para índices (`^BVSP`)
- **BCB API:** `https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json`
- **Score thresholds:** ≥75 = trade (com trade_setup), 50–74 = monitor, <50 = fora
- **Cache TTLs:** quotes=60s, indicators=300s, macro=600s, scan=4h (14400s)
- **Semaphore:** lazy-init `asyncio.Semaphore(8)` no scanner (evita erro de event loop no import)
- **Projeto Wheel existente:** `E:\Dropbox\apps_criados\wheel` — a ser portado no Sprint B (não agora)

---

## Como retomar

1. Abrir este arquivo para relembrar o contexto
2. Dizer ao assistente: *"Leia o SESSAO_CONTEXTO.md e execute a Tarefa 4"*
3. Aguardar código → aprovar → Tarefa 5 → Sprint A concluído

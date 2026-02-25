# APEX MANAGER — Instruções para Claude Code
### Cole este documento inteiro no Claude Code do VS Code

---

## QUEM VOCÊ É

Você é o desenvolvedor principal do APEX Manager. O diretor do projeto (o usuário) não é programador — ele diz O QUE quer e você resolve COMO fazer. Nunca peça para ele tomar decisões técnicas. Tome você e explique de forma simples o que fez.

---

## O QUE É O APEX MANAGER

Um sistema web de gestão ativa de portfólio com IA integrada. A IA (Claude) é o gestor de patrimônio — ela analisa o mercado, identifica oportunidades, gerencia posições e explica cada decisão. O app é para um único usuário por enquanto (sem sistema de login).

---

## DECISÕES JÁ TOMADAS

- **Plataforma:** Web primeiro (abre no navegador), depois vira app mobile
- **Usuários:** Apenas 1 por enquanto (sem autenticação)
- **Visual:** Dark mode, cores preto/branco/verde (#00E676), profissional e premium
- **Abordagem:** Etapa por etapa, testar cada coisa antes de avançar
- **Banco de dados:** SQLite local (arquivo `apex.db` na pasta do projeto) — sem servidor, sem Docker
- **Cache:** Em memória Python (sem Redis) — simples e suficiente para 1 usuário
- **Infraestrutura:** Rodando direto no Windows com Python + Node.js, sem Docker
- **Código:** Nenhuma modificação ou criação de código sem autorização explícita do diretor

> **NOTA SOBRE MIGRAÇÃO FUTURA:** Quando o app estiver funcionando e testado, migrar para
> PostgreSQL + Redis + Docker Compose para uso em produção/nuvem. A estrutura do código
> (SQLAlchemy, FastAPI) foi pensada para que essa migração seja simples — troca a URL do
> banco no `.env` e sobe o Docker. Não é necessário reescrever lógica de negócio.

---

## STACK TECNOLÓGICA

### Backend (fase atual — local Windows):
- Python 3.11+
- FastAPI (API REST)
- **SQLite** (banco de dados local — arquivo `apex.db` na pasta do projeto)
- **Cache em memória Python** (dicionário com TTL manual — sem Redis)
- **Scheduler APScheduler** (tarefas agendadas: morning briefing — sem Celery/Redis)
- Sem Docker — roda direto com `uvicorn`

### Backend (fase futura — produção/nuvem):
- PostgreSQL (substituir SQLite — apenas trocar URL no `.env`)
- Redis (substituir cache em memória)
- Celery + Redis (substituir APScheduler)
- Docker + Docker Compose

### Frontend:
- React.js com TypeScript
- Design system próprio (dark mode)
- TradingView Lightweight Charts (gráficos de preço)
- Recharts (gráficos de performance, alocação)
- Fontes: DM Sans (corpo) + Space Mono (dados/números)
- Cores: background #0a0e17, verde principal #00E676, verde secundário #00BFA5

### APIs de Dados:
- BRAPI (cotações brasileiras em tempo real, histórico, busca)
- yFinance (dados históricos globais, BDRs, ETFs internacionais)
- Anthropic API (motor de IA — Claude Sonnet para chamadas do app)

---

## ESTRUTURA DE PASTAS

```
apex-manager/
├── backend/
│   ├── app/
│   │   ├── api/            # Endpoints FastAPI
│   │   │   ├── __init__.py
│   │   │   ├── routes/
│   │   │   │   ├── onboarding.py
│   │   │   │   ├── portfolio.py
│   │   │   │   ├── scanner.py
│   │   │   │   ├── market.py
│   │   │   │   ├── briefing.py
│   │   │   │   └── chat.py
│   │   │   └── deps.py     # Dependências compartilhadas
│   │   ├── core/            # Lógica APEX (filtros, score, sizing)
│   │   │   ├── filters.py   # 5 filtros APEX sequenciais
│   │   │   ├── score.py     # Score 0-100
│   │   │   ├── regime.py    # BULL/MISTO/BEAR
│   │   │   ├── risk.py      # Orquestrador de risco
│   │   │   └── sizing.py    # Tamanho de posição
│   │   ├── modules/         # Um diretório por módulo
│   │   │   ├── momentum/
│   │   │   ├── wheel/
│   │   │   ├── etfs/
│   │   │   ├── fiis/
│   │   │   ├── renda_fixa/
│   │   │   └── alpha/
│   │   ├── ai/              # Integração Claude API
│   │   │   ├── client.py    # Cliente Anthropic
│   │   │   ├── prompts.py   # System prompts
│   │   │   └── context.py   # Builder de contexto do portfólio
│   │   ├── data/            # Integração APIs de dados
│   │   │   ├── brapi.py     # BRAPI client
│   │   │   ├── yfinance_client.py
│   │   │   └── cache.py     # Cache em memória (dict + TTL)
│   │   ├── models/          # Modelos SQLAlchemy / SQLite (migra para PostgreSQL no futuro)
│   │   │   ├── user.py
│   │   │   ├── portfolio.py
│   │   │   ├── position.py
│   │   │   ├── strategy.py
│   │   │   └── briefing.py
│   │   ├── tasks/           # Tarefas agendadas (APScheduler)
│   │   │   ├── morning_briefing.py
│   │   │   └── scanner.py
│   │   ├── config.py        # Configurações e env vars
│   │   └── main.py          # App FastAPI entry point
│   ├── tests/
│   ├── requirements.txt
│   ├── start.bat            # Script para rodar no Windows com 1 clique
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Onboarding.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Briefing.tsx
│   │   │   ├── Positions.tsx
│   │   │   ├── Scanner.tsx
│   │   │   ├── Analysis.tsx
│   │   │   ├── Chat.tsx
│   │   │   ├── Contributions.tsx
│   │   │   └── Reports.tsx
│   │   ├── components/
│   │   │   ├── ui/          # Design system (botões, cards, inputs)
│   │   │   ├── charts/      # Componentes de gráfico
│   │   │   ├── layout/      # Header, sidebar, navigation
│   │   │   └── onboarding/  # Steps do onboarding
│   │   ├── hooks/
│   │   ├── services/        # Chamadas à API backend
│   │   ├── types/           # TypeScript types
│   │   ├── styles/          # Theme, cores, variáveis
│   │   └── App.tsx
│   ├── public/
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   └── vite.config.ts
├── .env.example
└── README.md
```

---

## ETAPA ATUAL: SPRINT 1 — CORE DO APP

Construir as 5 telas essenciais nesta ordem:

### TELA 1 — ONBOARDING (prioridade máxima)

Conversa guiada pela IA para entender o perfil do investidor. NÃO é um formulário frio — é uma conversa com personalidade.

**Fluxo de telas:**
1. Welcome screen (logo APEX, botão "Iniciar Onboarding")
2. Pergunta o nome
3. Pergunta o patrimônio total (campo monetário R$)
4. Pergunta o objetivo — COM 4 OPÇÕES FLEXÍVEIS:
   - "Quero chegar em um valor" → campo R$ + seleção de prazo (3, 5, 10, +10 anos)
   - "Quero render X% ao ano" → campo percentual
   - "Quero viver de renda" → campo R$/mês
   - "Quero explicar do meu jeito" → campo de texto livre
5. Cenário de volatilidade: "Portfólio cai 20%, o que faz?" (4 opções)
6. Liquidez nos próximos 12 meses (4 opções)
7. Fonte de renda: ativa, parcial ou depende do portfólio (3 opções)
8. Experiência: multi-select (ações BR, FIIs, RF, opções, exterior, ETFs, nenhuma)
9. Tempo disponível por semana (4 opções)
10. Objetivo principal: crescimento / renda passiva / preservação / equilíbrio (4 opções)
11. Horizonte temporal: até 2, 2-5, 5-10, +10 anos (4 opções)
12. Tela de resultado: IA apresenta a estratégia (CORE ou ALPHA) com raciocínio completo + gráfico de alocação

**Tom da IA nas perguntas:**
- Direto, confiante, sem ser arrogante
- Usa cenários reais, não perguntas teóricas
- Cada pergunta tem uma introdução da IA explicando POR QUE está perguntando
- O texto aparece com efeito typewriter (digitando)

**Lógica de classificação:**
- Score baseado nas respostas (volatilidade, liquidez, renda, experiência, objetivo, horizonte, tempo)
- Score >= 11 pontos → APEX ALPHA
- Score < 11 pontos → APEX CORE

**Alocação APEX CORE:**
- ETFs: 35%, FIIs: 20%, Renda Fixa: 20%, Momentum: 15%, Caixa: 10%

**Alocação APEX ALPHA:**
- ETFs: 25%, Momentum: 20%, FIIs: 15%, Renda Fixa: 15%, Wheel: 10%, Convicção: 10%, Caixa: 5%

### TELA 2 — DASHBOARD PRINCIPAL

Tela que o investidor vê todo dia após o onboarding.

- Patrimônio total em tempo real com variação do dia
- Alocação atual vs alvo por módulo com semáforo de desvio (verde/amarelo/vermelho)
- Performance: dia, semana, mês, ano, desde o início
- Gráfico comparativo vs IBOV, CDI e S&P500
- Renda gerada no mês (dividendos, FIIs, prêmios Wheel)
- Semáforo de regime de mercado: BULL (verde) / MISTO (amarelo) / BEAR (vermelho)
- Projeção de patrimônio com cenários conservador e otimista

### TELA 3 — MORNING BRIEFING

Resumo diário gerado pela IA antes das 9h.

- Leitura macro: Selic, dólar, commodities, futuros IBOV e S&P500
- Regime de mercado com semáforo visual
- Posições que precisam de atenção (stops próximos, opções vencendo)
- Oportunidades identificadas pelo scanner
- Calendário de eventos (resultados trimestrais, decisões de juros)
- Tudo contextualizado para o portfólio específico do usuário

### TELA 4 — POSIÇÕES ABERTAS

Lista de tudo que o investidor tem:

- Ações: preço médio, stop atual, performance, score APEX, dias em posição
- FIIs e ETFs: cota média, yield atual, desvio da alocação alvo
- Opções Wheel: strike, vencimento, delta, prêmio, % lucro, sugestão de ação
- Renda Fixa: indexador, taxa, duration, vencimento

### TELA 5 — CHAT COM O GESTOR

Interface de conversa com a IA.

- Usuário pergunta qualquer coisa sobre o portfólio
- IA sempre recebe o contexto completo (posições, estratégia, regime, dados macro)
- Respostas com raciocínio completo e dados
- Pode pedir análise de qualquer ativo
- Pode solicitar revisão da estratégia

---

## DESIGN SYSTEM

### Cores:
```
--bg-primary: #0a0e17
--bg-secondary: #0f1729
--bg-card: rgba(15, 23, 42, 0.6)
--border: #1e293b
--text-primary: #f1f5f9
--text-secondary: #94a3b8
--text-muted: #64748b
--green-primary: #00E676
--green-secondary: #00BFA5
--green-light: #1DE9B6
--green-pale: #64FFDA
--green-surface: #A7FFEB
--yellow: #FFD740
--red: #FF5252
--red-surface: rgba(255, 82, 82, 0.1)
--yellow-surface: rgba(255, 215, 64, 0.1)
--green-surface-alpha: rgba(0, 230, 118, 0.08)
```

### Tipografia:
- Corpo: DM Sans (Google Fonts)
- Dados/números/monospace: Space Mono (Google Fonts)
- Títulos grandes: DM Sans 600-700
- Labels: Space Mono 13px com letter-spacing

### Componentes base:
- Cards com background semi-transparente + borda sutil (#1e293b)
- Botões primários: gradiente verde (#00E676 → #00BFA5)
- Inputs: fundo escuro, borda #1e293b, foco muda borda para #00E676
- Semáforos: verde/amarelo/vermelho com background suave
- Barras de alocação com animação suave
- Efeito typewriter para textos da IA

---

## COMO TRABALHAR

1. **REGRA ABSOLUTA:** Nunca escrever ou modificar código sem autorização explícita do diretor
2. **Um passo de cada vez** — não construa tudo junto
3. **Explique o que vai fazer antes de fazer** — aguarde o "sim" do diretor
4. **Comece pela estrutura de pastas + banco SQLite + FastAPI rodando**
5. **Depois o backend do onboarding**
6. **Depois o frontend do onboarding**
7. **Teste, peça feedback, ajuste**
8. **Só então avance para a próxima tela**

Quando o diretor mostrar um erro, analise o traceback completo e corrija.
Nunca tome decisões técnicas que impactem arquitetura sem apresentar as opções primeiro.

---

## ORDEM DE DESENVOLVIMENTO

Aguardar autorização do diretor para cada etapa antes de iniciar:

**Etapa 1 — Infraestrutura base:**
1. Limpar arquivos Docker desnecessários (`docker-compose.yml`, `Dockerfile`)
2. Criar estrutura de pastas definitiva
3. Configurar banco SQLite com SQLAlchemy
4. Criar modelos de banco (User, Portfolio, Strategy, Position)
5. Endpoint de saúde (`GET /health`)
6. Script `start.bat` para rodar com um clique

**Etapa 2 — Onboarding (após aprovação da Etapa 1):**
- Backend + Frontend do onboarding completo

**Etapa 3 — Dashboard (após aprovação do Onboarding):**
- Integração BRAPI + dashboard patrimonial

*(e assim por diante — uma etapa por vez)*

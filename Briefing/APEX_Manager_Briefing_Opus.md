# APEX MANAGER — Briefing Completo do Projeto
### Documento para início de desenvolvimento | Versão 2.0 | Fevereiro 2026

---

## ⚠️ DECISÃO DE INFRAESTRUTURA — ATUALIZADO EM FEVEREIRO 2026

**A stack de infraestrutura deste documento foi ajustada para a fase atual de desenvolvimento:**

| Componente | Especificado neste doc | **Fase atual (local Windows)** |
|---|---|---|
| Banco de dados | PostgreSQL | **SQLite** (arquivo `apex.db`) |
| Cache | Redis | **Cache em memória Python** |
| Tarefas agendadas | Celery + Redis | **APScheduler** |
| Infraestrutura | Docker + Docker Compose | **Direto no Windows** |

**Motivo:** O sistema é para 1 usuário em ambiente local. Docker adiciona complexidade desnecessária nesta fase.

**Migração futura:** Quando o app estiver funcionando e validado, migrar para PostgreSQL + Redis + Docker é simples — apenas troca a URL de conexão no `.env`. Nenhuma lógica de negócio precisa ser reescrita.

**Regra de desenvolvimento:** Nenhuma escrita ou modificação de código sem autorização explícita do diretor do projeto.

---

## CONTEXTO FUNDAMENTAL — LEIA ANTES DE TUDO

Este documento descreve um sistema de gestão de portfólio com inteligência artificial chamado **APEX Manager**. Você, o modelo de IA, **é o gestor**. Não é uma ferramenta passiva que responde perguntas — você é um gestor de patrimônio de elite que toma decisões ativas, analisa o mercado, identifica oportunidades, constrói teses de investimento e gerencia o portfólio do usuário com raciocínio completo e transparente.

**Seu perfil como gestor:**
Você tem conhecimento profundo dos maiores investidores e traders da história: Jim Simons (quant/momentum), Stanley Druckenmiller (macro global), Warren Buffett (value/concentração), George Soros (macro/assimetria), Ray Dalio (all weather/ciclos), Peter Lynch (growth/fundamentos). Você domina todas as estratégias e mercados: momentum, value investing, arbitragem, macro global, opções (Wheel, LEAPS, calls e puts direcionais, spreads), ETFs, renda fixa, FIIs, ações brasileiras e americanas, BDRs e mercados internacionais.

Você pensa e age como gestor institucional de alto nível voltado para pessoa física de alto patrimônio. Sua missão é buscar o maior retorno possível ajustado ao risco, batendo consistentemente os principais benchmarks. Você é honesto, direto e explica cada decisão com raciocínio completo.

---

## 1. O QUE É O APEX MANAGER

O APEX Manager é um **sistema profissional de gestão ativa de portfólio com IA integrada** desenvolvido para investidores pessoa física de alto patrimônio. Ele não é um app de acompanhamento passivo — é um gestor ativo que analisa o mercado diariamente, identifica oportunidades, gerencia posições abertas e executa rebalanceamentos baseados em dados reais.

**O problema que resolve:** Nenhuma plataforma disponível no mercado brasileiro para pessoa física integra de forma unificada scanner de momentum quantitativo, gestão de Wheel Strategy, controle de drawdown, análise macro automatizada, backtest e motor de IA explicativo. O investidor hoje precisa de 5 a 8 ferramentas diferentes. O APEX Manager resolve tudo em uma única interface.

**O diferencial central:** A combinação de três camadas simultâneas:
1. Algoritmos quantitativos do sistema APEX
2. Leitura de contexto macroeconômico em tempo real
3. Motor de IA (você) que explica cada sugestão em linguagem natural com raciocínio completo

O investidor não recebe só o sinal — recebe o raciocínio completo por trás de cada decisão.

---

## 2. FLUXO PRINCIPAL — ONBOARDING COM IA

O onboarding é o coração do sistema. **É a primeira coisa que acontece** quando um novo usuário entra no app. Nada funciona antes de completar o onboarding.

### Fase 1 — Diagnóstico (Questionário Inteligente)

A IA conduz uma conversa estruturada para entender o perfil real do usuário. Não são campos de formulário frios — é uma conversa com raciocínio contextual.

**Dimensões avaliadas:**

- **Patrimônio e objetivos:** Valor atual total (R$), objetivo em 5 anos, objetivo em 10 anos
- **Tolerância real a volatilidade:** Não teórica. Use cenários reais: *"Se seu portfólio caísse 20% em 3 meses e os fundamentos continuassem intactos, qual seria sua reação: venderia tudo, venderia parte, manteria ou compraria mais?"*
- **Liquidez:** Necessidade de resgate nos próximos 12 meses (% do patrimônio)
- **Renda:** Investe com renda ativa (salário/empresa) ou depende do portfólio para renda corrente?
- **Experiência:** Já operou renda variável? Já operou opções? Já investiu no exterior?
- **Tempo disponível:** Horas por semana para acompanhar o portfólio
- **Objetivo principal:** Crescimento máximo / renda passiva / preservação / equilíbrio
- **Horizonte temporal:** Prazo mínimo sem precisar do capital

### Fase 2 — A IA Elabora a Estratégia

Com base no diagnóstico, a IA **não apenas classifica o usuário** — ela gera um documento personalizado com a estratégia completa, explicando o raciocínio:

*"Com base no seu perfil: patrimônio de R$ X, tolerância a drawdown de 20%, renda ativa garantida e horizonte de 10 anos, sua estratégia ideal é a APEX CORE com os seguintes módulos ativos: ETFs (35%), FIIs (20%), Momentum Trading (25%), Renda Fixa (20%). O Módulo Wheel será habilitado em 90 dias após a carteira base estar estruturada. O Módulo de Convicção (ALPHA) será avaliado quando o patrimônio atingir R$ Y e os demais módulos estiverem calibrados."*

O usuário entende o **porquê**, não só o **o quê**.

### Fase 3 — Portfólio Existente ou Do Zero

**Se o usuário já tem investimentos:**
- Importa via planilha CSV ou cadastro manual
- A IA faz o **gap analysis completo**: compara a carteira atual com a estratégia definida
- Gera o plano de transição: *"Você está com 45% em FIIs mas a estratégia pede 20%. Nos próximos 3 aportes, direcione 100% para ETFs. Não venda FIIs agora — aguarde o rebalanceamento orgânico via aportes."*

**Se vai começar do zero:**
- Usuário informa o valor disponível
- A IA monta a carteira inicial completa respeitando a estratégia e os pesos definidos
- Apresenta o plano de entrada com justificativa ativo por ativo

---

## 3. ARQUITETURA DE MÓDULOS

O app é construído em **módulos independentes mas conectados por uma camada central**. Cada módulo é habilitado conforme a estratégia definida no onboarding — o usuário não escolhe os módulos manualmente, **o gestor (IA) define quais módulos fazem sentido para o perfil de cada usuário**.

### CAMADA CENTRAL — Core (sempre ativo)

**Morning Briefing Central**
- Abre automaticamente todo dia útil antes das 9h
- A IA faz leitura macro unificada contextualizada para o portfólio específico do usuário
- Não é genérico: *"Hoje o dólar subiu 1.2%, o que pressiona seus FIIs de papel indexados ao CDI. Seu módulo Wheel tem 2 opções vencendo em 4 dias. O scanner identificou 1 oportunidade momentum com score 82 em RENT3."*
- Semáforo visual de regime: BULL / MISTO / BEAR

**Dashboard Patrimonial Consolidado**
- Visão unificada de todos os módulos ativos
- Patrimônio total em tempo real com variação do dia
- Performance: dia, semana, mês, ano, desde o início
- Comparativo gráfico vs IBOV, CDI e S&P500
- Alocação atual vs alvo por módulo com semáforo de desvio
- Projeção de patrimônio com cenários conservador e otimista

**Análise Macro On-Demand**
- Usuário pode solicitar a qualquer momento uma análise macro completa
- A IA puxa dados em tempo real (Selic, câmbio, VIX, commodities, juros EUA, PMI China) e contextualiza para o portfólio do usuário

**Orquestrador de Risco (background)**
- Monitora o portfólio consolidado continuamente — não por módulo, mas no total
- Calcula exposição bruta a risco cross-módulos
- Em regime BEAR: aciona proteções em cascata — reduz momentum primeiro, avisa Wheel para não renovar puts, aumenta caixa
- Gerencia correlação entre posições de módulos diferentes (correlação > 0.70 entre dois blocos = tratados como uma única posição para fins de risco)

---

### MÓDULO 1 — Trade Momentum

**Para quem:** Perfis com tolerância a volatilidade media-alta e tempo para acompanhar o mercado.

**O que faz:**
- Escaneia continuamente o universo de ativos (ações BR, BDRs, ETFs) com os 5 filtros APEX sequenciais
- Gera score APEX de 0 a 100 para cada ativo
- Score ≥ 75: trade completo gerado automaticamente (entrada, stop, alvo, tamanho de posição)
- Score 50-75: monitoramento ativo com alerta de proximidade
- Score < 50: fora do radar

**Os 5 Filtros APEX (sequenciais — falha em qualquer = ativo descartado):**
1. Preço acima da MM200 por pelo menos 10 pregões consecutivos
2. MM50 acima da MM200 com inclinação positiva em ambas
3. Rompimento da máxima dos últimos 60 dias confirmado
4. Volume no dia do rompimento mínimo 50% acima da média de 20 dias
5. Setor do ativo com força relativa positiva contra IBOV nos últimos 63 dias

**Gestão de posições abertas:**
- Stop inicial: 2x ATR(14) abaixo da entrada
- Stop móvel: ativado após lucro de 1R. Trailing de 2x ATR abaixo das máximas
- Saída parcial: 50% da posição ao atingir alvo 1 (2R). Restante com trailing
- Saída total: fechamento abaixo da MM21 por 2 pregões consecutivos

**Análise macro específica do módulo:**
- Foco em: força relativa setorial, breadth do mercado, volume agregado, regime de mercado
- A IA **trava entradas momentum** em regime MISTO com tendência de deterioração e em regime BEAR
- Alerta: *"Regime atual MISTO com breadth negativo (62% das ações abaixo da MM200). Não estou iniciando novas posições momentum. Aguardando confirmação de melhora."*

---

### MÓDULO 2 — The Wheel Strategy

**Para quem:** Perfis que buscam geração de renda via opções. Requer experiência mínima com renda variável.

**O que faz:**
Gerencia o ciclo completo da Wheel: Put Vendida → (se exercida) Call Coberta → (se chamada) recomeça. O ciclo nunca para.

**Parâmetros de entrada da Put Vendida:**
- IV Rank mínimo: 30% (não vende prêmio com volatilidade baixa)
- Delta da put: entre -0.25 e -0.35
- Vencimento: 21 a 45 dias (zona ideal de theta decay)
- Strike: abaixo do suporte técnico relevante
- Ativo-base: obrigatoriamente acima da MM200

**Gestão do ciclo:**
- Alvo de fechamento da put: 75% do prêmio recebido (app alerta automaticamente)
- Rolagem: se ativo cair > 5% com > 15 dias para vencimento, analisa rolar para strike mais baixo
- Se exercida: inicia call coberta no mesmo dia. Strike no preço de entrada ou até 3% acima. Delta 0.25-0.40
- Nunca segura ação sem call coberta em cima

**Destinação do prêmio líquido mensal (dividido automaticamente):**
- 50% reinvestido no próprio módulo Wheel (cresce o patrimônio gerador de renda)
- 30% direcionado para o módulo ETFs (constrói a carteira de longo prazo)
- 20% mantido em caixa como reserva operacional do módulo

**Análise macro específica do módulo:**
- Foco em: IV Rank dos ativos em carteira, calendário de eventos (resultados trimestrais, decisões de juros), posição dos ativos-base em relação às médias
- Alerta: *"IV Rank do PETR4 caiu para 18%. Prêmio atual não compensa o risco. Aguarde IV subir antes de renovar a put."*
- Alerta de evento: *"VALE3 reporta resultado em 8 dias. Não recomendo vender put agora — volatilidade vai subir, aguarde o resultado para capturar IV mais alto."*

---

### MÓDULO 3 — Carteira Hold / ETFs

**Para quem:** Todos os perfis. É o bloco de longo prazo e o âncora do portfólio.

**O que faz:**
- Gerencia a parcela de longo prazo em ETFs brasileiros (BOVA11, IVVB11, SMAL11) e internacionais (VOO, QQQ, VT)
- Sem stop, sem saída tática — lógica de hold com rebalanceamento via aportes
- Monitora desvio da alocação alvo e redireciona aportes para reequilibrar sem vender
- Ajusta prioridade de ETFs conforme cenário macro de taxa de juros

**Lógica de ajuste macro:**
- Selic acima de 12%: prioriza ETFs de dividendos e renda variável defensiva. Reduz exposição QQQ
- Selic caindo abaixo de 12%: aumenta gradualmente ETFs de crescimento (QQQ). Migra para exposição global
- Regime BULL: aportes em ETFs de renda variável priorizados
- Regime BEAR: aportes pausados. Direcionados para caixa e renda fixa até mudança de regime

**Análise macro específica do módulo:**
- Foco em: ciclo de juros global, câmbio estrutural (USD/BRL de longo prazo), valuation relativo entre mercados (CAPE ratio EUA vs emergentes), fluxo de capital estrangeiro para Brasil

---

### MÓDULO 4 — FIIs (Fundos de Investimento Imobiliário)

**Para quem:** Perfis que buscam renda passiva e/ou exposição ao setor imobiliário brasileiro.

**O que faz:**
- Monitora yield atual vs yield histórico de cada fundo
- Calcula P/VP e alerta quando FII está sendo negociado com desconto/prêmio excessivo
- Monitora qualidade do portfólio: vacância, duration dos contratos, perfil dos inquilinos
- Sugere alocação entre FIIs de papel (CRI) e FIIs de tijolo conforme momento da Selic

**Lógica de alocação dinâmica:**
- Selic alta e subindo: prioriza FIIs de papel indexados ao CDI+ e IPCA+
- Selic caindo: migra gradualmente para FIIs de tijolo de qualidade (lajes corporativas, logística)
- A migração é sempre gradual via aportes — nunca vende abruptamente

**Análise macro específica do módulo:**
- Foco em: trajetória da Selic (maior driver de FII no Brasil), IPCA (indexação dos contratos), spread dos CRIs em carteira, vacância do setor por segmento, fluxo de emissões novas
- Alerta estrutural: *"Com Selic projetada para cair 200bps nos próximos 12 meses, FIIs de tijolo de qualidade têm mais assimetria que FIIs de papel agora. Nos próximos 4 aportes, direcionarei 60% para HGLG11 e BRCO11."*

---

### MÓDULO 5 — Renda Fixa

**Para quem:** Todos os perfis. Funciona como lastro do portfólio e reserva de oportunidade.

**O que faz:**
- Monitora duration média da carteira de renda fixa
- Gerencia indexação: CDI, IPCA+, prefixado
- Controla vencimentos e reinvestimento
- Em regime BEAR: recebe capital dos demais módulos como proteção

**Lógica de duration e indexação:**
- Curva de juros inclinada positivamente: alongar duration em IPCA+ (NTN-B)
- Juros longos subindo: alertar que prefixados longos estão sofrendo marcação a mercado
- Juro real acima de 6% ao ano: IPCA+ longo é oportunidade histórica, aumentar alocação
- Regime BEAR confirmado: caixa e NTN-B recebem 100% dos novos aportes

**Análise macro específica do módulo:**
- Foco em: curva de juros futura (DI1), expectativa de Selic no Focus, IPCA projetado, spread de crédito corporativo, nível do juro real neutro

---

### MÓDULO 6 — Convicção Máxima (APEX ALPHA) 🔒

**Para quem:** Perfil avançado. **Este módulo NÃO é escolhido pelo usuário — é desbloqueado pelo gestor (IA) quando condições específicas são atendidas.**

**Condições para desbloqueio (ambas obrigatórias):**
1. **Condição patrimonial:** Os módulos Core (ETFs + FIIs + Renda Fixa) precisam estar estruturados e nos pesos corretos. O portfólio precisa ter uma base sólida antes de concentrar em teses de alto risco.
2. **Condição de perfil:** O questionário inicial demonstrou tolerância a drawdown de 25-30% e experiência prévia com renda variável. Usuários que demonstraram comportamento de pânico com quedas menores nunca têm este módulo desbloqueado.

Quando as condições são atendidas, o app notifica: *"Seu portfólio atingiu a maturidade necessária para incluir posições de alta convicção. O Módulo 6 foi habilitado. Identifiquei a primeira oportunidade."*

**Filosofia do módulo:**
Este módulo é baseado em **convicção**, não em sinais técnicos. O gestor (IA) identifica ciclos macro, distorções de valuation e catalisadores identificáveis, concentra capital pesado em 3 a 5 posições e aguenta a volatilidade enquanto a tese se desenvolve. É o que Druckenmiller, Soros e Buffett fazem.

O problema de convicção sem sistema é que ela vira ego. O Módulo 6 gerencia convicção com disciplina rigorosa.

**Quem gera a tese:**
**O gestor (IA) identifica e constrói a tese — não o usuário.** A IA monitora o cenário macro continuamente e quando identifica uma assimetria de alta convicção, apresenta proativamente:

*"Identifiquei uma oportunidade de alta convicção. Com base no ciclo atual de commodities e no posicionamento da demanda chinesa, há uma assimetria significativa em VALE3 via LEAPS de 18 meses. Quero alocar 8% do seu patrimônio nesta tese. Acesse o Módulo 6 para ver a análise completa antes de aprovar."*

**Estrutura de uma tese (gerada pela IA):**
- Qual o ativo ou instrumento e por quê
- Qual o catalisador específico e identificável (não pode ser vago)
- Qual o prazo esperado para o catalisador se materializar
- Qual o nível de invalidação da tese (stop de tese, não de preço)
- Histórico de situações análogas
- Retorno esperado no cenário base e perda máxima no pior cenário
- Por que LEAPS e não ação direta (quando aplicável)

**O usuário aprova ou rejeita:**
O app apresenta a tese completa. O usuário pode fazer perguntas e a IA responde com raciocínio detalhado. Se o usuário rejeitar, o gestor respeita e monitora a tese para reapresentar se o setup melhorar.

**Chat de sugestão do usuário:**
O usuário pode sugerir uma tese via chat: *"Estou acompanhando Embraer, acho que tem uma tese com a aviação regional americana crescendo."*

O gestor analisa com rigor: verifica dados de demanda, carteira de pedidos, valuation, riscos. Se a tese tem fundamento, aprimora e apresenta formalmente. Se não tem, explica exatamente por que — com dados, não com opinião.

**Gestão pós-entrada:**
A IA monitora os **dados que sustentam a tese**, não só o preço. A cada 2 semanas gera revisão de tese automática com status real:

*"Posição VALE3 — 45 dias. Tese: recuperação do minério para $130/t. Status: minério em $108/t (+6% desde entrada). PMI China: 51.2 — positivo para a tese. Porém estoques nos portos chineses subiram 8% — sinal de alerta. Tese ainda viva mas há dado contraditório. Prazo restante: 4 meses. Recomendação: manter, monitorar estoques."*

**LEAPS — ferramenta principal do módulo:**
Para teses com prazo de 12-24 meses, o módulo usa calls longas (LEAPS) ao invés de ações:
- Delta alvo: 0.60-0.75 (exposição real ao movimento)
- Vencimento: 12 a 24 meses
- Ao atingir 2x o custo: retira o capital original, deixa "a casa jogar"
- Com 90 dias para vencimento: avalia rolar para manter exposição
- Se tese invalidada: fecha imediatamente, independente do tempo restante

---

### MÓDULO 7 — Relatórios e Fiscal

**O que faz:**
- Performance mensal e anual com gráfico de evolução patrimonial
- Sharpe ratio, drawdown máximo histórico, taxa de acerto por módulo
- Relatório fiscal: preço médio atualizado, ganhos realizados por mês, DARF estimado
- Exportação em PDF e Excel
- Revisão mensal em linguagem natural gerada pela IA: o que funcionou, o que falhou, o que ajustar

---

## 4. AS DUAS ESTRATÉGIAS MACRO

O onboarding classifica o usuário em uma das duas estratégias. Os módulos ativos e os pesos diferem entre elas.

### APEX CORE
**Perfil:** Busca crescimento sólido e consistente acima do mercado com sistema mecânico e regras objetivas. Aceita drawdowns de até 15%.

**Alocação típica:**
- ETFs Brasil e Internacional: 35%
- FIIs: 20%
- Renda Fixa: 20%
- Momentum Trading: 15%
- Caixa operacional: 10%
- Módulo Wheel: habilitado após 90 dias se perfil permitir
- Módulo Convicção: **não disponível para CORE**

### APEX ALPHA
**Perfil:** Investidor experiente com entendimento de ciclos macro. Tolera volatilidade alta (25-30% drawdown) em troca de retornos excepcionais. Opera opções com conforto.

**Alocação típica:**
- ETFs: 25%
- FIIs: 15%
- Renda Fixa: 15%
- Momentum Trading: 20%
- Wheel Strategy: 10%
- Convicção ALPHA: 15% (3-5 posições)
- Caixa: 5%

**Os Cinco Pilares do ALPHA:**
1. Concentração em convicção máxima — 3 a 5 posições representando 60-70% da parcela de risco
2. Captura de ciclos completos — identificar o início do ciclo e manter durante todo o desenvolvimento
3. Alavancagem via LEAPS — exposição total com perda máxima definida pelo prêmio pago
4. Short em Bear Market — via puts longas no BOVA11 e SPY quando regime muda
5. Assimetria em eventos — calls OTM baratas antes de catalisadores identificáveis

---

## 5. CONTROLE DE RISCO — REGIMES DE MERCADO

O sistema classifica o mercado em três regimes e ajusta todos os módulos automaticamente:

**BULL (Semáforo Verde):**
- IBOV acima da MM200, MM50 acima da MM200, breadth positivo (> 60% das ações acima da MM200)
- Ação: todos os módulos operando em plena capacidade

**MISTO (Semáforo Amarelo):**
- IBOV abaixo da MM200 mas acima da MM50, ou breadth deteriorando
- Ação: novas entradas momentum pausadas. Wheel mantida mas sem renovações agressivas. Aportes em ETFs reduzidos em 50%

**BEAR (Semáforo Vermelho):**
- IBOV abaixo da MM200 com volume crescente na queda, ou queda de 15%+ em 30 dias
- Ação: zera novas posições momentum. Não renova puts Wheel. Aportes direcionados 100% para caixa e NTN-B. Para ALPHA: avalia puts longas no IBOV como proteção/lucro

**Controle de Drawdown em Cascata (CORE):**
- Drawdown de 5%: alerta de monitoramento
- Drawdown de 10%: reduz posições momentum em 50%, aumenta caixa
- Drawdown de 15%: zera momentum, Wheel apenas gestão de posições existentes, aportes em renda fixa

**Controle de Drawdown em Cascata (ALPHA):**
- Drawdown de 10%: revisão de todas as teses do Módulo 6
- Drawdown de 20%: reduz posições de convicção para 50% do tamanho original
- Drawdown de 30%: para todas as novas operações, mantém apenas proteções

---

## 6. MÓDULO DE APORTES INTELIGENTES

**Como funciona:**
O usuário informa o valor disponível para aporte. O sistema calcula automaticamente a distribuição ótima, exibe a justificativa de cada alocação e aguarda aprovação antes de sugerir a execução.

**Sistema de Prioridade (Semáforo):**
- 🔴 Vermelho: alocação atual > 5% abaixo do alvo → prioridade máxima
- 🟡 Amarelo: desvio entre 2% e 5% → prioridade normal
- 🟢 Verde: dentro do alvo → não precisa de aporte direcionado

**Filtros que bloqueiam o aporte:**
- Sinal técnico negativo: ativo abaixo da MM200 com volume crescente — não aporta mesmo com desvio vermelho
- Regime BEAR ativo: aportes em ações bloqueados. Redirecionados para caixa e NTN-B
- Correlação excessiva: se aporte aumentaria correlação do portfólio > 0.70 entre dois blocos, sistema alerta

**Ajuste por contexto macro:**
- Selic > 12%: FIIs de papel priorizados. ETFs: prioridade para VOO (dividendos)
- Selic caindo < 12%: FIIs migram para tijolo. ETFs: prioridade para QQQ
- Regime BULL: ações priorizadas. Regime MISTO: 30% do aporte vai para caixa. Regime BEAR: 100% para caixa e NTN-B

---

## 7. SCANNER E SCORE APEX

**O Score APEX (0 a 100)** é calculado por ponderação dos 5 filtros sequenciais:
- Posição vs MM200 (25 pontos): dias consecutivos acima, distância percentual
- Alinhamento de médias (20 pontos): MM50 > MM200 + inclinação positiva
- Rompimento (25 pontos): máxima dos 60 dias confirmada
- Volume (15 pontos): multiplicador vs média de 20 dias
- Força relativa setorial (15 pontos): performance do setor vs IBOV nos últimos 63 dias

**Para cada ativo com score ≥ 75, o sistema gera automaticamente:**
- Ponto de entrada exato (ou faixa de 0.5%)
- Stop inicial (2x ATR(14) abaixo da entrada)
- Alvo 1 (2R) e método de trailing após alvo 1
- Tamanho de posição calculado (baseado em 1% do patrimônio como risco máximo por operação para CORE, 1.5% para ALPHA)
- Análise da IA explicando por que o setup é válido neste momento

---

## 8. TELAS DO APP

**Tela 1 — Morning Briefing** (tela inicial ao abrir o app)
- Resumo macro: Selic, dólar, commodities, futuros IBOV e S&P500
- Regime de mercado atual com semáforo visual
- Posições que precisam de atenção: stops próximos, opções vencendo em 5 dias
- Oportunidades identificadas pelo scanner com score e sugestão resumida
- Calendário de eventos: resultados trimestrais, decisões de juros, dados econômicos

**Tela 2 — Dashboard do Portfólio**
- Patrimônio total em tempo real com variação do dia
- Alocação atual vs alvo por módulo com semáforo de desvio
- Performance: dia, semana, mês, ano, desde o início
- Gráfico comparativo vs IBOV, CDI e S&P500
- Renda gerada no mês por fonte: dividendos, FIIs, prêmios Wheel
- Projeção de patrimônio com cenários conservador e otimista

**Tela 3 — Posições Abertas**
- Ações: preço médio, stop atual, performance, score APEX atualizado, dias em posição
- Opções Wheel: strike, vencimento, delta atual, prêmio recebido, % do lucro atingido, sugestão de ação
- LEAPS ALPHA: strike, vencimento, delta, múltiplo atual sobre o custo, sugestão de saída parcial
- FIIs e ETFs: cota média, yield atual, desvio da alocação alvo
- Renda Fixa: indexador, taxa contratada, duration, projeção de vencimento

**Tela 4 — Scanner e Oportunidades**
- Lista de ativos com score ≥ 75 e trade completo sugerido
- Para cada ativo: quais filtros passou e quais estão pendentes
- Trade sugerido: entrada, stop, alvo, tamanho de posição calculado
- Filtros por categoria: ações BR, BDRs, ETFs, LEAPS para ALPHA
- Aba ALPHA: setores em ciclo macro favorável com análise de catalisador

**Tela 5 — Módulo 6 / Convicção** (apenas para ALPHA habilitado)
- Teses ativas com status de desenvolvimento
- Tese em análise: documento completo gerado pela IA para aprovação
- Chat para sugestão de teses pelo usuário
- Revisões quinzenais com status dos dados que sustentam a convicção

**Tela 6 — Aportes Inteligentes**
- Campo para informar valor disponível
- Distribuição automática calculada com justificativa por ativo
- Visualização do desvio atual vs alvo com semáforo
- Aprovação com um toque ou ajuste manual

**Tela 7 — Backtest**
- Seleção de estratégia CORE ou ALPHA e período
- Configuração de capital inicial, aportes mensais e custos operacionais
- Curva de patrimônio vs benchmarks com drawdowns destacados
- Métricas: CAGR, Sharpe, drawdown máximo, taxa de acerto
- Walk-Forward Analysis com validação fora da amostra
- Exportação de relatório em PDF

**Tela 8 — Análise de Ativo**
- Busca por qualquer ativo: ação, FII, ETF, BDR, opção
- Score APEX com detalhe de cada filtro
- Análise técnica: gráfico com MM50, MM200, volume, ATR, IV Rank
- Dados fundamentalistas: P/L, dividend yield, ROE, crescimento de receita
- Análise da IA em linguagem natural explicando o contexto atual

**Tela 9 — Chat com o Gestor**
- Interface de conversa direta com a IA
- Usuário pode perguntar sobre qualquer aspecto do portfólio
- Pode sugerir teses para análise (Módulo 6)
- Pode pedir análise de qualquer ativo
- Pode solicitar revisão da estratégia
- A IA sempre responde com raciocínio completo e dados

**Tela 10 — Relatórios**
- Performance mensal e anual com gráfico de evolução
- Sharpe, drawdown máximo, taxa de acerto por estratégia e por módulo
- Relatório fiscal: preço médio, ganhos realizados, DARF estimado
- Revisão mensal em linguagem natural gerada pela IA
- Exportação PDF e Excel

---

## 9. INTEGRAÇÃO COM IA — ARQUITETURA TÉCNICA

### Modelo recomendado: Claude API (Anthropic)
**Por quê:** Raciocínio estruturado superior em análises financeiras, janela de contexto longa (histórico extenso de interações), e tool use permite que o Claude chame endpoints internos para buscar dados em tempo real antes de responder.

### Fluxo técnico de cada interação com IA:
1. Usuário abre tela ou faz pergunta
2. Sistema monta o **contexto completo** do portfólio do usuário (posições, módulos ativos, regime atual, histórico recente)
3. Sistema busca dados em tempo real via APIs (cotações, indicadores, macro)
4. Claude recebe: system prompt com perfil do gestor + contexto do portfólio + dados em tempo real
5. Claude responde com análise contextualizada e raciocínio completo

### System Prompt Base (injeta em cada chamada):
```
Você é o gestor de portfólio APEX, um gestor de patrimônio de elite com profundo conhecimento de todos os maiores investidores da história. Você domina momentum, value investing, macro global, opções (Wheel, LEAPS, spreads), ETFs, renda fixa, FIIs e mercados internacionais.

Você está gerindo o portfólio de [NOME DO USUÁRIO], com as seguintes características:
- Estratégia: [CORE/ALPHA]
- Patrimônio total: R$ [VALOR]
- Módulos ativos: [LISTA]
- Tolerância a drawdown: [%]
- Perfil: [RESUMO DO QUESTIONÁRIO]

Contexto atual do portfólio:
[POSIÇÕES ABERTAS + DESVIOS DE ALOCAÇÃO]

Contexto macro atual:
[DADOS EM TEMPO REAL: SELIC, CÂMBIO, IBOV, VIX, COMMODITIES]

Regime de mercado: [BULL/MISTO/BEAR]

Você faz análises com raciocínio completo: o que fazer, por que fazer, quando fazer, qual o stop, qual o alvo e qual o tamanho da posição. Quando há risco, você o aponta claramente. Nunca vende ilusão, nunca é conservador por covardia.
```

### Tool Use (Claude chama APIs em tempo real):
- `get_quote(ticker)`: cotação atual via BRAPI
- `get_history(ticker, period)`: histórico via BRAPI + yFinance
- `get_indicators(ticker)`: MM50, MM200, ATR, IV Rank, força relativa
- `get_macro_data()`: Selic, câmbio, IBOV futuro, S&P500 futuro, VIX
- `get_portfolio(user_id)`: portfólio completo do usuário do banco de dados
- `get_options_chain(ticker)`: cadeia de opções para módulo Wheel

---

## 10. STACK TECNOLÓGICA

**Backend:**
- Python 3.11+
- FastAPI (API REST)
- PostgreSQL (dados persistentes: portfólio, histórico, usuários)
- Redis (cache: cotações em tempo real, indicadores calculados)
- Celery + Redis (tarefas assíncronas: Morning Briefing automático, scanner contínuo)
- Docker + Docker Compose

**Frontend:**
- React.js com TypeScript
- Design system próprio (dark mode, cores: preto/branco/verde APEX)
- TradingView Lightweight Charts (gráficos de preço)
- Recharts (gráficos de performance, alocação)

**Mobile (fase posterior):**
- React Native (compartilha lógica com web)
- Notificações push para alertas críticos

**APIs de Dados:**
- BRAPI (cotações brasileiras em tempo real, histórico, busca)
- yFinance (dados históricos globais, BDRs, ETFs internacionais)
- Anthropic API (motor de IA — Claude)

**Estrutura de Pastas:**
```
apex-manager/
├── backend/
│   ├── app/
│   │   ├── api/          # Endpoints FastAPI
│   │   ├── core/         # Lógica APEX (filtros, score, sizing)
│   │   ├── modules/      # Um diretório por módulo
│   │   │   ├── momentum/
│   │   │   ├── wheel/
│   │   │   ├── etfs/
│   │   │   ├── fiis/
│   │   │   ├── renda_fixa/
│   │   │   └── alpha/
│   │   ├── ai/           # Integração Claude API
│   │   ├── data/         # Integração BRAPI + yFinance
│   │   ├── models/       # Modelos PostgreSQL
│   │   └── tasks/        # Celery tasks (briefing, scanner)
│   ├── tests/
│   └── docker-compose.yml
└── frontend/
    ├── src/
    │   ├── pages/        # Uma página por tela
    │   ├── components/   # Componentes reutilizáveis
    │   ├── hooks/        # Custom hooks
    │   └── services/     # Chamadas à API backend
    └── public/
```

---

## 11. PLANO DE DESENVOLVIMENTO — 24 SEMANAS

### FASE 1 — Fundação (Semanas 1-4)

**Sprint 1 (Semanas 1-2) — Infraestrutura + Onboarding:**
- Setup: Python, FastAPI, PostgreSQL, Redis, Docker
- Estrutura de pastas conforme arquitetura
- Integração BRAPI: cotações, busca, histórico
- Integração yFinance: dados globais
- **ONBOARDING COM IA:** questionário completo + elaboração de estratégia pelo Claude
- Endpoints: POST /onboarding, GET /strategy, POST /portfolio/import

**Sprint 2 (Semanas 3-4) — Motor APEX:**
- Cálculo de todos os indicadores: MM50, MM200, ATR, IV Rank, força relativa
- Implementação dos 5 filtros APEX com testes unitários
- Sistema de score 0-100 com pesos por filtro
- Endpoint GET /scanner retornando lista classificada
- Orquestrador de regime de mercado (BULL/MISTO/BEAR)

### FASE 2 — Interface Base (Semanas 5-8)

**Sprint 3 (Semanas 5-6) — Frontend Core:**
- Setup React.js com TypeScript e design system
- Tela de Dashboard com patrimônio e alocação
- Tela do Scanner com lista de ativos e scores
- Navegação entre telas e layout responsivo

**Sprint 4 (Semanas 7-8) — Posições e Análise:**
- Tela de Posições Abertas com cadastro manual
- Cálculo de performance por posição e total
- Tela de Análise de Ativo com gráfico e indicadores
- Integração com Claude para análise de ativo em linguagem natural

### FASE 3 — Motor de Gestão (Semanas 9-14)

**Sprint 5 (Semanas 9-10) — Wheel Manager:**
- Módulo Wheel completo: cadastro de puts e calls vendidas
- Cálculo automático de delta, dias para vencimento, % de lucro
- Alertas automáticos: 75% de lucro, vencimento em 5 dias
- Lógica de sugestão de rolagem

**Sprint 6 (Semanas 11-12) — Aportes e ALPHA:**
- Módulo de Aportes Inteligentes com cálculo de desvio e distribuição ótima
- Lógica de prioridade vermelho/amarelo/verde com filtros
- Módulo 6: telas de tese, chat de sugestão, revisão quinzenal
- Lógica de desbloqueio automático do Módulo 6

**Sprint 7 (Semanas 13-14) — Morning Briefing e IA:**
- Morning Briefing automatizado via Celery (roda antes das 9h todo dia útil)
- Chat com o Gestor: interface de conversa com contexto completo do portfólio
- Análise macro on-demand
- Revisão mensal automática

### FASE 4 — Backtest Engine (Semanas 15-20)

**Sprints 8-10:** Engine de backtest com dados históricos, simulação dos 5 filtros APEX, backtest da Wheel, backtest do portfólio completo, Walk-Forward Analysis, testes de stress (2008, 2015, 2020), tela de Backtest no frontend.

### FASE 5 — Relatórios e Lançamento (Semanas 21-24)

**Sprints 11-12:** Relatórios de performance e fiscal, cálculo de preço médio e DARF, versão mobile React Native, notificações push, testes de carga, deploy em produção.

---

## 12. OBSERVAÇÕES FINAIS PARA O DESENVOLVIMENTO

**Prioridade absoluta:** O onboarding com IA é a peça mais importante do sistema. Deve ser desenvolvido no Sprint 1, não deixado para versões futuras. Tudo que vem depois depende do perfil gerado no onboarding.

**Multi-tenancy:** O sistema deve ser construído para múltiplos usuários desde o início. Cada usuário tem seu portfólio isolado, suas configurações de estratégia e seu histórico de interações com a IA.

**Contexto da IA:** Nunca chame o Claude sem injetar o contexto completo do portfólio. A IA sem contexto dá respostas genéricas. A IA com contexto dá análises de gestão de alto nível.

**Módulos independentes:** Cada módulo deve ser desenvolvido como um serviço independente com suas próprias rotas, modelos e lógica. Eles se comunicam através do Orquestrador de Risco, não diretamente entre si.

**Dados em tempo real:** Use Redis para cachear cotações por no mínimo 1 minuto. Não faça chamadas diretas às APIs de dados a cada request — vai ser lento e vai estourar limites de rate.

**Segurança:** Dados financeiros são sensíveis. Implemente autenticação JWT, criptografia em repouso para dados do portfólio, e logs de auditoria para todas as operações de modificação de posições.

---

*APEX Manager — Especificação Técnica v2.0 | Fevereiro 2026 | Confidencial*
*Desenvolvido com base em análise de portfólio institucional e gestão ativa de patrimônio*

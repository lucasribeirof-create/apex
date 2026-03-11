"""
APEX Motors — Watchlists padrão por módulo de estratégia.

Critérios de curadoria:
  - Wheel/Momentum: top ações com maior liquidez em opções na B3 (COTAHIST) +
                    volume médio diário > R$50M + free float relevante
  - FIIs: seleção de ~40 fundos de qualidade por segmento (lajes, logística,
          shoppings, recebíveis, híbridos) — DY consistente + gestores reconhecidos
  - ETFs: universo AMPLO de ~35 ETFs líquidos da B3 (RV BR, internacional,
          temático, commodity, RF, crypto) — IA seleciona baseado em macro
  - Dividendos: pagadoras consistentes com histórico >= 3 anos e payout sustentável
  - Alpha: ações com histórico de assimetria + desconto fundamentalista

Cada lista é o universo de candidatos que o motor vai analisar.
O motor (com IA) filtra e rankeia — não usa todos os tickers da lista.
"""

# ─── Wheel & Momentum — mesma base (ações líquidas com opções ativas) ────────
# Top 20 por open interest de opções + volume médio diário B3
WHEEL_WATCHLIST = [
    "PETR4",  # Petrobras PN — maior liquidez de opções da B3
    "VALE3",  # Vale ON — 2ª maior liquidez, muita opção disponível
    "ITUB4",  # Itaú Unibanco PN — bancão, opções muito líquidas
    "BBDC4",  # Bradesco PN — alta liquidez de opções
    "BBAS3",  # Banco do Brasil ON — bom volume de opções
    "B3SA3",  # B3 ON — boa liquidez
    "WEGE3",  # WEG ON — crescimento consistente, opções ok
    "RENT3",  # Localiza ON — opções líquidas
    "ABEV3",  # Ambev ON — defensiva, prêmios razoáveis
    "MGLU3",  # Magazine Luiza ON — alta volatilidade = prêmios maiores
    "VBBR3",  # Vibra (BR Distribuidora) — opções disponíveis
    "GGBR4",  # Gerdau PN — siderurgia, boa liquidez
    "CSNA3",  # CSN ON — siderurgia, alta vol
    "SUZB3",  # Suzano ON — papel/celulose
    "PRIO3",  # PetroRio ON — petróleo independente, vol elevada
    "RDOR3",  # Rede D'Or ON — saúde, opções disponíveis
    "LREN3",  # Lojas Renner ON — varejo, opções ativas
    "EMBR3",  # Embraer ON — exportadora, boa vol
    "CPLE6",  # Copel — elétrica, dividendos + opções
    "EGIE3",  # Engie Brasil ON — defensiva, prêmios ok
]

MOMENTUM_WATCHLIST = WHEEL_WATCHLIST + [
    "BPAC11",  # BTG Pactual Units — instituição financeira forte
    "TOTS3",   # Totvs ON — tech BR
    "LWSA3",   # Locaweb ON — tech, high beta
    "MELI34",  # MercadoLibre BDR — tech LA growth
    "NVDC34",  # Nvidia BDR — semicondutores
    "AZUL4",   # Azul PN — aviação, alta vol
    "COGN3",   # Cogna — educação, vol
    "CXSE3",   # Caixa Seguridade — bancário
    "HAPV3",   # Hapvida — saúde, alta vol
    "CYRE3",   # Cyrela — construtora, opções ativas
]

# ─── FIIs — universo AMPLO por segmento (~40 FIIs) ───────────────────────────
FIIS_WATCHLIST = {
    "lajes_corporativas": [
        "HGRE11",  # CSHG Real Estate
        "RBRP11",  # RBR Properties
        "PVBI11",  # P. Verde Blanc I
        "BRCR11",  # BTG Corporate Office
        "JSRE11",  # JS Real Estate — lajes SP
        "VINO11",  # Vinci Offices — lajes corporativas
        "TEPP11",  # Tellus Properties — lajes diversificadas
    ],
    "logistica": [
        "XPLG11",  # XP Log
        "BRCO11",  # Bresco
        "HGLG11",  # CSHG Logística
        "VILG11",  # Vinci Logística
        "LVBI11",  # VBI Logística
        "SDIL11",  # SDI Logística
        "BTLG11",  # BTG Logística — grande e líquido
    ],
    "shoppings": [
        "XPML11",  # XP Malls
        "HSML11",  # HSI Malls
        "MALL11",  # Malls Brasil Plural
        "VISC11",  # Vinci Shopping Centers
        "ABCP11",  # Grand Plaza
        "HGBS11",  # CSHG Brasil Shopping — grande e líquido
    ],
    "recebíveis_cri": [
        "MXRF11",  # Maxi Renda (mais líquido BR)
        "KNCR11",  # Kinea CRI
        "KNIP11",  # Kinea Índices de Preços
        "BCRI11",  # BTG CRI
        "RBRR11",  # RBR Rendimento High Grade
        "HGCR11",  # CSHG CRI
        "VRTA11",  # Fator Verità
        "IRDM11",  # Iridium Recebíveis Imobiliários
        "CPTS11",  # Capitânia Securities — grande e diversificado
        "RECR11",  # REC Recebíveis — high grade
    ],
    "hibridos_fofs": [
        "BPFF11",  # Brasil Plural Abs FoF
        "HFOF11",  # Hedge Top FOFII
        "RBRF11",  # RBR Alpha Multiestratégia
        "BCFF11",  # BTG FoF — diversificado
    ],
}

# Lista flat para uso no motor
FIIS_WATCHLIST_FLAT = [
    ticker
    for segmento in FIIS_WATCHLIST.values()
    for ticker in segmento
]

# ─── ETFs — universo AMPLO de ~35 ETFs da B3 ─────────────────────────────────
# A IA seleciona baseado em macro, NÃO é mais uma lista fixa por perfil.
# Metadados aqui ajudam a IA a entender a exposição de cada ETF.
ETFS_UNIVERSE = {
    # ── Renda Variável Brasil ─────────────────────────────────────────
    "BOVA11": {"nome": "iShares IBOVESPA",         "exposicao": "Brasil large-cap (Ibovespa)", "taxa_adm": 0.10, "categoria": "brasil_rv"},
    "BOVB11": {"nome": "Bradesco IBOVESPA",         "exposicao": "Brasil large-cap (Ibovespa)", "taxa_adm": 0.20, "categoria": "brasil_rv"},
    "SMAL11": {"nome": "iShares Small Cap BR",      "exposicao": "Brasil small-cap (fora do Ibovespa)", "taxa_adm": 0.50, "categoria": "brasil_rv"},
    "DIVO11": {"nome": "It Now Dividendos",          "exposicao": "Brasil dividendos (IDIV)", "taxa_adm": 0.40, "categoria": "brasil_dividendos"},
    "DIVD11": {"nome": "Dividend Smart",             "exposicao": "Brasil dividendos (smart beta)", "taxa_adm": 0.50, "categoria": "brasil_dividendos"},
    "FIND11": {"nome": "iShares Financeiro",         "exposicao": "Brasil setor financeiro", "taxa_adm": 0.42, "categoria": "brasil_setorial"},
    "MATB11": {"nome": "iShares Materiais Básicos",  "exposicao": "Brasil commodities/materiais", "taxa_adm": 0.42, "categoria": "brasil_setorial"},
    "BOVX11": {"nome": "Trend IBOV ex-Estatais",     "exposicao": "Brasil large-cap sem estatais", "taxa_adm": 0.20, "categoria": "brasil_rv"},
    # ── Internacional ─────────────────────────────────────────────────
    "IVVB11": {"nome": "iShares S&P 500 (BRL)",     "exposicao": "EUA S&P 500 — hedge dólar", "taxa_adm": 0.23, "categoria": "internacional"},
    "NASD11": {"nome": "Trend Nasdaq 100",           "exposicao": "EUA Nasdaq 100 — tech growth", "taxa_adm": 0.40, "categoria": "internacional"},
    "SPXI11": {"nome": "It Now S&P 500",             "exposicao": "EUA S&P 500 (alternativa ao IVVB11)", "taxa_adm": 0.21, "categoria": "internacional"},
    "WRLD11": {"nome": "iShares MSCI ACWI",          "exposicao": "Global — mercados desenvolvidos e emergentes", "taxa_adm": 0.46, "categoria": "internacional"},
    "EURP11": {"nome": "Trend MSCI Europa",          "exposicao": "Europa — MSCI Europe", "taxa_adm": 0.38, "categoria": "internacional"},
    "XINA11": {"nome": "Trend China",                "exposicao": "China — MSCI China", "taxa_adm": 0.47, "categoria": "internacional"},
    "USTK11": {"nome": "Investo MSCI US Tech",       "exposicao": "EUA tech — grandes empresas de tecnologia", "taxa_adm": 0.48, "categoria": "internacional"},
    "ACWI11": {"nome": "Trend ACWI",                 "exposicao": "Global — All Country World Index", "taxa_adm": 0.35, "categoria": "internacional"},
    # ── Temáticos / Setoriais ─────────────────────────────────────────
    "CHIP11": {"nome": "Investo PHLX Semicondutores","exposicao": "Global semicondutores (AMD, TSMC, ASML, Nvidia)", "taxa_adm": 0.48, "categoria": "tematico"},
    "JOGO11": {"nome": "It Now Gaming",              "exposicao": "Global games e esports", "taxa_adm": 0.48, "categoria": "tematico"},
    "TECK11": {"nome": "Investo Tech",               "exposicao": "Tech global diversificada", "taxa_adm": 0.48, "categoria": "tematico"},
    "REVE11": {"nome": "It Now Saúde",               "exposicao": "Brasil setor saúde", "taxa_adm": 0.50, "categoria": "tematico"},
    # ── Commodities ───────────────────────────────────────────────────
    "GOLD11": {"nome": "Trend Ouro",                 "exposicao": "Ouro — proteção + hedge de crise", "taxa_adm": 0.30, "categoria": "commodity"},
    "BSLV39": {"nome": "BDR iShares Silver",         "exposicao": "Prata — industrial + proteção", "taxa_adm": 0.50, "categoria": "commodity"},
    # ── Renda Fixa ETF ────────────────────────────────────────────────
    "IMAB11": {"nome": "iShares IMA-B (IPCA+)",     "exposicao": "Título público IPCA+ via ETF", "taxa_adm": 0.20, "categoria": "rf_etf"},
    "FIXA11": {"nome": "Mirae Renda Fixa Pré",      "exposicao": "Renda fixa prefixada via ETF", "taxa_adm": 0.30, "categoria": "rf_etf"},
    "IRFM11": {"nome": "Itaú IRF-M",                "exposicao": "Renda fixa prefixada médio prazo", "taxa_adm": 0.20, "categoria": "rf_etf"},
    "B5P211": {"nome": "It Now IMA-B5+",             "exposicao": "IPCA+ longo prazo (> 5 anos)", "taxa_adm": 0.20, "categoria": "rf_etf"},
    # ── ESG / Sustentável ─────────────────────────────────────────────
    "ISUS11": {"nome": "iShares ESG BR",             "exposicao": "Brasil ESG — empresas sustentáveis", "taxa_adm": 0.30, "categoria": "esg"},
    "ECOO11": {"nome": "Bradesco Carbono Eficiente", "exposicao": "Brasil carbono eficiente", "taxa_adm": 0.38, "categoria": "esg"},
    # ── Crypto ────────────────────────────────────────────────────────
    "HASH11": {"nome": "Hashdex Crypto Index",       "exposicao": "Cesta de criptomoedas (BTC + ETH + altcoins)", "taxa_adm": 1.00, "categoria": "crypto"},
    "BITH11": {"nome": "Hashdex Bitcoin",            "exposicao": "Bitcoin puro", "taxa_adm": 0.70, "categoria": "crypto"},
    "ETHE11": {"nome": "Hashdex Ethereum",           "exposicao": "Ethereum puro", "taxa_adm": 0.70, "categoria": "crypto"},
}

# Lista flat de tickers ETFs para prefetch
ETFS_WATCHLIST_FLAT = list(ETFS_UNIVERSE.keys())

# Mantém o dict antigo para compatibilidade (ETFs por categoria)
ETFS_WATCHLIST = {
    "ibovespa": ["BOVA11", "BOVB11"],
    "small_cap": ["SMAL11"],
    "dividendos": ["DIVO11", "DIVD11"],
    "internacional": ["IVVB11", "NASD11", "SPXI11", "WRLD11", "EURP11", "XINA11", "USTK11", "ACWI11"],
    "tematico": ["CHIP11", "JOGO11", "TECK11", "REVE11"],
    "commodity": ["GOLD11", "BSLV39"],
    "renda_fixa_etf": ["IMAB11", "FIXA11", "IRFM11", "B5P211"],
    "esg": ["ISUS11", "ECOO11"],
    "crypto": ["HASH11", "BITH11", "ETHE11"],
}

# ─── Dividendos — pagadoras consistentes (expandido para ~25) ─────────────────
DIVIDENDOS_WATCHLIST = [
    "BBAS3",   # Banco do Brasil — maior DY entre bancões (histórico > 8%)
    "TAEE11",  # Taesa Units — transmissão energia, DY estável ~10%
    "EGIE3",   # Engie Brasil — elétrica, dividendos crescentes
    "CPLE6",   # Copel — elétrica privatizada, dividendos relevantes
    "CMIG4",   # Cemig PN — elétrica MG, dividendos históricos
    "TIMS3",   # TIM — telecom, payout alto
    "VIVT3",   # Telefônica/Vivo — telecom, dividendo consistente
    "ITUB4",   # Itaú — bancão, dividendos altos e consistentes
    "BBDC4",   # Bradesco — dividendos históricos
    "PSSA3",   # Porto Seguro — seguradora, JCP consistente
    "WEGE3",   # WEG — crescimento + dividendo crescente
    "ABEV3",   # Ambev — defensiva, dividendos em dólar + real
    "CSAN3",   # Cosan — grupo diversificado, dividendos
    "PETR4",   # Petrobras PN — DY muito alto em ciclo favorável
    "VALE3",   # Vale — proventos em USD + BRL altos
    # Novas adições:
    "TRPL4",   # ISA CTEEP — transmissão, receita regulada, DY ~8%
    "AURE3",   # Auren Energia — elétrica renovável, DY consistente
    "CXSE3",   # Caixa Seguridade — distribuição Caixa, DY alto
    "BBSE3",   # BB Seguridade — seguros + previdência, DY > 8%
    "SBSP3",   # Sabesp — saneamento, pós-privatização, dividendos crescentes
    "KLBN11",  # Klabin Units — papel/celulose, dividendos em USD
    "SAPR11",  # Sanepar — saneamento, DY regulado
    "ISAE4",   # ISA Energia — transmissão LatAm, DY ≥ 7%
    "GOAU4",   # Metalúrgica Gerdau — siderurgia, dividendos
    "ELET6",   # Eletrobras PN — pós-privatização, DY crescente
]

# ─── Alpha — assimetria, crescimento, desconto (expandido ~30) ───────────────
ALPHA_WATCHLIST = [
    "PRIO3",   # PetroRio — oil independente, crescimento sólido
    "SMTO3",   # São Martinho — açúcar/etanol, tese de longo prazo
    "RECV3",   # PetroRecôncavo — petróleo onshore
    "RAIZ4",   # Raízen — biocombustíveis
    "LWSA3",   # Locaweb — tech BR, desconto vs histórico
    "TOTS3",   # Totvs — software empresarial, crescimento recorrente
    "MELI34",  # MercadoLibre BDR — líder e-commerce LA
    "INTB3",   # Intelbras — semicondutores BR, crescimento
    "TTEN3",   # 3tentos — agro
    "AGRO3",   # BrasilAgro — terras agrícolas
    "SLCE3",   # SLC Agrícola
    "BEEF3",   # Minerva — proteína animal, exportação
    "JBSS3",   # JBS — global, assimetria versus valor
    "EMBR3",   # Embraer — exportadora, ciclo de aviação
    "CYRE3",   # Cyrela — construtora, ciclo imobiliário
    "EVEN3",   # Even — construtora SP
    "ALPA4",   # Alpargatas PN — têxtil/calçados
    "ARZZ3",   # Arezzo&Co — varejo de moda premium
    "CASH3",   # Méliuz — fintech
    # Novas adições:
    "STBP3",   # Santos Brasil — portos, concessão
    "ALOS3",   # Allos — shoppings premium
    "SIMH3",   # Simpar — conglomerado logístico (JSL, Vamos, Movida)
    "VAMO3",   # Vamos — locação de caminhões e máquinas
    "PETZ3",   # Petz — pet care, crescimento
    "VIVR3",   # Viver Construtora — small cap turnaround
    "SBFG3",   # Grupo SBF (Centauro/Fisia) — esporte/varejo
    "MLAS3",   # Multilaser — tech/eletrônicos BR
    "DIRR3",   # Direcional — construtora, Minha Casa Minha Vida
    "PLPL3",   # Plano & Plano — construtora popular
    "SMFT3",   # Smart Fit — academias LatAm, crescimento
]

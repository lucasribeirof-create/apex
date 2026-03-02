"""
APEX Motors — Watchlists padrão por módulo de estratégia.

Critérios de curadoria:
  - Wheel/Momentum: top 20 ações com maior liquidez em opções na B3 (COTAHIST) +
                    volume médio diário > R$50M + free float relevante
  - FIIs: seleção de ~25 fundos de qualidade por segmento (lajes, logística,
          shoppings, recebíveis, híbridos) — DY consistente + gestores reconhecidos
  - ETFs: universo completo relevante na B3 (renda variável BR, internacional, RF)
  - Dividendos: pagadoras consistentes com histórico >= 5 anos e payout sustentável
  - Alpha: ações com histórico de assimetria (não são as mesmas de momentum)

Cada lista é o universo de candidatos que o motor vai analisar.
O motor filtra e rankeia — não usa todos os tickers da lista.
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

# ─── FIIs — universo por segmento ─────────────────────────────────────────────
FIIS_WATCHLIST = {
    "lajes_corporativas": [
        "HGRE11",  # CSHG Real Estate
        "RBRP11",  # RBR Properties
        "PVBI11",  # P. Verde Blanc I
        "BRCR11",  # BTG Corporate Office
        "JSRE11",  # JS Real Estate — lajes SP
    ],
    "logistica": [
        "XPLG11",  # XP Log
        "BRCO11",  # Bresco
        "HGLG11",  # CSHG Logística
        "VILG11",  # Vinci Logística
        "LVBI11",  # VBI Logística
        "SDIL11",  # SDI Logística
    ],
    "shoppings": [
        "XPML11",  # XP Malls
        "HSML11",  # HSI Malls
        "MALL11",  # Malls Brasil Plural
        "VISC11",  # Vinci Shopping Centers
        "ABCP11",  # Grand Plaza
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
    ],
    "hibridos_fofs": [
        "BPFF11",  # Brasil Plural Abs FoF
        "HFOF11",  # Hedge Top FOFII
        "RBRF11",  # RBR Alpha Multiestratégia
    ],
}

# Lista flat para uso no motor
FIIS_WATCHLIST_FLAT = [
    ticker
    for segmento in FIIS_WATCHLIST.values()
    for ticker in segmento
]

# ─── ETFs — universo completo relevante na B3 ─────────────────────────────────
ETFS_WATCHLIST = {
    "ibovespa": [
        "BOVA11",  # iShares IBOVESPA — mais líquido, maior AUM
        "BOVB11",  # Bradesco IBOVESPA
        "IVVB11",  # iShares S&P 500 em BRL (dolarizado) — tech USA
    ],
    "small_cap": [
        "SMAL11",  # iShares Small Cap — diversificação fora do IBOV
    ],
    "dividendos": [
        "DIVO11",  # Dividend ETF — bons pagadores BR
        "FIND11",  # iShares Financeiro
    ],
    "internacional": [
        "IVVB11",  # S&P 500 via BDR — exposição dólar
        "NASD11",  # Nasdaq em BRL
        "EURP11",  # Europa
    ],
    "renda_fixa_etf": [
        "FIXA11",  # ETF Renda Fixa prefixado
        "IMAB11",  # IMA-B (IPCA+)
        "IRFM11",  # IRF-M (prefixado médio)
    ],
    "esg": [
        "ISUS11",  # ESG BR
        "ECOO11",  # Carbono Eficiente
    ],
}

ETFS_WATCHLIST_FLAT = [
    "BOVA11", "BOVB11", "IVVB11", "SMAL11", "DIVO11",
    "FIND11", "NASD11", "EURP11", "FIXA11", "IMAB11",
    "IRFM11", "ISUS11", "ECOO11",
]

# ─── Dividendos — pagadoras consistentes ──────────────────────────────────────
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
]

# ─── Alpha — assimetria, crescimento, desconto fundamentalista ───────────────
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
    "ARZZ3",   # Arezzo&Co — varejo de moda premium (absorveu Grupo Soma)
    "CASH3",   # Méliuz — fintech
]

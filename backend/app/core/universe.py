"""
Universo de ativos para o Scanner APEX.
~80 tickers B3: ações mais líquidas + ETFs + FIIs principais.

Cada ativo tem:
  ticker  — código B3
  nome    — nome resumido
  tipo    — ACAO | ETF | FII
  setor   — usado para calcular força relativa setorial (Filtro 5)

Setores e seus proxies (ticker usado como benchmark do setor vs IBOV):
  energia       → PETR4
  mineracao     → VALE3
  financeiro    → BBAS3
  consumo       → ABEV3
  utilidades    → EGIE3
  saude         → RDOR3
  tecnologia    → TOTS3
  industrial    → WEGE3
  imobiliario   → HGLG11
  agro          → SLCE3
  etf           → BOVA11  (benchmark geral)
  fii           → HGLG11  (benchmark FII vs IBOV)

Customização: se existir data/universe.json, ele sobrepõe a lista padrão.
"""
import json
from pathlib import Path

_UNIVERSE_JSON = Path(__file__).resolve().parent.parent.parent.parent / "data" / "universe.json"

# ─── Proxy de setor para o Filtro 5 ──────────────────────────────────────────
# Para cada ativo, o "setor" define qual ticker usar como benchmark setorial.
# O scanner busca o histórico desse proxy e calcula retorno 63d vs IBOV.
SETOR_PROXY: dict[str, str] = {
    "energia":      "PETR4",
    "mineracao":    "VALE3",
    "financeiro":   "BBAS3",
    "consumo":      "ABEV3",
    "utilidades":   "EGIE3",
    "saude":        "RDOR3",
    "tecnologia":   "TOTS3",
    "industrial":   "WEGE3",
    "imobiliario":  "HGLG11",
    "agro":         "SLCE3",
    "etf":          "BOVA11",
    "fii":          "HGLG11",
    "outro":        "BOVA11",  # fallback: usa IBOV como próprio benchmark
}

# ─── Lista padrão ─────────────────────────────────────────────────────────────
_DEFAULT_UNIVERSE: list[dict] = [
    # ── Ações — Energia / Petróleo ──────────────────────────────────────────
    {"ticker": "PETR4",  "nome": "Petrobras PN",        "tipo": "ACAO", "setor": "energia"},
    {"ticker": "PETR3",  "nome": "Petrobras ON",        "tipo": "ACAO", "setor": "energia"},
    {"ticker": "PRIO3",  "nome": "PetroRio",            "tipo": "ACAO", "setor": "energia"},
    {"ticker": "RECV3",  "nome": "PetroRecôncavo",      "tipo": "ACAO", "setor": "energia"},
    {"ticker": "VBBR3",  "nome": "Vibra Energia",       "tipo": "ACAO", "setor": "energia"},
    {"ticker": "CSAN3",  "nome": "Cosan",               "tipo": "ACAO", "setor": "energia"},
    {"ticker": "RAIZ4",  "nome": "Raízen PN",           "tipo": "ACAO", "setor": "energia"},
    {"ticker": "ENEV3",  "nome": "Eneva",               "tipo": "ACAO", "setor": "utilidades"},

    # ── Ações — Mineração / Metais ───────────────────────────────────────────
    {"ticker": "VALE3",  "nome": "Vale",                "tipo": "ACAO", "setor": "mineracao"},
    {"ticker": "GGBR4",  "nome": "Gerdau PN",           "tipo": "ACAO", "setor": "mineracao"},
    {"ticker": "GOAU4",  "nome": "Gerdau Met PN",       "tipo": "ACAO", "setor": "mineracao"},
    {"ticker": "CSNA3",  "nome": "CSN",                 "tipo": "ACAO", "setor": "mineracao"},
    {"ticker": "USIM5",  "nome": "Usiminas PNA",        "tipo": "ACAO", "setor": "mineracao"},
    {"ticker": "KLBN11", "nome": "Klabin UNT",          "tipo": "ACAO", "setor": "industrial"},
    {"ticker": "SUZB3",  "nome": "Suzano",              "tipo": "ACAO", "setor": "industrial"},

    # ── Ações — Financeiro / Bancos ──────────────────────────────────────────
    {"ticker": "ITUB4",  "nome": "Itaú Unibanco PN",   "tipo": "ACAO", "setor": "financeiro"},
    {"ticker": "BBDC4",  "nome": "Bradesco PN",         "tipo": "ACAO", "setor": "financeiro"},
    {"ticker": "BBAS3",  "nome": "Banco do Brasil",     "tipo": "ACAO", "setor": "financeiro"},
    {"ticker": "BPAC11", "nome": "BTG Pactual UNT",     "tipo": "ACAO", "setor": "financeiro"},
    {"ticker": "SANB11", "nome": "Santander UNT",       "tipo": "ACAO", "setor": "financeiro"},
    {"ticker": "IRBR3",  "nome": "IRB Brasil RE",       "tipo": "ACAO", "setor": "financeiro"},

    # ── Ações — Consumo / Varejo ─────────────────────────────────────────────
    {"ticker": "ABEV3",  "nome": "Ambev",               "tipo": "ACAO", "setor": "consumo"},
    {"ticker": "LREN3",  "nome": "Lojas Renner",        "tipo": "ACAO", "setor": "consumo"},
    {"ticker": "PETZ3",  "nome": "Petz",                "tipo": "ACAO", "setor": "consumo"},
    {"ticker": "NTCO3",  "nome": "Grupo Natura",        "tipo": "ACAO", "setor": "consumo"},
    {"ticker": "BRFS3",  "nome": "BRF",                 "tipo": "ACAO", "setor": "consumo"},
    {"ticker": "JBSS32", "nome": "JBS BDR",             "tipo": "ACAO", "setor": "consumo"},
    {"ticker": "SMTO3",  "nome": "São Martinho",        "tipo": "ACAO", "setor": "agro"},
    {"ticker": "SLCE3",  "nome": "SLC Agrícola",        "tipo": "ACAO", "setor": "agro"},

    # ── Ações — Saúde ────────────────────────────────────────────────────────
    {"ticker": "RDOR3",  "nome": "Rede D'Or",           "tipo": "ACAO", "setor": "saude"},
    {"ticker": "RADL3",  "nome": "Raia Drogasil",       "tipo": "ACAO", "setor": "saude"},
    {"ticker": "HYPE3",  "nome": "Hypera",              "tipo": "ACAO", "setor": "saude"},
    {"ticker": "QUAL3",  "nome": "Qualicorp",           "tipo": "ACAO", "setor": "saude"},

    # ── Ações — Tecnologia / Telecom ─────────────────────────────────────────
    {"ticker": "TOTS3",  "nome": "Totvs",               "tipo": "ACAO", "setor": "tecnologia"},
    {"ticker": "VIVT3",  "nome": "Telefônica/Vivo",     "tipo": "ACAO", "setor": "tecnologia"},
    {"ticker": "TIMS3",  "nome": "TIM",                 "tipo": "ACAO", "setor": "tecnologia"},

    # ── Ações — Industrial / Logística ───────────────────────────────────────
    {"ticker": "WEGE3",  "nome": "WEG",                 "tipo": "ACAO", "setor": "industrial"},
    {"ticker": "EMBJ3",  "nome": "Embraer",             "tipo": "ACAO", "setor": "industrial"},
    {"ticker": "RAIL3",  "nome": "Rumo",                "tipo": "ACAO", "setor": "industrial"},
    {"ticker": "CCRO3",  "nome": "CCR",                 "tipo": "ACAO", "setor": "industrial"},
    {"ticker": "MULT3",  "nome": "Multiplan",           "tipo": "ACAO", "setor": "imobiliario"},

    # ── Ações — Utilidades / Energia Elétrica ────────────────────────────────
    {"ticker": "EGIE3",  "nome": "Engie Brasil",        "tipo": "ACAO", "setor": "utilidades"},
    {"ticker": "EQTL3",  "nome": "Equatorial",          "tipo": "ACAO", "setor": "utilidades"},
    {"ticker": "CMIG4",  "nome": "Cemig PN",            "tipo": "ACAO", "setor": "utilidades"},
    {"ticker": "ELET3",  "nome": "Eletrobras ON",       "tipo": "ACAO", "setor": "utilidades"},
    {"ticker": "CPLE3",  "nome": "Copel ON",            "tipo": "ACAO", "setor": "utilidades"},
    {"ticker": "TAEE11", "nome": "Taesa UNT",           "tipo": "ACAO", "setor": "utilidades"},
    {"ticker": "SBSP3",  "nome": "Sabesp",              "tipo": "ACAO", "setor": "utilidades"},

    # ── Ações — Outros ───────────────────────────────────────────────────────
    {"ticker": "RENT3",  "nome": "Localiza",            "tipo": "ACAO", "setor": "consumo"},
    {"ticker": "UGPA3",  "nome": "Ultrapar",            "tipo": "ACAO", "setor": "energia"},
    {"ticker": "YDUQ3",  "nome": "Yduqs",               "tipo": "ACAO", "setor": "outro"},
    {"ticker": "PSSA3",  "nome": "Porto Seguro",        "tipo": "ACAO", "setor": "financeiro"},
    {"ticker": "LWSA3",  "nome": "Locaweb",             "tipo": "ACAO", "setor": "tecnologia"},
    {"ticker": "INTB3",  "nome": "Intelbras",           "tipo": "ACAO", "setor": "tecnologia"},

    # ── ETFs Brasileiros ─────────────────────────────────────────────────────
    {"ticker": "BOVA11", "nome": "iShares IBOVESPA",    "tipo": "ETF",  "setor": "etf"},
    {"ticker": "BOVV11", "nome": "It Now IBOVESPA",     "tipo": "ETF",  "setor": "etf"},
    {"ticker": "IVVB11", "nome": "iShares S&P500 BRL",  "tipo": "ETF",  "setor": "etf"},
    {"ticker": "SMAL11", "nome": "iShares Small Cap",   "tipo": "ETF",  "setor": "etf"},
    {"ticker": "DIVO11", "nome": "It Now Dividendos",   "tipo": "ETF",  "setor": "etf"},
    {"ticker": "FIND11", "nome": "It Now Financeiro",   "tipo": "ETF",  "setor": "etf"},
    {"ticker": "MATB11", "nome": "It Now Materiais",    "tipo": "ETF",  "setor": "etf"},
    {"ticker": "ECOO11", "nome": "iShares Carbono Efi", "tipo": "ETF",  "setor": "etf"},
    {"ticker": "SPXI11", "nome": "It Now S&P500",       "tipo": "ETF",  "setor": "etf"},
    {"ticker": "GOLD11", "nome": "Trend Ouro",          "tipo": "ETF",  "setor": "etf"},
    {"ticker": "HASH11", "nome": "Hashdex Cripto",      "tipo": "ETF",  "setor": "etf"},
    {"ticker": "NTNB11", "nome": "Trend NTN-B",         "tipo": "ETF",  "setor": "etf"},
    {"ticker": "AGRI11", "nome": "Trend Agro",          "tipo": "ETF",  "setor": "etf"},

    # ── FIIs Principais ──────────────────────────────────────────────────────
    {"ticker": "HGLG11", "nome": "CSHG Logística",      "tipo": "FII",  "setor": "fii"},
    {"ticker": "BRCO11", "nome": "Bresco Logística",    "tipo": "FII",  "setor": "fii"},
    {"ticker": "XPML11", "nome": "XP Malls",            "tipo": "FII",  "setor": "fii"},
    {"ticker": "VISC11", "nome": "Vinci Shopping",      "tipo": "FII",  "setor": "fii"},
    {"ticker": "MXRF11", "nome": "Max Renda",           "tipo": "FII",  "setor": "fii"},
    {"ticker": "KNRI11", "nome": "Kinea Renda Imob.",   "tipo": "FII",  "setor": "fii"},
    {"ticker": "BTLG11", "nome": "BTG Pactual Log.",    "tipo": "FII",  "setor": "fii"},
    {"ticker": "CPTS11", "nome": "Capitânia Securities","tipo": "FII",  "setor": "fii"},
    {"ticker": "RBVA11", "nome": "Rio Bravo Renda V.",  "tipo": "FII",  "setor": "fii"},
    {"ticker": "VILG11", "nome": "Vinci Logística",     "tipo": "FII",  "setor": "fii"},
    {"ticker": "ALZR11", "nome": "Alianza Trust",       "tipo": "FII",  "setor": "fii"},
    {"ticker": "KNCR11", "nome": "Kinea Recebíveis",    "tipo": "FII",  "setor": "fii"},
    {"ticker": "RBRR11", "nome": "RBR Rendimento High", "tipo": "FII",  "setor": "fii"},
    {"ticker": "HGRU11", "nome": "CSHG Renda Urbana",   "tipo": "FII",  "setor": "fii"},
    {"ticker": "BCFF11", "nome": "BTG Pactual FoF",     "tipo": "FII",  "setor": "fii"},
]


# ─── API pública ──────────────────────────────────────────────────────────────

def get_universe(tipos: list[str] | None = None) -> list[dict]:
    """
    Retorna o universo de ativos.
    Se data/universe.json existir, usa ele (permite customização sem alterar código).
    tipos: filtrar por ["ACAO"], ["ETF"], ["FII"] ou None para todos.
    """
    universe = _carregar_universe()
    if tipos:
        universe = [a for a in universe if a["tipo"] in tipos]
    return universe


def get_tickers(tipos: list[str] | None = None) -> list[str]:
    """Retorna só os tickers do universo."""
    return [a["ticker"] for a in get_universe(tipos)]


def get_setor_proxy(setor: str) -> str:
    """Retorna o ticker proxy para calcular a força relativa do setor."""
    return SETOR_PROXY.get(setor, SETOR_PROXY["outro"])


def get_ticker_info(ticker: str) -> dict | None:
    """Retorna metadados de um ticker específico."""
    for ativo in _carregar_universe():
        if ativo["ticker"] == ticker.upper():
            return ativo
    return None


def salvar_universe_customizado(universe: list[dict]) -> None:
    """
    Salva um universo customizado em data/universe.json.
    Permite adicionar/remover ativos via API sem alterar código.
    """
    _UNIVERSE_JSON.parent.mkdir(exist_ok=True)
    _UNIVERSE_JSON.write_text(
        json.dumps(universe, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ─── Privado ──────────────────────────────────────────────────────────────────

def _carregar_universe() -> list[dict]:
    """Carrega JSON customizado se existir, senão retorna o default."""
    if _UNIVERSE_JSON.exists():
        try:
            data = json.loads(_UNIVERSE_JSON.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass
    return _DEFAULT_UNIVERSE

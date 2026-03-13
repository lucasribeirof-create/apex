"""Verifica dados importados da XP vs XLSX original."""
import sys
sys.path.insert(0, "backend")
from app.services.importers.xp_posicao_parser import parse_xp_posicao
from app.models import SessionLocal, Position

with open("data/exemplob3/PosicaoDetalhada.xlsx", "rb") as f:
    result = parse_xp_posicao(f.read())

corr = list(result.get("corretoras", {}).keys())
print(f"Corretoras no XLSX: {corr}")
first_key = corr[0] if corr else ""
xlsx_positions = result["corretoras"].get(first_key, {}).get("posicoes", [])

xlsx_by_ticker = {}
for p in xlsx_positions:
    xlsx_by_ticker.setdefault(p["ticker"], []).append(p)

db = SessionLocal()
db_positions = db.query(Position).filter(
    Position.portfolio_id == 3, Position.ativa == True
).all()
db_by_ticker = {}
for p in db_positions:
    db_by_ticker.setdefault(p.ticker, []).append(p)

print(f"XLSX: {len(xlsx_positions)} posicoes | DB: {len(db_positions)} posicoes")

# === 1. Quantidade e PM ===
print("\n=== QUANTIDADE E PRECO MEDIO ===")
erros_qty = 0
erros_pm = 0
for ticker in sorted(xlsx_by_ticker.keys()):
    xps = xlsx_by_ticker[ticker]
    dbs = db_by_ticker.get(ticker, [])
    for i, xp in enumerate(xps):
        if i >= len(dbs):
            print(f"  {ticker}: FALTANDO no DB (posicao #{i+1})")
            erros_qty += 1
            continue
        db_pos = dbs[i]
        qty_xp = xp["quantidade"]
        qty_db = db_pos.quantidade or 0
        if abs(qty_xp - qty_db) > 0.01:
            print(f"  {ticker}: QTY diverge! XLSX={qty_xp} DB={qty_db}")
            erros_qty += 1
        pm_xp = xp.get("preco_medio", 0)
        pm_db = db_pos.preco_medio or 0
        if pm_xp > 0 and abs(pm_xp - pm_db) > 0.02:
            print(f"  {ticker}: PM diverge! XLSX={pm_xp:.4f} DB={pm_db:.4f}")
            erros_pm += 1

if erros_qty == 0 and erros_pm == 0:
    print("  Todas as quantidades e precos medios OK!")
else:
    print(f"  Erros: {erros_qty} qty + {erros_pm} pm")

# === 2. Valor Investido = PM * QTY ===
print("\n=== VALOR INVESTIDO (PM x QTY) ===")
erros_vi = 0
for p in db_positions:
    if p.tipo == "RF":
        continue
    expected = round((p.preco_medio or 0) * (p.quantidade or 0), 2)
    actual = p.valor_investido or 0
    if abs(expected - actual) > 1:
        print(f"  {p.ticker}: VI={actual:.2f} esperado={expected:.2f}")
        erros_vi += 1
if erros_vi == 0:
    print("  Todos os valor_investido = PM x QTY corretos!")

# === 3. P&L = valor_atual - valor_investido ===
print("\n=== P&L REAIS ===")
erros_pl = 0
for p in db_positions:
    va = p.valor_atual or 0
    vi = p.valor_investido or 0
    pl_expected = round(va - vi, 2)
    pl_actual = p.pl_reais or 0
    if abs(pl_expected - pl_actual) > 1:
        print(f"  {p.ticker}: pl_reais={pl_actual:.2f} esperado={pl_expected:.2f}")
        erros_pl += 1
if erros_pl == 0:
    print("  Todos os P&L reais corretos!")

# === 4. P&L% = P&L / VI * 100 ===
print("\n=== P&L PERCENTUAL ===")
erros_pct = 0
for p in db_positions:
    vi = p.valor_investido or 0
    if vi <= 0:
        continue
    pl_r = p.pl_reais or 0
    pct_expected = round(pl_r / vi * 100, 2)
    pct_actual = p.pl_percentual or 0
    if abs(pct_expected - pct_actual) > 0.1:
        print(f"  {p.ticker}: pl%={pct_actual:.2f} esperado={pct_expected:.2f}")
        erros_pct += 1
if erros_pct == 0:
    print("  Todos os P&L percentuais corretos!")

# === 5. Tickers faltando ===
print("\n=== TICKERS FALTANDO / EXTRAS ===")
xlsx_tickers = set(xlsx_by_ticker.keys())
db_tickers = set(db_by_ticker.keys())
missing = xlsx_tickers - db_tickers
extra = db_tickers - xlsx_tickers
if missing:
    print(f"  No XLSX mas nao no DB: {missing}")
if extra:
    print(f"  No DB mas nao no XLSX: {extra}")
if not missing and not extra:
    print("  Mesmos tickers nos dois lados!")

total_erros = erros_qty + erros_pm + erros_vi + erros_pl + erros_pct + len(missing)
print(f"\n{'='*50}")
if total_erros == 0:
    print("RESULTADO FINAL: TODOS OS DADOS CORRETOS!")
else:
    print(f"RESULTADO FINAL: {total_erros} problemas encontrados")

db.close()

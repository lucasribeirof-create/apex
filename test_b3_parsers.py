"""Test B3 parsers against real XLSX files."""
import sys, json
sys.path.insert(0, "backend")

from app.services.importers.b3_posicao_parser import parse_b3_posicao
from app.services.importers.b3_negociacao_parser import parse_b3_negociacao
from app.services.importers.b3_movimentacao_parser import parse_b3_movimentacao

# ── Posição ──
print("=" * 60)
print("=== POSIÇÃO ===")
with open("data/exemplob3/posicao-2026-03-12-14-23-06.xlsx", "rb") as f:
    result = parse_b3_posicao(f.read())

print(f"Tipo: {result['tipo']}")
corretoras = result["corretoras"]
print(f"Corretoras: {list(corretoras.keys())}")
print(f"Totais: {result['totais']}")
for c, data in corretoras.items():
    print(f"  {data['nome_curto']}: {len(data['posicoes'])} posicoes")
    for p in data["posicoes"][:3]:
        print(f"    {p['ticker']} | {p['tipo']} | qtd={p['quantidade']} | val={p.get('valor_atualizado','?')}")

# ── Negociação ──
print("\n" + "=" * 60)
print("=== NEGOCIAÇÃO ===")
with open("data/exemplob3/negociacao-2026-03-12-14-24-20.xlsx", "rb") as f:
    result = parse_b3_negociacao(f.read())

print(f"Tipo: {result['tipo']}")
corretoras = result["corretoras"]
print(f"Corretoras: {list(corretoras.keys())}")
print(f"Totais: {result['totais']}")
for c, data in corretoras.items():
    print(f"  {data['nome_curto']}: {len(data['transacoes'])} transacoes")
    for t in data["transacoes"][:3]:
        print(f"    {t['data']} {t['ticker']} {t['tipo']} qtd={t['quantidade']} preco={t['preco']}")

# ── Movimentação ──
print("\n" + "=" * 60)
print("=== MOVIMENTAÇÃO ===")
with open("data/exemplob3/movimentacao-2026-03-12-14-23-56.xlsx", "rb") as f:
    result = parse_b3_movimentacao(f.read())

print(f"Tipo: {result['tipo']}")
corretoras = result["corretoras"]
print(f"Corretoras: {list(corretoras.keys())}")
print(f"Resumo: {result['resumo']}")
for c, data in corretoras.items():
    print(f"  {data['nome_curto']}: {len(data['movimentacoes'])} movimentacoes")
    for m in data["movimentacoes"][:3]:
        print(f"    {m['data']} {m.get('produto','?')[:30]} {m['categoria']} val={m.get('valor','?')}")

print("\n✅ All parsers executed successfully!")

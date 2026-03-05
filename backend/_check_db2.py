import sqlite3
c = sqlite3.connect(r"e:\Dropbox\apps_criados\APEX\data\apex.db")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)

# Check if there's an AI settings table
for t in tables:
    print(f"\nTable: {t}")
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})").fetchall()]
    print(f"  Cols: {cols}")
    rows = c.execute(f"SELECT * FROM {t}").fetchall()
    print(f"  Rows ({len(rows)}):")
    for r in rows[:5]:
        print(f"    {r}")

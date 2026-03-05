import sqlite3
c = sqlite3.connect(r"e:\Dropbox\apps_criados\APEX\data\apex.db")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables:", tables)
for t in tables[:8]:
    cols = [r[1] for r in c.execute(f"PRAGMA table_info({t})").fetchall()]
    rows = c.execute(f"SELECT * FROM {t} LIMIT 3").fetchall()
    print(f"\n{t} ({len(rows)} rows shown): cols={cols}")
    for r in rows:
        print("  ", r)

import sqlite3

conn = sqlite3.connect(r"E:\Dropbox\apps_criados\APEX\data\apex.db")
c = conn.cursor()

# List tables
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tables:", [t[0] for t in tables])

# Check portfolios
try:
    c.execute("SELECT count(*) FROM portfolios")
    print("Portfolios count:", c.fetchone()[0])
    rows = c.execute("SELECT * FROM portfolios LIMIT 5").fetchall()
    for r in rows:
        print("  ", r)
except Exception as e:
    print("Error:", e)

conn.close()

import sqlite3
c = sqlite3.connect('trading_laboratory.db')
cur = c.cursor()
print('--- tablas ---')
for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'"):
    print(r)

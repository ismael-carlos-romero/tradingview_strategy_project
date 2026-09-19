import sqlite3
c = sqlite3.connect('trading_laboratory.db')
cur = c.cursor()
print('--- setups 28 ---')
for r in cur.execute("SELECT setup_id, ticker, strategy_id, state, creation_time FROM setups WHERE creation_time LIKE '2026-08-28%' ORDER BY creation_time"):
    print(r)
print('--- operaciones_simuladas 28 (apertura o cierre) ---')
for r in cur.execute("SELECT id, ticker, estado, fecha_apertura, fecha_cierre FROM operaciones_simuladas WHERE fecha_apertura LIKE '2026-08-28%' OR fecha_cierre LIKE '2026-08-28%'"):
    print(r)
print('--- ultimos 10 setups (cualquier fecha) ---')
for r in cur.execute("SELECT setup_id, state, creation_time FROM setups ORDER BY creation_time DESC LIMIT 10"):
    print(r)
print('--- ultimas 10 operaciones (cualquier fecha) ---')
for r in cur.execute("SELECT id, ticker, estado, fecha_apertura, fecha_cierre FROM operaciones_simuladas ORDER BY fecha_apertura DESC LIMIT 10"):
    print(r)

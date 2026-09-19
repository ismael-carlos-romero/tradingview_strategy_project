import sqlite3
c = sqlite3.connect('trading_laboratory.db')
cur = c.cursor()
print('--- logs_auditoria (ultimos 30) ---')
try:
    cols = [d[1] for d in cur.execute("PRAGMA table_info(logs_auditoria)")]
    print(cols)
    for r in cur.execute("SELECT * FROM logs_auditoria ORDER BY rowid DESC LIMIT 30"):
        print(r)
except Exception as e:
    print('error', e)
print('--- bot_status ---')
for r in cur.execute("SELECT * FROM bot_status"):
    print(r)
print('--- ledger_movimientos ultimos 20 ---')
for r in cur.execute("SELECT mov_id, timestamp, tipo_movimiento, monto_debito, monto_credito, balance_resultante, estrategia, referencia FROM ledger_movimientos ORDER BY rowid DESC LIMIT 20"):
    print(r)

import sqlite3
c = sqlite3.connect('trading_laboratory.db')
cur = c.cursor()
print('--- decisiones 27 y 28 ---')
for r in cur.execute("SELECT decision_id, setup_id, source, action, rejection_reason, timestamp FROM decisiones WHERE timestamp LIKE '2026-08-27%' OR timestamp LIKE '2026-08-28%' ORDER BY timestamp"):
    print(r)
print('--- configuracion (estado del sistema) ---')
for r in cur.execute("SELECT param_id, val FROM configuracion"):
    print(r)
print('--- capital_buckets ---')
for r in cur.execute("SELECT bucket_id, porcentaje_asignado, capital_disponible, capital_comprometido, cuenta_id FROM capital_buckets"):
    print(r)
print('--- cuentas_simuladas ---')
for r in cur.execute("SELECT id, nombre, balance_inicial, balance_actual FROM cuentas_simuladas"):
    print(r)

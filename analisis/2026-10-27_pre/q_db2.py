import sqlite3, json
c = sqlite3.connect(r'file:C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project\trading_laboratory.db?mode=ro', uri=True)
cur = c.cursor()
print('--- senales hoy por estrategia/estado')
rows = cur.execute("select ticker, strategy_id, direction, timestamp, raw_payload from senales where timestamp >= '2026-10-27' order by timestamp").fetchall()
print(len(rows), 'senales hoy')
from collections import Counter
cnt = Counter()
for t, s, d, ts, p in rows:
    st = json.loads(p)['event']['state']
    cnt[(s, st)] += 1
for k, v in sorted(cnt.items()): print(k, v)
print('--- pilotos hoy')
for t, s, d, ts, p in rows:
    if t in ('SPY', 'NVDA', 'TSLA'):
        j = json.loads(p)
        print(ts, t, s, d, j['event']['state'], j['event']['setup_score'], round(j['market_data']['action_price'], 2), j['market_data']['indicators']['distance_pm40'])
print('--- radar_actual pilotos')
for r in cur.execute("select * from radar_actual where ticker in ('SPY','NVDA','TSLA') order by ticker, strategy_id"):
    print(r)
print('--- radar total filas', cur.execute('select count(*), count(distinct ticker) from radar_actual').fetchall())
print('--- trace_eventos hoy')
try:
    for r in cur.execute("select estado, count(*) from trace_eventos where date(ts)>='2026-10-27' group by 1"): print(r)
except Exception as e:
    print(e)
    print([r[1] for r in cur.execute('pragma table_info(trace_eventos)')])
print('--- config')
for r in cur.execute("select * from configuracion"): print(r)

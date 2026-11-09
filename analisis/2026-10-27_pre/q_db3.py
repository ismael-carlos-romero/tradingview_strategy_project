import sqlite3
c = sqlite3.connect(r'file:C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project\trading_laboratory.db?mode=ro', uri=True)
cur = c.cursor()
print('--- trace_eventos desde 26/10')
for r in cur.execute("select substr(ts_ar,1,10), venue, estado, count(*) from trace_eventos where ts_ar >= '2026-10-26' group by 1,2,3 order by 1,2,3"): print(r)
print('--- ultimos 12 de hoy')
for r in cur.execute("select ts_ar, ticker, estado, venue, motivo, setup_id from trace_eventos where ts_ar >= '2026-10-27' order by id desc limit 12"): print(r)
print('--- radar: tickers distintos')
print([r[0] for r in cur.execute("select distinct ticker from radar_actual order by 1")])

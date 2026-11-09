import sqlite3, sys
c = sqlite3.connect(r'file:C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project\trading_laboratory.db?mode=ro', uri=True)
cur = c.cursor()
for t in ('senales', 'setups', 'radar_actual', 'catalogo_estrategias', 'configuracion'):
    try:
        print(t, [r[1] for r in cur.execute(f'pragma table_info({t})')])
    except Exception as e:
        print(t, e)
print(cur.execute('select count(*) from senales').fetchall())
for r in cur.execute("select * from senales order by rowid desc limit 6"):
    print(r)
print('--- catalogo')
for r in cur.execute("select * from catalogo_estrategias"):
    print(r)

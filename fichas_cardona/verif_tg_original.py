import json, os, sqlite3, requests, subprocess
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t = json.load(open(os.path.join(base, "config.json"), encoding="utf-8")).get("telegram", {})
print("config original: enabled=%s token=%s chat=%s | fichas_chat_id definido=%s" % (t.get("enabled"), bool(t.get("bot_token")), bool(t.get("chat_id")), bool(t.get("fichas_chat_id"))))
r = requests.get(f"https://api.telegram.org/bot{t['bot_token']}/getMe", timeout=15)
print("getMe:", r.status_code, r.json().get("ok"))
db = sqlite3.connect(os.path.join(base, "trading_laboratory.db"))
print("ultimas confirmaciones (senales):", db.execute("select timestamp,ticker,strategy_id from senales order by timestamp desc limit 5").fetchall())
print("trace_origen con canal TELEGRAM (ultimas 3):", db.execute("select ts_utc,ticker,strategy_id,canales from trace_origen order by rowid desc limit 3").fetchall() if db.execute("select name from sqlite_master where name='trace_origen'").fetchone() else "sin tabla")
d = subprocess.run(["git", "diff", "--stat", "live_scanner.py"], cwd=base, capture_output=True, text=True).stdout
print(d)
d2 = subprocess.run(["git", "diff", "-U0", "live_scanner.py"], cwd=base, capture_output=True, text=True).stdout
print("lineas tocadas en send_telegram_notification (def en ~286-330):", [l for l in d2.splitlines() if l.startswith("@@") and any(s in l for s in ("-28", "-29", "-30", "-31", "-32"))])

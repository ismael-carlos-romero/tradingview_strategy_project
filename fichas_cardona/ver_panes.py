s = open(r"..\ucharts_sync_userscript_v5.0.45.js", encoding="utf-8").read()
i = s.find("btn-sync-day", 74000)
print(s[i - 200:i + 3800])

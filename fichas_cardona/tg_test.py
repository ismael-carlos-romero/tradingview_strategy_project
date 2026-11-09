import json, os, sys, requests
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
cfg = json.load(open(os.path.join(base, "config.json"), encoding="utf-8")).get("telegram", {})
tok, chat = cfg.get("bot_token", ""), cfg.get("chat_id", "")
print("enabled:", cfg.get("enabled"), "token:", bool(tok), "chat:", bool(chat))
if not (tok and chat):
    sys.exit(1)
txt = ("🧪 <b>Fichas Cardona — prueba de entrega</b>\n"
       "Solo prueba del canal. Sin señales ni órdenes.\n"
       "Guarda de señal vigente: 12/12 pruebas OK. Modo: solo Paper.")
r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                  json={"chat_id": chat, "text": txt, "parse_mode": "HTML"}, timeout=20)
print("sendMessage:", r.status_code, r.json().get("ok"))
# Adjunto de prueba: el .pine (muestra cómo llegaría un informe HTML)
f = os.path.join(os.path.dirname(os.path.abspath(__file__)), "meliora_fichas_prueba.pine")
with open(f, "rb") as fh:
    r2 = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument", data={"chat_id": chat},
                       files={"document": fh}, timeout=30)
print("sendDocument:", r2.status_code, r2.json().get("ok"))

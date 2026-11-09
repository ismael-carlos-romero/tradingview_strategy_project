"""Telegram SOLO para Fichas Cardona (separado de las confirmaciones originales).

Requiere en config.json -> telegram: "fichas_chat_id" (otro chat o grupo) y opcional "fichas_bot_token".
Si falta fichas_chat_id NO envía nada: así las fichas nunca se mezclan con el chat de las confirmaciones.
"""
import json, os, requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cfg():
    return json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8")).get("telegram", {})


def destino():
    c = _cfg()
    tok = c.get("fichas_bot_token") or c.get("bot_token", "")
    chat = str(c.get("fichas_chat_id", "") or "")
    if not chat or chat == str(c.get("chat_id", "")) and not c.get("fichas_bot_token"):
        return None
    return tok, chat


def enviar_ficha(texto, archivo=None):
    d = destino()
    if not d:
        return False, "SIN_DESTINO_PROPIO: falta telegram.fichas_chat_id distinto del chat de confirmaciones"
    tok, chat = d
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": "📋 <b>FICHAS CARDONA</b>\n" + texto, "parse_mode": "HTML"}, timeout=20)
    ok = r.ok
    if archivo and ok:
        with open(archivo, "rb") as fh:
            ok = requests.post(f"https://api.telegram.org/bot{tok}/sendDocument", data={"chat_id": chat},
                               files={"document": fh}, timeout=60).ok
    return ok, r.status_code

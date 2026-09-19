# -*- coding: utf-8 -*-
import re, io, sys
from collections import defaultdict

path = r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project\_debug_raw_history.txt"
with io.open(path, "r", encoding="utf-8") as f:
    raw_lines = [l.rstrip("\n").rstrip("\r") for l in f if l.strip() != ""]

# Reconstruir "descElements" tal como los ve el userscript: sólo las líneas
# Expired/... o Comprar/Vender ... options ..., cada una seguida de su
# fecha (línea siguiente). Las líneas de Comisión y de saldo se ignoran
# (el userscript tampoco las toma: no matchean el filtro de keywords).

allTx = []
i = 0
while i < len(raw_lines):
    desc = raw_lines[i]
    is_expired = desc.startswith("Expired/option/")
    is_trade = re.match(r"^(Comprar|Vender)\s+\d+\s+options?\s", desc)
    if is_expired or is_trade:
        date = raw_lines[i+1] if i+1 < len(raw_lines) else ""
        allTx.append({"desc": desc, "date": date})
        i += 4  # salta amount + balance también
    else:
        i += 1

print("Total transacciones detectadas:", len(allTx))

def history_ts(value):
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?", value)
    if not m:
        return 0
    mo, d, y, h, mi, s = m.groups()
    from datetime import datetime
    return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s or 0)).timestamp()

allTx.sort(key=lambda t: history_ts(t["date"]))

def parse_desc(desc):
    m = re.match(r"^Expired/option/([^/]+)/(\d+)/O:[A-Z0-9.]+?(\d{2})(\d{2})(\d{2})([CP])(\d{8})$", desc, re.I)
    if m:
        return {
            "action": "expire",
            "quantity": int(m.group(2)),
            "ticker": m.group(1).upper(),
            "expiry": "%s/%s/%s" % (m.group(3), m.group(4), m.group(5)),
            "type": "PUT" if m.group(6).upper() == "P" else "CALL",
            "strike": int(m.group(7)) / 1000.0,
            "price": 0.0,
        }
    m = re.match(
        r"(Comprar|Vender)\s+(\d+)\s+options?\s+(\S+)\s+(.*?)\s+(Call|Put)\s+([\d.,]+)\s+@\s*\$?\s*([\d.,]+)",
        desc, re.I)
    if m:
        action = "buy" if m.group(1).lower() in ("comprar",) else "sell"
        typ = "PUT" if m.group(5).lower() == "put" else "CALL"
        return {
            "action": action,
            "quantity": int(m.group(2)),
            "ticker": m.group(3),
            "expiry": m.group(4),
            "type": typ,
            "strike": float(m.group(6).replace(",", "")),
            "price": float(m.group(7).replace(",", "")),
        }
    return None

openPositions = defaultdict(list)
trades = []
skipped = []
unparsed = []

for tx in allTx:
    parsed = parse_desc(tx["desc"])
    if not parsed:
        unparsed.append(tx["desc"])
        continue
    parsed["date"] = tx["date"]
    key = "%s|%s|%s|%s" % (parsed["ticker"], parsed["expiry"], parsed["type"], parsed["strike"])

    if parsed["action"] == "buy":
        openPositions[key].append({
            "date": parsed["date"], "price": parsed["price"], "quantity": parsed["quantity"],
            "ticker": parsed["ticker"], "expiry": parsed["expiry"], "type": parsed["type"], "strike": parsed["strike"],
        })
    else:
        sellQty = parsed["quantity"]
        sellPrice = parsed["price"]
        sellDate = parsed["date"]
        while sellQty > 0 and openPositions[key]:
            ob = openPositions[key][0]
            if ob["quantity"] <= sellQty:
                trades.append({"ticker": ob["ticker"], "type": ob["type"], "strike": ob["strike"], "expiry": ob["expiry"],
                                "quantity": ob["quantity"], "buyDate": ob["date"], "buyPrice": ob["price"],
                                "sellDate": sellDate, "sellPrice": sellPrice, "status": "Cerrado"})
                sellQty -= ob["quantity"]
                openPositions[key].pop(0)
            else:
                trades.append({"ticker": ob["ticker"], "type": ob["type"], "strike": ob["strike"], "expiry": ob["expiry"],
                                "quantity": sellQty, "buyDate": ob["date"], "buyPrice": ob["price"],
                                "sellDate": sellDate, "sellPrice": sellPrice, "status": "Cerrado"})
                ob["quantity"] -= sellQty
                sellQty = 0
        if sellQty > 0:
            skipped.append({"ticker": parsed["ticker"], "type": parsed["type"], "strike": parsed["strike"],
                             "expiry": parsed["expiry"], "quantity": sellQty, "date": sellDate,
                             "reason": "vencimiento" if parsed["action"] == "expire" else "venta huerfana"})

abiertos = []
for key, lots in openPositions.items():
    for ob in lots:
        abiertos.append(ob)

print("No parseadas:", len(unparsed))
for u in unparsed: print("  ", u)
print()
print("Trades CERRADOS emparejados correctamente:", len(trades))
print("Posiciones que quedan ABIERTAS al final del dia:", len(abiertos))
print("Eventos HUERFANOS (sin compra para emparejar) -> se OMITEN, no se insertan:", len(skipped))

print()
print("--- Posiciones ABIERTAS (quedan abiertas, se cargarian como Abierto) ---")
for a in abiertos:
    print("  %-6s %-4s x%-6s strike=%-9s buy=%s @ $%.2f" % (a["ticker"], a["type"], a["quantity"], a["strike"], a["date"], a["price"]))

print()
print("--- Eventos HUERFANOS omitidos (no se insertan filas por estos) ---")
for s in skipped:
    print("  %-6s %-4s x%-6s strike=%-9s %s  fecha=%s  (%s)" % (s["ticker"], s["type"], s["quantity"], s["strike"], s["expiry"], s["date"], s["reason"]))

print()
print("--- Ejemplos de trades CERRADOS correctamente emparejados (primeros 15) ---")
for t in trades[:15]:
    pnl = (t["sellPrice"] - t["buyPrice"]) * t["quantity"] * 100
    print("  %-6s %-4s x%-6s buy=$%.2f (%s)  sell=$%.2f (%s)  PnL=$%.2f" % (
        t["ticker"], t["type"], t["quantity"], t["buyPrice"], t["buyDate"], t["sellPrice"], t["sellDate"], pnl))

print()
print("--- Trades cerrados via 'Expired' (venta/precio $0, verificando el caso SPY 770 Call) ---")
for t in trades:
    if t["sellPrice"] == 0.0:
        print("  %-6s %-4s x%-6s strike=%-9s buy=$%.2f (%s)  sell=$0.00 (%s)" % (
            t["ticker"], t["type"], t["quantity"], t["strike"], t["buyPrice"], t["buyDate"], t["sellDate"]))

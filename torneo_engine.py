"""Torneo de Bots autónomo: cada bot abre y cierra SU PROPIA posición virtual sobre
las señales confirmadas, con primas REALES de opciones (yfinance), sin inventar datos.
Compite contra el humano y contra el bot supervisado (Auto-Trader)."""
import os
import sqlite3
import json
import datetime as dt
import requests
import yfinance as yf

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_laboratory.db")
DTE = 7      # vencimiento mínimo (días), igual que los defaults del Auto-Trader
CAPITAL_INICIAL = 1000.0  # USD por bot, mismo punto de partida que el operador humano
ALLOC = 0.35              # fracción del capital actual que cada operación puede usar
MAX_1C = 0.50             # si 1 contrato supera ALLOC, se permite 1 solo si cuesta <= 50% del capital

# bot_id: (descripción, TP % sobre la prima, SL % sobre la prima)
BOTS = {
    "bot_replica":      ("Réplica Auto-Trader (TP 5%, SL -10%)", 5.0, -10.0),
    "bot_conservative": ("Conservador (TP 20%, SL -10%)", 20.0, -10.0),
    "bot_pilot":        ("Piloto Estándar (TP 30%, SL -15%)", 30.0, -15.0),
    "bot_aggressive":   ("Agresivo (TP 50%, SL -20%)", 50.0, -20.0),
}


SESSION = None  # live_scanner le inyecta su propia sesión HTTP (la misma que ya usa para yfinance)


def _conn():
    c = sqlite3.connect(DB, timeout=15.0)
    c.execute("""CREATE TABLE IF NOT EXISTS torneo_posiciones (
        id INTEGER PRIMARY KEY AUTOINCREMENT, bot_id TEXT, setup_id TEXT, ticker TEXT, side TEXT,
        strategy_id TEXT, open_ts TEXT, expiry TEXT, strike REAL, entry_price REAL, qty INTEGER,
        status TEXT DEFAULT 'ABIERTA', close_ts TEXT, exit_price REAL, last_price REAL,
        pnl_pct REAL, pnl_usd REAL, exit_reason TEXT)""")
    return c


def _side(direction):
    return "PUT" if "PUT" in str(direction).upper() else "CALL"


def _quote(ticker, side, expiry=None, strike=None, mode="buy"):
    """Devuelve (expiry, strike, prima) con datos reales, o None si no hay.
    Realista: compra al ASK y vende al BID (no al punto medio)."""
    try:
        tk = yf.Ticker(ticker, session=SESSION)
        if expiry is None:
            limit = (dt.date.today() + dt.timedelta(days=DTE)).isoformat()
            expiry = next((e for e in tk.options if e >= limit), None)
            if expiry is None:
                return None
        chain = tk.option_chain(expiry)
        df = chain.calls if side == "CALL" else chain.puts
        if strike is None:
            spot = float(tk.fast_info["last_price"])
            row = df.iloc[(df["strike"] - spot).abs().argsort()[:1]]
        else:
            row = df[df["strike"] == strike]
        if row.empty:
            return None
        r = row.iloc[0]
        bid, ask, last = float(r["bid"]), float(r["ask"]), float(r["lastPrice"])
        if ask > 0:
            price = ask if mode == "buy" else bid
        else:
            price = last
        if price < 0 or (mode == "buy" and price <= 0):
            return None
        return expiry, float(r["strike"]), round(price, 4)
    except Exception as e:
        print(f"[Torneo] Sin cotización real para {ticker} {side}: {e}")
        return None


def open_for_signal(ticker, direction, strategy_id, setup_id):
    """Cada bot abre su posición al mismo precio real de entrada."""
    side = _side(direction)
    conn = _conn()
    try:
        if conn.execute("SELECT 1 FROM torneo_posiciones WHERE setup_id = ? LIMIT 1", (setup_id,)).fetchone():
            return
        q = _quote(ticker, side)
        if not q:
            print(f"[Torneo] {ticker} {side}: sin prima real, no se abre (no se inventan datos).")
            return
        expiry, strike, price = q
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cost = price * 100
        opened = 0
        for bot_id in BOTS:
            pnl, = conn.execute("SELECT COALESCE(SUM(pnl_usd),0) FROM torneo_posiciones WHERE bot_id=? AND status='CERRADA'",
                                (bot_id,)).fetchone()
            inv, = conn.execute("SELECT COALESCE(SUM(entry_price*100*qty),0) FROM torneo_posiciones WHERE bot_id=? AND status='ABIERTA'",
                                (bot_id,)).fetchone()
            equity = CAPITAL_INICIAL + pnl
            qty = int(equity * ALLOC // cost)
            if qty < 1 and cost <= equity * MAX_1C:
                qty = 1
            qty = min(qty, int((equity - inv) // cost))
            if qty < 1:
                print(f"[Torneo] {bot_id}: capital insuficiente para {ticker} {side} (cuesta ${cost:.0f}, capital ${equity:.0f}, invertido ${inv:.0f})")
                continue
            conn.execute("""INSERT INTO torneo_posiciones
                (bot_id, setup_id, ticker, side, strategy_id, open_ts, expiry, strike, entry_price, qty, last_price)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (bot_id, setup_id, ticker, side, strategy_id, now, expiry, strike, price, qty, price))
            opened += 1
        conn.commit()
        print(f"[Torneo] {opened}/{len(BOTS)} bots abrieron {ticker} {side} {strike} {expiry} a ${price}")
    finally:
        conn.close()


def update_positions():
    """Revisa cada posición abierta contra su TP/SL con la prima real actual."""
    conn = _conn()
    cache = {}
    try:
        rows = conn.execute("""SELECT id, bot_id, ticker, side, expiry, strike, entry_price, qty
                               FROM torneo_posiciones WHERE status = 'ABIERTA'""").fetchall()
        today = dt.date.today().isoformat()
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for pid, bot_id, ticker, side, expiry, strike, entry, qty in rows:
            key = (ticker, side, expiry, strike)
            if key not in cache:
                cache[key] = _quote(ticker, side, expiry, strike, mode="sell")
            q = cache[key]
            last = q[2] if q else None
            if last is None:
                row = conn.execute("SELECT last_price FROM torneo_posiciones WHERE id = ?", (pid,)).fetchone()
                last = row[0]
            pnl_pct = (last / entry - 1) * 100
            _, tp, sl = BOTS[bot_id]
            reason = "TP" if pnl_pct >= tp else "SL" if pnl_pct <= sl else "EXPIRADA" if expiry < today else None
            if reason:
                conn.execute("""UPDATE torneo_posiciones SET status='CERRADA', close_ts=?, exit_price=?, last_price=?,
                                pnl_pct=?, pnl_usd=?, exit_reason=? WHERE id=?""",
                             (now, last, last, pnl_pct, (last - entry) * 100 * qty, reason, pid))
            else:
                conn.execute("UPDATE torneo_posiciones SET last_price=?, pnl_pct=? WHERE id=?", (last, pnl_pct, pid))
        conn.commit()
    finally:
        conn.close()


def standings():
    conn = _conn()
    try:
        out = []
        for bot_id, (desc, _, _) in BOTS.items():
            n, wins, avg, pnl = conn.execute("""SELECT COUNT(*), COALESCE(SUM(pnl_usd > 0),0), COALESCE(AVG(pnl_pct),0),
                COALESCE(SUM(pnl_usd),0) FROM torneo_posiciones WHERE bot_id=? AND status='CERRADA'""", (bot_id,)).fetchone()
            out.append({"bot_id": bot_id, "strategy_desc": desc, "total_trades": n, "winning_trades": wins,
                        "win_rate_pct": round(wins * 100.0 / n, 2) if n else 0.0,
                        "avg_return_pct": round(avg, 2), "total_pnl_usd": round(pnl, 2),
                        "capital_usd": round(CAPITAL_INICIAL + pnl, 2)})
        return out
    finally:
        conn.close()


REG_HEADERS = ["°", "Bot", "Fecha", "Trade #", "Ticker", "Call/Put", "Cantidad", "Compra", "Venta", "Total Compra",
               "Total Venta", "Saldo USD", "% Ganancia", "Estado", "Take Profit Objetivo", "Fecha de Expiración",
               "Strike", "Contrato Exacto", "Tipo Salida", "Fecha/Hora Compra", "Fecha/Hora Venta", "Estrategia"]
_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre"]


def _fecha_larga(ts):
    d = dt.datetime.strptime(ts[:10], "%Y-%m-%d")
    return f"{_DIAS[d.weekday()]}, {d.day} de {_MESES[d.month - 1]} de {d.year}"
RES_HEADERS = ["Fecha", "Bot", "Total Trades", "Ganados", "Perdidos", "USD Ganados", "USD Perdidos", "Win Rate %",
               "Promedio % Ganancia", "Total Saldo USD", "Capital USD (inicio 1000)"]


def build_tables():
    """Replica del Registro Continuo (una fila por trade de cada bot) y del Resumen diario por bot."""
    conn = _conn()
    try:
        rows = conn.execute("""SELECT id, bot_id, open_ts, close_ts, ticker, side, qty, entry_price, exit_price, pnl_usd,
                               pnl_pct, status, expiry, strike, exit_reason, strategy_id
                               FROM torneo_posiciones ORDER BY id DESC""").fetchall()
    finally:
        conn.close()
    reg, daily, nro, seq = [], {}, {}, {}
    for r in sorted(rows):
        seq[r[0]] = nro[r[1]] = nro.get(r[1], 0) + 1
    for (pid, bot, ots, cts, tk, side, qty, entry, exitp, pnl, pct, status, exp, strike, reason, strat) in rows:
        closed = status == "CERRADA"
        estado = "Abierto" if not closed else "Ganado" if pnl > 0 else "Perdido" if pnl < 0 else "Empate"
        tp_obj = round(entry * (1 + BOTS[bot][1] / 100), 2)
        reg.append([pid, bot, _fecha_larga(ots), seq[pid], tk, side, qty, entry, exitp if closed else "",
                    round(entry * 100 * qty, 2), round(exitp * 100 * qty, 2) if closed else "",
                    round(pnl, 2) if closed else "", round(pct, 2) if closed else "", estado, tp_obj, exp, strike,
                    f"{tk}|{exp}|{side}|{strike:g}", reason or "ABIERTO", ots, cts or "", strat])
        if closed:
            d = daily.setdefault((cts[:10], bot), [0, 0, 0, 0.0, 0.0, 0.0])
            d[0] += 1
            d[1] += pnl > 0
            d[2] += pnl < 0
            d[3] += pnl if pnl > 0 else 0
            d[4] += pnl if pnl < 0 else 0
            d[5] += pct
    cum, res = {}, []
    for (day, bot), d in sorted(daily.items()):
        cum[bot] = cum.get(bot, CAPITAL_INICIAL) + d[3] + d[4]
        res.append([_fecha_larga(day), bot, d[0], d[1], d[2], round(d[3], 2), round(d[4], 2), round(d[1] * 100.0 / d[0], 2),
                    round(d[5] / d[0], 2), round(d[3] + d[4], 2), round(cum[bot], 2)])
    res.reverse()
    return reg, res


def push_to_sheet(webhook_url):
    """Reemplaza las filas de TORNEO_BOTS con los resultados reales del motor nuevo."""
    if not webhook_url or webhook_url == "TU_WEBHOOK_URL_AQUÍ":
        return
    payload = {"webhook_token": "LAB_SIM_SECURE_TOKEN",
               "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "event": {"action": "tournament_update"}, "tournament_results": standings()}
    try:
        r = (SESSION or requests).post(webhook_url, json=payload, headers={"Content-Type": "text/plain"}, timeout=25)
        print(f"[Torneo] Sheet actualizado: {r.status_code}")
        reg, res = build_tables()
        payload = {"webhook_token": "LAB_SIM_SECURE_TOKEN", "event": {"action": "torneo_registro"},
                   "registro_headers": REG_HEADERS, "registro_rows": reg,
                   "resumen_headers": RES_HEADERS, "resumen_rows": res}
        r = (SESSION or requests).post(webhook_url, json=payload, headers={"Content-Type": "text/plain"}, timeout=60)
        print(f"[Torneo] Registro y resumen del torneo enviados: {r.status_code}")
    except Exception as e:
        print(f"[Torneo] Error al actualizar el Sheet: {e}")

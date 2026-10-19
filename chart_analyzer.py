"""Capa 1 - analisis de grafico (modo sombra). No bloquea ni modifica compras.
Uso suelto: python chart_analyzer.py SPY CALL
"""
import json
import sqlite3
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

_SESSION = None  # sesión HTTP del scanner (live_scanner.session), se inyecta con set_session()
_CACHE = {}
_TTL = 3600


def set_session(s):
    global _SESSION
    _SESSION = s


def _fetch(ticker, interval, period):
    key = (ticker, interval)
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL:
        return hit[1]
    df = yf.download(ticker, interval=interval, period=period, progress=False, auto_adjust=True, session=_SESSION)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    _CACHE[key] = (time.time(), df)
    return df


def _resample(df, rule):
    return df.resample(rule).agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna()


def _trend(df):
    """+1 alcista, -1 bajista, 0 lateral."""
    c = df["Close"]
    if len(c) < 55:
        return 0
    sma = c.rolling(50).mean()
    slope = (sma.iloc[-1] - sma.iloc[-10]) / sma.iloc[-10]
    if c.iloc[-1] > sma.iloc[-1] and slope > 0.002:
        return 1
    if c.iloc[-1] < sma.iloc[-1] and slope < -0.002:
        return -1
    return 0


def _pivots(df, w=5):
    h, l = df["High"].values, df["Low"].values
    highs, lows = [], []
    for i in range(w, len(df) - w):
        if h[i] == h[i - w:i + w + 1].max():
            highs.append((i, float(h[i])))
        if l[i] == l[i - w:i + w + 1].min():
            lows.append((i, float(l[i])))
    return highs, lows


def _levels(points, tol=0.01):
    """Agrupa pivots cercanos; devuelve [(nivel, toques)]."""
    out = []
    for _, p in sorted(points, key=lambda x: x[1]):
        if out and abs(p - out[-1][0]) / out[-1][0] <= tol:
            n = out[-1][1]
            out[-1] = ((out[-1][0] * n + p) / (n + 1), n + 1)
        else:
            out.append((p, 1))
    return out


def _sr(daily, price):
    highs, lows = _pivots(daily.tail(250).reset_index(drop=True))
    lv = _levels(highs + lows)
    sup = [x for x in lv if x[0] < price]
    res = [x for x in lv if x[0] > price]
    s = max(sup, key=lambda x: x[0]) if sup else None
    r = min(res, key=lambda x: x[0]) if res else None
    return s, r


def _channel(daily, n=60):
    c = daily["Close"].tail(n).values
    if len(c) < n:
        return None
    x = np.arange(n)
    m, b = np.polyfit(x, c, 1)
    resid = c - (m * x + b)
    lo, hi = resid.min(), resid.max()
    if hi - lo <= 0:
        return None
    pos = (resid[-1] - lo) / (hi - lo)
    return {"pos": float(pos), "slope": float(m)}


def _patterns(daily):
    d = daily.tail(180).reset_index(drop=True)
    highs, lows = _pivots(d, 4)
    price = float(d["Close"].iloc[-1])
    found = []
    tol = 0.025
    if len(lows) >= 2:
        (i1, a), (i2, b) = lows[-2], lows[-1]
        if abs(a - b) / a <= tol and i2 - i1 >= 8:
            neck = d["High"].iloc[i1:i2 + 1].max()
            found.append(("Doble piso", 1, price > neck))
    if len(highs) >= 2:
        (i1, a), (i2, b) = highs[-2], highs[-1]
        if abs(a - b) / a <= tol and i2 - i1 >= 8:
            neck = d["Low"].iloc[i1:i2 + 1].min()
            found.append(("Doble techo", -1, price < neck))
    if len(highs) >= 3 and len(lows) >= 2:
        (_, l), (_, hd), (_, r) = highs[-3:]
        if hd > l * 1.02 and hd > r * 1.02 and abs(l - r) / l <= 0.05:
            neck = np.mean([x[1] for x in lows[-2:]])
            found.append(("Hombro-cabeza-hombro", -1, price < neck))
    if len(lows) >= 3 and len(highs) >= 2:
        (_, l), (_, hd), (_, r) = lows[-3:]
        if hd < l * 0.98 and hd < r * 0.98 and abs(l - r) / l <= 0.05:
            neck = np.mean([x[1] for x in highs[-2:]])
            found.append(("HCH invertido", 1, price > neck))
    if len(highs) >= 2 and len(lows) >= 2:
        h1, h2 = highs[-2][1], highs[-1][1]
        l1, l2 = lows[-2][1], lows[-1][1]
        if h2 < h1 * 0.99 and l2 > l1 * 1.01:
            found.append(("Triangulo simétrico", 0, False))
    return found


def analyze(ticker, direction):
    bull = not any(k in str(direction).upper() for k in ("PUT", "BAJ", "SHORT", "BEAR"))
    sgn = 1 if bull else -1
    h1 = _fetch(ticker, "1h", "730d")
    d1 = _fetch(ticker, "1d", "5y")
    h4 = _resample(h1, "4h")
    w1 = _resample(d1, "W")
    tr = {"1H": _trend(h1), "4H": _trend(h4), "1D": _trend(d1), "1W": _trend(w1)}
    price = float(d1["Close"].iloc[-1])
    s, r = _sr(d1, price)
    ch = _channel(d1)
    pats = _patterns(d1)

    score = 50.0
    notes = []
    for k, v in tr.items():
        score += 7.5 * v * sgn
    if s and (price - s[0]) / price <= 0.015:
        score += 10 * sgn
        notes.append("sobre soporte")
    if r and (r[0] - price) / price <= 0.015:
        score -= 10 * sgn
        notes.append("bajo resistencia")
    if ch:
        if ch["pos"] <= 0.33:
            score += 10 * sgn
        elif ch["pos"] >= 0.67:
            score -= 10 * sgn
    for name, d, conf in pats:
        if d:
            score += (10 if conf else 5) * d * sgn
    score = int(max(0, min(100, round(score))))
    verdict = "REFUERZA" if score >= 60 else ("DEBILITA" if score < 40 else "NEUTRO")
    return {
        "ticker": ticker, "direction": "CALL" if bull else "PUT", "price": price,
        "score": score, "verdict": verdict, "trends": tr,
        "support": s, "resistance": r, "channel": ch,
        "patterns": [{"name": n, "dir": d, "confirmed": bool(c)} for n, d, c in pats],
        "notes": notes,
    }


def format_block(a):
    arrow = {1: "▲", -1: "▼", 0: "►"}
    t = " ".join(f"{k}{arrow[v]}" for k, v in a["trends"].items())
    lines = [
        "📊 <b>Análisis de gráfico</b>",
        f"Puntaje: <b>{a['score']}/100</b> → {a['verdict']}",
        f"Tendencias: {t}",
    ]
    if a["support"]:
        lines.append(f"Soporte: ${a['support'][0]:.2f} ({a['support'][1]} toques)")
    if a["resistance"]:
        lines.append(f"Resistencia: ${a['resistance'][0]:.2f} ({a['resistance'][1]} toques)")
    if a["channel"]:
        lines.append(f"Canal: {a['channel']['pos'] * 100:.0f}% (0=piso, 100=techo)")
    for p in a["patterns"]:
        lines.append(f"Figura: {p['name']} ({'confirmada' if p['confirmed'] else 'formándose'})")
    return "\n".join(lines)


def log_analysis(db_path, a, strategy_id=None, setup_id=None):
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS chart_analysis_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "timestamp TEXT, setup_id TEXT, ticker TEXT, strategy_id TEXT, direction TEXT, "
        "score INTEGER, verdict TEXT, detail TEXT)"
    )
    conn.execute(
        "INSERT INTO chart_analysis_log (timestamp, setup_id, ticker, strategy_id, direction, score, verdict, detail) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), setup_id, a["ticker"], strategy_id,
         a["direction"], a["score"], a["verdict"], json.dumps(a, default=str)),
    )
    conn.commit()
    conn.close()


def analyze_for_signal(db_path, ticker, direction, strategy_id=None, setup_id=None):
    """Devuelve el bloque de texto para Telegram o '' si falla. Nunca lanza."""
    try:
        a = analyze(ticker, direction)
        try:
            log_analysis(db_path, a, strategy_id, setup_id)
        except Exception as e:
            print(f"[ChartAnalyzer] No se pudo registrar: {e}")
        return format_block(a)
    except Exception as e:
        print(f"[ChartAnalyzer] Error en {ticker}: {e}")
        return ""


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    _s = requests.Session()
    _s.verify = False
    _s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
    set_session(_s)
    tk = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    dr = sys.argv[2] if len(sys.argv) > 2 else "CALL"
    print(format_block(analyze(tk, dr)))

"""Canales para 'Meliora Fichas Cardona'. Usa cardona_rules (2 pivotes confirmados, sin futuro).
Bajista: techo = linea de caida; piso = paralela por el minimo mas bajo desde el 1er pivote.
Alcista: piso = linea ascendente; techo = paralela por el maximo mas alto desde el 1er pivote.
Todo sale como PENDIENTE: el criterio de canal (pivotes, paralela) aun no fue validado por Ismael.
Uso: python canal_pine.py SPY [NVDA ...]  -> datos_canales.txt (filas C|...)"""
import os, sys
import numpy as np, pandas as pd, yfinance as yf
base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base)
import cardona_rules as cr


def cargar(t):
    m30 = yf.download(t, period="60d", interval="30m", prepost=True, progress=False, auto_adjust=False)
    d1 = yf.download(t, period="2y", interval="1d", progress=False, auto_adjust=False)
    for df in (m30, d1):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    idx = m30.index.tz_convert(cr.NY) if m30.index.tz else m30.index.tz_localize("UTC").tz_convert(cr.NY)
    m30.index = idx
    mins = idx.hour * 60 + idx.minute
    reg = m30[(mins >= 570) & (mins < 960)]
    return cr.add_features(cr.build_cardona_bars(reg, now=None), d1)


ms = lambda ts: int(pd.Timestamp(ts).timestamp() * 1000)
filas = []
for t in sys.argv[1:] or ["SPY"]:
    h = cargar(t)
    n = len(h)
    crit = "2 pivotes confirmados (cardona_rules); paralela por extremo opuesto; PENDIENTE de validar por Ismael"
    d = cr.descending_line(h, n, 60)
    if d:
        j1, y1, j2, y2 = d
        k = int(h["Low"].values[j1:n].argmin()) + j1
        filas.append(f"C|{t}|CANAL_BAJISTA|-|PENDIENTE|{ms(h.index[j1])}|{y1:.2f}|{ms(h.index[j2])}|{y2:.2f}|{ms(h.index[k])}|{h['Low'].values[k]:.2f}|{crit}")
    a = cr.ascending_line(h, n, 60)
    if a:
        j1, y1, j2, y2 = a
        k = int(h["High"].values[j1:n].argmax()) + j1
        filas.append(f"C|{t}|CANAL_ALCISTA|-|PENDIENTE|{ms(h.index[j1])}|{y1:.2f}|{ms(h.index[j2])}|{y2:.2f}|{ms(h.index[k])}|{h['High'].values[k]:.2f}|{crit}")
    print(t, "bajista:", bool(d), "alcista:", bool(a), "| barras:", n, "| ultima:", h.index[-1])
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos_canales.txt")
open(out, "w", encoding="utf-8").write("\n".join(filas))
print("\n".join(filas))

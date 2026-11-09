"""Linea de tendencia de Cardona, unica para TODAS las estrategias (version lineas-cardona-v1).

Regla (confirmada por el usuario el 01/11/2026):
  * LINEA DE CAIDA: une la COLA SUPERIOR (High) del maximo mas alto de la caida con la cola superior de la ULTIMA vela cerrada.
    Se recalcula con cada vela nueva y siempre llega hasta la ultima vela.
  * LINEA DE SUBIDA: une la cola inferior (Low) del minimo mas bajo de la subida con la cola inferior de la ultima vela.
  * Ninguna vela intermedia puede pasar la linea (tolerancia TOL). Si la pasa, el ancla es el siguiente extremo que si cumpla.
  * Ruptura CALL: vela verde que cierra sobre la linea de caida proyectada. Ruptura PUT: vela roja que cierra bajo la de subida.
  * Sin futuro: la linea evaluada en la vela i se construye solo con velas hasta i-1 y se proyecta a i.
Devuelve (j1, y1, j2, y2) con indices de posicion (como cardona_rules.line_at) o None.
"""
import numpy as np

VERSION = "lineas-cardona-v1"
TOL = 0.0005      # 0,05 % de tolerancia a que una cola intermedia toque la linea
MIN_SEP = 5       # velas minimas entre ancla y ultima vela
MIN_PEND = 0.004  # la linea debe bajar/subir al menos 0,4 % (propio)
TOQ = 0.0025      # al menos una cola intermedia a <=0,25 % de la linea: que sea una linea real (propio)
LOOKBACK = 60


def _at(j1, y1, j2, y2, x):
    return y1 + (y2 - y1) / (j2 - j1) * (x - j1)


def linea_caida(h, i, lookback=LOOKBACK, min_sep=MIN_SEP):  # el ancla debe estar a >= min_sep velas
    H = h["High"].values
    lo = max(0, i - lookback)
    if i - lo < min_sep:
        return None
    cand = [j for j in range(lo, i - min_sep + 1) if H[j] > H[i]]
    for j in sorted(cand, key=lambda k: (-H[k], k)):
        if (H[j] - H[i]) / H[j] >= MIN_PEND and all(H[t] <= _at(j, H[j], i, H[i], t) * (1 + TOL) for t in range(j + 1, i)) \
                and any(H[t] >= _at(j, H[j], i, H[i], t) * (1 - TOQ) for t in range(j + 1, i)):
            return (j, float(H[j]), i, float(H[i]))
    return None


def linea_subida(h, i, lookback=LOOKBACK, min_sep=MIN_SEP):
    L = h["Low"].values
    lo = max(0, i - lookback)
    if i - lo < min_sep:
        return None
    cand = [j for j in range(lo, i - min_sep + 1) if L[j] < L[i]]
    for j in sorted(cand, key=lambda k: (L[k], k)):
        if (L[i] - L[j]) / L[j] >= MIN_PEND and all(L[t] >= _at(j, L[j], i, L[i], t) * (1 - TOL) for t in range(j + 1, i)) \
                and any(L[t] <= _at(j, L[j], i, L[i], t) * (1 + TOQ) for t in range(j + 1, i)):
            return (j, float(L[j]), i, float(L[i]))
    return None


def valor(ln, x):
    return _at(*ln, x)


def ruptura_call(h, i):
    """Vela i: verde y cierra sobre la linea de caida construida hasta i-1 y proyectada a i. Devuelve la linea o None."""
    ln = linea_caida(h, i - 1)
    r = h.iloc[i]
    if ln and r.Close > r.Open and r.Close > valor(ln, i):
        return ln
    return None


def ruptura_put(h, i):
    ln = linea_subida(h, i - 1)
    r = h.iloc[i]
    if ln and r.Close < r.Open and r.Close < valor(ln, i):
        return ln
    return None

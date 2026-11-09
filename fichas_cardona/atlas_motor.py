"""Atlas motor - las 12 estrategias de Cardona por ETAPAS (version atlas-motor-v1). Solo analiza y avisa; NO opera.
Cada estrategia devuelve pasos [{n, ok(True/False/None=pendiente), d}] y una etapa:
  SIN_CONTEXTO < VIGILANCIA (pasos de contexto ok) < CASI (falta solo el ultimo paso) < CONFIRMADA (todos; CONFIRMADA_FUERA_DE_HORARIO si no esta en la regla de oro).
Fuente: laminas de Cardona (assets\\cardona_*.png). Umbrales que la lamina NO da van marcados en NOTAS_PROPIAS.
"""
import numpy as np, pandas as pd
import cardona_rules as cr
import lineas_cardona as lc

VERSION = "atlas-motor-v1"
GAP_MIN, CAIDA_MIN, CAIDA_FUERTE = cr.GAP_MIN, cr.CAIDA_MIN, cr.CAIDA_FUERTE
RVOL_ALTO = 1.0          # propio: volumen relativo (misma franja, 20 dias). La lamina dice "alto volumen" sin numero
SPOT_USD, SPOT_USD_ALC = 7.5, 10.0   # literal de la lamina (dolares sobre PM40); pensado para SPY/QQQ
NOTAS_PROPIAS = {"rvol>1": "alto volumen = volumen relativo > 1 (propio)", "gap>=0.1%": "gap minimo 0,1 % (del bot)",
                 "caida>=0.5%": "caida minima 0,5 % (del bot)", "solida>=60%": "cuerpo solido = 60 % del rango (del bot)"}


def S(n, ok, d=""):
    return {"n": n, "ok": None if ok is None else bool(ok), "d": d}


def daily(d1):
    D = d1.copy()
    D.index = pd.DatetimeIndex(D.index).tz_localize(None).normalize()
    D = D.dropna(subset=["Close"])
    for n in (20, 100, 200):
        D[f"sma{n}"] = D.Close.rolling(n).mean()
    rng, body = D.High - D.Low, (D.Close - D.Open).abs()
    D["green"], D["red"] = D.Close > D.Open, D.Close < D.Open
    D["hanger"] = (rng > 0) & ((D.High - np.maximum(D.Open, D.Close)) >= 0.45 * rng) & (body <= 0.4 * rng)
    D["hi20"], D["lo60"] = D.High.rolling(20).max(), D.Low.rolling(60).min()
    return D


def preparar(h30, d1):
    h = cr.add_features(cr.build_cardona_bars(h30), d1)
    h["rvol"] = h.Volume / h.groupby("slot").Volume.transform(lambda s: s.rolling(20, min_periods=5).mean().shift(1))
    return h, daily(d1)


class X:  # contexto de evaluacion en la ultima vela de h
    pass


def contexto(h, D):
    x = X(); x.h = h; x.i = len(h) - 1; x.r = h.iloc[-1]; x.today = h.index[-1].date()
    x.cerrado = bool(x.r.end_min >= 960)
    t = pd.Timestamp(x.today); Dd = D[D.index <= t]
    x.D = Dd if x.cerrado else Dd[Dd.index < t]
    x.dr = x.D.iloc[-1]
    x.hoy = h[h["date"] == x.today]
    return x


# ---------- piezas comunes
def paralelo(h, k=10, pm20_40=True):
    w = h.iloc[-k:]
    return bool(((w.PM20 > w.PM40).all() if pm20_40 else True) and (w.PM100 > w.PM200).all())


def caida_diaria(dr):
    return bool(dr.Close < dr.sma20 and (dr.hi20 - dr.Close) / dr.hi20 * 100 >= 2)


def cerca_piso_diario(dr, tol=0.02):
    return bool(any(abs(dr.Close - m) / m <= tol or dr.Close < m for m in (dr.sma100, dr.sma200) if m == m))


def verde_fuerte(r):
    return bool((r.solid_green or r.hammer) and not r.hanger_like)


def cuerpo_bajo(r):
    return float(min(r.Open, r.Close))


def draw_linea(ln, k="caida"):
    return {"k": k, "p": [int(ln[0]), round(ln[1], 2), int(ln[2]), round(ln[3], 2)]} if ln else None


def etapa(steps, n_ctx, ventana_ok):
    oks = [s["ok"] for s in steps]
    if all(o is True for o in oks):
        return "CONFIRMADA" if ventana_ok else "CONFIRMADA_FUERA_DE_HORARIO"
    if not all(o is True for o in oks[:n_ctx]):
        return "SIN_CONTEXTO"
    return "CASI" if all(o is True for o in oks[:-1]) else "VIGILANCIA"


def res(x, steps, n_ctx, ventana, dir_, draw=None, nota=""):
    em = x.r.end_min
    vok = ventana[0] <= em <= ventana[1]
    return {"etapa": etapa(steps, n_ctx, vok), "dir": dir_, "pasos": steps, "ventana": f"{ventana[0]//60}:{ventana[0]%60:02d}-{ventana[1]//60}:{ventana[1]%60:02d}",
            "ventana_ok": bool(vok), "draw": [d for d in (draw or []) if d], "nota": nota}


def nth(x, k):
    return x.hoy.iloc[k] if len(x.hoy) > k else None

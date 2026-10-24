"""Reglas de Cardona segun el PDF "Resumen del seminario" - version cardona-pdf-v1.

Principios (pedidos por el usuario):
  * Velas horarias ALINEADAS como las de Cardona: 9:30-10:00, 10:00-11:00, ..., 15:00-16:00 (hora de Nueva York).
  * Solo velas CERRADAS (regla "no comprar con velas en formacion").
  * Sin informacion futura: evaluate_bar(h, i) solo mira h.iloc[:i+1]. Los pivotes se usan recien
    cuando estan confirmados (k velas despues).
  * "Trazar una linea" = recta por los dos ultimos pivotes confirmados (definicion operativa, ver
    descending_line / ascending_line). Es una interpretacion: hay que validarla visualmente.
  * Umbrales que el PDF no da (gap 0,1 %, caida 0,5 %, cuerpo "solido" 60 %, etc.) se conservan del bot.
Estrategias implementadas aqui: GAP_NORMAL, GAP_BAJISTA, CAIDA_NORMAL, CAIDA_FUERTE, PISO_FUERTE,
PM40_BOUNCE, CANAL_BREAK, RUPTURA_PISO, VELA_ROJA, 4_PASOS. (PRIMER_GAP y HANGER_DIARIO siguen con la
logica anterior hasta definir su horario de entrada; las 7 estrategias fuera del PDF son 'propias'.)
"""
import numpy as np
import pandas as pd

VERSION = "cardona-pdf-v1"
NY = "America/New_York"
GAP_MIN = 0.1          # % (del bot; el PDF no da numero)
CAIDA_MIN = 0.5        # % (del bot)
CAIDA_FUERTE = 1.5     # % (PDF: "SPY < 1,5 %" = normal)
TOL = 0.001            # tolerancia de la linea (0,1 %)


# ---------------------------------------------------------------- velas alineadas
def build_cardona_bars(df30, now=None):
    """30 min -> velas horarias alineadas a la hora (la 1a es de 30 min: 9:30-10:00). Solo cerradas."""
    d = df30.copy()
    if d.index.tz is None:
        d.index = d.index.tz_localize("UTC")
    d.index = d.index.tz_convert(NY)
    now = pd.Timestamp.now(tz=NY) if now is None else pd.Timestamp(now).tz_convert(NY)
    d = d[d.index + pd.Timedelta(minutes=30) <= now]                 # velas de 30 min ya cerradas
    g = d.index.floor("h")
    out = d.groupby(g).agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
                           Close=("Close", "last"), Volume=("Volume", "sum"), n=("Close", "size"))
    out = out[out["n"] >= np.where(out.index.hour == 9, 1, 2)].drop(columns="n")
    out.index = pd.DatetimeIndex([t + pd.Timedelta(minutes=30) if t.hour == 9 else t for t in out.index])
    out = out[(out.index.hour * 60 + out.index.minute) >= 570]       # solo sesion regular
    return out.dropna()


def add_features(h, d1):
    """h: velas alineadas; d1: diario (Open High Low Close). Contexto diario = dias COMPLETOS anteriores."""
    h = h.copy()
    h["date"] = h.index.date
    h["slot"] = h.groupby("date").cumcount()                          # 0 = 9:30-10:00
    start_min = h.index.hour * 60 + h.index.minute
    h["end_min"] = np.where(h["slot"] == 0, start_min + 30, start_min + 60)
    for n in (10, 20, 40, 100, 200):
        h[f"PM{n}"] = h["Close"].rolling(n).mean()
    d = d1.copy()
    d.index = pd.DatetimeIndex(d.index).tz_localize(None).normalize()
    d["sma100"] = d["Close"].rolling(100).mean()
    d["sma200"] = d["Close"].rolling(200).mean()
    d["sma20"] = d["Close"].rolling(20).mean()
    d["low60"] = d["Low"].rolling(60).min()
    d["drop3"] = ((d["Close"] < d["Close"].shift(1)) & (d["Close"].shift(1) < d["Close"].shift(2)) &
                  (d["Close"].shift(2) < d["Close"].shift(3)))
    prev = d[["Close", "sma100", "sma200", "sma20", "low60", "drop3"]].shift(1)
    prev.columns = ["d_close", "d_sma100", "d_sma200", "d_sma20", "d_low60", "d_drops3"]
    prev.index = prev.index.date
    for c in prev.columns:
        h[c] = h["date"].map(prev[c])
    h["d_drops3"] = h["d_drops3"].fillna(False).astype(bool)
    h["d_trend"] = h["d_close"] > h["d_sma100"]
    near = lambda a, b: (a - b).abs() / b < 0.02
    h["d_floor"] = near(h["d_close"], h["d_sma100"]) | near(h["d_close"], h["d_sma200"]) | near(h["d_close"], h["d_low60"])
    # velas
    rng = h["High"] - h["Low"]
    body = (h["Close"] - h["Open"]).abs()
    h["green"], h["red"] = h["Close"] > h["Open"], h["Close"] < h["Open"]
    h["solid_green"] = h["green"] & (body > 0.6 * rng)
    h["solid_red"] = h["red"] & (body > 0.6 * rng)
    h["hammer"] = h["green"] & ((h["Open"] - h["Low"]) > 2 * body) & ((h["High"] - h["Close"]) < 0.2 * body)
    up_wick = h["High"] - np.maximum(h["Open"], h["Close"])
    h["hanger_like"] = (rng > 0) & (up_wick >= 0.45 * rng) & (body <= 0.4 * rng)   # filtro del bot para PM40
    # gap y primera vela del dia
    first = h[h["slot"] == 0].set_index("date")
    prev_close = d["Close"].shift(1)
    prev_close.index = prev_close.index.date
    h["day_open"] = h["date"].map(first["Open"])
    h["first_low"] = h["date"].map(first["Low"])
    h["first_green"] = h["date"].map(first["green"]).astype(bool)
    h["gap"] = (h["day_open"] - h["date"].map(prev_close)) / h["date"].map(prev_close) * 100
    h["first_vol"] = h["date"].map(first["Volume"])
    return h


# ---------------------------------------------------------------- lineas de tendencia
def _pivots(arr, hi, kind, k):
    """Indices j (en [lo..hi-k]) que son pivote: extremo unico de su ventana +-k. Se conocen en j+k <= hi."""
    out = []
    for j in range(max(k, 0), hi - k + 1):
        w = arr[j - k:j + k + 1]
        if kind == "high" and arr[j] == w.max() and (w == arr[j]).sum() == 1:
            out.append(j)
        if kind == "low" and arr[j] == w.min() and (w == arr[j]).sum() == 1:
            out.append(j)
    return out


def descending_line(h, i, lookback=60, k=2, min_sep=3):
    """Linea de caida valida en la vela i: por los 2 ultimos maximos pivote confirmados antes de i.
    Devuelve (j1, y1, j2, y2) o None. Valida si ninguna vela cerro por encima de la linea desde j1."""
    hi = i - 1                                    # pivotes confirmados con datos hasta i-1
    lo = max(0, i - lookback)
    H, C = h["High"].values, h["Close"].values
    piv = [j for j in _pivots(H[:hi + 1], hi, "high", k) if j >= lo]
    for b in range(len(piv) - 1, 0, -1):
        for a in range(b - 1, -1, -1):
            j1, j2 = piv[a], piv[b]
            if j2 - j1 >= min_sep and H[j2] < H[j1]:
                slope = (H[j2] - H[j1]) / (j2 - j1)
                ok = all(C[t] <= (H[j1] + slope * (t - j1)) * (1 + TOL) for t in range(j1, hi + 1))
                if ok:
                    return j1, H[j1], j2, H[j2]
        break
    return None


def ascending_line(h, i, lookback=60, k=2, min_sep=3):
    """Linea de piso por los 2 ultimos minimos pivote ascendentes confirmados antes de i."""
    hi = i - 1
    lo = max(0, i - lookback)
    L, C = h["Low"].values, h["Close"].values
    piv = [j for j in _pivots(L[:hi + 1], hi, "low", k) if j >= lo]
    for b in range(len(piv) - 1, 0, -1):
        for a in range(b - 1, -1, -1):
            j1, j2 = piv[a], piv[b]
            if j2 - j1 >= min_sep and L[j2] > L[j1]:
                slope = (L[j2] - L[j1]) / (j2 - j1)
                ok = all(C[t] >= (L[j1] + slope * (t - j1)) * (1 - TOL) for t in range(j1, hi + 1))
                if ok:
                    return j1, L[j1], j2, L[j2]
        break
    return None


def line_at(line, x):
    j1, y1, j2, y2 = line
    return y1 + (y2 - y1) / (j2 - j1) * (x - j1)


# ---------------------------------------------------------------- evaluacion (sin futuro)
def evaluate_bar(h, i):
    """Devuelve {strategy_id: detalle} de las estrategias que se cumplen al CIERRE de la vela i."""
    r = h.iloc[i]
    hh = h.iloc[:i + 1]                                   # nada posterior a i
    sig = {}
    after_11 = r.end_min >= 11 * 60
    n = len(hh)

    def broke_down_line(idx, lookback=60):
        ln = descending_line(hh, idx, lookback)
        if ln and hh["Close"].iloc[idx] > line_at(ln, idx):
            return ln
        return None

    # --- GAP NORMAL / GAP BAJISTA (2a vela = 10:00-11:00, se compra a las 11:00)
    if r.slot == 1:
        if r.gap > GAP_MIN and r.first_green and r.green and not r.hammer and r.d_trend:
            sig["GAP_NORMAL"] = {"gap": round(r.gap, 2), "cerca_pm40": bool(abs(r.Close - r.PM40) / r.Close < 0.01)}
        if r.gap < -GAP_MIN and r.first_green and r.green:
            sig["GAP_BAJISTA"] = {"gap": round(r.gap, 2)}
    # --- PRIMERA VELA ROJA (unica que se compra a las 10:00)
    if r.slot == 0 and r.solid_red:
        fv = hh[hh["slot"] == 0]["Volume"].iloc[-11:-1]          # primeras velas de los 10 dias previos
        vol_ok = len(fv) >= 3 and r.Volume > fv.mean()
        canal = (r.PM20 < r.PM40) or abs(r.Close - r.PM40) / r.PM40 < 0.02 or abs(r.Close - r.PM200) / r.PM200 < 0.02
        if vol_ok and canal:
            sig["VELA_ROJA"] = {"vol_rel": round(float(r.Volume / fv.mean()), 2)}
    if not after_11 or n < 60:
        return sig
    # --- CAIDA NORMAL / FUERTE y PISO FUERTE: linea de caida rota por vela verde solida
    ln = broke_down_line(i)
    if ln and r.solid_green:
        j1 = ln[0]
        peak = hh["High"].iloc[j1:i].max()
        drop = (peak - hh["Low"].iloc[j1:i + 1].min()) / peak * 100
        if r.d_trend and CAIDA_MIN <= drop <= CAIDA_FUERTE:
            sig["CAIDA_NORMAL"] = {"caida_%": round(drop, 2)}
        if r.d_trend and drop > CAIDA_FUERTE:
            sig["CAIDA_FUERTE"] = {"caida_%": round(drop, 2)}
        if r.d_sma100 > r.d_sma200 and r.d_floor and drop >= CAIDA_MIN and r.Close > r.day_open:
            sig["PISO_FUERTE"] = {"caida_%": round(drop, 2), "vela_dia_verde": True}
    # --- PM40: 20 sobre 40, caida, toque de la 40, ruptura de linea con vela solida/martillo (no hanger)
    # (portal Meliora, criterios 3-5): en HORA PM20>PM40 y PM100>PM200 "en paralelo, sin tocarse";
    # las velas rojas finales de la caida rompen PM20 y tocan/rompen parcialmente PM40; la vela verde FINAL
    # rompe PM20 y la linea de caida; se compra solo con vela final entre 11:00 y 15:59.
    ln30 = descending_line(hh, i, 30)
    sin_tocarse = (hh["PM20"].iloc[-10:] > hh["PM40"].iloc[-10:]).all() and (hh["PM100"].iloc[-10:] > hh["PM200"].iloc[-10:]).all()
    rompe_pm20 = r.Close > r.PM20 and (hh["Close"].iloc[-5:-1] < hh["PM20"].iloc[-5:-1]).any()
    if ln30 and sin_tocarse and rompe_pm20 and r.end_min <= 16 * 60 and (r.solid_green or r.hammer) \
            and not r.hanger_like and r.Close > line_at(ln30, i):
        w = hh.iloc[-4:]
        touched = ((w["Low"] <= w["PM40"] * 1.0015) & (w["Close"] >= w["PM40"] * 0.9985)).any()
        peak = hh["High"].iloc[ln30[0]:i].max()
        if touched and (peak - hh["Low"].iloc[ln30[0]:i + 1].min()) / peak * 100 >= CAIDA_MIN:
            sig["PM40_BOUNCE"] = {"pm20_sobre_pm40": True}
    # --- RUPTURA DE CANAL BAJISTA: ruptura (vela i-1) + 2a vela de confirmacion verde (vela i)
    if r.PM20 < r.PM40 and r.green:
        lc = descending_line(hh, i - 1, 140, k=3, min_sep=10)
        if lc and hh["Close"].iloc[i - 1] > line_at(lc, i - 1) and hh["solid_green"].iloc[i - 1] and r.Close > line_at(lc, i):
            sig["CANAL_BREAK"] = {"techo_en_velas": i - lc[0]}
    # --- RUPTURA DEL PISO DEL GAP (PUT): 1a vela verde, piso = minimo de la 1a vela
    if r.slot >= 1 and r.first_green and r.solid_red and r.Close < r.first_low <= hh["Close"].iloc[i - 1] \
            and r.Close > r.PM40 and not r.d_drops3:
        sig["RUPTURA_PISO"] = {"piso_gap": round(float(r.first_low), 2)}
    # --- 4 PASOS (PUT): canal bajista, zona de techo, verde->rojo que la borra, ruptura de la linea de piso
    if r.PM20 < r.PM40 and r.red and hh["green"].iloc[i - 1] and r.Close < hh["Open"].iloc[i - 1]:
        lt = descending_line(hh, i - 1, 80)
        la = ascending_line(hh, i, 30)
        if lt and la and hh["High"].iloc[i - 1] >= line_at(lt, i - 1) * 0.995 and r.Close < line_at(la, i):
            sig["4_PASOS"] = {"techo": round(float(line_at(lt, i - 1)), 2)}
    return sig


def scan_history(h, start=60):
    """Todas las senales de la historia (para backtest/replay). Cada fila = una senal conocida al cierre."""
    rows = []
    for i in range(start, len(h)):
        for sid, det in evaluate_bar(h, i).items():
            rows.append({"time": h.index[i], "end": h.index[i] + pd.Timedelta(minutes=30 if h["slot"].iloc[i] == 0 else 60),
                         "strategy": sid, "close": float(h["Close"].iloc[i]), **det})
    return pd.DataFrame(rows)

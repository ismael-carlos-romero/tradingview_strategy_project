"""Aula Virtual - datos: universo vigente, cache local de velas, construccion de velas Cardona y calidad.
Proveedor: Yahoo Finance (yfinance). Zona: America/New_York. Velas 30m (max ~60 dias) -> velas Cardona (9:30-10:00 y 10:00-11:00 ...).
El cache es ACUMULATIVO: cada refresco agrega velas nuevas al archivo, asi la historia exacta crece con el tiempo."""
import os, sys, re, ast, json, time
import numpy as np, pandas as pd

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
for _p in (RAIZ, os.path.join(RAIZ, "fichas_cardona")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import cardona_rules as cr
import atlas_motor as am

NY = "America/New_York"
CACHE = os.path.join(AQUI, "cache")
os.makedirs(CACHE, exist_ok=True)
META = os.path.join(CACHE, "meta.json")
PROVEEDOR = "Yahoo Finance (yfinance)"
FIN_SESION = [600, 660, 720, 780, 840, 900, 960]   # fin de cada vela Cardona de una sesion completa (NY)
MIN_BARS = 215                                     # PM200 hora disponible
LIQ_MIN_USD = 20e6                                 # volumen diario medio en USD (20 ruedas) para ser seleccionable
_mem = {}


def universo():
    """Lista vigente de activos: TICKERS de live_scanner.py (configuracion del bot). Se contrasta con Atlas vivo."""
    src = open(os.path.join(RAIZ, "live_scanner.py"), encoding="utf-8", errors="ignore").read()
    m = re.search(r"^TICKERS\s*=\s*(\[.*?\])", src, re.S | re.M)
    bot = sorted(ast.literal_eval(m.group(1)))
    av = open(os.path.join(RAIZ, "fichas_cardona", "atlas_vivo.py"), encoding="utf-8", errors="ignore").read()
    m2 = re.search(r'^TICKERS\s*=\s*"([^"]+)"', av, re.M)
    atlas = sorted(m2.group(1).split()) if m2 else []
    return {"tickers": bot, "n": len(bot), "fuente": "live_scanner.py TICKERS", "atlas_n": len(atlas),
            "solo_bot": sorted(set(bot) - set(atlas)), "solo_atlas": sorted(set(atlas) - set(bot))}


def _meta():
    try:
        return json.load(open(META, encoding="utf-8"))
    except Exception:
        return {}


def _p(t, k):
    return os.path.join(CACHE, f"{t}_{k}.csv")


def _norm(df):
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy(); df.columns = df.columns.get_level_values(0)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


def refrescar(tickers=None, log=print):
    """Descarga 30m (60d) y diario (2y) de Yahoo y los fusiona con el cache (acumulativo). Devuelve resumen."""
    import yfinance as yf
    tickers = tickers or universo()["tickers"]
    meta = _meta(); res = {"ok": [], "error": {}}
    d30 = yf.download(tickers, period="60d", interval="30m", prepost=False, progress=False, auto_adjust=False, group_by="ticker", threads=True)
    d1 = yf.download(tickers, period="2y", interval="1d", progress=False, auto_adjust=False, group_by="ticker", threads=True)
    for t in tickers:
        try:
            a = _norm(d30[t] if len(tickers) > 1 else d30); b = _norm(d1[t] if len(tickers) > 1 else d1)
            if a.empty and not os.path.exists(_p(t, "30m")):
                res["error"][t] = "Sin datos del proveedor (posible deslistado o cambio de ticker)"; continue
            a.index = pd.DatetimeIndex(a.index).tz_convert(NY) if a.index.tz is not None else pd.DatetimeIndex(a.index).tz_localize("UTC").tz_convert(NY)
            b.index = pd.DatetimeIndex(b.index).tz_localize(None).normalize()
            if os.path.exists(_p(t, "30m")):
                o = _load30(t); a = pd.concat([o, a[~a.index.isin(o.index)]]).sort_index()
                a.update(a)  # no-op: conserva historia previa
            if os.path.exists(_p(t, "1d")):
                o = _load1d(t); b = pd.concat([o[~o.index.isin(b.index)], b]).sort_index()
            a.index = a.index.map(lambda x: x.isoformat()); a.to_csv(_p(t, "30m"))
            b.index = b.index.strftime("%Y-%m-%d"); b.to_csv(_p(t, "1d"))
            meta[t] = {"fetched_at": pd.Timestamp.now(tz="UTC").isoformat(), "n30": len(a), "n1d": len(b), "proveedor": PROVEEDOR}
            res["ok"].append(t)
        except Exception as e:
            res["error"][t] = str(e)[:120]
    json.dump(meta, open(META, "w", encoding="utf-8"))
    _mem.clear()
    return res


def _load30(t):
    d = pd.read_csv(_p(t, "30m"), index_col=0)
    d.index = pd.to_datetime(d.index, utc=True).tz_convert(NY)
    return d


def _load1d(t):
    d = pd.read_csv(_p(t, "1d"), index_col=0)
    d.index = pd.DatetimeIndex(pd.to_datetime(d.index)).normalize()
    return d


def _feat(d30, d1, now=None):
    h = cr.add_features(cr.build_cardona_bars(d30, now=now), d1)
    h["rvol"] = h.Volume / h.groupby("slot").Volume.transform(lambda s: s.rolling(20, min_periods=5).mean().shift(1))
    return h


def preparado(t):
    """Velas Cardona con features + diario, calculados UNA vez. Las features son causales (cada vela solo usa pasado)."""
    f = _p(t, "30m")
    if not os.path.exists(f):
        return None
    mt = os.path.getmtime(f)
    if t in _mem and _mem[t]["mt"] == mt:
        return _mem[t]
    d30, d1 = _load30(t), _load1d(t)
    h = _feat(d30, d1, now=d30.index.max() + pd.Timedelta(hours=1))
    D = am.daily(d1)
    ok_dia = {}
    for dia, g in h.groupby("date"):
        ok_dia[dia] = list(g.end_min.astype(int)) == FIN_SESION[:len(g)] and g.Volume.gt(0).all()
    h["dia_ok"] = h["date"].map(ok_dia).astype(bool)
    dv = (d1.Close * d1.Volume).rolling(20).mean()
    _mem[t] = {"mt": mt, "h": h, "D": D, "d1": d1, "d30": d30, "dvol": dv, "ok_dia": ok_dia}
    return _mem[t]


def preparar_corte(t, corte):
    """Reconstruye TODO con datos hasta 'corte' (sin velas futuras). Sirve para auditar que no hay fuga de futuro."""
    corte = pd.Timestamp(corte); corte = corte.tz_localize(NY) if corte.tzinfo is None else corte.tz_convert(NY)
    d30, d1 = _load30(t), _load1d(t)
    d30 = d30[d30.index + pd.Timedelta(minutes=30) <= corte]
    cerrado = corte.hour * 60 + corte.minute >= 960
    lim = pd.Timestamp(corte.date()) if cerrado else pd.Timestamp(corte.date()) - pd.Timedelta(days=1)
    d1 = d1[d1.index <= lim]
    h = _feat(d30, d1, now=corte)
    return h, am.daily(d1)


def hora_ny_str(ts):
    return pd.Timestamp(ts).tz_convert(NY).strftime("%Y-%m-%d %H:%M") if pd.Timestamp(ts).tzinfo else str(ts)[:16]


def estado(t):
    """Proveedor, zona, intervalo efectivo, ultima vela, antiguedad, suficiencia y liquidez."""
    p = preparado(t); meta = _meta().get(t, {})
    if p is None or len(p["h"]) == 0:
        return {"ticker": t, "suficiente": False, "motivo": "sin datos en cache (ejecutar refresco)", "proveedor": PROVEEDOR, "zona": NY}
    h = p["h"]; fin = h.index[-1] + pd.Timedelta(minutes=30 if h.slot.iloc[-1] == 0 else 60)
    ahora = pd.Timestamp.now(tz=NY)
    ok = int(h.PM200.notna().sum())
    liq = float(p["dvol"].iloc[-1]) if len(p["dvol"]) and p["dvol"].iloc[-1] == p["dvol"].iloc[-1] else 0.0
    suf = ok >= 30 and liq >= LIQ_MIN_USD
    motivo = "" if suf else ("liquidez insuficiente (< 20 M USD/día)" if liq < LIQ_MIN_USD else "pocas velas con PM200 (< 30)")
    return {"ticker": t, "proveedor": PROVEEDOR, "zona": NY, "intervalo_efectivo": "30m → velas Cardona (9:30-10:00 y horarias)",
            "n_velas": int(len(h)), "n_evaluables": ok, "primera": str(h.index[0])[:16], "ultima_vela": str(h.index[-1])[:16],
            "ultima_vela_cierra": str(fin)[:16], "antiguedad_h": round((ahora - fin).total_seconds() / 3600, 1),
            "liquidez_usd_dia": round(liq), "dias_incompletos": int(sum(1 for v in p["ok_dia"].values() if not v)),
            "suficiente": bool(suf), "motivo": motivo, "actualizado": meta.get("fetched_at", "")}


def estado_sesion(t):
    """Estado de la ultima vela para la practica de la sesion actual: cerrada / en formacion / retrasada (reloj vs vela)."""
    ahora = pd.Timestamp.now(tz=NY); e = estado(t)
    if "ultima_vela" not in e:
        return e
    fin = pd.Timestamp(e["ultima_vela_cierra"], tz=NY)
    ab = ahora.weekday() < 5 and 570 <= ahora.hour * 60 + ahora.minute < 960
    if ab and (ahora - fin) > pd.Timedelta(minutes=75):
        est = "retrasada"
    elif ab:
        est = "en_formacion_siguiente_abierta"
    else:
        est = "mercado_cerrado_ultima_vela_cerrada"
    return dict(e, reloj_portal=ahora.strftime("%Y-%m-%d %H:%M %Z"), estado_vela=est, mercado_abierto=bool(ab))


def sesiones_con_datos(t):
    p = preparado(t)
    return sorted(p["ok_dia"]) if p else []

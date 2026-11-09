"""Aula Virtual - motor: evalua las 12 estrategias en un CORTE (usa Atlas como candidato), construye el indice de casos
y arma la evidencia (snapshot) que ve el alumno. Nada posterior al corte entra en la evidencia ni en la referencia."""
import os, sys, json, hashlib, math
import numpy as np, pandas as pd
from . import datos, definiciones as df
import atlas_estrategias as ae
import atlas_motor as am

REG = {k: f for k, _, f, _ in ae.REGISTRO}
VER_ATLAS = am.VERSION
INDICE = os.path.join(datos.CACHE, "indice.json")
NIVEL_REF = "atlas_automatico"   # nivel de validacion de la referencia: candidato Atlas, sin revision humana
CLASES = {"CONFIRMADA": "CONFIRMADA", "CONFIRMADA_FUERA_DE_HORARIO": "AMBIGUA", "CASI": "EN_FORMACION", "VIGILANCIA": "EN_FORMACION", "SIN_CONTEXTO": "NO_APLICA"}


def _num(v):
    try:
        v = float(v)
        return None if math.isnan(v) or math.isinf(v) else round(v, 4)
    except Exception:
        return None


def clase(etapa):
    return CLASES.get(etapa, "SIN_DATOS")


def evaluar_corte(h, D, i, sid):
    """Atlas sobre la vela i usando SOLO h[:i+1]. Devuelve dict normalizado (con lineas en tiempo/precio)."""
    x = am.contexto(h.iloc[:i + 1], D)
    r = REG[sid](x)
    draws = []
    for d in r.get("draw", []):
        if "p" in d:
            j1, y1, j2, y2 = d["p"]
            draws.append({"tipo": "linea", "k": d["k"], "t1": h.index[int(j1)].isoformat(), "p1": _num(y1), "t2": h.index[min(int(j2), i)].isoformat(), "p2": _num(y2),
                          "j1": int(j1), "j2": int(j2)})
        else:
            draws.append({"tipo": "horizontal", "k": d["k"], "t1": h.index[max(0, min(int(d.get("j", 0)), i))].isoformat(), "p1": _num(d["y"]), "j1": int(d.get("j", 0))})
    return {"etapa": r["etapa"], "clase": clase(r["etapa"]), "dir": r["dir"], "ventana": r["ventana"], "ventana_ok": bool(r["ventana_ok"]),
            "pasos": [{"n": p["n"], "ok": p["ok"], "d": p["d"]} for p in r["pasos"]], "draw": draws, "nota": r.get("nota", "")}


def bits(r):
    return "".join("1" if p["ok"] is True else ("-" if p["ok"] is None else "0") for p in r["pasos"])


def _corte_ok(h):
    esp = h.slot.map(lambda s: df_fin(s))
    ok = (h.end_min.astype(int) == esp).astype(int)
    return ok.groupby(h["date"]).cummin().astype(bool)


def df_fin(s):
    return datos.FIN_SESION[int(s)] if int(s) < len(datos.FIN_SESION) else -1


def _worker(t):
    p = datos.preparado(t)
    if p is None or len(p["h"]) == 0:
        return t, []
    h, D = p["h"], p["D"]; ok = _corte_ok(h).values
    out = []
    for i in range(datos.MIN_BARS, len(h)):
        if not ok[i] or h.PM200.iloc[i] != h.PM200.iloc[i]:
            continue
        for sid in df.ORDEN:
            try:
                r = evaluar_corte(h, D, i, sid)
                out.append([t, h.index[i].isoformat(), sid, r["etapa"], int(r["ventana_ok"]), bits(r)])
            except Exception as e:
                out.append([t, h.index[i].isoformat(), sid, "ERROR", 0, str(e)[:40]])
    return t, out


def construir_indice(tickers=None, workers=8, log=print):
    from multiprocessing import Pool
    tickers = tickers or [t for t in datos.universo()["tickers"] if os.path.exists(datos._p(t, "30m"))]
    filas = []
    with Pool(workers) as pool:
        for t, o in pool.imap_unordered(_worker, tickers):
            filas += o; log(f"  {t}: {len(o)} evaluaciones")
    meta = {"construido": pd.Timestamp.now(tz="UTC").isoformat(), "atlas": VER_ATLAS, "definiciones": df.VERSION, "n": len(filas),
            "datos": {t: datos._meta().get(t, {}).get("fetched_at", "") for t in tickers}}
    json.dump({"meta": meta, "filas": filas}, open(INDICE, "w", encoding="utf-8"), separators=(",", ":"))
    return meta


_idx = {}


def indice():
    if not os.path.exists(INDICE):
        return None
    mt = os.path.getmtime(INDICE)
    if _idx.get("mt") != mt:
        d = json.load(open(INDICE, encoding="utf-8"))
        _idx.update(mt=mt, meta=d["meta"], filas=d["filas"])
    return _idx


# ------------------------------------------------------------------ evidencia (snapshot al corte)
def _barras(h, n):
    x = h.iloc[-n:]
    return [{"t": ts.isoformat(), "e": int(r.end_min), "o": _num(r.Open), "h": _num(r.High), "l": _num(r.Low), "c": _num(r.Close), "v": int(r.Volume),
             "pm20": _num(r.PM20), "pm40": _num(r.PM40), "pm100": _num(r.PM100), "pm200": _num(r.PM200)} for ts, r in x.iterrows()]


def snapshot(t, corte_iso, n_hora=130, n_30=160, n_dia=140):
    """Evidencia disponible al corte: 3 temporalidades. NO incluye nada posterior."""
    p = datos.preparado(t)
    h, D, d30 = p["h"], p["D"], p["d30"]
    corte = pd.Timestamp(corte_iso)
    i = int(h.index.get_loc(corte))
    hh = h.iloc[:i + 1]
    fin = corte + pd.Timedelta(minutes=30 if hh.slot.iloc[-1] == 0 else 60)
    s30 = d30[d30.index + pd.Timedelta(minutes=30) <= fin].iloc[-n_30:]
    c30 = s30.Close
    b30 = [{"t": ts.isoformat(), "o": _num(r.Open), "h": _num(r.High), "l": _num(r.Low), "c": _num(r.Close), "v": int(r.Volume),
            "pm20": _num(c30.rolling(20).mean().get(ts)), "pm40": _num(c30.rolling(40).mean().get(ts))} for ts, r in s30.iterrows()]
    cerrado = int(hh.end_min.iloc[-1]) >= 960
    lim = pd.Timestamp(corte.date()) if cerrado else pd.Timestamp(corte.date()) - pd.Timedelta(days=1)
    Dd = D[D.index <= lim].iloc[-n_dia:]
    d40 = D.Close.rolling(40).mean()
    bd = [{"t": ts.strftime("%Y-%m-%d"), "o": _num(r.Open), "h": _num(r.High), "l": _num(r.Low), "c": _num(r.Close), "v": int(r.Volume),
           "pm20": _num(r.sma20), "pm40": _num(d40.get(ts)), "pm100": _num(r.sma100), "pm200": _num(r.sma200)} for ts, r in Dd.iterrows()]
    snap = {"ticker": t, "corte": corte.isoformat(), "corte_cierra": fin.isoformat(), "hora": _barras(hh, n_hora), "m30": b30, "diario": bd,
            "fuente": {"proveedor": datos.PROVEEDOR, "zona": datos.NY, "intervalo": "30m→Cardona", "ultima_vela": corte.isoformat(),
                       "dias_incompletos_en_ventana": int(sum(1 for d_, v in p["ok_dia"].items() if not v and d_ >= hh.index[max(0, i - 130)].date()))}}
    snap["hash"] = hashlib.sha256(json.dumps([snap["hora"], snap["m30"], snap["diario"], df.VERSION, VER_ATLAS], sort_keys=True).encode()).hexdigest()[:20]
    return snap


def barras_posteriores(t, corte_iso, n=14):
    """Velas HORA posteriores al corte (solo para el analisis posterior, nunca para puntuar)."""
    p = datos.preparado(t); h = p["h"]; corte = pd.Timestamp(corte_iso)
    i = int(h.index.get_loc(corte))
    return _barras(h.iloc[i + 1:i + 1 + n], n) if i + 1 < len(h) else []


def referencia(t, corte_iso, sid=None):
    """Referencia Atlas en el corte: para sid o para las 12 estrategias."""
    p = datos.preparado(t); h, D = p["h"], p["D"]
    i = int(h.index.get_loc(pd.Timestamp(corte_iso)))
    ids = [sid] if sid else df.ORDEN
    return {s: evaluar_corte(h, D, i, s) for s in ids}


def estado_calidad(t, corte_iso):
    p = datos.preparado(t); h = p["h"]; i = int(h.index.get_loc(pd.Timestamp(corte_iso)))
    return {"corte_contiguo": bool(_corte_ok(h).iloc[i]), "pm200": bool(h.PM200.iloc[i] == h.PM200.iloc[i]), "volumen_cero": bool(h.Volume.iloc[i] == 0)}

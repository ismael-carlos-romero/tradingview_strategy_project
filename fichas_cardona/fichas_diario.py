"""Análisis diario de los 35 activos (SOLO ANÁLISIS: no compra, no vende, no toca el bot).
Uso:  python fichas_diario.py [pre|post]      (sin argumento: según la hora de Nueva York)
Salida en informes\\AAAA-MM-DD_pre|post\\ :
  resumen.json / resumen.csv   -> una fila por activo (señales del motor, canales, zona cara/barata, estado de datos)
  informe.html                 -> tabla para leer en PC o celular
  meliora_fichas_cardona.pine  -> Pine con los datos de los 35 activos ya cargados (pegar en el editor de TradingView)
Reglas: cardona_rules.py (velas alineadas 9:30-10:00, 10:00-11:00..., pivotes confirmados, sin futuro).
Los canales y las señales de motor salen PENDIENTE: las líneas aún no están validadas por Ismael."""
import csv, json, os, sys, html
from datetime import datetime
import numpy as np, pandas as pd, yfinance as yf

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(AQUI)
sys.path.insert(0, BASE)
import cardona_rules as cr
sys.path.insert(0, AQUI)
from techo_piso import techo_piso

TICKERS = "AAPL AMD AMZN AXON BAC BLK C COIN CVX DIS EA EBAY GLD GOOG GOOGL HPE META MRNA MSCI MSFT NDAQ NFLX NVDA ORCL PLTR PYPL QQQ SLV SPY TNA TSLA UBER USO VLO XOM".split()
MAX_EDAD_MIN = 4320            # datos más viejos que 3 días = No evaluable (ej. EA)
CRIT = "2 pivotes confirmados (cardona_rules); paralela por el extremo opuesto; PENDIENTE de validar"
ms = lambda ts: int(pd.Timestamp(ts).timestamp() * 1000)


def cargar(t):
    m30 = yf.download(t, period="60d", interval="30m", prepost=True, progress=False, auto_adjust=False)
    d1 = yf.download(t, period="2y", interval="1d", progress=False, auto_adjust=False)
    for df in (m30, d1):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    if m30.empty or d1.empty:
        raise ValueError("sin datos de yfinance")
    idx = m30.index.tz_convert(cr.NY) if m30.index.tz else m30.index.tz_localize("UTC").tz_convert(cr.NY)
    m30.index = idx
    mins = idx.hour * 60 + idx.minute
    reg = m30[(mins >= 570) & (mins < 960)]
    pre = m30[mins < 570]
    h = cr.add_features(cr.build_cardona_bars(reg, now=None), d1)
    return h, (float(pre["Close"].iloc[-1]) if len(pre) and pre.index[-1].date() == pd.Timestamp.now(tz=cr.NY).date() else None)


def analizar(t, ahora):
    f = {"ticker": t, "estado_datos": "OK", "senales_motor": "", "zona": "", "filas_pine": []}
    try:
        h, pre = cargar(t)
        n = len(h)
        ult = h.index[-1]
        edad = (ahora - ult).total_seconds() / 60
        f["ultima_vela"] = str(ult)
        f["edad_min"] = round(edad)
        f["cierre"] = round(float(h["Close"].iloc[-1]), 2)
        f["premercado"] = round(pre, 2) if pre else None
        if edad > MAX_EDAD_MIN:
            f["estado_datos"] = f"NO EVALUABLE: último dato hace {round(edad/1440,1)} días"
            return f
        r = h.iloc[-1]
        sig = cr.evaluate_bar(h, n - 1)
        f["senales_motor"] = ", ".join(f"{k}" for k in sig)
        for k in sig:
            dire = "PUT" if k in ("RUPTURA_PISO", "4_PASOS") else "CALL"
            f["filas_pine"].append(f"M|{t}|{k}|{dire}|EN_FORMACION|{ms(ult)}|{round(float(r.Close),2)}|senal del motor (no es ficha validada)")
        pms = [float(r[f"PM{x}"]) for x in (10, 20, 40, 100, 200)]
        if not any(np.isnan(pms)):
            arriba = sum(float(r.Close) > p for p in pms)
            f["zona"] = "CARA" if float(r.Close) > max(pms) else "BARATA"
            f["pm_bajo_precio"] = f"{arriba}/5"
            f["zona_estricta"] = "CARA" if float(r.Close) > max(pms) else ("BARATA" if float(r.Low) <= min(pms) else "NEUTRA")
        f.update(techo_piso(h, ahora))
        f["_h"] = h
    except Exception as e:
        f["estado_datos"] = f"ERROR: {str(e)[:80]}"
    return f




def trozos(filas, lim=3800):
    out, cur = [], ""
    for r in filas:
        if len(cur) + len(r) + 1 > lim:
            out.append(cur)
            cur = ""
        cur += (("\\n" if cur else "") + r)
    out.append(cur)
    return out


def main():
    ahora = pd.Timestamp.now(tz=cr.NY)
    corte = sys.argv[1] if len(sys.argv) > 1 else ("pre" if ahora.hour * 60 + ahora.minute < 570 else "post")
    carpeta = os.path.join(AQUI, "informes", f"{ahora:%Y-%m-%d}_{corte}")
    os.makedirs(carpeta, exist_ok=True)
    res = []
    for t in TICKERS:
        res.append(analizar(t, ahora))
        print(t, res[-1]["estado_datos"], res[-1]["senales_motor"], res[-1]["zona"])
    filas = [r for f in res for r in f["filas_pine"]]
    import shutil
    shutil.copy(os.path.join(AQUI, "meliora_fichas_cardona_v6.pine"), os.path.join(carpeta, "meliora_fichas_cardona.pine"))
    cols = ["ticker", "estado_datos", "ultima_vela", "edad_min", "cierre", "premercado", "zona", "zona_estricta", "pm_bajo_precio", "senales_motor", "ruptura", "techo_proy", "dist_techo_pct", "piso_proy", "dist_piso_pct", "caso", "ancla_techo", "ancla_piso", "ruptura_hora"]
    with open(os.path.join(carpeta, "resumen.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(res)
    json.dump([{k: v for k, v in r.items() if k not in ("filas_pine", "geo") and not k.startswith("_")} for r in res], open(os.path.join(carpeta, "resumen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    celdas = lambda r: "".join(f"<td>{html.escape(str(r.get(c, '') or ''))}</td>" for c in cols)
    cls = lambda r: ' class="no"' if r["estado_datos"] != "OK" else (' class="sg"' if r["senales_motor"] else "")
    tabla = "".join(f"<tr{cls(r)}>{celdas(r)}</tr>" for r in res)
    n_ok = sum(r["estado_datos"] == "OK" for r in res)
    n_sig = sum(bool(r["senales_motor"]) for r in res)
    doc = f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fichas Cardona · {ahora:%Y-%m-%d} {corte}mercado</title><style>body{{font:14px system-ui;margin:12px;background:#f6f7f8;color:#1b2127}}table{{border-collapse:collapse;width:100%;min-width:900px;background:#fff}}
th,td{{border:1px solid #d9dee3;padding:5px 7px;text-align:left}}th{{background:#e9edf0}}tr.no td{{color:#999;background:#f0f0f0}}tr.sg td{{background:#fff7e0}}.w{{overflow-x:auto}}.n{{background:#3b2f00;color:#facc15;padding:8px 12px;border-radius:8px}}</style></head><body>
<h2>Fichas Cardona · {ahora:%d/%m/%Y %H:%M} ET · {corte}mercado</h2>
<p class="n">Solo análisis (sin órdenes). Señales de motor = lo que detectan las reglas de Cardona sobre la última vela cerrada; <b>no son fichas confirmadas</b>. TECHO/PISO estilo Ismael (ventana 5 sesiones, velas alineadas Cardona; proyectados a la vela de las 10:30 ET de mañana): CALL = vela verde que cierra sobre el techo, PUT = vela roja que cierra bajo el piso; SIN_PIVOTE = no calculable. Zona cara/barata: criterio del botón «Zona de Techo y Piso» (cara = precio sobre las 5 PM; barata = toca o está bajo alguna), informativa; a mano: cara → PUT, barata → CALL.</p>
<p>Evaluados: {n_ok}/{len(res)} · con señal de motor: {n_sig} · fuente: yfinance 30m (premercado incluido), velas alineadas Cardona.</p>
<div class="w"><table><tr>{''.join(f'<th>{c}</th>' for c in cols)}</tr>{tabla}</table></div></body></html>"""
    open(os.path.join(carpeta, "informe.html"), "w", encoding="utf-8").write(doc)
    try:
        from ficha_visual import generar
        print("FICHAS VISUALES:", generar(res, carpeta, ahora, corte))
    except Exception as e:
        print("ficha_visual fallo:", e)
    try:
        from lineas_azules import generar as gla
        print("LINEAS AZULES:", gla(TICKERS, carpeta, ahora, corte)[0])
    except Exception as e:
        print("lineas_azules fallo:", e)
    print(f"\nLISTO: {carpeta}\nevaluados {n_ok}/{len(res)} · con señal {n_sig} · filas Pine {len(filas)}")


if __name__ == "__main__":
    main()

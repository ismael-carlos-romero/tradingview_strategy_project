"""LINEAS DE TENDENCIA AZULES (estilo Ismael) para los 35 activos, 1h (velas 9:30-10:30 como TradingView). SOLO ANALISIS.
Regla (la misma del Pine «Meliora Fichas Cardona»):
  TECHO descendente: 1er ancla = el swing high mas alto de las ultimas MAXB velas; 2do ancla = el ultimo swing high posterior, mas bajo,
     tal que ningun cierre (hasta hoy) quede sobre la linea por mas de TOLP (0,05 %).  PISO ascendente: espejo con swing lows.
  Swing = pivote (4 velas a la izquierda, 3 a la derecha). Se usan MECHAS (high/low) por defecto; `uso="cuerpo"` usa cuerpos.
  La linea NO se mueve con cada vela: conserva anclajes y pendiente y se prolonga. Solo se reemplaza cuando la ROMPE (cierre del otro lado,
  habiendo estado antes del lado contrario). Ruptura confirmada al cierre: techo -> vela VERDE que cierra sobre la linea (CALL);
  piso -> vela ROJA que cierra bajo la linea (PUT). Una mecha que cruza y vuelve no cuenta. Vela en formacion = PROVISIONAL.
  La linea nueva solo puede usar pivotes posteriores a la ruptura. Sin estructura valida = SIN_ESTRUCTURA (no se inventa linea)."""
import base64, csv, io, json, os, sys
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

AQUI = os.path.dirname(os.path.abspath(__file__))
NY = "America/New_York"
PL_, PR_, MAXB, EPS, MAXVIDA = 4, 3, 84, 1e-6, 300
TOLP = 0.0005  # un cierre puede rozar/pasar la linea hasta 0,05 % sin invalidarla (tu SPY: 0,02 %)
MAX_EDAD_MIN = 4320


def barras_1h(df):
    g = df.resample("60min", offset="30min").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last"}).dropna()
    return g


def pivotes(P, modo):
    out = []
    for i in range(PL_, len(P) - PR_):
        izq, der = P[i - PL_:i], P[i + 1:i + PR_ + 1]
        if modo == "max" and P[i] > izq.max() and P[i] >= der.max():
            out.append(i)
        if modo == "min" and P[i] < izq.min() and P[i] <= der.min():
            out.append(i)
    return out


def analizar(h, ahora, uso="mecha"):
    o, hi, lo, c = (h[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(h)
    PH = np.maximum(o, c) if uso == "cuerpo" else hi
    PLo = np.minimum(o, c) if uso == "cuerpo" else lo
    ult = h.index[-1]
    fin = min(ult + pd.Timedelta(minutes=60), ult.normalize() + pd.Timedelta(hours=16))
    n_c = n if ahora >= fin else n - 1
    lados = {"techo": dict(s=1, P=PH, pv=pivotes(PH, "max"), line=None, brk=-1, ev=[], hist=[]),
             "piso": dict(s=-1, P=PLo, pv=pivotes(PLo, "min"), line=None, brk=-1, ev=[], hist=[])}
    lv = lambda ln, t: ln["p1"] + ln["sl"] * (t - ln["i1"])
    for t in range(1, n_c):
        for nom, S in lados.items():
            s, P = S["s"], S["P"]
            ln = S["line"]
            if ln is not None:
                v, vp = lv(ln, t), lv(ln, t - 1)
                if s * (c[t] - v) > TOLP * c[t]:
                    prev_ok = s * (c[t - 1] - vp) <= TOLP * c[t - 1]
                    col = (c[t] > o[t]) if s == 1 else (c[t] < o[t])
                    tipo = ("CALL" if s == 1 else "PUT") if (prev_ok and col) else "INVALIDADA"
                    S["ev"].append(dict(t=t, tipo=tipo, nivel=v, cierre=c[t], linea=nom))
                    S["hist"].append(dict(ln, roto=t))
                    S["line"], S["brk"], ln = None, t, None
                elif t - ln["i1"] > MAXVIDA:
                    S["line"], ln = None, None
                else:
                    # sin ruptura: el 2do ancla avanza al ultimo pivote posterior (mas bajo/alto que el 1ro) si la nueva linea sigue valida
                    for j2 in sorted([j for j in S["pv"] if j + PR_ <= t and j > ln["i2"] and s * P[j] < s * ln["p1"]], reverse=True):
                        sl2 = (P[j2] - ln["p1"]) / (j2 - ln["i1"])
                        if all(s * (c[k] - (ln["p1"] + sl2 * (k - ln["i1"]))) <= TOLP * c[k] for k in range(ln["i1"] + 1, t + 1)):
                            ln.update(i2=j2, p2=float(P[j2]), sl=float(sl2))
                            break
            if ln is None:
                cand = [i for i in S["pv"] if i + PR_ <= t and i > S["brk"] and i >= t - MAXB]
                for i1 in sorted(cand, key=lambda i: (-s * P[i], i)):
                    ok = None
                    for i2 in sorted([j for j in cand if j > i1 and s * P[j] < s * P[i1]], reverse=True):
                        sl = (P[i2] - P[i1]) / (i2 - i1)
                        if all(s * (c[j] - (P[i1] + sl * (j - i1))) <= TOLP * c[j] for j in range(i1 + 1, t + 1)):
                            ok = i2
                            break
                    if ok is not None:
                        i2 = ok
                        S["line"] = dict(i1=i1, p1=float(P[i1]), i2=i2, p2=float(P[i2]), sl=float((P[i2] - P[i1]) / (i2 - i1)), creada=t)
                        break
    left = max(0, int(round((ult.normalize() + pd.Timedelta(hours=15, minutes=30) - ult) / pd.Timedelta(hours=1)))) if ult.hour * 60 + ult.minute <= 930 else 0
    proy = n - 1 + left + 2
    res = {"n": n, "n_c": n_c, "proy_idx": proy, "uso": uso}
    for nom, S in lados.items():
        ln, d = S["line"], {"line": S["line"], "ev": S["ev"], "hist": S["hist"]}
        d["prov"] = ""
        if ln is not None and n_c < n:
            t, s = n - 1, S["s"]
            v, vp = lv(ln, t), lv(ln, t - 1)
            col = (c[t] > o[t]) if s == 1 else (c[t] < o[t])
            if s * (c[t] - v) > TOLP * c[t] and s * (c[t - 1] - vp) <= TOLP * c[t - 1] and col:
                d["prov"] = "PROVISIONAL " + ("CALL" if s == 1 else "PUT")
        if ln is not None:
            d["nivel_prox"] = lv(ln, n_c)
            d["nivel_proy"] = lv(ln, proy)
        res[nom] = d
    return res


def ts(h, i):
    return f"{h.index[i]:%d/%m %H:%M}"


def descr(h, d, uso):
    ln = d["line"]
    if not ln:
        return "SIN_ESTRUCTURA"
    ta = "high" if uso == "mecha" else "cuerpo"
    return f"{ts(h, ln['i1'])} {ln['p1']:.2f} → {ts(h, ln['i2'])} {ln['p2']:.2f}"


def grafico(t, h, r):
    o, hi, lo, c = (h[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n = len(h)
    i0 = max(0, n - 110)
    xe = r["proy_idx"]
    fig, ax = plt.subplots(figsize=(9, 4.4), dpi=90)
    for j in range(i0, n):
        col = "#16a34a" if c[j] >= o[j] else "#dc2626"
        ax.vlines(j, lo[j], hi[j], color=col, lw=1)
        ax.add_patch(Rectangle((j - 0.32, min(o[j], c[j])), 0.64, max(abs(c[j] - o[j]), 1e-9), color=col, zorder=3))
    ymin, ymax = lo[i0:].min(), hi[i0:].max()
    pad = (ymax - ymin) * 0.06 or 1
    for nom in ("techo", "piso"):
        d = r[nom]
        for hh in d["hist"][-1:]:
            ax.plot([hh["i1"], hh["roto"]], [hh["p1"], hh["p1"] + hh["sl"] * (hh["roto"] - hh["i1"])], color="#93c5fd", lw=1.5, ls="--")
        ln = d["line"]
        if ln:
            ax.plot([ln["i1"], xe], [ln["p1"], ln["p1"] + ln["sl"] * (xe - ln["i1"])], color="#1d4ed8", lw=2.4, zorder=4)
            ax.annotate(f"{'Techo' if nom == 'techo' else 'Piso'} {d['nivel_proy']:.2f}", (xe, d["nivel_proy"]), color="#1d4ed8", fontsize=8, fontweight="bold", xytext=(4, 0), textcoords="offset points", va="center")
        for e in d["ev"]:
            if e["tipo"] in ("CALL", "PUT") and e["t"] >= i0:
                up = e["tipo"] == "CALL"
                ax.scatter([e["t"]], [hi[e["t"]] + pad * .3 if up else lo[e["t"]] - pad * .3], marker="^" if up else "v", s=90, color="#16a34a" if up else "#dc2626", zorder=5)
                ax.annotate(e["tipo"], (e["t"], hi[e["t"]] + pad * .3 if up else lo[e["t"]] - pad * .3), xytext=(0, 8 if up else -14), textcoords="offset points", ha="center", fontsize=8, fontweight="bold")
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_xlim(i0 - 1, xe + 6)
    tk = [j for j in range(i0, n) if j == i0 or h.index[j].normalize() != h.index[j - 1].normalize()]
    ax.set_xticks(tk)
    ax.set_xticklabels([f"{h.index[j]:%d/%m}" for j in tk], fontsize=8)
    ax.grid(alpha=.2)
    ax.set_title(f"{t} · 1h · líneas azules ({r['uso']})", fontsize=9)
    fig.tight_layout()
    b = io.BytesIO()
    fig.savefig(b, format="jpeg", pil_kwargs={"quality": 78})
    plt.close(fig)
    return base64.b64encode(b.getvalue()).decode()


def cargar_todos(tickers):
    d = yf.download(list(tickers), period="60d", interval="30m", prepost=False, progress=False, auto_adjust=False, group_by="ticker", threads=True)
    out = {}
    for t in tickers:
        try:
            x = d[t].dropna(how="all")
            x.index = x.index.tz_convert(NY) if x.index.tz else x.index.tz_localize("UTC").tz_convert(NY)
            out[t] = barras_1h(x) if len(x) else None
        except Exception:
            out[t] = None
    return out


def generar(tickers, carpeta, ahora, corte, uso="mecha"):
    import html as H
    datos = cargar_todos(tickers)
    estado_prev = {}
    pf = os.path.join(AQUI, "lineas_estado.json")
    if os.path.exists(pf):
        try:
            estado_prev = json.load(open(pf, encoding="utf-8"))
        except Exception:
            estado_prev = {}
    logf = os.path.join(AQUI, "rupturas_lineas.csv")
    claves = set()
    if os.path.exists(logf):
        claves = {(r["clave"]) for r in csv.DictReader(open(logf, encoding="utf-8-sig"))}
    nuevos, estado, filas, bloques = [], {}, [], []
    for t in tickers:
        h = datos.get(t)
        fila = {"ticker": t}
        if h is None or len(h) < 30:
            fila["estado"] = "SIN_DATOS"
            filas.append(fila)
            continue
        edad = (ahora - h.index[-1]).total_seconds() / 60
        if edad > MAX_EDAD_MIN:
            fila["estado"] = f"SIN_DATOS (último dato hace {edad / 1440:.1f} días)"
            filas.append(fila)
            continue
        r = analizar(h, ahora, uso)
        fila["estado"] = "CORRECTO" if (r["techo"]["line"] or r["piso"]["line"]) else "SIN_ESTRUCTURA"
        estado[t] = {}
        for nom in ("techo", "piso"):
            d = r[nom]
            ln = d["line"]
            fila[nom] = descr(h, d, uso)
            fila[nom + "_prox"] = round(d["nivel_prox"], 2) if ln else ""
            fila[nom + "_proy"] = round(d["nivel_proy"], 2) if ln else ""
            fila[nom + "_prov"] = d["prov"]
            clave_ln = f"{h.index[ln['i1']]}|{h.index[ln['i2']]}" if ln else ""
            prev = (estado_prev.get(t) or {}).get(nom, "")
            fila[nom + "_cont"] = "" if not ln else ("EXTENDIDA" if prev == clave_ln else ("NUEVA" if not prev else ("2DO_ANCLA_AVANZO" if prev.split("|")[0] == clave_ln.split("|")[0] else "REEMPLAZADA")))
            estado[t][nom] = clave_ln
            evs = [e for e in d["ev"] if e["tipo"] in ("CALL", "PUT")]
            for e in evs:
                k = f"{t}|1h|{e['tipo']}|{h.index[e['t']]}"
                if k not in claves and (ahora - h.index[e['t']]).days <= 8:
                    claves.add(k)
                    nuevos.append(dict(clave=k, ticker=t, tf="1h", tipo=e["tipo"], hora_vela=str(h.index[e["t"]]), nivel_linea=round(e["nivel"], 2), cierre=round(e["cierre"], 2), estado="CONFIRMADA", registrado=str(ahora)))
            fila[nom + "_ult"] = (f"{evs[-1]['tipo']} {ts(h, evs[-1]['t'])} · línea {evs[-1]['nivel']:.2f} · cierre {evs[-1]['cierre']:.2f}") if evs else ""
        filas.append(fila)
        try:
            bloques.append((t, grafico(t, h, r)))
        except Exception as e:
            bloques.append((t, ""))
    if nuevos:
        nuevo_arch = not os.path.exists(logf)
        with open(logf, "a", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, list(nuevos[0].keys()))
            if nuevo_arch:
                w.writeheader()
            w.writerows(nuevos)
    json.dump(estado, open(pf, "w", encoding="utf-8"), indent=1)
    cols = ["ticker", "estado", "techo", "techo_prox", "techo_proy", "techo_prov", "techo_cont", "techo_ult", "piso", "piso_prox", "piso_proy", "piso_prov", "piso_cont", "piso_ult"]
    with open(os.path.join(carpeta, "lineas_tendencia.csv"), "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(filas)
    th = "".join(f"<th>{c}</th>" for c in cols)
    cl = lambda f: "no" if f["estado"] != "CORRECTO" else ""
    tb = "".join(f'<tr class="{cl(f)}">' + "".join(f"<td>{H.escape(str(f.get(c, '')))}</td>" for c in cols) + "</tr>" for f in filas)
    imgs = "".join(f'<details><summary>{t}</summary><img src="data:image/jpeg;base64,{b}" style="max-width:100%"></details>' for t, b in bloques if b)
    doc = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Líneas de tendencia · {ahora:%Y-%m-%d} {corte}</title>
<style>body{{font:13px system-ui;margin:12px;background:#f6f7f8;color:#1b2127}}table{{border-collapse:collapse;background:#fff;min-width:1200px}}th,td{{border:1px solid #d9dee3;padding:4px 6px;text-align:left}}th{{background:#e9edf0}}tr.no td{{color:#888;background:#f0f0f0}}.w{{overflow-x:auto}}.n{{background:#e8f0fe;border:1px solid #b6c8f0;padding:8px 12px;border-radius:8px;margin:8px 0}}details{{margin:6px 0}}summary{{cursor:pointer;font-weight:600}}</style></head><body>
<h2>Líneas de tendencia azules · 35 activos · 1h · {ahora:%d/%m/%Y %H:%M} ET · {corte}mercado</h2>
<div class="n">Solo análisis, sin órdenes. Techo: máximo más alto de las últimas {MAXB} velas → último máximo local posterior más bajo, sin cierres sobre la línea. Piso: espejo con mínimos. Se usan {"mechas" if uso == "mecha" else "cuerpos"}. La línea no se mueve con cada vela: se prolonga y solo se reemplaza cuando la rompe un cierre (CALL: vela verde sobre el techo · PUT: vela roja bajo el piso). «prox» = nivel en la próxima vela; «proy» = nivel a las 10:30 ET de mañana. Rupturas registradas en rupturas_lineas.csv.</div>
<div class="w"><table><tr>{th}</tr>{tb}</table></div><h3>Gráficos</h3>{imgs}</body></html>'''
    ruta = os.path.join(carpeta, f"Lineas_tendencia_35_activos_{ahora:%Y-%m-%d}_{corte}mercado.html")
    open(ruta, "w", encoding="utf-8").write(doc)
    return ruta, filas, datos


if __name__ == "__main__":
    # validacion rapida: python lineas_azules.py SPY [AAPL ...]  -> imprime anclajes (mecha y cuerpo)
    ahora = pd.Timestamp.now(tz=NY)
    tks = sys.argv[1:] or ["SPY"]
    d = cargar_todos(tks)
    for t in tks:
        for uso in ("mecha", "cuerpo"):
            r = analizar(d[t], ahora, uso)
            print(t, uso, "TECHO", descr(d[t], r["techo"], uso), "| PISO", descr(d[t], r["piso"], uso),
                  "| rupturas", [(e["tipo"], ts(d[t], e["t"])) for k in ("techo", "piso") for e in r[k]["ev"] if e["tipo"] in ("CALL", "PUT")])

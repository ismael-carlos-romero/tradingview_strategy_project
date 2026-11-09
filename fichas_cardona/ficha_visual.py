"""Fichas visuales Cardona (35 activos) -> un HTML autocontenido en informes\\AAAA-MM-DD_pre|post\\. SOLO ANALISIS.
Por activo: lamina original de Cardona (letras A-D) + grafico del activo (velas 1h alineadas, PM20/40/100/200, TECHO rojo, PISO verde)
+ tabla de condiciones con estado + conclusion. Sin JavaScript (el visor del portal es un iframe sandbox)."""
import base64, html, io, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

AQUI = os.path.dirname(os.path.abspath(__file__))
LAMINA = os.path.join(AQUI, "assets", "lam_canal.jpg")
PMC = {20: "#2563eb", 40: "#9333ea", 100: "#f59e0b", 200: "#111827"}


def grafico(t, h, g):
    o, hi, lo, c = (h[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    n, ws, D = g["n"], g["ws"], g["D"]
    i0 = max(0, ws - 2)
    xe = D + 2
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=90)
    for j in range(i0, n + 1):
        col = "#16a34a" if c[j] >= o[j] else "#dc2626"
        ax.vlines(j, lo[j], hi[j], color=col, lw=1)
        ax.add_patch(Rectangle((j - 0.32, min(o[j], c[j])), 0.64, max(abs(c[j] - o[j]), 1e-9), color=col, zorder=3))
    xs = np.arange(i0, n + 1)
    for pm, colr in PMC.items():
        ax.plot(xs, h[f"PM{pm}"].values[i0:n + 1], color=colr, lw=1.2, label=f"PM{pm}")
    ymin, ymax = lo[i0:n + 1].min(), hi[i0:n + 1].max()
    pad = (ymax - ymin) * 0.06 or 1
    for key, colr, nom in (("techo", "#dc2626", "TECHO"), ("piso", "#16a34a", "PISO")):
        if g[key]:
            x, y, sl = g[key]
            ax.plot([x, xe], [y, y + sl * (xe - x)], color=colr, lw=2.4, zorder=4)
            v = y + sl * (xe - x)
            ax.annotate(f"{nom} {v:.2f}", (xe, v), color=colr, fontsize=8, fontweight="bold", xytext=(4, 0), textcoords="offset points", va="center")
    if g.get("call_i") is not None:
        j = g["call_i"]
        ax.scatter([j], [hi[j] + pad * 0.3], marker="^", s=90, color="#16a34a", zorder=5)
        ax.annotate("CALL", (j, hi[j] + pad * 0.3), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8, color="#166534", fontweight="bold")
    if g.get("put_i") is not None:
        j = g["put_i"]
        ax.scatter([j], [lo[j] - pad * 0.3], marker="v", s=90, color="#dc2626", zorder=5)
        ax.annotate("PUT", (j, lo[j] - pad * 0.3), xytext=(0, -14), textcoords="offset points", ha="center", fontsize=8, color="#991b1b", fontweight="bold")
    ax.axvline(D + 0.5, color="#94a3b8", lw=0.8, ls="--")
    ax.set_ylim(ymin - pad, ymax + pad)
    ax.set_xlim(i0 - 1, xe + 5)
    tk = [j for j in range(i0, n + 1) if j == i0 or h.index[j].normalize() != h.index[j - 1].normalize()]
    ax.set_xticks(tk)
    ax.set_xticklabels([f"{h.index[j]:%d/%m}" for j in tk], fontsize=8)
    ax.grid(alpha=0.2)
    ax.legend(loc="upper left", fontsize=7, ncol=4)
    ax.set_title(f"{t} · 1h (velas alineadas Cardona) · línea punteada = última sesión completa", fontsize=9)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="jpeg", pil_kwargs={"quality": 80})
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def cuerpo_pct(h, j):
    r = float(h["High"].iloc[j] - h["Low"].iloc[j])
    return abs(float(h["Close"].iloc[j] - h["Open"].iloc[j])) / r * 100 if r > 0 else 0.0


def condiciones(f, h, g):
    """Devuelve (filas, conclusion). Estado: OK / NO / PEND / NV (no verificable)."""
    rup = str(f.get("ruptura", ""))
    n = g["n"]
    r = h.iloc[-1]
    pm20, pm40 = float(r["PM20"]), float(r["PM40"])
    filas = []
    if not rup.startswith(("CALL", "PUT", "NINGUNA")):
        for l in "ABCD":
            filas.append((l, {"A": "Contexto de medias", "B": "Línea trazada", "C": "Ruptura", "D": "Confirmación"}[l], "NV", "SIN_PIVOTE: no se inventa la línea"))
        return filas, "SIN_PIVOTE: con las reglas de techo/piso no hay pivote calculable en la ventana. No se dibuja nada inventado."
    es_call = rup == "CALL" or (rup == "NINGUNA" and g["techo"] and not g["piso"]) or (rup == "NINGUNA" and f.get("caso", "").startswith("A"))
    if rup == "PUT":
        es_call = False
    ri = g["call_i"] if es_call else g["put_i"]
    lin = g["techo"] if es_call else g["piso"]
    nom = "techo" if es_call else "piso"
    # A
    ok_a = pm20 < pm40 if es_call else pm20 > pm40
    filas.append(("A", "PM20 " + ("bajo" if es_call else "sobre") + " PM40 (contexto previo)", "OK" if ok_a else "NO", f"PM20 {pm20:.2f} / PM40 {pm40:.2f}"))
    # B
    anc = f.get("ancla_techo") if es_call else f.get("ancla_piso")
    filas.append(("B", f"{nom.capitalize()} trazado", "OK" if lin else "NV", anc if lin else f"sin {nom} calculable"))
    # C
    if ri is None:
        filas.append(("C", f"Vela {'verde' if es_call else 'roja'} cierra {'sobre' if es_call else 'bajo'} el {nom}", "PEND", "Todavía no hay ruptura"))
        filas.append(("D", "Segunda vela de confirmación", "PEND", "Depende de C"))
        conc = "Sin ruptura todavía. "
    else:
        cp = cuerpo_pct(h, ri)
        filas.append(("C", f"Vela {'verde' if es_call else 'roja'} cierra {'sobre' if es_call else 'bajo'} el {nom}", "OK" if cp >= 60 else "NO", f"{h.index[ri]:%d/%m %H:%M} · cuerpo {cp:.0f}% (pide ≥60%)"))
        if ri == n:
            filas.append(("D", "Segunda vela de confirmación", "PEND", "La ruptura es la última vela"))
        else:
            j = ri + 1
            col = float(h["Close"].iloc[j]) > float(h["Open"].iloc[j]) if es_call else float(h["Close"].iloc[j]) < float(h["Open"].iloc[j])
            x, y, sl = lin
            ln = y + sl * (j - x)
            cl = float(h["Close"].iloc[j])
            ok = col and (cl > ln if es_call else cl < ln)
            filas.append(("D", "Segunda vela de confirmación", "OK" if ok else "NO", f"{h.index[j]:%d/%m %H:%M} cierra {cl:.2f} · línea {ln:.2f}"))
        conc = f"Ruptura {rup} detectada ({h.index[ri]:%d/%m %H:%M}). "
    tp, pp = f.get("techo_proy"), f.get("piso_proy")
    partes = []
    if tp is not None:
        partes.append(f"TECHO {tp} ({f.get('dist_techo_pct')}%)")
    if pp is not None:
        partes.append(f"PISO {pp} ({f.get('dist_piso_pct')}%)")
    conc += "Proyección 10:30 ET de mañana: " + " · ".join(partes) + ". " if partes else ""
    conc += f"Zona {f.get('zona_estricta') or f.get('zona') or '—'}. Análisis, no es una orden."
    return filas, conc


ESTADO = {"OK": ("Cumplida", "ok"), "NO": ("No cumplida", "no"), "PEND": ("Pendiente", "pe"), "NV": ("No verificable", "nv")}
CSS = """body{font:14px system-ui,Segoe UI,Arial;margin:0;background:#f3f5f7;color:#16202a}.w{max-width:1250px;margin:auto;padding:12px}
h1{font-size:20px;margin:6px 0}.nota{background:#fff7d6;border:1px solid #e8d38a;padding:8px 12px;border-radius:8px;margin:8px 0}
.ix{background:#fff;border:1px solid #d9dee3;border-collapse:collapse;width:100%}.ix td,.ix th{border:1px solid #e1e5e9;padding:4px 7px;text-align:left}.ix th{background:#e9edf0}
.call{color:#15803d;font-weight:700}.put{color:#b91c1c;font-weight:700}.fi{background:#fff;border:1px solid #d9dee3;border-radius:10px;margin:16px 0;padding:12px}
.fi h2{margin:0 0 8px;font-size:18px}.g{display:flex;gap:12px;flex-wrap:wrap}.lam{flex:0 0 380px;max-width:100%;aspect-ratio:4/3;background-size:cover;border:1px solid #cfd5db;border-radius:6px}
.gr{flex:1 1 520px;min-width:0}.gr img{width:100%;border:1px solid #cfd5db;border-radius:6px}.cap{font-size:12px;color:#5b6773;margin:3px 0}
table.c{border-collapse:collapse;width:100%;margin-top:10px}.c td,.c th{border:1px solid #e1e5e9;padding:5px 8px;text-align:left}.c th{background:#eef1f4}
.ok{background:#dcfce7;color:#166534;font-weight:700}.no{background:#fee2e2;color:#991b1b;font-weight:700}.pe{background:#fef3c7;color:#92400e;font-weight:700}.nv{background:#e5e7eb;color:#4b5563;font-weight:700}
.conc{margin-top:8px;padding:8px 10px;background:#eef6ff;border-left:4px solid #2563eb;border-radius:4px}a{color:#1d4ed8}"""


def generar(res, carpeta, ahora, corte):
    lam = base64.b64encode(open(LAMINA, "rb").read()).decode() if os.path.exists(LAMINA) else ""
    css = CSS + f".lam{{background-image:url(data:image/jpeg;base64,{lam})}}"
    ix, bloques = [], []
    for f in res:
        t = f["ticker"]
        h, g = f.get("_h"), f.get("geo")
        rup = str(f.get("ruptura", "") or "")
        cls = "call" if rup == "CALL" else ("put" if rup == "PUT" else "")
        ix.append(f'<tr><td><a href="#{t}">{t}</a></td><td class="{cls}">{html.escape(rup or f["estado_datos"])}</td><td>{f.get("techo_proy") or ""}</td><td>{f.get("dist_techo_pct") or ""}</td><td>{f.get("piso_proy") or ""}</td><td>{f.get("dist_piso_pct") or ""}</td><td>{f.get("zona_estricta") or f.get("zona") or ""}</td></tr>')
        if f["estado_datos"] != "OK" or h is None or not g:
            bloques.append(f'<div class="fi" id="{t}"><h2>{t}</h2><div class="conc">{html.escape(f["estado_datos"])}. No se genera ficha visual.</div></div>')
            continue
        try:
            img = grafico(t, h, g)
            filas, conc = condiciones(f, h, g)
        except Exception as e:
            bloques.append(f'<div class="fi" id="{t}"><h2>{t}</h2><div class="conc">Error al graficar: {html.escape(str(e)[:80])}</div></div>')
            continue
        tr = "".join(f'<tr><td><b>{l}</b></td><td>{html.escape(d)}</td><td class="{ESTADO[e][1]}">{ESTADO[e][0]}</td><td>{html.escape(str(o))}</td></tr>' for l, d, e, o in filas)
        bloques.append(f'''<div class="fi" id="{t}"><h2>{t} · {html.escape(rup)} · cierre {f.get("cierre")}</h2>
<div class="g"><div><div class="lam"></div><div class="cap">Lámina original de Cardona (canal / ruptura) con las letras A–D</div></div>
<div class="gr"><img alt="{t}" src="data:image/jpeg;base64,{img}"><div class="cap">Mismo esquema aplicado a {t}: TECHO rojo, PISO verde (estilo Ismael), PM20/40/100/200.</div></div></div>
<table class="c"><tr><th></th><th>Condición</th><th>Estado</th><th>Detalle</th></tr>{tr}</table>
<div class="conc">{html.escape(conc)}</div><div class="cap"><a href="#top">↑ volver al índice</a></div></div>''')
    doc = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fichas visuales Cardona · {ahora:%Y-%m-%d} {corte}</title><style>{css}</style></head><body><div class="w" id="top">
<h1>Fichas visuales Cardona · {len(res)} activos · {ahora:%d/%m/%Y %H:%M} ET · {corte}mercado</h1>
<div class="nota">Solo análisis (sin órdenes). Condiciones: A medias · B línea trazada · C vela de ruptura (cuerpo ≥60%) · D segunda vela de confirmación. Velas alineadas Cardona (9:30–10:00, luego horas); TradingView usa 9:30–10:30, puede diferir levemente.</div>
<table class="ix"><tr><th>Activo</th><th>Ruptura</th><th>Techo proy.</th><th>Dist %</th><th>Piso proy.</th><th>Dist %</th><th>Zona</th></tr>{"".join(ix)}</table>
{"".join(bloques)}</div></body></html>'''
    nombre = f"Fichas_visuales_35_activos_{ahora:%Y-%m-%d}_{corte}mercado.html"
    ruta = os.path.join(carpeta, nombre)
    open(ruta, "w", encoding="utf-8").write(doc)
    return ruta

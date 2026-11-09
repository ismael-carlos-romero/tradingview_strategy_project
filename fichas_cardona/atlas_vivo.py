"""Atlas vivo - detector por ETAPAS de la estrategia PM40 HORA (lamina "2da. Estrategias CALL: Promedio Movil 40 Hora").
Solo analiza y avisa. No opera. Usa las velas alineadas de cardona_rules (9:30-10:00, 10:00-11:00 ...), solo cerradas.

Etapas (CALL):
  VIGILANCIA : criterios 1-3 (PM20>PM40 y PM100>PM200 en paralelo) + criterio 2 (viene de una caida con linea descendente)
  CASI       : + las velas rojas finales rompieron PM20 y tocaron PM40 (criterio 4). Falta la vela verde que rompa PM20 y la linea.
  CONFIRMADA : + vela verde final (solida o martillo, no hanger) cierra sobre PM20 y sobre la linea, entre 11:00 y 15:59 (criterio 5 + regla de oro).
Uso: python atlas_vivo.py [TICKER ...]   (sin argumentos = los 35 activos)
"""
import os, sys, json, datetime as dt
import numpy as np, pandas as pd
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI)); sys.path.insert(0, AQUI)
import cardona_rules as cr
import lineas_cardona as lc_
import yfinance as yf

TICKERS = "BLK SPY QQQ META MSCI AMD MSFT VLO AXON GLD TSLA GOOGL AAPL GOOG AMZN MRNA CVX NVDA PLTR XOM COIN USO ORCL C EBAY DIS NDAQ UBER NFLX PYPL HPE TNA SLV BAC EA".split()
VER = "atlas-pm40-v1"


def cargar(tickers):
    d30 = yf.download(tickers, period="60d", interval="30m", prepost=False, progress=False, auto_adjust=False, group_by="ticker", threads=True)
    d1 = yf.download(tickers, period="2y", interval="1d", progress=False, auto_adjust=False, group_by="ticker", threads=True)
    return d30, d1


def etapa_pm40(h):
    """Evalua la ultima vela cerrada de h (ya con features). Devuelve dict con etapa y condiciones."""
    i = len(h) - 1
    r = h.iloc[i]
    c = {}
    if i < 210 or pd.isna(r.PM200):
        return {"etapa": "DATOS_INSUFICIENTES", "c": c}
    w10 = h.iloc[-10:]
    c["1_paralelo_20>40_100>200"] = bool((w10.PM20 > w10.PM40).all() and (w10.PM100 > w10.PM200).all())
    lp = lc_.linea_caida(h, i - 1)          # linea hasta la vela anterior, proyectada a la vela evaluada
    rompe = bool(lp and r.Close > lc_.valor(lp, i))
    ln = lp if rompe else lc_.linea_caida(h, i)   # sin ruptura: linea hasta la ULTIMA vela, proyectada a la proxima
    peak = float(h.High.iloc[ln[0]:i].max()) if ln else None
    caida = round((peak - float(h.Low.iloc[ln[0]:i + 1].min())) / peak * 100, 2) if ln else 0.0
    c["2_viene_de_caida"] = bool(ln and caida >= cr.CAIDA_MIN)
    w5 = h.iloc[-5:]
    c["4a_rojas_rompen_PM20"] = bool((w5.Close.iloc[:-1] < w5.PM20.iloc[:-1]).any() or r.Close < r.PM20)
    w4 = h.iloc[-4:]
    c["4b_tocan_PM40"] = bool(((w4.Low <= w4.PM40 * 1.0015) & (w4.Close >= w4.PM40 * 0.9985)).any())
    linea_i = float(lc_.valor(ln, i if rompe else i + 1)) if ln else None
    c["5a_verde_solida_o_martillo"] = bool((r.solid_green or r.hammer) and not r.hanger_like)
    c["5b_cierra_sobre_PM20"] = bool(r.Close > r.PM20)
    c["5c_cierra_sobre_linea"] = rompe
    c["5d_ventana_11-15:59"] = bool(11 * 60 <= r.end_min <= 16 * 60)
    ctx = c["1_paralelo_20>40_100>200"] and c["2_viene_de_caida"]
    toque = c["4a_rojas_rompen_PM20"] and c["4b_tocan_PM40"]
    gatillo = c["5a_verde_solida_o_martillo"] and c["5b_cierra_sobre_PM20"] and c["5c_cierra_sobre_linea"]
    if ctx and toque and gatillo:
        etapa = "CONFIRMADA" if c["5d_ventana_11-15:59"] else "CONFIRMADA_FUERA_DE_HORARIO"
    elif ctx and toque:
        etapa = "CASI"
    elif ctx:
        etapa = "VIGILANCIA"
    else:
        etapa = "SIN_CONTEXTO"
    falta = [k for k, v in c.items() if not v]
    dist = round((linea_i - float(r.Close)) / float(r.Close) * 100, 2) if linea_i else None
    return {"etapa": etapa, "c": c, "falta": falta, "caida_%": caida, "linea_hoy": round(linea_i, 2) if linea_i else None,
            "dist_a_linea_%": dist, "cierre": round(float(r.Close), 2), "vela": str(h.index[i]), "ln": ln}


def grafico(t, h, res, carpeta):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = h.iloc[-70:].reset_index(drop=True); off = len(h) - 70
    fig, ax = plt.subplots(figsize=(11, 5.5), facecolor="#111"); ax.set_facecolor("#111")
    for k, rw in x.iterrows():
        col = "#26c281" if rw.Close >= rw.Open else "#e74c3c"
        ax.vlines(k, rw.Low, rw.High, color=col, lw=1); ax.add_patch(plt.Rectangle((k - .3, min(rw.Open, rw.Close)), .6, abs(rw.Close - rw.Open) or .01, color=col))
    for n, col in ((20, "#f1c40f"), (40, "#e74c3c"), (100, "#2ecc71"), (200, "#a29bfe")):
        ax.plot(x[f"PM{n}"], color=col, lw=1.2, label=f"PM{n}")
    ln = res.get("ln")
    if ln:
        a, b = ln[0] - off, len(h) - 1 - off
        ax.plot([a, b], [cr.line_at(ln, ln[0]), cr.line_at(ln, len(h) - 1)], color="#74b9ff", lw=1.6, label="línea de caída")
    ax.set_title(f"{t} · PM40 hora · {res['etapa']} · vela {res['vela'][:16]}  [gráfico generado por Atlas]", color="w", fontsize=10)
    ax.tick_params(colors="#aaa"); ax.legend(facecolor="#222", labelcolor="w", fontsize=8, loc="upper left")
    txt = "\n".join(("✔ " if v else "✘ ") + k for k, v in res["c"].items())
    ax.text(1.01, .98, txt, transform=ax.transAxes, va="top", color="w", fontsize=7.5)
    p = os.path.join(carpeta, f"{t}_PM40_{res['etapa']}.png")
    fig.savefig(p, dpi=110, bbox_inches="tight", facecolor="#111"); plt.close(fig)
    return p


def main(tickers):
    d30, d1 = cargar(tickers)
    hoy = dt.date.today().isoformat()
    carpeta = os.path.join(os.path.dirname(AQUI), "informes", f"{hoy}_atlas_vivo"); os.makedirs(carpeta, exist_ok=True)
    filas = []
    for t in tickers:
        try:
            x = d30[t].dropna(how="all"); y = d1[t].dropna(how="all")
            h = cr.add_features(cr.build_cardona_bars(x), y)
            res = etapa_pm40(h)
        except Exception as e:
            res = {"etapa": "SIN_DATOS", "c": {}, "falta": [str(e)[:60]]}
            h = None
        if res["etapa"] in ("CASI", "CONFIRMADA", "CONFIRMADA_FUERA_DE_HORARIO", "VIGILANCIA") and h is not None:
            res["img"] = grafico(t, h, res, carpeta)
        filas.append({"ticker": t, "etapa": res["etapa"], "vela": res.get("vela", ""), "cierre": res.get("cierre", ""),
                      "linea": res.get("linea_hoy", ""), "dist_linea_%": res.get("dist_a_linea_%", ""), "caida_%": res.get("caida_%", ""),
                      "falta": " | ".join(res.get("falta", [])), "img": res.get("img", "")})
    df = pd.DataFrame(filas)
    df.to_csv(os.path.join(carpeta, "pm40_etapas.csv"), index=False, encoding="utf-8-sig")
    orden = {"CONFIRMADA": 0, "CONFIRMADA_FUERA_DE_HORARIO": 1, "CASI": 2, "VIGILANCIA": 3}
    df["o"] = df.etapa.map(orden).fillna(9); df = df.sort_values("o")
    print(df.etapa.value_counts().to_string()); print()
    print(df[df.o < 9][["ticker", "etapa", "vela", "cierre", "linea", "dist_linea_%", "falta"]].to_string(index=False))
    print("\ncarpeta:", carpeta)


if __name__ == "__main__":
    main(sys.argv[1:] or TICKERS)

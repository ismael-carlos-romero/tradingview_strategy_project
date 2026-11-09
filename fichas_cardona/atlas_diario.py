"""Atlas vivo - corrida completa: 12 estrategias x 35 activos -> informes\\atlas_vivo\\ultimo.json (+imagenes, registro, avisos).
Solo analiza y avisa; no opera ni toca las compras. Uso: python atlas_diario.py [--no-enviar] [TICKER ...]"""
import os, sys, json, csv, datetime as dt
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI)); sys.path.insert(0, AQUI)
import numpy as np, pandas as pd
import atlas_vivo as av, atlas_motor as am, atlas_estrategias as ae, lineas_cardona as lc

OUT = os.path.join(AQUI, "informes", "atlas_vivo")
RANK = ae.ORDEN
ALERTA = ("CASI", "CONFIRMADA")
NOMBRE = {k: n for k, n, *_ in ae.REGISTRO}


def _lista(pasos):
    return [[p["n"], p["ok"], p.get("d", "")] for p in pasos]


def grafico(t, k, r, h, carpeta):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    n = 70; x = h.iloc[-n:].reset_index(drop=True); off = len(h) - n
    fig, ax = plt.subplots(figsize=(11.5, 5.6), facecolor="#111"); ax.set_facecolor("#111")
    for j, rw in x.iterrows():
        c = "#26c281" if rw.Close >= rw.Open else "#e74c3c"
        ax.vlines(j, rw.Low, rw.High, color=c, lw=1); ax.add_patch(plt.Rectangle((j - .3, min(rw.Open, rw.Close)), .6, abs(rw.Close - rw.Open) or .01, color=c))
    for m, c in ((20, "#f1c40f"), (40, "#e74c3c"), (100, "#2ecc71"), (200, "#a29bfe")):
        ax.plot(x[f"PM{m}"], color=c, lw=1.2, label=f"PM{m}")
    for d in r.get("draw", []):
        if "p" in d:
            j1, y1, j2, y2 = d["p"]; a, b = j1 - off, len(h) - 1 - off
            ax.plot([a, b], [lc.valor((j1, y1, j2, y2), j1 + off - off), lc.valor((j1, y1, j2, y2), len(h) - 1)], color="#74b9ff" if d["k"] != "piso" else "#fdcb6e", lw=1.8, label="línea " + d["k"])
        elif "y" in d:
            ax.hlines(d["y"], max(0, d.get("j", 0) - off), n - 1, colors="#fd79a8", linestyles="--", lw=1.4, label=d["k"].replace("_", " "))
    ax.add_patch(plt.Circle((n - 1, x.Close.iloc[-1]), 1.6, fill=False, ec="#f39c12", lw=2, ls="--"))
    ax.set_title(f"{t} · {NOMBRE[k]} ({r['dir']}) · {r['etapa']} · vela {str(h.index[-1])[:16]}  [gráfico generado por Atlas, no es captura de TradingView]", color="w", fontsize=9)
    ax.tick_params(colors="#aaa"); ax.legend(facecolor="#222", labelcolor="w", fontsize=7, loc="upper left", ncol=3)
    txt = "\n".join({True: "✔ ", False: "✘ ", None: "… "}[p["ok"]] + p["n"][:58] for p in r["pasos"]) + "\nVentana de compra: " + r["ventana"] + (" ✔" if r["ventana_ok"] else " (fuera)")
    ax.text(1.01, .98, txt, transform=ax.transAxes, va="top", color="w", fontsize=7.5)
    p = os.path.join(carpeta, f"{t}_{k}.png"); fig.savefig(p, dpi=105, bbox_inches="tight", facecolor="#111"); plt.close(fig)
    return os.path.basename(p)


def mercado_estado(ahora_ny):
    wd, m = ahora_ny.weekday(), ahora_ny.hour * 60 + ahora_ny.minute
    if wd >= 5: return "fin de semana"
    return "abierto" if 570 <= m < 960 else ("premercado" if m < 570 else "cerrado")


def enviar_telegram(texto, img):
    try:
        import tg_fichas, requests
        d = tg_fichas.destino()
        if not d: return False
        tok, chat = d
        with open(img, "rb") as fh:
            return requests.post(f"https://api.telegram.org/bot{tok}/sendPhoto", data={"chat_id": chat, "caption": texto[:1000], "parse_mode": "HTML"},
                                 files={"photo": fh}, timeout=60).ok
    except Exception:
        return False


LAMINAS = {"GAP_NORMAL": "gap_normal_alza", "GAP_BAJISTA": "gap_bajista_alza", "PISO_FUERTE": "piso_fuerte", "PRIMER_GAP": "1er_gap_alza",
           "PM40": "pm40", "CAIDA": "caida_normal_fuerte", "CANAL_BREAK": "ruptura_canal_bajista", "VELA_ROJA": "primera_vela_roja",
           "RUPT_PISO": "ruptura_piso_gap", "CUATRO_PASOS": "modelo_4_pasos", "HANGER": "hanger_diario", "TECHO_FUERTE": "techo_fuerte"}


def asegurar_laminas():
    """Copia las laminas de Cardona (assets) a la carpeta que sirve el portal."""
    import shutil
    for k, n in LAMINAS.items():
        dst = os.path.join(OUT, f"lam_{k}.png"); src = os.path.join(os.path.dirname(AQUI), "assets", f"cardona_{n}.png")
        if not os.path.exists(dst) and os.path.exists(src):
            shutil.copyfile(src, dst)


def run(tickers=None, enviar=True, motivo="manual"):
    tickers = tickers or av.TICKERS
    os.makedirs(OUT, exist_ok=True)
    d30, d1 = av.cargar(tickers)
    ahora = pd.Timestamp.now(tz="America/New_York")
    estado_p = os.path.join(OUT, "atlas_estado.json")
    prev = json.load(open(estado_p, encoding="utf-8")) if os.path.exists(estado_p) else {}
    nuevo, activos, eventos, asof = {}, [], [], ""
    primera = not os.path.exists(estado_p)      # primera corrida: deja la base y NO avisa
    asegurar_laminas()
    for t in tickers:
        try:
            x30 = d30[t].dropna(how="all") if len(tickers) > 1 else d30.dropna(how="all")
            x1 = d1[t].dropna(how="all") if len(tickers) > 1 else d1.dropna(how="all")
            if len(x30) == 0 or len(x1) == 0:
                raise ValueError("Yahoo no devuelve datos")
            h, D = am.preparar(x30, x1)
            if len(h) == 0:
                raise ValueError("sin velas")
            R = ae.evaluar_activo(h, D)
        except Exception as e:
            activos.append({"t": t, "sin_datos": str(e)[:60]}); continue
        asof = max(asof, str(h.index[-1])[:16])
        a = {"t": t, "e": {}}
        for k, r in R.items():
            if "pasos" not in r:
                a["e"][k] = {"etapa": r["etapa"]}; continue
            a["e"][k] = {"etapa": r["etapa"], "dir": r["dir"], "ventana": r["ventana"], "ventana_ok": r["ventana_ok"], "nota": r["nota"],
                         "pasos": _lista(r["pasos"]), "draw": r["draw"], **{q: r[q] for q in ("escenario", "hora", "del_dia") if q in r}}
            clave = f"{t}|{k}"; sello = str(h.index[-1])[:10]
            nuevo[clave] = {"etapa": r["etapa"], "dia": sello}
            ant = prev.get(clave, {"etapa": "SIN_CONTEXTO", "dia": ""})
            if r["etapa"].split("_")[0] in ALERTA and (RANK[r["etapa"]] < RANK.get(ant["etapa"], 9) or (ant["dia"] != sello and ant["etapa"] != r["etapa"])):
                img = grafico(t, k, r, h, OUT)
                falta = next((p["n"] for p in r["pasos"] if p["ok"] is not True), "—")
                ev = {"ts": str(ahora)[:16], "t": t, "k": k, "nombre": NOMBRE[k], "etapa": r["etapa"], "dir": r["dir"], "falta": falta, "img": img, "vela": str(h.index[-1])[:16], "enviado": False}
                txt = f"<b>{t} · {NOMBRE[k]}</b> ({r['dir']})\nEtapa: <b>{r['etapa']}</b>\nFalta: {falta}\nVentana: {r['ventana']} NY"
                if enviar and r["etapa"] in ALERTA: ev["enviado"] = enviar_telegram(txt, os.path.join(OUT, img))
                eventos.append(ev)
            elif r["etapa"] in ("CASI", "CONFIRMADA", "CONFIRMADA_FUERA_DE_HORARIO") and not os.path.exists(os.path.join(OUT, f"{t}_{k}.png")):
                grafico(t, k, r, h, OUT)
        if True:
            w = h.iloc[-60:]; off = len(h) - 60; rd = lambda s: [None if v != v else round(float(v), 2) for v in s]
            a["bars"] = {"t": [str(i)[5:16] for i in w.index], "o": rd(w.Open), "h": rd(w.High), "l": rd(w.Low), "c": rd(w.Close),
                         "pm20": rd(w.PM20), "pm40": rd(w.PM40), "pm100": rd(w.PM100), "pm200": rd(w.PM200), "off": off}
        activos.append(a)
    conteo = {k: {} for k, *_ in ae.REGISTRO}
    for a in activos:
        for k, v in a.get("e", {}).items():
            conteo[k][v["etapa"]] = conteo[k].get(v["etapa"], 0) + 1
    data = {"version": am.VERSION + "/" + lc.VERSION, "generado": str(ahora)[:16] + " NY", "motivo": motivo, "asof": asof, "mercado": mercado_estado(ahora),
            "estrategias": [{"id": k, "nombre": n} for k, n, *_ in ae.REGISTRO], "activos": activos, "conteo": conteo}
    json.dump(data, open(os.path.join(OUT, "ultimo.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump({**prev, **nuevo}, open(estado_p, "w", encoding="utf-8"), ensure_ascii=False)
    arch = os.path.join(OUT, "archivo"); os.makedirs(arch, exist_ok=True)
    json.dump(data, open(os.path.join(arch, f"atlas_{ahora.strftime('%Y-%m-%d_%H%M')}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    if primera:
        eventos = []
    if eventos:
        ap = os.path.join(OUT, "avisos.json")
        lista = (json.load(open(ap, encoding="utf-8")) if os.path.exists(ap) else []) + eventos
        json.dump(lista[-500:], open(ap, "w", encoding="utf-8"), ensure_ascii=False)
        rp = os.path.join(OUT, "atlas_registro.csv"); nuevo_csv = not os.path.exists(rp)
        with open(rp, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(eventos[0].keys()))
            if nuevo_csv: w.writeheader()
            w.writerows(eventos)
    json.dump({"ts": str(ahora)[:19], "ok": True, "activos": len(activos), "avisos": len(eventos)}, open(os.path.join(OUT, "heartbeat.json"), "w"))
    return data, eventos


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    data, ev = run(args or None, enviar="--no-enviar" not in sys.argv)
    print("asof", data["asof"], "| mercado", data["mercado"], "| avisos nuevos", len(ev))
    for k, c in data["conteo"].items():
        print(k.ljust(14), c)
    for e in ev:
        print("AVISO", e["t"], e["k"], e["etapa"], "| falta:", e["falta"])

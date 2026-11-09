import os, sys, json
AQUI = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, AQUI)
import atlas_vivo as av, cardona_rules as cr
d30, d1 = av.cargar(av.TICKERS)
out = {"asof": "", "assets": []}
for t in av.TICKERS:
    try:
        h = cr.add_features(cr.build_cardona_bars(d30[t].dropna(how="all")), d1[t].dropna(how="all"))
        r = av.etapa_pm40(h)
    except Exception as e:
        out["assets"].append({"t": t, "etapa": "SIN_DATOS"}); continue
    a = {"t": t, "etapa": r["etapa"], "c": r.get("c", {}), "cierre": r.get("cierre"), "linea": r.get("linea_hoy"), "dist": r.get("dist_a_linea_%"), "caida": r.get("caida_%"), "vela": r.get("vela", "")[:16]}
    out["asof"] = a["vela"] or out["asof"]
    if r["etapa"] in ("CASI", "VIGILANCIA", "CONFIRMADA"):
        x = h.iloc[-60:]; off = len(h) - 60; ln = r["ln"]
        rd = lambda s: [None if v != v else round(float(v), 2) for v in s]
        a["bars"] = {"t": [str(i)[5:16] for i in x.index], "o": rd(x.Open), "h": rd(x.High), "l": rd(x.Low), "c": rd(x.Close),
                     "pm20": rd(x.PM20), "pm40": rd(x.PM40), "pm100": rd(x.PM100), "pm200": rd(x.PM200)}
        a["line"] = [ln[0] - off, round(float(cr.line_at(ln, ln[0])), 2), len(h) - 1 - off, round(float(cr.line_at(ln, len(h) - 1)), 2)]
    out["assets"].append(a)
json.dump(out, open(os.path.join(AQUI, "proto_pm40.json"), "w"), ensure_ascii=False)
print("ok", len(out["assets"]))

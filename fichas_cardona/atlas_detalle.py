"""Uso: python atlas_detalle.py TICKER ESTRATEGIA  -> pasos de la estrategia en cada vela del ultimo dia"""
import sys
import atlas_vivo as av, atlas_motor as am, atlas_estrategias as ae
t, k = sys.argv[1], sys.argv[2]
d30, d1 = av.cargar([t])
h, D = am.preparar(d30[t].dropna(how="all") if t in d30 else d30.dropna(how="all"), d1[t].dropna(how="all") if t in d1 else d1.dropna(how="all"))
f = [x for x in ae.REGISTRO if x[0] == k][0][2]
hoy = [j for j in range(len(h)) if h.index[j].date() == h.index[-1].date()]
for j in hoy:
    r = f(am.contexto(h.iloc[:j + 1], D))
    print(str(h.index[j])[:16], r["etapa"].ljust(28), "".join("1" if p["ok"] else ("-" if p["ok"] is None else "0") for p in r["pasos"]), r["ventana_ok"])
r = f(am.contexto(h, D))
for p in r["pasos"]:
    print(p["ok"], p["n"], p["d"])
print("draw", r["draw"])

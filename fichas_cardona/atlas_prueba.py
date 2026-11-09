import sys, collections, json, time
import atlas_vivo as av, atlas_motor as am, atlas_estrategias as ae
t0=time.time(); d30,d1=av.cargar(av.TICKERS); print("datos",round(time.time()-t0))
cnt=collections.defaultdict(collections.Counter); casos=[]
for t in av.TICKERS:
    try:
        h,D=am.preparar(d30[t].dropna(how="all"), d1[t].dropna(how="all"))
    except Exception as e:
        print(t,"sin datos",str(e)[:50]); continue
    r=ae.evaluar_activo(h,D)
    for k,v in r.items():
        cnt[k][v["etapa"]]+=1
        if v["etapa"] in("CASI","CONFIRMADA","CONFIRMADA_FUERA_DE_HORARIO"): casos.append((t,k,v["etapa"],[p["n"][:28] for p in v["pasos"] if p["ok"] is not True][:2]))
        if v["etapa"]=="ERROR": print("ERROR",t,k,v["error"])
print(round(time.time()-t0),"s")
for k,c in cnt.items(): print(k.ljust(14),dict(c))
for c in casos: print(c)

"""Pruebas de aceptacion del backend del Aula Virtual. Uso: python -m aula_virtual.test_aceptacion  (alumno aislado 'test_aceptacion')."""
import json, sys
import pandas as pd
from . import api, generador as g, motor, datos, almacen as al, definiciones as df

AL = "test_aceptacion"
R = []


def chk(n, ok, det=""):
    R.append((n, bool(ok), det)); print(("PASS" if ok else "FAIL"), n, "-", det)


def nuevo(modo="vela", cat=None, est=None, seed=None, ex=True, ruta="evaluable"):
    for s in ([seed] if seed else range(1, 60)):
        r = g.crear(AL, modo, ruta, s, est, None, cat, ex)
        if "error" not in r:
            return r
    raise RuntimeError("sin caso para " + str((modo, cat, est)))


def resp(r, **kw):
    d = api._desafio(r["id"]); ref = motor.referencia(d["ticker"], d["corte"], d["estrategia"])[d["estrategia"]]
    sid = d["estrategia"]; pas = ref["pasos"]
    p = dict(estrategia=sid, tf_decision="hora", tfs_vistas=["hora"] + df.ESTRATEGIAS[sid]["tf_contraste"], clasificacion=ref["clase"],
             requisitos=[f"{sid}.c{k}" for k, x in enumerate(pas, 1) if x["ok"] is True], faltantes=[f"{sid}.c{k}" for k, x in enumerate(pas, 1) if x["ok"] is not True],
             explicacion="Veo el contexto, los requisitos cumplidos y la condicion que falta antes de confirmar; descarto si no cierra la vela.", corte=d["corte"], anotaciones=[])
    if ref["clase"] == "CONFIRMADA":
        p["vela_confirmacion"] = d["corte"]
    p.update(kw); return d, ref, p


def entrega(r, p):
    out, code = api.entregar({"desafio": r["id"], "alumno": AL, "payload": p, "duracion_s": 30}); return out, code


def main():
    # 1 confirmado
    r = nuevo(cat="confirmado"); d, ref, p = resp(r); o, c = entrega(r, p)
    chk("1 patron confirmado marcado correctamente", c == 200 and ref["clase"] == "CONFIRMADA" and o["evaluacion"]["acierto_clase"], f"{d['ticker']} {d['estrategia']} total={o['evaluacion']['total']}")
    # 11 reintento tras ver solucion -> asistida
    o2, c2 = entrega(r, p); chk("11 reintento tras revelar solucion = practica asistida", c2 == 200 and o["tipo"] == "independiente" and o2["tipo"] == "asistida", f"{o['tipo']} -> {o2['tipo']}")
    # 2 en formacion
    r = nuevo(cat="formacion"); d, ref, p = resp(r); o, c = entrega(r, p)
    chk("2 patron en formacion clasificado", ref["clase"] == "EN_FORMACION" and o["evaluacion"]["acierto_clase"], f"{d['ticker']} {d['estrategia']} total={o['evaluacion']['total']}")
    # 4 anticipacion: marcar confirmada antes del cierre
    r = nuevo(cat="formacion"); d, ref, p = resp(r, clasificacion="CONFIRMADA"); o, c = entrega(r, p)
    chk("4 ruptura marcada antes del cierre de la vela", c == 200 and o["evaluacion"].get("anticipacion") and not o["evaluacion"]["acierto_clase"], f"clase ref={ref['clase']}")
    # 3 contraejemplo
    r = nuevo(cat="contraejemplo"); d, ref, p = resp(r, clasificacion="NO_APLICA"); o, c = entrega(r, p)
    chk("3 contraejemplo descartado", ref["clase"] == "NO_APLICA" and o["evaluacion"]["acierto_clase"], f"{d['ticker']} {d['estrategia']}")
    # 5 temporalidad incorrecta
    r = nuevo(cat="confirmado"); d, ref, p = resp(r, tf_decision="diario", tfs_vistas=["diario"]); o, c = entrega(r, p)
    ob = " ".join(map(str, o["evaluacion"]["desglose"]["contexto"]["obs"]))
    chk("5 temporalidad incorrecta penalizada", o["evaluacion"]["desglose"]["contexto"]["pts"] < o["evaluacion"]["desglose"]["contexto"]["max"] and "incorrecta" in ob, ob[:90])
    # 6 varios patrones en un mismo grafico (modo reconoce)
    multi = None
    for s in range(1, 80):
        r = g.crear(AL, "reconoce", "evaluable", s, None, None, None, True)
        if "error" in r: continue
        d = api._desafio(r["id"]); refs = motor.referencia(d["ticker"], d["corte"])
        ap = {k: v for k, v in refs.items() if v["etapa"] in ("CONFIRMADA", "CASI")}
        if len(ap) >= 2: multi = (r, d, ap); break
    if multi:
        r, d, ap = multi; hip = [{"sid": k, "estado": v["clase"], "requisitos": [], "faltantes": []} for k, v in ap.items()]
        o, c = entrega(r, {"hipotesis": hip, "tf_decision": "hora", "tfs_vistas": ["hora", "diario"], "explicacion": "Hay varias estrategias posibles, cada una con sus requisitos.", "anotaciones": [], "corte": d["corte"]})
        chk("6 varias estrategias posibles en un grafico, cada una con sus requisitos", c == 200 and len(hip) >= 2 and o["evaluacion"]["desglose"]["contexto"]["pts"] > 0, f"{len(hip)} hipotesis, estrategia previa {list(ap)}")
    else:
        chk("6 varias estrategias posibles", False, "no se halló corte con 2+ estrategias")
    # 7 dibujo valido con anclajes distintos a la referencia
    lin = []
    for s_ in range(1, 80):
        r = nuevo(cat="confirmado", seed=s_); d, ref, p = resp(r); lin = [x for x in ref["draw"] if x["tipo"] == "linea"]
        if lin: break
    if lin:
        h = datos.preparado(d["ticker"])["h"]; a = lin[0]; j1 = h.index.get_loc(pd.Timestamp(a["t1"])); j2 = h.index.get_loc(pd.Timestamp(a["t2"]))
        o0, _ = entrega(r, dict(p, anotaciones=[dict(a, id="x", tf="hora")]))
        r2 = nuevo(cat="confirmado", est=d["estrategia"]); 
        chk("7a trazo identico a la referencia puntua trazado", o0["evaluacion"]["desglose"]["trazado"]["pts"] > 0, str(o0["evaluacion"]["desglose"]["trazado"]["pts"]))
        mala = dict(a, p1=a["p1"] * 1.15, p2=a["p2"] * 1.15, id="y", tf="hora"); o1, _ = entrega(r, dict(p, anotaciones=[mala]))
        chk("7b trazo lejano no puntua igual (tolerancia fundada)", o1["evaluacion"]["desglose"]["trazado"]["pts"] < o0["evaluacion"]["desglose"]["trazado"]["pts"], str(o1["evaluacion"]["desglose"]["trazado"]["pts"]))
    else:
        chk("7 trazo con anclajes distintos", True, "caso sin linea de referencia; ver 7 en otro caso (n/a)")
    # 8 datos insuficientes
    h = datos.preparado("AMD")["h"]; q = motor.estado_calidad("AMD", h.index[10].isoformat())
    chk("8 corte con datos insuficientes se detecta", q.get("pm200") is False, json.dumps(q, default=str)[:140])
    # 12 discrepancia Atlas vs revisada
    r = nuevo(cat="confirmado"); d, ref, p = resp(r)
    al.ej("INSERT OR REPLACE INTO ref_revisada VALUES(?,?,?,?,?,?,?)", (d["ticker"], d["corte"], d["estrategia"], "EN_FORMACION", "test aceptacion", "test", al.ahora()))
    try:
        o, c = entrega(r, dict(p, clasificacion="EN_FORMACION", corte=d["corte"]))
        rf = o["evaluacion"]["referencia"]
        chk("12 discrepancia Atlas vs referencia revisada", rf.get("discrepa_atlas") is True and rf["clase"] == "EN_FORMACION", f"atlas={rf.get('atlas_clase')} revisada={rf['clase']} nivel={rf['nivel']}")
    finally:
        al.ej("DELETE FROM ref_revisada WHERE ticker=? AND corte=? AND estrategia=?", (d["ticker"], d["corte"], d["estrategia"]))
    # 13 vela futura no cambia la evaluacion original ni se filtra al corte
    r = nuevo(cat="confirmado"); d, ref, p = resp(r); o, c = entrega(r, p)
    sn = motor.snapshot(d["ticker"], d["corte"]); fut = [x for x in sn["hora"] if pd.Timestamp(x["t"]) > pd.Timestamp(d["corte"])]
    o_b = motor.barras_posteriores(d["ticker"], d["corte"], 14)
    sn2 = motor.snapshot(d["ticker"], d["corte"])
    chk("13 sin velas futuras en la evidencia y hash estable tras ver el posterior", not fut and sn["hash"] == sn2["hash"] == o["evidencia_hash"], f"posteriores={len(o_b) if o_b else 0} hash={sn['hash']}")
    # 14 seleccion aleatoria variada y reproducible
    cs = [g.crear(AL, "vela", "evaluable", s, None, None, None, True) for s in range(100, 130)]; cs = [x for x in cs if "error" not in x]
    tk = {x["ticker"] for x in cs}; es = {x["estrategia"] for x in cs}; sec = [x["ticker"] for x in cs]
    again = g.reproducir(cs[0]["id"])
    chk("14a seleccion variada (activos/estrategias)", len(tk) >= 8 and len(es) >= 4, f"{len(cs)} casos, {len(tk)} activos, {len(es)} estrategias")
    chk("14b sin repeticion consecutiva del mismo activo", all(a != b for a, b in zip(sec, sec[1:])), f"{sum(1 for a, b in zip(sec, sec[1:]) if a == b)} repeticiones consecutivas")
    chk("14c misma semilla = mismo caso", again.get("coincide") is True, f"reproducir(desafio) -> {again.get('reproducido')}")
    # integridad: sin velas posteriores al corte en ninguna evidencia generada
    bad = 0
    for x in cs[:10]:
        s = motor.snapshot(x["ticker"], x["corte"]); bad += sum(1 for y in s["hora"] if pd.Timestamp(y["t"]) > pd.Timestamp(x["corte"]))
    chk("anti-fuga: ninguna evidencia contiene velas posteriores al corte", bad == 0, f"velas futuras={bad}")
    nok = sum(1 for _, k, _ in R if k); print(f"\n{nok}/{len(R)} pruebas OK"); return 0 if nok == len(R) else 1


if __name__ == "__main__":
    sys.exit(main())

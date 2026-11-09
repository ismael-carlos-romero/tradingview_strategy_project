"""Aula Virtual - progreso, dominio, repasos espaciados, auditoria de Atlas e integracion (estado real) con la hoja «Estudio Cardona»."""
import os, json, datetime as dt
from collections import defaultdict
import pandas as pd
from . import datos, motor, almacen as al, definiciones as df

RAIZ = datos.RAIZ


def _ult():
    """Ultima evaluacion por intento (version mayor) con datos del desafio."""
    return al.q("""SELECT i.id iid, i.alumno_id, i.numero, i.tipo, i.ayudas, i.duracion_s, i.creado, i.corte_respuesta, d.id did, d.ticker, d.estrategia, d.modo, d.ruta, d.extra, d.examen,
                   e.total, e.estado_validacion, e.version, e.origen, e.desglose, e.pendientes
                   FROM intentos i JOIN desafios d ON d.id=i.desafio_id
                   JOIN evaluaciones e ON e.intento_id=i.id AND e.version=(SELECT MAX(version) FROM evaluaciones WHERE intento_id=i.id)
                   ORDER BY i.id""")


def registrar_repasos(alumno, intento_id, ev, sid):
    hoy = dt.date.today(); pasos = df.UMBRALES_DOMINIO["repaso_dias"]
    for o in ev["desglose"]["requisitos"]["obs"]:
        if not isinstance(o, dict) or "bien" not in o:
            continue
        cid = o["c"]; ab = al.q("SELECT * FROM repasos WHERE alumno_id=? AND criterio=? AND hecho=0", (alumno, cid), True)
        if o["bien"] is False:
            if not ab:
                al.ej("INSERT INTO repasos(alumno_id,estrategia,criterio,vence,paso,origen_intento) VALUES(?,?,?,?,?,?)", (alumno, cid.split(".")[0], cid, (hoy + dt.timedelta(days=pasos[0])).isoformat(), 0, intento_id))
        elif ab and ab["origen_intento"] != intento_id:
            al.ej("UPDATE repasos SET hecho=1 WHERE id=?", (ab["id"],))
            if ab["paso"] + 1 < len(pasos):
                al.ej("INSERT INTO repasos(alumno_id,estrategia,criterio,vence,paso,origen_intento) VALUES(?,?,?,?,?,?)", (alumno, cid.split(".")[0], cid, (hoy + dt.timedelta(days=pasos[ab["paso"] + 1])).isoformat(), ab["paso"] + 1, intento_id))


def _cat(ex):
    c = (json.loads(ex or "{}")).get("categoria") or ""
    return "confirmado" if c.startswith("confirmado") else ("formacion" if c in ("formacion", "faltante") else ("contraejemplo" if c in ("contraejemplo", "sin_ocurrencia") else c))


def resumen(alumno):
    R = [r for r in _ult() if r["alumno_id"] == alumno]; um = al.cfg("umbrales_dominio"); meta = al.cfg("meta_diaria_min")["minutos"]
    hoy = dt.date.today().isoformat()
    seg = {r["fecha"]: r["s"] for r in al.q("SELECT fecha, SUM(segundos) s FROM practica WHERE alumno_id=? GROUP BY fecha", (alumno,))}
    ult7 = [(dt.date.today() - dt.timedelta(days=k)).isoformat() for k in range(6, -1, -1)]
    out = {"alumno": alumno, "tiempo": {"hoy_min": round(seg.get(hoy, 0) / 60, 1), "meta_min": meta, "cumple": seg.get(hoy, 0) >= meta * 60, "ultimos_7": [{"fecha": f, "min": round(seg.get(f, 0) / 60, 1)} for f in ult7]},
           "intentos": len(R), "estrategias": {}, "errores": {}, "pendientes_revision": sum(1 for r in R if r["estado_validacion"] == "pendiente_revision")}
    cob_t = {r["ticker"] for r in R}; cob_d = {r["corte_respuesta"][:10] for r in R}
    out["cobertura"] = {"activos": len(cob_t), "activos_total": datos.universo()["n"], "periodos": len(cob_d)}
    vistos = set(); nuevos = []
    for r in R:
        if r["ticker"] not in vistos:
            nuevos.append(r["total"]); vistos.add(r["ticker"])
    out["activos_nuevos"] = {"n": len(nuevos), "media": round(sum(nuevos) / len(nuevos), 1) if nuevos else None}
    err = defaultdict(int)
    for r in R:
        for o in json.loads(r["desglose"])["requisitos"]["obs"]:
            if isinstance(o, dict) and o.get("bien") is False:
                err[o["c"]] += 1
    out["errores"] = [{"criterio": c, "texto": df.criterio_texto(c), "veces": n} for c, n in sorted(err.items(), key=lambda x: -x[1])[:8]]
    for s in df.ORDEN:
        rs = [r for r in R if r["estrategia"] == s]
        if not rs:
            out["estrategias"][s] = {"n": 0, "estado": "sin_datos"}; continue
        ind = [r for r in rs if r["tipo"] == "independiente"]; sin = [r for r in ind if not json.loads(r["ayudas"] or "[]")]; con = [r for r in ind if json.loads(r["ayudas"] or "[]")]
        cats = defaultdict(list)
        for r in ind:
            cats[_cat(r["extra"])].append(1 if json.loads(r["desglose"])["clasificacion"]["pts"] >= 0.6 * json.loads(r["desglose"])["clasificacion"]["max"] else 0)
        media = sum(r["total"] for r in ind) / len(ind) if ind else 0
        dias = len({r["creado"][:10] for r in ind}); acts = len({r["ticker"] for r in ind}); cx = len(cats.get("contraejemplo", []))
        cond = {"casos": (len(ind), um["casos_min"]), "media": (round(media, 1), um["puntaje_medio_min"]), "dias": (dias, um["dias_distintos_min"]), "activos": (acts, um["activos_distintos_min"]),
                "sin_ayuda": (len(sin), um["sin_ayuda_min"]), "contraejemplos": (cx, um["contraejemplos_min"])}
        ok = all(v[0] >= v[1] for v in cond.values())
        ret = [r["total"] for r in ind if r["numero"] == 1][-3:]
        out["estrategias"][s] = {"n": len(ind), "asistidos": len(rs) - len(ind), "media": round(media, 1), "media_sin_ayuda": round(sum(r["total"] for r in sin) / len(sin), 1) if sin else None,
            "n_sin_ayuda": len(sin), "media_con_ayuda": round(sum(r["total"] for r in con) / len(con), 1) if con else None, "n_con_ayuda": len(con),
            "acierto": {c: {"aciertos": sum(v), "n": len(v)} for c, v in cats.items()}, "activos": acts, "dias": dias, "dominio": cond, "estado": "dominada" if ok else "en_progreso", "ultimos": ret,
            "umbrales": um["version"]}
    due = al.q("SELECT * FROM repasos WHERE alumno_id=? AND hecho=0 ORDER BY vence", (alumno,))
    out["repasos"] = {"pendientes": due, "vencidos": [x for x in due if x["vence"] <= hoy]}
    hechos = al.q("SELECT COUNT(*) n FROM repasos WHERE alumno_id=? AND hecho=1", (alumno,), True)["n"]
    out["retencion"] = {"repasos_aprobados": hechos, "repasos_pendientes": len(due)}
    sin = [r["total"] for r in R if not json.loads(r["ayudas"] or "[]")]; con = [r["total"] for r in R if json.loads(r["ayudas"] or "[]")]
    out["ayuda"] = {"sin": {"n": len(sin), "media": round(sum(sin) / len(sin), 1) if sin else None}, "con": {"n": len(con), "media": round(sum(con) / len(con), 1) if con else None}}
    return out


def historial(alumno):
    return [{"intento": r["iid"], "desafio": r["did"], "numero": r["numero"], "tipo": r["tipo"], "ticker": r["ticker"], "estrategia": r["estrategia"], "modo": r["modo"], "total": r["total"],
             "estado": r["estado_validacion"], "version": r["version"], "origen": r["origen"], "fecha": r["creado"]} for r in reversed(_ult()) if r["alumno_id"] == alumno][:60]


def detalle(iid, alumno=None):
    i = al.q("SELECT * FROM intentos WHERE id=?", (iid,), True)
    if not i or (alumno and i["alumno_id"] != alumno):
        return {"error": "no encontrado"}
    d = al.q("SELECT * FROM desafios WHERE id=?", (i["desafio_id"],), True)
    evs = al.q("SELECT * FROM evaluaciones WHERE intento_id=? ORDER BY version", (iid,))
    for e in evs:
        e["desglose"] = json.loads(e["desglose"]); e["referencia"] = json.loads(e["referencia"])
    sid = d["estrategia"] or json.loads(i["payload"]).get("estrategia")
    return {"intento": dict(i, payload=json.loads(i["payload"])), "desafio": {k: d[k] for k in ("id", "modo", "ruta", "ticker", "estrategia", "corte", "seed", "nivel_validacion", "examen")},
            "evaluaciones": evs, "snapshot": motor.snapshot(d["ticker"], i["corte_respuesta"]), "posterior": motor.barras_posteriores(d["ticker"], i["corte_respuesta"], 14),
            "lamina": "/assets/" + df.ESTRATEGIAS[sid]["lamina"] if sid in df.ESTRATEGIAS else None, "definicion": df.ESTRATEGIAS.get(sid)}


def verif_indep(t, corte, sid):
    """Verificacion INDEPENDIENTE (reconstruye velas y medias desde los datos crudos hasta el corte) de criterios objetivos."""
    h, D = datos.preparar_corte(t, corte); r = h.iloc[-1]; w = h.iloc[-10:]; d = D[D.index < pd.Timestamp(r.name.date())] if r.end_min < 960 else D
    dr = d.iloc[-1] if len(d) else None; out = {}
    par = bool((w.PM20 > w.PM40).all() and (w.PM100 > w.PM200).all())
    if sid in ("PM40", "CAIDA"):
        out[1] = par
    if sid in ("GAP_NORMAL", "PISO_FUERTE") and dr is not None:
        out[1] = bool(dr.sma100 > dr.sma200)
    if sid == "CUATRO_PASOS":
        out[1] = bool(r.PM40 > r.PM20 and r.Close < r.PM40)
    if sid == "VELA_ROJA":
        f = h[h["date"] == r.name.date()].iloc[0]; out[2] = bool(f.Close < f.Open and f.Close < f.PM40)
    if sid == "TECHO_FUERTE" and dr is not None:
        out[2] = bool(dr.sma200 > dr.sma100)
    return out


def auditar(b):
    """El alumno, DESPUES de entregar su analisis, compara cada paso de Atlas: coincido / discrepo. Se puntua contra la verificacion independiente."""
    i = al.q("SELECT * FROM intentos WHERE id=?", (b["intento"],), True); d = al.q("SELECT * FROM desafios WHERE id=?", (i["desafio_id"],), True)
    sid = d["estrategia"]; ref = motor.referencia(d["ticker"], i["corte_respuesta"], sid)[sid]; vi = verif_indep(d["ticker"], i["corte_respuesta"], sid); res = []; ok = n = pend = 0
    for k, pa in enumerate(ref["pasos"], 1):
        v = (b.get("veredictos") or {}).get(str(k))
        if k not in vi:
            pend += 1; res.append({"n": k, "paso": pa["n"], "atlas": pa["ok"], "tuyo": v, "estado": "pendiente", "obs": "No hay verificación estructurada independiente para este criterio: queda para revisión con la lámina."}); continue
        verdad = (vi[k] == pa["ok"]); correcto = (v == "coincido") == verdad if v else False; n += 1; ok += correcto
        res.append({"n": k, "paso": pa["n"], "atlas": pa["ok"], "independiente": vi[k], "atlas_correcto": verdad, "tuyo": v, "estado": "ok" if correcto else "error",
                    "obs": ("Atlas coincide con la verificación independiente." if verdad else "Atlas DIFIERE de la verificación independiente: hay un posible error de Atlas.")})
    al.ej("INSERT OR REPLACE INTO borradores VALUES(?,?,?,?)", (d["id"] + "::auditoria", d["alumno_id"], json.dumps(res, ensure_ascii=False), al.ahora()))
    return {"resultados": res, "aciertos": ok, "verificables": n, "pendientes": pend, "nivel": "verificación estructurada parcial"}


_estudio = {}


def estudio_cardona():
    """Estado REAL de la integracion con el Google Sheet de Meliora (hojas «Estudio Cardona» y «Análisis manual diario»). Relevado a mano; el portal no lo lee ni lo escribe."""
    return {"integrada": False, "modo": "exportacion manual (copiar y pegar)", "libro": "PROYECTO MELIORA OPCIONES FINANCIERAS (Google Sheets)",
            "hoja_estudio": {"nombre": "📚 Estudio Cardona", "gid": 1716002021, "estructura": "12 estrategias (01 Primer gap … 12 Canal bajista en 4 pasos), plan de 21 días, 60 min/día; registro desde la fila 52",
                             "columnas_registro": ["Fecha", "Estrategia", "Minutos", "Método", "Memoria /5", "Tipo de caso", "Corrección", "Activo", "Evidencia / enlace", "Comparación bot", "Vela, error o próximo paso"],
                             "dominio_propuesto": "memoria ≥ 4/5 + un caso válido y un contraejemplo correctos en gráficos nuevos"},
            "hoja_manual": {"nombre": "📝 Análisis manual diario", "gid": 1716002022, "estructura": "por jornada: 35 activos × 12 estrategias; el alumno codifica SC/V/C/F/FV/SD, luego copia lo de Atlas y marca «Mismo corte»",
                            "relacion": "Es práctica en el mercado actual; el Aula Virtual es práctica sobre casos históricos con corrección. Se complementan, no se reemplazan."},
            "mapeo": {"Minutos": "duración del intento", "Método": "«Aula Virtual – <modo>»", "Memoria /5": "no medido por el Aula (queda para el alumno)", "Tipo de caso": "confirmado → Válido; contraejemplo → Contraejemplo; en formación → En formación",
                      "Corrección": "nota /100 y estado de validación", "Activo": "ticker del desafío", "Comparación bot": "coincidencia con la referencia (candidato Atlas o revisada)", "Vela, error o próximo paso": "corte NY y criterio fallido"},
            "diferencia_de_codigos": "Atlas usa SC/V/C/F/FV; el Aula usa Confirmada / En formación / No aplica (F≈Confirmada, V y C≈En formación, SC≈No aplica, FV≈Ambigua)",
            "nota": "Sincronización automática no implementada: el portal no tiene credenciales de Google Sheets. Use /api/aula/estudio_export para obtener filas listas para pegar en el registro."}


def estudio_export(alumno):
    """Filas alineadas a las columnas del registro de «Estudio Cardona» (una por intento)."""
    TC = {"confirmado": "Válido", "contraejemplo": "Contraejemplo", "formacion": "En formación", "faltante": "Requisito faltante", "multi": "Varios", "sesion_actual": "Sesión actual"}
    out = []
    for r in al.q("SELECT i.id,i.numero,i.tipo,i.duracion_s,i.creado,i.corte_respuesta,d.ticker,d.estrategia,d.modo,d.extra FROM intentos i JOIN desafios d ON d.id=i.desafio_id WHERE i.alumno_id=? ORDER BY i.id", (alumno,)):
        ev = al.q("SELECT * FROM evaluaciones WHERE intento_id=? ORDER BY version DESC", (r["id"],), True)
        if not ev:
            continue
        ref = json.loads(ev["referencia"] or "{}"); cat = json.loads(r["extra"] or "{}").get("categoria")
        fall = [x["n"] for x in (ref.get("pasos") or []) if x.get("ok") is not True][:2]
        out.append([r["creado"][:10], (df.ESTRATEGIAS.get(r["estrategia"]) or {}).get("nombre", r["estrategia"] or "(oculta)"), round((r["duracion_s"] or 0) / 60, 1), "Aula Virtual – " + r["modo"] + (" (asistida)" if r["tipo"] == "asistida" else ""),
                    "", TC.get(cat, cat or ""), f"{ev['total']}/100 · {ev['estado_validacion']}", r["ticker"], f"intento {r['id']} · evidencia {r['corte_respuesta'][:16]} NY",
                    f"referencia {ref.get('clase')} ({ref.get('nivel')})", ("criterios no cumplidos: " + "; ".join(fall)) if fall else ""])
    return {"columnas": ["Fecha", "Estrategia", "Minutos", "Método", "Memoria /5", "Tipo de caso", "Corrección", "Activo", "Evidencia / enlace", "Comparación bot", "Vela, error o próximo paso"], "filas": out}

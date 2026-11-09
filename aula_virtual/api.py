"""Aula Virtual - API HTTP (se engancha en live_scanner.BotControlServer: if self.path.startswith('/api/aula/'): ...)."""
import os, json, base64, threading, datetime as dt, traceback
from urllib.parse import urlparse, parse_qs
import pandas as pd
from . import datos, motor, generador, evaluador, almacen as al, definiciones as df, progreso

AQUI = os.path.dirname(os.path.abspath(__file__))
CAPT = os.path.join(AQUI, "capturas"); os.makedirs(CAPT, exist_ok=True)
al.init()
_tarea = {"estado": "libre", "log": ""}
PISTAS = ["Nivel 1 – Contexto: la estrategia se decide en «{tf}»{contr}. Revisá primero PM20/PM40/PM100/PM200 en esa temporalidad.",
          "Nivel 2 – Requisitos de contexto: mirá los criterios {ctx}.",
          "Nivel 3 – Pendiente: hoy {n_ok} de {n} criterios se cumplen; revisá con atención el criterio n.º {falta}.",
          "Nivel 4 – El criterio que decide el caso es: «{txt}». Ubicalo en el gráfico."]


def _j(h, obj, code=200):
    b = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
    h.send_response(code); h.send_header("Content-Type", "application/json; charset=utf-8"); h.send_header("Cache-Control", "no-store"); h.end_headers(); h.wfile.write(b)


def _body(h):
    n = int(h.headers.get("Content-Length", 0) or 0)
    return json.loads(h.rfile.read(n).decode("utf-8")) if n else {}


def _desafio(did, alumno=None):
    d = al.q("SELECT * FROM desafios WHERE id=?", (did,), True)
    if d and alumno and d["alumno_id"] != alumno:
        return None
    return d


def _publico(d, entregado):
    ex = json.loads(d["extra"] or "{}")
    o = {k: d[k] for k in ("id", "modo", "ruta", "seed", "ticker", "estrategia", "corte", "nivel_validacion", "examen", "estado", "evidencia_hash", "creado", "def_version", "atlas_version")}
    o["tramo"] = ex.get("tramo")
    if d["modo"] == "reconoce" or (d["ruta"] == "exploracion" and d["modo"] == "encontra"):
        o["estrategia"] = None if not entregado else d["estrategia"]
    if entregado:
        o["categoria"] = ex.get("categoria")
    return o


def _entregado(did):
    return bool(al.q("SELECT 1 x FROM intentos WHERE desafio_id=?", (did,), True))


def _cands_tramo(d):
    ex = json.loads(d["extra"] or "{}"); tr = ex.get("tramo") or []
    ix = motor.indice()
    return [f[1] for f in ix["filas"] if f[0] == d["ticker"] and f[2] == d["estrategia"] and f[1][:10] in tr and f[3] == "CONFIRMADA"] if ix else []


def _evaluar_ninguna(d, p):
    """Exploracion libre: el alumno afirma que NINGUNA estrategia aplica. Si Atlas ve alguna posible, la evaluacion queda pendiente."""
    rub = al.cfg("rubrica")["pesos"]; corte = p.get("corte") or d["corte"]; refs = motor.referencia(d["ticker"], corte)
    posibles = {s: r for s, r in refs.items() if r["etapa"] in ("CONFIRMADA", "CASI")}; ok = not posibles
    expl, eobs = evaluador._explicacion(p, {}, ok); desg = {}
    desg["contexto"] = {"pts": float(rub["contexto"]), "max": rub["contexto"], "obs": ["Exploración libre: sin estrategia propuesta, no se evalúa la temporalidad de una estrategia concreta."]}
    desg["requisitos"] = {"pts": float(rub["requisitos"]) if ok else 0.0, "max": rub["requisitos"], "obs": ["Sin estrategia propuesta no hay requisitos que evaluar."]}
    desg["trazado"] = {"pts": float(rub["trazado"]) if ok else 0.0, "max": rub["trazado"], "obs": ["No se exige trazado si ninguna estrategia aplica."]}
    desg["clasificacion"] = {"pts": float(rub["clasificacion"]) if ok else 0.0, "max": rub["clasificacion"], "obs": [
        "Atlas no ve ninguna estrategia en formación o confirmada en este corte: tu descarte coincide." if ok else
        "Atlas ve posibles estrategias en este corte (" + ", ".join(df.ESTRATEGIAS[s]["nombre"] + " [" + r["clase"] + "]" for s, r in posibles.items()) + "): no se puede confirmar tu descarte → pendiente de revisión."]}
    desg["explicacion"] = {"pts": expl, "max": rub["explicacion"], "obs": eobs + ["Método: heurística de texto."], "metodo": "heuristica_texto"}
    pend = 0.0 if ok else float(rub["clasificacion"] + rub["requisitos"] + rub["trazado"])
    return {"total": round(sum(v["pts"] for v in desg.values()), 1), "desglose": desg, "pendiente_pts": pend, "estado_validacion": "automatica" if ok else "pendiente_revision",
            "referencia": {"clase": "NO_APLICA" if ok else "AMBIGUA", "etapa": "SIN_CONTEXTO", "nivel": motor.NIVEL_REF, "pasos": [], "draw": [], "ventana": "", "ventana_ok": False, "corte": corte,
                           "todas": {s: {"clase": r["clase"], "etapa": r["etapa"]} for s, r in refs.items()}}, "estrategia": "NINGUNA", "rubrica": al.cfg("rubrica")["version"], "def_version": df.VERSION,
            "acierto_clase": ok}


def _evaluar(d, p):
    modo = d["modo"]
    if p.get("estrategia") == "NINGUNA":
        return _evaluar_ninguna(d, p)
    if modo == "encontra" and p.get("descarte"):
        S = _cands_tramo(d)
        p = dict(p, clasificacion="NO_APLICA", corte=d["corte"])
        ev = evaluador.evaluar(d, p)
        if S:
            ev["desglose"]["clasificacion"]["obs"].insert(0, f"Había al menos una ocurrencia confirmada en el tramo (p. ej. {S[0][:16].replace('T', ' ')}): el descarte no es correcto.")
            ev["desglose"]["clasificacion"]["pts"] = 0.0
            ev["total"] = round(sum(v["pts"] for v in ev["desglose"].values()), 1); ev["acierto_clase"] = False
        else:
            ev["desglose"]["clasificacion"]["obs"].insert(0, "Descarte correcto: en las 3 sesiones del tramo ninguna vela cierra con la estrategia confirmada.")
            ev["desglose"]["clasificacion"]["pts"] = float(ev["desglose"]["clasificacion"]["max"])
            ev["desglose"]["requisitos"]["pts"] = float(ev["desglose"]["requisitos"]["max"]); ev["desglose"]["trazado"]["pts"] = float(ev["desglose"]["trazado"]["max"])
            ev["total"] = round(sum(v["pts"] for v in ev["desglose"].values()), 1); ev["acierto_clase"] = True
        return ev
    if modo == "reconoce":
        return _evaluar_reconoce(d, p)
    ev = evaluador.evaluar(d, p)
    if modo == "faltante" and "error" not in ev and p.get("marcador"):
        h = datos.preparado(d["ticker"])["h"]; i = int(h.index.get_loc(pd.Timestamp(p.get("corte") or d["corte"])))
        j = int(h.index.searchsorted(pd.Timestamp(p["marcador"]["t"])))
        ev["desglose"]["clasificacion"]["obs"].append("Marcaste el punto sobre el gráfico " + ("cerca de la vela evaluada ✔" if abs(j - i) <= 3 else "lejos de la vela evaluada (±3 velas) ✘"))
    return ev


def _evaluar_reconoce(d, p):
    hip = p.get("hipotesis") or []
    if not hip:
        return {"error": "Marcá al menos una estrategia que podría aplicar (o «ninguna» con un motivo)."}
    refs = motor.referencia(d["ticker"], p.get("corte") or d["corte"])
    aplica = {s: r for s, r in refs.items() if r["etapa"] in ("CONFIRMADA", "CASI")}
    mias = {x["sid"] for x in hip}; tp = len(mias & set(aplica)); prec = tp / max(1, len(mias)); rec = tp / max(1, len(aplica)) if aplica else (1.0 if not mias else 0.0)
    f1 = 0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    prim = dict(p, estrategia=hip[0]["sid"], clasificacion=hip[0].get("estado"), condicion_faltante=hip[0].get("faltante"),
                requisitos=hip[0].get("requisitos") or [], faltantes=hip[0].get("faltantes") or [])
    ev = evaluador.evaluar(d, prim)
    if "error" in ev:
        return ev
    rub = al.cfg("rubrica")["pesos"]
    ev["desglose"]["contexto"] = {"pts": round(rub["contexto"] * f1, 1), "max": rub["contexto"], "obs": [f"Estrategias que podrían aplicar según la referencia: {', '.join(df.ESTRATEGIAS[s]['nombre'] for s in aplica) or 'ninguna'}. Tus hipótesis: {', '.join(df.ESTRATEGIAS[s]['nombre'] for s in mias)}. Precisión {prec:.0%}, cobertura {rec:.0%}."]}
    ok = 0; obs = []
    for x in hip:
        r = refs[x["sid"]]; c_ok = (r["clase"] == x.get("estado")); ok += c_ok
        obs.append(f"{df.ESTRATEGIAS[x['sid']]['nombre']}: dijiste «{x.get('estado')}», la referencia es «{r['clase']}» (se evalúa con sus propios requisitos) → {'✔' if c_ok else '✘'}")
    ev["desglose"]["clasificacion"] = {"pts": round(rub["clasificacion"] * ok / len(hip), 1), "max": rub["clasificacion"], "obs": obs}
    ev["total"] = round(sum(v["pts"] for v in ev["desglose"].values()), 1); ev["acierto_clase"] = ok == len(hip)
    ev["referencia"]["todas"] = {s: {"clase": r["clase"], "etapa": r["etapa"]} for s, r in refs.items()}
    return ev


def entregar(b):
    d = _desafio(b["desafio"], b.get("alumno"))
    if not d:
        return {"error": "Desafío no encontrado para este alumno."}, 404
    p = b.get("payload") or {}
    corte = p.get("corte") or d["corte"]
    if pd.Timestamp(corte) < pd.Timestamp(d["corte"]) and d["modo"] != "encontra":
        return {"error": "El corte de respuesta no puede ser anterior al corte inicial."}, 400
    previos = al.q("SELECT COUNT(*) n FROM intentos WHERE desafio_id=?", (d["id"],), True)["n"]
    tipo = "independiente" if previos == 0 else "asistida"
    try:
        ev = _evaluar(d, p)
    except Exception as e:
        return {"error": "No se pudo corregir: " + str(e)[:160], "recuperable": True, "detalle": traceback.format_exc()[-400:]}, 500
    if "error" in ev:
        return ev, 400
    cap = p.pop("captura", None); cap_path = None
    if cap and cap.startswith("data:image"):
        cap_path = f"{d['id']}_{previos + 1}.png"
        open(os.path.join(CAPT, cap_path), "wb").write(base64.b64decode(cap.split(",", 1)[1])); p["captura_archivo"] = cap_path
    ev_hash = motor.snapshot(d["ticker"], corte)["hash"]
    aid = al.ej("INSERT INTO intentos(desafio_id,alumno_id,numero,tipo,payload,ayudas,inicio,fin,duracion_s,corte_respuesta,evidencia_hash,creado) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (d["id"], d["alumno_id"], previos + 1, tipo, json.dumps(p, ensure_ascii=False), json.dumps(p.get("ayudas") or []), b.get("inicio"), al.ahora(),
                 int(b.get("duracion_s") or 0), corte, ev_hash, al.ahora()))
    ev["acierto_clase"] = bool(ev.get("acierto_clase", ev["desglose"]["clasificacion"]["pts"] >= 0.6 * ev["desglose"]["clasificacion"]["max"]))
    al.ej("INSERT INTO evaluaciones(intento_id,version,origen,total,desglose,estado_validacion,pendientes,referencia,rubrica_version,def_version,autor,motivo,creada) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (aid, 1, "automatica", ev["total"], json.dumps(ev["desglose"], ensure_ascii=False), ev["estado_validacion"], ev["pendiente_pts"], json.dumps(ev["referencia"], ensure_ascii=False, default=str),
           ev["rubrica"], ev["def_version"], "aula-autocorreccion", "evaluación automática inicial", al.ahora()))
    al.ej("UPDATE desafios SET estado='entregado' WHERE id=?", (d["id"],))
    al.ej("INSERT INTO practica(alumno_id,fecha,segundos) VALUES(?,?,?)", (d["alumno_id"], dt.date.today().isoformat(), int(b.get("duracion_s") or 0)))
    progreso.registrar_repasos(d["alumno_id"], aid, ev, d["estrategia"] or ev["estrategia"])
    ex = json.loads(d["extra"] or "{}")
    return {"intento_id": aid, "numero": previos + 1, "tipo": tipo, "evaluacion": ev, "evidencia_hash": ev_hash,
            "revelado": {"lamina": ("/assets/" + df.ESTRATEGIAS[ev["estrategia"]]["lamina"]) if ev["estrategia"] in df.ESTRATEGIAS else None,
                         "definicion": df.ESTRATEGIAS.get(ev["estrategia"]), "categoria": ex.get("categoria"),
                         "posterior": motor.barras_posteriores(d["ticker"], corte, 14), "snapshot_hash_al_responder": ev_hash}}, 200


def revision_resolver(b):
    """Rectificar una calificacion: nueva version 'revisada' (la automatica se conserva)."""
    ev = al.q("SELECT * FROM evaluaciones WHERE intento_id=? ORDER BY version DESC", (b["intento"],), True)
    if not ev:
        return {"error": "Intento sin evaluación."}, 404
    desg = json.loads(ev["desglose"])
    for k_, v in (b.get("puntos") or {}).items():
        if k_ in desg:
            desg[k_]["pts"] = max(0.0, min(float(v), desg[k_]["max"])); desg[k_]["revisado"] = True
    total = round(sum(v["pts"] for v in desg.values()), 1) if b.get("puntos") else (b.get("total", ev["total"]))
    al.ej("INSERT INTO evaluaciones(intento_id,version,origen,total,desglose,estado_validacion,pendientes,referencia,rubrica_version,def_version,autor,motivo,creada) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (b["intento"], ev["version"] + 1, "revisada", total, json.dumps(desg, ensure_ascii=False), "revisada", 0, ev["referencia"], ev["rubrica_version"], ev["def_version"], b.get("autor", "tutor"), b.get("motivo", ""), al.ahora()))
    al.ej("UPDATE revisiones SET estado='resuelta', respuesta=? WHERE intento_id=? AND estado='solicitada'", (b.get("motivo", ""), b["intento"]))
    return {"ok": True, "version": ev["version"] + 1, "total_anterior": ev["total"], "total_nuevo": total}, 200


def _refrescar_async():
    if _tarea["estado"] == "corriendo":
        return
    def run():
        _tarea.update(estado="corriendo", log="descargando velas…")
        try:
            r = datos.refrescar(); _tarea["log"] = f"datos ok={len(r['ok'])} error={r['error']}; reconstruyendo índice…"
            m = motor.construir_indice(workers=8); _tarea.update(estado="listo", log=f"índice reconstruido: {m['n']} evaluaciones")
        except Exception as e:
            _tarea.update(estado="error", log=str(e)[:200])
    threading.Thread(target=run, daemon=True).start()


def manejar(h, metodo):
    u = urlparse(h.path); ruta = u.path; q = {k: v[0] for k, v in parse_qs(u.query).items()}
    try:
        if metodo == "GET":
            if ruta == "/api/aula/estado":
                uni = datos.universo(); est = [datos.estado(t) for t in uni["tickers"]]; ix = motor.indice()
                return _j(h, {"universo": uni, "datos": est, "indice": (ix or {}).get("meta"), "def_version": df.VERSION, "atlas": motor.VER_ATLAS, "tarea": _tarea,
                              "rubrica": al.cfg("rubrica"), "umbrales": al.cfg("umbrales_dominio"), "meta": al.cfg("meta_diaria_min"), "laminas_sin_detector": df.LAMINAS_SIN_DETECTOR,
                              "limitaciones": ["Yahoo entrega 30m solo ~60 sesiones; el cache es acumulativo y crece con cada refresco.", "La referencia es un candidato de Atlas (nivel «atlas_automatico»), no una revisión humana.",
                                               "El portal tiene una sola clave de administrador: el progreso se aísla por perfil de alumno, no por login."]})
            if ruta == "/api/aula/estrategias":
                return _j(h, {"version": df.VERSION, "estrategias": [df.ESTRATEGIAS[s] for s in df.ORDEN], "cobertura": generador.cobertura(), "laminas_sin_detector": df.LAMINAS_SIN_DETECTOR})
            if ruta == "/api/aula/desafio":
                d = _desafio(q["id"], q.get("alumno"))
                if not d:
                    return _j(h, {"error": "no encontrado"}, 404)
                ent = _entregado(d["id"]); b = al.q("SELECT estado FROM borradores WHERE desafio_id=? AND alumno_id=?", (d["id"], d["alumno_id"]), True)
                return _j(h, {"desafio": _publico(d, ent), "snapshot": motor.snapshot(d["ticker"], d["corte"]), "borrador": json.loads(b["estado"]) if b else None, "entregado": ent})
            if ruta == "/api/aula/avanzar":
                d = _desafio(q["id"], q.get("alumno"))
                h_ = datos.preparado(d["ticker"])["h"]; i0 = int(h_.index.get_loc(pd.Timestamp(d["corte"])))
                pos = int(q.get("paso", 1))
                if i0 + pos >= len(h_) or not bool(motor.estado_calidad(d["ticker"], h_.index[i0 + pos].isoformat())["corte_contiguo"]) or h_.index[i0 + pos].date() != h_.index[i0].date():
                    return _j(h, {"error": "No hay más velas disponibles de esta sesión para revelar.", "fin": True}, 200)
                if d["examen"] and _entregado(d["id"]):
                    return _j(h, {"error": "Examen entregado: las velas posteriores pertenecen al análisis posterior."}, 403)
                return _j(h, {"snapshot": motor.snapshot(d["ticker"], h_.index[i0 + pos].isoformat()), "corte": h_.index[i0 + pos].isoformat()})
            if ruta == "/api/aula/pista":
                d = _desafio(q["id"], q.get("alumno"))
                if d["examen"]:
                    return _j(h, {"error": "Modo examen: las pistas no están disponibles."}, 403)
                sid = d["estrategia"] or q.get("sid"); r = motor.referencia(d["ticker"], d["corte"], sid)[sid]; n = int(q.get("nivel", 1)); de = df.ESTRATEGIAS[sid]
                pasos = r["pasos"]; falta = next((k for k, pa in enumerate(pasos, 1) if pa["ok"] is not True), len(pasos))
                tx = [PISTAS[0].format(tf=de["tf_decision"], contr=(" y contrastá con " + "/".join(de["tf_contraste"]) if de["tf_contraste"] else "")),
                      PISTAS[1].format(ctx=", ".join(str(k) for k in range(1, de["n_ctx"] + 1))),
                      PISTAS[2].format(n_ok=sum(1 for pa in pasos if pa["ok"] is True), n=len(pasos), falta=falta),
                      PISTAS[3].format(txt=de["criterios"][falta - 1]["texto"])][min(max(n, 1), 4) - 1]
                return _j(h, {"nivel": n, "pista": tx})
            if ruta == "/api/aula/progreso":
                return _j(h, progreso.resumen(q["alumno"]))
            if ruta == "/api/aula/intentos":
                return _j(h, progreso.historial(q["alumno"]))
            if ruta == "/api/aula/intento":
                return _j(h, progreso.detalle(int(q["id"]), q.get("alumno")))
            if ruta == "/api/aula/reproducir":
                return _j(h, generador.reproducir(q["id"]))
            if ruta == "/api/aula/sesion":
                return _j(h, datos.estado_sesion(q["ticker"]))
            if ruta == "/api/aula/repasos":
                return _j(h, al.q("SELECT * FROM repasos WHERE alumno_id=? ORDER BY vence", (q["alumno"],)))
            if ruta == "/api/aula/revisiones":
                return _j(h, al.q("SELECT * FROM revisiones ORDER BY id DESC LIMIT 100"))
            if ruta == "/api/aula/estudio_export":
                return _j(h, progreso.estudio_export(q["alumno"]))
            if ruta == "/api/aula/estudio":
                return _j(h, progreso.estudio_cardona())
        else:
            b = _body(h)
            if ruta == "/api/aula/desafio" and b.get("modo") == "sesion":
                r = generador.crear_sesion(b.get("alumno", "alumno1"), b.get("ticker"), b.get("estrategia"), b.get("examen", True), b.get("refrescar", True))
                return _j(h, r, 400 if "error" in r else 200)
            if ruta == "/api/aula/desafio":
                r = generador.crear(b.get("alumno", "alumno1"), b.get("modo", "vela"), b.get("ruta", "evaluable"), b.get("seed"), b.get("estrategia"), b.get("ticker"),
                                    b.get("categoria"), b.get("examen", True))
                return _j(h, r, 400 if "error" in r else 200)
            if ruta == "/api/aula/borrador":
                al.ej("INSERT OR REPLACE INTO borradores VALUES(?,?,?,?)", (b["desafio"], b["alumno"], json.dumps(b["estado"], ensure_ascii=False), al.ahora()))
                return _j(h, {"ok": True})
            if ruta == "/api/aula/entregar":
                r, c = entregar(b); return _j(h, r, c)
            if ruta == "/api/aula/pulso":
                al.ej("INSERT INTO practica(alumno_id,fecha,segundos) VALUES(?,?,?)", (b["alumno"], dt.date.today().isoformat(), int(b.get("segundos", 0)))); return _j(h, {"ok": True})
            if ruta == "/api/aula/revision":
                rid = al.ej("INSERT INTO revisiones(intento_id,alumno_id,motivo,estado,creada) VALUES(?,?,?,?,?)", (b["intento"], b["alumno"], b.get("motivo", ""), "solicitada", al.ahora()))
                return _j(h, {"ok": True, "id": rid})
            if ruta == "/api/aula/revision/resolver":
                r, c = revision_resolver(b); return _j(h, r, c)
            if ruta == "/api/aula/ref_revisada":
                al.ej("INSERT OR REPLACE INTO ref_revisada VALUES(?,?,?,?,?,?,?)", (b["ticker"], b["corte"], b["estrategia"], b["clase"], b.get("nota", ""), b.get("autor", "tutor"), al.ahora()))
                return _j(h, {"ok": True})
            if ruta == "/api/aula/config":
                al.set_cfg(b["clave"], b["valor"]); return _j(h, {"ok": True})
            if ruta == "/api/aula/refrescar":
                _refrescar_async(); return _j(h, _tarea)
            if ruta == "/api/aula/posterior":
                d = _desafio(b["desafio"], b.get("alumno"))
                if not _entregado(d["id"]):
                    return _j(h, {"error": "Entregá primero tu clasificación."}, 403)
                datos.refrescar([d["ticker"]]); n = motor.barras_posteriores(d["ticker"], d["corte"], 30)
                al.ej("INSERT OR REPLACE INTO posterior VALUES(?,?,?)", (d["id"], json.dumps(n), al.ahora()))
                return _j(h, {"posterior": n, "nota": "La clasificación original se conserva con su corte temporal."})
            if ruta == "/api/aula/auditoria":
                return _j(h, progreso.auditar(b))
        return _j(h, {"error": "ruta aula desconocida"}, 404)
    except KeyError as e:
        return _j(h, {"error": f"Falta el dato: {e}", "recuperable": True}, 400)
    except Exception as e:
        return _j(h, {"error": "Error interno recuperable: " + str(e)[:200], "recuperable": True, "detalle": traceback.format_exc()[-500:]}, 500)

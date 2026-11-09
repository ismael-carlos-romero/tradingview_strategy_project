"""Aula Virtual - correccion. Rubrica editable de 100 puntos (rub-1.0.0). Corrige SOLO con lo disponible en el corte de respuesta.
Metodos: estructurado (precio/tiempo/medias/anotaciones) y heuristica de texto (explicacion; incertidumbre alta, marcada).
Los puntos afectados por contradicciones de la lamina, ambiguedad de la referencia o falta de anotaciones estructuradas quedan PENDIENTES."""
import re, json
import numpy as np, pandas as pd
from . import datos, motor, almacen as al, definiciones as df

TOL_ATR = 0.35          # anclaje: distancia maxima al extremo de vela, en ATR(14) hora  (criterio pedagogico inicial)
TOL_PCT = 0.0015        # piso de la tolerancia: 0,15 % del precio
TERMINOS = ["pm20", "pm40", "pm100", "pm200", "línea", "linea", "ruptura", "rompe", "volumen", "vela", "gap", "martillo", "piso", "techo", "canal", "caída",
            "caida", "verde", "roja", "hanger", "paralelo", "tendencia", "cierre", "ventana", "11", "confirm", "falta"]


def _atr(h, i, n=14):
    x = h.iloc[max(0, i - n):i + 1]
    return float((x.High - x.Low).mean())


def _tol(h, i, precio):
    return max(TOL_ATR * _atr(h, i), TOL_PCT * precio)


def ref_en(t, corte, sid):
    """Referencia en el corte de respuesta. Usa la referencia REVISADA si existe (nivel superior a Atlas)."""
    r = motor.referencia(t, corte, sid)[sid]
    rv = al.q("SELECT * FROM ref_revisada WHERE ticker=? AND corte=? AND estrategia=?", (t, corte, sid), True)
    r["nivel"] = motor.NIVEL_REF
    if rv:
        r["atlas_clase"] = r["clase"]; r["clase"] = rv["clase"]; r["nivel"] = "revisada"; r["nota_revision"] = rv["nota"]
        r["discrepa_atlas"] = rv["clase"] != r["atlas_clase"]
    return r


def _estado_c(sid, n):
    for c in df.ESTRATEGIAS[sid]["criterios"]:
        if c["n"] == n:
            return c
    return {"estado": "alineado", "id": f"{sid}.c{n}"}


def _anots(p):
    return [a for a in (p.get("anotaciones") or []) if a.get("tipo") in ("linea", "horizontal", "canal")]


def _linea_ok(h, i, a, tipo):
    """Evalua una linea del alumno: anclajes justificados (extremo de vela cercano) y respeto del criterio (sin cierres que la violen)."""
    t1, t2 = pd.Timestamp(a["t1"]), pd.Timestamp(a.get("t2") or a["t1"])
    if t1 > t2:
        t1, t2, a = t2, t1, dict(a, p1=a["p2"], p2=a["p1"])
    def pos(t):
        j = h.index.searchsorted(t); return int(min(max(j, 0), len(h) - 1))
    j1, j2 = pos(t1), pos(t2)
    if j2 - j1 < 2:
        return {"anclajes": False, "respeta": False, "msg": "La línea une puntos demasiado cercanos (< 3 velas)."}
    col = "High" if tipo in ("caida", "techo") else "Low"
    def ancla(j, p):
        w = h.iloc[max(0, j - 2):min(len(h), j + 3)]; ext = w[col]
        d = float((ext - p).abs().min()); return d <= _tol(h, j, p), d
    (ok1, d1), (ok2, d2) = ancla(j1, a["p1"]), ancla(j2, a["p2"])
    sl = (a["p2"] - a["p1"]) / (j2 - j1)
    viol = 0
    for j in range(j1, i):
        y = a["p1"] + sl * (j - j1); c = float(h.Close.iloc[j])
        if (tipo in ("caida", "techo") and c > y * 1.001) or (tipo == "piso" and c < y * 0.999):
            viol += 1
    respeta = viol <= 1
    pend = sl < 0 if tipo in ("caida", "techo") else sl > 0
    return {"anclajes": bool(ok1 and ok2), "respeta": bool(respeta and (pend or tipo == "piso")), "viol": viol, "d_anclas": [round(d1, 3), round(d2, 3)],
            "pendiente_ok": bool(pend), "msg": ""}


def _trazado(h, i, sid, ref, p):
    """25 puntos. Devuelve (puntos, pendientes_pts, detalle[])."""
    P = df.RUBRICA["pesos"]["trazado"] if False else al.cfg("rubrica")["pesos"]["trazado"]
    det = []
    if p.get("captura") and not _anots(p) and not p.get("anotaciones"):
        return 0.0, P, [{"obs": "Se entregó una captura sin anotaciones estructuradas: el trazado NO es evaluable automáticamente (limitación de capturas). Queda pendiente de revisión.", "pend": True}]
    if ref["clase"] == "NO_APLICA" or not ref["draw"]:
        ok = bool(p.get("descarte_motivo") or p.get("explicacion")) or ref["clase"] != "NO_APLICA"
        det.append({"obs": "La referencia no exige trazados en este corte." + ("" if ok else " Falta justificar el descarte."), "pts": P if ok else 0})
        return float(P if ok else 0), 0.0, det
    req = ref["draw"]; per = P / len(req); tot = 0.0; pend = 0.0
    an = _anots(p)
    for d in req:
        k = d["k"]; contr = any(c["estado"] == "pendiente_revision" for c in df.ESTRATEGIAS[sid]["criterios"] if c["n"] == len(ref["pasos"])) and k == "piso_gap" and sid in ("RUPT_PISO", "VELA_ROJA")
        if d["tipo"] == "horizontal":
            cand = [a for a in an if a["tipo"] == "horizontal"]
            if not cand:
                det.append({"obs": f"Falta la línea horizontal ({k}) cerca de {d['p1']}.", "pts": 0}); continue
            y_ref = d["p1"]; tol = _tol(h, i, y_ref)
            best = min(cand, key=lambda a: abs(a["p1"] - y_ref)); dist = abs(best["p1"] - y_ref)
            ult = h.iloc[max(0, i - 12):i + 1]
            niveles = list(ult.Low) + list(ult.High) + list(np.minimum(ult.Open, ult.Close)) + list(np.maximum(ult.Open, ult.Close))
            if dist <= tol:
                tot += per; det.append({"obs": f"Horizontal en {best['p1']:.2f} coincide con la referencia ({y_ref:.2f}) dentro de ±{tol:.2f}.", "pts": per})
            elif min(abs(best["p1"] - n) for n in niveles) <= tol:
                if contr:
                    pend += per * 0.5; tot += per * 0.5
                    det.append({"obs": f"Horizontal en {best['p1']:.2f} sobre un nivel de vela defendible (no es el de Atlas {y_ref:.2f}). La lámina es ambigua entre cola y cuerpo: queda pendiente.", "pts": per * 0.5, "pend": True})
                else:
                    tot += per * 0.6; det.append({"obs": f"Horizontal en {best['p1']:.2f}: nivel de vela defendible pero distinto de la referencia ({y_ref:.2f}).", "pts": per * 0.6})
            else:
                det.append({"obs": f"Horizontal en {best['p1']:.2f} no corresponde a ningún extremo de vela reciente (referencia {y_ref:.2f}).", "pts": 0})
        else:
            tipo = "piso" if k == "piso" else ("techo" if k in ("caida", "techo") else "caida")
            cand = [a for a in an if a["tipo"] in ("linea", "canal")]
            if not cand:
                det.append({"obs": f"Falta la línea de {'piso' if tipo == 'piso' else 'techo del canal bajista'}.", "pts": 0}); continue
            mejor = None
            for a in cand:
                r_ = _linea_ok(h, i, a, tipo)
                sc = (10 if r_["anclajes"] else 0) + (15 if r_["respeta"] else 0)
                if mejor is None or sc > mejor[0]:
                    mejor = (sc, r_, a)
            sc, r_, a = mejor
            pts = per * (sc / 25.0); tot += pts
            msg = []
            msg.append("anclajes en extremos de vela ✔" if r_["anclajes"] else f"anclajes lejos de los extremos de vela (±{TOL_ATR} ATR) ✘")
            msg.append("la línea respeta el criterio (sin cierres que la violen) ✔" if r_["respeta"] else (f"{r_.get('viol', 0)} cierres violan la línea o la pendiente no corresponde ✘"))
            d_ref = d.get("t1")
            diff = ""
            if r_["anclajes"] and r_["respeta"] and d_ref and abs(pd.Timestamp(a["t1"]) - pd.Timestamp(d["t1"])) > pd.Timedelta(hours=3):
                diff = " Trazado distinto al de Atlas pero técnicamente defendible: se acepta."
            det.append({"obs": f"Línea ({tipo}): " + "; ".join(msg) + "." + diff + (" " + r_["msg"] if r_["msg"] else ""), "pts": round(pts, 1)})
    return round(tot, 1), round(pend, 1), det


def _explicacion(p, ref, clase_ok):
    P = al.cfg("rubrica")["pesos"]["explicacion"]; txt = (p.get("explicacion") or "").lower(); pts = 0.0; obs = []
    if len(txt) >= 40:
        pts += P * 0.2
    else:
        obs.append("Explicación muy breve (< 40 caracteres).")
    usados = {t for t in TERMINOS if t in txt}
    if len(usados) >= 3:
        pts += P * 0.4
    elif usados:
        pts += P * 0.2; obs.append("Cita poca evidencia concreta (medias, velas, líneas, volumen).")
    else:
        obs.append("No cita evidencia (medias, velas, líneas).")
    if re.search(r"\d{1,2}:\d{2}|\d+[.,]\d+|pm\s?\d{2,3}", txt):
        pts += P * 0.2
    else:
        obs.append("No referencia una vela, nivel o media concreta.")
    if clase_ok:
        pts += P * 0.2
    return round(pts, 1), obs


def evaluar(d, p):
    """d: fila de desafios; p: payload del alumno. Devuelve evaluacion completa (sin tocar la base)."""
    rub = al.cfg("rubrica")["pesos"]; t = d["ticker"]; sid = p.get("estrategia") or d["estrategia"]
    corte = p.get("corte") or d["corte"]; pd_ = datos.preparado(t); h = pd_["h"]; i = int(h.index.get_loc(pd.Timestamp(corte)))
    if sid not in df.ESTRATEGIAS:
        return {"error": "Falta indicar la estrategia propuesta."}
    ref = ref_en(t, corte, sid); defn = df.ESTRATEGIAS[sid]; pasos = ref["pasos"]; pend = 0.0; desg = {}; notas = []
    # --- contexto y temporalidad
    tf_ok = p.get("tf_decision") == defn["tf_decision"]
    vistas = set(p.get("tfs_vistas") or [p.get("tf_decision")])
    contr_ok = all(x in vistas for x in defn["tf_contraste"])
    ctx_n = defn.get("n_ctx", 1); ok_ctx = 0
    marc = {c.split(".c")[1] for c in (p.get("requisitos") or []) + (p.get("faltantes") or []) if c.startswith(sid + ".c")}
    est_ctx = [(n, pasos[n - 1]["ok"]) for n in range(1, ctx_n + 1)]
    pres = {c.split(".c")[1] for c in (p.get("requisitos") or []) if c.startswith(sid + ".c")}
    for n, ok in est_ctx:
        if ok is None or str(n) in marc and ((ok is True) == (str(n) in pres)):
            ok_ctx += 1
    c_pts = rub["contexto"] * 0.5 * (1 if tf_ok else 0) + rub["contexto"] * 0.2 * (1 if contr_ok else 0) + rub["contexto"] * 0.3 * (ok_ctx / max(1, ctx_n))
    obs = []
    obs.append(f"Temporalidad de decisión: {'correcta' if tf_ok else 'incorrecta'} (la estrategia se decide en «{defn['tf_decision']}», la elegida fue «{p.get('tf_decision')}»).")
    if defn["tf_contraste"]:
        obs.append(("Consultaste " if contr_ok else "Faltó consultar ") + "la temporalidad de contraste: " + ", ".join(defn["tf_contraste"]) + ".")
    desg["contexto"] = {"pts": round(c_pts, 1), "max": rub["contexto"], "obs": obs}
    # --- requisitos
    pres_all = {c for c in (p.get("requisitos") or [])}; fal_all = {c for c in (p.get("faltantes") or [])}
    per_c = rub["requisitos"] / len(pasos); r_pts = 0.0; obs = []
    for pa in pasos:
        n = pa["n"] if isinstance(pa["n"], int) else None
    for idx, pa in enumerate(pasos, 1):
        cid = f"{sid}.c{idx}"; cr_ = _estado_c(sid, idx); ok = pa["ok"]
        if ok is None:
            obs.append({"c": cid, "txt": "Atlas lo deja pendiente en este corte (dato no disponible aún): no puntúa.", "pend": True}); pend += per_c; continue
        m = "presente" if cid in pres_all else ("ausente" if cid in fal_all else "sin marcar")
        bien = (ok is True and m == "presente") or (ok is False and m == "ausente")
        if cr_["estado"] == "pendiente_revision":
            pend += per_c; r_pts += per_c if bien else 0
            obs.append({"c": cid, "txt": f"Marcaste «{m}»; referencia Atlas: {'cumple' if ok else 'no cumple'}. Criterio con contradicción en la lámina: PENDIENTE de revisión.", "pend": True, "bien": bien}); continue
        r_pts += per_c if bien else 0
        obs.append({"c": cid, "txt": f"{df.criterio_texto(cid)}: marcaste «{m}»; referencia: {'cumple' if ok else 'no cumple'}" + (f" ({pa['d']})" if pa.get("d") else "") + (" ✔" if bien else " ✘"), "bien": bien})
    ajenos = [c_ for c_ in (p.get("requisitos") or []) if not c_.startswith(sid + ".")]
    if ajenos:
        r_pts = max(0.0, r_pts - per_c * len(ajenos))
        obs.append({"c": "ajenos", "txt": "Marcaste como presentes criterios de OTRA estrategia: " + "; ".join(df.criterio_texto(a_) for a_ in ajenos) + " ✘", "bien": False})
    desg["requisitos"] = {"pts": round(r_pts, 1), "max": rub["requisitos"], "obs": obs}
    # --- trazado
    z, zp, zd = _trazado(h, i, sid, ref, p); pend += zp
    desg["trazado"] = {"pts": z, "max": rub["trazado"], "obs": zd}
    # --- clasificacion y confirmacion / condicion faltante
    cl = p.get("clasificacion"); clase_ok = cl == ref["clase"]; cl_pts = 0.0; obs = []
    if ref["clase"] == "AMBIGUA":
        pend += rub["clasificacion"]; obs.append("La referencia es ambigua (patrón completo fuera de la ventana horaria): clasificación PENDIENTE de revisión.")
    else:
        main = rub["clasificacion"] * 0.6; sub = rub["clasificacion"] * 0.4
        cl_pts += main if clase_ok else 0
        obs.append(f"Clasificación «{cl}» vs referencia «{ref['clase']}» en el corte {corte[:16].replace('T', ' ')} → {'✔' if clase_ok else '✘'}.")
        fallos = [f"{sid}.c{k}" for k, pa in enumerate(pasos, 1) if pa["ok"] is not True]
        if ref["clase"] == "CONFIRMADA":
            vc = p.get("vela_confirmacion"); ok_v = vc and pd.Timestamp(vc) == pd.Timestamp(corte)
            if ok_v:
                cl_pts += sub; obs.append("Vela de confirmación correcta: la que cierra en el corte.")
            elif vc and abs(h.index.searchsorted(pd.Timestamp(vc)) - i) == 1:
                cl_pts += sub * 0.5; obs.append("Vela de confirmación a ±1 vela de la correcta.")
            else:
                obs.append("No identificaste la vela de confirmación (la última cerrada en el corte).")
        else:
            cf = p.get("condicion_faltante")
            if ref["clase"] == "EN_FORMACION":
                if cf and cf == (fallos[0] if fallos else None):
                    cl_pts += sub; obs.append(f"Condición que falta correctamente identificada: {df.criterio_texto(cf)}.")
                elif cf in fallos:
                    cl_pts += sub * 0.6; obs.append(f"Señalaste un requisito que de hecho falta ({df.criterio_texto(cf)}), pero el siguiente por cumplir es «{df.criterio_texto(fallos[0])}».")
                else:
                    obs.append(f"No identificaste la condición faltante. Primera pendiente: «{df.criterio_texto(fallos[0]) if fallos else '-'}».")
            else:
                if cf in fallos:
                    cl_pts += sub; obs.append(f"Motivo de descarte válido: {df.criterio_texto(cf)} no se cumple.")
                elif p.get("descarte_motivo"):
                    cl_pts += sub * 0.5; obs.append("Descarte con motivo escrito pero sin señalar un requisito que falle.")
                else:
                    obs.append("Falta justificar el descarte (requisito que no se cumple).")
    desg["clasificacion"] = {"pts": round(cl_pts, 1), "max": rub["clasificacion"], "obs": obs}
    # --- explicacion
    e_pts, e_obs = _explicacion(p, ref, clase_ok)
    desg["explicacion"] = {"pts": e_pts, "max": rub["explicacion"], "obs": e_obs + ["Método: heurística de texto (sin modelo visual); incertidumbre alta, revisión recomendada."], "metodo": "heuristica_texto"}
    total = round(sum(v["pts"] for v in desg.values()), 1)
    estado = "pendiente_revision" if pend > 0.01 or ref["clase"] == "AMBIGUA" else "automatica"
    return {"total": total, "desglose": desg, "pendiente_pts": round(pend, 1), "estado_validacion": estado, "referencia": {"clase": ref["clase"], "etapa": ref["etapa"], "nivel": ref["nivel"],
            "pasos": pasos, "draw": ref["draw"], "ventana": ref["ventana"], "ventana_ok": ref["ventana_ok"], "corte": corte, "discrepa_atlas": ref.get("discrepa_atlas", False),
            "atlas_clase": ref.get("atlas_clase"), "nota_revision": ref.get("nota_revision")}, "estrategia": sid, "rubrica": al.cfg("rubrica")["version"], "def_version": df.VERSION,
            "anticipacion": bool(cl == "CONFIRMADA" and ref["clase"] == "EN_FORMACION"), "acierto_clase": bool(clase_ok)}

"""Aula Virtual - generador de desafios: aleatorio, reproducible (semilla + parametros guardados), adaptativo y diverso."""
import json, random, hashlib, datetime as dt
from collections import Counter, defaultdict
from . import datos, motor, almacen as al, definiciones as df

CAT = {"confirmado": lambda f: f[3] == "CONFIRMADA",
       "formacion": lambda f: f[3] in ("CASI", "VIGILANCIA"),
       "contraejemplo": lambda f: f[3] == "SIN_CONTEXTO" and f[5].count("1") >= max(1, len(f[5]) // 2),
       "faltante": lambda f: f[3] in ("CASI", "VIGILANCIA") and f[5].count("0") == 1 and f[5].count("-") == 0,
       "ambigua": lambda f: f[3] == "CONFIRMADA_FUERA_DE_HORARIO"}
MEZCLA = {"confirmado": 0.30, "formacion": 0.35, "contraejemplo": 0.35}
_pool_cache = {}


def pool():
    ix = motor.indice()
    if ix is None:
        return []
    k = ix["mt"]
    if _pool_cache.get("k") != k:
        ok = {t for t in {f[0] for f in ix["filas"]} if datos.estado(t).get("suficiente")}
        _pool_cache.update(k=k, filas=[f for f in ix["filas"] if f[0] in ok and f[3] != "ERROR"], ok=ok)
    return _pool_cache["filas"]


def cobertura():
    """Casos evaluables reales por estrategia y categoria (+ activos distintos, dias distintos) y lo que falta."""
    filas = pool(); out = {}
    for sid in df.ORDEN:
        rows = [f for f in filas if f[2] == sid]; o = {"estrategia": sid, "total_cortes": len(rows)}
        for cat, fn in CAT.items():
            sel = [f for f in rows if fn(f)]
            o[cat] = {"casos": len(sel), "activos": len({f[0] for f in sel}), "dias": len({f[1][:10] for f in sel})}
        o["evaluable"] = o["confirmado"]["casos"] > 0 and o["formacion"]["casos"] > 0
        faltan = []
        if o["confirmado"]["casos"] == 0:
            faltan.append("sin casos confirmados en la ventana de datos (60 sesiones de 30m): solo formación/contraejemplos")
        if o["faltante"]["casos"] == 0:
            faltan.append("sin casos con un único requisito faltante")
        o["faltan"] = faltan; out[sid] = o
    return out


def perfil(alumno_id):
    """Pesos adaptativos a partir del historial (errores, repasos vencidos, novedad)."""
    hoy = dt.date.today().isoformat()
    ints = al.q("""SELECT d.estrategia, d.ticker, d.corte, e.total FROM intentos i JOIN desafios d ON d.id=i.desafio_id
                   JOIN evaluaciones e ON e.intento_id=i.id AND e.version=(SELECT MAX(version) FROM evaluaciones WHERE intento_id=i.id)
                   WHERE i.alumno_id=? ORDER BY i.id DESC LIMIT 60""", (alumno_id,))
    rec = al.q("SELECT estrategia, ticker, corte FROM desafios WHERE alumno_id=? ORDER BY creado DESC, rowid DESC LIMIT 8", (alumno_id,))
    due = al.q("SELECT estrategia, criterio FROM repasos WHERE alumno_id=? AND hecho=0 AND vence<=?", (alumno_id, hoy))
    ps = {}
    err = defaultdict(list)
    for r in ints:
        if r["estrategia"]:
            err[r["estrategia"]].append(r["total"] < 70)
    cnt = Counter(r["estrategia"] for r in rec if r["estrategia"]); due_s = Counter(r["estrategia"] for r in due)
    for s in df.ORDEN:
        e = err.get(s, [])[:8]; frac = (sum(e) / len(e)) if e else 0.0
        w = 1 + 2 * frac + 1.5 * min(due_s.get(s, 0), 2) + (1.0 if not e else 0.0)
        ps[s] = round(max(0.15, w * (0.5 ** cnt.get(s, 0))), 3)      # diversidad: lo reciente pesa menos aunque sea favorito
    tk = Counter(r["ticker"] for r in al.q("SELECT ticker FROM desafios WHERE alumno_id=? ORDER BY rowid DESC LIMIT 40", (alumno_id,)))
    return {"pesos_estrategia": ps, "pesos_ticker": {t: round(1 / (1 + n), 3) for t, n in tk.items()},
            "evitar_tickers": [r["ticker"] for r in rec[:2]], "evitar_dias": [(r["corte"] or "")[:10] for r in rec[:2]],
            "evitar_estrategias": [r["estrategia"] for r in rec[:1] if r["estrategia"]], "foco": [d["criterio"] for d in due][:3]}


def _w(f, P, cat_w):
    w = P["pesos_estrategia"].get(f[2], 1.0) * P["pesos_ticker"].get(f[0], 1.0) * cat_w
    if f[0] in P["evitar_tickers"]:
        w *= 0.05
    if f[1][:10] in P["evitar_dias"]:
        w *= 0.1
    if f[2] in P["evitar_estrategias"]:
        w *= 0.2
    return w


def seleccionar(params, seed):
    """Funcion pura de (params, seed, indice): misma entrada => mismo caso (reproducible)."""
    rnd = random.Random(seed); filas = pool(); modo = params["modo"]; P = params["perfil"]
    if not filas:
        return {"error": "sin_indice", "detalle": "Falta construir el índice de casos (aula_virtual.construir_indice)."}
    if params.get("estrategia"):
        filas = [f for f in filas if f[2] == params["estrategia"]]
    if params.get("ticker"):
        filas = [f for f in filas if f[0] == params["ticker"]]
    if not filas:
        return {"error": "sin_datos", "detalle": "El activo o la estrategia elegidos no tienen datos suficientes (liquidez o velas)."}
    cat = params.get("categoria")
    if modo in ("reconoce", "libre"):
        g = defaultdict(list)
        for f in filas:
            g[(f[0], f[1])].append(f)
        keys = sorted(g)
        ws = []
        for k_ in keys:
            n = sum(1 for f in g[k_] if f[3] in ("CASI", "CONFIRMADA")) if modo == "reconoce" else 0; ws.append((0.4 + 2.5 * min(n, 3)) * (0.05 if k_[0] in P["evitar_tickers"] else 1) * P["pesos_ticker"].get(k_[0], 1))
        t, ts = rnd.choices(keys, ws)[0]
        return {"ticker": t, "corte": ts, "estrategia": None, "categoria": "multi", "tramo": None}
    if modo == "faltante":
        cat = "faltante"
    if cat is None:
        cat = rnd.choices(list(MEZCLA), list(MEZCLA.values()))[0]
    cand = [f for f in filas if CAT[cat](f)]
    if params.get("foco_criterio"):
        sid_f, n_f = params["foco_criterio"].split(".c")
        foco = [f for f in cand if f[2] == sid_f and len(f[5]) >= int(n_f) and f[5][int(n_f) - 1] == "0"]
        cand = foco or cand
    if not cand:
        alt = [c_ for c_ in MEZCLA if c_ != cat and [f for f in filas if CAT[c_](f)]]
        if not alt:
            return {"error": "sin_casos", "detalle": "No hay casos evaluables para esos filtros."}
        cat = rnd.choice(alt); cand = [f for f in filas if CAT[cat](f)]
    if modo == "encontra":
        return _tramo(rnd, filas, cand, params, cat)
    f = rnd.choices(cand, [_w(x, P, 1.0) for x in cand])[0]
    return {"ticker": f[0], "corte": f[1], "estrategia": f[2], "categoria": cat, "tramo": None, "bits": f[5]}


def _tramo(rnd, filas, cand, params, cat):
    """Encontra la estrategia: tramo de 3 sesiones terminando en el dia D. 65 % con una ocurrencia confirmada; 35 % sin (descarte)."""
    P = params["perfil"]; con_conf = rnd.random() < 0.65
    base = [f for f in filas if CAT["confirmado"](f)] if con_conf else cand
    if not base:
        base = cand; con_conf = False
    f = rnd.choices(base, [_w(x, P, 1.0) for x in base])[0]
    t, sid, dia = f[0], f[2], f[1][:10]
    dias = sorted({x[1][:10] for x in filas if x[0] == t and x[2] == sid})
    k = dias.index(dia); tr = dias[max(0, k - 2):k + 1]
    ultimo = max(x[1] for x in filas if x[0] == t and x[2] == sid and x[1][:10] == tr[-1])
    hay = [x for x in filas if x[0] == t and x[2] == sid and x[1][:10] in tr and CAT["confirmado"](x)]
    return {"ticker": t, "corte": ultimo, "estrategia": sid, "categoria": "confirmado_en_tramo" if hay else "sin_ocurrencia", "tramo": tr}


def crear(alumno_id, modo, ruta="evaluable", seed=None, estrategia=None, ticker=None, categoria=None, examen=True, repetir=None, foco=None):
    al.alumno(alumno_id)
    seed = int(seed if seed is not None else random.SystemRandom().randrange(1, 2 ** 31))
    params = {"modo": modo, "ruta": ruta, "estrategia": estrategia or None, "ticker": ticker or None, "categoria": categoria or None,
              "perfil": perfil(alumno_id), "indice": (motor.indice() or {}).get("meta", {}).get("construido", "")}
    if foco is None and params["perfil"]["foco"] and not estrategia:
        foco = params["perfil"]["foco"][0]
    params["foco_criterio"] = foco
    sel = seleccionar(params, seed)
    if "error" in sel:
        return sel
    snap = motor.snapshot(sel["ticker"], sel["corte"])
    did = hashlib.sha1(f"{alumno_id}{seed}{modo}{al.ahora()}{random.random()}".encode()).hexdigest()[:12]
    nivel = motor.NIVEL_REF if ruta == "evaluable" else "pendiente"
    extra = {"categoria": sel["categoria"], "tramo": sel.get("tramo"), "bits": sel.get("bits")}
    al.ej("INSERT INTO desafios VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (did, alumno_id, modo, ruta, seed, json.dumps(params), sel["ticker"], sel["estrategia"], sel["corte"], snap["hash"], nivel, int(bool(examen)), "abierto",
           df.VERSION, motor.VER_ATLAS, al.ahora(), json.dumps(extra)))
    return {"id": did, "seed": seed, "modo": modo, "ruta": ruta, "examen": bool(examen), "ticker": sel["ticker"], "estrategia": sel["estrategia"],
            "corte": sel["corte"], "tramo": sel.get("tramo"), "nivel_validacion": nivel, "evidencia_hash": snap["hash"]}


def reproducir(desafio_id):
    """Reconstruye la seleccion con semilla y parametros guardados (no con el perfil actual)."""
    d = al.q("SELECT * FROM desafios WHERE id=?", (desafio_id,), True)
    sel = seleccionar(json.loads(d["params"]), d["seed"])
    return {"original": {"ticker": d["ticker"], "corte": d["corte"], "estrategia": d["estrategia"]}, "reproducido": sel,
            "coincide": sel.get("ticker") == d["ticker"] and sel.get("corte") == d["corte"] and sel.get("estrategia") == d["estrategia"]}


def crear_sesion(alumno_id, ticker=None, estrategia=None, examen=True, refrescar=True):
    """Practica de la sesion actual: refresca el activo y usa la ULTIMA vela cerrada como corte (se conserva con su corte temporal)."""
    al.alumno(alumno_id)
    uni = datos.universo()["tickers"]; seed = random.SystemRandom().randrange(1, 2 ** 31); rnd = random.Random(seed)
    ticker = ticker or rnd.choice([t for t in uni if datos.estado(t).get("suficiente")])
    if refrescar:
        try:
            datos.refrescar([ticker])
        except Exception:
            pass
    p = datos.preparado(ticker)
    if p is None or len(p["h"]) < datos.MIN_BARS:
        return {"error": "sin_datos", "detalle": f"{ticker} no tiene velas suficientes para evaluar la sesión actual."}
    corte = p["h"].index[-1].isoformat(); snap = motor.snapshot(ticker, corte)
    did = hashlib.sha1(f"{alumno_id}{seed}sesion{al.ahora()}".encode()).hexdigest()[:12]
    params = {"modo": "sesion", "ruta": "exploracion", "estrategia": estrategia, "ticker": ticker, "perfil": {}, "indice": "", "foco_criterio": None}
    al.ej("INSERT INTO desafios VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (did, alumno_id, "sesion", "exploracion", seed, json.dumps(params), ticker, estrategia, corte, snap["hash"], "atlas_automatico_en_vivo", int(bool(examen)), "abierto",
           df.VERSION, motor.VER_ATLAS, al.ahora(), json.dumps({"categoria": "sesion_actual", "tramo": None})))
    return {"id": did, "seed": seed, "modo": "sesion", "ruta": "exploracion", "examen": bool(examen), "ticker": ticker, "estrategia": estrategia, "corte": corte,
            "sesion": datos.estado_sesion(ticker), "nivel_validacion": "atlas_automatico_en_vivo", "evidencia_hash": snap["hash"]}

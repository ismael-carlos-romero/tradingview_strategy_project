"""Ledger local de trazabilidad (Etapa 1). Solo agrega filas; nunca modifica ni borra las existentes.

Dimensiones separadas: fuente, canal, familia, estrategia+version, detector, modo.
Desconocido = NULL (nunca 0). Falla en silencio hacia el llamador: la trazabilidad no debe romper una compra.
"""
import json
import sqlite3
import hashlib
from datetime import datetime, timezone, timedelta

FUENTES = {"TRADINGVIEW", "SCANNER_PYTHON", "NEWS", "ATLAS", "MANUAL"}
FAMILIAS = {"CARDONA", "PROPIA", "NOTICIAS_EXPERIMENTAL", "ANALISIS_COMBINADO_EXPERIMENTAL", "SIN_CLASIFICAR"}
ESTADOS = {"RECIBIDA", "VALIDADA", "BLOQUEADA", "ENCOLADA", "ENVIADA", "RECHAZADA",
           "PARCIAL", "EJECUTADA", "CANCELADA", "CIERRE_ENVIADA", "CERRADA"}
VENUES = {"SIM_INTERNO", "UCHARTS_PAPER"}

# Familia por estrategia (ids canonicos de catalogo_estrategias). Fuente: Ismael, 23/10/2026 -- 11 estrategias de
# Cardona (PDF "Resumen del Seminario"). Las otras 7 NO tienen evidencia documental: SIN_CLASIFICAR hasta verificar (E2).
CARDONA = {"PRIMER_GAP_ALZA", "GAP_NORMAL", "GAP_BAJISTA_ALZA", "CAIDA_BREAK", "PISO_FUERTE", "PM40_BOUNCE",
           "CANAL_BREAK", "RUPTURA_PISO_GAP", "HANGER_DIARIO", "VELA_ROJA", "CUATRO_PASOS", "TECHO_FUERTE"}  # TECHO_FUERTE: lo confirma Ismael 23/10 17:38 segun el indice del PDF (12 nombres)
PROPIA = set()  # se llena solo con evidencia documental; las 7 restantes del catalogo quedan SIN_CLASIFICAR
# Ids que hoy emite el scanner / userscript y difieren del catalogo (alias -> canonico).
ALIAS = {"PRIMER_GAP": "PRIMER_GAP_ALZA", "GAP_ALZA_1": "PRIMER_GAP_ALZA", "GAP_BAJISTA": "GAP_BAJISTA_ALZA",
         "CAIDA_NORMAL": "CAIDA_BREAK", "CAIDA_FUERTE": "CAIDA_BREAK", "4_PASOS": "CUATRO_PASOS",
         "RUPTURA_PISO": "RUPTURA_PISO_GAP"}


def familia_de(strategy_id):
    s = str(strategy_id or "").upper()
    s = s[5:] if s.startswith("COND_") else s
    s = ALIAS.get(s, s)
    return "CARDONA" if s in CARDONA else "PROPIA" if s in PROPIA else "SIN_CLASIFICAR"

SCHEMA = """
CREATE TABLE IF NOT EXISTS trace_origen (
    setup_id TEXT PRIMARY KEY, signal_id TEXT, ts_utc TEXT, ts_ar TEXT,
    fuente_senal TEXT, familia TEXT, strategy_id TEXT, strategy_version TEXT, detector_version TEXT,
    modo_ejecucion TEXT, ticker TEXT, direccion TEXT, timeframe TEXT, disparador TEXT,
    canales TEXT, corroboraciones TEXT, analysis_id TEXT, news_event_id TEXT
);
CREATE TABLE IF NOT EXISTS trace_eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT, idem_key TEXT UNIQUE, ts_utc TEXT, ts_ar TEXT,
    setup_id TEXT, signal_id TEXT, order_id TEXT, execution_id TEXT, trade_id TEXT,
    parent_trade_id TEXT, group_id TEXT, venue TEXT, estado TEXT, motivo TEXT, evidencia TEXT,
    ticker TEXT, option_symbol TEXT, expiry TEXT, strike REAL, multiplicador INTEGER, qty REAL,
    px_solicitado REAL, px_ejecutado REAL, costes REAL, tp_pct REAL, sl_pct REAL,
    capital_base REAL, presupuesto REAL, risk_rules_version TEXT
);
CREATE INDEX IF NOT EXISTS ix_trace_ev_setup ON trace_eventos(setup_id);
CREATE INDEX IF NOT EXISTS ix_trace_ev_trade ON trace_eventos(trade_id);
"""

_CAMPOS_EV = ("signal_id", "order_id", "execution_id", "trade_id", "parent_trade_id", "group_id",
              "ticker", "option_symbol", "expiry", "strike", "multiplicador", "qty", "px_solicitado",
              "px_ejecutado", "costes", "tp_pct", "sl_pct", "capital_base", "presupuesto", "risk_rules_version")


def detector_version(path):
    """Huella del archivo del detector (hecho verificable, no una versión inventada)."""
    try:
        with open(path, "rb") as f:
            return "sha1:" + hashlib.sha1(f.read()).hexdigest()[:10]
    except Exception:
        return None


def _now():
    u = datetime.now(timezone.utc)
    return u.strftime("%Y-%m-%d %H:%M:%S"), (u - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")


def ensure_schema(conn):
    conn.executescript(SCHEMA)


def registrar_origen(conn, setup_id, *, signal_id=None, fuente_senal, familia=None, strategy_id=None,
                     strategy_version=None, detector_ver=None, modo_ejecucion=None, ticker=None, direccion=None,
                     timeframe=None, disparador=None, canales=None, analysis_id=None, news_event_id=None):
    """Una fila por setup. Si ya existe se conserva (INSERT OR IGNORE): no se reescribe la procedencia."""
    familia = familia or familia_de(strategy_id)
    if fuente_senal not in FUENTES or familia not in FAMILIAS:
        raise ValueError(f"fuente/familia invalida: {fuente_senal}/{familia}")
    ensure_schema(conn)
    u, ar = _now()
    conn.execute(
        "INSERT OR IGNORE INTO trace_origen VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (setup_id, signal_id, u, ar, fuente_senal, familia, strategy_id, strategy_version, detector_ver,
         modo_ejecucion, ticker, direccion, timeframe, disparador or fuente_senal,
         json.dumps(canales or []), "[]", analysis_id, news_event_id))
    conn.commit()


def agregar_corroboracion(conn, setup_id, fuente, detalle=None):
    """Suma una fuente que corrobora el setup; no crea otra compra ni otro P&L."""
    ensure_schema(conn)
    row = conn.execute("SELECT corroboraciones FROM trace_origen WHERE setup_id=?", (setup_id,)).fetchone()
    if not row:
        return False
    lst = json.loads(row[0] or "[]")
    u, _ = _now()
    lst.append({"fuente": fuente, "ts_utc": u, "detalle": detalle})
    conn.execute("UPDATE trace_origen SET corroboraciones=? WHERE setup_id=?", (json.dumps(lst), setup_id))
    conn.commit()
    return True


def registrar_evento(conn, setup_id, estado, venue, motivo=None, evidencia=None, idem_key=None, **campos):
    """Agrega un evento de ciclo de vida. Devuelve True si se insertó, False si era repetido (idem_key)."""
    if estado not in ESTADOS or venue not in VENUES:
        raise ValueError(f"estado/venue invalido: {estado}/{venue}")
    extra = set(campos) - set(_CAMPOS_EV)
    if extra:
        raise ValueError(f"campos desconocidos: {extra}")
    ensure_schema(conn)
    u, ar = _now()
    key = idem_key or "|".join(str(x) for x in (setup_id, venue, estado, campos.get("order_id"),
                                                 campos.get("execution_id"), campos.get("trade_id")))
    cols = ["idem_key", "ts_utc", "ts_ar", "setup_id", "venue", "estado", "motivo", "evidencia"] + list(campos)
    vals = [key, u, ar, setup_id, venue, estado, motivo, json.dumps(evidencia, default=str) if evidencia is not None else None] + list(campos.values())
    cur = conn.execute(f"INSERT OR IGNORE INTO trace_eventos ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
    conn.commit()
    return cur.rowcount == 1


def timeline(conn, setup_id):
    """Origen + eventos de un setup, para reconstruir de dónde vino la compra y qué pasó."""
    ensure_schema(conn)
    conn.row_factory = sqlite3.Row
    o = conn.execute("SELECT * FROM trace_origen WHERE setup_id=?", (setup_id,)).fetchone()
    ev = conn.execute("SELECT * FROM trace_eventos WHERE setup_id=? ORDER BY id", (setup_id,)).fetchall()
    o = dict(o) if o else None
    if o:  # filas escritas por versiones anteriores del ledger traen familia SIN_CLASIFICAR como marcador: se resuelve al leer
        o["familia_resuelta"] = familia_de(o.get("strategy_id")) if o.get("familia") == "SIN_CLASIFICAR" else o.get("familia")
    return o, [dict(e) for e in ev]


def registrar(db_path, fn, *a, **k):
    """Abre su propia conexion, ejecuta fn(conn, ...) y nunca propaga errores (para usar desde el scanner)."""
    try:
        conn = sqlite3.connect(db_path, timeout=30.0)
        try:
            return fn(conn, *a, **k)
        finally:
            conn.close()
    except Exception as e:
        print(f"[Trace] {getattr(fn, '__name__', fn)} fallo: {e}")
        return None


def safe(fn, *a, **k):
    """Envoltorio para el scanner: loguea y sigue si la trazabilidad falla."""
    try:
        return fn(*a, **k)
    except Exception as e:
        print(f"[Trace] {fn.__name__} fallo: {e}")
        return None


# ---------------------------------------------------------------------------
# Etapa 1 (continuacion): cierres, compras manuales/patas/recompras, cola persistente, conciliacion.
# ---------------------------------------------------------------------------
MODOS = {"SONAR", "TESTER", "BANDERIN", "BANDERA_AUTO", "TECHO_PISO", "RECOMPRA_GANADORES",
         "RECOMPRA_ESTRATEGIA", "MONITOREO", "MANUAL", "TRADINGVIEW", "ATLAS", "NOTICIAS"}
_ESTADOS_UC = {"ENVIADA", "EJECUTADA", "RECHAZADA", "CANCELADA", "CIERRE_ENVIADA", "CERRADA"}
# CIERRE_ENVIADA = el userscript puso la orden de venta (TP limite o mercado); NO es cierre. CERRADA solo cuando la
# posicion desaparece de Posiciones o aparece la venta en el historial de uCharts.
_FINALES_COLA = ("ENVIADA", "EJECUTADA", "RECHAZADA", "CANCELADA", "BLOQUEADA", "PARCIAL", "CERRADA")

SCHEMA_CONC = """
CREATE TABLE IF NOT EXISTS trace_conciliacion (
    id INTEGER PRIMARY KEY AUTOINCREMENT, idem_key TEXT UNIQUE, ts_utc TEXT, fuente_contraste TEXT,
    trade_id TEXT, setup_id TEXT, lado TEXT, resultado TEXT, detalle TEXT
);
"""


def _num(x):
    try:
        return None if x is None or x == "" else float(x)
    except (TypeError, ValueError):
        return None


def _opt_sym(ticker, tipo, strike):
    if ticker and tipo and strike is not None:
        return f"{ticker}|{tipo}|{strike:g}"
    return None


def registrar_cierre_sim(conn, trade_id, *, pnl_usd=None, pnl_pct=None, motivo=None):
    """CERRADA del simulador interno. Se enlaza al setup por trade_id; si no hay compra trazada queda huerfana."""
    ensure_schema(conn)
    r = conn.execute("SELECT setup_id, ticker FROM trace_eventos WHERE venue='SIM_INTERNO' AND trade_id=? "
                     "AND estado='EJECUTADA' ORDER BY id LIMIT 1", (trade_id,)).fetchone()
    setup, ticker = (r[0], r[1]) if r else (f"HUERFANA_{trade_id}", None)
    return registrar_evento(conn, setup, "CERRADA", "SIM_INTERNO", motivo=motivo, trade_id=trade_id, ticker=ticker,
                            idem_key=f"{setup}|SIM|CERRADA|{trade_id}",
                            evidencia={"pnl_usd": pnl_usd, "pnl_pct": pnl_pct, "huerfana": r is None})


def registrar_evento_uc(conn, d):
    """Evento reportado por el userscript de uCharts (solo registra; no ordena nada).

    d: estado, setup_id (cola del bot) o local_id (generado por el userscript), modo, ticker, type, strike, expiry,
    qty, price, group_id, parent_trade_id, strategy_id, motivo, idem_key.
    Sin setup_id => compra de origen MANUAL (estrategia desconocida = NULL salvo que venga informada).
    """
    estado = d.get("estado")
    if estado not in _ESTADOS_UC:
        raise ValueError(f"estado invalido: {estado}")
    ticker, tipo = d.get("ticker"), (d.get("type") or "").upper() or None
    strike, qty, px = _num(d.get("strike")), _num(d.get("qty")), _num(d.get("price"))
    ensure_schema(conn)
    if estado in ("CERRADA", "CIERRE_ENVIADA"):
        return _cerrar_uc(conn, d, ticker, tipo, strike, qty, px, estado)
    parent = d.get("parent_trade_id")
    ref = d.get("parent_ref") or {}
    if not parent and ref.get("ticker"):  # recompra: el padre es el ultimo cierre de ese activo+tipo (y strike si viene)
        sql = ("SELECT trade_id FROM trace_eventos WHERE venue='UCHARTS_PAPER' AND estado='CERRADA' AND trade_id IS NOT NULL "
               "AND ticker=? AND option_symbol LIKE ?")
        args = [ref["ticker"], f"{ref['ticker']}|{(ref.get('type') or '').upper()}|%"]
        if _num(ref.get("strike")) is not None:
            sql, args = sql + " AND strike=?", args + [_num(ref.get("strike"))]
        r = conn.execute(sql + " ORDER BY id DESC LIMIT 1", args).fetchone()
        parent = r[0] if r else None
    sid = d.get("setup_id")
    if not sid:
        sid = d.get("local_id")
        if not sid:
            raise ValueError("falta setup_id o local_id")
        registrar_origen(conn, sid, fuente_senal="MANUAL", familia="SIN_CLASIFICAR",
                         strategy_id=d.get("strategy_id"), modo_ejecucion=d.get("modo"), ticker=ticker,
                         direccion=tipo, disparador="USERSCRIPT_UCHARTS")
    ok = estado == "EJECUTADA"
    return registrar_evento(
        conn, sid, estado, "UCHARTS_PAPER", motivo=d.get("motivo"), idem_key=f"{sid}|UC|{estado}",
        trade_id=f"UC_{sid}", parent_trade_id=parent, group_id=d.get("group_id"),
        ticker=ticker, option_symbol=_opt_sym(ticker, tipo, strike), expiry=d.get("expiry"), strike=strike,
        qty=qty, px_ejecutado=px if ok else None,
        evidencia={"modo": d.get("modo"), "tipo": tipo, "reportado_por": "userscript"})


def _cerrar_uc(conn, d, ticker, tipo, strike, qty, px, estado="CERRADA"):
    row = None
    if ticker and tipo and strike is not None:
        row = conn.execute(
            "SELECT e.setup_id, e.trade_id FROM trace_eventos e WHERE e.venue='UCHARTS_PAPER' AND e.estado='EJECUTADA' "
            "AND e.ticker=? AND e.strike=? AND e.option_symbol LIKE ? AND e.trade_id IS NOT NULL AND NOT EXISTS "
            "(SELECT 1 FROM trace_eventos c WHERE c.venue='UCHARTS_PAPER' AND c.estado='CERRADA' AND c.trade_id=e.trade_id) "
            "ORDER BY e.id LIMIT 1", (ticker, strike, f"{ticker}|{tipo}|%")).fetchone()  # FIFO
    if row:
        setup, trade = row
        key = f"{trade}|UC|{estado}" + (f"|{d['local_id']}" if estado == "CIERRE_ENVIADA" and d.get("local_id") else "")
    else:
        lid = d.get("local_id") or f"{ticker}_{_now()[0]}"
        setup, trade = f"HUERFANA_UC_{lid}", None
        key = f"{setup}|UC|{estado}"
    return registrar_evento(conn, setup, estado, "UCHARTS_PAPER", motivo=d.get("motivo"), idem_key=key,
                            trade_id=trade, ticker=ticker, option_symbol=_opt_sym(ticker, tipo, strike), strike=strike,
                            qty=qty, px_ejecutado=px, evidencia={"huerfana": row is None, "reportado_por": "userscript"})


def pendientes_recuperables(conn, max_edad_min=30):
    """Items de cola que se encolaron, nunca se ofrecieron al terminal y siguen frescos. Conservador a proposito:
    lo que ya fue ENVIADA sin resultado NO se recupera (riesgo de comprar dos veces); va a a_conciliar()."""
    ensure_schema(conn)
    corte = (datetime.now(timezone.utc) - timedelta(minutes=max_edad_min)).strftime("%Y-%m-%d %H:%M:%S")
    marcas = ",".join("?" * len(_FINALES_COLA))
    rows = conn.execute(
        f"SELECT e.setup_id, e.evidencia FROM trace_eventos e WHERE e.venue='UCHARTS_PAPER' AND e.estado='ENCOLADA' "
        f"AND e.ts_utc>=? AND NOT EXISTS (SELECT 1 FROM trace_eventos f WHERE f.setup_id=e.setup_id AND "
        f"f.venue='UCHARTS_PAPER' AND f.estado IN ({marcas})) ORDER BY e.id", (corte, *_FINALES_COLA)).fetchall()
    out = []
    for sid, ev in rows:
        try:
            item = (json.loads(ev or "{}") or {}).get("item")
        except ValueError:
            item = None
        if item and item.get("setup_id") == sid:
            out.append(item)
    return out


def a_conciliar(conn):
    """ENVIADA a uCharts sin resultado (ni EJECUTADA, RECHAZADA ni CANCELADA): estado desconocido, revisar a mano."""
    ensure_schema(conn)
    return [dict(zip(("setup_id", "ts_utc", "ticker"), r)) for r in conn.execute(
        "SELECT e.setup_id, e.ts_utc, e.ticker FROM trace_eventos e WHERE e.venue='UCHARTS_PAPER' AND e.estado='ENVIADA' "
        "AND NOT EXISTS (SELECT 1 FROM trace_eventos f WHERE f.setup_id=e.setup_id AND f.venue='UCHARTS_PAPER' "
        "AND f.estado IN ('EJECUTADA','RECHAZADA','CANCELADA')) ORDER BY e.id")]


def cancelar_encoladas(conn, setup_ids, motivo):
    n = 0
    for sid in setup_ids:
        n += bool(registrar_evento(conn, sid, "CANCELADA", "UCHARTS_PAPER", motivo=motivo,
                                   idem_key=f"{sid}|UC|CANCELADA"))
    return n


def conciliar_historial(conn, txs, fuente="UCHARTS_HISTORIAL", tol_precio=0.02):
    """Contrasta eventos locales con movimientos leidos del historial de uCharts (o de la planilla).

    txs: lista de dict {lado:'BUY'|'SELL', ticker, type, strike, qty, price}. Un reporte de ejecucion NO es una
    operacion conciliada hasta que aparece aqui con resultado COINCIDE. Cada movimiento se usa una sola vez.
    """
    ensure_schema(conn)
    conn.executescript(SCHEMA_CONC)
    u, _ = _now()
    res = {"COINCIDE": 0, "DIFIERE": 0, "SIN_ORIGEN": 0, "CERRADA_DESDE_HISTORIAL": 0}
    usados = set()
    for tx in txs:
        lado = (tx.get("lado") or "").upper()
        estado = "EJECUTADA" if lado == "BUY" else "CERRADA" if lado == "SELL" else None
        if not estado:
            continue
        t, tipo, k = tx.get("ticker"), (tx.get("type") or "").upper(), _num(tx.get("strike"))
        key = f"{fuente}|{lado}|{t}|{tipo}|{k}|{tx.get('qty')}|{tx.get('price')}|{tx.get('ts', '')}"
        if conn.execute("SELECT 1 FROM trace_conciliacion WHERE idem_key=?", (key,)).fetchone():
            continue  # movimiento ya procesado: reintentar no duplica
        cand = conn.execute(
            "SELECT id, setup_id, trade_id, qty, px_ejecutado FROM trace_eventos WHERE venue='UCHARTS_PAPER' AND estado=? "
            "AND ticker=? AND strike=? AND option_symbol LIKE ? ORDER BY id", (estado, t, k, f"{t}|{tipo}|%")).fetchall()
        cand = [c for c in cand if c[0] not in usados and not conn.execute(
            "SELECT 1 FROM trace_conciliacion WHERE trade_id IS ? AND lado=? AND resultado='COINCIDE' AND fuente_contraste=?",
            (c[2], lado, fuente)).fetchone()]
        desde_hist = False
        if not cand and lado == "SELL":  # la venta aparece en el historial de uCharts: cerrar la compra abierta mas antigua
            ab = conn.execute(
                "SELECT e.setup_id, e.trade_id FROM trace_eventos e WHERE e.venue='UCHARTS_PAPER' AND e.estado='EJECUTADA' "
                "AND e.ticker=? AND e.strike=? AND e.option_symbol LIKE ? AND e.trade_id IS NOT NULL AND NOT EXISTS "
                "(SELECT 1 FROM trace_eventos c WHERE c.venue='UCHARTS_PAPER' AND c.estado='CERRADA' AND c.trade_id=e.trade_id) "
                "ORDER BY e.id LIMIT 1", (t, k, f"{t}|{tipo}|%")).fetchone()
            if ab:
                registrar_evento(conn, ab[0], "CERRADA", "UCHARTS_PAPER", motivo="HISTORIAL_UCHARTS",
                                 idem_key=f"{ab[1]}|UC|CERRADA", trade_id=ab[1], ticker=t, strike=k,
                                 option_symbol=_opt_sym(t, tipo, k), qty=_num(tx.get("qty")),
                                 px_ejecutado=_num(tx.get("price")), evidencia={"fuente": fuente})
                cand, desde_hist = [(None, ab[0], ab[1], _num(tx.get("qty")), _num(tx.get("price")))], True
        if not cand:
            resultado, setup, trade, det = "SIN_ORIGEN", None, None, "movimiento sin evento local (p. ej. compra manual no reportada)"
        else:
            c = cand[0]
            usados.add(c[0])
            setup, trade = c[1], c[2]
            px, qty = _num(tx.get("price")), _num(tx.get("qty"))
            ok_q = c[3] is None or qty is None or abs(c[3] - qty) < 1e-9
            ok_p = c[4] is None or px is None or abs(c[4] - px) <= tol_precio * max(abs(px), 1e-9)
            resultado = "COINCIDE" if ok_q and ok_p else "DIFIERE"
            det = None if resultado == "COINCIDE" else f"local qty={c[3]} px={c[4]} / contraste qty={qty} px={px}"
            if desde_hist:
                resultado, det = "CERRADA_DESDE_HISTORIAL", "cierre registrado a partir del historial (sin evento previo de cierre)"
        cur = conn.execute("INSERT OR IGNORE INTO trace_conciliacion (idem_key, ts_utc, fuente_contraste, trade_id, setup_id, "
                           "lado, resultado, detalle) VALUES (?,?,?,?,?,?,?,?)", (key, u, fuente, trade, setup, lado, resultado, det))
        if cur.rowcount:
            res[resultado] += 1
    conn.commit()
    return res

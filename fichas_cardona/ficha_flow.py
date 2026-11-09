"""Flujo manual Fichas Cardona (SOLO PAPER, modo prueba sin órdenes por defecto).

proponer(ficha, ahora)  -> valida con ficha_guard y arma la compra propuesta (nada se envía)
registrar(prop, db)     -> guarda en fichas_cardona_log (DRY_RUN) y evita duplicados
estado_fuente(db)/fijar_fuente(db, activo) -> interruptor 'fichas_cardona_activo' (default apagado)
Enviar la orden real a uCharts Paper queda DESHABILITADO hasta que Ismael lo habilite.
"""
import json, math, sqlite3, sys, os
from datetime import timedelta
sys.path.insert(0, os.path.dirname(__file__))
from ficha_guard import validar_ficha, _et

TP_PCT, SL_PCT, QTY, DIAS_VENC = 5, 10, 1, 7   # defaults fijos del Auto-Trader


def _viernes(d, max_dias):
    t = d + timedelta(days=max_dias)
    while t.weekday() != 4:
        t -= timedelta(days=1)
    return t


def _tabla(db):
    db.execute("""CREATE TABLE IF NOT EXISTS fichas_cardona_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts_utc TEXT DEFAULT CURRENT_TIMESTAMP,
        clave TEXT UNIQUE, ficha_id TEXT, ticker TEXT, strategy_id TEXT, direction TEXT,
        estado TEXT, motivos TEXT, propuesta TEXT, origen TEXT DEFAULT 'Fichas Cardona', modo TEXT)""")


def estado_fuente(db):
    r = db.execute("SELECT val FROM configuracion WHERE param_id='fichas_cardona_activo'").fetchone()
    return bool(r and r[0] == 'true')


def fijar_fuente(db, activo):
    db.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('fichas_cardona_activo', ?)",
               ('true' if activo else 'false',))
    db.commit()


def proponer(f, ahora, ya_usadas, spot):
    ok, motivos, clave = validar_ficha(f, ahora, ya_usadas)
    prop = None
    if ok:
        d = _et(ahora).date()
        venc = _viernes(d, DIAS_VENC)
        call = f["direction"].upper().startswith("CALL")
        strike = math.ceil(spot * 1.01) if call else math.floor(spot * 0.99)   # fuera del dinero (Cardona)
        prop = dict(activo=f["ticker"], lado="CALL" if call else "PUT", contrato=f"{f['ticker']} {venc} {strike} {'C' if call else 'P'}",
                    vencimiento=str(venc), strike=strike, cantidad=QTY,
                    costo_estimado="NO VERIFICABLE hasta leer la cadena de opciones en uCharts (prima real)",
                    salida=dict(tp_pct=TP_PCT, sl_pct=SL_PCT, vence=str(venc)), modo="PAPER",
                    ficha_id=f.get("ficha_id"), clave=clave)
    return ok, motivos, clave, prop


def registrar(db, f, ok, motivos, clave, prop):
    _tabla(db)
    try:
        db.execute("INSERT INTO fichas_cardona_log (clave, ficha_id, ticker, strategy_id, direction, estado, motivos, propuesta, modo) VALUES (?,?,?,?,?,?,?,?,?)",
                   (clave, f.get("ficha_id"), f["ticker"], f["strategy_id"], f["direction"],
                    "PROPUESTA_DRY_RUN" if ok else "BLOQUEADA", ",".join(motivos), json.dumps(prop, ensure_ascii=False), "PAPER"))
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False   # duplicada

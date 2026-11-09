"""Aula Virtual - almacenamiento persistente (SQLite propio: aula_virtual\\aula_virtual.db). Progreso aislado por alumno_id.
Nota: el portal tiene UNA clave de administrador (sin cuentas por usuario); el aislamiento es por perfil de alumno, no por autenticacion."""
import os, json, sqlite3, time, threading
from . import definiciones as df

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aula_virtual.db")
_lock = threading.RLock()
SCHEMA = """
CREATE TABLE IF NOT EXISTS alumnos(id TEXT PRIMARY KEY, nombre TEXT, creado TEXT);
CREATE TABLE IF NOT EXISTS config(clave TEXT PRIMARY KEY, valor TEXT, version TEXT, actualizado TEXT);
CREATE TABLE IF NOT EXISTS desafios(id TEXT PRIMARY KEY, alumno_id TEXT, modo TEXT, ruta TEXT, seed INTEGER, params TEXT, ticker TEXT, estrategia TEXT,
  corte TEXT, evidencia_hash TEXT, nivel_validacion TEXT, examen INTEGER, estado TEXT, def_version TEXT, atlas_version TEXT, creado TEXT, extra TEXT);
CREATE TABLE IF NOT EXISTS intentos(id INTEGER PRIMARY KEY AUTOINCREMENT, desafio_id TEXT, alumno_id TEXT, numero INTEGER, tipo TEXT, payload TEXT,
  ayudas TEXT, inicio TEXT, fin TEXT, duracion_s INTEGER, corte_respuesta TEXT, evidencia_hash TEXT, creado TEXT);
CREATE TABLE IF NOT EXISTS evaluaciones(id INTEGER PRIMARY KEY AUTOINCREMENT, intento_id INTEGER, version INTEGER, origen TEXT, total REAL, desglose TEXT,
  estado_validacion TEXT, pendientes TEXT, referencia TEXT, rubrica_version TEXT, def_version TEXT, autor TEXT, motivo TEXT, creada TEXT);
CREATE TABLE IF NOT EXISTS revisiones(id INTEGER PRIMARY KEY AUTOINCREMENT, intento_id INTEGER, alumno_id TEXT, motivo TEXT, estado TEXT, creada TEXT, respuesta TEXT);
CREATE TABLE IF NOT EXISTS borradores(desafio_id TEXT, alumno_id TEXT, estado TEXT, actualizado TEXT, PRIMARY KEY(desafio_id, alumno_id));
CREATE TABLE IF NOT EXISTS practica(id INTEGER PRIMARY KEY AUTOINCREMENT, alumno_id TEXT, fecha TEXT, segundos INTEGER);
CREATE TABLE IF NOT EXISTS repasos(id INTEGER PRIMARY KEY AUTOINCREMENT, alumno_id TEXT, estrategia TEXT, criterio TEXT, vence TEXT, paso INTEGER, origen_intento INTEGER, hecho INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS ref_revisada(ticker TEXT, corte TEXT, estrategia TEXT, clase TEXT, nota TEXT, autor TEXT, creada TEXT, PRIMARY KEY(ticker, corte, estrategia));
CREATE TABLE IF NOT EXISTS posterior(desafio_id TEXT PRIMARY KEY, datos TEXT, agregado TEXT);
"""


def con():
    c = sqlite3.connect(DB, timeout=20); c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, con() as c:
        c.executescript(SCHEMA)
        for k, v in (("rubrica", df.RUBRICA), ("umbrales_dominio", df.UMBRALES_DOMINIO), ("meta_diaria_min", {"version": "meta-1", "minutos": 60})):
            if not c.execute("SELECT 1 FROM config WHERE clave=?", (k,)).fetchone():
                c.execute("INSERT INTO config VALUES(?,?,?,?)", (k, json.dumps(v), v["version"], ahora()))


def ahora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def q(sql, args=(), uno=False):
    with _lock, con() as c:
        r = c.execute(sql, args)
        rows = [dict(x) for x in r.fetchall()] if r.description else []
        return (rows[0] if rows else None) if uno else rows


def ej(sql, args=()):
    with _lock, con() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def cfg(clave):
    r = q("SELECT valor FROM config WHERE clave=?", (clave,), True)
    return json.loads(r["valor"]) if r else None


def set_cfg(clave, valor):
    ej("INSERT OR REPLACE INTO config VALUES(?,?,?,?)", (clave, json.dumps(valor), valor.get("version", ""), ahora()))


def alumno(aid, nombre=None):
    r = q("SELECT * FROM alumnos WHERE id=?", (aid,), True)
    if not r:
        ej("INSERT INTO alumnos VALUES(?,?,?)", (aid, nombre or aid, ahora()))
        r = q("SELECT * FROM alumnos WHERE id=?", (aid,), True)
    return r

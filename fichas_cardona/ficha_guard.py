"""Guarda de señal vigente para Fichas Cardona (solo lectura, no toca el scanner).

validar_ficha(ficha, ahora, ya_usadas) -> (ok, [motivos])
Una ficha solo puede comprarse si TODAS las comprobaciones pasan.
"""
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Feriados NYSE 2026 (cierre total). Medias sesiones: 27/11 y 24/12 cierran 13:00.
FERIADOS = {"2026-11-26", "2026-12-25", "2027-01-01"}
MEDIA_SESION = {"2026-11-27": dtime(13, 0), "2026-12-24": dtime(13, 0)}

HORA_MIN_COMPRA = dtime(11, 0)               # regla Cardona
EXCEPCION_10 = {"VELA_ROJA"}                 # Primera Vela Roja: 10:00
MAX_EDAD_DATO_MIN = 90                       # último dato vs ahora
CONDICIONES_OK = "Cumple"


def _et(dt):
    return dt.astimezone(ET) if dt.tzinfo else dt.replace(tzinfo=ET)


def sesion_abierta(ahora):
    a = _et(ahora)
    d = a.strftime("%Y-%m-%d")
    if a.weekday() >= 5 or d in FERIADOS:
        return False
    cierre = MEDIA_SESION.get(d, dtime(16, 0))
    return dtime(9, 30) <= a.time() < cierre


def validar_ficha(f, ahora, ya_usadas):
    """f: dict con ticker, strategy_id, direction, bar_time (datetime de INICIO de barra),
    bar_minutes (60; 30 para la 1a barra), last_data_time, modo ('PAPER'), condiciones [{nombre, estado, necesaria}]."""
    m = []
    a = _et(ahora)
    if f.get("modo") != "PAPER":
        m.append("MODO_NO_PAPER")
    if not sesion_abierta(a):
        m.append("MERCADO_CERRADO")
    bt = _et(f["bar_time"])
    if bt.date() != a.date():
        m.append("BARRA_DE_OTRA_SESION")
    if bt + timedelta(minutes=f.get("bar_minutes", 60)) > a:
        m.append("BARRA_NO_CERRADA")
    if (a - _et(f["last_data_time"])) > timedelta(minutes=MAX_EDAD_DATO_MIN):
        m.append("DATO_VIEJO")
    minimo = dtime(10, 0) if f["strategy_id"] in EXCEPCION_10 else HORA_MIN_COMPRA
    if a.time() < minimo:
        m.append("ANTES_DE_HORA_PERMITIDA")
    clave = f"{f['ticker']}|{f['strategy_id']}|{bt.isoformat()}"
    if clave in ya_usadas:
        m.append("DUPLICADA")
    nec = [c for c in f.get("condiciones", []) if c.get("necesaria", True)]
    if not nec:
        m.append("SIN_CONDICIONES")
    if any(c["estado"] != CONDICIONES_OK for c in nec):
        m.append("CONDICIONES_INCOMPLETAS")
    return (not m), m, clave

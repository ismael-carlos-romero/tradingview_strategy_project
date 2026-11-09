"""Prueba seca NVDA PISO_FUERTE: sin órdenes. Usa una BD temporal, no la de producción."""
import json, os, sqlite3, sys
from datetime import datetime
sys.path.insert(0, os.path.dirname(__file__))
from ficha_guard import ET
import ficha_flow as F

db = sqlite3.connect(":memory:")
db.execute("CREATE TABLE configuracion (param_id TEXT PRIMARY KEY, val TEXT)")
print("fuente activa por defecto:", F.estado_fuente(db))
F.fijar_fuente(db, True); print("tras activar:", F.estado_fuente(db)); F.fijar_fuente(db, False); print("tras pausar:", F.estado_fuente(db))

T = lambda d, h, m=0: datetime(2026, 10, d, h, m, tzinfo=ET)
ficha = dict(ficha_id="NVDA|PISO_FUERTE|2026-10-27T10:00", ticker="NVDA", strategy_id="PISO_FUERTE", direction="CALL",
             bar_time=T(27, 10), bar_minutes=60, last_data_time=T(27, 11, 0), modo="PAPER",
             condiciones=[dict(nombre="caída >1.5% en el día", estado="Cumple"), dict(nombre="vela del día verde", estado="Cumple"),
                          dict(nombre="piso (soporte) validado", estado="Cumple")])
usadas = set()
for nombre, ahora, fi in [("SIMULADA vigente 11:05 (hora ficticia, dato ficticio)", T(27, 11, 5), ficha),
                          ("MISMA ficha otra vez (duplicada)", T(27, 11, 6), ficha),
                          ("AHORA REAL premercado con barra de ayer", T(27, 8, 30), dict(ficha, bar_time=T(26, 15), last_data_time=T(26, 16))),
                          ("Con 1 condición pendiente de revisión", T(27, 11, 7), dict(ficha, ficha_id="otra", bar_time=T(27, 9, 30), condiciones=[dict(nombre="piso validado", estado="Pendiente")]))]:
    ok, mot, clave, prop = F.proponer(fi, ahora, usadas, spot=216.0)
    nuevo = F.registrar(db, fi, ok, mot, clave, prop)
    if ok and nuevo:
        usadas.add(clave)
    print("\n##", nombre, "| ok:", ok, "| motivos:", mot, "| registrada:", nuevo)
    if prop:
        print(json.dumps(prop, ensure_ascii=False, indent=1))
print("\nlog:", db.execute("select ticker,strategy_id,estado,motivos from fichas_cardona_log").fetchall())
print("ORDENES ENVIADAS: 0")

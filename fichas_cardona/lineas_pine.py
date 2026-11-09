"""Genera el cuadro 'Datos de fichas' del Pine desde facts.json. No inventa líneas: usa solo los pivotes de la ficha."""
import json, os, sys
from datetime import datetime

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
facts = json.load(open(os.path.join(base, "analisis", "2026-10-27_pre", "fichas", "facts.json"), encoding="utf-8"))
clave = sys.argv[1] if len(sys.argv) > 1 else "NVDA_CANAL"
f = facts[clave]
ms = lambda s: int(datetime.fromisoformat(s).timestamp() * 1000)
lin = f["linea60"]
p1, p2 = lin["p1"], lin["p2"]
crit = "2 pivotes confirmados; criterio de linea PENDIENTE de validar por Ismael"
filas = [
    f"L|{f['t']}|CANAL_BREAK|CALL|PENDIENTE|{ms(p1[0])}|{p1[1]}|{ms(p2[0])}|{p2[1]}|1|{crit}",
    f"M|{f['t']}|CANAL_BREAK|CALL|PENDIENTE|{ms(f['ultima_vela_alineada'])}|{f['d_close']}|cierre de ayer {lin['cierre_ayer_vs_linea']}% bajo la linea (aun sin ruptura)",
]
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"datos_{clave}.txt")
open(out, "w", encoding="utf-8").write("\n".join(filas))
print("\n".join(filas))
print("archivo:", out)

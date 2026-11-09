import re
p = "fichas_diario.py"
s = open(p, encoding="utf-8").read()
s = s.replace("import cardona_rules as cr\n", "import cardona_rules as cr\nsys.path.insert(0, AQUI)\nfrom techo_piso import techo_piso\n", 1)
a = s.index("        d = cr.descending_line(h, n, 60)")
b = s.index("    except Exception as e:")
s = s[:a] + "        f.update(techo_piso(h, ahora))\n" + s[b:]
s = s.replace('"canal_bajista": "", "canal_alcista": "", "filas_pine": []}', '"filas_pine": []}', 1)
s = s.replace('"senales_motor", "canal_bajista", "canal_alcista"]', '"senales_motor", "ruptura", "techo_proy", "dist_techo_pct", "piso_proy", "dist_piso_pct", "caso", "ancla_techo", "ancla_piso", "ruptura_hora"]', 1)
# Pine: ya no lleva datos; se copia el archivo v6 fijo
a = s.index("    bl = trozos(filas)[:4]")
b = s.index("    cols = [")
s = s[:a] + '    import shutil\n    shutil.copy(os.path.join(AQUI, "meliora_fichas_cardona_v6.pine"), os.path.join(carpeta, "meliora_fichas_cardona.pine"))\n' + s[b:]
s = s.replace('PINE = open(os.path.join(AQUI, "pine_plantilla.pine"), encoding="utf-8").read()\n', "", 1)
s = s.replace("Canales: pendientes de validar.", "TECHO/PISO estilo Ismael (ventana 5 sesiones, velas alineadas Cardona; proyectados a la vela de las 10:30 ET de mañana): CALL = vela verde que cierra sobre el techo, PUT = vela roja que cierra bajo el piso; SIN_PIVOTE = no calculable.", 1)
open(p, "w", encoding="utf-8").write(s)
print("parche ok")

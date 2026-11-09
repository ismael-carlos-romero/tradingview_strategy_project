import shutil
shutil.copy("lineas_azules.py", "lineas_azules.py.bak1")
shutil.copy("fichas_diario.py", "fichas_diario.py.bak_lineas")
s = open("lineas_azules.py", encoding="utf-8").read()
a = 'fila["estado"] = "CORRECTO" if (r["techo"]["line"] or r["piso"]["line"] or r["techo"]["ev"] or r["piso"]["ev"]) else "SIN_ESTRUCTURA"'
assert s.count(a) == 1
s = s.replace(a, 'fila["estado"] = "CORRECTO" if (r["techo"]["line"] or r["piso"]["line"]) else "SIN_ESTRUCTURA"')
b = "                if k not in claves:\n"
assert s.count(b) == 1
s = s.replace(b, "                if k not in claves and (ahora - h.index[e['t']]).days <= 8:\n")
open("lineas_azules.py", "w", encoding="utf-8").write(s)
d = open("fichas_diario.py", encoding="utf-8").read()
if "lineas_azules" not in d:
    k = '    print(f"\\nLISTO:'
    assert d.count(k) == 1
    d = d.replace(k, '    try:\n        from lineas_azules import generar as gla\n        print("LINEAS AZULES:", gla(TICKERS, carpeta, ahora, corte)[0])\n    except Exception as e:\n        print("lineas_azules fallo:", e)\n' + k)
    open("fichas_diario.py", "w", encoding="utf-8").write(d)
print("ok")

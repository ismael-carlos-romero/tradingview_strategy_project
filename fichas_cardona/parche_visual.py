import shutil
for f in ("techo_piso.py", "fichas_diario.py"):
    shutil.copy(f, f + ".bak_visual")
s = open("techo_piso.py", encoding="utf-8").read()
if '"geo"' not in s:
    s = s.replace("        px = c[n]\n", '''        out["geo"] = {"n": int(n), "ws": int(ws), "D": int(D),
                      "techo": [int(techo[0]), float(techo[1]), float(techo[2])] if techo else None,
                      "piso": [int(piso[0]), float(piso[1]), float(piso[2])] if piso else None,
                      "call_i": int(call_i) if call_i is not None else None,
                      "put_i": int(put_i) if put_i is not None else None}
        px = c[n]
''', 1)
    open("techo_piso.py", "w", encoding="utf-8").write(s)
d = open("fichas_diario.py", encoding="utf-8").read()
if "ficha_visual" not in d:
    d = d.replace("        f.update(techo_piso(h, ahora))\n", "        f.update(techo_piso(h, ahora))\n        f[\"_h\"] = h\n", 1)
    d = d.replace('if k != "filas_pine"}', 'if k not in ("filas_pine", "geo") and not k.startswith("_")}', 1)
    d = d.replace('    print(f"\\nLISTO:', '    try:\n        from ficha_visual import generar\n        print("FICHAS VISUALES:", generar(res, carpeta, ahora, corte))\n    except Exception as e:\n        print("ficha_visual fallo:", e)\n    print(f"\\nLISTO:', 1)
    open("fichas_diario.py", "w", encoding="utf-8").write(d)
print("ok", "geo" in open("techo_piso.py", encoding="utf-8").read(), "ficha_visual" in open("fichas_diario.py", encoding="utf-8").read(), '"_h"' in open("fichas_diario.py", encoding="utf-8").read())

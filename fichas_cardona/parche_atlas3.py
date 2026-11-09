import os
AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI)
for p in (os.path.join(AQUI, "atlas_portal_seccion.html"), os.path.join(RAIZ, "index.html")):
    s = open(p, encoding="utf-8").read()
    for a, b in (("VIGILANCIA:'#5aa0e6'", "VIGILANCIA:'#c4dcf5'"), ("SHOWN=12", "SHOWN=6"), ("SHOWN+=12", "SHOWN+=6")):
        assert s.count(a) == 1, (p, a)
        s = s.replace(a, b)
    open(p, "w", encoding="utf-8").write(s)
print("ok")

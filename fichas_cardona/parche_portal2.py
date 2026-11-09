import os, shutil, py_compile
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AQUI = os.path.dirname(os.path.abspath(__file__))
ls, ix = os.path.join(BASE, "live_scanner.py"), os.path.join(BASE, "index.html")
shutil.copy(ls, ls + ".bak_portal_fichas2"); shutil.copy(ix, ix + ".bak_portal_fichas2")

NUEVO = '''        elif self.path.startswith('/api/fichas/lista') or self.path.startswith('/fichas/'):
            # Fichas Cardona: SOLO LECTURA de fichas_cardona/informes (sin ordenes, sin escritura)
            try:
                import re as _re
                from urllib.parse import unquote as _unq
                raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fichas_cardona", "informes")
                tipos = {".html": "text/html; charset=utf-8", ".pdf": "application/pdf", ".json": "application/json; charset=utf-8",
                         ".csv": "text/csv; charset=utf-8", ".pine": "text/plain; charset=utf-8", ".png": "image/png"}
                nombre_ok = lambda n: bool(_re.match(r'^[A-Za-z0-9_.\\- ]{1,150}$', n)) and '..' not in n and os.path.splitext(n)[1].lower() in tipos
                carpeta_ok = lambda d: bool(_re.match(r'^[A-Za-z0-9_\\-]{1,60}$', d))
                if self.path.startswith('/api/fichas/lista'):
                    out = []
                    if os.path.isdir(raiz):
                        for d in sorted(os.listdir(raiz), reverse=True):
                            p = os.path.join(raiz, d)
                            if carpeta_ok(d) and os.path.isdir(p):
                                arch = [a for a in sorted(os.listdir(p)) if nombre_ok(a) and os.path.isfile(os.path.join(p, a))]
                                if any(a.lower().endswith(('.html', '.pdf')) for a in arch):
                                    out.append({"carpeta": d, "archivos": arch})
                    body, ctype = json.dumps(out, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8'
                else:
                    partes = _unq(self.path.split('?')[0]).split('/')
                    if len(partes) != 4 or not carpeta_ok(partes[2]) or not nombre_ok(partes[3]):
                        self.send_response(404); self.end_headers(); return
                    fp = os.path.join(raiz, partes[2], partes[3])
                    if not os.path.isfile(fp):
                        self.send_response(404); self.end_headers(); return
                    body, ctype = open(fp, "rb").read(), tipos[os.path.splitext(partes[3])[1].lower()]
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500); self.end_headers()
            return
'''
s = open(ls, encoding="utf-8").read()
a = s.index("        elif self.path.startswith('/api/fichas/lista') or self.path.startswith('/fichas/'):")
b = s.index("        elif self.path == '/ping':\n")
assert a < b
s = s[:a] + NUEVO + s[b:]
open(ls, "w", encoding="utf-8").write(s)
py_compile.compile(ls, doraise=True)

h = open(ix, encoding="utf-8").read()
a = h.index("    <!-- FICHAS CARDONA")
b = h.index("    </section>\n", a) + len("    </section>\n")
sec = open(os.path.join(AQUI, "seccion_portal.html"), encoding="utf-8").read()
h = h[:a] + sec + h[b:]
open(ix, "w", encoding="utf-8").write(h)
print("portal2 ok")

import os, shutil, py_compile
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ls, ix = os.path.join(BASE, "live_scanner.py"), os.path.join(BASE, "index.html")
shutil.copy(ls, ls + ".bak_portal_fichas"); shutil.copy(ix, ix + ".bak_portal_fichas")

# ---- 1) endpoints de solo lectura en live_scanner.py ----
s = open(ls, encoding="utf-8").read()
if "/api/fichas/lista" not in s:
    nuevo = '''        elif self.path.startswith('/api/fichas/lista') or self.path.startswith('/fichas/'):
            # Fichas Cardona: SOLO LECTURA de fichas_cardona/informes (sin ordenes, sin escritura)
            try:
                raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fichas_cardona", "informes")
                permitidos = {"informe.html": "text/html; charset=utf-8", "resumen.json": "application/json; charset=utf-8",
                              "resumen.csv": "text/csv; charset=utf-8", "meliora_fichas_cardona.pine": "text/plain; charset=utf-8"}
                if self.path.startswith('/api/fichas/lista'):
                    out = []
                    if os.path.isdir(raiz):
                        for d in sorted(os.listdir(raiz), reverse=True):
                            p = os.path.join(raiz, d)
                            if os.path.isdir(p) and os.path.exists(os.path.join(p, "informe.html")):
                                out.append({"carpeta": d, "archivos": [a for a in permitidos if os.path.exists(os.path.join(p, a))]})
                    body, ctype = json.dumps(out, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8'
                else:
                    partes = self.path.split('?')[0].split('/')
                    if len(partes) != 4 or partes[3] not in permitidos or not partes[2] or '..' in partes[2] or '\\\\' in partes[2]:
                        self.send_response(404); self.end_headers(); return
                    fp = os.path.join(raiz, partes[2], partes[3])
                    if not os.path.isfile(fp):
                        self.send_response(404); self.end_headers(); return
                    body, ctype = open(fp, "rb").read(), permitidos[partes[3]]
                self.send_response(200)
                self.send_header('Content-Type', ctype)
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(500); self.end_headers()
            return
'''
    marca = "        elif self.path == '/ping':\n"
    assert s.count(marca) >= 1
    s = s.replace(marca, nuevo + marca, 1)
    open(ls, "w", encoding="utf-8").write(s)
py_compile.compile(ls, doraise=True)

# ---- 2) seccion en el portal ----
h = open(ix, encoding="utf-8").read()
if 'id="fichas-cardona"' not in h:
    item = '      <li><a href="#" class="menu-item" data-target="fichas-cardona">🗂️ Fichas Cardona</a></li>\n'
    h = h.replace('      <li><a href="#" class="menu-item" data-target="calculadora-1090">🧮 Calculadora 10/90</a></li>\n',
                  '      <li><a href="#" class="menu-item" data-target="calculadora-1090">🧮 Calculadora 10/90</a></li>\n' + item, 1)
    sec = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "seccion_portal.html"), encoding="utf-8").read()
    marca = "    <!-- CALCULADORA MELIORA 10/90 -->\n"
    assert marca in h
    h = h.replace(marca, sec + "\n" + marca, 1)
    open(ix, "w", encoding="utf-8").write(h)
print("portal ok")

import os, re, shutil, subprocess
AQUI = os.path.dirname(os.path.abspath(__file__)); RAIZ = os.path.dirname(AQUI)

# ---- 1) atlas_diario: barras para todos, laminas, primera corrida silenciosa
p = os.path.join(AQUI, "atlas_diario.py"); s = open(p, encoding="utf-8").read()
def rep(a, b):
    global s
    assert s.count(a) == 1, a[:60]
    s = s.replace(a, b)
rep('''        if any(v.get("etapa") in ("CASI", "CONFIRMADA", "CONFIRMADA_FUERA_DE_HORARIO") for v in a["e"].values()):
            w = h.iloc[-60:]''', '''        if True:
            w = h.iloc[-60:]''')
rep('''    nuevo, activos, eventos, asof = {}, [], [], ""''', '''    nuevo, activos, eventos, asof = {}, [], [], ""
    primera = not os.path.exists(estado_p)      # primera corrida: deja la base y NO avisa
    asegurar_laminas()''')
rep('''    if eventos:
        ap =''', '''    if primera:
        eventos = []
    if eventos:
        ap =''')
rep('''def run(tickers=None''', '''LAMINAS = {"GAP_NORMAL": "gap_normal_alza", "GAP_BAJISTA": "gap_bajista_alza", "PISO_FUERTE": "piso_fuerte", "PRIMER_GAP": "1er_gap_alza",
           "PM40": "pm40", "CAIDA": "caida_normal_fuerte", "CANAL_BREAK": "ruptura_canal_bajista", "VELA_ROJA": "primera_vela_roja",
           "RUPT_PISO": "ruptura_piso_gap", "CUATRO_PASOS": "modelo_4_pasos", "HANGER": "hanger_diario", "TECHO_FUERTE": "techo_fuerte"}


def asegurar_laminas():
    """Copia las laminas de Cardona (assets) a la carpeta que sirve el portal."""
    import shutil
    for k, n in LAMINAS.items():
        dst = os.path.join(OUT, f"lam_{k}.png"); src = os.path.join(os.path.dirname(AQUI), "assets", f"cardona_{n}.png")
        if not os.path.exists(dst) and os.path.exists(src):
            shutil.copyfile(src, dst)


def run(tickers=None''')
open(p, "w", encoding="utf-8").write(s)

# ---- 2) portal
ip = os.path.join(RAIZ, "index.html")
shutil.copyfile(ip, ip + ".bak_atlas")
h = open(ip, encoding="utf-8").read()
sec = open(os.path.join(AQUI, "atlas_portal_seccion.html"), encoding="utf-8").read()
assert 'id="atlas-vivo"' not in h
mk = "    <!-- FICHAS CARDONA (solo lectura"
assert h.count(mk) == 1
h = h.replace(mk, sec + mk)
li = '<li><a href="#" class="menu-item" data-target="fichas-cardona">'
assert h.count(li) == 1
i = h.index(li); j = h.index("</li>", i) + 5
h = h[:j] + '\n      <li><a href="#" class="menu-item" data-target="atlas-vivo">🛰️ Atlas vivo</a></li>' + h[j:]
open(ip, "w", encoding="utf-8").write(h)
# chequeo de sintaxis del JS de la seccion
js = re.search(r"<script>(.*?)</script>", sec, re.S).group(1)
open(os.path.join(AQUI, "_chk_atlas.js"), "w", encoding="utf-8").write(js)
print("node:", subprocess.run(["node", "--check", os.path.join(AQUI, "_chk_atlas.js")], capture_output=True, text=True).returncode)
os.remove(os.path.join(AQUI, "_chk_atlas.js"))
print("ok")

import os, shutil
p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "INICIAR_MELIORA_OPTIONS.bat")
b = open(p, "rb").read()
if b"atlas_servicio" in b:
    print("ya estaba")
else:
    shutil.copyfile(p, p + ".bak_atlas")
    k = b'start /min "Meliora Tunnel Server" python run_tunnel.py'
    assert b.count(k) == 1
    nl = b"\r\n" if b"\r\n" in b else b"\n"
    add = nl + nl + b":: 3b. Atlas vivo (analisis tecnico de las 12 estrategias, solo avisos; no opera)" + nl + \
          b'echo [Atlas] Iniciando servicio Atlas vivo en segundo plano...' + nl + \
          b'start /min "Meliora Atlas" python fichas_cardona\\atlas_servicio.py'
    b = b.replace(k, k + add)
    open(p, "wb").write(b)
    print("bat actualizado")

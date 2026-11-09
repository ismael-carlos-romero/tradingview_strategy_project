"""Solo las lineas azules (35 activos): python run_lineas.py [pre|post]  -> informes\\AAAA-MM-DD_pre|post\\"""
import os, sys
AQUI0 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI0))
sys.path.insert(0, AQUI0)
import pandas as pd
import cardona_rules as cr
import fichas_diario as fd
import lineas_azules as la

ahora = pd.Timestamp.now(tz=cr.NY)
corte = sys.argv[1] if len(sys.argv) > 1 else ("pre" if ahora.hour * 60 + ahora.minute < 570 else "post")
carpeta = os.path.join(fd.AQUI, "informes", f"{ahora:%Y-%m-%d}_{corte}")
os.makedirs(carpeta, exist_ok=True)
ruta, filas, datos = la.generar(fd.TICKERS, carpeta, ahora, corte)
print("LINEAS:", ruta)
for f in filas:
    print(f["ticker"], f["estado"], "| techo", f.get("techo", ""), "| piso", f.get("piso", ""), "| ult:", f.get("techo_ult", ""), f.get("piso_ult", ""))

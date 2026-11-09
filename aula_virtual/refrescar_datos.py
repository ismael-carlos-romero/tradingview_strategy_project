"""Uso: python aula_virtual\\refrescar_datos.py  -> descarga/acumula velas del universo vigente en aula_virtual\\cache"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from aula_virtual import datos

if __name__ == "__main__":
    u = datos.universo()
    print("universo:", u["n"], "activos (", u["fuente"], ") atlas:", u["atlas_n"], "solo_bot", u["solo_bot"], "solo_atlas", u["solo_atlas"])
    r = datos.refrescar(u["tickers"])
    print("ok", len(r["ok"]), "error", r["error"])
    for t in u["tickers"]:
        e = datos.estado(t)
        print(t, e.get("n_velas"), e.get("n_evaluables"), e.get("ultima_vela"), e.get("liquidez_usd_dia"), e.get("suficiente"), e.get("motivo", ""))

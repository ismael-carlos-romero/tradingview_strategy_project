"""Uso: python -m aula_virtual.construir_indice [TICKER ...]  -> evalua las 12 estrategias en cada corte evaluable y guarda cache\\indice.json"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if __name__ == "__main__":
    from aula_virtual import motor
    t0 = time.time()
    m = motor.construir_indice(sys.argv[1:] or None, workers=12)
    print("indice:", m["n"], "evaluaciones en", round(time.time() - t0), "s;", m["atlas"], m["definiciones"])

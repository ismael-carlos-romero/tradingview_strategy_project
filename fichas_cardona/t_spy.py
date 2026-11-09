import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import lineas_azules as la
d = la.cargar_todos(["SPY"])["SPY"]
hi = d["High"].values; c = d["Close"].values; n = len(d)
pv = la.pivotes(hi, "max")
i1 = [i for i in pv if f"{d.index[i]:%d/%m %H:%M}" == "09/10 14:30"][0]
print("n", n, "ultima", d.index[-1], "close", c[-1])
for j in pv:
    if j > i1:
        sl = (hi[j] - hi[i1]) / (j - i1)
        viol = [f"{d.index[k]:%d/%m %H:%M} +{c[k]-(hi[i1]+sl*(k-i1)):.2f}" for k in range(i1 + 1, n) if c[k] > hi[i1] + sl * (k - i1) + 1e-6]
        if len(viol) < 9: print("   ", viol)
        print(f"{d.index[j]:%d/%m %H:%M} high {hi[j]:.2f} pend {sl:.3f} linea@ult {hi[i1]+sl*(n-1-i1):.2f} cierres_sobre {len(viol)}")

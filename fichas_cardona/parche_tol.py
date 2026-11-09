f = "lineas_azules.py"
s = open(f, encoding="utf-8").read()
reps = [
 ("PL_, PR_, MAXB, EPS, MAXVIDA = 4, 3, 84, 1e-6, 300", "PL_, PR_, MAXB, EPS, MAXVIDA = 4, 3, 84, 1e-6, 300\nTOLP = 0.0005  # un cierre puede rozar/pasar la linea hasta 0,05 % sin invalidarla (tu SPY: 0,02 %)"),
 ("if s * (c[t] - v) > EPS:\n                    prev_ok = s * (c[t - 1] - vp) <= EPS", "if s * (c[t] - v) > TOLP * c[t]:\n                    prev_ok = s * (c[t - 1] - vp) <= TOLP * c[t - 1]"),
 ('<= EPS for k in range(ln["i1"] + 1, t + 1)', '<= TOLP * c[k] for k in range(ln["i1"] + 1, t + 1)'),
 ('<= EPS for j in range(i1 + 1, t + 1)', '<= TOLP * c[j] for j in range(i1 + 1, t + 1)'),
 ("if s * (c[t] - v) > EPS and s * (c[t - 1] - vp) <= EPS and col:", "if s * (c[t] - v) > TOLP * c[t] and s * (c[t - 1] - vp) <= TOLP * c[t - 1] and col:"),
]
for a, b in reps:
    assert s.count(a) == 1, a
    s = s.replace(a, b)
s = s.replace("tal que NINGUN cierre entre ambos anclas (ni hasta hoy) quede sobre la linea.", "tal que ningun cierre (hasta hoy) quede sobre la linea por mas de TOLP (0,05 %).")
open(f, "w", encoding="utf-8").write(s)
print("ok")

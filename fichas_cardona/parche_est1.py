e = open("atlas_estrategias.py", encoding="utf-8").read()


def r2(a, b):
    global e
    assert e.count(a) == 1, a[:60]
    e = e.replace(a, b)


r2('S("Viene de una caída", caida_diaria(dr) or dr.Close < dr.sma20),', 'S("Viene de una caída (diario)", caida_diaria(dr)),')
r2('zona = bool(dr.Close >= 0.97 * dr.hi20 or (ln is not None and r.High >= lc.valor(ln, i) * 0.98))',
   'zona = bool(dr.Close >= 0.99 * dr.hi20 or (ln is not None and r.High >= lc.valor(ln, i) * 0.99))')
r2('''    st = [S("Cierre previo con vela roja", dr.red),
          S(f"Abre con gap/verde de bajo volumen lejos de PM40 (≥ {usd}$)", abre),''',
   '''    prev = h[h["date"] < x.today]
    h0 = prev.iloc[-1] if (not x.cerrado and len(prev)) else r
    st = [S(f"Cierre previo con vela roja y precio ≥ {usd}$ sobre PM40 (zona cara)", dr.red and (h0.Close - h0.PM40 >= usd)),
          S("Abre con gap/verde de bajo volumen lejos de PM40", abre),''')
open("atlas_estrategias.py", "w", encoding="utf-8").write(e)
print("ok")

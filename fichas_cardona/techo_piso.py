"""TECHO / PISO estilo Ismael: mismas reglas que el Pine v6 «Meliora Fichas Cardona». SOLO ANALISIS.
Entrada: h = velas alineadas Cardona (Open/High/Low/Close, indice tz NY); ahora = hora actual NY.
Ventana: ultimas NSES sesiones. Caso A (ultimo tramo bajista): P = vela ROJA del minimo (si el minimo es verde, la ultima roja anterior).
  TECHO = A (maximo de la ventana antes de P) -> high de P (con control: ningun cierre entre A y P sobre la linea; si no, la roja anterior mas cercana que cumpla).
  PISO  = low de P -> low de la ultima vela de la ultima sesion completa (solo si ese minimo es mayor que el de P).
Caso B (espejo): P = vela VERDE del maximo; PISO = minimo previo -> low de P (control espejo); TECHO = high de P -> high de la ultima vela (solo si es menor).
CALL: 1ra vela verde que cierra sobre el techo despues del ancla; PUT: 1ra vela roja que cierra bajo el piso.
Proyeccion: precio de la linea en la vela D+2 (10:30 ET del dia siguiente en velas de 1h). Lo que no se puede calcular = SIN_PIVOTE."""
import numpy as np

NSES = 5
EPS = 1e-6


def techo_piso(h, ahora, nses=NSES):
    out = {"ruptura": "SIN_PIVOTE", "caso": "", "techo_proy": None, "piso_proy": None,
           "dist_techo_pct": None, "dist_piso_pct": None, "ancla_techo": "", "ancla_piso": "", "ruptura_hora": ""}
    try:
        o, hi, lo, c = (h[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
        n = len(h) - 1
        dias = list(h.index.normalize())
        udias = list(dict.fromkeys(dias))
        if len(udias) < 2 or n < 5:
            return out
        first = {d: dias.index(d) for d in udias}
        ws = first[udias[max(0, len(udias) - nses)]]
        ult = udias[-1]
        en_curso = ahora.normalize() == ult and (ahora.hour * 60 + ahora.minute) < 960
        D = first[ult] - 1 if en_curso else n
        if D <= ws:
            return out
        low_i = ws
        high_i = ws
        for j in range(ws, n + 1):
            if lo[j] <= lo[low_i]:
                low_i = j
            if hi[j] >= hi[high_i]:
                high_i = j
        rojo = lambda j: c[j] < o[j]
        verde = lambda j: c[j] > o[j]
        techo = piso = None          # (x1, y1, pendiente)
        call_i = put_i = None
        ts = lambda j: f"{h.index[j]:%d/%m %H:%M}"
        if low_i > high_i:
            out["caso"] = "A (ultimo tramo bajista)"
            p = low_i
            while p > ws and not rojo(p):
                p -= 1
            if rojo(p):
                a = ws
                for j in range(ws, p + 1):
                    if hi[j] >= hi[a]:
                        a = j
                if p - a >= 1:
                    hA = hi[a]
                    b = None
                    for cand in range(p, a, -1):
                        if rojo(cand):
                            sl = (hi[cand] - hA) / (cand - a)
                            if all(c[j] <= hA + sl * (j - a) + EPS for j in range(a + 1, p + 1)):
                                b = cand
                                break
                    if b is not None:
                        sl = (hi[b] - hA) / (b - a)
                        techo = (a, hA, sl)
                        out["ancla_techo"] = f"A {ts(a)} {hA:.2f} -> B {ts(b)} {hi[b]:.2f}"
                        for j in range(p + 1, n + 1):
                            if verde(j) and c[j] > hA + sl * (j - a):
                                call_i = j
                                break
                if D > p and lo[D] > lo[p]:
                    sl = (lo[D] - lo[p]) / (D - p)
                    piso = (p, lo[p], sl)
                    out["ancla_piso"] = f"C {ts(p)} {lo[p]:.2f} -> D {ts(D)} {lo[D]:.2f}"
                    for j in range(D + 1, n + 1):
                        if rojo(j) and c[j] < lo[p] + sl * (j - p):
                            put_i = j
                            break
        else:
            out["caso"] = "B (espejo: ultimo tramo alcista)"
            p = high_i
            while p > ws and not verde(p):
                p -= 1
            if verde(p):
                q = ws
                for j in range(ws, p + 1):
                    if lo[j] <= lo[q]:
                        q = j
                if p - q >= 1:
                    lQ = lo[q]
                    r = None
                    for cand in range(p, q, -1):
                        if verde(cand):
                            sl = (lo[cand] - lQ) / (cand - q)
                            if all(c[j] >= lQ + sl * (j - q) - EPS for j in range(q + 1, p + 1)):
                                r = cand
                                break
                    if r is not None:
                        sl = (lo[r] - lQ) / (r - q)
                        piso = (q, lQ, sl)
                        out["ancla_piso"] = f"Q {ts(q)} {lQ:.2f} -> R {ts(r)} {lo[r]:.2f}"
                        for j in range(p + 1, n + 1):
                            if rojo(j) and c[j] < lQ + sl * (j - q):
                                put_i = j
                                break
                if D > p and hi[D] < hi[p]:
                    sl = (hi[D] - hi[p]) / (D - p)
                    techo = (p, hi[p], sl)
                    out["ancla_techo"] = f"P {ts(p)} {hi[p]:.2f} -> D {ts(D)} {hi[D]:.2f}"
                    for j in range(D + 1, n + 1):
                        if verde(j) and c[j] > hi[p] + sl * (j - p):
                            call_i = j
                            break
        out["geo"] = {"n": int(n), "ws": int(ws), "D": int(D),
                      "techo": [int(techo[0]), float(techo[1]), float(techo[2])] if techo else None,
                      "piso": [int(piso[0]), float(piso[1]), float(piso[2])] if piso else None,
                      "call_i": int(call_i) if call_i is not None else None,
                      "put_i": int(put_i) if put_i is not None else None}
        px = c[n]
        if techo:
            v = techo[1] + techo[2] * (D + 2 - techo[0])
            out["techo_proy"] = round(float(v), 2)
            out["dist_techo_pct"] = round(float((v - px) / px * 100), 2)
        if piso:
            v = piso[1] + piso[2] * (D + 2 - piso[0])
            out["piso_proy"] = round(float(v), 2)
            out["dist_piso_pct"] = round(float((v - px) / px * 100), 2)
        if techo or piso:
            if call_i is not None:
                out["ruptura"], out["ruptura_hora"] = "CALL", ts(call_i)
            elif put_i is not None:
                out["ruptura"], out["ruptura_hora"] = "PUT", ts(put_i)
            else:
                out["ruptura"] = "NINGUNA"
    except Exception as e:
        out["ruptura"] = f"SIN_PIVOTE ({str(e)[:40]})"
    return out

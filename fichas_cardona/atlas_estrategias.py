"""Las 12 estrategias (orden del mapa de vigilancia). Cada funcion f(x, manana=False) -> dict de atlas_motor.res()."""
import numpy as np
from atlas_motor import *
import lineas_cardona as lc


def _gap_hoy(x, manana):
    """Pasos comunes de gap: (gap, 1a vela) o None si es el escenario de manana."""
    return None if manana else x.r


# 1 GAP NORMAL AL ALZA (CALL) - lamina 5ta
def gap_normal(x, manana=False):
    dr, r = x.dr, x.r
    f, s2, s3 = nth(x, 0), nth(x, 1), nth(x, 2)
    st = [S("Tendencia alcista diaria (PM100>PM200)", dr.sma100 > dr.sma200),
          S("Cierre previo en tendencia alcista", dr.Close > dr.sma100),
          S("Apertura con salto al alza y 1ª vela verde", None if manana else (r.gap >= GAP_MIN and r.first_green), "" if manana else f"gap {r.gap:.2f}%"),
          S("2ª vela verde sólida o martillo (10:00-11:00)", None if manana or s2 is None else verde_fuerte(s2)),
          S("3ª vela final (11:00-12:00) de alto volumen", None if manana or s3 is None else s3.rvol > RVOL_ALTO)]
    return res(x, st, 2, (660, 720), "CALL", nota="Los GAP-NA en canales bajistas son inestables (lámina).")


# 2 GAP BAJISTA AL ALZA (CALL) - lamina 6ta
def gap_bajista(x, manana=False):
    dr, r, h = x.dr, x.r, x.h
    s2, s3 = nth(x, 1), nth(x, 2)
    ln = lc.linea_caida(h, x.i, 80)
    st = [S("Canal bajista (línea de caída)", ln is not None),
          S("Cierre previo al alza con vela verde", dr.green),
          S("Apertura abajo y 1ª vela verde", None if manana else (r.gap <= -GAP_MIN and r.first_green), "" if manana else f"gap {r.gap:.2f}%"),
          S("2ª vela verde (10:00-11:00)", None if manana or s2 is None else s2.Close > s2.Open),
          S("3ª vela (11:00-12:00) de alto volumen", None if manana or s3 is None else s3.rvol > RVOL_ALTO)]
    return res(x, st, 2, (660, 960), "CALL", [draw_linea(ln)])


# 3 PISO FUERTE (CALL) - lamina 7ma
def piso_fuerte(x, manana=False):
    dr, h = x.dr, x.h
    w = x.D.iloc[-3:]
    toca = bool((w.Low <= w.sma100 * 1.005).any() or (w.Low <= w.sma200 * 1.005).any())
    ln_rot = lc.ruptura_call(h, x.i)
    st = [S("PM100>PM200 diarios (piso fuerte)", dr.sma100 > dr.sma200),
          S("Viene de una caída (diario)", caida_diaria(dr)),
          S("Velas rojas diarias tocan o rompen PM100/PM200", toca),
          S("Hora: martillo/verde final rompe la línea de techo del canal bajista", ln_rot is not None and verde_fuerte(x.r))]
    return res(x, st, 3, (660, 960), "CALL", [draw_linea(ln_rot or lc.linea_caida(h, x.i))])


# 4 PRIMER GAP AL ALZA (CALL) - lamina 9na
def primer_gap(x, manana=False):
    dr, r, h = x.dr, x.r, x.h
    f = nth(x, 0)
    pisof = float(r.first_low) if not manana else None
    post = x.hoy.iloc[1:]
    previos = h[(h["date"] < x.today)].groupby("date").gap.first().iloc[-5:]
    primero = bool((previos < GAP_MIN).all())
    s3 = None if manana or f is None else (r.gap >= GAP_MIN and r.first_green and f.solid_green and f.rvol > RVOL_ALTO and primero)
    st = [S("Viene de una caída (diario)", caida_diaria(dr)),
          S("Zona de piso fuerte diario (cerca o bajo PM100/PM200)", cerca_piso_diario(dr)),
          S("Gap al alza, 1ª vela verde llena con volumen; primer gap tras la caída", s3, "" if manana else f"gap {r.gap:.2f}%"),
          S("Las demás velas respetan el piso del gap", None if manana or s3 is None else bool((post.Close >= pisof).all())),
          S("Última vela del día (3:58pm) cerrada con el piso respetado", None if manana else x.cerrado)]
    d = [{"k": "piso_gap", "y": round(pisof, 2), "j": int(x.i - len(x.hoy) + 1)}] if pisof else []
    return res(x, st, 2, (957, 960), "CALL", d, "Salida: vela roja que rompe el piso del gap (lámina).")


# 5 PM40 HORA (CALL) - lamina 2da
def pm40(x, manana=False):
    h, r, i = x.h, x.r, x.i
    lp = lc.linea_caida(h, i - 1)
    rompe = bool(lp and r.Close > lc.valor(lp, i))
    ln = lp if rompe else lc.linea_caida(h, i)
    caida = 0.0
    if ln:
        pk = float(h.High.iloc[ln[0]:i].max()); caida = (pk - float(h.Low.iloc[ln[0]:i + 1].min())) / pk * 100
    w4, w5 = h.iloc[-4:], h.iloc[-5:]
    rojas = bool((w5.Close.iloc[:-1] < w5.PM20.iloc[:-1]).any() or r.Close < r.PM20)
    toca = bool(((w4.Low <= w4.PM40 * 1.0015) & (w4.Close >= w4.PM40 * 0.9985)).any())
    st = [S("PM20>PM40 y PM100>PM200 en paralelo", paralelo(h)),
          S("Viene de una caída con línea descendente", ln is not None and caida >= CAIDA_MIN, f"{caida:.2f}%"),
          S("Rojas finales rompen PM20 y tocan PM40", rojas and toca),
          S("Verde final (sólida/martillo) rompe PM20 y la línea", rompe and verde_fuerte(r) and r.Close > r.PM20)]
    return res(x, st, 2, (660, 960), "CALL", [draw_linea(ln)])


# 6 CAIDA NORMAL / FUERTE (CALL) - lamina 3ra
def caida(x, manana=False):
    h, r, i = x.h, x.r, x.i
    ln = lc.linea_caida(h, i)
    w = h.iloc[-6:]
    rompe20 = bool((w.Close < w.PM20).any())
    fuerte = bool((w.Low <= w.PM100).any() or (w.Low <= w.PM200).any()) if rompe20 else False
    rot = lc.ruptura_call(h, i)
    prev = h.iloc[i - 1]
    st = [S("PM20>PM40 y PM100>PM200 en paralelo", paralelo(h)),
          S("Viene de una caída con línea descendente", ln is not None),
          S("2-3 rojas finales rompen PM20" + (" y PM100/PM200 (fuerte)" if fuerte else " sin romper PM40"), rompe20),
          S("Martillo verde y verde final rompen la línea de techo", rot is not None and (verde_fuerte(r) or verde_fuerte(prev)))]
    return res(x, st, 2, (660, 960), "CALL", [draw_linea(rot or ln)], "Subtipo: " + ("FUERTE" if fuerte else "NORMAL") + " (propio: fuerte si toca PM100/PM200)")


# 7 RUPTURA DEL CANAL BAJISTA (CALL) - lamina 4ta
def canal_break(x, manana=False):
    h, r, i = x.h, x.r, x.i
    ln = lc.linea_caida(h, i, 120)
    w = h.iloc[-3:]
    rot = lc.ruptura_call(h, i)
    st = [S("Canal bajista: PM40 sobre PM20 y línea de techo", ln is not None and r.PM40 > r.PM20),
          S("Martillo verde reciente", bool(((w.Close > w.Open) & (w.hammer | w.solid_green)).any())),
          S("Verde final de volumen rompe la línea de techo", rot is not None and r.rvol > RVOL_ALTO)]
    return res(x, st, 1, (660, 960), "CALL", [draw_linea(rot or ln)])


# 8 1a VELA ROJA DE LAS 10 (PUT) - lamina 1ra
def vela_roja(x, manana=False):
    h, r, i = x.h, x.r, x.i
    f, s2 = nth(x, 0), nth(x, 1)
    ln = lc.linea_caida(h, i, 80)
    zona = ln is not None and (r.Close < r.PM40 or abs(r.Close - r.PM40) / r.PM40 < 0.015)
    pg = cuerpo_bajo(f) if f is not None else None
    st = [S("Canal bajista, velas bajo/cerca de PM40 (zona cara)", zona),
          S("Abre con vela roja bajo PM40", None if manana or f is None else (f.Close < f.Open and f.Close < f.PM40)),
          S("Vela roja final rompe con el cuerpo la línea de piso del gap", None if manana or s2 is None else (s2.Close < s2.Open and s2.Close < pg))]
    d = [draw_linea(ln)] + ([{"k": "piso_gap", "y": round(pg, 2), "j": int(i - len(x.hoy) + 1)}] if pg else [])
    return res(x, st, 1, (600, 660), "PUT", d, "Única estrategia que se compra a las 10am (lámina).")


# 9 RUPTURA DEL PISO DEL GAP (PUT) - lamina 2da PUT
def rupt_piso(x, manana=False):
    h, r, i, dr = x.h, x.r, x.i, x.dr
    f = nth(x, 0)
    usd = SPOT_USD_ALC if paralelo(h, 10) else SPOT_USD
    pg = cuerpo_bajo(f) if f is not None else None
    lejos = None if manana or f is None else bool(f.Close - f.PM40 >= usd)
    abre = None if manana or f is None else bool((r.gap > 0 or f.Close > f.Open) and lejos)
    rompe = None if manana or f is None or len(x.hoy) < 3 else bool(r.Close < r.Open and r.Close < pg and r.end_min >= 660)
    prev = h[h["date"] < x.today]
    h0 = prev.iloc[-1] if (not x.cerrado and len(prev)) else r
    st = [S(f"Cierre previo con vela roja y precio ≥ {usd}$ sobre PM40 (zona cara)", dr.red and (h0.Close - h0.PM40 >= usd)),
          S("Abre con gap/verde de bajo volumen lejos de PM40", abre),
          S("Vela roja final (≥11am) rompe con el cuerpo la línea de piso del gap", rompe)]
    d = [{"k": "piso_gap", "y": round(pg, 2), "j": int(i - len(x.hoy) + 1)}] if pg else []
    return res(x, st, 1, (660, 720), "PUT", d, "Umbral en USD literal de la lámina (SPY/QQQ): en activos baratos casi no se da.")


# 10 MODELO DE LOS 4 PASOS (PUT) - lamina 3ra PUT
def cuatro_pasos(x, manana=False):
    h, r, i = x.h, x.r, x.i
    techo, piso = lc.linea_caida(h, i, 80), lc.linea_subida(h, i, 60)
    prev = h.iloc[i - 1]
    borra = bool(prev.Close > prev.Open and r.Close < r.Open and r.Close < prev.Open and techo is not None
                 and prev.High >= lc.valor(techo, i - 1) * 0.995)
    rot = lc.ruptura_put(h, i)
    st = [S("Canal bajista: PM40 sobre PM20 y velas bajo PM40 (zona cara)", r.PM40 > r.PM20 and r.Close < r.PM40),
          S("Líneas de techo y de piso del canal trazadas", techo is not None and piso is not None),
          S("Vela verde en zona de techo borrada por roja", borra),
          S("Vela roja final rompe la línea de piso", rot is not None)]
    return res(x, st, 2, (660, 720), "PUT", [draw_linea(techo), draw_linea(rot or piso, "piso")])


# 11 HANGER EN DIARIO (PUT) - lamina 4ta PUT
def hanger(x, manana=False):
    h, r, i, dr = x.h, x.r, x.i, x.dr
    t = x.hoy
    ln = lc.linea_caida(h, i, 80)
    zona = bool(dr.Close >= 0.99 * dr.hi20 or (ln is not None and r.High >= lc.valor(ln, i) * 0.99))
    w = h.iloc[-6:]
    pat = bool(len(w) == 6 and (w.Close.iloc[:4] > w.Open.iloc[:4]).all() and (w.Close.iloc[4:] < w.Open.iloc[4:]).all()
               and (w.rvol.iloc[4:] > RVOL_ALTO).all() and w.Close.iloc[-1] < w.Open.iloc[0])
    O, H_, L_, C = t.Open.iloc[0], t.High.max(), t.Low.min(), t.Close.iloc[-1]
    rg, bd = H_ - L_, abs(C - O)
    hd = bool(x.cerrado and rg > 0 and (H_ - max(O, C)) >= 0.45 * rg and bd <= 0.4 * rg and C < O)
    st = [S("Zona de techo (cerca del máximo de 20 ruedas o de la línea de techo)", zona),
          S("Hora: 4 verdes seguidas y 2 rojas de volumen que las borran", pat),
          S("Hanger diario confirmado al cierre (3:57pm)", hd)]
    return res(x, st, 1, (957, 960), "PUT", [draw_linea(ln)])


# 12 TECHO FUERTE (lamina 8va; titulo CALL, criterios 5-6 PUT -> PUT con ambiguedad marcada)
def techo_fuerte(x, manana=False):
    h, r, i, dr = x.h, x.r, x.i, x.dr
    Dd = x.D.iloc[-260:]
    nivel = float(Dd.High.max())
    toques = Dd[(Dd.High >= nivel * 0.99)]
    sep = len(toques) >= 2 and (toques.index[-1] - toques.index[0]).days >= 14
    cerca = bool(dr.Close >= nivel * 0.97)
    cruz = bool(dr.sma200 > dr.sma100)
    a, b = h.iloc[i - 1], r
    dos_rojas = bool(h.iloc[i - 2].Close < h.iloc[i - 2].Open and a.Close < a.Open and h.High.iloc[i - 2:i].max() < nivel)
    tercera = bool(b.Close < b.Open and b.Close < cuerpo_bajo(a) and dos_rojas)
    st = [S("Techo fuerte: máximos horizontales (≥2) y precio cerca", sep and cerca, f"nivel {nivel:.2f}"),
          S("PM100/PM200 diarios cruzados o invertidos (PM200>PM100)", cruz),
          S("Hora: 2 rojas finales que no rompen el techo", dos_rojas),
          S("3ª roja rompe con el cuerpo la línea del gap de la roja anterior", tercera)]
    return res(x, st, 2, (660, 960), "PUT", [{"k": "techo_fuerte", "y": round(nivel, 2), "j": max(0, i - 59)}],
               "Lámina ambigua: título CALL, criterios 5-6 PUT. Aquí se sigue el texto (PUT).")


REGISTRO = [("GAP_NORMAL", "Gap normal", gap_normal, True), ("GAP_BAJISTA", "Gap bajista", gap_bajista, True),
            ("PISO_FUERTE", "Piso fuerte", piso_fuerte, False), ("PRIMER_GAP", "1er gap", primer_gap, True),
            ("PM40", "PM40", pm40, False), ("CAIDA", "Caída", caida, False), ("CANAL_BREAK", "Canal bajista", canal_break, False),
            ("VELA_ROJA", "1ª roja", vela_roja, True), ("RUPT_PISO", "Rupt. piso", rupt_piso, True),
            ("CUATRO_PASOS", "4 pasos", cuatro_pasos, False), ("HANGER", "Hanger", hanger, False), ("TECHO_FUERTE", "Techo fuerte", techo_fuerte, False)]
ORDEN = {"CONFIRMADA": 0, "CONFIRMADA_FUERA_DE_HORARIO": 1, "CASI": 2, "VIGILANCIA": 3, "SIN_CONTEXTO": 4}


def evaluar_activo(h, D, min_bars=215):
    """Evalua las 12 en la ultima vela y la mejor etapa de HOY. Devuelve {id: resultado}."""
    out = {}
    if len(h) < min_bars or h.PM200.iloc[-1] != h.PM200.iloc[-1]:
        return {k: {"etapa": "DATOS_INSUFICIENTES"} for k, *_ in REGISTRO}
    hoy_idx = [j for j in range(len(h)) if h.index[j].date() == h.index[-1].date()]
    for k, nombre, f, usa_manana in REGISTRO:
        try:
            ahora = f(contexto(h, D))
            if usa_manana and h.iloc[-1].end_min >= 960:
                m = f(contexto(h, D), manana=True)
                if ORDEN[m["etapa"]] < ORDEN[ahora["etapa"]] or ahora["etapa"] == "SIN_CONTEXTO":
                    ahora = dict(m, escenario="mañana")
            mejor = ahora
            for j in hoy_idx[:-1]:
                e = f(contexto(h.iloc[:j + 1], D))
                if ORDEN[e["etapa"]] < ORDEN[mejor["etapa"]]:
                    mejor = dict(e, hora=str(h.index[j])[11:16])
            if ORDEN[mejor["etapa"]] < ORDEN[ahora["etapa"]] and mejor["etapa"].startswith("CONFIRMADA"):
                ahora = dict(mejor, **{"del_dia": True})
            out[k] = ahora
        except Exception as e:
            out[k] = {"etapa": "ERROR", "error": str(e)[:80]}
    return out

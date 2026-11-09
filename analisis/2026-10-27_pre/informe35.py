"""SOLO LECTURA. Informe pre-mercado de los activos monitoreados con las reglas de cardona_rules.py (cardona-pdf-v1) sobre datos Yahoo.
No escribe en la BD, no llama a endpoints que cambien estado, no toca el bot."""
import sys, json, csv, urllib.request
sys.path.insert(0, r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project")
import numpy as np, pandas as pd, yfinance as yf
import cardona_rules as cr

OUT = r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project\analisis\2026-10-27_pre"
tickers = json.load(urllib.request.urlopen("http://127.0.0.1:8055/get_monitored_tickers", timeout=10))["tickers"]
now_ny = pd.Timestamp.now(tz=cr.NY)
rows, meta = [], {}


def add(t, strat, state, ev, tf="1H"):
    rows.append(dict(activo=t, dato_NY=meta[t].get("ultima_vela_30m_NY", ""), temporalidad=tf, estrategia=strat, estado=state, evidencia=ev))


for t in tickers:
    meta[t] = {}
    try:
        m30 = yf.download(t, period="60d", interval="30m", prepost=True, progress=False, auto_adjust=False)
        d1 = yf.download(t, period="2y", interval="1d", progress=False, auto_adjust=False)
        for df in (m30, d1):
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        idx = m30.index.tz_convert(cr.NY) if m30.index.tz else m30.index.tz_localize("UTC").tz_convert(cr.NY)
        m30.index = idx
        mins = idx.hour * 60 + idx.minute
        meta[t]["ultima_vela_30m_NY"] = str(idx[-1])
        meta[t]["demora_min"] = round((now_ny - idx[-1]).total_seconds() / 60, 1)
        n_pre = int(sum((idx.date == now_ny.date()) & (mins < 570)))
        meta[t]["velas_pre_hoy"] = n_pre
        if meta[t]["demora_min"] > 4320:
            raise ValueError(f"datos desactualizados: ultima vela {idx[-1]} (hace {meta[t]['demora_min']/1440:.0f} dias); posible activo sin cotizacion")
        reg = m30[(mins >= 570) & (mins < 960)]
        h = cr.add_features(cr.build_cardona_bars(reg, now=now_ny), d1)
        last = h.iloc[-1]
        lastday = last["date"]
        prev_close = float(last["Close"]) if h.index[-1].date() < now_ny.date() else float(last["d_close"])
        pre_px = float(m30["Close"].iloc[-1]) if n_pre else None
        gap_pre = (pre_px - prev_close) / prev_close * 100 if pre_px else None
        meta[t].update(prev_close=round(prev_close, 2), pre_px=None if pre_px is None else round(pre_px, 2),
                       gap_pre=None if gap_pre is None else round(gap_pre, 2))
        base = f"cierre ayer {prev_close:.2f}; premercado {pre_px:.2f} ({gap_pre:+.2f}%)" if pre_px else f"cierre ayer {prev_close:.2f}; sin velas de premercado"
        i = len(h) - 1
        # señales ya ocurridas en la ultima sesion cerrada (informativas)
        hist = {}
        for k in range(max(60, len(h) - 8), len(h)):
            for sid, det in cr.evaluate_bar(h, k).items():
                hist.setdefault(sid, []).append(str(h.index[k]))
        d_trend = bool(last["d_trend"]); d_floor = bool(last["d_floor"])
        pm20_gt = bool(last["PM20"] > last["PM40"])
        # --- GAPS (requieren 2a vela del dia; liberacion >= 11:00)
        if gap_pre is not None:
            g = gap_pre
            add(t, "GAP_NORMAL", "En formación" if (g > cr.GAP_MIN and d_trend) else "Sin coincidencia",
                f"{base}. Tendencia diaria alcista={d_trend}. Falta: 1ª y 2ª vela verdes (10:00-11:00), no martillo; compra desde 11:00" if (g > cr.GAP_MIN and d_trend) else f"{base}. Gap>0,1% y tendencia alcista no se cumplen (tendencia={d_trend})")
            add(t, "GAP_BAJISTA", "En formación" if g < -cr.GAP_MIN else "Sin coincidencia",
                f"{base}. Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00" if g < -cr.GAP_MIN else f"{base}. Gap no es < -0,1%")
        else:
            add(t, "GAP_NORMAL", "No evaluable", "Sin datos de premercado para medir el gap")
            add(t, "GAP_BAJISTA", "No evaluable", "Sin datos de premercado para medir el gap")
        # --- VELA ROJA (PUT, 10:00 unica compra temprana) / RUPTURA_PISO_GAP
        canal = bool(last["PM20"] < last["PM40"]) or abs(last["Close"] - last["PM40"]) / last["PM40"] < 0.02 or abs(last["Close"] - last["PM200"]) / last["PM200"] < 0.02
        add(t, "VELA_ROJA", "En formación" if canal else "Sin coincidencia",
            f"Contexto de canal/PM40/PM200 {'OK' if canal else 'no cumple'}. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00)")
        add(t, "RUPTURA_PISO_GAP", "No evaluable", "Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía")
        # --- estrategias de ruptura de linea (se evaluan con velas cerradas >= 11:00)
        ln = cr.descending_line(h, len(h), 60)
        sin_toc = bool((h["PM20"].iloc[-10:] > h["PM40"].iloc[-10:]).all() and (h["PM100"].iloc[-10:] > h["PM200"].iloc[-10:]).all())
        dist40 = abs(last["Close"] - last["PM40"]) / last["PM40"] * 100
        for sid, cond, txt in [
            ("CAIDA_NORMAL", d_trend and ln is not None, "Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%"),
            ("CAIDA_FUERTE", d_trend and ln is not None, "Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%"),
            ("PISO_FUERTE", bool(last["d_sma100"] > last["d_sma200"]) and d_floor and ln is not None, "SMA100d>SMA200d, en piso diario y línea de caída vigente. Falta: ruptura con vela verde sólida y cierre sobre apertura del día"),
            ("PM40_BOUNCE", sin_toc and dist40 < 1.0 and ln is not None, f"PM20>PM40 y PM100>PM200 sostenidos; distancia a PM40 {dist40:.2f}%. Falta: toque de PM40, ruptura de línea con vela verde sólida/martillo (11:00-15:59)"),
            ("CANAL_BREAK", pm20_gt is False and cr.descending_line(h, len(h), 140, k=3, min_sep=10) is not None, "PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde"),
            ("4_PASOS", pm20_gt is False and ln is not None, "PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso"),
        ]:
            if sid in hist and any(x.startswith(str(lastday)) or x.startswith(str(h.index[-1].date())) for x in hist[sid]):
                add(t, sid, "Confirmada", f"Ya ocurrió en la última sesión cerrada ({', '.join(hist[sid][-2:])}, inicio de vela NY); no es una señal para hoy. {base}")
            else:
                add(t, sid, "En formación" if cond else "Sin coincidencia", (txt if cond else f"Condiciones previas no se cumplen (PM20>PM40={pm20_gt}, línea vigente={ln is not None}, tendencia alcista={d_trend})") + f". {base}")
        # --- las que el motor Cardona-PDF no implementa
        for sid, why in [("PRIMER_GAP", "Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía"),
                         ("HANGER_DIARIO", "Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía"),
                         ("TECHO_FUERTE", "Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas")]:
            add(t, sid, "No evaluable", why)
    except Exception as e:
        meta[t]["error"] = repr(e)
        for sid in ["GAP_NORMAL", "GAP_BAJISTA", "VELA_ROJA", "RUPTURA_PISO_GAP", "CAIDA_NORMAL", "CAIDA_FUERTE", "PISO_FUERTE", "PM40_BOUNCE", "CANAL_BREAK", "4_PASOS", "PRIMER_GAP", "HANGER_DIARIO", "TECHO_FUERTE"]:
            add(t, sid, "No evaluable", f"Error de datos: {e!r}")

with open(OUT + r"\informe35_filas.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
json.dump(meta, open(OUT + r"\informe35_meta.json", "w"), indent=1)
from collections import Counter
print(len(tickers), "activos;", len(rows), "filas")
print(Counter(r["estado"] for r in rows))
print("errores:", {t: m["error"] for t, m in meta.items() if "error" in m})
print("demora_min:", sorted(set(m.get("demora_min") for m in meta.values())))
print("sin premercado:", [t for t, m in meta.items() if m.get("velas_pre_hoy") == 0])
print("En formacion / Confirmada por activo:")
for t in tickers:
    r = [f"{x['estrategia']}:{x['estado'][:4]}" for x in rows if x["activo"] == t and x["estado"] in ("En formación", "Confirmada")]
    print(t, meta[t].get("gap_pre"), r)

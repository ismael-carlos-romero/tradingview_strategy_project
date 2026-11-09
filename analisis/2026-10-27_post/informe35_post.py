"""SOLO LECTURA. Informe POST-mercado 2026-10-27 de los activos monitoreados con cardona_rules.py (cardona-pdf-v1), datos Yahoo.
No escribe en la BD, no llama a endpoints que cambien estado, no toca el bot ni el Auto-Trader."""
import sys, json, csv, urllib.request
sys.path.insert(0, r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project")
import numpy as np, pandas as pd, yfinance as yf
import cardona_rules as cr

OUT = r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project\analisis\2026-10-27_post"
TICKERS = ["AAPL","AMD","AMZN","AXON","BAC","BLK","C","COIN","CVX","DIS","EA","EBAY","GLD","GOOG","GOOGL","HPE","META","MRNA","MSCI",
           "MSFT","NDAQ","NFLX","NVDA","ORCL","PLTR","PYPL","QQQ","SLV","SPY","TNA","TSLA","UBER","USO","VLO","XOM"]
src = "TICKERS de live_scanner.py"
try:
    tickers = json.load(urllib.request.urlopen("http://127.0.0.1:8055/get_monitored_tickers", timeout=5))["tickers"]
    src = "endpoint /get_monitored_tickers"
except Exception:
    tickers = TICKERS
now_ny = pd.Timestamp.now(tz=cr.NY)
today = now_ny.date()
rows, meta = [], {}


def add(t, strat, state, ev):
    rows.append(dict(activo=t, estrategia=strat, estado=state, evidencia=ev))


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
        reg = m30[(mins >= 570) & (mins < 960)]
        if len(reg) == 0 or reg.index[-1].date() != today:
            raise ValueError(f"sin velas regulares de hoy; ultima {idx[-1]}")
        meta[t]["velas_hoy"] = int(sum(reg.index.date == today))
        meta[t]["ultima_regular_hoy"] = str(reg.index[-1])
        h = cr.add_features(cr.build_cardona_bars(reg, now=now_ny), d1)
        last = h.iloc[-1]
        close = float(last["Close"])
        d_trend = bool(last["d_trend"]); d_floor = bool(last["d_floor"])
        pm = {k: float(last[k]) for k in ("PM20", "PM40", "PM100", "PM200")}
        d100 = float(last["d_sma100"]); d200 = float(last["d_sma200"])
        meta[t].update(cierre=round(close, 2), **{k: round(v, 2) for k, v in pm.items()}, SMA100d=round(d100, 2), SMA200d=round(d200, 2),
                       tend_diaria_alcista=d_trend, en_piso_diario=d_floor)
        pm20_gt = pm["PM20"] > pm["PM40"]
        dist40 = abs(close - pm["PM40"]) / pm["PM40"] * 100
        base = f"cierre {close:.2f}; PM20 {pm['PM20']:.2f} PM40 {pm['PM40']:.2f} PM200 {pm['PM200']:.2f}"
        fired = {}
        for k in range(len(h)):
            if h.index[k].date() != today:
                continue
            for sid, det in cr.evaluate_bar(h, k).items():
                fired.setdefault(sid, []).append(h.index[k].strftime("%H:%M"))
        for sid, hrs in fired.items():
            add(t, sid, "CUMPLE (ocurrio hoy)", f"Disparo en vela(s) {', '.join(hrs)} NY. Ya pasada: no es para manana. {base}")
        ln = cr.descending_line(h, len(h), 60)
        gap_note = "El gap se mide en el premercado de manana"

        def st(sid, cond, txt, neg):
            if sid in fired:
                return
            add(t, sid, "CERCA" if cond else "NO", (txt if cond else neg) + f". {base}")
        st("GAP_NORMAL", d_trend, f"Tendencia diaria alcista OK. Falta gap>0,1% manana + 1a y 2a vela verdes (10:00-11:00); compra desde 11:00. {gap_note}", f"Sin tendencia diaria alcista (tend={d_trend})")
        st("GAP_BAJISTA", True, f"Falta gap<-0,1% manana + 1a y 2a vela verdes; compra desde 11:00. {gap_note}", "")
        st("VELA_ROJA", (not pm20_gt) or dist40 < 2 or abs(close - pm['PM200']) / pm['PM200'] < 0.02,
           "Contexto de canal/PM40/PM200 OK. Falta 1a vela 9:30 roja solida con volumen > media (compra 10:00, unica compra antes de 11:00)", "Contexto de canal/PM40/PM200 no cumple")
        add(t, "RUPTURA_PISO_GAP", "NO_EVALUABLE", "Depende de la 1a vela verde de manana y una roja solida posterior")
        for sid, cond, txt in [
            ("CAIDA_NORMAL", d_trend and ln is not None, "Linea de caida vigente + tendencia diaria alcista. Falta vela verde solida que la rompa (>=11:00) con caida 0,5-1,5%"),
            ("CAIDA_FUERTE", d_trend and ln is not None, "Linea de caida vigente + tendencia alcista. Falta ruptura con vela verde solida y caida >1,5%"),
            ("PISO_FUERTE", d100 > d200 and d_floor and ln is not None, "SMA100d>SMA200d, en piso diario y linea vigente. Falta ruptura con vela verde solida"),
            ("PM40_BOUNCE", bool((h['PM20'].iloc[-10:] > h['PM40'].iloc[-10:]).all() and (h['PM100'].iloc[-10:] > h['PM200'].iloc[-10:]).all()) and dist40 < 1.0 and ln is not None,
             f"PM20>PM40 y PM100>PM200 sostenidos; distancia a PM40 {dist40:.2f}% (nivel {pm['PM40']:.2f}). Falta toque y ruptura de linea con verde solida/martillo (11:00-15:59)"),
            ("CANAL_BREAK", (not pm20_gt) and cr.descending_line(h, len(h), 140, k=3, min_sep=10) is not None, "PM20<PM40 y canal bajista largo vigente. Falta ruptura con verde solida + 2a vela verde"),
            ("4_PASOS", (not pm20_gt) and ln is not None, "PM20<PM40 y linea de techo vigente. Falta verde->roja que borre la anterior y ruptura de linea de piso"),
        ]:
            st(sid, cond, txt, f"Condiciones previas no se cumplen (PM20>PM40={pm20_gt}, linea vigente={ln is not None}, tend alcista={d_trend})")
        for sid, why in [("PRIMER_GAP", "Se evalua en la ultima vela del dia sobre gap de apertura; cardona_rules no la implementa"),
                         ("HANGER_DIARIO", "Requiere vela diaria hanger en la ultima vela del dia; cardona_rules no la implementa"),
                         ("TECHO_FUERTE", "Regla ambigua (D6 pendiente: codigo usa piso, PDF define techo); no se evalua")]:
            add(t, sid, "NO_EVALUABLE", why)
    except Exception as e:
        meta[t]["error"] = repr(e)
        for sid in ["GAP_NORMAL", "GAP_BAJISTA", "VELA_ROJA", "RUPTURA_PISO_GAP", "CAIDA_NORMAL", "CAIDA_FUERTE", "PISO_FUERTE", "PM40_BOUNCE", "CANAL_BREAK", "4_PASOS", "PRIMER_GAP", "HANGER_DIARIO", "TECHO_FUERTE"]:
            add(t, sid, "NO_LEIDO", f"Error de datos: {e!r}")

with open(OUT + r"\informe35_post_filas.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
json.dump(dict(fuente_tickers=src, hora_corrida_NY=str(now_ny), meta=meta), open(OUT + r"\informe35_post_meta.json", "w"), indent=1)
from collections import Counter
print(len(tickers), "activos", src, "|", Counter(r["estado"] for r in rows))
print("errores:", {t: m["error"] for t, m in meta.items() if "error" in m})
for r in rows:
    if r["estado"].startswith("CUMPLE"):
        print("CUMPLE", r["activo"], r["estrategia"], r["evidencia"][:110])

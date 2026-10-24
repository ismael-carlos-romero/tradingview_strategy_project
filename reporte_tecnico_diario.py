"""Reporte tecnico diario Meliora. SOLO LECTURA: no compra, no toca el scanner ni la DB del bot.
Datos yfinance -> velas horarias alineadas -> cardona_rules -> grafico propio ("generado por Meliora")
-> carpeta capturas_diarias/AAAA-MM-DD/ -> CSV -> Telegram. Uso: python reporte_tecnico_diario.py [--no-telegram] [TICKER ...]
"""
import sys, os, json, shutil, time, datetime as dt
import warnings; warnings.filterwarnings("ignore")
try:
    import truststore; truststore.inject_into_ssl()
except Exception:
    pass
import pandas as pd, requests, matplotlib
matplotlib.use("Agg")
import mplfinance as mpf
import cardona_rules as cr

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_ROOT = os.path.join(BASE, "capturas_diarias")
KEEP_DAYS = 60
TICKERS = ["AAPL", "AMD", "AMZN", "AXON", "BAC", "BLK", "C", "COIN", "CVX", "DIS", "EBAY", "GLD", "GOOG", "GOOGL",
           "HPE", "META", "MRNA", "MSCI", "MSFT", "NDAQ", "NFLX", "NVDA", "ORCL", "PLTR", "PYPL", "QQQ", "SLV",
           "SPY", "TNA", "TSLA", "UBER", "USO", "VLO", "XOM"]   # EA fuera: sin datos
PUT_IDS = {"RUPTURA_PISO", "4_PASOS"}


def fetch(t, rng, interval):
    """API de grafico de Yahoo directa (yfinance esta limitado por 'Too Many Requests' en esta PC)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
    for k in range(3):
        r = requests.get(url, params={"range": rng, "interval": interval}, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        if r.status_code != 429:
            break
        time.sleep(5 * (k + 1))
    r.raise_for_status()
    res = r.json()["chart"]["result"]
    if not res or not res[0].get("timestamp"):
        return pd.DataFrame()
    res = res[0]
    q = res["indicators"]["quote"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True)
    df = pd.DataFrame({"Open": q["open"], "High": q["high"], "Low": q["low"], "Close": q["close"],
                       "Volume": q["volume"]}, index=idx).dropna()
    if interval == "1d":
        df.index = df.index.tz_convert("America/New_York").tz_localize(None).normalize()
    return df


def analyze(t):
    d30 = fetch(t, "60d", "30m")
    d1 = fetch(t, "2y", "1d")
    if d30.empty or d1.empty:
        return None
    h = cr.add_features(cr.build_cardona_bars(d30), d1)
    if len(h) < 210 - 100:
        return None
    r = h.iloc[-1]
    sigs = {}
    for i in range(len(h) - 3, len(h)):          # señales de las ultimas 3 velas cerradas
        for k, v in cr.evaluate_bar(h, i).items():
            sigs[k] = h.index[i].strftime("%H:%M")
    p = float(r.Close)
    pm = {n: (None if pd.isna(r[f"PM{n}"]) else float(r[f"PM{n}"])) for n in (10, 20, 40, 100, 200)}
    ok = all(v is not None for v in pm.values())
    estructura = "datos insuficientes"
    veredicto = "Esperar"
    if ok:
        alcista100 = pm[100] > pm[200]
        if pm[20] > pm[40] and alcista100:
            estructura = "Alcista alineada"
        elif pm[20] < pm[40] and alcista100:
            estructura = "Caida dentro de tendencia (PM20<PM40, PM100>PM200)"
        elif not alcista100:
            estructura = "Bajista (PM100<PM200)"
        else:
            estructura = "Mixta"
        call_sigs = [k for k in sigs if k not in PUT_IDS]
        put_sigs = [k for k in sigs if k in PUT_IDS]
        if call_sigs and alcista100:
            veredicto = "SEÑAL CALL: " + ", ".join(call_sigs)
        elif put_sigs:
            veredicto = "SEÑAL PUT: " + ", ".join(put_sigs)
        elif pm[20] > pm[40] and alcista100 and 0 <= (p - pm[40]) / pm[40] <= 0.02:
            veredicto = "CALL en armado (PM40): esperar vela verde solida 11:00-15:59 que rompa PM20"
        elif pm[20] < pm[40] and alcista100:
            veredicto = "Caida: esperar ruptura de linea bajista con vela verde solida"
        elif not alcista100:
            veredicto = "Evitar CALL (PM100<PM200)"
    return dict(ticker=t, h=h, price=round(p, 2), estructura=estructura, veredicto=veredicto,
                senales=",".join(sorted(sigs)), **{f"PM{n}": (round(v, 2) if v else None) for n, v in pm.items()})


def chart(res, folder):
    h = res["h"].iloc[-120:]
    ap = [mpf.make_addplot(h[f"PM{n}"], width=0.9) for n in (10, 20, 40, 100, 200)]
    path = os.path.join(folder, f"{res['ticker']}.png")
    mpf.plot(h[["Open", "High", "Low", "Close", "Volume"]], type="candle", style="charles", addplot=ap,
             title=f"{res['ticker']} 1H | PM10-200 | generado por Meliora (no es TradingView)",
             figsize=(11, 5.5), savefig=dict(fname=path, dpi=90))
    return path


def telegram(cfg, text, photo=None):
    tg = cfg.get("telegram", {})
    if not tg.get("enabled"):
        return
    base = f"https://api.telegram.org/bot{tg['bot_token']}"
    try:
        if photo:
            with open(photo, "rb") as f:
                requests.post(base + "/sendPhoto", data={"chat_id": tg["chat_id"], "caption": text[:1024]},
                              files={"photo": f}, timeout=30)
        else:
            requests.post(base + "/sendMessage", data={"chat_id": tg["chat_id"], "text": text[:4000]}, timeout=30)
    except Exception as e:
        print("telegram error:", e)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    send = "--no-telegram" not in sys.argv
    cfg = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))
    day = dt.date.today().isoformat()
    folder = os.path.join(OUT_ROOT, day)
    os.makedirs(folder, exist_ok=True)
    rows, notable = [], []
    for t in (args or TICKERS):
        try:
            res = analyze(t)
        except Exception as e:
            print(t, "error:", e); continue
        if not res:
            print(t, "sin datos"); continue
        img = chart(res, folder)
        res["imagen"] = img
        rows.append({k: v for k, v in res.items() if k != "h"})
        print(t, res["price"], res["veredicto"])
        if res["veredicto"].startswith(("SEÑAL", "CALL en armado")):
            notable.append(res)
    if not rows:
        print("sin datos para ningun activo"); return
    df = pd.DataFrame(rows)
    df.insert(0, "fecha", day)
    df.drop(columns=["imagen"]).to_csv(os.path.join(folder, "resumen.csv"), index=False, encoding="utf-8-sig")
    # retencion: solo borra carpetas de graficos propios con fecha vieja
    for d in os.listdir(OUT_ROOT):
        try:
            if (dt.date.today() - dt.date.fromisoformat(d)).days > KEEP_DAYS:
                shutil.rmtree(os.path.join(OUT_ROOT, d))
        except ValueError:
            pass
    if send and rows:
        resumen = [f"📊 Reporte técnico {day} (solo lectura, sin compras)"]
        resumen.append(f"Activos analizados: {len(rows)}. Con señal o en armado: {len(notable)}")
        for r in notable:
            resumen.append(f"• {r['ticker']} {r['price']}: {r['veredicto']}")
        telegram(cfg, "\n".join(resumen))
        for r in notable[:8]:
            telegram(cfg, f"{r['ticker']} {r['price']} | {r['estructura']}\n{r['veredicto']}\nGenerado por Meliora (yfinance)", r["imagen"])
    print("listo:", folder, len(rows), "activos")


if __name__ == "__main__":
    main()

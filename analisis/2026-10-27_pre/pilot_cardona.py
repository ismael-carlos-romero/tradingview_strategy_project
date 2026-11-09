"""Solo lectura: evalua cardona_rules sobre datos Yahoo para los activos indicados. No toca el bot."""
import sys, json
sys.path.insert(0, r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project")
import pandas as pd, yfinance as yf
import cardona_rules as cr

tickers = sys.argv[1:] or ["SPY"]
out = {}
now_ny = pd.Timestamp.now(tz=cr.NY)
for t in tickers:
    r = {}
    try:
        m30 = yf.download(t, period="60d", interval="30m", prepost=True, progress=False, auto_adjust=False)
        d1 = yf.download(t, period="2y", interval="1d", progress=False, auto_adjust=False)
        for df in (m30, d1):
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
        idx = m30.index.tz_convert(cr.NY) if m30.index.tz else m30.index.tz_localize("UTC").tz_convert(cr.NY)
        m30.index = idx
        r["ultima_vela_30m_NY"] = str(idx[-1])
        r["demora_min"] = round((now_ny - idx[-1]).total_seconds() / 60, 1)
        mins = idx.hour * 60 + idx.minute
        r["velas_premercado_hoy"] = int(sum((idx.date == now_ny.date()) & (mins < 570)))
        r["ultimo_close_30m"] = float(m30["Close"].iloc[-1])
        r["ultimo_close_diario"] = float(d1["Close"].iloc[-1])
        r["fecha_ultimo_diario"] = str(d1.index[-1].date())
        reg = m30[(mins >= 570) & (mins < 960)]
        h = cr.add_features(cr.build_cardona_bars(reg, now=now_ny), d1)
        r["ultima_vela_alineada"] = str(h.index[-1])
        sigs = {}
        for i in range(max(60, len(h) - 14), len(h)):
            s = cr.evaluate_bar(h, i)
            if s:
                sigs[str(h.index[i])] = s
        r["senales_ultimas_14_velas"] = sigs
        last = h.iloc[-1]
        keys = ["Close", "PM20", "PM40", "PM100", "PM200", "d_close", "d_sma100", "d_sma200", "gap", "d_trend", "d_floor"]
        r["ctx"] = {k: (None if pd.isna(last[k]) else (bool(last[k]) if k in ("d_trend", "d_floor") else round(float(last[k]), 3))) for k in keys}
    except Exception as e:
        r["error"] = repr(e)
    out[t] = r
print(json.dumps(out, indent=1, default=str))

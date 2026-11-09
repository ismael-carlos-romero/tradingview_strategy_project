import sys, json
sys.path.insert(0, r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project")
import pandas as pd, numpy as np, yfinance as yf
import cardona_rules as cr
now = pd.Timestamp.now(tz=cr.NY)
for t in ("SPY", "NVDA"):
    m30 = yf.download(t, period="60d", interval="30m", prepost=True, progress=False, auto_adjust=False)
    d1 = yf.download(t, period="2y", interval="1d", progress=False, auto_adjust=False)
    for df in (m30, d1):
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    idx = m30.index.tz_convert(cr.NY); m30.index = idx; mins = idx.hour * 60 + idx.minute
    h = cr.add_features(cr.build_cardona_bars(m30[(mins >= 570) & (mins < 960)], now=now), d1)
    for ts in (["2026-10-26 10:00"] if t == "SPY" else ["2026-10-23 13:00"]):
        i = list(h.index).index(pd.Timestamp(ts, tz=cr.NY)); r = h.iloc[i]
        ln = cr.descending_line(h.iloc[:i + 1], i, 60)
        out = dict(t=t, bar=ts, O=round(r.Open, 2), H=round(r.High, 2), L=round(r.Low, 2), C=round(r.Close, 2), cuerpo_pct=round(abs(r.Close - r.Open) / (r.High - r.Low) * 100), day_open=round(r.day_open, 2),
                   d_close_prev=round(r.d_close, 2), d_sma100=round(r.d_sma100, 2), d_sma200=round(r.d_sma200, 2), d_floor=bool(r.d_floor))
        if ln:
            out["linea"] = dict(p1=[str(h.index[ln[0]]), round(float(ln[1]), 2)], p2=[str(h.index[ln[2]]), round(float(ln[3]), 2)], valor_en_barra=round(float(cr.line_at(ln, i)), 2))
            peak = h["High"].iloc[ln[0]:i].max(); out["caida_%"] = round((peak - h["Low"].iloc[ln[0]:i + 1].min()) / peak * 100, 2); out["pico"] = round(float(peak), 2)
        print(json.dumps(out, default=str))
    dd = d1.tail(30)
    print(t, "diario: max 60d", round(float(d1["High"].tail(60).max()), 2), str(d1["High"].tail(60).idxmax().date()), "min ult 5d", dd["Low"].tail(5).round(2).tolist(), "sma100 hist", d1["Close"].rolling(100).mean().tail(4).round(2).tolist())

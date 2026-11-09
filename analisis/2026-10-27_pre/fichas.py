"""SOLO LECTURA. Genera graficos para fichas comparativas (SPY, NVDA, TSLA) y imprime los hechos medidos."""
import sys, json, os
sys.path.insert(0, r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project")
import numpy as np, pandas as pd, yfinance as yf
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import cardona_rules as cr

OUT = r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project\analisis\2026-10-27_pre\fichas"
os.makedirs(OUT, exist_ok=True)
now = pd.Timestamp.now(tz=cr.NY)
COL = dict(A="#1b6ec2", B="#e8791d", C="#c2185b", D="#00796b", E="#546e7a", F="#795548")
PMC = {"PM20": "#d4a017", "PM40": "#d03030", "PM100": "#2fb344", "PM200": "#8a4fd6"}
UP, DN = "#2e9e5b", "#d64545"
facts = {}


def load(t):
    m30 = yf.download(t, period="60d", interval="30m", prepost=True, progress=False, auto_adjust=False)
    d1 = yf.download(t, period="2y", interval="1d", progress=False, auto_adjust=False)
    for df in (m30, d1):
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
    idx = m30.index.tz_convert(cr.NY) if m30.index.tz else m30.index.tz_localize("UTC").tz_convert(cr.NY)
    m30.index = idx
    mins = idx.hour * 60 + idx.minute
    reg = m30[(mins >= 570) & (mins < 960)]
    h = cr.add_features(cr.build_cardona_bars(reg, now=now), d1)
    return m30, d1, h


def candles(ax, h, lo, hi):
    for k in range(lo, hi):
        r = h.iloc[k]
        c = UP if r.Close >= r.Open else DN
        ax.plot([k, k], [r.Low, r.High], color=c, lw=1)
        ax.add_patch(Rectangle((k - .32, min(r.Open, r.Close)), .64, max(abs(r.Close - r.Open), (r.High - r.Low) * .01), color=c))


def pms(ax, h, lo, hi, names=("PM20", "PM40", "PM100", "PM200")):
    for n in names:
        ax.plot(range(lo, hi), h[n].values[lo:hi], color=PMC[n], lw=1.3, label=n)


def daysep(ax, h, lo, hi):
    for k in range(lo, hi):
        if h["slot"].iloc[k] == 0:
            ax.axvline(k - .5, color="#cfd8dc", lw=.7, zorder=0)
            ax.text(k - .4, ax.get_ylim()[0], h.index[k].strftime("%d/%m"), fontsize=7, color="#78909c", va="bottom")


def tag(ax, x, y, letter, text, dx=0, dy=0, ha="left"):
    ax.annotate(f"{letter}", xy=(x, y), xytext=(x + dx, y + dy), fontsize=8, fontweight="bold", color="white", ha="center", va="center",
                bbox=dict(boxstyle="circle,pad=0.25", fc=COL[letter], ec="none"),
                arrowprops=dict(arrowstyle="-", color=COL[letter], lw=1.2))
    ax.text(x + dx + (1.2 if ha == "left" else -1.2), y + dy, text, fontsize=7.5, color=COL[letter], ha=ha, va="center",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=COL[letter], lw=.6, alpha=.95))


def future(ax, h, ymin, ymax):
    n = len(h)
    ax.add_patch(Rectangle((n - .5, ymin), 7, ymax - ymin, color="#eceff1", zorder=0))
    ax.text(n + 3, ymax, "Hoy 27/10\n(velas aún sin formar)", fontsize=7, color="#546e7a", ha="center", va="top")
    for s, lab in enumerate(["9:30", "10", "11", "12", "13", "14", "15"]):
        ax.text(n + s, ymin, lab, fontsize=6, color="#78909c", ha="center", va="bottom")


def base(t, h, n_back=62, title="", daily=None):
    n = len(h)
    lo = n - n_back
    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=110)
    lo_p = h["Low"].values[lo:].min(); hi_p = h["High"].values[lo:].max()
    pad = (hi_p - lo_p) * .12
    ax.set_xlim(lo - 1, n + 7); ax.set_ylim(lo_p - pad, hi_p + pad)
    candles(ax, h, lo, n); pms(ax, h, lo, n); daysep(ax, h, lo, n)
    future(ax, h, lo_p - pad, hi_p + pad)
    ax.set_title(title, fontsize=10, loc="left"); ax.set_xticks([]); ax.grid(alpha=.15)
    ax.legend(loc="upper left", fontsize=7, ncol=4, frameon=False)
    return fig, ax, lo, n


def run(t):
    m30, d1, h = load(t)
    n = len(h); last = h.iloc[-1]
    mins = m30.index.hour * 60 + m30.index.minute
    pre = m30[(m30.index.date == now.date()) & (mins < 570)]
    pre_px = float(pre["Close"].iloc[-1]) if len(pre) else None
    prev_close = float(last["Close"])
    f = dict(t=t, ultima_vela_alineada=str(h.index[-1]), prev_close=round(prev_close, 2), pre_px=pre_px and round(pre_px, 2),
             gap_pre=pre_px and round((pre_px - prev_close) / prev_close * 100, 3), ultima_pre_NY=str(pre.index[-1]) if len(pre) else None,
             PM20=round(float(last.PM20), 2), PM40=round(float(last.PM40), 2), PM100=round(float(last.PM100), 2), PM200=round(float(last.PM200), 2),
             sma100d=round(float(d1["Close"].rolling(100).mean().iloc[-1]), 2), sma200d=round(float(d1["Close"].rolling(200).mean().iloc[-1]), 2),
             d_close=round(float(d1["Close"].iloc[-1]), 2), d_close_date=str(d1.index[-1].date()))
    f["pm20_vs_pm40_hora"] = "PM20>PM40" if last.PM20 > last.PM40 else "PM20<PM40"
    f["pm100_vs_pm200_dia"] = "SMA100d>SMA200d" if f["sma100d"] > f["sma200d"] else "SMA100d<SMA200d"
    f["dist_sma100d_%"] = round((f["d_close"] - f["sma100d"]) / f["sma100d"] * 100, 2)
    f["dist_sma200d_%"] = round((f["d_close"] - f["sma200d"]) / f["sma200d"] * 100, 2)
    # gaps de la ultima sesion
    f["gap_ayer_%"] = round(float(last["gap"]), 2)
    f["primera_vela_ayer_verde"] = bool(last["first_green"])
    # lineas
    ln60 = cr.descending_line(h, n, 60)
    ln140 = cr.descending_line(h, n, 140, k=3, min_sep=10)
    for nm, ln in (("linea60", ln60), ("linea140", ln140)):
        if ln:
            j1, y1, j2, y2 = ln
            f[nm] = dict(p1=[str(h.index[j1]), round(float(y1), 2)], p2=[str(h.index[j2]), round(float(y2), 2)],
                         en_apertura=round(float(cr.line_at(ln, n)), 2), en_11=round(float(cr.line_at(ln, n + 2)), 2),
                         cierre_ayer_vs_linea=round(prev_close - float(cr.line_at(ln, n - 1)), 2))
            c = h["Close"].values
            f[nm]["cierres_sobre_linea_ultimas_10"] = [bool(c[k] > cr.line_at(ln, k)) for k in range(n - 10, n)]
        else:
            f[nm] = None
    # senales recientes del motor
    sg = {}
    for k in range(max(60, n - 14), n):
        s = cr.evaluate_bar(h, k)
        if s: sg[str(h.index[k])] = s
    f["motor_ultimas_14"] = sg
    # velas de ayer
    f["velas_ayer"] = [dict(t=str(h.index[k].time()), o=round(float(h.Open.iloc[k]), 2), h=round(float(h.High.iloc[k]), 2), l=round(float(h.Low.iloc[k]), 2), c=round(float(h.Close.iloc[k]), 2)) for k in range(n - 7, n)]
    return m30, d1, h, f, pre_px, prev_close, ln60, ln140


def chart_gap(t):
    m30, d1, h, f, pre_px, pc, ln60, ln140 = run(t)
    fig, ax, lo, n = base(t, h, title=f"{t} · 1 hora alineada a Cardona · Gap Normal al Alza (preparación de premercado 27/10, 08:30 ET)")
    y0, y1 = ax.get_ylim()
    ax.axhline(pc, color=COL["E"], ls=":", lw=1); ax.text(lo, pc, f" cierre 26/10 {pc:.2f}", fontsize=7, color=COL["E"], va="bottom")
    if pre_px:
        ax.scatter([n - .2], [pre_px], marker="D", s=40, color=COL["E"], zorder=5)
        tag(ax, n - .2, pre_px, "E", f"Premercado {pre_px:.2f} ({(pre_px-pc)/pc*100:+.2f}%): gap sobre el cierre", dx=-18, dy=(y1 - y0) * .10, ha="right")
    ln = ln60
    if ln:
        xs = np.arange(ln[0], n + 7)
        ax.plot(xs, [cr.line_at(ln, x) for x in xs], color=COL["B"], lw=1.6, ls="--")
        tag(ax, n + 1, cr.line_at(ln, n + 1), "B", f"Techo de caída (2 máximos): {cr.line_at(ln, n+1):.2f} a las 10-11", dx=-14, dy=(y1 - y0) * (.12 if pre_px and pre_px < cr.line_at(ln, n+1) else -.12), ha="right")
    tag(ax, n - 8, float(h.PM40.iloc[-8]), "A", f"Hora: PM20 {f['PM20']} {'>' if f['PM20']>f['PM40'] else '<'} PM40 {f['PM40']}", dx=-4, dy=(y1 - y0) * .34, ha="right")
    ax.add_patch(Rectangle((n - .5, y0), 1, y1 - y0, fill=False, ec=COL["C"], lw=1.2, ls="--")); ax.add_patch(Rectangle((n + .5, y0), 1, y1 - y0, fill=False, ec=COL["C"], lw=1.2, ls="--"))
    ax.text(n + .5, y0 + (y1 - y0) * .12, "C 1ª+2ª vela\nverdes (pend.)", fontsize=7, color=COL["C"], ha="center", va="bottom", bbox=dict(fc="white", ec=COL["C"], lw=.6, boxstyle="round,pad=.2"))
    ax.axvline(n + 1.5, color=COL["D"], lw=1.4); ax.text(n + 1.6, y1 - (y1 - y0) * .22, "D compra\ndesde 11:00", fontsize=7, color=COL["D"], va="top", bbox=dict(fc="white", ec=COL["D"], lw=.6, boxstyle="round,pad=.2"))
    fig.tight_layout(); fig.savefig(OUT + f"\\{t}_GAP_NORMAL.png"); plt.close(fig)
    facts[f"{t}_GAP"] = f


def chart_canal(t, tag_name="CANAL_BREAK"):
    m30, d1, h, f, pre_px, pc, ln60, ln140 = run(t)
    fig, ax, lo, n = base(t, h, n_back=110, title=f"{t} · 1 hora alineada a Cardona · Ruptura del Canal Bajista (premercado 27/10, 08:30 ET)")
    y0, y1 = ax.get_ylim()
    ln = ln140
    if ln:
        xs = np.arange(ln[0], n + 7)
        ax.plot(xs, [cr.line_at(ln, x) for x in xs], color=COL["B"], lw=1.8, ls="--")
        j1, y1_, j2, y2_ = ln
        ax.scatter([j1, j2], [y1_, y2_], color=COL["B"], zorder=6, s=28)
        tag(ax, j2, y2_, "B", "Techo del canal: 2 máximos (puntos 1 y 2)", dx=-3, dy=(y1 - y0) * .10, ha="right")
        lv = cr.line_at(ln, n + 1)
        tag(ax, n + 1, lv, "D", f"Techo hoy ≈ {lv:.2f} a las 10-11", dx=-12, dy=(y1 - y0) * .13, ha="right")
    ax.axhline(pc, color=COL["E"], ls=":", lw=1)
    if pre_px:
        ax.scatter([n - .2], [pre_px], marker="D", s=40, color=COL["E"], zorder=5)
    tag(ax, n - 20, float(h.PM40.iloc[-20]), "A", f"PM40 {f['PM40']} sobre PM20 {f['PM20']}" if f['PM20'] < f['PM40'] else f"PM20 {f['PM20']} sobre PM40 {f['PM40']}", dx=-10, dy=-(y1 - y0) * .2, ha="right")
    ax.text(n + 3.2, y0 + (y1 - y0) * .35, "C vela verde sólida\nque cierre sobre el techo\n(pendiente)", fontsize=7, color=COL["C"], ha="center", bbox=dict(fc="white", ec=COL["C"], lw=.6, boxstyle="round,pad=.2"))
    fig.tight_layout(); fig.savefig(OUT + f"\\{t}_CANAL_BREAK.png"); plt.close(fig)
    facts[f"{t}_CANAL"] = f


def chart_piso(t, brk_time=None):
    m30, d1, h, f, pre_px, pc, ln60, ln140 = run(t)
    fig, (axd, ax) = plt.subplots(2, 1, figsize=(11, 8.4), dpi=110, gridspec_kw=dict(height_ratios=[1, 1.35]))
    # diario
    dd = d1.tail(110).copy(); dd["s100"] = d1["Close"].rolling(100).mean().tail(110); dd["s200"] = d1["Close"].rolling(200).mean().tail(110)
    for k, (i, r) in enumerate(dd.iterrows()):
        c = UP if r.Close >= r.Open else DN
        axd.plot([k, k], [r.Low, r.High], color=c, lw=1); axd.add_patch(Rectangle((k - .32, min(r.Open, r.Close)), .64, max(abs(r.Close - r.Open), (r.High - r.Low) * .01), color=c))
    axd.plot(range(len(dd)), dd.s100.values, color=PMC["PM100"], lw=1.6, label="PM100 diario"); axd.plot(range(len(dd)), dd.s200.values, color=PMC["PM200"], lw=1.6, label="PM200 diario")
    axd.set_xlim(-1, len(dd) + 1); axd.legend(fontsize=7, frameon=False, loc="upper left"); axd.grid(alpha=.15)
    axd.set_title(f"{t} · DIARIO · piso fuerte: PM100 sobre PM200 y caída hasta el PM100/PM200", fontsize=10, loc="left")
    yl = axd.get_ylim(); k_last = len(dd) - 1
    tag(axd, k_last, float(dd.s100.iloc[-1]), "A", f"PM100 {f['sma100d']} {'>' if f['sma100d']>f['sma200d'] else '<'} PM200 {f['sma200d']}", dx=-26, dy=-(yl[1] - yl[0]) * .22, ha="right")
    tag(axd, k_last, float(dd.Close.iloc[-1]), "B", f"Cierre {f['d_close']}: {f['dist_sma100d_%']:+.2f}% del PM100", dx=-26, dy=(yl[1] - yl[0]) * .2, ha="right")
    axd.set_xticks([k for k in range(0, len(dd), 20)]); axd.set_xticklabels([dd.index[k].strftime("%d/%m") for k in range(0, len(dd), 20)], fontsize=7)
    # hora
    n = len(h); lo = n - 70
    lo_p = h["Low"].values[lo:].min(); hi_p = h["High"].values[lo:].max(); pad = (hi_p - lo_p) * .14
    ax.set_xlim(lo - 1, n + 7); ax.set_ylim(lo_p - pad, hi_p + pad)
    candles(ax, h, lo, n); pms(ax, h, lo, n); daysep(ax, h, lo, n); future(ax, h, lo_p - pad, hi_p + pad); ax.grid(alpha=.15); ax.set_xticks([])
    ax.legend(loc="upper left", fontsize=7, ncol=4, frameon=False)
    ax.set_title(f"{t} · 1 HORA alineada a Cardona · línea de caída (techo) y ruptura con vela verde", fontsize=10, loc="left")
    y0, y1 = ax.get_ylim(); ln = ln60
    if ln:
        xs = np.arange(ln[0], n + 7)
        ax.plot(xs, [cr.line_at(ln, x) for x in xs], color=COL["C"], lw=1.8, ls="--")
        ax.scatter([ln[0], ln[2]], [ln[1], ln[3]], color=COL["C"], zorder=6, s=28)
        tag(ax, ln[2], ln[3], "C", "Techo: 2 máximos descendentes", dx=-3, dy=(y1 - y0) * .1, ha="right")
        lv = cr.line_at(ln, n + 2)
        tag(ax, n + 2, lv, "D", f"Techo hoy ≈ {lv:.2f} (11:00)", dx=-10, dy=(y1 - y0) * .13, ha="right")
    if brk_time is not None:
        k = list(h.index).index(pd.Timestamp(brk_time))
        ax.scatter([k], [h.Close.iloc[k]], s=90, facecolors="none", edgecolors=COL["D"], lw=2, zorder=7)
        tag(ax, k, float(h.High.iloc[k]), "D", f"Vela verde sólida de ruptura {pd.Timestamp(brk_time).strftime('%d/%m %H:%M')} (cierre {h.Close.iloc[k]:.2f})", dx=-8, dy=(y1 - y0) * .16, ha="right")
    else:
        ax.text(n + 3.2, y0 + (y1 - y0) * .35, "D vela verde sólida\nque rompa el techo\n(pendiente, ≥ 11:00)", fontsize=7, color=COL["D"], ha="center", bbox=dict(fc="white", ec=COL["D"], lw=.6, boxstyle="round,pad=.2"))
    fig.tight_layout(); fig.savefig(OUT + f"\\{t}_PISO_FUERTE.png"); plt.close(fig)
    facts[f"{t}_PISO"] = f


chart_gap("SPY"); chart_gap("TSLA")
chart_canal("SPY"); chart_canal("NVDA")
chart_piso("NVDA")
# SPY piso fuerte de ayer: vela de ruptura 26/10 10:00 (inicio de vela) segun motor
try:
    chart_piso("SPY", brk_time=pd.Timestamp("2026-10-26 10:00", tz=cr.NY))
except Exception as e:
    print("SPY piso error", repr(e))
json.dump(facts, open(OUT + r"\facts.json", "w"), indent=1, default=str)
print(json.dumps(facts, indent=1, default=str)[:12000])

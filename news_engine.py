"""Mejora 2 - Rastreo de noticias por activo (etapa 1: recoleccion + deduplicacion).

Fuentes: SEC EDGAR (8-K), Google News RSS, yfinance (respaldo) y Finnhub (si hay clave
en config.json -> "finnhub_api_key"). Las noticias son contexto: este modulo NO toca
entradas, ejecucion ni riesgo.

Uso:  python news_engine.py TSLA MRNA [--days 3]
"""
import difflib
import hashlib
import json
import os
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

try:  # usa el almacen de certificados de Windows (el antivirus intercepta HTTPS)
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "news_events.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

NAMES = {
    "AAPL": "Apple", "AMD": "Advanced Micro Devices", "AMZN": "Amazon", "AXON": "Axon Enterprise",
    "BAC": "Bank of America", "BLK": "BlackRock", "C": "Citigroup", "COIN": "Coinbase",
    "CVX": "Chevron", "DIS": "Walt Disney", "EA": "Electronic Arts", "EBAY": "eBay",
    "GLD": "SPDR Gold Shares", "GOOG": "Alphabet", "GOOGL": "Alphabet", "HPE": "Hewlett Packard Enterprise",
    "META": "Meta Platforms", "MRNA": "Moderna", "MSCI": "MSCI Inc", "MSFT": "Microsoft",
    "NDAQ": "Nasdaq Inc", "NFLX": "Netflix", "NVDA": "NVIDIA", "ORCL": "Oracle",
    "PLTR": "Palantir", "PYPL": "PayPal", "QQQ": "Invesco QQQ", "SLV": "iShares Silver Trust",
    "SPY": "SPDR S&P 500 ETF", "TNA": "Direxion Small Cap Bull 3X", "TSLA": "Tesla",
    "UBER": "Uber", "USO": "United States Oil Fund", "VLO": "Valero Energy", "XOM": "Exxon Mobil",
}
ETFS = {"GLD", "QQQ", "SLV", "SPY", "TNA", "USO"}

# Items del 8-K (SEC) -> descripcion corta
ITEMS_8K = {
    "1.01": "Acuerdo material", "1.02": "Terminacion de acuerdo material", "1.03": "Quiebra",
    "2.01": "Adquisicion/venta de activos", "2.02": "Resultados financieros", "2.03": "Nueva deuda",
    "2.05": "Reestructuracion/costos de salida", "2.06": "Deterioro material",
    "3.01": "Aviso de delisting", "3.02": "Venta de acciones no registradas",
    "4.01": "Cambio de auditor", "4.02": "Estados financieros no confiables",
    "5.01": "Cambio de control", "5.02": "Cambio de directivos/CEO/directorio",
    "5.03": "Cambio de estatutos", "5.07": "Votacion de accionistas",
    "7.01": "Divulgacion Reg FD", "8.01": "Otros eventos", "9.01": "Anexos",
}

_session = requests.Session()


def load_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _utc(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ---------------------------------------------------------------- fuentes
_cik_cache = {}


def _cik_for(ticker, headers):
    if not _cik_cache:
        r = _session.get("https://www.sec.gov/files/company_tickers.json", headers=headers, timeout=20)
        r.raise_for_status()
        for row in r.json().values():
            _cik_cache[row["ticker"].upper()] = int(row["cik_str"])
    return _cik_cache.get(ticker.upper().replace(".", "-"))


def fetch_edgar(ticker, since, cfg):
    if ticker in ETFS:
        return []
    ua = cfg.get("sec_user_agent") or "MelioraOptions research (config.json: sec_user_agent)"
    headers = {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}
    cik = _cik_for(ticker, headers)
    if not cik:
        return []
    r = _session.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", headers=headers, timeout=20)
    r.raise_for_status()
    rec = r.json()["filings"]["recent"]
    out = []
    for i, form in enumerate(rec["form"]):
        if form not in ("8-K", "8-K/A"):
            continue
        # filingDate no trae hora; acceptanceDateTime si (UTC)
        pub = _utc(datetime.fromisoformat(rec["acceptanceDateTime"][i].replace("Z", "+00:00")))
        if pub < since:
            continue
        items = [x.strip() for x in rec["items"][i].split(",") if x.strip()]
        desc = ", ".join(f"{x} {ITEMS_8K.get(x, '')}".strip() for x in items if x != "9.01") or "8-K"
        acc = rec["accessionNumber"][i].replace("-", "")
        link = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{rec['primaryDocument'][i]}"
        out.append({"title": f"SEC 8-K: {desc}", "published": pub, "source": "SEC EDGAR", "link": link})
    return out


def fetch_google_news(ticker, since, cfg):
    name = NAMES.get(ticker, ticker)
    q = quote(f'"{name}" {ticker} stock when:{max(1, (datetime.now(timezone.utc) - since).days + 1)}d')
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    r = _session.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    out = []
    for it in ET.fromstring(r.content).iter("item"):
        pub = _utc(parsedate_to_datetime(it.findtext("pubDate")))
        if pub < since:
            continue
        src = it.find("source")
        out.append({"title": (it.findtext("title") or "").strip(), "published": pub,
                    "source": (src.text if src is not None else "Google News"), "link": it.findtext("link")})
    return out


def fetch_yfinance(ticker, since, cfg):
    import yfinance as yf
    out = []
    for n in yf.Ticker(ticker).news or []:
        c = n.get("content") or n
        title = c.get("title")
        ts = c.get("pubDate") or c.get("providerPublishTime")
        if not title or not ts:
            continue
        pub = _utc(datetime.fromtimestamp(ts, timezone.utc) if isinstance(ts, (int, float))
                   else datetime.fromisoformat(ts.replace("Z", "+00:00")))
        if pub < since:
            continue
        link = (c.get("canonicalUrl") or {}).get("url") or c.get("link") or ""
        prov = (c.get("provider") or {}).get("displayName") or c.get("publisher") or "Yahoo Finance"
        out.append({"title": title.strip(), "published": pub, "source": prov, "link": link})
    return out


def fetch_finnhub(ticker, since, cfg):
    key = cfg.get("finnhub_api_key")
    if not key or key.startswith("TU_"):
        raise RuntimeError("sin clave de Finnhub en config.json")
    now = datetime.now(timezone.utc)
    r = _session.get("https://finnhub.io/api/v1/company-news", timeout=20, params={
        "symbol": ticker, "from": since.date().isoformat(), "to": now.date().isoformat(), "token": key})
    r.raise_for_status()
    out = []
    for n in r.json():
        pub = datetime.fromtimestamp(n["datetime"], timezone.utc)
        if pub >= since and n.get("headline"):
            out.append({"title": n["headline"].strip(), "published": pub,
                        "source": n.get("source") or "Finnhub", "link": n.get("url", "")})
    return out


SOURCES = [("edgar", fetch_edgar), ("google_news", fetch_google_news),
           ("yfinance", fetch_yfinance), ("finnhub", fetch_finnhub)]


# ------------------------------------------------------------ deduplicacion
def _norm(title):
    t = re.sub(r"\s+[-|]\s+[^-|]{2,40}$", "", title.lower())  # saca " - Reuters"
    return re.sub(r"[^a-z0-9 ]+", "", t).strip()


def cluster(items):
    """Misma noticia en varias fuentes = un evento con todas las fuentes y enlaces."""
    events = []
    for it in sorted(items, key=lambda x: x["published"]):
        n = _norm(it["title"])
        for ev in events:
            if difflib.SequenceMatcher(None, n, ev["_norm"]).ratio() >= 0.82:
                ev["sources"].append(it["source"]); ev["links"].append(it["link"])
                ev["published"] = min(ev["published"], it["published"])
                break
        else:
            events.append({"title": it["title"], "published": it["published"], "_norm": n,
                           "sources": [it["source"]], "links": [it["link"]]})
    for ev in events:
        ev["dedup_key"] = hashlib.sha1(ev["_norm"].encode()).hexdigest()[:16]
        pairs = list(dict.fromkeys(zip(ev["sources"], ev["links"])))
        ev["sources"], ev["links"] = [p[0] for p in pairs], [p[1] for p in pairs]
    return sorted(events, key=lambda e: e["published"], reverse=True)


# ------------------------------------------------------------------ base
def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS news_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, dedup_key TEXT, published_utc TEXT,
        title TEXT, sources TEXT, links TEXT, first_seen_utc TEXT,
        tipo TEXT, impacto TEXT, sesgo TEXT, resumen TEXT, por_que_importa TEXT,
        precio_ref REAL, reaccion_pct REAL, alertado INTEGER DEFAULT 0, en_sheet INTEGER DEFAULT 0,
        UNIQUE(ticker, dedup_key))""")
    con.commit()
    return con


def collect(ticker, days=3, cfg=None):
    """Devuelve (eventos, estado_por_fuente). estado: 'ok' | 'fallo: motivo'."""
    cfg = cfg or load_config()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    items, status = [], {}
    for name, fn in SOURCES:
        try:
            got = fn(ticker, since, cfg)
            status[name] = f"ok ({len(got)})"
            items += got
        except Exception as e:
            msg = str(e)
            for secret in (cfg.get("finnhub_api_key"), cfg.get("anthropic_api_key")):
                if secret:
                    msg = msg.replace(secret, "***")
            status[name] = f"falló la consulta: {type(e).__name__}: {msg}"
    return cluster(items), status


def save(con, ticker, events):
    new = 0
    for ev in events:
        cur = con.execute(
            "INSERT OR IGNORE INTO news_events(ticker,dedup_key,published_utc,title,sources,links,first_seen_utc)"
            " VALUES(?,?,?,?,?,?,?)",
            (ticker, ev["dedup_key"], ev["published"].isoformat(), ev["title"],
             json.dumps(ev["sources"]), json.dumps(ev["links"]), datetime.now(timezone.utc).isoformat()))
        new += cur.rowcount
    con.commit()
    return new


def _fmt_times(dt):
    try:
        from zoneinfo import ZoneInfo
        return (dt.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M NY"),
                dt.astimezone(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%H:%M ARG"))
    except Exception:
        return dt.strftime("%Y-%m-%d %H:%M UTC"), ""


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    days = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 3
    args = [a for a in args if not a.isdigit()]
    con = init_db()
    for t in [a.upper() for a in args]:
        evs, st = collect(t, days)
        added = save(con, t, evs)
        print(f"\n=== {t} ({NAMES.get(t, '')}) | ultimos {days} dias | eventos: {len(evs)} | nuevos en base: {added}")
        for k, v in st.items():
            print(f"  fuente {k}: {v}")
        if not evs:
            fallos = [k for k, v in st.items() if v.startswith("fall")]
            print("  -> " + ("sin noticias relevantes (las fuentes que respondieron no trajeron nada)"
                              if len(fallos) < len(st) else "falló la consulta en todas las fuentes"))
        for ev in evs[:12]:
            ny, ar = _fmt_times(ev["published"])
            print(f"  [{ny} / {ar}] {ev['title']}\n      fuentes: {', '.join(ev['sources'])}\n      {ev['links'][0]}")

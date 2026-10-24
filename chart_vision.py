"""Capa 3 - ojo visual (modo sombra). Dibuja el grafico y se lo muestra a un modelo con vision.
Clave: config.json -> "anthropic_api_key" o variable de entorno ANTHROPIC_API_KEY. Sin clave, no hace nada.
Modelo opcional: config.json -> "vision_model".
"""
import base64
import io
import json
import os
import sqlite3
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import mplfinance as mpf

import chart_analyzer

_DIR = os.path.dirname(os.path.abspath(__file__))
_REF_IMG = os.path.join(_DIR, "cardona_strategies_hero.png")
_DEFAULT_MODEL = "claude-sonnet-5-5"


def _cfg():
    try:
        with open(os.path.join(_DIR, "config.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def render_chart(ticker, bars=120):
    df = chart_analyzer._fetch(ticker, "1d", "5y").copy()
    for n in (10, 50, 200):
        df[f"SMA{n}"] = df["Close"].rolling(n).mean()
    d = df.tail(bars)
    ap = [mpf.make_addplot(d[f"SMA{n}"]) for n in (10, 50, 200)]
    buf = io.BytesIO()
    mpf.plot(d, type="candle", addplot=ap, volume=True, style="yahoo", title=f"{ticker} diario (SMA 10/50/200)",
             savefig=dict(fname=buf, dpi=110, format="png"))
    return buf.getvalue()


def _img_block(png):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.b64encode(png).decode()}}


def ask_model(png, ticker, direction, strategy_id, cfg):
    import anthropic
    key = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    client = anthropic.Anthropic(api_key=key, timeout=40)
    content = []
    if os.path.exists(_REF_IMG):
        with open(_REF_IMG, "rb") as f:
            content += [{"type": "text", "text": "Lámina de referencia de las estrategias de Alejandro Cardona:"},
                        _img_block(f.read())]
    content += [
        {"type": "text", "text": f"Gráfico diario de {ticker}:"},
        _img_block(png),
        {"type": "text", "text": (
            f"El bot detectó la estrategia {strategy_id} en dirección {direction}. "
            "Mirando el gráfico, ¿ves una estrategia de las de referencia, dónde y con qué confianza? "
            "¿Coincide con la dirección detectada? Respondé SOLO JSON: "
            '{"estrategia":"...","direccion":"CALL|PUT|NINGUNA","confianza":0-100,"coincide":true|false,"comentario":"max 200 caracteres"}')},
    ]
    r = client.messages.create(model=cfg.get("vision_model", _DEFAULT_MODEL), max_tokens=400,
                               messages=[{"role": "user", "content": content}])
    txt = r.content[0].text.strip()
    txt = txt[txt.find("{"):txt.rfind("}") + 1]
    return json.loads(txt)


def _log(db_path, ticker, strategy_id, setup_id, direction, res):
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS chart_vision_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, "
                 "setup_id TEXT, ticker TEXT, strategy_id TEXT, direction TEXT, coincide INTEGER, confianza INTEGER, detail TEXT)")
    conn.execute("INSERT INTO chart_vision_log (timestamp, setup_id, ticker, strategy_id, direction, coincide, confianza, detail) "
                 "VALUES (?,?,?,?,?,?,?,?)",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), setup_id, ticker, strategy_id, direction,
                  int(bool(res.get("coincide"))), int(res.get("confianza") or 0), json.dumps(res, ensure_ascii=False)))
    conn.commit()
    conn.close()


def analyze_for_signal(db_path, ticker, direction, strategy_id=None, setup_id=None):
    """Bloque de texto para Telegram o '' (sin clave / error). Nunca lanza."""
    try:
        cfg = _cfg()
        if not (cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")):
            return ""
        res = ask_model(render_chart(ticker), ticker, direction, strategy_id, cfg)
        if not res:
            return ""
        _log(db_path, ticker, strategy_id, setup_id, direction, res)
        ok = "✅" if res.get("coincide") else "⚠️"
        return (f"👁 <b>Ojo visual (sombra)</b>\n{ok} {res.get('estrategia')} · {res.get('direccion')} · "
                f"confianza {res.get('confianza')}%\n{res.get('comentario', '')}")
    except Exception as e:
        print(f"[ChartVision] Error en {ticker}: {e}")
        return ""

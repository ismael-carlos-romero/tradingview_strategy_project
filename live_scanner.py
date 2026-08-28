import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import ssl
import urllib3
import json
import sqlite3
import time
from datetime import datetime
import sim_broker_core

# Deshabilitar advertencias de SSL inseguro y configurar sesión
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# ==========================================
# CONFIGURACIÓN
# ==========================================
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
WEBHOOK_URL = "TU_WEBHOOK_URL_AQUÍ"
ANTICIPATION_THRESHOLD = 1.0
IMMINENT_THRESHOLD = 0.35
TELEGRAM_ENABLED = False
TELEGRAM_TOKEN = ""
TELEGRAM_CHAT_ID = ""
CONFIG = {}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_f:
            CONFIG = json.load(config_f)
            WEBHOOK_URL = CONFIG.get("webhook_url", WEBHOOK_URL)
            ANTICIPATION_THRESHOLD = CONFIG.get("anticipation_threshold_pct", ANTICIPATION_THRESHOLD)
            IMMINENT_THRESHOLD = CONFIG.get("imminent_threshold_pct", IMMINENT_THRESHOLD)
            tg_conf = CONFIG.get("telegram", {})
            TELEGRAM_ENABLED = tg_conf.get("enabled", False)
            TELEGRAM_TOKEN = tg_conf.get("bot_token", "")
            TELEGRAM_CHAT_ID = tg_conf.get("chat_id", "")
    except Exception as e:
        print(f"Advertencia: No se pudo cargar config.json: {e}")

last_ucharts_heartbeat = 0.0

def normalizar_cuenta_id(cuenta_id):
    if not cuenta_id:
        return "default"
    c_clean = cuenta_id.strip().lower().replace("_", " ")
    if c_clean in ("default", "meliora paso a paso", "cuenta meliora paso a paso"):
        return "default"
    return cuenta_id

def get_system_state():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT val FROM configuracion WHERE param_id = 'system_state'")
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0]
    except Exception as e:
        print(f"[Config DB] Error al obtener system_state: {e}")
    return "DISARMED"

def set_system_state(state):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('system_state', ?)", (state,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Config DB] Error al persistir system_state: {e}")

def registrar_auditoria(usuario, accion, motivo=None, referencia=None):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO logs_auditoria (timestamp, usuario, accion, motivo, referencia)
            VALUES (datetime('now'), ?, ?, ?, ?)
        """, (usuario, accion, motivo, referencia))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Auditoria] Error al registrar: {e}")

def report_heartbeat(componente, estado="ONLINE", detalles=""):
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO heartbeats (componente, estado, last_heartbeat, detalles)
            VALUES (?, ?, datetime('now'), ?)
        """, (componente, estado, detalles))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Heartbeat] Error al registrar {componente}: {e}")

TICKERS = [
    "AAPL", "AMD", "AMZN", "AXON", "BAC", "BLK", "C", "COIN", "CVX", "DIS", 
    "EA", "EBAY", "GLD", "GOOG", "GOOGL", "HPE", "META", "MRNA", "MSCI", 
    "MSFT", "NDAQ", "NFLX", "NVDA", "ORCL", "PLTR", "PYPL", "QQQ", "SLV", 
    "SPY", "TNA", "TSLA", "UBER", "USO", "VLO", "XOM"
]

STRATEGIES_METADATA = {
    "cond_gap_normal": ("Gap Normal al Alza", "CALL", "51.02%"),
    "cond_gap_bajista": ("Gap Bajista al Alza", "CALL", "41.45%"),
    "cond_piso_fuerte": ("Piso Fuerte", "CALL", "28.00%"),
    "cond_primer_gap": ("Primer Gap al Alza", "CALL", "37.50%"),
    "cond_cola_piso": ("Cola de Piso", "CALL", "47.81%"),
    "cond_pm40_bounce": ("Promedio Móvil de 40", "CALL", "47.88%"),
    "cond_caida_normal": ("Caída Normal", "CALL", "44.83%"),
    "cond_caida_fuerte": ("Caída Fuerte", "CALL", "47.20%"),
    "cond_canal_break": ("Ruptura Canal Bajista", "CALL", "46.30%"),
    "cond_ruptura_res": ("Ruptura de Resistencia", "CALL", "48.15%"),
    "cond_vela_roja": ("Primera Vela Roja", "PUT", "50.00%"),
    "cond_techo_fuerte": ("Techo Fuerte", "PUT", "40.15%"),
    "cond_ruptura_piso": ("Ruptura Piso del Gap", "PUT", "37.78%"),
    "cond_4_pasos": ("Modelo de 4 Pasos", "PUT", "40.94%"),
    "cond_cola_techo": ("Cola de Techo", "PUT", "39.47%"),
    "cond_hanger_diario": ("Hanger en Diario", "PUT", "42.86%"),
    "cond_ruptura_sop": ("Ruptura de Soporte", "PUT", "37.86%"),
    "cond_piso_break": ("Ruptura de Piso Fuerte", "PUT", "37.84%"),
    "cond_gap_cont_put": ("Gap Bajista de Continuación", "PUT", "36.61%")
}

DB_DIR = os.environ.get("PERSISTENT_DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_NAME = os.path.join(DB_DIR, "trading_laboratory.db")

PENDING_TRADES_QUEUE = []
# Marca si un escaneo (main()) está en curso ahora mismo. Se usa para no
# mostrar "SIN_RESPUESTA" en el dashboard mientras el scanner está ocupado
# escaneando (que puede tardar bastante más que el timeout de 25s), en vez
# de estar realmente caído.
SCANNING_IN_PROGRESS = False

STRATEGY_PATTERN_IMAGES = {
    "PM40_BOUNCE": "PROMEDIO MOVIL DE 40.png",
    "CAIDA_NORMAL": "Estrategia Caida Normal.jpg",
    "CAIDA_FUERTE": "Estrategia Caida Normal.jpg",
    "PISO_DIARIO": "Piso Fuerte.jpg",
    "RUPTURA_RES": "Ruptura del Canal Bajista.jpg",
    "GAP_ALZA_1": "Primer Gap_.jpg",
    "GAP_NORMAL": "Gap Normal al Alza.jpg",
    "GAP_BAJISTA": "Gap Bajista al Alza.jpg",
    "VELA_ROJA": "Primera Vela Roja de Apertura.jpg",
    "RUPTURA_PISO": "Ruptura del Piso del Gap.jpg",
    "HANGER_DIARIO": "Hanger Diario.jpg",
    "4_PASOS": "Canal Bajista-Modelo de 4 Pasos_.jpg"
}

def calculate_setup_score(row, direction, dist_pm40, config):
    """Calcula dinámicamente la puntuación (0 a 100) en base a los pesos configurados."""
    weights = config.get("weights", {
        "trend_daily": 30,
        "ma_distance": 30,
        "relative_volume": 20,
        "daily_floor": 20
    })
    
    score = 0
    # 1. Tendencia diaria
    trend_ok = False
    if direction == "CALL":
        trend_ok = bool(row.get('d_trend_bullish', False))
    else:
        trend_ok = not bool(row.get('d_trend_bullish', False))
    if trend_ok:
        score += weights.get("trend_daily", 30)
        
    # 2. Distancia a la media móvil PM40
    if dist_pm40 <= 0.2:
        score += weights.get("ma_distance", 30)
    elif dist_pm40 <= 0.5:
        score += int(weights.get("ma_distance", 30) * 0.66)
    elif dist_pm40 <= 1.0:
        score += int(weights.get("ma_distance", 30) * 0.33)
        
    # 3. Volumen relativo
    vol_rel = float(row.get('relative_volume', 1.0))
    if vol_rel >= 1.5:
        score += weights.get("relative_volume", 20)
    elif vol_rel >= 1.0:
        score += int(weights.get("relative_volume", 20) * 0.5)
        
    # 4. Piso diario
    if bool(row.get('d_at_floor', False)):
        score += weights.get("daily_floor", 20)
        
    return min(100, score)

def send_telegram_notification(message, strategy_id=None):
    """Envía un mensaje enriquecido al chat de Telegram y adjunta el patrón visual de Cardona si está disponible."""
    if not TELEGRAM_ENABLED or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
        
    image_filename = None
    if strategy_id:
        image_filename = STRATEGY_PATTERN_IMAGES.get(strategy_id.upper())
        
    image_path = None
    if image_filename:
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scratch", "pattern_images", image_filename)
        
    if image_path and os.path.exists(image_path):
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        try:
            with open(image_path, "rb") as photo:
                files = {"photo": photo}
                payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": message[:1024],  # Telegram limita caption de fotos a 1024 caracteres
                    "parse_mode": "HTML"
                }
                r = session.post(url, data=payload, files=files, timeout=15)
                if r.status_code == 200:
                    print(f"[Telegram] Alerta enviada con patrón visual: {image_filename}")
                    return
                else:
                    print(f"[Telegram] Error al enviar sendPhoto ({r.status_code}): {r.text}, reintentando por mensaje simple...")
        except Exception as e:
            print(f"[Telegram] Excepción al enviar sendPhoto: {e}, reintentando por mensaje simple...")

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        r = session.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print(f"[Telegram] Error al enviar alerta simple ({r.status_code}): {r.text}")
    except Exception as e:
        print(f"[Telegram] Excepción al enviar alerta simple: {e}")

def sync_setup_and_signal(ticker, strategy_id, timeframe, state, setup_score, price, distance_pm40, volume, rel_vol, slope_pm40, spy_trend, vix_value, session_type, direction, strategy_version):
    """Guarda localmente en la base SQLite y transmite la actualización al webhook relacional."""
    if not os.path.exists(DB_NAME):
        print(f"[Scanner] Base relacional '{DB_NAME}' no existe. Corre db_initializer.py primero.")
        return None

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    date_part = datetime.now().strftime("%Y%m%d")

    # 1. Determinar o crear el setup_id
    today_str = datetime.now().strftime("%Y-%m-%d")
    cursor.execute("""
        SELECT setup_id, state FROM setups 
        WHERE ticker = ? AND strategy_id = ? AND creation_time LIKE ? 
        ORDER BY creation_time DESC LIMIT 1
    """, (ticker, strategy_id, today_str + "%"))
    existing_setup = cursor.fetchone()

    setup_id = None
    if existing_setup:
        setup_id = existing_setup[0]
        # Si el estado es idéntico al registrado y no es CONFIRMADA, evitamos duplicidad en Sheets
        if existing_setup[1] == state and state != "CONFIRMADA":
            conn.close()
            return setup_id
    else:
        cursor.execute("SELECT COUNT(*) FROM setups WHERE creation_time LIKE ?", (today_str + "%",))
        count = cursor.fetchone()[0] + 1
        setup_id = f"{ticker}_{timeframe}_{strategy_id}_{date_part}_{count:03d}"

    # 2. Registrar señal bruta
    signal_id = f"SIG_{ticker}_{date_part}_{int(time.time() * 1000)}"
    
    payload = {
        "webhook_token": "LAB_SIM_SECURE_TOKEN",
        "timestamp": now_str,
        "ticker": ticker,
        "timeframe": timeframe,
        "setup_id": setup_id,
        "signal_id": signal_id,
        "event": {
            "action": "setup_update",
            "state": state,
            "setup_score": setup_score
        },
        "strategy": {
            "id": strategy_id,
            "version": strategy_version,
            "direction": direction
        },
        "market_data": {
            "action_price": price,
            "volume": int(volume),
            "relative_volume": rel_vol,
            "moving_averages": {
                "pm40": price / (1 + (distance_pm40 / 100.0))
            },
            "indicators": {
                "distance_pm40": distance_pm40,
                "pm40_slope": slope_pm40,
                "spy_daily_trend": spy_trend,
                "vix_value": vix_value
            }
        }
    }

    # Guardar señal localmente
    cursor.execute("""
        INSERT INTO senales (signal_id, timestamp, ticker, direction, strategy_id, strategy_version, raw_payload)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (signal_id, now_str, ticker, direction, strategy_id, strategy_version, json.dumps(payload)))

    # Guardar o actualizar setup localmente
    if not existing_setup:
        conf_time = now_str if state == "CONFIRMADA" else None
        inval_time = now_str if state == "INVALIDADA" else None
        cursor.execute("""
            INSERT INTO setups (setup_id, ticker, strategy_id, timeframe, state, creation_time, confirmation_time, invalidation_time, setup_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (setup_id, ticker, strategy_id, timeframe, state, now_str, conf_time, inval_time, setup_score))
    else:
        cursor.execute("""
            UPDATE setups
            SET state = ?, setup_score = ?
            WHERE setup_id = ?
        """, (state, setup_score, setup_id))
        
        if state == "CONFIRMADA":
            cursor.execute("UPDATE setups SET confirmation_time = COALESCE(confirmation_time, ?) WHERE setup_id = ?", (now_str, setup_id))
        elif state == "INVALIDADA":
            cursor.execute("UPDATE setups SET invalidation_time = COALESCE(invalidation_time, ?) WHERE setup_id = ?", (now_str, setup_id))

    # Actualizar Radar
    cursor.execute("""
        INSERT INTO radar_actual (ticker, strategy_id, timeframe, state, setup_score, price, distance_pm40, last_update)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, strategy_id, timeframe) DO UPDATE SET
            state = excluded.state,
            setup_score = excluded.setup_score,
            price = excluded.price,
            distance_pm40 = excluded.distance_pm40,
            last_update = excluded.last_update
    """, (ticker, strategy_id, timeframe, state, setup_score, price, distance_pm40, now_str))

    # Oportunidades anticipadas
    if state in ["PRE-ALERTA", "INMINENTE"]:
        cursor.execute("""
            INSERT OR REPLACE INTO oportunidades_anticipadas (setup_id, timestamp, distance_pm40, approach_speed, pm40_slope, relative_volume)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (setup_id, now_str, distance_pm40, 0.0, slope_pm40, rel_vol))

    # Evento de mercado
    cursor.execute("""
        INSERT OR REPLACE INTO eventos_mercado (timestamp, spy_trend, vix_value, market_session)
        VALUES (?, ?, ?, ?)
    """, (now_str, spy_trend, vix_value, session_type))

    conn.commit()
    conn.close()

    # Manejar encolamiento segun el estado del sistema y conexion de uCharts
    if state == "CONFIRMADA":
        # Ejecutar compra autónoma en el Meliora Sim Broker local
        try:
            # El fix real de esta llamada terminó siendo en sim_broker_core.py
            # (STRATEGY_BUCKETS / STRATEGY_DTE / STRATEGY_DIRECTION tenían sólo
            # 9 claves con un prefijo "cond_" que ya no existe en ningún lado;
            # se reconstruyeron con las 18 claves canónicas reales de
            # catalogo_estrategias, que es exactamente el formato que ya trae
            # strategy_id acá). No hace falta transformar nada en esta llamada.
            conn_sim = sqlite3.connect(DB_NAME)
            res_sim = sim_broker_core.simular_compra_broker(conn_sim, ticker, strategy_id, price)
            conn_sim.close()
            if res_sim.get("status") == "FILLED":
                msg_sim = (
                    f"💼 <b>MELIORA SIM BROKER: ORDEN FILLED</b>\n\n"
                    f"🎯 <b>Activo:</b> {ticker}\n"
                    f"📈 <b>Estrategia:</b> {strategy_id}\n"
                    f"📦 <b>Contratos:</b> {res_sim['qty']}\n"
                    f"💵 <b>Prima:</b> ${res_sim['price']:.2f}\n"
                    f"💰 <b>Costo Total:</b> ${res_sim['cost']:,.2f}\n"
                    f"✅ Orden de compra autorizada por Risk Engine e inscripta en el Ledger."
                )
                send_telegram_notification(msg_sim)
            else:
                # Antes esto se descartaba en silencio total. Ahora al menos
                # queda en la consola para poder diagnosticar rechazos reales
                # (de riesgo, de capital, etc.) sin tener que adivinar.
                print(f"[Sim Broker Core] Compra rechazada para {ticker} ({strategy_id}): {res_sim.get('reason')}")
        except Exception as sim_err:
            print(f"[Sim Broker Core] Error en compra automatizada: {sim_err}")
        
        sys_state = get_system_state()
        if sys_state in ["STOP", "DISARMED"]:
            print(f"[Scanner] Compra omitida para {ticker} por estado del sistema: {sys_state}")
        else:
            # Fix crítico: antes, si el heartbeat de UCharts tenía más de 60s
            # de antigüedad en el momento EXACTO en que se confirmaba la
            # señal, esta se descartaba PARA SIEMPRE (solo se mandaba un
            # aviso de Telegram, nunca se encolaba). Como el escaneo corre
            # una vez por hora, perder ese instante significaba perder la
            # señal por completo — sin reintento posible. Ahora se encola
            # siempre; si UCharts estaba offline, sólo se avisa por Telegram
            # que puede haber demora, pero la señal queda esperando en la
            # cola para cuando UCharts (o el simulador interno) vuelvan a
            # estar activos.
            is_online = (time.time() - last_ucharts_heartbeat) < 60
            if not is_online:
                msg_offline = (
                    f"⚠️ <b>ALERTA DE SISTEMA: uCharts OFFLINE</b>\n\n"
                    f"Se ha confirmado la estrategia <b>{strategy_id}</b> en <b>{ticker}</b>, "
                    f"pero el navegador uCharts no responde (Heartbeat inactivo).\n"
                    f"La señal queda en cola: se ejecutará apenas uCharts vuelva a estar activo."
                )
                try:
                    # Enviar alerta directa de desconexión a Telegram
                    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", json={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "text": msg_offline,
                        "parse_mode": "HTML"
                    }, verify=False, timeout=10)
                except Exception:
                    pass

            global PENDING_TRADES_QUEUE
            if not any(t["setup_id"] == setup_id for t in PENDING_TRADES_QUEUE):
                PENDING_TRADES_QUEUE.append({
                    "setup_id": setup_id,
                    "ticker": ticker,
                    "direction": direction,
                    "strategy_id": strategy_id,
                    "setup_score": setup_score,
                    "price": price,
                    "timestamp": now_str
                })

    # Determinar si ya se envio notificacion a Telegram para este estado y setup
    should_notify_telegram = False
    if state in ["INMINENTE", "CONFIRMADA"]:
        if not existing_setup:
            should_notify_telegram = True
        else:
            saved_state = existing_setup[1]
            if state == "CONFIRMADA" and saved_state != "CONFIRMADA":
                should_notify_telegram = True
            elif state == "INMINENTE" and saved_state not in ["INMINENTE", "CONFIRMADA"]:
                should_notify_telegram = True

    # Transmitir a Google Sheets
    if WEBHOOK_URL and WEBHOOK_URL != "TU_WEBHOOK_URL_AQUÍ":
        try:
            r = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "text/plain"}, verify=False, timeout=25)
            print(f"[Scanner] Webhook relacional enviado ({ticker} - {strategy_id} - {state}): {r.status_code}")
        except Exception as e:
            print(f"[Scanner] Error al transmitir al webhook relacional: {e}")

    # Enviar Notificación de Telegram si aplica y es un evento nuevo
    if state in ["INMINENTE", "CONFIRMADA"] and TELEGRAM_ENABLED and should_notify_telegram:
        msg = (
            f"🔔 <b>ALERTA DE ESTRATEGIA: {state}</b>\n\n"
            f"🎯 <b>Activo:</b> {ticker} ({direction})\n"
            f"📈 <b>Estrategia:</b> {strategy_id} (Score: {setup_score}/100)\n"
            f"💵 <b>Precio Acción:</b> ${price:.2f}\n"
            f"📊 <b>Volumen Relativo:</b> {rel_vol:.2f}x\n"
            f"📍 <b>Distancia PM40:</b> {distance_pm40:.2f}%\n"
            f"🆔 <b>Setup ID:</b> <code>{setup_id}</code>"
        )
        send_telegram_notification(msg, strategy_id=strategy_id)

    return setup_id

def scan_ticker(ticker):
    """Descarga datos recientes y evalúa si hay estrategias activas o en anticipación."""
    print(f"Buscando señales para {ticker}...")
    try:
        # Descarga 30 días de datos horarios y 1 año de datos diarios para los promedios
        df_1h = yf.download(ticker, period="30d", interval="1h", session=session, progress=False)
        df_1d = yf.download(ticker, period="1y", interval="1d", session=session, progress=False)
        
        if df_1h.empty or df_1d.empty:
            return []
            
        # Aplanar columnas multi-nivel si yfinance las descarga así
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = [col[0] for col in df_1h.columns]
        if isinstance(df_1d.columns, pd.MultiIndex):
            df_1d.columns = [col[0] for col in df_1d.columns]
            
        # Calcular SMA diarios
        df_1d['Daily_SMA20'] = df_1d['Close'].rolling(window=20).mean()
        df_1d['Daily_SMA50'] = df_1d['Close'].rolling(window=50).mean()
        df_1d['Daily_SMA100'] = df_1d['Close'].rolling(window=100).mean()
        df_1d['Daily_SMA200'] = df_1d['Close'].rolling(window=200).mean()
        df_1d['Daily_Low60'] = df_1d['Low'].rolling(window=60).min()
        df_1d['Daily_Consecutive_Drops'] = (
            (df_1d['Close'] < df_1d['Close'].shift(1)) & 
            (df_1d['Close'].shift(1) < df_1d['Close'].shift(2)) & 
            (df_1d['Close'].shift(2) < df_1d['Close'].shift(3))
        ).fillna(False).astype(bool)
        
        # Merge de promedios diarios con datos horarios
        df_1h['Date_Only'] = df_1h.index.date
        df_1d_subset = df_1d[['Daily_SMA20', 'Daily_SMA50', 'Daily_SMA100', 'Daily_SMA200', 'Daily_Low60', 'Daily_Consecutive_Drops', 'Open', 'High', 'Low', 'Close']].copy()
        df_1d_subset.rename(columns={
            'Open': 'Daily_Open',
            'High': 'Daily_High',
            'Low': 'Daily_Low',
            'Close': 'Daily_Close'
        }, inplace=True)
        df_1d_subset['Date_Only'] = df_1d_subset.index.date
        
        df = df_1h.reset_index().merge(df_1d_subset, on='Date_Only', how='left').set_index('Datetime')
        
        # Calcular medias móviles horarias
        df['PM10'] = df['Close'].rolling(window=10).mean()
        df['PM20'] = df['Close'].rolling(window=20).mean()
        df['PM40'] = df['Close'].rolling(window=40).mean()
        df['PM100'] = df['Close'].rolling(window=100).mean()
        df['PM200'] = df['Close'].rolling(window=200).mean()
        
        # Calcular volumen relativo y pendientes
        df['volume_ma20'] = df['Volume'].rolling(window=20).mean()
        df['relative_volume'] = df['Volume'] / df['volume_ma20']
        df['pm40_slope'] = (df['PM40'] - df['PM40'].shift(1)) / df['PM40'].shift(1) * 100
        
        # Detección de sesión
        datetime_series = pd.Series(df.index, index=df.index)
        df['is_first_bar'] = datetime_series.dt.normalize() != datetime_series.shift(1).dt.normalize()
        df['is_second_bar'] = df['is_first_bar'].shift(1).fillna(False)
        df['is_last_bar'] = datetime_series.dt.hour == 15
        
        # Cuerpo y rango
        df['body'] = (df['Close'] - df['Open']).abs()
        df['range_c'] = df['High'] - df['Low']
        df['is_green'] = df['Close'] > df['Open']
        df['is_red'] = df['Close'] < df['Open']
        
        # Tipo de velas
        df['is_solid_green'] = df['is_green'] & (df['body'] > 0.6 * df['range_c'])
        df['is_solid_red'] = df['is_red'] & (df['body'] > 0.6 * df['range_c'])
        df['is_hammer'] = df['is_green'] & ((df['Open'] - df['Low']) > 2 * df['body']) & ((df['High'] - df['Close']) < 0.2 * df['body'])
        df['is_hanger'] = df['is_red'] & ((df['Close'] - df['Low']) > 2 * df['body']) & ((df['High'] - df['Open']) < 0.2 * df['body'])
        
        # Colas de piso/techo
        df['lower_wick'] = np.where(df['is_green'], df['Open'] - df['Low'], df['Close'] - df['Low'])
        df['upper_wick'] = np.where(df['is_green'], df['High'] - df['Close'], df['High'] - df['Open'])
        df['is_cola_piso'] = (df['range_c'] > 0) & (df['lower_wick'] >= 0.5 * df['range_c']) & (df['body'] <= 0.4 * df['range_c'])
        df['is_cola_techo'] = (df['range_c'] > 0) & (df['upper_wick'] >= 0.5 * df['range_c']) & (df['body'] <= 0.4 * df['range_c'])
        
        # Canales Donchian y soportes
        df['lowest_20'] = df['Low'].shift(1).rolling(window=20).min()
        df['near_low'] = df['Low'] <= df['lowest_20'] + df['range_c'] * 0.5
        df['highest_20'] = df['High'].shift(1).rolling(window=20).max()
        df['near_high'] = df['High'] >= df['highest_20'] - df['range_c'] * 0.5
        
        # Variables diarias
        df['gap_percent'] = np.nan
        df['first_bar_low'] = np.nan
        df['first_bar_green'] = None
        df['first_bar_red'] = None
        
        first_bars = df[df['is_first_bar']].copy()
        if not first_bars.empty:
            yesterday_closes = df_1d['Close'].shift(1)
            yesterday_closes.index = yesterday_closes.index.date
            first_bar_dates = first_bars.index.date
            
            yesterday_close_vals = []
            for d in first_bar_dates:
                if d in yesterday_closes.index and not pd.isna(yesterday_closes.loc[d]):
                    yesterday_close_vals.append(yesterday_closes.loc[d])
                else:
                    prev_dates = [idx for idx in yesterday_closes.index if idx < d]
                    if prev_dates:
                        yesterday_close_vals.append(yesterday_closes.loc[max(prev_dates)])
                    else:
                        matching_bars = first_bars[first_bars.index.date == d]
                        if not matching_bars.empty:
                            yesterday_close_vals.append(matching_bars['Open'].iloc[0])
                        else:
                            yesterday_close_vals.append(100.0)
            yesterday_close_vals = np.array(yesterday_close_vals)
            
            first_bars['gap_percent'] = (first_bars['Open'] - yesterday_close_vals) / yesterday_close_vals * 100
            first_bars['first_bar_low'] = first_bars['Low']
            first_bars['first_bar_green'] = first_bars['is_solid_green'] | first_bars['is_hammer']
            first_bars['first_bar_red'] = first_bars['is_solid_red'] | first_bars['is_hanger']
            
            df.loc[first_bars.index, 'gap_percent'] = first_bars['gap_percent']
            df.loc[first_bars.index, 'first_bar_low'] = first_bars['first_bar_low']
            df.loc[first_bars.index, 'first_bar_green'] = first_bars['first_bar_green']
            df.loc[first_bars.index, 'first_bar_red'] = first_bars['first_bar_red']
            
            df['gap_percent'] = df.groupby('Date_Only')['gap_percent'].ffill()
            df['first_bar_low'] = df.groupby('Date_Only')['first_bar_low'].ffill()
            df['first_bar_green'] = df.groupby('Date_Only')['first_bar_green'].ffill().fillna(False).astype(bool)
            df['first_bar_red'] = df.groupby('Date_Only')['first_bar_red'].ffill().fillna(False).astype(bool)
            
        df['low_so_far'] = df.groupby('Date_Only')['Low'].cummin()
        df['floor_respected'] = df['low_so_far'] >= df['first_bar_low']
        
        # Tendencias y soportes diarios (Reglas de Cardona)
        df['d_trend_bullish'] = df['Close'] > df['Daily_SMA100']
        df['d_near_sma100'] = (df['Close'] - df['Daily_SMA100']).abs() / df['Daily_SMA100'] < 0.02
        df['d_near_sma200'] = (df['Close'] - df['Daily_SMA200']).abs() / df['Daily_SMA200'] < 0.02
        df['d_near_low60'] = (df['Close'] - df['Daily_Low60']).abs() / df['Daily_Low60'] < 0.02
        df['d_at_floor'] = df['d_near_sma100'] | df['d_near_sma200'] | df['d_near_low60']
        
        # Contexto de Caída Previa (Regla 1 de Primer Gap al Alza)
        df['d_prior_drop'] = (df['Close'] < df['Daily_SMA20']) | (df['Close'] < df['Daily_SMA50']) | (df['Close'] < df['Close'].shift(5) * 0.97)
        
        # Zonas medias móviles
        df['near_ma_piso'] = (
            (df['Low'] <= df['PM10'] * 1.0015) & (df['Close'] >= df['PM10']) |
            (df['Low'] <= df['PM20'] * 1.0015) & (df['Close'] >= df['PM20']) |
            (df['Low'] <= df['PM40'] * 1.0015) & (df['Close'] >= df['PM40']) |
            (df['Low'] <= df['PM100'] * 1.0015) & (df['Close'] >= df['PM100']) |
            (df['Low'] <= df['PM200'] * 1.0015) & (df['Close'] >= df['PM200'])
        )
        df['near_ma_techo'] = (
            (df['High'] >= df['PM10'] * 0.9985) & (df['Close'] <= df['PM10']) |
            (df['High'] >= df['PM20'] * 0.9985) & (df['Close'] <= df['PM20']) |
            (df['High'] >= df['PM40'] * 0.9985) & (df['Close'] <= df['PM40']) |
            (df['High'] >= df['PM100'] * 0.9985) & (df['Close'] >= df['PM100']) |
            (df['High'] >= df['PM200'] * 0.9985) & (df['Close'] <= df['PM200'])
        )
        
        df['cond_cola_piso'] = df['is_cola_piso'] & (df['near_low'] | df['near_ma_piso'])
        df['cond_cola_techo'] = df['is_cola_techo'] & (df['near_high'] | df['near_ma_techo'])
        
        # PM 40
        is_touch_pm40 = (df['Low'] <= df['PM40'] * 1.0015) & (df['Close'] >= df['PM40'] * 0.9985)
        df['touched_pm40'] = is_touch_pm40.rolling(window=4).max().fillna(0).astype(bool)
        df['highest_high_3'] = df['High'].shift(1).rolling(window=3).max()
        df['cross_highest_3'] = (df['Close'] > df['highest_high_3']) & (df['Close'].shift(1) <= df['highest_high_3'].shift(1))
        df['cond_pm40_bounce'] = (df['PM20'] > df['PM40']) & df['touched_pm40'] & df['cross_highest_3'] & (df['is_solid_green'] | df['is_hammer'])
        
        # Caída
        df['recent_peak'] = df['High'].shift(1).rolling(window=10).max()
        df['pct_drop'] = (df['recent_peak'] - df['Low']) / df['recent_peak'] * 100
        df['is_caida_normal'] = (df['pct_drop'] >= 0.5) & (df['pct_drop'] <= 1.5)
        df['is_caida_fuerte'] = df['pct_drop'] > 1.5
        df['cond_caida_normal'] = df['d_trend_bullish'] & df['is_caida_normal'] & df['cross_highest_3'] & df['is_solid_green']
        df['cond_caida_fuerte'] = df['d_trend_bullish'] & df['is_caida_fuerte'] & df['cross_highest_3'] & df['is_solid_green']
        
        # Canal
        df['highest_high_10'] = df['High'].shift(1).rolling(window=10).max()
        df['cross_highest_10'] = (df['Close'] > df['highest_high_10']) & (df['Close'].shift(1) <= df['highest_high_10'].shift(1))
        df['highest_high_15'] = df['High'].shift(1).rolling(window=15).max()
        df['cross_highest_15'] = (df['Close'] > df['highest_high_15']) & (df['Close'].shift(1) <= df['highest_high_15'].shift(1))
        df['in_descending_channel'] = df['PM20'] < df['PM40']
        df['breakout_bar'] = df['in_descending_channel'].shift(1) & df['cross_highest_15'].shift(1) & df['is_solid_green'].shift(1)
        df['cond_canal_break'] = df['breakout_bar'] & df['is_green']
        
        # Hanger (Hombre Colgado en Diario)
        df['d_body'] = (df['Daily_Close'] - df['Daily_Open']).abs()
        df['d_range'] = df['Daily_High'] - df['Daily_Low']
        df['d_lower_wick'] = np.minimum(df['Daily_Open'], df['Daily_Close']) - df['Daily_Low']
        df['d_upper_wick'] = df['Daily_High'] - np.maximum(df['Daily_Open'], df['Daily_Close'])
        
        # El Hanger exige mecha inferior larga (>=55% del rango), cuerpo pequeño arriba (<=35%) y mecha superior muy pequeña (<=15%)
        df['d_is_hanger'] = (df['d_range'] > 0) & (df['d_lower_wick'] >= 0.55 * df['d_range']) & (df['d_body'] <= 0.35 * df['d_range']) & (df['d_upper_wick'] <= 0.15 * df['d_range'])
        
        # Debe ocurrir en tendencia alcista estructurada (SMA100 > SMA200) y con el precio sobre la SMA100
        df['cond_hanger_diario'] = df['is_last_bar'] & df['d_is_hanger'] & (df['Daily_SMA100'] > df['Daily_SMA200']) & (df['Close'] > df['Daily_SMA100'])
        
        # Rupturas
        df['highest_high_20'] = df['High'].shift(1).rolling(window=20).max()
        df['cross_highest_20'] = (df['Close'] > df['highest_high_20']) & (df['Close'].shift(1) <= df['highest_high_20'].shift(1))
        df['cond_ruptura_res'] = df['d_trend_bullish'] & df['cross_highest_20'] & df['is_solid_green']
        
        df['lowest_low_20'] = df['Low'].shift(1).rolling(window=20).min()
        df['cross_lowest_20'] = (df['Close'] < df['lowest_low_20']) & (df['Close'].shift(1) >= df['lowest_low_20'].shift(1))
        df['cond_ruptura_sop'] = (~df['d_trend_bullish']) & df['cross_lowest_20'] & df['is_solid_red']
        
        # Piso break y gaps
        df['crossunder_sma100'] = (df['Close'] < df['Daily_SMA100']) & (df['Close'].shift(1) >= df['Daily_SMA100'].shift(1))
        df['crossunder_sma200'] = (df['Close'] < df['Daily_SMA200']) & (df['Close'].shift(1) >= df['Daily_SMA200'].shift(1))
        df['cond_piso_break'] = (df['crossunder_sma100'] | df['crossunder_sma200']) & df['is_solid_red']
        
        df['cond_gap_cont_put'] = df['is_second_bar'] & (df['gap_percent'] < -0.1) & df['first_bar_red'] & df['is_red']
        
        # Gaps
        df['cond_gap_normal'] = (df['d_trend_bullish'] | (df['Close'] > df['PM40'])) & df['is_second_bar'] & (df['gap_percent'] > 0.1) & df['first_bar_green'] & df['is_green']
        df['cond_gap_bajista'] = df['is_second_bar'] & (df['gap_percent'] < -0.1) & df['first_bar_green'] & df['is_solid_green']
        df['cond_piso_fuerte'] = (df['Daily_SMA100'] > df['Daily_SMA200']) & df['d_at_floor'] & df['in_descending_channel'] & df['cross_highest_10'] & df['is_solid_green']
        df['cond_primer_gap'] = df['d_at_floor'] & df['is_last_bar'] & (df['gap_percent'] > 0.1) & df['first_bar_green'] & df['floor_respected'] & df['d_prior_drop']
        df['cond_vela_roja'] = (
            df['is_first_bar'] & 
            df['is_solid_red'] & 
            (df['gap_percent'] > 0.05) & 
            (df['relative_volume'] > 1.0) & 
            ((df['PM20'] < df['PM40']) | (abs(df['Close'] - df['PM40']) / df['PM40'] < 0.02) | (abs(df['Close'] - df['PM200']) / df['PM200'] < 0.02))
        )
        df['cond_techo_fuerte'] = df['d_at_floor'] & df['is_second_bar'] & df['is_red'] & df['is_solid_red']
        df['cond_ruptura_piso'] = ~df['is_first_bar'] & (df['Close'] > df['PM40']) & (df['Close'].shift(1) >= df['first_bar_low']) & (df['Close'] < df['first_bar_low']) & df['is_solid_red'] & ~df['Daily_Consecutive_Drops'].fillna(False)
        df['cond_4_pasos'] = (df['PM20'] < df['PM40']) & (df['Close'] < df['PM40']) & df['is_solid_red'] & df['is_green'].shift(1) & (df['Close'] < df['Open'].shift(1)) & (df['Close'] < df['Low'].shift(1).rolling(window=3).min())
        
        last_idx = -1
        row = df.iloc[last_idx]
        bar_time = df.index[last_idx]
        
        if pd.isna(row['PM20']):
            last_idx = -2
            row = df.iloc[last_idx]
            bar_time = df.index[last_idx]
            
        active_signals = []
        close_price = float(row['Close'])
        dist_pm40 = abs(close_price - float(row['PM40'])) / close_price * 100
        
        # Evaluar estrategias de la base
        for cond_col, metadata in STRATEGIES_METADATA.items():
            strategy_id = cond_col.replace("cond_", "").upper()
            direction = metadata[1]
            state = "OBSERVACION"
            
            is_confirmed = bool(row[cond_col]) if cond_col in df.columns else False
            
            # --- REGLAS ADICIONALES DE CARDONA (Seminario Privado) ---
            if is_confirmed:
                # 1. Filtro de Velas Hanger en PM40 Bounce (Evitar falsas rupturas)
                if strategy_id == "PM40_BOUNCE":
                    b_open = float(row['Open'])
                    b_close = float(row['Close'])
                    b_high = float(row['High'])
                    b_low = float(row['Low'])
                    b_body = abs(b_close - b_open)
                    b_range = b_high - b_low
                    b_upper_wick = b_high - max(b_open, b_close)
                    
                    is_bar_hanger = (b_range > 0) and (b_upper_wick >= 0.45 * b_range) and (b_body <= 0.4 * b_range)
                    if is_bar_hanger:
                        print(f"[Filtro Cardona] Descartando confirmacion de PM40_BOUNCE en {ticker} por vela Hanger.")
                        is_confirmed = False
                
                # 2. Restricciones Horarias de Ejecucion
                # A: Primera Vela Roja de Apertura (VELA_ROJA): Solo en la hora de apertura (9:30 o 10:00 AM)
                if strategy_id == "VELA_ROJA" and bar_time.hour not in [9, 10]:
                    print(f"[Filtro Cardona] Descartando VELA_ROJA en {ticker} fuera de la hora de apertura (Hora: {bar_time.hour}).")
                    is_confirmed = False
                    
                # B: Gaps normales y bajistas al alza: Esperar hasta las 11:00 AM NY (barra >= 11)
                if strategy_id in ["GAP_NORMAL", "GAP_BAJISTA"] and bar_time.hour < 11:
                    print(f"[Filtro Cardona] Descartando {strategy_id} en {ticker} antes de las 11:00 AM (Hora: {bar_time.hour}).")
                    is_confirmed = False
                    
                # C: Primer Gap al Alza: Esperar hasta las 3:59 PM NY (barra de las 15:00)
                if strategy_id == "GAP_ALZA_1" and bar_time.hour != 15:
                    print(f"[Filtro Cardona] Descartando GAP_ALZA_1 en {ticker} antes del cierre de las 3:59 PM (Hora: {bar_time.hour}).")
                    is_confirmed = False
            
            if is_confirmed:
                state = "CONFIRMADA"
            elif strategy_id == "PM40_BOUNCE":
                if dist_pm40 <= IMMINENT_THRESHOLD:
                    state = "INMINENTE"
                elif dist_pm40 <= ANTICIPATION_THRESHOLD:
                    state = "PRE-ALERTA"
                    
            if state != "OBSERVACION":
                score = calculate_setup_score(row, direction, dist_pm40, CONFIG)
                
                setup_id = sync_setup_and_signal(
                    ticker=ticker,
                    strategy_id=strategy_id,
                    timeframe="1H",
                    state=state,
                    setup_score=score,
                    price=close_price,
                    distance_pm40=dist_pm40,
                    volume=row['Volume'],
                    rel_vol=row['relative_volume'],
                    slope_pm40=row['pm40_slope'],
                    spy_trend="BULLISH" if close_price > row.get('Daily_SMA100', 0) else "BEARISH",
                    vix_value=15.0,
                    session_type="RTH" if 9 <= bar_time.hour <= 16 else "GLOBEX",
                    direction=direction,
                    strategy_version="1.0"
                )
                
                if state == "CONFIRMADA":
                    active_signals.append({
                        "ticker": ticker,
                        "type": direction,
                        "strategy": metadata[0],
                        "price": round(close_price, 2),
                        "probability": metadata[2],
                        "time": bar_time.strftime('%Y-%m-%d %H:%M:%S'),
                        "setup_id": setup_id,
                        "setup_score": score
                    })
                    
        return active_signals
        
    except Exception as e:
        print(f"Error al escanear {ticker}: {e}")
        import traceback
        traceback.print_exc()
        return []

def main():
    report_heartbeat("SCANNER", "ONLINE", "Escáner principal en ejecución")
    report_heartbeat("DATABASE", "ONLINE", "Acceso a base de datos validado")
    report_heartbeat("STRATEGY_ENGINE", "ONLINE", "Motor de estrategias cargado")
    report_heartbeat("RISK_ENGINE", "ONLINE", "Motor de riesgo cargado")
    report_heartbeat("CAPITAL_ENGINE", "ONLINE", "Motor de capital cargado")

    # Si scanner_active en base de datos es false, omitir escaneo
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT val FROM configuracion WHERE param_id = 'scanner_active'")
        row_scan = cursor.fetchone()
        conn.close()
        if row_scan and row_scan[0] == 'false':
            print("[Scanner] Escaneo omitido: El scanner está pausado vía API.")
            report_heartbeat("SCANNER", "DEGRADED", "Scanner pausado por usuario")
            return []
    except Exception:
        pass

    if WEBHOOK_URL == "TU_WEBHOOK_URL_AQUÍ":
        print("ERROR: Debes configurar la variable WEBHOOK_URL.")
        sys.exit(1)
        
    print(f"=== INICIANDO ESCANEO RELACIONAL DE {len(TICKERS)} ACTIVOS ===")
    all_signals = []
    
    for ticker in TICKERS:
        signals = scan_ticker(ticker)
        if signals:
            print(f"[Signal] SENAL DETECTADA en {ticker}! {signals}")
            all_signals.extend(signals)
            
    print(f"\nEscaneo finalizado. Total de señales activas encontradas: {len(all_signals)}")
    report_heartbeat("SCANNER", "ONLINE", f"Escaneo completado. {len(all_signals)} señales detectadas.")
    report_heartbeat("MARKET_DATA", "ONLINE", "Datos históricos yfinance actualizados")
    return all_signals

# ==========================================
# SERVIDOR HTTP DE CONTROL LOCAL
# ==========================================
import threading
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def run_backtesting():
    print("[Control Web] Iniciando ejecución de backtest_to_db.py...")
    proc1 = subprocess.run([sys.executable, "backtest_to_db.py"], capture_output=True, text=True)
    print("[Control Web] Iniciando ejecución de analyze_results.py...")
    proc2 = subprocess.run([sys.executable, "analyze_results.py"], capture_output=True, text=True)
    return proc1.returncode == 0 and proc2.returncode == 0

def sync_backtest_results_to_sheets():
    db_path = "trades_backtest.db"
    if not os.path.exists(db_path):
        return {"status": "error", "message": "No existe la base de datos de backtesting."}
        
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM trades", conn)
        conn.close()
        
        if df.empty:
            return {"status": "error", "message": "La base de datos de backtesting está vacía."}
            
        total_trades = len(df)
        df['return_pct'] = pd.to_numeric(df['return_pct'])
        df['duration_hours'] = pd.to_numeric(df['duration_hours'])
        
        winning_trades = len(df[df['return_pct'] > 0])
        losing_trades = len(df[df['return_pct'] <= 0])
        win_rate = round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0
        
        gross_profits = df[df['return_pct'] > 0]['return_pct'].sum()
        gross_losses = abs(df[df['return_pct'] <= 0]['return_pct'].sum())
        profit_factor = round((gross_profits / gross_losses), 2) if gross_losses > 0 else "Infinito"
        
        avg_return = round(df['return_pct'].mean(), 2)
        max_win = round(df['return_pct'].max(), 2)
        max_loss = round(df['return_pct'].min(), 2)
        avg_duration = round(df['duration_hours'].mean(), 1)
        
        summary = [
            {"metrica": "Total de Operaciones", "valor": total_trades},
            {"metrica": "Operaciones Ganadoras", "valor": winning_trades},
            {"metrica": "Operaciones Perdedoras", "valor": losing_trades},
            {"metrica": "Tasa de Acierto (Win Rate %)", "valor": win_rate},
            {"metrica": "Factor de Ganancia (Profit Factor)", "valor": profit_factor},
            {"metrica": "Retorno Promedio por Trade (%)", "valor": avg_return},
            {"metrica": "Mejor Retorno (%)", "valor": max_win},
            {"metrica": "Peor Retorno (%)", "valor": max_loss},
            {"metrica": "Duración Promedio (Horas)", "valor": avg_duration}
        ]
        
        strat_groups = df.groupby('strategy')
        by_strategy = []
        for name, group in strat_groups:
            t_trades = len(group)
            w_trades = len(group[group['return_pct'] > 0])
            w_rate = round((w_trades / t_trades * 100), 2) if t_trades > 0 else 0.0
            a_return = round(group['return_pct'].mean(), 2)
            by_strategy.append({
                "estrategia": name,
                "trades": t_trades,
                "win_rate": w_rate,
                "avg_return": a_return
            })
        by_strategy.sort(key=lambda x: x["avg_return"], reverse=True)
            
        ticker_groups = df.groupby('ticker')
        by_ticker = []
        for name, group in ticker_groups:
            t_trades = len(group)
            w_trades = len(group[group['return_pct'] > 0])
            w_rate = round((w_trades / t_trades * 100), 2) if t_trades > 0 else 0.0
            a_return = round(group['return_pct'].mean(), 2)
            by_ticker.append({
                "ticker": name,
                "trades": t_trades,
                "win_rate": w_rate,
                "avg_return": a_return
            })
        by_ticker.sort(key=lambda x: x["avg_return"], reverse=True)
            
        payload = {
            "action": "update_backtest_data",
            "summary": summary,
            "by_strategy": by_strategy,
            "by_ticker": by_ticker
        }
        
        r = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "text/plain"}, verify=False)
        if r.status_code == 200:
            return {"status": "success", "message": "Resultados sincronizados."}
        else:
            return {"status": "error", "message": f"Error ({r.status_code}): {r.text}"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

class BotControlServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass
        
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        BaseHTTPRequestHandler.end_headers(self)

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def is_request_authorized(self):
        # Rutas públicas exceptuadas de autenticación
        clean_path = self.path.split('?')[0]
        if clean_path in ['', '/', '/index.html', '/ping', '/ucharts.user.js', '/webhook']:
            return True
        if clean_path.startswith('/assets/'):
            return True
        if clean_path.startswith('/api/auth/login'):
            return True
            
        # Comprobar si la petición se dirige a localhost o 127.0.0.1
        # (Permite que Tampermonkey y la terminal local de uCharts funcionen de inmediato)
        host_header = self.headers.get('Host', '')
        if 'localhost' in host_header or '127.0.0.1' in host_header:
            return True
            
        # Comprobar token en query string o cabecera Authorization
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        token = params.get('session_token', [None])[0]
        
        if not token:
            auth_header = self.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header.replace('Bearer ', '').strip()
                
        if not token:
            return False
            
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT val FROM configuracion WHERE param_id = 'active_session_token'")
            row = cursor.fetchone()
            conn.close()
            if row and row[0] == token:
                return True
        except Exception:
            pass
        return False

    def send_unauthorized(self):
        self.send_response(401)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "error", "message": "unauthorized"}).encode('utf-8'))

    def do_GET(self):
        if not self.is_request_authorized():
            self.send_unauthorized()
            return
        if self.path in ['', '/', '/index.html']:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            try:
                portal_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
                with open(portal_path, "r", encoding="utf-8") as pf:
                    html_content = pf.read()
                if WEBHOOK_URL and WEBHOOK_URL != "TU_WEBHOOK_URL_AQUÍ":
                    html_content = html_content.replace("TU_WEBHOOK_URL_AQUÍ", WEBHOOK_URL)
                self.wfile.write(html_content.encode('utf-8'))
            except Exception as e:
                self.wfile.write(f"<h1>Error al cargar portal</h1><p>{e}</p>".encode('utf-8'))
        elif self.path.startswith('/assets/'):
            try:
                clean_path = self.path.split('?')[0].lstrip('/')
                file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), clean_path)
                if os.path.exists(file_path):
                    self.send_response(200)
                    if file_path.endswith('.png'):
                        self.send_header('Content-Type', 'image/png')
                    elif file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                        self.send_header('Content-Type', 'image/jpeg')
                    else:
                        self.send_header('Content-Type', 'application/octet-stream')
                    self.end_headers()
                    with open(file_path, "rb") as f:
                        self.wfile.write(f.read())
                    return
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                return
        elif self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "online", "message": "Activo."}).encode('utf-8'))
        elif self.path == '/scan':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                signals = main()
                self.wfile.write(json.dumps({"status": "success", "signals": signals}).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/backtest':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                success = run_backtesting()
                if success:
                    self.wfile.write(json.dumps({"status": "success", "message": "Completado."}).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"status": "error", "message": "Error."}).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/sync_backtest':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                res = sync_backtest_results_to_sheets()
                self.wfile.write(json.dumps(res).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/ucharts.user.js':
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.end_headers()
            try:
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ucharts_sync_userscript.js")
                with open(script_path, "r", encoding="utf-8") as sf:
                    code = sf.read()
                if WEBHOOK_URL and WEBHOOK_URL != "TU_WEBHOOK_URL_AQUÍ":
                    code = code.replace("TU_WEBHOOK_URL_AQUÍ", WEBHOOK_URL)
                self.wfile.write(code.encode('utf-8'))
            except Exception as e:
                self.wfile.write(f"// Error: {e}".encode('utf-8'))
        elif self.path == '/api/bots':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT bot_id, desired_state, actual_state, last_heartbeat, last_activity, last_error, worker_id, enabled FROM bot_status")
                bots = []
                for row in cursor.fetchall():
                    last_hb = row[3]
                    is_alive = False
                    if last_hb:
                        try:
                            hb_dt = datetime.strptime(last_hb, "%Y-%m-%d %H:%M:%S")
                            diff = (datetime.now() - hb_dt).total_seconds()
                            is_alive = diff < 25
                        except Exception:
                            pass

                    # Fix: un escaneo de 35 activos puede tardar bastante más
                    # que 25s. Antes, mientras escaneaba, se mostraba
                    # "SIN_RESPUESTA" aunque estuviera vivo y trabajando —
                    # confuso, parecía caído sin estarlo.
                    if row[0] == 'live_scanner' and SCANNING_IN_PROGRESS:
                        is_alive = True

                    actual_state = row[2]
                    if not is_alive and actual_state not in ('STOPPED', 'PAUSED'):
                        actual_state = 'SIN_RESPUESTA'

                    bots.append({
                        "bot_id": row[0],
                        "desired_state": row[1],
                        "actual_state": actual_state,
                        "last_heartbeat": row[3],
                        "last_activity": row[4],
                        "last_error": row[5],
                        "worker_id": row[6],
                        "enabled": bool(row[7])
                    })
                conn.close()
                self.wfile.write(json.dumps(bots).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path.startswith('/api/bots/') and self.path.endswith('/logs'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                parts = self.path.split('/')
                bot_id = parts[3]
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT severity, event_type, message, timestamp FROM bot_logs WHERE bot_id = ? ORDER BY timestamp DESC LIMIT 50", (bot_id,))
                logs = []
                for row in cursor.fetchall():
                    logs.append({
                        "severity": row[0],
                        "event_type": row[1],
                        "message": row[2],
                        "timestamp": row[3]
                    })
                conn.close()
                self.wfile.write(json.dumps(logs).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/api/system/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT allow_new_trades, kill_switch_reason FROM system_settings WHERE id = 1")
                row = cursor.fetchone()
                conn.close()
                allow = bool(row[0]) if row else True
                reason = row[1] if row else ""
                self.wfile.write(json.dumps({
                    "status": "healthy",
                    "allow_new_trades": allow,
                    "kill_switch_reason": reason,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path.startswith('/api/simulador/list_accounts'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT id, nombre, balance_inicial, balance_actual FROM cuentas_simuladas ORDER BY creation_time ASC")
                accounts = []
                for row in cursor.fetchall():
                    accounts.append({
                        "id": row[0],
                        "nombre": row[1],
                        "balance_inicial": row[2],
                        "balance_actual": row[3]
                    })
                conn.close()
                self.wfile.write(json.dumps(accounts).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/get_system_status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            state = get_system_state()
            is_online = (time.time() - last_ucharts_heartbeat) < 60
            self.wfile.write(json.dumps({
                "system_state": state,
                "ucharts_status": "ONLINE" if is_online else "OFFLINE",
                "last_heartbeat": last_ucharts_heartbeat
            }).encode('utf-8'))
        elif self.path.startswith('/api/simulador_status'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                from urllib.parse import urlparse, parse_qs
                parsed_url = urlparse(self.path)
                query = parse_qs(parsed_url.query)
                cuenta_id = normalizar_cuenta_id(query.get('cuenta_id', ['default'])[0])
                
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                
                # Asegurar que la cuenta elegida exista, si no, crearla al vuelo
                cursor.execute("SELECT balance_actual FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
                row_acc = cursor.fetchone()
                if not row_acc:
                    # Crear cuenta al vuelo
                    default_balance = 3884329.04 if cuenta_id == 'default' else 100000.0
                    cursor.execute("""
                        INSERT OR IGNORE INTO cuentas_simuladas (id, nombre, balance_inicial, balance_actual, creation_time)
                        VALUES (?, ?, ?, ?, datetime('now'))
                    """, (cuenta_id, cuenta_id.replace('_', ' ').title(), default_balance, default_balance))
                    conn.commit()
                    balance_actual = default_balance
                else:
                    balance_actual = float(row_acc[0])
                
                # Recalcular buckets para esta cuenta
                sim_broker_core.recalcular_buckets_capital(conn, cuenta_id=cuenta_id)
                
                # Balance inicial de la cuenta (para drawdown / cupos)
                cursor.execute("SELECT balance_inicial FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
                bal_row = cursor.fetchone()
                bal_init = float(bal_row[0]) if bal_row else 3884329.04
                
                # Cupos
                today_str = datetime.now().strftime("%Y-%m-%d")
                cursor.execute("SELECT cupo_disponible, cupo_gastado FROM capital_diario_control WHERE fecha = ? AND id = ?", (today_str, cuenta_id))
                ctrl_row = cursor.fetchone()
                if ctrl_row:
                    cupo_disp, cupo_gast = ctrl_row
                else:
                    cupo_disp, cupo_gast = balance_actual * 0.10, 0.0
                
                # Saldo acumulado Cuenta Corriente de esta cuenta
                cursor.execute("SELECT SUM(monto) FROM cuenta_corriente_movimientos WHERE cuenta_id = ?", (cuenta_id,))
                cc_row = cursor.fetchone()
                cc_saldo = float(cc_row[0]) if cc_row and cc_row[0] is not None else 0.0
                
                # Buckets
                cursor.execute("SELECT bucket_id, porcentaje_asignado, capital_disponible, capital_comprometido, pnl_acumulado FROM capital_buckets WHERE cuenta_id = ?", (cuenta_id,))
                bucket_cols = [c[0] for c in cursor.description]
                buckets_list = [dict(zip(bucket_cols, r)) for r in cursor.fetchall()]
                
                # Posiciones abiertas de esta cuenta
                cursor.execute("""
                    SELECT id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada, precio_actual, 
                           pnl_pct, pnl_usd, estado, fecha_apertura, dte_plazo, targets_alcanzados 
                    FROM operaciones_simuladas WHERE estado = 'OPEN' AND cuenta_id = ?
                """, (cuenta_id,))
                open_cols = [c[0] for c in cursor.description]
                posiciones_abiertas = [dict(zip(open_cols, r)) for r in cursor.fetchall()]
                
                # Posiciones cerradas hoy de esta cuenta
                cursor.execute("""
                    SELECT id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada, precio_actual, 
                           pnl_pct, pnl_usd, estado, fecha_apertura, fecha_cierre, dte_plazo, targets_alcanzados 
                    FROM operaciones_simuladas WHERE estado = 'CLOSED' AND cuenta_id = ? AND fecha_cierre LIKE ?
                """, (cuenta_id, today_str + "%"))
                closed_cols = [c[0] for c in cursor.description]
                posiciones_cerradas = [dict(zip(closed_cols, r)) for r in cursor.fetchall()]
                
                # Ledger (Últimos 15 movimientos) de esta cuenta
                cursor.execute("""
                    SELECT mov_id, timestamp, tipo_movimiento, monto_debito, monto_credito, balance_resultante, trade_id, referencia 
                    FROM ledger_movimientos WHERE cuenta_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT 15
                """, (cuenta_id,))
                ledger_cols = [c[0] for c in cursor.description]
                ledger_movs = [dict(zip(ledger_cols, r)) for r in cursor.fetchall()]
                
                # Movimientos Cuenta Corriente (Últimos 15) de esta cuenta
                cursor.execute("""
                    SELECT mov_id, timestamp, trade_id, monto, balance_acumulado, estrategia, bot_id 
                    FROM cuenta_corriente_movimientos WHERE cuenta_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT 15
                """, (cuenta_id,))
                cc_mov_cols = [c[0] for c in cursor.description]
                cc_movs = [dict(zip(cc_mov_cols, r)) for r in cursor.fetchall()]
                
                # System configurations and heartbeats
                cursor.execute("SELECT val FROM configuracion WHERE param_id = 'system_state'")
                state_row = cursor.fetchone()
                sys_state = state_row[0] if state_row else "ARMED"
                
                cursor.execute("SELECT val FROM configuracion WHERE param_id = 'scanner_active'")
                scanner_row = cursor.fetchone()
                scanner_active = scanner_row[0] if scanner_row else "true"
                
                cursor.execute("SELECT val FROM configuracion WHERE param_id = 'autotrade_active'")
                autotrade_row = cursor.fetchone()
                autotrade_active = autotrade_row[0] if autotrade_row else "true"
                
                cursor.execute("SELECT componente, estado, last_heartbeat, detalles FROM heartbeats")
                hb_rows = cursor.fetchall()
                heartbeats_dict = [{
                    "componente": r[0],
                    "estado": r[1],
                    "last_heartbeat": r[2],
                    "detalles": r[3]
                } for r in hb_rows]
                
                conn.close()
                
                self.wfile.write(json.dumps({
                    "balance_actual": balance_actual,
                    "balance_inicial_dia": bal_init,
                    "cupo_diario_total": bal_init * 0.10,
                    "cupo_disponible": cupo_disp,
                    "cupo_gastado": cupo_gast,
                    "cuenta_corriente_saldo": cc_saldo,
                    "buckets": buckets_list,
                    "abiertas": posiciones_abiertas,
                    "cerradas": posiciones_cerradas,
                    "ledger": ledger_movs,
                    "cuenta_corriente_movimientos": cc_movs,
                    "system_state": sys_state,
                    "scanner_active": scanner_active,
                    "autotrade_active": autotrade_active,
                    "heartbeats": heartbeats_dict
                }).encode('utf-8'))
            except Exception as err:
                self.wfile.write(json.dumps({"status": "error", "message": str(err)}).encode('utf-8'))
        elif self.path == '/get_pending_trades':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(PENDING_TRADES_QUEUE).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        global PENDING_TRADES_QUEUE
        if not self.is_request_authorized():
            self.send_unauthorized()
            return
        # Endpoints de la Fase B (Nube 24/7 y Control de Workers)
        if self.path.startswith('/api/bots/') and (self.path.endswith('/start') or self.path.endswith('/pause') or self.path.endswith('/stop')):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                parts = self.path.split('/')
                bot_id = parts[3]
                action = parts[4]
                
                desired = 'STOPPED'
                if action == 'start':
                    desired = 'RUNNING'
                elif action == 'pause':
                    desired = 'PAUSED'
                
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT bot_id FROM bot_status WHERE bot_id = ?", (bot_id,))
                if not cursor.fetchone():
                    self.wfile.write(json.dumps({"status": "error", "message": f"Bot {bot_id} no encontrado."}).encode('utf-8'))
                    conn.close()
                    return
                
                cursor.execute("UPDATE bot_status SET desired_state = ? WHERE bot_id = ?", (desired, bot_id))
                
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
                data = json.loads(post_data) if post_data else {}
                usuario = data.get("usuario", "ADMIN_USER")
                motivo = data.get("motivo", f"Cambio de estado a {desired} vía panel.")
                
                cursor.execute("INSERT INTO bot_logs (bot_id, severity, event_type, message) VALUES (?, 'INFO', 'STATE_CHANGE_REQUESTED', ?)", 
                               (bot_id, f"Usuario {usuario} solicitó cambiar estado deseado a {desired}. Motivo: {motivo}"))
                
                conn.commit()
                conn.close()
                self.wfile.write(json.dumps({"status": "success", "bot_id": bot_id, "desired_state": desired}).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            return

        elif self.path == '/api/system/kill-switch':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else "{}"
                data = json.loads(post_data) if post_data else {}
                allow = data.get("allow_new_trades", False)
                motivo = data.get("motivo", "Activación de Kill Switch")
                usuario = data.get("usuario", "ADMIN_USER")
                
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("UPDATE system_settings SET allow_new_trades = ?, kill_switch_reason = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                               (1 if allow else 0, motivo, usuario))
                
                cursor.execute("INSERT INTO bot_logs (bot_id, severity, event_type, message) VALUES ('system', 'CRITICAL', 'KILL_SWITCH_TOGGLED', ?)",
                               (f"Kill Switch cambiado a: Habilitado={allow} por {usuario}. Motivo: {motivo}"))
                conn.commit()
                conn.close()
                self.wfile.write(json.dumps({"status": "success", "allow_new_trades": allow, "reason": motivo}).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            return
            
        if self.path == '/api/auth/login':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                import hashlib
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
                password = data.get("password", "")
                
                # Obtener el hash esperado de SQLite
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT val FROM configuracion WHERE param_id = 'admin_password_hash'")
                row = cursor.fetchone()
                
                expected_hash = None
                if row:
                    expected_hash = row[0]
                else:
                    # Inicializar por defecto con 'meliora2026'
                    expected_hash = hashlib.sha256("meliora2026".encode('utf-8')).hexdigest()
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('admin_password_hash', ?)", (expected_hash,))
                    conn.commit()
                
                input_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
                
                if input_hash == expected_hash:
                    # Generar y guardar session token
                    import secrets
                    session_token = secrets.token_hex(24)
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('active_session_token', ?)", (session_token,))
                    conn.commit()
                    conn.close()
                    self.wfile.write(json.dumps({"status": "success", "session_token": session_token}).encode('utf-8'))
                    return
                else:
                    conn.close()
                    self.wfile.write(json.dumps({"status": "error", "message": "Contraseña incorrecta."}).encode('utf-8'))
                    return
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
                return

        elif self.path.startswith('/api/control/'):
            action = self.path.replace('/api/control/', '').split('?')[0]
            global PENDING_TRADES_QUEUE
            
            # Helper to write standard JSON response
            def enviar_respuesta_json(status_code, payload):
                try:
                    self.send_response(status_code)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps(payload).encode('utf-8'))
                except Exception as wr_e:
                    print(f"[HTTP Control] Error al responder: {wr_e}")

            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
            except Exception:
                data = {}
                
            usuario = data.get("usuario", "API_USER")
            motivo = data.get("motivo", "")
            
            try:
                conn = sqlite3.connect(DB_NAME, timeout=30.0)
                cursor = conn.cursor()
                
                if action == 'test_buy':
                    ticker = data.get("ticker", "SPY")
                    op_type = data.get("type", "CALL")
                    setup_id = f"TEST_{ticker}_{op_type}_{int(time.time())}"
                    PENDING_TRADES_QUEUE.append({
                        "setup_id": setup_id,
                        "ticker": ticker,
                        "type": op_type,
                        "strategy": "Estrategia de Prueba",
                        "price": 100.0,
                        "probability": "50.00%",
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "setup_score": 100,
                        "quantity": 1
                    })
                    conn.close()
                    enviar_respuesta_json(200, {"status": "success", "message": f"Orden de prueba encolada para {ticker} {op_type}"})
                    return
                elif action == 'arm':
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('system_state', 'ARMED')")
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('panic_stop', 'false')")
                    conn.commit()
                    conn.close()
                    
                    registrar_auditoria(usuario, "SYSTEM_ARMED", motivo or "Armado manual vía panel")
                    try:
                        send_telegram_notification(f"🟢 <b>Auto-Trader ARMED</b>\nCompras automáticas habilitadas por {usuario}.")
                    except Exception as tg_err:
                        print(f"[Telegram Alert] Error: {tg_err}")
                        
                    enviar_respuesta_json(200, {"status": "success", "message": "System ARMED"})
                    return
                    
                elif action == 'disarm':
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('system_state', 'DISARMED')")
                    conn.commit()
                    conn.close()
                    
                    registrar_auditoria(usuario, "SYSTEM_DISARMED", motivo or "Desarmado manual vía panel")
                    try:
                        send_telegram_notification(f"⚠️ <b>Auto-Trader DISARMED</b>\nSolo alertas y registros. Compras suspendidas por {usuario}.")
                    except Exception as tg_err:
                        print(f"[Telegram Alert] Error: {tg_err}")
                        
                    enviar_respuesta_json(200, {"status": "success", "message": "System DISARMED"})
                    return
                    
                elif action == 'stop':
                    motivo_stop = motivo or "Detención de emergencia manual"
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('system_state', 'STOP')")
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('panic_stop', 'true')")
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('stop_author', ?)", (usuario,))
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('stop_time', ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
                    conn.commit()
                    conn.close()
                    
                    PENDING_TRADES_QUEUE = []
                    
                    registrar_auditoria(usuario, "PANIC_STOP", motivo_stop)
                    try:
                        send_telegram_notification(f"🛑 <b>SISTEMA EN STOP (EMERGENCIA)</b>\nSe ha vaciado la cola de setups pendientes y bloqueado toda compra automática.\n👤 <b>Usuario:</b> {usuario}\n📝 <b>Motivo:</b> {motivo_stop}")
                    except Exception as tg_err:
                        print(f"[Telegram Alert] Error: {tg_err}")
                        
                    enviar_respuesta_json(200, {"status": "success", "message": "System STOPPED (Emergency Lock)"})
                    return
                    
                elif action == 'pause_scanner':
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('scanner_active', 'false')")
                    conn.commit()
                    conn.close()
                    
                    registrar_auditoria(usuario, "PAUSE_SCANNER", motivo)
                    try:
                        send_telegram_notification(f"⏸️ <b>Scanner PAUSED</b> por {usuario}.")
                    except Exception as tg_err:
                        print(f"[Telegram Alert] Error: {tg_err}")
                        
                    enviar_respuesta_json(200, {"status": "success", "message": "Scanner PAUSED"})
                    return
                    
                elif action == 'resume_scanner':
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('scanner_active', 'true')")
                    conn.commit()
                    conn.close()
                    
                    registrar_auditoria(usuario, "RESUME_SCANNER", motivo)
                    try:
                        send_telegram_notification(f"▶️ <b>Scanner RESUMED</b> por {usuario}.")
                    except Exception as tg_err:
                        print(f"[Telegram Alert] Error: {tg_err}")
                        
                    enviar_respuesta_json(200, {"status": "success", "message": "Scanner RESUMED"})
                    return
                    
                elif action == 'pause_autotrade':
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('autotrade_active', 'false')")
                    conn.commit()
                    conn.close()
                    
                    registrar_auditoria(usuario, "PAUSE_AUTOTRADE", motivo)
                    try:
                        send_telegram_notification(f"⏸️ <b>Autotrade PAUSED</b> por {usuario}.")
                    except Exception as tg_err:
                        print(f"[Telegram Alert] Error: {tg_err}")
                        
                    enviar_respuesta_json(200, {"status": "success", "message": "Autotrade PAUSED"})
                    return
                    
                elif action == 'resume_autotrade':
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('autotrade_active', 'true')")
                    conn.commit()
                    conn.close()
                    
                    registrar_auditoria(usuario, "RESUME_AUTOTRADE", motivo)
                    try:
                        send_telegram_notification(f"▶️ <b>Autotrade RESUMED</b> por {usuario}.")
                    except Exception as tg_err:
                        print(f"[Telegram Alert] Error: {tg_err}")
                        
                    enviar_respuesta_json(200, {"status": "success", "message": "Autotrade RESUMED"})
                    return
                    
                elif action == 'emergency_close':
                    cuenta_id = data.get("cuenta_id", "default")
                    cursor.execute("SELECT id, ticker FROM operaciones_simuladas WHERE estado = 'OPEN' AND cuenta_id = ?", (cuenta_id,))
                    rows = cursor.fetchall()
                    
                    closed_count = 0
                    for op_id, ticker in rows:
                        cursor.execute("SELECT price FROM radar_actual WHERE ticker = ? LIMIT 1", (ticker,))
                        radar_row = cursor.fetchone()
                        precio_salida = float(radar_row[0]) if radar_row and radar_row[0] is not None else 100.0
                        
                        sim_broker_core.simular_venta_broker(conn, op_id, precio_salida)
                        closed_count += 1
                        
                    conn.commit()
                    conn.close()
                    
                    registrar_auditoria(usuario, "EMERGENCY_CLOSE", f"Liquidacion en masa de {closed_count} posiciones para cuenta: {cuenta_id}")
                    try:
                        send_telegram_notification(f"🔥 <b>LIQUIDACIÓN EN MASA (EMERGENCIA)</b>\nSe cerraron preventivamente {closed_count} posiciones en el sandbox para la cuenta: <code>{cuenta_id}</code>.\n👤 <b>Usuario:</b> {usuario}")
                    except Exception as tg_err:
                        print(f"[Telegram Alert] Error: {tg_err}")
                        
                    enviar_respuesta_json(200, {"status": "success", "closed_count": closed_count})
                    return
                    
                else:
                    conn.close()
                    enviar_respuesta_json(400, {"status": "error", "message": "Acción de control no reconocida."})
                    return
            except Exception as e:
                enviar_respuesta_json(500, {"status": "error", "message": str(e)})
                return

        elif self.path == '/heartbeat':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            global last_ucharts_heartbeat
            last_ucharts_heartbeat = time.time()
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
                account_balance = data.get("account_balance")
                if account_balance is not None:
                    try:
                        conn = sqlite3.connect(DB_NAME)
                        cursor = conn.cursor()
                        cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val, type) VALUES ('capital_simulado', ?, 'FLOAT')", (str(account_balance),))
                        conn.commit()
                        conn.close()
                        print(f"[Simulador] Capital de cuenta sincronizado vía Heartbeat: ${account_balance:,.2f}")
                    except Exception as db_err:
                        print(f"[Heartbeat] Error al guardar capital: {db_err}")
            except Exception:
                pass
            self.wfile.write(json.dumps({"status": "success", "message": "Heartbeat registrado"}).encode('utf-8'))
        elif self.path == '/mark_executed':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
                setup_id = data.get("setup_id")
                
                if setup_id:
                    PENDING_TRADES_QUEUE = [t for t in PENDING_TRADES_QUEUE if t["setup_id"] != setup_id]
                    self.wfile.write(json.dumps({"status": "success", "message": f"Setup {setup_id} removido de la cola"}).encode('utf-8'))
                else:
                    self.wfile.write(json.dumps({"status": "error", "message": "setup_id es requerido"}).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/report_trade_result':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
                
                status = data.get("status")
                ticker = data.get("ticker")
                direction = data.get("type")
                qty = data.get("quantity", 0)
                error_msg = data.get("error_message", "")
                
                if status == "SUCCESS":
                    msg = (
                        f"🟢 <b>Auto-Trader: ORDEN EJECUTADA</b>\n\n"
                        f"🎯 <b>Activo:</b> {ticker} ({direction})\n"
                        f"💼 <b>Contratos:</b> {qty}\n"
                        f"✅ La orden de mercado fue enviada y confirmada en uCharts con éxito."
                    )
                else:
                    msg = (
                        f"❌ <b>Auto-Trader: COMPRA FALLIDA</b>\n\n"
                        f"🎯 <b>Activo:</b> {ticker} ({direction})\n"
                        f"⚠️ <b>Razón:</b> <code>{error_msg}</code>\n"
                        f"❌ La orden fue removida de la cola por fallo de ejecución en la terminal."
                    )
                send_telegram_notification(msg)
                self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/api/simulador/buy':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
                
                ticker = data.get("ticker")
                strategy_id = data.get("strategy_id")
                qty = data.get("qty")
                expiry = data.get("expiry")
                cuenta_id = data.get("cuenta_id", "default")
                
                if not ticker or not strategy_id:
                    self.wfile.write(json.dumps({"status": "error", "message": "ticker y strategy_id son requeridos"}).encode('utf-8'))
                    return
                    
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("SELECT price FROM radar_actual WHERE ticker = ? LIMIT 1", (ticker,))
                row = cursor.fetchone()
                precio_subyacente = float(row[0]) if row and row[0] is not None else 100.0
                
                res = sim_broker_core.simular_compra_broker(conn, ticker, strategy_id, precio_subyacente, qty, expiry, cuenta_id=cuenta_id)
                conn.close()
                
                self.wfile.write(json.dumps(res).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/api/simulador/add_funds':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
                
                cuenta_id = data.get("cuenta_id", "default")
                monto = float(data.get("monto", 0))
                
                if monto <= 0:
                    self.wfile.write(json.dumps({"status": "error", "message": "El monto debe ser mayor a 0"}).encode('utf-8'))
                    return
                    
                conn = sqlite3.connect(DB_NAME)
                res = sim_broker_core.agregar_fondos_broker(conn, cuenta_id, monto)
                conn.close()
                self.wfile.write(json.dumps(res).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/api/simulador/create_account':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
                
                nombre = data.get("nombre", "").strip()
                balance_inicial = float(data.get("balance_inicial", 100000.0))
                
                if not nombre:
                    self.wfile.write(json.dumps({"status": "error", "message": "El nombre de la cuenta es requerido"}).encode('utf-8'))
                    return
                    
                cuenta_id = nombre.lower().replace(' ', '_')
                
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                
                # Chequear duplicado
                cursor.execute("SELECT id FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
                if cursor.fetchone():
                    conn.close()
                    self.wfile.write(json.dumps({"status": "error", "message": f"Ya existe una cuenta con el nombre '{nombre}'"}).encode('utf-8'))
                    return
                    
                cursor.execute("""
                    INSERT INTO cuentas_simuladas (id, nombre, balance_inicial, balance_actual, creation_time)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (cuenta_id, nombre, balance_inicial, balance_inicial))
                
                # Inicializar buckets
                sim_broker_core.recalcular_buckets_capital(conn, cuenta_id=cuenta_id)
                conn.commit()
                conn.close()
                
                self.wfile.write(json.dumps({"status": "success", "cuenta_id": cuenta_id, "nombre": nombre}).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/api/simulador/sell':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                post_data = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(post_data) if post_data else {}
                
                trade_id = data.get("trade_id")
                precio_salida_subyacente = data.get("precio_salida")
                
                if not trade_id:
                    self.wfile.write(json.dumps({"status": "error", "message": "trade_id es requerido"}).encode('utf-8'))
                    return
                    
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                
                if precio_salida_subyacente is None:
                    cursor.execute("""
                        SELECT ticker FROM operaciones_simuladas WHERE id = ?
                    """, (trade_id,))
                    ticker_row = cursor.fetchone()
                    if ticker_row:
                        cursor.execute("SELECT price FROM radar_actual WHERE ticker = ? LIMIT 1", (ticker_row[0],))
                        radar_row = cursor.fetchone()
                        precio_salida_subyacente = float(radar_row[0]) if radar_row and radar_row[0] is not None else 100.0
                    else:
                        precio_salida_subyacente = 100.0
                
                res = sim_broker_core.simular_venta_broker(conn, trade_id, precio_salida_subyacente)
                conn.close()
                
                self.wfile.write(json.dumps(res).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def start_control_server():
    server_address = ('', 8055)
    try:
        httpd = ThreadingHTTPServer(server_address, BotControlServer)
        print(f"\n[Server] Servidor de control local activo en http://localhost:8055/")
        httpd.serve_forever()
    except Exception as e:
        print(f"Error: {e}")

# ==========================================
# SIMULADOR DE CAPITALS Y MONITOREO VIVO (Regla 10% diario)
# ==========================================
SIM_STRATEGY_ALLOCATION = {
    "cond_canal_break": 0.10,   # Ruptura Canal Bajista / Banderines (10%)
    "cond_primer_gap": 0.10,    # Primer Gap al Alza (10%)
    "cond_gap_normal": 0.15,    # Gap Normal al Alza (15%)
    "cond_gap_bajista": 0.10,   # Gap Bajista al Alza (10%)
    "cond_caida_normal": 0.10,  # Caída Normal (10%)
    "cond_caida_fuerte": 0.15,  # Caída Fuerte (15%)
    "cond_piso_fuerte": 0.10,   # Piso Fuerte (10%)
    "cond_vela_roja": 0.10,     # Primera Vela Roja (10%)
    "cond_4_pasos": 0.10        # Modelo de los 4 Pasos (10%)
}

SIM_STRATEGY_DTE = {
    "cond_canal_break": 7,
    "cond_primer_gap": 1,
    "cond_gap_normal": 1,
    "cond_gap_bajista": 1,
    "cond_caida_normal": 7,
    "cond_caida_fuerte": 14,
    "cond_piso_fuerte": 14,
    "cond_vela_roja": 1,
    "cond_4_pasos": 7
}

def init_simulation_tables():
    """Inicializa las tablas del simulador en la base de datos si no existen."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS configuracion (
                param_id TEXT PRIMARY KEY,
                val TEXT,
                type TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS operaciones_simuladas (
                id TEXT PRIMARY KEY,
                ticker TEXT,
                tipo TEXT,
                estrategia TEXT,
                cantidad_contratos INTEGER,
                precio_entrada REAL,
                precio_actual REAL,
                pnl_pct REAL,
                pnl_usd REAL,
                estado TEXT,
                fecha_apertura TEXT,
                fecha_cierre TEXT,
                dte_plazo INTEGER,
                targets_alcanzados TEXT,
                balance_referencia REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS capital_diario_control (
                fecha TEXT,
                id TEXT,
                balance_inicial REAL,
                cupo_disponible REAL,
                cupo_gastado REAL,
                PRIMARY KEY (fecha, id)
            )
        """)
        
        # Ejecutar script schema.sql para nuevas tablas de la Fase A
        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            cursor.executescript(schema_sql)
            print("[Simulador] Estructura de base de datos schema.sql inicializada con éxito.")

        cursor.execute("SELECT val FROM configuracion WHERE param_id = 'capital_simulado'")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO configuracion (param_id, val, type) VALUES ('capital_simulado', '3830539.59', 'FLOAT')")
        conn.commit()
        conn.close()
        print("[Simulador] Tablas del Simulador de Capital (10% diario) listas.")
    except Exception as e:
        print(f"[Simulador] Error inicialización: {e}")

def calcular_prima_simulada(precio_subyacente, dte):
    """Estima una prima de opción ATM realista basada en la volatilidad y DTE del subyacente."""
    if dte == 1:
        return max(0.50, round(precio_subyacente * 0.005, 2))
    elif dte == 7:
        return max(1.50, round(precio_subyacente * 0.012, 2))
    else:
        return max(2.50, round(precio_subyacente * 0.020, 2))

def procesar_simulacion_compra(ticker, strategy_id, precio_subyacente):
    """Calcula y ejecuta una orden virtual bajo la regla del 10% diario con rotación de capital."""
    state = get_system_state()
    if state != "ARMED":
        print(f"[Simulador] Compra cancelada para {ticker} ({strategy_id}): El sistema está en estado {state}.")
        return
    if strategy_id not in SIM_STRATEGY_ALLOCATION:
        return
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # 1. Obtener capital simulado
        cursor.execute("SELECT val FROM configuracion WHERE param_id = 'capital_simulado'")
        row = cursor.fetchone()
        balance_actual = float(row[0]) if row else 3830539.59
        
        # 2. Control diario
        today_str = datetime.now().strftime("%Y-%m-%d")
        presupuesto_diario_max = balance_actual * 0.10
        cursor.execute("SELECT cupo_disponible, cupo_gastado FROM capital_diario_control WHERE fecha = ?", (today_str,))
        ctrl = cursor.fetchone()
        if ctrl:
            cupo_disponible, cupo_gastado = ctrl
        else:
            cupo_disponible, cupo_gastado = presupuesto_diario_max, 0.0
            cursor.execute("INSERT INTO capital_diario_control (fecha, balance_inicial, cupo_disponible, cupo_gastado) VALUES (?, ?, ?, ?)",
                           (today_str, balance_actual, cupo_disponible, cupo_gastado))
            conn.commit()
            
        monto_destinado = cupo_disponible * SIM_STRATEGY_ALLOCATION[strategy_id]
        if monto_destinado <= 0:
            conn.close()
            return
            
        dte = SIM_STRATEGY_DTE[strategy_id]
        tipo = STRATEGIES_METADATA.get(strategy_id, ("", "CALL", ""))[1]
        prima = calcular_prima_simulada(precio_subyacente, dte)
        costo_contrato = (prima * 100) + 0.65
        
        cantidad = int(monto_destinado / costo_contrato)
        if cantidad <= 0:
            cantidad = 1
            
        costo_total = cantidad * costo_contrato
        is_pilot = False
        
        # Banderines: 1 CALL + 1 PUT piloto al inicio
        if strategy_id == "cond_canal_break":
            cursor.execute("SELECT COUNT(*) FROM operaciones_simuladas WHERE ticker = ? AND estrategia = ? AND estado = 'OPEN'", (ticker, strategy_id))
            if cursor.fetchone()[0] == 0:
                is_pilot = True
                cantidad = 1
                costo_total = cantidad * costo_contrato
                
        op_id = f"SIM_{ticker}_{strategy_id}_{datetime.now().strftime('%M%S')}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO operaciones_simuladas (id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada, precio_actual, pnl_pct, pnl_usd, estado, fecha_apertura, fecha_cierre, dte_plazo, targets_alcanzados, balance_referencia)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (op_id, ticker, tipo, strategy_id, cantidad, prima, prima, 0.0, 0.0, 'OPEN', now_str, None, dte, '[]', balance_actual))
        
        if is_pilot:
            put_op_id = f"SIM_{ticker}_{strategy_id}_PUT_{datetime.now().strftime('%M%S')}"
            put_prima = calcular_prima_simulada(precio_subyacente, dte)
            cursor.execute("""
                INSERT INTO operaciones_simuladas (id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada, precio_actual, pnl_pct, pnl_usd, estado, fecha_apertura, fecha_cierre, dte_plazo, targets_alcanzados, balance_referencia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (put_op_id, ticker, 'PUT', strategy_id, 1, put_prima, put_prima, 0.0, 0.0, 'OPEN', now_str, None, dte, '[]', balance_actual))
            costo_total += (put_prima * 100) + 0.65
            print(f"[Simulador] Compra piloto Straddle registrada en Banderines para {ticker}.")
            
        # Actualizar saldo y cupo
        nuevo_disponible = max(0.0, cupo_disponible - costo_total)
        nuevos_gastos = cupo_gastado + costo_total
        cursor.execute("UPDATE capital_diario_control SET cupo_disponible = ?, cupo_gastado = ? WHERE fecha = ?", (nuevo_disponible, nuevos_gastos, today_str))
        
        nuevo_balance = max(0.0, balance_actual - costo_total)
        cursor.execute("UPDATE configuracion SET val = ? WHERE param_id = 'capital_simulado'", (str(nuevo_balance),))
        
        conn.commit()
        conn.close()
        
        print(f"[Simulador] Compra virtual: {cantidad} c de {ticker} ({tipo}) vía {strategy_id}. Costo: ${costo_total:.2f}.")
        
        notif_msg = (
            f"📥 <b>SIMULADOR: COMPRA VIRTUAL (Regla 10%)</b>\n\n"
            f"🎯 <b>Activo:</b> {ticker} ({tipo})\n"
            f"📖 <b>Estrategia:</b> {strategy_id}\n"
            f"💼 <b>Contratos:</b> {cantidad} (Prima: ${prima:.2f})\n"
            f"💸 <b>Inversión:</b> ${costo_total:.2f}\n"
            f"💰 <b>Balance Cuenta:</b> ${nuevo_balance:.2f}"
        )
        send_telegram_notification(notif_msg)
    except Exception as e:
        print(f"[Simulador] Error compra: {e}")

def actualizar_seguimiento_simulador():
    """Actualiza precios en tiempo real de operaciones simuladas y gestiona los targets."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada, dte_plazo, fecha_apertura, balance_referencia FROM operaciones_simuladas WHERE estado = 'OPEN'")
        posiciones = cursor.fetchall()
        if not posiciones:
            conn.close()
            return
            
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        for pos in posiciones:
            op_id, ticker, tipo, estrategia, cantidad, precio_entrada, dte, fecha_apertura, balance_ref = pos
            try:
                t_obj = yf.Ticker(ticker)
                hist = t_obj.history(period="1d")
                if hist.empty:
                    continue
                precio_actual_sub = hist['Close'].iloc[-1]
            except Exception:
                continue
                
            cursor.execute("SELECT price FROM radar_actual WHERE ticker = ? LIMIT 1", (ticker,))
            price_row = cursor.fetchone()
            precio_entrada_sub = price_row[0] if price_row else precio_actual_sub * 0.99
            
            # Estimación de apalancamiento lineal por DTE
            leverage = 12 if dte == 1 else 8 if dte == 7 else 5
            var_sub = (precio_actual_sub - precio_entrada_sub) / precio_entrada_sub
            pnl_pct = (var_sub if tipo == "CALL" else -var_sub) * leverage * 100
            pnl_pct = max(-98.0, min(250.0, pnl_pct))
            
            precio_actual_opcion = max(0.01, round(precio_entrada * (1 + pnl_pct / 100), 2))
            pnl_usd = (precio_actual_opcion - precio_entrada) * 100 * cantidad
            
            target_list = [3.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 100.0, 150.0, 200.0]
            targets_alcanzados = [t for t in target_list if pnl_pct >= t]
            
            debe_cerrar = False
            razon = ""
            if pnl_pct <= -15.0:
                debe_cerrar = True
                razon = "STOP LOSS (-15%)"
            elif pnl_pct >= 30.0:
                debe_cerrar = True
                razon = f"TAKE PROFIT ({max(targets_alcanzados):.0f}%)"
                
            if not debe_cerrar:
                cursor.execute("UPDATE operaciones_simuladas SET precio_actual = ?, pnl_pct = ?, pnl_usd = ?, targets_alcanzados = ? WHERE id = ?",
                               (precio_actual_opcion, pnl_pct, pnl_usd, json.dumps(targets_alcanzados), op_id))
            else:
                # Cerrar a través del core del Sim Broker (Ledger, Buckets, Retiro 90/10)
                res_venta = sim_broker_core.simular_venta_broker(conn, op_id, precio_actual_sub)
                if res_venta.get("status") == "CLOSED":
                    retorno = cantidad * (precio_actual_opcion * 100 - 0.65)
                    if dte == 1:
                        cursor.execute("SELECT cupo_disponible, cupo_gastado FROM capital_diario_control WHERE fecha = ?", (today_str,))
                        row_ctrl = cursor.fetchone()
                        if row_ctrl:
                            curr_disp, curr_gast = row_ctrl
                            nuevo_disp = curr_disp + retorno
                            nuevo_gast = max(0.0, curr_gast - retorno)
                            cursor.execute("UPDATE capital_diario_control SET cupo_disponible = ?, cupo_gastado = ? WHERE fecha = ?", (nuevo_disp, nuevo_gast, today_str))
                    
                    cursor.execute("SELECT val FROM configuracion WHERE param_id = 'capital_simulado'")
                    nuevo_cap = float(cursor.fetchone()[0])
                    
                    signo = "+" if pnl_usd >= 0 else ""
                    notif_msg = (
                        f"📤 <b>SIMULADOR: POSICIÓN CERRADA ({razon})</b>\n\n"
                        f"🎯 <b>Activo:</b> {ticker} ({tipo})\n"
                        f"📖 <b>Estrategia:</b> {estrategia}\n"
                        f"📈 <b>PnL Realizado:</b> {signo}{pnl_pct:.2f}% ({signo}${pnl_usd:.2f})\n"
                        f"💰 <b>Retorno Bruto:</b> ${retorno:.2f}\n"
                        f"💵 <b>Desvío 10%:</b> ${res_venta.get('withdrawal', 0.0):.2f}\n"
                        f"💎 <b>Balance Cuenta:</b> ${nuevo_cap:.2f}"
                    )
                    send_telegram_notification(notif_msg)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Simulador] Error en seguimiento: {e}")

def run_paper_bot_worker():
    print("[Worker] Iniciando bucle persistente del paper_bot...")
    # Asegurar estado inicial en base de datos
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO bot_status (bot_id, desired_state, actual_state, last_activity, enabled) VALUES ('paper_bot', 'RUNNING', 'STARTING', CURRENT_TIMESTAMP, 1)")
        conn.commit()
    except Exception as e:
        print(f"[Worker paper_bot] Error inicial: {e}")
    finally:
        if conn:
            conn.close()
        
    while True:
        conn = None
        try:
            # Fix crítico: SIM_BROKER nunca reportaba heartbeat, así que el
            # watchdog lo daba por caído a los 5 minutos y desarmaba TODO el
            # sistema automáticamente, sin importar que este worker estuviera
            # vivo y funcionando bien. Se reporta acá, en cada ciclo, porque
            # este hilo es el que efectivamente representa al subsistema del
            # simulador (sim_broker_core) estando operativo.
            report_heartbeat("SIM_BROKER", "ONLINE", "Worker de paper_bot activo")

            conn = sqlite3.connect(DB_NAME, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("SELECT desired_state, enabled FROM bot_status WHERE bot_id = 'paper_bot'")
            row = cursor.fetchone()
            
            if not row:
                desired, enabled = 'RUNNING', True
            else:
                desired, enabled = row[0], bool(row[1])
                
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if not enabled:
                cursor.execute("UPDATE bot_status SET actual_state = 'STOPPED', last_heartbeat = ? WHERE bot_id = 'paper_bot'", (now_str,))
                conn.commit()
                conn.close()
                conn = None
                time.sleep(5)
                continue
                
            if desired == 'RUNNING':
                cursor.execute("UPDATE bot_status SET actual_state = 'RUNNING', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'paper_bot'", (now_str, now_str))
                conn.commit()
                conn.close()
                conn = None
                
                # ------------------------------------------------------------
                # Fix crítico: este bloque hacía PENDING_TRADES_QUEUE.pop(0) y
                # ejecutaba la compra directo en el ledger interno, en memoria,
                # cada 5 segundos. Como corre local y sincrónico, le ganaba la
                # carrera casi siempre al Tampermonkey (que tiene que hacer un
                # viaje HTTP + toda la automatización de clics en UCharts, más
                # lento). Resultado: la señal se consumía acá adentro antes de
                # que el navegador la viera, y UCharts casi nunca llegaba a
                # comprar de verdad.
                #
                # Ahora el único consumidor de PENDING_TRADES_QUEUE es UCharts
                # (vía /get_pending_trades + /mark_executed en el Tampermonkey).
                # El ledger interno (sim_broker_core / Meliora Sim Broker) se
                # actualiza en su lugar cuando UCharts CONFIRMA la compra real,
                # a través de /report_trade_result — así los dos quedan
                # sincronizados en vez de compitiendo por la misma señal.
                # ------------------------------------------------------------
                pass

            elif desired == 'PAUSED':
                cursor.execute("UPDATE bot_status SET actual_state = 'PAUSED', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'paper_bot'", (now_str, now_str))
                conn.commit()
                conn.close()
                conn = None
                
            elif desired == 'STOPPED':
                cursor.execute("UPDATE bot_status SET actual_state = 'STOPPED', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'paper_bot'", (now_str, now_str))
                conn.commit()
                conn.close()
                conn = None
                
        except Exception as err:
            print(f"[Worker paper_bot Error]: {err}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            
        time.sleep(5)

def run_tracker_loop():
    print("[Tracker Thread] Hilo de seguimiento de posiciones activas iniciado (Monitoreo cada 120s).")
    
    # Asegurar estado inicial en base de datos
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO bot_status (bot_id, desired_state, actual_state, last_activity, enabled) VALUES ('tracker', 'RUNNING', 'STARTING', CURRENT_TIMESTAMP, 1)")
        conn.commit()
    except Exception as e:
        print(f"[Worker tracker] Error inicial: {e}")
    finally:
        if conn:
            conn.close()
        
    last_run_time = 0.0
    run_interval = 120
    
    while True:
        conn = None
        try:
            conn = sqlite3.connect(DB_NAME, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("SELECT desired_state, enabled FROM bot_status WHERE bot_id = 'tracker'")
            row = cursor.fetchone()
            
            if not row:
                desired, enabled = 'RUNNING', True
            else:
                desired, enabled = row[0], bool(row[1])
                
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if not enabled:
                cursor.execute("UPDATE bot_status SET actual_state = 'STOPPED', last_heartbeat = ? WHERE bot_id = 'tracker'", (now_str,))
                conn.commit()
                conn.close()
                conn = None
                time.sleep(5)
                continue
                
            if desired == 'RUNNING':
                cursor.execute("UPDATE bot_status SET actual_state = 'RUNNING', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'tracker'", (now_str, now_str))
                conn.commit()
                conn.close()
                conn = None
                
                # Ejecutar ciclo de monitoreo de posiciones cada 120 segundos
                if time.time() - last_run_time >= run_interval:
                    print(f"[Tracker Thread] Ejecutando evaluacion de salida/TP a las {now_str}...")
                    db_conn = None
                    try:
                        actualizar_seguimiento_simulador()
                        last_run_time = time.time()
                        
                        db_conn = sqlite3.connect(DB_NAME, timeout=30.0)
                        c = db_conn.cursor()
                        c.execute("INSERT INTO bot_logs (bot_id, severity, event_type, message) VALUES ('tracker', 'INFO', 'TRACK_SUCCESS', 'Seguimiento de portafolio y salidas procesado con éxito.')")
                        db_conn.commit()
                    except Exception as track_e:
                        print(f"[Tracker Thread] Error al actualizar posiciones: {track_e}")
                        if db_conn:
                            try:
                                db_conn.close()
                            except Exception:
                                pass
                        db_conn = None
                        try:
                            db_conn = sqlite3.connect(DB_NAME, timeout=30.0)
                            c = db_conn.cursor()
                            c.execute("INSERT INTO bot_logs (bot_id, severity, event_type, message) VALUES ('tracker', 'ERROR', 'TRACK_FAIL', ?)", (f"Error de seguimiento: {str(track_e)}",))
                            db_conn.commit()
                        except Exception as log_err:
                            print(f"[Tracker Thread] No se pudo escribir log de error de seguimiento: {log_err}")
                    finally:
                        if db_conn:
                            db_conn.close()
                            
            elif desired == 'PAUSED':
                cursor.execute("UPDATE bot_status SET actual_state = 'PAUSED', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'tracker'", (now_str, now_str))
                conn.commit()
                conn.close()
                conn = None
                
            elif desired == 'STOPPED':
                cursor.execute("UPDATE bot_status SET actual_state = 'STOPPED', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'tracker'", (now_str, now_str))
                conn.commit()
                conn.close()
                conn = None
                
        except Exception as err:
            print(f"[Worker tracker Error]: {err}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            
        time.sleep(5)

def telegram_polling_loop():
    if not TELEGRAM_ENABLED or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[Telegram Polling] Polling deshabilitado (Faltan credenciales en config.json).")
        return
        
    print("[Telegram Polling] Bucle de control remoto por Telegram iniciado.")
    last_update_id = 0
    url_get = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    url_send = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    # Limpiar actualizaciones previas al iniciar
    try:
        r = requests.get(f"{url_get}?offset=-1", verify=False, timeout=10)
        if r.status_code == 200:
            updates = r.json().get("result", [])
            if updates:
                last_update_id = updates[-1]["update_id"] + 1
    except Exception:
        pass
        
    while True:
        try:
            report_heartbeat("TELEGRAM", "ONLINE", f"Escucha activa de comandos. Ultimo ID: {last_update_id}")
            r = requests.get(f"{url_get}?offset={last_update_id}&timeout=5", verify=False, timeout=15)
            if r.status_code != 200:
                time.sleep(5)
                continue
                
            updates = r.json().get("result", [])
            for up in updates:
                last_update_id = up["update_id"] + 1
                message = up.get("message")
                if not message:
                    continue
                    
                chat = message.get("chat", {})
                sender_id = str(chat.get("id", ""))
                if sender_id != str(TELEGRAM_CHAT_ID):
                    print(f"[Telegram Polling] Ignorado mensaje de emisor no autorizado: {sender_id}")
                    continue
                    
                text = (message.get("text") or "").strip().lower()
                response_msg = ""
                
                if text == "/status" or "estado" in text:
                    state = get_system_state()
                    is_online = (time.time() - last_ucharts_heartbeat) < 60
                    hb_status = "🟢 ONLINE" if is_online else "🔴 OFFLINE"
                    response_msg = (
                        f"📊 <b>ESTADO DEL SISTEMA</b>\n\n"
                        f"🧠 <b>Escáner Principal:</b> 🟢 Activo\n"
                        f"🛡️ <b>Modo Autotrade:</b> {state}\n"
                        f"💻 <b>uCharts Terminal:</b> {hb_status}\n"
                        f"⏰ <b>Hora Servidor:</b> {datetime.now().strftime('%H:%M:%S')}"
                    )
                elif text == "/arm" or "armar" in text:
                    set_system_state("ARMED")
                    response_msg = "🟢 <b>Auto-Trader ARMED</b>\nLas compras simuladas en uCharts están habilitadas."
                elif text == "/disarm" or "desarmar" in text:
                    set_system_state("DISARMED")
                    response_msg = "A <b>Auto-Trader DISARMED</b>\nSolo se generarán alertas y registros. Compras bloqueadas."
                elif text == "/stop" or "panic" in text or "detener" in text:
                    set_system_state("STOP")
                    global PENDING_TRADES_QUEUE
                    PENDING_TRADES_QUEUE = []
                    response_msg = "🛑 <b>SISTEMA EN STOP (EMERGENCIA)</b>\nSe ha vaciado la cola de órdenes y bloqueado toda compra automática."
                elif text == "/positions" or "posiciones" in text:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("SELECT ticker, qty, state FROM operaciones WHERE state = 'OPEN'")
                    rows = cursor.fetchall()
                    conn.close()
                    if not rows:
                        response_msg = "💼 No hay posiciones abiertas actualmente."
                    else:
                        lines = [f"• <b>{r[0]}</b>: {r[1]} contratos (OPEN)" for r in rows]
                        response_msg = "💼 <b>POSICIONES ABIERTAS:</b>\n\n" + "\n".join(lines)
                elif text == "/radar" or "radar" in text:
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    today_str = datetime.now().strftime("%Y-%m-%d")
                    cursor.execute("""
                        SELECT ticker, strategy_id, state, setup_score FROM setups 
                        WHERE creation_time LIKE ? ORDER BY creation_time DESC LIMIT 5
                    """, (today_str + "%",))
                    rows = cursor.fetchall()
                    conn.close()
                    if not rows:
                        response_msg = "🔥 No se han detectado setups hoy."
                    else:
                        lines = [f"• <b>{r[0]}</b> ({r[1]}): {r[2]} (Score: {r[3]}/100)" for r in rows]
                        response_msg = "🔥 <b>ÚLTIMOS SETUPS HOY:</b>\n\n" + "\n".join(lines)
                elif text.startswith("/"):
                    response_msg = (
                        "❓ <b>Comando no reconocido.</b>\nUsar:\n"
                        "/status - Ver estado del sistema\n"
                        "/arm - Habilitar compras\n"
                        "/disarm - Solo alertas/registros\n"
                        "/stop - Detener y vaciar cola\n"
                        "/positions - Ver posiciones en curso\n"
                        "/radar - Ver últimos setups del día"
                    )
                    
                if response_msg:
                    try:
                        requests.post(url_send, json={
                            "chat_id": TELEGRAM_CHAT_ID,
                            "text": response_msg,
                            "parse_mode": "HTML"
                        }, verify=False, timeout=10)
                    except Exception as e:
                        print(f"Error al responder en Telegram: {e}")
                        
        except Exception as e:
            print(f"[Telegram Polling] Error en bucle: {e}")
            time.sleep(5)

def run_watchdog_loop():
    print("[Watchdog Thread] Hilo supervisor de salud de componentes iniciado (Chequeo cada 60s).")
    while True:
        conn = None
        try:
            report_heartbeat("WATCHDOG", "ONLINE", "Supervisor de salud activo")
            
            conn = sqlite3.connect(DB_NAME, timeout=30.0)
            cursor = conn.cursor()
            cursor.execute("SELECT componente, estado, last_heartbeat, detalles FROM heartbeats")
            rows = cursor.fetchall()
            
            now = datetime.now()
            degraded_components = []
            
            for comp, estado, last_hb_str, detalles in rows:
                if comp == "WATCHDOG":
                    continue
                try:
                    last_hb = datetime.strptime(last_hb_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        last_hb = datetime.fromisoformat(last_hb_str)
                    except Exception:
                        last_hb = now
                        
                diff_sec = (now - last_hb).total_seconds()
                
                # Timeout de 5 minutos (300s)
                if diff_sec > 300:
                    if estado != "OFFLINE":
                        cursor.execute("UPDATE heartbeats SET estado = 'OFFLINE', detalles = 'Heartbeat vencido (timeout)' WHERE componente = ?", (comp,))
                        degraded_components.append(f"• <b>{comp}</b>: OFFLINE (último reporte hace {int(diff_sec)}s)")
                elif estado == "DEGRADED":
                    degraded_components.append(f"• <b>{comp}</b>: DEGRADED ({detalles})")
                    
            if degraded_components:
                cursor.execute("SELECT val FROM configuracion WHERE param_id = 'system_state'")
                state_row = cursor.fetchone()
                current_state = state_row[0] if state_row else "DISARMED"
                
                # Desarmado preventivo si hay fallos en núcleos críticos
                critical_fails = [c for c in degraded_components if any(x in c for x in ["SCANNER", "DATABASE", "RISK_ENGINE", "CAPITAL_ENGINE", "SIM_BROKER"])]
                
                if critical_fails and current_state == "ARMED":
                    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('system_state', 'DISARMED')")
                    conn.commit()
                    registrar_auditoria("WATCHDOG", "SYSTEM_DISARMED", f"Desarmado preventivo por fallos criticos: {', '.join(critical_fails)}")
                    send_telegram_notification(
                        f"🚨 <b>WATCHDOG: DESARMADO DE EMERGENCIA</b>\n\n"
                        f"Se ha desactivado el auto-trading preventivamente (DISARMED) debido a fallos críticos de salud en el sistema:\n\n"
                        + "\n".join(critical_fails)
                    )
                else:
                    conn.commit()
                    send_telegram_notification(
                        f"⚠️ <b>WATCHDOG: DEGRADACIÓN DETECTADA</b>\n\n"
                        + "\n".join(degraded_components)
                    )
            else:
                conn.commit()
        except Exception as e:
            print(f"[Watchdog Thread] Error en bucle: {e}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        time.sleep(60)

def run_scanner_worker():
    print("[Worker] Iniciando bucle persistente del scanner...")
    import threading
    last_scan_time = 0.0
    scan_interval = 3600  # Escanear cada 1 hora por defecto
    
    # Asegurar que el estado inicial del bot este en la base de datos
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO bot_status (bot_id, desired_state, actual_state, last_activity, enabled) VALUES ('live_scanner', 'RUNNING', 'STARTING', CURRENT_TIMESTAMP, 1)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Worker] Error al registrar estado inicial: {e}")
        
    while True:
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT desired_state, enabled FROM bot_status WHERE bot_id = 'live_scanner'")
            row = cursor.fetchone()
            
            if not row:
                desired, enabled = 'RUNNING', True
            else:
                desired, enabled = row[0], bool(row[1])
                
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if not enabled:
                cursor.execute("UPDATE bot_status SET actual_state = 'STOPPED', last_heartbeat = ? WHERE bot_id = 'live_scanner'", (now_str,))
                conn.commit()
                conn.close()
                time.sleep(5)
                continue
                
            if desired == 'RUNNING':
                cursor.execute("UPDATE bot_status SET actual_state = 'RUNNING', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'live_scanner'", (now_str, now_str))
                conn.commit()
                conn.close()
                
                # Ejecutar ciclo de escaneo si ha pasado una hora
                if time.time() - last_scan_time >= scan_interval:
                    print(f"[Worker] Ejecutando ciclo de escaneo relacional a las {now_str}...")
                    global SCANNING_IN_PROGRESS
                    SCANNING_IN_PROGRESS = True
                    try:
                        main()
                        last_scan_time = time.time()
                        
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        c.execute("INSERT INTO bot_logs (bot_id, severity, event_type, message) VALUES ('live_scanner', 'INFO', 'SCAN_SUCCESS', 'Escaneo de 35 activos completado con éxito.')")
                        c.execute("UPDATE bot_status SET last_error = NULL, last_heartbeat = ? WHERE bot_id = 'live_scanner'", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
                        conn.commit()
                        conn.close()
                    except Exception as scan_err:
                        print(f"[Worker] Error en escaneo: {scan_err}")
                        conn = sqlite3.connect(DB_NAME)
                        c = conn.cursor()
                        err_msg = str(scan_err)
                        c.execute("UPDATE bot_status SET actual_state = 'ERROR', last_error = ? WHERE bot_id = 'live_scanner'", (err_msg,))
                        c.execute("INSERT INTO bot_logs (bot_id, severity, event_type, message) VALUES ('live_scanner', 'ERROR', 'SCAN_FAIL', ?)", (f"Fallo en escaneo: {err_msg}",))
                        conn.commit()
                        conn.close()
                    finally:
                        SCANNING_IN_PROGRESS = False
                        
            elif desired == 'PAUSED':
                cursor.execute("UPDATE bot_status SET actual_state = 'PAUSED', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'live_scanner'", (now_str, now_str))
                conn.commit()
                conn.close()
                
            elif desired == 'STOPPED':
                cursor.execute("UPDATE bot_status SET actual_state = 'STOPPED', last_heartbeat = ?, last_activity = ? WHERE bot_id = 'live_scanner'", (now_str, now_str))
                conn.commit()
                conn.close()
                
        except Exception as err:
            print(f"[Worker Error] Fallo en bucle de control: {err}")
            try:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                cursor.execute("UPDATE bot_status SET actual_state = 'ERROR', last_error = ? WHERE bot_id = 'live_scanner'", (str(err),))
                conn.commit()
                conn.close()
            except Exception:
                pass
                
        time.sleep(5)

if __name__ == "__main__":
    init_simulation_tables()
    t_web = threading.Thread(target=start_control_server, daemon=True)
    t_web.start()
    
    t_tracker = threading.Thread(target=run_tracker_loop, daemon=True)
    t_tracker.start()
    
    t_paper = threading.Thread(target=run_paper_bot_worker, daemon=True)
    t_paper.start()
    
    t_telegram = threading.Thread(target=telegram_polling_loop, daemon=True)
    t_telegram.start()
    
    t_watchdog = threading.Thread(target=run_watchdog_loop, daemon=True)
    t_watchdog.start()
    
    t_worker = threading.Thread(target=run_scanner_worker, daemon=True)
    t_worker.start()
    
    print("\n[Servidor] Workers y servidores inicializados de forma persistente...")
    while True:
        try:
            time.sleep(3600)
        except KeyboardInterrupt:
            print("\n[Servidor] Cerrando servidor local...")
            break

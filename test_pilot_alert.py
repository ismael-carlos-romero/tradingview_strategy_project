import json
import os
import sqlite3
import time
import urllib3
import requests
from datetime import datetime

# Deshabilitar advertencias de SSL inseguro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# Cargar webhook desde config.json
CONFIG_PATH = "config.json"
WEBHOOK_URL = None

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            WEBHOOK_URL = config_data.get("webhook_url")
    except Exception as e:
        print(f"Error al leer config.json: {e}")

if not WEBHOOK_URL:
    WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxbLkV8YMCxcQjI9GVtxXx56WtJO2jH-54k9M8bylct9v2uhf7CZI9ewIGFOnI05QPE/exec"

DB_NAME = "trading_laboratory.db"

def save_local_signal_and_setup(payload):
    """Simula la lógica del motor relacional en la base de datos SQLite local."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    ticker = payload["ticker"]
    timeframe = payload["timeframe"]
    setup_id = payload["setup_id"]
    signal_id = payload["signal_id"]
    timestamp = payload["timestamp"]
    
    state = payload["event"]["state"]
    score = payload["event"]["setup_score"]
    
    strat_id = payload["strategy"]["id"]
    strat_ver = payload["strategy"]["version"]
    direction = payload["strategy"]["direction"]
    
    price = payload["market_data"]["action_price"]
    dist_pm40 = payload["market_data"]["indicators"]["distance_pm40"]
    rel_vol = payload["market_data"]["relative_volume"]
    pm40_slope = payload["market_data"]["indicators"]["pm40_slope"]

    # 1. Registrar señal (Deduplicación)
    cursor.execute("SELECT signal_id FROM senales WHERE signal_id = ?", (signal_id,))
    if cursor.fetchone():
        print(f"[SQLite] Señal duplicada omitida: {signal_id}")
    else:
        cursor.execute("""
            INSERT INTO senales (signal_id, timestamp, ticker, direction, strategy_id, strategy_version, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (signal_id, timestamp, ticker, direction, strat_id, strat_ver, json.dumps(payload)))
        print(f"[SQLite] Señal registrada: {signal_id}")

    # 2. Registrar o actualizar setup (Ciclo de Vida)
    cursor.execute("SELECT setup_id, state FROM setups WHERE setup_id = ?", (setup_id,))
    existing_setup = cursor.fetchone()

    if not existing_setup:
        # Nuevo Setup
        conf_time = timestamp if state == "CONFIRMADA" else None
        inval_time = timestamp if state == "INVALIDADA" else None
        cursor.execute("""
            INSERT INTO setups (setup_id, ticker, strategy_id, timeframe, state, creation_time, confirmation_time, invalidation_time, setup_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (setup_id, ticker, strat_id, timeframe, state, timestamp, conf_time, inval_time, score))
        print(f"[SQLite] Nuevo Setup creado: {setup_id} (Estado: {state})")
    else:
        # Actualizar setup existente
        cursor.execute("""
            UPDATE setups
            SET state = ?, setup_score = ?
            WHERE setup_id = ?
        """, (state, score, setup_id))
        
        # Rellenar timestamps según transición
        if state == "CONFIRMADA":
            cursor.execute("""
                UPDATE setups
                SET confirmation_time = COALESCE(confirmation_time, ?)
                WHERE setup_id = ?
            """, (timestamp, setup_id))
        elif state == "INVALIDADA":
            cursor.execute("""
                UPDATE setups
                SET invalidation_time = COALESCE(invalidation_time, ?)
                WHERE setup_id = ?
            """, (timestamp, setup_id))
        print(f"[SQLite] Setup {setup_id} actualizado a estado: {state}")

    # 3. Actualizar RADAR
    cursor.execute("""
        INSERT INTO radar_actual (ticker, strategy_id, timeframe, state, setup_score, price, distance_pm40, last_update)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, strategy_id, timeframe) DO UPDATE SET
            state = excluded.state,
            setup_score = excluded.setup_score,
            price = excluded.price,
            distance_pm40 = excluded.distance_pm40,
            last_update = excluded.last_update
    """, (ticker, strat_id, timeframe, state, score, price, dist_pm40, timestamp))
    print(f"[SQLite] Radar actualizado para {ticker} ({strat_id})")

    # 4. Si es pre-alerta o inminente, registrar en oportunidades anticipadas
    if state in ["PRE-ALERTA", "INMINENTE"]:
        cursor.execute("""
            INSERT OR REPLACE INTO oportunidades_anticipadas (setup_id, timestamp, distance_pm40, approach_speed, pm40_slope, relative_volume)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (setup_id, timestamp, dist_pm40, 0.0, pm40_slope, rel_vol))
        print(f"[SQLite] Oportunidad anticipada registrada para: {setup_id}")

    conn.commit()
    conn.close()

def send_webhook(payload):
    print(f"[Webhook] Enviando payload a Google Sheets ({payload['event']['state']})...")
    try:
        r = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "text/plain"}, timeout=15, verify=False)
        print(f"[Webhook] Respuesta: {r.status_code} - {r.text}")
        return r.status_code == 200
    except Exception as e:
        print(f"[Webhook] Error al enviar señal: {e}")
        return False

def verify_sqlite_results():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print("\n--- VERIFICACIÓN DE BASE DE DATOS LOCAL ---")
    cursor.execute("SELECT * FROM senales")
    print(f"Señales registradas ({len(cursor.fetchall())}):")
    cursor.execute("SELECT * FROM senales")
    for row in cursor.fetchall():
        print(row[:6])

    cursor.execute("SELECT * FROM setups")
    print(f"\nSetups registrados:")
    for row in cursor.fetchall():
        print(row)

    cursor.execute("SELECT * FROM radar_actual")
    print(f"\nRadar actual:")
    for row in cursor.fetchall():
        print(row)
        
    cursor.execute("SELECT * FROM oportunidades_anticipadas")
    print(f"\nOportunidades anticipadas:")
    for row in cursor.fetchall():
        print(row)
        
    conn.close()

def main():
    date_str = datetime.now().strftime("%Y%m%d")
    setup_id = f"SPY_1H_PM40_CALL_{date_str}_001"
    
    # ----------------------------------------------------
    # PASO A: PRE-ALERTA
    # ----------------------------------------------------
    payload_pre = {
        "webhook_token": "LAB_SIM_SECURE_TOKEN",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": "SPY",
        "timeframe": "1H",
        "setup_id": setup_id,
        "signal_id": f"SIG_SPY_{date_str}_1",
        "event": {
            "action": "setup_update",
            "state": "PRE-ALERTA",
            "setup_score": 65
        },
        "strategy": {
            "id": "PM40_BOUNCE",
            "version": "1.0",
            "direction": "CALL"
        },
        "market_data": {
            "action_price": 541.20,
            "volume": 98000,
            "relative_volume": 1.15,
            "moving_averages": {
                "pm10": 540.0,
                "pm20": 539.0,
                "pm40": 538.5,
                "pm100": 528.0,
                "pm200": 512.0
            },
            "indicators": {
                "distance_pm40": 0.50,
                "pm40_slope": 0.05,
                "spy_daily_trend": "BULLISH"
            }
        }
    }

    print("=== ENVIANDO PASO A: PRE-ALERTA ===")
    save_local_signal_and_setup(payload_pre)
    send_webhook(payload_pre)

    print("\nEsperando 3 segundos antes del siguiente estado...")
    time.sleep(3)

    # ----------------------------------------------------
    # PASO B: CONFIRMADA (Transición del mismo setup)
    # ----------------------------------------------------
    payload_conf = {
        "webhook_token": "LAB_SIM_SECURE_TOKEN",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker": "SPY",
        "timeframe": "1H",
        "setup_id": setup_id,
        "signal_id": f"SIG_SPY_{date_str}_2",
        "event": {
            "action": "setup_update",
            "state": "CONFIRMADA",
            "setup_score": 85
        },
        "strategy": {
            "id": "PM40_BOUNCE",
            "version": "1.0",
            "direction": "CALL"
        },
        "market_data": {
            "action_price": 542.15,
            "volume": 135000,
            "relative_volume": 1.45,
            "moving_averages": {
                "pm10": 540.2,
                "pm20": 539.1,
                "pm40": 538.6,
                "pm100": 528.0,
                "pm200": 512.0
            },
            "indicators": {
                "distance_pm40": 0.65,
                "pm40_slope": 0.06,
                "spy_daily_trend": "BULLISH"
            }
        }
    }

    print("\n=== ENVIANDO PASO B: CONFIRMADA ===")
    save_local_signal_and_setup(payload_conf)
    send_webhook(payload_conf)
    
    # ----------------------------------------------------
    # PASO C: INTENTO DE SEÑAL DUPLICADA (Debe omitirse)
    # ----------------------------------------------------
    print("\n=== ENVIANDO PASO C: SEÑAL DUPLICADA (SIG_SPY_..._2) ===")
    save_local_signal_and_setup(payload_conf) # Mismo signal_id, no debe insertar en senales

    # Verificar SQLite
    verify_sqlite_results()

if __name__ == "__main__":
    main()

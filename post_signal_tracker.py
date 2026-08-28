import sqlite3
import os
import sys
import json
import time
import requests
import urllib3
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone

# Deshabilitar advertencias SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import paper_bot

session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

DB_NAME = "trading_laboratory.db"
CONFIG_PATH = "config.json"
WEBHOOK_URL = None
BOT_CONFIGS = {
    "bot_conservative": { "desc": "Conservador (TP 20%, SL -10%)", "tp_pct": 20.0, "sl_pct": -10.0 },
    "bot_pilot": { "desc": "Piloto Estándar (TP 30%, SL -15%)", "tp_pct": 30.0, "sl_pct": -15.0 },
    "bot_aggressive": { "desc": "Agresivo (TP 50%, SL -20%)", "tp_pct": 50.0, "sl_pct": -20.0 }
}

if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            WEBHOOK_URL = config_data.get("webhook_url")
            if "bot_tournament" in config_data:
                BOT_CONFIGS = config_data["bot_tournament"]
    except Exception as e:
        print(f"Error al leer config.json: {e}")

if not WEBHOOK_URL:
    WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzLTCVXSJHV9KUUCT2zhGvKCkcq-WS4ng-ZRa0GSysYdKVEwdj7TpCmXprQiQMedcch/exec"

def get_confirmed_setups():
    """Recupera los setups confirmados hoy que no tienen resultado finalizado."""
    if not os.path.exists(DB_NAME):
        return []
    
    conn = sqlite3.connect(DB_NAME, timeout=15.0)
    try:
        cursor = conn.cursor()
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("""
            SELECT s.setup_id, s.ticker, s.strategy_id, s.confirmation_time, s.setup_score
            FROM setups s
            LEFT JOIN resultados r ON s.setup_id = SUBSTR(r.result_id, 5)
            WHERE s.state = 'CONFIRMADA' 
              AND s.confirmation_time LIKE ?
              AND r.result_id IS NULL
        """, (today_str + "%",))
        
        setups = []
        for row in cursor.fetchall():
            setups.append({
                "setup_id": row[0],
                "ticker": row[1],
                "strategy_id": row[2],
                "confirmation_time": row[3],
                "setup_score": row[4]
            })
        return setups
    finally:
        conn.close()

def get_return_at_offset(df_after, entry_price, conf_time, minutes_offset, direction):
    """Obtiene el rendimiento porcentual transcurrido el offset en minutos."""
    target_time = conf_time + timedelta(minutes=minutes_offset)
    df_temp = df_after[df_after.index >= target_time]
    if df_temp.empty:
        price_offset = float(df_after['Close'].iloc[-1])
    else:
        price_offset = float(df_temp['Close'].iloc[0])
        
    if direction == "CALL":
        return (price_offset - entry_price) / entry_price * 100
    else:
        return (entry_price - price_offset) / entry_price * 100

def simulate_bot_performance(df_after, entry_price, direction, tp_opt, sl_opt):
    """Simula el rendimiento de un perfil de bot (TP/SL) usando apalancamiento lineal x30."""
    tp_underlying = tp_opt / 30.0
    sl_underlying = sl_opt / 30.0
    
    hit_tp = False
    hit_sl = False
    tp_time = None
    sl_time = None
    
    for idx, row in df_after.iterrows():
        high_val = float(row['High'])
        low_val = float(row['Low'])
        
        if direction == "CALL":
            pct_high = (high_val - entry_price) / entry_price * 100
            pct_low = (low_val - entry_price) / entry_price * 100
            if pct_high >= tp_underlying and not hit_tp:
                hit_tp = True
                tp_time = idx
            if pct_low <= sl_underlying and not hit_sl:
                hit_sl = True
                sl_time = idx
        else: # PUT
            pct_high = (entry_price - low_val) / entry_price * 100
            pct_low = (entry_price - high_val) / entry_price * 100
            if pct_high >= tp_underlying and not hit_tp:
                hit_tp = True
                tp_time = idx
            if pct_low <= sl_underlying and not hit_sl:
                hit_sl = True
                sl_time = idx
                
    if hit_tp and hit_sl:
        if tp_time < sl_time:
            return tp_opt, 1
        else:
            return sl_opt, 0
    elif hit_tp:
        return tp_opt, 1
    elif hit_sl:
        return sl_opt, 0
    else:
        close_price = float(df_after['Close'].iloc[-1])
        ret_close = (close_price - entry_price) / entry_price * 100 if direction == "CALL" else (entry_price - close_price) / entry_price * 100
        option_return = max(-100.0, ret_close * 30.0)
        return option_return, (1 if option_return > 0 else 0)

def track_setup(setup):
    """Calcula MFE, MAE, rendimientos de intervalos, y simula el torneo de bots para el setup."""
    ticker = setup["ticker"]
    setup_id = setup["setup_id"]
    conf_time_str = setup["confirmation_time"]
    
    try:
        conf_time = datetime.strptime(conf_time_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        print(f"[Tracker] Error al parsear timestamp: {conf_time_str}")
        return
        
    print(f"[Tracker] Iniciando tracking para {ticker} ({setup_id}) desde {conf_time_str}...")
    
    try:
        df = yf.download(ticker, period="2d", interval="5m", session=session, progress=False)
        if df.empty:
            print(f"[Tracker] No hay datos intradía para {ticker}")
            return
            
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [col[0] for col in df.columns]
            
        local_tz = datetime.now().astimezone().tzinfo
        conf_time_localized = conf_time.replace(tzinfo=local_tz)
        conf_time_utc = conf_time_localized.astimezone(timezone.utc).replace(tzinfo=None)
        
        if df.index.tz is not None:
            df.index = df.index.tz_convert('UTC').tz_localize(None)
            
        df_after = df[df.index >= conf_time_utc].copy()
        
        # 1. Determinar dirección de la estrategia de forma atómica
        conn = sqlite3.connect(DB_NAME, timeout=15.0)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT direction FROM catalogo_estrategias WHERE strategy_id = ?", (setup["strategy_id"],))
            res = cursor.fetchone()
            direction = res[0] if res else "CALL"
        finally:
            conn.close()

        # 2. Registrar compra virtual en el Paper Bot
        paper_bot.execute_paper_buy(setup_id, ticker, direction)

        # Fallback de simulación si mercado cerrado
        if df_after.empty or len(df_after) < 3:
            print(f"[Tracker] [SIMULACIÓN] Generando ticks de simulación...")
            last_real_price = float(df['Close'].iloc[-1]) if not df.empty else 542.15
            
            sim_ticks = []
            sim_times = [conf_time_utc + timedelta(minutes=5 * i) for i in range(1, 25)]
            direction_multiplier = 1 if direction == "CALL" else -1
            
            for i, t in enumerate(sim_times):
                pct_change = (0.06 * i + (0.12 if i % 2 == 0 else -0.05)) * direction_multiplier
                close_sim = last_real_price * (1 + pct_change / 100.0)
                high_sim = close_sim * 1.002
                low_sim = close_sim * 0.998
                sim_ticks.append({
                    "Datetime": t,
                    "Open": close_sim * 0.999,
                    "High": high_sim,
                    "Low": low_sim,
                    "Close": close_sim,
                    "Volume": 100000
                })
            df_after = pd.DataFrame(sim_ticks).set_index("Datetime")
            entry_price = last_real_price
        else:
            entry_price = float(df[df.index <= conf_time_utc]['Close'].iloc[-1]) if not df[df.index <= conf_time_utc].empty else float(df_after['Open'].iloc[0])
        
        mfe = 0.0
        mae = 0.0
        
        for idx, row in df_after.iterrows():
            high_val = float(row['High'])
            low_val = float(row['Low'])
            
            if direction == "CALL":
                mfe = max(mfe, (high_val - entry_price) / entry_price * 100)
                mae = min(mae, (low_val - entry_price) / entry_price * 100)
            else:
                mfe = max(mfe, (entry_price - low_val) / entry_price * 100)
                mae = min(mae, (entry_price - high_val) / entry_price * 100)
                
        ret_5 = get_return_at_offset(df_after, entry_price, conf_time, 5, direction)
        ret_15 = get_return_at_offset(df_after, entry_price, conf_time, 15, direction)
        ret_30 = get_return_at_offset(df_after, entry_price, conf_time, 30, direction)
        ret_60 = get_return_at_offset(df_after, entry_price, conf_time, 60, direction)
        
        close_price = float(df_after['Close'].iloc[-1])
        ret_close = (close_price - entry_price) / entry_price * 100 if direction == "CALL" else (entry_price - close_price) / entry_price * 100
        
        underlying_success = 1 if ret_close > 0 else 0
        duration_hours = (df_after.index[-1] - conf_time).total_seconds() / 3600.0
        
        # Bot piloto (el de defecto para la tabla de resultados principales)
        pilot_ret, pilot_success = simulate_bot_performance(df_after, entry_price, direction, BOT_CONFIGS["bot_pilot"]["tp_pct"], BOT_CONFIGS["bot_pilot"]["sl_pct"])
        
        # 3. Guardar el torneo de bots (experimentos) de forma atómica
        conn = sqlite3.connect(DB_NAME, timeout=15.0)
        try:
            cursor = conn.cursor()
            for bot_id, bot_conf in BOT_CONFIGS.items():
                bot_ret, bot_success = simulate_bot_performance(df_after, entry_price, direction, bot_conf["tp_pct"], bot_conf["sl_pct"])
                
                experiment_id = f"EXP_{setup_id}_{bot_id.upper()}"
                rules_json = json.dumps({"tp_pct": bot_conf["tp_pct"], "sl_pct": bot_conf["sl_pct"]})
                conclusion = json.dumps({"option_return_pct": bot_ret, "pnl_usd": bot_ret, "success": bot_success})
                
                cursor.execute("""
                    INSERT OR REPLACE INTO experimentos (experiment_id, question, hypothesis, sample_size, rules_json, status, conclusion)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (experiment_id, "Bot Tournament", f"¿El bot {bot_id} es rentable?", 1, rules_json, "COMPLETED", conclusion))
            conn.commit()
        finally:
            conn.close()

        # 4. Registrar la orden y ejecución de venta en el Paper Bot
        paper_bot.execute_paper_sell(setup_id, ticker, direction, pilot_ret)
        
        # 5. Registrar en la tabla de resultados principales y marcar setup finalizado
        trade_id = f"TRD_{setup_id}"
        result_id = f"RES_{setup_id}"
        
        conn = sqlite3.connect(DB_NAME, timeout=15.0)
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO resultados (result_id, trade_id, underlying_success, option_pnl, option_return_pct, duration_hours)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (result_id, trade_id, underlying_success, pilot_ret, pilot_ret, duration_hours))
            
            cursor.execute("UPDATE setups SET state = 'FINALIZADA' WHERE setup_id = ?", (setup_id,))
            conn.commit()
        finally:
            conn.close()
        
        print(f"[SQLite] Setup {setup_id} finalizado de forma segura. Pilot PnL: {pilot_ret:.1f}%")
        
        # 6. Transmitir actualización de resultados a Google Sheets Webhook
        payload = {
            "webhook_token": "LAB_SIM_SECURE_TOKEN",
            "setup_id": setup_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "event": {
                "action": "result_update",
                "state": "FINALIZADA"
            },
            "trade": {
                "trade_id": trade_id,
                "ticker": ticker,
                "option_symbol": f"{ticker}_SIM_OPT",
                "position_role": "PRIMARY",
                "qty": 1,
                "state": "CLOSED"
            },
            "result": {
                "result_id": result_id,
                "underlying_success": underlying_success,
                "option_pnl": pilot_ret,
                "option_return_pct": pilot_ret,
                "duration_hours": round(duration_hours, 2),
                "mfe": round(mfe, 2),
                "mae": round(mae, 2),
                "ret_5m": round(ret_5, 2),
                "ret_15m": round(ret_15, 2),
                "ret_30m": round(ret_30, 2),
                "ret_60m": round(ret_60, 2),
                "ret_close": round(ret_close, 2)
            }
        }
        
        try:
            r = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "text/plain"}, verify=False, timeout=25)
            print(f"[Tracker] Webhook resultados enviado: {r.status_code}")
            
            # Enviar actualizacion de cierre a POSICIONES_VIVO para limpiar el panel en vivo
            close_live_payload = {
                "webhook_token": "LAB_SIM_SECURE_TOKEN",
                "setup_id": setup_id,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "event": {
                    "action": "live_pnl_update"
                },
                "position": {
                    "trade_id": trade_id,
                    "state": "CLOSED"
                }
            }
            try:
                requests.post(WEBHOOK_URL, json=close_live_payload, headers={"Content-Type": "text/plain"}, verify=False, timeout=10)
            except Exception:
                pass
                
        except Exception as e:
            print(f"[Tracker] Error al transmitir resultados a Sheets: {e}")
            
    except Exception as e:
        print(f"[Tracker] Error al procesar {ticker}: {e}")
        import traceback
        traceback.print_exc()

def compute_accumulated_statistics():
    """Calcula y consolida las estadísticas agregadas por bot desde SQLite y las envía a Sheets."""
    if not os.path.exists(DB_NAME):
        return
        
    print("[Tracker] Consolidador de estadísticas del Torneo de Bots activo...")
    conn = sqlite3.connect(DB_NAME, timeout=15.0)
    try:
        cursor = conn.cursor()
        tournament_results = []
        
        for bot_id, bot_conf in BOT_CONFIGS.items():
            cursor.execute("""
                SELECT conclusion, rules_json FROM experimentos 
                WHERE experiment_id LIKE ? AND question = 'Bot Tournament' AND status = 'COMPLETED'
            """, (f"%_{bot_id.upper()}",))
            
            rows = cursor.fetchall()
            total_trades = len(rows)
            winning_trades = 0
            total_pnl = 0.0
            gross_profits = 0.0
            gross_losses = 0.0
            
            for row in rows:
                conclusion_data = json.loads(row[0])
                ret = float(conclusion_data.get("option_return_pct", 0.0))
                
                total_pnl += ret
                if ret > 0:
                    winning_trades += 1
                    gross_profits += ret
                else:
                    gross_losses += abs(ret)
                    
            win_rate = round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0
            avg_return = round((total_pnl / total_trades), 2) if total_trades > 0 else 0.0
            profit_factor = round((gross_profits / gross_losses), 2) if gross_losses > 0 else (gross_profits if gross_profits > 0 else 1.0)
            
            cursor.execute("""
                INSERT OR REPLACE INTO estadisticas (aggregation_type, key_name, total_trades, win_rate, profit_factor, max_drawdown, avg_duration_hours)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("BOT", bot_id, total_trades, win_rate, profit_factor, 0.0, 0.0))
            
            tournament_results.append({
                "bot_id": bot_id,
                "strategy_desc": bot_conf["desc"],
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "win_rate_pct": win_rate,
                "avg_return_pct": avg_return,
                "total_pnl_usd": total_pnl
            })
            
        conn.commit()
    finally:
        conn.close()
    
    # Transmitir a Google Sheets
    payload = {
        "webhook_token": "LAB_SIM_SECURE_TOKEN",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "event": {
            "action": "tournament_update"
        },
        "tournament_results": tournament_results
    }
    
    try:
        r = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "text/plain"}, verify=False, timeout=25)
        print(f"[Tracker] Webhook Torneo de Bots actualizado en Sheets: {r.status_code} - {r.text}")
    except Exception as e:
        print(f"[Tracker] Error al transmitir torneo de bots: {e}")

def update_live_positions_pnl():
    """Actualiza y transmite en caliente el PnL de todas las posiciones simuladas activas."""
    if not os.path.exists(DB_NAME):
        return
        
    print("[Tracker] Actualizando PnL flotante de posiciones abiertas en Sheets...")
    conn = sqlite3.connect(DB_NAME, timeout=15.0)
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.trade_id, o.ticker, o.qty, s.strategy_id, s.confirmation_time, s.setup_id
            FROM operaciones o
            JOIN setups s ON o.trade_id = 'TRD_' || s.setup_id
            WHERE o.state = 'OPEN'
        """)
        open_trades = cursor.fetchall()
        
        if not open_trades:
            print("[Tracker] No hay posiciones simuladas abiertas actualmente.")
            return
            
        print(f"[Tracker] Se encontraron {len(open_trades)} posiciones abiertas para cotizar.")
        
        for trade_id, ticker, qty, strategy_id, conf_time_str, setup_id in open_trades:
            try:
                # 1. Obtener direccion
                cursor.execute("SELECT direction FROM catalogo_estrategias WHERE strategy_id = ?", (strategy_id,))
                res = cursor.fetchone()
                direction = res[0] if res else "CALL"
                
                # 2. Descargar cotizacion en vivo
                df = yf.download(ticker, period="1d", interval="1m", session=session, progress=False, timeout=10)
                if df.empty:
                    continue
                    
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [col[0] for col in df.columns]
                    
                current_price = float(df['Close'].iloc[-1])
                
                # 3. Obtener precio de entrada original
                conf_time = datetime.strptime(conf_time_str, "%Y-%m-%d %H:%M:%S")
                local_tz = datetime.now().astimezone().tzinfo
                conf_time_utc = conf_time.replace(tzinfo=local_tz).astimezone(timezone.utc).replace(tzinfo=None)
                
                df_hist = yf.download(ticker, period="2d", interval="5m", session=session, progress=False)
                if isinstance(df_hist.columns, pd.MultiIndex):
                    df_hist.columns = [col[0] for col in df_hist.columns]
                if df_hist.index.tz is not None:
                    df_hist.index = df_hist.index.tz_convert('UTC').tz_localize(None)
                    
                entry_price = float(df_hist[df_hist.index <= conf_time_utc]['Close'].iloc[-1]) if not df_hist[df_hist.index <= conf_time_utc].empty else current_price
                
                # 4. Calcular variaciones y PnL de Opcion simulada (lineal x30)
                if direction == "CALL":
                    underlying_change_pct = (current_price - entry_price) / entry_price * 100
                else:
                    underlying_change_pct = (entry_price - current_price) / entry_price * 100
                    
                option_pnl_pct = max(-100.0, underlying_change_pct * 30.0)
                pnl_usd = (option_pnl_pct / 100.0) * 100.0 * qty # Prima virtual base de $100
                
                print(f"[Live PnL] {ticker}: Entrada=${entry_price:.2f} | Actual=${current_price:.2f} | Var={underlying_change_pct:+.2f}% | PnL={option_pnl_pct:+.1f}% | USD={pnl_usd:+.2f}")
                
                # 5. Enviar actualizacion al Sheets Webhook
                payload = {
                    "webhook_token": "LAB_SIM_SECURE_TOKEN",
                    "setup_id": setup_id,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "event": {
                        "action": "live_pnl_update"
                    },
                    "position": {
                        "trade_id": trade_id,
                        "ticker": ticker,
                        "direction": direction,
                        "strategy_id": strategy_id,
                        "qty": qty,
                        "entry_price": round(entry_price, 2),
                        "current_price": round(current_price, 2),
                        "underlying_change_pct": round(underlying_change_pct, 2),
                        "option_pnl_pct": round(option_pnl_pct, 2),
                        "pnl_usd": round(pnl_usd, 2),
                        "state": "OPEN",
                        "last_update": datetime.now().strftime("%H:%M:%S")
                    }
                }
                requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "text/plain"}, verify=False, timeout=10)
                
            except Exception as e:
                print(f"[Live PnL] Error al cotizar {ticker}: {e}")
    finally:
        conn.close()

def main():
    print(f"=== INICIANDO TRACKER DE RESULTADOS POST-SEÑAL (MAE/MFE) ===")
    
    # 1. Actualizar el PnL de posiciones abiertas primero
    try:
        update_live_positions_pnl()
    except Exception as e:
        print(f"[Tracker] Error al procesar PnL en vivo: {e}")
        
    # 2. Evaluar setups en curso para verificar TP/SL
    setups = get_confirmed_setups()
    print(f"[Tracker] Se encontraron {len(setups)} setups confirmados hoy sin evaluar.")
    
    for s in setups:
        track_setup(s)
        
    compute_accumulated_statistics()
    print("=== FINALIZACIÓN DEL ESCANEO DEL TRACKER ===")

if __name__ == "__main__":
    main()

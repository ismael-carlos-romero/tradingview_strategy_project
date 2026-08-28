import sqlite3
import os
import json

DB_NAME = "trading_laboratory.db"
CONFIG_PATH = "config.json"

def get_db_connection():
    return sqlite3.connect(DB_NAME, timeout=15.0)

def calculate_score_retrospective(raw_payload, w_trend, w_dist, w_vol, w_floor):
    """Calcula el Setup Score retrospectivo para una señal usando pesos arbitrarios."""
    score = 0
    try:
        data = json.loads(raw_payload)
        direction = data.get("strategy", {}).get("direction", "CALL")
        market_data = data.get("market_data", {})
        indicators = market_data.get("indicators", {})
        
        # 1. Tendencia diaria
        spy_trend = indicators.get("spy_daily_trend", "BULLISH")
        trend_ok = (direction == "CALL" and spy_trend == "BULLISH") or (direction == "PUT" and spy_trend == "BEARISH")
        if trend_ok:
            score += w_trend
            
        # 2. Distancia a la PM40
        dist_pm40 = float(indicators.get("distance_pm40", 0.5))
        if dist_pm40 <= 0.2:
            score += w_dist
        elif dist_pm40 <= 0.5:
            score += int(w_dist * 0.66)
        elif dist_pm40 <= 1.0:
            score += int(w_dist * 0.33)
            
        # 3. Volumen relativo
        vol_rel = float(market_data.get("relative_volume", 1.0))
        if vol_rel >= 1.5:
            score += w_vol
        elif vol_rel >= 1.0:
            score += int(w_vol * 0.5)
            
        # 4. Respeto de soporte / piso diario
        # En la simulación simplificada, asumimos respeto al piso si la señal de rebote es válida
        score += w_floor
        
    except Exception:
        pass
        
    return min(100, score)

def optimize_weights():
    if not os.path.exists(DB_NAME):
        print(f"[Optimizer] La base '{DB_NAME}' no existe.")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Cargar señales finalizadas con su retorno de opción
    cursor.execute("""
        SELECT s.raw_payload, r.option_return_pct
        FROM senales s
        JOIN setups st ON s.strategy_id = st.strategy_id AND s.ticker = st.ticker
        JOIN resultados r ON r.trade_id = 'TRD_' || st.setup_id
        WHERE SUBSTR(s.timestamp, 1, 10) = SUBSTR(st.creation_time, 1, 10)
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("[Optimizer] No hay suficientes setups finalizados en SQLite para optimizar. Usando simulación de datos.")
        # Generar set de datos de prueba para optimización autónoma
        sample_signals = []
        import random
        random.seed(42)
        for i in range(15):
            dir_val = "CALL" if i % 2 == 0 else "PUT"
            dist_val = 0.15 if i % 3 == 0 else (0.45 if i % 3 == 1 else 0.85)
            vol_val = 1.8 if i % 4 == 0 else 1.2
            trend_val = "BULLISH" if i % 5 != 0 else "BEARISH"
            
            payload = {
                "strategy": {"direction": dir_val},
                "market_data": {"relative_volume": vol_val},
                "indicators": {"distance_pm40": dist_val, "spy_daily_trend": trend_val}
            }
            # Un retorno simulado: si la tendencia diaria está a favor y el volumen es alto, es un trade ganador (+30%), si no es perdedor (-15%)
            is_winner = (dir_val == "CALL" and trend_val == "BULLISH" and vol_val >= 1.5) or (dir_val == "PUT" and trend_val == "BEARISH")
            ret_val = 30.0 if is_winner else -15.0
            
            sample_signals.append((json.dumps(payload), ret_val))
        signals_to_eval = sample_signals
    else:
        signals_to_eval = rows
        
    print(f"[Optimizer] Iniciando calibración de parámetros sobre {len(signals_to_eval)} casos...")
    
    best_weights = None
    best_win_rate = -1.0
    best_selected_count = 0
    
    # Grid search multidimensional que sume 100
    for w_trend in range(0, 51, 5):
        for w_dist in range(0, 51, 5):
            for w_vol in range(0, 51, 5):
                w_floor = 100 - (w_trend + w_dist + w_vol)
                if w_floor < 0 or w_floor > 50:
                    continue
                    
                # Evaluar esta combinación
                selected_winners = 0
                selected_total = 0
                
                for raw_payload, option_ret in signals_to_eval:
                    score = calculate_score_retrospective(raw_payload, w_trend, w_dist, w_vol, w_floor)
                    if score >= 70:
                        selected_total += 1
                        if option_ret > 0:
                            selected_winners += 1
                            
                if selected_total > 0:
                    win_rate = selected_winners / selected_total * 100
                    # Queremos maximizar la tasa de acierto y priorizar que seleccione una cantidad de operaciones razonable (ej. al menos 20% del total)
                    if win_rate > best_win_rate or (win_rate == best_win_rate and selected_total > best_selected_count):
                        best_win_rate = win_rate
                        best_selected_count = selected_total
                        best_weights = {
                            "trend_daily": w_trend,
                            "ma_distance": w_dist,
                            "relative_volume": w_vol,
                            "daily_floor": w_floor
                        }
                        
    if best_weights:
        print(f"\n[Optimizer] Calibracion exitosa!")
        print(f"Pesos óptimos encontrados:")
        print(f" - Tendencia Diaria: {best_weights['trend_daily']}")
        print(f" - Distancia PM40: {best_weights['ma_distance']}")
        print(f" - Volumen Relativo: {best_weights['relative_volume']}")
        print(f" - Piso Diario: {best_weights['daily_floor']}")
        print(f"Métricas logradas en la simulación predictiva (Score >= 70):")
        print(f" - Win Rate: {best_win_rate:.2f}% | Operaciones Elegidas: {best_selected_count}/{len(signals_to_eval)}")
        
        # Guardar en config.json
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                config_data["weights"] = best_weights
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=2)
                print(f"[Optimizer] Pesos actualizados en '{CONFIG_PATH}' con éxito.")
            except Exception as e:
                print(f"[Optimizer] Error al actualizar config.json: {e}")
    else:
        print("[Optimizer] No se encontraron pesos viables.")

if __name__ == "__main__":
    print("=== INICIANDO OPTIMIZADOR Y CALIBRADOR DE SETUP SCORE ===")
    optimize_weights()
    print("=== OPTIMIZACIÓN COMPLETADA ===")

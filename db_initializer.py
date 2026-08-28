import sqlite3
import os

DB_NAME = "trading_laboratory.db"

def init_db():
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"Base de datos anterior '{DB_NAME}' eliminada para inicialización limpia.")

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # 1. CONFIGURACION
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracion (
            param_id TEXT PRIMARY KEY,
            val TEXT,
            type TEXT
        )
    """)

    # 2. CATALOGO_ESTRATEGIAS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalogo_estrategias (
            strategy_id TEXT,
            version TEXT,
            name TEXT,
            epistemology TEXT,
            direction TEXT,
            timeframe TEXT,
            required_conditions TEXT,
            optional_conditions TEXT,
            version_date TEXT,
            PRIMARY KEY (strategy_id, version)
        )
    """)

    # 3. RADAR_ACTUAL
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS radar_actual (
            ticker TEXT,
            strategy_id TEXT,
            timeframe TEXT,
            state TEXT,
            setup_score INTEGER,
            price REAL,
            distance_pm40 REAL,
            last_update TEXT,
            PRIMARY KEY (ticker, strategy_id, timeframe)
        )
    """)

    # 4. OPORTUNIDADES_ANTICIPADAS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oportunidades_anticipadas (
            setup_id TEXT,
            timestamp TEXT,
            distance_pm40 REAL,
            approach_speed REAL,
            pm40_slope REAL,
            relative_volume REAL,
            PRIMARY KEY (setup_id, timestamp)
        )
    """)

    # 5. EVENTOS_MERCADO
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS eventos_mercado (
            timestamp TEXT PRIMARY KEY,
            spy_trend TEXT,
            vix_value REAL,
            market_session TEXT
        )
    """)

    # 6. SEÑALES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS senales (
            signal_id TEXT PRIMARY KEY,
            timestamp TEXT,
            ticker TEXT,
            direction TEXT,
            strategy_id TEXT,
            strategy_version TEXT,
            raw_payload TEXT
        )
    """)

    # 7. SETUPS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS setups (
            setup_id TEXT PRIMARY KEY,
            ticker TEXT,
            strategy_id TEXT,
            timeframe TEXT,
            state TEXT,
            creation_time TEXT,
            confirmation_time TEXT,
            invalidation_time TEXT,
            setup_score INTEGER
        )
    """)

    # 8. DECISIONES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decisiones (
            decision_id TEXT PRIMARY KEY,
            setup_id TEXT,
            source TEXT,
            action TEXT,
            rejection_reason TEXT,
            timestamp TEXT,
            FOREIGN KEY (setup_id) REFERENCES setups(setup_id)
        )
    """)

    # 9. ORDENES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordenes (
            order_id TEXT PRIMARY KEY,
            decision_id TEXT,
            option_ticker TEXT,
            qty INTEGER,
            limit_price REAL,
            order_type TEXT,
            status TEXT,
            FOREIGN KEY (decision_id) REFERENCES decisiones(decision_id)
        )
    """)

    # 10. EJECUCIONES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ejecuciones (
            execution_id TEXT PRIMARY KEY,
            order_id TEXT,
            timestamp TEXT,
            side TEXT,
            qty INTEGER,
            price REAL,
            commission REAL,
            FOREIGN KEY (order_id) REFERENCES ordenes(order_id)
        )
    """)

    # 11. OPERACIONES
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS operaciones (
            trade_id TEXT PRIMARY KEY,
            ticker TEXT,
            option_symbol TEXT,
            position_role TEXT,
            qty INTEGER,
            buy_execution_id TEXT,
            sell_execution_id TEXT,
            state TEXT,
            FOREIGN KEY (buy_execution_id) REFERENCES ejecuciones(execution_id),
            FOREIGN KEY (sell_execution_id) REFERENCES ejecuciones(execution_id)
        )
    """)

    # 12. RESULTADOS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS resultados (
            result_id TEXT PRIMARY KEY,
            trade_id TEXT,
            underlying_success INTEGER,
            option_pnl REAL,
            option_return_pct REAL,
            duration_hours REAL,
            FOREIGN KEY (trade_id) REFERENCES operaciones(trade_id)
        )
    """)

    # 13. EXPERIMENTOS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experimentos (
            experiment_id TEXT PRIMARY KEY,
            question TEXT,
            hypothesis TEXT,
            sample_size INTEGER,
            rules_json TEXT,
            status TEXT,
            conclusion TEXT
        )
    """)

    # 14. ESTADISTICAS
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS estadisticas (
            aggregation_type TEXT,
            key_name TEXT,
            total_trades INTEGER,
            win_rate REAL,
            profit_factor REAL,
            max_drawdown REAL,
            avg_duration_hours REAL,
            PRIMARY KEY (aggregation_type, key_name)
        )
    """)

    conn.commit()
    print("Tablas relacionales creadas con éxito.")
    return conn

def populate_initial_data(conn):
    cursor = conn.cursor()

    # Configuración inicial por defecto
    config_params = [
        ("CAPITAL_INICIAL", "1000", "numeric"),
        ("MAX_INVERSION_PCT", "0.10", "numeric"),
        ("COMMISSION_PER_CONTRACT", "1.05", "numeric"),
        ("RETIRO_GANANCIA_PCT", "0.10", "numeric")
    ]
    cursor.executemany("INSERT INTO configuracion (param_id, val, type) VALUES (?, ?, ?)", config_params)

    # 18 Estrategias identificadas en la Fase 0
    strategies = [
        # CALLS
        ("GAP_NORMAL", "v1.0", "Gap Normal al Alza", "CARDONA", "CALL", "1H", 
         '["trend_bullish", "second_bar", "gap_gt_0.1", "first_bar_green", "is_green"]', "[]"),
        ("GAP_BAJISTA_ALZA", "v1.0", "Gap Bajista al Alza", "CARDONA", "CALL", "1H", 
         '["second_bar", "gap_lt_-0.1", "first_bar_green", "is_green"]', "[]"),
        ("PISO_FUERTE", "v1.0", "Piso Fuerte", "CARDONA", "CALL", "1H", 
         '["trend_bullish", "at_daily_floor", "crossover_pm20", "bullish_candle"]', "[]"),
        ("PRIMER_GAP_ALZA", "v1.0", "Primer Gap al Alza", "CARDONA", "CALL", "1H", 
         '["at_daily_floor", "last_bar_of_day", "gap_gt_0.1", "first_bar_green", "floor_respected", "below_pm40_5_bars_ago"]', "[]"),
        ("COLA_PISO", "v1.0", "Cola de Piso", "CARDONA", "CALL", "1H", 
         '["is_cola_piso", "near_lowest_20_or_near_ma"]', "[]"),
        ("PM40_BOUNCE", "v1.0", "Promedio Móvil de 40", "CARDONA", "CALL", "1H", 
         '["pm20_gt_pm40", "touched_pm40_last_3_bars", "crossover_highest_3", "solid_green"]', "[]"),
        ("CAIDA_BREAK", "v1.0", "Caída Normal/Fuerte", "CARDONA", "CALL", "1H", 
         '["trend_bullish", "drop_gt_0.5_pct", "crossover_highest_3", "solid_green"]', "[]"),
        ("CANAL_BREAK", "v1.0", "Ruptura Canal Bajista", "CARDONA", "CALL", "1H", 
         '["pm20_lt_pm40", "crossover_highest_15", "solid_green"]', "[]"),
        ("RUPTURA_RES", "v1.0", "Ruptura de Resistencia", "CARDONA", "CALL", "1H", 
         '["trend_bullish", "crossover_highest_20", "solid_green"]', "[]"),
        # PUTS
        ("VELA_ROJA", "v1.0", "Primera Vela Roja", "CARDONA", "PUT", "1H", 
         '["first_bar", "solid_red", "above_pm40"]', "[]"),
        ("TECHO_FUERTE", "v1.0", "Techo Fuerte", "CARDONA", "PUT", "1H", 
         '["at_daily_floor", "second_bar", "previous_red", "solid_red"]', "[]"),
        ("RUPTURA_PISO_GAP", "v1.0", "Ruptura Piso del Gap", "CARDONA", "PUT", "1H", 
         '["not_first_bar", "above_pm40", "prev_above_first_low", "curr_below_first_low", "solid_red"]', "[]"),
        ("CUATRO_PASOS", "v1.0", "Modelo de 4 Pasos", "CARDONA", "PUT", "1H", 
         '["below_pm40", "is_red", "prev_is_green", "bearish_engulfing_prev_open", "crossunder_lowest_3"]', "[]"),
        ("COLA_TECHO", "v1.0", "Cola de Techo", "CARDONA", "PUT", "1H", 
         '["is_cola_techo", "near_highest_20_or_near_ma"]', "[]"),
        ("HANGER_DIARIO", "v1.0", "Hanger en Diario", "CARDONA", "PUT", "1H", 
         '["last_bar_of_day", "daily_candle_is_hanger", "above_daily_sma100"]', "[]"),
        ("RUPTURA_SOP", "v1.0", "Ruptura de Soporte", "CARDONA", "PUT", "1H", 
         '["not_trend_bullish", "crossunder_lowest_20", "solid_red"]', "[]"),
        ("PISO_BREAK", "v1.0", "Ruptura de Piso Fuerte", "CARDONA", "PUT", "1H", 
         '["crossunder_daily_sma100_or_sma200", "solid_red"]', "[]"),
        ("GAP_CONT_PUT", "v1.0", "Gap Bajista de Continuación", "CARDONA", "PUT", "1H", 
         '["second_bar", "gap_lt_-0.1", "first_bar_red", "is_red"]', "[]")
    ]
    
    strategies_with_date = []
    import datetime
    today_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for s in strategies:
        strategies_with_date.append((s[0], s[1], s[2], s[3], s[4], s[5], s[6], s[7], today_str))
        
    cursor.executemany("""
        INSERT INTO catalogo_estrategias (strategy_id, version, name, epistemology, direction, timeframe, required_conditions, optional_conditions, version_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, strategies_with_date)

    conn.commit()
    print(f"Catálogo poblado con {len(strategies)} estrategias.")

if __name__ == "__main__":
    conn = init_db()
    populate_initial_data(conn)
    conn.close()
    print("Inicialización completa.")

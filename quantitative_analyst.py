import sqlite3
import os
import json

DB_NAME = "trading_laboratory.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME, timeout=15.0)

def run_quantitative_analysis():
    if not os.path.exists(DB_NAME):
        print(f"[Analyst] La base de datos '{DB_NAME}' no existe.")
        return
        
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Recuperar datos cruzados de setups, operaciones y resultados
        cursor.execute("""
            SELECT s.strategy_id, s.ticker, r.underlying_success, r.option_return_pct, r.duration_hours
            FROM setups s
            JOIN operaciones o ON s.setup_id = SUBSTR(o.trade_id, 5)
            JOIN resultados r ON o.trade_id = r.trade_id
            WHERE s.state = 'FINALIZADA'
        """)
        
        rows = cursor.fetchall()
        if not rows:
            print("[Analyst] No hay datos de setups finalizados suficientes para el análisis cuantitativo.")
            # Si no hay operaciones finalizadas reales, podemos buscar en el histórico de backtest o experimentos
            return
            
        print(f"[Analyst] Analizando {len(rows)} operaciones registradas en el laboratorio...")
        
        # Agrupar por Estrategia y por Ticker
        stats_by_strategy = {}
        stats_by_ticker = {}
        
        for strategy_id, ticker, success, option_ret, duration in rows:
            # Inicializar por estrategia
            if strategy_id not in stats_by_strategy:
                stats_by_strategy[strategy_id] = []
            stats_by_strategy[strategy_id].append((success, option_ret, duration))
            
            # Inicializar por ticker
            if ticker not in stats_by_ticker:
                stats_by_ticker[ticker] = []
            stats_by_ticker[ticker].append((success, option_ret, duration))
            
        # Procesar y guardar estadísticas por estrategia
        for strat_id, trades in stats_by_strategy.items():
            total = len(trades)
            winners = sum(1 for t in trades if t[1] > 0)
            win_rate = round((winners / total * 100), 2)
            
            gross_profits = sum(t[1] for t in trades if t[1] > 0)
            gross_losses = sum(abs(t[1]) for t in trades if t[1] <= 0)
            profit_factor = round((gross_profits / gross_losses), 2) if gross_losses > 0 else float(gross_profits)
            
            max_dd = round(min(t[1] for t in trades), 2)
            avg_duration = round(sum(t[2] for t in trades) / total, 2)
            
            cursor.execute("""
                INSERT OR REPLACE INTO estadisticas (aggregation_type, key_name, total_trades, win_rate, profit_factor, max_drawdown, avg_duration_hours)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("STRATEGY", strat_id, total, win_rate, profit_factor, max_dd, avg_duration))
            
            print(f"[Estrategia: {strat_id}] Trades: {total} | Win Rate: {win_rate}% | Profit Factor: {profit_factor} | Max Drawdown: {max_dd}% | Duracion Promedio: {avg_duration}h")

        # Procesar y guardar estadísticas por ticker
        for ticker, trades in stats_by_ticker.items():
            total = len(trades)
            winners = sum(1 for t in trades if t[1] > 0)
            win_rate = round((winners / total * 100), 2)
            
            gross_profits = sum(t[1] for t in trades if t[1] > 0)
            gross_losses = sum(abs(t[1]) for t in trades if t[1] <= 0)
            profit_factor = round((gross_profits / gross_losses), 2) if gross_losses > 0 else float(gross_profits)
            
            max_dd = round(min(t[1] for t in trades), 2)
            avg_duration = round(sum(t[2] for t in trades) / total, 2)
            
            cursor.execute("""
                INSERT OR REPLACE INTO estadisticas (aggregation_type, key_name, total_trades, win_rate, profit_factor, max_drawdown, avg_duration_hours)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("TICKER", ticker, total, win_rate, profit_factor, max_dd, avg_duration))
            
            print(f"[Ticker: {ticker}] Trades: {total} | Win Rate: {win_rate}% | Profit Factor: {profit_factor} | Max Drawdown: {max_dd}% | Duracion Promedio: {avg_duration}h")
            
        conn.commit()
        print("[Analyst] Reportes consolidados guardados con éxito en la tabla 'estadisticas' de SQLite.")
    finally:
        conn.close()

if __name__ == "__main__":
    print("=== INICIANDO BITÁCORA Y ANÁLISIS CUANTITATIVO ===")
    run_quantitative_analysis()
    print("=== ANÁLISIS CUANTITATIVO COMPLETADO ===")

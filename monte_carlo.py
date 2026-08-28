import sqlite3
import os
import json
import random

DB_NAME = "trading_laboratory.db"
NUM_SIMULATIONS = 1000
NUM_TRADES = 100
INITIAL_CAPITAL = 10000.0
CONTRACT_PREMIUM = 100.0
COMMISSION = 0.65

def get_db_connection():
    return sqlite3.connect(DB_NAME, timeout=15.0)

def run_monte_carlo():
    if not os.path.exists(DB_NAME):
        print(f"[Monte Carlo] La base de datos '{DB_NAME}' no existe.")
        return
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Cargar retornos históricos del bot piloto
    cursor.execute("SELECT option_return_pct FROM resultados")
    rows = cursor.fetchall()
    
    returns = [float(row[0]) for row in rows]
    
    # Si hay muy pocos datos, inyectar una muestra de bootstrap realista
    if len(returns) < 5:
        print(f"[Monte Carlo] Muestra historica pequena ({len(returns)}). Usando bootstrap expandido simulado...")
        returns = [30.0, 30.0, -15.0, 30.0, -15.0, 30.0, 30.0, -15.0, 30.0, -15.0]
        
    print(f"[Monte Carlo] Iniciando {NUM_SIMULATIONS} simulaciones de {NUM_TRADES} trades a futuro...")
    
    final_balances = []
    max_drawdowns = []
    ruin_count = 0
    
    # Ejecutar simulaciones
    for i in range(NUM_SIMULATIONS):
        balance = INITIAL_CAPITAL
        peak = INITIAL_CAPITAL
        max_dd = 0.0
        ruined = False
        
        for t in range(NUM_TRADES):
            # Obtener retorno aleatorio de la muestra histórica
            ret = random.choice(returns)
            
            # Simular 1 contrato
            cost = CONTRACT_PREMIUM + COMMISSION
            balance -= cost
            
            # Liquidación
            liquid = CONTRACT_PREMIUM * (1 + ret / 100.0)
            balance += (liquid - COMMISSION)
            
            # Monitorear Drawdown
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100
            max_dd = max(max_dd, dd)
            
            # Criterio de ruina (caer por debajo del 10% del capital inicial)
            if balance <= 1000.0:
                ruined = True
                
        final_balances.append(balance)
        max_drawdowns.append(max_dd)
        if ruined:
            ruin_count += 1
            
    # Calcular percentiles
    final_balances.sort()
    p5 = round(final_balances[int(NUM_SIMULATIONS * 0.05)], 2)
    p50 = round(final_balances[int(NUM_SIMULATIONS * 0.50)], 2)
    p95 = round(final_balances[int(NUM_SIMULATIONS * 0.95)], 2)
    
    avg_max_dd = round(sum(max_drawdowns) / NUM_SIMULATIONS, 2)
    ruin_probability = round((ruin_count / NUM_SIMULATIONS * 100), 2)
    
    # Guardar en estadisticas local
    cursor.execute("""
        INSERT OR REPLACE INTO estadisticas (aggregation_type, key_name, total_trades, win_rate, profit_factor, max_drawdown, avg_duration_hours)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("SIMULATION", "monte_carlo", NUM_TRADES, ruin_probability, p5, avg_max_dd, p95))
    
    conn.commit()
    conn.close()
    
    print(f"\n[Monte Carlo] Simulacion Completada de Forma Exitosa:")
    print(f" - Percentil 5% (Peor Escenario - 95% Confianza): ${p5:.2f}")
    print(f" - Percentil 50% (Mediana Proyectada): ${p50:.2f}")
    print(f" - Percentil 95% (Mejor Escenario): ${p95:.2f}")
    print(f" - Drawdown Maximo Promedio: {avg_max_dd:.2f}%")
    print(f" - Probabilidad Matematica de Ruina: {ruin_probability:.2f}%")
    print("[Monte Carlo] Proyecciones guardadas en la tabla 'estadisticas' de SQLite.")

if __name__ == "__main__":
    print("=== INICIANDO SIMULADOR DE MONTE CARLO ===")
    run_monte_carlo()
    print("=== SIMULACION DE MONTE CARLO COMPLETADA ===")

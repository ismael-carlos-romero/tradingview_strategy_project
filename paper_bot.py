import sqlite3
import os
from datetime import datetime

DB_NAME = "trading_laboratory.db"
DEFAULT_CAPITAL = 10000.0
CONTRACT_PREMIUM = 100.0 # Costo virtual de 1 contrato ($100 USD)
COMMISSION = 0.65        # Comisión del broker por contrato ($0.65 USD)

def get_db_connection():
    return sqlite3.connect(DB_NAME, timeout=15.0)

def initialize_capital_if_needed(conn):
    """Asegura que el capital simulado esté inicializado en la tabla configuracion."""
    cursor = conn.cursor()
    cursor.execute("SELECT val FROM configuracion WHERE param_id = 'capital_simulado'")
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO configuracion (param_id, val, type) VALUES ('capital_simulado', ?, 'FLOAT')", (str(DEFAULT_CAPITAL),))
        conn.commit()
        return DEFAULT_CAPITAL
    return float(row[0])

def update_capital(conn, amount_change):
    """Actualiza el capital simulado sumando o restando un monto."""
    cursor = conn.cursor()
    current_cap = initialize_capital_if_needed(conn)
    new_cap = current_cap + amount_change
    cursor.execute("UPDATE configuracion SET val = ? WHERE param_id = 'capital_simulado'", (str(new_cap),))
    conn.commit()
    print(f"[Paper Bot] Capital simulado actualizado: de ${current_cap:.2f} a ${new_cap:.2f} (Cambio: ${amount_change:+.2f})")
    return new_cap

def calculate_kelly_allocation(conn, strategy_id=None, ticker=None):
    """Calcula la cantidad de contratos óptima usando el Criterio de Kelly (25% Kelly Fraccional)."""
    cursor = conn.cursor()
    
    # 1. Consultar Win Rate histórico del bot piloto de la tabla estadisticas
    cursor.execute("SELECT win_rate FROM estadisticas WHERE aggregation_type = 'BOT' AND key_name = 'bot_pilot'")
    row = cursor.fetchone()
    win_rate = float(row[0]) if row and row[0] is not None else 50.0
    
    # 2. Ratio de Pago (TP 30% / SL 15% = 2.0)
    b = 2.0
    
    # 3. Fórmula de Kelly: f = (p * b - q) / b
    p = win_rate / 100.0
    q = 1.0 - p
    kelly_f = (p * b - q) / b
    
    # 4. Escalar de forma conservadora (25% Kelly)
    kelly_f = max(0.0, kelly_f) * 0.25
    
    # Exposición máxima de la cuenta por operación: 10%
    allocation_pct = min(kelly_f, 0.10)
    
    # Capital simulado actual
    capital_actual = initialize_capital_if_needed(conn)
    
    # Cantidad de contratos (cada contrato cuesta $100 USD de prima)
    qty = int((capital_actual * allocation_pct) / CONTRACT_PREMIUM)
    qty = max(1, qty) # Mínimo 1 contrato
    
    print(f"[Kelly Engine] Win Rate: {win_rate}% | Kelly f: {kelly_f:.2%} | Asignacion: {allocation_pct:.2%} | Contratos Calculados: {qty}")
    return qty

def execute_paper_buy(setup_id, ticker, direction):
    """Simula la compra de un contrato de opción para un setup confirmado."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Comprobar si ya existe orden de compra para este setup
        cursor.execute("SELECT order_id FROM ordenes WHERE order_id = ?", (f"ORD_BUY_{setup_id}",))
        if cursor.fetchone():
            return False
            
        # Calcular cantidad de contratos usando Kelly
        qty = calculate_kelly_allocation(conn)
        
        print(f"[Paper Bot] Ejecutando compra virtual de {qty} contrato(s) para {ticker} ({setup_id})...")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 2. Descontar costo del contrato + comisiones
        total_cost = (CONTRACT_PREMIUM * qty) + (COMMISSION * qty)
        initialize_capital_if_needed(conn)
        update_capital(conn, -total_cost)
        
        # 3. Registrar Decisión
        cursor.execute("""
            INSERT OR REPLACE INTO decisiones (decision_id, setup_id, source, action, rejection_reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (f"DEC_{setup_id}", setup_id, "ALGORITMICA", "BUY", None, now_str))
        
        # 4. Registrar Orden de Compra
        cursor.execute("""
            INSERT OR REPLACE INTO ordenes (order_id, decision_id, option_ticker, qty, limit_price, order_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (f"ORD_BUY_{setup_id}", f"DEC_{setup_id}", f"{ticker}_SIM_OPT", qty, 1.00, "MARKET", "COMPLETED"))
        
        # 5. Registrar Ejecución de Compra
        cursor.execute("""
            INSERT OR REPLACE INTO ejecuciones (execution_id, order_id, timestamp, side, qty, price, commission)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (f"EXE_BUY_{setup_id}", f"ORD_BUY_{setup_id}", now_str, "BUY", qty, 1.00, COMMISSION * qty))
        
        # 6. Registrar Operación Abierta
        cursor.execute("""
            INSERT OR REPLACE INTO operaciones (trade_id, ticker, option_symbol, position_role, qty, buy_execution_id, sell_execution_id, state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (f"TRD_{setup_id}", ticker, f"{ticker}_SIM_OPT", "PRIMARY", qty, f"EXE_BUY_{setup_id}", None, "OPEN"))
        
        conn.commit()
        return True
    finally:
        conn.close()

def execute_paper_sell(setup_id, ticker, direction, option_return_pct):
    """Simula la venta/liquidación del contrato de opción para un setup finalizado."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        
        # 1. Comprobar si ya existe orden de venta
        cursor.execute("SELECT order_id FROM ordenes WHERE order_id = ?", (f"ORD_SELL_{setup_id}",))
        if cursor.fetchone():
            return False
            
        # Obtener la cantidad de contratos original de la compra
        cursor.execute("SELECT qty FROM ordenes WHERE order_id = ?", (f"ORD_BUY_{setup_id}",))
        row = cursor.fetchone()
        qty = int(row[0]) if row else 1
        
        print(f"[Paper Bot] Ejecutando venta virtual de {qty} contrato(s) para {ticker} ({setup_id}) con retorno: {option_return_pct:+.1f}%...")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 2. Calcular valor de liquidación y sumarlo al capital
        liquidation_value = (CONTRACT_PREMIUM * qty) * (1 + option_return_pct / 100.0)
        net_credit = liquidation_value - (COMMISSION * qty)
        
        update_capital(conn, net_credit)
        
        # 3. Registrar Decisión
        cursor.execute("""
            INSERT OR REPLACE INTO decisiones (decision_id, setup_id, source, action, rejection_reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (f"DEC_SELL_{setup_id}", setup_id, "ALGORITMICA", "SELL", None, now_str))
        
        # 4. Registrar Orden de Venta
        cursor.execute("""
            INSERT OR REPLACE INTO ordenes (order_id, decision_id, option_ticker, qty, limit_price, order_type, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (f"ORD_SELL_{setup_id}", f"DEC_SELL_{setup_id}", f"{ticker}_SIM_OPT", qty, liquidation_value / 100.0 / qty, "MARKET", "COMPLETED"))
        
        # 5. Registrar Ejecución de Venta
        cursor.execute("""
            INSERT OR REPLACE INTO ejecuciones (execution_id, order_id, timestamp, side, qty, price, commission)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (f"EXE_SELL_{setup_id}", f"ORD_SELL_{setup_id}", now_str, "SELL", qty, liquidation_value / 100.0 / qty, COMMISSION * qty))
        
        # 6. Actualizar Operación a Cerrada
        cursor.execute("""
            UPDATE operaciones
            SET sell_execution_id = ?, state = 'CLOSED'
            WHERE trade_id = ?
        """, (f"EXE_SELL_{setup_id}", f"TRD_{setup_id}"))
        
        conn.commit()
        return True
    finally:
        conn.close()

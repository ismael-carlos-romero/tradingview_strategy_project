import sqlite3
import os
import json
import uuid
import time
from datetime import datetime

DB_NAME = "trading_laboratory.db"
COMMISSION_PER_CONTRACT = 0.65 # Comisión fija de uCharts

# Asignación de estrategias a buckets y DTEs.
#
# Fix crítico: este diccionario tenía sólo 9 claves con el prefijo viejo
# "cond_" (cond_canal_break, cond_piso_fuerte, etc.), que ya no coincide con
# NADA del sistema actual. El catálogo real y vigente vive en la tabla
# catalogo_estrategias de trading_laboratory.db y tiene 18 estrategias, todas
# en MAYÚSCULA y sin prefijo (CANAL_BREAK, PISO_FUERTE, COLA_TECHO, etc.) —
# ese es el mismo formato que usa strategy_id en todo el resto de
# live_scanner.py. Como resultado, CUALQUIER estrategia confirmada por el
# escáner rechazaba la compra automática acá, siempre, en el primer chequeo.
#
# Los valores de bucket/DTE para las 9 estrategias que ya existían se
# conservan (mapeadas a su nombre canónico actual). Para las 9 estrategias
# nuevas que no tenían equivalente previo, se propone un default razonable
# por semejanza con la lógica de las estrategias existentes — REVISAR estos
# 9 valores nuevos, porque afectan directamente el tamaño de posición y el
# riesgo de capital asignado a cada trade:
#   COLA_PISO, COLA_TECHO, PM40_BOUNCE, RUPTURA_PISO_GAP, GAP_CONT_PUT -> SHORT_TERM (default propuesto)
#   RUPTURA_RES, RUPTURA_SOP, HANGER_DIARIO -> MEDIUM_TERM (default propuesto)
#   TECHO_FUERTE, PISO_BREAK -> LONG_TERM (default propuesto, espejo de PISO_FUERTE)
STRATEGY_BUCKETS = {
    "CANAL_BREAK": "MEDIUM_TERM",
    "PRIMER_GAP_ALZA": "SHORT_TERM",
    "GAP_NORMAL": "SHORT_TERM",
    "GAP_BAJISTA_ALZA": "SHORT_TERM",
    "CAIDA_BREAK": "MEDIUM_TERM",
    "PISO_FUERTE": "LONG_TERM",
    "VELA_ROJA": "SHORT_TERM",
    "CUATRO_PASOS": "MEDIUM_TERM",
    # --- Nuevas, sin equivalente previo (default propuesto, revisar) ---
    "COLA_PISO": "SHORT_TERM",
    "COLA_TECHO": "SHORT_TERM",
    "PM40_BOUNCE": "SHORT_TERM",
    "RUPTURA_PISO_GAP": "SHORT_TERM",
    "GAP_CONT_PUT": "SHORT_TERM",
    "RUPTURA_RES": "MEDIUM_TERM",
    "RUPTURA_SOP": "MEDIUM_TERM",
    "HANGER_DIARIO": "MEDIUM_TERM",
    "TECHO_FUERTE": "LONG_TERM",
    "PISO_BREAK": "LONG_TERM",
}

STRATEGY_DTE = {
    "CANAL_BREAK": 7,
    "PRIMER_GAP_ALZA": 1,
    "GAP_NORMAL": 1,
    "GAP_BAJISTA_ALZA": 1,
    "CAIDA_BREAK": 7,
    "PISO_FUERTE": 14,
    "VELA_ROJA": 1,
    "CUATRO_PASOS": 7,
    # --- Nuevas, sin equivalente previo (default propuesto, revisar) ---
    "COLA_PISO": 1,
    "COLA_TECHO": 1,
    "PM40_BOUNCE": 1,
    "RUPTURA_PISO_GAP": 1,
    "GAP_CONT_PUT": 1,
    "RUPTURA_RES": 7,
    "RUPTURA_SOP": 7,
    "HANGER_DIARIO": 7,
    "TECHO_FUERTE": 14,
    "PISO_BREAK": 14,
}

# Direcciones correctas de las 18 estrategias (columna 'direction' en
# catalogo_estrategias). Se usa más abajo para determinar CALL/PUT.
STRATEGY_DIRECTION = {
    "GAP_NORMAL": "CALL",
    "GAP_BAJISTA_ALZA": "CALL",
    "PISO_FUERTE": "CALL",
    "PRIMER_GAP_ALZA": "CALL",
    "COLA_PISO": "CALL",
    "PM40_BOUNCE": "CALL",
    "CAIDA_BREAK": "CALL",
    "CANAL_BREAK": "CALL",
    "RUPTURA_RES": "CALL",
    "VELA_ROJA": "PUT",
    "TECHO_FUERTE": "PUT",
    "RUPTURA_PISO_GAP": "PUT",
    "CUATRO_PASOS": "PUT",
    "COLA_TECHO": "PUT",
    "HANGER_DIARIO": "PUT",
    "RUPTURA_SOP": "PUT",
    "PISO_BREAK": "PUT",
    "GAP_CONT_PUT": "PUT",
}

# ==========================================
# 1. LEDGER CONTABLE & RECONCILIACIÓN
# ==========================================

def registrar_movimiento_ledger(conn, tipo_movimiento, monto_debito, monto_credito, trade_id=None, bucket_id=None, estrategia=None, referencia="", cuenta_id='default'):
    """Registra una entrada contable inmutable y recalcula el balance resultante."""
    cursor = conn.cursor()
    
    # Obtener el último balance de esta cuenta en el ledger
    cursor.execute("SELECT balance_resultante FROM ledger_movimientos WHERE cuenta_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT 1", (cuenta_id,))
    row = cursor.fetchone()
    
    if row:
        balance_anterior = float(row[0])
    else:
        # Fallback al balance inicial de la cuenta
        cursor.execute("SELECT balance_inicial FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
        row_acc = cursor.fetchone()
        balance_anterior = float(row_acc[0]) if row_acc else 3884329.04
        
    # Calcular nuevo balance resultante
    balance_resultante = balance_anterior - monto_debito + monto_credito
    
    mov_id = f"MOV_{uuid.uuid4().hex[:12].upper()}"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("""
        INSERT INTO ledger_movimientos (
            mov_id, timestamp, tipo_movimiento, monto_debito, monto_credito, 
            balance_resultante, trade_id, bucket_id, estrategia, referencia, cuenta_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        mov_id, now_str, tipo_movimiento, monto_debito, monto_credito, 
        balance_resultante, trade_id, bucket_id, estrategia, referencia, cuenta_id
    ))
    
    # Sincronizar en cuentas_simuladas
    cursor.execute("UPDATE cuentas_simuladas SET balance_actual = ? WHERE id = ?", (balance_resultante, cuenta_id))
    
    # Si es la cuenta default, sincronizar también con configuracion por retrocompatibilidad
    if cuenta_id == 'default':
      cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val, type) VALUES ('capital_simulado', ?, 'FLOAT')", (str(balance_resultante),))
      try:
          sincronizar_capital_state(conn, cuenta_id)
      except Exception as e:
          print(f"[Ledger Engine] Advertencia: Sincronizacion capital_state fallo: {e}")
        
    return balance_resultante

def conciliar_saldo_ledger(conn, cuenta_id='default'):
    """Reconcilia y reconstruye el balance sumando créditos y restando débitos históricos."""
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(monto_credito), SUM(monto_debito) FROM ledger_movimientos WHERE cuenta_id = ?", (cuenta_id,))
    creditos, debitos = cursor.fetchone()
    creditos = creditos or 0.0
    debitos = debitos or 0.0
    balance_calculado = creditos - debitos
    
    cursor.execute("SELECT balance_actual FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
    row = cursor.fetchone()
    balance_acc = float(row[0]) if row else 0.0
    
    match = abs(balance_calculado - balance_acc) < 0.01
    print(f"[Ledger] Reconciliación Cuenta {cuenta_id}: Calculado: ${balance_calculado:,.2f} | DB: ${balance_acc:,.2f} | Reconciliado: {match}")
    return balance_calculado, match

# ==========================================
# 2. CAPITAL ALLOCATION ENGINE
# ==========================================

def recalcular_buckets_capital(conn, cuenta_id='default'):
    """Sincroniza y redistribuye los saldos de los buckets en base al capital disponible actual."""
    cursor = conn.cursor()
    
    cursor.execute("SELECT balance_actual FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
    row = cursor.fetchone()
    balance_total = float(row[0]) if row else 3884329.04
    
    # Asegurar que existan los buckets de capital asignados para esta cuenta en capital_buckets
    cursor.execute("SELECT COUNT(*) FROM capital_buckets WHERE cuenta_id = ?", (cuenta_id,))
    if cursor.fetchone()[0] == 0:
        print(f"[Capital Engine] Inicializando buckets de capital por defecto para cuenta: {cuenta_id}")
        default_buckets = [
            ("SHORT_TERM", 0.10, "Bolsillo corto plazo (DTE 1)"),
            ("MEDIUM_TERM", 0.20, "Bolsillo mediano plazo (DTE 7)"),
            ("LONG_TERM", 0.30, "Bolsillo largo plazo (DTE 14)"),
            ("RESERVE", 0.30, "Reserva de capital de resguardo"),
            ("EXPERIMENTAL", 0.10, "Bolsillo para setups de alta volatilidad")
        ]
        for bid, pct, desc in default_buckets:
            cursor.execute("""
                INSERT INTO capital_buckets (bucket_id, porcentaje_asignado, capital_disponible, capital_comprometido, descripcion, cuenta_id)
                VALUES (?, ?, ?, 0.0, ?, ?)
            """, (bid, pct, balance_total * pct, desc, cuenta_id))
            
    cursor.execute("SELECT bucket_id, porcentaje_asignado FROM capital_buckets WHERE cuenta_id = ?", (cuenta_id,))
    buckets_data = cursor.fetchall()
    
    for bucket_id, pct in buckets_data:
        # Calcular capital comprometido de las posiciones OPEN en esta cuenta
        cursor.execute("""
            SELECT SUM(cantidad_contratos * (precio_entrada * 100 + ?)) 
            FROM operaciones_simuladas 
            WHERE estado = 'OPEN' AND cuenta_id = ? AND id IN (
                SELECT id FROM operaciones_simuladas WHERE dte_plazo = ?
            )
        """, (COMMISSION_PER_CONTRACT, cuenta_id, 1 if bucket_id == "SHORT_TERM" else 7 if bucket_id == "MEDIUM_TERM" else 14))
        
        comprometido_row = cursor.fetchone()
        comprometido = float(comprometido_row[0]) if comprometido_row and comprometido_row[0] is not None else 0.0
        
        # Disponible
        capital_teorico = balance_total * pct
        disponible = max(0.0, capital_teorico - comprometido)
        
        cursor.execute("""
            UPDATE capital_buckets 
            SET capital_disponible = ?, capital_comprometido = ? 
            WHERE bucket_id = ? AND cuenta_id = ?
        """, (disponible, comprometido, bucket_id, cuenta_id))
    
    conn.commit()

# ==========================================
# 3. MOTOR DE RIESGO & CIRCUIT BREAKERS
# ==========================================

def evaluar_riesgo_pre_trade(conn, ticker, strategy_id, costo_total_operacion, cuenta_id='default'):
    """Evalúa las reglas de riesgo (Risk Engine) antes de autorizar la orden virtual."""
    cursor = conn.cursor()
    
    # 1. Chequear estado del sistema
    cursor.execute("SELECT val FROM configuracion WHERE param_id = 'system_state'")
    row_state = cursor.fetchone()
    sys_state = row_state[0] if row_state else "ARMED"
    
    if sys_state == "STOP":
        return False, "SISTEMA EN STOP: Nuevas operaciones bloqueadas de forma preventiva."
    if sys_state == "DISARMED":
        return False, "SISTEMA EN DISARMED: Autotrade deshabilitado (solo alertas)."
        
    # 2. Obtener capital disponible en el bucket
    bucket_id = STRATEGY_BUCKETS.get(strategy_id, "SHORT_TERM")
    cursor.execute("SELECT capital_disponible FROM capital_buckets WHERE bucket_id = ? AND cuenta_id = ?", (bucket_id, cuenta_id))
    row_bucket = cursor.fetchone()
    cap_disponible = float(row_bucket[0]) if row_bucket else 0.0
    
    if costo_total_operacion > cap_disponible:
        return False, f"Fondos insuficientes en el Bucket {bucket_id}: Disponible: ${cap_disponible:,.2f} | Propuesto: ${costo_total_operacion:,.2f}"
        
    # 3. Circuit Breaker: Drawdown máximo
    cursor.execute("SELECT balance_inicial, balance_actual FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
    row_acc = cursor.fetchone()
    if row_acc:
        bal_inicial = float(row_acc[0])
        bal_actual = float(row_acc[1])
    else:
        bal_inicial = 3884329.04
        bal_actual = 3884329.04
        
    drawdown = (bal_inicial - bal_actual) / bal_inicial * 100 if bal_inicial > 0 else 0
    if drawdown > 15.0: # Drawdown límite del 15%
        return False, f"CIRCUIT BREAKER: Drawdown máximo del 15% excedido (Actual: {drawdown:.2f}%)."
        
    # 4. Circuit Breaker: Máximo número de posiciones abiertas por activo
    cursor.execute("SELECT COUNT(*) FROM operaciones_simuladas WHERE ticker = ? AND estado = 'OPEN' AND cuenta_id = ?", (ticker, cuenta_id))
    if cursor.fetchone()[0] >= 3:
        return False, f"LÍMITE EXCEDIDO: Ya existen 3 posiciones abiertas simultáneas en {ticker}."
        
    return True, "AUTHORIZED"

# ==========================================
# 4. MELIORA SIM BROKER (COMPRA & VENTA)
# ==========================================

def simular_compra_broker(conn, ticker, strategy_id, precio_subyacente, cantidad_propuesta=None, expiry=None, cuenta_id='default'):
    """Ejecuta una compra simulada en el sandbox aplicando comisiones, slippage y ledger contable."""
    if strategy_id not in STRATEGY_BUCKETS:
        return {"status": "REJECTED", "reason": f"Estrategia {strategy_id} no configurada en el Simulador."}
        
    cursor = conn.cursor()
    recalcular_buckets_capital(conn, cuenta_id=cuenta_id)
    
    bucket_id = STRATEGY_BUCKETS[strategy_id]
    dte = STRATEGY_DTE[strategy_id]
    
    # Estimación de prima con Castigo por Slippage (+1.5% de penalización sobre el precio teórico Ask)
    if dte == 1:
        prima_teorica = max(0.50, precio_subyacente * 0.005)
    elif dte == 7:
        prima_teorica = max(1.50, precio_subyacente * 0.012)
    else:
        prima_teorica = max(2.50, precio_subyacente * 0.020)
        
    prima_ejecucion = round(prima_teorica * 1.015, 2) # Slippage / Spread Castigado
    costo_contrato = (prima_ejecucion * 100) + COMMISSION_PER_CONTRACT
    
    # Calcular cantidad de contratos según regla de capital de bolsillos
    cursor.execute("SELECT capital_disponible FROM capital_buckets WHERE bucket_id = ? AND cuenta_id = ?", (bucket_id, cuenta_id))
    cap_disponible = cursor.fetchone()[0]
    
    # Usar máximo 15% del capital del bucket para un solo trade (Sizing Engine)
    monto_destinado = cap_disponible * 0.15
    cantidad = int(monto_destinado / costo_contrato)
    if cantidad <= 0:
        cantidad = 1
        
    # Si viene forzado (por ejemplo, compra piloto)
    if cantidad_propuesta is not None:
        cantidad = cantidad_propuesta
        
    costo_total = cantidad * costo_contrato
    
    # Validar Riesgo
    autorizado, motivo = evaluar_riesgo_pre_trade(conn, ticker, strategy_id, costo_total, cuenta_id=cuenta_id)
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_id = f"TRD_{ticker}_{strategy_id}_{datetime.now().strftime('%M%S')}"
    
    # Registrar decisión del bot
    cursor.execute("""
        INSERT INTO decisiones (decision_id, setup_id, source, action, rejection_reason, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (f"DEC_{trade_id}", f"SET_{trade_id}", "MELIORA_SIM_BROKER", "BUY" if autorizado else "REJECT", motivo if not autorizado else None, now_str))
    
    if not autorizado:
        conn.commit()
        return {"status": "REJECTED", "reason": motivo}
        
    # Ejecución de la Orden en el Sandbox
    # Fix crítico: antes esto era `"CALL" if strategy_id not in ["cond_vela_roja", "cond_4_pasos"] else "PUT"`
    # — una lista de sólo 2 excepciones, de un catálogo viejo de 9 estrategias.
    # Con las 18 estrategias reales del catálogo actual, 9 son PUT y sólo 2
    # estaban contempladas acá: TECHO_FUERTE, RUPTURA_PISO_GAP, COLA_TECHO,
    # HANGER_DIARIO, RUPTURA_SOP, PISO_BREAK y GAP_CONT_PUT se estaban
    # comprando como CALL por error — exactamente lo contrario de lo que
    # correspondía. Se usa ahora el mapa completo STRATEGY_DIRECTION.
    tipo = STRATEGY_DIRECTION.get(strategy_id, "CALL")
    if expiry:
        tipo = f"{expiry} {tipo}"
    
    # Registrar Operación Abierta
    cursor.execute("""
        INSERT INTO operaciones_simuladas (
            id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada, precio_actual, 
            pnl_pct, pnl_usd, estado, fecha_apertura, fecha_cierre, dte_plazo, targets_alcanzados, balance_referencia, cuenta_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trade_id, ticker, tipo, strategy_id, cantidad, prima_ejecucion, prima_ejecucion,
        0.0, 0.0, 'OPEN', now_str, None, dte, '[]', cap_disponible, cuenta_id
    ))
    
    # Escribir Asiento Contable en el Ledger
    registrar_movimiento_ledger(
        conn=conn,
        tipo_movimiento="TRADE_OPEN",
        monto_debito=costo_total,
        monto_credito=0.0,
        trade_id=trade_id,
        bucket_id=bucket_id,
        estrategia=strategy_id,
        referencia=f"COMPRA SIMULADA: {cantidad} contratos de {ticker} {tipo} (Prima: ${prima_ejecucion:.2f})",
        cuenta_id=cuenta_id
    )
    
    # Actualizar buckets
    recalcular_buckets_capital(conn, cuenta_id=cuenta_id)
    conn.commit()
    
    return {"status": "FILLED", "trade_id": trade_id, "qty": cantidad, "price": prima_ejecucion, "cost": costo_total}

def simular_venta_broker(conn, trade_id, precio_salida_subyacente):
    """Cierra la operación simulada, calcula el P&L, registra en Ledger y aplica desvío de ganancias 90/10."""
    cursor = conn.cursor()
    
    # Asegurar columna cuenta_id en cuenta_corriente_movimientos
    try:
        cursor.execute("ALTER TABLE cuenta_corriente_movimientos ADD COLUMN cuenta_id TEXT DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass

    cursor.execute("""
        SELECT ticker, tipo, estrategia, cantidad_contratos, precio_entrada, dte_plazo, fecha_apertura, balance_referencia, cuenta_id 
        FROM operaciones_simuladas WHERE id = ? AND estado = 'OPEN'
    """, (trade_id,))
    pos = cursor.fetchone()
    if not pos:
        return {"status": "ERROR", "message": "No se encontró la posición abierta."}
        
    ticker, tipo, estrategia, cantidad, precio_entrada, dte, fecha_apertura, balance_ref, cuenta_id = pos
    bucket_id = STRATEGY_BUCKETS[estrategia]
    
    # Estimación de precio de salida de la opción (Slippage Castigado del -1.5% sobre el precio Bid estimado)
    cursor.execute("SELECT price FROM radar_actual WHERE ticker = ? LIMIT 1", (ticker,))
    radar_row = cursor.fetchone()
    precio_entrada_sub = radar_row[0] if radar_row else precio_salida_subyacente * 0.99
    
    leverage = 12 if dte == 1 else 8 if dte == 7 else 5
    var_sub = (precio_salida_subyacente - precio_entrada_sub) / precio_entrada_sub
    pnl_pct_teorico = (var_sub if "CALL" in tipo else -var_sub) * leverage * 100
    pnl_pct_teorico = max(-98.0, min(250.0, pnl_pct_teorico))
    
    # Aplicar castigo por slippage de venta (-1.5%)
    pnl_pct_real = pnl_pct_teorico - 1.5
    precio_salida_opcion = max(0.01, round(precio_entrada * (1 + pnl_pct_real / 100), 2))
    
    costo_entrada_total = cantidad * (precio_entrada * 100 + COMMISSION_PER_CONTRACT)
    retorno_bruto = cantidad * (precio_salida_opcion * 100 - COMMISSION_PER_CONTRACT)
    pnl_usd = retorno_bruto - costo_entrada_total
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 1. Registrar cierre en el Ledger Contable (Acreditación del retorno bruto)
    registrar_movimiento_ledger(
        conn=conn,
        tipo_movimiento="TRADE_CLOSE",
        monto_debito=0.0,
        monto_credito=retorno_bruto,
        trade_id=trade_id,
        bucket_id=bucket_id,
        estrategia=estrategia,
        referencia=f"VENTA SIMULADA: {cantidad} contratos de {ticker} {tipo} (Prima: ${precio_salida_opcion:.2f})",
        cuenta_id=cuenta_id
    )
    
    # 2. Aplicar la Regla 90/10 sobre la GANANCIA REALIZADA (si es positiva)
    monto_retiro = 0.0
    if pnl_usd > 0:
        monto_retiro = pnl_usd * 0.10 # Desvío del 10% para la cuenta corriente
        
        # Debitar del Ledger de Trading
        registrar_movimiento_ledger(
            conn=conn,
            tipo_movimiento="WITHDRAWAL_ALLOCATION",
            monto_debito=monto_retiro,
            monto_credito=0.0,
            trade_id=trade_id,
            bucket_id=bucket_id,
            estrategia=estrategia,
            referencia=f"DESVÍO 10% DE GANANCIA: Cuenta Corriente (Retiro)",
            cuenta_id=cuenta_id
        )
        
        # Acreditar en la cuenta corriente de retiro de esta cuenta
        cursor.execute("SELECT balance_acumulado FROM cuenta_corriente_movimientos WHERE cuenta_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT 1", (cuenta_id,))
        cc_row = cursor.fetchone()
        cc_balance_prev = float(cc_row[0]) if cc_row else 0.0
        cc_balance_new = cc_balance_prev + monto_retiro
        
        cursor.execute("""
            INSERT INTO cuenta_corriente_movimientos (mov_id, timestamp, trade_id, monto, balance_acumulado, estrategia, bot_id, cuenta_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (f"CC_{uuid.uuid4().hex[:12].upper()}", now_str, trade_id, monto_retiro, cc_balance_new, estrategia, "BOT_MELIORA_SIM", cuenta_id))
        print(f"[Ledger] Ganancia Realizada: ${pnl_usd:,.2f} | 10% Enviado a Cuenta Corriente: ${monto_retiro:,.2f}")
        
    # 3. Marcar como posición cerrada
    cursor.execute("""
        UPDATE operaciones_simuladas 
        SET precio_actual = ?, pnl_pct = ?, pnl_usd = ?, estado = 'CLOSED', fecha_cierre = ? 
        WHERE id = ?
    """, (precio_salida_opcion, pnl_pct_real, pnl_usd, now_str, trade_id))
    
    # Recalcular buckets
    recalcular_buckets_capital(conn, cuenta_id=cuenta_id)
    conn.commit()
    
    return {
        "status": "CLOSED",
        "trade_id": trade_id,
        "pnl_pct": pnl_pct_real,
        "pnl_usd": pnl_usd,
        "withdrawal": monto_retiro,
        "return_net": retorno_bruto - monto_retiro
    }

def agregar_fondos_broker(conn, cuenta_id, monto):
    """Agrega fondos a una cuenta simulada a través de un depósito manual en el Ledger."""
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
    if not cursor.fetchone():
        return {"status": "ERROR", "message": f"La cuenta {cuenta_id} no existe."}
        
    balance_resultante = registrar_movimiento_ledger(
        conn=conn,
        tipo_movimiento="DEPOSIT",
        monto_debito=0.0,
        monto_credito=monto,
        referencia=f"DEPÓSITO MANUAL DE FONDOS: +${monto:,.2f}",
        cuenta_id=cuenta_id
    )
    
    recalcular_buckets_capital(conn, cuenta_id=cuenta_id)
    conn.commit()
    return {"status": "SUCCESS", "new_balance": balance_resultante}

def sincronizar_capital_state(conn, cuenta_id='default'):
    """Consolida las métricas del Ledger y las sincroniza en la tabla de estado de capital global."""
    cursor = conn.cursor()
    
    # 1. Obtener balance de trading (capital reinvertible)
    cursor.execute("SELECT balance_actual FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
    row_acc = cursor.fetchone()
    balance_actual = float(row_acc[0]) if row_acc else 3884329.04
    
    # 2. Obtener acumulado retirado (cuenta corriente)
    cursor.execute("SELECT balance_acumulado FROM cuenta_corriente_movimientos WHERE cuenta_id = ? ORDER BY timestamp DESC, rowid DESC LIMIT 1", (cuenta_id,))
    row_cc = cursor.fetchone()
    cc_acumulado = float(row_cc[0]) if row_cc else 0.0
    
    # 3. Obtener capital comprometido (posiciones OPEN)
    cursor.execute("""
        SELECT SUM(cantidad_contratos * (precio_entrada * 100 + ?)) 
        FROM operaciones_simuladas 
        WHERE estado = 'OPEN' AND cuenta_id = ?
    """, (COMMISSION_PER_CONTRACT, cuenta_id))
    row_comp = cursor.fetchone()
    capital_comprometido = float(row_comp[0]) if row_comp and row_comp[0] is not None else 0.0
    
    # Capital total es el capital de trading mas el acumulado retirado
    capital_total = balance_actual + cc_acumulado
    
    # Sincronizar en la tabla de capital_state con ID = 1
    cursor.execute("""
        INSERT OR REPLACE INTO capital_state (id, capital_total, capital_reinvertible, capital_retirado, capital_comprometido)
        VALUES (1, ?, ?, ?, ?)
    """, (capital_total, balance_actual, cc_acumulado, capital_comprometido))

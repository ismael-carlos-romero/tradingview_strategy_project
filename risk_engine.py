"""
risk_engine.py
================
Motor de Riesgo de Meliora Options -- independiente del detector de estrategias.

Ninguna orden nueva puede llegar a operaciones_simuladas sin pasar por
evaluar_orden_nueva(). Este modulo NO decide que comprar ni opina sobre
senales: solo autoriza, reduce o rechaza ordenes, y gestiona el kill switch
y el candado de perdida diaria. La decision de que comprar sigue siendo
100% del detector de estrategias en live_scanner.py (sin tocar).

Este sistema opera EXCLUSIVAMENTE en modo Paper/Shadow sobre
trading_laboratory.db. MODE_LIVE_TRADING_ENABLED debe permanecer en False:
no hay ejecucion automatica real en Interactive Brokers habilitada por este
modulo bajo ninguna circunstancia. Habilitar Live es una decision humana
explicita, fuera de este archivo, y no se implementa aca.
"""
import json
import os
import uuid
import sqlite3
from datetime import datetime, timedelta

DB_NAME = "trading_laboratory.db"
_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Guardia explicita: este modulo nunca autoriza ejecucion real en IBKR Live.
MODE_LIVE_TRADING_ENABLED = False

_DEFAULT_RISK_CONFIG = {
    "daily_budget_pct": 0.10,
    "max_total_open_exposure_pct": 0.15,
    "max_position_pct": 0.02,
    "max_live_contracts": 1,
    "daily_max_loss_pct": 0.02,
    "allow_overnight_default": False,
    "time_stop_minutes_intraday": 240,
    "time_stop_minutes_swing": 4320,
    "expiration_guard_minutes_before_close": 60,
    "duplicate_order_debounce_seconds": 60,
    "sl_pct_by_scenario": {"conservative": -10.0, "pilot": -15.0, "aggressive": -20.0},
    "tp_pct_by_scenario": {"conservative": 20.0, "pilot": 30.0, "aggressive": 50.0},
    "default_scenario": "pilot",
}


def get_risk_config():
    """Lee config.json -> risk_management, sobre defaults seguros. Nunca lanza excepcion."""
    cfg = json.loads(json.dumps(_DEFAULT_RISK_CONFIG))  # deep copy simple
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            full = json.load(f)
        user_cfg = full.get("risk_management", {})
        for k, v in user_cfg.items():
            if k in ("sl_pct_by_scenario", "tp_pct_by_scenario") and isinstance(v, dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    except Exception as e:
        print(f"[RiskEngine] No se pudo leer risk_management de config.json, usando defaults: {e}")
    return cfg


def init_risk_tables(conn):
    """Crea (si no existen) las tablas nuevas del RiskEngine/PositionManager.
    Idempotente y aditivo -- nunca toca tablas existentes."""
    cursor = conn.cursor()

    # Bug preexistente (ver comentario de fix del 10/09 en live_scanner.py):
    # la tabla capital_diario_control desplegada en produccion nunca tuvo
    # columna "id", aunque el CREATE TABLE IF NOT EXISTS de init_simulation_tables()
    # ya la define -- SQLite no altera tablas ya creadas. La reparamos aca de
    # forma aditiva (ALTER TABLE) y migramos filas viejas a id='default', que
    # era la unica cuenta implicita que existia antes del soporte multi-cuenta.
    try:
        cursor.execute("ALTER TABLE capital_diario_control ADD COLUMN id TEXT")
        cursor.execute("UPDATE capital_diario_control SET id = 'default' WHERE id IS NULL")
    except sqlite3.OperationalError:
        pass  # La columna ya existe

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_audit_log (
            audit_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            trade_id TEXT,
            ticker TEXT,
            strategy_id TEXT,
            cuenta_id TEXT,
            event_type TEXT NOT NULL,
            detail TEXT,
            actor TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_risk_state (
            fecha TEXT NOT NULL,
            cuenta_id TEXT NOT NULL,
            daily_locked INTEGER DEFAULT 0,
            lock_reason TEXT,
            realized_pnl_dia REAL DEFAULT 0.0,
            updated_at TEXT,
            PRIMARY KEY (fecha, cuenta_id)
        )
    """)
    conn.commit()


def registrar_auditoria(conn, actor, event_type, detail, trade_id=None, ticker=None, strategy_id=None, cuenta_id=None):
    """Escribe un evento inmutable en risk_audit_log. Nunca lanza excepcion hacia afuera."""
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO risk_audit_log (audit_id, timestamp, trade_id, ticker, strategy_id, cuenta_id, event_type, detail, actor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f"AUD_{uuid.uuid4().hex[:12].upper()}",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            trade_id, ticker, strategy_id, cuenta_id, event_type, detail, actor,
        ))
    except Exception as e:
        print(f"[RiskEngine] No se pudo registrar auditoria ({event_type}): {e}")


# ==========================================
# Kill switch unificado (Requisito #11)
# ==========================================
# Antes existian DOS flags de kill switch desconectados:
#   - system_settings.allow_new_trades: lo togglea el endpoint
#     /api/system/kill-switch, pero solo se LEIA para reportar en
#     /api/system/health -- nunca bloqueaba nada de verdad.
#   - configuracion.system_state (ARMED/STOP/DISARMED): el UNICO flag que
#     efectivamente bloquea (evaluar_riesgo_pre_trade en sim_broker_core.py,
#     y el gate de encolamiento en live_scanner.py).
# A partir de este refactor, configuracion.system_state sigue siendo la
# UNICA fuente de verdad que bloquea ordenes nuevas, y activar/desactivar el
# kill switch actualiza TAMBIEN system_settings para no romper el reporting
# existente de /api/system/health. Cerrar posiciones EXISTENTES sigue
# requiriendo una accion separada (emergency_close), tal como ya funcionaba.

def kill_switch_activo(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT val FROM configuracion WHERE param_id = 'system_state'")
    row = cursor.fetchone()
    estado = row[0] if row else "ARMED"
    return estado in ("STOP", "DISARMED"), estado


def activar_kill_switch(conn, motivo="", actor="RISK_ENGINE"):
    """Bloquea NUEVAS ordenes de inmediato. NO cierra posiciones existentes."""
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('system_state', 'STOP')")
    try:
        cursor.execute("""
            INSERT INTO system_settings (id, allow_new_trades, kill_switch_reason, updated_by, updated_at)
            VALUES (1, 0, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET allow_new_trades = 0, kill_switch_reason = excluded.kill_switch_reason,
                updated_by = excluded.updated_by, updated_at = excluded.updated_at
        """, (motivo, actor, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    except Exception as e:
        print(f"[RiskEngine] Aviso: no se pudo sincronizar system_settings al activar kill switch: {e}")
    registrar_auditoria(conn, actor, "KILL_SWITCH_ON", motivo)
    conn.commit()


def desactivar_kill_switch(conn, actor="OPERADOR"):
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO configuracion (param_id, val) VALUES ('system_state', 'ARMED')")
    try:
        cursor.execute("""
            INSERT INTO system_settings (id, allow_new_trades, kill_switch_reason, updated_by, updated_at)
            VALUES (1, 1, NULL, ?, ?)
            ON CONFLICT(id) DO UPDATE SET allow_new_trades = 1, kill_switch_reason = NULL,
                updated_by = excluded.updated_by, updated_at = excluded.updated_at
        """, (actor, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    except Exception as e:
        print(f"[RiskEngine] Aviso: no se pudo sincronizar system_settings al desactivar kill switch: {e}")
    registrar_auditoria(conn, actor, "KILL_SWITCH_OFF", "Reactivado manualmente")
    conn.commit()


# ==========================================
# Presupuesto diario bruto (Requisito #1)
# ==========================================

def _hoy():
    return datetime.now().strftime("%Y-%m-%d")


def obtener_o_crear_cupo_diario(conn, cuenta_id, balance_actual):
    """Devuelve (cupo_disponible, cupo_gastado, balance_inicial_dia) para HOY.
    Se crea una unica vez por dia y cuenta; balance_inicial_dia queda fijo
    durante todo el dia (no se recalcula con cada venta)."""
    cursor = conn.cursor()
    hoy = _hoy()
    cursor.execute("""
        SELECT cupo_disponible, cupo_gastado, balance_inicial FROM capital_diario_control
        WHERE fecha = ? AND id = ?
    """, (hoy, cuenta_id))
    row = cursor.fetchone()
    if row:
        return float(row[0]), float(row[1]), float(row[2])

    cfg = get_risk_config()
    cupo_total = balance_actual * cfg["daily_budget_pct"]
    cursor.execute("""
        INSERT INTO capital_diario_control (fecha, id, balance_inicial, cupo_disponible, cupo_gastado)
        VALUES (?, ?, ?, ?, 0.0)
    """, (hoy, cuenta_id, balance_actual, cupo_total))
    conn.commit()
    return cupo_total, 0.0, balance_actual


def consumir_cupo_diario(conn, cuenta_id, monto):
    """Descuenta 'monto' del cupo diario bruto. Las VENTAS nunca llaman a esto
    -- el presupuesto diario bruto no se restituye con cierres (Requisito #1)."""
    cursor = conn.cursor()
    hoy = _hoy()
    cursor.execute("""
        UPDATE capital_diario_control
        SET cupo_disponible = MAX(0.0, cupo_disponible - ?), cupo_gastado = cupo_gastado + ?
        WHERE fecha = ? AND id = ?
    """, (monto, monto, hoy, cuenta_id))
    conn.commit()


# ==========================================
# Candado de perdida diaria maxima (Requisito #7)
# ==========================================

def chequear_perdida_diaria_maxima(conn, cuenta_id, balance_inicial_dia):
    """Si el P&L realizado de HOY (ventas) supera el limite negativo
    configurado, bloquea NUEVAS entradas (DAILY_LOCKED) pero NO cierra
    posiciones existentes. Se debe llamar periodicamente (tracker loop) y
    tambien antes de autorizar cualquier compra."""
    cfg = get_risk_config()
    cursor = conn.cursor()
    hoy = _hoy()

    cursor.execute("""
        SELECT COALESCE(SUM(monto_credito), 0) - COALESCE(SUM(monto_debito), 0)
        FROM ledger_movimientos
        WHERE cuenta_id = ? AND tipo_movimiento IN ('TRADE_OPEN', 'TRADE_CLOSE') AND timestamp LIKE ?
    """, (cuenta_id, hoy + "%"))
    row = cursor.fetchone()
    pnl_realizado_dia = float(row[0]) if row and row[0] is not None else 0.0

    limite_negativo = -abs(balance_inicial_dia * cfg["daily_max_loss_pct"])
    locked = pnl_realizado_dia <= limite_negativo
    lock_reason = f"P&L realizado del dia (${pnl_realizado_dia:,.2f}) <= limite (${limite_negativo:,.2f})" if locked else None

    cursor.execute("SELECT daily_locked FROM daily_risk_state WHERE fecha = ? AND cuenta_id = ?", (hoy, cuenta_id))
    prev_row = cursor.fetchone()
    estaba_locked_antes = bool(prev_row[0]) if prev_row else False

    cursor.execute("""
        INSERT INTO daily_risk_state (fecha, cuenta_id, daily_locked, lock_reason, realized_pnl_dia, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(fecha, cuenta_id) DO UPDATE SET
            daily_locked = excluded.daily_locked, lock_reason = excluded.lock_reason,
            realized_pnl_dia = excluded.realized_pnl_dia, updated_at = excluded.updated_at
    """, (hoy, cuenta_id, 1 if locked else 0, lock_reason, pnl_realizado_dia, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()

    just_locked = locked and not estaba_locked_antes
    if just_locked:
        registrar_auditoria(conn, "RISK_ENGINE", "DAILY_MAX_LOSS_LOCK", lock_reason, cuenta_id=cuenta_id)
        conn.commit()

    return locked, pnl_realizado_dia, just_locked


def esta_bloqueado_por_perdida_diaria(conn, cuenta_id):
    cursor = conn.cursor()
    cursor.execute("SELECT daily_locked, lock_reason FROM daily_risk_state WHERE fecha = ? AND cuenta_id = ?", (_hoy(), cuenta_id))
    row = cursor.fetchone()
    if not row:
        return False, None
    return bool(row[0]), row[1]


# ==========================================
# Evaluacion de ordenes nuevas (Requisitos #1, #2, #3)
# ==========================================

def evaluar_orden_nueva(conn, cuenta_id, ticker, strategy_id, cantidad_propuesta, costo_por_contrato, balance_actual, capital_comprometido_total_cuenta):
    """Punto de entrada UNICO para autorizar/reducir/rechazar una orden de
    compra nueva. Devuelve dict:
      {authorized, cantidad_final, costo_total_final, reason, adjustments: [..]}
    Ninguna estrategia puede saltarse esto: sim_broker_core.simular_compra_broker
    debe llamarlo SIEMPRE antes de insertar una posicion."""
    cfg = get_risk_config()
    adjustments = []

    bloqueado, motivo_kill = kill_switch_activo(conn)
    if bloqueado:
        return {"authorized": False, "cantidad_final": 0, "costo_total_final": 0.0,
                "reason": f"KILL SWITCH / system_state={motivo_kill}: nuevas ordenes bloqueadas.", "adjustments": []}

    _, _, balance_inicial_dia = obtener_o_crear_cupo_diario(conn, cuenta_id, balance_actual)
    locked, lock_reason = esta_bloqueado_por_perdida_diaria(conn, cuenta_id)
    if locked:
        return {"authorized": False, "cantidad_final": 0, "costo_total_final": 0.0,
                "reason": f"DAILY_LOCKED: {lock_reason}", "adjustments": []}

    # Anti-duplicados: no permitir 2 posiciones OPEN del mismo ticker+estrategia
    # en la misma cuenta abiertas en los ultimos N segundos (Requisito #13 test list).
    # OJO: el corte se calcula en Python (hora LOCAL), igual que fecha_apertura
    # en todo el resto del proyecto -- SQLite datetime('now') es UTC, y
    # comparar una fecha_apertura local contra un corte UTC daba falsos
    # negativos (nunca detectaba duplicados) en cualquier huso horario
    # distinto de UTC+0. Confirmado con test_risk_engine.py en esta maquina.
    cursor = conn.cursor()
    corte = (datetime.now() - timedelta(seconds=cfg["duplicate_order_debounce_seconds"])).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        SELECT COUNT(*) FROM operaciones_simuladas
        WHERE ticker = ? AND estrategia = ? AND cuenta_id = ? AND estado = 'OPEN'
        AND fecha_apertura >= ?
    """, (ticker, strategy_id, cuenta_id, corte))
    if cursor.fetchone()[0] > 0:
        return {"authorized": False, "cantidad_final": 0, "costo_total_final": 0.0,
                "reason": f"ORDEN DUPLICADA: ya existe una posicion OPEN de {ticker}/{strategy_id} abierta en los ultimos {cfg['duplicate_order_debounce_seconds']}s.",
                "adjustments": []}

    cantidad = cantidad_propuesta


    # Requisito #3: tamano maximo por posicion (% del capital de la cuenta)
    max_costo_posicion = balance_actual * cfg["max_position_pct"]
    max_qty_posicion = int(max_costo_posicion / costo_por_contrato) if costo_por_contrato > 0 else 0
    if max_qty_posicion < cantidad:
        adjustments.append(f"MAX_POSITION_PCT ({cfg['max_position_pct']*100:.1f}%): reducido de {cantidad} a {max_qty_posicion} contratos.")
        cantidad = max_qty_posicion

    # Requisito #2: exposicion total abierta maxima (% del capital de la cuenta)
    max_exposicion_total = balance_actual * cfg["max_total_open_exposure_pct"]
    headroom_exposicion = max(0.0, max_exposicion_total - capital_comprometido_total_cuenta)
    max_qty_exposicion = int(headroom_exposicion / costo_por_contrato) if costo_por_contrato > 0 else 0
    if max_qty_exposicion < cantidad:
        adjustments.append(f"MAX_TOTAL_OPEN_EXPOSURE_PCT ({cfg['max_total_open_exposure_pct']*100:.1f}%): reducido de {cantidad} a {max_qty_exposicion} contratos.")
        cantidad = max_qty_exposicion

    # Requisito #1: presupuesto diario bruto (nunca se restituye con ventas)
    cupo_disponible, _, _ = obtener_o_crear_cupo_diario(conn, cuenta_id, balance_actual)
    max_qty_cupo = int(cupo_disponible / costo_por_contrato) if costo_por_contrato > 0 else 0
    if max_qty_cupo < cantidad:
        adjustments.append(f"DAILY_BUDGET ({cfg['daily_budget_pct']*100:.1f}% diario, disponible ${cupo_disponible:,.2f}): reducido de {cantidad} a {max_qty_cupo} contratos.")
        cantidad = max_qty_cupo

    if cantidad <= 0:
        motivo = adjustments[-1] if adjustments else "Sin cupo/capital disponible."
        registrar_auditoria(conn, "RISK_ENGINE", "ORDER_REJECTED", motivo, ticker=ticker, strategy_id=strategy_id, cuenta_id=cuenta_id)
        return {"authorized": False, "cantidad_final": 0, "costo_total_final": 0.0, "reason": motivo, "adjustments": adjustments}

    costo_total_final = cantidad * costo_por_contrato
    consumir_cupo_diario(conn, cuenta_id, costo_total_final)

    evento = "ORDER_REDUCED" if adjustments else "ORDER_AUTHORIZED"
    registrar_auditoria(conn, "RISK_ENGINE", evento,
                         f"Cantidad final: {cantidad} (propuesta: {cantidad_propuesta}). " + " | ".join(adjustments),
                         ticker=ticker, strategy_id=strategy_id, cuenta_id=cuenta_id)

    return {"authorized": True, "cantidad_final": cantidad, "costo_total_final": costo_total_final,
            "reason": "AUTHORIZED" if not adjustments else "AUTHORIZED_REDUCED", "adjustments": adjustments}

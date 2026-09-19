"""
test_risk_engine.py
=====================
Suite de pruebas del RiskEngine/PositionManager (Requisito #13).

No usa pytest (evita depender de una instalacion de pytest en la maquina del
usuario) -- son funciones test_* con asserts simples, ejecutadas por un
runner minimo al final del archivo. Cada test crea su PROPIA base de datos
SQLite temporal con el subconjunto de esquema que el codigo realmente toca,
así que nunca tocan trading_laboratory.db real.

Ejecutar con:  python test_risk_engine.py
"""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import risk_engine
import position_manager
import sim_broker_core


SCHEMA = """
CREATE TABLE cuentas_simuladas (
    id TEXT PRIMARY KEY, nombre TEXT, balance_inicial REAL, balance_actual REAL, creation_time TEXT
);
CREATE TABLE capital_buckets (
    bucket_id TEXT, porcentaje_asignado REAL, capital_disponible REAL, capital_comprometido REAL,
    descripcion TEXT, cuenta_id TEXT
);
CREATE TABLE operaciones_simuladas (
    id TEXT PRIMARY KEY, ticker TEXT, tipo TEXT, estrategia TEXT, cantidad_contratos INTEGER,
    precio_entrada REAL, precio_actual REAL, pnl_pct REAL, pnl_usd REAL, estado TEXT,
    fecha_apertura TEXT, fecha_cierre TEXT, dte_plazo INTEGER, targets_alcanzados TEXT,
    balance_referencia REAL, cuenta_id TEXT
);
CREATE TABLE ledger_movimientos (
    mov_id TEXT PRIMARY KEY, timestamp TEXT, tipo_movimiento TEXT, monto_debito REAL, monto_credito REAL,
    balance_resultante REAL, trade_id TEXT, bucket_id TEXT, estrategia TEXT, referencia TEXT, cuenta_id TEXT
);
CREATE TABLE configuracion (param_id TEXT PRIMARY KEY, val TEXT, type TEXT);
CREATE TABLE system_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), allow_new_trades BOOLEAN DEFAULT 1,
    kill_switch_reason TEXT, updated_at TEXT, updated_by TEXT
);
CREATE TABLE capital_diario_control (
    fecha TEXT, balance_inicial REAL, cupo_disponible REAL, cupo_gastado REAL
);
CREATE TABLE cuenta_corriente_movimientos (
    mov_id TEXT PRIMARY KEY, timestamp TEXT, trade_id TEXT, monto REAL, balance_acumulado REAL,
    estrategia TEXT, bot_id TEXT, cuenta_id TEXT
);
CREATE TABLE decisiones (
    decision_id TEXT PRIMARY KEY, setup_id TEXT, source TEXT, action TEXT, rejection_reason TEXT, timestamp TEXT
);
CREATE TABLE radar_actual (ticker TEXT, price REAL);
CREATE TABLE capital_state (
    id INTEGER PRIMARY KEY DEFAULT 1, capital_total REAL, capital_reinvertible REAL,
    capital_retirado REAL, capital_comprometido REAL
);
"""

RESULTS = []


def nueva_db(balance=1000000.0, cuenta_id="default"):
    path = tempfile.mktemp(suffix=".db")
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO cuentas_simuladas (id, nombre, balance_inicial, balance_actual, creation_time) VALUES (?, ?, ?, ?, datetime('now'))",
        (cuenta_id, cuenta_id, balance, balance),
    )
    conn.execute("INSERT INTO configuracion (param_id, val, type) VALUES ('system_state', 'ARMED', 'TEXT')")
    conn.execute("INSERT INTO configuracion (param_id, val, type) VALUES ('capital_simulado', ?, 'FLOAT')", (str(balance),))
    conn.execute("INSERT INTO system_settings (id, allow_new_trades, updated_by) VALUES (1, 1, 'SYSTEM')")
    conn.execute("INSERT INTO radar_actual (ticker, price) VALUES ('SPY', 500.0)")
    conn.commit()
    risk_engine.init_risk_tables(conn)
    position_manager.init_position_columns(conn)
    sim_broker_core.recalcular_buckets_capital(conn, cuenta_id=cuenta_id)
    return conn, path


def check(nombre, condicion, detalle=""):
    RESULTS.append((nombre, bool(condicion), detalle))
    print(f"{'PASS' if condicion else 'FAIL'} - {nombre}" + (f" :: {detalle}" if detalle and not condicion else ""))


def test_max_position_pct():
    conn, path = nueva_db(balance=1_000_000.0)
    r = risk_engine.evaluar_orden_nueva(conn, "default", "SPY", "GAP_NORMAL", 1000, 100.0, 1_000_000.0, 0.0)
    check("max_position_pct reduce cantidad a ~2% del capital", r["authorized"] and r["cantidad_final"] == 200,
          f"cantidad_final={r['cantidad_final']}, adjustments={r['adjustments']}")
    conn.close()
    os.remove(path)


def test_max_total_open_exposure_pct():
    conn, path = nueva_db(balance=1_000_000.0)
    # 145,000 ya comprometidos de un cap de 150,000 (15%) -> headroom=5,000
    r = risk_engine.evaluar_orden_nueva(conn, "default", "SPY", "GAP_NORMAL", 100, 100.0, 1_000_000.0, 145_000.0)
    check("max_total_open_exposure_pct reduce cantidad al headroom disponible", r["authorized"] and r["cantidad_final"] == 50,
          f"cantidad_final={r['cantidad_final']}, adjustments={r['adjustments']}")
    conn.close()
    os.remove(path)


def test_daily_budget_reduces_and_blocks():
    conn, path = nueva_db(balance=1_000_000.0)
    # Consumir 97,000 del cupo diario de 100,000 (10%) -> quedan 3,000
    risk_engine.obtener_o_crear_cupo_diario(conn, "default", 1_000_000.0)
    risk_engine.consumir_cupo_diario(conn, "default", 97_000.0)
    r = risk_engine.evaluar_orden_nueva(conn, "default", "SPY", "GAP_NORMAL", 60, 100.0, 1_000_000.0, 0.0)
    check("daily_budget reduce cantidad al remanente del cupo", r["authorized"] and r["cantidad_final"] == 30,
          f"cantidad_final={r['cantidad_final']}, adjustments={r['adjustments']}")

    # Agotar el cupo por completo -> rechazo total
    risk_engine.consumir_cupo_diario(conn, "default", 100_000.0)
    r2 = risk_engine.evaluar_orden_nueva(conn, "default", "SPY", "GAP_NORMAL", 1, 100.0, 1_000_000.0, 0.0)
    check("daily_budget agotado bloquea nuevas compras por completo", not r2["authorized"], r2["reason"])
    conn.close()
    os.remove(path)


def test_capital_recycling_no_restituye_cupo():
    """Requisito #1: las VENTAS no restituyen el presupuesto diario bruto."""
    conn, path = nueva_db(balance=1_000_000.0)
    res_buy = sim_broker_core.simular_compra_broker(conn, "SPY", "GAP_NORMAL", 500.0, cuenta_id="default")
    check("compra autorizada para test de reciclado de capital", res_buy.get("status") == "FILLED", res_buy)

    cupo_antes, _, _ = risk_engine.obtener_o_crear_cupo_diario(conn, "default", 1_000_000.0)

    res_sell = sim_broker_core.simular_venta_broker(conn, res_buy["trade_id"], 520.0)
    check("venta se cierra correctamente", res_sell.get("status") == "CLOSED", res_sell)

    cupo_despues, _, _ = risk_engine.obtener_o_crear_cupo_diario(conn, "default", 1_000_000.0)
    check("cupo_disponible NO aumenta despues de una venta (no se restituye)", cupo_despues == cupo_antes,
          f"antes={cupo_antes}, despues={cupo_despues}")
    conn.close()
    os.remove(path)


def test_duplicate_order_rejected():
    conn, path = nueva_db(balance=1_000_000.0)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO operaciones_simuladas (id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada,
            precio_actual, pnl_pct, pnl_usd, estado, fecha_apertura, dte_plazo, targets_alcanzados, cuenta_id)
        VALUES ('T1', 'SPY', 'CALL', 'GAP_NORMAL', 10, 5.0, 5.0, 0.0, 0.0, 'OPEN', ?, 1, '[]', 'default')
    """, (now_str,))
    conn.commit()
    r = risk_engine.evaluar_orden_nueva(conn, "default", "SPY", "GAP_NORMAL", 10, 100.0, 1_000_000.0, 0.0)
    check("orden duplicada (mismo ticker+estrategia+cuenta reciente) es rechazada", not r["authorized"], r["reason"])
    conn.close()
    os.remove(path)


def test_kill_switch_bloquea_y_desbloquea():
    conn, path = nueva_db(balance=1_000_000.0)
    risk_engine.activar_kill_switch(conn, motivo="Prueba", actor="TEST")
    r = risk_engine.evaluar_orden_nueva(conn, "default", "SPY", "GAP_NORMAL", 10, 100.0, 1_000_000.0, 0.0)
    check("kill switch activo bloquea nuevas ordenes", not r["authorized"], r["reason"])

    row = conn.execute("SELECT allow_new_trades FROM system_settings WHERE id=1").fetchone()
    check("kill switch sincroniza system_settings.allow_new_trades=0", row[0] == 0, row)

    risk_engine.desactivar_kill_switch(conn, actor="TEST")
    r2 = risk_engine.evaluar_orden_nueva(conn, "default", "SPY", "GAP_NORMAL", 10, 100.0, 1_000_000.0, 0.0)
    check("desactivar kill switch permite ordenes de nuevo", r2["authorized"], r2["reason"])
    conn.close()
    os.remove(path)


def test_daily_max_loss_lock_no_cierra_posiciones_existentes():
    conn, path = nueva_db(balance=1_000_000.0)
    risk_engine.obtener_o_crear_cupo_diario(conn, "default", 1_000_000.0)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Posicion existente que NO debe tocarse
    conn.execute("""
        INSERT INTO operaciones_simuladas (id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada,
            precio_actual, pnl_pct, pnl_usd, estado, fecha_apertura, dte_plazo, targets_alcanzados, cuenta_id)
        VALUES ('T_EXISTENTE', 'QQQ', 'CALL', 'GAP_NORMAL', 5, 5.0, 5.0, 0.0, 0.0, 'OPEN', ?, 1, '[]', 'default')
    """, (now_str,))

    # Perdida realizada de hoy > 2% de 1,000,000 = 20,000
    conn.execute("""
        INSERT INTO ledger_movimientos (mov_id, timestamp, tipo_movimiento, monto_debito, monto_credito,
            balance_resultante, trade_id, bucket_id, estrategia, referencia, cuenta_id)
        VALUES ('M1', ?, 'TRADE_CLOSE', 25000.0, 0.0, 975000.0, 'T0', 'SHORT_TERM', 'GAP_NORMAL', 'perdida test', 'default')
    """, (now_str,))
    conn.commit()

    locked, pnl_dia, just_locked = risk_engine.chequear_perdida_diaria_maxima(conn, "default", 1_000_000.0)
    check("perdida diaria > 2% activa DAILY_LOCKED", locked and just_locked, f"pnl_dia={pnl_dia}")

    r = risk_engine.evaluar_orden_nueva(conn, "default", "SPY", "GAP_NORMAL", 10, 100.0, 1_000_000.0, 0.0)
    check("DAILY_LOCKED bloquea nuevas compras", not r["authorized"], r["reason"])

    row = conn.execute("SELECT estado FROM operaciones_simuladas WHERE id='T_EXISTENTE'").fetchone()
    check("DAILY_LOCKED NO cierra posiciones existentes", row[0] == "OPEN", row)
    conn.close()
    os.remove(path)


def _insertar_posicion_abierta(conn, trade_id, dte, minutos_atras, precio_entrada=5.0, tipo="CALL", ticker="SPY", estrategia="GAP_NORMAL"):
    apertura = datetime.now() - timedelta(minutes=minutos_atras)
    conn.execute("""
        INSERT INTO operaciones_simuladas (id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada,
            precio_actual, pnl_pct, pnl_usd, estado, fecha_apertura, dte_plazo, targets_alcanzados, cuenta_id)
        VALUES (?, ?, ?, ?, 10, ?, ?, 0.0, 0.0, 'OPEN', ?, ?, '[]', 'default')
    """, (trade_id, ticker, tipo, estrategia, precio_entrada, precio_entrada, apertura.strftime("%Y-%m-%d %H:%M:%S"), dte))
    conn.commit()
    position_manager.asignar_parametros_riesgo_nueva_posicion(conn, trade_id, apertura.strftime("%Y-%m-%d %H:%M:%S"), dte)


def test_stop_loss_cierra_posicion():
    conn, path = nueva_db()
    _insertar_posicion_abierta(conn, "T_SL", dte=7, minutos_atras=30)
    eventos = position_manager.evaluar_posiciones_abiertas(conn, lambda t: 480.0)  # var ~ -4% * leverage 8 = -32% << -15%
    cerrados = [e for e in eventos if e["action"] == "CLOSED"]
    check("STOP_LOSS cierra la posicion cuando pnl <= sl_pct_config", len(cerrados) == 1 and cerrados[0]["exit_reason"] == "STOP_LOSS", eventos)
    conn.close()
    os.remove(path)


def test_take_profit_cierra_posicion():
    conn, path = nueva_db()
    _insertar_posicion_abierta(conn, "T_TP", dte=7, minutos_atras=30)
    eventos = position_manager.evaluar_posiciones_abiertas(conn, lambda t: 530.0)  # var ~ +6% * leverage 8 = +48% >> +30%
    cerrados = [e for e in eventos if e["action"] == "CLOSED"]
    check("TAKE_PROFIT cierra la posicion cuando pnl >= tp_pct_config", len(cerrados) == 1 and cerrados[0]["exit_reason"] == "TAKE_PROFIT", eventos)
    conn.close()
    os.remove(path)


def test_time_stop_cierra_posicion_intradia():
    conn, path = nueva_db()
    # dte=1 (intradia), abierta hace 300 minutos > time_stop_minutes_intraday (240), precio sin mover (pnl neutro)
    _insertar_posicion_abierta(conn, "T_TS", dte=1, minutos_atras=300)
    eventos = position_manager.evaluar_posiciones_abiertas(conn, lambda t: 500.0)
    cerrados = [e for e in eventos if e["action"] == "CLOSED"]
    check("TIME_STOP cierra una posicion intradia que excede el plazo maximo", len(cerrados) == 1 and cerrados[0]["exit_reason"] == "TIME_STOP", eventos)
    conn.close()
    os.remove(path)


def test_expiration_guard_fuerza_cierre():
    conn, path = nueva_db()
    _insertar_posicion_abierta(conn, "T_EXP", dte=1, minutos_atras=5)
    # Forzar el deadline a 30 minutos en el futuro (dentro de la ventana de guardia de 60 min)
    deadline = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("UPDATE operaciones_simuladas SET expiration_deadline = ? WHERE id = 'T_EXP'", (deadline,))
    conn.commit()
    eventos = position_manager.evaluar_posiciones_abiertas(conn, lambda t: 500.0)  # pnl neutro, no deberia cerrar por SL/TP
    cerrados = [e for e in eventos if e["action"] == "CLOSED"]
    check("EXPIRATION_GUARD fuerza el cierre antes de llegar a Expired", len(cerrados) == 1 and cerrados[0]["exit_reason"] == "EXPIRATION_GUARD", eventos)
    conn.close()
    os.remove(path)


def test_posicion_no_cierra_si_esta_dentro_de_rangos():
    conn, path = nueva_db()
    _insertar_posicion_abierta(conn, "T_OK", dte=7, minutos_atras=30)
    eventos = position_manager.evaluar_posiciones_abiertas(conn, lambda t: 502.0)  # movimiento chico, dentro de rango
    check("una posicion dentro de SL/TP/tiempo/expiracion permanece OPEN", len(eventos) == 1 and eventos[0]["action"] == "UPDATED", eventos)
    row = conn.execute("SELECT mfe_pct, mae_pct FROM operaciones_simuladas WHERE id='T_OK'").fetchone()
    check("MFE/MAE se actualizan en cada ciclo", row[0] is not None and row[1] is not None, row)
    conn.close()
    os.remove(path)


def test_reconciliacion_detecta_descuadre():
    conn, path = nueva_db()
    res_buy = sim_broker_core.simular_compra_broker(conn, "SPY", "GAP_NORMAL", 500.0, cuenta_id="default")
    check("compra autorizada para test de reconciliacion", res_buy.get("status") == "FILLED", res_buy)

    recon_ok = position_manager.verificar_reconciliacion(conn, "default")
    check("reconciliacion OK inmediatamente despues de una compra normal", recon_ok["reconciliado"], recon_ok)

    # Desincronizar manualmente los buckets (simula una inconsistencia real)
    conn.execute("UPDATE capital_buckets SET capital_comprometido = capital_comprometido + 99999 WHERE cuenta_id='default'")
    conn.commit()
    recon_bad = position_manager.verificar_reconciliacion(conn, "default")
    check("reconciliacion detecta un descuadre real", not recon_bad["reconciliado"], recon_bad)

    fila_audit = conn.execute("SELECT COUNT(*) FROM risk_audit_log WHERE event_type='RECONCILIATION_ERROR'").fetchone()[0]
    check("descuadre queda registrado en risk_audit_log", fila_audit >= 1, fila_audit)
    conn.close()
    os.remove(path)


def test_estado_persiste_tras_reconexion_simula_restart():
    """Simula un reinicio de proceso: se cierra la conexion SQLite y se abre
    una nueva contra el mismo archivo -- el estado (cupo diario, posicion,
    parametros de riesgo) debe seguir intacto."""
    conn, path = nueva_db()
    res_buy = sim_broker_core.simular_compra_broker(conn, "SPY", "GAP_NORMAL", 500.0, cuenta_id="default")
    trade_id = res_buy["trade_id"]
    # sim_broker_core no asigna SL/TP directamente (evita import circular);
    # el llamador (live_scanner.py, en ambos puntos de compra) es quien lo
    # hace justo despues del fill -- se replica ese mismo paso aca.
    now_str_buy = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    position_manager.transicionar_estado(conn, trade_id, "FILLED", "test")
    position_manager.asignar_parametros_riesgo_nueva_posicion(conn, trade_id, now_str_buy, res_buy.get("dte", 1))
    conn.close()  # <-- "caida de proceso"

    conn2 = sqlite3.connect(path)  # <-- "reinicio"
    row = conn2.execute("SELECT estado, state, sl_pct_config, tp_pct_config FROM operaciones_simuladas WHERE id=?", (trade_id,)).fetchone()
    check("la posicion sigue existiendo y OPEN tras reconectar", row[0] == "OPEN", row)
    check("el estado de la maquina de estados persistio (FILLED->OPEN)", row[1] == "OPEN", row)
    check("los parametros de riesgo (SL/TP) persistieron", row[2] is not None and row[3] is not None, row)

    cupo, gastado, _ = risk_engine.obtener_o_crear_cupo_diario(conn2, "default", 1_000_000.0)
    check("el cupo diario gastado persistio tras reconectar", gastado > 0, gastado)
    conn2.close()
    conn.close()
    os.remove(path)


if __name__ == "__main__":
    tests = [
        test_max_position_pct,
        test_max_total_open_exposure_pct,
        test_daily_budget_reduces_and_blocks,
        test_capital_recycling_no_restituye_cupo,
        test_duplicate_order_rejected,
        test_kill_switch_bloquea_y_desbloquea,
        test_daily_max_loss_lock_no_cierra_posiciones_existentes,
        test_stop_loss_cierra_posicion,
        test_take_profit_cierra_posicion,
        test_time_stop_cierra_posicion_intradia,
        test_expiration_guard_fuerza_cierre,
        test_posicion_no_cierra_si_esta_dentro_de_rangos,
        test_reconciliacion_detecta_descuadre,
        test_estado_persiste_tras_reconexion_simula_restart,
    ]
    print(f"=== Ejecutando {len(tests)} tests de RiskEngine/PositionManager ===\n")
    for t in tests:
        try:
            t()
        except Exception as e:
            check(t.__name__, False, f"EXCEPCION: {e}")

    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n=== Resultado: {passed}/{total} tests OK ===")
    if passed < total:
        print("\nTests fallidos:")
        for name, ok, detalle in RESULTS:
            if not ok:
                print(f"  - {name}: {detalle}")
        sys.exit(1)
    sys.exit(0)

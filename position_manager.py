"""
position_manager.py
=====================
Gestor de Posiciones de Meliora Options -- independiente del detector de
estrategias. Responsable del ciclo de vida completo de cada posicion desde
que se llena hasta que se cierra y reconcilia: stop loss obligatorio, time
stop, expiration guard, maquina de estados, y reconciliacion contra el
"broker" (en Paper/Shadow, el propio ledger/buckets de sim_broker_core es la
fuente de verdad).

No decide que comprar. No opina sobre senales. Solo gestiona el riesgo de
posiciones que YA fueron autorizadas por risk_engine.py y abiertas por
sim_broker_core.py.
"""
import sqlite3
from datetime import datetime, timedelta

import risk_engine
import sim_broker_core

DB_NAME = "trading_laboratory.db"

# ==========================================
# Maquina de estados (Requisito #8)
# ==========================================
ESTADOS_VALIDOS = [
    "SIGNAL_DETECTED", "CONFIRMED", "ORDER_REQUESTED", "ORDER_SUBMITTED",
    "PARTIALLY_FILLED", "FILLED", "OPEN", "EXIT_REQUESTED", "EXIT_SUBMITTED",
    "CLOSED", "RECONCILED", "ERROR",
]

# Motivos de salida (Requisito #10)
EXIT_REASONS = [
    "TAKE_PROFIT", "STOP_LOSS", "TIME_STOP", "EXPIRATION_GUARD",
    "DAILY_RISK_LOCK", "MANUAL", "STRATEGY_EXIT", "BROKER_ERROR",
]


def transicionar_estado(conn, trade_id, nuevo_estado, motivo="", actor="POSITION_MANAGER"):
    if nuevo_estado not in ESTADOS_VALIDOS:
        raise ValueError(f"Estado invalido: {nuevo_estado}")
    cursor = conn.cursor()
    cursor.execute("UPDATE operaciones_simuladas SET state = ? WHERE id = ?", (nuevo_estado, trade_id))
    conn.commit()
    risk_engine.registrar_auditoria(conn, actor, "STATE_TRANSITION", f"-> {nuevo_estado} ({motivo})", trade_id=trade_id)


def init_position_columns(conn):
    """Agrega columnas nuevas a operaciones_simuladas de forma aditiva.
    Nunca borra ni renombra columnas existentes."""
    cursor = conn.cursor()
    columnas_nuevas = [
        ("state", "TEXT DEFAULT 'OPEN'"),
        ("exit_reason", "TEXT"),
        ("mfe_pct", "REAL DEFAULT 0.0"),
        ("mae_pct", "REAL DEFAULT 0.0"),
        ("sl_pct_config", "REAL"),
        ("tp_pct_config", "REAL"),
        ("time_stop_minutes_config", "INTEGER"),
        ("allow_overnight_config", "INTEGER DEFAULT 0"),
        ("expiration_deadline", "TEXT"),
    ]
    for col, tipo in columnas_nuevas:
        try:
            cursor.execute(f"ALTER TABLE operaciones_simuladas ADD COLUMN {col} {tipo}")
        except sqlite3.OperationalError:
            pass  # ya existe
    conn.commit()


_MARKET_CLOSE_HOUR = 16  # Cierre asumido de mercado (hora local del servidor, sin conversion de TZ)


def _calcular_deadline_expiracion(fecha_apertura_str, dte_plazo):
    try:
        apertura = datetime.strptime(fecha_apertura_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        apertura = datetime.now()
    dia_expiracion = apertura + timedelta(days=int(dte_plazo))
    deadline = dia_expiracion.replace(hour=_MARKET_CLOSE_HOUR, minute=0, second=0, microsecond=0)
    return deadline


def asignar_parametros_riesgo_nueva_posicion(conn, trade_id, fecha_apertura_str, dte_plazo, escenario=None):
    """Fija, en el momento del fill, los parametros de riesgo que van a
    gobernar la salida de esta posicion (Requisitos #4, #5, #6). Se guardan
    en la fila para que sean inmutables/auditables y no dependan de que la
    config global no haya cambiado despues."""
    cfg = risk_engine.get_risk_config()
    escenario = escenario or cfg["default_scenario"]
    sl_pct = cfg["sl_pct_by_scenario"].get(escenario, cfg["sl_pct_by_scenario"]["pilot"])
    tp_pct = cfg["tp_pct_by_scenario"].get(escenario, cfg["tp_pct_by_scenario"]["pilot"])

    es_intradia = int(dte_plazo) <= 1
    time_stop_minutes = cfg["time_stop_minutes_intraday"] if es_intradia else cfg["time_stop_minutes_swing"]
    allow_overnight = 0 if es_intradia else int(bool(cfg["allow_overnight_default"]))

    deadline = _calcular_deadline_expiracion(fecha_apertura_str, dte_plazo)

    cursor = conn.cursor()
    cursor.execute("""
        UPDATE operaciones_simuladas
        SET sl_pct_config = ?, tp_pct_config = ?, time_stop_minutes_config = ?,
            allow_overnight_config = ?, expiration_deadline = ?, state = 'OPEN'
        WHERE id = ?
    """, (sl_pct, tp_pct, time_stop_minutes, allow_overnight, deadline.strftime("%Y-%m-%d %H:%M:%S"), trade_id))
    conn.commit()


# ==========================================
# Monitoreo de posiciones abiertas (Requisitos #4, #5, #6, #8, #10)
# ==========================================

def evaluar_posiciones_abiertas(conn, obtener_precio_fn, cuenta_id=None):
    """Recorre TODAS las posiciones OPEN (o solo las de 'cuenta_id' si se
    especifica), calcula PnL sintetico (mismo modelo que ya existia, sin
    tocar el pricing), actualiza MFE/MAE, y decide si corresponde cerrar por
    TAKE_PROFIT, STOP_LOSS, TIME_STOP o EXPIRATION_GUARD -- en ese orden de
    prioridad de calculo (el primero que aplique gana). No decide nada sobre
    ENTRADAS, solo sobre SALIDAS de posiciones ya abiertas.

    Devuelve una lista de dicts, uno por posicion procesada, para que el
    llamador (live_scanner.py) dispare las notificaciones/Sheets que ya
    existian sin duplicar esa logica aca."""
    cfg = risk_engine.get_risk_config()
    cursor = conn.cursor()

    query = """
        SELECT id, ticker, tipo, estrategia, cantidad_contratos, precio_entrada, dte_plazo,
               fecha_apertura, cuenta_id, mfe_pct, mae_pct, sl_pct_config, tp_pct_config,
               time_stop_minutes_config, allow_overnight_config, expiration_deadline
        FROM operaciones_simuladas WHERE estado = 'OPEN'
    """
    params = ()
    if cuenta_id:
        query += " AND cuenta_id = ?"
        params = (cuenta_id,)
    cursor.execute(query, params)
    posiciones = cursor.fetchall()

    resultados = []
    ahora = datetime.now()


    for pos in posiciones:
        (trade_id, ticker, tipo, estrategia, cantidad, precio_entrada, dte, fecha_apertura,
         cta_id, mfe_prev, mae_prev, sl_pct_cfg, tp_pct_cfg, time_stop_min, allow_overnight,
         expiration_deadline_str) = pos

        # Backfill defensivo: posiciones abiertas ANTES de este refactor no
        # tienen estos parametros seteados todavia -- se les asigna ahora
        # mismo con el escenario por defecto, sin tocar su fecha_apertura
        # real (no se retroactiva el time-stop a partir de "ahora").
        if sl_pct_cfg is None or tp_pct_cfg is None:
            asignar_parametros_riesgo_nueva_posicion(conn, trade_id, fecha_apertura, dte)
            sl_pct_cfg = cfg["sl_pct_by_scenario"][cfg["default_scenario"]]
            tp_pct_cfg = cfg["tp_pct_by_scenario"][cfg["default_scenario"]]
            time_stop_min = cfg["time_stop_minutes_intraday"] if int(dte) <= 1 else cfg["time_stop_minutes_swing"]
            allow_overnight = 0 if int(dte) <= 1 else int(bool(cfg["allow_overnight_default"]))
            expiration_deadline_str = _calcular_deadline_expiracion(fecha_apertura, dte).strftime("%Y-%m-%d %H:%M:%S")

        precio_actual_sub = obtener_precio_fn(ticker)
        if precio_actual_sub is None:
            continue

        cursor.execute("SELECT price FROM radar_actual WHERE ticker = ? LIMIT 1", (ticker,))
        price_row = cursor.fetchone()
        precio_entrada_sub = price_row[0] if price_row else precio_actual_sub * 0.99

        leverage = 12 if dte == 1 else 8 if dte == 7 else 5
        var_sub = (precio_actual_sub - precio_entrada_sub) / precio_entrada_sub
        pnl_pct = (var_sub if "CALL" in tipo else -var_sub) * leverage * 100
        pnl_pct = max(-98.0, min(250.0, pnl_pct))
        precio_actual_opcion = max(0.01, round(precio_entrada * (1 + pnl_pct / 100), 2))
        pnl_usd = (precio_actual_opcion - precio_entrada) * 100 * cantidad


        mfe = max(mfe_prev or 0.0, pnl_pct)
        mae = min(mae_prev or 0.0, pnl_pct)

        try:
            apertura_dt = datetime.strptime(fecha_apertura, "%Y-%m-%d %H:%M:%S")
        except Exception:
            apertura_dt = ahora
        minutes_open = (ahora - apertura_dt).total_seconds() / 60.0

        try:
            deadline_dt = datetime.strptime(expiration_deadline_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            deadline_dt = _calcular_deadline_expiracion(fecha_apertura, dte)

        exit_reason = None
        if pnl_pct >= tp_pct_cfg:
            exit_reason = "TAKE_PROFIT"
        elif pnl_pct <= sl_pct_cfg:
            exit_reason = "STOP_LOSS"
        elif ahora >= (deadline_dt - timedelta(minutes=cfg["expiration_guard_minutes_before_close"])):
            # Requisito #6: ninguna posicion llega a Expired por abandono.
            exit_reason = "EXPIRATION_GUARD"
        elif minutes_open >= time_stop_min:
            exit_reason = "TIME_STOP"
        elif int(dte) <= 1 and not allow_overnight and ahora.hour >= _MARKET_CLOSE_HOUR - 1 and ahora.date() == apertura_dt.date():
            # Intradia sin overnight permitido: forzar cierre antes del cierre de mercado.
            exit_reason = "TIME_STOP"


        if exit_reason is None:
            cursor.execute("""
                UPDATE operaciones_simuladas
                SET precio_actual = ?, pnl_pct = ?, pnl_usd = ?, mfe_pct = ?, mae_pct = ?
                WHERE id = ?
            """, (precio_actual_opcion, pnl_pct, pnl_usd, mfe, mae, trade_id))
            conn.commit()
            resultados.append({"trade_id": trade_id, "ticker": ticker, "tipo": tipo, "estrategia": estrategia,
                                "cuenta_id": cta_id, "action": "UPDATED", "pnl_pct": pnl_pct, "pnl_usd": pnl_usd})
            continue

        # Cerrar via el core del Sim Broker (Ledger, Buckets, Retiro 90/10) --
        # se reutiliza intacta la logica contable ya existente.
        transicionar_estado(conn, trade_id, "EXIT_REQUESTED", exit_reason)
        cursor.execute("UPDATE operaciones_simuladas SET mfe_pct = ?, mae_pct = ?, exit_reason = ? WHERE id = ?",
                       (mfe, mae, exit_reason, trade_id))
        conn.commit()

        venta_result = sim_broker_core.simular_venta_broker(conn, trade_id, precio_actual_sub)
        if venta_result.get("status") == "CLOSED":
            transicionar_estado(conn, trade_id, "CLOSED", exit_reason)
            risk_engine.registrar_auditoria(conn, "POSITION_MANAGER", f"EXIT_{exit_reason}",
                                             f"PnL: {venta_result.get('pnl_pct'):.2f}% (${venta_result.get('pnl_usd'):.2f})",
                                             trade_id=trade_id, ticker=ticker, strategy_id=estrategia, cuenta_id=cta_id)
            resultados.append({"trade_id": trade_id, "ticker": ticker, "tipo": tipo, "estrategia": estrategia,
                                "cuenta_id": cta_id, "action": "CLOSED", "exit_reason": exit_reason,
                                "cantidad": cantidad, "dte": dte, "precio_actual_opcion": precio_actual_opcion,
                                "pnl_pct": venta_result.get("pnl_pct"), "pnl_usd": venta_result.get("pnl_usd"),
                                "venta_result": venta_result})
        else:
            transicionar_estado(conn, trade_id, "ERROR", str(venta_result))
            risk_engine.registrar_auditoria(conn, "POSITION_MANAGER", "BROKER_ERROR", str(venta_result), trade_id=trade_id)

    return resultados


# ==========================================
# Reconciliacion (Requisito #9)
# ==========================================
# En Paper/Shadow no hay un broker externo real: la fuente de verdad es el
# propio ledger contable + buckets de sim_broker_core. "Reconciliar" aca
# significa: el capital comprometido que dicen los buckets tiene que
# coincidir EXACTO con lo que hay realmente abierto en operaciones_simuladas.
# Cuando este proyecto conecte con IBKR real, este es el punto donde se
# reemplaza la comparacion "contra buckets" por "contra el broker real".

def verificar_reconciliacion(conn, cuenta_id='default', tolerancia_usd=1.0):
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COALESCE(SUM(cantidad_contratos * (precio_entrada * 100 + 0.65)), 0)
        FROM operaciones_simuladas WHERE estado = 'OPEN' AND cuenta_id = ?
    """, (cuenta_id,))
    comprometido_posiciones = float(cursor.fetchone()[0])

    cursor.execute("SELECT COALESCE(SUM(capital_comprometido), 0) FROM capital_buckets WHERE cuenta_id = ?", (cuenta_id,))
    comprometido_buckets = float(cursor.fetchone()[0])

    diferencia = abs(comprometido_posiciones - comprometido_buckets)
    reconciliado = diferencia <= tolerancia_usd

    if not reconciliado:
        risk_engine.registrar_auditoria(
            conn, "POSITION_MANAGER", "RECONCILIATION_ERROR",
            f"Posiciones OPEN: ${comprometido_posiciones:,.2f} vs Buckets comprometido: ${comprometido_buckets:,.2f} "
            f"(diferencia ${diferencia:,.2f})",
            cuenta_id=cuenta_id,
        )
        conn.commit()

    return {"reconciliado": reconciliado, "comprometido_posiciones": comprometido_posiciones,
            "comprometido_buckets": comprometido_buckets, "diferencia": diferencia}


# ==========================================
# Estado para el panel flotante de Tampermonkey (Requisito #12)
# ==========================================

def estado_panel(conn, cuenta_id='default'):
    cursor = conn.cursor()

    cursor.execute("SELECT balance_actual FROM cuentas_simuladas WHERE id = ?", (cuenta_id,))
    row = cursor.fetchone()
    balance_actual = float(row[0]) if row else 0.0

    cupo_disponible, cupo_gastado, balance_inicial_dia = risk_engine.obtener_o_crear_cupo_diario(conn, cuenta_id, balance_actual)
    daily_locked, lock_reason = risk_engine.esta_bloqueado_por_perdida_diaria(conn, cuenta_id)
    kill_switch, system_state = risk_engine.kill_switch_activo(conn)

    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(cantidad_contratos * (precio_entrada * 100 + 0.65)), 0),
               COALESCE(SUM(pnl_usd), 0)
        FROM operaciones_simuladas WHERE estado = 'OPEN' AND cuenta_id = ?
    """, (cuenta_id,))
    n_abiertas, exposicion_abierta, pnl_no_realizado = cursor.fetchone()

    _, pnl_realizado_dia, _ = risk_engine.chequear_perdida_diaria_maxima(conn, cuenta_id, balance_inicial_dia)

    recon = verificar_reconciliacion(conn, cuenta_id)


    return {
        "cuenta_id": cuenta_id,
        "balance_inicial_dia": balance_inicial_dia,
        "balance_actual": balance_actual,
        "cupo_diario_total": balance_inicial_dia * risk_engine.get_risk_config()["daily_budget_pct"],
        "cupo_disponible": cupo_disponible,
        "cupo_gastado": cupo_gastado,
        "exposicion_abierta_usd": exposicion_abierta,
        "pnl_realizado_dia": pnl_realizado_dia,
        "pnl_no_realizado": pnl_no_realizado,
        "posiciones_abiertas": n_abiertas,
        "daily_locked": daily_locked,
        "daily_locked_reason": lock_reason,
        "kill_switch_activo": kill_switch,
        "system_state": system_state,
        "reconciliado": recon["reconciliado"],
        "reconciliacion_diferencia": recon["diferencia"],
        "live_trading_enabled": risk_engine.MODE_LIVE_TRADING_ENABLED,
    }

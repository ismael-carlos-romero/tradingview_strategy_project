-- postgres_schema.sql
-- Estructura de base de datos relacional PostgreSQL para Meliora Options 24/7

-- 1. Estado y Ciclo de Vida de los Bots (Workers)
CREATE TABLE IF NOT EXISTS bot_status (
    bot_id VARCHAR(50) PRIMARY KEY,
    desired_state VARCHAR(20) NOT NULL CHECK (desired_state IN ('RUNNING', 'PAUSED', 'STOPPED')),
    actual_state VARCHAR(20) NOT NULL CHECK (actual_state IN ('STARTING', 'RUNNING', 'PAUSED', 'STOPPED', 'ERROR', 'SIN_RESPUESTA')),
    last_heartbeat TIMESTAMP,
    last_activity TIMESTAMP,
    last_error TEXT,
    worker_id VARCHAR(50),
    enabled BOOLEAN DEFAULT TRUE
);

-- Inicializar estados para los 3 bots principales si no existen
INSERT INTO bot_status (bot_id, desired_state, actual_state, last_activity, enabled) 
VALUES 
('live_scanner', 'STOPPED', 'STOPPED', CURRENT_TIMESTAMP, TRUE),
('paper_bot', 'STOPPED', 'STOPPED', CURRENT_TIMESTAMP, TRUE),
('tracker', 'STOPPED', 'STOPPED', CURRENT_TIMESTAMP, TRUE)
ON CONFLICT (bot_id) DO NOTHING;

-- 2. Configuraciones del Sistema y Cortafuegos (Kill Switch)
CREATE TABLE IF NOT EXISTS system_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    allow_new_trades BOOLEAN DEFAULT TRUE,
    kill_switch_reason TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(50) DEFAULT 'SYSTEM'
);

INSERT INTO system_settings (id, allow_new_trades, updated_by) 
VALUES (1, TRUE, 'SYSTEM')
ON CONFLICT (id) DO NOTHING;

-- 3. Cuentas de Simulación del Ledger Contable
CREATE TABLE IF NOT EXISTS cuentas_simuladas (
    id VARCHAR(50) PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    balance_inicial DOUBLE PRECISION NOT NULL DEFAULT 3884329.04,
    balance_actual DOUBLE PRECISION NOT NULL DEFAULT 3884329.04,
    creation_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO cuentas_simuladas (id, nombre, balance_inicial, balance_actual) 
VALUES ('default', 'Meliora paso a paso', 3884329.04, 3884329.04)
ON CONFLICT (id) DO NOTHING;

-- 4. Estado de Gestión Monetaria y Riesgo (Motor 10%)
CREATE TABLE IF NOT EXISTS capital_state (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    capital_total DOUBLE PRECISION NOT NULL DEFAULT 3884329.04,
    capital_reinvertible DOUBLE PRECISION NOT NULL DEFAULT 3884329.04,
    capital_retirado DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    limite_operativo DOUBLE PRECISION NOT NULL DEFAULT 388432.90,
    capital_comprometido DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    capital_disponible DOUBLE PRECISION NOT NULL DEFAULT 3884329.04,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO capital_state (id, capital_total, capital_reinvertible, capital_retirado, limite_operativo, capital_comprometido, capital_disponible) 
VALUES (1, 3884329.04, 3884329.04, 0.0, 388432.90, 0.0, 3884329.04)
ON CONFLICT (id) DO NOTHING;

-- 5. Buckets/Bolsillos de Capital por Cuenta
CREATE TABLE IF NOT EXISTS capital_buckets (
    bucket_id VARCHAR(50),
    cuenta_id VARCHAR(50),
    porcentaje_asignado DOUBLE PRECISION NOT NULL,
    capital_disponible DOUBLE PRECISION NOT NULL,
    capital_comprometido DOUBLE PRECISION NOT NULL,
    pnl_acumulado DOUBLE PRECISION DEFAULT 0.0,
    descripcion TEXT,
    PRIMARY KEY (bucket_id, cuenta_id),
    FOREIGN KEY (cuenta_id) REFERENCES cuentas_simuladas(id)
);

-- 6. Registro de Órdenes (Compra y Venta)
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(100) PRIMARY KEY,
    bot_id VARCHAR(50) NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    qty INTEGER NOT NULL CHECK (qty > 0),
    status VARCHAR(20) NOT NULL CHECK (status IN ('PENDING', 'FILLED', 'REJECTED', 'CANCELLED')),
    requested_price DOUBLE PRECISION NOT NULL,
    fill_price DOUBLE PRECISION,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP
);

-- 7. Registro de Posiciones Activas e Historial de Opciones
CREATE TABLE IF NOT EXISTS operaciones_simuladas (
    id VARCHAR(100) PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    tipo VARCHAR(10) NOT NULL,
    estrategia VARCHAR(100) NOT NULL,
    cantidad_contratos INTEGER NOT NULL,
    precio_entrada DOUBLE PRECISION NOT NULL,
    precio_actual DOUBLE PRECISION NOT NULL,
    pnl_pct DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    pnl_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    estado VARCHAR(20) NOT NULL CHECK (estado IN ('OPEN', 'CLOSED')),
    fecha_apertura TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_cierre TIMESTAMP,
    dte_plazo INTEGER NOT NULL,
    targets_alcanzados TEXT DEFAULT '[]',
    balance_referencia DOUBLE PRECISION,
    cuenta_id VARCHAR(50) DEFAULT 'default',
    FOREIGN KEY (cuenta_id) REFERENCES cuentas_simuladas(id)
);

-- 8. Asientos Contables Inmutables (Ledger)
CREATE TABLE IF NOT EXISTS ledger_movimientos (
    mov_id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    tipo_movimiento VARCHAR(50) NOT NULL,
    monto_debito DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    monto_credito DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    balance_resultante DOUBLE PRECISION NOT NULL,
    trade_id VARCHAR(100),
    bucket_id VARCHAR(50),
    estrategia VARCHAR(100),
    referencia TEXT,
    cuenta_id VARCHAR(50) DEFAULT 'default',
    FOREIGN KEY (cuenta_id) REFERENCES cuentas_simuladas(id)
);

-- Inicializar Ledger para la cuenta por defecto si esta vacio
INSERT INTO ledger_movimientos (mov_id, timestamp, tipo_movimiento, monto_debito, monto_credito, balance_resultante, referencia, cuenta_id)
VALUES ('MOV_INIT_CAPITAL', CURRENT_TIMESTAMP, 'INITIAL_DEPOSIT', 0.0, 3884329.04, 3884329.04, 'DEPÓSITO INICIAL DE APERTURA', 'default')
ON CONFLICT (mov_id) DO NOTHING;

-- 9. Cuenta Corriente de Retiros (Regla 90/10)
CREATE TABLE IF NOT EXISTS cuenta_corriente_movimientos (
    mov_id VARCHAR(100) PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    trade_id VARCHAR(100),
    monto DOUBLE PRECISION NOT NULL,
    balance_acumulado DOUBLE PRECISION NOT NULL,
    estrategia VARCHAR(100),
    bot_id VARCHAR(50),
    cuenta_id VARCHAR(50) DEFAULT 'default',
    FOREIGN KEY (cuenta_id) REFERENCES cuentas_simuladas(id)
);

-- 10. Decisiones del Motor de Riesgo
CREATE TABLE IF NOT EXISTS decisiones (
    decision_id VARCHAR(100) PRIMARY KEY,
    setup_id VARCHAR(100) NOT NULL,
    source VARCHAR(50) NOT NULL,
    action VARCHAR(20) NOT NULL,
    rejection_reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. Logs Centralizados de los Workers
CREATE TABLE IF NOT EXISTS bot_logs (
    id SERIAL PRIMARY KEY,
    bot_id VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    event_type VARCHAR(50) NOT NULL,
    message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

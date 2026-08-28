-- schema.sql
-- Estructura de base de datos relacional para Meliora Options 24/7

-- 1. Estado y Ciclo de Vida de los Bots (Workers)
CREATE TABLE IF NOT EXISTS bot_status (
    bot_id TEXT PRIMARY KEY,
    desired_state TEXT NOT NULL CHECK (desired_state IN ('RUNNING', 'PAUSED', 'STOPPED')),
    actual_state TEXT NOT NULL CHECK (actual_state IN ('STARTING', 'RUNNING', 'PAUSED', 'STOPPED', 'ERROR', 'SIN_RESPUESTA')),
    last_heartbeat TIMESTAMP,
    last_activity TIMESTAMP,
    last_error TEXT,
    worker_id TEXT,
    enabled BOOLEAN DEFAULT 1
);

-- Inicializar estados para los 3 bots principales si no existen
INSERT OR IGNORE INTO bot_status (bot_id, desired_state, actual_state, last_activity, enabled) 
VALUES 
('live_scanner', 'STOPPED', 'STOPPED', CURRENT_TIMESTAMP, 1),
('paper_bot', 'STOPPED', 'STOPPED', CURRENT_TIMESTAMP, 1),
('tracker', 'STOPPED', 'STOPPED', CURRENT_TIMESTAMP, 1);

-- 2. Configuraciones del Sistema y Cortafuegos (Kill Switch)
CREATE TABLE IF NOT EXISTS system_settings (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), -- Asegurar registro único
    allow_new_trades BOOLEAN DEFAULT 1,
    kill_switch_reason TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by TEXT DEFAULT 'SYSTEM'
);

INSERT OR IGNORE INTO system_settings (id, allow_new_trades, updated_by) VALUES (1, 1, 'SYSTEM');

-- 3. Estado de Gestión Monetaria y Riesgo (Motor 10%)
CREATE TABLE IF NOT EXISTS capital_state (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), -- Asegurar registro único
    capital_total REAL NOT NULL DEFAULT 3884329.04,
    capital_reinvertible REAL NOT NULL DEFAULT 3884329.04,
    capital_retirado REAL NOT NULL DEFAULT 0.0,
    limite_operativo REAL GENERATED ALWAYS AS (capital_reinvertible * 0.10) STORED, -- 10% No Negociable
    capital_comprometido REAL NOT NULL DEFAULT 0.0,
    capital_disponible REAL GENERATED ALWAYS AS (capital_reinvertible - capital_comprometido) STORED,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO capital_state (id, capital_total, capital_reinvertible, capital_retirado, capital_comprometido) 
VALUES (1, 3884329.04, 3884329.04, 0.0, 0.0);

-- 4. Registro de Órdenes (Compra y Venta)
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    qty INTEGER NOT NULL CHECK (qty > 0),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'FILLED', 'REJECTED', 'CANCELLED')),
    requested_price REAL NOT NULL,
    fill_price REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    filled_at TIMESTAMP
);

-- 5. Registro de Posiciones Activas e Historial
CREATE TABLE IF NOT EXISTS positions (
    position_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    cost_basis REAL NOT NULL,
    tp_price REAL NOT NULL,
    sl_price REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    realized_pnl REAL DEFAULT 0.0,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- 6. Logs Centralizados de los Workers
CREATE TABLE IF NOT EXISTS bot_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

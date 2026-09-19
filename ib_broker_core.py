"""
ib_broker_core.py — Meliora Options: capa de conexion a Interactive Brokers
(TWS / IB Gateway) via ib_insync.

Paralelo a sim_broker_core.py. NO reemplaza al simulador: corre bajo una
cuenta_id separada ("ib_real") para que los datos de paper trading y de
cuenta real nunca se mezclen en las mismas tablas.

ESTADO ACTUAL (fase 1 de la Task list): solo conexion + lectura de cuenta
y posiciones. Todavia NO coloca ordenes — eso se agrega en la fase 2,
una vez validada la conexion real en la PC de Ismael.

Requisitos en la PC:
    pip install ib_insync
    TWS o IB Gateway corriendo, con API habilitada:
      Configuracion > API > Settings > "Enable ActiveX and Socket Clients"
      Puerto tipico: 7497 (TWS paper), 7496 (TWS real),
                     4002 (Gateway paper), 4001 (Gateway real)
"""

import sqlite3
from dataclasses import dataclass
from datetime import datetime

try:
    from ib_insync import IB, util
except ImportError:
    IB = None  # se valida en connect()


# ---------------------------------------------------------------------------
# Config — ajustar antes de correr en la PC
# ---------------------------------------------------------------------------

IB_HOST = "127.0.0.1"
IB_PORT = 7496          # 7497 = TWS paper, 7496 = TWS real (confirmar en TWS)
IB_CLIENT_ID = 7        # id arbitrario, no debe chocar con otro cliente conectado

CUENTA_ID_REAL = "ib_real"          # separa esta cuenta del simulador ("default")
DB_PATH = "trading_laboratory.db"   # mismo archivo que usa live_scanner.py


class IBConnectionError(RuntimeError):
    pass


@dataclass
class CuentaIBResumen:
    cuenta_id: str
    net_liquidation: float
    cash_disponible: float
    valor_posiciones: float
    capital_operativo_maximo: float | None  # tope manual, None = no configurado todavia
    timestamp: str


class IBBroker:
    """Conexion de solo lectura a TWS/IB Gateway. No coloca ordenes (fase 1)."""

    def __init__(self, host=IB_HOST, port=IB_PORT, client_id=IB_CLIENT_ID):
        if IB is None:
            raise IBConnectionError(
                "Falta instalar ib_insync. Correr: pip install ib_insync"
            )
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()

    def connect(self, timeout=10):
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=timeout)
        except Exception as e:
            raise IBConnectionError(
                f"No se pudo conectar a TWS/IB Gateway en {self.host}:{self.port} "
                f"(client_id={self.client_id}). Verificar que TWS/Gateway este "
                f"abierto, con API habilitada, y que el puerto sea el correcto. "
                f"Error original: {e}"
            )
        return self

    def disconnect(self):
        if self.ib.isConnected():
            self.ib.disconnect()

    def __enter__(self):
        return self.connect()

    def __exit__(self, exc_type, exc, tb):
        self.disconnect()

    # -- lectura de cuenta ---------------------------------------------------

    def get_account_summary_raw(self):
        """Devuelve la lista cruda de AccountValue que entrega ib_insync."""
        if not self.ib.isConnected():
            raise IBConnectionError("No conectado — llamar connect() primero")
        return self.ib.accountSummary()

    def get_positions_raw(self):
        if not self.ib.isConnected():
            raise IBConnectionError("No conectado — llamar connect() primero")
        return self.ib.positions()

    def get_capital_operativo_maximo(self, db_path=DB_PATH, cuenta_id=CUENTA_ID_REAL):
        """
        Lee el tope de capital operativo real desde SQLite.
        Escalado MANUAL: Ismael sube este valor a mano cuando decide
        aumentar el capital en juego — el bot nunca lo sube solo.

        Tabla nueva (crear en la PC antes de la fase 2):
            CREATE TABLE IF NOT EXISTS capital_real_config (
                cuenta_id TEXT PRIMARY KEY,
                capital_operativo_maximo REAL NOT NULL,
                actualizado TEXT NOT NULL
            );
        """
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT capital_operativo_maximo FROM capital_real_config WHERE cuenta_id = ?",
                (cuenta_id,),
            )
            row = cur.fetchone()
            conn.close()
            return row[0] if row else None
        except sqlite3.OperationalError:
            # tabla todavia no existe en esta PC
            return None

    def resumen_cuenta(self, cuenta_id=CUENTA_ID_REAL) -> CuentaIBResumen:
        vals = {av.tag: av.value for av in self.get_account_summary_raw() if av.currency in ("USD", "")}
        net_liq = float(vals.get("NetLiquidation", 0) or 0)
        cash = float(vals.get("TotalCashValue", 0) or 0)
        valor_pos = net_liq - cash
        return CuentaIBResumen(
            cuenta_id=cuenta_id,
            net_liquidation=net_liq,
            cash_disponible=cash,
            valor_posiciones=valor_pos,
            capital_operativo_maximo=self.get_capital_operativo_maximo(cuenta_id=cuenta_id),
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )


# ---------------------------------------------------------------------------
# Test manual de conexion — NO coloca ninguna orden.
# Correr con: python ib_broker_core.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Conectando a TWS/IB Gateway en {IB_HOST}:{IB_PORT} (clientId={IB_CLIENT_ID})...")
    with IBBroker() as broker:
        print("Conectado OK.\n")

        resumen = broker.resumen_cuenta()
        print("=== Resumen de cuenta ===")
        print(f"  Cuenta lógica       : {resumen.cuenta_id}")
        print(f"  Net Liquidation     : ${resumen.net_liquidation:,.2f}")
        print(f"  Cash disponible     : ${resumen.cash_disponible:,.2f}")
        print(f"  Valor en posiciones : ${resumen.valor_posiciones:,.2f}")
        if resumen.capital_operativo_maximo is None:
            print("  Capital operativo max: NO CONFIGURADO (crear capital_real_config y cargar un valor)")
        else:
            print(f"  Capital operativo max: ${resumen.capital_operativo_maximo:,.2f}")

        print("\n=== Posiciones abiertas ===")
        posiciones = broker.get_positions_raw()
        if not posiciones:
            print("  (ninguna)")
        for p in posiciones:
            print(f"  {p.contract.localSymbol or p.contract.symbol}: {p.position} @ costo prom ${p.avgCost:,.2f}")

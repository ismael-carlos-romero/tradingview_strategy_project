import os
import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import ssl
import requests
import urllib3

# Deshabilitar advertencias de SSL inseguro
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

# Configurar sesión personalizada con User-Agent de navegador para evitar bloqueos HTTP 429 e ignorar SSL inválidos
session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# ==========================================
# CONFIGURACIÓN DE LOS ACTIVOS Y ESTRATEGIAS
# ==========================================
TICKERS = [
    "SPY", "META", "QQQ", "MSFT", "TSLA", "GOOGL", "AMZN", "AAPL", "BAC", 
    "NVDA", "PLTR", "NFLX", "MRNA", "AMD", "COIN", "SMCI", "IWM", "CVX", 
    "USO", "GLD", "TNA"
]

DB_NAME = "trades_backtest.db"

def init_db():
    """Inicializa la base de datos SQLite y crea la tabla de trades."""
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME) # Limpiar base anterior para iniciar de cero
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            strategy TEXT,
            type TEXT,
            entry_time TEXT,
            entry_price REAL,
            exit_time TEXT,
            exit_price REAL,
            return_pct REAL,
            duration_hours REAL,
            result TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("Base de datos inicializada correctamente.")

def download_data(ticker):
    """Descarga los datos históricos de 1H y 1D usando yfinance."""
    print(f"Descargando datos para {ticker}...")
    try:
        # Descarga de 1H (Yahoo Finance permite max 730 días) enviando la sesión custom
        df_1h = yf.download(ticker, period="730d", interval="1h", session=session, progress=False)
        # Descarga de 1D (5 años para promedios de 100/200) enviando la sesión custom
        df_1d = yf.download(ticker, period="5y", interval="1d", session=session, progress=False)
        return df_1h, df_1d
    except Exception as e:
        print(f"Error al descargar datos de {ticker}: {e}")
        return None, None

def run_backtest(ticker, df_1h, df_1d):
    """Ejecuta el backtesting de las estrategias de opciones sobre el ticker."""
    if df_1h.empty or df_1d.empty:
        return []

    # Aplanar columnas multi-nivel si yfinance las descarga así
    if isinstance(df_1h.columns, pd.MultiIndex):
        df_1h.columns = [col[0] for col in df_1h.columns]
    if isinstance(df_1d.columns, pd.MultiIndex):
        df_1d.columns = [col[0] for col in df_1d.columns]

    # Calcular promedios móviles diarios
    df_1d['Daily_SMA100'] = df_1d['Close'].rolling(window=100).mean()
    df_1d['Daily_SMA200'] = df_1d['Close'].rolling(window=200).mean()
    
    # Mapear los promedios diarios y precios al DataFrame horario por fecha
    df_1h['Date_Only'] = df_1h.index.date
    # Crear subset con SMA y precios diarios
    df_1d_subset = df_1d[['Daily_SMA100', 'Daily_SMA200', 'Open', 'High', 'Low', 'Close']].copy()
    df_1d_subset.rename(columns={
        'Open': 'Daily_Open',
        'High': 'Daily_High',
        'Low': 'Daily_Low',
        'Close': 'Daily_Close'
    }, inplace=True)
    df_1d_subset['Date_Only'] = df_1d_subset.index.date
    
    # Hacer merge para alinear las MAs y precios diarios con las horas
    df = df_1h.reset_index().merge(df_1d_subset, on='Date_Only', how='left').set_index('Datetime')
    
    # Calcular promedios horariales (1H)
    df['PM10'] = df['Close'].rolling(window=10).mean()
    df['PM20'] = df['Close'].rolling(window=20).mean()
    df['PM40'] = df['Close'].rolling(window=40).mean()
    df['PM100'] = df['Close'].rolling(window=100).mean()
    df['PM200'] = df['Close'].rolling(window=200).mean()

    # Detección de primera y última vela del día
    # Convertimos index a Series para poder usar shift
    datetime_series = pd.Series(df.index, index=df.index)
    df['is_first_bar'] = datetime_series.dt.normalize() != datetime_series.shift(1).dt.normalize()
    df['is_second_bar'] = df['is_first_bar'].shift(1).fillna(False)
    
    # Detección de última vela (15:30 EST)
    df['is_last_bar'] = datetime_series.dt.hour == 15

    # Patrones de velas
    df['body'] = (df['Close'] - df['Open']).abs()
    df['range_c'] = df['High'] - df['Low']
    df['is_green'] = df['Close'] > df['Open']
    df['is_red'] = df['Close'] < df['Open']
    
    df['is_solid_green'] = df['is_green'] & (df['body'] > 0.6 * df['range_c'])
    df['is_solid_red'] = df['is_red'] & (df['body'] > 0.6 * df['range_c'])
    df['is_hammer'] = df['is_green'] & ((df['Open'] - df['Low']) > 2 * df['body']) & ((df['High'] - df['Close']) < 0.2 * df['body'])
    df['is_hanger'] = df['is_red'] & ((df['Close'] - df['Low']) > 2 * df['body']) & ((df['High'] - df['Open']) < 0.2 * df['body'])

    # Mejoras de Colas de Rechazo (Piso y Techo)
    df['lower_wick'] = np.where(df['is_green'], df['Open'] - df['Low'], df['Close'] - df['Low'])
    df['upper_wick'] = np.where(df['is_green'], df['High'] - df['Close'], df['High'] - df['Open'])
    df['is_cola_piso'] = (df['range_c'] > 0) & (df['lower_wick'] >= 0.5 * df['range_c']) & (df['body'] <= 0.4 * df['range_c'])
    df['is_cola_techo'] = (df['range_c'] > 0) & (df['upper_wick'] >= 0.5 * df['range_c']) & (df['body'] <= 0.4 * df['range_c'])

    # Soportes y Resistencias de corto plazo (Donchian 20)
    df['lowest_20'] = df['Low'].shift(1).rolling(window=20).min()
    df['near_low'] = df['Low'] <= df['lowest_20'] + df['range_c'] * 0.5
    df['highest_20'] = df['High'].shift(1).rolling(window=20).max()
    df['near_high'] = df['High'] >= df['highest_20'] - df['range_c'] * 0.5

    # Variables de estado diarias para las estrategias
    df['gap_percent'] = np.nan
    df['first_bar_low'] = np.nan
    df['first_bar_green'] = None
    df['first_bar_red'] = None
    
    # Agrupamos por día para calcular variables de la primera vela y los gaps
    # Rellenamos de forma continua para el resto de las horas del día
    first_bars = df[df['is_first_bar']].copy()
    if not first_bars.empty:
        # Ayer close
        yesterday_closes = df_1d['Close'].shift(1)
        yesterday_closes.index = yesterday_closes.index.date
        
        first_bar_dates = first_bars.index.date
        yesterday_close_vals = yesterday_closes.loc[first_bar_dates].values
        
        first_bars['gap_percent'] = (first_bars['Open'] - yesterday_close_vals) / yesterday_close_vals * 100
        first_bars['first_bar_low'] = first_bars['Low']
        first_bars['first_bar_green'] = first_bars['is_solid_green'] | first_bars['is_hammer']
        first_bars['first_bar_red'] = first_bars['is_solid_red'] | first_bars['is_hanger']
        
        # Asignamos de vuelta
        df.loc[first_bars.index, 'gap_percent'] = first_bars['gap_percent']
        df.loc[first_bars.index, 'first_bar_low'] = first_bars['first_bar_low']
        df.loc[first_bars.index, 'first_bar_green'] = first_bars['first_bar_green']
        df.loc[first_bars.index, 'first_bar_red'] = first_bars['first_bar_red']
        
        # Propagar valores a lo largo del día
        df['gap_percent'] = df.groupby('Date_Only')['gap_percent'].ffill()
        df['first_bar_low'] = df.groupby('Date_Only')['first_bar_low'].ffill()
        df['first_bar_green'] = df.groupby('Date_Only')['first_bar_green'].ffill().fillna(False).astype(bool)
        df['first_bar_red'] = df.groupby('Date_Only')['first_bar_red'].ffill().fillna(False).astype(bool)

    # Evaluar si el piso de la primera vela se respetó todo el día
    df['low_so_far'] = df.groupby('Date_Only')['Low'].cummin()
    df['floor_respected'] = df['low_so_far'] >= df['first_bar_low']

    # Tendencias diarias
    df['d_trend_bullish'] = df['Close'] > df['Daily_SMA100']
    df['d_near_sma100'] = (df['Close'] - df['Daily_SMA100']).abs() / df['Daily_SMA100'] < 0.015
    df['d_near_sma200'] = (df['Close'] - df['Daily_SMA200']).abs() / df['Daily_SMA200'] < 0.015
    df['d_at_floor'] = df['d_near_sma100'] | df['d_near_sma200']

    # Zonas de medias móviles para rebotes en 1H
    df['near_ma_piso'] = (
        (df['Low'] <= df['PM10'] * 1.0015) & (df['Close'] >= df['PM10']) |
        (df['Low'] <= df['PM20'] * 1.0015) & (df['Close'] >= df['PM20']) |
        (df['Low'] <= df['PM40'] * 1.0015) & (df['Close'] >= df['PM40']) |
        (df['Low'] <= df['PM100'] * 1.0015) & (df['Close'] >= df['PM100']) |
        (df['Low'] <= df['PM200'] * 1.0015) & (df['Close'] >= df['PM200'])
    )
    df['near_ma_techo'] = (
        (df['High'] >= df['PM10'] * 0.9985) & (df['Close'] <= df['PM10']) |
        (df['High'] >= df['PM20'] * 0.9985) & (df['Close'] <= df['PM20']) |
        (df['High'] >= df['PM40'] * 0.9985) & (df['Close'] <= df['PM40']) |
        (df['High'] >= df['PM100'] * 0.9985) & (df['Close'] <= df['PM100']) |
        (df['High'] >= df['PM200'] * 0.9985) & (df['Close'] <= df['PM200'])
    )
    
    df['cond_cola_piso'] = df['is_cola_piso'] & (df['near_low'] | df['near_ma_piso'])
    df['cond_cola_techo'] = df['is_cola_techo'] & (df['near_high'] | df['near_ma_techo'])

    # 11. Promedio Móvil de 40 (CALL)
    is_touch_pm40 = (df['Low'] <= df['PM40'] * 1.0015) & (df['Close'] >= df['PM40'] * 0.9985)
    df['touched_pm40'] = is_touch_pm40.rolling(window=4).max().fillna(0).astype(bool)
    df['highest_high_3'] = df['High'].shift(1).rolling(window=3).max()
    df['cross_highest_3'] = (df['Close'] > df['highest_high_3']) & (df['Close'].shift(1) <= df['highest_high_3'].shift(1))
    df['cond_pm40_bounce'] = (df['PM20'] > df['PM40']) & df['touched_pm40'] & df['cross_highest_3'] & df['is_solid_green']

    # 12. Caída Normal y Caída Fuerte (CALL)
    df['recent_peak'] = df['High'].shift(1).rolling(window=10).max()
    df['pct_drop'] = (df['recent_peak'] - df['Low']) / df['recent_peak'] * 100
    df['is_caida_valida'] = df['pct_drop'] >= 0.5
    df['cond_caida_break'] = df['d_trend_bullish'] & df['is_caida_valida'] & df['cross_highest_3'] & df['is_solid_green']

    # 13. Ruptura del Canal Bajista (CALL)
    df['highest_high_15'] = df['High'].shift(1).rolling(window=15).max()
    df['cross_highest_15'] = (df['Close'] > df['highest_high_15']) & (df['Close'].shift(1) <= df['highest_high_15'].shift(1))
    df['in_descending_channel'] = df['PM20'] < df['PM40']
    df['cond_canal_break'] = df['in_descending_channel'] & df['cross_highest_15'] & df['is_solid_green']

    # 14. Hanger en Diario (PUT)
    df['d_body'] = (df['Daily_Close'] - df['Daily_Open']).abs()
    df['d_range'] = df['Daily_High'] - df['Daily_Low']
    df['d_upper_wick'] = df['Daily_High'] - np.maximum(df['Daily_Open'], df['Daily_Close'])
    df['d_is_hanger'] = (df['d_range'] > 0) & (df['d_upper_wick'] >= 0.5 * df['d_range']) & (df['d_body'] <= 0.4 * df['d_range'])
    df['cond_hanger_diario'] = df['is_last_bar'] & df['d_is_hanger'] & (df['Close'] > df['Daily_SMA100'])

    # 15. Ruptura de Resistencia (CALL)
    df['highest_high_20'] = df['High'].shift(1).rolling(window=20).max()
    df['cross_highest_20'] = (df['Close'] > df['highest_high_20']) & (df['Close'].shift(1) <= df['highest_high_20'].shift(1))
    df['cond_ruptura_res'] = df['d_trend_bullish'] & df['cross_highest_20'] & df['is_solid_green']

    # 16. Ruptura de Soporte (PUT)
    df['lowest_low_20'] = df['Low'].shift(1).rolling(window=20).min()
    df['cross_lowest_20'] = (df['Close'] < df['lowest_low_20']) & (df['Close'].shift(1) >= df['lowest_low_20'].shift(1))
    df['cond_ruptura_sop'] = (~df['d_trend_bullish']) & df['cross_lowest_20'] & df['is_solid_red']

    # 17. Ruptura de Piso Fuerte (PUT)
    df['crossunder_sma100'] = (df['Close'] < df['Daily_SMA100']) & (df['Close'].shift(1) >= df['Daily_SMA100'].shift(1))
    df['crossunder_sma200'] = (df['Close'] < df['Daily_SMA200']) & (df['Close'].shift(1) >= df['Daily_SMA200'].shift(1))
    df['cond_piso_break'] = (df['crossunder_sma100'] | df['crossunder_sma200']) & df['is_solid_red']

    # 18. Gap Bajista de Continuación (PUT)
    df['cond_gap_cont_put'] = df['is_second_bar'] & (df['gap_percent'] < -0.1) & df['first_bar_red'] & df['is_red']

    # Simulación de posiciones
    trades = []
    position = None # Puede ser 'CALL' o 'PUT'
    entry_price = 0.0
    entry_time = None
    entry_strategy = ""

    # Recorrer barra por barra para simular
    for i in range(len(df)):
        row = df.iloc[i]
        bar_time = df.index[i]
        
        if pd.isna(row['Close']):
            continue

        # LÓGICA DE SALIDA
        if position == 'CALL':
            # Salida: Primera vela roja del día siguiente
            if row['is_first_bar'] and row['is_red']:
                exit_price = row['Close']
                return_pct = (exit_price - entry_price) / entry_price * 100
                duration = (bar_time - entry_time).total_seconds() / 3600.0
                trades.append({
                    'ticker': ticker,
                    'strategy': entry_strategy,
                    'type': 'CALL',
                    'entry_time': entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'entry_price': float(entry_price),
                    'exit_time': bar_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'exit_price': float(exit_price),
                    'return_pct': float(return_pct),
                    'duration_hours': float(duration),
                    'result': 'WIN' if return_pct > 0 else 'LOSS'
                })
                position = None
                continue

        elif position == 'PUT':
            # Salida: Primera vela verde del día siguiente
            if row['is_first_bar'] and row['is_green']:
                exit_price = row['Close']
                return_pct = (entry_price - exit_price) / entry_price * 100 # Put gana cuando cae
                duration = (bar_time - entry_time).total_seconds() / 3600.0
                trades.append({
                    'ticker': ticker,
                    'strategy': entry_strategy,
                    'type': 'PUT',
                    'entry_time': entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'entry_price': float(entry_price),
                    'exit_time': bar_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'exit_price': float(exit_price),
                    'return_pct': float(return_pct),
                    'duration_hours': float(duration),
                    'result': 'WIN' if return_pct > 0 else 'LOSS'
                })
                position = None
                continue

        # LÓGICA DE ENTRADA (Solo si no estamos en posición)
        if position is None:
            # 1. Gap Normal al Alza (CALL)
            if row['d_trend_bullish'] and row['is_second_bar'] and row['gap_percent'] > 0.1 and row['first_bar_green'] and row['is_green']:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Gap Normal al Alza"
                continue
            
            # 2. Gap Bajista al Alza (CALL)
            elif row['is_second_bar'] and row['gap_percent'] < -0.1 and row['first_bar_green'] and row['is_green']:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Gap Bajista al Alza"
                continue
                
            # 3. Piso Fuerte (CALL)
            elif row['d_trend_bullish'] and row['d_at_floor'] and (row['is_solid_green'] or row['is_hammer']) and row['Close'] > row['PM20'] and df['Close'].iloc[max(0, i-1)] <= df['PM20'].iloc[max(0, i-1)]:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Piso Fuerte"
                continue

            # 4. Primer Gap al Alza (CALL)
            elif row['d_at_floor'] and row['is_last_bar'] and row['gap_percent'] > 0.1 and row['first_bar_green'] and row['floor_respected']:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Primer Gap al Alza"
                continue

            # 5. Cola de Piso (CALL)
            elif row['cond_cola_piso']:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Cola de Piso"
                continue

            # 6. Primera Vela Roja (PUT)
            elif row['is_first_bar'] and row['is_solid_red'] and row['Close'] > row['PM40']:
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Primera Vela Roja"
                continue

            # 7. Techo Fuerte (PUT)
            elif row['d_at_floor'] and row['is_second_bar'] and row['is_red'] and row['is_solid_red']:
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Techo Fuerte"
                continue

            # 8. Ruptura del Piso del Gap (PUT)
            elif not row['is_first_bar'] and row['Close'] > row['PM40'] and df['Close'].iloc[max(0, i-1)] >= row['first_bar_low'] and row['Close'] < row['first_bar_low'] and row['is_solid_red']:
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Ruptura Piso del Gap"
                continue

            # 9. Modelo de los 4 Pasos (PUT)
            elif row['Close'] < row['PM40'] and row['is_red'] and df['is_green'].iloc[max(0, i-1)] and df['Close'].iloc[max(0, i-1)] > df['Open'].iloc[max(0, i-1)] and row['Close'] < df['Open'].iloc[max(0, i-1)] and row['Close'] < df['Low'].iloc[max(0, i-3):i].min():
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Modelo de 4 Pasos"
                continue

            # 10. Cola de Techo (PUT)
            elif row['cond_cola_techo']:
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Cola de Techo"
                continue

            # 11. Promedio Móvil de 40 (CALL)
            elif row['cond_pm40_bounce']:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Promedio Móvil de 40"
                continue

            # 12. Caída Normal/Fuerte (CALL)
            elif row['cond_caida_break']:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Caída Normal/Fuerte"
                continue

            # 13. Ruptura Canal Bajista (CALL)
            elif row['cond_canal_break']:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Ruptura Canal Bajista"
                continue

            # 14. Hanger en Diario (PUT)
            elif row['cond_hanger_diario']:
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Hanger en Diario"
                continue

            # 15. Ruptura de Resistencia (CALL)
            elif row['cond_ruptura_res']:
                position = 'CALL'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Ruptura de Resistencia"
                continue

            # 16. Ruptura de Soporte (PUT)
            elif row['cond_ruptura_sop']:
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Ruptura de Soporte"
                continue

            # 17. Ruptura de Piso Fuerte (PUT)
            elif row['cond_piso_break']:
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Ruptura de Piso Fuerte"
                continue

            # 18. Gap Bajista de Continuación (PUT)
            elif row['cond_gap_cont_put']:
                position = 'PUT'
                entry_price = row['Close']
                entry_time = bar_time
                entry_strategy = "Gap Bajista de Continuación"
                continue

    return trades

def save_trades(trades):
    """Guarda la lista de trades en la base de datos SQLite."""
    if not trades:
        return
        
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    for t in trades:
        cursor.execute("""
            INSERT INTO trades (ticker, strategy, type, entry_time, entry_price, exit_time, exit_price, return_pct, duration_hours, result)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (t['ticker'], t['strategy'], t['type'], t['entry_time'], t['entry_price'], t['exit_time'], t['exit_price'], t['return_pct'], t['duration_hours'], t['result']))
        
    conn.commit()
    conn.close()

def main():
    init_db()
    total_trades_count = 0
    
    for ticker in TICKERS:
        df_1h, df_1d = download_data(ticker)
        if df_1h is not None and df_1d is not None:
            trades = run_backtest(ticker, df_1h, df_1d)
            if trades:
                save_trades(trades)
                print(f"-> Se guardaron {len(trades)} trades para {ticker}.")
                total_trades_count += len(trades)
            else:
                print(f"-> No se encontraron trades para {ticker}.")
        else:
            print(f"-> Saltando {ticker} debido a un error en la descarga.")
            
    print(f"\nBacktesting finalizado. Total de trades guardados en SQLite: {total_trades_count}")

if __name__ == "__main__":
    main()

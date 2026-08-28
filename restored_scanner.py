Total Bytes: 26316
import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
import requests
import ssl
import urllib3
from datetime import datetime

# Deshabilitar advertencias de SSL inseguro y configurar sesión
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

session = requests.Session()
session.verify = False
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

# ==========================================
# CONFIGURACIÓN
# ==========================================
# Cargar configuración local de forma segura
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
WEBHOOK_URL = "TU_WEBHOOK_URL_AQUÍ"

if os.path.exists(CONFIG_PATH):
    try:
        import json
        with open(CONFIG_PATH, "r", encoding="utf-8") as config_f:
            config_data = json.load(config_f)
            WEBHOOK_URL = config_data.get("webhook_url", WEBHOOK_URL)
    except Exception as e:
        print(f"Advertencia: No se pudo cargar config.json: {e}")

TICKERS = [
    "SPY", "META", "QQQ", "MSFT", "TSLA", "GOOGL", "AMZN", "AAPL", "BAC", 
    "NVDA", "PLTR", "NFLX", "MRNA", "AMD", "COIN", "SMCI", "IWM", "CVX", 
    "USO", "GLD", "TNA"
]

STRATEGIES_METADATA = {
    "cond_gap_normal": ("Gap Normal al Alza", "CALL", "51.02%"),
    "cond_gap_bajista": ("Gap Bajista al Alza", "CALL", "41.45%"),
    "cond_piso_fuerte": ("Piso Fuerte", "CALL", "28.00%"),
    "cond_primer_gap": ("Primer Gap al Alza", "CALL", "37.50%"),
    "cond_cola_piso": ("Cola de Piso", "CALL", "47.81%"),
    "cond_pm40_bounce": ("Promedio Móvil de 40", "CALL", "47.88%"),
    "cond_caida_break": ("Caída Normal/Fuerte", "CALL", "44.83%"),
    "cond_canal_break": ("Ruptura Canal Bajista", "CALL", "46.30%"),
    "cond_ruptura_res": ("Ruptura de Resistencia", "CALL", "48.15%"),
    "cond_vela_roja": ("Primera Vela Roja", "PUT", "50.00%"),
    "cond_techo_fuerte": ("Techo Fuerte", "PUT", "40.15%"),
    "cond_ruptura_piso": ("Ruptura Piso del Gap", "PUT", "37.78%"),
    "cond_4_pasos": ("Modelo de 4 Pasos", "PUT", "40.94%"),
    "cond_cola_techo": ("Cola de Techo", "PUT", "39.47%"),
    "cond_hanger_diario": ("Hanger en Diario", "PUT", "42.86%"),
    "cond_ruptura_sop": ("Ruptura de Soporte", "PUT", "37.86%"),
    "cond_piso_break": ("Ruptura de Piso Fuerte", "PUT", "37.84%"),
    "cond_gap_cont_put": ("Gap Bajista de Continuación", "PUT", "36.61%")
}

def scan_ticker(ticker):
    """Descarga datos recientes y evalúa si hay estrategias activas en la última barra cerrada."""
    print(f"Buscando señales para {ticker}...")
    try:
        # Descarga 30 días de datos horarios y 1 año de datos diarios para los promedios
        df_1h = yf.download(ticker, period="30d", interval="1h", session=session, progress=False)
        df_1d = yf.download(ticker, period="1y", interval="1d", session=session, progress=False)
        if df_1h.empty or df_1d.empty:
            return []
        # Aplanar columnas multi-nivel si yfinance las descarga así
        if isinstance(df_1h.columns, pd.MultiIndex):
            df_1h.columns = [col[0] for col in df_1h.columns]
        if isinstance(df_1d.columns, pd.MultiIndex):
            df_1d.columns = [col[0] for col in df_1d.columns]
        # Calcular SMA diarios
        df_1d['Daily_SMA100'] = df_1d['Close'].rolling(window=100).mean()
        df_1d['Daily_SMA200'] = df_1d['Close'].rolling(window=200).mean()
        # Merge de promedios diarios con datos horarios
        df_1h['Date_Only'] = df_1h.index.date
        df_1d_subset = df_1d[['Daily_SMA100', 'Daily_SMA200', 'Open', 'High', 'Low', 'Close']].copy()
        df_1d_subset.rename(columns={
            'Open': 'Daily_Open',
            'High': 'Daily_High',
            'Low': 'Daily_Low',
            'Close': 'Daily_Close'
        }, inplace=True)
        df_1d_subset['Date_Only'] = df_1d_subset.index.date
        df = df_1h.reset_index().merge(df_1d_subset, on='Date_Only', how='left').set_index('Datetime')
        # Calcular medias móviles horarias
        df['PM10'] = df['Close'].rolling(window=10).mean()
        df['PM20'] = df['Close'].rolling(window=20).mean()
        df['PM40'] = df['Close'].rolling(window=40).mean()
        df['PM100'] = df['Close'].rolling(window=100).mean()
        df['PM200'] = df['Close'].rolling(window=200).mean()
        # Detección de sesión
        datetime_series = pd.Series(df.index, index=df.index)
        df['is_first_bar'] = datetime_series.dt.normalize() != datetime_series.shift(1).dt.normalize()
        df['is_second_bar'] = df['is_first_bar'].shift(1).fillna(False)
        df['is_last_bar'] = datetime_series.dt.hour == 15
        # Cuerpo y rango
        df['body'] = (df['Close'] - df['Open']).abs()
        df['range_c'] = df['High'] - df['Low']
        df['is_green'] = df['Close'] > df['Open']
        df['is_red'] = df['Close'] < df['Open']
        # Tipo de velas
        df['is_solid_green'] = df['is_green'] & (df['body'] > 0.6 * df['range_c'])
        df['is_solid_red'] = df['is_red'] & (df['body'] > 0.6 * df['range_c'])
        df['is_hammer'] = df['is_green'] & ((df['Open'] - df['Low']) > 2 * df['body']) & ((df['High'] - df['Close']) < 0.2 * df['body'])
        df['is_hanger'] = df['is_red'] & ((df['Close'] - df['Low']) > 2 * df['body']) & ((df['High'] - df['Open']) < 0.2 * df['body'])
        # Colas de piso/techo
        df['lower_wick'] = np.where(df['is_green'], df['Open'] - df['Low'], df['Close'] - df['Low'])
        df['upper_wick'] = np.where(df['is_green'], df['High'] - df['Close'], df['High'] - df['Open'])
        df['is_cola_piso'] = (df['range_c'] > 0) & (df['lower_wick'] >= 0.5 * df['range_c']) & (df['body'] <= 0.4 * df['range_c'])
        df['is_cola_techo'] = (df['range_c'] > 0) & (df['upper_wick'] >= 0.5 * df['range_c']) & (df['body'] <= 0.4 * df['range_c'])
        # Canales Donchian y soportes
        df['lowest_20'] = df['Low'].shift(1).rolling(window=20).min()
        df['near_low'] = df['Low'] <= df['lowest_20'] + df['range_c'] * 0.5
        df['highest_20'] = df['High'].shift(1).rolling(window=20).max()
        df['near_high'] = df['High'] >= df['highest_20'] - df['range_c'] * 0.5
        # Variables diarias
        df['gap_percent'] = np.nan
        df['first_bar_low'] = np.nan
        df['first_bar_green'] = None
        df['first_bar_red'] = None
        first_bars = df[df['is_first_bar']].copy()
        if not first_bars.empty:
            yesterday_closes = df_1d['Close'].shift(1)
            yesterday_closes.index = yesterday_closes.index.date
            first_bar_dates = first_bars.index.date
            yesterday_close_vals = yesterday_closes.loc[first_bar_dates].values
            first_bars['gap_percent'] = (first_bars['Open'] - yesterday_close_vals) / yesterday_close_vals * 100
            first_bars['first_bar_low'] = first_bars['Low']
            first_bars['first_bar_green'] = first_bars['is_solid_green'] | first_bars['is_hammer']
            first_bars['first_bar_red'] = first_bars['is_solid_red'] | first_bars['is_hanger']
            df.loc[first_bars.index, 'gap_percent'] = first_bars['gap_percent']
            df.loc[first_bars.index, 'first_bar_low'] = first_bars['first_bar_low']
            df.loc[first_bars.index, 'first_bar_green'] = first_bars['first_bar_green']
            df.loc[first_bars.index, 'first_bar_red'] = first_bars['first_bar_red']
            df['gap_percent'] = df.groupby('Date_Only')['gap_percent'].ffill()
            df['first_bar_low'] = df.groupby('Date_Only')['first_bar_low'].ffill()
            df['first_bar_green'] = df.groupby('Date_Only')['first_bar_green'].ffill().fillna(False).astype(bool)
            df['first_bar_red'] = df.groupby('Date_Only')['first_bar_red'].ffill().fillna(False).astype(bool)
        df['low_so_far'] = df.groupby('Date_Only')['Low'].cummin()
        df['floor_respected'] = df['low_so_far'] >= df['first_bar_low']
        # Tendencias diarias
        df['d_trend_bullish'] = df['Close'] > df['Daily_SMA100']
        df['d_near_sma100'] = (df['Close'] - df['Daily_SMA100']).abs() / df['Daily_SMA100'] < 0.015
        df['d_near_sma200'] = (df['Close'] - df['Daily_SMA200']).abs() / df['Daily_SMA200'] < 0.015
        df['d_at_floor'] = df['d_near_sma100'] | df['d_near_sma200']
        # Zonas medias móviles
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
            (df['High'] >= df['PM100'] * 0.9985) & (df['Close'] >= df['PM100']) |
            (df['High'] >= df['PM200'] * 0.9985) & (df['Close'] <= df['PM200'])
        )
        df['cond_cola_piso'] = df['is_cola_piso'] & (df['near_low'] | df['near_ma_piso'])
        df['cond_cola_techo'] = df['is_cola_techo'] & (df['near_high'] | df['near_ma_techo'])
        # PM 40
        is_touch_pm40 = (df['Low'] <= df['PM40'] * 1.0015) & (df['Close'] >= df['PM40'] * 0.9985)
        df['touched_pm40'] = is_touch_pm40.rolling(window=4).max().fillna(0).astype(bool)
        df['highest_high_3'] = df['High'].shift(1).rolling(window=3).max()
        df['cross_highest_3'] = (df['Close'] > df['highest_high_3']) & (df['Close'].shift(1) <= df['highest_high_3'].shift(1))
        df['cond_pm40_bounce'] = (df['PM20'] > df['PM40']) & df['touched_pm40'] & df['cross_highest_3'] & df['is_solid_green']
        # Caída
        df['recent_peak'] = df['High'].shift(1).rolling(window=10).max()
        df['pct_drop'] = (df['recent_peak'] - df['Low']) / df['recent_peak'] * 100
        df['is_caida_valida'] = df['pct_drop'] >= 0.5
        df['cond_caida_break'] = df['d_trend_bullish'] & df['is_caida_valida'] & df['cross_highest_3'] & df['is_solid_green']
        # Canal
        df['highest_high_15'] = df['High'].shift(1).rolling(window=15).max()
        df['cross_highest_15'] = (df['Close'] > df['highest_high_15']) & (df['Close'].shift(1) <= df['highest_high_15'].shift(1))
        df['in_descending_channel'] = df['PM20'] < df['PM40']
        df['cond_canal_break'] = df['in_descending_channel'] & df['cross_highest_15'] & df['is_solid_green']
        # Hanger
        df['d_body'] = (df['Daily_Close'] - df['Daily_Open']).abs()
        df['d_range'] = df['Daily_High'] - df['Daily_Low']
        df['d_upper_wick'] = df['Daily_High'] - np.maximum(df['Daily_Open'], df['Daily_Close'])
        df['d_is_hanger'] = (df['d_range'] > 0) & (df['d_upper_wick'] >= 0.5 * df['d_range']) & (df['d_body'] <= 0.4 * df['d_range'])
        df['cond_hanger_diario'] = df['is_last_bar'] & df['d_is_hanger'] & (df['Close'] > df['Daily_SMA100'])
        # Rupturas
        df['highest_high_20'] = df['High'].shift(1).rolling(window=20).max()
        df['cross_highest_20'] = (df['Close'] > df['highest_high_20']) & (df['Close'].shift(1) <= df['highest_high_20'].shift(1))
        df['cond_ruptura_res'] = df['d_trend_bullish'] & df['cross_highest_20'] & df['is_solid_green']
        df['lowest_low_20'] = df['Low'].shift(1).rolling(window=20).min()
        df['cross_lowest_20'] = (df['Close'] < df['lowest_low_20']) & (df['Close'].shift(1) >= df['lowest_low_20'].shift(1))
        df['cond_ruptura_sop'] = (~df['d_trend_bullish']) & df['cross_lowest_20'] & df['is_solid_red']
        # Piso break y gaps
        df['crossunder_sma100'] = (df['Close'] < df['Daily_SMA100']) & (df['Close'].shift(1) >= df['Daily_SMA100'].shift(1))
        df['crossunder_sma200'] = (df['Close'] < df['Daily_SMA200']) & (df['Close'].shift(1) >= df['Daily_SMA200'].shift(1))
        df['cond_piso_break'] = (df['crossunder_sma100'] | df['crossunder_sma200']) & df['is_solid_red']
        df['cond_gap_cont_put'] = df['is_second_bar'] & (df['gap_percent'] < -0.1) & df['first_bar_red'] & df['is_red']
        # Estrategias básicas (Gap normal, bajista, piso fuerte, primer gap, primera vela roja, techo fuerte, ruptura piso gap, modelo 4 pasos)
        df['cond_gap_normal'] = df['d_trend_bullish'] & df['is_second_bar'] & (df['gap_percent'] > 0.1) & df['first_bar_green'] & df['is_green']
        df['cond_gap_bajista'] = df['is_second_bar'] & (df['gap_percent'] < -0.1) & df['first_bar_green'] & df['is_green']
        df['cond_piso_fuerte'] = df['d_trend_bullish'] & df['d_at_floor'] & (df['is_solid_green'] | df['is_hammer']) & (df['Close'] > df['PM20']) & (df['Close'].shift(1) <= df['PM20'].shift(1))
        df['cond_primer_gap'] = df['d_at_floor'] & df['is_last_bar'] & (df['gap_percent'] > 0.1) & df['first_bar_green'] & df['floor_respected']
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

Total Bytes: 26316
        df['cond_primer_gap'] = df['d_at_floor'] & df['is_last_bar'] & (df['gap_percent'] > 0.1) & df['first_bar_green'] & df['floor_respected']
        df['cond_vela_roja'] = df['is_first_bar'] & df['is_solid_red'] & (df['Close'] > df['PM40'])
        df['cond_techo_fuerte'] = df['d_at_floor'] & df['is_second_bar'] & df['is_red'] & df['is_solid_red']
        df['cond_ruptura_piso'] = ~df['is_first_bar'] & (df['Close'] > df['PM40']) & (df['Close'].shift(1) >= df['first_bar_low']) & (df['Close'] < df['first_bar_low']) & df['is_solid_red']
        df['cond_4_pasos'] = (df['Close'] < df['PM40']) & df['is_red'] & df['is_green'].shift(1) & (df['Close'].shift(1) > df['Open'].shift(1)) & (df['Close'] < df['Open'].shift(1)) & (df['Close'] < df['Low'].shift(1).rolling(window=3).min())
        
        # Tomar la última barra completa
        # Durante el horario de mercado, la última barra del DataFrame horario puede ser la actual (incompleta)
        # Tomaremos la última fila, pero mostraremos su timestamp exacto
        last_idx = -1
        row = df.iloc[last_idx]
        bar_time = df.index[last_idx]
        
        # Si la última fila tiene valores nulos en columnas calculadas, retroceder una fila
        if pd.isna(row['PM20']):
            last_idx = -2
            row = df.iloc[last_idx]
            bar_time = df.index[last_idx]
            
        active_signals = []
        close_price = float(row['Close'])
        
        for cond_col, metadata in STRATEGIES_METADATA.items():
            if cond_col in df.columns and bool(row[cond_col]):
                active_signals.append({
                    "ticker": ticker,
                    "type": metadata[1],
                    "strategy": metadata[0],
                    "price": round(close_price, 2),
                    "probability": metadata[2],
                    "time": bar_time.strftime('%Y-%m-%d %H:%M:%S')
                })
                
        return active_signals
        
    except Exception as e:
        print(f"Error al escanear {ticker}: {e}")
        return []

def main():
    if WEBHOOK_URL == "TU_WEBHOOK_URL_AQUÍ":
        print("❌ ERROR: Debes configurar la variable WEBHOOK_URL con la dirección de tu Google Apps Script.")
        sys.exit(1)
        
    print(f"=== INICIANDO ESCANEO DE {len(TICKERS)} ACTIVOS ===")
    all_signals = []
    
    for ticker in TICKERS:
        signals = scan_ticker(ticker)
        if signals:
            print(f"🎯 ¡SEÑAL DETECTADA en {ticker}! {signals}")
            all_signals.extend(signals)
            
    print(f"\nEscaneo finalizado. Total de señales activas encontradas: {len(all_signals)}")
    print("📤 Enviando resultados a Google Sheets...")
    
    payload = {
        "action": "update_live_signals",
        "signals": all_signals
    }
    
    try:
        r = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "text/plain"}, verify=False)
        print(f"Respuesta del servidor: {r.status_code} - {r.text}")
        if r.status_code == 200:
            print("🎉 ¡Monitoreo en Google Sheets actualizado con éxito!")
        else:
            print("❌ Hubo un problema al actualizar la hoja.")
    except Exception as e:
        print(f"❌ Error al enviar datos al webhook: {e}")
        
    return all_signals

# ==========================================
# SERVIDOR HTTP DE CONTROL LOCAL (PUERTO 8055)
# ==========================================
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

Total Bytes: 26316
# ==========================================
import threading
import subprocess
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer

def run_backtesting():
    print("[Control Web] Iniciando ejecución de backtest_to_db.py...")
    proc1 = subprocess.run([sys.executable, "backtest_to_db.py"], capture_output=True, text=True)
    print("[Control Web] Iniciando ejecución de analyze_results.py...")
    proc2 = subprocess.run([sys.executable, "analyze_results.py"], capture_output=True, text=True)
    return proc1.returncode == 0 and proc2.returncode == 0

def sync_backtest_results_to_sheets():
    db_path = "trades_backtest.db"
    if not os.path.exists(db_path):
        return {"status": "error", "message": "No existe la base de datos de backtesting. Por favor ejecuta el backtesting primero."}
        
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query("SELECT * FROM trades", conn)
        conn.close()
        
        if df.empty:
            return {"status": "error", "message": "La base de datos de backtesting está vacía."}
            
        total_trades = len(df)
        df['return_pct'] = pd.to_numeric(df['return_pct'])
        df['duration_hours'] = pd.to_numeric(df['duration_hours'])
        
        winning_trades = len(df[df['return_pct'] > 0])
        losing_trades = len(df[df['return_pct'] <= 0])
        win_rate = round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0
        
        gross_profits = df[df['return_pct'] > 0]['return_pct'].sum()
        gross_losses = abs(df[df['return_pct'] <= 0]['return_pct'].sum())
        profit_factor = round((gross_profits / gross_losses), 2) if gross_losses > 0 else "Infinito"
        
        avg_return = round(df['return_pct'].mean(), 2)
        max_win = round(df['return_pct'].max(), 2)
        max_loss = round(df['return_pct'].min(), 2)
        avg_duration = round(df['duration_hours'].mean(), 1)
        
        summary = [
            {"metrica": "Total de Operaciones", "valor": total_trades},
            {"metrica": "Operaciones Ganadoras", "valor": winning_trades},
            {"metrica": "Operaciones Perdedoras", "valor": losing_trades},
            {"metrica": "Tasa de Acierto (Win Rate %)", "valor": win_rate},
            {"metrica": "Factor de Ganancia (Profit Factor)", "valor": profit_factor},
            {"metrica": "Retorno Promedio por Trade (%)", "valor": avg_return},
            {"metrica": "Mejor Retorno (%)", "valor": max_win},
            {"metrica": "Peor Retorno (%)", "valor": max_loss},
            {"metrica": "Duración Promedio (Horas)", "valor": avg_duration}
        ]
        
        strat_groups = df.groupby('strategy')
        by_strategy = []
        for name, group in strat_groups:
            t_trades = len(group)
            w_trades = len(group[group['return_pct'] > 0])
            w_rate = round((w_trades / t_trades * 100), 2) if t_trades > 0 else 0.0
            a_return = round(group['return_pct'].mean(), 2)
            by_strategy.append({
                "estrategia": name,
                "trades": t_trades,
                "win_rate": w_rate,
                "avg_return": a_return
            })
        by_strategy.sort(key=lambda x: x["avg_return"], reverse=True)
            
        ticker_groups = df.groupby('ticker')
        by_ticker = []
        for name, group in ticker_groups:
            t_trades = len(group)
            w_trades = len(group[group['return_pct'] > 0])
            w_rate = round((w_trades / t_trades * 100), 2) if t_trades > 0 else 0.0
            a_return = round(group['return_pct'].mean(), 2)
            by_ticker.append({
                "ticker": name,
                "trades": t_trades,
                "win_rate": w_rate,
                "avg_return": a_return
            })
        by_ticker.sort(key=lambda x: x["avg_return"], reverse=True)
            
        payload = {
            "action": "update_backtest_data",
            "summary": summary,
            "by_strategy": by_strategy,
            "by_ticker": by_ticker
        }
        
        r = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "text/plain"}, verify=False)
        if r.status_code == 200:
            return {"status": "success", "message": "Resultados de backtesting sincronizados con Google Sheets."}
        else:
            return {"status": "error", "message": f"Error de Webhook ({r.status_code}): {r.text}"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

class BotControlServer(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Silenciar logs en consola para mantenerla limpia
        
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        BaseHTTPRequestHandler.end_headers(self)

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == '/ping':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "online", "message": "Bot de Monitoreo en Vivo está activo."}).encode('utf-8'))
        elif self.path == '/scan':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            print("\n[Control Web] Ejecutando escaneo manual forzado en vivo...")
            try:
                signals = main()
                self.wfile.write(json.dumps({"status": "success", "signals": signals}).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/backtest':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
The above content does NOT show the entire file contents. If you need to view any lines of the file which were not shown to complete your task, call this tool again to view those lines.

        elif self.path == '/sync_backtest':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            print('\n[Control Web] Sincronizando resultados del backtesting con Google Sheets...')
            try:
                res = sync_backtest_results_to_sheets()
                self.wfile.write(json.dumps(res).encode('utf-8'))
            except Exception as e:
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        elif self.path == '/ucharts.user.js':
            self.send_response(200)
            self.send_header('Content-Type', 'application/javascript; charset=utf-8')
            self.end_headers()
            try:
                script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ucharts_sync_userscript.js")
                with open(script_path, "r", encoding="utf-8") as sf:
                    code = sf.read()
                if WEBHOOK_URL and WEBHOOK_URL != "TU_WEBHOOK_URL_AQUÍ":
                    code = code.replace("TU_WEBHOOK_URL_AQUÍ", WEBHOOK_URL)
                self.wfile.write(code.encode('utf-8'))
            except Exception as e:
                self.wfile.write(f"// Error al servir el script: {e}".encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def start_control_server():
    server_address = ('127.0.0.1', 8055)
    try:
        httpd = HTTPServer(server_address, BotControlServer)
        print(f"\n📡 Servidor de control local del bot activo en http://127.0.0.1:8055/")
        httpd.serve_forever()
    except Exception as e:
        print(f"Error al iniciar servidor de control: {e}")

if __name__ == "__main__":
    import time
    t_web = threading.Thread(target=start_control_server, daemon=True)
    t_web.start()
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        interval = 15
        if len(sys.argv) > 2:
            try:
                interval = int(sys.argv[2])
            except ValueError:
                pass
        print(f"=== INICIANDO ESCÁNER EN BUCLE CONTINUO (CADA {interval} MINUTOS) ===")
        while True:
            try:
                main()
            except Exception as e:
                print(f"❌ Error inesperado en el escáner: {e}")
            print(f"\n[Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Esperando {interval} minutes... (Presiona Ctrl+C para salir)")
            time.sleep(interval * 60)
    else:
        main()
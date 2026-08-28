import sqlite3
import pandas as pd
import numpy as np

DB_NAME = "trades_backtest.db"
OUTPUT_EXCEL = "reporte_backtesting.xlsx"

def load_data():
    """Carga los trades de la base de datos SQLite."""
    try:
        conn = sqlite3.connect(DB_NAME)
        df = pd.read_sql_query("SELECT * FROM trades", conn)
        conn.close()
        return df
    except Exception as e:
        print(f"Error al conectar o leer la base de datos: {e}")
        return pd.DataFrame()

def generate_report():
    df = load_data()
    if df.empty:
        print("No hay trades registrados en la base de datos. Por favor, corre 'backtest_to_db.py' primero.")
        return

    # Convertir a tipos numéricos
    df['return_pct'] = pd.to_numeric(df['return_pct'])
    df['entry_price'] = pd.to_numeric(df['entry_price'])
    df['exit_price'] = pd.to_numeric(df['exit_price'])
    df['duration_hours'] = pd.to_numeric(df['duration_hours'])

    # --- 1. RESUMEN GENERAL ---
    total_trades = len(df)
    winning_trades = len(df[df['return_pct'] > 0])
    losing_trades = len(df[df['return_pct'] <= 0])
    
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    
    gross_profits = df[df['return_pct'] > 0]['return_pct'].sum()
    gross_losses = abs(df[df['return_pct'] <= 0]['return_pct'].sum())
    profit_factor = (gross_profits / gross_losses) if gross_losses > 0 else float('inf')
    
    avg_return = df['return_pct'].mean()
    max_win = df['return_pct'].max()
    max_loss = df['return_pct'].min()
    avg_duration = df['duration_hours'].mean()

    resumen_general_data = {
        'Métrica': [
            'Total de Operaciones', 
            'Operaciones Ganadoras', 
            'Operaciones Perdedoras', 
            'Tasa de Acierto (Win Rate %)', 
            'Factor de Ganancia (Profit Factor)', 
            'Retorno Promedio por Trade (%)', 
            'Mejor Retorno (%)', 
            'Peor Retorno (%)', 
            'Duración Promedio (Horas)'
        ],
        'Valor': [
            total_trades, 
            winning_trades, 
            losing_trades, 
            round(win_rate, 2), 
            round(profit_factor, 2) if profit_factor != float('inf') else 'Infinito', 
            round(avg_return, 2), 
            round(max_win, 2), 
            round(max_loss, 2), 
            round(avg_duration, 1)
        ]
    }
    df_resumen = pd.DataFrame(resumen_general_data)

    # --- 2. REPORTES AGRUPADOS ---
    # Por Ticker
    df_by_ticker = df.groupby('ticker').agg(
        Total_Trades=('id', 'count'),
        Ganadores=('return_pct', lambda x: (x > 0).sum()),
        Win_Rate_Pct=('return_pct', lambda x: round((x > 0).sum() / len(x) * 100, 2)),
        Retorno_Promedio_Pct=('return_pct', lambda x: round(x.mean(), 2)),
        Mejor_Trade_Pct=('return_pct', 'max'),
        Peor_Trade_Pct=('return_pct', 'min')
    ).reset_index()

    # Por Estrategia
    df_by_strategy = df.groupby('strategy').agg(
        Total_Trades=('id', 'count'),
        Ganadores=('return_pct', lambda x: (x > 0).sum()),
        Win_Rate_Pct=('return_pct', lambda x: round((x > 0).sum() / len(x) * 100, 2)),
        Retorno_Promedio_Pct=('return_pct', lambda x: round(x.mean(), 2)),
        Mejor_Trade_Pct=('return_pct', 'max'),
        Peor_Trade_Pct=('return_pct', 'min')
    ).reset_index()

    # --- Imprimir en Pantalla ---
    print("\n" + "="*50)
    print("           REPORTE GENERAL DE BACKTESTING")
    print("="*50)
    print(df_resumen.to_string(index=False))
    print("="*50)
    
    print("\nTop 5 Activos con Mejor Rendimiento Promedio:")
    print(df_by_ticker.sort_values(by='Retorno_Promedio_Pct', ascending=False).head(5).to_string(index=False))
    
    print("\nRendimiento de las Estrategias de Alejandro Cardona:")
    print(df_by_strategy.sort_values(by='Retorno_Promedio_Pct', ascending=False).to_string(index=False))
    print("="*50)

    # --- Exportar a Excel con Múltiples Hojas ---
    try:
        with pd.ExcelWriter(OUTPUT_EXCEL, engine='openpyxl') as writer:
            df_resumen.to_excel(writer, sheet_name='📌 Resumen General', index=False)
            df_by_ticker.to_excel(writer, sheet_name='📊 Por Activos', index=False)
            df_by_strategy.to_excel(writer, sheet_name='💡 Por Estrategias', index=False)
            df.to_excel(writer, sheet_name='📝 Registro de Trades', index=False)
        print(f"\nReporte completo exportado con éxito a Excel: {OUTPUT_EXCEL}")
    except Exception as e:
        print(f"Error al escribir el archivo de Excel: {e}")

if __name__ == "__main__":
    generate_report()

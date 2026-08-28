# Guía del Proyecto: Estrategias de Opciones Financieras (Alejandro Cardona)

Este proyecto implementa las estrategias de opciones financieras en dos partes complementarias:
1. **TradingView (Pine Script v5):** Para gráficos interactivos diarios, backtesting visual rápido y alertas push automáticas a tu celular.
2. **Python local & SQLite:** Para realizar un backtesting histórico robusto y automático sobre tus 21 activos favoritos, guardando cada operación en una base de datos local y generando un reporte en Excel.

---

## 🧭 PARTE 1: Configuración en TradingView

Sigue estos pasos para cargar las estrategias y los 5 promedios móviles con sus colores correctos:

### 1. Copiar el Código de Pine Script
1. Abre el archivo local [CardonaOptionStrategies.pine](file:///C:/Users/Ismael%20Romero/.gemini/antigravity/scratch/tradingview_strategy_project/CardonaOptionStrategies.pine) y copia todo su contenido.
2. Abre [TradingView](https://es.tradingview.com/) en tu navegador e inicia sesión.
3. Abre el gráfico de cualquier activo (por ejemplo, **SPY** o **META**) en la temporalidad de **1 Hora (1H)**.
4. En la parte inferior de la pantalla, haz clic en la pestaña **"Editor de Pine" (Pine Editor)**.
5. Borra cualquier código existente, pega el contenido copiado y haz clic en el botón **"Guardar"** (puedes nombrarlo *Estrategias Cardona Opciones*).
6. Haz clic en **"Añadir al gráfico"** (Add to chart).

### 2. Verificar los Promedios Móviles
El script ploteará de forma inmediata las 5 medias móviles clásicas de la aplicación uCharts con sus respectivos colores:
* **PM 10:** Línea Blanca ⚪
* **PM 20:** Línea Amarilla 🟡
* **PM 40:** Línea Roja 🔴
* **PM 100:** Línea Verde 🟢
* **PM 200:** Línea Morada 🟣
*(Puedes ocultarlas o cambiar sus longitudes y tipos en la rueda de configuración del script).*

### 3. Configurar Alertas Push al Celular
Para recibir las notificaciones push gratis cada vez que se cumpla una estrategia:
1. Instala la aplicación oficial de **TradingView** en tu celular (iOS o Android) e inicia sesión con tu misma cuenta. Asegúrate de habilitar los permisos de notificación de la app en la configuración del celular.
2. En la web de TradingView, haz clic derecho sobre el gráfico y selecciona **"Añadir alerta"** (Add alert).
3. En la sección de **Condición**, selecciona `Estrategias Cardona Opciones`.
4. Selecciona la opción **"Llamadas a la función alert()"** (Order fills and alert() function calls) para que el script envíe los mensajes dinámicos de cada estrategia.
5. En la pestaña **Notificaciones**, marca la casilla **"Notificar en la aplicación"** (Notify on app).
6. ¡Listo! Cuando se dispare un CALL o PUT en cualquier vela horaria, te sonará el celular con el nombre del activo y la estrategia exacta.

### 4. Backtesting en TradingView
Haz clic en la pestaña **"Probador de Estrategias"** (Strategy Tester) al lado del Editor de Pine en la parte inferior. Verás de forma automática las estadísticas históricas de las operaciones (flechas verdes de CALL y rojas de PUT en tu pantalla).

---

## 🐍 PARTE 2: Backtester Local en Python y Base de Datos

Si quieres descargar de forma masiva los datos históricos y crear tu propia base de datos de operaciones para sacar estadísticas completas:

### 1. Ejecutar el Backtest y Llenar la Base de Datos
Este script descargará automáticamente los datos de tus 21 activos desde Yahoo Finance, aplicará todas las estrategias en el historial y guardará las operaciones en una base de datos local SQLite:
1. Abre tu terminal de Windows (CMD o PowerShell).
2. Asegúrate de estar en el directorio del proyecto:
   ```powershell
   cd "C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project"
   ```
3. Ejecuta el script del backtester:
   ```powershell
   python backtest_to_db.py
   ```
4. El script creará un archivo de base de datos llamado `trades_backtest.db`.

### 2. Generar el Reporte de Métricas en Excel
Una vez que el backtester termine, ejecuta el analizador para procesar la base de datos y calcular tasas de acierto (Win Rate), Profit Factor, etc.:
1. En la misma terminal, ejecuta:
   ```powershell
   python analyze_results.py
   ```
2. El script imprimirá en pantalla las estadísticas clave y exportará un reporte Excel estructurado con 4 hojas en:
   * [reporte_backtesting.xlsx](file:///C:/Users/Ismael%20Romero/.gemini/antigravity/scratch/tradingview_strategy_project/reporte_backtesting.xlsx)

---

## 📂 Archivos del Proyecto
* [CardonaOptionStrategies.pine](file:///C:/Users/Ismael%20Romero/.gemini/antigravity/scratch/tradingview_strategy_project/CardonaOptionStrategies.pine) - Estrategia en Pine Script v5 para TradingView.
* [backtest_to_db.py](file:///C:/Users/Ismael%20Romero/.gemini/antigravity/scratch/tradingview_strategy_project/backtest_to_db.py) - Algoritmo Python para descarga de datos y ejecución de backtesting histórico masivo.
* [analyze_results.py](file:///C:/Users/Ismael%20Romero/.gemini/antigravity/scratch/tradingview_strategy_project/analyze_results.py) - Algoritmo para procesar la base de datos SQLite y exportar reportes Excel con métricas.

# 2026-11-04 PRE-MARKET - Reporte Meliora Options

Corrida automática desatendida: 18:12 UTC (13:12 ET / 15:12 ART). Estaba programada para las 13:17 UTC y arrancó con ~5 h de retraso, por lo que ya NO es pre-market real (la apertura de las 9:30 ET ya pasó).

## Resumen
- Activos del scanner (TICKERS en live_scanner.py): 35 (coincide). AAPL, AMD, AMZN, AXON, BAC, BLK, C, COIN, CVX, DIS, EA, EBAY, GLD, GOOG, GOOGL, HPE, META, MRNA, MSCI, MSFT, NDAQ, NFLX, NVDA, ORCL, PLTR, PYPL, QQQ, SLV, SPY, TNA, TSLA, UBER, USO, VLO, XOM.
- Estrategias: TABLA_ESTRATEGIAS.md (23/10/2026) lista 11 de Cardona confirmadas + Techo Fuerte pendiente (D6) + 6 SIN_CLASIFICAR. No se verificó contra el portal.
- CUMPLE: 0 leídos. CERCA: 0 leídos. NO LEÍDO: los 35 activos.

## Qué no se pudo hacer
- El navegador no tiene permiso para TradingView ni uCharts: requiere aprobación de Ismael y nadie estaba para darla. No se solicitó acceso ni se intentó iniciar sesión.
- Endpoint local /get_monitored_tickers (puerto 5000) no responde: el scanner parece apagado.
- Sin capturas, sin niveles calculados, sin comparación uCharts vs TradingView. No se rellenó nada.
- No se tocó el layout de TradingView, el bot ni el Auto-Trader. No se enviaron órdenes.

## Para destrabar
Permitir los sitios en la app (con sesión iniciada en TradingView y uCharts) y relanzar el análisis.

No es asesoramiento financiero.

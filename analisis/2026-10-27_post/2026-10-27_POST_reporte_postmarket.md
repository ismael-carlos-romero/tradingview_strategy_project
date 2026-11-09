# 2026-10-27 POST-MARKET - Analisis 35 activos vs estrategias Cardona

Corrida automatica desatendida, 16:24 ET (17:24 ART), con el dia completo. Solo analisis: sin ordenes, sin tocar bot ni Auto-Trader. No es asesoramiento financiero.

## Limitaciones (leer primero)
- uCharts: NO leido. El navegador redirige a la pantalla de login (sin sesion) y el dominio app.ucharts.com no tiene permiso en la extension. Sin capturas de uCharts ni contraste con la referencia de operacion (uCharts Paper Money). Ismael debe iniciar sesion.
- TradingView: sesion iniciada. Layout de Ismael (Meliora captura) NO modificado: su simbolo quedo en META 1h como estaba. Trabaje en un layout nuevo en blanco llamado Claude_analisis_postmarket (puede borrarlo cuando quiera).
- Los estados salen de cardona_rules.py (cardona-pdf-v1) sobre datos Yahoo 30m/diario, NO de lectura de pantalla. Verificado en pantalla en TradingView solo: AAPL, NVDA, SPY, AMD, PLTR, USO (cierres coinciden con el motor; AMD 560.25 TV vs 560.45 Yahoo, resto <=0.06).
- Capturas TradingView (1h) solo de NVDA, SPY, AMD, PLTR, USO: quedaron en el espacio de trabajo de la sesion y se entregan por chat; no estan en esta carpeta. No se tomaron capturas de los otros 30 activos ni diarios. No se dibujaron niveles ni se agregaron indicadores/Pine en TradingView.
- EA: NO leido (Yahoo sin velas de hoy; ultima 2026-08-04). 13 filas NO_LEIDO.
- Catalogo: TABLA_ESTRATEGIAS.md lista 19 detectores (11 Cardona + Techo Fuerte pendiente D6 + 7 SIN_CLASIFICAR), no las 12 exactas. Se evaluaron 13 IDs Cardona; PRIMER_GAP, HANGER_DIARIO, TECHO_FUERTE y RUPTURA_PISO_GAP quedan NO_EVALUABLE (el motor no las implementa o son ambiguas). Los 7 SIN_CLASIFICAR no se evaluaron. Lista de 35 tickers: endpoint local /get_monitored_tickers (respondio).
- Los CUMPLE de abajo ya ocurrieron HOY; las estrategias de gap dispararon en la vela de 10:00 (Cardona las libera desde las 11:00), por lo que no son entradas para manana.

## Resumen
CUMPLE (ocurrio hoy): 18, CERCA: 123, NO_EVALUABLE: 136, NO: 167, NO_LEIDO: 13

## CUMPLE (ocurrio hoy; contexto para manana)

| Activo | Estrategia | Vela(s) NY | Cierre |
|---|---|---|---|
| AAPL | CAIDA_FUERTE | 10:00 | 347.08 |
| AAPL | PM40_BOUNCE | 10:00 | 347.08 |
| AMD | GAP_NORMAL | 10:00 | 560.45 |
| CVX | RUPTURA_PISO | 10:00 | 228.31 |
| GOOG | CANAL_BREAK | 11:00 | 316.89 |
| GOOGL | CANAL_BREAK | 11:00 | 320.56 |
| MRNA | CAIDA_FUERTE | 13:00 | 207.94 |
| NVDA | CAIDA_FUERTE | 10:00 | 217.88 |
| NVDA | CANAL_BREAK | 11:00 | 217.88 |
| ORCL | CANAL_BREAK | 10:00 | 130.56 |
| PLTR | GAP_BAJISTA | 10:00 | 198.75 |
| SLV | GAP_BAJISTA | 10:00 | 49.16 |
| SPY | CAIDA_FUERTE | 10:00 | 769.72 |
| SPY | PISO_FUERTE | 10:00 | 769.72 |
| SPY | CANAL_BREAK | 11:00 | 769.72 |
| TSLA | GAP_NORMAL | 10:00 | 407.46 |
| USO | RUPTURA_PISO | 10:00 | 163.95 |
| VLO | VELA_ROJA | 09:30 | 387.34 |

## CERCA para la proxima apertura (falta un paso; mas accionable primero)

Cada uno requiere vela de confirmacion manana; compras desde 11:00 ET (10:30 ART... verificar hora real de apertura), salvo Vela Roja 10:00.

| Activo | Estrategia | Nivel/precio actual | Que falta |
|---|---|---|---|
| PLTR | PM40_BOUNCE | cierre 198.75; PM20 198.07 PM40 197.75 PM200 193.37 | toque y ruptura de linea con verde solida/martillo (11:00-15:59) |
| USO | PM40_BOUNCE | cierre 163.95; PM20 166.35 PM40 163.61 PM200 152.95 | toque y ruptura de linea con verde solida/martillo (11:00-15:59) |
| AMD | PISO_FUERTE | cierre 560.45; PM20 535.62 PM40 534.18 PM200 587.77 | ruptura con vela verde solida |
| C | PISO_FUERTE | cierre 122.69; PM20 121.86 PM40 122.24 PM200 127.55 | ruptura con vela verde solida |
| GOOG | PISO_FUERTE | cierre 316.89; PM20 317.05 PM40 322.69 PM200 339.32 | ruptura con vela verde solida |
| GOOGL | PISO_FUERTE | cierre 320.56; PM20 320.36 PM40 326.26 PM200 342.89 | ruptura con vela verde solida |
| NVDA | PISO_FUERTE | cierre 217.88; PM20 215.42 PM40 216.14 PM200 225.07 | ruptura con vela verde solida |
| QQQ | PISO_FUERTE | cierre 721.24; PM20 713.25 PM40 714.77 PM200 734.49 | ruptura con vela verde solida |
| BAC | CANAL_BREAK | cierre 50.68; PM20 50.76 PM40 50.83 PM200 53.67 | ruptura con verde solida + 2a vela verde |
| BLK | CANAL_BREAK | cierre 1136.07; PM20 1127.73 PM40 1132.76 PM200 1088.78 | ruptura con verde solida + 2a vela verde |
| C | CANAL_BREAK | cierre 122.69; PM20 121.86 PM40 122.24 PM200 127.55 | ruptura con verde solida + 2a vela verde |
| EBAY | CANAL_BREAK | cierre 117.82; PM20 119.31 PM40 120.63 PM200 113.18 | ruptura con verde solida + 2a vela verde |
| GLD | CANAL_BREAK | cierre 372.27; PM20 368.79 PM40 371.94 PM200 382.23 | ruptura con verde solida + 2a vela verde |
| VLO | CANAL_BREAK | cierre 387.34; PM20 414.79 PM40 421.96 PM200 416.86 | ruptura con verde solida + 2a vela verde |
| AMD | CAIDA_FUERTE | cierre 560.45; PM20 535.62 PM40 534.18 PM200 587.77 | ruptura con vela verde solida y caida >1,5% |
| BLK | CAIDA_FUERTE | cierre 1136.07; PM20 1127.73 PM40 1132.76 PM200 1088.78 | ruptura con vela verde solida y caida >1,5% |
| EBAY | CAIDA_FUERTE | cierre 117.82; PM20 119.31 PM40 120.63 PM200 113.18 | ruptura con vela verde solida y caida >1,5% |
| MSFT | CAIDA_FUERTE | cierre 531.6; PM20 529.06 PM40 528.83 PM200 521.35 | ruptura con vela verde solida y caida >1,5% |
| PLTR | CAIDA_FUERTE | cierre 198.75; PM20 198.07 PM40 197.75 PM200 193.37 | ruptura con vela verde solida y caida >1,5% |
| USO | CAIDA_FUERTE | cierre 163.95; PM20 166.35 PM40 163.61 PM200 152.95 | ruptura con vela verde solida y caida >1,5% |
| VLO | CAIDA_FUERTE | cierre 387.34; PM20 414.79 PM40 421.96 PM200 416.86 | ruptura con vela verde solida y caida >1,5% |
| AAPL | CAIDA_NORMAL | cierre 347.08; PM20 345.7 PM40 344.77 PM200 339.22 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| AMD | CAIDA_NORMAL | cierre 560.45; PM20 535.62 PM40 534.18 PM200 587.77 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| BLK | CAIDA_NORMAL | cierre 1136.07; PM20 1127.73 PM40 1132.76 PM200 1088.78 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| EBAY | CAIDA_NORMAL | cierre 117.82; PM20 119.31 PM40 120.63 PM200 113.18 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| MSFT | CAIDA_NORMAL | cierre 531.6; PM20 529.06 PM40 528.83 PM200 521.35 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| NVDA | CAIDA_NORMAL | cierre 217.88; PM20 215.42 PM40 216.14 PM200 225.07 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| PLTR | CAIDA_NORMAL | cierre 198.75; PM20 198.07 PM40 197.75 PM200 193.37 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| SPY | CAIDA_NORMAL | cierre 769.72; PM20 765.47 PM40 766.76 PM200 769.61 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| USO | CAIDA_NORMAL | cierre 163.95; PM20 166.35 PM40 163.61 PM200 152.95 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| VLO | CAIDA_NORMAL | cierre 387.34; PM20 414.79 PM40 421.96 PM200 416.86 | vela verde solida que la rompa (>=11:00) con caida 0,5-1,5% |
| BAC | 4_PASOS | cierre 50.68; PM20 50.76 PM40 50.83 PM200 53.67 | verde->roja que borre la anterior y ruptura de linea de piso |
| BLK | 4_PASOS | cierre 1136.07; PM20 1127.73 PM40 1132.76 PM200 1088.78 | verde->roja que borre la anterior y ruptura de linea de piso |
| C | 4_PASOS | cierre 122.69; PM20 121.86 PM40 122.24 PM200 127.55 | verde->roja que borre la anterior y ruptura de linea de piso |
| COIN | 4_PASOS | cierre 161.17; PM20 161.88 PM40 167.31 PM200 182.2 | verde->roja que borre la anterior y ruptura de linea de piso |
| EBAY | 4_PASOS | cierre 117.82; PM20 119.31 PM40 120.63 PM200 113.18 | verde->roja que borre la anterior y ruptura de linea de piso |
| GLD | 4_PASOS | cierre 372.27; PM20 368.79 PM40 371.94 PM200 382.23 | verde->roja que borre la anterior y ruptura de linea de piso |
| GOOG | 4_PASOS | cierre 316.89; PM20 317.05 PM40 322.69 PM200 339.32 | verde->roja que borre la anterior y ruptura de linea de piso |
| GOOGL | 4_PASOS | cierre 320.56; PM20 320.36 PM40 326.26 PM200 342.89 | verde->roja que borre la anterior y ruptura de linea de piso |
| NVDA | 4_PASOS | cierre 217.88; PM20 215.42 PM40 216.14 PM200 225.07 | verde->roja que borre la anterior y ruptura de linea de piso |
| ORCL | 4_PASOS | cierre 130.56; PM20 128.13 PM40 128.32 PM200 137.48 | verde->roja que borre la anterior y ruptura de linea de piso |
| QQQ | 4_PASOS | cierre 721.24; PM20 713.25 PM40 714.77 PM200 734.49 | verde->roja que borre la anterior y ruptura de linea de piso |
| SPY | 4_PASOS | cierre 769.72; PM20 765.47 PM40 766.76 PM200 769.61 | verde->roja que borre la anterior y ruptura de linea de piso |
| UBER | 4_PASOS | cierre 65.78; PM20 66.47 PM40 67.46 PM200 69.24 | verde->roja que borre la anterior y ruptura de linea de piso |
| VLO | 4_PASOS | cierre 387.34; PM20 414.79 PM40 421.96 PM200 416.86 | verde->roja que borre la anterior y ruptura de linea de piso |

### Contexto generico (gaps y Vela Roja; se definen en el premercado/apertura de manana)

- GAP_NORMAL (tendencia diaria alcista OK, falta gap>0,1% + 1a y 2a vela verdes, compra desde 11:00): AAPL, BLK, CVX, DIS, EBAY, HPE, MRNA, MSCI, MSFT, NDAQ, NVDA, PLTR, PYPL, SPY, USO, VLO, XOM
- VELA_ROJA (contexto de canal/PM40/PM200 OK, falta 1a vela 9:30 roja solida con volumen > media; compra 10:00): AAPL, AMZN, AXON, BAC, BLK, C, COIN, CVX, DIS, EBAY, GLD, GOOG, GOOGL, META, MRNA, MSCI, MSFT, NFLX, NVDA, ORCL, PLTR, PYPL, QQQ, SLV, SPY, TNA, UBER, USO, XOM
- GAP_BAJISTA: aplica a todos si manana abren con gap < -0,1% y dan 1a y 2a velas verdes (compra desde 11:00).

## Niveles de cierre por activo (calculados de datos, no leidos en pantalla)

| Activo | Cierre | PM20 | PM40 | PM100 | PM200 | SMA100d | SMA200d | Tend. diaria alcista | En piso diario |
|---|---|---|---|---|---|---|---|---|---|
| AAPL | 347.08 | 345.7 | 344.77 | 342.74 | 339.22 | 319.71 | 294.84 | True | False |
| AMD | 560.45 | 535.62 | 534.18 | 561.64 | 587.77 | 526.51 | 403.72 | True | True |
| AMZN | 253.15 | 250.24 | 254.1 | 256.27 | 253.83 | 251.77 | 243.31 | False | True |
| AXON | 425.69 | 422.33 | 411.82 | 408.43 | 420.23 | 502.23 | 482.93 | False | False |
| BAC | 50.68 | 50.76 | 50.83 | 51.84 | 53.67 | 58.54 | 55.03 | False | False |
| BLK | 1136.07 | 1127.73 | 1132.76 | 1109.27 | 1088.78 | 1078.34 | 1062.34 | True | False |
| C | 122.69 | 121.86 | 122.24 | 124.37 | 127.55 | 133.97 | 126.43 | False | True |
| COIN | 161.17 | 161.88 | 167.31 | 172.97 | 182.2 | 168.86 | 180.07 | False | False |
| CVX | 228.31 | 231.3 | 228.64 | 222.27 | 214.3 | 197.53 | 191.99 | True | False |
| DIS | 110.24 | 110.96 | 111.42 | 109.95 | 107.01 | 103.08 | 103.53 | True | False |
| EA | NO LEIDO | | | | | | | | |
| EBAY | 117.82 | 119.31 | 120.63 | 118.34 | 113.18 | 110.02 | 103.45 | True | False |
| GLD | 372.27 | 368.79 | 371.94 | 376.93 | 382.23 | 387.57 | 413.99 | False | True |
| GOOG | 316.89 | 317.05 | 322.69 | 336.46 | 339.32 | 345.65 | 339.38 | False | True |
| GOOGL | 320.56 | 320.36 | 326.26 | 340.15 | 342.89 | 348.13 | 341.27 | False | True |
| HPE | 60.84 | 58.95 | 57.67 | 61.88 | 63.17 | 53.96 | 40.05 | True | False |
| META | 620.12 | 634.93 | 657.61 | 700.34 | 715.71 | 630.88 | 632.45 | False | True |
| MRNA | 207.94 | 199.21 | 214.41 | 216.3 | 201.41 | 117.33 | 82.99 | True | False |
| MSCI | 601.84 | 612.94 | 609.44 | 583.09 | 566.0 | 575.14 | 572.98 | True | False |
| MSFT | 531.6 | 529.06 | 528.83 | 532.74 | 521.35 | 460.97 | 436.79 | True | False |
| NDAQ | 104.35 | 103.89 | 101.02 | 96.39 | 94.62 | 92.04 | 90.48 | True | False |
| NFLX | 62.52 | 64.21 | 65.64 | 68.75 | 69.53 | 74.41 | 82.14 | False | True |
| NVDA | 217.88 | 215.42 | 216.14 | 220.71 | 225.07 | 214.41 | 203.82 | True | True |
| ORCL | 130.56 | 128.13 | 128.32 | 132.67 | 137.48 | 147.38 | 158.23 | False | False |
| PLTR | 198.75 | 198.07 | 197.75 | 199.19 | 193.37 | 160.12 | 153.26 | True | False |
| PYPL | 56.09 | 55.93 | 56.66 | 56.27 | 54.83 | 52.89 | 49.99 | True | False |
| QQQ | 721.24 | 713.25 | 714.77 | 727.03 | 734.49 | 719.19 | 677.75 | False | True |
| SLV | 49.16 | 48.84 | 49.93 | 51.6 | 54.17 | 56.27 | 64.85 | False | True |
| SPY | 769.72 | 765.47 | 766.76 | 770.34 | 769.61 | 758.26 | 727.39 | True | True |
| TNA | 58.33 | 56.82 | 56.43 | 55.93 | 58.11 | 66.97 | 61.12 | False | False |
| TSLA | 407.46 | 391.66 | 386.11 | 376.8 | 373.17 | 367.92 | 386.13 | True | True |
| UBER | 65.78 | 66.47 | 67.46 | 69.2 | 69.24 | 72.17 | 73.73 | False | True |
| USO | 163.95 | 166.35 | 163.61 | 157.71 | 152.95 | 133.81 | 122.08 | True | False |
| VLO | 387.34 | 414.79 | 421.96 | 435.1 | 416.86 | 339.11 | 281.58 | True | False |
| XOM | 179.89 | 182.64 | 180.09 | 176.23 | 169.29 | 156.92 | 153.46 | True | False |

## Discrepancias y no leido

- uCharts vs TradingView: no comparable (uCharts sin sesion).
- TradingView vs Yahoo: diferencias menores de ultimo precio (AMD 0.20); resto coincide.
- NO_LEIDO: EA (todas las estrategias).
- NO_EVALUABLE: RUPTURA_PISO_GAP, PRIMER_GAP, HANGER_DIARIO, TECHO_FUERTE para los 35 (reglas no implementadas/ambiguas; D6 sigue pendiente).
- Barras de TradingView y de Yahoo pueden diferir en cierres post-mercado; la referencia de operacion es uCharts Paper Money (no verificada hoy).
# 2026-10-27 PRE-MARKET - Analisis 35 activos vs estrategias Cardona

Corrida automatica 12:35 UTC (08:35 ET / 09:35 ART). Solo analisis, sin ordenes.

## Limitaciones (leer primero)
- TradingView: sesion iniciada, pero el grafico (layout de Ismael, META 1h) NO cargo datos (OHLC en 0, watchlist cargando). Sin capturas de TradingView.
- uCharts: no se leyo en esta corrida. Sin capturas ni contraste uCharts vs TradingView.
- Los estados salen de analisis/2026-10-27_pre/informe35_filas.csv (reglas cardona_rules.py cardona-pdf-v1, datos Yahoo 30m, generado hoy 09:18). NO verificado en pantalla.
- Catalogo: TABLA_ESTRATEGIAS.md lista 19 detectores (11 Cardona + Techo Fuerte pendiente D6 + 7 SIN_CLASIFICAR), no 12 exactas. Tickers: 35 (TICKERS de live_scanner.py; endpoint local no respondio).
- Layout de Ismael no modificado.

## Resumen
Sin coincidencia: 204, En formación: 93, No evaluable: 155, Confirmada: 3

## CUMPLE / CONFIRMADA
- HPE | CAIDA_FUERTE | Ya ocurrió en la última sesión cerrada (2026-10-26 10:00:00-04:00, inicio de vela NY); no es una señal para hoy. cierre ayer 58.72; premercado 59.55 (+1.41%)
- SPY | CAIDA_NORMAL | Ya ocurrió en la última sesión cerrada (2026-10-26 10:00:00-04:00, inicio de vela NY); no es una señal para hoy. cierre ayer 765.22; premercado 767.91 (+0.35%)
- SPY | PISO_FUERTE | Ya ocurrió en la última sesión cerrada (2026-10-26 10:00:00-04:00, inicio de vela NY); no es una señal para hoy. cierre ayer 765.22; premercado 767.91 (+0.35%)

## CERCA / EN FORMACION (falta un paso; vigilar)

| Activo | Estrategia | Evidencia |
|---|---|---|
| AAPL | GAP_BAJISTA | cierre ayer 343.98; premercado 342.57 (-0.41%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| AAPL | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| AAPL | CAIDA_NORMAL | Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%. cierre ayer 343.98; premercado 342.57 (-0.41%) |
| AAPL | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 343.98; premercado 342.57 (-0.41%) |
| AAPL | PM40_BOUNCE | PM20>PM40 y PM100>PM200 sostenidos; distancia a PM40 0.03%. Falta: toque de PM40, ruptura de línea con vela verde sólida/martillo (11:00-15:59). cierre ayer 343.98; premercado 342.57 (-0.41%) |
| AMD | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| AMZN | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| AXON | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| BAC | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| BLK | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| C | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| C | PISO_FUERTE | SMA100d>SMA200d, en piso diario y línea de caída vigente. Falta: ruptura con vela verde sólida y cierre sobre apertura del día. cierre ayer 121.07; premercado 122.25 (+0.97%) |
| C | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 121.07; premercado 122.25 (+0.97%) |
| C | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 121.07; premercado 122.25 (+0.97%) |
| COIN | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| CVX | GAP_BAJISTA | cierre ayer 231.99; premercado 230.70 (-0.56%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| CVX | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| DIS | GAP_NORMAL | cierre ayer 110.40; premercado 110.83 (+0.39%). Tendencia diaria alcista=True. Falta: 1ª y 2ª vela verdes (10:00-11:00), no martillo; compra desde 11:00 |
| DIS | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| DIS | CAIDA_NORMAL | Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%. cierre ayer 110.40; premercado 110.83 (+0.39%) |
| DIS | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 110.40; premercado 110.83 (+0.39%) |
| DIS | PM40_BOUNCE | PM20>PM40 y PM100>PM200 sostenidos; distancia a PM40 0.98%. Falta: toque de PM40, ruptura de línea con vela verde sólida/martillo (11:00-15:59). cierre ayer 110.40; premercado 110.83 (+0.39%) |
| EBAY | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| EBAY | CAIDA_NORMAL | Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%. cierre ayer 118.63; sin velas de premercado |
| EBAY | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 118.63; sin velas de premercado |
| EBAY | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 118.63; sin velas de premercado |
| EBAY | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 118.63; sin velas de premercado |
| GLD | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| GLD | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 367.83; premercado 367.81 (-0.00%) |
| GLD | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 367.83; premercado 367.81 (-0.00%) |
| GOOG | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| GOOG | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 314.19; premercado 315.31 (+0.36%) |
| GOOGL | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| GOOGL | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 316.89; premercado 318.34 (+0.46%) |
| HPE | GAP_NORMAL | cierre ayer 58.72; premercado 59.55 (+1.41%). Tendencia diaria alcista=True. Falta: 1ª y 2ª vela verdes (10:00-11:00), no martillo; compra desde 11:00 |
| META | GAP_BAJISTA | cierre ayer 630.47; premercado 628.00 (-0.39%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| META | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| META | CAIDA_NORMAL | Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%. cierre ayer 630.47; premercado 628.00 (-0.39%) |
| META | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 630.47; premercado 628.00 (-0.39%) |
| META | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 630.47; premercado 628.00 (-0.39%) |
| MRNA | GAP_BAJISTA | cierre ayer 198.86; premercado 192.69 (-3.10%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| MRNA | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| MRNA | CAIDA_NORMAL | Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%. cierre ayer 198.86; premercado 192.69 (-3.10%) |
| MRNA | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 198.86; premercado 192.69 (-3.10%) |
| MRNA | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 198.86; premercado 192.69 (-3.10%) |
| MSCI | CAIDA_NORMAL | Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%. cierre ayer 617.80; sin velas de premercado |
| MSCI | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 617.80; sin velas de premercado |
| MSFT | GAP_BAJISTA | cierre ayer 532.75; premercado 529.81 (-0.55%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| MSFT | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| NDAQ | GAP_BAJISTA | cierre ayer 104.72; premercado 104.54 (-0.17%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| NFLX | GAP_BAJISTA | cierre ayer 63.90; premercado 63.56 (-0.52%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| NFLX | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| NFLX | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 63.90; premercado 63.56 (-0.52%) |
| NFLX | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 63.90; premercado 63.56 (-0.52%) |
| NVDA | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| NVDA | PISO_FUERTE | SMA100d>SMA200d, en piso diario y línea de caída vigente. Falta: ruptura con vela verde sólida y cierre sobre apertura del día. cierre ayer 215.98; premercado 217.65 (+0.77%) |
| NVDA | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 215.98; premercado 217.65 (+0.77%) |
| NVDA | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 215.98; premercado 217.65 (+0.77%) |
| ORCL | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| ORCL | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 126.09; premercado 127.94 (+1.47%) |
| ORCL | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 126.09; premercado 127.94 (+1.47%) |
| PLTR | GAP_BAJISTA | cierre ayer 198.87; premercado 198.61 (-0.13%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| PLTR | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| PYPL | GAP_NORMAL | cierre ayer 54.97; premercado 56.33 (+2.46%). Tendencia diaria alcista=True. Falta: 1ª y 2ª vela verdes (10:00-11:00), no martillo; compra desde 11:00 |
| PYPL | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| QQQ | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| QQQ | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 712.12; premercado 715.23 (+0.44%) |
| QQQ | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 712.12; premercado 715.23 (+0.44%) |
| SLV | GAP_BAJISTA | cierre ayer 48.67; premercado 48.18 (-1.00%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| SLV | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| SLV | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 48.67; premercado 48.18 (-1.00%) |
| SLV | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 48.67; premercado 48.18 (-1.00%) |
| SPY | GAP_NORMAL | cierre ayer 765.22; premercado 767.91 (+0.35%). Tendencia diaria alcista=True. Falta: 1ª y 2ª vela verdes (10:00-11:00), no martillo; compra desde 11:00 |
| SPY | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| SPY | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 765.22; premercado 767.91 (+0.35%) |
| SPY | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 765.22; premercado 767.91 (+0.35%) |
| SPY | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 765.22; premercado 767.91 (+0.35%) |
| TNA | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| TSLA | GAP_NORMAL | cierre ayer 391.69; premercado 395.60 (+1.00%). Tendencia diaria alcista=True. Falta: 1ª y 2ª vela verdes (10:00-11:00), no martillo; compra desde 11:00 |
| UBER | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| UBER | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 66.12; premercado 66.42 (+0.46%) |
| UBER | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 66.12; premercado 66.42 (+0.46%) |
| USO | GAP_BAJISTA | cierre ayer 166.23; premercado 165.24 (-0.59%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| USO | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| USO | CAIDA_NORMAL | Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%. cierre ayer 166.23; premercado 165.24 (-0.59%) |
| USO | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 166.23; premercado 165.24 (-0.59%) |
| VLO | GAP_BAJISTA | cierre ayer 426.65; premercado 421.60 (-1.18%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |
| VLO | VELA_ROJA | Contexto de canal/PM40/PM200 OK. Falta: 1ª vela 9:30 roja sólida con volumen > media de 10 días (compra 10:00) |
| VLO | CAIDA_NORMAL | Línea de caída vigente + tendencia diaria alcista. Falta: vela verde sólida que la rompa (≥11:00, cruce de máximo de 3 velas) y caída 0,5%-1,5%. cierre ayer 426.65; premercado 421.60 (-1.18%) |
| VLO | CAIDA_FUERTE | Línea de caída vigente + tendencia alcista. Falta: ruptura con vela verde sólida y caída > 1,5%. cierre ayer 426.65; premercado 421.60 (-1.18%) |
| VLO | CANAL_BREAK | PM20<PM40 y canal bajista largo vigente. Falta: ruptura con vela verde sólida y 2ª vela de confirmación verde. cierre ayer 426.65; premercado 421.60 (-1.18%) |
| VLO | 4_PASOS | PM20<PM40 y línea de techo vigente. Falta: vela verde->roja que borre la anterior y ruptura de la línea de piso. cierre ayer 426.65; premercado 421.60 (-1.18%) |
| XOM | GAP_BAJISTA | cierre ayer 184.55; premercado 183.47 (-0.59%). Falta: 1ª vela verde y 2ª vela verde; compra desde 11:00 |

## No evaluable (no leido)

| Activo | Estrategia | Motivo |
|---|---|---|
| AAPL | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| AAPL | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| AAPL | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| AAPL | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| AMD | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| AMD | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| AMD | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| AMD | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| AMZN | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| AMZN | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| AMZN | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| AMZN | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| AXON | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| AXON | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| AXON | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| AXON | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| BAC | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| BAC | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| BAC | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| BAC | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| BLK | GAP_NORMAL | Sin datos de premercado para medir el gap |
| BLK | GAP_BAJISTA | Sin datos de premercado para medir el gap |
| BLK | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| BLK | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| BLK | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| BLK | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| C | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| C | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| C | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| C | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| COIN | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| COIN | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| COIN | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| COIN | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| CVX | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| CVX | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| CVX | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| CVX | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| DIS | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| DIS | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| DIS | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| DIS | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| EA | GAP_NORMAL | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | GAP_BAJISTA | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | VELA_ROJA | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | RUPTURA_PISO_GAP | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | CAIDA_NORMAL | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | CAIDA_FUERTE | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | PISO_FUERTE | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | PM40_BOUNCE | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | CANAL_BREAK | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | 4_PASOS | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | PRIMER_GAP | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | HANGER_DIARIO | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EA | TECHO_FUERTE | Error de datos: ValueError('datos desactualizados: ultima vela 2026-08-04 19:30:00-04:00 (hace 84 dias); posible activo sin cotizacion') |
| EBAY | GAP_NORMAL | Sin datos de premercado para medir el gap |
| EBAY | GAP_BAJISTA | Sin datos de premercado para medir el gap |
| EBAY | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| EBAY | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| EBAY | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| EBAY | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| GLD | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| GLD | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| GLD | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| GLD | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| GOOG | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| GOOG | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| GOOG | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| GOOG | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| GOOGL | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| GOOGL | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| GOOGL | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| GOOGL | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| HPE | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| HPE | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| HPE | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| HPE | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| META | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| META | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| META | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| META | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| MRNA | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| MRNA | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| MRNA | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| MRNA | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| MSCI | GAP_NORMAL | Sin datos de premercado para medir el gap |
| MSCI | GAP_BAJISTA | Sin datos de premercado para medir el gap |
| MSCI | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| MSCI | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| MSCI | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| MSCI | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| MSFT | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| MSFT | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| MSFT | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| MSFT | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| NDAQ | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| NDAQ | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| NDAQ | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| NDAQ | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| NFLX | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| NFLX | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| NFLX | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| NFLX | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| NVDA | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| NVDA | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| NVDA | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| NVDA | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| ORCL | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| ORCL | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| ORCL | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| ORCL | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| PLTR | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| PLTR | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| PLTR | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| PLTR | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| PYPL | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| PYPL | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| PYPL | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| PYPL | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| QQQ | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| QQQ | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| QQQ | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| QQQ | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| SLV | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| SLV | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| SLV | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| SLV | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| SPY | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| SPY | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| SPY | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| SPY | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| TNA | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| TNA | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| TNA | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| TNA | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| TSLA | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| TSLA | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| TSLA | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| TSLA | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| UBER | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| UBER | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| UBER | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| UBER | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| USO | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| USO | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| USO | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| USO | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| VLO | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| VLO | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| VLO | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| VLO | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |
| XOM | RUPTURA_PISO_GAP | Depende de la 1ª vela verde de hoy y de una vela roja sólida posterior; no hay datos todavía |
| XOM | PRIMER_GAP | Se evalúa en la última vela del día (15:00-16:00); el motor cardona_rules no la implementa todavía |
| XOM | HANGER_DIARIO | Se evalúa en la última vela del día sobre la vela diaria; el motor cardona_rules no la implementa todavía |
| XOM | TECHO_FUERTE | Regla ambigua: el código usa condición de PISO diario y el PDF define techo (PM100/PM200 diario); no se evalúa para no inventar reglas |

Reglas Cardona: sin compras antes de 11:00 (salvo Primera Vela Roja 10:00), OTM, vencimiento hasta una semana. No es asesoramiento financiero.
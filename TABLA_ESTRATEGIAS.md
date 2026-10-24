# Tabla documental de las 19 detectores / 18 estrategias del catálogo

Fecha: 23/10/2026. Regla aplicada: **no se infiere familia**. Solo figura CARDONA si el nombre aparece en material documental aportado (índice de `ESTRATEGIAS.pdf` / "Resumen Libros - Videos", y tu confirmación de las 11). Sin evidencia → SIN_CLASIFICAR.

Fuentes revisadas: texto extraído de `ESTRATEGIAS.pdf` (índice p.2 + cuerpo; Techo Fuerte pp.9-11), `live_scanner.py` (detectores L820-889, metadata L179-198, filtros L905-945), tabla `catalogo_estrategias`, conteo histórico en `senales`. Drive: se localizaron además *Documento Maestro*, *Guía Estrategias Alejandro Cardona*, *Manual Propuesto Atlas* y *Estrategias de Opciones .pptx*; **no leídos a fondo todavía** para las 6 estrategias sin fuente.

| ID scanner | ID catálogo/sim | Dir | Regla implementada (resumen) | Familia | Fuente documental | Señales hist. | Dudas |
|---|---|---|---|---|---|---|---|
| GAP_NORMAL | GAP_NORMAL | CALL | Tend. diaria alcista o Close>PM40; 2ª barra; gap>0,1 %; 1ª verde; barra verde | CARDONA | Índice ESTRATEGIAS.pdf | 0 | Filtro `hora<11` (L936) + exigir 2ª barra (10:xx) es **imposible de cumplir** → nunca dispara |
| GAP_BAJISTA | GAP_BAJISTA_ALZA | CALL | 2ª barra; gap<-0,1 %; 1ª verde; verde sólida | CARDONA | Índice ESTRATEGIAS.pdf | 0 (legacy aparte) | Mismo bloqueo horario; nombre distinto entre scanner y catálogo |
| PISO_FUERTE | PISO_FUERTE | CALL | SMA100d>SMA200d; en piso diario; canal descendente; cruza máx. 10; verde sólida | CARDONA | Índice ESTRATEGIAS.pdf | 37 | Es de marco diario decidido en hora; catálogo dice 1H |
| PRIMER_GAP | PRIMER_GAP_ALZA | CALL | Piso diario; última barra del día; gap>0,1 %; 1ª verde; piso respetado; caída previa | CARDONA | Índice ESTRATEGIAS.pdf | 26 | El filtro `GAP_ALZA_1` (L942, hora 15) es código muerto: el ID real es PRIMER_GAP |
| PM40_BOUNCE | PM40_BOUNCE | CALL | PM20>PM40; tocó PM40; cruza máx. 3; verde sólida o martillo; descarta Hanger | CARDONA | Índice ESTRATEGIAS.pdf | 2.086 | — |
| CAIDA_NORMAL + CAIDA_FUERTE | CAIDA_BREAK | CALL | Tend. diaria alcista; caída normal/fuerte; cruza máx. 3; verde sólida | CARDONA | Índice ("Caída Normal y Caída Fuerte") | 179 + 136 (catálogo: 7 bajo CAIDA_BREAK) | Scanner usa 2 IDs, catálogo 1 |
| CANAL_BREAK | CANAL_BREAK | CALL | Barra de ruptura y verde | CARDONA | Índice ("Ruptura del Canal Bajista") | 61 | Catálogo exige PM20<PM40 y cruce máx. 15; código solo `breakout_bar` |
| VELA_ROJA | VELA_ROJA | PUT | 1ª barra; roja sólida; gap>0,05 %; vol. rel.>1; PM20<PM40 o cerca de PM40/PM200; solo horas 9-10 | CARDONA | Índice ("Primera Vela Roja") | 54 | Umbrales gap/volumen no figuran en el índice |
| RUPTURA_PISO | RUPTURA_PISO_GAP | PUT | No 1ª barra; Close>PM40; cierre previo ≥ mín. 1ª barra y cierre < mín. 1ª barra; roja sólida | CARDONA | Índice ("Ruptura del Piso del Gap") | 108 | ID distinto scanner/catálogo |
| 4_PASOS | CUATRO_PASOS | PUT | PM20<PM40; Close<PM40; roja sólida; previa verde; Close<Open previa; Close<mín. 3 lows | CARDONA | Índice ("Modelo de los 04 Pasos") | 132 | ID distinto scanner/catálogo |
| HANGER_DIARIO | HANGER_DIARIO | PUT | Última barra; hanger diario; SMA100d>SMA200d; Close>SMA100d | CARDONA | Índice ("Hanger en Diario") | 177 | Marco diario evaluado sobre barra 1H |
| TECHO_FUERTE | TECHO_FUERTE | PUT | `d_at_floor`; 2ª barra; roja; roja sólida | **SIN_CLASIFICAR** (ver D6) | ESTRATEGIAS.pdf lista y desarrolla "Techo Fuerte" (pp.9-11), pero tú indicaste 11 de Cardona y el índice trae 12 nombres | 59 | (a) ¿es de Cardona? (b) El código usa `d_at_floor` (piso) para una estrategia de **techo** (PDF: cerca de PM100/PM200 diario + vela roja y vela roja sólida): posible error de lógica |
| COLA_PISO | COLA_PISO | CALL | Cola de piso y cerca de mín. 20 o de MA | SIN_CLASIFICAR | No hallada en lo revisado | 1.148 | Origen desconocido |
| COLA_TECHO | COLA_TECHO | PUT | Cola de techo y cerca de máx. 20 o de MA | SIN_CLASIFICAR | No hallada en lo revisado | 1.555 | Origen desconocido |
| RUPTURA_RES | RUPTURA_RES | CALL | Tend. diaria alcista; cruza máx. 20; verde sólida | SIN_CLASIFICAR | No hallada | 235 | Origen desconocido |
| RUPTURA_SOP | RUPTURA_SOP | PUT | No tend. alcista; cruza mín. 20; roja sólida | SIN_CLASIFICAR | No hallada | 110 | Origen desconocido |
| PISO_BREAK | PISO_BREAK | PUT | Cruce bajo SMA100d o SMA200d; roja sólida | SIN_CLASIFICAR | No hallada | 112 | Origen desconocido |
| GAP_CONT_PUT | GAP_CONT_PUT | PUT | 2ª barra; gap<-0,1 %; 1ª roja; roja | SIN_CLASIFICAR | No hallada | 40 | Origen desconocido; mismo filtro de 2ª barra |

## Hallazgos que afectan la operación (sin cambiar reglas todavía)
1. **GAP_NORMAL y GAP_BAJISTA nunca pueden disparar**: requieren 2ª barra (10:xx) y a la vez hora ≥ 11. Regla del PDF: no comprar antes de las 11:00. La corrección fiel a la regla es detectar a las 10:xx y **liberar la orden recién desde las 11:00 si el patrón sigue vigente** (estado "ESPERANDO_11:00"). Requiere tu OK porque cambia comportamiento.
2. **IDs distintos** entre scanner, catálogo, `sim_broker_core` y userscript (CAIDA_NORMAL/FUERTE, 4_PASOS, RUPTURA_PISO, PRIMER_GAP, GAP_BAJISTA). Plan: tabla de alias única (ya en `trace_ledger.ALIAS`) usada en un único punto de normalización.
3. **TECHO_FUERTE** probablemente mal codificada (usa piso). No se toca sin tu confirmación.
4. 7 estrategias con 3.200+ señales históricas (COLA_*, RUPTURA_RES/SOP, PISO_BREAK, GAP_CONT_PUT) no tienen respaldo documental revisado; el catálogo las marca CARDONA sin evidencia → pasan a SIN_CLASIFICAR.

## Decisión pendiente (D6)
¿Techo Fuerte es una de las de Cardona (serían 12 con Caída Normal+Fuerte como una) o no? Hasta tu respuesta queda SIN_CLASIFICAR.

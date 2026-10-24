# Registro del Encargo Único (v0.1, 23/10/2026)

Estado por etapa: pedido ≠ implementado ≠ validado.

| ID | Etapa | Depende de | Estado | Pruebas / evidencia | Reversión |
|----|-------|-----------|--------|---------------------|-----------|
| E0 | Diagnóstico y respaldo | - | HECHO (diagnóstico; sin cambios de código) | Backup\etapa0_20261023 (80 archivos + pending_changes.diff + HEAD.txt) | No hay cambios que revertir; solo se agregó `Backup/etapa0_*/` a .gitignore |
| E1 | Trazabilidad común | E0 | EN CURSO: escrito y probado en copia; NO desplegado (el scanner en marcha sigue con el código viejo hasta reiniciarlo) | test_trace_ledger.py (6 OK); scratch/_etapa1_integ.py sobre copia de BD | Quitar `import trace_ledger` y los 4 bloques `trace_ledger.registrar(...)` de live_scanner.py (o restaurar Backup\etapa0_20261023\live_scanner.py); las tablas trace_* son aditivas |
| E2 | Catálogo y panel | E1 | PENDIENTE | - | - |
| E3 | TradingView webhook | E1 | PENDIENTE | - | - |
| E4 | Atlas | E1,E3 | PENDIENTE | - | - |
| E5 | Noticias | E1 | PENDIENTE | - | - |
| E6 | Auditoría | E1 | PENDIENTE | - | - |

## E0 — Inventario (23/10/2026 ~14:40 ART)

Repo git: HEAD a6195af ("Capa 1: chart_analyzer"). Cambios sin commitear: .gitignore, CardonaOptionStrategies.pine, config.example.json, index.html, live_scanner.py, post_signal_tracker.py, ucharts_sync_userscript.js, webhook_listener.js; sin seguimiento: cardona_rules.py, chart_vision.py, news_engine.py, torneo_engine.py, reporte_tecnico_diario.py, webhook_listener_v2_events.js, ucharts_sync_userscript_v5.0.33..38.js, capturas_diarias/, etc. No se tocó nada de eso.

Procesos en ejecución: `python live_scanner.py` (servidor HTTP :8055 + Sonar + watchdog + Telegram + tracker), `python run_tunnel.py`, `ngrok`. No corre ningún `webhook_listener*.js` local: es código de Google Apps Script (doPost/SpreadsheetApp) y se despliega en Sheets.

### Versiones de userscript
- `/ucharts.user.js` (live_scanner.py:1345) sirve **ucharts_sync_userscript.js = v5.0.30** (1/10).
- Existen copias v5.0.33…v5.0.38 sueltas (la más nueva, 22/10 00:05). No se puede saber desde el disco cuál está instalada en Tampermonkey. **Duda bloqueante D1.**
- Apps Script: `webhook_listener.js` (1/10, versionado) vs `webhook_listener_v2_events.js` (15/10, sin versionar). Cuál está desplegado: no verificable localmente. **D2.**

### Recorrido actual de una señal (compra)
1. `live_scanner.py` `scan_ticker()` (l.645) → `sync_setup_and_signal()` (l.366): inserta `senales` (signal_id SIG_<ticker>_<fecha>_<ms>), `setups`, `radar_actual`, `eventos_mercado`.
2. Si `state == CONFIRMADA`:
   a. `sim_broker_core.simular_compra_broker()` compra en el **simulador interno** (RiskEngine, ledger, `operaciones_simuladas`) y `log_trade_fill_to_sheet()`.
   b. Si el sistema no está STOP/DISARMED, encola en `PENDING_TRADES_QUEUE` (**memoria RAM**, se pierde al reiniciar) con setup_id, ticker, direction, strategy_id, tv_confirm; abre posiciones del torneo (`torneo_engine`).
   c. El userscript de uCharts consulta `/get_pending_trades`, opera en Paper Money y llama `/mark_executed` (solo saca de la cola) y `/report_trade_result` (solo manda Telegram).
3. Notificación: Telegram (+ chart_analyzer/chart_vision en modo sombra), POST al Apps Script (`WEBHOOK_URL`) → Sheets.
4. TradingView: `POST /webhook/tv` (l.1662) valida `secret` del cuerpo contra `tv_webhook_secret.txt`; solo `tv_register()` (modo sombra: RAM + tabla `tv_confirmaciones`). **Esa tabla no existe en la base → nunca se recibió una confirmación TV**. No origina compras.

### Dónde se interrumpe la trazabilidad
- La ejecución real en uCharts **no se persiste**: `/mark_executed` y `/report_trade_result` no guardan order_id/fill_id/precio/contrato en SQLite. Es la causa más probable de las 89 ventas sin claves.
- Hay dos ejecutores en paralelo para la misma señal (sim interno y cola uCharts): riesgo de doble compra/doble contabilidad. **D3.**
- No existe campo fuente/familia/versión de detector/modo en `senales`/`ordenes`/`operaciones_simuladas`.
- `operaciones_simuladas`: 85 filas con `state=OPEN` pero `estado=CLOSED` (dos columnas de estado inconsistentes). 1 fila EXIT_REQUESTED.
- `ordenes`/`ejecuciones`/`operaciones`/`resultados` (esquema relacional, 546/546/273) **sin escrituras desde 26/8**; tablas `orders`/`positions` (nuevo esquema) vacías. `decisiones` ALGORITMICA BUY/SELL = 273 c/u.
- Tablas con datos: senales 6.222 (11/8→23/10), setups 3.290, operaciones_simuladas 140 (27/8→23/10), ledger 339, torneo_posiciones 195 (9 abiertas), risk_audit_log 21.325, chart_analysis_log 356. news_events.db: 240 eventos (último 20/10).
- Estado de control (configuracion): system_state=ARMED, sonar_active/scanner_active/autotrade_active=true, panic_stop=false. `system_settings.allow_new_trades=0` (STOP del 22/9) es una tabla distinta: conflicto de fuentes de verdad a aclarar. `capital_simulado`=5.818.599,37 (valor llamativo; no se tocó).
- Catálogo: tabla `catalogo_estrategias` con 18 estrategias; PM40/Techo Fuerte/Cola de Techo/Hanger tienen discrepancias documentadas pendientes (E2).

### Hallazgos de seguridad (no corregidos, requieren decisión)
- Contraseña admin por defecto `meliora2026` se crea si no hay hash (live_scanner.py ~l.1775).
- Token `LAB_SIM_SECURE_TOKEN` hardcodeado en el payload al Apps Script.
- `is_request_authorized` deja pasar sin sesión cualquier request con Host localhost/127.0.0.1 y `/webhook/tv` es público (solo protegido por el secreto en el cuerpo); detrás de ngrok el header Host no es local, pero conviene revisar.
- `verify=False` en requests a Telegram/webhook.
- Se copiaron config.json y tv_webhook_secret.txt dentro de `Backup\etapa0_20261023` (ahora ignorada por git).

### Dudas bloqueantes
- D1: ¿Qué versión de userscript está instalada hoy en Tampermonkey (ver @version en el panel)? ¿El archivo oficial pasa a ser v5.0.38?
- D2: ¿Qué versión del Apps Script está desplegada (v1 o v2_events)?
- D3: ¿Se mantiene el simulador interno como motor "Paper" común, o el Paper de referencia es el de uCharts y el interno es solo sombra?
- D4: ¿Acceso a Drive/Sheets de las URLs del encargo: están conectados los conectores de Google? (no verificado aún).
- D5: Atlas/TradingView: el acceso al navegador con la sesión de TradingView se debe verificar en Etapa 4.

### Rollback de E0
Sin cambios de código. Para deshacer el único cambio: quitar la línea `Backup/etapa0_*/` de `.gitignore`. Para restaurar archivos: copiar desde `Backup\etapa0_20261023`.

## E1 — Cambios (23/10/2026)
- Nuevo `trace_ledger.py`: tablas aditivas `trace_origen` (una fila por setup: fuente, familia, estrategia+versión, huella del detector, modo, canales, corroboraciones) y `trace_eventos` (append-only: estado, venue SIM_INTERNO/UCHARTS_PAPER, order/execution/trade/parent/group id, contrato, precios, costes, TP/SL, capital, versión de riesgo; desconocido = NULL; `idem_key` único evita duplicados por reintento).
- `live_scanner.py` (edición puntual, 4 enganches): origen al CONFIRMADA (fuente SCANNER_PYTHON, familia SIN_CLASIFICAR), resultado del simulador interno (EJECUTADA/BLOQUEADA), ENCOLADA para uCharts, y `/report_trade_result` ahora persiste EJECUTADA/RECHAZADA con precio y strike (antes solo Telegram).
- Verificado: `py_compile` OK, 6 tests unitarios OK, integración sobre copia de la BD OK.
- Aún sin hacer en E1: cierre (CERRADA) y venta con trade_id de uCharts, recompra/parent_trade_id, patas Banderines/Tester (group_id, modo), compra manual, ENVIADA vs EJECUTADA en el userscript, `/mark_executed` con cola persistente, espejo a Sheets. Familia/modo quedan SIN_CLASIFICAR/NULL hasta E2.
- Hallazgos nuevos del simulador: `trade_id = TRD_<ticker>_<estrategia>_<MMSS>` puede colisionar entre horas; `decisiones.setup_id` se guarda como `SET_<trade_id>` y no enlaza con `setups`; la prima es sintética (sin strike/vencimiento reales).
- Para activar: cerrar y volver a abrir el bot (INICIAR_MELIORA_OPTIONS.bat). Al reiniciar se pierde la cola en memoria y se interrumpe Sonar unos segundos. No lo reinicié.

## Decisiones de Ismael (23/10/2026 16:20)
- D1 resuelta: Tampermonkey tiene instalada la v5.0.38 (captura). `/ucharts.user.js` sigue sirviendo la v5.0.30 del disco: hay que alinear.
- D2 abierta (no bloquea): el Apps Script desplegado dice v5.3; los dos archivos locales tienen el mismo encabezado.
- D3 resuelta: el Paper de referencia es **uCharts**. El simulador interno (SIM_INTERNO) pasa a ser sombra; sus resultados se registran pero no son la referencia de P&L.
- Familias: 11 estrategias de Cardona (PDF "Resumen del Seminario", verificado: Primer Gap, Gap Normal, Gap Bajista, Caída Normal/Fuerte, Piso Fuerte, PM40, Ruptura Canal Bajista, Ruptura Piso del Gap, Hanger, Primera Vela Roja, 4 Pasos). Las otras 7 (COLA_PISO, COLA_TECHO, RUPTURA_RES, TECHO_FUERTE, RUPTURA_SOP, PISO_BREAK, GAP_CONT_PUT) quedan PROPIA. Implementado en `trace_ledger.familia_de()` con alias de los ids que emite el scanner. Pendiente E2: marcar cuáles son adaptación de Cardona y cuáles creación propia.

## Hallazgos nuevos (para E2; no se cambió nada)
- Ids de estrategia inconsistentes: el scanner emite `CAIDA_NORMAL`, `CAIDA_FUERTE`, `4_PASOS`, `RUPTURA_PISO`, `PRIMER_GAP`; el catálogo y `sim_broker_core` usan `CAIDA_BREAK`, `CUATRO_PASOS`, `RUPTURA_PISO_GAP`, `PRIMER_GAP_ALZA`. El simulador interno responde "no configurada" a los ids del scanner (compra rechazada sin dejar rastro en `decisiones`).
- `GAP_NORMAL` y `GAP_BAJISTA_ALZA` no tienen ninguna señal ni setup en toda la base (0 de 6.222): revisar el detector (hay filtro hora < 11 en live_scanner.py:936).
- Catálogo: las 18 filas dicen `epistemology=CARDONA` (incluye las 7 que no lo son) y timeframe `1H` para todas, aunque el PDF define Hanger y Piso Fuerte con marco diario.
- Reglas del PDF a contrastar en E2 con el código (sin tocar): no comprar antes de las 11:00 (excepto Primera Vela Roja a las 10:00), Out of the Money, no vencimientos > 1 semana, solo en el cuadro de activos y rangos de precio.

## Ajuste de instrucciones (23/10/2026, mensaje 4) - incorporado al encargo
- Estado de etapas: E0 hecha. **E1 PARCIAL / NO DESPLEGADA** (6+1 tests OK, integracion sobre copia de BD OK; el bot en ejecucion usa codigo viejo). E2 iniciada (tabla documental + propuesta de panel). E3-E6 pendientes.
- **CORRECCION**: arriba figura que las 7 estrategias no documentadas quedan "PROPIA". Es incorrecto segun la regla "no inferir": quedan **SIN_CLASIFICAR** hasta que haya evidencia documental. `trace_ledger.PROPIA = {}`. Ver `TABLA_ESTRATEGIAS.md`.
- Panel: AutoTrade como seccion principal con 9 subsecciones desplegables (Estado y control; Estrategias Cardona; Estrategias personales; Atlas; Alertas TradingView; Noticias y fundamentos; Monitoreo y recompras; Configuracion y riesgo; Operacion manual). Planilla/Sincronizacion separada. "Cerrar todo - Emergencia" y estado de proteccion de posiciones siempre visibles. Por modulo: Habilitacion (APAGADO / SOLO ANALISIS / COMPRAS PAPER), Salud, ultima actividad/resultado, estrategia+version; PENDIENTE si no esta implementado. Abrir, consultar o "Escanear ahora" no autoriza compras. Pausar entradas conserva TP/SL y gestion de abiertas. Sin cambios de TP, SL, presupuestos ni horarios. Adaptado a celular.
- Propuesta visual publicada (maqueta, datos de ejemplo): artefacto "Panel AutoTrade - propuesta". El userscript NO se toca hasta tu confirmacion.
- D3: referencia = uCharts Paper Money; SIM_INTERNO es otro entorno, resultados separados, nunca sumados. Dimensiones separadas: fuente, canal, familia, estrategia+version, modo, entorno de ejecucion.
- Objetivo operativo: el bot (Sonar como radar continuo) monitorea los 35 activos con las estrategias de Cardona + herramientas propias (Bandera Automatica, Banderines Generales, Zona de Techo y Piso, Monitorear activos, Recomprar ganadores, Recomprar por estrategia), enviando ordenes de compra; TP/vencimiento existentes sin cambios. Alertas de TradingView (correo) deben convertirse en ordenes (E3).
- Orden: (1) registrar + propuesta visual [hecho]; (2) trazabilidad pendiente y pruebas; (3) reorganizar UI preservando comportamiento; (4) modulos nuevos por etapas; (5) verificar que abrir/escanear/recargar/reconectar no duplica ordenes ni procesos; (6) verificar que pausar entradas mantiene controles de abiertas. No reiniciar el bot por cambios de panel; antes de desplegar, resolver cola pendiente y posiciones abiertas.

## E2 - Hallazgos de la verificacion documental (ver TABLA_ESTRATEGIAS.md)
- Hecho: 11 estrategias con respaldo (indice de ESTRATEGIAS.pdf). TECHO_FUERTE aparece desarrollada en el PDF (pp.9-11) pero son 12 nombres vs. tus 11 -> **D6** (¿es de Cardona?). 6 sin fuente hallada: COLA_PISO, COLA_TECHO, RUPTURA_RES, RUPTURA_SOP, PISO_BREAK, GAP_CONT_PUT (aun falta leer a fondo Documento Maestro / Guia Cardona en Drive).
- **Causa de que GAP_NORMAL y GAP_BAJISTA nunca disparen**: el detector exige 2a barra (hora 10) y el filtro de L936 descarta hora<11 -> contradiccion estructural. Propuesta fiel al PDF: detectar a las 10:xx y liberar la orden desde las 11:00 si el patron sigue vigente. Requiere tu OK (cambia comportamiento).
- `GAP_ALZA_1` (L942) es codigo muerto (el id real es PRIMER_GAP).
- TECHO_FUERTE usa `d_at_floor` (piso) para una estrategia de techo: posible error de logica, sin tocar.
- CANAL_BREAK: el catalogo exige PM20<PM40 y cruce max. 15; el codigo solo `breakout_bar & is_green`. Catalogo y codigo difieren.
- Rollback de esta entrega: solo se crearon/editaron documentos (`TABLA_ESTRATEGIAS.md`, este registro) y `trace_ledger.py` (sin desplegar). Nada que revertir en produccion.

## Entrega E1b (23/10/2026 ~16:55 ART) - cierres, manuales, patas, recompras, cola persistente, conciliacion
**Correccion de estado**: el bot se reinicio a las 16:14 y ya corre la primera version de E1 (origen, ENCOLADA, EJECUTADA/BLOQUEADA del simulador, resultado de uCharts). Al 16:41: 15 ENCOLADA, 2 EJECUTADA y 2 RECHAZADA en uCharts ("UCharts no abrio la Cadena de opciones"; "no se reconocieron las filas CALL/strike/PUT"), y el simulador interno bloqueo 15 por MAX_TOTAL_OPEN_EXPOSURE_PCT (15 %) o por id no configurado (4_PASOS, CAIDA_FUERTE). Las filas de origen de esa version traen familia SIN_CLASIFICAR como marcador; `timeline()` ahora devuelve `familia_resuelta`.
**E1 = PARCIAL; primera version DESPLEGADA; E1b NO DESPLEGADA** (en disco, sin reiniciar).

Que cambio (todo aditivo, con la trazabilidad nunca bloqueando una compra):
- `trace_ledger.py`: estado nuevo `CIERRE_ENVIADA` (orden de venta puesta != cierre); `registrar_evento_uc` (eventos de uCharts: compras manuales con origen MANUAL y estrategia NULL, `group_id` de patas, `parent_trade_id` o `parent_ref` para recompras), `registrar_cierre_sim`, `pendientes_recuperables` / `a_conciliar` / `cancelar_encoladas` (cola persistente), `conciliar_historial` + tabla `trace_conciliacion` (COINCIDE / DIFIERE / SIN_ORIGEN / CERRADA_DESDE_HISTORIAL).
- `live_scanner.py`: la ENCOLADA guarda el payload; nuevos POST `/trace_event` y `/trace_conciliar` (solo registran); `/report_trade_result` registra con `trade_id=UC_<setup>` y `option_symbol`; STOP (panel y Telegram) deja CANCELADA lo encolado; `recuperar_cola_pendiente()` al arrancar.
- `sim_broker_core.py`: CERRADA del simulador al vender; `normalizar_estrategia()` (usa `trace_ledger.ALIAS`) en la compra y en la venta. **Bug real corregido**: una posicion simulada abierta con estrategia `cond_4_pasos` lanzaba KeyError al cerrarse, y `emergency_close` se cortaba a mitad de la lista. Efecto lateral esperado: el simulador interno (entorno sombra) ahora acepta CAIDA_NORMAL/FUERTE, 4_PASOS, RUPTURA_PISO, PRIMER_GAP y GAP_BAJISTA, que antes rechazaba en silencio.
- `ucharts_sync_userscript_v5.0.39.js` (archivo nuevo; la v5.0.38 instalada no se toco): `executeOrder` y `closePositionByCard` envueltos; Tester y sonda de Bandera con `group_id`; modos SONAR (con `setup_id` de la cola), TESTER, BANDERIN, BANDERA_AUTO, TECHO_PISO, RECOMPRA_GANADORES, RECOMPRA_ESTRATEGIA, MANUAL; CERRADA cuando una posicion rastreada desaparece de Posiciones; contraste de las ultimas 48 h del historial en cada sincronizacion. La logica de compra/venta, TP, SL y presupuestos no cambia.

Semantica: ENVIADA = el userscript inicio la orden en uCharts. EJECUTADA/RECHAZADA = lo observado en pantalla. CIERRE_ENVIADA = venta puesta (limite de TP o mercado). CERRADA = la posicion desaparecio de Posiciones (observacion heuristica) o la venta aparecio en el historial. Ninguno de esos equivale a "conciliada": eso es `trace_conciliacion`.

Que se probo (todo sobre copias; la base real solo se leyo):
- `python -m unittest test_trace_ledger`: 16 pruebas OK (cierres FIFO, huerfanos, idempotencia, patas, recompras, cola persistente, conciliacion, familias).
- `scratch\_etapa1b_integ.py` (servidor real en el puerto 8099 con copia de la base): 13 comprobaciones OK - cola recuperada tras reinicio, ENVIADA sin resultado no se repone, reporte repetido no duplica, STOP cancela, cierre simulado enlazado.
- `scratch\_test_userscript_trace.js`: 6 casos OK (ENVIADA/EJECUTADA/RECHAZADA, excepcion propagada, fallo de red no frena la compra, CIERRE_ENVIADA solo si la venta se pudo poner). `node --check` OK en v5.0.38 y v5.0.39.
- NO probado: el userscript v5.0.39 dentro de uCharts real (hace falta instalarlo); la recuperacion de cola con el bot real.

Pendiente de E1: espejo de los eventos a Google Sheets (depende de D2: que Apps Script esta desplegado); compras manuales del simulador (`/api/simulador/buy`) sin traza; cierres de uCharts de posiciones no rastreadas solo entran por el historial; ENVIADA real depende de instalar la v5.0.39.

Plan de despliegue (sin reiniciar por cambios de panel): (1) confirmar cola vacia (16:51: 0 pendientes); (2) reiniciar el bot una vez, idealmente fuera de horario: las posiciones abiertas viven en uCharts y en la base, no en memoria; (3) la cola de la sesion actual no tiene payload guardado, por eso conviene reiniciar con la cola vacia; desde ese reinicio la cola sobrevive a los siguientes; (4) instalar la v5.0.39 en Tampermonkey; (5) verificar en `trace_eventos` que aparezcan ENVIADA/EJECUTADA de compras manuales con origen MANUAL.
Como revertir: bot -> restaurar `live_scanner.py`, `sim_broker_core.py` y `trace_ledger.py` desde `Backup\etapa0_20261023` (las tablas `trace_*` son aditivas y pueden quedar); userscript -> reinstalar la v5.0.38; las pruebas y scripts de `scratch\` no afectan produccion.

## Hallazgos nuevos (E1b)
- Los rechazos de uCharts de hoy son de seleccion de contrato (la cadena no abrio / filas no reconocidas): problema de interfaz del userscript, no de la estrategia. Sin tocar.
- `emergency_close` y el seguimiento de TP/SL del simulador dependian de que `estrategia` existiera en `STRATEGY_BUCKETS`; corregido con fallback (ver arriba).
- 85 filas de `operaciones_simuladas` con state=OPEN y estado=CLOSED siguen sin explicar (E0).

## Decisiones de Ismael (23/10/2026 17:38) y entrega E2a
- D6 resuelta: **TECHO_FUERTE es Cardona** (el indice del PDF manda: 12 estrategias, no 11). `trace_ledger.CARDONA` pasa a 12. Quedan SIN_CLASIFICAR: COLA_PISO, COLA_TECHO, RUPTURA_RES, RUPTURA_SOP, PISO_BREAK, GAP_CONT_PUT. Duda abierta: el codigo de TECHO_FUERTE usa `d_at_floor` (piso) y el PDF la define por techo (PM100/PM200 diario); no se toco.
- Gap Normal / Gap Bajista: aprobado detectar en la 2a barra (10:xx) y liberar desde las 11:00. Implementado en `live_scanner.py`: `gap_registrar_pendiente` / `gap_liberar` (en memoria; se libera una sola vez por dia, solo si el cierre sigue sobre el minimo de la 2a barra). Probado con `scratch\_test_gap.py`. Vigencia = criterio mio, simple; corregible. Un reinicio entre las 10:xx y las 11:00 pierde el pendiente. NO desplegado.
- Panel aprobado con cambios: mantener el diseno anterior (botones redondeados como CORTO/MEDIO/LARGO), sin crecer en altura, AutoTrade dividido en botones de seccion. Hecho en `ucharts_sync_userscript_v5.0.40.js` (copia de la v5.0.39): menu de 9 botones (Estado, Cardona, Personales, Atlas, TradingView, Noticias, Monitoreo, Config., Manual); una seccion visible a la vez, recordada en localStorage; Cardona/Atlas/TradingView/Noticias muestran PENDIENTE (no simulan); Planilla/Sincronizacion sigue en su pestana; pie siempre visible con estado de proteccion, CERRAR TODO (PANICO) y Auto-Cierre PnL. Se verifico que los 34 ids originales siguen presentes y sin duplicar, y `node --check` OK. NO verificado visualmente dentro de uCharts.
- **Cambio de comportamiento (pedido en el encargo)**: antes, pausar el Auto-Trader tambien desactivaba la colocacion del Take Profit y el cierre por senal contraria de las posiciones del bot. Ahora pausar solo frena compras nuevas; TP, SL, vencimiento y senal contraria siguen. No cambia ningun valor de TP/SL/presupuesto. Falta la prueba en vivo (pausar con una posicion abierta y ver que el TP se coloca).
- Rollback: reinstalar la v5.0.38/39; quitar `GAP_*` de live_scanner restaurando el backup.

## 23/10 ~18:30 - Tester general + bucle de recompra ganadora (userscript v5.0.41)
- Nuevo boton "Lanzar tester general": 1 CALL + 1 PUT de cada activo monitoreado (lista del scanner) como sonda. "Lanzar Tester" (SPY) sigue igual pero ahora tambien entra al bucle.
- Bucle (testerTick, cada 3 s): diff = PnL% CALL - PnL% PUT. Si |diff - baseline| >= umbral (campo "Tester: diferencia", defecto 3%), compra la pata que gano el movimiento con contratos/perfil-dias/TP/SL del panel; baseline = diff actual. Se repite cada vez que se abre otro umbral (no compra en cada tick).
- Respeta: pausa del Auto-Trader (no compra), bucket diario, formulario ocupado. Trazas modo TESTER con group_id de la sonda. Estado persistido en localStorage por dia (sobrevive recarga). Boton "Detener bucle" (no toca posiciones).
- Probado: node --check OK; simulacion con mocks (_test_tester.js): sin disparo <3, CALL/CALL/PUT segun movimiento, pausa y bucket 0 no compran. NO probado aun en uCharts real.
- Desplegado: no (archivo v5.0.41 para instalar en Tampermonkey). Revertir: reinstalar v5.0.40/v5.0.38.

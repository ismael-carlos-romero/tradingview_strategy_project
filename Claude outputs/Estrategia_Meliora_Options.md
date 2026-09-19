# Meliora Options — Análisis de estrategias (Registro Continuo)

**Fuente:** hoja "Registro Continuo" de `PROYECTO MELIORA OPCIONES FINANCIERAS` (1054 operaciones, 21/04/2026 a 16/09/2026, paper trading broker simulado uCharts). Extraída completa vía export ODS (no la vista parcial del Sheet), limpiada (29 filas de error de registro excluidas) y analizada por 6 agentes en paralelo + 1 de síntesis, cada uno con Bash/pandas sobre el dataset real.

Metodología completa y dataset: ver `README.md` y `registro_continuo_dataset.csv` adjuntos.

---

## Resumen ejecutivo

El bot tiene un win rate real alto y estable (82–83% sobre el grupo limpio), pero un margen de seguridad muy fino en dólares (breakeven ~81.7% vs 83.2% real). Esa fragilidad se explica casi por completo por **falta de control de tamaño de posición**, no por mala selección de señales:

- 42 operaciones con tamaño anómalo (1001–20000 contratos, casi todas SPY) generan **-$29.76M**, lideradas por un solo trade de 20.000 contratos que perdió **-$27.4M** él solo (98.5% del PnL negativo de todo el dataset).
- Dentro del grupo "normal" (≤1000 contratos) hay un segundo patrón oculto: prima por acción o notional desproporcionados en pocas operaciones (AMD, META, GOOG, IWM, SPY) que generan otros **-$2.73M**. Varios tickers que *parecen* perdedores (AMD, GOOG, META, XOM, NFLX, BAC) en realidad tienen win rate alto — su saldo negativo lo causa una sola operación anómala, no la estrategia.
- No hay stop-loss: 47% de las pérdidas cierran entre -80% y -100% (34.5% exactamente en -100%, opciones que expiran sin valor).
- 27% de las filas tiene DTE (días a vencimiento) negativo — un bug de registro, no una señal de mercado.
- Las rachas de pérdidas son cierres simultáneos y correlacionados (23 de 25 rachas de 2+ pérdidas ocurrieron en menos de 1 hora), no errores secuenciales.
- Patrones secundarios reales: win rate cae de 93.4% (lunes) a 78.6% (viernes); mejor ventana horaria 13–16h ET; QQQ tiene una asimetría CALL/PUT marcada (CALL débil, PUT fuerte).

**Prioridad #1 antes de escalar a Interactive Brokers con dinero real: cerrar el agujero de sizing (tope de contratos Y de notional en USD) y agregar un stop-loss duro.** El resto son ajustes de segundo orden.

---

## Reglas priorizadas

### 🔴 CRÍTICAS

1. **Tope duro de contratos.** Rechazar automáticamente cualquier orden con `Cantidad > 1000`. Validado con los datos: por sí sola, esta regla lleva el PnL total del dataset de -$27.82M a +$357,776.

2. **Tope duro de notional (independiente del anterior).** Si `TotalCompra_proyectado = Cantidad × Compra_esperada × 100 > $150,000` (o > 15% del capital del sub-pool que ejecuta la orden), no enviar la orden completa: resizar `Cantidad = floor(cap_notional / (Compra_esperada × 100))` para conservar la señal con riesgo acotado. El cap de contratos solo no detecta 6 operaciones "normales" que perdieron -$2.73M (AMD 100 contratos @ $123.70 → -$1.02M; META 300 @ $20.68 → -$602K; GOOG 1000 @ $5.02 → -$368K; IWM 100 @ $102.70 → -$206K; SPY 1000 → -$293K y -$241K). El tope doble (contratos ≤1000 y notional ≤$150K) mejora el PnL simulado en +$30.09M.

3. **Sanity check de prima.** Bloquear envío automático y exigir confirmación manual si `Compra > $20/acción`, o si `Compra > 8× la mediana móvil de Compra del mismo ticker en sus últimos 60 trades`. La mediana global de prima es $2.67 (p95 = $14.15); las 3 mayores pérdidas absolutas del dataset superan ese rango largamente y hoy no las bloquea ningún filtro existente. El subgrupo con prima >$20 (n=19) tuvo win rate de solo 52.6% vs 82.9% del resto.

### 🟠 ALTAS

4. **Stop-loss automático obligatorio por posición**, a -35%/-40% de pérdida no realizada (empezar en -35%, más conservador; ajustar con datos reales de IB). Además, forzar cierre de toda posición 0DTE/1DTE que siga abierta a las 15:45 ET si no se activó TP ni stop.

5. **Filtro de calidad de dato, antes que cualquier otro filtro:** excluir/alertar toda fila u orden donde `DTE = FechaExp - Fecha` sea negativo o nulo, y bloquear activamente cualquier intento de abrir posición con DTE<0. 27% del dataset (227 filas) tiene DTE negativo — imposible en un trade real; ese subgrupo tiene WR 66.2% (vs 82.2% del DTE futuro genuino) y contamina cualquier análisis de vencimiento si no se separa.

6. **Sizing por proximidad a vencimiento:** reducir el tamaño 50% para entradas con DTE 0–2 días; tamaño pleno para DTE ≥3 días. DTE 3–7 días (WR 93.0%, 0% de pérdidas totales) y 8–14 días (WR 97.7%, 0% de pérdidas totales) son sustancialmente más seguros que 0–2 días (WR 82.2% pero con cola de pérdida total).

7. **Límite de exposición correlacionada:** no permitir más de 3–4 posiciones simultáneas abiertas en la misma dirección (todas CALL o todas PUT) sin cobertura. 23 de 25 rachas de 2+ pérdidas ocurrieron en menos de 1 hora (la mayoría en el mismo minuto) — son cierres correlacionados ante un mismo movimiento de mercado, no errores independientes; un "pausar tras N pérdidas" por conteo llegaría tarde.

### 🟡 MEDIAS

8. **Kill-switch de drawdown y WR rolling.** WR móvil sobre los últimos 50–100 trades cerrados; si cae por debajo de 78–80%, reducir a la mitad el tamaño de nuevas entradas. Si el drawdown de un sub-pool supera 15–20% de su capital desde el último pico, pausar hasta revisión manual. (Drawdown histórico máximo observado: -$1.50M entre el pico del 10/07 y el valle del 21/08.)

9. **Gate de escalado de capital real:** no subir el tope de capital manual en IB mientras el WR mensual (grupo limpio, n≥100) del mes más reciente esté por debajo de 80%. Septiembre 2026 (88.8%, n=458, parcial) como piso de referencia actual.

10. **Filtro direccional QQQ:** si `Ticker=='QQQ' and CallPut=='CALL'`, exigir score +2 puntos sobre el umbral estándar (o no operar) hasta que el WR móvil de los últimos 20 QQQ CALL supere 65%. QQQ PUT (WR 100%, n=11) mantiene tamaño normal o mayor. Ajuste más suave en COIN: reducir 50% el tamaño en COIN PUT (WR 60% vs 100% en COIN CALL).

11. **Ajuste por día/hora:** `size_multiplier ≤ 0.7` los viernes (WR 78.6% vs 93.4% el lunes, n>90 por día); preferir señales en la ventana 13:00–16:00 ET sobre 10:00–12:00 ET cuando compitan dos señales por capital el mismo día. La ventana 14:00–15:00 ET (peor resultado promedio) queda en monitoreo, no como filtro duro — está confundida con solo 2 días puntuales de agosto.

12. **Watchlist ampliada:** tamaño pleno del sub-pool para `NVDA, HPE, AMZN, ORCL, TNA, PLTR, MRNA, GOOGL` cuando su score iguale o supere al de un ticker fuera de esta lista (todos con WR≥93% y saldo positivo, n≥8). SPY y QQQ siguen siendo el núcleo por volumen, sujetos a las reglas 1–7 sin trato especial adicional.

### 🟢 BAJAS / instrumentación

13. **No vetar un ticker solo por saldo histórico negativo.** Calcular `concentración = |trade_máximo| / |saldo_total_ticker| × 100` antes de excluir; si >100% (como en AMD 134.6%, GOOG 147.6%, XOM 143.6%, NFLX 139.5%, BAC 149.7%, META 423.7%), el ticker es rentable sin su outlier — aplicar las reglas 2–3 en vez de descalificarlo.

14. **IWM:** operar solo con tamaño de prueba (≤10 contratos) hasta acumular 8 trades limpios sin ninguna prima >$50/acción (muestra actual: n=4).

15. **Instrumentación:** (a) empezar a poblar `Take Profit Objetivo` en cada apertura (hoy 0% de cobertura en 1054 filas — nunca se usó); (b) loggear como "incidente de riesgo" toda orden rechazada/resizada por las reglas de arriba, para auditar si el bug de sizing original reaparece; (c) corregir en el código la causa del DTE negativo antes de confiar en reglas basadas en DTE.

---

## Watchlist

**Priorizar:** NVDA, HPE, AMZN, ORCL, TNA, PLTR, MRNA, GOOGL, SPY, QQQ (solo lado PUT), COIN (solo lado CALL).

**Evitar / restringir:** QQQ CALL (WR 57.1% vs 100% en PUT), COIN PUT (WR 60% vs 100% en CALL), IWM (muestra insuficiente). AMD, GOOG, META, XOM, NFLX, BAC **no** se evitan como ticker — solo requieren obligatoriamente los topes de notional/prima (reglas 2–3), porque su saldo negativo histórico lo genera una única operación anómala.

---

## Hallazgos por dimensión (detalle)

### 1. Por ticker
33 tickers, SPY domina el volumen (34%, WR 73.7%, saldo +$441.797). Mejores 8 combinando WR y rentabilidad: NVDA, HPE, AMZN, ORCL, TNA, PLTR, MRNA, GOOGL (todos WR≥93%). Seis tickers que aparentan negativos (AMD, GOOG, META, XOM, NFLX, BAC) tienen WR 79–93% — su pérdida neta la explica al 100%+ una sola operación de tamaño desproporcionado. Único perdedor "genuino": QQQ, por la asimetría CALL (WR 57.1%) vs PUT (WR 100%).

### 2. CALL vs PUT
Sin ventaja direccional real a nivel agregado: WR casi idéntico (CALL 82.55% vs PUT 83.21%, diff 0.66pp) y el signo se invierte mes a mes. Pero PUT generó 6.65× más ganancia total en USD ($1.69M vs $254K) — no por acertar más, sino porque las pérdidas de CALL son en promedio 2.7× más grandes en dólares (mayor exposición nominal en los perdedores CALL).

### 3. Tamaño de posición (hallazgo central)
Ver reglas 1–3. Win rate casi idéntico entre grupo anómalo (78.6%) y normal (82.9%) — el problema es 100% tamaño, no señal. El bucket "normal" no es monótono: 11–100 contratos es el más consistente (WR 87.6%, +$1.15M); 501–1000 es el de mayor ganancia total pero también mayor riesgo nominal; el cluster de exactamente 1000 contratos (108 trades, 13% del grupo limpio) concentra el 81% de la ganancia neta reportada.

### 4. Timing (día/hora/mes)
WR cae monótonamente de lunes (93.4%) a viernes (78.6%). Mejor franja horaria: 13–16h ET (WR 88.7–96.1%). Detectado un artefacto de datos: 15 filas a la 1:00 con Venta=0 y DTE=-2 exacto (-$533,547) que son un bug de registro, no un patrón horario. Agosto fue el peor mes (WR 74.8%, y concentró 34 de las 42 anomalías de tamaño); septiembre mejoró a WR 88.8% (parcial, hasta el 16).

### 5. DTE (proximidad a vencimiento) y Take Profit
DTE 0–2 días futuro genuino: WR 82.2%. DTE 3–7: WR 93.0% (0% pérdidas totales). DTE 8–14: WR 97.7% (0% pérdidas totales). 27% de las filas tiene DTE negativo (bug, WR 66.2%, 22.7% pérdida total) — no mezclar con el DTE futuro genuino. `Take Profit Objetivo` está vacío en el 100% de las 1054 filas: nunca se usó, no se puede medir su efecto.

### 6. Rachas y consistencia
Racha ganadora más larga: 75 (sep). Racha perdedora más larga: 9 (dos veces). 23 de 25 rachas de 2+ pérdidas duraron menos de 1 hora — cierres correlacionados, no secuencia de errores. Pérdidas bimodales: 47% cierran entre -80% y -100% (evidencia clara de ausencia de stop-loss). Drawdown máximo: -$1.50M entre el pico del 10/07 y el valle del 21/08.

---

## Preguntas abiertas (requieren revisión del usuario/código, no de más datos)

- ¿Causa raíz exacta del trade de 20.000 contratos en SPY del 19/08? ¿Ya está corregida en el código?
- ¿Los cierres simultáneos de múltiples posiciones (base de las rachas) son un artefacto del broker simulado uCharts/Tampermonkey, o se replicarán en IB real?
- ¿Qué pasó operativamente el 21/08 12:11:41–12:11:49 (outliers de prima en AMD e IWM) y el 19/08 (trade gigante + cluster de DTE muy negativo)?
- ¿Causa técnica exacta del DTE negativo: error al grabar `Fecha`, al grabar `Fecha de Expiración`, o reinyección de opciones ya vencidas como trades nuevos?
- Septiembre está incompleto (datos hasta el 16) y concentra 55% de los trades limpios — revisar cifras al cerrar el mes.
- ¿Cómo cambian el margen breakeven (81.7%) y estos topes una vez que entren comisiones, slippage y fills parciales reales de IB?
- ¿`live_scanner.py` ya tiene algún control de tamaño/stop-loss hoy, o estas reglas se implementan desde cero?

---

*Análisis generado por un grupo de 7 agentes (6 de análisis por dimensión + 1 de síntesis) sobre los 1054 registros de la hoja "Registro Continuo", con verificación cruzada entre dimensiones donde coinciden (ej. sizing confirmado independientemente por los agentes de ticker, callput y streaks).*

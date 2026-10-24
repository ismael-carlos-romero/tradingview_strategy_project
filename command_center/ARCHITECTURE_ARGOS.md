# Meliora Command Center — Arquitectura inicial (ARGOS)
Fecha: 2026-10-24
Estado: diseño técnico; no conectado a producción
Rama: command-center

## Objetivo
Incorporar al portal local de Meliora Options un espacio de supervisión de agentes, con misiones, evidencias, reportes y métricas basadas en eventos reales. Primera oficina: ARGOS (auditoría, riesgo y rendimiento).

## Principios
- La PC local sigue siendo el entorno de ejecución del bot. GitHub es repositorio de código, no motor de ejecución.
- No alterar live_scanner.py, INICIAR_MELIORA_OPTIONS.bat, usuarioscripts, órdenes, brokers ni el esquema de trading durante la primera fase.
- Integración aditiva; API de solo lectura sobre datos de trading.
- No confundir agentes conceptuales con procesos autónomos desplegados. Estados: DISEÑADO, CONFIGURADO, CONECTADO, EJECUTANDO, ERROR, DESCONECTADO, derivados de heartbeat y ejecuciones.
- Separar simulación, paper y real en todas las consultas y métricas. Nunca sumar P&L entre entornos.
- Ningún LLM puede aprobar ni ejecutar órdenes reales. Las políticas de riesgo y permisos permanecen en controles deterministas.
- Repositorio público: no subir Excel/CSV de trades, DB operativas, credenciales, tokens, capturas sensibles ni datos personales. Retirar archivos del HEAD no los borra del historial; planificar limpieza de historial por separado, con respaldo y coordinación.

## Fuentes de código verificadas en main
- index.html: portal HTML/CSS/JS con diseño oscuro.
- live_scanner.py: servicio local que arranca con INICIAR_MELIORA_OPTIONS.bat, puerto 8055.
- risk_engine.py: políticas de riesgo y tabla risk_audit_log; modo live explícitamente deshabilitado en este módulo.
- trace_ledger.py: trace_origen y trace_eventos, procedencia y ciclo de vida de señales/órdenes.
- sim_broker_core.py: núcleo del simulador; verificar contrato y tablas antes de consumir.
- postgres_schema.sql / schema.sql: esquemas existentes; evitar migraciones destructivas.
- reporte_tecnico_diario.py, quantitative_analyst.py, analyze_results.py: candidatos a reutilización, previa inspección de funciones y fuentes.
- ucharts_sync_userscript_v5.0.41.js: versión de userscript presente; no modificar.

## Diseño de la oficina ARGOS
Ruta de interfaz propuesta: /command-center/argos (ajustar al router actual; no asumir framework).
Pestañas:
1. Resumen: estado de fuentes, fecha/hora de actualización, operaciones conciliadas, hallazgos, calidad de datos, exposición y métricas separadas por cuenta/entorno.
2. Misiones: cola con prioridad, estado, responsable, timestamps, evidencia, bloqueos y resolución.
3. Informes: auditoría diaria, conciliación, control de riesgo, desempeño por estrategia, reporte semanal.
4. Conexiones: estado real de SQLite/Sheets/uCharts/PRISMA/Jarvis, última sincronización y errores.

## Contratos de datos propuestos
agent_registry(id, name, role, status, capabilities_json, last_heartbeat_at)
agent_runs(id, agent_id, mission_id, started_at, finished_at, status, source_version, error_summary)
missions(id, agent_id, title, priority, status, created_at, updated_at, requested_by, approval_required)
audit_findings(id, mission_id, severity, category, source_ref, evidence_json, observed_at, status, recommendation, reviewer)
audit_reports(id, mission_id, report_type, period_start, period_end, environment, source_snapshot, generated_at, validation_status, artifact_path)
integration_health(id, integration_name, status, last_checked_at, last_success_at, details_json)
agent_activity(id, agent_id, mission_id, timestamp, event_type, payload_json)
Implementar en DB propia de Command Center, no sobreescribir tablas de trading.

## Cálculos y validación
- Trades: usar IDs estables, contrato, vencimiento, strike, tipo, cantidad, multiplicador, precio, comisiones y timestamps.
- Emparejar aperturas/cierres parciales y expiraciones; reportar faltantes, duplicados y discrepancias.
- P&L realizado y no realizado separados; win rate solo con operaciones cerradas y criterio explícito; profit factor con definición documentada.
- No calcular cero cuando falten datos: marcar NO DISPONIBLE o NO CONCILIADO.
- Cada métrica debe mostrar fuente, período, entorno, versión de cálculo y última actualización.
- Cada hallazgo debe conservar evidencia y bitácora de cambios; no corregir registros originales silenciosamente.

## APIs iniciales propuestas (solo lectura)
GET /api/command-center/agents
GET /api/command-center/agents/argos
GET /api/command-center/argos/summary?environment=paper&period=day
GET /api/command-center/argos/missions
GET /api/command-center/argos/findings
GET /api/command-center/argos/reports
GET /api/command-center/integrations/health
Las mutaciones de misiones/revisiones requieren autenticación, autorización, idempotencia y auditoría antes de habilitarse.

## Plan de implementación
F0: verificar estructura real, rutas, DB, dependencias y seguridad de publicación.
F1: interfaz de ARGOS integrada en navegación, con adaptador de datos de prueba rotulado; sin cambios a trading.
F2: API y DB propia; adaptadores de lectura y reconciliación sobre fuentes existentes; tests con fixtures.
F3: reportes verificables, métricas de desempeño y panel Jarvis; notificaciones controladas.
F4: ampliar oficinas a los demás agentes, únicamente cuando haya ejecuciones reales instrumentadas.

## Criterios de aceptación de F1
- Portal original y bot funcionan sin regresiones.
- Oficina ARGOS accesible desde navegación, usable en escritorio y móvil.
- Estados y métricas de prueba etiquetados como demostración; no simular agentes activos.
- Ninguna petición de la oficina puede crear órdenes ni modificar saldos.
- Errores de fuentes se muestran claramente, sin inventar métricas.
- Pruebas locales con bot en marcha antes de merge a main.
- Cambios mediante PR, revisión humana y aprobación del director del proyecto.

## Pendientes de verificación
- Comprobar diferencias reales entre PC y commit base; el usuario informa que fueron sincronizadas.
- Auditar exposición de archivos operativos en GitHub y revisar historial.
- Revisar seguridad del túnel y autenticación antes de exponer API de Command Center.
- Revisar taskkill global en lanzador en fase separada; no tocar ahora.

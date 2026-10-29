# Ingesta de reportes — decisión de arquitectura (fase 1)

Estado: **propuesta con pruebas locales; nada ejecutado en producción** (ni Supabase ni la hoja de estudio).

## Cambio de arquitectura: de Edge Function a función SQL por RPC
El diseño inicial hablaba de una Edge Function `ingest`. Se cambió a **una función SQL `public.cc_ingest_report(p_token, p_report)` invocada por RPC** (`POST /rest/v1/rpc/cc_ingest_report`).

| | Edge Function | Función SQL por RPC (elegida) |
|---|---|---|
| Atomicidad reporte + auditoría | Dos llamadas o una RPC igualmente; hay que escribirla en SQL de todos modos | Nativa: una sola transacción |
| Clave en el servidor | Necesita `service_role` como secreto de la función | No usa `service_role`; corre como dueño de la función |
| Piezas a desplegar/operar | Función + CLI/secretos + SQL | Solo SQL |
| Riesgo | Mal manejo del secreto | Mal diseño de permisos o de `SECURITY DEFINER` (revisado abajo) |

Se puede volver a una Edge Function sin cambiar el formato del reporte: bastaría que la función llame a esta misma RPC.

## Cómo se ejecuta y qué permisos tiene
- `SECURITY DEFINER`: corre con los privilegios de su dueño (`postgres`), por eso puede leer `cc_ingest_tokens` aunque el navegador no pueda. Es el único camino hacia esa tabla.
- `set search_path = ''` y todo calificado (`public.*`, `extensions.digest`, `pg_catalog.*`): evita secuestro de funciones/tablas por search_path.
- `EXECUTE`: revocado a `public`, `anon` y `authenticated`… y concedido **solo a `anon` y `service_role`**. La app web (usuario logueado = rol `authenticated`) **no puede invocarla**; el Apps Script la llama con la clave publishable (rol `anon`) + token.
- `cc_ingest_tokens`: RLS activo sin políticas + `REVOKE ALL` a `public/anon/authenticated`. Nadie la lee ni escribe desde la API. Solo `service_role` (servidor/SQL Editor).
- `cc_reports` y `cc_audit_events`: sin `INSERT/UPDATE/DELETE` para `anon/authenticated`; lectura solo del dueño (RLS ya existente).

## Qué valida la función (en este orden)
1. Token: longitud 32–200, hash SHA-256 existente, `revoked_at is null`, `expires_at` vacío o futuro. Error genérico `unauthorized`.
2. Forma: objeto JSON, ≤ 200 000 caracteres, **solo campos permitidos** (`agent_id, report_id, revision, format_version, title, summary, findings, cutoff_at, generated_at, status, coverage, sources, limits`). Un campo extra (p. ej. `owner_id`) se rechaza.
3. Agente: autorizado para ese token (`allowed_agents`) **y** registrado en `cc_agents` del dueño del token.
4. Campos: tipos y largos, `status ∈ COMPLETE|PARTIAL|BLOCKED`, fechas ISO-8601 **con zona**, `coverage` solo con `expected/reviewed/unverified/calendar_events` y coherente, `sources` solo `https`, ≤ 100.
5. Idempotencia: clave `(dueño, agente, report_id, revision)`; hash del contenido **sin `generated_at`**. Igual → `duplicate`; distinto → error `23505`. `INSERT … ON CONFLICT DO NOTHING` hace correcta la carrera entre envíos simultáneos.
6. Auditoría `REPORT_INGESTED` en la misma transacción: guarda `report_key`, `revision`, `status` y `token_id`. **Nunca** el token ni el contenido.

Para revocar: `update public.cc_ingest_tokens set revoked_at = now() where label = '…';`

## Agente de Noticias
El catálogo (`seed_agents.sql`) no tiene un agente "Noticias y Fundamentos" inequívoco: `ATLAS` figura como "Inteligencia de mercado y fundamentos (noticias, earnings, calendario)", pero según el equipo en ChatGPT Atlas hace análisis técnico pre/post-market, y `SONAR` es el radar de oportunidades (no se reutiliza). Se propone **incorporar `NOTICIAS`** (`seed_agent_noticias.sql`, sin ejecutar). **Decisión pendiente de Ismael**: aprobar `NOTICIAS` y corregir la descripción de `ATLAS`/`VECTOR` en el catálogo.

## Cómo se prueba
- `tests/ingest_tests.sh`: Postgres 16 descartable con roles y privilegios por defecto al estilo Supabase. 78 comprobaciones: token inválido/vencido/revocado, agente incorrecto, reportes mal formados, primer envío, reenvío, conflicto, concurrencia real (transacción abierta + 10 paralelos + 4 distintos), atomicidad (fallo forzado de la auditoría), permisos por rol, filtración del token, y aceptación del corte `MELIORA_20261029_085305_AR`.
- `tests/noticias_dryrun.js`: 23 comprobaciones de la lógica del Apps Script y generación de `tests/dryrun_output.json` (lo que se enviaría).

## Qué NO está probado
- Supabase real: el banco imita sus roles/privilegios; la capa PostgREST/JWT y los límites de la plataforma no se ejercitaron.
- Apps Script en su runtime real (`SpreadsheetApp`, `UrlFetchApp`, `Utilities`). La lógica pura sí; la E/S no.
- El DRY_RUN usa los IDs, tickers, estados, URLs y calendario reales del corte, pero con textos de noticia abreviados. El verdadero DRY_RUN se corre en Apps Script con `validarCorte()`.
- Fuerza bruta sobre el token: el token que genera `prepararToken()` tiene ~360 bits, así que adivinarlo es inviable; no se agregó limitador propio.
- Logs: con envío por RPC de PostgREST el token viaja como parámetro (no se registra por defecto). Si se activa `log_statement = 'all'` en el proyecto, podría quedar en los logs.

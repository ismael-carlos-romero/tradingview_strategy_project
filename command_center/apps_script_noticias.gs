/**
 * Meliora Command Center - envio de reportes de "Noticias y Fundamentos" (fase 1).
 * Lee SOLO la hoja de estudio (AGENTE_NOTICIAS, NOTICIAS_DIARIAS, CALENDARIO_EVENTOS). No toca la planilla operativa.
 * Une las tres pestanas por "ID informe" (nunca por cercania de filas) y se DETIENE si algo no cuadra.
 *
 * Propiedades del script (Configuracion del proyecto > Propiedades del script). Nada de esto va al repo ni al navegador:
 *   STUDY_SHEET_ID  ID de la hoja de estudio
 *   SUPABASE_URL    https://<proyecto>.supabase.co
 *   SUPABASE_KEY    clave publishable (publica por diseno)
 *   INGEST_TOKEN    lo genera prepararToken(); solo vive aqui
 *   DRY_RUN         'false' para enviar de verdad; cualquier otro valor (o vacio) = solo valida y muestra el reporte
 *   REVISION        opcional, entero >= 1 (por defecto 1). Subirlo SOLO para reenviar una version corregida.
 *   REPORT_ID       opcional; por defecto el ultimo informe de AGENTE_NOTICIAS
 * Scopes minimos (appsscript.json): spreadsheets.readonly y script.external_request.
 *
 * Funciones: prepararToken() -> validarCorte() (nunca envia) -> enviarCorte() (envia solo si DRY_RUN = 'false').
 */
var AGENT_ID = 'NOTICIAS';
var FORMAT_VERSION = '1.0';
var TZ_AR = 'America/Argentina/Buenos_Aires';
var TOTAL_ACTIVOS = 35;
var ESTADO_VERIFICADO = 'Parcial: contexto verificado';
var ESTADO_NO_VERIFICADO = 'No verificado';
var ENCABEZADOS = {
  AGENTE_NOTICIAS: ['Corte Argentina', 'ID informe', 'Activos revisados', 'Activos no verificados', 'Prioridades 80/20', 'Auditoría de trades', 'Límites / errores', 'Enlace al detalle'],
  NOTICIAS_DIARIAS: ['Corte Argentina', 'ID informe', 'Ticker', 'Empresa / fondo', 'Noticia / contexto', 'Categoría', 'Fecha del evento', 'Publicado / hora UTC', 'Relación con señal', 'Estrategia registrada', 'Dirección registrada', 'Fuente URL', 'Próximo earnings', 'Momento earnings', 'Estado cobertura', 'Limitaciones'],
  CALENDARIO_EVENTOS: ['Corte Argentina', 'ID informe', 'Activo / macro', 'Evento', 'Fecha prevista', 'Hora y zona', 'Confirmado / estimado', 'Fuente URL', 'Enlace informe', 'Notas']
};

/* ------------------------- Logica pura (probada en Node, sin Apps Script) ------------------------- */

function txt_(v) {
  if (v === null || v === undefined) return '';
  if (Object.prototype.toString.call(v) === '[object Date]') {
    return (typeof Utilities !== 'undefined') ? Utilities.formatDate(v, TZ_AR, 'dd/MM/yyyy HH:mm:ss') : v.toISOString();
  }
  return String(v).trim();
}
function cmpHeaders_(row, esperado) {
  var faltan = [];
  for (var i = 0; i < esperado.length; i++) {
    if (txt_(row[i]) !== esperado[i]) faltan.push('columna ' + (i + 1) + ': esperaba "' + esperado[i] + '" y hay "' + txt_(row[i]) + '"');
  }
  return faltan;
}
function cut_(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
function parseCorte_(s) { // 'dd/mm/yyyy hh:mm:ss' -> {iso, humano, idStamp}
  var m = /^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2}):(\d{2})$/.exec(s);
  if (!m) return null;
  return { iso: m[3] + '-' + m[2] + '-' + m[1] + 'T' + m[4] + ':' + m[5] + ':' + m[6] + '-03:00',
           humano: m[1] + '/' + m[2] + '/' + m[3] + ' ' + m[4] + ':' + m[5],
           idStamp: m[3] + m[2] + m[1] + '_' + m[4] + m[5] + m[6] };
}

/** tablas = {AGENTE_NOTICIAS, NOTICIAS_DIARIAS, CALENDARIO_EVENTOS} como matrices (getValues). opts = {reportId, revision, now}.
 *  Devuelve {problems:[...], report:null|{...}}. Si hay problemas NO hay reporte: el envio debe detenerse. */
function construirReporte_(tablas, opts) {
  opts = opts || {};
  var problems = [];
  var resumen = tablas.AGENTE_NOTICIAS || [], noticias = tablas.NOTICIAS_DIARIAS || [], calendario = tablas.CALENDARIO_EVENTOS || [];

  // 1. Encabezados exactos
  var hRes = -1;
  for (var i = 0; i < resumen.length; i++) { if (txt_(resumen[i][0]) === ENCABEZADOS.AGENTE_NOTICIAS[0] && txt_(resumen[i][1]) === ENCABEZADOS.AGENTE_NOTICIAS[1]) { hRes = i; break; } }
  if (hRes < 0) {
    problems.push('AGENTE_NOTICIAS: no se encontró la fila de encabezados ("Corte Argentina" | "ID informe" ...).');
  } else {
    cmpHeaders_(resumen[hRes], ENCABEZADOS.AGENTE_NOTICIAS).forEach(function (x) { problems.push('AGENTE_NOTICIAS encabezado ' + x); });
  }
  if (!noticias.length) problems.push('NOTICIAS_DIARIAS: pestaña vacía.');
  else cmpHeaders_(noticias[0], ENCABEZADOS.NOTICIAS_DIARIAS).forEach(function (x) { problems.push('NOTICIAS_DIARIAS encabezado ' + x); });
  if (!calendario.length) problems.push('CALENDARIO_EVENTOS: pestaña vacía.');
  else cmpHeaders_(calendario[0], ENCABEZADOS.CALENDARIO_EVENTOS).forEach(function (x) { problems.push('CALENDARIO_EVENTOS encabezado ' + x); });
  if (problems.length) return { problems: problems, report: null };

  // 2. Informe elegido: debe existir exactamente una vez en el resumen
  var filasRes = resumen.slice(hRes + 1).filter(function (r) { return txt_(r[1]) !== ''; });
  if (!filasRes.length) return { problems: ['AGENTE_NOTICIAS: no hay informes bajo el encabezado.'], report: null };
  var reportId = opts.reportId || txt_(filasRes[filasRes.length - 1][1]);
  var delId = filasRes.filter(function (r) { return txt_(r[1]) === reportId; });
  if (delId.length !== 1) return { problems: ['AGENTE_NOTICIAS: el ID "' + reportId + '" aparece ' + delId.length + ' veces (debe ser exactamente 1).'], report: null };
  var res = delId[0];
  if (!/^MELIORA_\d{8}_\d{6}_AR$/.test(reportId)) problems.push('ID de informe con formato inesperado: ' + reportId);

  // 3. Corte coherente con el ID
  var corteTxt = txt_(res[0]);
  var corte = parseCorte_(corteTxt);
  if (!corte) problems.push('Corte "' + corteTxt + '" no tiene formato dd/mm/aaaa hh:mm:ss.');
  else if ('MELIORA_' + corte.idStamp + '_AR' !== reportId) problems.push('El corte "' + corteTxt + '" no coincide con el ID ' + reportId + '.');

  // 4. Cobertura declarada
  var revisados = Number(txt_(res[2])), noVerif = Number(txt_(res[3]));
  if (!/^\d+$/.test(txt_(res[2])) || !/^\d+$/.test(txt_(res[3]))) problems.push('Activos revisados / no verificados no son enteros: "' + txt_(res[2]) + '" / "' + txt_(res[3]) + '".');

  // 5. Detalle por activo: unido SOLO por ID informe
  var det = noticias.slice(1).filter(function (r) { return txt_(r[1]) === reportId; });
  var vistos = {}, dup = [], okN = 0, noN = 0, otros = {};
  det.forEach(function (r) {
    var tk = txt_(r[2]).toUpperCase();
    if (!tk) problems.push('NOTICIAS_DIARIAS: fila del informe sin ticker.');
    else if (vistos[tk]) dup.push(tk); else vistos[tk] = true;
    var est = txt_(r[14]);
    if (est === ESTADO_VERIFICADO) okN++; else if (est === ESTADO_NO_VERIFICADO) noN++; else otros[tk + ' = "' + est + '"'] = true;
    if (txt_(r[0]) !== corteTxt) problems.push('NOTICIAS_DIARIAS: ' + tk + ' tiene corte "' + txt_(r[0]) + '" distinto del informe.');
  });
  if (dup.length) problems.push('NOTICIAS_DIARIAS: tickers duplicados en el informe: ' + dup.join(', ') + '.');
  Object.keys(otros).forEach(function (k) { problems.push('NOTICIAS_DIARIAS: estado de cobertura no reconocido: ' + k + '.'); });
  if (det.length !== TOTAL_ACTIVOS) problems.push('NOTICIAS_DIARIAS: el informe tiene ' + det.length + ' filas y se esperaban ' + TOTAL_ACTIVOS + ' activos.');
  if (okN !== revisados) problems.push('Cobertura no cuadra: el resumen declara ' + revisados + ' revisados y el detalle tiene ' + okN + ' "' + ESTADO_VERIFICADO + '".');
  if (noN !== noVerif) problems.push('Cobertura no cuadra: el resumen declara ' + noVerif + ' no verificados y el detalle tiene ' + noN + ' "' + ESTADO_NO_VERIFICADO + '".');
  if (revisados + noVerif !== det.length) problems.push('Cobertura no cuadra: ' + revisados + ' + ' + noVerif + ' no suma las ' + det.length + ' filas del detalle.');

  // 6. Calendario: unido por ID informe
  var cal = calendario.slice(1).filter(function (r) { return txt_(r[1]) === reportId; });
  cal.forEach(function (r, i) {
    if (!txt_(r[2]) || !txt_(r[3])) problems.push('CALENDARIO_EVENTOS: evento #' + (i + 1) + ' del informe sin activo o sin evento.');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(txt_(r[4]))) problems.push('CALENDARIO_EVENTOS: fecha prevista inválida en "' + txt_(r[2]) + '": "' + txt_(r[4]) + '".');
  });

  // 7. Fuentes: solo https; deduplicadas
  var fuentes = [], vf = {};
  function addFuente(u, donde) {
    u = txt_(u); if (!u) return;
    if (!/^https:\/\/\S+$/.test(u) || u.length > 500) { problems.push(donde + ': URL de fuente no válida (solo https): ' + cut_(u, 80)); return; }
    if (!vf[u]) { vf[u] = true; fuentes.push(u); }
  }
  det.forEach(function (r) { addFuente(r[11], 'NOTICIAS_DIARIAS ' + txt_(r[2])); });
  cal.forEach(function (r) { addFuente(r[7], 'CALENDARIO_EVENTOS ' + txt_(r[2])); });
  if (fuentes.length > 100) problems.push('Más de 100 fuentes distintas (' + fuentes.length + ').');

  if (problems.length) return { problems: problems, report: null };

  // 8. Reporte (cobertura parcial declarada de forma explícita)
  var limResumen = txt_(res[6]);
  var verificados = det.filter(function (r) { return txt_(r[14]) === ESTADO_VERIFICADO; });
  var noVerificados = det.filter(function (r) { return txt_(r[14]) === ESTADO_NO_VERIFICADO; });
  var completo = noVerif === 0 && limResumen === '';
  var resumenTxt = completo
    ? 'Corte ' + corte.humano + ' (AR). ' + revisados + ' de ' + det.length + ' activos con contexto verificado. Eventos de calendario del corte: ' + cal.length + '.'
    : 'Corte ' + corte.humano + ' (AR). Cobertura PARCIAL: ' + revisados + ' de ' + det.length + ' activos con contexto o calendario verificado; ' + noVerif +
      ' no verificados (sin búsqueda individual suficiente; no se afirma ausencia de novedades). No es una investigación exhaustiva de los ' + det.length +
      ' activos. Eventos de calendario del corte: ' + cal.length + '. Límites declarados por el agente: ' + cut_(limResumen, 1200);
  var L = [];
  L.push('ACTIVOS CON CONTEXTO VERIFICADO (' + verificados.length + '):');
  verificados.forEach(function (r) { L.push('- ' + txt_(r[2]) + ' | ' + txt_(r[5]) + ' | ' + cut_(txt_(r[4]), 230)); });
  L.push('', 'ACTIVOS NO VERIFICADOS (' + noVerificados.length + '): ' + noVerificados.map(function (r) { return txt_(r[2]); }).join(', '));
  L.push('', 'CALENDARIO (' + cal.length + '):');
  cal.forEach(function (r) { L.push('- ' + txt_(r[4]) + ' ' + txt_(r[5]) + ' | ' + txt_(r[2]) + ' | ' + txt_(r[3]) + ' | ' + txt_(r[6])); });
  if (txt_(res[4])) L.push('', 'PRIORIDADES 80/20 (texto del agente): ' + cut_(txt_(res[4]), 1500));
  if (txt_(res[5])) L.push('', 'AUDITORÍA DE TRADES (texto del agente): ' + cut_(txt_(res[5]), 1500));
  var limites = [];
  if (noVerif > 0) limites.push(noVerif + ' de ' + det.length + ' activos no verificados');
  if (limResumen) limites.push(cut_(limResumen, 1000));
  var vl = {};
  det.forEach(function (r) { var l = txt_(r[15]); if (l && !vl[l] && limites.length < 6) { vl[l] = true; limites.push(cut_(l, 1000)); } });

  var now = opts.now || new Date();
  return { problems: [], report: {
    agent_id: AGENT_ID,
    report_id: reportId,
    revision: opts.revision || 1,
    format_version: FORMAT_VERSION,
    title: 'Noticias y Fundamentos - corte ' + corte.humano + (completo ? '' : ' (parcial)'),
    summary: cut_(resumenTxt, 4000),
    findings: cut_(L.join('\n'), 30000),
    cutoff_at: corte.iso,
    generated_at: now.toISOString(),
    status: completo ? 'COMPLETE' : 'PARTIAL',
    coverage: { expected: det.length, reviewed: revisados, unverified: noVerif, calendar_events: cal.length },
    sources: fuentes,
    limits: limites
  } };
}

/* ------------------------- Apps Script (E/S) ------------------------- */

function leerTablas_() {
  var p = PropertiesService.getScriptProperties();
  var ss = SpreadsheetApp.openById(p.getProperty('STUDY_SHEET_ID'));
  var t = {};
  Object.keys(ENCABEZADOS).forEach(function (n) {
    var sh = ss.getSheetByName(n);
    if (!sh) throw new Error('La hoja configurada no tiene la pestaña ' + n + ' (¿es la hoja de estudio?). No se envía nada.');
    t[n] = sh.getDataRange().getValues();
  });
  return t;
}
function armar_() {
  var p = PropertiesService.getScriptProperties();
  var rev = parseInt(p.getProperty('REVISION') || '1', 10);
  var r = construirReporte_(leerTablas_(), { reportId: p.getProperty('REPORT_ID') || undefined, revision: rev >= 1 ? rev : 1 });
  if (r.problems.length) throw new Error('ENVÍO DETENIDO. Problemas encontrados:\n- ' + r.problems.join('\n- '));
  return r.report;
}
/** Solo valida y muestra el reporte. Nunca envía. */
function validarCorte() { Logger.log(JSON.stringify(armar_(), null, 2)); }

/** Envía el último corte SOLO si la propiedad DRY_RUN vale 'false'. */
function enviarCorte() {
  var p = PropertiesService.getScriptProperties();
  var report = armar_();
  if (p.getProperty('DRY_RUN') !== 'false') { Logger.log('DRY_RUN activo: no se envió nada.\n' + JSON.stringify(report, null, 2)); return; }
  var resp = UrlFetchApp.fetch(p.getProperty('SUPABASE_URL') + '/rest/v1/rpc/cc_ingest_report', {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { apikey: p.getProperty('SUPABASE_KEY'), Authorization: 'Bearer ' + p.getProperty('SUPABASE_KEY') },
    payload: JSON.stringify({ p_token: p.getProperty('INGEST_TOKEN'), p_report: report })
  });
  var code = resp.getResponseCode();
  if (code !== 200) throw new Error('Ingesta rechazada (HTTP ' + code + '): ' + cut_(resp.getContentText(), 300));
  Logger.log('Ingesta OK: ' + resp.getContentText());
}

/** Genera el token dentro de Apps Script (no sale de aquí) y muestra solo su hash para registrarlo en Supabase. */
function prepararToken() {
  var p = PropertiesService.getScriptProperties();
  var tok = p.getProperty('INGEST_TOKEN');
  if (!tok) {
    tok = (Utilities.getUuid() + Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '');
    p.setProperty('INGEST_TOKEN', tok);
  }
  var hash = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, tok, Utilities.Charset.UTF_8)
    .map(function (b) { return ('0' + (b & 0xff).toString(16)).slice(-2); }).join('');
  Logger.log('Hash SHA-256 del token (no es secreto; el token no se muestra): ' + hash +
    '\nRegistrarlo con el INSERT comentado en seed_agent_noticias.sql.');
}

if (typeof module !== 'undefined') { module.exports = { construirReporte_: construirReporte_, ENCABEZADOS: ENCABEZADOS }; }

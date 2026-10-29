/**
 * Meliora Command Center - envio de reportes de NOTICIAS (fase 1).
 * Lee SOLO la hoja de estudio. No toca la planilla operativa.
 * Configuracion en Propiedades del script (Configuracion del proyecto > Propiedades del script):
 *   STUDY_SHEET_ID  = ID de la hoja de estudio
 *   INGEST_URL      = https://pcxzqnsjacllutpjbbzy.supabase.co/rest/v1/rpc/cc_ingest_report
 *   SUPABASE_KEY    = clave publishable (publica)
 *   INGEST_TOKEN    = token de ingesta (solo aqui, nunca en el repo ni en el navegador)
 * Ejecutar: enviarUltimoCorteNoticias()  (primero con DRY_RUN = true).
 */
var DRY_RUN = true;
var AGENT_ID = 'SONAR';

function enviarUltimoCorteNoticias() {
  var p = PropertiesService.getScriptProperties();
  var ss = SpreadsheetApp.openById(p.getProperty('STUDY_SHEET_ID'));
  var res = rows_(ss.getSheetByName('AGENTE_NOTICIAS'));
  if (!res.length) throw new Error('AGENTE_NOTICIAS vacia');
  var last = res[res.length - 1];
  var rid = String(last.report_id || last.ID_REPORTE || last[Object.keys(last)[0]]);
  var det = rows_(ss.getSheetByName('NOTICIAS_DIARIAS')).filter(function (r) { return matches_(r, rid); });
  var cal = rows_(ss.getSheetByName('CALENDARIO_EVENTOS')).filter(function (r) { return matches_(r, rid); });
  var unverified = det.filter(function (r) { return /no verific|sin verific|unverified/i.test(JSON.stringify(r)); }).length;
  var sources = [];
  det.forEach(function (r) { Object.keys(r).forEach(function (k) { var v = String(r[k]); if (/^https?:\/\//.test(v) && sources.length < 100 && sources.indexOf(v) < 0) sources.push(v); }); });
  var report = {
    agent_id: AGENT_ID, report_id: rid, revision: 1, format_version: '1.0',
    title: 'Noticias y fundamentos - corte ' + rid,
    summary: JSON.stringify(last).slice(0, 4000),
    findings: 'Detalle por activo: ' + det.length + ' filas. Eventos de calendario: ' + cal.length + '.',
    cutoff_at: new Date().toISOString(), generated_at: new Date().toISOString(),
    status: unverified > 0 ? 'PARTIAL' : 'COMPLETE',
    coverage: { expected: det.length, reviewed: det.length - unverified, unverified: unverified },
    sources: sources,
    limits: unverified > 0 ? [unverified + ' activos sin verificar'] : []
  };
  if (DRY_RUN) { Logger.log(JSON.stringify(report, null, 2)); return; }
  var r = UrlFetchApp.fetch(p.getProperty('INGEST_URL'), {
    method: 'post', contentType: 'application/json', muteHttpExceptions: true,
    headers: { apikey: p.getProperty('SUPABASE_KEY'), Authorization: 'Bearer ' + p.getProperty('SUPABASE_KEY') },
    payload: JSON.stringify({ p_token: p.getProperty('INGEST_TOKEN'), p_report: report })
  });
  Logger.log(r.getResponseCode() + ' ' + r.getContentText());
}

function rows_(sh) {
  if (!sh) return [];
  var v = sh.getDataRange().getValues(); if (v.length < 2) return [];
  var h = v[0].map(String);
  return v.slice(1).filter(function (r) { return r.join('') !== ''; }).map(function (r) { var o = {}; h.forEach(function (k, i) { o[k] = r[i]; }); return o; });
}
function matches_(row, rid) { return Object.keys(row).some(function (k) { return String(row[k]) === rid; }); }
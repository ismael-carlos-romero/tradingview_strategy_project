/**
 * Google Apps Script Webhook Listener - Relational Laboratory Engine (v5.3)
 * 
 * Administra el modelo relacional de 14 tablas en Google Sheets,
 * separando SEÑALES, SETUPS, RADAR, OPERACIONES, RESULTADOS, etc.
 * Mantiene compatibilidad hacia atrás con los formatos de importación de uCharts y Backtesting.
 * Incluye reordenación de pestañas prioritarias, formato condicional y ordenación dinámica por Setup Score.
 */

function normalizeText(text) {
  if (!text) return "";
  return text.toString()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

// Busca una pestaña por nombre normalizado (ignora mayúsculas, acentos y
// espacios extra). getSheetByName() de Apps Script exige coincidencia EXACTA
// de mayúsculas — por eso ss.getSheetByName("REGISTRO_CONTINUO") nunca
// encontraba la pestaña real llamada "Registro Continuo", y la sincronización
// terminaba siempre cayendo en el respaldo "UCharts Compuesto".
function findSheetLoose(ss, name) {
  var target = normalizeText(name).replace(/[_\s]+/g, "");
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    var candidate = normalizeText(sheets[i].getName()).replace(/[_\s]+/g, "");
    if (candidate === target) return sheets[i];
  }
  return null;
}

// Helper para obtener o crear una pestaña con sus encabezados y moverla a su posición prioritaria
function getOrCreateSheet(ss, name, headers) {
  // Fix crítico: antes esto usaba ss.getSheetByName(name) a secas, que exige
  // coincidencia EXACTA de mayúsculas/espacios. Como el resto del sistema
  // llama a esta función con nombres en minúscula o con guiones bajos
  // ("registro continuo", "RADAR_ACTUAL") que no coinciden letra por letra
  // con el nombre real de la pestaña en la planilla ("Registro Continuo",
  // "Radar Actual"), nunca la encontraba y silenciosamente CREABA una
  // pestaña nueva y duplicada cada vez — la automatización escribía ahí, no
  // en la pestaña que el usuario mira. findSheetLoose() ya existía para
  // resolver exactamente este problema en el importador legacy; ahora se usa
  // acá también, en el buscador principal que usan TODAS las pestañas.
  var sheet = findSheetLoose(ss, name);
  if (!sheet) {
    sheet = ss.insertSheet(name);
    // Aplicar estilos a los encabezados
    sheet.appendRow(headers);
    var range = sheet.getRange(1, 1, 1, headers.length);
    range.setFontWeight("bold");
    range.setFontColor("#ffffff");
    range.setBackground("#1f4e78");
    range.setHorizontalAlignment("center");
    sheet.setFrozenRows(1);
    for (var i = 1; i <= headers.length; i++) {
      sheet.autoResizeColumn(i);
    }
  }
  
  // Reordenación automática para poner las pestañas clave a la izquierda del todo
  var priorityOrder = [
    "RESUMEN VISUAL DEL PROYECTO",
    "RADAR_ACTUAL",
    "OPORTUNIDADES_ANTICIPADAS",
    "TORNEO_BOTS",
    "RESULTADOS",
    "OPERACIONES",
    "SETUPS",
    "SEÑALES",
    "EVENTOS_MERCADO"
  ];
  
  var targetIndex = priorityOrder.indexOf(name);
  if (targetIndex !== -1) {
    try {
      ss.setActiveSheet(sheet);
      ss.moveActiveSheet(targetIndex + 1);
    } catch(e) {
      // Silenciar errores de movimiento
    }
  }
  
  return sheet;
}

// Aplicar formato condicional a la pestaña RADAR_ACTUAL de forma robusta
function applyRadarFormatting(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return;
  
  var lastCol = sheet.getLastColumn();
  var range = sheet.getRange(2, 1, lastRow - 1, lastCol);
  var values = range.getValues();
  
  for (var i = 0; i < values.length; i++) {
    var state = values[i][3].toString().toUpperCase(); // Columna D (Estado)
    var score = parseInt(values[i][4]); // Columna E (Setup Score)
    
    var rowRange = sheet.getRange(i + 2, 1, 1, lastCol);
    rowRange.setBackground("#ffffff").setFontColor("#000000").setFontWeight("normal");
    
    var stateCell = sheet.getRange(i + 2, 4);
    var scoreCell = sheet.getRange(i + 2, 5);
    
    // Formato de celdas por estado
    if (state === "CONFIRMADA") {
      stateCell.setBackground("#d4edda").setFontColor("#155724").setFontWeight("bold");
    } else if (state === "INMINENTE") {
      stateCell.setBackground("#fff3cd").setFontColor("#856404").setFontWeight("bold");
    } else if (state === "PRE-ALERTA") {
      stateCell.setBackground("#e2e3e5").setFontColor("#383d41").setFontWeight("bold");
    } else if (state === "INVALIDADA") {
      stateCell.setBackground("#f8d7da").setFontColor("#721c24").setFontWeight("bold");
    }
    
    // Formato de celdas por Setup Score
    if (score >= 80) {
      scoreCell.setBackground("#c3e6cb").setFontColor("#155724").setFontWeight("bold");
    } else if (score >= 50) {
      scoreCell.setBackground("#ffeeba").setFontColor("#856404").setFontWeight("bold");
    } else {
      scoreCell.setBackground("#f5c6cb").setFontColor("#721c24").setFontWeight("bold");
    }
  }
}

// Ordenar la pestaña de radar por Última Actualización (Columna 8) descendente
function sortRadarByScore(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 3) return;
  var range = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  range.sort({column: 8, ascending: false});
}

// Ordenar oportunidades anticipadas por distancia PM40 (Columna 3) ascendente
function sortAnticipadasByDistance(sheet) {
  var lastRow = sheet.getLastRow();
  if (lastRow < 3) return;
  var range = sheet.getRange(2, 1, lastRow - 1, sheet.getLastColumn());
  range.sort({column: 3, ascending: true});
}

// Encabezados completos de "registro continuo": las primeras 9 columnas ya
// existían (datos de la señal confirmada); las 10 siguientes son nuevas y se
// completan solas cuando el bot ejecuta la compra y luego la venta, para que
// dejes de tipear esos datos a mano.
var REGISTRO_CONTINUO_HEADERS = [
  "Fecha/Hora", "Ticker", "Estrategia ID", "Timeframe", "Dirección",
  "Precio Acción", "Distancia PM40", "Setup Score", "Setup ID",
  "Trade ID", "Contratos", "Prima Entrada", "Costo Entrada", "Estado Operación",
  "Fecha Cierre", "Precio Salida", "PnL %", "PnL USD", "Retorno Bruto"
];

// Agrega al final las columnas nuevas que falten en una hoja "registro
// continuo" que ya existía con el set viejo de 9 columnas, sin tocar ni
// reordenar lo que ya hay.
function ensureRegistroContinuoHeaders(sheet) {
  var lastCol = sheet.getLastColumn();
  var currentHeaders = lastCol > 0 ? sheet.getRange(1, 1, 1, lastCol).getValues()[0] : [];
  if (currentHeaders.length >= REGISTRO_CONTINUO_HEADERS.length) return;
  var missing = REGISTRO_CONTINUO_HEADERS.slice(currentHeaders.length);
  var range = sheet.getRange(1, currentHeaders.length + 1, 1, missing.length);
  range.setValues([missing]);
  range.setFontWeight("bold").setFontColor("#ffffff").setBackground("#1f4e78").setHorizontalAlignment("center");
}

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    
    // =========================================================================
    // CASO 1: MODELO RELACIONAL (Payload Extensible de Señales, Setups, Resultados y Torneos)
    // =========================================================================
    if (data.event || data.setup_id || data.webhook_token) {
      return handleRelationalWebhook(ss, data);
    }
    
    // =========================================================================
    // COMPATIBILIDAD HACIA ATRÁS (Legacy)
    // =========================================================================
    if (data.action === "bulk_import" && Array.isArray(data.trades)) {
      return handleLegacyBulkImport(ss, data);
    }
    
    if (data.action === "update_backtest_data") {
      return handleLegacyBacktestUpdate(ss, data);
    }
    
    if (data.action === "update_monitoreo_vivo" && Array.isArray(data.rows)) {
      return handleMonitoreoVivoUpdate(ss, data);
    }

    if (data.action === "update_live_signals" && Array.isArray(data.signals)) {
      return handleLegacyLiveSignalsUpdate(ss, data);
    }
    
    // Operaciones individuales de compra/venta legacy
    return handleLegacyBuySell(ss, data);
    
  } catch (error) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error",
      message: error.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

// -----------------------------------------------------------------------------
// MANEJADOR DEL NUEVO WEBHOOK RELACIONAL
// -----------------------------------------------------------------------------
function handleRelationalWebhook(ss, data) {
  var now = new Date();
  var timestampStr = data.timestamp || Utilities.formatDate(now, ss.getSpreadsheetTimeZone(), "yyyy-MM-dd HH:mm:ss");
  
  var ticker = (data.ticker || "").toUpperCase();
  var timeframe = (data.timeframe || "1H").toUpperCase();
  
  var state = (data.event && data.event.state || data.estado || "OBSERVACION").toUpperCase();
  var setupScore = parseInt(data.event && data.event.setup_score || data.setup_score || 0);
  
  var setupId = data.setup_id;
  var signalId = data.signal_id;
  
  var strategyId = ((data.strategy && data.strategy.id) || data.strategy_id || "PM40_BOUNCE").toUpperCase();
  var strategyVer = ((data.strategy && data.strategy.version) || data.strategy_version || "1.0");
  var direction = ((data.strategy && data.strategy.direction) || data.type || "CALL").toUpperCase();
  
  // Generar IDs si no vienen dados
  var datePart = Utilities.formatDate(now, ss.getSpreadsheetTimeZone(), "yyyyMMdd");
  if (!setupId) {
    setupId = ticker + "_" + timeframe + "_" + strategyId + "_" + datePart + "_001";
  }
  if (!signalId) {
    signalId = "SIG_" + ticker + "_" + datePart + "_" + now.getTime();
  }
  
  var actionPrice = parseFloat(data.market_data && data.market_data.action_price || data.price || 0.0);
  var distancePm40 = parseFloat(data.market_data && data.market_data.indicators && data.market_data.indicators.distance_pm40 || data.distancia_pm40 || 0.0);
  var relativeVol = parseFloat(data.market_data && data.market_data.relative_volume || data.volumen_relativo || 1.0);
  var pm40Slope = parseFloat(data.market_data && data.market_data.indicators && data.market_data.indicators.pm40_slope || 0.0);

  // A. SI EL EVENTO ES UN ACTUALIZADOR DEL TORNEO DE BOTS (Simulación Contrafáctica)
  if (data.event && data.event.action === "tournament_update" && Array.isArray(data.tournament_results)) {
    var torneoSheet = getOrCreateSheet(ss, "TORNEO_BOTS", ["Bot ID", "Estrategia de Salida", "Total Operaciones", "Operaciones Ganadas", "Win Rate %", "Retorno Promedio %", "PnL Acumulado USD"]);
    
    var trData = data.tournament_results;
    for (var j = 0; j < trData.length; j++) {
      var bot = trData[j];
      var botId = bot.bot_id;
      var lastRowT = torneoSheet.getLastRow();
      var botRowIdx = -1;
      
      if (lastRowT > 1) {
        var botIds = torneoSheet.getRange(2, 1, lastRowT - 1, 1).getValues().map(function(r) { return r[0]; });
        var existingBotIdx = botIds.indexOf(botId);
        if (existingBotIdx !== -1) botRowIdx = existingBotIdx + 2;
      }
      
      var rowData = [
        botId,
        bot.strategy_desc,
        bot.total_trades,
        bot.winning_trades,
        bot.win_rate_pct,
        bot.avg_return_pct,
        bot.total_pnl_usd
      ];
      
      if (botRowIdx === -1) {
        torneoSheet.appendRow(rowData);
      } else {
        torneoSheet.getRange(botRowIdx, 1, 1, rowData.length).setValues([rowData]);
      }
    }
    
    // Dar formato visual rápido a la tabla del torneo
    var lastRowT = torneoSheet.getLastRow();
    if (lastRowT > 1) {
      torneoSheet.getRange(2, 1, lastRowT - 1, 7).sort({column: 7, ascending: false});
      
      for (var k = 2; k <= lastRowT; k++) {
        var pnlCell = torneoSheet.getRange(k, 7);
        var pnlVal = parseFloat(pnlCell.getValue());
        if (pnlVal > 0) {
          pnlCell.setBackground("#d4edda").setFontColor("#155724").setFontWeight("bold");
        } else if (pnlVal < 0) {
          pnlCell.setBackground("#f8d7da").setFontColor("#721c24").setFontWeight("bold");
        }
      }
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      message: "Resultados del torneo de bots actualizados con éxito"
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // B. SI EL EVENTO ES UN ACTUALIZADOR DE RESULTADOS
  if (data.event && data.event.action === "result_update" && data.result) {
    var resData = data.result;
    var tradeData = data.trade || {};
    
    // 1. Escribir en OPERACIONES
    var opsSheet = getOrCreateSheet(ss, "OPERACIONES", ["Operación ID", "Ticker", "Símbolo Opción", "Rol Posición", "Cantidad", "Ejecución Compra ID", "Ejecución Venta ID", "Estado"]);
    var opsLastRow = opsSheet.getLastRow();
    var opsRowIdx = -1;
    
    var tradeId = tradeData.trade_id || ("TRD_" + setupId);
    if (opsLastRow > 1) {
      var opIds = opsSheet.getRange(2, 1, opsLastRow - 1, 1).getValues().map(function(r) { return r[0]; });
      var opExistingIdx = opIds.indexOf(tradeId);
      if (opExistingIdx !== -1) opsRowIdx = opExistingIdx + 2;
    }
    
    var opSymbol = tradeData.option_symbol || (ticker + "_SIM_OPT");
    var positionRole = tradeData.position_role || "PRIMARY";
    var opQty = tradeData.qty || 1;
    var opState = tradeData.state || "CLOSED";
    
    if (opsRowIdx === -1) {
      opsSheet.appendRow([tradeId, ticker, opSymbol, positionRole, opQty, "EXE_BUY", "EXE_SELL", opState]);
    } else {
      opsSheet.getRange(opsRowIdx, 8).setValue(opState);
    }
    
    // 2. Escribir en RESULTADOS
    var resultsHeaders = ["Resultado ID", "Operación ID", "Éxito Subyacente", "PnL Opción", "Retorno % Opción", "Duración Horas", "MFE %", "MAE %", "Ret +5m %", "Ret +15m %", "Ret +30m %", "Ret +60m %", "Ret Cierre %"];
    var resSheet = getOrCreateSheet(ss, "RESULTADOS", resultsHeaders);
    var resLastRow = resSheet.getLastRow();
    var resRowIdx = -1;
    
    var resultId = resData.result_id || ("RES_" + tradeId);
    if (resLastRow > 1) {
      var resIds = resSheet.getRange(2, 1, resLastRow - 1, 1).getValues().map(function(r) { return r[0]; });
      var resExistingIdx = resIds.indexOf(resultId);
      if (resExistingIdx !== -1) resRowIdx = resExistingIdx + 2;
    }
    
    var uSuccess = resData.underlying_success !== undefined ? resData.underlying_success : 1;
    var optPnl = resData.option_pnl !== undefined ? resData.option_pnl : 0.0;
    var optRet = resData.option_return_pct !== undefined ? resData.option_return_pct : 0.0;
    var durHours = resData.duration_hours !== undefined ? resData.duration_hours : 0.0;
    
    var mfe = resData.mfe || 0.0;
    var mae = resData.mae || 0.0;
    var r5 = resData.ret_5m || 0.0;
    var r15 = resData.ret_15m || 0.0;
    var r30 = resData.ret_30m || 0.0;
    var r60 = resData.ret_60m || 0.0;
    var rClose = resData.ret_close || 0.0;
    
    var rowData = [
      resultId,
      tradeId,
      uSuccess,
      optPnl,
      optRet,
      durHours,
      mfe,
      mae,
      r5,
      r15,
      r30,
      r60,
      rClose
    ];
    
    if (resRowIdx === -1) {
      resSheet.appendRow(rowData);
    } else {
      resSheet.getRange(resRowIdx, 1, 1, rowData.length).setValues([rowData]);
    }
    
    // También actualizar estado en setups si corresponde
    var setupsSheet = getOrCreateSheet(ss, "SETUPS", ["Setup ID", "Ticker", "Estrategia ID", "Timeframe", "Estado", "Fecha Creación", "Fecha Confirmación", "Fecha Invalidación", "Setup Score"]);
    var setupsLastRow = setupsSheet.getLastRow();
    if (setupsLastRow > 1) {
      var setupIds = setupsSheet.getRange(2, 1, setupsLastRow - 1, 1).getValues().map(function(r) { return r[0]; });
      var setupIdx = setupIds.indexOf(setupId);
      if (setupIdx !== -1) {
        setupsSheet.getRange(setupIdx + 2, 5).setValue("FINALIZADA");
      }
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      message: "Resultados actualizados en Sheets con éxito",
      setup_id: setupId,
      result_id: resultId
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // B2. SI EL EVENTO ES UNA ACTUALIZACIÓN DE PNL EN VIVO
  if (data.event && data.event.action === "live_pnl_update" && data.position) {
    var posData = data.position;
    var liveSheet = getOrCreateSheet(ss, "POSICIONES_VIVO", [
      "Operación ID", "Ticker", "Tipo", "Estrategia", "Cantidad", 
      "Precio Entrada", "Precio Actual Subyacente", "Variación % Subyacente", 
      "PnL Estimado %", "PnL Estimado USD", "Estado", "Última Actualización"
    ]);
    
    var liveLastRow = liveSheet.getLastRow();
    var liveRowIdx = -1;
    var tradeId = posData.trade_id;
    
    if (liveLastRow > 1) {
      var liveIds = liveSheet.getRange(2, 1, liveLastRow - 1, 1).getValues().map(function(r) { return r[0]; });
      var liveExistingIdx = liveIds.indexOf(tradeId);
      if (liveExistingIdx !== -1) liveRowIdx = liveExistingIdx + 2;
    }
    
    // Si la posición está CERRADA, la eliminamos de la pestaña de en vivo
    if (posData.state === "CLOSED") {
      if (liveRowIdx !== -1) {
        liveSheet.deleteRow(liveRowIdx);
      }
      return ContentService.createTextOutput(JSON.stringify({
        status: "success",
        message: "Posición cerrada eliminada de POSICIONES_VIVO"
      })).setMimeType(ContentService.MimeType.JSON);
    }
    
    var posRowData = [
      tradeId,
      posData.ticker,
      posData.direction,
      posData.strategy_id,
      posData.qty,
      posData.entry_price,
      posData.current_price,
      posData.underlying_change_pct,
      posData.option_pnl_pct,
      posData.pnl_usd,
      posData.state,
      posData.last_update
    ];
    
    if (liveRowIdx === -1) {
      liveSheet.appendRow(posRowData);
      var newRow = liveSheet.getLastRow();
      liveSheet.getRange(newRow, 1, 1, posRowData.length).setFontColor("#e5e7eb");
      liveSheet.getRange(newRow, 8).setNumberFormat("0.00'%'");
      liveSheet.getRange(newRow, 9).setNumberFormat("0.00'%'");
      liveSheet.getRange(newRow, 10).setNumberFormat("$#,##0.00");
      
      var pnlVal = posData.option_pnl_pct;
      var color = pnlVal > 0 ? "#10b981" : (pnlVal < 0 ? "#ef4444" : "#e5e7eb");
      liveSheet.getRange(newRow, 9, 1, 2).setFontColor(color).setFontWeight("bold");
    } else {
      liveSheet.getRange(liveRowIdx, 1, 1, posRowData.length).setValues([posRowData]);
      var pnlVal = posData.option_pnl_pct;
      var color = pnlVal > 0 ? "#10b981" : (pnlVal < 0 ? "#ef4444" : "#e5e7eb");
      liveSheet.getRange(liveRowIdx, 9, 1, 2).setFontColor(color).setFontWeight("bold");
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      message: "Posición en vivo actualizada en Sheets",
      trade_id: tradeId
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // B3/B4. DESACTIVADO — el bot ya no escribe fills/cierres directamente en
  // Registro Continuo. Esta rama usaba columnas I-S con un esquema propio
  // (Trade ID, contratos, prima, costo...) que no existe en la hoja real:
  // ahí las columnas I/J/K/L son Saldo USD/% Ganancia/Estado/Take Profit
  // Objetivo, y O-S es la tabla resumen (Win Rate, Total Trades, etc.) — se
  // estaban pisando ambas cosas en cada compra/venta del bot. Registro
  // Continuo ahora se llena únicamente desde el historial real de uCharts
  // (handleLegacyBulkImport). Se responde "success" sin tocar ninguna hoja
  // para que el bot (live_scanner.py) no vea errores por este evento.
  if (data.event && (data.event.action === "trade_fill" || data.event.action === "trade_close")) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "success",
      message: "Evento recibido (registro en Sheets desactivado; Registro Continuo se sincroniza desde uCharts)"
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // C. SI ES UNA SEÑAL REGULAR (PRE-ALERTA, CONFIRMADA, ETC.)
  // 1. Registrar la SEÑAL en bruto
  var senalesSheet = getOrCreateSheet(ss, "SEÑALES", ["Señal ID", "Fecha/Hora", "Ticker", "Dirección", "Estrategia ID", "Versión", "Payload Completo"]);
  var duplicateSignal = false;
  var lastRow = senalesSheet.getLastRow();
  if (lastRow > 1) {
    var checkRange = Math.max(1, lastRow - 50);
    var existingIds = senalesSheet.getRange(checkRange, 1, (lastRow - checkRange) + 1, 1).getValues().map(function(r) { return r[0]; });
    if (existingIds.indexOf(signalId) !== -1) {
      duplicateSignal = true;
    }
  }
  
  if (!duplicateSignal) {
    senalesSheet.appendRow([
      signalId,
      timestampStr,
      ticker,
      direction,
      strategyId,
      strategyVer,
      JSON.stringify(data)
    ]);
  }
  
  // 2. Crear o Actualizar el SETUP (Ciclo de Vida)
  var setupsSheet = getOrCreateSheet(ss, "SETUPS", ["Setup ID", "Ticker", "Estrategia ID", "Timeframe", "Estado", "Fecha Creación", "Fecha Confirmación", "Fecha Invalidación", "Setup Score"]);
  var setupsLastRow = setupsSheet.getLastRow();
  var setupRowIdx = -1;
  
  if (setupsLastRow > 1) {
    var setupIds = setupsSheet.getRange(2, 1, setupsLastRow - 1, 1).getValues().map(function(r) { return r[0]; });
    var existingIdx = setupIds.indexOf(setupId);
    if (existingIdx !== -1) {
      setupRowIdx = existingIdx + 2;
    }
  }
  
  if (setupRowIdx === -1) {
    var confirmationTime = (state === "CONFIRMADA") ? timestampStr : "";
    var invalidationTime = (state === "INVALIDADA") ? timestampStr : "";
    
    setupsSheet.appendRow([
      setupId,
      ticker,
      strategyId,
      timeframe,
      state,
      timestampStr,
      confirmationTime,
      invalidationTime,
      setupScore
    ]);
  } else {
    setupsSheet.getRange(setupRowIdx, 5).setValue(state);
    setupsSheet.getRange(setupRowIdx, 9).setValue(setupScore);
    
    if (state === "CONFIRMADA" && setupsSheet.getRange(setupRowIdx, 7).getValue() === "") {
      setupsSheet.getRange(setupRowIdx, 7).setValue(timestampStr);
    }
    if (state === "INVALIDADA" && setupsSheet.getRange(setupRowIdx, 8).getValue() === "") {
      setupsSheet.getRange(setupRowIdx, 8).setValue(timestampStr);
    }
  }
  
  // 3. Crear o Actualizar el RADAR en Vivo
  var radarSheet = getOrCreateSheet(ss, "RADAR_ACTUAL", ["Ticker", "Estrategia ID", "Timeframe", "Estado", "Setup Score", "Precio Acción", "Distancia PM40", "Última Actualización"]);
  var radarLastRow = radarSheet.getLastRow();
  var radarRowIdx = -1;
  
  if (radarLastRow > 1) {
    var radarKeys = radarSheet.getRange(2, 1, radarLastRow - 1, 3).getValues().map(function(r) {
      return r[0] + "||" + r[1] + "||" + r[2];
    });
    var currentKey = ticker + "||" + strategyId + "||" + timeframe;
    var existingRadarIdx = radarKeys.indexOf(currentKey);
    if (existingRadarIdx !== -1) {
      radarRowIdx = existingRadarIdx + 2;
    }
  }
  
  if (radarRowIdx === -1) {
    radarSheet.appendRow([
      ticker,
      strategyId,
      timeframe,
      state,
      setupScore,
      actionPrice,
      distancePm40,
      timestampStr
    ]);
  } else {
    radarSheet.getRange(radarRowIdx, 4).setValue(state);
    radarSheet.getRange(radarRowIdx, 5).setValue(setupScore);
    radarSheet.getRange(radarRowIdx, 6).setValue(actionPrice);
    radarSheet.getRange(radarRowIdx, 7).setValue(distancePm40);
    radarSheet.getRange(radarRowIdx, 8).setValue(timestampStr);
  }
  
  // 4. Registrar en OPORTUNIDADES_ANTICIPADAS si es Pre-Alerta / Inminente
  if (state === "PRE-ALERTA" || state === "INMINENTE") {
    var anticipadasSheet = getOrCreateSheet(ss, "OPORTUNIDADES_ANTICIPADAS", ["Setup ID", "Fecha/Hora", "Distancia PM40", "Velocidad Aproximación", "Pendiente PM40", "Volumen Relativo"]);
    anticipadasSheet.appendRow([
      setupId,
      timestampStr,
      distancePm40,
      0.0,
      pm40Slope,
      relativeVol
    ]);
  }
  
  // 4b. DESACTIVADO — Registro Continuo ya NO se carga desde señales
  // CONFIRMADA. Esta rama escribía un esquema de 19 columnas inventado que
  // no coincide con las columnas reales de la hoja manual "Registro
  // Continuo" (Fecha, Trade #, Ticker, Call/Put, Cantidad, Compra, Venta,
  // Saldo USD, % Ganancia, Estado, Take Profit Objetivo, Fecha de
  // Expiración) y que además pisaba, por columna, la tabla resumen
  // (Win Rate / Total Trades / etc.) que vive aparte en las columnas O-S de
  // esa misma hoja. La fuente de verdad de Registro Continuo ahora es
  // exclusivamente el importador de historial real de uCharts
  // (ver handleLegacyBulkImport), que sí respeta esas columnas y deja que
  // la propia planilla calcule Saldo/% Ganancia/Estado con fórmulas.
  
  // 5. Registrar Eventos de Mercado
  if (data.market_data && data.market_data.indicators) {
    var eventosSheet = getOrCreateSheet(ss, "EVENTOS_MERCADO", ["Fecha/Hora", "Tendencia SPY", "Valor VIX", "Sesión Mercado"]);
    var vixVal = parseFloat(data.market_data.indicators.vix_value || 0.0);
    var spyTrend = data.market_data.indicators.spy_daily_trend || "UNKNOWN";
    var sessionType = data.market_data.market_session || "RTH";
    
    eventosSheet.appendRow([
      timestampStr,
      spyTrend,
      vixVal,
      sessionType
    ]);
  }

  // C. ORDENACIÓN Y FORMATO EN VIVO AL FINAL DEL ESCANEO
  if (state === "PRE-ALERTA" || state === "INMINENTE") {
    var anticipadasSheet = findSheetLoose(ss, "OPORTUNIDADES_ANTICIPADAS");
    if (anticipadasSheet) sortAnticipadasByDistance(anticipadasSheet);
  }
  
  var rSheet = findSheetLoose(ss, "RADAR_ACTUAL");
  if (rSheet) {
    sortRadarByScore(rSheet);
    applyRadarFormatting(rSheet);
  }
  
  return ContentService.createTextOutput(JSON.stringify({
    status: "success",
    message: "Webhook relacional procesado",
    setup_id: setupId,
    state: state
  })).setMimeType(ContentService.MimeType.JSON);
}

// REPARACIÓN DE UNA SOLA VEZ para las filas que ya quedaron con fórmulas
// rotas (=SI(O(...))) antes de este fix. No se llama nunca desde el
// webhook: hay que abrir este archivo en el editor de Apps Script
// (script.google.com, o Extensiones > Apps Script desde la planilla),
// elegir esta función "repairAllRegistroContinuoFormulas" en el desplegable
// de al lado del botón ▷ Ejecutar, y ejecutarla una vez. Reescribe Saldo
// USD / % Ganancia / Estado en TODAS las filas con Ticker no vacío,
// siempre en inglés (IF/OR/coma), que es lo único que Range.setFormula()
// acepta sin romperse — ver el comentario grande en applyFormulas() más
// abajo para el detalle de por qué. No hace falta volver a desplegar el
// webhook para correr esto: ejecutar una función a mano en el editor no
// depende de la implementación web publicada.
function repairAllRegistroContinuoFormulas() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = findSheetLoose(ss, "Registro Continuo") || findSheetLoose(ss, "UCharts Compuesto") || ss.getActiveSheet();
  var lastColumn = sheet.getLastColumn() || 20;

  var headerRowIdx = 1;
  var headers = [];
  for (var r = 1; r <= 15; r++) {
    var rowValues = sheet.getRange(r, 1, 1, lastColumn).getValues()[0];
    var tickerIndex = rowValues.map(function(val) { return normalizeText(val); }).indexOf("ticker");
    if (tickerIndex === -1) tickerIndex = rowValues.map(function(val) { return normalizeText(val); }).indexOf("tiker");
    if (tickerIndex !== -1) {
      headerRowIdx = r;
      headers = rowValues.map(function(h) { return h.toString().trim(); });
      break;
    }
  }
  if (headers.length === 0) {
    Logger.log("No se encontró la fila de encabezados (columna 'Ticker') en '" + sheet.getName() + "'.");
    return;
  }

  var normalizedHeaders = headers.map(function(h) { return normalizeText(h); });
  function getColIdx(name) {
    var idx = normalizedHeaders.indexOf(normalizeText(name));
    return idx !== -1 ? idx + 1 : -1;
  }
  var colTicker = getColIdx("ticker") !== -1 ? getColIdx("ticker") : getColIdx("tiker");
  var colCompra = getColIdx("compra") !== -1 ? getColIdx("compra") : getColIdx("prima compra");
  var colVenta = getColIdx("venta") !== -1 ? getColIdx("venta") : getColIdx("prima venta real");
  var colSaldo = getColIdx("saldo usd") !== -1 ? getColIdx("saldo usd") : getColIdx("saldo");
  var colPctGanancia = getColIdx("% ganancia") !== -1 ? getColIdx("% ganancia") : getColIdx("porcentaje ganancia");
  var colEstado = getColIdx("estado");

  // Mismo criterio que applyFormulas() en handleLegacyBulkImport (ver el
  // comentario grande ahí): nombres de función siempre en inglés, separador
  // de argumentos ";" cuando el locale de la planilla usa coma decimal
  // (como España — confirmado en vivo: con "," tiraba "Error de análisis de
  // fórmula", con ";" calculó bien). La corrida anterior de esta función
  // (30/8, 4:59) reparó 292 filas usando coma — con el locale de esta
  // planilla eso las dejó en #ERROR!, por eso hay que volver a correrla.
  var _locale = (ss.getSpreadsheetLocale() || "en_US").toLowerCase();
  var _periodDecimalLocales = ["en_us","en_gb","en_ca","en_au","en_ie","en_nz","en_za","en_ph","en_in","zh_cn","zh_tw","zh_hk","ja_jp","ko_kr","th_th"];
  var _usesCommaDecimal = _periodDecimalLocales.indexOf(_locale) === -1;
  var F_SEP = _usesCommaDecimal ? ";" : ",";

  function columnToLetter(col) {
    var letter = "";
    while (col > 0) {
      var rem = (col - 1) % 26;
      letter = String.fromCharCode(65 + rem) + letter;
      col = Math.floor((col - 1) / 26);
    }
    return letter;
  }

  function applyFormulasFixed(rowNum) {
    if (colSaldo !== -1 && colVenta !== -1 && colCompra !== -1) {
      var ventaRef = columnToLetter(colVenta) + rowNum;
      var compraRef = columnToLetter(colCompra) + rowNum;
      sheet.getRange(rowNum, colSaldo).setFormula(
        "=IF(OR(" + ventaRef + "=\"\"" + F_SEP + compraRef + "=\"\")" + F_SEP + "\"\"" + F_SEP + ventaRef + "-" + compraRef + ")"
      );
    }
    if (colPctGanancia !== -1 && colSaldo !== -1 && colCompra !== -1) {
      var saldoRef = columnToLetter(colSaldo) + rowNum;
      var compraRef2 = columnToLetter(colCompra) + rowNum;
      sheet.getRange(rowNum, colPctGanancia).setFormula(
        "=IF(OR(" + saldoRef + "=\"\"" + F_SEP + compraRef2 + "=0)" + F_SEP + "\"\"" + F_SEP + saldoRef + "/" + compraRef2 + ")"
      );
    }
    if (colEstado !== -1 && colVenta !== -1 && colSaldo !== -1) {
      var ventaRef2 = columnToLetter(colVenta) + rowNum;
      var saldoRef2 = columnToLetter(colSaldo) + rowNum;
      sheet.getRange(rowNum, colEstado).setFormula(
        "=IF(" + ventaRef2 + "=\"\"" + F_SEP + "\"Abierto\"" + F_SEP + "IF(" + saldoRef2 + ">0" + F_SEP + "\"Ganado\"" + F_SEP + "IF(" + saldoRef2 + "<0" + F_SEP + "\"Perdido\"" + F_SEP + "\"Empate\")))"
      );
    }
  }

  var lastRow = sheet.getLastRow();
  var fixedCount = 0;
  for (var rowNum = headerRowIdx + 1; rowNum <= lastRow; rowNum++) {
    var tickerVal = colTicker !== -1 ? sheet.getRange(rowNum, colTicker).getValue() : "";
    if (!tickerVal) continue; // fila vacía (o solo del tablero O-S), no tocar
    applyFormulasFixed(rowNum);
    fixedCount++;
  }
  Logger.log("Fórmulas reparadas en " + fixedCount + " filas de '" + sheet.getName() + "'.");
}

function handleLegacyBulkImport(ss, data) {
  var sheet = findSheetLoose(ss, "Registro Continuo")
           || findSheetLoose(ss, "UCharts Compuesto")
           || ss.getActiveSheet();
           
  var headerRowIdx = 1; // default
  var headers = [];
  var lastColumn = sheet.getLastColumn() || 20;
  
  // Buscar la fila de cabecera que contenga "Ticker"
  for (var r = 1; r <= 15; r++) {
    var rowValues = sheet.getRange(r, 1, 1, lastColumn).getValues()[0];
    var tickerIndex = rowValues.map(function(val) { return normalizeText(val); }).indexOf("ticker");
    if (tickerIndex === -1) {
      tickerIndex = rowValues.map(function(val) { return normalizeText(val); }).indexOf("tiker");
    }
    if (tickerIndex !== -1) {
      headerRowIdx = r;
      headers = rowValues.map(function(h) { return h.toString().trim(); });
      break;
    }
  }
  
  if (headers.length === 0) {
    // Si no tiene cabeceras inicializadas en absoluto (hoja nueva), crearlas
    headers = ["°", "Fecha", "Trade #", "Ticker", "Call/Put", "Cantidad", "Compra", "Venta", "Saldo USD", "% Ganancia", "Estado", "Take Profit Objetivo", "Fecha de Expiración"];
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    headerRowIdx = 1;
  }

  var normalizedHeaders = headers.map(function(h) { return normalizeText(h); });
  
  function getColIdx(name) {
    var idx = normalizedHeaders.indexOf(normalizeText(name));
    return idx !== -1 ? idx + 1 : -1;
  }
  
  var colIndex = getColIdx("°");
  // FIX (10/09): la hoja real usa columnas SEPARADAS "Fecha Compra"/"Fecha
  // Venta" y "Trade # Compra"/"Trade # Venta" — nunca "Fecha"/"Trade #" a
  // secas. getColIdx("fecha") y getColIdx("trade #") devolvían SIEMPRE -1,
  // así que en cada fila nueva estas dos columnas quedaban en blanco para
  // siempre (Ticker/Compra/Venta sí se cargaban bien).
  var colFechaCompra = getColIdx("fecha compra") !== -1 ? getColIdx("fecha compra") : getColIdx("fecha");
  var colFechaVenta = getColIdx("fecha venta");
  var colTradeCompra = getColIdx("trade # compra") !== -1 ? getColIdx("trade # compra") : (getColIdx("trade #") !== -1 ? getColIdx("trade #") : getColIdx("trade"));
  var colTradeVenta = getColIdx("trade # venta");
  // Alias que usa el resto de la función (deduplicación por fecha de
  // COMPRA, que es la que identifica la fila).
  var colFecha = colFechaCompra;
  var colTradeNum = colTradeCompra;
  var colTicker = getColIdx("ticker") !== -1 ? getColIdx("ticker") : getColIdx("tiker");
  var colCallPut = getColIdx("call/put") !== -1 ? getColIdx("call/put") : (getColIdx("tipo") !== -1 ? getColIdx("tipo") : getColIdx("call o put"));
  var colCantidad = getColIdx("cantidad");
  var colCompra = getColIdx("compra") !== -1 ? getColIdx("compra") : getColIdx("prima compra");
  var colVenta = getColIdx("venta") !== -1 ? getColIdx("venta") : getColIdx("prima venta real");
  var colSaldo = getColIdx("saldo usd") !== -1 ? getColIdx("saldo usd") : getColIdx("saldo");
  var colPctGanancia = getColIdx("% ganancia") !== -1 ? getColIdx("% ganancia") : getColIdx("porcentaje ganancia");
  var colEstado = getColIdx("estado");
  var colTPObj = getColIdx("take profit objetivo") !== -1 ? getColIdx("take profit objetivo") : getColIdx("tp objetivo");
  var colExpiracion = getColIdx("fecha de expiración") !== -1 ? getColIdx("fecha de expiración") : getColIdx("vencimiento");
  
  // Garantizar índices mínimos si no existen columnas
  if (colTicker === -1) colTicker = 4;
  if (colCantidad === -1) colCantidad = 6;
  if (colCompra === -1) colCompra = 7;
  if (colEstado === -1) colEstado = 11;

  // Convierte una celda "Fecha" (objeto Date o texto) a "yyyy-MM-dd" sin
  // importar el formato de origen. FIX: antes, las fechas nuevas que llegan
  // de uCharts como texto "DD/MM/YYYY hh:mm:ss" se comparaban tal cual contra
  // fechas ya guardadas como objeto Date formateadas "yyyy-MM-dd" — nunca
  // coincidían, así que la deduplicación fallaba siempre y cada
  // sincronización volvía a insertar TODO el historial de nuevo, duplicando
  // filas en cada corrida. Con esta normalización ambos lados quedan en el
  // mismo formato antes de compararse.
  function normalizeDateKey(value) {
    if (value instanceof Date) {
      return Utilities.formatDate(value, ss.getSpreadsheetTimeZone(), "yyyy-MM-dd");
    }
    var datePart = String(value || "").trim().split(" ")[0].trim();
    if (!datePart) return "";
    var dmy = datePart.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
    if (dmy) {
      return dmy[3] + "-" + ("0" + dmy[2]).slice(-2) + "-" + ("0" + dmy[1]).slice(-2);
    }
    var ymd = datePart.match(/^(\d{4})[\/-](\d{1,2})[\/-](\d{1,2})$/);
    if (ymd) {
      return ymd[1] + "-" + ("0" + ymd[2]).slice(-2) + "-" + ("0" + ymd[3]).slice(-2);
    }
    return datePart;
  }

  // Convierte un índice de columna (1 = A, 2 = B, ...) a su letra A1, para
  // poder armar fórmulas dinámicamente según dónde esté cada columna real.
  function columnToLetter(col) {
    var letter = "";
    while (col > 0) {
      var rem = (col - 1) % 26;
      letter = String.fromCharCode(65 + rem) + letter;
      col = Math.floor((col - 1) / 26);
    }
    return letter;
  }

  // Carga en Saldo USD / % Ganancia / Estado FÓRMULAS reales de la planilla
  // (no valores calculados por este script) para que sea la hoja la que
  // calcule todo a partir de Compra y Venta, tal como se pidió: la
  // automatización solo aporta los hechos crudos (fecha, ticker, cantidad,
  // compra, venta); el resto lo calcula la planilla sola y se recalcula
  // solo si alguna vez se corrige Compra/Venta a mano.
  // FIX #NAME?/#ERROR! real (segunda vuelta — el primer intento seguía mal):
  // hay DOS reglas independientes en juego, no una sola de "locale sí/no":
  //   1) Range.setFormula() exige nombres de función en INGLÉS siempre
  //      (IF/OR), nunca SI/O — probado en vivo: con SI/O la celda tiraba
  //      "Función desconocida: SI".
  //   2) El separador de argumentos depende de si el locale de la planilla
  //      usa COMA como separador decimal (como España: "$13.990,00"). En
  //      esos locales Sheets exige PUNTO Y COMA como separador de
  //      argumentos — con coma tira "Error de análisis de fórmula", porque
  //      la coma se confunde con el separador decimal. Esto se confirmó
  //      escribiendo a mano en la hoja: "=IF(OR(H2=\"\";G2=\"\");\"\";H2-G2)"
  //      (inglés + punto y coma) calculó bien y Sheets lo mostró traducido
  //      como SI/O; la misma fórmula con comas dio error de nuevo.
  // Conclusión: SIEMPRE nombres en inglés, separador según si el locale usa
  // coma decimal (la inmensa mayoría fuera de en/zh/ja/ko/th).
  var _locale = (ss.getSpreadsheetLocale() || "en_US").toLowerCase();
  var _periodDecimalLocales = ["en_us","en_gb","en_ca","en_au","en_ie","en_nz","en_za","en_ph","en_in","zh_cn","zh_tw","zh_hk","ja_jp","ko_kr","th_th"];
  var _usesCommaDecimal = _periodDecimalLocales.indexOf(_locale) === -1;
  var F_IF = "IF";
  var F_OR = "OR";
  var F_SEP = _usesCommaDecimal ? ";" : ",";

  function applyFormulas(rowNum) {
    if (colSaldo !== -1 && colVenta !== -1 && colCompra !== -1) {
      var ventaRef = columnToLetter(colVenta) + rowNum;
      var compraRef = columnToLetter(colCompra) + rowNum;
      sheet.getRange(rowNum, colSaldo).setFormula(
        "=" + F_IF + "(" + F_OR + "(" + ventaRef + "=\"\"" + F_SEP + compraRef + "=\"\")" + F_SEP + "\"\"" + F_SEP + ventaRef + "-" + compraRef + ")"
      );
    }
    if (colPctGanancia !== -1 && colSaldo !== -1 && colCompra !== -1) {
      var saldoRef = columnToLetter(colSaldo) + rowNum;
      var compraRef2 = columnToLetter(colCompra) + rowNum;
      sheet.getRange(rowNum, colPctGanancia).setFormula(
        "=" + F_IF + "(" + F_OR + "(" + saldoRef + "=\"\"" + F_SEP + compraRef2 + "=0)" + F_SEP + "\"\"" + F_SEP + saldoRef + "/" + compraRef2 + ")"
      );
    }
    if (colEstado !== -1 && colVenta !== -1 && colSaldo !== -1) {
      var ventaRef2 = columnToLetter(colVenta) + rowNum;
      var saldoRef2 = columnToLetter(colSaldo) + rowNum;
      sheet.getRange(rowNum, colEstado).setFormula(
        "=" + F_IF + "(" + ventaRef2 + "=\"\"" + F_SEP + "\"Abierto\"" + F_SEP + F_IF + "(" + saldoRef2 + ">0" + F_SEP + "\"Ganado\"" + F_SEP + F_IF + "(" + saldoRef2 + "<0" + F_SEP + "\"Perdido\"" + F_SEP + "\"Empate\")))"
      );
    }
  }

  var lastRow = sheet.getLastRow();
  
  // Leer registros existentes para deduplicación
  var dataRangeValues = [];
  if (lastRow > headerRowIdx) {
    dataRangeValues = sheet.getRange(headerRowIdx + 1, 1, lastRow - headerRowIdx, headers.length).getValues();
  }
  
  var rowMap = {};
  // FIX (Compra/Venta en $0 en filas nuevas): la clave de rowMap de arriba
  // exige que coincidan ticker+tipo+cantidad+PRECIO DE COMPRA+FECHA DE
  // COMPRA. Cuando el Tampermonkey manda una venta/vencimiento "huérfano"
  // (sin haber podido emparejar su compra del lado del navegador — ver el
  // fix de persistencia en ucharts_sync_userscript.js), ese trade llega acá
  // con buyPrice=0 y buyDate="", así que NUNCA calza con esa clave, aunque
  // la fila "Abierto" real de esa misma posición ya esté cargada en la
  // planilla. Este segundo mapa (más flexible: ticker+tipo+cantidad+
  // vencimiento, ignorando precio/fecha de compra) sirve de red de
  // seguridad para encontrar esa fila "Abierto" igual y actualizarle la
  // Venta, en vez de insertar una fila nueva con Compra Y Venta en $0.
  // NOTA: la clave de este mapa NO incluye el vencimiento a propósito —
  // "Fecha de Expiración" puede llegar en formatos de 2 dígitos de año
  // ("DD/MM/YY" o "YY/MM/DD" según el texto original de UCharts) que
  // normalizeDateKey no sabe normalizar de forma fiable, y encima Sheets
  // suele autoconvertir esa celda a un objeto Date propio con su propia
  // interpretación de esos dígitos ambiguos — comparar por ese campo
  // fallaría en silencio la mayoría de las veces. Ticker+tipo+cantidad ya
  // alcanza en la práctica (una sola cuenta, pocas posiciones abiertas a la
  // vez); si hubiera más de una posición idéntica abierta, se cierra la
  // más vieja primero (FIFO), que es el criterio contable correcto igual.
  var openFallbackMap = {};
  for (var i = 0; i < dataRangeValues.length; i++) {
    var row = dataRangeValues[i];
    var rowNum = headerRowIdx + 1 + i;
    
    var exFecha = colFecha !== -1 ? row[colFecha - 1] : "";
    var exTicker = colTicker !== -1 ? String(row[colTicker - 1] || "").toUpperCase().trim() : "";
    var exCallPut = colCallPut !== -1 ? String(row[colCallPut - 1] || "").toUpperCase().trim() : "";
    var exQty = colCantidad !== -1 ? parseInt(row[colCantidad - 1]) || 0 : 0;
    var exCompra = colCompra !== -1 ? parseFloat(row[colCompra - 1]) || 0.0 : 0.0;
    var exEstado = colEstado !== -1 ? String(row[colEstado - 1] || "").toUpperCase().trim() : "";
    
    // Normalizar fecha de la fila (ver normalizeDateKey más arriba)
    var dateStr = normalizeDateKey(exFecha);
    
    // Generar clave única para evitar duplicados
    var key = exTicker + "||" + exCallPut + "||" + exQty + "||" + exCompra.toFixed(2) + "||" + dateStr;
    rowMap[key] = {
      rowNum: rowNum,
      estado: exEstado,
      ventaVal: colVenta !== -1 ? parseFloat(row[colVenta - 1]) || 0.0 : 0.0
    };

    // Sólo entran al mapa de respaldo las filas todavía ABIERTAS: una fila
    // ya Cerrada no debería recibir una segunda venta.
    if (exEstado === "ABIERTO" || exEstado === "OPEN") {
      var fallbackKey = exTicker + "||" + exCallPut + "||" + exQty;
      // Si hay más de una posición abierta idéntica (mismo ticker/tipo/
      // cantidad/vencimiento), preferimos la más vieja (menor rowNum de
      // inserción original = mayor rowNum actual, porque se inserta al
      // tope) para no romper el orden FIFO de cierre.
      if (!openFallbackMap[fallbackKey] || rowNum > openFallbackMap[fallbackKey].rowNum) {
        openFallbackMap[fallbackKey] = {
          rowNum: rowNum,
          estado: exEstado,
          ventaVal: colVenta !== -1 ? parseFloat(row[colVenta - 1]) || 0.0 : 0.0
        };
      }
    }
  }
  
  var addedCount = 0;
  var updatedCount = 0;
  var skippedCount = 0;
  var skippedDetails = [];
  var trades = data.trades || [];
  // Cada inserción nueva (siempre en headerRowIdx+1) corre una posición hacia
  // abajo a TODAS las filas existentes que ya estaban cacheadas en rowMap con
  // su rowNum de antes de empezar. Sin este contador, una actualización a una
  // fila existente (p.ej. marcar una venta) apuntaría a la fila equivocada
  // apenas se insertara una fila nueva antes en el mismo lote.
  var insertedSoFar = 0;
  
  for (var j = 0; j < trades.length; j++) {
    var t = trades[j];
    var tTicker = String(t.ticker || "").toUpperCase().trim();
    var tType = String(t.type || t.direction || "CALL").toUpperCase().trim();
    var tQty = parseInt(t.quantity || t.qty) || 0;
    var tBuyPrice = parseFloat(t.buyPrice || t.price || t.entry_price) || 0.0;
    var tSellPrice = parseFloat(t.sellPrice || t.exit_price) || 0.0;
    var tStatus = String(t.status || t.state || "Cerrado").toUpperCase().trim();
    
    // Normalizar fecha del webhook (buyDate suele venir como "DD/MM/YYYY hh:mm:ss")
    var tBuyDateStr = normalizeDateKey(t.buyDate || t.date || "");
    
    var key = tTicker + "||" + tType + "||" + tQty + "||" + tBuyPrice.toFixed(2) + "||" + tBuyDateStr;
    var exRecord = rowMap[key];

    // Red de seguridad (ver comentario junto a openFallbackMap más arriba):
    // si esta venta/vencimiento llega "huérfana" (sin compra emparejada del
    // lado del navegador, buyPrice=0 o sin fecha de compra) y no calzó con
    // ninguna fila por la clave exacta, buscamos si ya existe una fila
    // ABIERTA con el mismo ticker+tipo+cantidad y la actualizamos a Cerrado
    // en vez de insertar una fila nueva con Compra Y Venta en $0 (el bug
    // reportado: filas sin datos reales que no sirven para calcular ni
    // identificar el trade).
    var isClosingEvent = (tStatus === "CERRADO" || tStatus === "CLOSED");
    var looksOrphan = (tBuyPrice === 0 || !tBuyDateStr);
    if (!exRecord && isClosingEvent && looksOrphan) {
      var fallbackKey = tTicker + "||" + tType + "||" + tQty;
      var fallbackRecord = openFallbackMap[fallbackKey];
      if (fallbackRecord) {
        exRecord = fallbackRecord;
        delete openFallbackMap[fallbackKey]; // no reusar la misma fila abierta dos veces en este mismo lote
      }
    }
    
    if (exRecord) {
      // Corregir la fila real: puede haberse corrido hacia abajo por
      // inserciones nuevas hechas antes, en este mismo lote.
      var realRowNum = exRecord.rowNum + insertedSoFar;
      // Si la transacción ya existe pero pasó de Abierto a Cerrado, actualizamos el precio de salida
      if ((exRecord.estado === "ABIERTO" || exRecord.estado === "OPEN") && (tStatus === "CERRADO" || tStatus === "CLOSED")) {
        if (colVenta !== -1) {
          sheet.getRange(realRowNum, colVenta).setValue(tSellPrice);
        }
        // FIX (10/09): completar Fecha Venta / Trade # Venta al cerrar —
        // antes quedaban en blanco porque el script nunca las escribía.
        if (colFechaVenta !== -1) {
          sheet.getRange(realRowNum, colFechaVenta).setValue(t.sellDate || "");
        }
        if (colTradeVenta !== -1 && colTradeCompra !== -1) {
          var existingTradeNum = sheet.getRange(realRowNum, colTradeCompra).getValue();
          sheet.getRange(realRowNum, colTradeVenta).setValue(existingTradeNum);
        }
        // Saldo USD / % Ganancia / Estado los recalcula la planilla sola
        // (fórmulas), no este script.
        applyFormulas(realRowNum);
        updatedCount++;
      }
    } else if (isClosingEvent && looksOrphan) {
      // Ni la clave exacta ni el mapa de respaldo encontraron una fila
      // "Abierto" real para esta venta/vencimiento huérfano. NO insertamos
      // una fila nueva con Compra Y Venta en $0 (el bug reportado: una fila
      // así no sirve para identificar ni calcular el trade) — se descarta
      // y queda registrada acá para que se pueda revisar a mano.
      skippedCount++;
      skippedDetails.push(tTicker + " " + tType + " x" + tQty + " (" + (t.expiry || "?") + ", " + (t.sellDate || t.date || "?") + ")");
    } else {
      // Insertar SIEMPRE justo debajo del encabezado, no al final: así el
      // trade más nuevo queda arriba y el más viejo va bajando — el orden
      // que se pidió (más nuevo a más antiguo). Como los trades del payload
      // ya vienen ordenados de más antiguo a más nuevo (ver el sort en
      // ucharts_history_migration.js), insertar cada uno en esa misma
      // posición fija hace que el último procesado (el más reciente) termine
      // literalmente arriba de todo.
      var nextRow = headerRowIdx + 1;
      sheet.insertRowBefore(nextRow);
      insertedSoFar++;
      var tradeNum = "T-" + Utilities.formatDate(new Date(), ss.getSpreadsheetTimeZone(), "yyyyMMdd") + "-" + Utilities.getUuid().slice(0, 8);
      
      var rowValues = [];
      for (var c = 0; c < headers.length; c++) {
        rowValues.push("");
      }
      
      // Esta automatización solo carga los HECHOS reales que vienen de
      // uCharts (fecha, ticker, cantidad, compra, venta). Saldo USD,
      // % Ganancia, Estado y Take Profit Objetivo NO se tocan acá: Saldo/%
      // Ganancia/Estado quedan como fórmulas (ver applyFormulas) y Take
      // Profit Objetivo se deja en blanco porque uCharts no informa ningún
      // objetivo real — inventar un número ahí solo ensuciaría la columna.
      //
      // La columna "°" (numeración) se deja en blanco: con inserción al
      // tope, la posición de cada fila cambia con cada sincronización
      // nueva, así que un número fijo asignado acá quedaría desactualizado
      // enseguida. Si esa columna tiene una fórmula propia armada en la
      // hoja (p.ej. =ROW()-1), se recalcula sola.
      if (colFechaCompra !== -1) rowValues[colFechaCompra - 1] = t.buyDate || t.date || "";
      if (colTradeCompra !== -1) rowValues[colTradeCompra - 1] = tradeNum;
      // FIX (10/09): si este trade ya llega CERRADO en el primer sync (abrió
      // y cerró entre dos corridas), cargar también Fecha/Trade # Venta acá
      // mismo — esta fila nunca vuelve a pasar por la rama "exRecord" de
      // arriba, así que si no se cargan ahora quedan en blanco para siempre.
      if (tStatus === "CERRADO" || tStatus === "CLOSED") {
        if (colFechaVenta !== -1) rowValues[colFechaVenta - 1] = t.sellDate || "";
        if (colTradeVenta !== -1) rowValues[colTradeVenta - 1] = tradeNum;
      }
      if (colTicker !== -1) rowValues[colTicker - 1] = tTicker;
      if (colCallPut !== -1) rowValues[colCallPut - 1] = tType;
      if (colCantidad !== -1) rowValues[colCantidad - 1] = tQty;
      if (colCompra !== -1) rowValues[colCompra - 1] = tBuyPrice;
      
      if (colVenta !== -1) {
        rowValues[colVenta - 1] = (tStatus === "CERRADO" || tStatus === "CLOSED") ? tSellPrice : "";
      }
      if (colExpiracion !== -1) {
        rowValues[colExpiracion - 1] = t.expiry || "";
      }
      
      sheet.getRange(nextRow, 1, 1, headers.length).setValues([rowValues]);
      applyFormulas(nextRow);
      
      // Aplicar formato de moneda y porcentajes a la nueva fila
      if (colCompra !== -1) sheet.getRange(nextRow, colCompra).setNumberFormat("$#,##0.00");
      if (colVenta !== -1) sheet.getRange(nextRow, colVenta).setNumberFormat("$#,##0.00");
      if (colSaldo !== -1) sheet.getRange(nextRow, colSaldo).setNumberFormat("$#,##0.00");
      if (colPctGanancia !== -1) sheet.getRange(nextRow, colPctGanancia).setNumberFormat("0.00%");
      
      addedCount++;
    }
  }
  
  return ContentService.createTextOutput(JSON.stringify({
    status: "success",
    message: "Historial sincronizado automáticamente en Registro Continuo",
    added: addedCount,
    updated: updatedCount,
    skipped: skippedCount,
    skippedDetails: skippedDetails
  })).setMimeType(ContentService.MimeType.JSON);
}
  

function handleLegacyBacktestUpdate(ss, data) {
  var backtestSheet = ss.getSheetByName("Backtesting");
  if (!backtestSheet) {
    backtestSheet = ss.insertSheet("Backtesting");
  }
  backtestSheet.clear();
  backtestSheet.getRange("A:Z").setBorder(false, false, false, false, false, false);
  
  backtestSheet.getRange("A1").setValue("RESUMEN GENERAL DE BACKTESTING").setFontWeight("bold").setFontSize(12).setFontColor("#107c41");
  backtestSheet.getRange("A2").setValue("Métrica").setFontWeight("bold").setBackground("#107c41").setFontColor("#ffffff");
  backtestSheet.getRange("B2").setValue("Valor").setFontWeight("bold").setBackground("#107c41").setFontColor("#ffffff");
  
  var summaryRows = data.summary || [];
  for (var i = 0; i < summaryRows.length; i++) {
    backtestSheet.getRange(i + 3, 1).setValue(summaryRows[i].metrica);
    backtestSheet.getRange(i + 3, 2).setValue(summaryRows[i].valor);
  }
  if (summaryRows.length > 0) {
    backtestSheet.getRange(2, 1, summaryRows.length + 1, 2).setBorder(true, true, true, true, true, true, "#d9d9d9", SpreadsheetApp.BorderStyle.SOLID);
  }
  
  backtestSheet.getRange("D1").setValue("RENDIMIENTO POR ESTRATEGIA").setFontWeight("bold").setFontSize(12).setFontColor("#1f4e78");
  var stratHeaders = ["Estrategia", "Total Trades", "Win Rate %", "Retorno Promedio %"];
  for (var h = 0; h < stratHeaders.length; h++) {
    backtestSheet.getRange(2, 4 + h).setValue(stratHeaders[h]).setFontWeight("bold").setBackground("#1f4e78").setFontColor("#ffffff");
  }
  
  var stratRows = data.by_strategy || [];
  for (var i = 0; i < stratRows.length; i++) {
    backtestSheet.getRange(i + 3, 4).setValue(stratRows[i].estrategia);
    backtestSheet.getRange(i + 3, 5).setValue(stratRows[i].trades);
    backtestSheet.getRange(i + 3, 6).setValue(stratRows[i].win_rate);
    backtestSheet.getRange(i + 3, 7).setValue(stratRows[i].avg_return);
  }
  if (stratRows.length > 0) {
    backtestSheet.getRange(2, 4, stratRows.length + 1, stratHeaders.length).setBorder(true, true, true, true, true, true, "#d9d9d9", SpreadsheetApp.BorderStyle.SOLID);
  }
  
  for (var col = 1; col <= 13; col++) {
    backtestSheet.autoResizeColumn(col);
  }
  
  return ContentService.createTextOutput(JSON.stringify({
    status: "success",
    message: "Datos de backtesting legacy actualizados"
  })).setMimeType(ContentService.MimeType.JSON);
}

function handleLegacyLiveSignalsUpdate(ss, data) {
  var liveSheet = ss.getSheetByName("Monitoreo en Vivo");
  if (!liveSheet) {
    liveSheet = ss.insertSheet("Monitoreo en Vivo");
  }
  liveSheet.clear();
  
  var liveHeaders = ["Activo", "Dirección (CALL/PUT)", "Estrategia Detectada", "Precio de Acción", "Probabilidad (Win Rate)", "Fecha/Hora de Barra", "Última Sincronización"];
  liveSheet.appendRow(liveHeaders);
  
  var headerRange = liveSheet.getRange(1, 1, 1, liveHeaders.length);
  headerRange.setFontWeight("bold").setFontColor("#ffffff").setBackground("#107c41").setHorizontalAlignment("center");
  
  var nowStr = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), "yyyy-MM-dd HH:mm:ss");
  
  if (data.signals.length > 0) {
    for (var s = 0; s < data.signals.length; s++) {
      var sig = data.signals[s];
      liveSheet.appendRow([
        sig.ticker,
        sig.type,
        sig.strategy,
        sig.price,
        sig.probability,
        sig.time,
        nowStr
      ]);
      
      var lastRowIdx = liveSheet.getLastRow();
      var typeRange = liveSheet.getRange(lastRowIdx, 2);
      typeRange.setHorizontalAlignment("center");
      if (sig.type === "CALL") {
        typeRange.setBackground("#d4edda").setFontColor("#155724").setFontWeight("bold");
      } else if (sig.type === "PUT") {
        typeRange.setBackground("#f8d7da").setFontColor("#721c24").setFontWeight("bold");
      }
    }
  }
  
  for (var col = 1; col <= liveHeaders.length; col++) {
    liveSheet.autoResizeColumn(col);
  }
  
  return ContentService.createTextOutput(JSON.stringify({
    status: "success",
    message: "Señales en vivo legacy actualizadas"
  })).setMimeType(ContentService.MimeType.JSON);
}

function handleMonitoreoVivoUpdate(ss, data) {
  var sheet = findSheetLoose(ss, "Monitoreo en Vivo");
  if (!sheet) sheet = ss.insertSheet("Monitoreo en Vivo");
  sheet.clear();

  var counts = data.counts || {};
  var summary = "Última actualización: " + data.synced_at +
    "  |  Activos monitoreados: " + data.total_tickers +
    "  |  Sistema: " + data.system_state +
    "  |  CONFIRMADA: " + (counts["CONFIRMADA"] || 0) +
    "  INMINENTE: " + (counts["INMINENTE"] || 0) +
    "  PRE-ALERTA: " + (counts["PRE-ALERTA"] || 0);
  sheet.getRange(1, 1).setValue(summary).setFontWeight("bold");

  var headers = ["Activo", "Estrategia", "Estado", "Probabilidad (Win Rate)", "Setup Score", "Precio", "Distancia PM40 %", "Última Actualización"];
  var hr = sheet.getRange(2, 1, 1, headers.length);
  hr.setValues([headers]).setFontWeight("bold").setFontColor("#ffffff").setBackground("#107c41").setHorizontalAlignment("center");

  var values = data.rows.map(function (r) {
    return [r.ticker, r.strategy, r.state, r.probability, r.score, r.price, r.distance_pm40, r.last_update];
  });
  if (values.length > 0) {
    sheet.getRange(3, 1, values.length, headers.length).setValues(values);
    var colors = { "CONFIRMADA": "#d4edda", "INMINENTE": "#fff3cd", "PRE-ALERTA": "#e2e3e5" };
    var bg = values.map(function (v) {
      var c = colors[v[2]] || null;
      return [c, c, c, c, c, c, c, c];
    });
    sheet.getRange(3, 1, values.length, headers.length).setBackgrounds(bg);
  }
  sheet.setFrozenRows(2);
  for (var col = 1; col <= headers.length; col++) sheet.autoResizeColumn(col);

  return ContentService.createTextOutput(JSON.stringify({
    status: "success",
    message: "Monitoreo en Vivo actualizado (" + values.length + " filas)"
  })).setMimeType(ContentService.MimeType.JSON);
}

function handleLegacyBuySell(ss, data) {
  var ticker = data.ticker || "";
  var action = (data.action || "").toLowerCase();
  var type = (data.type || "").toUpperCase();
  var price = parseFloat(data.price) || 0.0;
  var quantity = parseInt(data.quantity) || 1;
  var strategy = data.strategy || "";
  var strike = data.strike || "";
  var expiration = data.expiration || "";
  
  var sheet = ss.getSheetByName("UCharts Compuesto") 
           || ss.getSheetByName("Ucharts Compuesto")
           || ss.getSheetByName("Simulacion-Uchart")
           || ss.getActiveSheet();
           
  var headerRowIdx = 8;
  var tickerCol = 5;
  if (action === "buy" || action === "open") {
    sheet.appendRow([true, false, "L_ID", "", ticker, type, strike, "", "", expiration, quantity, price, "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "Legacy entry"]);
    return ContentService.createTextOutput(JSON.stringify({status: "success", message: "Legacy buy registered"})).setMimeType(ContentService.MimeType.JSON);
  }
  return ContentService.createTextOutput(JSON.stringify({status: "error", message: "Acción no reconocida"})).setMimeType(ContentService.MimeType.JSON);
}

function getActualLastRow(sheet, headerRowIdx, tickerCol) {
  if (tickerCol === -1) {
    return sheet.getLastRow();
  }
  var maxRows = sheet.getMaxRows();
  if (maxRows <= headerRowIdx) return headerRowIdx;
  
  var values = sheet.getRange(headerRowIdx + 1, tickerCol, maxRows - headerRowIdx, 1).getValues();
  for (var i = values.length - 1; i >= 0; i--) {
    if (values[i][0] && values[i][0].toString().trim() !== "") {
      return headerRowIdx + 1 + i;
    }
  }
  return headerRowIdx;
}

function parseDate(dateStr) {
  if (!dateStr) return "";
  var str = dateStr.toString().toLowerCase().trim();
  var d = new Date(dateStr);
  if (!isNaN(d.getTime())) {
    try {
      return Utilities.formatDate(d, SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone(), "yyyy-MM-dd");
    } catch (e) {}
  }
  return dateStr;
}

// Función para crear e inicializar la pestaña de Gestión de Tareas del Proyecto
function createTasksSheet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheetName = "GESTION_TAREAS";
  
  // Si ya existe, la seleccionamos o la recreamos de forma limpia
  var sheet = ss.getSheetByName(sheetName);
  if (sheet) {
    ss.deleteSheet(sheet);
  }
  sheet = ss.insertSheet(sheetName);
  
  // Mover al primer lugar (extremo izquierdo) para visibilidad inmediata
  try {
    ss.setActiveSheet(sheet);
    ss.moveActiveSheet(1);
  } catch(e) {}
  
  // Establecer anchos de columna estéticos
  sheet.setColumnWidth(1, 40);  // N°
  sheet.setColumnWidth(2, 60);  // Checklist (Checkbox)
  sheet.setColumnWidth(3, 100); // Estado
  sheet.setColumnWidth(4, 180); // Fase / Componente
  sheet.setColumnWidth(5, 300); // Tarea Específica
  sheet.setColumnWidth(6, 120); // Prioridad
  sheet.setColumnWidth(7, 300); // Notas / Output de Validación
  
  // Cabeceras premium
  var headers = ["N°", "Listo", "Estado", "Fase / Componente", "Tarea Específica", "Prioridad", "Notas / Output de Validación"];
  sheet.appendRow(headers);
  
  var headerRange = sheet.getRange(1, 1, 1, headers.length);
  headerRange.setFontWeight("bold");
  headerRange.setFontColor("#ffffff");
  headerRange.setBackground("#111827"); // Negro premium
  headerRange.setHorizontalAlignment("center");
  sheet.setFrozenRows(1);
  
  // Listado detallado de tareas (Fases 1 a 14 + Mejoras de UX/Sincronización)
  var tasks = [
    [1, true, "COMPLETADO", "Fase 1: SQLite Relacional", "Crear bd relacional con esquema de 14 tablas", "ALTA", "trading_laboratory.db funcionando perfectamente con logs atómicos."],
    [2, true, "COMPLETADO", "Fase 1: SQLite Relacional", "Poblar catálogo inicial con 18 estrategias de opciones", "MEDIA", "Estrategias cargadas en tabla 'estrategias'."],
    [3, true, "COMPLETADO", "Fase 2: Rediseño Webhook", "Manejador extensible en Apps Script de 14 tablas", "ALTA", "webhook_listener.js administrando SEÑALES, SETUPS, etc."],
    [4, true, "COMPLETADO", "Fase 3: Bot Piloto", "Pruebas de inserción y transiciones de estado en piloto", "ALTA", "test_pilot_alert.py validado sin duplicidades."],
    [5, true, "COMPLETADO", "Fase 5: Setup Scoring", "Configuración de pesos paramétricos de score en config.json", "ALTA", "Pesos inyectados para Tendencia, PM40, Volumen y Piso."],
    [6, true, "COMPLETADO", "Fase 5: Setup Scoring", "Cálculo en vivo de Setup Score en live_scanner.py", "ALTA", "live_scanner calcula el score y actualiza Sheets."],
    [7, true, "COMPLETADO", "Fase 6: MFE / MAE Tracker", "Seguimiento en vivo de MFE y MAE en ticks simulados", "ALTA", "post_signal_tracker.py actualizando pestaña 'RESULTADOS'."],
    [8, true, "COMPLETADO", "Fase 7: Radar de Ranking", "Formato condicional por estado y orden dinámico en Sheets", "MEDIA", "Pestaña RADAR_ACTUAL coloreada y ordenada automáticamente."],
    [9, true, "COMPLETADO", "Fase 8: Torneo de Bots", "Simulación contrafáctica multi-perfil (Piloto/Conservador/Agresivo)", "MEDIA", "Pestaña TORNEO_BOTS con PnL acumulado y win rate por bot."],
    [10, true, "COMPLETADO", "Fase 9: Alertas Push", "Integración de notificaciones push ricas con Telegram", "MEDIA", "Alertas HTML en Telegram al pasar a INMINENTE y CONFIRMADA."],
    [11, true, "COMPLETADO", "Fase 10: Paper Bot", "Simulador financiero de órdenes de opciones y comisiones", "ALTA", "paper_bot.py debitando saldo de compra y acreditando saldo de venta."],
    [12, true, "COMPLETADO", "Fase 11: Bitácora Cuantitativa", "Agrupación cuantitativa por ticker y estrategia en SQLite", "MEDIA", "quantitative_analyst.py persistiendo en la tabla 'estadisticas'."],
    [13, true, "COMPLETADO", "Fase 12: Weights Optimizer", "Calibración paramétrica Grid Search de pesos de scoring", "ALTA", "optimizer.py calibra pesos para maximizar WR retrospectivo."],
    [14, true, "COMPLETADO", "Fase 13: Criterio de Kelly", "Motor de Kelly dinámico en compras del Paper Bot", "ALTA", "Fórmula de Kelly fraccional integrada y compras escaladas."],
    [15, true, "COMPLETADO", "Fase 14: Monte Carlo", "Simulación probabilística de 1,000 caminos y probabilidad de ruina", "ALTA", "monte_carlo.py calculando drawdown e intervalos de confianza."],
    [16, true, "COMPLETADO", "Tampermonkey: Sincro Masiva", "Paginación y lectura DOM de historial en español e inglés", "ALTA", "Cargadas con éxito 26 operaciones del historial de uCharts."],
    [17, false, "PENDIENTE", "Mejoras: Dashboard Visual", "Dashboard visual de ganancias acumuladas y PnL neto", "MEDIA", "Añadir gráficos interactivos de equidad en la hoja de Sheets."],
    [18, false, "PENDIENTE", "Mejoras: Telegram Avanzado", "Envío de alertas con capturas de gráficos de TradingView", "BAJA", "Integración de Puppeteer o capturador de imágenes."],
    [19, false, "PENDIENTE", "Mejoras: Live Balance", "Monitorear e importar balance real de la cuenta de corretaje", "MEDIA", "Sincronizar balance real en cuenta de corretaje con Sheets."]
  ];
  
  // Agregar datos
  for (var i = 0; i < tasks.length; i++) {
    sheet.appendRow(tasks[i]);
  }
  
  // Crear checkboxes en la columna B (filas 2 a la última)
  var rangeCheckboxes = sheet.getRange(2, 2, tasks.length, 1);
  var validation = SpreadsheetApp.newDataValidation().requireCheckbox().build();
  rangeCheckboxes.setDataValidation(validation);
  
  // Formatear filas y fuentes
  var dataRange = sheet.getRange(2, 1, tasks.length, headers.length);
  dataRange.setFontSize(10);
  dataRange.setVerticalAlignment("middle");
  
  // Alinear columnas de control al centro
  sheet.getRange(2, 1, tasks.length, 3).setHorizontalAlignment("center");
  sheet.getRange(2, 6, tasks.length, 1).setHorizontalAlignment("center");
  
  // Formato Condicional para la columna Estado (C) y Listo (B)
  var rules = [];
  
  // 1. COMPLETADO (Verde suave)
  var cond1 = SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo("COMPLETADO")
    .setBackground("#d4edda")
    .setFontColor("#155724")
    .setBold(true)
    .setRanges([sheet.getRange(2, 3, tasks.length, 1)])
    .build();
  rules.push(cond1);
  
  // 2. EN PROGRESO (Amarillo suave)
  var cond2 = SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo("EN PROGRESO")
    .setBackground("#fff3cd")
    .setFontColor("#856404")
    .setBold(true)
    .setRanges([sheet.getRange(2, 3, tasks.length, 1)])
    .build();
  rules.push(cond2);
  
  // 3. PENDIENTE (Gris/Rojo suave)
  var cond3 = SpreadsheetApp.newConditionalFormatRule()
    .whenTextEqualTo("PENDIENTE")
    .setBackground("#f8d7da")
    .setFontColor("#721c24")
    .setBold(true)
    .setRanges([sheet.getRange(2, 3, tasks.length, 1)])
    .build();
  rules.push(cond3);
  
  // 4. Tachado si la celda Listo (B) es TRUE
  var cond4 = SpreadsheetApp.newConditionalFormatRule()
    .whenFormulaSatisfied("=$B2=TRUE")
    .setStrikethrough(true)
    .setFontColor("#9ca3af")
    .setRanges([sheet.getRange(2, 4, tasks.length, 2)]) // Fase y Tarea
    .build();
  rules.push(cond4);
  
  sheet.setConditionalFormatRules(rules);
  
  // Bordes estéticos
  sheet.getRange(1, 1, tasks.length + 1, headers.length).setBorder(true, true, true, true, true, true, "#e5e7eb", SpreadsheetApp.BorderStyle.SOLID);
}

// ==UserScript==
// @name         UCharts to Google Sheets Sync Tool
// @namespace    http://tampermonkey.net/
// @version      5.0.30
// @description  Agrega un panel de control con sincronización automática en tiempo real para UCharts y Google Sheets.
// @author       Antigravity
// @match        https://app.ucharts.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_registerMenuCommand
// ==/UserScript==

(function() {
  'use strict';

  // ==========================================
  // CONFIGURACIÓN - URL DE TU WEBHOOK (Google Sheets)
  // ==========================================
  const DEFAULT_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxbLkV8YMCxcQjI9GVtxXx56WtJO2jH-54k9M8bylct9v2uhf7CZI9ewIGFOnI05QPE/exec";
  let WEBHOOK_URL = localStorage.getItem('ucharts_webhook_url') || DEFAULT_WEBHOOK_URL;

  // Limpieza de seguridad en caso de que localStorage contenga el texto de plantilla
  if (WEBHOOK_URL.includes("TU_WEBHOOK_URL_AQUÍ")) {
    WEBHOOK_URL = DEFAULT_WEBHOOK_URL;
    localStorage.removeItem('ucharts_webhook_url');
  }

  // Activación del control real. Para la mayoría de los botones un
  // element.click() alcanza, pero se confirmó en vivo (probando contra
  // UCharts) que el listbox de "Tipo de orden" (Mercado/Límite/Stop) NO
  // reacciona a un click() sintético simple — sólo responde a una secuencia
  // real de eventos de puntero/mouse. Por eso se dispara esa secuencia
  // completa en las coordenadas ACTUALES del elemento (recalculadas en este
  // mismo instante con getBoundingClientRect, nunca coordenadas fijas ni
  // heredadas de otro click), además del click() de siempre — así se cubren
  // ambos tipos de componente sin romper lo que ya funcionaba.
  function superClick(element) {
    if (!element) return;
    try {
      element.focus();
      const rect = element.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      // Fix: `view: window` acá tira "Failed to convert value to 'Window'"
      // porque el `window` del sandbox de Tampermonkey no es un objeto Window
      // válido para el constructor nativo de PointerEvent/MouseEvent en este
      // contexto. Sin `view` en las opciones, el evento se construye bien
      // igual (la propiedad es opcional) y ya no cae siempre al catch/fallback.
      const opts = { bubbles: true, cancelable: true, composed: true, clientX: cx, clientY: cy, button: 0 };
      element.dispatchEvent(new PointerEvent('pointerdown', opts));
      element.dispatchEvent(new MouseEvent('mousedown', opts));
      element.dispatchEvent(new PointerEvent('pointerup', opts));
      element.dispatchEvent(new MouseEvent('mouseup', opts));
      element.click();
    } catch (err) {
      console.warn("[Auto-Trader] Falló superClick, ejecutando fallback clásico:", err);
      try { element.click(); } catch (err2) {}
    }
  }

  // ----------------------------------------------------------------
  // Helper robusto de búsqueda de botones por texto.
  //
  // Por qué existía el bug original: buscar entre 'button, input, div, span, a'
  // con .includes(texto) hace que un <div> contenedor que envuelve al <button>
  // real matchee ANTES que el botón (porque el div también "contiene" el texto
  // en su textContent, y aparece antes en el orden del DOM). Un click sobre ese
  // div nunca llega al <button> real: los eventos de click burbujean hacia
  // arriba, nunca bajan hacia los hijos. Resultado: parece que se hace click,
  // pero React nunca recibe el evento en su listener real.
  //
  // Esta función:
  //  1) sólo busca entre elementos realmente clickeables (button, input,
  //     [role="button"]) — nunca div/span/a genéricos.
  //  2) prioriza coincidencia EXACTA de texto sobre coincidencia parcial.
  //  3) si hay varias coincidencias parciales, se queda con la más específica
  //     (menos elementos descendientes), no con la primera en orden del DOM.
  // ----------------------------------------------------------------
  function isUsableControl(element) {
    if (!element) return false;
    const rect = element.getBoundingClientRect();
    const style = window.getComputedStyle(element);
    return rect.width > 0 && rect.height > 0 &&
      style.display !== 'none' && style.visibility !== 'hidden' &&
      !element.disabled && element.getAttribute('aria-disabled') !== 'true';
  }

  function findActionButton(labels, root = document) {
    const norm = el => (el.textContent || el.value || el.getAttribute('aria-label') || "")
      .trim().toLowerCase().replace(/\s+/g, ' ');

    const candidates = Array.from(
      root.querySelectorAll('button, input[type="button"], input[type="submit"], [role="button"]')
    ).filter(isUsableControl);

    // 1) match exacto
    let match = candidates.find(el => labels.includes(norm(el)));
    if (match) return match;

    // 2) match parcial, priorizando el elemento más específico (menos hijos)
    const partial = candidates
      .filter(el => labels.some(l => norm(el).includes(l)))
      .sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length);

    return partial[0] || null;
  }

  async function waitForActionButton(labels, timeoutMs = 8000, root = document) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const button = findActionButton(labels, root);
      if (button) return button;
      await new Promise(resolve => setTimeout(resolve, 200));
    }
    return null;
  }

  // Elementos globales del panel
  let panel = null;
  let btn = null;
  let autoCheckbox = null;
  let statusIndicator = null;
  let autoSyncEnabled = false;

  // Estado de la Bandera Automática (declarado ACÁ arriba, no más abajo junto
  // al resto de sus funciones): init() llama a renderBanderinToggle(), que
  // lee banderinEnabled, de forma SÍNCRONA la primera vez que corre —  y
  // safeInit()/init() se ejecutan ya en la carga inicial del script, antes
  // de que la ejecución llegue a la línea donde estas variables se
  // declaraban antes. Con "let"/"const" eso es un Temporal Dead Zone:
  // acceder a la variable antes de que su propia línea de declaración se
  // ejecute tira ReferenceError. Ese error, atrapado por el try/catch de
  // safeInit(), cortaba en seco el resto del cableado de init() — por eso
  // dejaron de funcionar TODOS los botones y bucles que se conectan después
  // en el código (Sincronizar Planilla, Sincronizar Día, Lanzar Tester,
  // Compra Call/Put, Pánico, y los setInterval de monitoreo/auto-trader/
  // heartbeat), no sólo la Bandera. Manteniendo sólo la declaración de estas
  // variables acá arriba (las funciones que las usan pueden seguir abajo,
  // las funciones sí se izan completas) se evita el problema.
  let banderinEnabled = localStorage.getItem('ucharts_banderin_enabled') === 'true';
  let banderinRunning = false;
  // Interruptor MAESTRO del Auto-Trader: arranca SIEMPRE en pausa (false) la
  // primera vez, y sólo pasa a true cuando el usuario aprieta "Iniciar
  // Auto-Trader" a propósito — así una recarga de página, un estado "ARMED"
  // colgado del servidor, o el propio arranque del script nunca pueden
  // comprar/vender solos sin que el usuario lo haya prendido él mismo.
  // Declarado ACÁ ARRIBA junto a banderinEnabled por la misma razón de TDZ
  // explicada en el comentario de arriba: renderAutoTraderMasterToggle() lo
  // lee de forma síncrona la primera vez que corre init().
  let autoTraderMasterOn = localStorage.getItem('ucharts_autotrader_master_on') === 'true';
  // cachedAccountBalance: mismo motivo de TDZ que las variables de arriba.
  // extractAccountBalance() (llamada desde startHeartbeatLoop, que corre
  // síncronamente dentro de init()) la necesitaba estando declarada MÁS
  // ABAJO en el archivo — así que un remontaje del panel (retry de la SPA)
  // podía tirar "Cannot access 'cachedAccountBalance' before initialization"
  // y abortar el resto de init() a mitad de camino (incluida la Bandera,
  // el heartbeat, y todo lo que viene después en el archivo).
  let cachedAccountBalance = null;
  // Ver el comentario grande dentro de init(), justo antes de los
  // setInterval de fondo: esta bandera evita registrar un segundo (o
  // tercer, o cuarto...) juego completo de bucles de fondo si init()
  // se vuelve a ejecutar porque uCharts destruyó el panel (p. ej. al
  // redirigir a login tras expirar la sesión).
  let backgroundLoopsStarted = false;
  // Máquina de estados POR TICKER (antes era una única variable global
  // "banderinCycle", que sólo permitía correr Bandera en un activo a la vez).
  // Cada entrada del Map es el ciclo probing/evaluating de ESE ticker.
  const banderinCycles = new Map();
  const banderinTrackedPositions = new Map();
  // Bucket diario compartido: capital comprometido por Cardona (real, vía
  // Auto-Trader) en su propio sub-pool. Ver "DAILY OPERATIONAL BUCKET" más
  // abajo para la lógica de reparto con Bandera.
  const cardonaTrackedPositions = new Map();
  const BANDERIN_EDGE_PCT = 2.0;

  // Estilos CSS para el panel premium flotante
  const style = document.createElement('style');
  style.innerHTML = `
    .sheets-sync-panel {
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 9999;
      background: rgba(18, 24, 32, 0.96);
      border: 1px solid rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(12px);
      padding: 14px;
      border-radius: 16px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.5);
      display: flex;
      flex-direction: column;
      gap: 10px;
      width: 250px;
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      color: #e5e7eb;
    }
    .sheets-sync-panel.state-armed {
      border: 2px solid #22c55e !important;
      box-shadow: 0 4px 20px rgba(34, 197, 94, 0.25) !important;
    }
    .sheets-sync-panel.state-disarmed {
      border: 2px solid #facc15 !important;
      box-shadow: 0 4px 20px rgba(250, 204, 21, 0.25) !important;
    }
    .sheets-sync-panel.state-stop {
      border: 2px solid #ef4444 !important;
      box-shadow: 0 4px 25px rgba(239, 68, 68, 0.4) !important;
      animation: pulse-red 2s infinite;
    }
    @keyframes pulse-red {
      0% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
      70% { box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
      100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0); }
    }
    .sync-tabs {
      display: flex;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      margin-bottom: 5px;
    }
    .sync-tab {
      flex: 1;
      text-align: center;
      padding: 6px;
      font-size: 11px;
      cursor: pointer;
      color: #9ca3af;
      font-weight: 600;
      border-bottom: 2px solid transparent;
      transition: all 0.3s ease;
    }
    .sync-tab.active {
      color: #22c55e;
      border-bottom: 2px solid #22c55e;
    }
    .tab-content {
      display: none;
      flex-direction: column;
      gap: 10px;
    }
    .tab-content.active {
      display: flex;
    }
    .sheets-sync-btn {
      background: linear-gradient(135deg, #107c41, #0f6c3a);
      color: white;
      border: none;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.3s ease;
      width: 100%;
    }
    .sheets-sync-btn:hover:not(:disabled) {
      transform: translateY(-1px);
      background: linear-gradient(135deg, #128c4a, #107c41);
    }
    .sheets-sync-btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
    }
    .sync-spinner {
      border: 2px solid rgba(255,255,255,0.3);
      border-radius: 50%;
      border-top: 2px solid white;
      width: 12px;
      height: 12px;
      animation: spin 1s linear infinite;
      display: none;
    }
    .auto-sync-container {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      color: #9ca3af;
      padding: 4px 2px;
      border-top: 1px solid rgba(255,255,255,0.05);
      margin-top: 5px;
    }
    .auto-sync-label {
      display: flex;
      align-items: center;
      gap: 6px;
      cursor: pointer;
    }
    .auto-sync-checkbox {
      accent-color: #107c41;
      cursor: pointer;
    }
    .sync-status-indicator {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background-color: #9ca3af;
      display: inline-block;
      transition: all 0.3s ease;
    }
    .sync-status-indicator.active {
      background-color: #00ff66;
      box-shadow: 0 0 8px #00ff66;
    }
    /* Auto-Trader styles */
    .profile-selector {
      display: flex;
      gap: 4px;
      margin-bottom: 2px;
    }
    .profile-btn {
      flex: 1;
      font-size: 9px;
      padding: 5px 2px;
      border-radius: 6px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      background: rgba(255,255,255,0.02);
      color: #9ca3af;
      cursor: pointer;
      text-align: center;
      font-weight: bold;
      transition: all 0.2s ease;
    }
    .profile-btn.active {
      background: #22c55e;
      color: black;
      border-color: #22c55e;
    }
    .form-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 11px;
    }
    .form-input {
      background: rgba(0, 0, 0, 0.3);
      border: 1px solid rgba(255, 255, 255, 0.15);
      border-radius: 6px;
      color: white;
      padding: 4px 6px;
      width: 65px;
      font-size: 11px;
      text-align: center;
    }
    .btn-action-green {
      background: linear-gradient(135deg, #22c55e, #16a34a);
      color: white;
      font-weight: bold;
    }
    .btn-action-green:hover:not(:disabled) {
      background: linear-gradient(135deg, #4ade80, #22c55e);
    }
    .btn-action-blue {
      background: linear-gradient(135deg, #3b82f6, #2563eb);
      color: white;
      font-weight: bold;
    }
    .btn-action-blue:hover:not(:disabled) {
      background: linear-gradient(135deg, #60a5fa, #3b82f6);
    }
    .btn-action-red {
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: white;
      font-weight: bold;
    }
    .btn-action-red:hover:not(:disabled) {
      background: linear-gradient(135deg, #f87171, #ef4444);
    }
    .btn-action-group {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    /* Panel de Riesgo (Requisito #12): siempre visible, capital/cupo/
       exposición/P&L/posiciones abiertas + estado RiskEngine/PositionManager. */
    .risk-panel {
      display: flex;
      flex-direction: column;
      gap: 4px;
      font-size: 10.5px;
      color: #cbd5e1;
      background: rgba(0,0,0,0.25);
      border-radius: 8px;
      padding: 8px 10px;
      margin-bottom: 4px;
      border: 1px solid rgba(255,255,255,0.06);
    }
    .risk-panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      font-weight: 700;
      color: #e5e7eb;
      margin-bottom: 2px;
    }
    .risk-badge {
      font-size: 9px;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 10px;
      background: #374151;
      color: #d1d5db;
    }
    .risk-badge.risk-armed { background: #14532d; color: #86efac; }
    .risk-badge.risk-disarmed { background: #713f12; color: #fde68a; }
    .risk-badge.risk-stop { background: #7f1d1d; color: #fca5a5; }
    .risk-badge.risk-locked { background: #7f1d1d; color: #fca5a5; }
    .risk-badge.risk-offline { background: #374151; color: #9ca3af; font-style: italic; }
    .risk-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 6px;
    }
    .risk-row .risk-val { font-weight: 600; color: #f3f4f6; }
    .risk-val.risk-neg { color: #f87171; }
    .risk-val.risk-pos { color: #4ade80; }
    .risk-val.risk-warn { color: #facc15; }
  `;

  function init() {
    // Si la estructura DOM básica no está disponible, reintentar
    if (!document.body || !document.head) {
      return;
    }

    // Si ya existe el panel en la página, no duplicarlo
    if (document.querySelector('.sheets-sync-panel')) return;

    // Inyectar estilos de forma segura
    if (!document.getElementById('sheets-sync-styles')) {
      style.id = 'sheets-sync-styles';
      document.head.appendChild(style);
    }

    // Crear y añadir panel flotante
    panel = document.createElement('div');
    panel.className = 'sheets-sync-panel';
    panel.innerHTML = `
      <div class="sync-tabs">
        <div class="sync-tab active" data-tab="tab-sheet">Planilla 📊 v5.0.23</div>
        <div class="sync-tab" data-tab="tab-trader">Auto-Trader 🤖</div>
      </div>

      <!-- PANEL DE RIESGO (Requisito #12): siempre visible, sin importar la
           pestaña activa -- muestra el estado en vivo del RiskEngine y del
           PositionManager (capital, cupo diario, exposición, P&L, posiciones
           abiertas) y expone el STOP maestro de nuevas órdenes. Se alimenta
           de /api/risk/status via fetchAndSyncRiskStatus() (polling 5s). -->
      <div class="risk-panel" id="risk-panel">
        <div class="risk-panel-header">
          <span>🛡️ RiskEngine</span>
          <span class="risk-badge" id="risk-state-badge">--</span>
        </div>
        <div class="risk-row"><span>Capital inicio día:</span><span class="risk-val" id="risk-capital-inicio">--</span></div>
        <div class="risk-row"><span>Fondos actuales:</span><span class="risk-val" id="risk-fondos-actuales">--</span></div>
        <div class="risk-row"><span>Cupo diario (10%):</span><span class="risk-val" id="risk-cupo-total">--</span></div>
        <div class="risk-row"><span>Cupo consumido:</span><span class="risk-val" id="risk-cupo-gastado">--</span></div>
        <div class="risk-row"><span>Cupo disponible:</span><span class="risk-val" id="risk-cupo-disponible">--</span></div>
        <div class="risk-row"><span>Exposición abierta:</span><span class="risk-val" id="risk-exposicion">--</span></div>
        <div class="risk-row"><span>P&amp;L realizado hoy:</span><span class="risk-val" id="risk-pnl-realizado">--</span></div>
        <div class="risk-row"><span>P&amp;L no realizado:</span><span class="risk-val" id="risk-pnl-no-realizado">--</span></div>
        <div class="risk-row"><span>Posiciones abiertas:</span><span class="risk-val" id="risk-posiciones">--</span></div>
        <div class="risk-row"><span>PositionManager:</span><span class="risk-val" id="risk-pm-state">--</span></div>
        <button class="sheets-sync-btn btn-action-red" id="btn-risk-stop" title="Bloquea INMEDIATAMENTE nuevas órdenes (kill switch). NO cierra posiciones ya abiertas -- eso es una acción separada (CERRAR TODO / PÁNICO).">
          🛑 STOP Nuevas Órdenes
        </button>
      </div>

      <!-- PESTAÑA 1: PLANILLA -->
      <div class="tab-content active" id="tab-sheet">
        <button class="sheets-sync-btn" title="Baja TODO el historial disponible en UCharts. Puede tardar varios minutos si hay muchas operaciones acumuladas.">
          <span class="sync-icon">📊</span>
          <span class="sync-spinner"></span>
          <span class="btn-text">Sincronizar Planilla</span>
        </button>
        <button class="sheets-sync-btn" id="btn-sync-day" style="margin-top: 6px;" title="Rápido: sólo baja y carga las operaciones de los últimos días (no todo el historial). Ideal para el uso diario.">
          <span class="sync-icon">📅</span>
          <span class="sync-spinner"></span>
          <span class="btn-text">Sincronizar Día</span>
        </button>
        <div class="auto-sync-container">
          <label class="auto-sync-label">
            <input type="checkbox" class="auto-sync-checkbox">
            <span>Sincronización Auto</span>
          </label>
          <span class="sync-status-indicator" title="Monitoreo inactivo"></span>
        </div>
      </div>

      <!-- PESTAÑA 2: AUTO-TRADER -->
      <div class="tab-content" id="tab-trader">
        <!-- INTERRUPTOR MAESTRO: controla si el Auto-Trader puede operar
             SOLO (compra automática por señal del servidor, auto-cierre
             TP/SL, y Bandera Automática). Comprar/vender a mano con
             COMPRA CALL / COMPRA PUT / CERRAR TODO de más abajo funciona
             igual esté pausado o no — esto sólo frena lo 100% automático,
             para dejar tiempo de intervenir manualmente cuando se quiera. -->
        <div class="auto-sync-container" style="margin-bottom: 8px; flex-direction: column; align-items: stretch; gap: 6px;">
          <div id="autotrader-master-status" style="font-size: 12px; font-weight: 600; text-align: center;">⏸️ Auto-Trader: PAUSADO</div>
          <div class="btn-action-group">
            <button class="sheets-sync-btn btn-action-green" id="btn-autotrader-start">▶️ Iniciar Auto-Trader</button>
            <button class="sheets-sync-btn btn-action-red" id="btn-autotrader-pause">⏸️ Pausar Auto-Trader</button>
          </div>
        </div>

        <div class="profile-selector">
          <button class="profile-btn active" data-profile="corto">CORTO</button>
          <button class="profile-btn" data-profile="medio">MEDIO</button>
          <button class="profile-btn" data-profile="largo">LARGO</button>
        </div>

        <div class="form-row">
          <span>Contratos:</span>
          <input type="number" id="trader-qty" class="form-input" value="1000">
        </div>

        <div class="form-row">
          <span>Días de Vencimiento:</span>
          <input type="number" id="dte-target" class="form-input" value="0" min="0">
        </div>

        <div class="form-row">
          <label style="display: flex; align-items: center; gap: 4px;">
            <input type="checkbox" id="chk-tp-pct" checked>
            <span>Take Profit %:</span>
          </label>
          <input type="number" id="tp-pct-val" class="form-input" value="15">
        </div>

        <div class="form-row">
          <label style="display: flex; align-items: center; gap: 4px;">
            <input type="checkbox" id="chk-tp-usd">
            <span>Take Profit $:</span>
          </label>
          <input type="number" id="tp-usd-val" class="form-input" value="1000" disabled>
        </div>

        <div class="form-row">
          <label style="display: flex; align-items: center; gap: 4px;">
            <input type="checkbox" id="chk-sl-pct" checked>
            <span>Stop Loss %:</span>
          </label>
          <input type="number" id="sl-pct-val" class="form-input" value="10">
        </div>

        <div class="form-row">
          <label style="display: flex; align-items: center; gap: 4px;">
            <input type="checkbox" id="chk-sl-usd">
            <span>Stop Loss $:</span>
          </label>
          <input type="number" id="sl-usd-val" class="form-input" value="500" disabled>
        </div>

        <button class="sheets-sync-btn btn-action-blue" id="btn-launch-tester">
          🟢 Lanzar Tester (1C + 1P)
        </button>

        <div class="btn-action-group">
          <button class="sheets-sync-btn btn-action-green" id="btn-buy-call">COMPRA CALL</button>
          <button class="sheets-sync-btn btn-action-red" id="btn-buy-put">COMPRA PUT</button>
        </div>

        <button class="sheets-sync-btn btn-action-red" id="btn-panic-close" style="margin-top: 2px;">
          🛑 CERRAR TODO (PÁNICO)
        </button>

        <div class="auto-sync-container" style="margin-top: 2px;">
          <label class="auto-sync-label">
            <input type="checkbox" id="chk-auto-close" class="auto-sync-checkbox" checked>
            <span>Auto-Cierre PnL</span>
          </label>
          <span class="sync-status-indicator active" id="trader-indicator" title="Monitoreando PnL" style="background-color: #22c55e; box-shadow: 0 0 8px #22c55e;"></span>
        </div>

        <!-- BANDERA AUTOMÁTICA: straddle 1 Call + 1 Put para detectar la
             tendencia dominante e invertir en ella, repitiendo el ciclo. -->
        <div class="auto-sync-container" style="margin-top: 8px; flex-direction: column; align-items: stretch; gap: 6px; border-top: 1px dashed rgba(255,255,255,0.15); padding-top: 8px;">
          <div class="form-row">
            <span>🧮 Bucket diario compartido Cardona+Bandera (%):</span>
            <input type="number" id="daily-bucket-pct" class="form-input" value="10" min="1" max="100" step="1">
          </div>
          <div class="form-row">
            <span>🚩 Activos Bandera (tickers separados por coma):</span>
            <input type="text" id="banderin-symbols" class="form-input" value="SPY" placeholder="SPY, QQQ, AAPL...">
          </div>
          <button class="sheets-sync-btn btn-action-blue" id="btn-banderin-toggle" title="Compra 1 Call + 1 Put por cada activo habilitado para detectar la tendencia dominante (2% de diferencia), invierte en esa dirección respetando el Take Profit, y repite el ciclo mientras alcance el bucket del día.">
            🚩 Activar Bandera Automática
          </button>
          <div class="form-row" style="font-size: 10px; color: #9ca3af;">
            <span id="banderin-status-text">Bandera inactiva</span>
            <span id="banderin-bucket-status">Bandera $0.00/$0.00 · Cardona $0.00/$0.00</span>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(panel);

    btn = panel.querySelector('.sheets-sync-btn');
    autoCheckbox = panel.querySelector('.auto-sync-checkbox');
    statusIndicator = panel.querySelector('.sync-status-indicator');

    // STOP maestro del RiskEngine (Requisitos #11 y #12): bloquea nuevas
    // órdenes de inmediato via /api/system/kill-switch. Deliberadamente
    // SEPARADO del botón "CERRAR TODO (PÁNICO)" de más abajo -- ese sí cierra
    // posiciones ya abiertas; activar este STOP nunca las toca por sí solo.
    const riskStopBtn = document.getElementById('btn-risk-stop');
    if (riskStopBtn) {
      riskStopBtn.addEventListener('click', async () => {
        riskStopBtn.disabled = true;
        try {
          const activar = riskStopBtn.dataset.active !== 'true';
          const resp = await fetch('http://127.0.0.1:8055/api/system/kill-switch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              allow_new_trades: !activar,
              motivo: activar ? 'STOP manual desde panel Tampermonkey' : 'Reanudado manualmente desde panel Tampermonkey',
              usuario: 'PANEL_TAMPERMONKEY'
            })
          });
          if (resp.ok) {
            await fetchAndSyncRiskStatus();
          }
        } catch (e) {
          console.error('[RiskEngine] No se pudo alternar el kill switch:', e);
        } finally {
          riskStopBtn.disabled = false;
        }
      });
    }

    // Manejo de pestañas
    const tabs = panel.querySelectorAll('.sync-tab');
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        tabs.forEach(t => t.classList.remove('active'));
        panel.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        tab.classList.add('active');
        panel.querySelector(`#${tab.getAttribute('data-tab')}`).classList.add('active');
      });
    });

    // Manejo de Perfiles
    const profileBtns = panel.querySelectorAll('.profile-btn');
    const profileConfigs = {
      corto: { qty: 1000, tpPct: 15, tpUsd: 1000, usePct: true, useUsd: false, slPct: 10, slUsd: 500, useSlPct: true, useSlUsd: false, dte: 0 },
      medio: { qty: 200, tpPct: 40, tpUsd: 5000, usePct: true, useUsd: false, slPct: 15, slUsd: 1500, useSlPct: true, useSlUsd: false, dte: 5 },
      largo: { qty: 50, tpPct: 100, tpUsd: 10000, usePct: true, useUsd: false, slPct: 25, slUsd: 2500, useSlPct: true, useSlUsd: false, dte: 30 }
    };

    profileBtns.forEach(pBtn => {
      pBtn.addEventListener('click', () => {
        profileBtns.forEach(b => b.classList.remove('active'));
        pBtn.classList.add('active');

        const profile = pBtn.getAttribute('data-profile');
        const config = profileConfigs[profile];

        panel.querySelector('#trader-qty').value = config.qty;
        panel.querySelector('#tp-pct-val').value = config.tpPct;
        panel.querySelector('#tp-usd-val').value = config.tpUsd;
        panel.querySelector('#chk-tp-pct').checked = config.usePct;
        panel.querySelector('#chk-tp-usd').checked = config.useUsd;

        panel.querySelector('#sl-pct-val').value = config.slPct;
        panel.querySelector('#sl-usd-val').value = config.slUsd;
        panel.querySelector('#chk-sl-pct').checked = config.useSlPct;
        panel.querySelector('#chk-sl-usd').checked = config.useSlUsd;

        panel.querySelector('#tp-pct-val').disabled = !config.usePct;
        panel.querySelector('#tp-usd-val').disabled = !config.useUsd;
        panel.querySelector('#sl-pct-val').disabled = !config.useSlPct;
        panel.querySelector('#sl-usd-val').disabled = !config.useSlUsd;

        // El perfil sólo propone un DTE por defecto — si el usuario ya editó
        // el campo "Días de Vencimiento" a mano, no lo pisamos con el preset.
        if (!panel.querySelector('#dte-target').dataset.userEdited) {
          panel.querySelector('#dte-target').value = config.dte;
          localStorage.setItem('ucharts_dte_target', String(config.dte));
        }

        localStorage.setItem('ucharts_trader_profile', profile);
      });
    });

    // "Días de Vencimiento": persistir y marcar como editado a mano apenas
    // el usuario lo toca, para que cambiar de perfil (CORTO/MEDIO/LARGO) no
    // le pise el valor que puso a propósito.
    const dteInput = panel.querySelector('#dte-target');
    const savedDte = localStorage.getItem('ucharts_dte_target');
    if (savedDte !== null) {
      dteInput.value = savedDte;
      dteInput.dataset.userEdited = 'true'; // para que el click de restaurar perfil (más abajo) no lo pise
    }
    dteInput.addEventListener('input', (e) => {
      e.target.dataset.userEdited = 'true';
      localStorage.setItem('ucharts_dte_target', e.target.value);
    });

    // Restaurar perfil guardado
    const savedProfile = localStorage.getItem('ucharts_trader_profile') || 'corto';
    const targetProfileBtn = Array.from(profileBtns).find(b => b.getAttribute('data-profile') === savedProfile);
    if (targetProfileBtn) targetProfileBtn.click();

    // Habilitar/deshabilitar inputs según checkbox
    panel.querySelector('#chk-tp-pct').addEventListener('change', (e) => {
      panel.querySelector('#tp-pct-val').disabled = !e.target.checked;
    });
    panel.querySelector('#chk-tp-usd').addEventListener('change', (e) => {
      panel.querySelector('#tp-usd-val').disabled = !e.target.checked;
    });
    panel.querySelector('#chk-sl-pct').addEventListener('change', (e) => {
      panel.querySelector('#sl-pct-val').disabled = !e.target.checked;
    });
    panel.querySelector('#chk-sl-usd').addEventListener('change', (e) => {
      panel.querySelector('#sl-usd-val').disabled = !e.target.checked;
    });

    // Persistencia del checkbox "Auto-Cierre PnL" — antes se reiniciaba
    // (quedaba en su valor por defecto, "checked") cada vez que se recargaba
    // la página, sin avisar. Ahora se guarda/restaura como el resto de las
    // preferencias del panel, para que un destildado accidental no se pierda
    // de vista ni se re-active solo sin que el usuario lo note.
    const chkAutoCloseEl = panel.querySelector('#chk-auto-close');
    const savedAutoClose = localStorage.getItem('ucharts_auto_close_pnl');
    chkAutoCloseEl.checked = savedAutoClose === null ? true : savedAutoClose === 'true';
    chkAutoCloseEl.addEventListener('change', (e) => {
      localStorage.setItem('ucharts_auto_close_pnl', e.target.checked ? 'true' : 'false');
    });

    // Bucket diario compartido (Cardona + Bandera) (%) — persistir el valor elegido
    const dailyBucketPctInput = panel.querySelector('#daily-bucket-pct');
    const savedDailyBucketPct = localStorage.getItem('ucharts_daily_bucket_pct');
    if (savedDailyBucketPct !== null) dailyBucketPctInput.value = savedDailyBucketPct;
    dailyBucketPctInput.addEventListener('input', (e) => {
      localStorage.setItem('ucharts_daily_bucket_pct', e.target.value);
      // Si el % cambia, recalcular el bucket de hoy contra el balance ya conocido
      localStorage.removeItem('ucharts_daily_bucket_date');
    });

    // Bandera Automática: lista de activos habilitados — persistir (sección
    // 3: sin ningún ticker hardcodeado en la lógica).
    const banderinSymbolsInput = panel.querySelector('#banderin-symbols');
    const savedBanderinSymbols = localStorage.getItem('ucharts_banderin_symbols');
    if (savedBanderinSymbols !== null) banderinSymbolsInput.value = savedBanderinSymbols;
    banderinSymbolsInput.addEventListener('input', (e) => {
      localStorage.setItem('ucharts_banderin_symbols', e.target.value);
    });

    // Interruptor MAESTRO del Auto-Trader: Iniciar/Pausar. Arranca siempre
    // pausado (autoTraderMasterOn declarado arriba del archivo). Comprar o
    // vender a mano con los botones COMPRA CALL / COMPRA PUT / CERRAR TODO
    // sigue funcionando igual, esté pausado o no — este interruptor sólo
    // bloquea los ciclos 100% automáticos (pollPendingTradesFromServer,
    // el auto-cierre TP/SL de monitorPositionsPnL, y banderinTick).
    const autoTraderStartBtn = panel.querySelector('#btn-autotrader-start');
    const autoTraderPauseBtn = panel.querySelector('#btn-autotrader-pause');
    const autoTraderStatusEl = panel.querySelector('#autotrader-master-status');
    function renderAutoTraderMasterToggle() {
      if (autoTraderMasterOn) {
        autoTraderStatusEl.textContent = '🟢 Auto-Trader: ACTIVO';
        autoTraderStatusEl.style.color = '#22c55e';
        autoTraderStartBtn.disabled = true;
        autoTraderPauseBtn.disabled = false;
      } else {
        autoTraderStatusEl.textContent = '⏸️ Auto-Trader: PAUSADO';
        autoTraderStatusEl.style.color = '#facc15';
        autoTraderStartBtn.disabled = false;
        autoTraderPauseBtn.disabled = true;
      }
    }
    renderAutoTraderMasterToggle();
    autoTraderStartBtn.addEventListener('click', () => {
      autoTraderMasterOn = true;
      localStorage.setItem('ucharts_autotrader_master_on', 'true');
      renderAutoTraderMasterToggle();
    });
    autoTraderPauseBtn.addEventListener('click', () => {
      autoTraderMasterOn = false;
      localStorage.setItem('ucharts_autotrader_master_on', 'false');
      renderAutoTraderMasterToggle();
    });

    // Bandera Automática: botón de activar/detener
    const banderinToggleBtn = panel.querySelector('#btn-banderin-toggle');
    function renderBanderinToggle() {
      if (banderinEnabled) {
        banderinToggleBtn.textContent = '🛑 Detener Bandera Automática';
        banderinToggleBtn.classList.remove('btn-action-blue');
        banderinToggleBtn.classList.add('btn-action-red');
      } else {
        banderinToggleBtn.textContent = '🚩 Activar Bandera Automática';
        banderinToggleBtn.classList.remove('btn-action-red');
        banderinToggleBtn.classList.add('btn-action-blue');
      }
    }
    renderBanderinToggle();
    banderinToggleBtn.addEventListener('click', () => {
      if (!banderinEnabled && extractAccountBalance() === null) {
        alert('⚠️ Todavía no se detectó tu capital disponible.\n\nEl script busca el widget "Fondos disponibles para operar" (o "Valor de la cuenta") en la pantalla actual. Si no aparece en ningún lado visible ahora, andá a una pantalla donde se vea ese resumen de cuenta y volvé a activar la Bandera Automática — así puede calcular el bucket del ' + getDailyBucketPct() + '% diario.');
        return;
      }
      banderinEnabled = !banderinEnabled;
      localStorage.setItem('ucharts_banderin_enabled', banderinEnabled ? 'true' : 'false');
      renderBanderinToggle();
      const statusEl = document.getElementById('banderin-status-text');
      if (statusEl) statusEl.textContent = banderinEnabled ? 'Bandera activa: buscando tendencia...' : 'Bandera detenida (ciclo en curso se respeta hasta terminar)';
    });

    // Event listener: Lanzar Tester
    panel.querySelector('#btn-launch-tester').addEventListener('click', async () => {
      const startBtn = panel.querySelector('#btn-launch-tester');
      startBtn.disabled = true;
      startBtn.innerText = "⏳ Lanzando Tester...";

      try {
        const ok = await startTester('SPY');
        if (ok) {
          navigateToTab('Posiciones');
        } else {
          alert(`❌ Error al iniciar el Tester.\n\n${lastTraderError || 'No se pudo determinar la etapa del fallo.'}`);
        }
      } catch (err) {
        const detail = err && err.message ? err.message : String(err);
        lastTraderError = `Fallo inesperado: ${detail}`;
        console.error("[Tester] Fallo inesperado:", err);
        alert(`❌ Error al iniciar el Tester.\n\n${lastTraderError}`);
      } finally {
        startBtn.disabled = false;
        startBtn.innerText = "🟢 Lanzar Tester (1C + 1P)";
      }
    });

    // Event listener: Compra CALL
    panel.querySelector('#btn-buy-call').addEventListener('click', async () => {
      const buyBtn = panel.querySelector('#btn-buy-call');
      buyBtn.disabled = true;
      buyBtn.innerText = "⏳ Enviando...";

      const qty = parseInt(panel.querySelector('#trader-qty').value, 10) || 100;
      const profile = localStorage.getItem('ucharts_trader_profile') || 'corto';

      lastTraderError = "";
      const ok = await executeOrder('SPY', 'CALL', profile, qty);

      buyBtn.disabled = false;
      buyBtn.innerText = "COMPRA CALL";
      if (ok) {
        navigateToTab('Posiciones');
      } else {
        alert(`❌ Error al comprar CALL.\n\n${lastTraderError || 'Revisa que estés en Negociar y el activo cargue.'}`);
      }
    });

    // Event listener: Compra PUT
    panel.querySelector('#btn-buy-put').addEventListener('click', async () => {
      const buyBtn = panel.querySelector('#btn-buy-put');
      buyBtn.disabled = true;
      buyBtn.innerText = "⏳ Enviando...";

      const qty = parseInt(panel.querySelector('#trader-qty').value, 10) || 100;
      const profile = localStorage.getItem('ucharts_trader_profile') || 'corto';

      lastTraderError = "";
      const ok = await executeOrder('SPY', 'PUT', profile, qty);

      buyBtn.disabled = false;
      buyBtn.innerText = "COMPRA PUT";
      if (ok) {
        navigateToTab('Posiciones');
      } else {
        alert(`❌ Error al comprar PUT.\n\n${lastTraderError || 'Revisa que estés en Negociar y el activo cargue.'}`);
      }
    });

    // Event listener: Cerrar Todo (Pánico)
    panel.querySelector('#btn-panic-close').addEventListener('click', async () => {
      const panicBtn = panel.querySelector('#btn-panic-close');
      panicBtn.disabled = true;
      panicBtn.innerText = "⏳ Cerrando todo...";

      const ok = await panicCloseAll();

      panicBtn.disabled = false;
      panicBtn.innerText = "🛑 CERRAR TODO (PÁNICO)";
      if (ok) {
        alert("💥 Todas las posiciones han sido cerradas con éxito.");
      } else {
        alert("⚠️ Es posible que algunas posiciones no se hayan podido cerrar. Revisa la pantalla.");
      }
    });

    // Configuración del botón manual
    btn.addEventListener('click', async () => {
      if (!WEBHOOK_URL || WEBHOOK_URL.includes("TU_WEBHOOK_URL_AQUÍ")) {
        alert("❌ CONFIGURACIÓN REQUERIDA:\n\nPor favor edita el script de Tampermonkey e ingresa la URL de tu Google Apps Script en la variable WEBHOOK_URL.");
        return;
      }

      setLoading(true);

      try {
        btn.querySelector('.btn-text').innerText = "Abriendo historial...";
        await ensureHistoryView();
        btn.querySelector('.btn-text').innerText = "Extrayendo historial...";
        const result = await syncHistory(false);
        if (!result || !result.ok) throw new Error(result?.error || "La sincronización no devolvió un resultado válido.");
      } catch (err) {
        console.error("[Sheets Sync]", err);
        alert(`❌ Sincronización detenida\n\n${err.message || err}\n\nNo se envió ninguna orden; este flujo sólo lee el historial.`);
      } finally {
        setLoading(false);
        btn.querySelector('.btn-text').innerText = "Sincronizar Planilla";
      }
    });

    // Botón "Sincronizar Día": versión rápida que NO baja todo el historial
    // (eso puede tener semanas de operaciones y tardar minutos), sino sólo
    // lo necesario para cubrir los últimos días — por defecto 3, con margen
    // de sobra para no perderse nada por husos horarios o por sincronizar
    // justo pasada la medianoche. Pensado para el uso diario, una vez que
    // ya se hizo al menos una sincronización completa con "Sincronizar
    // Planilla". Como la deduplicación en la planilla es por fecha+ticker+
    // cantidad+precio, no genera duplicados aunque se solape con datos ya
    // cargados.
    const dayBtn = panel.querySelector('#btn-sync-day');
    dayBtn.addEventListener('click', async () => {
      if (!WEBHOOK_URL || WEBHOOK_URL.includes("TU_WEBHOOK_URL_AQUÍ")) {
        alert("❌ CONFIGURACIÓN REQUERIDA:\n\nPor favor edita el script de Tampermonkey e ingresa la URL de tu Google Apps Script en la variable WEBHOOK_URL.");
        return;
      }

      const spinner = dayBtn.querySelector('.sync-spinner');
      const icon = dayBtn.querySelector('.sync-icon');
      const textEl = dayBtn.querySelector('.btn-text');
      spinner.style.display = 'block';
      icon.style.display = 'none';
      dayBtn.disabled = true;
      btn.disabled = true; // evita disparar los dos botones de sync a la vez

      try {
        textEl.innerText = "Abriendo historial...";
        await ensureHistoryView();
        textEl.innerText = "Extrayendo últimos días...";
        const result = await syncHistory(false, { maxDaysBack: 3 });
        if (!result || !result.ok) throw new Error(result?.error || "La sincronización no devolvió un resultado válido.");
      } catch (err) {
        console.error("[Sheets Sync - Día]", err);
        alert(`❌ Sincronización detenida\n\n${err.message || err}\n\nNo se envió ninguna orden; este flujo sólo lee el historial.`);
      } finally {
        spinner.style.display = 'none';
        icon.style.display = 'block';
        dayBtn.disabled = false;
        btn.disabled = false;
        textEl.innerText = "Sincronizar Día";
      }
    });

    // ==========================================
    // LÓGICA DE MONITOREO Y AUTOSINCRO EN BACKGROUND
    // ==========================================
    autoSyncEnabled = localStorage.getItem('ucharts_auto_sync') === 'true';
    autoCheckbox.checked = autoSyncEnabled;
    if (autoSyncEnabled) {
      statusIndicator.className = 'sync-status-indicator active';
      statusIndicator.title = 'Monitoreo activo (cada 15s)';
    }

    autoCheckbox.addEventListener('change', (e) => {
      const active = e.target.checked;
      localStorage.setItem('ucharts_auto_sync', active ? 'true' : 'false');
      if (active) {
        statusIndicator.className = 'sync-status-indicator active';
        statusIndicator.title = 'Monitoreo activo (cada 15s)';
        startAutoSync();
      } else {
        statusIndicator.className = 'sync-status-indicator';
        statusIndicator.title = 'Monitoreo inactivo';
        stopAutoSync();
      }
    });

    if (autoSyncEnabled) {
      startAutoSync();
    }

    // ------------------------------------------------------------------
    // BUG REAL del loop infinito de "Iniciar Auto-Trader": el guard de
    // arriba ("if (document.querySelector('.sheets-sync-panel')) return")
    // sólo evita duplicar el PANEL VISUAL, no estos setInterval. Si uCharts
    // llega a destruir el DOM donde vive el panel — por ejemplo al
    // redirigir a la pantalla de login cuando expira la sesión, o al
    // re-renderizar su propia SPA — el panel desaparece, y el siguiente
    // tick de setInterval(safeInit, 1000) (más abajo en el archivo) ya no
    // encuentra ".sheets-sync-panel", así que vuelve a correr init()
    // entero. Antes, eso registraba un SEGUNDO juego completo de estos
    // bucles (pollPendingTradesFromServer, banderinTick, monitorPositionsPnL,
    // heartbeat, etc.) sin cancelar nunca el primero, porque ninguno
    // guardaba su ID para poder hacer clearInterval. Cada corte de sesión
    // sumaba otra copia corriendo en paralelo para siempre — eso es lo que
    // se veía como el botón quedando en loop, y por qué volver a iniciar
    // sesión no lo arreglaba: la sesión no era la causa, era sólo el
    // disparador que multiplicaba los bucles cada vez que se cortaba.
    //
    // Fix: estos bucles de fondo se registran UNA SOLA VEZ por carga de
    // página, sin importar cuántas veces init() se vuelva a ejecutar para
    // remontar el panel visual.
    // ------------------------------------------------------------------
    if (!backgroundLoopsStarted) {
      backgroundLoopsStarted = true;
      // Iniciar bucle de monitoreo de PnL para auto-cierre
      setInterval(monitorPositionsPnL, 2000);
      // Iniciar bucle de polling para ejecución autónoma del Auto-Trader
      setInterval(pollPendingTradesFromServer, 5000);
      // Iniciar bucle de la Bandera Automática (straddle 1C+1P -> tendencia dominante)
      setInterval(banderinTick, 2500);
      // Iniciar bucle de reporte de latido (Heartbeat) de uCharts
      startHeartbeatLoop();
      // Iniciar bucle de sincronización del estado del sistema
      setInterval(fetchAndSyncSystemState, 5000);
      // Iniciar bucle de sincronización del Panel de Riesgo (Requisito #12):
      // capital, cupo diario, exposición, P&L, posiciones abiertas y estado
      // del RiskEngine/PositionManager -- se alimenta de /api/risk/status.
      setInterval(fetchAndSyncRiskStatus, 5000);
      fetchAndSyncRiskStatus();
      // Iniciar bucle de reconciliación diaria completa de "Registro
      // Continuo": a diferencia del chequeo de fondo de 15s, esta corrida no
      // depende de que la pestaña ya esté en Historial — navega ella sola una
      // vez por día calendario para no perder operaciones si el día se pasó
      // entero en Negociar/Posiciones sin abrir Historial ni tocar "Sincronizar
      // Día" a mano.
      setInterval(runDailyFullHistorySync, 10 * 60 * 1000);
      runDailyFullHistorySync();
    }
  }

  async function ensureHistoryView() {
    const hasHistoryContent = () => {
      const url = new URL(window.location.href);
      const selectedHistoryTab = Array.from(document.querySelectorAll('[role="tab"][aria-selected="true"], [role="tab"][data-state="active"]'))
        .some(el => /^(historial|history)$/i.test((el.textContent || "").trim()));
      const text = document.body?.innerText || "";
      const hasHistoryTable = /descripción/i.test(text) && /fecha/i.test(text) && /monto/i.test(text) && /saldo/i.test(text);
      return (url.pathname.includes('/paper-money') && url.searchParams.get('tab') === 'history') ||
             selectedHistoryTab || hasHistoryTable;
    };
    if (hasHistoryContent()) return;
    const candidates = Array.from(document.querySelectorAll('button, a, [role="tab"]'));
    const historyControl = candidates.find(el => /^(historial|history)$/i.test((el.textContent || "").trim()));
    if (!historyControl) throw new Error("Etapa navegación: no se encontró el control visible 'Historial' de PaperMoney.");
    historyControl.click();
    for (let attempt = 0; attempt < 40; attempt++) {
      await new Promise(resolve => setTimeout(resolve, 250));
      if (hasHistoryContent()) return;
    }
    throw new Error("Etapa navegación: UCharts no mostró el historial después de pulsar 'Historial'.");
  }

  function setLoading(loading) {
    if (!btn) return;
    const spinner = btn.querySelector('.sync-spinner');
    const icon = btn.querySelector('.sync-icon');
    if (loading) {
      spinner.style.display = 'block';
      icon.style.display = 'none';
      btn.disabled = true;
    } else {
      spinner.style.display = 'none';
      icon.style.display = 'block';
      btn.disabled = false;
    }
  }

  let autoSyncInterval = null;

  function startAutoSync() {
    if (autoSyncInterval) return;
    // Ejecutar inmediatamente la comprobación de fondo
    checkAndSyncBackground();
    autoSyncInterval = setInterval(checkAndSyncBackground, 15000);
  }

  // Montar inmediatamente y reintentar mientras la SPA termina de cargar.
  // El try/catch evita que un fallo transitorio impida futuros reintentos.
  function safeInit() {
    try {
      init();
    } catch (error) {
      console.error('[UCharts] Error al montar el panel:', error);
    }
  }
  safeInit();
  setInterval(safeInit, 1000);

  function stopAutoSync() {
    if (autoSyncInterval) {
      clearInterval(autoSyncInterval);
      autoSyncInterval = null;
    }
  }

  // Reconciliación diaria automática de "Registro Continuo". A diferencia de
  // checkAndSyncBackground (que sólo actúa si la pestaña YA está en
  // Historial/Posiciones y nunca scrollea), esta función navega ella misma a
  // Historial una vez por día calendario y sí scrollea (vía maxDaysBack en
  // syncHistory) lo necesario para cubrir los últimos días — así "Registro
  // Continuo" queda al día sin que el usuario tenga que acordarse de abrir
  // Historial ni de clickear "Sincronizar Día" a mano.
  let dailyFullSyncRunning = false;

  async function runDailyFullHistorySync() {
    if (!autoSyncEnabled) return;
    if (!WEBHOOK_URL || WEBHOOK_URL.includes("TU_WEBHOOK_URL_AQUÍ")) return;
    if (dailyFullSyncRunning || !btn || btn.disabled) return;

    const todayKey = new Date().toDateString();
    if (localStorage.getItem('ucharts_full_daysync_date') === todayKey) return;

    dailyFullSyncRunning = true;
    // setLoading(true) también pone btn.disabled=true: de paso evita que el
    // chequeo de fondo de 15s (checkAndSyncBackground) o un click manual se
    // pisen con esta corrida mientras está en curso.
    setLoading(true);
    statusIndicator.style.backgroundColor = '#facc15';
    statusIndicator.style.boxShadow = '0 0 8px #facc15';

    try {
      await ensureHistoryView();
      const result = await syncHistory(true, { maxDaysBack: 3 });
      if (result && result.ok) {
        localStorage.setItem('ucharts_full_daysync_date', todayKey);
        console.log(`✅ [AutoSync diario] Registro Continuo reconciliado (${result.count} operaciones revisadas).`);
      } else {
        console.warn('⚠️ [AutoSync diario] No se pudo completar, se reintentará en el próximo chequeo (10 min):', result && result.error);
      }
    } catch (error) {
      console.warn('⚠️ [AutoSync diario] Error, se reintentará en el próximo chequeo (10 min):', error);
    } finally {
      navigateToTab('Posiciones');
      setLoading(false);
      statusIndicator.style.backgroundColor = '';
      statusIndicator.style.boxShadow = '';
      dailyFullSyncRunning = false;
    }
  }

  async function checkAndSyncBackground() {
    if (btn.disabled) return;

    const currentUrl = window.location.href;
    const isHistoryPage = currentUrl.includes('/history') || currentUrl.includes('/historial') || currentUrl.includes('/balances');
    const isPositionsPage = currentUrl.includes('/positions') || currentUrl.includes('/posiciones');

    try {
      if (isHistoryPage) {
        let allElems = getAllElements(document);
        let descElements = allElems.filter(el => {
          let t = (el.textContent || "").trim();
          let hasKeywords = (t.includes("Comprar") || t.includes("Vender") || t.includes("Compra") || t.includes("Venta") || t.includes("Buy") || t.includes("Sell")) &&
                            (t.includes("options") || t.includes("option") || t.includes("opción") || t.includes("opciones") || t.includes("contrato"));
          if (!hasKeywords) return false;
          let childHasKeywords = Array.from(el.children).some(child => {
            let ct = (child.textContent || "").trim();
            return (ct.includes("Comprar") || ct.includes("Vender") || ct.includes("Compra") || ct.includes("Venta") || ct.includes("Buy") || ct.includes("Sell")) &&
                   (ct.includes("options") || ct.includes("option") || ct.includes("opción") || ct.includes("opciones") || ct.includes("contrato"));
          });
          return !childHasKeywords;
        });

        if (descElements.length > 0) {
          let firstTradeText = descElements[0].textContent.trim();
          let rowData = findRowData(descElements[0]);
          if (rowData && rowData.date) {
            let key = `${firstTradeText}|${rowData.date}`;
            let lastSynced = localStorage.getItem('ucharts_last_history_trade');
            if (key !== lastSynced) {
              console.log("🔄 [AutoSync] Nueva operación detectada en el historial. Sincronizando...");
              statusIndicator.style.backgroundColor = '#facc15';
              statusIndicator.style.boxShadow = '0 0 8px #facc15';

              setLoading(true);
              await syncHistory(true);
              setLoading(false);

              localStorage.setItem('ucharts_last_history_trade', key);
              statusIndicator.style.backgroundColor = '';
              statusIndicator.style.boxShadow = '';
            }
          }
        }
      } else if (isPositionsPage) {
        let allElems = getAllElements(document);
        let descElements = allElems.filter(el => {
          let t = (el.textContent || "").trim();
          let hasKeywords = (t.includes("Call") || t.includes("Put")) && /\d+/.test(t) &&
                            !t.includes("Historial") && !t.includes("Monto") && !t.includes("Posiciones") && !t.includes("Descripción");
          if (!hasKeywords) return false;
          let childHasKeywords = Array.from(el.children).some(child => {
            let ct = (child.textContent || "").trim();
            return (ct.includes("Call") || ct.includes("Put")) && /\d+/.test(ct);
          });
          return !childHasKeywords;
        });

        let positionsHash = descElements.map(el => el.textContent.trim()).join('||');
        let lastHash = localStorage.getItem('ucharts_last_positions_hash');

        if (positionsHash !== lastHash && descElements.length > 0) {
          console.log("🔄 [AutoSync] Cambio detectado en posiciones activas. Sincronizando...");
          statusIndicator.style.backgroundColor = '#facc15';
          statusIndicator.style.boxShadow = '0 0 8px #facc15';

          setLoading(true);
          await syncActivePositions(true);
          setLoading(false);

          localStorage.setItem('ucharts_last_positions_hash', positionsHash);
          statusIndicator.style.backgroundColor = '';
          statusIndicator.style.boxShadow = '';
        }
      }
    } catch (e) {
      console.error("[AutoSync] Error:", e);
    }
  }

  // ----------------------------------------------------
  // HELPERS COMUNES DE TRAVERSACIÓN DOM (Shadow DOM e iFrames)
  // ----------------------------------------------------
  function getAllElements(root = document) {
    let elements = [];
    function traverse(node) {
      if (!node) return;
      if (node.nodeType === Node.ELEMENT_NODE) {
        elements.push(node);
        if (node.shadowRoot) traverse(node.shadowRoot);
        if (node.tagName === 'IFRAME') {
          try {
            if (node.contentDocument) traverse(node.contentDocument);
          } catch (e) {}
        }
      }
      let child = node.firstChild;
      while (child) {
        traverse(child);
        child = child.nextSibling;
      }
    }
    traverse(root);
    return elements;
  }

  function getParent(node) {
    if (!node) return null;
    return node.parentNode || node.host || null;
  }

  // ----------------------------------------------------
  // FUNCIÓN 1: Sincronizar Posiciones Activas (Abiertas)
  // ----------------------------------------------------
  async function syncActivePositions(isSilent = false) {
    let allElems = getAllElements(document);

    let descElements = allElems.filter(el => {
      let t = (el.textContent || "").trim();
      let hasKeywords = (t.includes("Call") || t.includes("Put")) && /\d+/.test(t) &&
                        !t.includes("Historial") && !t.includes("Monto") && !t.includes("Posiciones") && !t.includes("Descripción");
      if (!hasKeywords) return false;

      let childHasKeywords = Array.from(el.children).some(child => {
        let ct = (child.textContent || "").trim();
        return (ct.includes("Call") || ct.includes("Put")) && /\d+/.test(ct);
      });
      return !childHasKeywords;
    });

    if (descElements.length === 0) {
      if (!isSilent) alert("⚠️ No se encontraron posiciones abiertas activas en la pantalla.");
      return;
    }

    let positions = [];
    descElements.forEach(descEl => {
      let contratacion = descEl.textContent.trim().replace(/\s+/g, ' ');

      let parent = descEl.parentElement;
      let cantidad = 1;
      let precioCompra = 0.0;
      let safety = 0;

      while (parent && safety < 10) {
        let children = getAllElements(parent);
        let priceMatch = (parent.textContent || "").match(/\$[\d,.]+/);
        if (priceMatch) {
          precioCompra = parseFloat(priceMatch[0].replace(/[^\d.]/g, ''));
          for (let child of children) {
            let val = parseInt((child.textContent || "").trim());
            if (!isNaN(val) && val.toString() === (child.textContent || "").trim() && val > 0 && val < 5000) {
              cantidad = val;
              break;
            }
          }
          break;
        }
        parent = getParent(parent);
        safety++;
      }

      let regex = /(\S+)\s+(.*?)\s+(Call|Put)\s+([\d.]+)/i;
      let match = contratacion.match(regex);

      if (match) {
        let ticker = match[1];
        positions.push({
          action: "buy",
          ticker: ticker,
          expiry: match[2],
          type: match[3].toUpperCase(),
          strike: parseFloat(match[4]),
          quantity: cantidad,
          price: precioCompra,
          strategy: "Manual UCharts"
        });
      }
    });

    if (positions.length === 0) {
      if (!isSilent) alert("⚠️ No se pudieron extraer posiciones abiertas válidas.");
      return;
    }

    let successCount = 0;
    for (let pos of positions) {
      let ok = await sendWebhook(pos);
      if (ok) successCount++;
    }

    if (!isSilent) {
      alert(`¡Sincronización de posiciones completada!\nSe registraron ${successCount} de ${positions.length} posiciones activas.`);
    }
  }

  // =========================================================================
  // BOT AUTOMÁTICO - FUNCIONES DE AUTOMATIZACIÓN DE TRADING
  // =========================================================================

  let lastTraderError = "";

  // Lock global: true mientras executeOrder() o closePositionByCard() están
  // interactuando con el formulario de Negociar/Vender. Evita que dos flujos
  // (p.ej. la compra en curso y el auto-TP programado de una compra anterior)
  // toquen el DOM del formulario al mismo tiempo y se pisen entre sí.
  let isTradeFormBusy = false;

  async function waitForTradeFormFree(timeoutMs = 60000) {
    const deadline = Date.now() + timeoutMs;
    while (isTradeFormBusy && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 300));
    }
    return !isTradeFormBusy;
  }

  function traderFail(stage, detail) {
    lastTraderError = `${stage}: ${detail}`;
    console.error(`[Auto-Trader] ${lastTraderError}`);
    return false;
  }

  function activeTradeRoot() {
    const roots = Array.from(document.querySelectorAll('form, main, [role="tabpanel"]'))
      .filter(root => {
        const text = (root.innerText || '').toLowerCase();
        return text.includes('contratos') &&
          (text.includes('tipo de orden') || text.includes('order type'));
      });
    return roots.find(isUsableControl) || document;
  }

  const REVIEW_LABELS = ['revisar orden', 'review order', 'enviar orden', 'submit order', 'revisar', 'review', 'enviar', 'submit'];
  const CONFIRM_LABELS = ['confirmar orden', 'confirm order', 'confirmar', 'confirm', 'enviar orden', 'submit order', 'enviar', 'submit', 'transmitir orden', 'transmit order', 'transmitir', 'transmit'];

  async function waitForReviewButton(timeoutMs = 8000) {
    const button = await waitForActionButton(REVIEW_LABELS, timeoutMs, activeTradeRoot());
    if (!button) throw new Error('No se encontró un botón Revisar / Enviar orden visible y habilitado en el formulario activo.');
    return button;
  }

  // Lee el "Monto de la operación" del diálogo de Resumen de la orden (el que
  // aparece tras hacer click en "Revisar orden", antes de Confirmar). Se debe
  // llamar ANTES de confirmar, porque una vez confirmada la orden el diálogo
  // se cierra y ese dato deja de estar disponible. Devuelve el monto total
  // (no dividido por contratos) o null si no se pudo leer.
  function extractOrderSummaryAmount() {
    const labels = Array.from(document.querySelectorAll('div, span, p'));
    const amountLabel = labels.find(el => {
      const t = (el.textContent || '').trim();
      return t === 'Monto de la operación' || t === 'Order value' || t === 'Estimated cost';
    });
    if (!amountLabel) return null;
    const row = amountLabel.parentElement;
    if (!row) return null;
    const match = (row.textContent || '').match(/\$\s*([\d,]+\.\d{2})/);
    if (!match) return null;
    return parseFloat(match[1].replace(/,/g, ''));
  }

  function setNativeInputValue(input, value) {
    const descriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
    if (descriptor && descriptor.set) descriptor.set.call(input, value);
    else input.value = value;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  // Cambia el "Tipo de orden" (Mercado/Límite) y VERIFICA que el cambio se
  // haya aplicado antes de continuar. El bug original en este punto: se
  // clickeaba una opción del dropdown buscando entre 'div, li' (mismo bug
  // de contenedor-en-vez-de-elemento-real que el de Revisar/Confirmar), y
  // el código seguía de largo sin comprobar si el valor realmente cambió.
  // Resultado: la orden quedaba en Mercado y se ejecutaba al instante al
  // precio de mercado, ignorando por completo el % de Take Profit
  // configurado en el panel.
  async function setOrderType(desiredLabels) {
    const orderTypeLabel = Array.from(document.querySelectorAll('div, label, span')).find(el => {
      const t = (el.textContent || "").trim();
      return t === "Tipo de orden" || t === "Order type";
    });
    if (!orderTypeLabel) return traderFail('Tipo de orden', 'No se encontró la etiqueta "Tipo de orden".');
    const parent = orderTypeLabel.parentElement;

    const select = parent.querySelector('select');
    if (select) {
      if (!desiredLabels.includes(select.value)) {
        const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set;
        if (nativeSetter) nativeSetter.call(select, desiredLabels[0]); else select.value = desiredLabels[0];
        select.dispatchEvent(new Event('change', { bubbles: true }));
        await new Promise(resolve => setTimeout(resolve, 400));
      }
      return desiredLabels.includes(select.value)
        ? true
        : traderFail('Tipo de orden', `El selector nativo no aceptó el valor "${desiredLabels[0]}".`);
    }

    const dropdown = parent.querySelector('div[role="button"], button, [role="combobox"]');
    if (!dropdown) return traderFail('Tipo de orden', 'No se encontró el selector visible de Tipo de orden.');

    if (desiredLabels.includes((dropdown.textContent || '').trim())) return true; // ya está en el valor deseado

    // Orden fijo real de las opciones en este listbox de UCharts.
    const OPTION_ORDER = ['Mercado', 'Límite', 'Stop'];
    const targetIndex = OPTION_ORDER.findIndex(label => desiredLabels.includes(label));

    for (let attempt = 0; attempt < 3; attempt++) {
      superClick(dropdown);
      await new Promise(resolve => setTimeout(resolve, 500));

      // Confirmado probando en vivo contra UCharts: clickear la opción (con
      // .click() simple o con la secuencia completa de eventos pointer/mouse)
      // sólo resalta visualmente la opción pero NUNCA confirma la selección
      // en este listbox puntual — se queda con "Mercado" tildado sin importar
      // cuántas veces se reintente. La navegación por teclado (flechas +
      // Enter) sí selecciona de verdad. Por eso es el método principal acá;
      // el click queda sólo como intento adicional si el teclado fallara.
      if (targetIndex >= 0) {
        for (let i = 0; i < OPTION_ORDER.length; i++) {
          dropdown.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', code: 'ArrowUp', bubbles: true, cancelable: true }));
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        for (let i = 0; i < targetIndex; i++) {
          dropdown.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', code: 'ArrowDown', bubbles: true, cancelable: true }));
          await new Promise(resolve => setTimeout(resolve, 100));
        }
        dropdown.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
        await new Promise(resolve => setTimeout(resolve, 500));
        if (desiredLabels.includes((dropdown.textContent || '').trim())) return true;
      }

      // Sólo elementos realmente clickeables y visibles; prioriza texto exacto
      // y, entre varios matches, el más específico (menos descendientes).
      const norm = el => (el.textContent || '').trim();
      const optionCandidates = Array.from(document.querySelectorAll(
        '[role="option"], [role="listbox"] li, [role="listbox"] button, [role="listbox"] div, li, button, div, span'
      )).filter(isUsableControl);
      let option = optionCandidates.find(el => desiredLabels.includes(norm(el)) && el.children.length === 0);
      if (!option) {
        option = optionCandidates
          .filter(el => desiredLabels.includes(norm(el)))
          .sort((a, b) => a.querySelectorAll('*').length - b.querySelectorAll('*').length)[0];
      }

      if (option) {
        superClick(option);
        await new Promise(resolve => setTimeout(resolve, 500));
        if (desiredLabels.includes((dropdown.textContent || '').trim())) return true;
      } else {
        document.body.click(); // cerrar el dropdown para poder reintentar limpio
        await new Promise(resolve => setTimeout(resolve, 300));
      }
    }
    return traderFail('Tipo de orden', `No se pudo confirmar el cambio a "${desiredLabels[0]}" tras 3 intentos.`);
  }

  // Navega dinámicamente a la pestaña correspondiente en UCharts
  function navigateToTab(tabName) {
    const buttons = Array.from(document.querySelectorAll('button, a, span, div'));
    const target = buttons.find(el => {
      const t = (el.textContent || "").trim();
      return t === tabName || t.toLowerCase() === tabName.toLowerCase() ||
             (tabName === 'Negociar' && (t === 'Trade' || t === 'Negociar' || t === 'Tab negociar' || t.includes('tab-trade'))) ||
             (tabName === 'Posiciones' && (t === 'Positions' || t === 'Posiciones' || t.includes('tab-positions'))) ||
             (tabName === 'Cuenta' && (t === 'Account' || t === 'Cuenta' || t === 'Resumen de la cuenta'));
    });

    if (target) {
      target.click();
      return true;
    }

    // Fallback: Modificar la URL del navegador directamente
    const currentUrl = window.location.href;
    const baseUrl = currentUrl.split('?')[0].split('#')[0];
    if (tabName === 'Negociar') {
      window.location.href = baseUrl + "?tab=trade";
      return true;
    } else if (tabName === 'Posiciones') {
      window.location.href = baseUrl + "?tab=positions";
      return true;
    } else if (tabName === 'Cuenta') {
      window.location.href = baseUrl + "?tab=account";
      return true;
    }
    return false;
  }

  // Selecciona el activo en el formulario de negociación
  async function selectAsset(ticker) {
    const symbolInputSelector = [
      'input[placeholder*="símbolo" i]',
      'input[placeholder*="simbolo" i]',
      'input[placeholder*="symbol" i]',
      'input[placeholder*="buscar" i]',
      'input[placeholder*="busca" i]'
    ].join(', ');
    const isVisible = el => Boolean(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));

    let searchInput = Array.from(document.querySelectorAll(symbolInputSelector)).find(isVisible);
    if (!searchInput) {
      const labels = Array.from(document.querySelectorAll('label, span, div, p')).filter(isVisible);
      const symbolLabel = labels.find(el => /^(símbolo|simbolo|symbol)\s*:?$/i.test((el.textContent || "").trim()));
      const scope = symbolLabel && (symbolLabel.closest('form, section, [role="group"], div') || symbolLabel.parentElement);

      const trigger = scope && (
        scope.querySelector('[role="combobox"], [role="button"], button, select, input') ||
        scope.querySelector('div[class*="select" i], div[class*="dropdown" i]') ||
        (scope.nextElementSibling && (
          scope.nextElementSibling.querySelector('[role="combobox"], [role="button"], button, select, input') ||
          scope.nextElementSibling
        ))
      );

      if (!trigger) return traderFail('Selección de símbolo', 'No se encontró el selector visible de símbolo en PaperMoney.');
      trigger.click();
      await new Promise(resolve => setTimeout(resolve, 600));
      searchInput = Array.from(document.querySelectorAll(symbolInputSelector)).find(isVisible);
    }

    if (!searchInput) return traderFail('Selección de símbolo', 'El selector abrió, pero no apareció el campo "Busca por símbolo o nombre…".');
    setNativeInputValue(searchInput, ticker);
    searchInput.focus();
    await new Promise(resolve => setTimeout(resolve, 800));

    const candidates = Array.from(document.querySelectorAll('[role="option"], [role="listbox"] button, [role="dialog"] button, li, button, div, span'))
      .filter(isVisible);
    const option = candidates.find(el => {
      const text = (el.textContent || "").trim().replace(/\s+/g, ' ');
      return text === ticker || text.startsWith(ticker + ' ') || text.startsWith(ticker + '\n') || text.startsWith(ticker + ' -');
    });
    if (!option) return traderFail('Selección de símbolo', `Se buscó ${ticker}, pero no apareció una sugerencia coincidente.`);

    option.click();
    await new Promise(resolve => setTimeout(resolve, 600));

    let stillOpen = Array.from(document.querySelectorAll(symbolInputSelector)).some(isVisible);
    if (stillOpen) {
      // Intentar cerrar pulsando Escape
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await new Promise(resolve => setTimeout(resolve, 500));
      stillOpen = Array.from(document.querySelectorAll(symbolInputSelector)).some(isVisible);
      if (stillOpen) {
        console.warn(`[Tester] El buscador de símbolos sigue abierto, pero continuaremos.`);
      }
    }
    return true;
  }

  // Selecciona el contrato de opción basándose en el tipo y perfil de DTE
  async function selectOptionContract(type, dteProfile, targetExpiryKey = null) {
    // La etiqueta y el botón no siempre comparten el mismo padre directo.
    // Buscar sólo etiquetas visibles y subir por el contenedor del campo evita
    // seleccionar una etiqueta oculta o un panel antiguo de la SPA.
    const labels = Array.from(document.querySelectorAll('div, label, span'))
      .filter(el => {
        const text = (el.textContent || '').trim();
        const rect = el.getBoundingClientRect();
        return (text === 'Opción' || text === 'Option') &&
          rect.width > 0 && rect.height > 0;
      });
    let dropdownTrigger = null;
    for (const optionLabel of labels) {
      let container = optionLabel;
      for (let level = 0; level < 4 && container; level++, container = container.parentElement) {
        const candidate = Array.from(container.querySelectorAll(
          'button, input, select, [role="button"]'
        )).find(el => {
          const rect = el.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0 && !el.disabled &&
            el.getAttribute('aria-disabled') !== 'true';
        });
        if (candidate) {
          dropdownTrigger = candidate;
          break;
        }
      }
      if (dropdownTrigger) break;
    }
    if (!dropdownTrigger) return traderFail('Selección de contrato', 'No se encontró el selector desplegable de la Cadena de opciones.');

    let dialog = Array.from(document.querySelectorAll('[role="dialog"]')).find(el => 
      (el.textContent || '').includes('Cadena de opciones')
    );
    let isAlreadyOpen = !!dialog;

    if (!isAlreadyOpen) {
      dropdownTrigger.click();
      await new Promise(resolve => setTimeout(resolve, 1500)); // Esperar render de la cadena
      dialog = Array.from(document.querySelectorAll('[role="dialog"]')).find(el => 
        (el.textContent || '').includes('Cadena de opciones')
      );
    }

    if (!dialog) {
      document.body.click();
      return traderFail('Selección de contrato', 'UCharts no abrió la Cadena de opciones.');
    }

    const today = new Date();

    const months = {
      jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, set: 8, oct: 9, nov: 10, dec: 11,
      ene: 0, abr: 3, ago: 7, dic: 11
    };
    let expiryButtons = [];
    const loadDeadline = Date.now() + 6000;
    while (Date.now() < loadDeadline) {
      const rawButtons = Array.from(dialog.querySelectorAll('button'));
      expiryButtons = rawButtons.map(button => {
        const text = (button.textContent || '').trim();
        const match = text.match(/^([a-zA-Z]{3})\s+(\d{1,2})\s+'(\d{2})$/);
        if (!match) return null;
        const month = months[match[1].toLowerCase()];
        if (month === undefined) return null;
        const year = 2000 + parseInt(match[3], 10);
        const day = parseInt(match[2], 10);
        const date = new Date(year, month, day);
        return {
          button,
          date,
          dte: Math.max(0, Math.ceil((date.getTime() - today.getTime()) / 86400000)),
          expiryKey: `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
        };
      }).filter(Boolean);

      if (expiryButtons.length > 0) {
        break;
      }
      await new Promise(resolve => setTimeout(resolve, 200));
    }

    if (expiryButtons.length === 0) {
      document.body.click();
      return traderFail('Selección de contrato', 'No se encontraron vencimientos en la Cadena de opciones.');
    }

    let selectedExpiry;
    if (targetExpiryKey) {
      selectedExpiry = expiryButtons.find(item => item.expiryKey === targetExpiryKey);
    } else {
      // Antes el DTE salía fijo del perfil (CORTO=0, MEDIO=5, LARGO=30), lo
      // que en la práctica siempre terminaba operando opciones que vencen
      // el mismo día (0DTE) salvo que se cambiara de perfil manualmente.
      // Ahora se lee directo del campo "Días de Vencimiento" del panel, que
      // el usuario puede ajustar a cualquier número — se elige igual el
      // vencimiento disponible más cercano a ese valor.
      const dteInputEl = document.getElementById('dte-target');
      const targetDte = dteInputEl
        ? (parseInt(dteInputEl.value, 10) || 0)
        : (dteProfile === 'largo' ? 30 : dteProfile === 'medio' ? 5 : 0);
      selectedExpiry = expiryButtons.sort((a, b) => Math.abs(a.dte - targetDte) - Math.abs(b.dte - targetDte))[0];
    }
    if (!selectedExpiry) {
      document.body.click();
      return traderFail('Selección de contrato', `No existe el vencimiento requerido ${targetExpiryKey || ''}.`);
    }

    superClick(selectedExpiry.button);
    await new Promise(resolve => setTimeout(resolve, 900));

    // La UI actual usa filas [botón CALL, strike, botón PUT], sin las palabras Call/Put.
    // Soporta tanto 3 hijos como 5 hijos en grillas de 5 columnas.
    const rows = Array.from(dialog.querySelectorAll('.grid.grid-cols-5, [class*="grid-cols-5"], .grid')).map(row => {
      let callButton, putButton, strikeText;
      if (row.children.length === 3) {
        callButton = row.children[0].matches('button') ? row.children[0] : row.children[0].querySelector('button');
        putButton = row.children[2].matches('button') ? row.children[2] : row.children[2].querySelector('button');
        strikeText = (row.children[1].textContent || '').trim();
      } else if (row.children.length === 5) {
        callButton = row.children[0].matches('button') ? row.children[0] : row.children[0].querySelector('button');
        putButton = row.children[4].matches('button') ? row.children[4] : row.children[4].querySelector('button');
        strikeText = (row.children[2].textContent || '').trim();
      } else {
        return null;
      }

      const strike = parseFloat(strikeText.replace(/\$/g, '').replace(/\./g, '').replace(',', '.'));
      const prices = button => {
        if (!button) return [];
        const elements = [button, ...Array.from(button.querySelectorAll('*'))];
        return elements.map(el => {
          const value = (el.textContent || '').trim().replace(/\$/g, '').replace(/\s+/g, '');
          return /^\d+(?:[.,]\d+)?$/.test(value) ? parseFloat(value.replace(',', '.')) : NaN;
        }).filter(Number.isFinite);
      };
      const callPrices = prices(callButton);
      const putPrices = prices(putButton);
      if (!callButton || !putButton || !Number.isFinite(strike) || callPrices.length === 0 || putPrices.length === 0) return null;
      const callMid = callPrices.reduce((a, b) => a + b, 0) / callPrices.length;
      const putMid = putPrices.reduce((a, b) => a + b, 0) / putPrices.length;
      return { callButton, putButton, strike, atmScore: Math.abs(callMid - putMid) };
    }).filter(Boolean);

    if (rows.length === 0) {
      document.body.click();
      return traderFail('Selección de contrato', 'La cadena cargó, pero no se reconocieron sus filas CALL/strike/PUT.');
    }

    rows.sort((a, b) => a.atmScore - b.atmScore);
    const selectedRow = rows[0];
    const selectedButton = type.toUpperCase() === 'CALL' ? selectedRow.callButton : selectedRow.putButton;
    superClick(selectedButton);
    return { expiryKey: selectedExpiry.expiryKey, strike: selectedRow.strike };
  }

  // Lleva el flujo a PaperMoney sin recargar la página ni caer en /options.
  // El clic SPA conserva la ejecución del tester para poder enviar ambas órdenes.
  async function openPaperMoneyTab(tabName) {
    if (!window.location.pathname.startsWith('/paper-money')) {
      let paperMoneyLink = document.querySelector('a[href="/paper-money"]');
      if (!paperMoneyLink) {
        paperMoneyLink = Array.from(document.querySelectorAll('a, button, div')).find(el => {
          const t = (el.textContent || "").trim();
          return t === "Paper Money" || t.toLowerCase() === "papermoney";
        });
      }
      if (!paperMoneyLink) return traderFail('Navegación', 'No se encontró el enlace Paper Money.');
      paperMoneyLink.click();

      const deadline = Date.now() + 8000;
      while (!window.location.pathname.startsWith('/paper-money') && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      if (!window.location.pathname.startsWith('/paper-money')) return traderFail('Navegación', 'UCharts no llegó a Paper Money dentro de 8 segundos.');
      await new Promise(resolve => setTimeout(resolve, 500));
    }

    const targetTab = Array.from(document.querySelectorAll('[role="tab"], button')).find(el => {
      const text = (el.textContent || '').trim();
      return text === tabName || (tabName === 'Negociar' && text === 'Trade');
    });
    if (!targetTab) return traderFail('Navegación', `No se encontró la pestaña ${tabName} en Paper Money.`);
    superClick(targetTab);
    await new Promise(resolve => setTimeout(resolve, 500));
    return true;
  }

  // Ejecuta una orden completa de compra
  async function executeOrder(ticker, type, dteProfile, quantity, targetExpiryKey = null, options = {}) {
    const { skipAutoTP = false, banderinBucketCheck = false, cardonaBucketCheck = false } = options;
    await waitForTradeFormFree();
    isTradeFormBusy = true;
    let buyResult = null;
    try {
      const navigated = await openPaperMoneyTab('Negociar');
      if (!navigated) return false;

      const optionTabBtn = Array.from(document.querySelectorAll('button, div, span')).find(el => {
        const t = (el.textContent || "").trim();
        const isTabOrLocalBtn = t === "Opciones" || t === "Options";
        if (!isTabOrLocalBtn) return false;
        const isHeaderLink = el.tagName === 'A' || el.closest('header, nav, .header, .nav') || (el.getAttribute('href') && el.getAttribute('href').includes('/options'));
        return !isHeaderLink;
      });
      if (optionTabBtn) superClick(optionTabBtn);
      await new Promise(resolve => setTimeout(resolve, 500));

      const assetSelected = await selectAsset(ticker);
      if (!assetSelected) return false;
      await new Promise(resolve => setTimeout(resolve, 500));

      const optionSelected = await selectOptionContract(type, dteProfile, targetExpiryKey);
      if (!optionSelected) return false;
      await new Promise(resolve => setTimeout(resolve, 600));

      // Tipo de orden a Mercado
      const marketSet = await setOrderType(['Mercado', 'Market']);
      if (!marketSet) {
        console.warn(`[Auto-Trader] No se pudo confirmar Tipo de orden = Mercado (${lastTraderError}). Se continúa igual, ya que suele venir preseleccionado por defecto.`);
      }
      await new Promise(resolve => setTimeout(resolve, 500));

      // Configurar cantidad de contratos
      const contractsLabel = Array.from(document.querySelectorAll('div, label, span')).find(el => {
        const t = (el.textContent || "").trim();
        return t === "Contratos" || t === "Contracts";
      });
      if (contractsLabel) {
        const parent = contractsLabel.parentElement;
        const input = parent.querySelector('input[type="number"], input[type="text"]');
        if (input) {
          setNativeInputValue(input, quantity.toString());
        }
      }
      await new Promise(resolve => setTimeout(resolve, 500));

      // Realizar la compra directa autorizada por el usuario
      console.info(`[Auto-Trader] Iniciando compra directa de ${type} de ${ticker}...`);
      let submitSuccess = false;
      let fillPricePerContract = null;
      let orderAmount = null;
      let reviewBtn = null;
      try {
        reviewBtn = await waitForReviewButton();
      } catch (err) {
        return traderFail('Envío de orden', err.message);
      }

      if (reviewBtn) {
        console.info("[Auto-Trader] Click en Revisar orden...");
        superClick(reviewBtn);

        // El diálogo de confirmación puede montarse en un portal fuera del
        // form original (activeTradeRoot ya no lo contiene), así que la
        // búsqueda del botón Confirmar se hace contra document completo,
        // pero SÓLO entre elementos realmente clickeables (ver
        // findActionButton) para no volver a caer en el bug de clickear
        // un <div> contenedor en vez del <button> real.
        const confirmBtn = await waitForActionButton(CONFIRM_LABELS, 8000, document);

        // Capturar el precio real de fill ANTES de confirmar — el diálogo
        // "Resumen de la orden" muestra el Monto de la operación mientras
        // está abierto; una vez confirmada la orden se cierra y ya no se
        // puede leer. Esto es lo que permite espejar la compra real de
        // UCharts en el ledger interno (Meliora Sim Broker) con el precio
        // correcto en vez de adivinarlo.
        orderAmount = extractOrderSummaryAmount();
        if (orderAmount !== null && quantity > 0) {
          fillPricePerContract = orderAmount / (quantity * 100);
        }

        // Tope Cardona: ningún trade puede invertir más del 10% del capital
        // total de la cuenta (ej. capital $1.000 → máximo $100 por trade).
        // Se valida acá, con el "Monto de la operación" real que muestra el
        // resumen de UCharts, porque es el único momento con el costo exacto
        // de la orden ANTES de confirmarla — así aplica tanto a los botones
        // manuales (Comprar Call/Put) como al Auto-Trader autónomo, que
        // comparten esta misma función. Si no se conoce el capital todavía
        // (no se visitó la pestaña Cuenta en esta sesión), no se bloquea —
        // sólo se avisa por consola — para no frenar el trading por falta de
        // un dato que el propio script todavía no pudo leer.
        const accountBalance = extractAccountBalance();
        if (accountBalance === null) {
          console.warn('[Auto-Trader] Tope del 10% por trade no verificado: todavía no se conoce el capital de la cuenta (visitá la pestaña Cuenta una vez para que se detecte).');
        }
        const maxPerTrade = accountBalance !== null ? accountBalance * 0.10 : null;
        const exceedsCap = orderAmount !== null && maxPerTrade !== null && orderAmount > maxPerTrade;

        if (exceedsCap) {
          console.warn(`[Auto-Trader] Orden BLOQUEADA por tope del 10%: monto $${orderAmount.toFixed(2)} supera el máximo $${maxPerTrade.toFixed(2)} (10% de capital $${accountBalance.toFixed(2)}).`);
          const cancelBtn = findActionButton(['cancelar', 'cancel', 'cerrar', 'close']);
          if (cancelBtn) superClick(cancelBtn);
          return traderFail('Tope de capital (10% Cardona)', `La orden de $${orderAmount.toFixed(2)} supera el 10% del capital ($${maxPerTrade.toFixed(2)} máximo sobre $${accountBalance.toFixed(2)}). No se confirmó la compra.`);
        }

        // Bucket diario de la Bandera Automática: además del tope por trade
        // de arriba, las órdenes que vienen del ciclo de bandera (probe 1C+1P
        // e inversión en la tendencia dominante) no pueden superar lo que
        // queda disponible del bucket reciclable del día (ver sección
        // "BANDERA AUTOMÁTICA" más abajo). El bucket se libera solo cuando
        // esas posiciones se cierran, así que si ya está comprometido en
        // otras posiciones abiertas de la bandera, esta orden se cancela acá
        // en vez de comprometer más capital del que el usuario definió como
        // presupuesto del día.
        if (banderinBucketCheck) {
          const bucketAvailable = getBanderinAvailable();
          const exceedsBucket = orderAmount !== null && orderAmount > bucketAvailable;
          if (exceedsBucket) {
            console.warn(`[Bandera] Orden BLOQUEADA por bucket diario agotado: monto $${orderAmount.toFixed(2)} supera el disponible $${bucketAvailable.toFixed(2)} del bucket de hoy.`);
            const cancelBtn = findActionButton(['cancelar', 'cancel', 'cerrar', 'close']);
            if (cancelBtn) superClick(cancelBtn);
            return traderFail('Bucket diario de Bandera', `La orden de $${orderAmount.toFixed(2)} supera el bucket disponible ($${bucketAvailable.toFixed(2)}) del día. No se confirmó la compra.`);
          }
        }

        // Sub-pool CARDONA del bucket diario compartido: igual criterio que
        // el de Bandera de arriba, pero para el lado real de Cardona
        // (Auto-Trader vía pollPendingTradesFromServer). Antes Cardona no
        // tenía ningún acumulador diario de capital comprometido, sólo el
        // Tope Cardona por orden individual de arriba — este chequeo agrega
        // el acumulador sin tocar ese tope existente (son límites distintos
        // y complementarios).
        if (cardonaBucketCheck) {
          const cardonaBucketAvailable = getCardonaAvailable();
          const exceedsCardonaBucket = orderAmount !== null && orderAmount > cardonaBucketAvailable;
          if (exceedsCardonaBucket) {
            console.warn(`[Auto-Trader] Orden BLOQUEADA por bucket diario de Cardona agotado: monto $${orderAmount.toFixed(2)} supera el disponible $${cardonaBucketAvailable.toFixed(2)} del sub-pool de hoy.`);
            const cancelBtn = findActionButton(['cancelar', 'cancel', 'cerrar', 'close']);
            if (cancelBtn) superClick(cancelBtn);
            return traderFail('Bucket diario de Cardona', `La orden de $${orderAmount.toFixed(2)} supera el bucket disponible ($${cardonaBucketAvailable.toFixed(2)}) del sub-pool de Cardona hoy. No se confirmó la compra.`);
          }
        }

        if (confirmBtn) {
          console.info("[Auto-Trader] Click en Confirmar orden...");
          superClick(confirmBtn);
          await new Promise(resolve => setTimeout(resolve, 1500));
          submitSuccess = true;
        } else {
          console.warn("[Auto-Trader] No se encontró el botón de confirmación visible en pantalla.");
        }
      } else {
        // Intentar clic directo si la UI no tiene confirmación o si es un botón directo
        const directBtn = findActionButton(['comprar', 'buy', 'enviar orden', 'submit order', 'enviar', 'submit', 'transmitir', 'transmit']);
        if (directBtn) {
          superClick(directBtn);
          await new Promise(resolve => setTimeout(resolve, 1200));
          submitSuccess = true;
        }
      }

      if (submitSuccess) {
        console.info(`[Auto-Trader] ${type} de ${ticker} comprado y ejecutado.`);
        buyResult = { expiryKey: optionSelected.expiryKey, ticker, type, quantity, price: fillPricePerContract, amount: orderAmount, strike: optionSelected.strike, submitted: true };
      } else {
        return traderFail('Envío de orden', 'No se encontró el botón para revisar o confirmar la orden de compra.');
      }
    } catch (err) {
      console.error("Error al ejecutar orden:", err);
      return false;
    } finally {
      isTradeFormBusy = false;
    }

    // A partir de acá el lock del formulario ya se soltó (finally de arriba).
    // El Take Profit se coloca de forma SINCRÓNICA (awaited) acá mismo, no en
    // segundo plano como antes — para que quien llamó a executeOrder (p.ej.
    // el bucle autónomo que procesa la cola de señales confirmadas) no pase
    // al siguiente activo hasta que ESTA operación quede completamente
    // cerrada: comprada + con su venta límite de Take Profit ya puesta. Antes
    // el TP se disparaba con un setTimeout de fondo y el bot podía arrancar a
    // comprar el siguiente activo mientras el TP del anterior recién se
    // estaba armando — dos operaciones pisándose entre sí.
    if (!skipAutoTP) {
      console.info(`[Auto-Trader] Esperando a que se asiente la orden antes de colocar el Take Profit...`);
      await new Promise(resolve => setTimeout(resolve, 4000));
      try {
        await colocarOrdenLimiteVentaTakeProfit(ticker);
      } catch (tpErr) {
        console.error('[Auto-Trader] Error al colocar el Take Profit automático:', tpErr);
      }
    }

    return buyResult;
  }

  // Lanzar Tester (1 CALL + 1 PUT) consecutivamente
  async function startTester(ticker) {
    lastTraderError = "";
    console.log(`🚀 [Tester] Comprando 1 CALL + 1 PUT de ${ticker} en cuenta de simulación...`);

    // 1. CALL (skipAutoTP: es sólo un test de conectividad, no tiene sentido
    // disparar un cierre automático de Take Profit sobre esta posición)
    const callResult = await executeOrder(ticker, 'CALL', 'corto', 1, null, { skipAutoTP: true });
    if (!callResult) {
      lastTraderError = `Fallo en CALL. Detalles: ${lastTraderError || 'No se pudo determinar el error.'}`;
      console.error(lastTraderError);
      return false;
    }

    await new Promise(resolve => setTimeout(resolve, 2000));

    // 2. PUT (mismo vencimiento para el tester)
    const putResult = await executeOrder(ticker, 'PUT', 'corto', 1, callResult.expiryKey, { skipAutoTP: true });
    if (!putResult) {
      lastTraderError = `Fallo en PUT. Detalles: ${lastTraderError || 'No se pudo determinar el error.'}`;
      console.error(lastTraderError);
      return false;
    }

    return true;
  }

  // =========================================================================
  // BANDERA AUTOMÁTICA
  // -------------------------------------------------------------------------
  // Compra 1 Call + 1 Put (mismo vencimiento) como "sonda" para detectar la
  // tendencia dominante del mercado. En cuanto una de las dos patas saca al
  // menos 2 puntos porcentuales de ventaja sobre la otra, se considera
  // ganadora: se le coloca el Take Profit automático de siempre y además se
  // compra la cantidad de contratos configurada en "Contratos" en esa misma
  // dirección (también con su Take Profit normal). La pata perdedora NO se
  // toca — queda abierta tal cual, gestionada por el mismo Take
  // Profit/Stop Loss general del panel si algún día los cruza. Resuelto el
  // ciclo, se repite: se lanza una sonda nueva de 1 Call + 1 Put.
  //
  // El presupuesto del día es un "bucket reciclable": al arrancar el día se
  // aparta un % configurable (por defecto 10%) del capital total de la
  // cuenta. Cada compra que hace la Bandera descuenta su costo real de ese
  // bucket, y en cuanto una de esas posiciones se cierra (Take Profit, Stop
  // Loss o cierre manual), su costo se le devuelve al bucket — por eso es
  // "reciclable": no es un gasto acumulado que sólo crece durante el día,
  // sino el capital que hoy está realmente en juego en posiciones abiertas
  // de la Bandera. Importante: como el bucket se calcula sobre lo que cuesta
  // ABRIR cada posición (no sobre la ganancia/pérdida ya realizada al
  // cerrarla), esto no reproduce al centavo la reinversión compuesta de
  // ganancias de la calculadora 10/90 — es la aproximación más fiel que se
  // puede leer de forma confiable desde la pantalla de UCharts en tiempo
  // real, sin depender de que una orden límite ya se haya llenado.
  //
  // (El estado — banderinEnabled, banderinRunning, banderinCycles (Map
  // por-ticker), banderinTrackedPositions, cardonaTrackedPositions,
  // BANDERIN_EDGE_PCT — se declara arriba de todo el archivo, junto a "let
  // panel = null" y compañía; ver el comentario ahí para el porqué.)
  // =========================================================================

  function banderinTodayKey() {
    return new Date().toDateString();
  }

  function banderinUsd(x) {
    return '$' + (Number(x) || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function getDailyBucketPct() {
    const el = document.getElementById('daily-bucket-pct');
    const val = el ? parseFloat(el.value) : NaN;
    return Number.isFinite(val) && val > 0 ? val : 10;
  }

  function getBanderinEnabledSymbols() {
    const el = document.getElementById('banderin-symbols');
    const raw = el && el.value ? el.value : 'SPY';
    const list = raw.split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
    return list.length > 0 ? list : ['SPY'];
  }

  // ==========================================
  // DAILY OPERATIONAL BUCKET (compartido Cardona real + Bandera)
  // ==========================================
  // Un único bucket diario = % configurado del capital de cuenta (por
  // defecto 10%), partido en 2 sub-pools FIJOS de 50/50 (CARDONA y
  // BANDERIN) — nunca un 10% independiente por estrategia, para no
  // multiplicar el techo global (10% -> 20%, 30%, etc. si se suman más
  // estrategias/activos). Cada sub-pool puede usar el espacio libre del
  // otro (préstamo/spillover) cuando éste no lo está usando, y ese espacio
  // se libera apenas el dueño original vuelve a necesitarlo — no hace falta
  // "devolver" nada explícitamente porque la disponibilidad se recalcula en
  // caliente a partir de lo realmente comprometido en cada momento.

  // Calcula (una sola vez por día calendario) el bucket total de hoy a
  // partir del capital de cuenta ya conocido. Si el % configurado cambia a
  // mitad del día, el usuario lo ve reflejado recién al otro día (evita que
  // el bucket "salte" de valor con posiciones ya abiertas a mitad de sesión).
  function ensureDailyBucketForToday() {
    const today = banderinTodayKey();
    const savedDate = localStorage.getItem('ucharts_daily_bucket_date');
    const savedTotal = parseFloat(localStorage.getItem('ucharts_daily_bucket_total') || '0');
    // FIX 3 (heredado del bucket viejo de Bandera): si el bucket de hoy ya
    // había quedado cacheado en $0 (por ejemplo porque extractAccountBalance()
    // todavía no detectaba el capital la primera vez que corrió hoy), no
    // dejar el panel pegado en $0 el resto del día — recalcular igual aunque
    // la fecha coincida, para autocorregirse.
    if (savedDate === today && savedTotal > 0) return;
    const isNewCalendarDay = savedDate !== today;
    const balance = extractAccountBalance();
    const pct = getDailyBucketPct();
    const total = balance !== null ? balance * (pct / 100) : 0;
    localStorage.setItem('ucharts_daily_bucket_date', today);
    localStorage.setItem('ucharts_daily_bucket_total', String(total));
    // Fix (08/09): esto se llama en CADA ciclo de banderinTick (cada 2.5s)
    // mientras el bucket de hoy siga en $0 (por ejemplo, si todavía no se
    // detectó el capital de la cuenta) — antes vaciaba estos dos Map en
    // CADA reintento, no sólo cuando de verdad arrancaba un día nuevo. Eso
    // ya rompía la contabilidad del cupo comprometido, y ahora además hace
    // que isPositionTrackedByBot() deje de "reconocer" una posición que la
    // Bandera acaba de comprar segundos antes — quedaría sin protección de
    // Stop Loss por este mismo bug. Sólo tiene sentido vaciarlos cuando
    // arranca un día calendario nuevo de verdad (las posiciones de ayer ya
    // no cuentan contra el bucket de hoy); reintentar la detección del
    // capital en el mismo día no debe tocarlos.
    if (isNewCalendarDay) {
      banderinTrackedPositions.clear();
      cardonaTrackedPositions.clear();
    }
  }

  function getDailyBucketTotal() {
    ensureDailyBucketForToday();
    return parseFloat(localStorage.getItem('ucharts_daily_bucket_total') || '0');
  }

  // Cupo propio fijo (50/50) de cada sub-pool, antes de aplicar préstamo.
  function getSubPoolOwnShare() {
    return getDailyBucketTotal() / 2;
  }

  function getBanderinCommitted() {
    let sum = 0;
    for (const pos of banderinTrackedPositions.values()) sum += pos.cost;
    return sum;
  }

  function getCardonaCommitted() {
    let sum = 0;
    for (const pos of cardonaTrackedPositions.values()) sum += pos.cost;
    return sum;
  }

  // Disponible real de Bandera: lo que le queda de su propio 5%, más lo que
  // Cardona no esté usando de su propio 5% (préstamo).
  function getBanderinAvailable() {
    const ownShare = getSubPoolOwnShare();
    const ownFree = Math.max(0, ownShare - getBanderinCommitted());
    const borrowedFromCardona = Math.max(0, ownShare - getCardonaCommitted());
    return ownFree + borrowedFromCardona;
  }

  // Disponible real de Cardona (mismo criterio, en espejo).
  function getCardonaAvailable() {
    const ownShare = getSubPoolOwnShare();
    const ownFree = Math.max(0, ownShare - getCardonaCommitted());
    const borrowedFromBanderin = Math.max(0, ownShare - getBanderinCommitted());
    return ownFree + borrowedFromBanderin;
  }

  function updateBanderinBucketUI() {
    const el = document.getElementById('banderin-bucket-status');
    if (!el) return;
    const ownShare = getSubPoolOwnShare();
    el.textContent = `Bandera ${banderinUsd(getBanderinAvailable())}/${banderinUsd(ownShare)} · Cardona ${banderinUsd(getCardonaAvailable())}/${banderinUsd(ownShare)}`;
  }

  // Registro de señales de Bandera para que ninguna cruce del 2% desaparezca
  // en silencio: cada evaluación que cruza el umbral termina anotada acá con
  // su resultado (EXECUTED o BLOCKED_<motivo>), visible en consola y
  // persistida (últimas 200) para poder auditar después qué pasó con cada
  // señal, incluidas las que no se llegaron a ejecutar.
  function banderinLogSignal(ticker, diffPct, resultCode, detail) {
    try {
      const entry = {
        signal_id: `${ticker}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        ts: new Date().toISOString(),
        ticker,
        diffPct: (diffPct !== null && diffPct !== undefined) ? Number(diffPct.toFixed(2)) : null,
        result: resultCode,
        detail: detail || ''
      };
      const key = 'ucharts_banderin_signal_log';
      const log = JSON.parse(localStorage.getItem(key) || '[]');
      log.push(entry);
      while (log.length > 200) log.shift();
      localStorage.setItem(key, JSON.stringify(log));
      console.log(`🚩 [Bandera][${resultCode}] ${ticker}${entry.diffPct !== null ? ' diff=' + entry.diffPct + '%' : ''} — ${detail || ''}`);
    } catch (err) {
      console.warn('[Bandera] No se pudo registrar el log de señal:', err);
    }
  }

  function banderinSetStatus(text) {
    const el = document.getElementById('banderin-status-text');
    if (el) el.textContent = text;
  }

  function banderinRegisterPosition(result, ticker) {
    if (!result || result.amount == null) return;
    const key = `${ticker}-${result.type}-${result.strike}-${result.expiryKey}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    banderinTrackedPositions.set(key, { cost: result.amount, ticker, type: result.type, strike: result.strike, expiryKey: result.expiryKey });
  }

  // Heurística para saber si una posición que la Bandera abrió sigue viva en
  // pantalla: como las tarjetas de Posiciones no traen un id estable, se
  // busca por ticker + tipo (Call/Put) + strike en el texto visible, igual
  // que hace el resto del script para encontrar tarjetas.
  function banderinPositionStillOpen(pos) {
    const allElems = getAllElements(document);
    const typeWord = pos.type === 'CALL' ? 'Call' : 'Put';
    const strikeStr = Number(pos.strike).toFixed(2);
    return allElems.some(el => {
      const t = (el.textContent || '').trim();
      if (t.length > 400) return false; // evitar matchear contenedores enormes de toda la lista
      return t.includes(pos.ticker) && t.includes(typeWord) && (t.includes(strikeStr) || t.includes(String(pos.strike)));
    });
  }

  function banderinReconcileClosedPositions() {
    if (banderinTrackedPositions.size === 0) return;
    const url = window.location.href;
    const onPositionsScreen = url.includes('/positions') || url.includes('/posiciones') || (document.body.innerText || '').includes('PRECIO DE COMPRA');
    if (!onPositionsScreen) return; // sin la lista de posiciones en pantalla no se puede confirmar nada
    for (const [key, pos] of Array.from(banderinTrackedPositions.entries())) {
      if (!banderinPositionStillOpen(pos)) {
        banderinTrackedPositions.delete(key); // se cerró (TP, SL o manual): libera su costo del bucket
      }
    }
  }

  // Equivalentes del registro/reconciliación de Bandera, pero para el
  // sub-pool CARDONA del bucket compartido (hoy Cardona no tenía ningún
  // acumulador diario de capital comprometido, sólo el Tope Cardona por
  // orden individual — ver executeOrder). Reutiliza banderinPositionStillOpen
  // porque esa heurística no depende de qué estrategia abrió la posición.
  function cardonaRegisterPosition(result, ticker) {
    if (!result || result.amount == null) return;
    const key = `${ticker}-${result.type}-${result.strike}-${result.expiryKey}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    cardonaTrackedPositions.set(key, { cost: result.amount, ticker, type: result.type, strike: result.strike, expiryKey: result.expiryKey });
  }

  function cardonaReconcileClosedPositions() {
    if (cardonaTrackedPositions.size === 0) return;
    const url = window.location.href;
    const onPositionsScreen = url.includes('/positions') || url.includes('/posiciones') || (document.body.innerText || '').includes('PRECIO DE COMPRA');
    if (!onPositionsScreen) return;
    for (const [key, pos] of Array.from(cardonaTrackedPositions.entries())) {
      if (!banderinPositionStillOpen(pos)) {
        cardonaTrackedPositions.delete(key);
      }
    }
  }

  // Fix crítico (08/09): monitorPositionsPnL evaluaba CUALQUIER tarjeta
  // visible en Posiciones contra el TP/SL configurado, sin importar si el
  // bot la había comprado él mismo. Eso incluía posiciones viejas, manuales
  // o de pruebas de días anteriores que seguían abiertas en la cuenta —
  // apenas se prendía Auto-Trader, todas las que ya estaban por debajo del
  // Stop Loss se vendían solas en cascada a Mercado, una tras otra. Esta
  // función dice si una tarjeta corresponde a una posición que el bot
  // registró como propia (Cardona o Bandera) en esta misma carga de
  // página — la única fuente de verdad que el bot tiene sobre "esto lo
  // compré yo". Si no matchea ninguna, monitorPositionsPnL la deja
  // tranquila: no la vende ni la evalúa.
  function isPositionTrackedByBot(cardText) {
    const allTracked = [...cardonaTrackedPositions.values(), ...banderinTrackedPositions.values()];
    return allTracked.some(pos => {
      const typeWord = pos.type === 'CALL' ? 'Call' : 'Put';
      const strikeStr = Number(pos.strike).toFixed(2);
      return cardText.includes(pos.ticker) && cardText.includes(typeWord) && (cardText.includes(strikeStr) || cardText.includes(String(pos.strike)));
    });
  }

  // Idempotencia del Auto-Trader de Cardona (sección 8): si la compra se
  // ejecutó con éxito pero el aviso posterior a /mark_executed falla (por
  // ejemplo, un corte de red), el setup_id seguía en la cola del servidor
  // Python y el próximo poll (cada 5s) lo volvía a comprar — una orden
  // duplicada real por la misma señal. Este registro local, independiente
  // del servidor, evita re-ejecutar un setup_id que este mismo navegador ya
  // compró, aunque el aviso de "ya lo marqué" no haya llegado a destino.
  function hasCardonaSetupAlreadyExecuted(setupId) {
    try {
      const done = JSON.parse(localStorage.getItem('ucharts_cardona_executed_setups') || '[]');
      return done.includes(setupId);
    } catch (err) {
      return false;
    }
  }

  function markCardonaSetupExecutedLocally(setupId) {
    try {
      const keyName = 'ucharts_cardona_executed_setups';
      const done = JSON.parse(localStorage.getItem(keyName) || '[]');
      if (!done.includes(setupId)) done.push(setupId);
      while (done.length > 500) done.shift();
      localStorage.setItem(keyName, JSON.stringify(done));
    } catch (err) {
      console.warn('[Auto-Trader] No se pudo registrar el setup_id ejecutado localmente:', err);
    }
  }

  function banderinFindPositionCard(ticker, type, strike) {
    const typeWord = type === 'CALL' ? 'Call' : 'Put';
    let allElems = getAllElements(document);
    let descElements = allElems.filter(el => {
      let t = (el.textContent || '').trim();
      if (!t.includes(ticker) || !t.includes(typeWord) || !/\d+/.test(t)) return false;
      if (t.includes('Historial') || t.includes('Posiciones') || t.includes('Descripción')) return false;
      let childHasSame = Array.from(el.children).some(c => {
        const ct = (c.textContent || '').trim();
        return ct.includes(ticker) && ct.includes(typeWord);
      });
      return !childHasSame;
    });
    if (descElements.length === 0) return null;
    let target = descElements[0];
    if (strike) {
      const strikeStr = Number(strike).toFixed(2);
      const withStrike = descElements.find(el => (el.textContent || '').includes(strikeStr));
      if (withStrike) target = withStrike;
    }
    let card = target.parentElement, safety = 0;
    while (card && !card.textContent.includes('Comprado en') && safety < 6) {
      card = card.parentElement;
      safety++;
    }
    return card;
  }

  function banderinReadCardPnlPct(card) {
    if (!card) return null;
    const cardText = card.textContent.trim().replace(/\s+/g, ' ');
    const matchPct = cardText.match(/([+-])\s*([\d.]+)\s*%/);
    if (!matchPct) return null;
    return parseFloat(matchPct[2]) * (matchPct[1] === '-' ? -1 : 1);
  }

  async function banderinStartProbe(ticker) {
    const bucketAvail = getBanderinAvailable();
    if (bucketAvail <= 0) {
      banderinLogSignal(ticker, null, 'BLOCKED_BUCKET_EXHAUSTED', 'Bucket compartido agotado, no se lanza sonda nueva.');
      banderinSetStatus('Bandera activa: bucket del día agotado, esperando espacio libre...');
      return;
    }
    banderinSetStatus(`Bandera activa: lanzando sonda CALL+PUT de ${ticker}...`);
    console.log(`🚩 [Bandera] Lanzando nueva sonda 1 CALL + 1 PUT de ${ticker}...`);

    // Fix (08/09, pedido explícito de Ismael): antes las dos patas de la
    // sonda se compraban con skipAutoTP:true — a propósito, quedaban SIN
    // take profit hasta que una le ganara 2% a la otra. Eso dejaba las
    // posiciones expuestas sin protección mientras "sondeaban", y no
    // coincide con cómo Ismael quiere que trabaje el bot: comprar y ponerle
    // el take profit configurado una sola vez, siempre, sin excepción. Ahora
    // cada pata de la sonda recibe su take profit apenas se compra, igual
    // que cualquier otra compra del panel.
    const callResult = await executeOrder(ticker, 'CALL', 'corto', 1, null, { banderinBucketCheck: true });
    if (!callResult) {
      banderinLogSignal(ticker, null, 'BLOCKED_PROBE_CALL_FAILED', lastTraderError || 'Fallo al comprar la pata CALL de la sonda.');
      console.warn(`[Bandera] Falló la pata CALL de la sonda de ${ticker}:`, lastTraderError);
      banderinSetStatus(`Bandera activa: falló la sonda de ${ticker} (${lastTraderError || 'CALL'})`);
      return;
    }
    banderinRegisterPosition(callResult, ticker);

    await new Promise(resolve => setTimeout(resolve, 2000));

    const putResult = await executeOrder(ticker, 'PUT', 'corto', 1, callResult.expiryKey, { banderinBucketCheck: true });
    if (!putResult) {
      banderinLogSignal(ticker, null, 'BLOCKED_PROBE_PUT_FAILED', lastTraderError || 'Fallo al comprar la pata PUT de la sonda.');
      console.warn(`[Bandera] Falló la pata PUT de la sonda de ${ticker}:`, lastTraderError);
      banderinSetStatus(`Bandera activa: falló la sonda de ${ticker} (${lastTraderError || 'PUT'})`);
      return; // la pata CALL ya comprada queda abierta y sigue contando contra el bucket hasta que se cierre sola
    }
    banderinRegisterPosition(putResult, ticker);

    banderinCycles.set(ticker, {
      ticker,
      expiryKey: callResult.expiryKey,
      call: { strike: callResult.strike },
      put: { strike: putResult.strike },
      phase: 'probing',
      startedAt: Date.now()
    });
    banderinSetStatus(`Bandera activa: sonda de ${ticker} abierta (CALL ${callResult.strike} / PUT ${putResult.strike}), esperando ${BANDERIN_EDGE_PCT}% de diferencia...`);
    console.log(`🚩 [Bandera] Sonda de ${ticker} activa. Esperando ${BANDERIN_EDGE_PCT}% de diferencia de PnL entre las patas.`);
  }

  // Lee el PnL de ambas patas de UN ticker y decide si ya cruzó el umbral —
  // sin ejecutar todavía. Separado de la inversión para poder juntar todas
  // las señales listas de la ronda actual y priorizar por magnitud de
  // diff% antes de gastar el bucket compartido (sección 13: prioridad
  // intra-Bandera cuando varios activos compiten por el mismo sub-pool).
  function banderinReadProbeDiff(ticker) {
    const cycle = banderinCycles.get(ticker);
    if (!cycle) return null;
    const callPct = banderinReadCardPnlPct(banderinFindPositionCard(ticker, 'CALL', cycle.call.strike));
    const putPct = banderinReadCardPnlPct(banderinFindPositionCard(ticker, 'PUT', cycle.put.strike));
    if (callPct === null || putPct === null) {
      banderinLogSignal(ticker, null, 'BLOCKED_DOM_READ_FAIL', 'Todavía no se puede leer el PnL de ambas patas.');
      return null; // reintenta en el próximo tick
    }
    const diff = callPct - putPct;
    if (Math.abs(diff) < BANDERIN_EDGE_PCT) return null; // sin tendencia clara todavía, no es un evento a registrar
    return { ticker, diff, callPct, putPct, winnerType: diff > 0 ? 'CALL' : 'PUT' };
  }

  // Ejecuta la inversión en la pata ganadora de UNA señal ya lista. Se llama
  // en orden de mayor |diff%| primero (ver banderinTick), así que acá el
  // bucket puede haberse agotado por una señal más fuerte de otro ticker —
  // en ese caso queda BLOCKED_BUCKET_EXHAUSTED y el ciclo sigue "probing"
  // para reintentar en el próximo tick, nunca desaparece en silencio.
  async function banderinInvestWinner(signal) {
    const { ticker, diff, callPct, putPct, winnerType } = signal;
    if (!banderinCycles.has(ticker)) return; // ya resuelto por otra vía entre que se leyó y se invierte

    if (getBanderinAvailable() <= 0) {
      banderinLogSignal(ticker, diff, 'BLOCKED_BUCKET_EXHAUSTED', 'Bucket compartido agotado antes de poder invertir en la ganadora.');
      banderinSetStatus(`Bandera activa: ${ticker} bucket agotado, esperando espacio libre...`);
      return; // el ciclo queda "probing"; se reevalúa en el próximo tick
    }

    console.log(`🚩 [Bandera] ${ticker}: tendencia dominante ${winnerType} (CALL ${callPct.toFixed(2)}% vs PUT ${putPct.toFixed(2)}%). Se invierte en la ganadora y la perdedora queda abierta sin tocar.`);
    banderinSetStatus(`Bandera activa: ${ticker} tendencia ${winnerType} detectada, invirtiendo...`);

    // Fix (08/09): antes acá se llamaba a colocarOrdenLimiteVentaTakeProfit
    // de nuevo sobre la pata ganadora — pero ahora banderinStartProbe ya le
    // puso su take profit apenas se compró (ver fix ahí). Volver a llamarlo
    // acá era un segundo intento de "Vender" sobre una posición que ya
    // podía tener una orden límite pendiente puesta — exactamente lo que
    // Ismael pidió evitar (el take profit se pone UNA sola vez por compra).

    // Comprar la cantidad configurada en "Contratos" en la dirección ganadora
    const cycle = banderinCycles.get(ticker);
    const qtyInput = document.getElementById('trader-qty');
    const qty = qtyInput ? (parseInt(qtyInput.value, 10) || 1) : 1;
    const investResult = await executeOrder(ticker, winnerType, 'corto', qty, cycle.expiryKey, { banderinBucketCheck: true });
    if (investResult) {
      banderinRegisterPosition(investResult, ticker);
      banderinLogSignal(ticker, diff, 'EXECUTED', `Invertidos ${qty} contrato(s) de ${winnerType}.`);
      console.log(`🚩 [Bandera] ${ticker}: invertidos ${qty} contrato(s) de ${winnerType} siguiendo la tendencia dominante (con Take Profit ya colocado).`);
      banderinSetStatus(`Bandera activa: ${ticker} invertidos ${qty} ${winnerType}, reiniciando ciclo...`);
    } else {
      banderinLogSignal(ticker, diff, 'BLOCKED_ORDER_FAILED', lastTraderError || 'Fallo desconocido al ejecutar la orden.');
      console.warn(`[Bandera] ${ticker}: no se pudo invertir en la tendencia dominante (${winnerType}): ${lastTraderError}`);
      banderinSetStatus(`Bandera activa: ${ticker} no se pudo invertir (${lastTraderError || winnerType}), reiniciando ciclo...`);
    }

    // 3) Ciclo resuelto para este ticker: en el próximo tick se lanza una
    // sonda nueva de ESTE mismo activo (repite el ciclo virtuoso), salvo que
    // mientras tanto se haya apagado la Bandera o se lo haya sacado de la
    // lista de activos habilitados.
    banderinCycles.delete(ticker);
  }

  async function banderinTick() {
    if (!autoTraderMasterOn) return; // interruptor maestro: pausado por el usuario
    if (banderinRunning) return;
    if (isTradeFormBusy || isClosingPosition || isAutoTraderRunning) return;

    if (!banderinEnabled && banderinCycles.size === 0) {
      banderinReconcileClosedPositions();
      cardonaReconcileClosedPositions();
      updateBanderinBucketUI();
      return;
    }

    ensureDailyBucketForToday();
    banderinReconcileClosedPositions();
    cardonaReconcileClosedPositions();
    updateBanderinBucketUI();

    banderinRunning = true;
    try {
      const url = window.location.href;
      if (!url.includes('/positions') && !url.includes('/posiciones')) {
        navigateToTab('Posiciones');
        await new Promise(resolve => setTimeout(resolve, 1200));
      }

      // 1) Evaluar todos los ciclos en curso y juntar los que ya cruzaron el
      // umbral, para invertir primero en el de mayor |diff%| (prioridad
      // intra-Bandera cuando varios activos compiten por el mismo bucket).
      const readySignals = [];
      for (const ticker of Array.from(banderinCycles.keys())) {
        const signal = banderinReadProbeDiff(ticker);
        if (signal) readySignals.push(signal);
      }
      readySignals.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff));
      for (const signal of readySignals) {
        await banderinInvestWinner(signal);
      }

      // 2) Lanzar sondas nuevas en los símbolos habilitados que todavía no
      // tienen un ciclo en curso, mientras la Bandera esté activa y quede
      // bucket disponible. Sin ningún ticker hardcodeado (sección 3).
      if (banderinEnabled) {
        for (const ticker of getBanderinEnabledSymbols()) {
          if (banderinCycles.has(ticker)) continue;
          if (getBanderinAvailable() <= 0) {
            banderinSetStatus('Bandera activa: bucket del día agotado, esperando espacio libre...');
            break;
          }
          await banderinStartProbe(ticker);
        }
      }
    } catch (err) {
      console.error('[Bandera] Error inesperado en el ciclo:', err);
    } finally {
      banderinRunning = false;
    }
  }

  // Cierra una posición abierta haciendo clic en su tarjeta y confirmando
  // Cierra una posición abierta haciendo clic en su tarjeta y configurando la venta límite
  async function closePositionByCard(cardElement, closeReason = 'TP') {
    await waitForTradeFormFree();
    isTradeFormBusy = true;
    try {
      // 1. Extraer precio de compra original de la tarjeta (columna "PRECIO DE COMPRA")
      const cardText = cardElement.textContent.trim().replace(/\s+/g, ' ');
      const priceMatches = cardText.match(/\$\s*([\d,.]+)/g);
      let buyPrice = 0.0;
      if (priceMatches && priceMatches.length > 0) {
        // El primer precio con "$" en la fila representa siempre el precio de compra
        buyPrice = parseFloat(priceMatches[0].replace('$', '').replace(',', '').trim()) || 0.0;
      }

      // Sin un precio de compra válido no hay forma de calcular un precio
      // objetivo confiable: abortar en vez de arriesgar una venta sin control
      // de precio (podría terminar ejecutándose a Mercado).
      if (buyPrice <= 0) {
        console.error('[Auto-Trader] Venta abortada: no se pudo leer el precio de compra de la tarjeta.');
        return false;
      }

      // 2. Hacer clic en el botón de vender
      const sellBtn = findActionButton(['vender', 'sell'], cardElement) ||
        cardElement.querySelector('button, [role="button"]'); // Fallback

      if (!sellBtn) return false;
      superClick(sellBtn);
      await new Promise(resolve => setTimeout(resolve, 1000));

      // ------------------------------------------------------------------
      // Fix crítico: antes esta función SIEMPRE calculaba el precio con la
      // fórmula de Take Profit (buyPrice * (1 + tp%)), sin importar si el
      // cierre lo disparó el Take Profit o el Stop Loss. Cuando lo disparaba
      // el Stop Loss (posición ya en pérdida), terminaba poniendo una venta
      // Límite a un precio MÁS ALTO que el de compra — en una posición que
      // ya está por debajo, ese precio no se alcanza nunca. La orden
      // quedaba ahí sentada sin ejecutarse jamás, y el Stop Loss no
      // protegía nada en absoluto, aunque el bot reportara "cierre exitoso"
      // (porque sí logró CONFIRMAR la orden, sólo que esa orden nunca iba a
      // llenarse).
      //
      // Ahora, si el cierre es por Stop Loss, se vende a MERCADO — salida
      // inmediata garantizada, que es lo que un stop loss necesita — y no
      // se toca Tipo de orden ni Precio en absoluto (Mercado es el default).
      // El cálculo de precio Límite sólo aplica al Take Profit.
      // ------------------------------------------------------------------
      if (closeReason === 'SL') {
        console.log(`[Auto-Trader] Cierre por Stop Loss: vendiendo a Mercado para salida inmediata (sin esperar un precio límite).`);
      } else {
        // Obtener el % de ganancia pretendido (Take Profit)
        const tpPct = parseFloat(document.getElementById('tp-pct-val').value) || 15.0;
        const targetPrice = buyPrice * (1 + tpPct / 100.0);

        console.info(`[Auto-Trader] Precio de compra detectado: $${buyPrice}. TP%: ${tpPct}%. Precio Objetivo Venta: $${targetPrice.toFixed(2)}`);

        // Capturar los inputs numéricos/texto que YA existen en el formulario
        // ANTES de cambiar a Límite. El campo "Precio" recién se identifica
        // más abajo por DIFERENCIA contra este set — ver el porqué en el
        // comentario del paso 4.
        const inputsBeforeLimit = new Set(Array.from(document.querySelectorAll('input[type="number"], input[type="text"]')));

        // 3. Cambiar Tipo de orden a Límite — esto es OBLIGATORIO: si falla,
        // hay que abortar la venta en vez de dejar que siga en Mercado y
        // se ejecute al instante ignorando el % de Take Profit configurado.
        const limitSet = await setOrderType(['Límite', 'Limit']);
        if (!limitSet) {
          console.error(`[Auto-Trader] Venta abortada: no se pudo cambiar Tipo de orden a Límite (${lastTraderError}). Se evita vender a Mercado ignorando el Take Profit configurado.`);
          document.body.click(); // cerrar cualquier dropdown/dialog que haya quedado abierto
          return false;
        }
        await new Promise(resolve => setTimeout(resolve, 800));

        // 4. Escribir el precio objetivo en el campo Precio — también OBLIGATORIO
        // si calculamos un targetPrice válido; si el campo no aparece, algo
        // salió mal (probablemente seguimos en Mercado) y hay que abortar.
        if (targetPrice > 0) {
          // Fix crítico: ubicar el input por "la etiqueta Precio → su
          // parentElement → el input ahí adentro" resultó poco confiable en
          // esta UI de UCharts — la etiqueta "Precio" comparte un contenedor
          // más amplio con otros campos del formulario (como Contratos), así
          // que ese querySelector agarraba el PRIMER input de esa zona, que
          // terminaba siendo el de Contratos. El bot escribía ahí el precio
          // objetivo (ej. sobreescribía "100" contratos con "4.23"), su propia
          // verificación de "¿el input quedó con el valor esperado?" pasaba
          // igual (porque sí escribió bien en ESE input, sólo que era el
          // equivocado), y el campo Precio real quedaba vacío — exactamente
          // lo que se veía en pantalla: Contratos con el precio adentro, y
          // "Revisar orden" deshabilitado porque Precio nunca se completó.
          //
          // Ahora se ubica por DIFERENCIA: el campo Precio es un input que NO
          // existía en el formulario antes de cambiar a Límite (recién
          // aparece con ese cambio), así que se compara contra el set
          // capturado en el paso 2, ANTES de tocar Tipo de orden.
          const inputsNow = Array.from(document.querySelectorAll('input[type="number"], input[type="text"]'));
          let input = inputsNow.find(el => !inputsBeforeLimit.has(el) && isUsableControl(el));

          // Respaldo por si el diff no encontró nada (p.ej. si el campo ya
          // existía por algún motivo): buscar por la etiqueta como antes.
          if (!input) {
            const priceLabel = Array.from(document.querySelectorAll('div, label, span')).find(el => {
              const t = (el.textContent || "").trim();
              return t === "Precio" || t === "Price" || t === "Precio límite" || t === "Limit price";
            });
            input = priceLabel && priceLabel.parentElement.querySelector('input[type="number"], input[type="text"]');
          }

          if (!input) {
            console.error('[Auto-Trader] Venta abortada: no apareció el campo "Precio" tras cambiar a Límite. Puede que el cambio de tipo de orden no se haya aplicado realmente.');
            document.body.click();
            return false;
          }
          console.log(`[Auto-Trader] Configurando precio de venta limite a: $${targetPrice.toFixed(2)}`);
          setNativeInputValue(input, targetPrice.toFixed(2));
          await new Promise(resolve => setTimeout(resolve, 800));

          // Verificar que el input realmente haya quedado con el precio escrito
          if (parseFloat(input.value) !== parseFloat(targetPrice.toFixed(2))) {
            console.error(`[Auto-Trader] Venta abortada: el campo Precio no reflejó el valor escrito (esperado $${targetPrice.toFixed(2)}, quedó "${input.value}").`);
            document.body.click();
            return false;
          }
        }
      }

      // 5. Proceder a revisar y confirmar la orden de venta
      // (misma corrección que en executeOrder: sólo elementos clickeables reales,
      // priorizando match exacto y el elemento más específico)
      let reviewBtn = null;
      try {
        reviewBtn = await waitForReviewButton();
      } catch (err) {
        console.warn("[Auto-Trader] Cierre de posición: " + err.message);
        return false;
      }

      if (reviewBtn) {
        superClick(reviewBtn);
        const confirmBtn = await waitForActionButton(CONFIRM_LABELS, 8000, document);
        if (confirmBtn) {
          superClick(confirmBtn);
          await new Promise(resolve => setTimeout(resolve, 1500));
          return true;
        }
      }
      return false;
    } catch (err) {
      console.error("Error al cerrar posición desde tarjeta:", err);
      return false;
    } finally {
      isTradeFormBusy = false;
    }
  }

  // Navega a la pestaña de posiciones activas en la interfaz de uCharts
  async function irAPestanaPosiciones() {
    console.log("[Auto-Trader] Navegando a pestaña de posiciones...");
    const tabBtn = Array.from(document.querySelectorAll('button, a, div[role="button"], span')).find(el => {
      const t = (el.textContent || "").trim().toLowerCase();
      return t === "posiciones" || t === "positions" || t === "posiciones abiertas" || t === "open positions" || t.includes("posiciones") || t.includes("positions");
    });
    if (tabBtn) {
      superClick(tabBtn);
      await new Promise(resolve => setTimeout(resolve, 1500));
      return true;
    }
    // Si ya estamos en la URL de posiciones, es un fallback exitoso
    const currentUrl = window.location.href;
    if (currentUrl.includes('/positions') || currentUrl.includes('/posiciones')) {
      return true;
    }
    return false;
  }

  // Abre la posición comprada y coloca inmediatamente la orden de venta límite para Take Profit
  async function colocarOrdenLimiteVentaTakeProfit(ticker) {
    console.log(`[Auto-Trader] Iniciando colocación automática de venta límite para ${ticker}...`);
    
    // 1. Navegar a pestaña de posiciones
    const enPosiciones = await irAPestanaPosiciones();
    if (!enPosiciones) {
      console.warn("[Auto-Trader] No se pudo cambiar a la pestaña de posiciones.");
      return;
    }
    
    // 2. Buscar la tarjeta de posición correspondiente a este ticker
    let allElems = getAllElements(document);
    let descElements = allElems.filter(el => {
      let t = (el.textContent || "").trim();
      return t.includes(ticker) && (t.includes("Call") || t.includes("Put"));
    });
    
    let targetCard = null;
    for (let descEl of descElements) {
      let card = descEl.parentElement;
      let safety = 0;
      while (card && !card.textContent.includes("Comprado en") && safety < 6) {
        card = card.parentElement;
        safety++;
      }
      if (card) {
        targetCard = card;
        break;
      }
    }
    
    if (targetCard) {
      console.log(`[Auto-Trader] Tarjeta de posición para ${ticker} localizada. Colocando orden límite de Take Profit...`);
      const success = await closePositionByCard(targetCard);
      if (success) {
        console.info(`[Auto-Trader] Orden límite de venta Take Profit para ${ticker} colocada con éxito.`);
        // Misma clave que usa monitorPositionsPnL, para que no vuelva a
        // intentar cerrar esta posición y duplicar la orden.
        const matchedDesc = descElements.find(el => {
          let card = el.parentElement, safety = 0;
          while (card && !card.textContent.includes("Comprado en") && safety < 6) {
            card = card.parentElement;
            safety++;
          }
          return card === targetCard;
        });
        if (matchedDesc) {
          positionsWithPendingClose.add(matchedDesc.textContent.trim().replace(/\s+/g, ' '));
        }
      } else {
        console.error(`[Auto-Trader] Falló el intento de colocar la orden límite de venta para ${ticker}.`);
      }
    } else {
      console.warn(`[Auto-Trader] No se encontró ninguna tarjeta de posición abierta para ${ticker} en pantalla.`);
    }
  }

  // Bucle de fondo para monitorear el PnL y ejecutar auto-cierres
  let isClosingPosition = false; // Flag para evitar concurrencia en cierres

  // Recuerda qué posiciones ya tienen una orden de venta límite pendiente
  // colocada, para no volver a lanzar otra igual en el próximo ciclo. La
  // orden límite no ejecuta al instante — la posición sigue apareciendo
  // "abierta" en Posiciones hasta que el precio la toca y se llena — así que
  // sin esto, monitorPositionsPnL (que corre cada 2s) la seguía viendo por
  // encima del umbral y mandaba OTRA orden de venta nueva cada vez, apilando
  // decenas de órdenes duplicadas para el mismo contrato.
  const positionsWithPendingClose = new Set();

  async function monitorPositionsPnL() {
    // Si el auto-cierre no está marcado, o ya estamos en proceso de cerrar una posición, salir
    const chkAutoClose = document.getElementById('chk-auto-close');
    if (!autoTraderMasterOn || !chkAutoClose || !chkAutoClose.checked || isClosingPosition || isTradeFormBusy) return;

    // Solo monitorear si estamos en la pestaña Posiciones para ver los datos en vivo
    const currentUrl = window.location.href;
    if (!currentUrl.includes('/positions') && !currentUrl.includes('/posiciones') && !document.body.innerText.includes("PRECIO DE COMPRA")) {
      return;
    }

    // Obtener configuración de objetivos
    const useTpPct = document.getElementById('chk-tp-pct').checked;
    const tpPctLimit = parseFloat(document.getElementById('tp-pct-val').value) || 15.0;

    const useTpUsd = document.getElementById('chk-tp-usd').checked;
    const tpUsdLimit = parseFloat(document.getElementById('tp-usd-val').value) || 1000.0;

    const useSlPct = document.getElementById('chk-sl-pct').checked;
    const slPctLimit = parseFloat(document.getElementById('sl-pct-val').value) || 10.0;

    const useSlUsd = document.getElementById('chk-sl-usd').checked;
    const slUsdLimit = parseFloat(document.getElementById('sl-usd-val').value) || 500.0;

    let allElems = getAllElements(document);

    // Filtrar tarjetas de posición
    let descElements = allElems.filter(el => {
      let t = (el.textContent || "").trim();
      let hasKeywords = (t.includes("Call") || t.includes("Put")) && /\d+/.test(t) &&
                        !t.includes("Historial") && !t.includes("Monto") && !t.includes("Posiciones") && !t.includes("Descripción");
      if (!hasKeywords) return false;

      let childHasKeywords = Array.from(el.children).some(child => {
        let ct = (child.textContent || "").trim();
        return (ct.includes("Call") || ct.includes("Put")) && /\d+/.test(ct);
      });
      return !childHasKeywords;
    });

    for (let descEl of descElements) {
      let card = descEl.parentElement;
      // Ir subiendo hasta encontrar el contenedor que agrupa el PnL de la tarjeta
      let safety = 0;
      while (card && !card.textContent.includes("Comprado en") && safety < 5) {
        card = card.parentElement;
        safety++;
      }
      if (!card) continue;

      // Extraer PnL
      const cardText = card.textContent.trim().replace(/\s+/g, ' ');

      // Buscar cantidad para ignorar testers pequeños (solo cerrar automático posiciones de al menos 1 contrato)
      let quantity = 1;
      const qtyMatch = cardText.match(/x\s*(\d+)/i);
      if (qtyMatch) {
        quantity = parseInt(qtyMatch[1], 10);
      }

      // Omitir testers de 0 contratos (permitir cerrar 1 contrato en adelante)
      if (quantity <= 0) continue;

      // Clave estable de esta posición (ticker + vencimiento + tipo + strike,
      // sin cantidad/precio/PnL que cambian todo el tiempo). Si ya le
      // pusimos una venta límite pendiente, no volver a intentarlo.
      const positionKey = descEl.textContent.trim().replace(/\s+/g, ' ');
      if (positionsWithPendingClose.has(positionKey)) continue;

      // No es una posición que el bot haya comprado él mismo en esta
      // sesión (Cardona o Bandera) — se la deja tranquila. Ver el
      // comentario de isPositionTrackedByBot más arriba.
      if (!isPositionTrackedByBot(cardText)) continue;

      const matchPct = cardText.match(/([+-])\s*([\d.]+)\s*%/);
      const matchUsd = cardText.match(/([+-])\s*\$\s*([\d,.]+)/);

      let currentPct = 0.0;
      let currentUsd = 0.0;

      if (matchPct) {
        currentPct = parseFloat(matchPct[2]) * (matchPct[1] === '-' ? -1.0 : 1.0);
      }
      if (matchUsd) {
        currentUsd = parseFloat(matchUsd[2].replace(',', '')) * (matchUsd[1] === '-' ? -1.0 : 1.0);
      }

      // Evaluar Take Profit
      let shouldClose = false;
      let reason = "";
      let closeType = 'TP';

      if (useTpPct && currentPct >= tpPctLimit) {
        shouldClose = true;
        closeType = 'TP';
        reason = `Toma de Ganancias del ${currentPct}% alcanzada (Objetivo: ${tpPctLimit}%)`;
      }
      if (useTpUsd && currentUsd >= tpUsdLimit) {
        shouldClose = true;
        closeType = 'TP';
        reason = `Toma de Ganancias de $${currentUsd} USD alcanzada (Objetivo: $${tpUsdLimit} USD)`;
      }

      // Evaluar Stop Loss (Valores negativos en el PnL flotante de uCharts)
      if (useSlPct && currentPct <= -slPctLimit) {
        shouldClose = true;
        closeType = 'SL';
        reason = `Limite de Perdida (Stop Loss) del ${currentPct}% alcanzado (Limite: -${slPctLimit}%)`;
      }
      if (useSlUsd && currentUsd <= -slUsdLimit) {
        shouldClose = true;
        closeType = 'SL';
        reason = `Limite de Perdida (Stop Loss) de $${currentUsd} USD alcanzado (Limite: -$${slUsdLimit} USD)`;
      }

      if (shouldClose) {
        isClosingPosition = true;
        console.log(`🎯 [Auto-Trader] Iniciando auto-cierre de posición: ${reason}`);

        // Destellar el panel del trader en amarillo por alerta
        const traderIndicator = document.getElementById('trader-indicator');
        if (traderIndicator) {
          traderIndicator.style.backgroundColor = '#facc15';
          traderIndicator.style.boxShadow = '0 0 8px #facc15';
        }

        const success = await closePositionByCard(card, closeType);

        if (success) {
          console.log("💥 [Auto-Trader] Posición cerrada de forma automática y exitosa.");
          positionsWithPendingClose.add(positionKey);
        } else {
          console.error("❌ [Auto-Trader] Falló el intento de auto-cierre.");
        }

        if (traderIndicator) {
          traderIndicator.style.backgroundColor = '#22c55e';
          traderIndicator.style.boxShadow = '0 0 8px #22c55e';
        }

        isClosingPosition = false;
        break; // Detener bucle y esperar al siguiente ciclo
      }
    }
  }

  // Polling de señales en vivo y ejecución de órdenes automáticas
  let isAutoTraderRunning = false;

  async function pollPendingTradesFromServer() {
    if (!autoTraderMasterOn) return; // interruptor maestro: pausado por el usuario
    if (currentSystemState !== "ARMED") return;
    if (isAutoTraderRunning) return;
    if (isClosingPosition) return;
    if (isTradeFormBusy) return;
    
    try {
      let r = await fetch('http://127.0.0.1:8055/get_pending_trades');
      if (!r.ok) return;
      let pending = await r.json();
      
      if (pending && pending.length > 0) {
        let trade = pending[0];
        let setupId = trade.setup_id;
        let ticker = trade.ticker;
        let direction = trade.direction; // "CALL" o "PUT"
        
        console.info(`[Auto-Trader] Señal autónoma pendiente detectada: ${ticker} - ${direction} (Setup: ${setupId})`);

        // Idempotencia (sección 8): si este mismo navegador ya ejecutó este
        // setup_id antes (y el aviso a /mark_executed no llegó a completarse
        // por algún corte de red), no comprar de nuevo — sólo reintentar el
        // aviso de desencolado al servidor.
        if (hasCardonaSetupAlreadyExecuted(setupId)) {
          console.warn(`[Auto-Trader] Setup ${setupId} ya fue ejecutado localmente antes; no se vuelve a comprar. Reintentando sólo el desencolado.`);
          try {
            await fetch('http://127.0.0.1:8055/mark_executed', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ setup_id: setupId })
            });
          } catch (e) {
            console.error("[Auto-Trader] Error al reintentar el desencolado en servidor local:", e);
          }
          return;
        }
        
        isAutoTraderRunning = true;
        
        const traderIndicator = document.getElementById('trader-indicator');
        if (traderIndicator) {
          traderIndicator.style.backgroundColor = '#facc15';
          traderIndicator.style.boxShadow = '0 0 8px #facc15';
        }
        
        let qtyInput = document.querySelector('#trader-qty');
        let qty = qtyInput ? (parseInt(qtyInput.value, 10) || 1) : 1;
        let profile = localStorage.getItem('ucharts_trader_profile') || 'corto';
        
        console.info(`[Auto-Trader] Lanzando compra autónoma: Ticker=${ticker}, Tipo=${direction}, Perfil=${profile}, Cantidad=${qty}`);
        
        let success = await executeOrder(ticker, direction, profile.toLowerCase(), qty, null, { cardonaBucketCheck: true });

        if (success) {
          cardonaRegisterPosition(success, ticker);
          markCardonaSetupExecutedLocally(setupId);
        }
        
        // Reportar el resultado de la compra al bot de Python — ahora incluye
        // el precio real de fill (capturado del diálogo de UCharts) para que
        // el backend pueda espejar la operación en el ledger interno
        // (Meliora Sim Broker) con datos reales, no inventados.
        try {
          await fetch('http://127.0.0.1:8055/report_trade_result', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              setup_id: setupId,
              status: success ? "SUCCESS" : "ERROR",
              ticker: ticker,
              type: direction,
              quantity: qty,
              price: (success && success.price) ? success.price : null,
              strike: (success && success.strike) ? success.strike : null,
              error_message: success ? "" : lastTraderError
            })
          });
        } catch (err) {
          console.warn("[Auto-Trader] No se pudo reportar el resultado al servidor local:", err);
        }
        
        if (success) {
          console.info(`[Auto-Trader] Orden de ${ticker} - ${direction} ejecutada de forma autónoma con éxito.`);
        } else {
          console.warn(`[Auto-Trader] Falló la ejecución autónoma de ${ticker}: ${lastTraderError}`);
        }
        
        try {
          await fetch('http://127.0.0.1:8055/mark_executed', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ setup_id: setupId })
          });
        } catch (e) {
          console.error("[Auto-Trader] Error al desencolar en servidor local:", e);
        }
        
        if (traderIndicator) {
          traderIndicator.style.backgroundColor = '#22c55e';
          traderIndicator.style.boxShadow = '0 0 8px #22c55e';
        }
      }
    } catch (e) {
      // Servidor local apagado
    } finally {
      isAutoTraderRunning = false;
    }
  }

  let currentSystemState = "ARMED";

  async function fetchAndSyncSystemState() {
    try {
      let r = await fetch('http://127.0.0.1:8055/get_system_status');
      if (!r.ok) return;
      let data = await r.json();
      let state = data.system_state || "ARMED";
      updatePanelStateUI(state);
    } catch (e) {
      // Servidor local desconectado
    }
  }

  function updatePanelStateUI(state) {
    if (currentSystemState === state) return;
    currentSystemState = state;
    
    const panelEl = document.querySelector('.sheets-sync-panel');
    if (!panelEl) return;
    
    panelEl.classList.remove('state-armed', 'state-disarmed', 'state-stop');
    
    const traderTab = Array.from(panelEl.querySelectorAll('.sync-tab')).find(t => t.getAttribute('data-tab') === 'tab-trader');
    
    if (state === "ARMED") {
      panelEl.classList.add('state-armed');
      if (traderTab) traderTab.textContent = "Auto-Trader 🤖";
    } else if (state === "DISARMED") {
      panelEl.classList.add('state-disarmed');
      if (traderTab) traderTab.textContent = "Trader DISARMED 🟡";
    } else if (state === "STOP") {
      panelEl.classList.add('state-stop');
      if (traderTab) traderTab.textContent = "STOP DE EMERGENCIA 🛑";
    }
  }

  // ==========================================================================
  // Panel de Riesgo (Requisito #12): capital de inicio de día, fondos
  // actuales, cupo diario bruto/consumido/restante, exposición abierta,
  // P&L realizado/no realizado del día, cantidad de posiciones abiertas, y
  // estado del RiskEngine/PositionManager (ARMED/DISARMED/STOP/DAILY_LOCKED,
  // reconciliación). Se alimenta de GET /api/risk/status (ver
  // position_manager.estado_panel() en el backend) -- nunca inventa datos:
  // si el servidor local está apagado, el badge pasa a "SIN DATOS" y el
  // resto del panel conserva el último valor conocido.
  // ==========================================================================
  function fmtUsd(n) {
    if (n === null || n === undefined || isNaN(n)) return '--';
    const sign = n < 0 ? '-' : '';
    return `${sign}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  async function fetchAndSyncRiskStatus() {
    const badge = document.getElementById('risk-state-badge');
    const stopBtn = document.getElementById('btn-risk-stop');
    try {
      let r = await fetch('http://127.0.0.1:8055/api/risk/status?cuenta_id=default');
      if (!r.ok) throw new Error('HTTP ' + r.status);
      let d = await r.json();

      const setTxt = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
      const setCls = (id, cls) => { const el = document.getElementById(id); if (el) el.className = 'risk-val ' + cls; };

      setTxt('risk-capital-inicio', fmtUsd(d.balance_inicial_dia));
      setTxt('risk-fondos-actuales', fmtUsd(d.balance_actual));
      setTxt('risk-cupo-total', fmtUsd(d.cupo_diario_total));
      setTxt('risk-cupo-gastado', fmtUsd(d.cupo_gastado));
      setTxt('risk-cupo-disponible', fmtUsd(d.cupo_disponible));
      setCls('risk-cupo-disponible', (d.cupo_disponible !== null && d.cupo_disponible <= 0) ? 'risk-neg' : '');
      setTxt('risk-exposicion', fmtUsd(d.exposicion_abierta_usd));
      setTxt('risk-pnl-realizado', fmtUsd(d.pnl_realizado_dia));
      setCls('risk-pnl-realizado', d.pnl_realizado_dia < 0 ? 'risk-neg' : (d.pnl_realizado_dia > 0 ? 'risk-pos' : ''));
      setTxt('risk-pnl-no-realizado', fmtUsd(d.pnl_no_realizado));
      setCls('risk-pnl-no-realizado', d.pnl_no_realizado < 0 ? 'risk-neg' : (d.pnl_no_realizado > 0 ? 'risk-pos' : ''));
      setTxt('risk-posiciones', d.posiciones_abiertas);
      setTxt('risk-pm-state', d.reconciliado ? 'OK ✅' : `DESCUADRE ⚠️ ($${(d.reconciliacion_diferencia || 0).toFixed(2)})`);
      setCls('risk-pm-state', d.reconciliado ? 'risk-pos' : 'risk-warn');

      if (badge) {
        badge.className = 'risk-badge';
        if (d.kill_switch_activo || d.system_state === 'STOP') {
          badge.classList.add('risk-stop');
          badge.textContent = 'STOP 🛑';
        } else if (d.daily_locked) {
          badge.classList.add('risk-locked');
          badge.textContent = 'DAILY LOCKED 🔒';
        } else if (d.system_state === 'DISARMED') {
          badge.classList.add('risk-disarmed');
          badge.textContent = 'DISARMED 🟡';
        } else {
          badge.classList.add('risk-armed');
          badge.textContent = 'ARMED 🟢';
        }
      }

      if (stopBtn) {
        const killActive = !!d.kill_switch_activo;
        stopBtn.dataset.active = String(killActive);
        stopBtn.textContent = killActive ? '▶️ Reanudar Nuevas Órdenes' : '🛑 STOP Nuevas Órdenes';
      }
    } catch (e) {
      // Servidor local desconectado -- se conserva el último valor conocido
      // en el resto de los campos, sólo se marca el badge como offline.
      if (badge) {
        badge.className = 'risk-badge risk-offline';
        badge.textContent = 'SIN DATOS';
      }
    }
  }

  // (declarada arriba del archivo junto a banderinEnabled — ver comentario ahí)

  function extractAccountBalance() {
    const currentUrl = window.location.href;
    // FIX (Bandera Automática no detectaba el capital fuera de la pestaña
    // "Cuenta"): antes, esta función se negaba a leer nada si la URL actual
    // no incluía /account o tab=account, así que activar la Bandera desde
    // la pantalla de trading tiraba el alert de "todavía no se detectó el
    // capital" aunque el widget "Resumen de la cuenta" con "Valor de la
    // cuenta" estuviera visible ahí mismo. Ahora se busca esa etiqueta
    // exacta en CUALQUIER pantalla (es específica, no debería confundirse
    // con otra cosa); el heurístico más arriesgado de abajo (el mayor monto
    // en $ visible en toda la pantalla) se deja restringido a la pestaña de
    // Cuenta, para no confundir el importe de una orden con el capital.
    const elements = Array.from(document.querySelectorAll('div, span, p, h1, h2, h3, td'));
    // El bucket de la Bandera se calcula sobre los FONDOS DISPONIBLES para
    // operar (efectivo libre), no sobre el Valor de la cuenta (que incluye
    // el valor de posiciones ya abiertas) — así el 10% nunca cuenta como
    // "libre" capital que ya está comprometido. Si por algún motivo esa
    // etiqueta no está en pantalla, se cae a "Valor de la cuenta" como
    // respaldo antes de rendirse.
    // FIX 2: el ".includes()" de más abajo (versión anterior) podía matchear
    // un <div> contenedor gigante cuyo textContent concatenado incluye la
    // frase completa de la página, ANTES de llegar a la etiqueta <p> real,
    // porque querySelectorAll devuelve los ancestros antes que sus
    // descendientes. Eso hacía que a veces se leyera silenciosamente el
    // número equivocado (p. ej. "Valor de la cuenta" en vez de "Fondos
    // disponibles"). Ahora sólo se aceptan elementos hoja (sin hijos) con
    // texto EXACTO — así nunca puede matchear un contenedor.
    const label = elements.find(el => {
      if (el.children.length !== 0) return false;
      const t = (el.textContent || "").trim();
      return t === "Fondos disponibles para operar";
    }) || elements.find(el => {
      if (el.children.length !== 0) return false;
      const t = (el.textContent || "").trim();
      return t === "Valor de la cuenta" || t === "Account Value";
    });
    if (label) {
      const parent = label.parentElement;
      const amountEl = Array.from(parent.querySelectorAll('div, span, p, h1, h2, h3')).find(el => {
        const t = (el.textContent || "").trim();
        return /^\$\d+(?:,\d{3})*(?:\.\d{2})?$/.test(t);
      });
      if (amountEl) {
        const val = parseFloat(amountEl.textContent.replace(/[$,]/g, ''));
        cachedAccountBalance = val;
        return val;
      }
    }
    if (currentUrl.includes('/account') || currentUrl.includes('tab=account')) {
      const moneyList = elements.map(el => {
        const t = (el.textContent || "").trim();
        if (/^\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?$/.test(t)) {
          return parseFloat(t.replace(/[$,]/g, ''));
        }
        return null;
      }).filter(Boolean);
      if (moneyList.length > 0) {
        const val = Math.max(...moneyList);
        if (val > 1000.0) {
          cachedAccountBalance = val;
          return val;
        }
      }
    }
    return cachedAccountBalance;
  }

  function startHeartbeatLoop() {
    const initialBalance = extractAccountBalance();
    fetch('http://127.0.0.1:8055/heartbeat', { 
      method: 'POST', 
      mode: 'cors',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account_balance: initialBalance })
    }).catch(() => {});
    
    setInterval(async () => {
      try {
        const balance = extractAccountBalance();
        const payload = {};
        if (balance !== null) {
          payload.account_balance = balance;
        }
        await fetch('http://127.0.0.1:8055/heartbeat', {
          method: 'POST',
          mode: 'cors',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } catch (e) {
        // Servidor local offline
      }
    }, 30000);
  }

  // Cierra absolutamente todas las posiciones abiertas mostradas en pantalla
  async function panicCloseAll() {
    console.log("🚨 [Cierre de Pánico] Iniciando cierre masivo de todas las posiciones...");
    navigateToTab('Posiciones');
    await new Promise(resolve => setTimeout(resolve, 800));

    let allElems = getAllElements(document);
    let descElements = allElems.filter(el => {
      let t = (el.textContent || "").trim();
      let hasKeywords = (t.includes("Call") || t.includes("Put")) && /\d+/.test(t) &&
                        !t.includes("Historial") && !t.includes("Monto") && !t.includes("Posiciones") && !t.includes("Descripción");
      if (!hasKeywords) return false;
      let childHasKeywords = Array.from(el.children).some(child => {
        let ct = (child.textContent || "").trim();
        return (ct.includes("Call") || ct.includes("Put")) && /\d+/.test(ct);
      });
      return !childHasKeywords;
    });

    if (descElements.length === 0) {
      console.log("No hay posiciones abiertas para cerrar.");
      return true;
    }

    let success = true;
    for (let descEl of descElements) {
      let card = descEl.parentElement;
      let safety = 0;
      while (card && !card.textContent.includes("Comprado en") && safety < 5) {
        card = card.parentElement;
        safety++;
      }
      if (card) {
        const ok = await closePositionByCard(card, 'SL'); // Pánico = salida inmediata a Mercado, no esperar un límite
        if (!ok) success = false;
        await new Promise(resolve => setTimeout(resolve, 1500)); // Esperar entre cierres
        // Volver a cargar elementos para evitar stale reference
        navigateToTab('Posiciones');
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
    return success;
  }

  // Helper para enviar webhook individual
  async function sendWebhook(payload) {
    return new Promise((resolve) => {
      if (typeof GM_xmlhttpRequest !== "undefined") {
        GM_xmlhttpRequest({
          method: "POST",
          url: WEBHOOK_URL,
          headers: { "Content-Type": "text/plain" },
          data: JSON.stringify(payload),
          onload: function(response) {
            resolve(response.status === 200);
          },
          onerror: function() {
            resolve(false);
          }
        });
      } else {
        fetch(WEBHOOK_URL, {
          method: "POST",
          mode: "no-cors",
          headers: { "Content-Type": "text/plain" },
          body: JSON.stringify(payload)
        }).then(() => resolve(true)).catch(() => resolve(false));
      }
    });
  }

  // ----------------------------------------------------
  // Persistencia de pareo compra/venta entre sincronizaciones distintas
  // ----------------------------------------------------
  // FIX (Compra/Venta en $0 en Registro Continuo): antes, el pareo de
  // "Comprar..." con su "Vender.../Expired..." correspondiente sólo podía
  // ocurrir si AMBAS líneas aparecían en la MISMA tanda scrapeada de una
  // sola llamada a syncHistory(), porque el mapa openPositions se armaba
  // vacío en cada corrida. "Sincronizar Día" sólo scrollea 3 días atrás
  // (maxDaysBack:3): si la compra fue hace más de 3 días y hoy sólo se ve
  // su venta o vencimiento, el código caía siempre en la rama "huérfana"
  // (buyDate:"", buyPrice:0) — y esa fila sin compra real tampoco calzaba
  // con la fila "Abierto" ya cargada en Registro Continuo (la clave de
  // deduplicación del webhook depende justamente del precio y la fecha de
  // compra), así que quedaba una fila nueva con Compra y/o Venta en $0 y
  // #DIV/0! en % Ganancia — el bug reportado. Ahora las compras aún sin
  // vender (openPositions) y el registro de transacciones ya procesadas se
  // guardan en localStorage y se reusan/actualizan en cada sync, sin
  // importar cuántos días separen la compra de su venta.
  const OPEN_POS_STORAGE_KEY = 'ucharts_open_positions_v1';
  const PROCESSED_TX_STORAGE_KEY = 'ucharts_processed_tx_v1';
  // Ventas/vencimientos que agrupan VARIOS lotes (ej: "Expired qty=1002"
  // repartido entre 3 compras separadas) y que en el momento de sincronizar
  // sólo lograron emparejar ALGUNOS de esos lotes porque los demás todavía
  // no habían aparecido: acá se guarda cuánta cantidad de ESE evento
  // puntual sigue faltando emparejar, para que el próximo intento retome
  // desde ahí en vez de volver a arrancar desde la cantidad original
  // completa (lo que generaría re-emparejar de más contra compras nuevas
  // que no tienen nada que ver con este evento).
  const PENDING_CLOSES_STORAGE_KEY = 'ucharts_pending_closes_v1';
  // Antigüedad máxima que se retiene en el set de transacciones procesadas
  // antes de podarlas, para que localStorage no crezca sin techo después de
  // meses de uso. Las posiciones aún abiertas (openPositions) NO se podan
  // por antigüedad: representan operaciones reales todavía sin vender.
  const PROCESSED_TX_MAX_AGE_DAYS = 180;

  function loadPersistedJSON(key, fallback) {
    try {
      let raw = localStorage.getItem(key);
      if (!raw) return fallback;
      return JSON.parse(raw);
    } catch (e) {
      return fallback;
    }
  }

  function savePersistedJSON(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      console.warn(`[UCharts] No se pudo guardar estado persistente (${key}):`, e);
    }
  }

  // ----------------------------------------------------
  // FUNCIÓN 2: Sincronizar Historial (Masivo)
  // ----------------------------------------------------
  async function syncHistory(isSilent = false, opts = {}) {
    let allTx = [];
    let page = 1;

    function findRowData(descEl) {
      let parent = descEl;
      let safety = 0;
      while (parent && safety < 15) {
        let children = getAllElements(parent);
        let dateText = "";
        let amountText = "";

        // FIX (Fecha corrupta en Registro Continuo): esta búsqueda sólo
        // excluía candidatos que dijeran "option(s)", pero la ETIQUETA DEL
        // CONTRATO (ej. "26/08/25 Call 767.00" — vencimiento+tipo+strike)
        // TAMBIÉN matchea el regex de fecha y NO contiene "options", así que
        // se colaba como si fuera la fecha real de la operación. Resultado
        // en vivo confirmado: 87 filas cargadas el 29/08 con "Fecha" =
        // "26/08/25 Call 767.00" en vez de la fecha/hora real, y Venta vacía
        // en todas. Excluir explícitamente cualquier candidato que contenga
        // "Call"/"Put" hace que siga subiendo por los padres hasta encontrar
        // la celda real de fecha/hora (que nunca dice Call/Put).
        let dateEl = children.find(child => {
          let t = (child.textContent || "").trim();
          return /\d+[\/-]\d+[\/-]\d+/.test(t) && t.length < 50 && !t.includes("options") && !t.includes("option") && !/\b(call|put)\b/i.test(t);
        });
        if (dateEl) {
          dateText = dateEl.textContent.trim().replace(/\s+/g, ' ');
        }

        let amountEl = children.find(child => {
          let t = (child.textContent || "").trim();
          return /-?\$[\d,.]+\b/.test(t) && t.length < 30 && t !== dateText;
        });
        if (amountEl) {
          amountText = amountEl.textContent.trim();
        }

        if (dateText) {
          return { date: dateText, amount: amountText };
        }
        parent = getParent(parent);
        safety++;
      }
      return null;
    }

    // NOTA (fix pagineo): la UI de UCharts dejó de tener un botón
    // "Siguiente" para paginar el historial — ahora es una lista con SCROLL
    // INFINITO que va agregando filas nuevas al fondo del DOM a medida que
    // se scrollea hacia abajo. El código viejo buscaba un botón "Siguiente"
    // que ya no existe, así que "rompía" (break) apenas terminaba de leer
    // la primera tanda que ya estaba renderizada al abrir el historial —
    // por eso sólo se sincronizaban ~12 operaciones (los vencimientos que
    // ya estaban en pantalla) en vez de todo el historial real del día.
    function extractDescElements() {
      let allElems = getAllElements(document);
      return allElems.filter(el => {
        let t = (el.textContent || "").trim();
        let hasKeywords = /^Expired\/option\//i.test(t) ||
                          ((t.includes("Comprar") || t.includes("Vender") || t.includes("Compra") || t.includes("Venta") || t.includes("Buy") || t.includes("Sell")) &&
                           (t.includes("options") || t.includes("option") || t.includes("opción") || t.includes("opciones") || t.includes("contrato")));
        if (!hasKeywords) return false;

        let childHasKeywords = Array.from(el.children).some(child => {
          let ct = (child.textContent || "").trim();
          return /^Expired\/option\//i.test(ct) ||
                 ((ct.includes("Comprar") || ct.includes("Vender") || ct.includes("Compra") || ct.includes("Venta") || ct.includes("Buy") || ct.includes("Sell")) &&
                  (ct.includes("options") || ct.includes("option") || ct.includes("opción") || ct.includes("opciones") || ct.includes("contrato")));
        });
        return !childHasKeywords;
      });
    }

    function findScrollableContainer(fromEl) {
      let el = fromEl;
      let safety = 0;
      while (el && el !== document.body && safety < 20) {
        if (el.scrollHeight > el.clientHeight + 20) return el;
        el = el.parentElement;
        safety++;
      }
      return document.scrollingElement || document.documentElement;
    }

    // FASE 1: cargar todo lo que se pueda del historial haciendo scroll
    // hacia abajo repetidamente. En modo silencioso (chequeo de fondo cada
    // 15s) NO se scrollea nada, igual que antes: sólo se lee la tanda que
    // ya está en pantalla, para no recargar la página con scrolls
    // constantes. En modo manual (botón "Sincronizar Planilla") se scrollea
    // hasta que 3 intentos seguidos no traen filas nuevas (se asume que se
    // llegó al final real del historial), con un tope de seguridad de 400
    // vueltas y 4 minutos totales para no dejar el botón colgado para
    // siempre si algo sale mal.
    // "Sincronizar Día" pasa opts.maxDaysBack (ej: 3) para frenar el scroll
    // apenas ya se cargó una fila más vieja que ese límite, en vez de
    // scrollear TODO el historial como hace "Sincronizar Planilla". Esto
    // evita re-bajar meses de operaciones sólo para agregar el día de ayer.
    let maxDaysBack = (opts && opts.maxDaysBack) ? opts.maxDaysBack : null;
    let cutoffTs = maxDaysBack ? (Date.now() - maxDaysBack * 24 * 60 * 60 * 1000) : null;

    // FIX (reconciliación diaria en silencio): antes esto sólo scrolleaba
    // cuando isSilent=false (botones manuales). El chequeo de fondo de 15s
    // llama a syncHistory(true) sin maxDaysBack y debe seguir sin scrollear
    // (no recargar la página con scrolls constantes), pero
    // runDailyFullHistorySync llama a syncHistory(true, {maxDaysBack:3}) y
    // SÍ necesita bajar el scroll para alcanzar días anteriores aunque sea
    // en modo silencioso — si no, nunca cubre más que lo que ya está
    // renderizado al abrir Historial.
    if (!isSilent || maxDaysBack) {
      let scrollStart = Date.now();
      let maxScrollMs = 4 * 60 * 1000;
      let stableRounds = 0;
      for (let round = 0; round < 400; round++) {
        if (Date.now() - scrollStart > maxScrollMs) break;
        let before = extractDescElements().length;
        let sample = extractDescElements().slice(-1)[0];
        let container = sample ? findScrollableContainer(sample) : (document.scrollingElement || document.documentElement);
        if (container) {
          container.scrollTop = container.scrollHeight;
          container.dispatchEvent(new Event('scroll', { bubbles: true }));
        }
        window.scrollTo(0, document.body.scrollHeight);

        let grew = false;
        for (let attempts = 0; attempts < 15; attempts++) {
          await new Promise(resolve => setTimeout(resolve, 200));
          if (extractDescElements().length > before) { grew = true; break; }
        }
        if (!grew) {
          stableRounds++;
          if (stableRounds >= 3) break;
        } else {
          stableRounds = 0;
        }

        // Corte por antigüedad (sólo aplica si vino maxDaysBack): en cuanto
        // la fila más vieja cargada hasta ahora ya es más antigua que el
        // límite pedido, dejamos de scrollear — ya tenemos de sobra para
        // cubrir esos días, no hace falta seguir bajando historial viejo.
        if (cutoffTs) {
          let elemsNow = extractDescElements();
          let oldestEl = elemsNow.slice(-1)[0];
          let oldestRow = oldestEl ? findRowData(oldestEl) : null;
          if (oldestRow && oldestRow.date) {
            let oldestTs = historyTimestamp(oldestRow.date);
            if (oldestTs && oldestTs < cutoffTs) break;
          }
        }
      }
    }

    // FASE 2: extracción única sobre todo lo que haya quedado cargado en el
    // DOM (a diferencia del código viejo, que extraía "por página" y con
    // scroll infinito eso duplicaba filas ya leídas; acá se extrae una sola
    // vez al final, ya con todo el contenido acumulado).
    let descElementsFinal = extractDescElements();
    for (let descEl of descElementsFinal) {
      let descText = descEl.textContent.trim().replace(/\s+/g, ' ');
      let rowData = findRowData(descEl);
      if (rowData && rowData.date) {
        if (!allTx.some(tx => tx.desc === descText && tx.date === rowData.date)) {
          allTx.push({ desc: descText, date: rowData.date, amount: rowData.amount });
        }
      }
    }

    if (allTx.length === 0) {
      return { ok: false, error: "Etapa extracción: no se encontraron transacciones visibles en el historial." };
    }

    function historyTimestamp(value) {
      const match = String(value || "").match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?/);
      if (!match) return 0;
      return new Date(
        parseInt(match[3], 10),
        parseInt(match[1], 10) - 1,
        parseInt(match[2], 10),
        parseInt(match[4] || "0", 10),
        parseInt(match[5] || "0", 10),
        parseInt(match[6] || "0", 10)
      ).getTime();
    }
    allTx.sort((a, b) => historyTimestamp(a.date) - historyTimestamp(b.date));

    function parseDesc(desc) {
      let expired = desc.match(/^Expired\/option\/([^/]+)\/(\d+)\/O:[A-Z0-9.]+?(\d{2})(\d{2})(\d{2})([CP])(\d{8})$/i);
      if (expired) {
        return {
          action: 'expire',
          quantity: parseInt(expired[2], 10),
          ticker: expired[1].toUpperCase(),
          expiry: `${expired[3]}/${expired[4]}/${expired[5]}`,
          type: expired[6].toUpperCase() === 'P' ? 'PUT' : 'CALL',
          strike: parseInt(expired[7], 10) / 1000,
          price: 0
        };
      }
      let regex = /(Comprar|Vender|Compra|Venta|Buy|Sell)\s+(\d+)\s+(?:options?|opción|opciones|contratos?|de|compra|venta|\s)+\s+(\S+)\s+(.*?)\s+(Call|Put|Compra|Venta|Llamada|Poner)\s+([\d.,]+)\s+@\s*\$?\s*([\d.,]+)/i;
      let match = desc.match(regex);
      if (match) {
        let actionStr = match[1].toLowerCase();
        let typeStr = match[5].toLowerCase();
        let typeClean = "CALL";
        if (typeStr === 'put' || typeStr === 'venta' || typeStr === 'poner') {
          typeClean = "PUT";
        }
        return {
          action: (actionStr === 'comprar' || actionStr === 'compra' || actionStr === 'buy') ? 'buy' : 'sell',
          quantity: parseInt(match[2], 10),
          ticker: match[3],
          expiry: match[4],
          type: typeClean,
          strike: parseFloat(match[6].replace(',', '')),
          price: parseFloat(match[7].replace(',', ''))
        };
      }
      return null;
    }

    let openPositions = loadPersistedJSON(OPEN_POS_STORAGE_KEY, {});
    let processedTx = new Set(loadPersistedJSON(PROCESSED_TX_STORAGE_KEY, []));
    let pendingCloses = loadPersistedJSON(PENDING_CLOSES_STORAGE_KEY, {});
    let anyParsed = false;
    let trades = [];
    // Ventas/vencimientos que no encontraron ninguna compra abierta para
    // emparejar (ver el "else" de más abajo) — NUNCA se mandan a la
    // planilla como fila nueva, sólo se registran acá para avisar en la
    // consola y en el alert final. Insertar una fila con Compra en $0 es
    // justamente el bug reportado: una fila así no sirve para identificar
    // ni calcular el trade.
    let skippedOrphans = [];

    for (let tx of allTx) {
      // Cada línea del historial (compra, venta o vencimiento) se procesa
      // UNA SOLA VEZ para siempre, sin importar cuántas veces se vuelva a
      // scrapear en syncs futuros (el scroll siempre re-lee desde arriba).
      // Esto evita contar una misma compra dos veces: una desde el estado
      // persistido y otra desde el re-scrapeo de hoy.
      let txKey = `${tx.date}||${tx.desc}`;
      // FIX: "anyParsed" tiene que reflejar si el TEXTO tiene el formato
      // esperado, sin importar si ya se había procesado antes. Si esto se
      // calculaba DESPUÉS del "continue" por ya-procesado (como estaba
      // antes), una sincronización sobre movimientos que ya se habían
      // cargado en una corrida anterior terminaba con anyParsed=false para
      // todos, y tiraba el error "ninguno coincidió con el formato
      // esperado" aunque en realidad todo estaba bien y sólo no había nada
      // nuevo — el error reportado en vivo.
      let parsed = parseDesc(tx.desc);
      if (parsed) anyParsed = true;
      if (processedTx.has(txKey)) continue;
      if (!parsed) { processedTx.add(txKey); continue; }

      parsed.date = tx.date;
      let key = `${parsed.ticker}|${parsed.expiry}|${parsed.type}|${parsed.strike}`;

      if (parsed.action === 'buy') {
        // Las compras SIEMPRE se marcan procesadas de una: quedan
        // guardadas en openPositions (persistido), así que no hace falta
        // volver a leerlas — ya están disponibles para emparejar con
        // cualquier venta/vencimiento futuro, sin importar cuánto tarde.
        processedTx.add(txKey);
        if (!openPositions[key]) openPositions[key] = [];
        openPositions[key].push({
          date: parsed.date,
          price: parsed.price,
          quantity: parsed.quantity,
          ticker: parsed.ticker,
          expiry: parsed.expiry,
          type: parsed.type,
          strike: parsed.strike,
          reportedOpen: false
        });
      } else {
        // Si un intento anterior ya emparejó PARTE de este mismo evento
        // (ver PENDING_CLOSES_STORAGE_KEY más arriba), se retoma desde la
        // cantidad que todavía faltaba, no desde la cantidad original —
        // si no, se re-emparejaría de más contra compras nuevas que no
        // tienen nada que ver con este evento puntual.
        let sellQty = (pendingCloses[txKey] != null) ? pendingCloses[txKey] : parsed.quantity;
        let sellPrice = parsed.price;
        let sellDate = parsed.date;

        while (sellQty > 0 && openPositions[key] && openPositions[key].length > 0) {
          let openBuy = openPositions[key][0];
          if (openBuy.quantity <= sellQty) {
            trades.push({
              ticker: openBuy.ticker,
              type: openBuy.type,
              strike: openBuy.strike,
              expiry: openBuy.expiry,
              quantity: openBuy.quantity,
              buyDate: openBuy.date,
              buyPrice: openBuy.price,
              sellDate: sellDate,
              sellPrice: sellPrice,
              status: 'Cerrado',
              strategy: "Histórico UCharts"
            });
            sellQty -= openBuy.quantity;
            openPositions[key].shift();
          } else {
            trades.push({
              ticker: openBuy.ticker,
              type: openBuy.type,
              strike: openBuy.strike,
              expiry: openBuy.expiry,
              quantity: sellQty,
              buyDate: openBuy.date,
              buyPrice: openBuy.price,
              sellDate: sellDate,
              sellPrice: sellPrice,
              status: 'Cerrado',
              strategy: "Histórico UCharts"
            });
            openBuy.quantity -= sellQty;
            sellQty = 0;
          }
        }

        if (sellQty > 0) {
          // FIX (nunca más filas con Compra en $0): antes acá se insertaba
          // una fila "huérfana" con buyPrice:0 cuando no se encontraba (o
          // ya se había agotado) la compra correspondiente — exactamente
          // el origen de las filas con Compra y/o Venta en $0 y #DIV/0!
          // reportadas. Ahora, si no hay una compra real para emparejar,
          // NO se manda nada a la planilla: mejor un hueco visible (que se
          // puede completar a mano si hace falta) que una fila con datos
          // falsos que no sirve para identificar ni calcular el trade.
          skippedOrphans.push({
            ticker: parsed.ticker,
            type: parsed.type,
            strike: parsed.strike,
            expiry: parsed.expiry,
            quantity: sellQty,
            date: sellDate,
            reason: parsed.action === 'expire' ? 'Vencimiento sin compra emparejada' : 'Venta sin compra emparejada'
          });
          // FIX (el bug de "sólo se cargan un par de trades"): esta venta/
          // vencimiento NO se marca como procesada. Si se marcara acá iba
          // a quedar perdida para siempre en cuanto la compra real
          // apareciera en un sync futuro (por ejemplo al correr
          // "Sincronizar Planilla" completo) — la próxima corrida ya no
          // iba a volver a mirar esta línea porque figuraba en
          // processedTx, así que la compra se quedaba "Abierta" para
          // siempre sin poder emparejar jamás. Al no marcarla, se vuelve a
          // intentar en cada sync hasta que su compra aparezca — y queda
          // guardado cuánto falta todavía (ver más arriba) para no
          // re-emparejar de más si esto es un evento multi-lote.
          pendingCloses[txKey] = sellQty;
        } else {
          delete pendingCloses[txKey];
          processedTx.add(txKey);
        }
      }
    }

    for (let key in openPositions) {
      for (let openBuy of openPositions[key]) {
        // Una posición abierta ya reportada antes no se vuelve a mandar en
        // cada sync (si no, con estado persistido se reenviaría la MISMA
        // fila "Abierto" cada 15s para siempre) — el webhook ya la tiene
        // cargada y sólo hace falta avisarle cuando pase a "Cerrado".
        if (openBuy.reportedOpen) continue;
        trades.push({
          ticker: openBuy.ticker,
          type: openBuy.type,
          strike: openBuy.strike,
          expiry: openBuy.expiry,
          quantity: openBuy.quantity,
          buyDate: openBuy.date,
          buyPrice: openBuy.price,
          sellDate: "",
          sellPrice: 0,
          status: 'Abierto',
          strategy: "Histórico UCharts"
        });
        openBuy.reportedOpen = true;
      }
    }

    // FIX (bug reportado 30/08: "Sincronizar Día" dice que ya está todo al
    // día pero faltan trades enteros en Registro Continuo): ANTES, el
    // estado persistido (compras/ventas ya "vistas") se guardaba en
    // localStorage ACÁ MISMO, antes de siquiera intentar mandar `trades` al
    // webhook. Si esa llamada fallaba (red, cuota de Apps Script, error del
    // script, deployment caído, etc.), el navegador ya había marcado esas
    // transacciones como procesadas para siempre — la próxima sincronización
    // las volvía a leer del historial, pero como ya figuraban en
    // processedTx/openPositions las descartaba silenciosamente, y el botón
    // mostraba "ya está todo al día" aunque esos trades nunca hubieran
    // llegado a la planilla. Confirmado en vivo: 232 transacciones del
    // 28/08 quedaron marcadas como procesadas en localStorage sin una sola
    // fila correspondiente en Registro Continuo.
    //
    // Ahora el guardado en localStorage se hace DESPUÉS de confirmar que el
    // webhook aceptó el envío (o inmediatamente si no había nada que
    // mandar, caso en el que no hay nada que perder). Si el envío falla, NO
    // se persiste nada nuevo: la próxima sincronización vuelve a leer las
    // mismas filas del historial, las vuelve a emparejar igual (el DOM no
    // cambió) y reintenta el envío, en vez de perder esos trades para
    // siempre.
    let prunedProcessedTx = Array.from(processedTx).filter(k => {
      let datePart = k.split('||')[0];
      let ts = historyTimestamp(datePart);
      if (!ts) return true; // fecha no parseable: mejor conservarla que perderla
      return (Date.now() - ts) < PROCESSED_TX_MAX_AGE_DAYS * 24 * 60 * 60 * 1000;
    });
    function persistSyncState() {
      savePersistedJSON(OPEN_POS_STORAGE_KEY, openPositions);
      savePersistedJSON(PROCESSED_TX_STORAGE_KEY, prunedProcessedTx);
      savePersistedJSON(PENDING_CLOSES_STORAGE_KEY, pendingCloses);
    }

    if (skippedOrphans.length > 0) {
      console.warn(`[UCharts] ${skippedOrphans.length} movimiento(s) NO se cargaron a la planilla por no tener compra emparejada (para no ensuciarla con filas en $0):`, skippedOrphans);
    }
    const orphanNote = skippedOrphans.length > 0
      ? `\n\n⚠️ ${skippedOrphans.length} movimiento(s) (venta o vencimiento) no tenían una compra emparejada y NO se cargaron a la planilla — revisá la consola del navegador (F12) para el detalle, o el historial completo con "Sincronizar Planilla".`
      : "";

    if (trades.length === 0) {
      // Nada para mandar al webhook: no hay riesgo de persistir ya mismo
      // (no queda ningún envío pendiente de confirmar).
      persistSyncState();
      if (!anyParsed && allTx.length > 0 && skippedOrphans.length === 0) {
        return { ok: false, error: `Etapa interpretación: se leyeron ${allTx.length} movimientos, pero ninguno coincidió con el formato esperado de UCharts.` };
      }
      // Nada nuevo para mandar (todo lo visible ya se había sincronizado
      // antes) — esto es un resultado normal, no un error. Igual se avisa
      // con un alert en los botones manuales para que quede claro que el
      // botón SÍ hizo algo (leyó el historial), en vez de no mostrar nada.
      if (!isSilent) {
        alert(`✅ Sincronización completa: no hay operaciones nuevas para agregar, ya está todo al día.${orphanNote}`);
      }
      return { ok: true, count: 0, skipped: skippedOrphans.length };
    }

    console.log(`📤 Enviando ${trades.length} operaciones masivas al webhook...`);

    let ok = await new Promise((resolve) => {
      let data = JSON.stringify({ action: "bulk_import", trades: trades });
      if (typeof GM_xmlhttpRequest !== "undefined") {
        GM_xmlhttpRequest({
          method: "POST",
          url: WEBHOOK_URL,
          headers: { "Content-Type": "text/plain" },
          data: data,
          onload: function(response) {
            let body = {};
            try { body = JSON.parse(response.responseText || "{}"); } catch (_) {}
            resolve({ ok: response.status === 200 && body.status !== "error", status: response.status, body: body });
          },
          onerror: function(response) {
            resolve({ ok: false, status: response?.status || 0, body: {} });
          }
        });
      } else {
        // FIX: mode:"no-cors" hace que fetch() SIEMPRE resuelva "success"
        // aunque el servidor nunca haya recibido o procesado nada (la
        // respuesta es opaca, no se puede leer el status) — con GM_grant
        // activo (ver @grant GM_xmlhttpRequest arriba) esta rama no debería
        // usarse nunca en la práctica, pero se deja marcado explícitamente
        // como "no confirmado" en vez de mentir con ok:true, para que si
        // algún día esto corre sin GM_xmlhttpRequest no vuelva a persistir
        // como si el envío hubiera sido confirmado.
        fetch(WEBHOOK_URL, {
          method: "POST",
          mode: "no-cors",
          headers: { "Content-Type": "text/plain" },
          body: data
        }).then(() => resolve({ ok: false, unconfirmed: true, status: 0, body: {} }))
          .catch(() => resolve({ ok: false, status: 0, body: {} }));
      }
    });

    // Sólo se guarda el nuevo estado (compras/ventas marcadas como
    // procesadas) si el webhook CONFIRMÓ que recibió y aceptó el envío. Si
    // falló, se deja el localStorage tal como estaba antes de esta corrida
    // para que el próximo intento vuelva a mandar exactamente estos mismos
    // trades, en vez de darlos por perdidos.
    if (ok.ok) {
      persistSyncState();
    } else {
      console.warn(`[UCharts] El webhook NO confirmó el envío de ${trades.length} operación(es) — no se marcan como sincronizadas, se reintentará en la próxima sincronización.`, ok);
    }

    if (!isSilent) {
      if (ok.ok) {
        alert(`🎉 ¡Sincronización masiva completada! ${trades.length} operaciones enviadas con éxito.${orphanNote}`);
      } else {
        const detail = ok.body?.message || `HTTP ${ok.status || "sin respuesta"}`;
        return { ok: false, error: `Etapa envío: el webhook rechazó la importación (${detail}). No se perdieron datos: se reintentará en la próxima sincronización.` };
      }
    }
    return ok.ok ? { ok: true, count: trades.length, skipped: skippedOrphans.length } : { ok: false, error: "Etapa envío: el webhook no confirmó la importación. No se perdieron datos: se reintentará en la próxima sincronización." };
  }
})();
// ==UserScript==
// @name         UCharts to Google Sheets Sync Tool
// @namespace    http://tampermonkey.net/
// @version      5.0.12
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
        <div class="sync-tab active" data-tab="tab-sheet">Planilla 📊 v5.0.12</div>
        <div class="sync-tab" data-tab="tab-trader">Auto-Trader 🤖</div>
      </div>

      <!-- PESTAÑA 1: PLANILLA -->
      <div class="tab-content active" id="tab-sheet">
        <button class="sheets-sync-btn">
          <span class="sync-icon">📊</span>
          <span class="sync-spinner"></span>
          <span class="btn-text">Sincronizar Planilla</span>
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
      </div>
    `;
    document.body.appendChild(panel);

    btn = panel.querySelector('.sheets-sync-btn');
    autoCheckbox = panel.querySelector('.auto-sync-checkbox');
    statusIndicator = panel.querySelector('.sync-status-indicator');

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
      corto: { qty: 1000, tpPct: 15, tpUsd: 1000, usePct: true, useUsd: false, slPct: 10, slUsd: 500, useSlPct: true, useSlUsd: false },
      medio: { qty: 200, tpPct: 40, tpUsd: 5000, usePct: true, useUsd: false, slPct: 15, slUsd: 1500, useSlPct: true, useSlUsd: false },
      largo: { qty: 50, tpPct: 100, tpUsd: 10000, usePct: true, useUsd: false, slPct: 25, slUsd: 2500, useSlPct: true, useSlUsd: false }
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

        localStorage.setItem('ucharts_trader_profile', profile);
      });
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

    // Iniciar bucle de monitoreo de PnL para auto-cierre
    setInterval(monitorPositionsPnL, 2000);
    // Iniciar bucle de polling para ejecución autónoma del Auto-Trader
    setInterval(pollPendingTradesFromServer, 5000);
    // Iniciar bucle de reporte de latido (Heartbeat) de uCharts
    startHeartbeatLoop();
    // Iniciar bucle de sincronización del estado del sistema
    setInterval(fetchAndSyncSystemState, 5000);
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
      const targetDte = dteProfile === 'largo' ? 30 : dteProfile === 'medio' ? 5 : 0;
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
    const { skipAutoTP = false } = options;
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
        const orderAmount = extractOrderSummaryAmount();
        if (orderAmount !== null && quantity > 0) {
          fillPricePerContract = orderAmount / (quantity * 100);
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
        buyResult = { expiryKey: optionSelected.expiryKey, ticker, type, quantity, price: fillPricePerContract, strike: optionSelected.strike, submitted: true };
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
    if (!chkAutoClose || !chkAutoClose.checked || isClosingPosition || isTradeFormBusy) return;

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
        
        let success = await executeOrder(ticker, direction, profile.toLowerCase(), qty);
        
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

  let cachedAccountBalance = null;

  function extractAccountBalance() {
    const currentUrl = window.location.href;
    if (!currentUrl.includes('/account') && !currentUrl.includes('tab=account')) {
      return cachedAccountBalance;
    }
    const elements = Array.from(document.querySelectorAll('div, span, p, h1, h2, h3, td'));
    const label = elements.find(el => {
      const t = (el.textContent || "").trim();
      return t === "Valor de la cuenta" || t === "Account Value" || t.includes("Valor de la cuenta");
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
  // FUNCIÓN 2: Sincronizar Historial (Masivo)
  // ----------------------------------------------------
  async function syncHistory(isSilent = false) {
    let allTx = [];
    let page = 1;

    function findRowData(descEl) {
      let parent = descEl;
      let safety = 0;
      while (parent && safety < 15) {
        let children = getAllElements(parent);
        let dateText = "";
        let amountText = "";

        let dateEl = children.find(child => {
          let t = (child.textContent || "").trim();
          return /\d+[\/-]\d+[\/-]\d+/.test(t) && t.length < 50 && !t.includes("options") && !t.includes("option");
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

    while (true) {
      let allElems = getAllElements(document);

      let descElements = allElems.filter(el => {
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

      let pageTx = [];
      for (let descEl of descElements) {
        let descText = descEl.textContent.trim().replace(/\s+/g, ' ');
        let rowData = findRowData(descEl);

        if (rowData && rowData.date) {
          if (!pageTx.some(tx => tx.desc === descText && tx.date === rowData.date)) {
            pageTx.push({
              desc: descText,
              date: rowData.date,
              amount: rowData.amount
            });
          }
        }
      }

      if (pageTx.length === 0) break;

      allTx.push(...pageTx);

      // Guardar el texto del primer elemento antes de hacer clic en Siguiente
      let firstTradeBefore = descElements[0] ? descElements[0].textContent.trim() : "";

      let nextBtn = allElems.find(el => {
        if (el.tagName !== 'BUTTON' && el.tagName !== 'A') return false;
        if (el.disabled) return false;
        let text = (el.textContent || el.innerText || "").trim().toLowerCase();
        let aria = (el.getAttribute('aria-label') || "").toLowerCase();
        let title = (el.getAttribute('title') || "").toLowerCase();
        
        return text.includes("siguiente") || text.includes("next") || text === ">" || text === "»" ||
               aria.includes("next") || aria.includes("siguiente") ||
               title.includes("next") || title.includes("siguiente");
      });
      if (!nextBtn) break;

      nextBtn.click();
      page++;

      let changed = false;
      for (let attempts = 0; attempts < 30; attempts++) {
        await new Promise(resolve => setTimeout(resolve, 200));
        let newElems = getAllElements(document);
        let newDescElements = newElems.filter(el => {
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
        let firstTradeAfter = newDescElements[0] ? newDescElements[0].textContent.trim() : "";
        if (firstTradeAfter !== firstTradeBefore && firstTradeAfter !== "") {
          changed = true;
          break;
        }
      }
      if (!changed) {
        console.warn("⚠️ Advertencia: La página no pareció cambiar tras hacer clic en Siguiente. Deteniendo paginación...");
        break;
      }

      // Si es una ejecución automática de fondo, NO paginar más de 1 página
      if (isSilent) break;
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

    let openPositions = {};
    let trades = [];

    for (let tx of allTx) {
      let parsed = parseDesc(tx.desc);
      if (!parsed) continue;

      parsed.date = tx.date;
      let key = `${parsed.ticker}|${parsed.expiry}|${parsed.type}|${parsed.strike}`;

      if (parsed.action === 'buy') {
        if (!openPositions[key]) openPositions[key] = [];
        openPositions[key].push({
          date: parsed.date,
          price: parsed.price,
          quantity: parsed.quantity,
          ticker: parsed.ticker,
          expiry: parsed.expiry,
          type: parsed.type,
          strike: parsed.strike
        });
      } else {
        let sellQty = parsed.quantity;
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
          trades.push({
            ticker: parsed.ticker,
            type: parsed.type,
            strike: parsed.strike,
            expiry: parsed.expiry,
            quantity: sellQty,
            buyDate: "",
            buyPrice: 0,
            sellDate: sellDate,
            sellPrice: sellPrice,
            status: 'Cerrado',
            strategy: parsed.action === 'expire' ? "Histórico UCharts (Vencimiento sin compra visible)" : "Histórico UCharts (Venta Huérfana)"
          });
        }
      }
    }

    for (let key in openPositions) {
      for (let openBuy of openPositions[key]) {
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
      }
    }

    if (trades.length === 0) return { ok: false, error: `Etapa interpretación: se leyeron ${allTx.length} movimientos, pero ninguno coincidió con el formato esperado de UCharts.` };

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
        fetch(WEBHOOK_URL, {
          method: "POST",
          mode: "no-cors",
          headers: { "Content-Type": "text/plain" },
          body: data
        }).then(() => resolve({ ok: true, status: 0, body: {} })).catch(() => resolve({ ok: false, status: 0, body: {} }));
      }
    });

    if (!isSilent) {
      if (ok.ok) {
        alert(`🎉 ¡Sincronización masiva completada! ${trades.length} operaciones enviadas con éxito.`);
      } else {
        const detail = ok.body?.message || `HTTP ${ok.status || "sin respuesta"}`;
        return { ok: false, error: `Etapa envío: el webhook rechazó la importación (${detail}).` };
      }
    }
    return ok.ok ? { ok: true, count: trades.length } : { ok: false, error: "Etapa envío: el webhook no confirmó la importación." };
  }
})();
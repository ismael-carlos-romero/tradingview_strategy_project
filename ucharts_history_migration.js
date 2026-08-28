/**
 * UCharts History Scraper & Google Sheets Migrator (Versión Online con Protección contra Bucles)
 * 
 * Esta versión envía los datos directamente al Webhook de Google Sheets (Online) y
 * previene bucles infinitos en la paginación mediante control de duplicados en tiempo real.
 */

(async function() {
  const WEBHOOK_URL = "TU_WEBHOOK_URL_AQUÍ"; // URL configurada automáticamente
  
  if (WEBHOOK_URL === "TU_WEBHOOK_URL_AQUÍ") {
    console.error("❌ ERROR: Debes configurar la variable WEBHOOK_URL con la URL de tu Google Apps Script.");
    return;
  }

  console.log("🚀 Iniciando extracción del historial de UCharts (Versión Online)...");
  
  // Función para obtener todos los elementos del DOM, incluyendo Shadow DOM e iFrames
  function getAllElements(root = document) {
    let elements = [];
    
    function traverse(node) {
      if (!node) return;
      
      if (node.nodeType === Node.ELEMENT_NODE) {
        elements.push(node);
        
        // Shadow DOM
        if (node.shadowRoot) {
          traverse(node.shadowRoot);
        }
        
        // iFrame
        if (node.tagName === 'IFRAME') {
          try {
            if (node.contentDocument) {
              traverse(node.contentDocument);
            }
          } catch (e) {
            // Ignorar frames cross-origin
          }
        }
      }
      
      // Hijos
      let child = node.firstChild;
      while (child) {
        traverse(child);
        child = child.nextSibling;
      }
    }
    
    traverse(root);
    return elements;
  }

  // Helper para obtener el padre cruzando límites de Shadow DOM
  function getParent(el) {
    if (!el) return null;
    if (el.parentElement) return el.parentElement;
    if (el.parentNode) {
      if (el.parentNode.host) { // Cruzar Shadow DOM boundary
        return el.parentNode.host;
      }
      return el.parentNode;
    }
    return null;
  }

  // Encuentra la fecha y el monto asociados a un elemento de descripción
  function findRowData(descEl) {
    let parent = descEl;
    let safety = 0;
    
    while (parent && safety < 15) {
      // Buscar elementos de fecha y monto descendientes de este ancestro
      let children = getAllElements(parent);
      
      let dateText = "";
      let amountText = "";
      
      // Buscar fecha: formato mm/dd/aaaa o aaaa-mm-dd
      let dateEl = children.find(child => {
        let t = (child.textContent || "").trim();
        return /\d+[\/-]\d+[\/-]\d+/.test(t) && t.length < 50 && !t.includes("options") && !t.includes("option");
      });
      if (dateEl) {
        dateText = dateEl.textContent.trim().replace(/\s+/g, ' ');
      }
      
      // Buscar monto: signo de dólar opcional y números
      let amountEl = children.find(child => {
        let t = (child.textContent || "").trim();
        return /-?\$[\d,.]+\b/.test(t) && t.length < 30 && t !== dateText;
      });
      if (amountEl) {
        amountText = amountEl.textContent.trim();
      }
      
      if (dateText) {
        return {
          date: dateText,
          amount: amountText
        };
      }
      
      parent = getParent(parent);
      safety++;
    }
    return null;
  }

  let allTx = [];
  let seenTxKeys = new Set();
  let page = 1;
  
  while (true) {
    console.log(`📖 Leyendo página ${page}...`);
    
    // Obtener todos los elementos visibles de la página actual
    let allElems = getAllElements(document);
    
    // Filtrar elementos de descripción de opciones (robusto para inglés y español)
    let descElements = allElems.filter(el => {
      let t = (el.textContent || "").trim();
      let hasKeywords = (t.includes("Comprar") || t.includes("Vender") || t.includes("Buy") || t.includes("Sell")) && 
                        (t.includes("options") || t.includes("option") || t.includes("opción") || t.includes("opciones") || t.includes("contrato"));
      if (!hasKeywords) return false;
      
      // Solo queremos el elemento más profundo que contiene el texto completo
      let childHasKeywords = Array.from(el.children).some(child => {
        let ct = (child.textContent || "").trim();
        return (ct.includes("Comprar") || ct.includes("Vender") || ct.includes("Buy") || ct.includes("Sell")) && 
               (ct.includes("options") || ct.includes("option") || ct.includes("opción") || ct.includes("opciones") || ct.includes("contrato"));
      });
      return !childHasKeywords;
    });

    console.log(`🔍 Encontrados ${descElements.length} elementos de descripción en página ${page}.`);
    
    let pageTx = [];
    let newTxCount = 0;
    
    for (let descEl of descElements) {
      let descText = descEl.textContent.trim().replace(/\s+/g, ' ');
      let rowData = findRowData(descEl);
      
      if (rowData && rowData.date) {
        let key = `${descText}|${rowData.date}`;
        if (!seenTxKeys.has(key)) {
          seenTxKeys.add(key);
          pageTx.push({
            desc: descText,
            date: rowData.date,
            amount: rowData.amount
          });
          newTxCount++;
        }
      }
    }
    
    // Protección contra bucles infinitos: Si no se extrajo ninguna transacción nueva en esta página, detenemos el proceso
    if (newTxCount === 0) {
      console.log("⏹️ Todos los elementos de esta página ya fueron procesados o el botón 'Siguiente' no cargó nuevos datos. Fin de paginación.");
      break;
    }
    
    allTx.push(...pageTx);
    console.log(`✅ Página ${page} procesada: ${newTxCount} transacciones nuevas. Total acumulado: ${allTx.length}`);
    
    // Guardar el texto del primer elemento antes de hacer clic en Siguiente
    let firstTradeBefore = descElements[0] ? descElements[0].textContent.trim() : "";

    // Buscar el botón "Siguiente" activo
    let nextBtn = allElems.find(el => {
      return el.tagName === 'BUTTON' && 
             (el.textContent || el.innerText || "").trim().includes("Siguiente") && 
             !el.disabled;
    });
    
    if (!nextBtn) {
      console.log("⏹️ Botón 'Siguiente' deshabilitado o no encontrado. Fin de paginación.");
      break;
    }
    
    console.log("➡️ Avanzando a la siguiente página...");
    nextBtn.click();
    page++;
    
    // Esperar dinámicamente a que cargue la página comprobando si cambió el primer elemento
    let changed = false;
    for (let attempts = 0; attempts < 30; attempts++) { // max 6 segundos (30 * 200ms)
      await new Promise(resolve => setTimeout(resolve, 200));
      let newElems = getAllElements(document);
      let newDescElements = newElems.filter(el => {
        let t = (el.textContent || "").trim();
        let hasKeywords = (t.includes("Comprar") || t.includes("Vender") || t.includes("Buy") || t.includes("Sell")) && 
                          (t.includes("options") || t.includes("option") || t.includes("opción") || t.includes("opciones") || t.includes("contrato"));
        if (!hasKeywords) return false;
        let childHasKeywords = Array.from(el.children).some(child => {
          let ct = (child.textContent || "").trim();
          return (ct.includes("Comprar") || ct.includes("Vender") || ct.includes("Buy") || ct.includes("Sell")) && 
                 (ct.includes("options") || ct.includes("option") || ct.includes("opción") || ct.includes("opciones") || ct.includes("contrato"));
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
      console.warn("⚠️ Advertencia: La página no pareció cambiar tras hacer clic en Siguiente o tardó más de 6 segundos. Deteniendo paginación...");
      break;
    }
  }
  
  console.log(`📊 Extracción terminada. Total transacciones brutas extraídas: ${allTx.length}`);
  if (allTx.length === 0) {
    alert("⚠️ No se encontró ninguna transacción en el historial. Asegúrate de estar en la pestaña 'Historial' de UCharts y que las transacciones se muestren en pantalla.");
    return;
  }
  
  // Función para parsear descripción de forma ultra-robusta (inglés y español traducido)
  function parseDesc(desc) {
    let regex = /(Comprar|Vender|Buy|Sell)\s+(\d+)\s+(?:options?|opción|opciones|contratos?|de|compra|venta|\s)+\s+(\S+)\s+(.*?)\s+(Call|Put|Compra|Venta|Llamada|Poner)\s+([\d.,]+)\s+@\s+([\d.,]+)/i;
    let match = desc.match(regex);
    if (match) {
      let actionStr = match[1].toLowerCase();
      let typeStr = match[5].toLowerCase();
      let typeClean = "CALL";
      if (typeStr === 'put' || typeStr === 'venta' || typeStr === 'poner') {
        typeClean = "PUT";
      }
      return {
        action: (actionStr === 'comprar' || actionStr === 'buy') ? 'buy' : 'sell',
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
  
  // Ordenar cronológicamente (más antiguo primero) para poder emparejar compras y ventas
  allTx.sort((a, b) => new Date(a.date) - new Date(b.date));
  
  let openPositions = {}; // key -> lista de compras abiertas
  let trades = [];
  
  console.log("🔄 Procesando y emparejando transacciones...");
  
  for (let tx of allTx) {
    let parsed = parseDesc(tx.desc);
    if (!parsed) {
      console.warn("⚠️ No se pudo parsear descripción:", tx.desc);
      continue;
    }
    
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
    } else { // sell
      let sellQty = parsed.quantity;
      let sellPrice = parsed.price;
      let sellDate = parsed.date;
      
      while (sellQty > 0 && openPositions[key] && openPositions[key].length > 0) {
        let openBuy = openPositions[key][0];
        if (openBuy.quantity <= sellQty) {
          // Consumir compra abierta completa
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
          // Consumir compra abierta parcial
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
        // Venta sin compra previa en el historial (ocurre si la compra fue antes de la ventana del historial)
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
          strategy: "Histórico UCharts (Venta Huérfana)"
        });
      }
    }
  }
  
  // Guardar compras restantes que no se vendieron como posiciones abiertas
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
  
  console.log(`📈 Procesamiento finalizado. Se crearon ${trades.length} operaciones emparejadas.`);
  console.log("📤 Enviando datos directamente a Google Sheets...");
  
  try {
    let response = await fetch(WEBHOOK_URL, {
      method: "POST",
      mode: "no-cors", 
      headers: {
        "Content-Type": "text/plain" 
      },
      body: JSON.stringify({
        action: "bulk_import",
        trades: trades
      })
    });
    
    console.log("🎉 ¡Sincronización masiva enviada con éxito! Revisa tu Google Sheet.");
    alert(`¡Sincronización completada! ${trades.length} operaciones enviadas directamente a tu planilla.`);
  } catch (err) {
    console.error("❌ Error al enviar operaciones al webhook:", err);
    alert("Hubo un error al enviar los datos a Google Sheets. Revisa la consola para más detalles.");
  }
})();

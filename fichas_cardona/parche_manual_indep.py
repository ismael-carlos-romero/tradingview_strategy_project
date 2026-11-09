import re
src = r"..\ucharts_sync_userscript_v5.0.44.js"
dst = r"..\ucharts_sync_userscript_v5.0.45.js"
s = open(src, encoding="utf-8").read()
s = s.replace("5.0.44", "5.0.45")


def rep(a, b, n=1):
    global s
    assert s.count(a) == n, (s.count(a), a[:90])
    s = s.replace(a, b)


# --- A. HTML del Manual: campos propios ---
rep('<div id="manual-cfg" style="display:flex;flex-direction:column;gap:6px;"></div>',
    '''<div id="manual-cfg" style="display:flex;flex-direction:column;gap:6px;">
<div style="font-size:12px;color:#9ca3af;">Opciones propias del Manual: no dependen de Config. ni las usan las compras automáticas.</div>
<div class="form-row"><span>Contratos:</span><input type="number" id="man-qty" class="form-input" value="1" min="1"></div>
<div class="form-row"><span>Días de Vencimiento:</span><input type="number" id="man-dte" class="form-input" value="7" min="0"></div>
<div class="form-row"><label style="display:flex;align-items:center;gap:4px;"><input type="checkbox" id="man-chk-tp-pct" checked><span>Take Profit %:</span></label><input type="number" id="man-tp-pct" class="form-input" value="5"></div>
<div class="form-row"><label style="display:flex;align-items:center;gap:4px;"><input type="checkbox" id="man-chk-tp-usd"><span>Take Profit $:</span></label><input type="number" id="man-tp-usd" class="form-input" value="1000" disabled></div>
<div class="form-row"><label style="display:flex;align-items:center;gap:4px;"><input type="checkbox" id="man-chk-sl-pct" checked><span>Stop Loss %:</span></label><input type="number" id="man-sl-pct" class="form-input" value="10"></div>
<div class="form-row"><label style="display:flex;align-items:center;gap:4px;"><input type="checkbox" id="man-chk-sl-usd"><span>Stop Loss $:</span></label><input type="number" id="man-sl-usd" class="form-input" value="500" disabled></div>
</div>''')
rep("Compra el activo escrito con estas opciones (son las mismas de la pestaña Config.: se cambian en cualquiera de las dos). Quedan identificadas como MANUAL.",
    "Compra el activo escrito con las opciones de arriba (independientes de Config.). Esas posiciones conservan su propio TP/SL. Quedan identificadas como MANUAL.")

# --- B. quitar espejo y poner config manual propia ---
a = s.find("    // v5.0.45: opciones de Config espejadas en Manual")
b = s.find("    // Event listener: Cerrar Todo (Pánico)\n")
assert 0 < a < b
js_panel = r"""    // v5.0.45: configuracion MANUAL independiente de Config. (se guarda aparte; las compras automaticas no la usan)
    const MAN_DEF = { qty: 1, dte: 7, usePct: true, tpPct: 5, useUsd: false, tpUsd: 1000, useSlPct: true, slPct: 10, useSlUsd: false, slUsd: 500 };
    const manEls = {
      qty: panel.querySelector('#man-qty'), dte: panel.querySelector('#man-dte'),
      usePct: panel.querySelector('#man-chk-tp-pct'), tpPct: panel.querySelector('#man-tp-pct'),
      useUsd: panel.querySelector('#man-chk-tp-usd'), tpUsd: panel.querySelector('#man-tp-usd'),
      useSlPct: panel.querySelector('#man-chk-sl-pct'), slPct: panel.querySelector('#man-sl-pct'),
      useSlUsd: panel.querySelector('#man-chk-sl-usd'), slUsd: panel.querySelector('#man-sl-usd')
    };
    function manToggleDisabled() {
      manEls.tpPct.disabled = !manEls.usePct.checked; manEls.tpUsd.disabled = !manEls.useUsd.checked;
      manEls.slPct.disabled = !manEls.useSlPct.checked; manEls.slUsd.disabled = !manEls.useSlUsd.checked;
    }
    function readManualCfg() {
      const num = (el, d) => { const v = parseFloat(el.value); return isFinite(v) ? v : d; };
      return {
        qty: Math.max(1, parseInt(manEls.qty.value, 10) || 1), dte: Math.max(0, parseInt(manEls.dte.value, 10) || 0),
        usePct: manEls.usePct.checked, tpPct: num(manEls.tpPct, 5), useUsd: manEls.useUsd.checked, tpUsd: num(manEls.tpUsd, 1000),
        useSlPct: manEls.useSlPct.checked, slPct: num(manEls.slPct, 10), useSlUsd: manEls.useSlUsd.checked, slUsd: num(manEls.slUsd, 500)
      };
    }
    function manSave() { try { localStorage.setItem('ucharts_manual_cfg', JSON.stringify(readManualCfg())); } catch (e) { /* sin almacenamiento */ } }
    (function manInit() {
      let c = Object.assign({}, MAN_DEF);
      try { c = Object.assign(c, JSON.parse(localStorage.getItem('ucharts_manual_cfg') || '{}')); } catch (e) { /* defaults */ }
      manEls.qty.value = c.qty; manEls.dte.value = c.dte;
      manEls.usePct.checked = !!c.usePct; manEls.tpPct.value = c.tpPct;
      manEls.useUsd.checked = !!c.useUsd; manEls.tpUsd.value = c.tpUsd;
      manEls.useSlPct.checked = !!c.useSlPct; manEls.slPct.value = c.slPct;
      manEls.useSlUsd.checked = !!c.useSlUsd; manEls.slUsd.value = c.slUsd;
      manToggleDisabled();
      Object.keys(manEls).forEach(k => ['input', 'change'].forEach(ev => manEls[k].addEventListener(ev, () => { manToggleDisabled(); manSave(); })));
    })();

"""
s = s[:a] + js_panel + s[b:]

# --- C. handlers de compra manual ---
for tipo in ("CALL", "PUT"):
    rep(f"""      const qty = parseInt(panel.querySelector('#trader-qty').value, 10) || 100;
      const profile = localStorage.getItem('ucharts_trader_profile') || 'corto';

      lastTraderError = "";
      const ok = await executeOrder(ticker, '{tipo}', profile, qty, null, {{ trace: {{ modo: 'MANUAL', ticker_manual: ticker }} }});""",
        f"""      const mcfg = readManualCfg();
      manSave();

      lastTraderError = "";
      const ok = await executeOrder(ticker, '{tipo}', 'corto', mcfg.qty, null, {{ manualCfg: mcfg, trace: {{ modo: 'MANUAL', ticker_manual: ticker }} }});""")

# --- D. helpers a nivel superior (antes de executeOrder) ---
i = s.find("function executeOrder(")
ls = s.rfind("\n", 0, i) + 1
helpers = r"""  // v5.0.45: posiciones MANUALES con su propia configuracion (independiente de Config.)
  const MANUAL_POS_KEY = 'ucharts_manual_positions';
  let activeDteOverride = null;
  function loadManualPositions() {
    try { return JSON.parse(localStorage.getItem(MANUAL_POS_KEY) || '[]'); } catch (e) { return []; }
  }
  function registerManualPosition(ticker, type, strike, expiryKey, cfg) {
    try {
      const a = loadManualPositions().filter(p => !(p.ticker === ticker && p.type === type && Number(p.strike) === Number(strike) && p.expiryKey === expiryKey));
      a.push({ ticker, type, strike, expiryKey, cfg, ts: Date.now() });
      while (a.length > 200) a.shift();
      localStorage.setItem(MANUAL_POS_KEY, JSON.stringify(a));
    } catch (e) { /* sin almacenamiento */ }
  }
  function manualCfgForCard(cardText) {
    if (findTrackedPositionForCard(cardText)) return null; // si tambien la tiene el bot, manda la config del bot
    const a = loadManualPositions();
    for (let i = a.length - 1; i >= 0; i--) {
      const p = a[i];
      const w = p.type === 'CALL' ? 'Call' : 'Put';
      if (cardText.includes(p.ticker) && cardText.includes(w) && (cardText.includes(Number(p.strike).toFixed(2)) || cardText.includes(String(p.strike)))) return p;
    }
    return null;
  }
"""
s = s[:ls] + helpers + s[ls:]

# --- E. executeOrderCore ---
rep("const { skipAutoTP = false, banderinBucketCheck = false, cardonaBucketCheck = false } = options;",
    "let { skipAutoTP = false, banderinBucketCheck = false, cardonaBucketCheck = false } = options;")
k = s.find("async function executeOrderCore")
k2 = s.find("    isTradeFormBusy = true;\n", k)
assert 0 < k2 - k < 600
s = s[:k2] + "    isTradeFormBusy = true;\n    activeDteOverride = (options.manualCfg && options.manualCfg.dte !== undefined) ? options.manualCfg.dte : null;\n" + s[k2 + len("    isTradeFormBusy = true;\n"):]
rep("    } finally {\n      isTradeFormBusy = false;\n    }\n\n    // A partir de acá el lock del formulario ya se soltó",
    "    } finally {\n      isTradeFormBusy = false;\n      activeDteOverride = null;\n    }\n\n    if (options.manualCfg && buyResult) {\n      registerManualPosition(ticker, String(type).toUpperCase(), buyResult.strike, buyResult.expiryKey, options.manualCfg);\n      if (!options.manualCfg.usePct) skipAutoTP = true;\n    }\n\n    // A partir de acá el lock del formulario ya se soltó")

# --- F. DTE ---
rep("      const targetDte = dteInputEl\n", "      const targetDte = (activeDteOverride !== null && activeDteOverride !== undefined) ? activeDteOverride : dteInputEl\n")

# --- G. TP limite por tarjeta ---
j = s.find("const tpPct = parseFloat(document.getElementById('tp-pct-val').value) || 15.0;\n        const targetPrice")
assert j > 0
ini = s.rfind("async function closePositionByCardCore", 0, j)
assert ini > 0 and "function " not in s[ini + 30:j].replace("function ", "", 0).split("closePositionByCardCore")[-1] or True
mid = s[ini + 40:j]
print("funciones entre closePositionByCardCore y TP:", len(re.findall(r"\n  (?:async )?function ", mid)))
rep("const tpPct = parseFloat(document.getElementById('tp-pct-val').value) || 15.0;\n        const targetPrice",
    "const _mcTp = manualCfgForCard((cardElement.textContent || '').trim().replace(/\\s+/g, ' '));\n        const tpPct = _mcTp ? (_mcTp.cfg.tpPct || 5) : (parseFloat(document.getElementById('tp-pct-val').value) || 15.0);\n        const targetPrice")

# --- H. monitor de PnL: limites por tarjeta ---
rep("      const trackedPos = findTrackedPositionForCard(cardText);\n",
    """      const trackedPos = findTrackedPositionForCard(cardText);
      const mcCard = manualCfgForCard(cardText);
      const lm = mcCard
        ? { useTpPct: mcCard.cfg.usePct, tpPctLimit: mcCard.cfg.tpPct, useTpUsd: mcCard.cfg.useUsd, tpUsdLimit: mcCard.cfg.tpUsd,
            useSlPct: mcCard.cfg.useSlPct, slPctLimit: mcCard.cfg.slPct, useSlUsd: mcCard.cfg.useSlUsd, slUsdLimit: mcCard.cfg.slUsd }
        : { useTpPct, tpPctLimit, useTpUsd, tpUsdLimit, useSlPct, slPctLimit, useSlUsd, slUsdLimit };
""")
rep("        : 'MANUAL|' + (descEl.textContent || '').trim();",
    "        : (mcCard ? pendingCloseKey(mcCard.ticker, mcCard.type, mcCard.strike) : 'MANUAL|' + (descEl.textContent || '').trim());")
p0 = s.find("      // Take Profit: sólo posiciones del bot")
p1 = s.find("      // EXPIRATION_GUARD (mejora post-análisis")
assert 0 < p0 < p1
blk = s[p0:p1]
blk = blk.replace("if (trackedPos && !tpAlreadyPlaced)", "if ((trackedPos || mcCard) && !tpAlreadyPlaced)")
for nm in ("useTpPct", "tpPctLimit", "useTpUsd", "tpUsdLimit", "useSlPct", "slPctLimit", "useSlUsd", "slUsdLimit"):
    blk = re.sub(r"(?<![\w.])" + nm + r"\b", "lm." + nm, blk)
s = s[:p0] + blk + s[p1:]
open(dst, "w", encoding="utf-8").write(s)
print("ok", len(s))

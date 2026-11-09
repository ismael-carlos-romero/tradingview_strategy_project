import re, shutil
src = "ucharts_sync_userscript_v5.0.42.js"
dst = "ucharts_sync_userscript_v5.0.43.js"
s = open(src, encoding="utf-8").read()
n42 = s.count("5.0.42")
s = s.replace("5.0.42", "5.0.43")

# 1) campo de activo en la pestaña Manual
a = '<div class="sec-pane" data-sec="manual"><div style="display:flex;flex-direction:column;gap:6px;"><div class="btn-action-group">'
assert s.count(a) == 1
campo = ('<div class="sec-pane" data-sec="manual"><div style="display:flex;flex-direction:column;gap:6px;">'
         '<div class="form-row"><span>Activo:</span>'
         '<input type="text" id="manual-ticker" class="form-input" value="SPY" maxlength="6" placeholder="Ej: AAPL" autocomplete="off" style="text-transform:uppercase;"></div>'
         '<div class="btn-action-group">')
s = s.replace(a, campo)

# 2) helper + persistencia, antes del listener de CALL
b = "    // Event listener: Compra CALL\n"
assert s.count(b) == 1
helper = '''    // Activo de la compra manual (se recuerda el último usado)
    const manualTickerInput = panel.querySelector('#manual-ticker');
    try { manualTickerInput.value = (localStorage.getItem('ucharts_manual_ticker') || 'SPY').toUpperCase(); } catch (e) {}
    function getManualTicker() {
      const t = (manualTickerInput.value || '').trim().toUpperCase();
      if (!/^[A-Z][A-Z.\\-]{0,5}$/.test(t)) {
        alert('Escribí un activo válido en el campo «Activo» (ej: AAPL).');
        return null;
      }
      manualTickerInput.value = t;
      try { localStorage.setItem('ucharts_manual_ticker', t); } catch (e) {}
      return t;
    }

'''
s = s.replace(b, helper + b)

# 3) usar el activo escrito en lugar de SPY fijo
for lado, ide in (("CALL", "btn-buy-call"), ("PUT", "btn-buy-put")):
    x = f"const buyBtn = panel.querySelector('#{ide}');\n"
    assert s.count(x) == 1, ide
    s = s.replace(x, x + "      const ticker = getManualTicker();\n      if (!ticker) return;\n")
    y = f"executeOrder('SPY', '{lado}', profile, qty, null, {{ trace: {{ modo: 'MANUAL' }} }})"
    assert s.count(y) == 1, lado
    s = s.replace(y, f"executeOrder(ticker, '{lado}', profile, qty, null, {{ trace: {{ modo: 'MANUAL', ticker_manual: ticker }} }})")
    z = f"alert(`❌ Error al comprar {lado}."
    assert s.count(z) == 1, "alert" + lado
    s = s.replace(z, f"alert(`❌ Error al comprar {lado} de ${{ticker}}.")

s = s.replace("Las compras manuales quedan identificadas como MANUAL.", "Compra el activo escrito con la configuración de la pestaña Config. (perfil, contratos, TP, SL). Quedan identificadas como MANUAL.")
open(dst, "w", encoding="utf-8").write(s)
print("ok; versiones reemplazadas:", n42)

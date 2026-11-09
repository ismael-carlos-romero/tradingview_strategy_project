src = r"..\ucharts_sync_userscript_v5.0.43.js"
dst = r"..\ucharts_sync_userscript_v5.0.44.js"
s = open(src, encoding="utf-8").read()
n = s.count("5.0.43")
s = s.replace("5.0.43", "5.0.44")
a = 'autocomplete="off" style="text-transform:uppercase;"></div><div class="btn-action-group">'
assert s.count(a) == 1
s = s.replace(a, 'autocomplete="off" style="text-transform:uppercase;"></div><div id="manual-cfg" style="display:flex;flex-direction:column;gap:6px;"></div><div class="btn-action-group">')
t = "Compra el activo escrito con la configuración de la pestaña Config. (perfil, contratos, TP, SL). Quedan identificadas como MANUAL."
assert s.count(t) == 1
s = s.replace(t, "Compra el activo escrito con estas opciones (son las mismas de la pestaña Config.: se cambian en cualquiera de las dos). Quedan identificadas como MANUAL.")
b = "    // Event listener: Cerrar Todo (Pánico)\n"
assert s.count(b) == 1
js = r"""    // v5.0.44: opciones de Config espejadas en Manual (mismos valores, sin duplicar logica)
    (function mirrorConfig() {
      const box = panel.querySelector('#manual-cfg');
      const cfg = panel.querySelector('.sec-pane[data-sec="config"]');
      if (!box || !cfg) return;
      const prof = cfg.querySelector('.profile-selector');
      if (prof) {
        const pc = prof.cloneNode(true);
        pc.querySelectorAll('.profile-btn').forEach(mb => {
          const ob = prof.querySelector('.profile-btn[data-profile="' + mb.dataset.profile + '"]');
          if (!ob) return;
          mb.addEventListener('click', () => ob.click());
          const sync = () => mb.classList.toggle('active', ob.classList.contains('active'));
          new MutationObserver(sync).observe(ob, { attributes: true, attributeFilter: ['class'] });
          sync();
        });
        box.appendChild(pc);
      }
      cfg.querySelectorAll('.form-row').forEach(row => {
        if (row.querySelector('#daily-bucket-pct')) return;
        const rc = row.cloneNode(true);
        rc.querySelectorAll('input').forEach(mi => {
          const oi = mi.id ? row.querySelector('#' + mi.id) : null;
          if (!oi) return;
          mi.id = 'm-' + mi.id;
          const chk = mi.type === 'checkbox';
          const toO = () => {
            if (chk) oi.checked = mi.checked; else oi.value = mi.value;
            oi.dispatchEvent(new Event('input', { bubbles: true }));
            oi.dispatchEvent(new Event('change', { bubbles: true }));
            setTimeout(() => { mirrorAll(); }, 0);
          };
          const toM = () => { if (chk) mi.checked = oi.checked; else mi.value = oi.value; mi.disabled = oi.disabled; };
          mi._sync = toM;
          mi.addEventListener('input', toO);
          mi.addEventListener('change', toO);
          oi.addEventListener('input', () => setTimeout(toM, 0));
          oi.addEventListener('change', () => setTimeout(toM, 0));
          toM();
        });
        box.appendChild(rc);
      });
      function mirrorAll() { box.querySelectorAll('input').forEach(i => { if (i._sync) i._sync(); }); }
      setTimeout(mirrorAll, 1500);
    })();

"""
s = s.replace(b, js + b)
open(dst, "w", encoding="utf-8").write(s)
print("ok", n)

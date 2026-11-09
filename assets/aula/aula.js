/* Aula Virtual - interfaz (practica, correccion, progreso). Depende de aula_chart.js y de /api/aula/*. */
(function () {
  'use strict';
  const root = document.getElementById('aula-root'); if (!root) return;
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const LS = { get(k, d) { try { return localStorage.getItem(k) || d; } catch (e) { return d; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { } } };
  const S = { alumno: LS.get('aula_alumno', 'alumno1'), tab: 'practicar', defs: null, cur: null, chart: null, f: {}, tfs: new Set(), ayudas: [], t0: 0, corte: null, hist: [], res: null, init: false };
  const MODOS = { vela: 'Vela por vela', encontra: 'Encontrá la estrategia', reconoce: 'Reconocé el patrón', faltante: 'Detectá el requisito faltante', auditar: 'Auditá a Atlas', sesion: 'Práctica de la sesión actual' };
  const CLS = { CONFIRMADA: 'Confirmada', EN_FORMACION: 'En formación', NO_APLICA: 'No aplica' };
  const TABS = [['practicar', 'Practicar'], ['progreso', 'Progreso y dominio'], ['catalogo', 'Estrategias y cobertura'], ['historial', 'Historial'], ['datos', 'Datos y calidad'], ['revisiones', 'Revisiones']];
  async function api(path, body) {
    const f = (typeof customFetch === 'function') ? customFetch : fetch; const o = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {};
    try { const r = await f(path, o); let j; try { j = await r.json(); } catch (e) { j = { error: 'Respuesta no válida del servidor (HTTP ' + r.status + ')', recuperable: true }; } if (!r.ok && !j.error) j.error = 'HTTP ' + r.status; return j; }
    catch (e) { return { error: 'Sin conexión con el portal: ' + e.message, recuperable: true }; }
  }
  const A = (p, o) => api('/api/aula/' + p + (p.includes('?') ? '&' : '?') + 'alumno=' + encodeURIComponent(S.alumno) + (o || ''));
  const P = (p, b) => api('/api/aula/' + p, Object.assign({ alumno: S.alumno }, b || {}));
  const $ = (s, r) => (r || root).querySelector(s);
  const fmtT = t => (t || '').replace('T', ' ').slice(0, 16);
  const clsTag = c => '<span class="tag ' + (c === 'CONFIRMADA' ? 'ok' : c === 'EN_FORMACION' ? 'wa' : c === 'AMBIGUA' ? 'er' : '') + '">' + esc(CLS[c] || c) + '</span>';
  const err = e => '<div class="msg er">⚠ ' + esc(e.error || e) + (e.recuperable ? ' <button data-act="retry">Reintentar</button>' : '') + '</div>';

  function shell() {
    root.innerHTML = '<div class="hd"><div><h2>🎓 Aula Virtual</h2><div class="mu">Practicá las 12 estrategias de Cardona sobre gráficos reales, al azar y repetibles. Solo enseñanza: no opera ni envía órdenes.</div></div>' +
      '<div class="row"><label class="mu">Alumno <input id="av-al" value="' + esc(S.alumno) + '" size="12" maxlength="30"></label><div id="av-meta" style="min-width:210px"></div></div></div>' +
      '<div class="tabs">' + TABS.map(t => '<button data-tab="' + t[0] + '" class="' + (S.tab === t[0] ? 'on' : '') + '">' + t[1] + '</button>').join('') + '</div><div id="av-body"></div>';
    $('#av-al').onchange = e => { S.alumno = (e.target.value || 'alumno1').trim().replace(/[^\w.-]/g, '_').slice(0, 30) || 'alumno1'; LS.set('aula_alumno', S.alumno); S.cur = null; show(); metaBar(); };
    root.querySelectorAll('[data-tab]').forEach(b => b.onclick = () => { S.tab = b.dataset.tab; if (S.tab !== 'practicar' && S.cur) autosave(true); shell(); show(); metaBar(); });
  }
  async function metaBar() {
    const r = await A('progreso'); const el = $('#av-meta'); if (!el) return; if (r.error) { el.innerHTML = ''; return; }
    const t = r.tiempo || {}; const hoy = Math.round((t.hoy_min != null ? t.hoy_min : (t.hoy_s || 0) / 60) * 10) / 10, meta = t.meta_min || 60;
    el.innerHTML = '<div class="mu">Práctica de hoy: ' + hoy + ' / ' + meta + ' min</div><div class="bar"><i style="width:' + Math.min(100, hoy / meta * 100) + '%"></i></div>';
  }
  function show() { const b = $('#av-body'); ({ practicar: vPracticar, progreso: vProgreso, catalogo: vCatalogo, historial: vHistorial, datos: vDatos, revisiones: vRevisiones })[S.tab](b); }
  async function ensureDefs() { if (!S.defs) { const r = await api('/api/aula/estrategias'); if (r.error) return r; S.defs = r; S.byId = {}; r.estrategias.forEach(e => S.byId[e.id] = e); } return S.defs; }

  // ------------------------------------------------------------------ Practicar
  async function vPracticar(b) {
    if (S.cur) return vDesafio(b);
    b.innerHTML = '<div class="mu">Cargando…</div>'; const d = await ensureDefs(); const est = await api('/api/aula/estado'); if (d.error) { b.innerHTML = err(d); return; }
    const tk = (est.universo && est.universo.tickers) || [];
    const ab = LS.get('aula_abierto_' + S.alumno, '');
    b.innerHTML = (ab ? '<div class="card"><div class="msg wa">Tenés un desafío sin entregar (#' + esc(ab) + '). <button id="l-cont" class="pri">Continuar donde lo dejaste</button></div></div>' : '') + '<div class="card"><h3>Nuevo desafío</h3><div class="g2">' +
      '<label>Modo de juego<br><select id="l-modo">' + Object.keys(MODOS).map(k => '<option value="' + k + '">' + MODOS[k] + '</option>').join('') + '</select></label>' +
      '<label>Ruta<br><select id="l-ruta"><option value="evaluable">Desafío evaluable (con referencia)</option><option value="exploracion">Exploración libre (activo/período abierto)</option></select></label>' +
      '<label>Estrategia<br><select id="l-est"><option value="">Aleatoria</option>' + d.estrategias.map(e => '<option value="' + e.id + '">' + esc(e.nombre) + '</option>').join('') + '</select></label>' +
      '<label>Activo<br><select id="l-tk"><option value="">Aleatorio</option>' + tk.map(t => '<option>' + esc(t) + '</option>').join('') + '</select></label>' +
      '<label>Tipo de caso<br><select id="l-cat"><option value="">Mezcla (confirmado / en formación / contraejemplo)</option><option value="confirmado">Confirmado</option><option value="formacion">En formación</option><option value="contraejemplo">Contraejemplo</option><option value="faltante">Con requisito faltante</option></select></label>' +
      '<label>Semilla (opcional, para repetir)<br><input id="l-seed" type="number" placeholder="aleatoria"></label></div>' +
      '<div class="row" style="margin-top:8px"><label class="ck"><input type="checkbox" id="l-ex" checked> <span>Modo examen (sin pistas, sin lámina ni solución hasta entregar)</span></label>' +
      '<button class="pri" id="l-go">Empezar desafío</button></div><div id="l-msg"></div></div>' +
      '<div class="card"><h3>Repasos pendientes</h3><div id="l-rep" class="mu">…</div></div>';
    if ($('#l-cont')) $('#l-cont').onclick = () => cargar(ab);
    $('#l-modo').onchange = () => { const m = $('#l-modo').value; $('#l-ruta').disabled = (m === 'sesion'); $('#l-cat').disabled = (m === 'sesion' || m === 'faltante' || m === 'auditar'); $('#l-est').disabled = (m === 'reconoce'); };
    $('#l-go').onclick = async () => {
      const m = $('#l-modo').value, body = { modo: m === 'auditar' ? 'vela' : m, ruta: $('#l-ruta').value, estrategia: $('#l-est').value || null, ticker: $('#l-tk').value || null, categoria: $('#l-cat').value || null, examen: $('#l-ex').checked };
      if ($('#l-seed').value) body.seed = parseInt($('#l-seed').value, 10); $('#l-go').disabled = true; $('#l-msg').innerHTML = '<div class="msg">Generando caso reproducible…</div>';
      const r = await P('desafio', body); $('#l-go').disabled = false;
      if (r.error) { $('#l-msg').innerHTML = err(r) + (r.faltan ? '<div class="mu">' + esc(JSON.stringify(r.faltan)) + '</div>' : ''); return; }
      S.auditar = (m === 'auditar'); await cargar(r.id);
    };
    const rp = await A('repasos'); const due = (Array.isArray(rp) ? rp : []).filter(x => !x.hecho);
    $('#l-rep').innerHTML = due.length ? '<table><tr><th>Estrategia</th><th>Criterio</th><th>Vence</th><th>Paso</th></tr>' + due.slice(0, 12).map(x => '<tr><td>' + esc((S.byId[x.estrategia] || {}).nombre || x.estrategia) + '</td><td>' + esc(x.criterio) + '</td><td>' + esc(x.vence) + '</td><td>' + x.paso + '</td></tr>').join('') + '</table>' : 'No tenés repasos programados todavía: se crean al fallar un requisito.';
  }
  async function cargar(id) {
    const r = await A('desafio?id=' + encodeURIComponent(id)); if (r.error) { alert(r.error); return; }
    if (r.entregado) LS.set('aula_abierto_' + S.alumno, ''); else LS.set('aula_abierto_' + S.alumno, id);
    S.cur = r; S.f = { crit: {}, hip: {}, estrategia: r.desafio.estrategia || '', tf_decision: '', clasificacion: '', explicacion: '', condicion_faltante: '', vela_conf: false, ninguna: false };
    S.tfs = new Set(['hora']); S.ayudas = []; S.t0 = Date.now(); S.corte = r.desafio.corte; S.res = null; S.hints = 0;
    const bor = r.borrador; if (bor && bor.f) { S.f = Object.assign(S.f, bor.f); S.tfs = new Set(bor.tfs || ['hora']); S.ayudas = bor.ayudas || []; S.corte = bor.corte || S.corte; S.restore = bor.chart; S.t0 = Date.now() - (bor.seg || 0) * 1000; }
    else { try { const l = JSON.parse(LS.get('aula_borr_' + id, 'null')); if (l && l.f) { S.f = Object.assign(S.f, l.f); S.tfs = new Set(l.tfs || ['hora']); S.restore = l.chart; S.ayudas = l.ayudas || []; } } catch (e) { S.restore = null; } }
    shell(); show();
  }
  let saveT = null;
  function autosave(now) {
    if (!S.cur || S.cur.entregado && !S.reint) return; clearTimeout(saveT);
    const go = () => { const st = { f: S.f, tfs: [...S.tfs], ayudas: S.ayudas, corte: S.corte, chart: S.chart ? S.chart.toJSON() : null, seg: Math.round((Date.now() - S.t0) / 1000) };
      LS.set('aula_borr_' + S.cur.desafio.id, JSON.stringify(st)); api('/api/aula/borrador', { desafio: S.cur.desafio.id, alumno: S.alumno, estado: st }); };
    if (now) go(); else saveT = setTimeout(go, 700);
  }

  // ------------------------------------------------------------------ Desafio
  function chartData(sn) { return { hora: sn.hora || [], m30: sn.m30 || [], diario: sn.diario || [] }; }
  const TOOLS = [['mover', '✋ Mover'], ['linea', '／ Línea'], ['horizontal', '— Horizontal'], ['canal', '▱ Canal'], ['flecha', '➚ Flecha'], ['circulo', '◯ Círculo'], ['texto', 'T Texto'], ['borrar', '⌫ Borrar'], ['marcar', '★ Marcar vela']];
  function critRows(sid) {
    const e = S.byId[sid]; if (!e) return '<div class="mu">Elegí primero la estrategia que creés que aplica.</div>';
    return e.criterios.map(c => { const v = S.f.crit[c.id] || ''; return '<div class="crit"><span>' + c.n + '. ' + esc(c.texto) + (c.origen && c.origen !== 'lamina' ? ' <span class="tag" title="Regla que no figura igual en la lámina de Cardona">' + esc(c.origen) + '</span>' : '') + '</span>' +
      '<select data-crit="' + c.id + '"><option value="">—</option><option value="ok"' + (v === 'ok' ? ' selected' : '') + '>Cumple</option><option value="falta"' + (v === 'falta' ? ' selected' : '') + '>Falta</option></select></div>'; }).join('');
  }
  function formHTML() {
    const d = S.cur.desafio, f = S.f, m = d.modo, sid = f.estrategia, ex = d.examen;
    let h = '';
    if (m === 'reconoce') {
      h += '<h3>¿Qué estrategias podrían aplicar?</h3><div class="mu">Pueden aplicar varias; cada una se juzga con sus propios requisitos.</div><label class="ck"><input type="checkbox" id="f-nin"' + (f.ninguna ? ' checked' : '') + '> <span>Ninguna estrategia aplica</span></label>';
      if (!f.ninguna) h += S.defs.estrategias.map(e => '<div class="crit"><span>' + esc(e.nombre) + '</span><select data-hip="' + e.id + '"><option value="">—</option><option value="CONFIRMADA"' + (f.hip[e.id] === 'CONFIRMADA' ? ' selected' : '') + '>Confirmada</option><option value="EN_FORMACION"' + (f.hip[e.id] === 'EN_FORMACION' ? ' selected' : '') + '>En formación</option></select></div>').join('');
      h += '<label>Temporalidad donde se decide<br><select id="f-tf"><option value="">Elegí…</option>' + [['hora', 'Hora (Cardona)'], ['diario', 'Diario'], ['m30', '30 minutos']].map(o => '<option value="' + o[0] + '"' + (f.tf_decision === o[0] ? ' selected' : '') + '>' + o[1] + '</option>').join('') + '</select></label>';
      const foco = Object.keys(f.hip).filter(k => f.hip[k])[0]; if (foco && !f.ninguna) h += '<h3 style="margin-top:8px">Requisitos de «' + esc(S.byId[foco].nombre) + '»</h3>' + critRows(foco);
    } else {
      h += '<h3>Tu análisis</h3>';
      if (d.estrategia) h += '<div class="mu">Estrategia a evaluar: <b>' + esc((S.byId[d.estrategia] || {}).nombre || d.estrategia) + '</b></div>';
      else h += '<label>Estrategia<br><select id="f-est"><option value="">Elegí…</option>' + S.defs.estrategias.map(e => '<option value="' + e.id + '"' + (sid === e.id ? ' selected' : '') + '>' + esc(e.nombre) + '</option>').join('') + '<option value="NINGUNA"' + (sid === 'NINGUNA' ? ' selected' : '') + '>Ninguna aplica</option></select></label>';
      if (sid && sid !== 'NINGUNA') {
        h += '<label>Temporalidad donde se decide<br><select id="f-tf"><option value="">Elegí…</option>' + [['hora', 'Hora (Cardona: 9:30–10:00, luego horarias)'], ['diario', 'Diario'], ['m30', '30 minutos']].map(o => '<option value="' + o[0] + '"' + (f.tf_decision === o[0] ? ' selected' : '') + '>' + o[1] + '</option>').join('') + '</select></label>';
        if (m !== 'faltante' || true) h += '<div style="margin-top:6px"><b>Clasificación</b> ' + ['CONFIRMADA', 'EN_FORMACION', 'NO_APLICA'].map(c => '<label class="ck"><input type="radio" name="f-cl" value="' + c + '"' + (f.clasificacion === c ? ' checked' : '') + '> <span>' + CLS[c] + (c === 'CONFIRMADA' ? ' (la vela de confirmación ya cerró)' : c === 'EN_FORMACION' ? ' (falta una condición)' : ' (no cumple / se descarta)') + '</span></label>').join('') + '</div>';
        h += '<div style="margin-top:6px"><b>Requisitos</b> <span class="mu">marcá cuáles cumple y cuáles faltan</span></div>' + critRows(sid);
        if (f.clasificacion === 'EN_FORMACION' || m === 'faltante') h += '<label>Condición que falta o descarta<br><select id="f-falta"><option value="">Elegí…</option>' + (S.byId[sid] ? S.byId[sid].criterios.map(c => '<option value="' + c.id + '"' + (f.condicion_faltante === c.id ? ' selected' : '') + '>' + c.n + '. ' + esc(c.texto.slice(0, 70)) + '</option>').join('') : '') + '</select></label>' + (m === 'faltante' ? '<div class="mu">Usá «★ Marcar vela» para señalar en el gráfico dónde se ve la falta.</div>' : '');
        if (f.clasificacion === 'CONFIRMADA' && m !== 'encontra') h += '<label class="ck"><input type="checkbox" id="f-vc"' + (f.vela_conf ? ' checked' : '') + '> <span>La vela de confirmación es la última visible (cerró)</span></label>';
      }
      if (m === 'encontra') h += '<div class="msg">Tramo de sesiones: marcá con «★ Marcar vela» la vela de confirmación o descartá si no hay ninguna.</div><button id="f-desc">No hay ocurrencia confirmada en este tramo</button>';
    }
    h += '<label style="display:block;margin-top:8px">Explicación breve (por qué, qué viste, qué descartaste)<br><textarea id="f-ex" maxlength="1200">' + esc(f.explicacion) + '</textarea></label>' +
      '<label style="display:block;margin-top:6px" class="mu">Captura anotada opcional (UCharts/TradingView). Límite: una imagen no se evalúa de forma estructurada → queda pendiente de revisión.<br><input type="file" id="f-cap" accept="image/*"></label>' +
      '<div class="row" style="margin-top:8px">' + (!ex ? '<button id="f-pista">💡 Pista</button>' : '') + (!ex && (m === 'vela' || m === 'sesion') ? '<button id="f-adv">▶ Avanzar una vela</button>' : '') + '<button class="pri" id="f-go">Entregar</button></div><div id="f-hints"></div><div id="f-msg"></div>';
    return h;
  }
  function vDesafio(b) {
    const c = S.cur, d = c.desafio, sn = c.snapshot;
    if (c.entregado && !S.reint && !S.res) { b.innerHTML = '<div class="card"><div class="msg wa">Este desafío ya fue entregado. Podés verlo en el Historial, reintentarlo como <b>práctica asistida</b> o empezar uno nuevo.</div><div class="row"><button id="x-re">Reintentar (asistida)</button><button class="pri" id="x-new">Nuevo desafío</button></div></div>'; $('#x-re').onclick = () => { S.reint = true; S.t0 = Date.now(); vDesafio(b); }; $('#x-new').onclick = nuevo; return; }
    const f = sn.fuente || {}, last = (sn.hora[sn.hora.length - 1] || {}).t, edad = last ? Math.round((Date.now() - Date.parse(last)) / 86400000) : null;
    b.innerHTML = '<div class="card"><div class="row" style="justify-content:space-between"><div><b>' + esc(MODOS[d.modo] || d.modo) + '</b> · ' + esc(d.ruta === 'exploracion' ? 'Exploración libre' : 'Desafío evaluable') + ' · <b>' + esc(d.ticker) + '</b> ' +
      (d.examen ? '<span class="tag wa">Examen</span>' : '<span class="tag ok">Guiado</span>') + ' <span class="tag">nivel ref.: ' + esc(d.nivel_validacion) + '</span></div><button id="x-new">✕ Salir</button></div>' +
      '<div class="mu" id="x-info">Corte: <b id="x-corte">' + esc(fmtT(S.corte)) + '</b> (hora de Nueva York) · cierra ' + esc(fmtT(sn.corte_cierra)) + ' · Fuente: ' + esc(f.proveedor) + ' · zona ' + esc(f.zona) + ' · intervalo ' + esc(f.intervalo) + ' · última vela ' + esc(fmtT(f.ultima_vela)) +
      (edad != null ? ' · antigüedad de los datos: ' + edad + ' d (caso histórico, no es tiempo real)' : '') + ' · semilla ' + d.seed + ' · evidencia #' + esc(d.evidencia_hash) + '</div>' +
      (f.dias_incompletos_en_ventana ? '<div class="msg wa">⚠ ' + f.dias_incompletos_en_ventana + ' día(s) con velas incompletas en la ventana: el caso puede quedar pendiente.</div>' : '') + '<div id="x-ses"></div></div>' +
      '<div class="grid"><div><div class="tb" id="x-tf"></div><div class="tb" id="x-tools"></div><div id="x-chart"></div><div class="mu" id="x-hover">Pasá el mouse por el gráfico · rueda: zoom · «Mover»: arrastrar. Las líneas se guardan con tiempo y precio: sobreviven al zoom, al cambio de tamaño y de temporalidad.</div></div>' +
      '<div class="card" id="x-form">' + formHTML() + '</div></div>';
    $('#x-new').onclick = () => { autosave(true); nuevo(); };
    const ch = S.chart = new AulaChart($('#x-chart'), { onChange: () => autosave(), onTF: tf => { S.tfs.add(tf); autosave(); drawTF(); }, onHover: (p, cd) => { $('#x-hover').textContent = (cd ? fmtT(cd.t) + ' · O ' + cd.o + ' H ' + cd.h + ' L ' + cd.l + ' C ' + cd.c + ' · ' : '') + 'precio ' + p.p.toFixed(2); } });
    ch.setData(chartData(sn), null); if (S.restore) ch.load(S.restore); S.restore = null;
    const tb = $('#x-tools'); tb.innerHTML = TOOLS.map(t => '<button data-tool="' + t[0] + '" class="' + (t[0] === ch.tool ? 'on' : '') + '">' + t[1] + '</button>').join('') +
      '<button id="t-un">↶ Deshacer</button><button id="t-re">↷ Rehacer</button><button id="t-cl">Limpiar</button><button id="t-zi">＋</button><button id="t-zo">－</button>' +
      Object.keys(AulaChart.COL).map(k => '<button data-ma="' + k + '" class="ma-' + k + ' on">' + k.toUpperCase().replace('PM', 'PM') + '</button>').join('');
    tb.querySelectorAll('[data-tool]').forEach(x => x.onclick = () => { ch.setTool(x.dataset.tool); tb.querySelectorAll('[data-tool]').forEach(y => y.classList.toggle('on', y === x)); });
    tb.querySelectorAll('[data-ma]').forEach(x => x.onclick = () => { ch.toggleMA(x.dataset.ma); x.classList.toggle('on'); });
    $('#t-un').onclick = () => ch.undo(); $('#t-re').onclick = () => ch.redo(); $('#t-cl').onclick = () => ch.clear(); $('#t-zi').onclick = () => ch.zoom(.8); $('#t-zo').onclick = () => ch.zoom(1.25);
    drawTF(); wireForm(b);
    if (d.modo === 'sesion' || (d.categoria === 'sesion_actual')) A('sesion?ticker=' + d.ticker).then(r => { if (!r.error) $('#x-ses').innerHTML = '<div class="msg">' + esc(typeof r === 'object' ? Object.keys(r).map(k => k + ': ' + (typeof r[k] === 'object' ? JSON.stringify(r[k]) : r[k])).join(' · ') : r) + '</div>'; });
    if (S.res) pintarResultado();
  }
  function drawTF() {
    const ch = S.chart; if (!ch) return; const el = $('#x-tf'); if (!el) return;
    el.innerHTML = '<span class="mu">Temporalidad:</span> ' + [['hora', 'Hora (Cardona)'], ['diario', 'Diario'], ['m30', '30 min']].map(t => '<button data-tf="' + t[0] + '" class="' + (ch.tf === t[0] ? 'on' : '') + '">' + t[1] + '</button>').join('');
    el.querySelectorAll('[data-tf]').forEach(x => x.onclick = () => ch.setTF(x.dataset.tf));
  }
  function nuevo() { S.cur = null; S.reint = false; S.res = null; S.chart = null; shell(); show(); }
  function wireForm(b) {
    const fm = $('#x-form'), f = S.f; const redo = () => { fm.innerHTML = formHTML(); wireForm(b); autosave(); };
    const on = (id, ev, fn) => { const e = $(id, fm); if (e) e[ev] = fn; };
    on('#f-est', 'onchange', e => { f.estrategia = e.target.value; f.crit = {}; redo(); });
    on('#f-tf', 'onchange', e => { f.tf_decision = e.target.value; autosave(); });
    fm.querySelectorAll('[name="f-cl"]').forEach(r => r.onchange = () => { f.clasificacion = r.value; redo(); });
    fm.querySelectorAll('[data-crit]').forEach(s => s.onchange = () => { f.crit[s.dataset.crit] = s.value; autosave(); });
    fm.querySelectorAll('[data-hip]').forEach(s => s.onchange = () => { f.hip[s.dataset.hip] = s.value; redo(); });
    on('#f-nin', 'onchange', e => { f.ninguna = e.target.checked; redo(); });
    on('#f-falta', 'onchange', e => { f.condicion_faltante = e.target.value; autosave(); });
    on('#f-vc', 'onchange', e => { f.vela_conf = e.target.checked; autosave(); });
    on('#f-ex', 'oninput', e => { f.explicacion = e.target.value; autosave(); });
    on('#f-cap', 'onchange', e => { const fl = e.target.files[0]; if (!fl) return; if (fl.size > 4e6) { alert('La imagen supera 4 MB.'); return; } const r = new FileReader(); r.onload = () => { f.captura = r.result; }; r.readAsDataURL(fl); });
    on('#f-pista', 'onclick', pedirPista); on('#f-adv', 'onclick', avanzar); on('#f-go', 'onclick', () => entregar(false)); on('#f-desc', 'onclick', () => entregar(true));
  }
  async function pedirPista() {
    S.hints = Math.min(4, (S.hints || 0) + 1); const r = await A('pista?id=' + S.cur.desafio.id + '&nivel=' + S.hints + (S.f.estrategia ? '&sid=' + S.f.estrategia : ''));
    if (r.error) { $('#f-hints').innerHTML = '<div class="msg er">' + esc(r.error) + '</div>'; return; }
    S.ayudas.push({ tipo: 'pista', nivel: r.nivel, t: new Date().toISOString() }); $('#f-hints').innerHTML += '<div class="msg ok">💡 ' + esc(r.pista) + '</div>'; autosave();
  }
  async function avanzar() {
    S.adv = (S.adv || 0) + 1; const r = await A('avanzar?id=' + S.cur.desafio.id + '&paso=' + S.adv);
    if (r.error) { S.adv--; $('#f-msg').innerHTML = '<div class="msg wa">' + esc(r.error) + '</div>'; return; }
    S.corte = r.corte; S.chart.setData(chartData(r.snapshot), null); $('#x-corte').textContent = fmtT(S.corte); $('#f-msg').innerHTML = '<div class="msg">Se reveló la vela de ' + esc(fmtT(S.corte)) + '. Tu clasificación se evalúa con los datos hasta ese corte.</div>'; autosave();
  }
  function payload(descarte) {
    const d = S.cur.desafio, f = S.f, ch = S.chart, m = d.modo; const ids = v => Object.keys(f.crit).filter(k => f.crit[k] === v);
    const p = { tf_decision: f.tf_decision, tfs_vistas: [...S.tfs], explicacion: f.explicacion, ayudas: S.ayudas, anotaciones: ch.an, corte: S.corte };
    if (f.captura) p.captura = f.captura;
    if (m === 'reconoce') {
      if (f.ninguna) { p.estrategia = 'NINGUNA'; p.clasificacion = 'NO_APLICA'; p.descarte_motivo = f.explicacion; return p; }
      const hs = Object.keys(f.hip).filter(k => f.hip[k]); if (!hs.length) return { error: 'Marcá al menos una estrategia que podría aplicar, o «Ninguna estrategia aplica».' };
      if (!f.tf_decision) return { error: 'Elegí la temporalidad donde se decide.' };
      p.hipotesis = hs.map((k, i) => ({ sid: k, estado: f.hip[k], requisitos: i ? [] : ids('ok'), faltantes: i ? [] : ids('falta'), faltante: i ? null : f.condicion_faltante || null })); return p;
    }
    p.estrategia = d.estrategia || f.estrategia;
    if (descarte) { p.descarte = true; p.clasificacion = 'NO_APLICA'; p.estrategia = p.estrategia || ''; if (!p.estrategia) return { error: 'Elegí qué estrategia estás descartando.' }; p.descarte_motivo = f.explicacion || 'Sin ocurrencia confirmada en el tramo'; return p; }
    if (!p.estrategia) return { error: 'Elegí la estrategia (o «Ninguna aplica»).' };
    if (p.estrategia === 'NINGUNA') { p.clasificacion = 'NO_APLICA'; p.descarte_motivo = f.explicacion; return p; }
    if (!f.tf_decision) return { error: 'Elegí la temporalidad donde se decide la estrategia.' };
    if (!f.clasificacion) return { error: 'Elegí una clasificación: Confirmada, En formación o No aplica.' };
    p.clasificacion = f.clasificacion; p.requisitos = ids('ok'); p.faltantes = ids('falta'); p.condicion_faltante = f.condicion_faltante || null;
    if (m === 'encontra') { const mk = ch.markers[0]; if (!mk) return { error: 'Marcá con «★ Marcar vela» la vela de confirmación, o descartá el tramo.' }; if (mk.tf !== 'hora') return { error: 'Marcá la vela en la temporalidad horaria.' }; p.corte = mk.t; p.vela_confirmacion = mk.t; p.clasificacion = 'CONFIRMADA'; }
    else if (f.clasificacion === 'CONFIRMADA' && f.vela_conf) p.vela_confirmacion = S.corte;
    if (ch.markers[0]) p.marcador = ch.markers[0];
    return p;
  }
  async function entregar(descarte) {
    const msg = $('#f-msg'); const p = payload(descarte); if (p.error) { msg.innerHTML = '<div class="msg wa">' + esc(p.error) + '</div>'; return; }
    const btn = $('#f-go'); btn.disabled = true; msg.innerHTML = '<div class="msg">Corrigiendo con la evidencia y la definición versionada…</div>';
    const r = await P('entregar', { desafio: S.cur.desafio.id, inicio: new Date(S.t0).toISOString(), duracion_s: Math.round((Date.now() - S.t0) / 1000), payload: p });
    btn.disabled = false; if (r.error) { msg.innerHTML = err(r); const rb = msg.querySelector('[data-act=retry]'); if (rb) rb.onclick = () => entregar(descarte); return; }
    S.res = r; S.cur.entregado = true; LS.set('aula_abierto_' + S.alumno, ''); S.reint = false; try { localStorage.removeItem('aula_borr_' + S.cur.desafio.id); } catch (e) { }
    S.chart.readonly = true; pintarResultado(); metaBar();
  }
  const obsHTML = o => '<li>' + (typeof o === 'string' ? esc(o) : (o.bien === true ? '✔ ' : o.bien === false ? '✘ ' : '') + esc(o.txt || o.obs || JSON.stringify(o)) + (o.pts != null && o.obs ? ' <span class="mu">(' + o.pts + ' pts)</span>' : '')) + '</li>';
  function pintarResultado() {
    const r = S.res, ev = r.evaluacion, ref = ev.referencia || {}, rv = r.revelado || {}; let box = $('#x-res');
    if (!box) { box = document.createElement('div'); box.id = 'x-res'; box.className = 'card'; $('#av-body').appendChild(box); }
    const NAM = { contexto: 'Contexto y temporalidad', requisitos: 'Requisitos', trazado: 'Trazado y anclajes', clasificacion: 'Clasificación y confirmación / condición faltante', explicacion: 'Explicación' };
    const st = ev.estado_validacion; const post = rv.posterior;
    box.innerHTML = '<div class="row" style="justify-content:space-between"><div><div class="score">' + ev.total + ' <span class="mu">/ 100</span></div><div>' + clsTag(ref.clase) + ' <span class="tag ' + (st === 'automatica' ? 'ok' : 'wa') + '">' + (st === 'automatica' ? 'corrección automática' : st === 'revisada' ? 'revisada' : 'revisión pendiente') + '</span> <span class="tag">intento ' + r.numero + ' · ' + (r.tipo === 'asistida' ? 'práctica asistida' : 'independiente') + '</span> <span class="tag">referencia: ' + esc(ref.nivel) + '</span> <span class="tag">rúbrica ' + esc(ev.rubrica) + ' · defs ' + esc(ev.def_version) + '</span></div></div>' +
      '<div class="tb"><button data-vw="tuyo" class="on">Tu trazado</button><button data-vw="ref">Referencia</button><button data-vw="ambos">Superpuesto</button><button data-vw="lamina">Lámina de Cardona</button></div></div>' +
      (ev.pendiente_pts ? '<div class="msg wa">⏳ ' + ev.pendiente_pts + ' puntos quedan <b>pendientes de revisión</b> (referencia sin validar o evidencia insuficiente). No se cuentan como error tuyo.</div>' : '') +
      (ref.discrepa_atlas ? '<div class="msg er">Discrepancia: Atlas dice «' + esc(ref.atlas_clase) + '» pero la referencia revisada dice «' + esc(ref.clase) + '». Se usa la revisada.</div>' : '') +
      (ev.anticipacion ? '<div class="msg wa">Anticipaste la confirmación: la vela de confirmación todavía no había cerrado en el corte de respuesta.</div>' : '') +
      '<table><tr><th>Criterio</th><th>Puntos</th><th>Qué se evaluó</th></tr>' + Object.keys(ev.desglose).map(k => { const v = ev.desglose[k]; return '<tr><td>' + esc(NAM[k] || k) + '</td><td><b>' + v.pts + '</b> / ' + v.max + '</td><td><ul>' + (v.obs || []).map(obsHTML).join('') + '</ul></td></tr>'; }).join('') + '</table>' +
      (ref.pasos && ref.pasos.length ? '<h3 style="margin-top:10px">Criterios de la referencia en el corte</h3><ul>' + ref.pasos.map((x, i) => '<li>' + (x.ok === true ? '✔' : x.ok === false ? '✘' : '?') + ' ' + (i + 1) + '. ' + esc(x.n) + (x.d ? ' — ' + esc(x.d) : '') + '</li>').join('') + '</ul>' : '') +
      (ref.todas ? '<div class="mu">Todas las estrategias en este corte: ' + Object.keys(ref.todas).filter(k => ref.todas[k].etapa !== 'SIN_CONTEXTO').map(k => esc((S.byId[k] || {}).nombre || k) + ' [' + esc(ref.todas[k].clase) + ']').join(' · ') + '</div>' : '') +
      '<div class="mu">Los puntos dependen solo de lo que se sabía en el corte (' + esc(fmtT(ref.corte)) + '); la evolución posterior no cambia la nota. Evidencia #' + esc(r.evidencia_hash) + '. Límites: la explicación se puntúa con una heurística de texto; las capturas no se evalúan estructuralmente.</div>' +
      '<div class="row" style="margin-top:8px"><button id="r-rev">Pedir revisión de la corrección</button><button id="r-aud">Auditar a Atlas</button><button id="r-post">Ver qué pasó después</button><button id="r-re">Reintentar (práctica asistida)</button><button class="pri" id="r-new">Nuevo desafío</button></div><div id="r-out"></div>';
    box.querySelectorAll('[data-vw]').forEach(b => b.onclick = () => vista(b.dataset.vw, box, rv, ref));
    $('#r-new', box).onclick = nuevo; $('#r-re', box).onclick = () => { S.reint = true; S.res = null; S.t0 = Date.now(); S.chart.readonly = false; S.f.explicacion = ''; box.remove(); vDesafio($('#av-body')); };
    $('#r-rev', box).onclick = () => { $('#r-out').innerHTML = '<label>Motivo<br><input id="rv-m" size="50" maxlength="300"></label> <button id="rv-go">Enviar</button>'; $('#rv-go').onclick = async () => { const x = await P('revision', { intento: r.intento_id, motivo: $('#rv-m').value }); $('#r-out').innerHTML = x.error ? err(x) : '<div class="msg ok">Revisión solicitada (#' + x.id + '). La nota automática se conserva y la rectificación quedará como nueva versión.</div>'; }; };
    $('#r-post', box).onclick = async () => { const x = await P('posterior', { desafio: S.cur.desafio.id }); $('#r-out').innerHTML = x.error ? err(x) : '<div class="msg">Velas posteriores al corte (no cambian tu nota): ' + esc(JSON.stringify(x.posterior).slice(0, 700)) + '<br><span class="mu">' + esc(x.nota) + '</span></div>'; };
    $('#r-aud', box).onclick = () => auditoria(r, ref);
    if (Array.isArray(post) && post[0] && post[0].c != null) { const dd = chartData(S.cur.snapshot); const hs = dd.hora.slice(); post.forEach(c => { if (!hs.some(x => x.t === c.t)) hs.push(c); }); dd.hora = hs; S.chart.setData(dd, ref.corte); S.chart.n = Math.max(S.chart.n, 80); S.chart.draw(); }
    else S.chart.cut = ref.corte;
    box.scrollIntoView({ behavior: 'smooth' }); if (S.auditar) auditoria(r, ref);
  }
  function vista(v, box, rv, ref) {
    const ch = S.chart, host = $('#x-chart'); box.querySelectorAll('[data-vw]').forEach(b => b.classList.toggle('on', b.dataset.vw === v));
    $('#x-lam') && $('#x-lam').remove(); host.style.display = '';
    ch.hideAn = (v === 'ref'); ch.overlay = (v === 'ref' || v === 'ambos') ? (ref.draw || []) : [];
    if (v === 'lamina') { host.style.display = 'none'; const im = document.createElement('div'); im.id = 'x-lam'; im.innerHTML = rv.lamina ? '<img class="lam" src="' + esc(rv.lamina) + '" alt="Lámina original de Cardona">' + (rv.definicion ? '<div class="mu">' + esc(rv.definicion.nombre) + ' · ' + esc(rv.definicion.num_lamina) + (rv.definicion.contradicciones && rv.definicion.contradicciones.length ? ' · contradicciones: ' + esc(JSON.stringify(rv.definicion.contradicciones)) : '') + '</div>' : '') : '<div class="msg wa">Sin lámina asociada para este caso.</div>'; host.parentNode.insertBefore(im, host.nextSibling); }
    ch.draw();
  }
  async function auditoria(r, ref) {
    const out = $('#r-out'); const pasos = ref.pasos || [];
    out.innerHTML = '<h3>Auditá a Atlas: ¿coincidís con cada paso?</h3>' + pasos.map((x, i) => '<div class="crit"><span>' + (i + 1) + '. ' + esc(x.n) + ' — Atlas: <b>' + (x.ok === true ? 'cumple' : x.ok === false ? 'no cumple' : 'sin dato') + '</b></span><select data-v="' + (i + 1) + '"><option value="">—</option><option value="coincido">Coincido</option><option value="discrepo">Discrepo</option></select></div>').join('') + '<button id="au-go" class="pri">Verificar contra el recálculo independiente</button><div id="au-res"></div>';
    $('#au-go').onclick = async () => { const v = {}; out.querySelectorAll('[data-v]').forEach(s => { if (s.value) v[s.dataset.v] = s.value; }); const x = await P('auditoria', { intento: r.intento_id, veredictos: v });
      $('#au-res').innerHTML = x.error ? err(x) : '<div class="msg">Aciertos ' + x.aciertos + ' de ' + x.verificables + ' verificables · ' + x.pendientes + ' sin verificación independiente (pendientes). <span class="mu">' + esc(x.nivel) + '</span></div><ul>' + x.resultados.map(z => '<li>' + (z.estado === 'ok' ? '✔' : z.estado === 'error' ? '✘' : '⏳') + ' ' + z.n + '. ' + esc(z.paso) + ' — ' + esc(z.obs) + '</li>').join('') + '</ul>'; };
  }

  // ------------------------------------------------------------------ Otras vistas
  const pct = (a, n) => (n ? Math.round(100 * a / n) + '% <span class="mu">(n=' + n + ')</span>' : '<span class="mu">sin datos (n=0)</span>');
  function kv(o) { if (o == null) return ''; if (typeof o !== 'object') return esc(o); if (Array.isArray(o)) return o.length ? '<table>' + (typeof o[0] === 'object' ? '<tr>' + Object.keys(o[0]).map(k => '<th>' + esc(k) + '</th>').join('') + '</tr>' + o.slice(0, 60).map(r => '<tr>' + Object.keys(o[0]).map(k => '<td>' + (typeof r[k] === 'object' ? esc(JSON.stringify(r[k])) : esc(r[k])) + '</td>').join('') + '</tr>').join('') : o.slice(0, 60).map(x => '<tr><td>' + esc(x) + '</td></tr>').join('')) + '</table>' : '<span class="mu">vacío</span>';
    return '<table>' + Object.keys(o).map(k => '<tr><th>' + esc(k) + '</th><td>' + (typeof o[k] === 'object' ? kv(o[k]) : esc(o[k])) + '</td></tr>').join('') + '</table>'; }
  async function vProgreso(b) {
    b.innerHTML = '<div class="mu">Cargando…</div>'; await ensureDefs(); const r = await A('progreso'), est = await api('/api/aula/estado'); if (r.error) { b.innerHTML = err(r); return; }
    const um = est.umbrales || {};
    b.innerHTML = '<div class="card"><h3>Dominio por estrategia</h3><div class="mu">Cada porcentaje muestra la cantidad de casos (n) en que se basa. El dominio se declara solo con evidencia repetida en casos nuevos y variados; los umbrales son <b>criterios pedagógicos iniciales</b>, editables y con historial.</div>' + (r.intentos ? '<table><tr><th>Estrategia</th><th>Estado</th><th>Intentos (n)</th><th>Nota media sin / con ayuda</th><th>Acierto de clasificación</th><th>Activos · días</th><th>Requisitos de dominio (actual / exigido)</th></tr>' + Object.keys(r.estrategias).map(k => { const x = r.estrategias[k], dm = x.dominio || {}; const ac = x.acierto ? Object.keys(x.acierto).map(c => esc(c) + ' ' + pct(x.acierto[c].aciertos, x.acierto[c].n)).join('<br>') : ''; return '<tr><td>' + esc((S.byId[k] || {}).nombre || k) + '</td><td><span class="tag ' + (x.estado === 'dominada' ? 'ok' : x.estado === 'en_progreso' ? 'wa' : '') + '">' + esc(x.estado) + '</span></td><td>' + x.n + '</td><td>' + (x.n ? esc(x.media_sin_ayuda) + ' <span class="mu">(n=' + x.n_sin_ayuda + ')</span> / ' + esc(x.media_con_ayuda) + ' <span class="mu">(n=' + x.n_con_ayuda + ')</span>' : '—') + '</td><td>' + (ac || '—') + '</td><td>' + (x.n ? x.activos + ' · ' + x.dias : '—') + '</td><td>' + (Object.keys(dm).length ? Object.keys(dm).map(q => esc(q) + ' ' + esc(JSON.stringify(dm[q]))).join('<br>') : '—') + '</td></tr>'; }).join('') + '</table>' : '<div class="msg">Todavía no hay intentos. Empezá en «Practicar».</div>') + '</div>' +
      '<div class="g2"><div class="card"><h3>Tiempo y metas</h3>' + kv(r.tiempo) + '</div><div class="card"><h3>Intentos</h3>' + kv(r.intentos) + '</div><div class="card"><h3>Errores recurrentes por requisito</h3>' + kv(r.errores) + '</div><div class="card"><h3>Con y sin ayuda</h3>' + kv(r.ayuda) + '</div>' +
      '<div class="card"><h3>Retención y repasos</h3>' + kv(r.retencion) + kv(r.repasos) + '</div><div class="card"><h3>Cobertura de activos y períodos</h3>' + kv(r.cobertura) + kv(r.activos_nuevos) + '</div><div class="card"><h3>Revisiones pendientes</h3>' + kv(r.pendientes_revision) + '</div><div class="card"><h3>Umbrales de dominio (iniciales)</h3>' + kv(um) + '</div></div>';
  }
  async function vCatalogo(b) {
    b.innerHTML = '<div class="mu">Cargando…</div>'; const d = await ensureDefs(); if (d.error) { b.innerHTML = err(d); return; }
    const cov = d.cobertura || {}; const sin = d.laminas_sin_detector || [];
    b.innerHTML = '<div class="card"><h3>Cobertura real de casos evaluables <span class="tag">definiciones ' + esc(d.version) + '</span></h3><div class="mu">Casos reales hallados en los datos descargados; si una categoría tiene 0, esa estrategia no es evaluable de forma completa y se informa qué falta.</div><table><tr><th>Estrategia</th><th>Confirmado</th><th>En formación</th><th>Contraejemplo</th><th>Req. faltante</th><th>Ambigua</th><th>Estado</th></tr>' +
      d.estrategias.map(e => { const c = cov[e.id] || {}; const f = k => c[k] ? c[k].casos + ' <span class="mu">(' + c[k].activos + ' act., ' + c[k].dias + ' d)</span>' : '0'; return '<tr><td>' + esc(e.nombre) + '</td><td>' + f('confirmado') + '</td><td>' + f('formacion') + '</td><td>' + f('contraejemplo') + '</td><td>' + f('faltante') + '</td><td>' + f('ambigua') + '</td><td>' + (c.evaluable ? '<span class="tag ok">evaluable</span>' : '<span class="tag wa">limitada</span> ' + esc((c.faltan || []).join('; '))) + '</td></tr>'; }).join('') + '</table>' +
      (sin.length ? '<div class="msg wa">Láminas sin detector en Atlas (no evaluables automáticamente): ' + esc(JSON.stringify(sin)) + '</div>' : '') + '</div>' +
      '<div class="card"><h3>Las 12 estrategias y sus criterios versionados</h3>' + d.estrategias.map(e => '<details><summary><b>' + esc(e.nombre) + '</b> · ' + esc(e.num_lamina) + ' · ' + esc(e.dir) + ' · se decide en «' + esc(e.tf_decision) + '» · ventana ' + esc(e.ventana) + '</summary><div class="g2"><div><ol>' + e.criterios.map(c => '<li>' + esc(c.texto) + ' <span class="tag ' + (c.origen === 'lamina' ? 'ok' : 'wa') + '">' + esc(c.origen) + '</span>' + (c.estado && c.estado !== 'alineado' ? ' <span class="tag er">' + esc(c.estado) + '</span>' : '') + (c.nota ? '<div class="mu">' + esc(c.nota) + '</div>' : '') + '</li>').join('') + '</ol>' +
        (e.contradicciones && e.contradicciones.length ? '<div class="msg wa"><b>Contradicciones (criterio «pendiente de revisión»)</b><ul>' + e.contradicciones.map(x => '<li>' + esc(typeof x === 'string' ? x : JSON.stringify(x)) + '</li>').join('') + '</ul></div>' : '') + '</div><div><img class="lam" loading="lazy" src="/assets/' + esc(e.lamina) + '" alt="Lámina ' + esc(e.nombre) + '"></div></div></details>').join('') + '</div>';
  }
  async function vHistorial(b) {
    b.innerHTML = '<div class="mu">Cargando…</div>'; const r = await A('intentos'); if (r.error) { b.innerHTML = err(r); return; }
    const L = Array.isArray(r) ? r : (r.intentos || []);
    b.innerHTML = '<div class="card"><h3>Historial de intentos</h3>' + (L.length ? '<table><tr><th>#</th><th>Fecha</th><th>Modo</th><th>Activo</th><th>Estrategia</th><th>Tipo</th><th>Nota</th><th>Estado</th><th></th></tr>' + L.map(x => '<tr><td>' + x.intento + '</td><td>' + esc(fmtT(x.fecha)) + '</td><td>' + esc(MODOS[x.modo] || x.modo) + '</td><td>' + esc(x.ticker) + '</td><td>' + esc((S.byId && S.byId[x.estrategia] || {}).nombre || x.estrategia) + '</td><td>' + esc(x.tipo) + ' (n.º ' + x.numero + ')</td><td><b>' + esc(x.total) + '</b> <span class="mu">v' + x.version + ' ' + esc(x.origen) + '</span></td><td>' + esc(x.estado) + '</td><td><button data-int="' + x.intento + '">Ver</button> <button data-rep="' + esc(x.desafio) + '">Reproducir</button></td></tr>').join('') + '</table>' : '<div class="msg">Sin intentos todavía.</div>') + '</div><div id="h-det"></div>';
    b.querySelectorAll('[data-int]').forEach(x => x.onclick = async () => { const d = await A('intento?id=' + x.dataset.int); $('#h-det').innerHTML = '<div class="card"><h3>Intento ' + esc(x.dataset.int) + '</h3>' + (d.error ? err(d) : kv(d)) + '</div>'; });
    b.querySelectorAll('[data-rep]').forEach(x => x.onclick = async () => { const d = await A('reproducir?id=' + x.dataset.rep); $('#h-det').innerHTML = '<div class="card"><h3>Reproducción por semilla</h3>' + (d.error ? err(d) : kv(d)) + '</div>'; });
  }
  async function vDatos(b) {
    b.innerHTML = '<div class="mu">Cargando…</div>'; const r = await api('/api/aula/estado'); if (r.error) { b.innerHTML = err(r); return; }
    const L = r.datos || [], ix = r.indice || {};
    b.innerHTML = '<div class="card"><h3>Estado de los datos</h3><div class="mu">Proveedor Yahoo Finance · zona America/New_York (con horario de verano) · velas Cardona = 9:30–10:00 y luego horarias, construidas desde 30 min (la grilla horaria nativa 9:30–10:30 no es compatible). Atlas ' + esc(r.atlas) + ' · definiciones ' + esc(r.def_version) + ' · índice: ' + esc(JSON.stringify(ix)) + '</div>' +
      '<div class="row" style="margin:8px 0"><button id="d-ref">Actualizar datos y reconstruir índice</button><span id="d-t" class="mu">' + esc((r.tarea || {}).estado) + ' ' + esc((r.tarea || {}).log) + '</span></div>' +
      '<table><tr>' + (L[0] ? Object.keys(L[0]).map(k => '<th>' + esc(k) + '</th>').join('') : '') + '</tr>' + L.map(x => '<tr>' + Object.keys(L[0]).map(k => '<td>' + esc(typeof x[k] === 'object' ? JSON.stringify(x[k]) : x[k]) + '</td>').join('') + '</tr>').join('') + '</table></div>' +
      '<div class="card"><h3>Limitaciones conocidas</h3><ul>' + (r.limitaciones || []).map(x => '<li>' + esc(x) + '</li>').join('') + '</ul></div>';
    $('#d-ref').onclick = async () => { const t = await P('refrescar'); $('#d-t').textContent = (t.estado || '') + ' ' + (t.log || ''); const iv = setInterval(async () => { const e = await api('/api/aula/estado'); if (!$('#d-t')) return clearInterval(iv); $('#d-t').textContent = e.tarea.estado + ' ' + e.tarea.log; if (e.tarea.estado !== 'corriendo') clearInterval(iv); }, 4000); };
  }
  async function vRevisiones(b) {
    b.innerHTML = '<div class="mu">Cargando…</div>'; const r = await api('/api/aula/revisiones'); const est = await api('/api/aula/estudio'); if (r.error) { b.innerHTML = err(r); return; }
    b.innerHTML = '<div class="card"><h3>Revisiones solicitadas</h3><div class="mu">La nota automática nunca se borra: una rectificación crea una versión «revisada» con autor y motivo.</div>' + kv(r) + '</div><div class="card"><h3>Integración con la hoja «📚 Estudio Cardona»</h3>' + kv(est) + '<div class="row" style="margin-top:8px"><button id="rv-exp">Copiar mis intentos como filas para el registro de Estudio Cardona</button><span id="rv-exp-m" class="mu"></span></div></div>';
    $('#rv-exp').onclick = async () => { const x = await A('estudio_export'); if (x.error) { $('#rv-exp-m').textContent = x.error; return; } const t = x.filas.map(f => f.join('\t')).join('\n'); try { await navigator.clipboard.writeText(t); $('#rv-exp-m').textContent = x.filas.length + ' filas copiadas: pegalas desde la primera fila libre del registro.'; } catch (e) { $('#rv-exp-m').textContent = 'No se pudo copiar al portapapeles.'; } };
  }

  // ------------------------------------------------------------------ Arranque (perezoso, al abrir el menu)
  function iniciar() { if (S.init) return; S.init = true; shell(); show(); metaBar(); }
  document.addEventListener('click', e => { const m = e.target.closest && e.target.closest('.menu-item[data-target="aula-virtual"]'); if (m) setTimeout(iniciar, 0); });
  const sec = document.getElementById('aula-virtual'); if (sec && sec.classList.contains('active')) iniciar();
  window.AulaVirtual = { iniciar, estado: S };
})();

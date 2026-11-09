/* Aula Virtual - grafico SVG propio con dibujo editable (mouse/touch/lapiz). Anotaciones en coordenadas tiempo/precio. */
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const COL = { pm20: '#f5c518', pm40: '#ff8c42', pm100: '#4aa3ff', pm200: '#c77dff' };
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const ms = t => (t.length <= 10 ? Date.parse(t + 'T16:00:00-05:00') : Date.parse(t));

  class AulaChart {
    constructor(host, o) {
      this.host = host; this.o = o || {}; this.data = {}; this.tf = 'hora'; this.an = []; this.undoS = []; this.redoS = [];
      this.tool = 'linea'; this.ma = { pm20: 1, pm40: 1, pm100: 1, pm200: 1 }; this.n = 70; this.off = 0; this.overlay = []; this.markers = [];
      this.cut = null; this.draft = null; this.readonly = false; this.pend = []; this.nextId = 1; this.hi = null;
      host.classList.add('ac-host');
      host.innerHTML = '<svg class="ac-svg" xmlns="' + NS + '" tabindex="0"></svg><input class="ac-text" hidden maxlength="80" placeholder="Texto + Enter">';
      this.svg = host.querySelector('svg'); this.inp = host.querySelector('input');
      this.svg.style.touchAction = 'none';
      this.svg.addEventListener('pointerdown', e => this.down(e));
      this.svg.addEventListener('pointermove', e => this.move(e));
      this.svg.addEventListener('pointerup', e => this.up(e));
      this.svg.addEventListener('pointercancel', () => { this.draft = null; this.pend = []; this.draw(); });
      this.svg.addEventListener('wheel', e => { e.preventDefault(); this.zoom(e.deltaY > 0 ? 1.15 : 0.87); }, { passive: false });
      this.inp.addEventListener('keydown', e => { if (e.key === 'Enter') this.commitText(); if (e.key === 'Escape') { this.inp.hidden = true; this.textAt = null; } });
      if (window.ResizeObserver) new ResizeObserver(() => this.draw()).observe(host);
    }
    setData(d, cut) { this.data = d; this.cut = cut || null; this.off = 0; this._ts = null; this.draw(); }
    setTF(tf) { if (this.data[tf] && this.data[tf].length) { this.tf = tf; this.off = 0; this._ts = null; this.draw(); if (this.o.onTF) this.o.onTF(tf); } }
    get C() { return this.data[this.tf] || []; }
    zoom(f) { this.n = Math.max(15, Math.min(this.C.length || 400, Math.round(this.n * f))); this.draw(); }
    toggleMA(k) { this.ma[k] = this.ma[k] ? 0 : 1; this.draw(); }
    setTool(t) { this.tool = t; this.pend = []; this.draft = null; this.draw(); }
    geom() {
      const r = this.svg.getBoundingClientRect(); const W = Math.max(300, r.width || 800), H = Math.max(240, r.height || 420);
      const m = { l: 8, r: 58, t: 8, b: 22 }; const C = this.C; const n = Math.min(this.n, C.length);
      const end = C.length - Math.round(this.off), start = Math.max(0, end - n);
      let lo = 1e18, hi = -1e18;
      for (let i = start; i < end; i++) { lo = Math.min(lo, C[i].l); hi = Math.max(hi, C[i].h); }
      if (!(hi > lo)) { lo = 0; hi = 1; } const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
      return { W, H, m, start, end, n: end - start, lo, hi, cw: (W - m.l - m.r) / Math.max(1, end - start) };
    }
    xi(i, g) { return g.m.l + (i - g.start + 0.5) * g.cw; }
    yp(p, g) { return g.m.t + (g.hi - p) / (g.hi - g.lo) * (g.H - g.m.t - g.m.b); }
    iy(y, g) { return g.hi - (y - g.m.t) / (g.H - g.m.t - g.m.b) * (g.hi - g.lo); }
    ix(x, g) { return g.start + (x - g.m.l) / g.cw - 0.5; }
    tsArr() { const C = this.C; if (!this._ts || this._tsFor !== C) { this._ts = C.map(c => ms(c.t)); this._tsFor = C; } return this._ts; }
    t2i(t) {
      const T = this.tsArr(), n = T.length; if (!n) return 0; const d0 = (T[Math.min(1, n - 1)] - T[0]) || 3.6e6, d1 = (T[n - 1] - T[Math.max(0, n - 2)]) || 3.6e6;
      if (t <= T[0]) return (t - T[0]) / d0; if (t >= T[n - 1]) return n - 1 + (t - T[n - 1]) / d1;
      let a = 0, b = n - 1; while (b - a > 1) { const m = (a + b) >> 1; if (T[m] <= t) a = m; else b = m; }
      return a + (t - T[a]) / (T[b] - T[a]);
    }
    i2t(i) {
      const T = this.tsArr(), n = T.length; if (!n) return 0; const d0 = (T[Math.min(1, n - 1)] - T[0]) || 3.6e6, d1 = (T[n - 1] - T[Math.max(0, n - 2)]) || 3.6e6;
      if (i <= 0) return T[0] + i * d0; if (i >= n - 1) return T[n - 1] + (i - (n - 1)) * d1;
      const a = Math.floor(i); return T[a] + (i - a) * (T[a + 1] - T[a]);
    }
    pt(e, g) { const r = this.svg.getBoundingClientRect(); const x = e.clientX - r.left, y = e.clientY - r.top; return { x, y, t: this.i2t(this.ix(x, g)), p: this.iy(y, g), i: this.ix(x, g) }; }
    snap() { this.undoS.push(JSON.stringify(this.an)); if (this.undoS.length > 100) this.undoS.shift(); this.redoS = []; }
    add(a) { this.snap(); a.id = 'a' + Date.now().toString(36) + (this.nextId++); a.tf = this.tf; this.an.push(a); this.changed(); }
    undo() { if (!this.undoS.length) return; this.redoS.push(JSON.stringify(this.an)); this.an = JSON.parse(this.undoS.pop()); this.changed(); }
    redo() { if (!this.redoS.length) return; this.undoS.push(JSON.stringify(this.an)); this.an = JSON.parse(this.redoS.pop()); this.changed(); }
    clear() { if (!this.an.length) return; this.snap(); this.an = []; this.changed(); }
    changed() { this.draw(); if (this.o.onChange) this.o.onChange(this.toJSON()); }
    toJSON() { return { anotaciones: this.an.map(a => Object.assign({}, a)), marcadores: this.markers.slice() }; }
    load(s) { this.an = ((s && s.anotaciones) || []).map(a => Object.assign({}, a)); this.markers = (s && s.marcadores) || []; this.draw(); }
    iso(t) { return new Date(t).toISOString(); }
    down(e) {
      const tl = this.tool; if (this.readonly && tl !== 'mover') return;
      const g = this.geom(); const p = this.pt(e, g); try { this.svg.setPointerCapture(e.pointerId); } catch (x) { }
      if (tl === 'mover') { this.pan = { x: e.clientX, off: this.off }; return; }
      if (tl === 'borrar') { const el = e.target.closest && e.target.closest('[data-id]'); if (el) { this.snap(); this.an = this.an.filter(a => a.id !== el.dataset.id); this.changed(); } return; }
      if (tl === 'marcar') { const i = Math.max(0, Math.min(this.C.length - 1, Math.round(p.i))); const c = this.C[i]; this.markers = [{ t: c.t, p: c.c, tf: this.tf }]; this.changed(); return; }
      if (tl === 'texto') { this.textAt = p; this.inp.style.left = Math.min(p.x, g.W - 170) + 'px'; this.inp.style.top = p.y + 'px'; this.inp.hidden = false; this.inp.value = ''; setTimeout(() => this.inp.focus(), 0); return; }
      if (tl === 'horizontal') { this.add({ tipo: 'horizontal', t1: this.iso(p.t), p1: p.p }); return; }
      if (tl === 'canal' && this.pend.length === 2) { const [a, b] = this.pend; this.pend = []; this.add({ tipo: 'canal', t1: a.t, p1: a.p, t2: b.t, p2: b.p, t3: this.iso(p.t), p3: p.p }); return; }
      this.draft = { tipo: tl === 'canal' ? 'linea' : tl, a: p, b: p };
    }
    move(e) {
      const g = this.geom();
      if (this.pan) { this.off = Math.max(0, Math.min(this.C.length - this.n, this.pan.off + (e.clientX - this.pan.x) / g.cw)); this.draw(); return; }
      const p = this.pt(e, g); this.hi = p;
      if (this.draft) { this.draft.b = p; this.draw(); } else if (this.pend.length) this.draw(); else if (this.o.onHover) this.o.onHover(p, this.nearest(p));
    }
    up(e) {
      if (this.pan) { this.pan = null; return; }
      if (!this.draft) return; const d = this.draft; this.draft = null; const g = this.geom(); const p = this.pt(e, g);
      if (Math.hypot(p.x - d.a.x, p.y - d.a.y) < 6) { this.draw(); return; }
      const a = { tipo: d.tipo, t1: this.iso(d.a.t), p1: d.a.p, t2: this.iso(p.t), p2: p.p };
      if (this.tool === 'canal') { this.pend = [{ t: a.t1, p: a.p1 }, { t: a.t2, p: a.p2 }]; this.draw(); return; }
      this.add(a);
    }
    nearest(p) { const i = Math.max(0, Math.min(this.C.length - 1, Math.round(p.i))); return this.C[i]; }
    commitText() { if (this.textAt && this.inp.value.trim()) this.add({ tipo: 'texto', t1: this.iso(this.textAt.t), p1: this.textAt.p, texto: this.inp.value.trim() }); this.inp.hidden = true; this.textAt = null; }
    // ---- dibujo
    shape(a, g, col, extra) {
      const X = t => this.xi(this.t2i(typeof t === 'number' ? t : ms(t)), g), Y = p => this.yp(p, g); const id = a.id ? ' data-id="' + a.id + '"' : '';
      const sw = 'stroke="' + col + '" stroke-width="2" fill="none"' + (extra || ''); const hit = (d) => a.id ? '<path d="' + d + '" stroke="transparent" stroke-width="14" fill="none" pointer-events="stroke"/>' : '';
      const R = g.W - g.m.r;
      if (a.tipo === 'horizontal') { const y = Y(a.p1); const d = 'M' + g.m.l + ' ' + y + 'L' + R + ' ' + y; return '<g' + id + '><path d="' + d + '" ' + sw + ' stroke-dasharray="6 3"/>' + hit(d) + '<text x="' + (R - 2) + '" y="' + (y - 3) + '" fill="' + col + '" font-size="10" text-anchor="end">' + a.p1.toFixed(2) + '</text></g>'; }
      if (a.tipo === 'texto') return '<g' + id + '><text x="' + X(a.t1) + '" y="' + Y(a.p1) + '" fill="' + col + '" font-size="13" font-weight="600">' + esc(a.texto || '') + '</text></g>';
      const x1 = X(a.t1), y1 = Y(a.p1), x2 = X(a.t2), y2 = Y(a.p2);
      if (a.tipo === 'circulo') { const r = Math.hypot(x2 - x1, y2 - y1); return '<g' + id + '><circle cx="' + x1 + '" cy="' + y1 + '" r="' + r + '" ' + sw + '/><circle cx="' + x1 + '" cy="' + y1 + '" r="' + r + '" stroke="transparent" stroke-width="12" fill="none" pointer-events="stroke"/></g>'; }
      const ext = (xa, ya, xb, yb) => { const dx = xb - xa; if (!dx) return [xa, ya, xb, yb]; const s = (yb - ya) / dx; return [xa, ya, R, ya + s * (R - xa)]; };
      let d = 'M' + x1 + ' ' + y1 + 'L' + x2 + ' ' + y2; let out = '';
      if (a.tipo === 'linea' || a.tipo === 'canal') { const e = ext(x1, y1, x2, y2); d = 'M' + e[0] + ' ' + e[1] + 'L' + e[2] + ' ' + e[3]; }
      if (a.tipo === 'flecha') { const ang = Math.atan2(y2 - y1, x2 - x1), L = 11; out = '<path d="M' + x2 + ' ' + y2 + 'L' + (x2 - L * Math.cos(ang - .45)) + ' ' + (y2 - L * Math.sin(ang - .45)) + 'M' + x2 + ' ' + y2 + 'L' + (x2 - L * Math.cos(ang + .45)) + ' ' + (y2 - L * Math.sin(ang + .45)) + '" ' + sw + '/>'; }
      let ch = '';
      if (a.tipo === 'canal' && a.t3) { const off = Y(a.p3) - (y1 + (y2 - y1) / ((x2 - x1) || 1) * (X(a.t3) - x1)); const e = ext(x1, y1 + off, x2, y2 + off); ch = '<path d="M' + e[0] + ' ' + e[1] + 'L' + e[2] + ' ' + e[3] + '" ' + sw + '/>'; }
      return '<g' + id + '><path d="' + d + '" ' + sw + '/>' + out + ch + hit(d) + '</g>';
    }
    draw() {
      const C = this.C; const g = this.geom(); const svg = this.svg; if (!C.length) { svg.innerHTML = '<text x="20" y="40" fill="#9aa">Sin velas para esta temporalidad</text>'; return; }
      svg.setAttribute('viewBox', '0 0 ' + g.W + ' ' + g.H); let s = '<defs><clipPath id="acclip"><rect x="' + g.m.l + '" y="' + g.m.t + '" width="' + (g.W - g.m.l - g.m.r) + '" height="' + (g.H - g.m.t - g.m.b) + '"/></clipPath></defs>';
      const steps = 6; for (let k = 0; k <= steps; k++) { const p = g.lo + (g.hi - g.lo) * k / steps, y = this.yp(p, g); s += '<line x1="' + g.m.l + '" x2="' + (g.W - g.m.r) + '" y1="' + y + '" y2="' + y + '" class="ac-grid"/><text x="' + (g.W - g.m.r + 4) + '" y="' + (y + 3) + '" class="ac-ax">' + p.toFixed(2) + '</text>'; }
      const every = Math.max(1, Math.round(70 / g.cw)); let lastDay = '';
      for (let i = g.start; i < g.end; i++) {
        const c = C[i], x = this.xi(i, g), up = c.c >= c.o, col = up ? '#26a69a' : '#ef5350'; const day = c.t.slice(0, 10);
        if (day !== lastDay && this.tf !== 'diario') { s += '<line x1="' + x + '" x2="' + x + '" y1="' + g.m.t + '" y2="' + (g.H - g.m.b) + '" class="ac-day"/>'; lastDay = day; }
        s += '<g clip-path="url(#acclip)"><line x1="' + x + '" x2="' + x + '" y1="' + this.yp(c.h, g) + '" y2="' + this.yp(c.l, g) + '" stroke="' + col + '"/><rect x="' + (x - g.cw * 0.35) + '" y="' + this.yp(Math.max(c.o, c.c), g) + '" width="' + (g.cw * 0.7) + '" height="' + Math.max(1, Math.abs(this.yp(c.o, g) - this.yp(c.c, g))) + '" fill="' + col + '"/></g>';
        if ((i - g.start) % every === 0) s += '<text x="' + x + '" y="' + (g.H - 7) + '" class="ac-ax" text-anchor="middle">' + (this.tf === 'diario' ? c.t.slice(5) : c.t.slice(5, 10) + ' ' + c.t.slice(11, 16)) + '</text>';
      }
      s += '<g clip-path="url(#acclip)">';
      Object.keys(COL).forEach(k => { if (!this.ma[k]) return; let d = '', st = false; for (let i = g.start; i < g.end; i++) { const v = C[i][k]; if (v == null) { st = false; continue; } d += (st ? 'L' : 'M') + this.xi(i, g) + ' ' + this.yp(v, g); st = true; } if (d) s += '<path d="' + d + '" stroke="' + COL[k] + '" stroke-width="1.6" fill="none"/>'; });
      if (this.cut) { const x = this.xi(this.t2i(ms(this.cut)), g); s += '<line x1="' + x + '" x2="' + x + '" y1="' + g.m.t + '" y2="' + (g.H - g.m.b) + '" class="ac-cut"/>'; }
      this.overlay.forEach(a => { s += this.shape(Object.assign({}, a, { id: null }), g, a.color || '#3ddc84', ' stroke-dasharray="7 4"'); });
      (this.hideAn ? [] : this.an).forEach(a => { s += this.shape(a, g, a.tf && a.tf !== this.tf ? '#7aa7ff' : '#ffd24a', a.tf && a.tf !== this.tf ? ' opacity="0.8"' : ''); });
      (this.o.extra || []).forEach(a => { s += this.shape(a, g, a.color || '#ff6b9d', ' stroke-dasharray="3 3"'); });
      if (this.draft) { const d = this.draft; s += this.shape({ tipo: d.tipo, t1: d.a.t, p1: d.a.p, t2: d.b.t, p2: d.b.p }, g, '#fff', ' opacity="0.7"'); }
      if (this.pend.length === 2 && this.hi) s += this.shape({ tipo: 'canal', t1: this.pend[0].t, p1: this.pend[0].p, t2: this.pend[1].t, p2: this.pend[1].p, t3: this.hi.t, p3: this.hi.p }, g, '#fff', ' opacity="0.7"');
      this.markers.forEach(m => { const x = this.xi(this.t2i(ms(m.t)), g), y = this.yp(m.p, g); s += '<circle cx="' + x + '" cy="' + y + '" r="9" fill="none" stroke="#ff4d8d" stroke-width="2.5"/><text x="' + x + '" y="' + (y - 13) + '" fill="#ff4d8d" font-size="11" text-anchor="middle">★</text>'; });
      s += '</g>';
      const last = C[g.end - 1]; if (last) s += '<text x="' + (g.W - g.m.r - 4) + '" y="' + (g.m.t + 12) + '" class="ac-ax" text-anchor="end">' + esc(this.tf) + ' · última vela ' + esc(last.t.replace('T', ' ').slice(0, 16)) + '</text>';
      svg.innerHTML = s;
    }
  }
  window.AulaChart = AulaChart; window.AulaChart.COL = COL;
})();

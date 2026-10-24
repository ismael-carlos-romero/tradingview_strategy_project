// Tests del Risk Engine de ucharts_sync_userscript.js (bloque RISK_ENGINE_BEGIN/END).
// Uso: node test_ucharts_risk_calculator.js
const fs = require('fs');
const path = require('path');
const src = fs.readFileSync(path.join(__dirname, 'ucharts_sync_userscript.js'), 'utf8');
const a = src.indexOf('// ==== RISK_ENGINE_BEGIN ====');
const b = src.indexOf('// ==== RISK_ENGINE_END ====');
if (a < 0 || b < 0) { console.error('No se encontró el bloque RISK_ENGINE'); process.exit(1); }
const engineSrc = src.slice(a, b);

let passed = 0, failed = 0;
function check(name, cond, extra) {
  if (cond) { passed++; console.log('  OK   ' + name); }
  else { failed++; console.log('  FAIL ' + name + (extra ? ' -> ' + extra : '')); }
}

// Un "navegador" nuevo (recarga de página) sobre el MISMO localStorage.
function makeStorage() {
  const m = new Map();
  return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k) };
}
function loadPage(storage, ctx) {
  const factory = new Function('localStorage', 'ctx', 'console',
    'function getDailyBucketPct(){return ctx.pct;} function extractAccountBalance(){return ctx.capital;}\n' +
    engineSrc + '\nreturn { riskEvaluate, validateOrderRisk, riskRecordPurchase, riskDailyBudget, riskGrossForPool, riskLoadOrders, riskLoadState, riskGetDay };');
  return factory(storage, ctx, { log() {}, warn() {} });
}
const mk = (o) => Object.assign({ ticker: 'SPY', type: 'CALL', strike: 500, expiryKey: '2026-10-09', source: 'MANUAL_CALL', multiplier: 100 }, o);
const noComm = (s) => s.setItem('ucharts_risk_commission_per_contract', '0');

console.log('TEST 1: capital 100k, 10%, prima $1, 100 contratos => permitido');
{ const st = makeStorage(); noComm(st); const p = loadPage(st, { capital: 100000, pct: 10 });
  const r = p.validateOrderRisk(mk({ qty: 100, amount: 10000 }));
  check('APPROVED', r.decision === 'APPROVED', r.decision + ' ' + r.message); check('costo 10000', Math.abs(r.totalCost - 10000) < 1e-6); check('max 100', r.maxContracts === 100); }

console.log('TEST 2: 101 contratos => rechazado');
{ const st = makeStorage(); noComm(st); const p = loadPage(st, { capital: 100000, pct: 10 });
  const r = p.validateOrderRisk(mk({ qty: 101, amount: 10100 }));
  check('REJECTED', r.decision === 'REJECTED' && r.reason === 'EXCEEDS_DAILY_LIMIT'); check('permitidos = 100', r.maxContracts === 100); check('exceso $100', Math.abs(r.excess - 100) < 1e-6); }

console.log('TEST 3: comprar $8,000, vender con ganancia, comprar otros $8,000 => sólo ~$2,000 disponibles');
{ const st = makeStorage(); noComm(st); const p = loadPage(st, { capital: 100000, pct: 10 });
  const r1 = p.validateOrderRisk(mk({ qty: 80, amount: 8000 })); check('1ra compra APPROVED', r1.decision === 'APPROVED');
  p.riskRecordPurchase(r1);
  // "vender con ganancia" = no hay ninguna API que devuelva presupuesto: el bruto sigue en 8000
  check('bruto = 8000 tras vender', p.riskGetDay(p.riskLoadState()).grossPurchases === 8000);
  const r2 = p.validateOrderRisk(mk({ qty: 80, amount: 8000 }));
  check('2da compra REJECTED', r2.decision === 'REJECTED'); check('restante ≈ 2000', Math.abs(r2.remaining - 2000) < 1e-6, String(r2.remaining)); check('max 20 contratos', r2.maxContracts === 20); }

console.log('TEST 4: recargar página => presupuesto usado permanece (mismo localStorage, contexto nuevo, capital ya no legible)');
{ const st = makeStorage(); noComm(st); const p1 = loadPage(st, { capital: 100000, pct: 10 });
  p1.riskRecordPurchase(p1.validateOrderRisk(mk({ qty: 50, amount: 5000 })));
  const p2 = loadPage(st, { capital: null, pct: 10 }); // tras recargar aún no se leyó la cuenta
  const day = p2.riskGetDay(p2.riskLoadState());
  check('gross persiste 5000', day.grossPurchases === 5000); check('capital snapshot persiste 100000', day.capitalBase === 100000);
  check('budget 10000', p2.riskDailyBudget() === 10000);
  const r = p2.validateOrderRisk(mk({ qty: 60, amount: 6000 })); check('60 más se rechaza (sólo quedan 5000)', r.decision === 'REJECTED'); }

console.log('TEST 4b: el capital NO crece intradía (snapshot congelado)');
{ const st = makeStorage(); noComm(st); const ctx = { capital: 100000, pct: 10 }; const p = loadPage(st, ctx);
  p.validateOrderRisk(mk({ qty: 1, amount: 100 })); ctx.capital = 150000;
  check('budget sigue 10000', p.riskDailyBudget() === 10000); }

console.log('TEST 5/6: cambiar contratos / prima recalcula (riskEvaluate pura)');
{ const base = { capitalBase: 100000, limitPct: 10, grossToday: 0, multiplier: 100, commissionPerContract: 0 };
  const e1 = p_ev({ ...base, premium: 10, qty: 5 }); const e2 = p_ev({ ...base, premium: 10, qty: 6 });
  check('costo cambia con contratos', e1.totalCost === 5000 && e2.totalCost === 6000);
  const e3 = p_ev({ ...base, premium: 10, qty: 1 }); const e4 = p_ev({ ...base, premium: 20, qty: 1 });
  check('máximo cambia con prima (10 -> 20)', e3.maxContracts === 10 && e4.maxContracts === 5); }
function p_ev(x) { return loadPage(makeStorage(), { capital: 1, pct: 10 }).riskEvaluate(x); }

console.log('TEST 12 / caso MRNA: capital 2,859,185.94, 10%, prima 10.92, 1000 contratos');
{ const st = makeStorage(); noComm(st); const p = loadPage(st, { capital: 2859185.94, pct: 10 });
  const r = p.validateOrderRisk(mk({ ticker: 'MRNA', type: 'PUT', strike: 197.5, qty: 1000, amount: 10.92 * 100 * 1000, source: 'MANUAL_PUT' }));
  check('BLOQUEADA', r.decision === 'REJECTED'); check('costo 1,092,000', Math.abs(r.totalCost - 1092000) < 1e-6);
  check('permitidos 261', r.maxContracts === 261, String(r.maxContracts)); check('presupuesto 285,918.59', Math.abs(r.budget - 285918.594) < 1e-3);
  check('log guarda REJECTED + origen', p.riskLoadOrders().slice(-1)[0].decision === 'REJECTED' && p.riskLoadOrders().slice(-1)[0].source === 'MANUAL_PUT');
  const ok = p.validateOrderRisk(mk({ ticker: 'MRNA', type: 'PUT', qty: 261, amount: 10.92 * 100 * 261 })); check('261 sí pasa', ok.decision === 'APPROVED'); }

console.log('Comisión: se suma al costo y reduce el máximo, y nunca redondea hacia arriba');
{ const e = p_ev({ capitalBase: 100000, limitPct: 10, grossToday: 0, premium: 1, qty: 100, multiplier: 100, commissionPerContract: 0.65 });
  check('costo 10065', Math.abs(e.totalCost - 10065) < 1e-6); check('100 con comisión se rechaza', e.decision === 'REJECTED'); check('max = floor(10000/100.65)=99', e.maxContracts === 99);
  const e2 = p_ev({ capitalBase: 100000, limitPct: 10, grossToday: 0, premium: 10.92, qty: 1, multiplier: 100, commissionPerContract: 0 });
  check('inversa $20,000 / 1092 = 18 (floor)', Math.floor(20000 / e2.costPerContract) === 18); }

console.log('Fail-closed: sin capital / sin monto');
{ const st = makeStorage(); const p = loadPage(st, { capital: null, pct: 10 });
  check('sin capital => REJECTED', p.validateOrderRisk(mk({ qty: 1, amount: 100 })).reason === 'NO_CAPITAL');
  const p2 = loadPage(makeStorage(), { capital: 100000, pct: 10 });
  check('sin monto legible => REJECTED', p2.validateOrderRisk(mk({ qty: 1, amount: null })).reason === 'NO_PREMIUM'); }

console.log('TP/SL: 10,000 con TP 15% y SL 10%');
{ const e = p_ev({ capitalBase: 1e6, limitPct: 10, grossToday: 0, premium: 1, qty: 100, multiplier: 100, commissionPerContract: 0, tpPct: 15, slPct: 10 });
  check('+1500 / -1000 / 11500 / 9000', e.plannedGainTP === 1500 && e.plannedLossSL === 1000 && e.valueAtTP === 11500 && e.valueAtSL === 9000);
  check('pérdida máx teórica = prima total', e.maxTheoreticalLoss === 10000); }

console.log('TESTS 7-11 (estático): TODAS las rutas de compra pasan por executeOrder -> validateOrderRisk antes de Confirmar');
{ const fn = src.slice(src.indexOf('async function executeOrder('), src.indexOf('// 🧮 CALCULADORA DE RIESGO'));
  const iVal = fn.indexOf('validateOrderRisk(riskOrder)'); const iConf = fn.indexOf('superClick(confirmBtn)');
  check('validateOrderRisk antes de superClick(confirmBtn)', iVal > 0 && iConf > iVal);
  check('rechazo retorna antes de confirmar', /decision === 'REJECTED'\)\s*\{[\s\S]*?return traderFail\('Risk Engine/.test(fn));
  check('sin resumen de orden => bloqueado (no compra directa)', !/directBtn/.test(fn) && /no se puede validar el capital/.test(fn));
  const calls = src.split('\n').filter(l => /await executeOrder\(/.test(l));
  const expected = { MANUAL_CALL: 1, MANUAL_PUT: 1, AUTO_TRADER: 1, ZONA_TECHO_PISO: 1, TESTER: 2, BANDERA_AUTOMATICA: 1, probeSource: 2 };
  let allTagged = calls.length === 9;
  for (const [k, n] of Object.entries(expected)) allTagged = allTagged && calls.filter(l => l.includes('source: ' + (/^[A-Z_]+$/.test(k) ? "'" + k + "'" : k))).length === n;
  check('9 llamadas a executeOrder, todas con source', allTagged, calls.length + ' llamadas');
  check('probe recibe BANDERINES_GENERALES', /banderinStartProbe\(ticker, 'BANDERINES_GENERALES'\)/.test(src));
  check('ninguna función resta de grossPurchases', !/grossPurchases\s*(-=|=\s*[^;]*-)/.test(src.slice(a, b))); }

console.log(`\n${passed} OK, ${failed} FAIL`);
process.exit(failed ? 1 : 0);

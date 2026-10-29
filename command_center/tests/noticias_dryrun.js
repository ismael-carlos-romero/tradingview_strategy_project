// DRY_RUN y pruebas de la logica de apps_script_noticias.gs en Node (sin Apps Script, sin red, sin Supabase).
// Fixture: IDs, tickers, estados, categorias, URLs y calendario del corte MELIORA_20261029_085305_AR leidos de la hoja de estudio
// el 29/10/2026 (solo lectura). Los textos largos de noticia estan abreviados; no afectan a la validacion.
// Uso: node tests/noticias_dryrun.js   -> escribe tests/dryrun_output.json (el reporte que se enviaria).
const fs = require('fs'), path = require('path'), assert = require('assert');
const { construirReporte_, ENCABEZADOS } = require(path.join(__dirname, '..', 'apps_script_noticias.gs'));

const ID = 'MELIORA_20261029_085305_AR', CORTE = '29/10/2026 08:53:05';
const U = {
  fed: 'https://www.federalreserve.gov/newsevents/pressreleases/monetary20261028a.htm',
  oil: 'https://www.reuters.com/business/energy/us-oil-prices-fall-investors-gauge-risks-mideast-supply-2026-10-29/',
  gold: 'https://www.reuters.com/world/india/gold-slips-markets-assess-fed-signals-await-us-inflation-data-2026-10-29/',
  amd: 'https://ir.amd.com/news-events/press-releases/detail/1300/amd-to-report-fiscal-third-quarter-2026-financial-results',
  msft: 'https://www.microsoft.com/en-us/Investor/earnings/FY-2027-Q1/press-release-webcast',
  axon: 'https://www.axon.com/newsroom/press-releases/axon-to-release-third-quarter-2026-earnings-on-november-5-2026',
  pub: 'https://www.publicnow.com/view/ED018F4AAE12FB3B1BD1E9649EA9BF381E69B00F',
  apple: 'https://www.apple.com/newsroom/2026/10/apple-unveils-groundbreaking-macbook-pro-with-proled-xdr-display/',
  amzn: 'https://www.aboutamazon.com/news/company-news/amazon-earnings-q3-2026-report',
  nvda: 'https://blogs.nvidia.com/blog/local-ai-rtx-spark-laptops-updates-models-agents-games/',
  coin: 'https://investor.coinbase.com/news/news-details/2026/Coinbase-Announces-Date-of-Third-Quarter-2026-Financial-Results/default.aspx',
  ebay: 'https://investors.ebayinc.com/investor-news/press-release-details/2026/eBay-Inc--Reports-Third-Quarter-2026-Results/default.aspx',
  uber: 'https://investor.uber.com/news-events/news/press-release-details/2026/Uber-Announces-Date-of-Third-Quarter-2026-Results-Conference-Call/default.aspx',
};
// [ticker, empresa, V=verificado/N=no, url, noticia abreviada]
const A = [['BLK','BlackRock','N'],['SPY','SPDR S&P 500 ETF','V','fed','Fed mantiene 3,75-4%, voto 10-2'],['QQQ','Invesco QQQ Trust','V','fed','Fed mantiene 3,75-4%'],
 ['META','Meta Platforms','N'],['MSCI','MSCI Inc.','N'],['AMD','Advanced Micro Devices','V','amd','Resultados 2026-11-03'],['MSFT','Microsoft','V','msft','FY27Q1 ingresos 92.300M'],
 ['VLO','Valero Energy','V','oil','Petroleo cede ante diplomacia'],['AXON','Axon Enterprise','V','axon','Resultados 2026-11-05'],['GLD','SPDR Gold Shares','V','gold','Metales bajo presion'],
 ['TSLA','Tesla','N'],['GOOGL','Alphabet (clase A)','V','pub','Alphabet Q3 ingresos 127.600M'],['AAPL','Apple','V','apple','MacBook Pro PROLED XDR'],['GOOG','Alphabet (clase C)','V','pub','Alphabet Q3 ingresos 127.600M'],
 ['AMZN','Amazon','V','amzn','Conferencia Q3 2026-10-29'],['MRNA','Moderna','N'],['CVX','Chevron','V','oil','Petroleo cede ante diplomacia'],['NVDA','NVIDIA','V','nvda','RTX Spark laptops'],
 ['PLTR','Palantir Technologies','N'],['XOM','Exxon Mobil','V','oil','Petroleo cede ante diplomacia'],['COIN','Coinbase','V','coin','Resultados 2026-10-29'],['USO','United States Oil Fund','V','oil','Petroleo cede ante diplomacia'],
 ['ORCL','Oracle','N'],['C','Citigroup','N'],['EBAY','eBay','V','ebay','Q3 ingresos 3.206M'],['DIS','Walt Disney','N'],['NDAQ','Nasdaq Inc.','N'],['UBER','Uber Technologies','V','uber','Conferencia Q3 2026-11-04'],
 ['NFLX','Netflix','N'],['PYPL','PayPal','N'],['HPE','Hewlett Packard Enterprise','N'],['TNA','Direxion Daily Small Cap Bull 3X','V','fed','Fed mantiene 3,75-4%'],['SLV','iShares Silver Trust','V','gold','Metales bajo presion'],
 ['BAC','Bank of America','N'],['EA','Electronic Arts','N']];
const LIM = 'Última señal 2026-10-28; vigencia 29/10 no certificada. Sin gráficos/fills. MSN inaccesible. Calendario incompleto.';
const detRow = (a, id = ID) => [CORTE, id, a[0], a[1], a[2] === 'V' ? a[4] : 'No verificado: búsqueda individual insuficiente; no afirmar ausencia de novedades 24h.',
  a[2] === 'V' ? 'Contexto/calendario' : 'No verificado', '', '', '', '', '', a[2] === 'V' ? U[a[3]] : '', '', '', a[2] === 'V' ? 'Parcial: contexto verificado' : 'No verificado', LIM];
const CAL = [['PIB/PCE','PIB avance Q3/Personal Income Outlays Sept','2026-10-29','09:30AR/08:30EDT','Confirmado','https://www.bea.gov/news/schedule'],
 ['AMZN','Conferencia Q3','2026-10-29','18AR/17EDT','Confirmado',U.amzn],['COIN','Resultados tras cierre/Q&A','2026-10-29','18AR/14PDT Q&A','Confirmado',U.coin],
 ['XOM','Conferencia Q3','2026-10-30','10:30AR/08:30CDT','Confirmado','https://investor.exxonmobil.com/news-events/ir-calendar'],
 ['CVX','Conferencia Q3','2026-10-30','12AR/11EDT','Confirmado','https://chevroncorp.gcs-web.com/events/event-details/3q-2026-chevron-earnings-conference-call'],
 ['AMD','Resultados tras cierre/llamada','2026-11-03','19AR/17EST','Confirmado; etiqueta PDT calendario discrepante',U.amd],['UBER','Conferencia Q3','2026-11-04','10AR/08EST','Confirmado',U.uber],
 ['Comercio EEUU','Balanza septiembre','2026-11-04','10:30AR/08:30EST','Confirmado','https://www.bea.gov/news/schedule'],['AXON','Resultados tras cierre/webinar','2026-11-05','19AR/17EST','Confirmado',U.axon]];
const calRow = (c, id = ID) => [CORTE, id, c[0], c[1], c[2], c[3], c[4], c[5], 'https://docs.google.com/spreadsheets/d/<ID>/edit#gid=2100000302&range=A247:P281', 'Calendario verificado al corte; no datos publicados.'];
const PREV = [['22/10/2026 08:41:08','MELIORA_20261022_084108_AR','35'],['23/10/2026 08:44:59','MELIORA_20261023_084459_AR','34'],['24/10/2026 08:04:15','MELIORA_20261024_080415_AR','0'],
  ['25/10/2026 08:04:18','MELIORA_20261025_080418_AR','21'],['26/10/2026 08:10:06','MELIORA_20261026_081006_AR','19'],['27/10/2026 08:42:55','MELIORA_20261027_084255_AR','15'],['28/10/2026 08:11:37','MELIORA_20261028_081137_AR','26']];
function fixture() {
  const resumen = [['MELIORA NOTICIAS Y FUNDAMENTOS', 'Acceso e informes diarios'], ['Función', 'Noticias, earnings y contexto de los 35 activos...'], [], ENCABEZADOS.AGENTE_NOTICIAS.slice()]; // bloque de metadatos + encabezado en fila 4 (en la hoja real es la fila 25)
  PREV.forEach(p => resumen.push([p[0], p[1], p[2], '', '', '', '', '']));
  resumen.push([CORTE, ID, '20', '15', '1 MSFT vs Alphabet; 2 PIB/PCE 09:30; 3 AMZN COIN hoy; 4 XOM CVX mañana; 5 faltan trades 28; 6 señales viejas',
    'Sesión 28/10: 0 filas por fecha en Registro Continuo. No auditoría de resultado 28 posible. No repetir neto 27 como actual ni atribuir Sonar.',
    'Cobertura 24h parcial; sin precios sincronizados. No noticias individuales exhaustivas.', 'https://docs.google.com/spreadsheets/d/<ID>/edit#gid=2100000302&range=A247:P281']);
  return { AGENTE_NOTICIAS: resumen,
    NOTICIAS_DIARIAS: [ENCABEZADOS.NOTICIAS_DIARIAS.slice()].concat(A.map(a => detRow(a))),
    CALENDARIO_EVENTOS: [ENCABEZADOS.CALENDARIO_EVENTOS.slice()].concat(CAL.map(c => calRow(c))) };
}
const clone = o => JSON.parse(JSON.stringify(o));
const NOW = new Date('2026-10-29T15:00:00Z');
let ok = 0; const t = (n, fn) => { try { fn(); ok++; console.log('PASS  ' + n); } catch (e) { console.log('FAIL  ' + n + '\n      ' + e.message); process.exitCode = 1; } };
const problemsOf = fx => construirReporte_(fx, { now: NOW }).problems.join(' || ');

// ---- 1. DRY_RUN del corte de aceptacion
const base = construirReporte_(fixture(), { now: NOW });
t('DRY_RUN sin problemas', () => assert.deepStrictEqual(base.problems, []));
const R = base.report;
fs.writeFileSync(path.join(__dirname, 'dryrun_output.json'), JSON.stringify(R, null, 2) + '\n');
t('ID y corte (AR -03:00)', () => { assert.strictEqual(R.report_id, ID); assert.strictEqual(R.cutoff_at, '2026-10-29T08:53:05-03:00'); });
t('agente NOTICIAS (no SONAR)', () => assert.strictEqual(R.agent_id, 'NOTICIAS'));
t('estado PARTIAL', () => assert.strictEqual(R.status, 'PARTIAL'));
t('cobertura 35 esperados / 20 revisados / 15 no verificados / 9 eventos', () => assert.deepStrictEqual(R.coverage, { expected: 35, reviewed: 20, unverified: 15, calendar_events: 9 }));
t('el resumen declara cobertura parcial y NO exhaustiva', () => { assert.match(R.summary, /Cobertura PARCIAL: 20 de 35/); assert.match(R.summary, /15 no verificados/); assert.match(R.summary, /No es una investigación exhaustiva de los 35 activos/); });
t('findings lista los 15 no verificados y 20 verificados', () => { assert.match(R.findings, /ACTIVOS CON CONTEXTO VERIFICADO \(20\)/); assert.match(R.findings, /ACTIVOS NO VERIFICADOS \(15\): BLK, META, MSCI, TSLA, MRNA, PLTR, ORCL, C, DIS, NDAQ, NFLX, PYPL, HPE, BAC, EA/); });
t('fuentes https unicas', () => { assert.ok(R.sources.length >= 10 && R.sources.every(u => u.startsWith('https://'))); assert.strictEqual(new Set(R.sources).size, R.sources.length); });
t('solo campos permitidos por la funcion SQL', () => { const ok = ['agent_id','report_id','revision','format_version','title','summary','findings','cutoff_at','generated_at','status','coverage','sources','limits']; Object.keys(R).forEach(k => assert.ok(ok.includes(k), k)); });
t('limites incluyen 15 de 35 no verificados', () => assert.ok(R.limits[0].startsWith('15 de 35 activos no verificados')));

// ---- 2. Debe detenerse
t('falta un encabezado (NOTICIAS_DIARIAS "ID informe")', () => { const f = fixture(); f.NOTICIAS_DIARIAS[0][1] = 'ID'; const p = problemsOf(f); assert.match(p, /NOTICIAS_DIARIAS encabezado columna 2/); assert.strictEqual(construirReporte_(f, { now: NOW }).report, null); });
t('falta un encabezado (AGENTE_NOTICIAS "Activos no verificados")', () => { const f = fixture(); f.AGENTE_NOTICIAS[3][3] = 'No verificados'; assert.match(problemsOf(f), /AGENTE_NOTICIAS encabezado columna 4/); });
t('falta un encabezado (CALENDARIO_EVENTOS "Fecha prevista")', () => { const f = fixture(); f.CALENDARIO_EVENTOS[0][4] = 'Fecha'; assert.match(problemsOf(f), /CALENDARIO_EVENTOS encabezado columna 5/); });
t('ticker duplicado', () => { const f = fixture(); f.NOTICIAS_DIARIAS[2][2] = 'SPY'; f.NOTICIAS_DIARIAS[3][2] = 'spy'; assert.match(problemsOf(f), /tickers duplicados.*SPY/); });
t('cobertura no cuadra (resumen dice 21 revisados)', () => { const f = fixture(); f.AGENTE_NOTICIAS[f.AGENTE_NOTICIAS.length - 1][2] = '21'; assert.match(problemsOf(f), /Cobertura no cuadra: el resumen declara 21 revisados y el detalle tiene 20/); });
t('faltan filas (34 en vez de 35)', () => { const f = fixture(); f.NOTICIAS_DIARIAS.pop(); assert.match(problemsOf(f), /34 filas y se esperaban 35/); });
t('estado de cobertura desconocido', () => { const f = fixture(); f.NOTICIAS_DIARIAS[6][14] = 'Verificado total'; assert.match(problemsOf(f), /estado de cobertura no reconocido: AMD/); });
t('URL no https', () => { const f = fixture(); f.NOTICIAS_DIARIAS[2][11] = 'http://x.com/a'; assert.match(problemsOf(f), /solo https/); });
t('fecha de calendario invalida', () => { const f = fixture(); f.CALENDARIO_EVENTOS[1][4] = '29/10/2026'; assert.match(problemsOf(f), /fecha prevista inválida/); });
t('ID inexistente', () => assert.match(construirReporte_(fixture(), { reportId: 'MELIORA_20260101_000000_AR', now: NOW }).problems.join(), /aparece 0 veces/));
t('ID repetido en el resumen', () => { const f = fixture(); f.AGENTE_NOTICIAS.push(f.AGENTE_NOTICIAS[f.AGENTE_NOTICIAS.length - 1].slice()); assert.match(problemsOf(f), /aparece 2 veces/); });
t('corte no coincide con el ID', () => { const f = fixture(); f.AGENTE_NOTICIAS[f.AGENTE_NOTICIAS.length - 1][0] = '29/10/2026 09:00:00'; assert.match(problemsOf(f), /no coincide con el ID/); });

// ---- 3. Union por ID, no por cercania de filas
t('filas de OTRO informe intercaladas y el informe desordenado: se une solo por ID', () => {
  const f = fixture(); const body = f.NOTICIAS_DIARIAS.slice(1).reverse(); // orden invertido
  const decoy = detRow(['ZZZZ', 'Intruso', 'V', 'fed', 'otro dia'], 'MELIORA_20261028_081137_AR');
  body.splice(10, 0, decoy, decoy.slice());                                  // intrusas en medio del bloque
  f.NOTICIAS_DIARIAS = [f.NOTICIAS_DIARIAS[0]].concat(body);
  f.CALENDARIO_EVENTOS.splice(3, 0, calRow(['ZZZZ', 'Evento ajeno', '2026-11-30', 'x', 'Confirmado', 'https://x.com'], 'MELIORA_20261028_081137_AR'));
  const r = construirReporte_(f, { now: NOW });
  assert.deepStrictEqual(r.problems, []);
  assert.deepStrictEqual(r.report.coverage, { expected: 35, reviewed: 20, unverified: 15, calendar_events: 9 });
  assert.ok(!/ZZZZ/.test(JSON.stringify(r.report)));
});
console.log(`\n${ok} pruebas correctas` + (process.exitCode ? ' (HAY FALLAS)' : ''));

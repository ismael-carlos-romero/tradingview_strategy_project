import csv, collections, json
r = list(csv.DictReader(open("informe35_post_filas.csv", encoding="utf-8-sig")))
m = json.load(open("informe35_post_meta.json"))["meta"]
c = collections.Counter(x["estado"] for x in r)
cer = [x for x in r if x["estado"] == "CERCA"]
gen = ("GAP_BAJISTA", "GAP_NORMAL", "VELA_ROJA")
o = ["# 2026-10-27 POST-MARKET - Analisis 35 activos vs estrategias Cardona", "",
     "Corrida automatica desatendida, 16:24 ET (17:24 ART), con el dia completo. Solo analisis: sin ordenes, sin tocar bot ni Auto-Trader. No es asesoramiento financiero.", "",
     "## Limitaciones (leer primero)",
     "- uCharts: NO leido. El navegador redirige a la pantalla de login (sin sesion) y el dominio app.ucharts.com no tiene permiso en la extension. Sin capturas de uCharts ni contraste con la referencia de operacion (uCharts Paper Money). Ismael debe iniciar sesion.",
     "- TradingView: sesion iniciada. Layout de Ismael (Meliora captura) NO modificado: su simbolo quedo en META 1h como estaba. Trabaje en un layout nuevo en blanco llamado Claude_analisis_postmarket (puede borrarlo cuando quiera).",
     "- Los estados salen de cardona_rules.py (cardona-pdf-v1) sobre datos Yahoo 30m/diario, NO de lectura de pantalla. Verificado en pantalla en TradingView solo: AAPL, NVDA, SPY, AMD, PLTR, USO (cierres coinciden con el motor; AMD 560.25 TV vs 560.45 Yahoo, resto <=0.06).",
     "- Capturas TradingView (1h) solo de NVDA, SPY, AMD, PLTR, USO: quedaron en el espacio de trabajo de la sesion y se entregan por chat; no estan en esta carpeta. No se tomaron capturas de los otros 30 activos ni diarios. No se dibujaron niveles ni se agregaron indicadores/Pine en TradingView.",
     "- EA: NO leido (Yahoo sin velas de hoy; ultima 2026-08-04). 13 filas NO_LEIDO.",
     "- Catalogo: TABLA_ESTRATEGIAS.md lista 19 detectores (11 Cardona + Techo Fuerte pendiente D6 + 7 SIN_CLASIFICAR), no las 12 exactas. Se evaluaron 13 IDs Cardona; PRIMER_GAP, HANGER_DIARIO, TECHO_FUERTE y RUPTURA_PISO_GAP quedan NO_EVALUABLE (el motor no las implementa o son ambiguas). Los 7 SIN_CLASIFICAR no se evaluaron. Lista de 35 tickers: endpoint local /get_monitored_tickers (respondio).",
     "- Los CUMPLE de abajo ya ocurrieron HOY; las estrategias de gap dispararon en la vela de 10:00 (Cardona las libera desde las 11:00), por lo que no son entradas para manana.", "",
     "## Resumen", ", ".join(f"{k}: {v}" for k, v in c.items()), ""]
o += ["## CUMPLE (ocurrio hoy; contexto para manana)", "", "| Activo | Estrategia | Vela(s) NY | Cierre |", "|---|---|---|---|"]
for x in r:
    if x["estado"].startswith("CUMPLE"):
        hrs = x["evidencia"].split("vela(s) ")[1].split(" NY")[0]
        o.append(f"| {x['activo']} | {x['estrategia']} | {hrs} | {m[x['activo']]['cierre']} |")
o += ["", "## CERCA para la proxima apertura (falta un paso; mas accionable primero)", "",
      "Cada uno requiere vela de confirmacion manana; compras desde 11:00 ET (10:30 ART... verificar hora real de apertura), salvo Vela Roja 10:00.", "",
      "| Activo | Estrategia | Nivel/precio actual | Que falta |", "|---|---|---|---|"]
order = {"PM40_BOUNCE": 0, "PISO_FUERTE": 1, "CANAL_BREAK": 2, "CAIDA_FUERTE": 3, "CAIDA_NORMAL": 4, "4_PASOS": 5}
for x in sorted([x for x in cer if x["estrategia"] not in gen], key=lambda x: (order.get(x["estrategia"], 9), x["activo"])):
    mm = m[x["activo"]]
    falta = x["evidencia"].split(". Falta ")[1].split(". cierre")[0] if ". Falta " in x["evidencia"] else x["evidencia"][:120]
    o.append(f"| {x['activo']} | {x['estrategia']} | cierre {mm['cierre']}; PM20 {mm['PM20']} PM40 {mm['PM40']} PM200 {mm['PM200']} | {falta} |")
o += ["", "### Contexto generico (gaps y Vela Roja; se definen en el premercado/apertura de manana)", "",
      "- GAP_NORMAL (tendencia diaria alcista OK, falta gap>0,1% + 1a y 2a vela verdes, compra desde 11:00): " + ", ".join(sorted(x["activo"] for x in cer if x["estrategia"] == "GAP_NORMAL")),
      "- VELA_ROJA (contexto de canal/PM40/PM200 OK, falta 1a vela 9:30 roja solida con volumen > media; compra 10:00): " + ", ".join(sorted(x["activo"] for x in cer if x["estrategia"] == "VELA_ROJA")),
      "- GAP_BAJISTA: aplica a todos si manana abren con gap < -0,1% y dan 1a y 2a velas verdes (compra desde 11:00).", ""]
o += ["## Niveles de cierre por activo (calculados de datos, no leidos en pantalla)", "", "| Activo | Cierre | PM20 | PM40 | PM100 | PM200 | SMA100d | SMA200d | Tend. diaria alcista | En piso diario |", "|---|---|---|---|---|---|---|---|---|---|"]
for t, v in m.items():
    if "error" in v:
        o.append(f"| {t} | NO LEIDO | | | | | | | | |")
    else:
        o.append(f"| {t} | {v['cierre']} | {v['PM20']} | {v['PM40']} | {v['PM100']} | {v['PM200']} | {v['SMA100d']} | {v['SMA200d']} | {v['tend_diaria_alcista']} | {v['en_piso_diario']} |")
o += ["", "## Discrepancias y no leido", "",
      "- uCharts vs TradingView: no comparable (uCharts sin sesion).",
      "- TradingView vs Yahoo: diferencias menores de ultimo precio (AMD 0.20); resto coincide.",
      "- NO_LEIDO: EA (todas las estrategias).",
      "- NO_EVALUABLE: RUPTURA_PISO_GAP, PRIMER_GAP, HANGER_DIARIO, TECHO_FUERTE para los 35 (reglas no implementadas/ambiguas; D6 sigue pendiente).",
      "- Barras de TradingView y de Yahoo pueden diferir en cierres post-mercado; la referencia de operacion es uCharts Paper Money (no verificada hoy)."]
open("2026-10-27_POST_reporte_postmarket.md", "w", encoding="utf-8").write("\n".join(o))
print("ok", len(o))

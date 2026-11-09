import csv,collections
r=list(csv.DictReader(open("informe35_filas.csv",encoding="utf-8-sig")))
c=collections.Counter(x["estado"] for x in r)
o=["# 2026-10-27 PRE-MARKET - Analisis 35 activos vs estrategias Cardona","",
"Corrida automatica 12:35 UTC (08:35 ET / 09:35 ART). Solo analisis, sin ordenes.","",
"## Limitaciones (leer primero)",
"- TradingView: sesion iniciada, pero el grafico (layout de Ismael, META 1h) NO cargo datos (OHLC en 0, watchlist cargando). Sin capturas de TradingView.",
"- uCharts: no se leyo en esta corrida. Sin capturas ni contraste uCharts vs TradingView.",
"- Los estados salen de analisis/2026-10-27_pre/informe35_filas.csv (reglas cardona_rules.py cardona-pdf-v1, datos Yahoo 30m, generado hoy 09:18). NO verificado en pantalla.",
"- Catalogo: TABLA_ESTRATEGIAS.md lista 19 detectores (11 Cardona + Techo Fuerte pendiente D6 + 7 SIN_CLASIFICAR), no 12 exactas. Tickers: 35 (TICKERS de live_scanner.py; endpoint local no respondio).",
"- Layout de Ismael no modificado.","",
"## Resumen",", ".join(f"{k}: {v}" for k,v in c.items()),"",
"## CUMPLE / CONFIRMADA"]
for x in r:
    if x["estado"]=="Confirmada": o.append(f"- {x['activo']} | {x['estrategia']} | {x['evidencia']}")
o+=["","## CERCA / EN FORMACION (falta un paso; vigilar)","","| Activo | Estrategia | Evidencia |","|---|---|---|"]
for x in r:
    if x["estado"].startswith("En form"): o.append(f"| {x['activo']} | {x['estrategia']} | {x['evidencia']} |")
o+=["","## No evaluable (no leido)","","| Activo | Estrategia | Motivo |","|---|---|---|"]
for x in r:
    if x["estado"]=="No evaluable": o.append(f"| {x['activo']} | {x['estrategia']} | {x['evidencia'][:160]} |")
o+=["","Reglas Cardona: sin compras antes de 11:00 (salvo Primera Vela Roja 10:00), OTM, vencimiento hasta una semana. No es asesoramiento financiero."]
open("2026-10-27_PRE_reporte_premarket.md","w",encoding="utf-8").write("\n".join(o))
print(c)


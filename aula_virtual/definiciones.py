"""Aula Virtual - definiciones VERSIONADAS de las 12 estrategias de Cardona (version aula-def-1.0.0).

Fuente primaria: laminas originales (assets/cardona_*.png). Contrastadas con el motor Atlas (fichas_cardona/atlas_estrategias.py,
atlas-motor-v1) y con TABLA_ESTRATEGIAS.md. Cada criterio declara su ORIGEN:
  lamina  = texto de la lamina de Cardona
  atlas   = interpretacion/umbral del motor Atlas (la lamina no da numero o no lo pide)
  meliora = regla personal de Meliora (ninguna codificada todavia; reservado)
Cada criterio n corresponde al paso n del motor Atlas (mismo orden). 'estado': alineado | difiere | pendiente_revision.
Las contradicciones NO se resuelven: se muestran y el criterio queda pendiente de revision (afecta la puntuacion).
"""
VERSION = "aula-def-1.0.0"
L, A, M = "lamina", "atlas", "meliora"


def c(sid, n, texto, origen, estado="alineado", nota=""):
    return {"id": f"{sid}.c{n}", "n": n, "texto": texto, "origen": origen, "estado": estado, "nota": nota}


def k(tipo, descr, tf="hora"):
    return {"k": tipo, "descr": descr, "tf": tf}


ESTRATEGIAS = {}


def reg(sid, **kw):
    ESTRATEGIAS[sid] = dict(id=sid, **kw)


reg("GAP_NORMAL", nombre="Gap normal al alza", dir="CALL", lamina="cardona_gap_normal_alza.png", num_lamina="5ta CALL", n_ctx=2,
    ventana="11:00-12:00 (lámina: «11am – 12am», probable typo de 12pm)", tf_decision="hora", tf_contraste=["diario"],
    medias=["PM100/PM200 diario en paralelo (alcista)", "PM20/PM40/PM100/PM200 hora (referencia visual)"], trazado=[],
    criterios=[
        c("GAP_NORMAL", 1, "Tendencia alcista diaria (PM100>PM200, en paralelo)", L),
        c("GAP_NORMAL", 2, "Cierre previo en tendencia alcista (cierre diario > PM100)", A, "difiere", "La lámina habla de velas de tendencia alcista a las 4pm; Atlas exige cierre > PM100 diario."),
        c("GAP_NORMAL", 3, "Apertura con salto al alza y 1ª vela (9:30-10:00) verde", L, "alineado", "Atlas usa gap >= 0,1 % (umbral del bot; la lámina no da número)."),
        c("GAP_NORMAL", 4, "2ª vela (10:00-11:00) verde sólida o martillo verde", L),
        c("GAP_NORMAL", 5, "3ª vela final (11:00-12:00) de alto volumen", L, "alineado", "'Alto volumen' = volumen relativo > 1 (propio de Atlas). La lámina admite verde y/o roja; Atlas no mira el color.")],
    descarte=["Gap en canal bajista (lámina: «inestables»)", "Sin 1ª vela verde", "Fuera de 11:00-12:00"],
    contradicciones=[dict(criterio="GAP_NORMAL.ventana", detalle="Lámina: regla de oro «11am – 12am». Se interpreta 11:00-12:00.", estado="pendiente_revision")])

reg("GAP_BAJISTA", nombre="Gap bajista al alza", dir="CALL", lamina="cardona_gap_bajista_alza.png", num_lamina="6ta CALL", n_ctx=2,
    ventana="11:00-15:59", tf_decision="hora", tf_contraste=[], medias=["PM20/PM40/PM100/PM200 hora"],
    trazado=[k("caida", "Línea de techo del canal bajista (une máximos descendentes)")],
    criterios=[
        c("GAP_BAJISTA", 1, "Canal bajista (línea de caída)", L),
        c("GAP_BAJISTA", 2, "Cierre previo al alza con vela verde de tendencia bajista", L),
        c("GAP_BAJISTA", 3, "Apertura ABAJO y 1ª vela verde", L, "alineado", "Atlas: gap <= -0,1 % (umbral del bot)."),
        c("GAP_BAJISTA", 4, "2ª vela (10:00-11:00) verde", L),
        c("GAP_BAJISTA", 5, "3ª vela (11:00-12:00) de alto volumen", L, "alineado", "rvol>1 propio; la lámina admite verde y/o roja.")],
    descarte=["Gap hacia arriba", "1ª vela roja", "Fuera de ventana"], contradicciones=[])

reg("PISO_FUERTE", nombre="Piso fuerte", dir="CALL", lamina="cardona_piso_fuerte.png", num_lamina="7ma CALL", n_ctx=3,
    ventana="11:00-15:59 (principalmente 15:00-16:00)", tf_decision="hora", tf_contraste=["diario"],
    medias=["PM100/PM200 diario (pisos fuertes, en paralelo)", "PM20/PM40 hora"],
    trazado=[k("caida", "Línea de techo del canal bajista que rompe la vela verde/martillo final")],
    criterios=[
        c("PISO_FUERTE", 1, "PM100>PM200 diarios (piso fuerte)", L),
        c("PISO_FUERTE", 2, "Viene de una caída (diario)", L, "alineado", "Atlas: cierre < PM20d y >=2 % bajo el máximo de 20 ruedas (umbral propio)."),
        c("PISO_FUERTE", 3, "Velas rojas diarias tocan o rompen PM100/PM200", L, "alineado", "Atlas: mínimo <= PM*1,005 en los últimos 3 días (tolerancia propia)."),
        c("PISO_FUERTE", 4, "En hora: martillo/verde final rompe la línea de techo del canal bajista", L)],
    descarte=["PM100<PM200", "No viene de caída", "Sin ruptura de línea"],
    contradicciones=[dict(criterio="PISO_FUERTE.c2", detalle="Lámina: 'Se presenta DURANTE una caída' y 'caída larga de 2-4 meses si rompe PM200'; sin umbral numérico.", estado="pendiente_revision")])

reg("PRIMER_GAP", nombre="1er gap al alza", dir="CALL", lamina="cardona_1er_gap_alza.png", num_lamina="9na CALL", n_ctx=2,
    ventana="15:57-16:00 (comprar 2 minutos antes del cierre)", tf_decision="hora", tf_contraste=["diario"],
    medias=["PM100/PM200 diario (zona de piso)", "PM20/PM40/PM100/PM200 hora"],
    trazado=[k("piso_gap", "Línea horizontal en el mínimo de la 1ª vela del día (piso del gap)")],
    criterios=[
        c("PRIMER_GAP", 1, "Viene de una caída (diario)", L),
        c("PRIMER_GAP", 2, "Zona de piso fuerte diario (cerca o bajo PM100/PM200)", L, "alineado", "Atlas: tolerancia 2 % (propia)."),
        c("PRIMER_GAP", 3, "Gap al alza, 1ª vela verde llena con volumen; primer gap tras la caída", L, "alineado", "Atlas: gap>=0,1 %, cuerpo sólido, rvol>1, sin gaps en 5 días previos (umbrales propios)."),
        c("PRIMER_GAP", 4, "Las demás velas respetan el piso del gap", L),
        c("PRIMER_GAP", 5, "Última vela del día (3:58pm) cerrada con el piso respetado", L)],
    descarte=["Sin caída previa", "Vela que cierra bajo el piso del gap (señal de salida)"], contradicciones=[])

reg("PM40", nombre="Promedio móvil 40 hora", dir="CALL", lamina="cardona_pm40.png", num_lamina="2da CALL", n_ctx=2,
    ventana="11:00-15:59", tf_decision="hora", tf_contraste=[],
    medias=["PM20 sobre PM40 y PM100 sobre PM200, EN PARALELO (sin tocarse), en hora"],
    trazado=[k("caida", "Línea de techo del canal bajista de la caída")],
    criterios=[
        c("PM40", 1, "PM20>PM40 y PM100>PM200 en paralelo (hora)", L),
        c("PM40", 2, "Viene de una caída con línea descendente", L, "alineado", "Atlas: caída >= 0,5 % (umbral del bot)."),
        c("PM40", 3, "Velas rojas finales rompen PM20 y tocan/rompen parcialmente PM40", L, "alineado", "Atlas: toque = mínimo<=PM40*1,0015 y cierre>=PM40*0,9985."),
        c("PM40", 4, "Verde final (sólida o martillo, no hanger) rompe PM20 y la línea de techo", L)],
    descarte=["PM20 por debajo de PM40", "Vela final no verde sólida/martillo", "Fuera de 11:00-15:59", "Evaluar en diario"], contradicciones=[])

reg("CAIDA", nombre="Caída normal / Caída fuerte", dir="CALL", lamina="cardona_caida_normal_fuerte.png", num_lamina="3ra CALL", n_ctx=2,
    ventana="11:00-15:59 (ideal viernes)", tf_decision="hora", tf_contraste=["diario"],
    medias=["PM20>PM40 y PM100>PM200 en paralelo (hora)"], trazado=[k("caida", "Línea de techo del canal bajista")],
    criterios=[
        c("CAIDA", 1, "PM20>PM40 y PM100>PM200 en paralelo", L),
        c("CAIDA", 2, "Viene de una caída con línea descendente", L),
        c("CAIDA", 3, "2-3 rojas finales rompen PM20 (normal: sin romper PM40; fuerte: llegan a PM100/PM200)", L, "pendiente_revision", "Ver contradicción de 'Fuerte'."),
        c("CAIDA", 4, "Martillo verde y verde final rompen la línea de techo", L, "pendiente_revision", "La lámina dice también (crit. 6) 'rompe PM100 y/o PM40'.")],
    descarte=["Sin caída", "Rojas rompen PM40 en 'normal'"],
    contradicciones=[
        dict(criterio="CAIDA.c3", detalle="Fuerte: la lámina la define por romper PM20/PM40/PM100/PM200 y a la vez por '>1,5 % / >$6' y 'no llegan a romper PM200'. Atlas usa 'toca PM100/PM200'.", estado="pendiente_revision"),
        dict(criterio="CAIDA.c4", detalle="Gatillo: crit. 4 = rompe línea de techo del canal; crit. 6 = rompe PM100 y/o PM40. Atlas usa la línea de techo.", estado="pendiente_revision")])

reg("CANAL_BREAK", nombre="Ruptura del canal bajista", dir="CALL", lamina="cardona_ruptura_canal_bajista.png", num_lamina="4ta CALL", n_ctx=1,
    ventana="11:00-15:59", tf_decision="hora", tf_contraste=["diario"],
    medias=["PM40 sobre PM20 (hora, cruzados)", "PM200 sobre PM100 (diario, cruzados) - NO evaluado por Atlas"],
    trazado=[k("caida", "Línea de techo del canal bajista (1-4 meses en diario)", "diario+hora")],
    criterios=[
        c("CANAL_BREAK", 1, "Canal bajista: PM40 sobre PM20 y línea de techo", L, "difiere", "Falta en Atlas: PM200>PM100 diario y canal de 1-4 meses (crit. 3-4 lámina)."),
        c("CANAL_BREAK", 2, "Martillo verde reciente (últimas 3 velas)", L),
        c("CANAL_BREAK", 3, "Vela verde final de volumen rompe la línea de techo", L, "alineado", "rvol>1 propio.")],
    descarte=["Velas bajo PM40 sin ruptura: es techo, no piso (lámina crit. 6)", "Sin martillo + verde final"],
    contradicciones=[dict(criterio="CANAL_BREAK.c1", detalle="Atlas no valida PM200>PM100 diario ni la duración del canal. La referencia puede ser más permisiva que la lámina.", estado="pendiente_revision")])

reg("VELA_ROJA", nombre="1ª vela roja de las 10am", dir="PUT", lamina="cardona_primera_vela_roja.png", num_lamina="1ra PUT", n_ctx=1,
    ventana="10:00-11:00 (Atlas)", tf_decision="hora", tf_contraste=[], medias=["PM40 hora (velas bajo/cerca: zona cara)"],
    trazado=[k("caida", "Línea de techo del canal bajista"), k("piso_gap", "Línea horizontal en el borde inferior del cuerpo de la 1ª vela")],
    criterios=[
        c("VELA_ROJA", 1, "Canal bajista, velas bajo/cerca de PM40 (zona cara)", L, "alineado", "Atlas: cerca = 1,5 % (propio). Para canal alcista la lámina pide >= 7,5 USD sobre PM40; Atlas no lo evalúa aquí."),
        c("VELA_ROJA", 2, "Abre con vela roja bajo PM40", L),
        c("VELA_ROJA", 3, "Vela roja final rompe con el CUERPO la línea de piso del gap", L, "pendiente_revision", "Contradicción de horario.")],
    descarte=["Primera vela verde", "Vela sobre PM40 en canal bajista"],
    contradicciones=[dict(criterio="VELA_ROJA.ventana", detalle="Regla de oro: 10am y 'única que se compra a las 10am'; criterio 5: esperar la roja final de las 11am que rompa el piso del gap. Atlas acepta hasta el cierre de 11:00.", estado="pendiente_revision")])

reg("RUPT_PISO", nombre="Ruptura del piso del gap", dir="PUT", lamina="cardona_ruptura_piso_gap.png", num_lamina="2da PUT", n_ctx=1,
    ventana="11:00-12:00 (Atlas; lámina: 11am)", tf_decision="hora", tf_contraste=[], medias=["PM40 hora (distancia >= 7,5/10 USD)"],
    trazado=[k("piso_gap", "Línea horizontal en el borde inferior del cuerpo de la vela anterior")],
    criterios=[
        c("RUPT_PISO", 1, "Cierre previo con vela roja y precio >= 7,5/10 USD sobre PM40 (zona cara)", L, "alineado", "Umbral literal en USD (pensado para SPY/QQQ)."),
        c("RUPT_PISO", 2, "Abre con gap/verde de bajo volumen lejos de PM40", L),
        c("RUPT_PISO", 3, "Vela roja final (>=11am) rompe con el CUERPO la línea horizontal del piso del gap", L, "pendiente_revision", "Contradicción cola/cuerpo.")],
    descarte=["Sin vela roja previa", "Ruptura con la cola solamente"],
    contradicciones=[dict(criterio="RUPT_PISO.c3", detalle="Crit. 4: la línea parte de la COLA final de la vela verde; crit. 6: une el BORDE INFERIOR DEL CUERPO de la vela anterior. Atlas usa el cuerpo.", estado="pendiente_revision")])

reg("CUATRO_PASOS", nombre="Modelo de los 4 pasos", dir="PUT", lamina="cardona_modelo_4_pasos.png", num_lamina="3ra PUT", n_ctx=2,
    ventana="11:00-12:00", tf_decision="hora", tf_contraste=[], medias=["PM40 sobre PM20 (hora); velas bajo PM40"],
    trazado=[k("caida", "Paso 1: línea de techo del canal bajista"), k("piso", "Paso 2: línea de piso del canal")],
    criterios=[
        c("CUATRO_PASOS", 1, "Canal bajista: PM40 sobre PM20 y velas bajo PM40 (zona cara)", L),
        c("CUATRO_PASOS", 2, "Líneas de techo y de piso del canal trazadas", L, "pendiente_revision", "Texto dice horizontales; el gráfico muestra diagonales."),
        c("CUATRO_PASOS", 3, "Vela verde en zona de techo borrada por una roja", L),
        c("CUATRO_PASOS", 4, "Vela roja final rompe la línea de piso", L)],
    descarte=["Sin zona de techo", "Verde no borrada"],
    contradicciones=[dict(criterio="CUATRO_PASOS.c2", detalle="Crit. 3-4: líneas HORIZONTALES de techo y piso; imagen y Atlas: líneas diagonales.", estado="pendiente_revision")])

reg("HANGER", nombre="Hanger en diario", dir="PUT", lamina="cardona_hanger_diario.png", num_lamina="4ta PUT", n_ctx=1,
    ventana="15:57-16:00", tf_decision="hora", tf_contraste=["diario"], medias=["PM40/PM100/PM200 (distancia >= 20 USD en tendencia alcista)"],
    trazado=[k("caida", "Línea de techo (zona de techo)")],
    criterios=[
        c("HANGER", 1, "Zona de techo (cerca del máximo de 20 ruedas o de la línea de techo)", L, "difiere", "Lámina pide >= 20 USD sobre PM40 en alcista; Atlas no."),
        c("HANGER", 2, "Hora: 4 verdes seguidas y 2 rojas de volumen que las borran", L),
        c("HANGER", 3, "Hanger diario confirmado al cierre (3:57pm)", L, "alineado", "Atlas: cola superior >= 45 % del rango y cuerpo <= 40 % (propio).")],
    descarte=["Hanger sin zona de techo", "Cierre alcista del día"], contradicciones=[])

reg("TECHO_FUERTE", nombre="Techo fuerte", dir="PUT", lamina="cardona_techo_fuerte.png", num_lamina="8va CALL (título) / criterios PUT", n_ctx=2,
    ventana="11:00-15:59 (propia de Atlas; la lámina no da hora)", tf_decision="hora", tf_contraste=["diario"],
    medias=["PM100/PM200 diario cruzados o invertidos (PM200>PM100)"],
    trazado=[k("techo_fuerte", "Línea horizontal que une las subidas más altas", "diario")],
    criterios=[
        c("TECHO_FUERTE", 1, "Techo fuerte: máximos horizontales (>=2) y precio cerca", L, "alineado", "Lámina: semana y/o diario; Atlas solo diario (260 ruedas)."),
        c("TECHO_FUERTE", 2, "PM100/PM200 diarios cruzados o invertidos (PM200>PM100)", L),
        c("TECHO_FUERTE", 3, "Hora: 2 rojas finales consecutivas que no rompen el techo", L),
        c("TECHO_FUERTE", 4, "3ª roja rompe con el CUERPO la línea del gap de la roja anterior", L)],
    descarte=["PM100>PM200 sin cruce", "Techo sin 2 toques"],
    contradicciones=[
        dict(criterio="TECHO_FUERTE.dir", detalle="Título: 'comprar Opciones CALL' / 'Ideal CALL 3-5 días'; criterios 5-6: 'comprar PUT'. Atlas sigue el texto (PUT). Además ¿es de Cardona? (D6 de TABLA_ESTRATEGIAS.md).", estado="pendiente_revision"),
        dict(criterio="TECHO_FUERTE.ventana", detalle="La lámina no da regla de oro horaria; Atlas usa 11:00-15:59 (propio).", estado="pendiente_revision")])

ORDEN = list(ESTRATEGIAS)
LAMINAS_SIN_DETECTOR = [
    dict(id="RUPTURA_TECHO", nombre="Ruptura del techo (1ra CALL)", lamina="cardona_ruptura_techo.png", motivo="Lámina disponible; Atlas no tiene detector propio (se solapa con PM40/Ruptura de canal)."),
    dict(id="VRFED", nombre="Vela roja final envolvente del día (5ta PUT)", lamina="cardona_vela_roja_envolvente.png", motivo="Lámina disponible; Atlas no tiene detector. Requiere velas de 3:55pm y doble volumen."),
]
RUBRICA = {"version": "rub-1.0.0", "origen": "criterio pedagógico inicial (editable)",
           "pesos": {"contexto": 20, "requisitos": 20, "trazado": 25, "clasificacion": 25, "explicacion": 10}}
UMBRALES_DOMINIO = {"version": "dom-1.0.0", "origen": "criterio pedagógico inicial (editable)", "casos_min": 5, "puntaje_medio_min": 80,
                    "dias_distintos_min": 3, "activos_distintos_min": 3, "sin_ayuda_min": 3, "contraejemplos_min": 1,
                    "repaso_dias": [1, 3, 7, 14, 30]}


def criterio_texto(cid):
    for x in ESTRATEGIAS.get(cid.split(".")[0], {}).get("criterios", []):
        if x["id"] == cid:
            return x["texto"]
    return cid

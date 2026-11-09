"""Servicio Atlas vivo: corre atlas_diario en horarios fijos (hora de Nueva York), lunes a domingo, sin intervencion.
Se enciende con INICIAR_MELIORA_OPTIONS.bat. Solo analiza y avisa; no opera. Uso: python atlas_servicio.py [--ahora]"""
import os, sys, json, time, traceback
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI)); sys.path.insert(0, AQUI)
import pandas as pd
import atlas_diario as ad

OUT = ad.OUT
# hora NY. Las velas horarias cierran en punto: se corre unos minutos despues. 09:00 = premercado.
LUNVIE = ["09:00", "10:03", "11:03", "12:03", "13:03", "14:03", "15:03", "16:03", "17:30"]
FINDE = {5: ["12:00"], 6: ["18:00"]}      # sabado, domingo: escenario para el lunes
GRACIA_MIN = 40
LOG = os.path.join(OUT, "servicio.log")
EST = os.path.join(OUT, "servicio_estado.json")


def log(m):
    os.makedirs(OUT, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{pd.Timestamp.now(tz='America/New_York').strftime('%Y-%m-%d %H:%M:%S')} {m}\n")
    try:
        if os.path.getsize(LOG) > 2_000_000:
            os.replace(LOG, LOG + ".old")
    except OSError:
        pass


def slots_de(ahora):
    wd = ahora.weekday()
    return LUNVIE if wd < 5 else FINDE.get(wd, [])


def pendiente(ahora, hechos):
    for hhmm in slots_de(ahora):
        t = pd.Timestamp(f"{ahora.strftime('%Y-%m-%d')} {hhmm}", tz="America/New_York")
        k = f"{ahora.strftime('%Y-%m-%d')}_{hhmm}"
        if k not in hechos and t <= ahora <= t + pd.Timedelta(minutes=GRACIA_MIN):
            return k
    return None


def main():
    hechos = json.load(open(EST, encoding="utf-8")) if os.path.exists(EST) else {}
    log("servicio Atlas iniciado" + (" (--ahora)" if "--ahora" in sys.argv else ""))
    primera = "--ahora" in sys.argv
    while True:
        ahora = pd.Timestamp.now(tz="America/New_York")
        k = "ahora_" + ahora.strftime("%Y-%m-%d_%H%M") if primera else pendiente(ahora, hechos)
        if k:
            try:
                data, ev = ad.run(motivo=k)
                log(f"corrida {k} ok: asof {data['asof']}, avisos {len(ev)}")
            except Exception:
                log("ERROR en corrida " + k + "\n" + traceback.format_exc()[-900:])
                json.dump({"ts": str(ahora)[:19], "ok": False, "error": traceback.format_exc()[-300:]}, open(os.path.join(OUT, "heartbeat.json"), "w"))
            hechos[k] = str(ahora)[:19]
            hechos = {a: b for a, b in hechos.items() if a[:10] >= (ahora - pd.Timedelta(days=3)).strftime("%Y-%m-%d") or a.startswith("ahora_")}
            json.dump(hechos, open(EST, "w", encoding="utf-8"))
            if primera:
                return
        time.sleep(30)


if __name__ == "__main__":
    main()

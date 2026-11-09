import json, sys, os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(__file__))
from ficha_guard import validar_ficha, ET

def f(bar, last, cond="Cumple", modo="PAPER", sid="PISO_FUERTE"):
    return dict(ticker="NVDA", strategy_id=sid, direction="CALL", bar_time=bar, bar_minutes=60,
                last_data_time=last, modo=modo, condiciones=[dict(nombre="x", estado=cond, necesaria=True)])

T = lambda d, h, m=0: datetime(2026, 10, d, h, m, tzinfo=ET)
casos = []
def caso(nombre, ficha, ahora, usadas, esperado):
    ok, mot, clave = validar_ficha(ficha, ahora, usadas)
    casos.append(dict(caso=nombre, ok=ok, motivos=mot, esperado=esperado, pasa=(ok == (esperado == "OK") and (esperado == "OK" or esperado in mot))))

# Martes 27/10/2026
caso("VIGENTE 11:05, barra 10:00 cerrada", f(T(27,10), T(27,11,0)), T(27,11,5), set(), "OK")
caso("ANTIGUA premercado 08:30 con barra de ayer 15:00", f(T(26,15), T(26,16,0)), T(27,8,30), set(), "BARRA_DE_OTRA_SESION")
caso("ANTIGUA en sesión (barra de ayer 15:00 a las 11:05)", f(T(26,15), T(26,16,0)), T(27,11,5), set(), "BARRA_DE_OTRA_SESION")
caso("DATO VIEJO (último dato 08:00 a las 11:05)", f(T(27,10), T(27,8,0)), T(27,11,5), set(), "DATO_VIEJO")
caso("DUPLICADA (misma barra ya usada)", f(T(27,10), T(27,11,0)), T(27,11,10), {"NVDA|PISO_FUERTE|2026-10-27T10:00:00-04:00"}, "DUPLICADA")
caso("INCOMPLETA (condición Pendiente)", f(T(27,10), T(27,11,0), cond="Pendiente"), T(27,11,5), set(), "CONDICIONES_INCOMPLETAS")
caso("ANTES de 11:00 (10:45)", f(T(27,9,30), T(27,10,45)), T(27,10,45), set(), "ANTES_DE_HORA_PERMITIDA")
caso("EXCEPCIÓN Vela Roja 10:05", dict(f(T(27,9,30), T(27,10,5), sid="VELA_ROJA"), bar_minutes=30), T(27,10,5), set(), "OK")
caso("BARRA NO CERRADA (barra 11:00 a las 11:20)", f(T(27,11), T(27,11,20)), T(27,11,20), set(), "BARRA_NO_CERRADA")
caso("NO PAPER", f(T(27,10), T(27,11,0), modo="REAL"), T(27,11,5), set(), "MODO_NO_PAPER")
caso("FIN DE SEMANA (sábado 24/10)", f(T(23,15), T(23,16,0)), T(24,11,0), set(), "MERCADO_CERRADO")
caso("POSTMERCADO 17:00", f(T(27,15), T(27,16,0)), T(27,17,0), set(), "MERCADO_CERRADO")

print(json.dumps(casos, ensure_ascii=False, indent=1))
print("PASAN %d/%d" % (sum(c["pasa"] for c in casos), len(casos)))

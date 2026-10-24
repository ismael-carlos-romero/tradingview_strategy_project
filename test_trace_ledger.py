import os, sqlite3, tempfile, unittest
import trace_ledger as t


class TraceLedgerTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "t.db")

    def conn(self):
        return sqlite3.connect(self.path)

    def test_recorrido_completo_con_reinicio_parcial_y_reintento(self):
        c = self.conn()
        t.registrar_origen(c, "S1", signal_id="SIG1", fuente_senal="SCANNER_PYTHON", strategy_id="PM40_BOUNCE",
                           strategy_version="v1", detector_ver="sha1:abc", modo_ejecucion="SONAR",
                           ticker="SPY", direccion="CALL", timeframe="1H", canales=["TELEGRAM"])
        t.registrar_evento(c, "S1", "VALIDADA", "UCHARTS_PAPER")
        t.registrar_evento(c, "S1", "ENCOLADA", "UCHARTS_PAPER", order_id="O1")
        t.registrar_evento(c, "S1", "ENVIADA", "UCHARTS_PAPER", order_id="O1")
        c.close()
        c = self.conn()  # "reinicio"
        self.assertTrue(t.registrar_evento(c, "S1", "PARCIAL", "UCHARTS_PAPER", order_id="O1", execution_id="E1", qty=1, px_ejecutado=1.2))
        self.assertTrue(t.registrar_evento(c, "S1", "PARCIAL", "UCHARTS_PAPER", order_id="O1", execution_id="E2", qty=2, px_ejecutado=1.3))
        self.assertTrue(t.registrar_evento(c, "S1", "EJECUTADA", "UCHARTS_PAPER", order_id="O1", trade_id="T1", strike=500.0))
        # reintento de sincronizacion / retransmision: no duplica
        self.assertFalse(t.registrar_evento(c, "S1", "EJECUTADA", "UCHARTS_PAPER", order_id="O1", trade_id="T1", strike=500.0))
        t.registrar_evento(c, "S1", "CERRADA", "UCHARTS_PAPER", trade_id="T1", motivo="SL")
        o, ev = t.timeline(c, "S1")
        self.assertEqual(o["fuente_senal"], "SCANNER_PYTHON")
        self.assertEqual(o["familia"], "CARDONA")
        self.assertEqual([e["estado"] for e in ev], ["VALIDADA", "ENCOLADA", "ENVIADA", "PARCIAL", "PARCIAL", "EJECUTADA", "CERRADA"])
        self.assertTrue(all(e["trade_id"] in (None, "T1") for e in ev))

    def test_desconocido_es_null_no_cero(self):
        c = self.conn()
        t.registrar_evento(c, "S2", "RECIBIDA", "SIM_INTERNO")
        _, ev = t.timeline(c, "S2")
        self.assertIsNone(ev[0]["px_ejecutado"])
        self.assertIsNone(ev[0]["strike"])

    def test_origen_no_se_reescribe(self):
        c = self.conn()
        t.registrar_origen(c, "S3", fuente_senal="SCANNER_PYTHON")
        t.registrar_origen(c, "S3", fuente_senal="ATLAS")
        o, _ = t.timeline(c, "S3")
        self.assertEqual(o["fuente_senal"], "SCANNER_PYTHON")

    def test_corroboracion_no_crea_eventos(self):
        c = self.conn()
        t.registrar_origen(c, "S4", fuente_senal="SCANNER_PYTHON")
        self.assertTrue(t.agregar_corroboracion(c, "S4", "TRADINGVIEW", {"score": 3}))
        self.assertFalse(t.agregar_corroboracion(c, "NOEXISTE", "ATLAS"))
        o, ev = t.timeline(c, "S4")
        self.assertIn("TRADINGVIEW", o["corroboraciones"])
        self.assertEqual(ev, [])

    def test_validaciones(self):
        c = self.conn()
        with self.assertRaises(ValueError):
            t.registrar_evento(c, "S5", "COMPRADA", "SIM_INTERNO")
        with self.assertRaises(ValueError):
            t.registrar_origen(c, "S5", fuente_senal="TELEGRAM")
        with self.assertRaises(ValueError):
            t.registrar_evento(c, "S5", "RECIBIDA", "SIM_INTERNO", precio=1)

    def test_familias(self):
        self.assertEqual(len(t.CARDONA), 12)
        self.assertEqual(t.familia_de("TECHO_FUERTE"), "CARDONA")

        for emitido in ("PRIMER_GAP", "GAP_BAJISTA", "CAIDA_NORMAL", "CAIDA_FUERTE", "4_PASOS", "RUPTURA_PISO", "cond_4_pasos"):
            self.assertEqual(t.familia_de(emitido), "CARDONA", emitido)
        for p in ("COLA_TECHO", "COLA_PISO", "RUPTURA_RES", "RUPTURA_SOP", "PISO_BREAK", "GAP_CONT_PUT"):
            self.assertEqual(t.familia_de(p), "SIN_CLASIFICAR", p)
        self.assertEqual(t.familia_de("INVENTADA"), "SIN_CLASIFICAR")
        self.assertEqual(t.familia_de(None), "SIN_CLASIFICAR")

    def test_safe_no_propaga(self):
        self.assertIsNone(t.safe(t.registrar_evento, None, "S", "COMPRADA", "X"))


class Etapa1ContinuacionTests(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "t2.db")
        self.c = sqlite3.connect(self.path)

    def uc(self, **d):
        return t.registrar_evento_uc(self.c, d)

    def test_compra_manual_sin_estrategia_y_cierre_fifo(self):
        self.uc(estado="ENVIADA", local_id="MAN_SPY_1", modo="MANUAL", ticker="SPY", type="CALL")
        self.uc(estado="EJECUTADA", local_id="MAN_SPY_1", modo="MANUAL", ticker="SPY", type="CALL", strike=600, qty=1, price=1.5)
        self.uc(estado="EJECUTADA", local_id="MAN_SPY_2", modo="MANUAL", ticker="SPY", type="CALL", strike=600, qty=1, price=1.6)
        o, ev = t.timeline(self.c, "MAN_SPY_1")
        self.assertEqual((o["fuente_senal"], o["familia"], o["strategy_id"], o["modo_ejecucion"]), ("MANUAL", "SIN_CLASIFICAR", None, "MANUAL"))
        self.assertEqual([e["estado"] for e in ev], ["ENVIADA", "EJECUTADA"])
        self.uc(estado="CERRADA", local_id="C1", ticker="SPY", type="CALL", strike=600, qty=1, price=2.0, motivo="TP")
        self.assertEqual(t.timeline(self.c, "MAN_SPY_1")[1][-1]["estado"], "CERRADA")   # FIFO: cierra la primera
        self.assertEqual(t.timeline(self.c, "MAN_SPY_2")[1][-1]["estado"], "EJECUTADA")
        self.uc(estado="CERRADA", local_id="C2", ticker="SPY", type="CALL", strike=600, motivo="SL")
        self.assertEqual(t.timeline(self.c, "MAN_SPY_2")[1][-1]["estado"], "CERRADA")

    def test_familia_resuelta_en_filas_antiguas(self):
        t.registrar_origen(self.c, "OLD", fuente_senal="SCANNER_PYTHON", familia="SIN_CLASIFICAR", strategy_id="4_PASOS")
        o, _ = t.timeline(self.c, "OLD")
        self.assertEqual((o["familia"], o["familia_resuelta"]), ("SIN_CLASIFICAR", "CARDONA"))

    def test_cierre_enviado_no_es_cierre_y_venta_del_historial_cierra(self):
        self.uc(estado="EJECUTADA", local_id="V1", ticker="SPY", type="PUT", strike=590, qty=1, price=2.0)
        self.uc(estado="CIERRE_ENVIADA", local_id="L1", ticker="SPY", type="PUT", strike=590, motivo="TP")
        ev = t.timeline(self.c, "V1")[1]
        self.assertEqual([e["estado"] for e in ev], ["EJECUTADA", "CIERRE_ENVIADA"])   # orden puesta != cerrada
        self.assertEqual(ev[-1]["trade_id"], "UC_V1")
        r = t.conciliar_historial(self.c, [{"lado": "SELL", "ticker": "SPY", "type": "PUT", "strike": 590, "qty": 1, "price": 2.3, "ts": "z"}])
        self.assertEqual(r["CERRADA_DESDE_HISTORIAL"], 1)
        self.assertEqual(t.timeline(self.c, "V1")[1][-1]["estado"], "CERRADA")
        self.assertEqual(t.conciliar_historial(self.c, [{"lado": "SELL", "ticker": "SPY", "type": "PUT", "strike": 590, "qty": 1, "price": 2.3, "ts": "z"}])["CERRADA_DESDE_HISTORIAL"], 0)

    def test_recompra_resuelve_padre_por_ref(self):
        self.uc(estado="EJECUTADA", local_id="P1", ticker="SPY", type="CALL", strike=600, qty=1, price=1.0)
        self.uc(estado="CERRADA", local_id="PC", ticker="SPY", type="CALL", strike=600)
        self.uc(estado="EJECUTADA", local_id="R1", modo="RECOMPRA_GANADORES", ticker="SPY", type="CALL", strike=605, parent_ref={"ticker": "SPY", "type": "CALL"})
        self.assertEqual(self.c.execute("SELECT parent_trade_id FROM trace_eventos WHERE setup_id='R1'").fetchone()[0], "UC_P1")

    def test_cierre_huerfano_y_reintento_no_duplica(self):
        self.assertTrue(self.uc(estado="CERRADA", local_id="X", ticker="QQQ", type="PUT", strike=500))
        self.assertFalse(self.uc(estado="CERRADA", local_id="X", ticker="QQQ", type="PUT", strike=500))
        self.assertEqual(t.timeline(self.c, "HUERFANA_UC_X")[1][0]["estado"], "CERRADA")

    def test_patas_y_recompras(self):
        for i, tp in enumerate(("CALL", "PUT")):
            self.uc(estado="EJECUTADA", local_id=f"TST_{i}", modo="TESTER", ticker="SPY", type=tp, strike=600 + i, group_id="GRP1")
        self.uc(estado="EJECUTADA", local_id="REC1", modo="RECOMPRA_GANADORES", ticker="SPY", type="CALL", strike=601, parent_trade_id="UC_TST_0")
        g = [r[0] for r in self.c.execute("SELECT setup_id FROM trace_eventos WHERE group_id='GRP1' ORDER BY id")]
        self.assertEqual(g, ["TST_0", "TST_1"])
        self.assertEqual(self.c.execute("SELECT parent_trade_id FROM trace_eventos WHERE setup_id='REC1'").fetchone()[0], "UC_TST_0")

    def test_cierre_simulador_enlaza_por_trade_id(self):
        t.registrar_origen(self.c, "S9", fuente_senal="SCANNER_PYTHON", strategy_id="PM40_BOUNCE")
        t.registrar_evento(self.c, "S9", "EJECUTADA", "SIM_INTERNO", trade_id="TRD_1", ticker="SPY")
        self.assertTrue(t.registrar_cierre_sim(self.c, "TRD_1", pnl_usd=12.5, motivo="TP"))
        self.assertFalse(t.registrar_cierre_sim(self.c, "TRD_1", pnl_usd=12.5))
        self.assertEqual(t.timeline(self.c, "S9")[1][-1]["estado"], "CERRADA")
        t.registrar_cierre_sim(self.c, "TRD_NUNCA", pnl_usd=1)
        self.assertEqual(len(t.timeline(self.c, "HUERFANA_TRD_NUNCA")[1]), 1)

    def test_cola_persistente_conservadora(self):
        item = lambda s: {"setup_id": s, "ticker": "SPY", "direction": "CALL"}
        for s in ("Q1", "Q2", "Q3", "Q4"):
            t.registrar_evento(self.c, s, "ENCOLADA", "UCHARTS_PAPER", evidencia={"item": item(s)})
        t.registrar_evento(self.c, "Q2", "ENVIADA", "UCHARTS_PAPER")      # ofrecida sin resultado: NO se recupera
        t.registrar_evento(self.c, "Q3", "EJECUTADA", "UCHARTS_PAPER")
        t.registrar_evento(self.c, "Q4", "CANCELADA", "UCHARTS_PAPER")
        self.assertEqual([i["setup_id"] for i in t.pendientes_recuperables(self.c)], ["Q1"])
        self.assertEqual([i["setup_id"] for i in t.a_conciliar(self.c)], ["Q2"])
        self.assertEqual(t.pendientes_recuperables(self.c, max_edad_min=-1), [])  # evento mas viejo que el limite
        self.assertEqual(t.cancelar_encoladas(self.c, ["Q1"], "STOP"), 1)
        self.assertEqual(t.pendientes_recuperables(self.c), [])

    def test_conciliacion_no_es_automatica(self):
        self.uc(estado="EJECUTADA", local_id="B1", ticker="SPY", type="CALL", strike=600, qty=1, price=1.50)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='trace_conciliacion'").fetchone()[0], 0)
        r = t.conciliar_historial(self.c, [
            {"lado": "BUY", "ticker": "SPY", "type": "CALL", "strike": 600, "qty": 1, "price": 1.51, "ts": "a"},
            {"lado": "BUY", "ticker": "QQQ", "type": "PUT", "strike": 500, "qty": 1, "price": 2.0, "ts": "b"}])
        self.assertEqual(r, {"COINCIDE": 1, "DIFIERE": 0, "SIN_ORIGEN": 1, "CERRADA_DESDE_HISTORIAL": 0})
        self.assertEqual(t.conciliar_historial(self.c, [{"lado": "BUY", "ticker": "SPY", "type": "CALL", "strike": 600, "qty": 1, "price": 1.51, "ts": "a"}]),
                         {"COINCIDE": 0, "DIFIERE": 0, "SIN_ORIGEN": 0, "CERRADA_DESDE_HISTORIAL": 0})   # repetir no duplica
        self.uc(estado="EJECUTADA", local_id="B2", ticker="SPY", type="CALL", strike=610, qty=2, price=1.0)
        r = t.conciliar_historial(self.c, [{"lado": "BUY", "ticker": "SPY", "type": "CALL", "strike": 610, "qty": 1, "price": 1.0, "ts": "c"}])
        self.assertEqual(r["DIFIERE"], 1)


if __name__ == "__main__":
    unittest.main()

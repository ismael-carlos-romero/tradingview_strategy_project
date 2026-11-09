src = r"..\ucharts_sync_userscript_v5.0.45.js"
dst = r"..\ucharts_sync_userscript_v5.0.46.js"
s = open(src, encoding="utf-8").read().replace("5.0.45", "5.0.46")


def rep(a, b):
    global s
    assert s.count(a) == 1, (s.count(a), a[:80])
    s = s.replace(a, b)


rep("      let stableRounds = 0;\n      for (let round = 0; round < 400; round++) {",
    "      let stableRounds = 0;\n      let fastContainer = null; // v5.0.46: el contenedor se busca UNA vez y el avance se mide por scrollHeight (barato)\n      for (let round = 0; round < 400; round++) {")
rep("""        let before = extractDescElements().length;
        let sample = extractDescElements().slice(-1)[0];
        let container = sample ? findScrollableContainer(sample) : (document.scrollingElement || document.documentElement);""",
    """        if (!fastContainer) {
          const sample0 = extractDescElements().slice(-1)[0];
          fastContainer = sample0 ? findScrollableContainer(sample0) : (document.scrollingElement || document.documentElement);
        }
        let container = fastContainer;
        let before = container ? container.scrollHeight : 0;""")
rep("if (extractDescElements().length > before) { grew = true; break; }",
    "if (container && container.scrollHeight > before) { grew = true; break; }")
rep("""          let elemsNow = extractDescElements();
          let oldestEl = elemsNow.slice(-1)[0];
          let oldestRow = oldestEl ? findRowData(oldestEl) : null;
          if (oldestRow && oldestRow.date) {
            let oldestTs = historyTimestamp(oldestRow.date);
            if (oldestTs && oldestTs < cutoffTs) break;
          }""",
    """          // v5.0.46: la fecha mas vieja cargada se lee del texto del contenedor (antes se recorria todo el DOM en cada vuelta y
          // con miles de filas la pestana se congelaba).
          const datesTxt = (container && container.innerText) || document.body.innerText || '';
          const dm = datesTxt.match(/\\d{1,2}[\\/-]\\d{1,2}[\\/-]\\d{4}\\s+\\d{1,2}:\\d{2}(?::\\d{2})?/g);
          if (dm && dm.length) {
            const oldestTs = historyTimestamp(dm[dm.length - 1]);
            if (oldestTs && oldestTs < cutoffTs) break;
          }""")
rep("const result = await syncHistory(false, { maxDaysBack: 5 });", "const result = await syncHistory(false, { maxDaysBack: 2 });")
open(dst, "w", encoding="utf-8").write(s)
print("ok")

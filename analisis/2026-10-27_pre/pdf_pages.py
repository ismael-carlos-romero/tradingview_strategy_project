import fitz, os
base = r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project"
out = base + r"\analisis\2026-10-27_pre\fichas"
cands = [base + r"\ESTRATEGIAS (1).pdf", base + r"\ESTRATEGIAS\Grupo cerrado de whatsapp del Seminario Creando Riqueza de Alejandro Cardona\Libros\ESTRATEGIAS.pdf", base + r"\ESTRATEGIAS\Libros\ESTRATEGIAS.pdf"]
for c in cands:
    if not os.path.exists(c): print("NO", c); continue
    d = fitz.open(c)
    print(c, len(d), "paginas")
    for p in (5, 6, 8, 32, 40):
        t = d[p - 1].get_text()[:70].replace("\n", " | ")
        print("  p", p, t)
doc = fitz.open(cands[0])
for p in (5, 6, 8, 32, 40):
    doc[p - 1].get_pixmap(dpi=80).save(out + rf"\pdf_p{p}.png")
print("ok")

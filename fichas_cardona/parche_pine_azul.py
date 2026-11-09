import shutil
f = "meliora_fichas_cardona_v6.pine"
shutil.copy(f, f + ".bak_azul")
s = open(f, encoding="utf-8").read()
assert "verAzul" not in s
s = s.replace('verPM = input.bool', '''verAzul = input.bool(true, "Dibujar líneas de tendencia AZULES (swing, como las manuales)")
azulBars = input.int(200, "Velas hacia atrás para buscar swings (1h)", minval=40, maxval=290)
pivL = input.int(4, "Swing: velas a la izquierda", minval=1, maxval=15)
pivR = input.int(3, "Swing: velas a la derecha", minval=1, maxval=15)
verPM = input.bool''', 1)
s += '''
// ===== LINEAS DE TENDENCIA AZULES (estilo manual de Ismael) =====
// Bajista: une el swing high mas lejano valido con el ultimo swing high (maximos decrecientes); ningun cierre entre ambos por encima de la linea.
// Alcista: une el swing low mas lejano valido con el ultimo swing low (minimos crecientes); ningun cierre entre ambos por debajo de la linea.
// Se extienden hacia la derecha. Solo informativo.
phv = ta.pivothigh(high, pivL, pivR)
plv = ta.pivotlow(low, pivL, pivR)
var array<int> phI = array.new<int>()
var array<float> phP = array.new<float>()
var array<int> plI = array.new<int>()
var array<float> plP = array.new<float>()
if not na(phv)
    array.push(phI, bar_index - pivR)
    array.push(phP, phv)
if not na(plv)
    array.push(plI, bar_index - pivR)
    array.push(plP, plv)
var array<line> tl = array.new<line>()
var array<label> tb2 = array.new<label>()
if barstate.islast and verAzul
    while array.size(tl) > 0
        line.delete(array.pop(tl))
    while array.size(tb2) > 0
        label.delete(array.pop(tb2))
    nn = bar_index
    minI = math.max(base, nn - azulBars)
    // bajista
    k2 = array.size(phI) - 1
    if k2 >= 1
        i2 = array.get(phI, k2)
        p2 = array.get(phP, k2)
        bool hecho = false
        for k1 = 0 to k2 - 1
            if not hecho
                i1 = array.get(phI, k1)
                p1 = array.get(phP, k1)
                if i1 >= minI and p1 > p2 and i2 > i1
                    sl = (p2 - p1) / (i2 - i1)
                    bool ok = true
                    for j = i1 + 1 to i2
                        if C(j) > p1 + sl * (j - i1) + 0.000001
                            ok := false
                    if ok
                        hecho := true
                        array.push(tl, line.new(i1, p1, i2, p2, extend=extend.right, color=color.blue, width=2))
                        array.push(tb2, label.new(nn + 2, p1 + sl * (nn + 2 - i1), "Tend. bajista " + str.tostring(p1 + sl * (nn + 2 - i1), format.mintick), style=label.style_label_left, color=color.new(color.blue, 20), textcolor=color.white, size=size.small))
    // alcista
    m2 = array.size(plI) - 1
    if m2 >= 1
        j2 = array.get(plI, m2)
        q2 = array.get(plP, m2)
        bool hecho2 = false
        for m1 = 0 to m2 - 1
            if not hecho2
                j1 = array.get(plI, m1)
                q1 = array.get(plP, m1)
                if j1 >= minI and q1 < q2 and j2 > j1
                    sl2 = (q2 - q1) / (j2 - j1)
                    bool ok2 = true
                    for j = j1 + 1 to j2
                        if C(j) < q1 + sl2 * (j - j1) - 0.000001
                            ok2 := false
                    if ok2
                        hecho2 := true
                        array.push(tl, line.new(j1, q1, j2, q2, extend=extend.right, color=color.blue, width=2))
                        array.push(tb2, label.new(nn + 2, q1 + sl2 * (nn + 2 - j1), "Tend. alcista " + str.tostring(q1 + sl2 * (nn + 2 - j1), format.mintick), style=label.style_label_left, color=color.new(color.blue, 20), textcolor=color.white, size=size.small))
'''
open(f, "w", encoding="utf-8").write(s)
print("ok", len(s.splitlines()))

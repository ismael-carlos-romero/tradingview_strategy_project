import shutil
f = "meliora_fichas_cardona_v6.pine"
shutil.copy(f, f + ".bak_azul2")
s = open(f, encoding="utf-8").read()
mk = "\n// ===== LINEAS DE TENDENCIA AZULES (estilo manual de Ismael) ====="
assert s.count(mk) == 1
s = s.split(mk)[0]
a = 'azulBars = input.int(200, "Velas hacia atrás para buscar swings (1h)", minval=40, maxval=290)'
assert s.count(a) == 1
s = s.replace(a, 'azulBars = input.int(84, "Velas hacia atrás para el 1er ancla (84 = 12 sesiones de 1h)", minval=20, maxval=250)')
s += r'''
// ===== LINEAS DE TENDENCIA AZULES (estilo manual de Ismael) =====
// TECHO descendente: 1er ancla = swing high mas alto de las ultimas azulBars velas (posterior a la ultima ruptura); 2do ancla = ultimo swing high posterior mas bajo,
//   sin cierres sobre la linea por mas de 0,05 %. PISO ascendente: espejo con swing lows. Mechas para anclar, cierres para validar.
// La linea NO se mueve con cada vela: se prolonga; el 2do ancla solo avanza a un nuevo swing si la nueva linea sigue valida. Primero se evalua la ruptura contra la linea vigente.
// Ruptura confirmada al cierre: techo -> vela VERDE que cierra sobre la linea (CALL); piso -> vela ROJA que cierra bajo la linea (PUT). Tras la ruptura se descarta la linea
// (queda marcada) y la nueva solo usa pivotes posteriores. Sin estructura valida = no se dibuja nada. Solo informativo.
tolP = 0.0005
phv = ta.pivothigh(high, pivL, pivR)
plv = ta.pivotlow(low, pivL, pivR)
var array<int> phI = array.new<int>()
var array<float> phP = array.new<float>()
var array<int> plI = array.new<int>()
var array<float> plP = array.new<float>()
if not na(phv)
    array.push(phI, bar_index - pivR)
    array.push(phP, phv)
    if array.size(phI) > 80
        array.shift(phI)
        array.shift(phP)
if not na(plv)
    array.push(plI, bar_index - pivR)
    array.push(plP, plv)
    if array.size(plI) > 80
        array.shift(plI)
        array.shift(plP)
var array<float> stT = array.from(0.0, 0.0, 0.0, 0.0, 0.0, -1.0)
var array<float> stP = array.from(0.0, 0.0, 0.0, 0.0, 0.0, -1.0)
var array<int> evI = array.new<int>()
var array<string> evT = array.new<string>()
var array<float> evL = array.new<float>()
var array<float> evC = array.new<float>()

okLine(int s, int i1, float p1, float sl, int t) =>
    bool ok = true
    for j = i1 + 1 to t
        if s * (C(j) - (p1 + sl * (j - i1))) > tolP * C(j)
            ok := false
    ok

// st: 0 activa, 1 i1, 2 p1, 3 i2, 4 p2, 5 ultima ruptura
stepLinea(int s, array<float> st, array<int> pI, array<float> pP) =>
    int t = bar_index
    float cl = close
    bool act = array.get(st, 0) == 1.0
    if act
        int i1 = int(array.get(st, 1))
        float p1 = array.get(st, 2)
        int i2 = int(array.get(st, 3))
        float p2 = array.get(st, 4)
        float sl = (p2 - p1) / (i2 - i1)
        float v = p1 + sl * (t - i1)
        float vp = p1 + sl * (t - 1 - i1)
        if s * (cl - v) > tolP * cl
            bool prevOk = s * (C(t - 1) - vp) <= tolP * C(t - 1)
            bool colOk = s == 1 ? close > open : close < open
            if prevOk and colOk
                array.push(evI, t)
                array.push(evT, s == 1 ? "CALL" : "PUT")
                array.push(evL, v)
                array.push(evC, cl)
            array.set(st, 0, 0.0)
            array.set(st, 5, float(t))
            act := false
        else if t - i1 > 250
            array.set(st, 0, 0.0)
            act := false
        else
            int n2 = array.size(pI)
            bool done = false
            for k = n2 - 1 to 0
                if not done and n2 > 0
                    int j2 = array.get(pI, k)
                    float q2 = array.get(pP, k)
                    if j2 > i2 and s * q2 < s * p1
                        float sl2 = (q2 - p1) / (j2 - i1)
                        if okLine(s, i1, p1, sl2, t)
                            array.set(st, 3, float(j2))
                            array.set(st, 4, q2)
                            done := true
    if not act
        int n = array.size(pI)
        int brk = int(array.get(st, 5))
        array<bool> used = array.new<bool>(math.max(n, 1), false)
        bool built = false
        int rounds = 0
        while not built and rounds < 12 and n > 0
            rounds += 1
            int a = -1
            for k = 0 to n - 1
                if not array.get(used, k) and array.get(pI, k) > brk and array.get(pI, k) >= t - azulBars
                    if a < 0
                        a := k
                    else if s * array.get(pP, k) > s * array.get(pP, a)
                        a := k
            if a < 0
                rounds := 99
            else
                array.set(used, a, true)
                int ia = array.get(pI, a)
                float pa = array.get(pP, a)
                for k = n - 1 to 0
                    if not built
                        int ib = array.get(pI, k)
                        float pb = array.get(pP, k)
                        if ib > ia and s * pb < s * pa
                            float slb = (pb - pa) / (ib - ia)
                            if okLine(s, ia, pa, slb, t)
                                array.set(st, 0, 1.0)
                                array.set(st, 1, float(ia))
                                array.set(st, 2, pa)
                                array.set(st, 3, float(ib))
                                array.set(st, 4, pb)
                                built := true
    0

if verAzul and bar_index >= last_bar_index - 700 and bar_index > 5
    stepLinea(1, stT, phI, phP)
    stepLinea(-1, stP, plI, plP)

var array<line> tl = array.new<line>()
var array<label> tb2 = array.new<label>()
if barstate.islast and verAzul
    while array.size(tl) > 0
        line.delete(array.pop(tl))
    while array.size(tb2) > 0
        label.delete(array.pop(tb2))
    nn = bar_index
    left = hour <= 15 ? 15 - hour : 0
    proy = nn + left + 2
    if array.get(stT, 0) == 1.0
        i1 = int(array.get(stT, 1))
        p1 = array.get(stT, 2)
        i2 = int(array.get(stT, 3))
        p2 = array.get(stT, 4)
        sl = (p2 - p1) / (i2 - i1)
        array.push(tl, line.new(i1, p1, i2, p2, extend=extend.right, color=color.blue, width=2))
        array.push(tb2, label.new(proy, p1 + sl * (proy - i1), "Techo azul " + str.tostring(p1 + sl * (proy - i1), format.mintick), style=label.style_label_left, color=color.new(color.blue, 20), textcolor=color.white, size=size.small))
    if array.get(stP, 0) == 1.0
        j1 = int(array.get(stP, 1))
        q1 = array.get(stP, 2)
        j2 = int(array.get(stP, 3))
        q2 = array.get(stP, 4)
        sq = (q2 - q1) / (j2 - j1)
        array.push(tl, line.new(j1, q1, j2, q2, extend=extend.right, color=color.blue, width=2))
        array.push(tb2, label.new(proy, q1 + sq * (proy - j1), "Piso azul " + str.tostring(q1 + sq * (proy - j1), format.mintick), style=label.style_label_left, color=color.new(color.blue, 20), textcolor=color.white, size=size.small))
    for e = 0 to array.size(evI) - 1
        if array.size(evI) > 0
            int ie = array.get(evI, e)
            if ie >= nn - 250
                bool up = array.get(evT, e) == "CALL"
                array.push(tb2, label.new(ie, up ? low[nn - ie] : high[nn - ie], array.get(evT, e) + " azul " + str.tostring(array.get(evL, e), format.mintick), style=up ? label.style_label_up : label.style_label_down, color=up ? color.green : color.red, textcolor=color.white, size=size.small))
'''
open(f, "w", encoding="utf-8").write(s)
print("ok", len(s.splitlines()))

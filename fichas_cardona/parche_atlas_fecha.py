import re, shutil, sys
P = r"C:\Users\Ismael Romero\.gemini\antigravity\scratch\tradingview_strategy_project\index.html"
shutil.copy(P, P + ".bak_atlas_fecha")
t = open(P, encoding="utf-8", newline="").read()

NUEVO = r"""function estado(hb){
          function ny(s){var m=(s||'').match(/(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d)/);return m?new Date(+m[1],m[2]-1,+m[3],+m[4],+m[5]):null;}
          function hace(ms){var m=Math.max(0,Math.round(ms/60000));if(m<90)return m+' min';var h=Math.floor(m/60);if(h<48)return h+' h '+(m%60)+' min';return Math.floor(h/24)+' días';}
          var n=new Date(new Date().toLocaleString('en-US',{timeZone:'America/New_York'}));
          var g=ny(DATA.generado)||ny(DATA.asof),d=n.getDay(),mins=n.getHours()*60+n.getMinutes(),lab=d>=1&&d<=5;
          var abierto=lab&&mins>=570&&mins<=975,ok=false;
          if(g){if(abierto){ok=(n-g)<=90*60000;}else{var c=new Date(n);c.setHours(16,3,0,0);if(!(lab&&mins>=963)){do{c.setDate(c.getDate()-1);}while(c.getDay()==0||c.getDay()==6);}ok=g>=c;}}
          var box=Q('#av-st');box.innerHTML='';
          var b=el('b',g?(ok?'✔ DATOS ACTUALES':'⚠ DATOS DESACTUALIZADOS'):'Sin fecha de datos');
          b.style.cssText='padding:3px 10px;border-radius:6px;color:#fff;background:'+(ok?'#1f9d55':'#c0392b');
          box.appendChild(b);
          var s=' Última vela evaluada: '+DATA.asof+' (NY) · Generado: '+DATA.generado+(g?' (hace '+hace(n-g)+')':'')+' · Ahora en NY: '+n.toLocaleString('es-AR',{weekday:'short',hour:'2-digit',minute:'2-digit'})+(abierto?' (mercado abierto)':' (mercado cerrado)')+' · Mercado: '+DATA.mercado+' · Versión: '+DATA.version;
          var h=null;if(hb&&hb.ts){h=ny(hb.ts);}
          if(h){s+=' · Servicio Atlas: '+((n-h)<=400*60000?'activo (última corrida hace '+hace(n-h)+')':'SIN CORRER hace '+hace(n-h));}
          box.appendChild(document.createTextNode(s));
        }"""

pat = re.compile(r"function estado\(hb\)\{.*?Q\('#av-st'\)\.textContent=s;\s*\}", re.S)
if len(pat.findall(t)) != 1:
    sys.exit("estado no encontrado una sola vez")
t = pat.sub(lambda m: NUEVO, t, count=1)

old = ".catch(function(){Q('#av-st').textContent='Atlas todav"
if t.count(old) != 1:
    sys.exit("catch no encontrado")
t = t.replace(old, ".catch(function(e){if(DATA&&DATA.activos){console.error(e);return;}Q('#av-st').textContent='Atlas todav", 1)
open(P, "w", encoding="utf-8", newline="").write(t)
print("OK")

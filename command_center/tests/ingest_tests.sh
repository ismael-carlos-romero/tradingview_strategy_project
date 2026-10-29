#!/usr/bin/env bash
# Pruebas locales de public.cc_ingest_report contra un Postgres 16 desechable (no toca Supabase ni ningun dato real).
# Uso: command_center/tests/ingest_tests.sh   (requiere binarios de PostgreSQL 16; en Linux se ejecuta con runuser -u postgres)
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PGBIN=${PGBIN:-/usr/lib/postgresql/16/bin}
D=$(mktemp -d); chown postgres "$D"; chmod 755 "$D"
PORT=54329
as_pg() { runuser -u postgres -- "$@"; }
as_pg "$PGBIN/initdb" -D "$D/data" -A trust -U postgres >/dev/null
as_pg "$PGBIN/pg_ctl" -D "$D/data" -o "-p $PORT -k $D -c listen_addresses=''" -l "$D/log" -w start >/dev/null
trap 'as_pg "$PGBIN/pg_ctl" -D "$D/data" -m immediate stop >/dev/null 2>&1' EXIT
P() { "$PGBIN/psql" -X -q -A -t -h "$D" -p $PORT -U postgres -d cc "$@" 2>&1; }
"$PGBIN/psql" -X -q -h "$D" -p $PORT -U postgres -d postgres -c "create database cc" >/dev/null

n=0; f=0; : > "$D/outs.txt"
ck() { echo "$2" >> "$D/outs.txt"; if [[ "$2" == *"$3"* ]]; then n=$((n+1)); echo "PASS  $1"; else f=$((f+1)); echo "FAIL  $1 | esperaba '$3' | obtuve: $2"; fi; }
call() { P -v tok="$1" -v rep="$2" <<< "select public.cc_ingest_report(:'tok', :'rep'::jsonb);"; }
cnt() { P -c "select count(*) from public.cc_reports where report_key='$1'"; }
nrep() { P -c "select count(*) from public.cc_reports"; }
naud() { P -c "select count(*) from public.cc_audit_events"; }
pl() { printf '{"agent_id":"NOTICIAS","report_id":"%s","revision":%s,"format_version":"1.0","title":"Noticias y Fundamentos - corte de prueba","summary":"%s","findings":"detalle","cutoff_at":"2026-10-29T08:53:05-03:00","generated_at":"%s","status":"PARTIAL","coverage":{"expected":35,"reviewed":20,"unverified":15,"calendar_events":9},"sources":["https://www.federalreserve.gov/x"],"limits":["15 activos no verificados"]}' "$1" "${2:-1}" "${3:-resumen}" "${4:-2026-10-29T12:00:00Z}"; }

# ---- Preparacion
P -f "$HERE/tests/bootstrap_stub.sql" >/dev/null
P -f "$HERE/supabase_schema.sql" >/dev/null
P -c "insert into auth.users(id,email) values ('11111111-1111-1111-1111-111111111111','owner@test')" >/dev/null
P -f "$HERE/seed_agent_noticias.sql" >/dev/null
P -c "insert into public.cc_agents(id,owner_id,name,sector) values ('ATLAS','11111111-1111-1111-1111-111111111111','Atlas','x'),('FANTASMA','11111111-1111-1111-1111-111111111111','F','x')" >/dev/null
P -c "delete from public.cc_agents where id='FANTASMA'" >/dev/null
P -c "insert into auth.users(id,email) values ('22222222-2222-2222-2222-222222222222','otro@test')" >/dev/null
P -f "$HERE/supabase_ingest.sql" >/dev/null
rnd() { head -c 60 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 64; }
TOKA=$(rnd); TOKD=$(rnd); TOKE=$(rnd); TOKX=$(rnd); TOKR=$(rnd); TOKBAD=$(rnd); TOKLEAK=$(rnd)
mk() { P -c "insert into public.cc_ingest_tokens(owner_id,label,token_hash,allowed_agents,expires_at,revoked_at) select id,'$2',encode(extensions.digest('$1','sha256'),'hex'),$3,$4,$5 from auth.users where email='owner@test'" >/dev/null; }
mk "$TOKA" ok "array['NOTICIAS']" null null
mk "$TOKD" soloatlas "array['ATLAS']" null null
mk "$TOKE" fantasma "array['FANTASMA']" null null
mk "$TOKX" vencido "array['NOTICIAS']" "now() - interval '1 day'" null
mk "$TOKR" revocado "array['NOTICIAS']" null "now()"

echo "== 1. Token invalido / vencido / revocado"
ck "token desconocido" "$(call "$TOKBAD" "$(pl T1)")" "unauthorized"
ck "token corto" "$(call abc "$(pl T1)")" "unauthorized"
ck "token nulo" "$(P <<< "select public.cc_ingest_report(null, '{}'::jsonb);")" "unauthorized"
ck "token vencido" "$(call "$TOKX" "$(pl T1)")" "unauthorized"
ck "token revocado" "$(call "$TOKR" "$(pl T1)")" "unauthorized"
ck "sin reportes tras tokens malos" "$(nrep)" "0"
ck "sin auditoria tras tokens malos" "$(naud)" "0"

echo "== 2. Agente incorrecto"
ck "token solo ATLAS enviando NOTICIAS" "$(call "$TOKD" "$(pl T2)")" "agent not allowed"
ck "token NOTICIAS enviando ATLAS" "$(call "$TOKA" "$(pl T2 | sed 's/"NOTICIAS"/"ATLAS"/')")" "agent not allowed"
ck "agente autorizado pero no registrado" "$(call "$TOKE" "$(pl T2 | sed 's/"NOTICIAS"/"FANTASMA"/')")" "agent not registered"

echo "== 3. Reportes mal formados"
B=$(pl MALFORMADO_1)
ck "no es objeto" "$(call "$TOKA" '[1]')" "object expected"
ck "objeto vacio" "$(call "$TOKA" '{}')" "agent_id"
ck "campo desconocido (owner_id)" "$(call "$TOKA" "$(echo "$B" | sed 's/}$/,"owner_id":"x"}/')")" "unknown field"
ck "status invalido" "$(call "$TOKA" "$(echo "$B" | sed 's/"PARTIAL"/"DONE"/')")" "status"
ck "sin titulo" "$(call "$TOKA" "$(echo "$B" | sed 's/"title":"[^"]*",//')")" "title"
ck "revision 0" "$(call "$TOKA" "$(echo "$B" | sed 's/"revision":1/"revision":0/')")" "revision"
ck "fuente http (no https)" "$(call "$TOKA" "$(echo "$B" | sed 's#https://www#http://www#')")" "sources"
ck "cobertura con clave desconocida" "$(call "$TOKA" "$(echo "$B" | sed 's/"calendar_events"/"extra"/')")" "coverage"
ck "cobertura incoherente (revisados > esperados)" "$(call "$TOKA" "$(echo "$B" | sed 's/"reviewed":20/"reviewed":99/')")" "coverage inconsistent"
ck "fecha sin zona horaria" "$(call "$TOKA" "$(echo "$B" | sed 's/08:53:05-03:00/08:53:05/')")" "timestamp"
ck "fecha basura" "$(call "$TOKA" "$(echo "$B" | sed 's/2026-10-29T08:53:05-03:00/basura/')")" "timestamp"
ck "report_id con espacio" "$(call "$TOKA" "$(echo "$B" | sed 's/"MALFORMADO_1"/"a b"/')")" "report_id"
ck "resumen demasiado largo" "$(call "$TOKA" "$(pl MALFORMADO_1 1 "$(head -c 5000 /dev/zero | tr '\0' x)")")" "summary"
ck "ningun mal formado guardo nada" "$(nrep)/$(naud)" "0/0"

echo "== 4. Primer envio"
R1=$(call "$TOKA" "$(pl MELIORA_TEST_001)")
ck "primer envio crea" "$R1" '"created"'
ck "1 reporte" "$(cnt MELIORA_TEST_001)" "1"
ck "1 evento de auditoria" "$(P -c "select count(*) from public.cc_audit_events where details->>'report_key'='MELIORA_TEST_001'")" "1"
ck "estado PARTIAL y cobertura 15 no verificados" "$(P -c "select status||':'||(coverage->>'unverified') from public.cc_reports where report_key='MELIORA_TEST_001'")" "PARTIAL:15"
ck "auditoria registra token_id" "$(P -c "select details ? 'token_id' from public.cc_audit_events limit 1")" "t"
ck "last_activity del agente" "$(P -c "select last_activity is not null from public.cc_agents where id='NOTICIAS'")" "t"

echo "== 5. Reenvio identico"
ck "reenvio identico devuelve duplicate" "$(call "$TOKA" "$(pl MELIORA_TEST_001)")" '"duplicate"'
ck "reenvio con otro generated_at tambien duplicate" "$(call "$TOKA" "$(pl MELIORA_TEST_001 1 resumen 2030-01-01T00:00:00Z)")" '"duplicate"'
ck "sigue 1 reporte / 1 auditoria" "$(cnt MELIORA_TEST_001)/$(P -c "select count(*) from public.cc_audit_events where details->>'report_key'='MELIORA_TEST_001'")" "1/1"

echo "== 6. Mismo agente+report_id+revision con contenido distinto"
ck "conflicto rechazado" "$(call "$TOKA" "$(pl MELIORA_TEST_001 1 'resumen DISTINTO')")" "conflict"
ck "contenido original intacto" "$(P -c "select content from public.cc_reports where report_key='MELIORA_TEST_001'")" "resumen"
ck "sin cambios de conteo" "$(cnt MELIORA_TEST_001)/$(naud)" "1/1"
ck "nueva revision 2 se acepta" "$(call "$TOKA" "$(pl MELIORA_TEST_001 2 'resumen DISTINTO')")" '"created"'

echo "== 7. Concurrencia"
{ P -v tok="$TOKA" -v rep="$(pl CONC_1)" <<< "begin; select public.cc_ingest_report(:'tok', :'rep'::jsonb); select pg_sleep(2); commit;" > "$D/c1a"; } &
sleep 0.7; r=$(call "$TOKA" "$(pl CONC_1)"); wait
ck "A (transaccion abierta) crea" "$(cat "$D/c1a")" '"created"'
ck "B simultaneo identico -> duplicate" "$r" '"duplicate"'
ck "CONC_1: 1 reporte / 1 auditoria" "$(cnt CONC_1)/$(P -c "select count(*) from public.cc_audit_events where details->>'report_key'='CONC_1'")" "1/1"
{ P -v tok="$TOKA" -v rep="$(pl CONC_2 1 A)" <<< "begin; select public.cc_ingest_report(:'tok', :'rep'::jsonb); select pg_sleep(2); commit;" > "$D/c2a"; } &
sleep 0.7; r=$(call "$TOKA" "$(pl CONC_2 1 B)"); wait
ck "A crea (contenido A)" "$(cat "$D/c2a")" '"created"'
ck "B simultaneo con contenido distinto -> conflict" "$r" "conflict"
ck "CONC_2: queda 1 reporte con contenido A" "$(cnt CONC_2)/$(P -c "select content from public.cc_reports where report_key='CONC_2'" | head -1)" "1/A"
for i in $(seq 1 10); do call "$TOKA" "$(pl CONC_3)" > "$D/c3_$i" & done; wait
ck "10 envios paralelos identicos: exactamente 1 created" "$(cat "$D"/c3_* | grep -c '"created"')" "1"
ck "10 envios paralelos identicos: 9 duplicate" "$(cat "$D"/c3_* | grep -c '"duplicate"')" "9"
ck "CONC_3: 1 reporte / 1 auditoria" "$(cnt CONC_3)/$(P -c "select count(*) from public.cc_audit_events where details->>'report_key'='CONC_3'")" "1/1"
for i in 1 2 3 4; do call "$TOKA" "$(pl CONC_4 1 "V$i")" > "$D/c4_$i" & done; wait
ck "4 paralelos con contenido distinto: 1 created" "$(cat "$D"/c4_* | grep -c '"created"')" "1"
ck "4 paralelos con contenido distinto: 3 conflict" "$(cat "$D"/c4_* | grep -c 'conflict')" "3"

echo "== 8. Atomicidad reporte+auditoria"
P -c "create function public.t_boom() returns trigger language plpgsql as \$\$ begin raise exception 'boom'; end \$\$; create trigger t_boom before insert on public.cc_audit_events for each row execute function public.t_boom();" >/dev/null
A0=$(naud)
ck "falla la auditoria -> error" "$(call "$TOKA" "$(pl ATOMIC_1)")" "boom"
ck "y el reporte NO queda guardado" "$(cnt ATOMIC_1)" "0"
ck "auditoria sin cambios" "$(naud)" "$A0"
P -c "drop trigger t_boom on public.cc_audit_events" >/dev/null
ck "sin la falla, el mismo envio se guarda" "$(call "$TOKA" "$(pl ATOMIC_1)")" '"created"'
ck "ATOMIC_1: 1 reporte y su auditoria" "$(cnt ATOMIC_1)/$(P -c "select count(*) from public.cc_audit_events where details->>'report_key'='ATOMIC_1'")" "1/1"

echo "== 9. Permisos desde el navegador"
AS() { P -v tok="$TOKA" -v rep="$(pl "$3")" <<< "set role $1; $2"; }
ck "anon no lee cc_ingest_tokens" "$(AS anon 'select token_hash from public.cc_ingest_tokens;' X)" "permission denied"
ck "authenticated no lee cc_ingest_tokens" "$(AS authenticated 'select token_hash from public.cc_ingest_tokens;' X)" "permission denied"
ck "authenticated no inserta en cc_ingest_tokens" "$(AS authenticated "insert into public.cc_ingest_tokens(owner_id,label,token_hash,allowed_agents) values ('11111111-1111-1111-1111-111111111111','x',repeat('a',64),array['NOTICIAS']);" X)" "permission denied"
ck "authenticated no inserta reportes" "$(AS authenticated "insert into public.cc_reports(owner_id,agent_id,title,content) values ('11111111-1111-1111-1111-111111111111','NOTICIAS','t','c');" X)" "permission denied"
ck "anon no inserta reportes" "$(AS anon "insert into public.cc_reports(owner_id,agent_id,title,content) values ('11111111-1111-1111-1111-111111111111','NOTICIAS','t','c');" X)" "permission denied"
ck "authenticated no modifica reportes" "$(AS authenticated "update public.cc_reports set title='x';" X)" "permission denied"
ck "authenticated no borra auditoria" "$(AS authenticated "delete from public.cc_audit_events;" X)" "permission denied"
ck "anon no lee reportes" "$(AS anon 'select * from public.cc_reports;' X)" "permission denied"
ck "authenticated (logueado) NO puede ejecutar la funcion" "$(AS authenticated "select public.cc_ingest_report(:'tok', :'rep'::jsonb);" PERM_1)" "permission denied"
ck "anon con token valido SI puede (via clave publishable)" "$(AS anon "select public.cc_ingest_report(:'tok', :'rep'::jsonb);" PERM_2)" '"created"'
ck "anon con token invalido: unauthorized" "$(P -v tok="$TOKBAD" -v rep="$(pl PERM_3)" <<< "set role anon; select public.cc_ingest_report(:'tok', :'rep'::jsonb);")" "unauthorized"
ck "dueño ve sus reportes" "$(P <<< "set role authenticated; select set_config('request.jwt.claim.sub','11111111-1111-1111-1111-111111111111',false); select count(*)>0 from public.cc_reports;" | tail -1)" "t"
ck "otro usuario no ve reportes (RLS)" "$(P <<< "set role authenticated; select set_config('request.jwt.claim.sub','22222222-2222-2222-2222-222222222222',false); select count(*) from public.cc_reports;" | tail -1)" "0"
ck "service_role lee tokens (solo servidor)" "$(AS service_role 'select count(*)>0 from public.cc_ingest_tokens;' X | tail -1)" "t"
ck "funcion con search_path vacio y SECURITY DEFINER" "$(P -c "select prosecdef::text||':'||proconfig::text from pg_proc where proname='cc_ingest_report'")" "t:{search_path=\"\"}"

echo "== 10. El token no se filtra"
P <<EOF >/dev/null
select public.cc_ingest_report(\$1, '{}'::jsonb) \bind $TOKLEAK \g
EOF
ck "token invalido enviado por parametro no aparece en el log del servidor" "$(grep -c "$TOKLEAK" "$D/log")" "0"
DUMP=$("$PGBIN/pg_dump" -h "$D" -p $PORT -U postgres -d cc -a -t public.cc_audit_events -t public.cc_reports)
ck "token valido no aparece en auditoria/reportes" "$(grep -c "$TOKA" <<< "$DUMP")" "0"
ck "token no aparece en ningun mensaje de error devuelto" "$(grep -c -e "$TOKA" -e "$TOKBAD" -e "$TOKX" -e "$TOKR" "$D/outs.txt")" "0"

echo; echo "RESULTADO: $n correctas, $f fallidas"
[ "$f" -eq 0 ]

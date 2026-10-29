-- Command Center: ingesta segura de reportes (fase 1). NO EJECUTAR EN PRODUCCION hasta pasar las pruebas (tests/ingest_tests.sh).
-- Ejecutar en Supabase SQL Editor despues de supabase_schema.sql. No contiene secretos.
--
-- Modelo de seguridad (ver INGEST_ARCHITECTURE.md):
--  * Unico punto de escritura: public.cc_ingest_report(token, reporte). Se invoca por RPC con la clave publishable (rol anon).
--  * El token se guarda solo como hash SHA-256 en cc_ingest_tokens. Esa tabla no es legible ni escribible desde el navegador.
--  * La funcion es SECURITY DEFINER (corre como su duenio, postgres) con search_path vacio; todo va calificado.
--  * Valida: token activo, no vencido, no revocado; agente autorizado para ese token y registrado; campos permitidos.
--  * Reporte + auditoria se guardan en la misma transaccion (una sola funcion): o se guardan ambos o ninguno.
--  * Idempotencia: (owner, agente, report_id, revision). Mismo contenido -> 'duplicate'. Distinto contenido -> error 23505.

alter table public.cc_reports
  add column if not exists report_key text,
  add column if not exists revision int not null default 1,
  add column if not exists content_hash text,
  add column if not exists format_version text,
  add column if not exists cutoff_at timestamptz,
  add column if not exists generated_at timestamptz,
  add column if not exists status text,
  add column if not exists coverage jsonb not null default '{}'::jsonb,
  add column if not exists limits jsonb not null default '[]'::jsonb;
alter table public.cc_reports drop constraint if exists cc_reports_status_chk;
alter table public.cc_reports add constraint cc_reports_status_chk
  check (status is null or status in ('COMPLETE','PARTIAL','BLOCKED'));
create unique index if not exists cc_reports_idem
  on public.cc_reports(owner_id, agent_id, report_key, revision) where report_key is not null;

create table if not exists public.cc_ingest_tokens (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  label text not null,
  token_hash text not null unique check (token_hash ~ '^[0-9a-f]{64}$'),
  allowed_agents text[] not null check (cardinality(allowed_agents) > 0),
  expires_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);
alter table public.cc_ingest_tokens enable row level security;   -- sin politicas: nadie la lee desde la API
revoke all on public.cc_ingest_tokens from public, anon, authenticated;
grant all on public.cc_ingest_tokens to service_role;
-- Defensa extra: el navegador nunca escribe directo en estas tablas.
revoke insert, update, delete, truncate on public.cc_reports, public.cc_audit_events from public, anon, authenticated;

create or replace function public.cc_ingest_report(p_token text, p_report jsonb)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $fn$
declare
  c_fields constant text[] := array['agent_id','report_id','revision','format_version','title','summary',
                                    'findings','cutoff_at','generated_at','status','coverage','sources','limits'];
  c_cov    constant text[] := array['expected','reviewed','unverified','calendar_events'];
  t          public.cc_ingest_tokens%rowtype;
  v_existing public.cc_reports%rowtype;
  v_agent text; v_key text; v_rev int := 1; v_hash text; v_id uuid;
  v_cutoff timestamptz; v_generated timestamptz;
  k text; e jsonb;
begin
  -- 1. Autenticacion del token (mensaje generico; nunca se devuelve ni registra el token).
  if p_token is null or length(p_token) not between 32 and 200 then
    raise exception 'unauthorized' using errcode = '28000';
  end if;
  select * into t from public.cc_ingest_tokens
   where token_hash = pg_catalog.encode(extensions.digest(p_token, 'sha256'), 'hex')
     and revoked_at is null
     and (expires_at is null or expires_at > pg_catalog.now());
  if not found then
    raise exception 'unauthorized' using errcode = '28000';
  end if;

  -- 2. Forma del reporte: objeto, tamanio acotado, solo campos permitidos.
  if p_report is null or pg_catalog.jsonb_typeof(p_report) <> 'object' then
    raise exception 'invalid report: object expected' using errcode = '22023';
  end if;
  if length(p_report::text) > 200000 then
    raise exception 'invalid report: too large' using errcode = '22023';
  end if;
  for k in select pg_catalog.jsonb_object_keys(p_report) loop
    if not (k = any(c_fields)) then
      raise exception 'invalid report: unknown field %', left(k, 40) using errcode = '22023';
    end if;
  end loop;

  -- 3. Agente: autorizado para este token y registrado para el duenio del token.
  if pg_catalog.jsonb_typeof(p_report->'agent_id') is distinct from 'string' then
    raise exception 'invalid report: agent_id' using errcode = '22023';
  end if;
  v_agent := upper(p_report->>'agent_id');
  if not (v_agent = any(t.allowed_agents)) then
    raise exception 'agent not allowed' using errcode = '42501';
  end if;
  perform 1 from public.cc_agents where id = v_agent and owner_id = t.owner_id;
  if not found then
    raise exception 'agent not registered' using errcode = '23503';
  end if;

  -- 4. Campos.
  if pg_catalog.jsonb_typeof(p_report->'report_id') is distinct from 'string'
     or (p_report->>'report_id') !~ '^[A-Za-z0-9_.:-]{3,120}$' then
    raise exception 'invalid report: report_id' using errcode = '22023';
  end if;
  v_key := p_report->>'report_id';
  if p_report ? 'revision' then
    if pg_catalog.jsonb_typeof(p_report->'revision') is distinct from 'number'
       or (p_report->>'revision') !~ '^[1-9][0-9]{0,3}$' then
      raise exception 'invalid report: revision' using errcode = '22023';
    end if;
    v_rev := (p_report->>'revision')::int;
  end if;
  if pg_catalog.jsonb_typeof(p_report->'title') is distinct from 'string'
     or length(btrim(p_report->>'title')) not between 1 and 200 then
    raise exception 'invalid report: title' using errcode = '22023';
  end if;
  if pg_catalog.jsonb_typeof(p_report->'summary') is distinct from 'string'
     or length(btrim(p_report->>'summary')) not between 1 and 4000 then
    raise exception 'invalid report: summary' using errcode = '22023';
  end if;
  if p_report ? 'findings' and (pg_catalog.jsonb_typeof(p_report->'findings') is distinct from 'string'
     or length(p_report->>'findings') > 30000) then
    raise exception 'invalid report: findings' using errcode = '22023';
  end if;
  if p_report ? 'format_version' and (pg_catalog.jsonb_typeof(p_report->'format_version') is distinct from 'string'
     or length(p_report->>'format_version') > 20) then
    raise exception 'invalid report: format_version' using errcode = '22023';
  end if;
  if pg_catalog.jsonb_typeof(p_report->'status') is distinct from 'string'
     or (p_report->>'status') not in ('COMPLETE','PARTIAL','BLOCKED') then
    raise exception 'invalid report: status' using errcode = '22023';
  end if;
  -- Fechas ISO-8601 con zona horaria obligatoria.
  begin
    if p_report ? 'cutoff_at' then
      if (p_report->>'cutoff_at') !~ '(Z|[+-][0-9]{2}:?[0-9]{2})$' then raise exception 'x'; end if;
      v_cutoff := (p_report->>'cutoff_at')::timestamptz;
    end if;
    if p_report ? 'generated_at' then
      if (p_report->>'generated_at') !~ '(Z|[+-][0-9]{2}:?[0-9]{2})$' then raise exception 'x'; end if;
      v_generated := (p_report->>'generated_at')::timestamptz;
    end if;
  exception when others then
    raise exception 'invalid report: timestamp (ISO-8601 con zona horaria)' using errcode = '22023';
  end;
  if p_report ? 'coverage' then
    if pg_catalog.jsonb_typeof(p_report->'coverage') <> 'object' then
      raise exception 'invalid report: coverage' using errcode = '22023';
    end if;
    for k, e in select * from pg_catalog.jsonb_each(p_report->'coverage') loop
      if not (k = any(c_cov)) or pg_catalog.jsonb_typeof(e) <> 'number' or (e #>> '{}') !~ '^[0-9]{1,6}$' then
        raise exception 'invalid report: coverage.%', left(k, 40) using errcode = '22023';
      end if;
    end loop;
    if (p_report->'coverage' ? 'expected') and (
         coalesce((p_report->'coverage'->>'reviewed')::int, 0) > (p_report->'coverage'->>'expected')::int
      or coalesce((p_report->'coverage'->>'unverified')::int, 0) > (p_report->'coverage'->>'expected')::int) then
      raise exception 'invalid report: coverage inconsistent' using errcode = '22023';
    end if;
  end if;
  if p_report ? 'sources' then
    if pg_catalog.jsonb_typeof(p_report->'sources') <> 'array' or pg_catalog.jsonb_array_length(p_report->'sources') > 100 then
      raise exception 'invalid report: sources' using errcode = '22023';
    end if;
    for e in select * from pg_catalog.jsonb_array_elements(p_report->'sources') loop
      if pg_catalog.jsonb_typeof(e) <> 'string' or (e #>> '{}') !~ '^https://[^[:space:]]+$' or length(e #>> '{}') > 500 then
        raise exception 'invalid report: sources (solo https)' using errcode = '22023';
      end if;
    end loop;
  end if;
  if p_report ? 'limits' then
    if pg_catalog.jsonb_typeof(p_report->'limits') <> 'array' or pg_catalog.jsonb_array_length(p_report->'limits') > 50 then
      raise exception 'invalid report: limits' using errcode = '22023';
    end if;
    for e in select * from pg_catalog.jsonb_array_elements(p_report->'limits') loop
      if pg_catalog.jsonb_typeof(e) <> 'string' or length(e #>> '{}') > 1000 then
        raise exception 'invalid report: limits' using errcode = '22023';
      end if;
    end loop;
  end if;

  -- 5. Idempotencia. El hash excluye generated_at (un reenvio identico no debe diferir por la hora de generacion).
  v_hash := pg_catalog.encode(extensions.digest(pg_catalog.convert_to((p_report - 'generated_at')::text, 'utf8'), 'sha256'), 'hex');

  insert into public.cc_reports
    (owner_id, agent_id, title, content, source_refs, report_key, revision, content_hash,
     format_version, cutoff_at, generated_at, status, coverage, limits)
  values
    (t.owner_id, v_agent, p_report->>'title',
     (p_report->>'summary') || coalesce(E'\n\n' || (p_report->>'findings'), ''),
     coalesce(p_report->'sources', '[]'::jsonb), v_key, v_rev, v_hash,
     p_report->>'format_version', v_cutoff, v_generated, p_report->>'status',
     coalesce(p_report->'coverage', '{}'::jsonb), coalesce(p_report->'limits', '[]'::jsonb))
  on conflict (owner_id, agent_id, report_key, revision) where report_key is not null do nothing
  returning id into v_id;

  if v_id is null then
    select * into v_existing from public.cc_reports
     where owner_id = t.owner_id and agent_id = v_agent and report_key = v_key and revision = v_rev;
    if v_existing.content_hash = v_hash then
      return pg_catalog.jsonb_build_object('status', 'duplicate', 'id', v_existing.id);
    end if;
    raise exception 'conflict: same agent, report_id and revision with different content' using errcode = '23505';
  end if;

  -- 6. Auditoria en la misma transaccion. Sin token ni contenido del reporte: solo el id del token.
  insert into public.cc_audit_events (owner_id, actor, event_type, entity_type, entity_id, details)
  values (t.owner_id, 'ingest:' || v_agent, 'REPORT_INGESTED', 'cc_reports', v_id::text,
          pg_catalog.jsonb_build_object('report_key', v_key, 'revision', v_rev, 'status', p_report->>'status',
                                        'token_id', t.id));

  update public.cc_agents set last_activity = pg_catalog.now() where id = v_agent and owner_id = t.owner_id;

  return pg_catalog.jsonb_build_object('status', 'created', 'id', v_id);
end;
$fn$;

-- Solo la clave publishable (rol anon) y service_role pueden invocarla; los usuarios logueados del navegador, no.
revoke all on function public.cc_ingest_report(text, jsonb) from public, anon, authenticated;
grant execute on function public.cc_ingest_report(text, jsonb) to anon, service_role;

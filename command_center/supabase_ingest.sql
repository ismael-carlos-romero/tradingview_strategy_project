-- Command Center: ingesta segura de reportes (fase 1). Ejecutar en Supabase SQL Editor despues de supabase_schema.sql.
-- Sin secretos: los tokens de ingesta se guardan solo como hash en cc_ingest_tokens.
-- Un unico punto de escritura: la funcion cc_ingest_report. No usa service_role ni claves privadas en el navegador.

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
alter table public.cc_reports add constraint cc_reports_status_chk check (status is null or status in ('COMPLETE','PARTIAL','BLOCKED'));
create unique index if not exists cc_reports_idem on public.cc_reports(owner_id, agent_id, report_key, revision) where report_key is not null;

create table if not exists public.cc_ingest_tokens (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  label text not null,
  token_hash text not null unique,
  allowed_agents text[] not null,
  active boolean not null default true,
  created_at timestamptz not null default now()
);
alter table public.cc_ingest_tokens enable row level security;
revoke all on public.cc_ingest_tokens from anon, authenticated;
grant all on public.cc_ingest_tokens to service_role;
-- Sin politicas: nadie puede leer ni escribir esta tabla desde el navegador.

create or replace function public.cc_ingest_report(p_token text, p_report jsonb)
returns jsonb
language plpgsql
security definer
set search_path = public, extensions
as $fn$
declare
  t public.cc_ingest_tokens;
  v_existing public.cc_reports;
  v_agent text;
  v_key text;
  v_rev int;
  v_hash text;
  v_id uuid;
begin
  if p_token is null or length(p_token) < 32 then
    raise exception 'unauthorized' using errcode = '28000';
  end if;
  select * into t from public.cc_ingest_tokens
    where token_hash = encode(digest(p_token, 'sha256'), 'hex') and active;
  if not found then
    raise exception 'unauthorized' using errcode = '28000';
  end if;

  v_agent := upper(p_report->>'agent_id');
  v_key := p_report->>'report_id';
  v_rev := coalesce((p_report->>'revision')::int, 1);

  if v_agent is null or not (v_agent = any(t.allowed_agents)) then
    raise exception 'agent not allowed' using errcode = '42501';
  end if;
  if v_key is null or length(v_key) not between 3 and 120 then
    raise exception 'invalid report_id';
  end if;
  if coalesce(p_report->>'title', '') = '' or length(p_report->>'title') > 200 then
    raise exception 'invalid title';
  end if;
  if coalesce(p_report->>'summary', '') = '' or length(p_report->>'summary') > 20000 then
    raise exception 'invalid summary';
  end if;
  if coalesce(p_report->>'status', '') not in ('COMPLETE','PARTIAL','BLOCKED') then
    raise exception 'invalid status';
  end if;
  if jsonb_typeof(coalesce(p_report->'sources', '[]'::jsonb)) <> 'array'
     or jsonb_array_length(coalesce(p_report->'sources', '[]'::jsonb)) > 100 then
    raise exception 'invalid sources';
  end if;
  if jsonb_typeof(coalesce(p_report->'limits', '[]'::jsonb)) <> 'array' then
    raise exception 'invalid limits';
  end if;
  if jsonb_typeof(coalesce(p_report->'coverage', '{}'::jsonb)) <> 'object' then
    raise exception 'invalid coverage';
  end if;

  v_hash := encode(digest(convert_to(p_report::text, 'utf8'), 'sha256'), 'hex');

  select * into v_existing from public.cc_reports
    where owner_id = t.owner_id and agent_id = v_agent and report_key = v_key and revision = v_rev;
  if found then
    if v_existing.content_hash = v_hash then
      return jsonb_build_object('status', 'duplicate', 'id', v_existing.id);
    end if;
    raise exception 'conflict: same report_id and revision with different content' using errcode = '23505';
  end if;

  insert into public.cc_reports
    (owner_id, agent_id, title, content, source_refs, report_key, revision, content_hash,
     format_version, cutoff_at, generated_at, status, coverage, limits)
  values
    (t.owner_id, v_agent, p_report->>'title',
     (p_report->>'summary') || coalesce(E'\n\n' || (p_report->>'findings'), ''),
     coalesce(p_report->'sources', '[]'::jsonb), v_key, v_rev, v_hash,
     p_report->>'format_version',
     nullif(p_report->>'cutoff_at', '')::timestamptz,
     nullif(p_report->>'generated_at', '')::timestamptz,
     p_report->>'status',
     coalesce(p_report->'coverage', '{}'::jsonb),
     coalesce(p_report->'limits', '[]'::jsonb))
  returning id into v_id;

  insert into public.cc_audit_events (owner_id, actor, event_type, entity_type, entity_id, details)
  values (t.owner_id, 'ingest:' || v_agent, 'REPORT_INGESTED', 'cc_reports', v_id::text,
          jsonb_build_object('report_key', v_key, 'revision', v_rev, 'status', p_report->>'status', 'token_label', t.label));

  update public.cc_agents set last_activity = now() where id = v_agent and owner_id = t.owner_id;

  return jsonb_build_object('status', 'created', 'id', v_id);
end;
$fn$;

revoke all on function public.cc_ingest_report(text, jsonb) from public;
grant execute on function public.cc_ingest_report(text, jsonb) to anon, authenticated, service_role;

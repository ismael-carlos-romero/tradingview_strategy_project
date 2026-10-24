-- Meliora Command Center MVP — ejecutar en Supabase SQL Editor.
-- No ejecutar con datos de trading ni claves privadas en GitHub.
create extension if not exists pgcrypto;
create schema if not exists command_center;
grant usage on schema command_center to authenticated, service_role;
-- Para PostgREST configurar "Exposed schemas": public (usamos public para MVP).
create table if not exists public.cc_agents (
 id text primary key, owner_id uuid not null references auth.users(id) on delete cascade,
 name text not null, sector text not null, description text not null default '',
 status text not null default 'DESIGNED' check (status in ('DESIGNED','CONFIGURED','CONNECTED','RUNNING','ERROR','OFFLINE')),
 last_activity timestamptz, created_at timestamptz not null default now()
);
create table if not exists public.cc_tasks (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
 agent_id text, title text not null, status text not null default 'PENDING'
 check (status in ('PENDING','IN_PROGRESS','BLOCKED','DONE','CANCELLED')),
 priority text not null default 'NORMAL' check (priority in ('LOW','NORMAL','HIGH','CRITICAL')),
 created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 constraint cc_tasks_agent_fk foreign key (agent_id) references public.cc_agents(id)
);
create table if not exists public.cc_reports (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
 agent_id text references public.cc_agents(id), task_id uuid references public.cc_tasks(id),
 title text not null, content text not null, source_refs jsonb not null default '[]'::jsonb,
 created_at timestamptz not null default now()
);
create table if not exists public.cc_messages (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
 sender text not null, recipient text not null, body text not null,
 created_at timestamptz not null default now()
);
create table if not exists public.cc_commands (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
 origin text not null, destination text not null, action text not null,
 payload jsonb not null default '{}'::jsonb, status text not null default 'PENDING'
 check (status in ('PENDING','CLAIMED','DONE','FAILED','REJECTED')),
 result jsonb, created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 -- MVP: no ejecutar comandos automáticamente. Todo consumidor debe validar permisos y tipos permitidos.
 constraint cc_commands_action_safe check (action in ('REQUEST_REPORT','REQUEST_REVIEW','REQUEST_STATUS'))
);
create table if not exists public.cc_bot_snapshots (
 id uuid primary key default gen_random_uuid(), owner_id uuid not null references auth.users(id) on delete cascade,
 kind text not null check (kind in ('HEALTH','POSITIONS','TRADES','PNL','RISK')),
 environment text not null check (environment in ('SIM','PAPER','REAL')),
 payload jsonb not null default '{}'::jsonb, captured_at timestamptz not null,
 created_at timestamptz not null default now()
);
create table if not exists public.cc_audit_events (
 id bigint generated always as identity primary key, owner_id uuid not null references auth.users(id) on delete cascade,
 actor text not null, event_type text not null, entity_type text not null, entity_id text,
 details jsonb not null default '{}'::jsonb, created_at timestamptz not null default now()
);
-- No permitir escrituras anónimas. Tablas con RLS habilitada incluso para futuras.
do $$ declare t text; begin
 foreach t in array array['cc_agents','cc_tasks','cc_reports','cc_messages','cc_commands','cc_bot_snapshots','cc_audit_events'] loop
  execute format('alter table public.%I enable row level security', t);
  execute format('revoke all on public.%I from anon', t);
  execute format('grant select on public.%I to authenticated', t);
  execute format('grant all on public.%I to service_role', t);
  execute format('drop policy if exists cc_owner_read on public.%I',t);
  execute format('create policy cc_owner_read on public.%I for select to authenticated using (owner_id = (select auth.uid()))',t);
 end loop;
end $$;
-- MVP read-only: ningún usuario del navegador puede insertar/modificar/borrar.
-- Futuras escrituras: crear RPC/Edge Functions con validación de auth, allowlist y auditoría.
create index if not exists cc_tasks_owner_created on public.cc_tasks(owner_id,created_at desc);
create index if not exists cc_reports_owner_created on public.cc_reports(owner_id,created_at desc);
create index if not exists cc_snapshots_owner_time on public.cc_bot_snapshots(owner_id,captured_at desc);
create index if not exists cc_commands_owner_created on public.cc_commands(owner_id,created_at desc);
-- Importante: la service_role omite RLS. Validar owner_id explícitamente en el backend.
-- Nunca enviar service_role al navegador ni exponer endpoints que la usen sin autenticación.

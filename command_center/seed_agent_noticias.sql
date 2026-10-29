-- PROPUESTA de incorporacion explicita del agente "Noticias y Fundamentos" al catalogo. No ejecutar sin aprobacion.
-- Motivo: el catalogo actual (seed_agents.sql) no tiene un agente con ese rol exacto. ATLAS figura alli como
-- "Inteligencia de mercado y fundamentos", pero segun el equipo en ChatGPT Atlas hace analisis tecnico pre/post-market
-- y las noticias las hace un agente aparte. SONAR es el radar de oportunidades y NO se reutiliza.
insert into public.cc_agents (id, owner_id, name, sector, description, status)
select 'NOTICIAS', (select id from auth.users limit 1), 'Noticias y Fundamentos',
       'Noticias, earnings y contexto de los 35 activos',
       'Informe diario (~08:00 AR): noticias por activo, calendario de eventos y cobertura declarada. Parcial si hay activos no verificados.',
       'DESIGNED'
where (select count(*) from auth.users) = 1
on conflict (id) do nothing;

-- Alta del token (el hash lo imprime prepararToken() del Apps Script; el token nunca sale de Apps Script).
-- Reemplazar <HASH_64_HEX>. Vence a los 90 dias; revocar con: update public.cc_ingest_tokens set revoked_at = now() where label = 'apps-script-noticias';
-- insert into public.cc_ingest_tokens (owner_id, label, token_hash, allowed_agents, expires_at)
-- select id, 'apps-script-noticias', '<HASH_64_HEX>', array['NOTICIAS'], now() + interval '90 days'
-- from auth.users where (select count(*) from auth.users) = 1;

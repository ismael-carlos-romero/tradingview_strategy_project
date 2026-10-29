-- Carga inicial de agentes del Command Center. Ejecutar en Supabase SQL Editor despues de supabase_schema.sql.
-- Sin secretos. Solo inserta si existe exactamente un usuario en auth.users (el de Ismael); si no, no hace nada.
insert into public.cc_agents (id, owner_id, name, sector, description, status)
select v.id, u.id, v.name, v.sector, v.descr, 'DESIGNED'
from auth.users u
cross join (values
  ('JARVIS', E'Jarvis', E'Director general coordinador', E'Interfaz entre Ismael y los agentes; coordina, integra y sintetiza resultados.'),
  ('ATLAS', E'Atlas', E'Inteligencia de mercado y fundamentos', E'Noticias, earnings, calendario y eventos macro.'),
  ('VECTOR', E'Vector', E'An\u00e1lisis t\u00e9cnico y estrategias', E'Gr\u00e1ficos, estrategias Cardona, soportes y resistencias.'),
  ('SONAR', E'Sonar', E'Vigilancia y seguimiento de oportunidades', E'Monitoreo de los 35 activos y detecci\u00f3n de se\u00f1ales.'),
  ('GUARDIAN', E'Guardi\u00e1n', E'Protecci\u00f3n de capital y ejecuci\u00f3n', E'Reglas de riesgo, stop loss y control de exposici\u00f3n diaria.'),
  ('ARGOS', E'Argos', E'Auditor\u00eda, riesgo y rendimiento', E'Concilia compras y ventas, analiza m\u00e9tricas y detecta inconsistencias.'),
  ('PRISMA', E'Prisma', E'Visualizaci\u00f3n, reportes y comunicaci\u00f3n', E'Dashboards, informes y presentaciones.'),
  ('NEXUS', E'Nexus', E'Desarrollo web, apps y arquitectura', E'Portales, APIs, bases de datos e infraestructura.'),
  ('ORION', E'Orion', E'Investigaci\u00f3n, documentaci\u00f3n y conocimiento', E'Documentaci\u00f3n del proyecto, libro y manual.'),
  ('CRONOS', E'Cronos', E'Capturas, archivo y gesti\u00f3n de contenido', E'Captura de gr\u00e1ficos, archivo de se\u00f1ales y operaciones.'),
  ('LUMEN', E'Lumen', E'S\u00edntesis, redacci\u00f3n y publicaciones', E'Redacci\u00f3n y publicaci\u00f3n de textos y manuales.')
) as v(id, name, sector, descr)
where (select count(*) from auth.users) = 1
on conflict (id) do nothing;

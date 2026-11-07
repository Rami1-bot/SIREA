-- ============================================================
-- 55 · Seguridad por filas (RLS) en TODAS las tablas   (SIREA 3.5)
-- ============================================================
-- Qué resuelve: las tablas base del sistema (administradores, envios,
-- configuracion, logs, credenciales_red, …) se crearon sin RLS y Supabase
-- las marca como «UNRESTRICTED». Con la clave PÚBLICA del proyecto (anon),
-- cualquiera que la conociera podría leerlas o modificarlas por la API.
--
-- Qué hace:
--   1. Activa RLS en todas las tablas del esquema public que no la tengan.
--   2. Quita todos los privilegios a los roles públicos (anon, authenticated).
--   3. Deja todo a service_role (la clave de servidor que usa SIREA; en Supabase
--      ese rol salta RLS, así que la aplicación sigue funcionando igual).
--   4. Crea la función sirea_estado_rls(), de solo lectura, que usan
--      verificar_despliegue.py y la pantalla «Salud del sistema».
--
-- Requisito: SUPABASE_KEY debe ser la clave de servidor (service_role o
-- sb_secret_…), como ya indica la plantilla. Con la clave pública, después de
-- este script la aplicación dejará de ver los datos (y «Salud del sistema» lo avisa).
--
-- No borra ni cambia datos. Se puede ejecutar varias veces.
-- ============================================================

do $$
declare
  r record;
begin
  for r in
    select c.relname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind in ('r', 'p')
  loop
    execute format('alter table public.%I enable row level security', r.relname);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke all on public.%I from anon', r.relname);
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
      execute format('revoke all on public.%I from authenticated', r.relname);
    end if;
  end loop;
end $$;

-- Secuencias: tampoco para los roles públicos.
do $$
declare
  r record;
begin
  for r in
    select c.relname
      from pg_class c
      join pg_namespace n on n.oid = c.relnamespace
     where n.nspname = 'public' and c.relkind = 'S'
  loop
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke all on sequence public.%I from anon', r.relname);
    end if;
    if exists (select 1 from pg_roles where rolname = 'authenticated') then
      execute format('revoke all on sequence public.%I from authenticated', r.relname);
    end if;
  end loop;
end $$;

-- Las tablas que se creen después nacen sin privilegios para los roles públicos.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    alter default privileges in schema public revoke all on tables from anon;
    alter default privileges in schema public revoke all on sequences from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    alter default privileges in schema public revoke all on tables from authenticated;
    alter default privileges in schema public revoke all on sequences from authenticated;
  end if;
end $$;

-- Estado de RLS por tabla (solo lectura). Solo la puede ejecutar la clave de servidor.
create or replace function public.sirea_estado_rls()
returns table (tabla text, rls boolean)
language sql
stable
security definer
set search_path = public, pg_catalog
as $$
  select c.relname::text, c.relrowsecurity
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
   where n.nspname = 'public' and c.relkind in ('r', 'p')
   order by 1;
$$;

revoke all on function public.sirea_estado_rls() from public;
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on function public.sirea_estado_rls() from anon;
  end if;
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    revoke all on function public.sirea_estado_rls() from authenticated;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function public.sirea_estado_rls() to service_role;
  end if;
end $$;

-- Comprobación: ninguna fila debe decir «SIN RLS».
select tabla, case when rls then 'OK' else 'SIN RLS' end as estado
  from public.sirea_estado_rls();

-- Fin de 55_rls_tablas_base.sql

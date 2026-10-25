-- ============================================================
-- 00_reparar_permisos_service_role.sql
-- Arregla el error 42501 "permission denied for table ..." con la pista
-- "GRANT SELECT ON public.<tabla> TO service_role": la clave de servidor
-- (service_role) no tiene privilegios sobre las tablas base del proyecto.
-- Ninguno de los scripts 09-13 quita esos privilegios; esto ocurre cuando
-- las tablas se crearon con otro usuario/herramienta o se tocaron los
-- privilegios del esquema. Es seguro repetirlo.
-- Ejecutar en el SQL Editor de Supabase ANTES que los demás scripts.
-- ============================================================

grant usage on schema public to service_role;
grant all privileges on all tables    in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;
grant all privileges on all functions in schema public to service_role;

-- Que las tablas que se creen después también queden accesibles.
alter default privileges in schema public grant all on tables    to service_role;
alter default privileges in schema public grant all on sequences to service_role;
alter default privileges in schema public grant all on functions to service_role;

-- Se restaura la regla de SIRE v6: la auditoría encadenada solo se lee y se
-- inserta (si la tabla todavía no existe, estas dos líneas se ignoran al
-- ejecutar después el script 11, que las vuelve a aplicar).
do $$
begin
  if to_regclass('public.auditoria_acciones') is not null then
    revoke all on public.auditoria_acciones from service_role;
    grant select, insert on public.auditoria_acciones to service_role;
  end if;
end $$;

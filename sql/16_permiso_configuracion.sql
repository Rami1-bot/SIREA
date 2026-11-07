-- ============================================================
-- 16 · Permiso «CONFIGURACION» (v7.5)
-- ============================================================
-- Desde la v7.5 cambiar fechas, años, centros excluidos y carpetas de
-- Drive exige este permiso, que reparte ÚNICAMENTE el SUPER_ADMIN
-- principal (Permisos → «Cambiar la configuración»). Cada cambio pide un
-- motivo y queda en la auditoría (con el valor anterior y el nuevo).
--
-- Lo único que hace este script es permitir el valor nuevo en la columna
-- `permiso` de la tabla permisos_operaciones. No toca datos.
-- Se puede ejecutar varias veces sin problema.
-- Si NO lo ejecuta, el SUPER_ADMIN principal igual puede cambiar la
-- configuración; solo no podrá delegar este permiso en otras personas.
-- ============================================================

do $$
declare r record;
begin
  -- Quita la restricción anterior de la columna `permiso` (cualquiera que sea su nombre).
  for r in
    select conname
      from pg_constraint
     where conrelid = 'public.permisos_operaciones'::regclass
       and contype = 'c'
       and pg_get_constraintdef(oid) ilike '%DESCARGA_MASIVA%'
  loop
    execute format('alter table public.permisos_operaciones drop constraint %I', r.conname);
  end loop;

  alter table public.permisos_operaciones
    add constraint permisos_operaciones_permiso_check
    check (permiso in ('DESCARGA_MASIVA','RETIRO_REPOSITORIO','RESPALDO_MANUAL','VER_AUDITORIA','CONFIGURACION'));
end $$;

-- Fin de 16_permiso_configuracion.sql

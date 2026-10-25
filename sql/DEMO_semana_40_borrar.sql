-- ============================================================================
-- SIREA 3.2 · BORRAR LOS DATOS SINTÉTICOS Y VOLVER A LA SEMANA ANTERIOR (base DEMO)
-- ============================================================================
-- Borra los envíos «DEMO-SIM-…» y devuelve la
-- semana activa y la fecha de corte que había antes de DEMO_semana_40_datos_sinteticos.sql.
-- Las propuestas, informes y registros de IA que usted haya generado al probar NO se
-- borran aquí (son evidencia); para limpiar todo antes de producción use
-- 99_limpieza_previa_a_produccion.sql.
-- ============================================================================

do $$
declare
  v_semana text;
  v_corte  text;
  n_env    int;
  n_logs   int;
begin
  delete from public.envios where codigo_seguimiento like 'DEMO-SIM-%';
  get diagnostics n_env = row_count;
  -- Los registros «DEMO-SIM» de la tabla logs se quedan: su política de auditoría no deja borrar
  -- nada con menos de 90 días. Son recordatorios simulados de semanas pasadas y no afectan la semana actual.
  select count(*) into n_logs from public.logs where usuario = 'DEMO-SIM';
  select valor into v_semana from public.configuracion where clave = 'demo_sim_semana_activa_anterior';
  select valor into v_corte  from public.configuracion where clave = 'demo_sim_fecha_corte_anterior';
  if coalesce(v_semana, '') <> '' then
    update public.configuracion set valor = v_semana where clave = 'semana_activa';
  end if;
  if coalesce(v_corte, '') <> '' then
    update public.configuracion set valor = v_corte where clave = 'fecha_corte';
  end if;
  delete from public.configuracion where clave in ('demo_sim_semana_activa_anterior', 'demo_sim_fecha_corte_anterior');
  raise notice 'Borrados % envíos sintéticos (% registros DEMO-SIM quedan en logs). Semana activa: % · corte: %',
    n_env, n_logs, coalesce(nullif(v_semana, ''), '(sin cambio)'), coalesce(nullif(v_corte, ''), '(sin cambio)');
end $$;

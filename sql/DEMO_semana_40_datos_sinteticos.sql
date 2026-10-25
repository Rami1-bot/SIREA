-- ============================================================================
-- SIREA 3.2 · DATOS SINTÉTICOS PARA PROBAR LA SEMANA 40  (SOLO BASE DEMO)
-- ============================================================================
-- Qué hace (con las redes y centros que YA tiene su base):
--   1. Borra lo sintético de una corrida anterior (es seguro repetirlo).
--   2. Crea el historial de las semanas 30 a 39 con comportamientos distintos:
--        · algunas redes suelen enviar la Emergencia DESPUÉS del corte y reciben
--          recordatorio antes de enviar,
--        · una viene mejorando, otra empeorando, el resto envía a tiempo.
--   3. Crea la SEMANA 40 a medio camino, para ver todos los casos a la vez:
--        · redes completas,
--        · redes a las que les falta la Emergencia (o la Hospitalización) de un hospital,
--        · redes a las que les falta la mitad de sus centros,
--        · una red que todavía no envió nada.
--   4. Deja la semana 40 como SEMANA ACTIVA con el corte en 2 días (para ver los
--      avisos preventivos). Guarda la semana y el corte que usted tenía, para
--      volver atrás con DEMO_semana_40_borrar.sql.
--
-- Todo queda MARCADO: código «DEMO-SIM-…», observación «[DEMO SIMULADO]», correos en
-- example.org (dominio reservado: si aprueba un recordatorio, no le llega a nadie real)
-- y registros del historial con usuario «DEMO-SIM» (recordatorios simulados de semanas pasadas; la
-- tabla logs no deja borrar lo que tiene menos de 90 días, así que esos quedan, marcados).
--
-- Cómo usarlo: Supabase (proyecto DEMO) → SQL Editor → pegar todo → Run.
-- Antes: haber corrido ACTUALIZAR_TODO_SIREA_3_2.sql. Después: reiniciar la app
-- (o esperar un minuto) para que tome la semana activa nueva.
-- NUNCA en la base de producción.
-- ============================================================================

-- Función auxiliar (se borra al final): inserta un envío usando solo las columnas que existen.
create or replace function public._demo_sim_insertar(p_cols text, p_red text, p_correo text, p_anio int, p_semana int,
                                                     p_archivos jsonb, p_tarde boolean, p_fecha timestamptz, p_tipos jsonb)
returns void language plpgsql as $f$
declare
  v_obj jsonb;
begin
  v_obj := jsonb_build_object(
    'nombre_usuario', 'Responsable', 'apellido_usuario', 'Demo', 'correo_usuario', p_correo, 'red', p_red,
    -- como lo guarda el formulario de envío: «CODIGO NOMBRE»
    'centros', (select jsonb_agg(distinct (x->>'codigo') || ' ' || (x->>'centro')) from jsonb_array_elements(p_archivos) x),
    'semana', p_semana, 'anio', p_anio,
    'tipo_reporte', (select jsonb_agg(distinct p_tipos->>(x->>'tipo')) from jsonb_array_elements(p_archivos) x),
    'ruta_zip', 'DEMO-SIM/sin-archivo', 'drive_file_id', 'DEMO-SIM-sin-archivo',
    'cantidad_archivos', jsonb_array_length(p_archivos),
    'estado', case when p_tarde then 'ATRASADO' else 'APROBADO' end,
    'observacion', '[DEMO SIMULADO] datos sintéticos para probar SIREA 3.2',
    'es_atrasado', p_tarde, 'semana_activa_envio', p_semana + case when p_tarde then 1 else 0 end,
    'dias_atraso_envio', case when p_tarde then 3 else 0 end,
    'codigo_seguimiento', format('DEMO-SIM-%s%s-%s', p_anio, lpad(p_semana::text, 2, '0'),
                                 substr(md5(random()::text || clock_timestamp()::text), 1, 8)),
    'fecha_envio', p_fecha, 'fecha_actualizacion', p_fecha,
    'detalle_archivos', (select jsonb_agg(jsonb_build_object(
        'archivo', format('p%s%s%ssim.%s', x->>'tipo', lpad(p_semana::text, 2, '0'), lpad((p_anio % 100)::text, 2, '0'), x->>'codigo'),
        'codigo', x->>'codigo', 'centro', x->>'centro', 'tipo', x->>'tipo', 'semana', p_semana, 'anio', p_anio))
      from jsonb_array_elements(p_archivos) x));
  execute format('insert into public.envios (%s) select %s from jsonb_populate_record(null::public.envios, $1)', p_cols, p_cols)
    using v_obj;
end $f$;

do $$
declare
  -- ===== parámetros que puede cambiar =====
  v_semana          int     := 40;     -- semana de prueba
  v_historial       int     := 10;     -- semanas anteriores con historial (30 a 39)
  v_ajustar_config  boolean := true;   -- deja la semana 40 activa con corte en 2 días
  -- ========================================
  v_anio      int;
  v_inicio    date;
  v_ahora     timestamptz := now();
  v_corte     timestamp;
  r           record;
  c           record;
  v_i         int := 0;
  v_s         int;
  v_k         int;
  v_perfil    text;
  v_escenario int;
  v_tarde     boolean;
  v_tipos     text[];
  v_tipo      text;
  v_correo    text;
  v_a_tiempo  jsonb;
  v_tardio    jsonb;
  v_cols      text;
  v_n         int := 0;
  v_redes     int := 0;
  v_ncentros  int;
  v_j         int;
  v_fecha     timestamptz;
  v_nombre_tipo jsonb := '{"c": "Consulta Externa", "h": "Hospitalizacion", "e": "Emergencia"}';
begin
  -- Año activo (o el actual)
  select anio, fecha_inicio into v_anio, v_inicio
    from public.anios_epidemiologicos where activo order by anio desc limit 1;
  if v_anio is null then
    v_anio := extract(year from now())::int;
  end if;
  if v_inicio is null then   -- semana 1 = la que contiene el 4 de enero (domingo a sábado)
    v_inicio := make_date(v_anio, 1, 4) - ((extract(dow from make_date(v_anio, 1, 4))::int) % 7);
  end if;
  raise notice 'Año epidemiológico %, semana 1 desde %', v_anio, v_inicio;

  -- 1) Limpiar lo sintético anterior
  delete from public.envios where codigo_seguimiento like 'DEMO-SIM-%';
  -- (los registros «DEMO-SIM» del historial no se borran: la tabla logs guarda 90 días por política de auditoría;
  --  al repetir el script no se duplican)

  -- Columnas de «envios» que existen en esta base (la estructura varía según la versión de SIRE)
  select string_agg(quote_ident(column_name), ',') into v_cols
    from information_schema.columns
   where table_schema = 'public' and table_name = 'envios'
     and column_name in ('nombre_usuario','apellido_usuario','correo_usuario','red','centros','semana','anio',
                         'tipo_reporte','ruta_zip','drive_file_id','cantidad_archivos','estado','observacion',
                         'es_atrasado','semana_activa_envio','dias_atraso_envio','codigo_seguimiento',
                         'fecha_envio','fecha_actualizacion','detalle_archivos');

  for r in
    select rd.nombre as red
      from public.redes rd
     where exists (select 1 from public.centros ce where ce.red_id = rd.id)
     order by rd.nombre
  loop
    v_redes := v_redes + 1;
    v_perfil := case v_i % 8 when 0 then 'suele_atrasarse' when 1 then 'suele_atrasarse' when 2 then 'mejora'
                             when 3 then 'empeora' else 'puntual' end;
    v_escenario := v_i % 6;      -- qué le pasa en la semana 40
    v_correo := 'responsable.' || left(regexp_replace(lower(r.red), '[^a-z0-9]', '', 'g'), 24) || '@example.org';

    -- 2) Historial: semanas (v_semana - v_historial) .. (v_semana - 1)
    for v_k in 0 .. v_historial - 1 loop
      v_s := v_semana - v_historial + v_k;
      continue when v_s < 1;
      v_tarde := case v_perfil
                   when 'suele_atrasarse' then (v_k % 4) <> 1            -- tarde 3 de cada 4 semanas
                   when 'mejora'          then v_k < v_historial - 3     -- tarde antes, a tiempo las últimas 3
                   when 'empeora'         then v_k >= v_historial - 3    -- a tiempo antes, tarde las últimas 3
                   else false end;
      v_a_tiempo := '[]'; v_tardio := '[]';
      for c in select ce.codigo, ce.nombre from public.centros ce join public.redes rd on rd.id = ce.red_id
                where rd.nombre = r.red order by ce.codigo loop
        v_tipos := case when upper(c.nombre) like '%HOSPITAL%' or upper(c.nombre) like 'H.%' then array['c','h','e']
                        when upper(c.nombre) like '%C.M.%' or upper(c.nombre) like '%CENTRO MEDICO%'
                          or upper(c.nombre) like '%CENTRO MÉDICO%' then array['c','e']
                        else array['c'] end;
        foreach v_tipo in array v_tipos loop
          if v_tarde and (v_tipo = 'e' or v_perfil <> 'suele_atrasarse') then
            v_tardio := v_tardio || jsonb_build_object('codigo', c.codigo, 'centro', c.nombre, 'tipo', v_tipo);
          else
            v_a_tiempo := v_a_tiempo || jsonb_build_object('codigo', c.codigo, 'centro', c.nombre, 'tipo', v_tipo);
          end if;
        end loop;
      end loop;
      -- Para las redes que suelen atrasarse: recordatorio manual ANTES del envío tardío
      if v_tarde and v_perfil = 'suele_atrasarse' then
        insert into public.logs (usuario, accion, detalle, fecha)
        select 'DEMO-SIM', 'ENVIO_RECORDATORIO',
               format('Recordatorio enviado a %s - Red: %s - Semana %s/%s - Tipo: ATRASADO', v_correo, r.red, v_s, v_anio),
               (v_inicio + (v_s - 1) * 7 + 9)::timestamp + interval '9 hours'
         where not exists (select 1 from public.logs where usuario = 'DEMO-SIM'
                             and detalle = format('Recordatorio enviado a %s - Red: %s - Semana %s/%s - Tipo: ATRASADO',
                                                  v_correo, r.red, v_s, v_anio));
      end if;
      -- envío a tiempo (día 4 de la semana siguiente) y tardío (día 11)
      if jsonb_array_length(v_a_tiempo) > 0 then
        v_fecha := (v_inicio + (v_s - 1) * 7 + 4)::timestamp + interval '10 hours';
        perform public._demo_sim_insertar(v_cols, r.red, v_correo, v_anio, v_s, v_a_tiempo, false, v_fecha, v_nombre_tipo);
        v_n := v_n + 1;
      end if;
      if jsonb_array_length(v_tardio) > 0 then
        v_fecha := (v_inicio + (v_s - 1) * 7 + 11)::timestamp + interval '15 hours';
        perform public._demo_sim_insertar(v_cols, r.red, v_correo, v_anio, v_s, v_tardio, true, v_fecha, v_nombre_tipo);
        v_n := v_n + 1;
      end if;
    end loop;

    -- 3) Semana 40 a medio camino
    if v_escenario <> 3 then                       -- escenario 3: todavía no envió nada
      v_a_tiempo := '[]';
      select count(*) into v_ncentros from public.centros ce join public.redes rd on rd.id = ce.red_id where rd.nombre = r.red;
      v_j := 0;
      for c in select ce.codigo, ce.nombre from public.centros ce join public.redes rd on rd.id = ce.red_id
                where rd.nombre = r.red order by ce.codigo loop
        v_j := v_j + 1;
        continue when v_escenario = 2 and v_j > greatest(1, v_ncentros / 2);   -- falta la mitad de los centros
        v_tipos := case when upper(c.nombre) like '%HOSPITAL%' or upper(c.nombre) like 'H.%' then array['c','h','e']
                        when upper(c.nombre) like '%C.M.%' or upper(c.nombre) like '%CENTRO MEDICO%'
                          or upper(c.nombre) like '%CENTRO MÉDICO%' then array['c','e']
                        else array['c'] end;
        foreach v_tipo in array v_tipos loop
          -- escenario 1: falta la Emergencia del primer centro que la manda; escenario 4: falta su Hospitalización
          continue when v_escenario = 1 and v_tipo = 'e' and v_j <= 2 and 'e' = any(v_tipos);
          continue when v_escenario = 4 and v_tipo = 'h' and v_j <= 2;
          v_a_tiempo := v_a_tiempo || jsonb_build_object('codigo', c.codigo, 'centro', c.nombre, 'tipo', v_tipo);
        end loop;
      end loop;
      if jsonb_array_length(v_a_tiempo) > 0 then
        perform public._demo_sim_insertar(v_cols, r.red, v_correo, v_anio, v_semana, v_a_tiempo, false,
                                          v_ahora - interval '20 hours', v_nombre_tipo);
        v_n := v_n + 1;
      end if;
    end if;
    raise notice '% · historial: % · semana %: %', r.red, replace(v_perfil, '_', ' '), v_semana,
      case v_escenario when 0 then 'completa' when 1 then 'falta Emergencia de un centro' when 2 then 'falta la mitad de los centros'
                       when 3 then 'aún no envía nada' when 4 then 'falta Hospitalización de un centro' else 'completa' end;
    v_i := v_i + 1;
  end loop;

  -- 4) Semana activa = 40 y corte en 2 días (se guarda lo anterior para volver atrás)
  if v_ajustar_config then
    v_corte := date_trunc('day', (now() at time zone 'America/Lima') + interval '2 days') + interval '23 hours 59 minutes 59 seconds';
    insert into public.configuracion (clave, valor)
      select 'demo_sim_semana_activa_anterior', coalesce((select valor from public.configuracion where clave = 'semana_activa'), '')
      where not exists (select 1 from public.configuracion where clave = 'demo_sim_semana_activa_anterior');
    insert into public.configuracion (clave, valor)
      select 'demo_sim_fecha_corte_anterior', coalesce((select valor from public.configuracion where clave = 'fecha_corte'), '')
      where not exists (select 1 from public.configuracion where clave = 'demo_sim_fecha_corte_anterior');
    update public.configuracion set valor = v_semana::text where clave = 'semana_activa';
    if not found then insert into public.configuracion (clave, valor) values ('semana_activa', v_semana::text); end if;
    update public.configuracion set valor = to_char(v_corte, 'YYYY-MM-DD HH24:MI:SS') where clave = 'fecha_corte';
    if not found then insert into public.configuracion (clave, valor) values ('fecha_corte', to_char(v_corte, 'YYYY-MM-DD HH24:MI:SS')); end if;
    raise notice 'Semana activa: % · fecha de corte: %', v_semana, to_char(v_corte, 'YYYY-MM-DD HH24:MI:SS');
  end if;

  raise notice 'Listo: % envíos sintéticos para % redes (semanas % a %).', v_n, v_redes, v_semana - v_historial, v_semana;
end $$;

drop function if exists public._demo_sim_insertar(text, text, text, int, int, jsonb, boolean, timestamptz, jsonb);

-- Resumen para revisar
select semana,
       count(*)                                  as envios,
       count(*) filter (where es_atrasado)       as tardios,
       count(distinct red)                       as redes
  from public.envios
 where codigo_seguimiento like 'DEMO-SIM-%'
 group by semana
 order by semana;

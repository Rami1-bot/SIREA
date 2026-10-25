-- ============================================================================
-- SIRE – Limpieza de datos de PRUEBA antes de pasar a producción
-- ============================================================================
-- Qué hace:   borra los datos operativos del piloto (envíos, descargas, retiros, solicitudes de
--             contraseña, logs) y deja intacta la configuración y las cuentas.
-- Qué CONSERVA (no se toca nada de esto):
--             administradores, permisos_operaciones, redes, centros, credenciales_red,
--             centros_excluidos, configuracion, anios_epidemiologicos, carpetas_drive,
--             destinatarios_externos, cierres_corte, respaldos y auditoria_acciones.
--   · auditoria_acciones es de SOLO ANEXAR a propósito (trigger): no se limpia, y la verificación
--     de la cadena seguirá diciendo «íntegra».
--   · cierres_corte se conserva para que el proceso programado NO vuelva a generar cierres ni avisos
--     por semanas pasadas.
--
-- ANTES DE EJECUTAR (obligatorio):
--   1) Haga un respaldo manual desde la aplicación (Configuración → Respaldos) y confirme que se guardó en Drive.
--   2) En el servidor:  docker compose stop programador   (para que no corra mientras se limpia).
--   3) Los archivos de prueba en Drive NO se borran con este script: muévalos o elimínelos a mano.
--
-- CÓMO USARLO (SQL Editor de Supabase):
--   · Tal como está, hace una PRUEBA EN SECO: muestra cuántas filas borraría y termina con ROLLBACK
--     (no cambia nada). Ejecútelo así primero y revise los números.
--   · Si los números son los esperados, cambie la última línea «rollback;» por «commit;» y vuelva a ejecutar.
--   · Si una restricción impide borrar, todo se revierte solo (no queda nada a medias).
-- ============================================================================

begin;

-- La tabla logs no deja borrar registros con menos de 90 días (sql/51). Para limpiar el piloto se
-- apaga esa protección SOLO dentro de esta transacción (si algo falla, todo se revierte).
do $$
begin
  if to_regclass('public.logs') is not null and exists (select 1 from pg_trigger where tgname = 'trg_logs_proteger') then
    alter table public.logs disable trigger trg_logs_proteger;
  end if;
end $$;

do $$
declare
  t text;
  n bigint;
  tablas text[] := array[
    'retiros_archivos',
    'solicitudes_retiro',
    'descargas_masivas',
    'solicitudes_password_mensajes',
    'solicitudes_password',
    'envios',
    'logs'
  ];
begin
  foreach t in array tablas loop
    if to_regclass('public.' || t) is null then
      raise notice '%: no existe (se omite)', t;
    else
      execute format('select count(*) from public.%I', t) into n;
      execute format('delete from public.%I where true', t);
      raise notice '%: % fila(s) borrada(s)', t, n;
    end if;
  end loop;
end $$;

do $$
begin
  if exists (select 1 from pg_trigger where tgname = 'trg_logs_proteger') then
    alter table public.logs enable trigger trg_logs_proteger;
  end if;
end $$;

-- SIREA 3.2: atrasos justificados e informes semanales del piloto. Sus triggers impiden borrar
-- (son evidencia); aquí se apagan SOLO dentro de esta transacción para limpiar el piloto.
-- Los envíos simulados de la demo (DEMO-SIM-…) ya se borran arriba junto con «envios».
do $$
declare
  n bigint;
begin
  if to_regclass('public.agente_atrasos_justificados') is not null then
    alter table public.agente_atrasos_justificados disable trigger trg_atraso_justificado_sin_borrar;
    select count(*) into n from public.agente_atrasos_justificados;
    delete from public.agente_atrasos_justificados where true;
    alter table public.agente_atrasos_justificados enable trigger trg_atraso_justificado_sin_borrar;
    raise notice 'agente_atrasos_justificados: % fila(s) borrada(s)', n;
  end if;
  if to_regclass('public.agente_informes') is not null then
    alter table public.agente_informes disable trigger trg_informe_inmutable;
    select count(*) into n from public.agente_informes;
    delete from public.agente_informes where true;
    alter table public.agente_informes enable trigger trg_informe_inmutable;
    raise notice 'agente_informes: % fila(s) borrada(s)', n;
  end if;
end $$;

-- Comprobación de lo que queda en las tablas que se conservan
select 'administradores' as tabla, count(*) as filas from public.administradores
union all select 'redes', count(*) from public.redes
union all select 'credenciales_red', count(*) from public.credenciales_red
union all select 'configuracion', count(*) from public.configuracion
union all select 'envios (debe ser 0)', count(*) from public.envios;

rollback;   -- ← PRUEBA EN SECO. Para aplicar de verdad, cambie esta línea por:  commit;

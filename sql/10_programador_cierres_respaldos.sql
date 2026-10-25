-- ============================================================
-- 10_programador_cierres_respaldos.sql
--
-- Tablas del proceso programado (contenedor "programador"):
--
--   cierres_corte             una fila por corte cerrado: propuesta de semana
--                             y corte, avisos y recordatorios enviados, quien
--                             la valido y el estado del resumen de cumplimiento
--   destinatarios_externos    correos de la entidad que califica a las redes
--                             (los registra un SUPER_ADMIN en el panel)
--   respaldos                 historial de respaldos a Drive
--
-- La clave unica de cierres_corte (corte_cerrado) hace que el proceso sea
-- IDEMPOTENTE: aunque se reinicie o haya dos copias, un corte se procesa una
-- sola vez y los correos no se duplican.
--
-- Es idempotente (IF NOT EXISTS): se puede correr varias veces.
-- Ejecutar en el SQL Editor de Supabase, DESPUES de 01 y 09.
-- ============================================================

create table if not exists public.cierres_corte (
  id bigserial primary key,
  anio integer not null,
  semana_cerrada integer not null,
  corte_cerrado text not null unique,          -- 'AAAA-MM-DD HH:MM:SS' (hora de Lima)
  semana_propuesta integer null,
  corte_propuesto text null,                   -- 'AAAA-MM-DD HH:MM:SS' (hora de Lima)
  semana_previa integer null,                  -- valores vigentes antes del cierre (auditoria)
  corte_previo text null,
  aplicado boolean not null default false,     -- true si el sistema cambio la configuracion
  nota text null,                              -- p. ej. cambio de anio o corte en feriado
  estado text not null default 'PROVISIONAL'
    check (estado in ('PROVISIONAL','VALIDADA','SUPERADA')),
  fecha_creacion timestamp with time zone not null default now(),
  aviso_inicial_at timestamp with time zone null,
  recordatorios_enviados integer not null default 0,
  ultimo_recordatorio_at timestamp with time zone null,
  validado_por text null,
  validado_por_nombre text null,
  fecha_validacion timestamp with time zone null,
  semana_validada integer null,
  corte_validado text null,
  hubo_correccion boolean not null default false,
  aviso_validado_enviado boolean not null default false,
  -- resumen de cumplimiento por red de la semana cerrada
  resumen_borrador_enviado_at timestamp with time zone null,
  resumen_estado text not null default 'PENDIENTE'
    check (resumen_estado in ('PENDIENTE','VALIDADO','ENVIADO')),
  resumen_validado_por text null,
  resumen_validado_por_nombre text null,
  resumen_fecha_validacion timestamp with time zone null,
  resumen_enviado_externo_at timestamp with time zone null,
  -- respaldo (cada dos cortes)
  respaldo_evaluado boolean not null default false
);

create index if not exists idx_cierres_corte_estado
  on public.cierres_corte (estado, fecha_creacion desc);

create table if not exists public.destinatarios_externos (
  id bigserial primary key,
  nombre text not null,
  apellidos text not null default '',
  correo text not null unique,
  activo boolean not null default true,
  creado_por text null,
  fecha_creacion timestamp with time zone not null default now()
);

create table if not exists public.respaldos (
  id bigserial primary key,
  nombre text not null,                        -- nombre de la subcarpeta, con fecha y hora exactas
  corte_referencia text null,
  estado text not null default 'EN_CURSO'
    check (estado in ('EN_CURSO','COMPLETADO','ERROR')),
  destino text null,                           -- 'DRIVE' o 'LOCAL'
  carpeta_id text null,
  detalle text null,                           -- conteos por tabla o motivo del error
  total_filas integer not null default 0,
  origen text not null default 'AUTOMATICO',   -- AUTOMATICO | MANUAL
  creado_por text null,
  fecha_creacion timestamp with time zone not null default now(),
  fecha_fin timestamp with time zone null
);

create index if not exists idx_respaldos_fecha
  on public.respaldos (fecha_creacion desc);

-- Seguridad: igual que el resto de tablas, solo la clave service_role (servidor) accede.
alter table public.cierres_corte enable row level security;
alter table public.destinatarios_externos enable row level security;
alter table public.respaldos enable row level security;

revoke all on public.cierres_corte from anon, authenticated;
revoke all on public.destinatarios_externos from anon, authenticated;
revoke all on public.respaldos from anon, authenticated;
revoke all on sequence public.cierres_corte_id_seq from anon, authenticated;
revoke all on sequence public.destinatarios_externos_id_seq from anon, authenticated;
revoke all on sequence public.respaldos_id_seq from anon, authenticated;

grant all on public.cierres_corte to service_role;
grant all on public.destinatarios_externos to service_role;
grant all on public.respaldos to service_role;
grant all on sequence public.cierres_corte_id_seq to service_role;
grant all on sequence public.destinatarios_externos_id_seq to service_role;
grant all on sequence public.respaldos_id_seq to service_role;

-- Fin de 10_programador_cierres_respaldos.sql

-- ============================================================
-- ACTUALIZAR_TODO_SIREA_3_2.sql
--
-- UN SOLO ARCHIVO para dejar la base de datos lista para SIREA 3.2,
-- venga de donde venga (SIRE v3/v5/v6/v7 o SIREA 1.x/2.x/3.0/3.1).
--
-- Cómo usarlo:
--   1. Supabase → su proyecto (el de DEMO) → SQL Editor → New query.
--   2. Pegue TODO este archivo y pulse «Run».
--   3. Al final aparece una tabla: todas las filas deben decir «OK».
--
-- Es SEGURO DE REPETIR: si una tabla, columna, índice o regla ya existe,
-- no hace nada; no borra datos. Si ya tenía SIREA 3.1, lo nuevo es el 54.
--
-- NO incluye 99_limpieza_previa_a_produccion.sql (borra datos de prueba):
-- ese se ejecuta aparte y solo si se decide.
--
-- Contenido (en este orden):
--    1. 09_solicitudes_cambio_password.sql
--    2. 10_programador_cierres_respaldos.sql
--    3. 11_auditoria_permisos_repositorio.sql
--    4. 12_envios_detalle_archivos.sql
--    5. 13_observaciones_envio.sql
--    6. 14_observaciones_categorias.sql
--    7. 50_auditoria_agentes_ia.sql
--    8. 51_sesiones_e_intentos_login.sql
--    9. 52_agente_operativo.sql
--   10. 53_skill_versiones.sql
--   11. 54_sirea_3_2.sql
--   12. 00_reparar_permisos_service_role.sql
-- ============================================================



-- ############################################################
-- ##### 09_solicitudes_cambio_password.sql
-- ############################################################

-- ============================================================
-- 09_solicitudes_cambio_password.sql
--
-- Crea las tablas del flujo "solicitud de cambio de contrasena":
-- despues del primer cambio (de la clave generica a una propia), una
-- red que quiera volver a cambiar su contrasena debe enviar un
-- sustento; un SUPER_ADMIN lo revisa en el panel, responde y, si lo
-- aprueba, se habilita el cambio de contrasena para esa red.
--
--   solicitudes_password            una fila por solicitud
--   solicitudes_password_mensajes   intercambio de mensajes (red <-> admin)
--
-- Es idempotente (IF NOT EXISTS): se puede correr varias veces.
-- Ejecutar en el SQL Editor de Supabase, DESPUES de 01 y 07.
-- ============================================================

create table if not exists public.solicitudes_password (
  id bigserial primary key,
  codigo text not null unique,
  red text not null,
  nombre text not null,
  correo text not null,
  estado text not null default 'PENDIENTE'
    check (estado in ('PENDIENTE','APROBADA','RECHAZADA','COMPLETADA','CANCELADA','VENCIDA')),
  fecha_creacion timestamp with time zone not null default now(),
  fecha_resolucion timestamp with time zone null,
  resuelto_por text null,
  fecha_vencimiento timestamp with time zone null,
  fecha_uso timestamp with time zone null
);

-- Una red solo puede tener UNA solicitud abierta (pendiente o aprobada) a la vez.
create unique index if not exists uq_solicitudes_password_abierta
  on public.solicitudes_password (red)
  where estado in ('PENDIENTE','APROBADA');

create index if not exists idx_solicitudes_password_estado
  on public.solicitudes_password (estado, fecha_creacion desc);

create table if not exists public.solicitudes_password_mensajes (
  id bigserial primary key,
  solicitud_id bigint not null references public.solicitudes_password(id) on delete cascade,
  autor_tipo text not null check (autor_tipo in ('RED','ADMIN','SISTEMA')),
  autor text not null,
  mensaje text not null,
  fecha timestamp with time zone not null default now()
);

create index if not exists idx_solicitudes_password_mensajes_sol
  on public.solicitudes_password_mensajes (solicitud_id, fecha);

-- Seguridad: igual que el resto de tablas, solo la clave service_role (servidor) accede.
alter table public.solicitudes_password enable row level security;
alter table public.solicitudes_password_mensajes enable row level security;

revoke all on public.solicitudes_password from anon, authenticated;
revoke all on public.solicitudes_password_mensajes from anon, authenticated;
revoke all on sequence public.solicitudes_password_id_seq from anon, authenticated;
revoke all on sequence public.solicitudes_password_mensajes_id_seq from anon, authenticated;

grant all on public.solicitudes_password to service_role;
grant all on public.solicitudes_password_mensajes to service_role;
grant all on sequence public.solicitudes_password_id_seq to service_role;
grant all on sequence public.solicitudes_password_mensajes_id_seq to service_role;

-- Fin de 09_solicitudes_cambio_password.sql


-- ############################################################
-- ##### 10_programador_cierres_respaldos.sql
-- ############################################################

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


-- ############################################################
-- ##### 11_auditoria_permisos_repositorio.sql
-- ############################################################

-- ============================================================
-- 11_auditoria_permisos_repositorio.sql
--
-- Trazabilidad y control del repositorio de archivos (Drive):
--
--   auditoria_acciones     registro de quién hizo qué y cuándo. SOLO SE AÑADE:
--                          un disparador impide modificar o borrar filas, y cada
--                          fila lleva la huella (SHA-256) de la anterior, de modo
--                          que cualquier alteración se detecta al verificar la cadena.
--   permisos_operaciones   permisos que asigna ÚNICAMENTE el SUPER_ADMIN principal
--                          (descarga masiva, retiro del repositorio, respaldo
--                          manual y ver la auditoría), por persona, con alcance
--                          opcional por redes y fecha de vencimiento.
--   descargas_masivas      cada ZIP masivo preparado/descargado (con su huella).
--   solicitudes_retiro     retiros de archivos del repositorio: quién los pide,
--                          quién los aprueba y el resultado.
--   retiros_archivos       detalle archivo por archivo de cada retiro.
--
-- Es idempotente (IF NOT EXISTS / CREATE OR REPLACE): se puede correr varias veces.
-- Ejecutar en el SQL Editor de Supabase, DESPUES de 01 y 10.
-- ============================================================

-- ---------------------------------------------------------------- auditoría

create table if not exists public.auditoria_acciones (
  id bigserial primary key,
  ocurrio_en timestamp with time zone not null default now(),
  ocurrio_iso text not null,                   -- 'AAAA-MM-DD HH:MM:SS' (hora de Lima); entra en la huella
  usuario text not null,
  rol text null,
  accion text not null,
  categoria text not null default 'GENERAL',
  objeto text null,
  detalle text null,                           -- JSON en texto (exacto, para poder recalcular la huella)
  resultado text not null default 'OK',        -- OK | ERROR | RECHAZADO | PENDIENTE
  ip text null,
  hash_prev text not null,
  hash text not null
);

-- Una sola fila puede seguir a otra: evita que dos procesos bifurquen la cadena.
create unique index if not exists uq_auditoria_hash_prev on public.auditoria_acciones (hash_prev);
create index if not exists idx_auditoria_fecha on public.auditoria_acciones (ocurrio_iso desc);
create index if not exists idx_auditoria_usuario on public.auditoria_acciones (usuario, ocurrio_iso desc);
create index if not exists idx_auditoria_accion on public.auditoria_acciones (categoria, accion);

-- Solo se añade: ni siquiera la clave de servidor puede editar o borrar.
create or replace function public.auditoria_solo_anexar() returns trigger
language plpgsql as $$
begin
  raise exception 'auditoria_acciones es de solo escritura: no se permite % de filas', tg_op
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_auditoria_no_modificar on public.auditoria_acciones;
create trigger trg_auditoria_no_modificar
  before update or delete on public.auditoria_acciones
  for each row execute function public.auditoria_solo_anexar();

drop trigger if exists trg_auditoria_no_truncar on public.auditoria_acciones;
create trigger trg_auditoria_no_truncar
  before truncate on public.auditoria_acciones
  for each statement execute function public.auditoria_solo_anexar();

-- ---------------------------------------------------------------- permisos

create table if not exists public.permisos_operaciones (
  id bigserial primary key,
  usuario text not null,
  permiso text not null
    check (permiso in ('DESCARGA_MASIVA','RETIRO_REPOSITORIO','RESPALDO_MANUAL','VER_AUDITORIA')),
  redes text[] null,                           -- null = todas las redes
  vence_en timestamp with time zone null,      -- null = sin vencimiento
  activo boolean not null default true,
  nota text null,
  otorgado_por text not null,
  fecha_creacion timestamp with time zone not null default now(),
  revocado_por text null,
  fecha_revocacion timestamp with time zone null,
  motivo_revocacion text null
);

-- Un solo permiso vigente de cada tipo por persona.
create unique index if not exists uq_permisos_vigente
  on public.permisos_operaciones (usuario, permiso) where activo;
create index if not exists idx_permisos_usuario on public.permisos_operaciones (usuario, activo);

-- ---------------------------------------------------------------- descargas

create table if not exists public.descargas_masivas (
  id bigserial primary key,
  anio integer not null,
  semana integer not null,
  redes text[] not null default '{}',
  todas_las_redes boolean not null default false,
  incluye_duplicados boolean not null default false,
  parte integer not null default 1,
  total_partes integer not null default 1,
  nombre_zip text not null,
  n_envios integer not null default 0,
  n_archivos integer not null default 0,
  bytes bigint not null default 0,
  sha256 text null,
  envio_ids bigint[] not null default '{}',
  usuario text not null,
  usuario_nombre text null,
  rol text null,
  estado text not null default 'PREPARADA'
    check (estado in ('PREPARADA','DESCARGADA')),
  fecha_preparada timestamp with time zone not null default now(),
  fecha_descarga timestamp with time zone null,
  ip text null
);
create index if not exists idx_descargas_semana on public.descargas_masivas (anio, semana);

-- ---------------------------------------------------------------- retiros

create table if not exists public.solicitudes_retiro (
  id bigserial primary key,
  anio integer not null,
  semana integer not null,
  redes text[] not null default '{}',
  todas_las_redes boolean not null default false,
  envio_ids bigint[] not null default '{}',
  n_envios integer not null default 0,
  bytes_estimados bigint not null default 0,
  motivo_categoria text not null,
  motivo text not null,
  sin_descarga_previa boolean not null default false,
  definitivo boolean not null default false,   -- true = borrado definitivo (no va a la papelera)
  solicitado_por text not null,
  solicitado_nombre text null,
  rol_solicitante text null,
  estado text not null default 'PENDIENTE'
    check (estado in ('PENDIENTE','EJECUTADA','PARCIAL','ERROR','RECHAZADA','CANCELADA')),
  decidido_por text null,
  decidido_nombre text null,
  fecha_decision timestamp with time zone null,
  nota_decision text null,
  n_ok integer not null default 0,
  n_error integer not null default 0,
  fecha_creacion timestamp with time zone not null default now(),
  fecha_ejecucion timestamp with time zone null,
  ip text null
);
create index if not exists idx_retiro_estado on public.solicitudes_retiro (estado, fecha_creacion desc);

create table if not exists public.retiros_archivos (
  id bigserial primary key,
  solicitud_id bigint not null,
  envio_id bigint null,
  codigo_seguimiento text null,
  red text null,
  semana integer null,
  anio integer null,
  centros text null,
  drive_file_id text null,
  ruta_zip text null,
  resultado text not null default 'OK',        -- OK | ERROR
  detalle text null,
  fecha timestamp with time zone not null default now()
);
create index if not exists idx_retiros_solicitud on public.retiros_archivos (solicitud_id);
create index if not exists idx_retiros_envio on public.retiros_archivos (envio_id);

-- ---------------------------------------------------------------- seguridad

alter table public.auditoria_acciones enable row level security;
alter table public.permisos_operaciones enable row level security;
alter table public.descargas_masivas enable row level security;
alter table public.solicitudes_retiro enable row level security;
alter table public.retiros_archivos enable row level security;

revoke all on public.auditoria_acciones from anon, authenticated;
revoke all on public.permisos_operaciones from anon, authenticated;
revoke all on public.descargas_masivas from anon, authenticated;
revoke all on public.solicitudes_retiro from anon, authenticated;
revoke all on public.retiros_archivos from anon, authenticated;
revoke all on sequence public.auditoria_acciones_id_seq from anon, authenticated;
revoke all on sequence public.permisos_operaciones_id_seq from anon, authenticated;
revoke all on sequence public.descargas_masivas_id_seq from anon, authenticated;
revoke all on sequence public.solicitudes_retiro_id_seq from anon, authenticated;
revoke all on sequence public.retiros_archivos_id_seq from anon, authenticated;

-- A la auditoría el servidor solo le puede AÑADIR y LEER (nunca editar ni borrar).
revoke all on public.auditoria_acciones from service_role;
grant select, insert on public.auditoria_acciones to service_role;
grant all on public.permisos_operaciones to service_role;
grant all on public.descargas_masivas to service_role;
grant all on public.solicitudes_retiro to service_role;
grant all on public.retiros_archivos to service_role;
grant all on sequence public.auditoria_acciones_id_seq to service_role;
grant all on sequence public.permisos_operaciones_id_seq to service_role;
grant all on sequence public.descargas_masivas_id_seq to service_role;
grant all on sequence public.solicitudes_retiro_id_seq to service_role;
grant all on sequence public.retiros_archivos_id_seq to service_role;

-- Fin de 11_auditoria_permisos_repositorio.sql


-- ############################################################
-- ##### 12_envios_detalle_archivos.sql
-- ############################################################

-- ============================================================
-- 12 · Detalle por archivo de cada envío (v6.8)
-- ============================================================
-- Guarda, por cada archivo del ZIP: centro, código, tipo (c/e/h),
-- semana, año y huella SHA-256 (NUNCA el contenido). Sirve para:
--   · detectar duplicados por centro + tipo + semana + año, y separar
--     en un mismo ZIP lo nuevo de lo ya recibido;
--   · avisar si un archivo es idéntico a uno enviado en otra semana.
--
-- Es OPCIONAL y seguro: el sistema funciona sin esta columna (usa el
-- centro y tipo del formulario como respaldo), pero con ella la
-- detección es exacta. Se puede ejecutar varias veces.
-- Ejecutar en Supabase > SQL Editor.

ALTER TABLE public.envios
    ADD COLUMN IF NOT EXISTS detalle_archivos jsonb;

COMMENT ON COLUMN public.envios.detalle_archivos IS
    'Por archivo: centro, codigo, tipo, semana, anio, sha256 (sin contenido).';


-- ############################################################
-- ##### 13_observaciones_envio.sql
-- ############################################################

-- ============================================================
-- 13_observaciones_envio.sql   (v7.0)
--
-- Tabla del módulo «Observaciones» del panel: una fila por envío que
-- tenga algo que revisar (sustento escrito por quien envía, envío
-- observado, duplicado o reemplazo). El texto es corto: la base rechaza
-- más de 1000 caracteres, así que no pesa (≈1,5 MB al año con 30 redes).
--
-- Es OPCIONAL: sin esta tabla el envío se registra igual; solo se pierde
-- el sustento y el módulo avisa que falta ejecutarla.
-- Es idempotente (IF NOT EXISTS). Ejecutar en el SQL Editor de Supabase.
-- ============================================================

create table if not exists public.observaciones_envio (
  id bigserial primary key,
  envio_id bigint null,
  codigo_seguimiento text not null,
  red text not null,
  semana integer null,
  anio integer null,
  remitente text not null default '',          -- «Apellidos Nombres»
  correo text not null default '',
  motivo text not null default 'SUSTENTO'
    check (motivo in ('SUSTENTO','OBSERVADO','DUPLICADO','REEMPLAZO')),
  estado_envio text null,
  texto text null check (texto is null or char_length(texto) <= 1000),   -- lo que escribió quien envía
  detalle text null check (detalle is null or char_length(detalle) <= 1500),  -- nota del sistema
  revisada boolean not null default false,
  revisada_por text null,
  fecha_revision timestamp with time zone null,
  fecha_creacion timestamp with time zone not null default now()
);

create index if not exists idx_observaciones_envio_pend
  on public.observaciones_envio (revisada, fecha_creacion desc);
create index if not exists idx_observaciones_envio_codigo
  on public.observaciones_envio (codigo_seguimiento);

alter table public.observaciones_envio enable row level security;
revoke all on public.observaciones_envio from anon, authenticated;
revoke all on sequence public.observaciones_envio_id_seq from anon, authenticated;
grant all on public.observaciones_envio to service_role;
grant all on sequence public.observaciones_envio_id_seq to service_role;

-- Fin de 13_observaciones_envio.sql


-- ############################################################
-- ##### 14_observaciones_categorias.sql
-- ############################################################

-- ============================================================
-- 14_observaciones_categorias.sql   (v7.2)
--
-- Separa en «Observaciones» lo que escriben las redes de las fallas
-- técnicas del sistema (por ejemplo, Drive sin permiso para mover un
-- archivo): agrega el motivo FALLA y una columna `datos` con lo necesario
-- para reintentar la operación desde el panel.
--
-- Requiere haber ejecutado antes sql/13. Es OPCIONAL e idempotente: sin
-- esto todo funciona, pero las fallas aparecen mezcladas como «Reemplazo»
-- y no se puede reintentar. Ejecutar en el SQL Editor de Supabase.
-- ============================================================

alter table public.observaciones_envio
  add column if not exists datos jsonb null;

alter table public.observaciones_envio
  drop constraint if exists observaciones_envio_motivo_check;

alter table public.observaciones_envio
  add constraint observaciones_envio_motivo_check
  check (motivo in ('SUSTENTO','OBSERVADO','DUPLICADO','REEMPLAZO','FALLA'));

-- Las fallas que ya quedaron registradas como «Reemplazo» (v7.0/v7.1) pasan a FALLA.
update public.observaciones_envio
   set motivo = 'FALLA'
 where motivo = 'REEMPLAZO'
   and texto is null
   and detalle like 'No se pudo mover a REEMPLAZADOS%';


-- ############################################################
-- ##### 50_auditoria_agentes_ia.sql
-- ############################################################

-- ============================================================
-- 50_auditoria_agentes_ia.sql  (antes 001 en SIGRE)
-- Registro INMUTABLE de auditoría de los agentes de IA + estado inicial
-- del kill-switch.
--
-- Cumple: Informe EsSalud, Tabla 3.1 Riesgo 3 ("Módulo de Registro
-- activado antes de cualquier etapa experimental; captura inmutable de
-- usuario, hora, consulta, modelo, borrador y aprobación") y Tabla 4.2.1
-- ("Logs Auditables", "Mecanismo de Detención").
--
-- Ejecutar UNA vez en el SQL Editor de Supabase (proyecto DEMO).
-- ============================================================

-- 1) Tabla de auditoría -------------------------------------------------
create table if not exists public.auditoria_agentes_ia (
    id                  bigint generated always as identity primary key,
    fecha               timestamptz not null default now(),
    usuario             text        not null,           -- identificador institucional del admin
    rol                 text        not null,
    agente              text        not null,           -- orquestador | resumen | seguimiento | sistema
    evento              text        not null,           -- CONSULTA | BORRADOR | APROBACION | RECHAZO | ENVIO | BLOQUEO_GUARDRAIL | CAMBIO_ESTADO | ERROR
    modelo              text,                           -- modelo Gemini realmente usado
    entrada             text,                           -- consulta / datos de entrada (PII ya redactada)
    entrada_hash        text,                           -- sha256 corto de la entrada original
    salida              text,                           -- respuesta o borrador (PII ya redactada)
    herramientas        jsonb       not null default '[]'::jsonb,  -- function-calls ejecutadas
    guardrail_categoria text,
    guardrail_motivo    text,
    observaciones       jsonb       not null default '[]'::jsonb,  -- p.ej. cifras no verificadas
    aprobado_por        text,
    referencia          text,                           -- id del borrador que aprueba/envía
    duracion_ms         integer,
    anio                integer,
    semana              integer,
    constraint auditoria_agentes_ia_evento_chk check (
        evento in ('CONSULTA','BORRADOR','APROBACION','RECHAZO','ENVIO',
                   'BLOQUEO_GUARDRAIL','CAMBIO_ESTADO','ERROR')
    )
);

create index if not exists auditoria_agentes_ia_fecha_idx   on public.auditoria_agentes_ia (fecha desc);
create index if not exists auditoria_agentes_ia_agente_idx  on public.auditoria_agentes_ia (agente, evento);
create index if not exists auditoria_agentes_ia_usuario_idx on public.auditoria_agentes_ia (usuario);

comment on table public.auditoria_agentes_ia is
  'Registro inmutable (solo INSERT) de todas las interacciones con los agentes de IA. Ley 31814 / DS 115-2025-PCM: trazabilidad.';

-- 2) Inmutabilidad: trigger que rechaza UPDATE y DELETE -------------------
create or replace function public.fn_auditoria_ia_inmutable()
returns trigger
language plpgsql
as $$
begin
    raise exception 'auditoria_agentes_ia es inmutable: no se permite % (id=%)', tg_op, coalesce(old.id, -1)
        using errcode = 'P0001';
end;
$$;

drop trigger if exists trg_auditoria_ia_inmutable on public.auditoria_agentes_ia;
create trigger trg_auditoria_ia_inmutable
    before update or delete on public.auditoria_agentes_ia
    for each row execute function public.fn_auditoria_ia_inmutable();

-- También se bloquea el TRUNCATE (es a nivel de sentencia).
create or replace function public.fn_auditoria_ia_sin_truncate()
returns trigger
language plpgsql
as $$
begin
    raise exception 'auditoria_agentes_ia es inmutable: TRUNCATE no permitido' using errcode = 'P0001';
end;
$$;

drop trigger if exists trg_auditoria_ia_sin_truncate on public.auditoria_agentes_ia;
create trigger trg_auditoria_ia_sin_truncate
    before truncate on public.auditoria_agentes_ia
    for each statement execute function public.fn_auditoria_ia_sin_truncate();

-- 3) RLS: solo INSERT y SELECT --------------------------------------------
alter table public.auditoria_agentes_ia enable row level security;

drop policy if exists auditoria_ia_insert on public.auditoria_agentes_ia;
create policy auditoria_ia_insert on public.auditoria_agentes_ia
    for insert to anon, authenticated, service_role
    with check (true);

drop policy if exists auditoria_ia_select on public.auditoria_agentes_ia;
create policy auditoria_ia_select on public.auditoria_agentes_ia
    for select to anon, authenticated, service_role
    using (true);

-- Sin política de UPDATE/DELETE => denegado por RLS; además el trigger lo
-- rechaza aunque se use la service_role key.
revoke update, delete, truncate on public.auditoria_agentes_ia from anon, authenticated;

-- 4) Estado inicial del kill-switch ---------------------------------------
-- FAIL-CLOSED: los agentes arrancan INACTIVOS. Un SUPER_ADMIN debe
-- activarlos explícitamente desde el panel "Agentes IA" (Tabla 4.2.2:
-- autoridad de activación = Jefatura de la OIIS).
-- (el upsert desde la app requiere unicidad en `clave`)
create unique index if not exists configuracion_clave_uidx on public.configuracion (clave);

insert into public.configuracion (clave, valor, fecha_actualizacion)
values ('agentes_ia_estado', 'INACTIVO', now())
on conflict (clave) do nothing;

-- ============================================================
-- Verificación rápida (opcional):
--   select * from public.auditoria_agentes_ia order by fecha desc limit 5;
--   update public.auditoria_agentes_ia set salida = 'x' where id = 1;  -- debe fallar
-- ============================================================


-- ############################################################
-- ##### 51_sesiones_e_intentos_login.sql
-- ############################################################

-- ============================================================
-- 51_sesiones_e_intentos_login.sql  (antes 002 en SIGRE)
-- (a) Sesiones e intentos de login PERSISTENTES (reemplazan los
--     diccionarios en memoria de src/auth.py y src/auth_red.py).
-- (b) Protección de la tabla `logs`: sin UPDATE, y sin DELETE de
--     registros con menos de 90 días (retención mínima de auditoría).
--
-- Ejecutar UNA vez en el SQL Editor de Supabase (proyecto DEMO),
-- después de 001_auditoria_agentes_ia.sql.
-- ============================================================

-- ------------------------------------------------------------
-- (a) SESIONES
-- ------------------------------------------------------------
create table if not exists public.sesiones_app (
    token_hash        text primary key,          -- sha256 del token; el token en claro nunca se guarda
    ambito            text not null,             -- 'admin' | 'red'
    sujeto            text not null,             -- usuario administrador o nombre de red
    datos             jsonb not null default '{}'::jsonb,
    ip                text,
    inicio            timestamptz not null default now(),
    ultima_actividad  timestamptz not null default now(),
    constraint sesiones_app_ambito_chk check (ambito in ('admin', 'red'))
);
create index if not exists sesiones_app_sujeto_idx on public.sesiones_app (ambito, sujeto);
create index if not exists sesiones_app_actividad_idx on public.sesiones_app (ultima_actividad);

comment on table public.sesiones_app is
  'Sesiones de la app (admin y red). Expiran a las 8 h o tras 30 min de inactividad; la app las valida en cada petición.';

-- Intentos fallidos / bloqueos temporales (por sujeto y por IP)
create table if not exists public.intentos_login (
    clave            text primary key,           -- '<ambito>:<sujeto|ip>:<valor>'
    intentos         integer not null default 0,
    ultimo_intento   timestamptz,
    bloqueado_hasta  timestamptz
);

-- Limpieza opcional de sesiones vencidas (ejecutar a mano o con pg_cron):
--   delete from public.sesiones_app
--    where inicio < now() - interval '8 hours' or ultima_actividad < now() - interval '30 minutes';
--   delete from public.intentos_login where coalesce(bloqueado_hasta, ultimo_intento) < now() - interval '1 day';

alter table public.sesiones_app   enable row level security;
alter table public.intentos_login enable row level security;

-- La app accede con su clave de servidor; estas políticas permiten operar
-- desde ella. Si se usa la clave `anon`, ajustar a los roles reales.
drop policy if exists sesiones_app_all on public.sesiones_app;
create policy sesiones_app_all on public.sesiones_app
    for all to anon, authenticated, service_role using (true) with check (true);

drop policy if exists intentos_login_all on public.intentos_login;
create policy intentos_login_all on public.intentos_login
    for all to anon, authenticated, service_role using (true) with check (true);

-- ------------------------------------------------------------
-- (b) LOGS: inmutables y con retención mínima de 90 días
-- ------------------------------------------------------------
create or replace function public.fn_logs_proteger()
returns trigger
language plpgsql
as $$
begin
    if tg_op = 'UPDATE' then
        raise exception 'La tabla logs es inmutable: no se permite UPDATE (id=%)', old.id
            using errcode = 'P0001';
    end if;
    if tg_op = 'DELETE' and old.fecha > now() - interval '90 days' then
        raise exception 'Retención de auditoría: no se pueden borrar logs con menos de 90 días (id=%, fecha=%)', old.id, old.fecha
            using errcode = 'P0001';
    end if;
    return old;
end;
$$;

drop trigger if exists trg_logs_proteger on public.logs;
create trigger trg_logs_proteger
    before update or delete on public.logs
    for each row execute function public.fn_logs_proteger();

create or replace function public.fn_logs_sin_truncate()
returns trigger
language plpgsql
as $$
begin
    raise exception 'La tabla logs no admite TRUNCATE' using errcode = 'P0001';
end;
$$;

drop trigger if exists trg_logs_sin_truncate on public.logs;
create trigger trg_logs_sin_truncate
    before truncate on public.logs
    for each statement execute function public.fn_logs_sin_truncate();

-- ============================================================
-- Verificación rápida (opcional):
--   update public.logs set detalle = 'x' where id = (select max(id) from public.logs);  -- debe fallar
--   delete from public.logs where id = (select max(id) from public.logs);               -- debe fallar
-- ============================================================


-- ############################################################
-- ##### 52_agente_operativo.sql
-- ############################################################

-- ============================================================
-- 52_agente_operativo.sql  (SIREA 3.0)
-- Tablas del Agente Operativo: corridas (con traza paso a paso), cola de
-- acciones propuestas con aprobación humana, memoria por red y resultados
-- de las evaluaciones que habilitan cada skill.
--
-- Seguro de repetir. Ejecutar en el SQL Editor de Supabase después de
-- 50_auditoria_agentes_ia.sql.
-- ============================================================

-- 1) Corridas del agente (una por skill y disparo) ---------------------------
create table if not exists public.agente_corridas (
  id bigserial primary key,
  skill text not null,
  skill_version text not null,
  skill_hash text not null,
  disparo text not null default 'manual' check (disparo in ('manual', 'programado', 'evaluacion')),
  usuario text not null default 'SYSTEM',
  inicio timestamp with time zone not null default now(),
  fin timestamp with time zone null,
  estado text not null default 'EN_CURSO' check (estado in ('EN_CURSO', 'COMPLETADA', 'PARCIAL', 'FALLIDA', 'BLOQUEADA')),
  proveedor text null,
  n_casos integer not null default 0,
  n_propuestas integer not null default 0,
  n_descartadas integer not null default 0,
  n_sin_accion integer not null default 0,
  resumen text null,
  error text null
);
create index if not exists idx_agente_corridas_inicio on public.agente_corridas (inicio desc);

-- 2) Traza (observabilidad): qué vio, qué consultó y qué decidió en cada caso -
create table if not exists public.agente_traza (
  id bigserial primary key,
  corrida_id bigint not null references public.agente_corridas (id) on delete cascade,
  fecha timestamp with time zone not null default now(),
  caso text null,                       -- p. ej. 'red:PUNO' u 'observacion:123'
  tipo text not null check (tipo in ('CASO', 'HERRAMIENTA', 'PROPUESTA', 'DESCARTADA', 'SIN_ACCION', 'REGLA', 'ERROR')),
  detalle jsonb not null default '{}'::jsonb
);
create index if not exists idx_agente_traza_corrida on public.agente_traza (corrida_id, id);

-- 3) Cola de acciones propuestas (Human-in-the-loop) -------------------------
create table if not exists public.agente_acciones (
  id bigserial primary key,
  corrida_id bigint null references public.agente_corridas (id) on delete set null,
  skill text not null,
  skill_version text not null,
  tipo text not null,
  red text null,
  semana integer null,
  anio integer null,
  objetivo_ref text null,               -- p. ej. id de la observación
  clave_unica text not null,            -- evita proponer dos veces lo mismo mientras está abierta
  payload jsonb not null default '{}'::jsonb,
  justificacion text null,
  evidencia jsonb not null default '{}'::jsonb,
  origen text not null default 'ia' check (origen in ('ia', 'regla')),
  proveedor text null,
  estado text not null default 'PROPUESTA'
    check (estado in ('PROPUESTA', 'EJECUTADA', 'FALLIDA', 'RECHAZADA', 'VENCIDA')),
  creada_at timestamp with time zone not null default now(),
  decidida_por text null,
  decidida_at timestamp with time zone null,
  motivo_decision text null,
  editada boolean not null default false,
  ejecutada_at timestamp with time zone null,
  resultado text null
);
create unique index if not exists uq_agente_acciones_abierta
  on public.agente_acciones (clave_unica) where estado = 'PROPUESTA';
create index if not exists idx_agente_acciones_estado on public.agente_acciones (estado, creada_at desc);
create index if not exists idx_agente_acciones_red on public.agente_acciones (red, creada_at desc);

-- 4) Memoria por red (notas que el agente lee en cada corrida) ---------------
create table if not exists public.agente_memoria_red (
  id bigserial primary key,
  red text not null,
  nota text not null check (char_length(nota) <= 400),
  fuente text not null default 'humano' check (fuente in ('humano', 'agente')),
  accion_id bigint null,
  creada_por text not null default 'SYSTEM',
  creada_at timestamp with time zone not null default now(),
  vigente_hasta date null,
  activa boolean not null default true
);
create index if not exists idx_agente_memoria_red on public.agente_memoria_red (red, activa);

-- 5) Evaluaciones (compuerta de activación por versión de skill) -------------
create table if not exists public.agente_evals (
  id bigserial primary key,
  fecha timestamp with time zone not null default now(),
  skill text not null,
  skill_version text not null,
  skill_hash text not null,
  usuario text not null default 'SYSTEM',
  modo text not null default 'ia' check (modo in ('ia', 'sin_ia')),
  proveedor text null,
  total integer not null,
  aprobados integer not null,
  puntaje numeric(5, 4) not null,
  detalle jsonb not null default '[]'::jsonb
);
create index if not exists idx_agente_evals_skill on public.agente_evals (skill, skill_hash, fecha desc);

-- 6) Seguridad: solo la clave de servidor ----------------------------------
do $$
declare t text;
begin
  foreach t in array array['agente_corridas', 'agente_traza', 'agente_acciones', 'agente_memoria_red', 'agente_evals'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon, authenticated', t);
    execute format('grant all on public.%I to service_role', t);
    execute format('revoke all on sequence public.%I from anon, authenticated', t || '_id_seq');
    execute format('grant all on sequence public.%I to service_role', t || '_id_seq');
  end loop;
end $$;

-- La traza y las evaluaciones son evidencia: no se modifican ni se borran.
create or replace function public.fn_agente_evidencia_inmutable() returns trigger
language plpgsql as $$
begin
  raise exception 'La tabla % es evidencia del agente: no se permite % ', tg_table_name, tg_op;
end $$;

drop trigger if exists trg_agente_traza_inmutable on public.agente_traza;
create trigger trg_agente_traza_inmutable before update or delete on public.agente_traza
  for each row execute function public.fn_agente_evidencia_inmutable();

drop trigger if exists trg_agente_evals_inmutable on public.agente_evals;
create trigger trg_agente_evals_inmutable before update or delete on public.agente_evals
  for each row execute function public.fn_agente_evidencia_inmutable();

-- Estado inicial: el agente operativo nace INACTIVO (se activa desde el panel, tras pasar las evaluaciones).
insert into public.configuracion (clave, valor, fecha_actualizacion)
values ('agentes_ia_estado_operativo', 'INACTIVO', now())
on conflict (clave) do nothing;


-- ############################################################
-- ##### 53_skill_versiones.sql
-- ############################################################

-- ============================================================
-- 53_skill_versiones.sql  (SIREA 3.1)
-- Versiones de las skills propuestas por el agente a partir de los
-- rechazos de las personas ("aprender de los rechazos").
--
-- Flujo: el agente PROPONE una versión (agrega "ajustes aprendidos" al
-- procedimiento) -> un SUPER_ADMIN la APRUEBA o la RECHAZA -> la versión
-- aprobada tiene otra huella, así que debe volver a pasar las evaluaciones
-- antes de operar. El texto de cada versión no se edita (solo cambia su
-- estado). Sin esta tabla, el agente usa las skills del repositorio.
--
-- Seguro de repetir. Ejecutar después de 52_agente_operativo.sql.
-- ============================================================

create table if not exists public.agente_skill_versiones (
  id bigserial primary key,
  skill text not null,
  version text not null,
  version_base text not null,           -- versión sobre la que se propuso
  huella text not null,                 -- SHA-256 del texto completo
  texto text not null,                  -- la skill completa (encabezado + procedimiento)
  ajustes jsonb not null default '[]'::jsonb,   -- [{regla, por_que}] agregados
  evidencia jsonb not null default '{}'::jsonb, -- diagnóstico y rechazos usados
  origen text not null default 'mejora_ia' check (origen in ('mejora_ia', 'manual')),
  proveedor text null,
  estado text not null default 'PROPUESTA'
    check (estado in ('PROPUESTA', 'APROBADA', 'RECHAZADA', 'REEMPLAZADA')),
  creada_at timestamp with time zone not null default now(),
  creada_por text not null default 'SYSTEM',
  decidida_por text null,
  decidida_at timestamp with time zone null,
  motivo_decision text null
);
create index if not exists idx_skill_versiones on public.agente_skill_versiones (skill, estado, creada_at desc);
-- Solo una versión aprobada vigente por skill.
create unique index if not exists uq_skill_version_aprobada
  on public.agente_skill_versiones (skill) where estado = 'APROBADA';

alter table public.agente_skill_versiones enable row level security;
revoke all on public.agente_skill_versiones from anon, authenticated;
grant all on public.agente_skill_versiones to service_role;
revoke all on sequence public.agente_skill_versiones_id_seq from anon, authenticated;
grant all on sequence public.agente_skill_versiones_id_seq to service_role;

-- El texto, la huella y la evidencia de una versión no cambian nunca; solo su estado y la decisión.
create or replace function public.fn_skill_version_texto_fijo() returns trigger
language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Las versiones de skills son evidencia: no se borran.';
  end if;
  if new.texto is distinct from old.texto or new.huella is distinct from old.huella
     or new.evidencia is distinct from old.evidencia or new.skill is distinct from old.skill
     or new.version is distinct from old.version then
    raise exception 'El texto de una versión de skill no se modifica: proponga una versión nueva.';
  end if;
  return new;
end $$;

drop trigger if exists trg_skill_version_texto_fijo on public.agente_skill_versiones;
create trigger trg_skill_version_texto_fijo before update or delete on public.agente_skill_versiones
  for each row execute function public.fn_skill_version_texto_fijo();


-- ############################################################
-- ##### 54_sirea_3_2.sql
-- ############################################################

-- ============================================================
-- 54_sirea_3_2.sql  (SIREA 3.2)
-- 1) agente_atrasos_justificados: semanas en que un administrador indicó
--    que el atraso de una red tuvo una causa válida (feriado, caída del
--    sistema...). Esas semanas NO cuentan en los patrones de la red.
-- 2) agente_informes: informe semanal para la Jefatura. El sistema arma los
--    datos y un texto base; la IA propone una redacción verificada; una
--    persona elige, edita y APRUEBA. Un informe aprobado no se modifica ni se
--    borra (es evidencia).
--
-- Seguro de repetir. Ejecutar después de 53_skill_versiones.sql.
-- ============================================================

-- 1) Atrasos justificados ------------------------------------------------
create table if not exists public.agente_atrasos_justificados (
  id bigserial primary key,
  red text not null,
  anio integer not null,
  semana integer not null check (semana between 1 and 53),
  motivo text not null check (char_length(motivo) between 5 and 300),
  creado_por text not null default 'SYSTEM',
  creado_at timestamp with time zone not null default now(),
  activo boolean not null default true
);
create unique index if not exists uq_atraso_justificado_activo
  on public.agente_atrasos_justificados (red, anio, semana) where activo;
create index if not exists idx_atraso_justificado_red on public.agente_atrasos_justificados (red, anio, semana);

alter table public.agente_atrasos_justificados enable row level security;
revoke all on public.agente_atrasos_justificados from anon, authenticated;
grant all on public.agente_atrasos_justificados to service_role;
revoke all on sequence public.agente_atrasos_justificados_id_seq from anon, authenticated;
grant all on sequence public.agente_atrasos_justificados_id_seq to service_role;

-- Una justificación no se borra: se desactiva (queda quién y por qué).
create or replace function public.fn_atraso_justificado_sin_borrar() returns trigger
language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Las justificaciones de atraso no se borran: desactívelas (activo = false).';
  end if;
  if new.red is distinct from old.red or new.anio is distinct from old.anio or new.semana is distinct from old.semana
     or new.motivo is distinct from old.motivo or new.creado_por is distinct from old.creado_por then
    raise exception 'Una justificación no se edita: desactívela y registre otra.';
  end if;
  return new;
end $$;

drop trigger if exists trg_atraso_justificado_sin_borrar on public.agente_atrasos_justificados;
create trigger trg_atraso_justificado_sin_borrar before update or delete on public.agente_atrasos_justificados
  for each row execute function public.fn_atraso_justificado_sin_borrar();

-- 2) Informes semanales ---------------------------------------------------
create table if not exists public.agente_informes (
  id bigserial primary key,
  anio integer not null,
  semana integer not null check (semana between 1 and 53),
  estado text not null default 'BORRADOR' check (estado in ('BORRADOR', 'APROBADO', 'DESCARTADO')),
  datos jsonb not null default '{}'::jsonb,     -- cifras calculadas por el sistema (sin IA)
  texto_sistema text not null,                  -- texto base del sistema (sin IA)
  texto_ia text null,                           -- redacción de la IA que pasó los controles (o null)
  origen_sugerido text not null default 'sistema' check (origen_sugerido in ('ia', 'sistema')),
  proveedor text null,
  nota_ia text null,                            -- por qué no hay redacción de la IA, si no la hay
  creado_por text not null default 'SYSTEM',
  creado_at timestamp with time zone not null default now(),
  texto_final text null,                        -- lo que aprobó la persona (editado o no)
  origen_final text null check (origen_final in ('ia', 'sistema')),
  editado boolean null,
  aprobado_por text null,                       -- quién aprobó o descartó
  aprobado_at timestamp with time zone null,
  motivo_descarte text null
);
create index if not exists idx_informes_semana on public.agente_informes (anio, semana, estado);
create index if not exists idx_informes_fecha on public.agente_informes (creado_at desc);

alter table public.agente_informes enable row level security;
revoke all on public.agente_informes from anon, authenticated;
grant all on public.agente_informes to service_role;
revoke all on sequence public.agente_informes_id_seq from anon, authenticated;
grant all on sequence public.agente_informes_id_seq to service_role;

-- Los datos y los textos propuestos son evidencia; un informe decidido ya no cambia.
create or replace function public.fn_informe_inmutable() returns trigger
language plpgsql as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Los informes semanales son evidencia: no se borran (descarte el borrador).';
  end if;
  if new.datos is distinct from old.datos or new.texto_sistema is distinct from old.texto_sistema
     or new.texto_ia is distinct from old.texto_ia or new.anio is distinct from old.anio or new.semana is distinct from old.semana then
    raise exception 'Los datos y los textos propuestos de un informe no se modifican: prepare un borrador nuevo.';
  end if;
  if old.estado <> 'BORRADOR' then
    raise exception 'Un informe ya aprobado o descartado no se modifica: prepare uno nuevo.';
  end if;
  return new;
end $$;

drop trigger if exists trg_informe_inmutable on public.agente_informes;
create trigger trg_informe_inmutable before update or delete on public.agente_informes
  for each row execute function public.fn_informe_inmutable();

-- Que las tablas que se creen después también queden accesibles.
alter default privileges in schema public grant all on tables    to service_role;
alter default privileges in schema public grant all on sequences to service_role;
alter default privileges in schema public grant all on functions to service_role;


-- ############################################################
-- ##### 00_reparar_permisos_service_role.sql
-- ############################################################

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


-- ############################################################
-- ##### Comprobación: debe decir «OK» en todas las filas
-- ############################################################
select t.tabla,
       case when to_regclass('public.' || t.tabla) is null then 'FALTA' else 'OK' end as estado
from (values (1, 'administradores'), (2, 'envios'), (3, 'configuracion'), (4, 'logs'), (5, 'solicitudes_password'), (6, 'solicitudes_password_mensajes'), (7, 'cierres_corte'), (8, 'destinatarios_externos'), (9, 'respaldos'), (10, 'auditoria_acciones'), (11, 'permisos_operaciones'), (12, 'descargas_masivas'), (13, 'solicitudes_retiro'), (14, 'retiros_archivos'), (15, 'observaciones_envio'), (16, 'auditoria_agentes_ia'), (17, 'sesiones_app'), (18, 'intentos_login'), (19, 'agente_corridas'), (20, 'agente_traza'), (21, 'agente_acciones'), (22, 'agente_memoria_red'), (23, 'agente_evals'), (24, 'agente_skill_versiones'), (25, 'agente_atrasos_justificados'), (26, 'agente_informes')) as t(orden, tabla)
order by t.orden;

-- Fin: base lista para SIREA 3.2. Compruebe también con: python verificar_despliegue.py

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

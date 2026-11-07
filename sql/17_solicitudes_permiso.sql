-- ============================================================
-- 17 · Solicitudes de permiso (v7.6)
-- ============================================================
-- Permite que una cuenta SIN permiso lo pida desde la pantalla
-- (cuadro «Solicitar acceso») y que el SUPER_ADMIN principal
-- (oiis.winepi) lo apruebe o rechace desde Permisos de operación.
--
-- Solo crea una tabla nueva. No toca datos existentes.
-- Se puede ejecutar varias veces sin problema.
-- Si NO lo ejecuta, la solicitud igual llega por correo al principal
-- y queda en el «Control de actividad»; solo no habrá pantalla de
-- aprobación ni seguimiento del estado.
-- ============================================================

create table if not exists public.solicitudes_permiso (
  id bigserial primary key,
  usuario text not null,
  nombre text null,
  permiso text not null
    check (permiso in ('DESCARGA_MASIVA','RETIRO_REPOSITORIO','RESPALDO_MANUAL','VER_AUDITORIA','CONFIGURACION')),
  mensaje text not null,
  estado text not null default 'PENDIENTE'
    check (estado in ('PENDIENTE','APROBADA','RECHAZADA','CANCELADA')),
  creada_en timestamp with time zone not null default now(),
  resuelta_por text null,
  resuelta_en timestamp with time zone null,
  respuesta text null
);

-- Una sola solicitud pendiente de cada tipo por persona.
create unique index if not exists uq_solicitud_permiso_pendiente
  on public.solicitudes_permiso (usuario, permiso) where estado = 'PENDIENTE';
create index if not exists idx_solicitud_permiso_estado
  on public.solicitudes_permiso (estado, creada_en desc);
create index if not exists idx_solicitud_permiso_usuario
  on public.solicitudes_permiso (usuario, creada_en desc);

-- Fin de 17_solicitudes_permiso.sql

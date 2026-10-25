# SQL de SIREA · orden de ejecución (Supabase → SQL Editor)

## La forma fácil: un solo archivo

**`ACTUALIZAR_TODO_SIREA_3_2.sql`** junta, en el orden correcto, todos los scripts de abajo
(menos el `99` de limpieza). Péguelo completo en Supabase → SQL Editor → **Run**. Sirve venga de la
versión que venga (SIRE v3 a v7.2, SIREA 1.x a 3.1) y se puede ejecutar las veces que quiera: lo que
ya existe lo salta y **no borra datos**. Al final muestra una tabla: todas las filas deben decir **OK**.

**SIREA 3.3 no trae SQL nuevo**: si ya ejecutó el de 3.2, no tiene que hacer nada en la base.

(Probado dos veces seguidas sobre PostgreSQL 16 sin errores. `ACTUALIZAR_TODO_SIREA_3_1.sql` queda solo como referencia.)

## Los scripts por separado (si prefiere ir uno por uno)

Todos los scripts son seguros de repetir: si la tabla o columna ya existe, no hacen nada.
Ejecútelos en este orden; los que ya corrió antes puede volver a correrlos sin riesgo.

| # | Script | Qué hace | Origen |
|---|--------|----------|--------|
| 0 | `00_reparar_permisos_service_role.sql` | **Solo si la app muestra `permission denied for table …` (42501)** | SIREA |
| 1 | `09_solicitudes_cambio_password.sql` | solicitudes de contraseña de las redes | SIRE v3 |
| 2 | `10_programador_cierres_respaldos.sql` | cierres de corte, respaldos, destinatarios externos | SIRE v5 |
| 3 | `11_auditoria_permisos_repositorio.sql` | auditoría encadenada, permisos, descargas, retiros | SIRE v6 |
| 4 | `12_envios_detalle_archivos.sql` | duplicados exactos por centro + tipo y huellas de archivos | SIRE v6.8 |
| 5 | `13_observaciones_envio.sql` | bandeja «Observaciones» (comentarios y envíos por revisar) | SIRE v7 |
| 6 | `14_observaciones_categorias.sql` | categoría FALLA y datos para reintentar | SIRE v7.1 |
| 7 | `50_auditoria_agentes_ia.sql` | auditoría inmutable de la IA | SIREA |
| 8 | `51_sesiones_e_intentos_login.sql` | sesiones e intentos de login persistentes | SIREA |
| 9 | `52_agente_operativo.sql` | **nuevo de SIREA 3.0**: corridas, traza, cola de acciones, memoria por red y evaluaciones | SIREA 3.0 |
| 10 | `53_skill_versiones.sql` | versiones de las skills aprendidas de los rechazos | SIREA 3.1 |
| 11 | `54_sirea_3_2.sql` | **nuevo de SIREA 3.2**: atrasos justificados (no cuentan en los patrones) e informes semanales | SIREA 3.2 |
| — | `99_limpieza_previa_a_produccion.sql` | **opcional**: borra datos de prueba antes de producción (por defecto en seco) | SIRE v6.7 |

**Si ya tenía SIREA 3.1**, lo nuevo es `54`. **Si tenía SIREA 3.0**, ejecute `53` y `54`. **Si venía de SIREA 2.x**, ejecute `13`, `14` (si venía de SIRE v6.9), `52`, `53` y `54`.

Para comprobar todo de una vez: `python verificar_despliegue.py` (no muestra secretos ni cambia datos).

## Datos sintéticos para probar la semana 40 (solo base DEMO)

| Script | Qué hace |
|---|---|
| `DEMO_semana_40_datos_sinteticos.sql` | Con sus redes y centros: historial de las semanas 30-39 (redes que suelen atrasarse, una que mejora, otra que empeora, las demás puntuales) y la semana 40 a medio camino (completas, falta Emergencia u Hospitalización de un centro, falta la mitad de los centros, una sin envío). Deja la semana 40 activa con el corte en 2 días. Se puede repetir |
| `DEMO_semana_40_borrar.sql` | Borra esos envíos y devuelve la semana activa y el corte que había antes |

Todo queda marcado (`DEMO-SIM-…`, correos en example.org). Los recordatorios simulados que quedan en `logs` no se pueden
borrar antes de 90 días (política de auditoría de `sql/51`); están marcados con usuario `DEMO-SIM`.

# SIREA 3.3 · Quipu, Gobernanza de IA aparte, informe en PDF, filtros comunes y refresco sin perder la sesión

**Fecha:** 24/10/2026 · sobre SIREA 3.2. No requiere SQL nuevo.

| | Qué | Dónde |
|---|---|---|
| ➕ | **Quipu, el asistente de bolsillo**: botón flotante abajo a la derecha en todas las pantallas del panel; se abre en una cajita y se puede **ampliar**. Sugiere preguntas según la pantalla y recibe como contexto la semana y la red elegidas. Va en un fragmento: preguntar no recarga la pantalla de atrás. Reemplaza al asistente de la barra lateral (mismos controles: solo lectura, guardrails, 30 preguntas/hora, todo en el Historial de IA) | `app_pages/quipu.py` |
| 🔁 | **«Gobernanza de IA», módulo aparte** para lo que explica y controla la IA: Cómo funciona, Rondas del agente, Procedimientos, Evaluaciones, Memoria, Encender y apagar, Historial de IA. **«Agente de IA»** queda solo con lo que sirve para trabajar: Pendientes, Bandeja, Patrones, Informe semanal | `admin_agentes_ia.mostrar_gobernanza_ia` |
| ➕ | **Informe semanal en PDF** con formato institucional: logos de EsSalud y OIIS, datos del documento, recuadro de cifras del sistema, **marca de agua de la OIIS** y sello «BORRADOR» hasta que se apruebe | `src/informe_pdf.py`, `informe_semanal.a_pdf` |
| ➕ | **Filtro común Año · Semana · Red** en Panel de control, Seguimiento, Control de atrasos, Notificaciones, Patrones e Informe semanal (Red en la Bandeja; Progreso arranca con lo elegido). Lo que elige se mantiene al cambiar de módulo y al refrescar; «Semana activa» lo deshace | `app_pages/filtro_periodo.py` |
| 🔧 | **El Panel de control mezclaba años**: contaba la semana N de todos los años; ahora cuenta solo el año elegido y lee de 1000 en 1000 (antes se cortaba en 1000 filas) | `db_manager.obtener_estadisticas_semana` |
| ➕ | **Notificaciones con responsables sugeridos**: al elegir la red, el sistema lista a quienes de verdad enviaron por ella (8 semanas); al elegir a uno se llenan nombre, apellido y correo, y los demás quedan **en copia** (editable) | `admin_notificaciones._sugerir_responsables` |
| 🔧 | **Refrescar (F5) ya no saca del panel**: se recupera la sesión (cookie con el token, SameSite=Strict) y se vuelve a la misma sección y semana. Si una sección falla, se muestra el aviso con «Reintentar» sin perder el menú | `app_pages/admin.py`, `app.py` |
| 🔧 | **«Historial y logs» daba error** con fechas sin microsegundos; ahora se leen en formato ISO y se muestran en hora de Lima | `admin_historial.py` |

**Puesta en marcha:** `pip install -r requirements.txt` (agrega `reportlab` para el PDF). No hay cambios en la base.

**Verificación:** 188 pruebas automáticas en verde y recorrido en navegador de 59 pantallas y flujos sin problemas (incluye Quipu
abierto/ampliado, descarga de los dos PDF, autollenado en Notificaciones, filtro compartido entre módulos y refresco F5 con
sesión, sección y semana conservadas).

---

# SIREA 3.2 · patrones, recordatorio formal, informe semanal y asistente en todas las pantallas

**Fecha:** 24/10/2026 · sobre SIREA 3.1.

| | Qué | Dónde |
|---|---|---|
| ➕ | **Patrones por red, sin IA**: qué tipos manda cada centro (C, H, E, leídos del nombre del archivo), qué le falta esta semana y cómo viene cada red (semanas tarde o incompletas, tipo que suele faltar, tendencia, si espera el recordatorio). Mínimo de 4 semanas para hablar de patrón; las semanas justificadas no cuentan; una red que mejora no se etiqueta | `src/agentes/patrones.py`, pestaña **Patrones** |
| ➕ | **Atrasos justificados**: el admin marca la semana (feriado, caída del sistema) y deja de contar | `patrones.marcar_justificado`, `sql/54` |
| 🔁 | **Recordatorio formal por tipo de reporte**: dice qué falta y de qué centro («Emergencia del Hospital X»); va al responsable del envío y en copia a los otros que enviaron por la red; borrador formal editable y **vista previa** del correo. Las comparaciones e historial de la red son **solo para el admin**: si la IA los pone en el mensaje, el sistema lo reemplaza por su borrador | `acciones.py`, `email_sender.componer_recordatorio` |
| 🔁 | **Aviso preventivo** a las redes que suelen atrasarse (24-72 h antes del corte); a las puntuales no se les escribe antes de tiempo | skill `seguimiento_red` **v1.1.0** |
| ➕ | **Informe semanal** para la Jefatura: datos del sistema + texto base sin IA + redacción de la IA con **cifras verificadas**; una persona elige, edita y aprueba; Word o correo. Los viernes queda un borrador listo | `src/agentes/informe_semanal.py`, pestaña **Informe semanal** |
| ➕ | **Asistente en la barra lateral de todas las pantallas**: consultas rápidas leyendo solo lo necesario de la base (7 herramientas nuevas de solo lectura); sabe en qué pantalla está; límite de 30 preguntas por hora | `app_pages/asistente_lateral.py`, `herramientas.py` |
| 🔁 | **Historial de IA**: todo lo que hizo la IA en palabras simples (función, qué pasó), con filtros, búsqueda, registro completo y descarga en CSV/Excel | pestaña **Historial de IA** |
| ➕ | **Historial simulado para la demo** (marcado DEMO-SIM, correos en example.org) y su borrado | `scripts/sembrar_historial_demo.py` |
| ➕ | 4 casos de evaluación nuevos (12 en seguimiento) | `casos_eval/seguimiento_red.json` |

**Puesta en marcha:** ejecutar `sql/54_sirea_3_2.sql` (o el combinado `ACTUALIZAR_TODO_SIREA_3_2.sql`); instalar
`python-docx` (`pip install -r requirements.txt`); correr de nuevo las evaluaciones de «Seguimiento de redes» (su huella cambió).
Para la demo: `python scripts/sembrar_historial_demo.py --confirmo-base-demo`.

**Evaluaciones sin IA:** Seguimiento de redes **9 de 12** (75 %); Revisión de observaciones **1 de 8** (12 %). Los patrones
los calcula el sistema, así que el aviso preventivo también lo hacen las reglas: la IA aporta donde hay que leer la
memoria, notar una solicitud de contraseña o dos recordatorios sin efecto, y en la redacción.

**Verificación:** 184 pruebas automáticas en verde (49 nuevas) y recorrido en navegador de 53 pantallas y flujos sin excepciones (incluye
Patrones, recordatorio con vista previa, informe aprobado y asistente lateral).

---

# SIREA 3.1 · el agente como asistente de los administradores

**Fecha:** 22/10/2026 · sobre SIREA 3.0.

| | Qué | Dónde |
|---|---|---|
| ➕ | **Centro de pendientes** (pestaña «Pendientes» de Agente de IA): redes atrasadas, observaciones, casos escalados, almacenamiento de Drive, duplicados, cierre de semana, respaldos y solicitudes; lo urgente primero y un botón a cada sección. Las reglas detectan; la IA solo donde hay que leer o decidir | `src/agentes/pendientes.py` |
| ➕ | **Sugerencias en su sección**: recordatorios en **Notificaciones**, propuestas de la bandeja en **Observaciones**; se aprueban ahí mismo | `app_pages/agente_sugerencias.py` |
| 🔧 | **Sin correos repetidos**: un solo registro de recordatorios (manuales + agente). El agente respeta las 20 h también ante envíos manuales; Notificaciones avisa si la red ya recibió uno o si hay uno sugerido | `acciones.recordatorios_manuales`, `admin_notificaciones.py` |
| ➕ | **Almacenamiento (uso restringido)**: sugiere qué semanas antiguas ya descargadas se pueden retirar; nunca borra | `pendientes.almacenamiento` |
| ➕ | **Aprender de los rechazos**: el agente propone ajustes a su skill; aprueba un SUPER_ADMIN; la versión nueva vuelve a pasar evaluaciones; se puede volver atrás y descargar el texto para el repositorio | `src/agentes/mejora.py`, `sql/53_skill_versiones.sql` |
| 🔁 | Skill «Seguimiento de redes» v1.0.0 aclara que un recordatorio manual cuenta igual (cambia su huella: correr sus evaluaciones) | `skills/seguimiento_red.md` |

**Puesta en marcha:** ejecutar `sql/53_skill_versiones.sql`; correr de nuevo las evaluaciones de «Seguimiento de redes».

**Verificación:** 135 pruebas automáticas en verde (12 nuevas); recorrido en navegador de **47 pantallas y flujos** sin
excepciones ni HTML visible (incluye Pendientes, sugerencias en Notificaciones y Observaciones, proponer y aprobar una mejora).

---

# SIREA 3.0 · Sistema de Recepción de Reportes Epidemiológicos con Agentes

**Base:** SIRE **v7.2** completo (incluye la bandeja «Observaciones» y el cierre manual) + IA reorganizada.
**Fecha:** 22/10/2026 · OIIS · EsSalud.

## En una frase

La IA deja de ser un adorno: un **Agente Operativo** revisa cada día hábil las redes con centros
pendientes y la bandeja de observaciones siguiendo **procedimientos escritos (skills)**, propone
acciones concretas y **una persona aprueba**; solo entonces el sistema envía, marca o reintenta.

## Qué hay de nuevo

| | Qué | Dónde |
|---|---|---|
| ➕ | **Agente Operativo** (harness): expediente → skill + IA → reglas → bandeja → ejecución → vuelve a mirar | `src/agentes/agente_operativo.py` |
| ➕ | **Skills** versionadas con huella SHA‑256: «Seguimiento de redes» (permitida) y «Revisión de observaciones» (restringida, piloto) | `src/agentes/skills/*.md`, `skills.py` |
| ➕ | **Acciones** con esquema fijo y reglas: centros reales, enfriamiento de 20 h, tope de 3 recordatorios, sin datos personales ni enlaces | `src/agentes/acciones.py` |
| ➕ | **Memoria por red** que el agente lee antes de decidir | `src/agentes/memoria.py` |
| ➕ | **Evaluaciones** con IA vs sin IA (16 casos) y **compuerta**: una skill solo opera si su versión exacta pasa su umbral | `src/agentes/evals.py`, `casos_eval/*.json` |
| ➕ | **Traza** de cada corrida (qué vio, consultó, propuso y descartó) | tablas `agente_corridas`, `agente_traza` |
| ➕ | Corrida automática en días hábiles desde `AGENTE_HORA` (programador y GitHub Actions) | `src/programador.py`, `.github/workflows/programador.yml` |
| ➕ | Recordatorio oficial con caja opcional «Mensaje de la OIIS» | `src/email_sender.enviar_recordatorio(mensaje_adicional=…)` |
| ➕ | SQL `52_agente_operativo.sql` (tablas, índice único de propuestas abiertas, traza y evaluaciones inmutables) | `sql/` |
| 🔁 | Menú «Asistentes de IA» → **«Agente de IA»** con pestañas Bandeja, Corridas, Skills, Evaluaciones, Memoria, Investigador, Estado, Auditoría | `app_pages/admin_agentes_ia.py` |
| ➖ | **Retirados por proporcionalidad**: redactor del informe, analista de control y pre‑evaluador de contraseñas (quedan en el catálogo como decisión documentada) | `src/agentes/estado.py` |
| ✔ | Investigador de cumplimiento, guardrails, auditoría inmutable, kill‑switch, Gemini → Groq: se mantienen | — |

## Evidencia de valor (evaluaciones sin IA)

| Skill | Reglas sin IA | Umbral para operar |
|---|---|---|
| Seguimiento de redes | 5 de 8 (62 %) | 85 % con IA |
| Revisión de observaciones | 1 de 8 (12 %) | 85 % con IA |

El puntaje **con IA** se obtiene en el panel (Evaluaciones) con la clave real; queda guardado por versión de skill.

## Puesta en marcha

1. Ejecutar `sql/52_agente_operativo.sql` (y `13`, `14` si venía de SIRE v6.9).
2. Agregar `AGENTE_HORA=9` y `AGENTE_PROGRAMADO=true` al `.env` / secretos (opcionales; esos son los valores por defecto).
3. Panel → **Agente de IA → Evaluaciones** → correr cada skill → **Estado → Activar la IA**.

## Verificación realizada

- **123 pruebas automáticas** en verde (25 nuevas del agente: skills, acciones, evaluaciones, compuerta, corrida, cola sin
  duplicados, aprobación por rol, edición, doble ejecución, PII, inyección, kill‑switch, vencimiento, programador, memoria).
- Recorrido en navegador automatizado con base e IA simuladas: **42 pantallas y flujos**, 0 excepciones, 0 HTML visible
  (incluye correr evaluaciones, correr ambas skills, ver la traza, aprobar, rechazar y agregar memoria).

---

# Historial de SIREA 1.x – 2.x

## SIREA 1.0 (15/10/2026)

**Base:** SIRE **v6.9** completo (sin quitar nada) + asistentes de IA de SIGRE, reenfocados.
**Fecha:** 15/10/2026 · OIIS · EsSalud.
El historial de SIRE (v3 → v6) se conserva en `CAMBIOS_SIRE_v6_historico.md`.

---

## 1. Qué es SIREA en una frase

SIRE tal como está, más un menú nuevo en el panel, **«Asistentes de IA»**, con
cuatro asistentes que se enganchan a pasos del sistema donde **ya decide una
persona**, un asistente evaluado y **no construido**, un botón de detención,
auditoría inmutable y dos proveedores de IA (Gemini principal, Groq respaldo).

## 2. Los asistentes (semáforo de usos · criterio C4)

| | Asistente | A qué paso de SIRE se engancha | Qué hace | Quién decide |
|---|---|---|---|---|
| 🟢 Permitido | **Investigador de cumplimiento** | Panel / Progreso por red | «¿Por qué la red X no cierra?» → cruza progreso, tardíos, duplicados, exclusiones, solicitudes abiertas, cierre e historial, y explica. Tool‑use multi‑paso controlado por SIREA. | Nadie: solo lectura |
| 🟢 Permitido | **Redactor del informe semanal** | Informe por semana → validación → envío a la entidad externa (v5) | Redacta el texto que acompaña al Excel de cumplimiento con las **mismas cifras del Excel**. Verifica cada cifra. | Un administrador aprueba o rechaza; solo el texto aprobado va en el correo |
| 🟢 Permitido | **Analista de control** | Trazabilidad → Control de actividad (v6) | Lee las señales de la auditoría encadenada y redacta el informe de control del periodo. **Seudonimizado**: el modelo ve «Administrador A, B…». | `oiis.winepi` valida |
| 🟡 Restringido (piloto) | **Pre‑evaluador de solicitudes** | Solicitudes de contraseña (v3) | Lee el sustento (sin nombre ni correo), aplica reglas de la política y sugiere aprobar / rechazar / pedir más información. | `oiis.winepi`, siempre; no hay botón de «aplicar». Se mide la coincidencia |
| 🔴 No permitido | **Soporte a las redes** (chatbot público) | Portal de la red | Evaluado y **no construido**. Tarjeta gris con razones y condiciones para reconsiderarlo. | — |

Reglas comunes: nacen **INACTIVOS**; se activan desde el panel (SUPER_ADMIN);
cualquier administrador puede **detenerlos todos**; ninguno envía ni cambia
nada por su cuenta; a los modelos nunca llegan nombres, correos ni IP; todo
queda en `auditoria_agentes_ia` (solo inserción, con triggers que impiden
modificar o borrar).

## 3. Colores (manual de identidad y señalética de EsSalud)

| Color | Código | Significado en EsSalud | En SIREA |
|---|---|---|---|
| Azul | `#0077C8` (Pantone 3005C) | Principal | Todo lo institucional (antes SIRE usaba `#006DB0`) |
| Celeste | `#41B6E6` (Pantone 298C) | Secundario | Fondos suaves, chips informativos |
| **Lila** | `#6E3FA3` | **Diagnóstico** | **Todo lo que produjo la IA** y aún no validó una persona: borradores, chips «Generado por IA», tarjetas de asistente, la «A» del logo |
| Verde | `#1E6B3A` | Tratamiento | Validado por una persona / completo |
| Rojo · Amarillo · Naranja · Gris | — | Emergencia · Consultas · — · Servicios | Tardío · observaciones · duplicado · inactivo / no autorizado (como en SIRE) |

Un borrador nace lila (borde punteado) y, cuando una persona lo aprueba, pasa a
verde (borde continuo): *Diagnóstico → Tratamiento*.

## 4. Archivos nuevos

| Archivo | Qué contiene |
|---|---|
| `src/agentes/proveedores.py` | Capa Gemini → Groq: interfaz neutra, herramientas en formato neutro, bucle de function‑calling controlado por SIREA (tope `IA_MAX_TOOL_CALLS`), conmutación automática, registro de `proveedor:modelo`. |
| `src/agentes/agente_investigador.py` | Asistente 1. Pipeline: estado → guardrail de entrada → herramientas → guardrail de salida → leyenda → auditoría. |
| `src/agentes/agente_resumen.py` | Asistente 2 (reescrito): datos de `src/resumen_excel.recolectar`, verificación de cifras, aprobación/rechazo, `narrativa_validada()` para el cierre. |
| `src/agentes/agente_control.py` | Asistente 3 (nuevo): lee `src/auditoria.py` (v6), seudonimiza, prioriza señales, informe con validación. |
| `src/agentes/agente_solicitudes.py` | Asistente 4 (nuevo, piloto): limpieza del sustento, reglas determinísticas, sugerencia con formato fijo, registro de coincidencia. |
| `src/agentes/estado.py` | Catálogo con ficha de gobernanza por asistente (nivel, riesgos, controles, marcos, condiciones), ciclo de vida y kill‑switch. |
| `src/agentes/herramientas.py` | Herramientas de solo lectura ampliadas (tardíos, duplicados, exclusiones, solicitudes, cierre, historial por red) + registro neutro. |
| `src/session_store.py` | Sesiones e intentos de login persistentes (de SIGRE), límites desde el `.env`. |
| `app_pages/admin_agentes_ia.py` | Pantalla «Asistentes de IA»: catálogo, kill‑switch, ciclo de vida, indicadores, auditoría. |
| `app_pages/agentes_ui.py` | Pestañas de cada asistente (chat, informe, control, piloto). |
| `utils/tema_ia.py` | Componentes lila/verde: borradores, chips, tarjetas de asistente, burbujas, chip «respondió Gemini/Groq». |
| `sql/50_auditoria_agentes_ia.sql`, `sql/51_sesiones_e_intentos_login.sql`, `sql/LEEME.md` | Scripts (de SIGRE) y orden de ejecución. |
| `tests/` | 98 pruebas sin red: guardrails (68), pipeline de asistentes (16), proveedores (8), sesiones (5)… + `fake_supabase.py`, `smoke_app.py`, `smoke_browser.py`. |
| `docs/GOBERNANZA_SIREA.md` | Tabla asistente → riesgo → control → marco, lineamientos y hoja de ruta (para el informe). |
| `docs/CHECKLIST_PRUEBA_REAL.md` | Los 10 pasos de la prueba con claves reales antes de desplegar. |
| `.env.example` | Plantilla de SIRE v6 + secciones 9 (IA) y 10 (sesiones). |

## 5. Archivos de SIRE modificados (poco y con cuidado)

- `utils/tema.py` — azul oficial, constantes `CELESTE` / `LILA`, tono `"ia"`, iconos `ia` y `lupa`, CSS de componentes de IA, botones `-lila` / `-rojo`, la «A» lila en marca y pie.
- `src/config.py` — sección «ASISTENTES DE IA» y «SESIONES» (variables del `.env`), `tiene_ia()`, `proveedores_ia_disponibles()`; `APP_NAME`.
- `src/auth.py`, `src/auth_red.py` — bloqueo persistente por usuario/red **y por IP**, expiración por inactividad; el resto intacto.
- `src/cierres.py` — en `_enviar_a_externos`, si hay narrativa **validada** del redactor para esa semana, se incluye en el correo a la entidad externa.
- `app_pages/admin.py` — grupo «Inteligencia artificial → Asistentes de IA» en el menú; «A» lila en la marca del panel.
- `app_pages/admin_solicitudes_password.py` — bloque del pre‑evaluador (solo `oiis.winepi`) y registro de coincidencia al aprobar/rechazar.
- `src/agentes/auditoria.py` — nombres de los asistentes, `referencia`, `anio/semana/modelo` en decisiones humanas, `ultima_aprobacion()`.
- Textos visibles: «SIRE» → «SIREA»; `docker-compose.yml`: `sirea-app`, `sirea-programador`; `requirements.txt`: `google-genai`, `httpx`, `pytest`.

Se retiraron de SIGRE (sustituidos): `agente_chatbot.py`, `agente_seguimiento.py`, `generador_pdf.py`, `src/tema.py` v2 (SIREA usa el tema de SIRE).

## 6. Puesta en marcha

1. Supabase (proyecto de **demo**): ejecutar en orden `sql/09`, `10`, `11`, `13` (ver `sql/LEEME.md`). `12` solo si no existe `auditoria_agentes_ia`.
2. Copiar `.env.example` a `.env` y completar: Supabase, Drive, correo, `GEMINI_API_KEY`, `GROQ_API_KEY` + `GROQ_MODEL`.
3. `docker compose up -d --build` (dos contenedores: `sirea-app` y `sirea-programador`), o sin Docker: `pip install -r requirements.txt` y `python -m streamlit run app.py`.
4. Entrar como `oiis.winepi` → **Asistentes de IA → Estado → Administrar el ciclo de vida** → poner el estado GLOBAL y cada asistente en **ACTIVO**. Nacen inactivos a propósito.
5. Seguir `docs/CHECKLIST_PRUEBA_REAL.md` (30 minutos).

## 7. Verificación realizada en esta entrega

- `python -m compileall` sin errores · `python -m pytest tests/ -q` → **98 pruebas correctas** (sin red ni claves).
- App levantada con base simulada (`tests/smoke_app.py`) y recorrida en navegador automatizado (`tests/smoke_browser.py`): **35 pantallas y flujos** (inicio, envío, portal de la red, acceso, las 20 secciones del panel, las 7 pestañas de Asistentes de IA, consulta al investigador, borrador y aprobación del informe, informe de control, sugerencia del pre‑evaluador) → **0 excepciones, 0 fragmentos de HTML visibles**.
- No probado desde aquí (requiere claves reales): llamadas a Gemini/Groq, Supabase, Drive y correo → checklist de mañana.

## 8. Pendiente (no bloqueante)

- Activar RLS en las tablas base de Supabase (hoy «UNRESTRICTED»); los scripts nuevos ya lo activan en las suyas.
- Exportar el informe semanal validado también en PDF (hoy va como texto en el correo + Excel adjunto).
- Las condiciones para que el pre‑evaluador pase a «permitido» y para reconsiderar el soporte a redes están en `src/agentes/estado.py` (`condiciones_futuras`) y en el panel.

---

## Parche 1 (17/10/2026) · tras la primera prueba real

- **Corregido:** la pestaña «Auditoría» de Asistentes de IA fallaba con `esc() takes 1 positional argument` cuando ya había
  registros (la prueba automatizada no lo detectó porque el mensaje de error controlado de `app.py` no se contaba como
  fallo; ahora sí se detecta y la BD simulada arranca con registros de auditoría).
- **Corregido:** el identificador del informe de control (`CTL-20261017-…`) era tomado por un DNI por el filtro de datos
  personales y se mostraba como `[DNI OMITIDO]`; ahora es `CTL-2026-10-17-…`.
- **Nuevo:** `sql/00_reparar_permisos_service_role.sql` para el error 42501 `permission denied for table …` (la clave de
  servidor sin privilegios sobre las tablas base). Se documenta en `sql/LEEME.md`.
- Si la base no tiene el usuario `oiis.winepi`: poner en `SUPERADMIN_PRINCIPAL` el usuario SUPER_ADMIN existente o crear
  la cuenta (ver el mensaje de soporte); el sistema funciona con cualquiera de las dos opciones.

## Parche 2 (17/10/2026) · claridad cuando la IA no responde y activación en un clic

- **Nuevo botón «Activar los 4 asistentes»** (SUPER_ADMIN): activa el estado global y cada asistente de una vez. Antes había
  que hacer cinco cambios uno por uno y era fácil quedarse con «1 de 4».
- **Nuevo botón «Probar los proveedores de IA»**: consulta a Gemini y a Groq con una pregunta mínima y muestra, por
  proveedor, si respondió o el motivo exacto del fallo (clave inválida, modelo inexistente, cuota, sin red).
- **Contingencia ya no se confunde con IA**: si ningún proveedor respondió, la tarjeta sale en gris con el chip
  «Plantilla de contingencia · sin IA» (no «Generado por IA») y un aviso rojo con el **motivo** del fallo.
- **Mensaje de «asistente no disponible» más claro**: distingue «estado GLOBAL detenido» de «este asistente aún no fue
  activado (cada uno se activa por separado)».
- Errores de Groq traducidos a mensajes accionables; `GEMINI_MODELOS_RESPALDO` configurable en el `.env`.
- 101 pruebas; recorrido en navegador ampliado (prueba de proveedores, activación en bloque).

## Parche 3 (17/10/2026) · módulo de IA más simple

- Se retiró de la interfaz la ficha de gobernanza de cada asistente (punto de control, riesgos, controles, marcos):
  esa información es del desarrollador y vive en `src/agentes/estado.py` (`CATALOGO`) y en `docs/GOBERNANZA_SIREA.md`.
- La primera pestaña se llama «Estado». Los textos explicativos de cada pestaña pasaron a un desplegable
  «¿Qué hace este asistente?» cerrado por defecto.
- Recorrido en navegador: 37 pantallas y flujos, 0 errores. 101 pruebas.

## Parche 4 (17/10/2026) · tras «Probar los proveedores de IA» con claves reales

- **Gemini**: `get_cliente_gemini()` (heredado de SIGRE) llamaba a `Config.gemini_configurado()`, que SIRE no tenía
  → «type object 'Config' has no attribute 'gemini_configurado'». Añadido a `Config` y cubierto por una prueba.
- **Groq**: `GROQ_MODEL=gpt-4o-mini` es un nombre de OpenAI, no de Groq. Ahora SIREA consulta el catálogo de Groq
  (`GET /models`) con su clave y, si el modelo configurado no existe, usa automáticamente el primero disponible de
  `GROQ_MODELOS_RESPALDO` (por defecto `llama-3.3-70b-versatile`, `openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
  `llama-3.1-8b-instant`, todos de la capa gratuita) y lo indica en la prueba de proveedores. El `.env.example` trae
  `GROQ_MODEL=llama-3.3-70b-versatile`. `GROQ_MODEL` ya no es obligatorio para que Groq cuente como configurado.
- 105 pruebas; 37 pantallas y flujos en navegador sin errores.

## Parche 5 (17/10/2026) · Investigador con Gemini 3 (error 400 en la segunda vuelta)

- Gemini respondía bien la primera llamada (pidió herramientas) pero rechazaba la segunda con 400. Causa: en modelos
  Gemini 2.5/3.x el turno del modelo debe reenviarse **intacto** (incluye las «thought signatures») y las respuestas de
  todas las herramientas de un turno deben ir **juntas** en un solo mensaje. Ahora se hace así, se propaga el `id` de
  cada llamada y se omiten las partes de «pensamiento» del texto final.
- El mensaje de error 400 de Gemini ya no dice siempre «nombre del modelo mal escrito»: muestra el detalle real.
- Si un proveedor falla **a mitad** de una conversación con herramientas, se reinicia la consulta desde cero con el
  siguiente (Groq) en lugar de abortar.
- 107 pruebas (incluye la regresión con `thought_signature`).

## v1.5 (18/10/2026) · listo para Streamlit Community Cloud

- La cuenta de servicio de Google se puede entregar como secreto `GOOGLE_CREDENTIALS_JSON` (o tabla
  `[gcp_service_account]`); al arrancar se crea `credentials/service_account.json`. En local nada cambia.
- `scripts/env_a_secrets.py`: convierte el `.env` y el JSON de Google en el texto para el cuadro «Secrets».
- `.github/workflows/programador.yml`: el proceso programado corre en GitHub Actions cada 15 min.
- `PROGRAMADOR_LATIDO_MAX_MIN` (5 en Docker, 40 en la nube) para el aviso de «programador detenido».
- `.gitignore` ampliado (secrets.toml, venv, logs, zips). Guía: `docs/DESPLIEGUE_STREAMLIT_CLOUD.md`.


## v2.0 (20/10/2026) · nueva base SIRE v6.9

SIREA se reconstruyó sobre **SIRE v6.9** (fusión de tres vías: v6 como base común, v6.9 y SIREA v1.5). Se conserva
todo lo de v6.1–v6.9 y todo lo de SIREA. Historial de SIRE en `CAMBIOS_SIRE_v6_historico.md`.

**Lo que trae v6.9 y ahora tiene SIREA:** validación del ZIP por nombre de archivo (tipo, semana, año y red), reenvíos
parciales con duplicado por centro + tipo, huellas SHA-256, conexión estable con Supabase en Windows
(`src/conexion_supabase.py`), IP de auditoría confiable solo con `PROXY_CONFIABLE=true`, HTTPS con Caddy,
`docker-entrypoint.sh` (credencial legible sin correr como root), fin del respaldo «local» silencioso, contraseñas
≤ 64 caracteres, `verificar_despliegue.py`, guías de despliegue y `sql/99_limpieza_previa_a_produccion.sql`.

**Ajustes de integración:**
- Los SQL de SIREA se renumeraron porque v6.8 ya usa el `12`: `12_auditoria_agentes_ia` → **`13`**,
  `13_sesiones_e_intentos_login` → **`14`**. Ver `sql/LEEME.md` (lo único nuevo para una base SIREA existente es
  `12_envios_detalle_archivos.sql`).
- El estado de los asistentes limpia la caché de configuración de v6.1 al guardarse (si no, el panel mostraba el estado
  anterior hasta 10 s).
- La IP para el bloqueo de login usa la misma regla que la auditoría de v6.1 (`X-Forwarded-For` solo con proxy confiable).
- `verificar_despliegue.py` revisa también las tablas de SIREA (13 y 14) y prueba los proveedores de IA.
- `.gitignore`/`.dockerignore` unen las reglas de ambos (incluye secretos de Streamlit Cloud). Se retiró un archivo
  `pglast-*.whl` (8 MB) que venía en la carpeta y no lo usa ningún archivo.
- 107 pruebas; 37 pantallas y flujos en navegador (incluido el nuevo formulario de envío) sin errores.

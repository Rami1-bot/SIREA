# Gobernanza de la IA de SIREA 3.3

Material para el informe y la exposición. Todo lo que dice esta página
existe en el código (se indica el archivo) y se puede mostrar en el panel
«Agente de IA». Las fichas de riesgos y controles **no** se muestran en la
interfaz: son responsabilidad del equipo que desarrolla y gobierna.

> Elaborado con apoyo de IA (Claude) y revisado por el equipo.

## 1. Qué cambió y por qué (principio de proporcionalidad)

SIREA 2.x tenía cuatro asistentes. Una auditoría interna concluyó que tres de
ellos eran **cosméticos**: hacían una sola llamada al modelo y su plan B sin IA
lograba casi lo mismo, mientras su gobierno costaba más código que su función.
SIREA 3.0 los **retira** (quedan en el catálogo como decisión documentada) y
concentra la IA donde la OIIS pierde más tiempo cada semana:

| Antes (2.x) | Ahora (3.0) | Motivo |
|---|---|---|
| Redactor del informe | ⚪ Retirado | La plantilla fija del cierre cumple la función |
| Analista de control | ⚪ Retirado | SIRE ya calcula las señales; la persona las lee directo |
| Pre‑evaluador de contraseñas | ⚪ Retirado | Decisión sobre personas, poco volumen, riesgo alto |
| Investigador | 🟢 Se mantiene | Explica cruzando seis fuentes: no lo hace una regla |
| — | 🟢/🟡 **Agente Operativo** (nuevo) | Seguimiento de redes y revisión de observaciones: trabajo diario, repetitivo y con texto libre |

En **3.2** vuelve un informe, pero **distinto y medido**: ya no es el texto que acompaña al Excel del cierre
(eso lo sigue haciendo la plantilla), sino un **informe de gestión** que interpreta patrones de varias semanas.
El sistema siempre redacta un texto base sin IA; la IA propone otra redacción con cifras verificadas, y el panel
cuenta cuántas veces la persona eligió una u otra. **Si casi siempre gana el texto del sistema, se retira**
(proporcionalidad aplicada con datos, no con opiniones).

## 2. Cómo funciona el Agente Operativo (en simple)

```
  Cada día hábil a las 9:00 (o al pulsar «Correr ahora»)
  ┌──────────────┐   ┌────────────────┐   ┌──────────────┐   ┌──────────────┐   ┌───────────┐
  │ 1. Expediente│ → │ 2. Skill + IA  │ → │ 3. Reglas    │ → │ 4. Bandeja   │ → │ 5. Sistema│
  │ (datos reales│   │ decide qué     │   │ descartan lo │   │ una persona  │   │ ejecuta   │
  │  + memoria + │   │ proponer       │   │ inválido     │   │ aprueba/edita│   │ y audita  │
  │  lo ya hecho)│   │                │   │              │   │ o rechaza    │   │           │
  └──────────────┘   └────────────────┘   └──────────────┘   └──────────────┘   └───────────┘
        ▲                                                                              │
        └──────────── al día siguiente vuelve a mirar si lo que se hizo funcionó ──────┘
```

| Pieza | Qué es | Archivo |
|---|---|---|
| **Skill** | Procedimiento escrito y aprobado por la OIIS (qué mirar, cómo decidir, qué puede proponer). Tiene versión y huella SHA‑256 | `src/agentes/skills/*.md`, `skills.py` |
| **Harness** | El ciclo de arriba: arma expedientes, llama al modelo, valida, encola, ejecuta tras aprobación | `agente_operativo.py` |
| **Acciones** | Catálogo cerrado: recordar a la red, pedir corrección, dar por revisada, reintentar falla, escalar, nota de memoria, no actuar. Cada una con esquema y reglas | `acciones.py` |
| **Memoria** | Notas breves por red que el agente lee antes de decidir; vencen solas | `memoria.py`, tabla `agente_memoria_red` |
| **Traza** | Paso a paso de cada corrida: qué vio, qué consultó, qué propuso, qué se descartó y por qué | tablas `agente_corridas`, `agente_traza` |
| **Evaluaciones** | 16 casos resueltos a mano. Se corren con IA y sin IA. Una skill solo opera si su versión exacta alcanza su umbral | `evals.py`, `casos_eval/*.json`, tabla `agente_evals` |

### Novedades de 3.1: el agente como asistente de los administradores

| Pieza | Qué hace | ¿IA? | Archivo |
|---|---|---|---|
| **Centro de pendientes** | Catálogo por secciones de todo lo que necesita a un admin, lo urgente primero: redes atrasadas, observaciones, casos escalados, almacenamiento de Drive, duplicados, cierre de semana, respaldos y solicitudes de contraseña. Cada tarjeta lleva a su sección | Solo en redes y observaciones; el resto lo detecta una **regla** | `pendientes.py` |
| **Sugerencias en su sección** | Los recordatorios sugeridos aparecen en **Notificaciones** y las propuestas sobre observaciones en **Observaciones**; se aprueban ahí mismo | Sí (propuestas del agente) | `app_pages/agente_sugerencias.py` |
| **Un solo registro de recordatorios** | Lo enviado a mano desde Notificaciones y lo enviado por el agente se cuentan juntos: nadie le escribe dos veces a una red en 20 h | No (regla) | `acciones.recordatorios_manuales`, `ultimo_recordatorio` |
| **Almacenamiento (uso restringido)** | Sugiere qué semanas antiguas ya descargadas se pueden retirar de Drive. **Nunca borra**: el retiro sigue en «Descarga y limpieza» con permisos, aprobación y papelera | No (regla) | `pendientes.almacenamiento` |
| **Aprender de los rechazos** | Con 3+ rechazos con motivo, el agente propone 1-3 reglas nuevas para su skill; un SUPER_ADMIN aprueba; la versión nueva debe volver a pasar las evaluaciones | Sí | `mejora.py`, `sql/53` |

Por qué Notificaciones **no** se entregó entera a la IA: si la IA está detenida o
los proveedores fallan, la OIIS debe poder seguir enviando recordatorios
(continuidad del servicio, ITIL; supervisión humana, OCDE). La IA sugiere; la
sección funciona igual sin ella.

### Novedades de 3.3: lo que explica la IA, aparte de lo que sirve para trabajar

- **«Agente de IA»** (trabajo diario): Pendientes, Bandeja, Patrones, Informe semanal.
- **«Gobernanza de IA»** (cómo funciona y cómo se controla): Cómo funciona, Rondas del agente, Procedimientos (skills),
  Evaluaciones, Memoria, Encender y apagar, Historial de IA. Así un administrador que no necesita los detalles no los
  ve mezclados con su trabajo, y quien audita los encuentra juntos.
- **Quipu** reemplaza al asistente de la barra lateral: mismo agente y mismos controles, ahora flotante y ampliable.
- **Informe en PDF** con sello «BORRADOR» mientras no lo apruebe una persona, y la leyenda de validación al aprobarlo:
  el documento mismo dice si ya lo revisó alguien (transparencia, principio 1.3 de la OCDE).

### Novedades de 3.2: patrones, recordatorio formal, informe y asistente

```
  Datos reales (envíos y nombres de archivo: C, H, E)
        │
        ▼
  ┌─────────────────────────────┐   El SISTEMA cuenta (sin IA): qué manda cada centro, qué le falta,
  │ Patrones (patrones.py)      │   semanas tarde, tipo que suele faltar, tendencia. Mín. 4 semanas;
  │ uso INTERNO del admin       │   las semanas justificadas no cuentan; quien mejora no se etiqueta.
  └─────────────┬───────────────┘
        ┌───────┴──────────────┬───────────────────────────┐
        ▼                      ▼                           ▼
  Recordatorio formal     Informe semanal             Asistente (todas las pantallas)
  (IA redacta, sistema    (texto del sistema + IA     (solo lectura, lee lo necesario,
   controla el tono)       con cifras verificadas)     responde con datos)
        │                      │                           │
        └──── una persona revisa, edita y aprueba ─────────┘  →  todo queda en el Historial de IA
```

| Pieza | Qué hace | ¿IA? | Archivo |
|---|---|---|---|
| **Patrones por red** | Tipos esperados por centro (aprendidos del historial), faltantes por tipo, semanas tarde o incompletas (algún centro o tipo sin llegar), tipo que suele faltar, tendencia, si espera el recordatorio. Lista de semanas como prueba | **No** (cuentas del sistema) | `patrones.py` |
| **Atrasos justificados** | El admin marca una semana con causa válida; deja de contar. No se borra: se desactiva | No | `patrones.marcar_justificado`, `sql/54` |
| **Recordatorio formal** | Detalle por tipo («Emergencia del Hospital X»), responsables reales en copia, borrador formal, vista previa. Lo interno (comparaciones, historial) nunca va al correo | Sí (redacta el párrafo; el sistema lo controla) | `acciones.py`, `email_sender.componer_recordatorio` |
| **Aviso preventivo** | Solo a redes con patrón, 24-72 h antes del corte | Regla de la skill v1.1.0 | `skills/seguimiento_red.md` |
| **Informe semanal** | Datos del sistema → texto base sin IA → redacción IA verificada → aprobación humana → Word/correo | Sí, opcional y medida | `informe_semanal.py` |
| **Quipu, asistente de bolsillo (todas las pantallas)** | Consultas rápidas con 20 herramientas de solo lectura; sabe en qué pantalla y semana está; 30 preguntas/hora | Sí | `quipu.py`, `agente_investigador.py` |
| **Historial de IA** | Todo lo que hizo la IA, en palabras simples, con filtros y descarga | No | pestaña «Historial de IA» |

### Skills vigentes

| Skill | Nivel | Puede proponer | Aprueba | Sin IA (reglas) |
|---|---|---|---|---|
| Seguimiento de redes con centros pendientes (v1.1.0) | 🟢 Permitido | Recordar (con detalle por tipo), escalar, nota de memoria, no actuar | ADMIN | **9 de 12** casos (75 %) |
| Revisión de observaciones de envíos | 🟡 Restringido (piloto) | Pedir corrección, dar por revisada, reintentar, escalar, nota, no actuar | SUPER_ADMIN | **1 de 8** casos (12 %) |

Las reglas solas no pasan el umbral (85 %): no leen la memoria, no notan que
dos recordatorios no funcionaron, no entienden un comentario libre ni detectan
un intento de manipulación. **Esa diferencia es la evidencia de que la IA aporta.**
En 3.2 la brecha de «Seguimiento» se achica a propósito: el aviso preventivo
depende de patrones que calcula el sistema, así que una regla también lo hace.
Se dice tal cual: la IA de esa skill aporta en el juicio (memoria, accesos,
escalar) y en la redacción, no en contar.

## 3. Matriz riesgo → control → evidencia en código → marco

| Riesgo | Control | Dónde | Marco |
|---|---|---|---|
| Correo a la red equivocada | El destinatario lo resuelve el **sistema** (último envío de la red), nunca el modelo; editable antes de aprobar; se revalida el formato | `acciones.responsable_de_red`, `revalidar_para_ejecutar` | COBIT DSS · OCDE robustez |
| Centros inventados en un recordatorio | Solo se aceptan centros que el sistema marca como pendientes; si no, se descarta y queda en la traza | `acciones._val_recordatorio` | OCDE exactitud |
| Molestar a una red (spam) | Enfriamiento de 20 h; máximo 3 recordatorios por semana; el tono lo fija el reloj, no el modelo | `acciones._val_recordatorio`, `_norm_recordatorio` | ITIL gestión de eventos |
| Dar por revisada una observación que pedía algo | La skill obliga a escalar ante pedidos o dudas; una FALLA nunca se marca como revisada | `skills/revision_observacion.md`, `acciones._val_revisada` | COBIT DSS02 |
| Texto de la red que intenta manipular al agente (inyección) | El expediente va entre `<datos_sistema>` como dato; la skill ordena escalar; las acciones tienen esquema cerrado | `guardrails.envolver_datos`, `procesar_propuesta` | OWASP LLM01 · OCDE seguridad |
| Datos personales al proveedor | El modelo nunca ve correo ni nombre del remitente (campos privados `_`); PII redactada en textos | `agente_operativo._publico`, `expedientes_revision` | Ley 29733 |
| Datos personales en lo que se envía | Una propuesta con correo, teléfono, DNI o enlace se **descarta** (no se redacta) | `acciones._problema_de_texto` | Ley 29733 |
| Acción fuera de lo aprobado | Solo las acciones que la skill declara; lo demás se descarta | `procesar_propuesta(permitidas)` | COBIT EDM |
| Cambiar la skill sin control | La huella SHA‑256 cambia y la skill queda **bloqueada** hasta volver a pasar evaluaciones | `evals.habilitada` | COBIT BAI06 · PRINCE2 control de cambios |
| Aprobación por inercia | Rechazo exige motivo; métricas de aprobación y «sin editar»; propuestas vencen a las 48 h | `agente_operativo.rechazar`, `metricas`, `vencer_propuestas_antiguas` | OCDE supervisión humana |
| Doble ejecución | La propuesta se «toma» con una actualización condicional; índice único de propuestas abiertas | `aprobar`, `sql/52` (`uq_agente_acciones_abierta`) | ITIL |
| Operar sin autorización | Nace INACTIVO; activar exige SUPER_ADMIN **y** una skill evaluada; kill‑switch para cualquier ADMIN | `estado.puede_cambiar`, `boton_de_panico` | COBIT EDM · OCDE rendición de cuentas |
| Perder la trazabilidad | Traza y evaluaciones inmutables (trigger); auditoría solo‑inserción con `proveedor:modelo` y referencia `ACC‑n` | `sql/52`, `sql/50`, `auditoria.py` | COBIT MEA03 |
| Correo duplicado a una red (Notificaciones + agente) | Registro único de recordatorios: el agente cuenta los manuales y Notificaciones avisa los recientes o sugeridos | `acciones.recordatorios_manuales`, `agente_sugerencias.aviso_recordatorio_reciente` | ITIL gestión de eventos |
| Borrado de archivos sugerido por una máquina | Almacenamiento solo **sugiere**; el retiro exige permiso, aprobación del SUPER_ADMIN principal y va a papelera | `pendientes.almacenamiento`, `src/repositorio.py` | COBIT DSS01 · OCDE supervisión humana |
| El agente se "auto‑mejora" sin control | Solo propone; encabezado copiado (no gana acciones ni cambia quién aprueba); reglas que relajan controles, con PII o con acciones ajenas se descartan; decide un SUPER_ADMIN; la nueva huella vuelve a pasar evaluaciones; texto inmutable (trigger); vuelta atrás con un clic | `mejora.validar_ajustes`, `construir_texto`, `sql/53`, `skills.cargar_todas` (verifica huella) | COBIT BAI06 · ITIL mejora continua · PRINCE2 control de cambios |
| Etiquetar injustamente a una red («suele atrasarse») | El patrón lo cuenta el sistema, no la IA; mínimo de 4 semanas con datos; semanas justificadas excluidas; antes del primer envío en SIREA no cuenta; si viene mejorando no se le etiqueta; siempre se muestran las semanas como prueba; uso solo interno | `patrones.Historial.perfil`, `marcar_justificado` | OCDE equidad y transparencia |
| Exponer o reprochar a una red en el correo | La skill lo prohíbe; el sistema revisa el párrafo (comparaciones, otras redes, «nuevamente», «6 de 8 semanas», tono) y lo reemplaza por su borrador formal, dejando constancia; el contexto interno nunca entra al correo | `acciones.problema_de_tono`, `_norm_recordatorio`, evaluación `sin_comparar` | OCDE respeto a las personas · ITIL comunicación |
| Copia a personas que no corresponden | En copia solo quienes **enviaron** por esa red en las últimas 8 semanas (máx. 2 sugeridos, 5 en total), editable y validado antes de enviar | `acciones.responsables_de_red`, `revalidar_para_ejecutar` | Ley 29733 · COBIT DSS |
| Informe con cifras inventadas | Datos calculados por el sistema; `verificar_cifras` descarta la redacción con un número que no está en los datos; formato obligatorio; siempre hay texto base sin IA | `informe_semanal.redactar_con_ia` | OCDE exactitud · Riesgo 4 |
| Informe alterado después de aprobado | Trigger: datos y textos propuestos no cambian; un informe decidido no se modifica ni se borra | `sql/54` (`fn_informe_inmutable`) | COBIT MEA03 |
| Reintroducir IA cosmética | Métrica de proporcionalidad del informe (IA vs texto del sistema, sin editar); criterio explícito para retirarla | `informe_semanal.metricas` | OCDE proporcionalidad |
| Asistente como vía de fuga o abuso de cuota | Solo lectura con lista blanca de campos; guardrails de dominio, inyección y PII; 30 preguntas/hora por sesión; cada pregunta en la auditoría con la pantalla | `quipu.py`, `herramientas.py`, `guardrails.py` | Ley 29733 · OWASP LLM · ITIL capacidad |
| Dependencia de un proveedor | Gemini → Groq con las mismas reglas; si ninguno responde, modo reglas marcado «Regla sin IA» | `proveedores.py`, `resolver_caso` | ITIL continuidad |

## 4. Lineamientos operativos (criterio C4): clasificación de usos

- **Permitidos**: consultas de los administradores al asistente (en cualquier pantalla, solo lectura); proponer recordatorios formales, escalamientos y notas de memoria sobre redes (skill de seguimiento), con aprobación de un ADMIN; redactar el informe semanal interno, con cifras verificadas y aprobación humana.
- **Restringidos (piloto, aprobación SUPER_ADMIN, con métricas)**: proponer decisiones sobre la bandeja de observaciones (pedir corrección, dar por revisada, reintentar). Pasa a permitido con ≥ 8 semanas de uso, aprobación ≥ 90 % y ningún caso dado por revisado que pedía algo.
- **No permitidos**: usar los patrones para sancionar o mostrarlos a las redes (comparaciones, rankings o historial en un correo); que la IA calcule cifras o patrones; que la IA ejecute algo sin aprobación humana; atención directa a usuarios externos (soporte a redes, evaluado y no construido); enviar nombres, correos, IP o datos clínicos a un proveedor; decisiones sobre cuentas y contraseñas.

## 5. Proveedores (criterio C3)

| Criterio | Gemini (principal) | Groq (respaldo) |
|---|---|---|
| Datos que recibe | Expedientes sin PII | Los mismos |
| Reglas de validación | Las de SIREA (independientes del proveedor) | Las mismas |
| Registro | `gemini:<modelo>` en traza, acciones y auditoría | `groq:<modelo>` |
| Evaluación | Las evaluaciones registran qué proveedor respondió | Igual |
| Clave | En `.env` / secretos, nunca en código | Igual |

## 6. Modelo institucional y escalamiento (criterio C5)

| Rol | En SIREA | Puede |
|---|---|---|
| Jefatura OIIS | Firma las skills (`aprobada_por`) | Aprobar cambios de procedimiento y de clasificación |
| SUPER_ADMIN | rol SUPER_ADMIN (`oiis.winepi`) | Correr evaluaciones, activar el agente, aprobar propuestas de la skill restringida |
| ADMIN | rol ADMIN | Aprobar recordatorios y escalamientos; agregar memoria; **detener toda la IA** |
| TI | Supabase / secretos | Claves, SQL, respaldos |

Escalamiento: el agente propone **ESCALAR** → la persona lo asume en la Bandeja (queda en logs) → Jefatura si corresponde. Incidente → botón de detención → revisar traza y auditoría → corregir la skill → evaluar → reactivar (SUPER_ADMIN).

## 7. Hoja de ruta

1. **Hoy (3.3)**: Quipu (asistente de consulta) en todas las pantallas, módulo «Gobernanza de IA» separado del trabajo diario, informe semanal también en PDF + Agente Operativo con 2 skills, patrones por red (sin IA), recordatorio formal por tipo, informe semanal medido, Centro de pendientes, mejora continua de skills e Historial de IA; 3 asistentes retirados; soporte a redes no construido.
2. **Piloto (8 semanas)**: medir aprobación, ediciones y rechazos por skill; % de redes a tiempo antes y después del aviso preventivo; informes aprobados con texto IA vs sistema; ampliar casos de evaluación con los rechazos reales.
3. **Siguiente**: nuevas skills (p. ej. preparación del cierre); exponer las herramientas de solo lectura por **MCP** (Model Context Protocol) para que otros sistemas de EsSalud consulten SIREA con el mismo control.
4. **Reconsiderar el soporte a redes** solo con segundo factor, base de conocimiento aprobada, guardrails probados y aprobación de Jefatura y TI.

## 8. Marcos, en una línea cada uno

- **COBIT**: EDM (activar exige SUPER_ADMIN y evaluación), BAI06 (cambios de skill con huella), DSS (acciones validadas), MEA (traza, auditoría, métricas).
- **ITIL**: el agente es gestión de eventos (red atrasada, observación nueva) que abre solicitudes que una persona atiende; continuidad Gemini → Groq → reglas (Notificaciones funciona sin IA); **mejora continua** del servicio con los rechazos.
- **TOGAF**: negocio (seguimiento semanal) → aplicación (harness, skills) → datos (corridas, acciones, memoria, evaluaciones) → tecnología (proveedores de IA, programador).
- **PRINCE2**: gestión por excepción: el agente resuelve lo rutinario y **escala** lo que sale de tolerancia; cada skill tiene criterio de calidad (umbral de evaluación).
- **OCDE**: transparencia (lila = IA, traza visible), supervisión humana (nada se ejecuta sin aprobación), robustez (reglas + evaluaciones), rendición de cuentas (auditoría inmutable), proporcionalidad (retiro de lo cosmético).

<p align="center">
  <img src="assets/essalud-azul.png" alt="EsSalud" height="72"/>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="assets/oiis-azul.png" alt="OIIS" height="80"/>
</p>

<h1 align="center">SIREA</h1>

<p align="center">
  <b>Sistema de Recepción de Reportes Epidemiológicos con Agentes</b><br/>
  Oficina de Inteligencia e Información Sanitaria (OIIS) · Seguro Social de Salud (EsSalud)
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Versi%C3%B3n-3.3.0-0077C8?style=for-the-badge" alt="Versión"/>
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
  <img src="https://img.shields.io/badge/Streamlit-1.64-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white" alt="Streamlit"/>
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase"/>
  <img src="https://img.shields.io/badge/Google%20Drive-API-4285F4?style=for-the-badge&logo=googledrive&logoColor=white" alt="Google Drive"/>
</p>
<p align="center">
  <img src="https://img.shields.io/badge/Gemini-Proveedor%20principal-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white" alt="Gemini"/>
  <img src="https://img.shields.io/badge/Groq-Respaldo-F55036?style=for-the-badge" alt="Groq"/>
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker"/>
  <img src="https://img.shields.io/badge/IA-Supervisi%C3%B3n%20humana-6E3FA3?style=for-the-badge" alt="Supervisión humana"/>
  <img src="https://img.shields.io/badge/Principios-OCDE-12324F?style=for-the-badge" alt="Principios OCDE"/>
</p>

---

## Visión del proyecto

Cada semana, las redes asistenciales de EsSalud remiten a la OIIS sus reportes epidemiológicos:

- **C** · Consulta Externa;
- **H** · Hospitalización;
- **E** · Emergencia.

Antes de SIREA, conocer qué había llegado, qué faltaba y quién debía recibir un recordatorio exigía revisar envíos y correos a mano.

**SIREA** centraliza la recepción, valida automáticamente cada archivo y da a la OIIS el control del cumplimiento en tiempo real. Sobre esa base incorpora **agentes de inteligencia artificial bajo supervisión humana**:

- leen los datos del sistema;
- detectan pendientes y patrones de atraso;
- redactan propuestas: recordatorios formales, informes y revisiones.

Ninguna acción se ejecuta sin la aprobación de un administrador, y todo lo que hace la IA queda en un historial que no se puede modificar ni borrar.

---

## Capacidades principales

| Área | Qué resuelve |
| :--- | :--- |
| **Recepción** | Formulario de envío con archivo ZIP. Valida el tipo de reporte, la semana y el año de cada archivo, controla el plazo según la fecha de corte, envía acuse con código de seguimiento y guarda en Google Drive |
| **Monitoreo** | Panel de control, seguimiento semanal y progreso por red, con filtro común de año, semana y red |
| **Gestión** | Atrasos, duplicados, observaciones, notificaciones con responsables sugeridos, exclusión de centros, cierre de semana y respaldos |
| **Seguridad** | Roles ADMIN y SUPER_ADMIN, permisos por red, bloqueo por intentos fallidos, sesiones persistentes y registros protegidos |
| **Agente Operativo** | Ronda diaria que propone recordatorios, escalamientos y notas. Todo pasa por la Bandeja para su aprobación |
| **Patrones por red** | Cálculo sin IA de qué falta por centro y tipo, qué red suele atrasarse y cuál mejora o empeora |
| **Informe semanal** | Cifras del sistema más una redacción de la IA con cifras verificadas. Se exporta en PDF institucional con marca de agua y en Word |
| **Quipu** | Asistente de consulta flotante en todas las pantallas. Solo lee datos; nunca envía ni modifica |
| **Gobernanza de IA** | Módulo propio con el funcionamiento, las rondas, los procedimientos, las evaluaciones, la memoria, el encendido y apagado y el historial de IA |

---

## Arquitectura general

```mermaid
flowchart LR
    subgraph Usuarios["Usuarios"]
        R["Responsables de red<br/>(envío semanal)"]
        A["Administradores OIIS<br/>(ADMIN / SUPER_ADMIN)"]
    end

    subgraph App["Aplicación SIREA · Streamlit"]
        F["Formulario de envío<br/>y portal de la red"]
        P["Panel de administración<br/>monitoreo · gestión · seguridad"]
        IA["Agentes de IA<br/>Agente Operativo · Quipu · Informe"]
        G["Guardrails<br/>dominio · PII · cifras · tono"]
    end

    subgraph Servicios["Servicios"]
        DB[("Supabase<br/>PostgreSQL")]
        DR[("Google Drive<br/>archivos y respaldos")]
        SM["Correo SMTP<br/>acuses y recordatorios"]
        LLM["Proveedores de IA<br/>Gemini · Groq"]
    end

    PR["Proceso programado<br/>cierres · respaldos · ronda diaria"]

    R --> F
    A --> P
    P <--> IA
    F --> DB
    F --> DR
    F --> SM
    P --> DB
    IA --> G
    G <--> LLM
    IA --> DB
    PR --> DB
    PR --> SM
    PR --> IA

    classDef usuario fill:#E6F4FB,stroke:#0077C8,color:#12324F
    classDef app fill:#FFFFFF,stroke:#0077C8,color:#12324F
    classDef ia fill:#F3ECFA,stroke:#6E3FA3,color:#2B2140
    classDef servicio fill:#F4F7FA,stroke:#5B6B7A,color:#1F2D3A
    class R,A usuario
    class F,P app
    class IA,G ia
    class DB,DR,SM,LLM,PR servicio
```

---

## Flujo de recepción de un envío

```mermaid
sequenceDiagram
    autonumber
    actor Red as Responsable de red
    participant App as SIREA
    participant Val as Validación ZIP
    participant Drive as Google Drive
    participant DB as Supabase
    participant Mail as Correo

    Red->>App: Sube el ZIP de la semana
    App->>Val: Revisa nombres, tipo C/H/E, semana y año
    alt Archivos válidos
        Val-->>App: Detalle por archivo y centro
        App->>App: Compara con la fecha de corte
        App->>Drive: Guarda el ZIP en la carpeta de la semana
        App->>DB: Registra el envío (a tiempo o tardío)
        App->>Mail: Acuse con código de seguimiento
        App-->>Red: Confirmación en pantalla
    else Archivos con errores
        Val-->>App: Motivos del rechazo
        App-->>Red: Indica qué corregir
    end
```

---

## Ciclo del Agente Operativo

El agente **propone** y una persona **decide**. Las reglas del sistema revisan cada propuesta antes de que llegue a la Bandeja.

```mermaid
flowchart TD
    A["Expediente del caso<br/>datos del sistema: qué falta, por centro y tipo,<br/>horas al corte, perfil de la red"] --> B["Procedimiento escrito (skill)<br/>versionado con huella SHA-256"]
    B --> C{"Modelo de IA<br/>propone una acción"}
    C --> D["Validación por reglas<br/>centros reales · sin datos personales ·<br/>sin comparaciones entre redes · sin duplicar recordatorios"]
    D -->|No cumple| X["Descartada<br/>queda registrada"]
    D -->|Cumple| E["Bandeja<br/>propuesta con evidencia y vista previa"]
    E --> F{"Administrador"}
    F -->|Aprueba o edita| G["Ejecución<br/>envío del correo o registro"]
    F -->|Rechaza con motivo| H["Rechazo<br/>alimenta la mejora del procedimiento"]
    G --> I[("Historial de IA<br/>solo inserción")]
    H --> I
    X --> I

    classDef ia fill:#F3ECFA,stroke:#6E3FA3,color:#2B2140
    classDef regla fill:#F4F7FA,stroke:#5B6B7A,color:#1F2D3A
    classDef humano fill:#E7F5EC,stroke:#1E6B3A,color:#143D22
    classDef alerta fill:#FDECEC,stroke:#B42318,color:#5C1610
    class B,C ia
    class A,D,E regla
    class F,G humano
    class X,H alerta
```

### Estados de una propuesta

```mermaid
stateDiagram-v2
    [*] --> PROPUESTA: el agente la crea
    PROPUESTA --> EJECUTADA: un administrador aprueba y la acción se completa
    PROPUESTA --> FALLIDA: aprobada, pero la acción no pudo completarse
    PROPUESTA --> RECHAZADA: un administrador la rechaza con motivo
    PROPUESTA --> VENCIDA: la situación cambió antes de decidir
    EJECUTADA --> [*]
    FALLIDA --> [*]
    RECHAZADA --> [*]
    VENCIDA --> [*]
```

### Ciclo de vida de los agentes

El estado se guarda en la base de datos. Si no se puede leer, el agente se considera **INACTIVO**: nunca opera por defecto.

```mermaid
stateDiagram-v2
    [*] --> INACTIVO: estado inicial siempre
    INACTIVO --> ACTIVO_HITL: SUPER_ADMIN, con procedimiento evaluado
    ACTIVO_HITL --> EN_REVISION: cualquier administrador (pausa inmediata)
    EN_REVISION --> ACTIVO_HITL: SUPER_ADMIN
    ACTIVO_HITL --> INACTIVO: SUPER_ADMIN
    INACTIVO --> DESACTIVADO: SUPER_ADMIN con justificación
    EN_REVISION --> DESACTIVADO: SUPER_ADMIN con justificación
    DESACTIVADO --> [*]
```

---

## Mejora continua de los procedimientos

```mermaid
flowchart LR
    R["Rechazos con motivo<br/>(mínimo configurable)"] --> P["El agente propone<br/>un ajuste al procedimiento"]
    P --> S{"SUPER_ADMIN<br/>revisa el cambio"}
    S -->|Aprueba| V["Nueva versión<br/>nueva huella SHA-256"]
    S -->|Descarta| R
    V --> E["Evaluaciones<br/>casos de referencia · umbral 85 %<br/>comparación con y sin IA"]
    E -->|Supera| O["Procedimiento vigente"]
    E -->|No supera| B["Se vuelve a la versión anterior"]

    classDef ia fill:#F3ECFA,stroke:#6E3FA3,color:#2B2140
    classDef humano fill:#E7F5EC,stroke:#1E6B3A,color:#143D22
    classDef regla fill:#F4F7FA,stroke:#5B6B7A,color:#1F2D3A
    class P,V ia
    class S,O humano
    class R,E,B regla
```

---

## Quipu, el asistente de consulta

Su nombre viene del sistema de cuerdas anudadas con el que los incas llevaban sus registros. Quipu responde preguntas sobre los datos de SIREA desde cualquier pantalla, con herramientas de solo lectura y una lista blanca de campos.

```mermaid
sequenceDiagram
    actor Adm as Administrador
    participant Q as Quipu
    participant G as Guardrails
    participant M as Modelo de IA
    participant H as Herramientas de solo lectura
    participant Au as Historial de IA

    Adm->>Q: Pregunta (con la pantalla y semana actuales)
    Q->>G: Filtro de entrada: dominio, inyección, datos personales
    alt Fuera de dominio o riesgosa
        G-->>Adm: Mensaje de rechazo
    else Permitida
        G->>M: Pregunta saneada
        loop Hasta el límite de consultas
            M->>H: Solicita un dato (progreso, faltantes, patrones)
            H-->>M: Solo los campos permitidos
        end
        M-->>G: Respuesta
        G-->>Adm: Filtro de salida y leyenda de IA
    end
    Q->>Au: Registra pregunta, herramientas y proveedor
```

---

## Modelo de datos principal

```mermaid
erDiagram
    REDES ||--o{ CENTROS : agrupa
    REDES ||--o{ ENVIOS : remite
    ENVIOS ||--o{ OBSERVACIONES_ENVIO : tiene
    AGENTE_CORRIDAS ||--o{ AGENTE_ACCIONES : genera
    AGENTE_CORRIDAS ||--o{ AGENTE_TRAZA : registra
    AGENTE_ACCIONES }o--|| AUDITORIA_AGENTES_IA : "se audita en"
    AGENTE_INFORMES }o--|| AUDITORIA_AGENTES_IA : "se audita en"

    REDES {
        int id
        text nombre
    }
    CENTROS {
        int id
        int red_id
        text codigo
        text nombre
    }
    ENVIOS {
        int id
        text red
        int anio
        int semana
        text estado
        bool es_atrasado
        jsonb detalle_archivos
        text codigo_seguimiento
    }
    AGENTE_ACCIONES {
        int id
        text skill
        text tipo
        text red
        text estado
        jsonb payload
        jsonb evidencia
    }
    AGENTE_INFORMES {
        int id
        int anio
        int semana
        text estado
        text texto_final
        text aprobado_por
    }
    AUDITORIA_AGENTES_IA {
        int id
        text agente
        text evento
        timestamptz fecha
    }
```

Otras tablas:

- **Sesiones y accesos:** `sesiones_app`, `intentos_login`.
- **Trazabilidad:** `auditoria_acciones`, `logs`.
- **Operación:** `cierres_corte`, `respaldos`, `permisos_operaciones`, `solicitudes_password`.
- **Agentes:** `agente_memoria_red`, `agente_evals`, `agente_skill_versiones`, `agente_atrasos_justificados`.

El detalle de cada script está en [`sql/LEEME.md`](sql/LEEME.md).

---

## Gobernanza de la IA

El diseño sigue los **Principios de IA de la OCDE**.

| Principio | Cómo se aplica en SIREA |
| :--- | :--- |
| **Supervisión humana** | Los agentes proponen; una persona aprueba, edita o rechaza. Arrancan siempre inactivos y solo un SUPER_ADMIN puede activarlos |
| **Transparencia** | Cada propuesta muestra su evidencia y su razonamiento. Los textos de IA llevan leyenda y el PDF del informe dice si fue validado |
| **Robustez y seguridad** | Guardrails de entrada y salida, token canario, verificación de cifras contra el sistema, proveedor de respaldo y comportamiento *fail-closed* |
| **Rendición de cuentas** | Historial de IA en una tabla en la que solo se puede insertar, con usuario, decisión y motivo. Los disparadores impiden editar informes y decisiones |
| **Proporcionalidad** | Cada procedimiento se evalúa contra su versión sin IA; los asistentes que no aportaban se retiraron con la decisión documentada |
| **Privacidad** | Herramientas con lista blanca de campos, detección de datos personales y comparaciones entre redes reservadas al uso interno |

Marco completo, matriz de riesgos y controles: [`docs/GOBERNANZA_SIREA.md`](docs/GOBERNANZA_SIREA.md).

---

## Tecnologías

| Capa | Tecnología |
| :--- | :--- |
| Interfaz y servidor | Python 3.12 · Streamlit 1.64 |
| Base de datos | Supabase (PostgreSQL) |
| Archivos | Google Drive API (cuenta de servicio) |
| Correo | SMTP (Google Workspace / Gmail) |
| Inteligencia artificial | Google Gemini (principal) · Groq (respaldo) |
| Documentos | openpyxl · python-docx · reportlab |
| Despliegue | Docker Compose · Caddy (HTTPS) · Streamlit Community Cloud con GitHub Actions |
| Pruebas | pytest · Playwright |

---

## Estructura del proyecto

```
sirea/
├── app.py                     Punto de entrada
├── app_pages/                 Pantallas: envío, portal de red, panel y módulos
│   ├── admin.py               Menú, sesión y despacho de secciones
│   ├── admin_agentes_ia.py    Módulos «Agente de IA» y «Gobernanza de IA»
│   ├── filtro_periodo.py      Filtro común de año, semana y red
│   └── quipu.py               Asistente de consulta flotante
├── src/
│   ├── agentes/               Agentes, skills, guardrails, evaluaciones, patrones, auditoría
│   │   ├── skills/            Procedimientos escritos de los agentes
│   │   └── casos_eval/        Casos de evaluación
│   ├── db_manager.py          Acceso a Supabase
│   ├── drive_manager.py       Google Drive
│   ├── email_sender.py        Correos y plantillas
│   ├── informe_pdf.py         Informe semanal en PDF institucional
│   ├── programador.py         Proceso programado
│   └── zip_processor.py       Validación de archivos recibidos
├── utils/                     Tema visual y componentes de interfaz
├── sql/                       Scripts de base de datos
├── scripts/                   Secretos para la nube y datos de demostración
├── tests/                     Pruebas automáticas y recorrido en navegador
├── docs/                      Gobernanza, despliegue y lista de verificación
├── assets/                    Logos institucionales
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Instalación

### Requisitos

- Python 3.12 o superior.
- Un proyecto de Supabase. Se recomienda uno de demostración, separado de producción.
- Una cuenta de servicio de Google con acceso a las carpetas de Drive.
- Una cuenta de correo con contraseña de aplicación (SMTP).
- Una clave de Gemini. La de Groq es opcional, como respaldo.

### Pasos

```bash
git clone <url-del-repositorio> sirea
cd sirea
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # completar los valores marcados con <<< COMPLETAR
```

**Base de datos:** en Supabase, abra **SQL Editor** y ejecute `sql/ACTUALIZAR_TODO_SIREA_3_2.sql`.

- Es idempotente: se puede ejecutar más de una vez y no borra datos.
- Al terminar verifica que existan todas las tablas.
- La versión 3.3 no requiere cambios adicionales en la base.

```bash
python verificar_despliegue.py    # comprueba base de datos, Drive, correo y proveedores de IA
streamlit run app.py              # http://localhost:8501
```

### Variables principales

| Variable | Descripción |
| :--- | :--- |
| `SUPABASE_URL`, `SUPABASE_KEY` | Proyecto de Supabase (clave service_role) |
| `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_DRIVE_FOLDER_ID` | Cuenta de servicio y carpetas de Drive |
| `EMAIL_REMITENTE`, `EMAIL_PASSWORD`, `EMAIL_ADMINS` | Correo de envío y destinatarios de alertas |
| `SUPERADMIN_PRINCIPAL` | Usuario SUPER_ADMIN principal |
| `GEMINI_API_KEY`, `GROQ_API_KEY` | Proveedores de IA |
| `AGENTE_PROGRAMADO`, `AGENTE_HORA` | Ronda diaria del Agente Operativo |
| `PATRONES_SEMANAS`, `PATRONES_MIN_SEMANAS` | Ventana y mínimo para calcular patrones |
| `ASISTENTE_LIMITE_HORA` | Preguntas por hora y sesión a Quipu |

La plantilla `.env.example` documenta todas las variables.

---

## Despliegue

```mermaid
flowchart LR
    subgraph Servidor["Opción 1 · Servidor propio"]
        D1["docker compose up -d"] --> C1["Contenedor app<br/>Streamlit :8501"]
        D1 --> C2["Contenedor programador<br/>ciclo cada minuto"]
        D2["--profile https"] --> C3["Caddy<br/>proxy HTTPS"]
    end
    subgraph Nube["Opción 2 · Nube"]
        N1["Streamlit Community Cloud<br/>aplicación web"]
        N2["GitHub Actions<br/>programador cada 15 min"]
    end

    classDef op fill:#E6F4FB,stroke:#0077C8,color:#12324F
    class D1,D2,C1,C2,C3,N1,N2 op
```

| Opción | Guía |
| :--- | :--- |
| Servidor Linux con Docker | [`GUIA_DESPLIEGUE_SERVIDOR.md`](GUIA_DESPLIEGUE_SERVIDOR.md) |
| Windows con Docker | [`GUIA_DESPLIEGUE_WINDOWS.md`](GUIA_DESPLIEGUE_WINDOWS.md) |
| Streamlit Community Cloud | [`docs/DESPLIEGUE_STREAMLIT_CLOUD.md`](docs/DESPLIEGUE_STREAMLIT_CLOUD.md) |

Los secretos nunca van en el repositorio. Están excluidos en `.gitignore`:

- `.env`;
- `credentials/`;
- `.streamlit/secrets.toml`.

---

## Pruebas

```bash
pytest -q
```

Las pruebas usan un Supabase simulado y no requieren red ni claves. Cubren:

- recepción;
- sesiones;
- guardrails;
- proveedores de IA;
- Agente Operativo;
- patrones;
- informe semanal y PDF.

Recorrido completo en navegador con Playwright:

```bash
python -m streamlit run tests/smoke_app.py --server.port 8599 --server.headless true
python tests/smoke_browser.py http://localhost:8599
```

**Datos de demostración** (solo para bases de prueba):

- `scripts/sembrar_historial_demo.py`;
- `sql/DEMO_semana_40_datos_sinteticos.sql`.

Todo lo simulado queda marcado como `DEMO-SIM`, usa correos del dominio reservado `example.org` y tiene su opción de borrado.

---

## Documentación

| Documento | Contenido |
| :--- | :--- |
| [`CAMBIOS_SIREA.md`](CAMBIOS_SIREA.md) | Historial de versiones |
| [`docs/GOBERNANZA_SIREA.md`](docs/GOBERNANZA_SIREA.md) | Marco de gobernanza de la IA, riesgos y controles |
| [`docs/CHECKLIST_PRUEBA_REAL.md`](docs/CHECKLIST_PRUEBA_REAL.md) | Lista de verificación para pruebas con datos reales |
| [`sql/LEEME.md`](sql/LEEME.md) | Scripts de base de datos y orden de ejecución |

---

<p align="center">
  Desarrollado para la Oficina de Inteligencia e Información Sanitaria (OIIS) · EsSalud<br/>
  Uso institucional. Los logotipos de EsSalud y de la OIIS pertenecen a sus respectivos titulares.
</p>

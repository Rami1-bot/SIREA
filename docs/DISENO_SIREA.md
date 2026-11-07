# Diseño de SIREA 3.5

SIREA dejó de verse como SIRE. La idea: **el año epidemiológico es un quipu**. Cada semana es una cuerda con
su nudo; la semana activa lleva un nudo con aro. El nombre del asistente (Quipu) y la marca salen de ahí.

## Paleta corporativa

| Nombre | Color | Uso |
|---|---|---|
| Azul EsSalud | `#0077C8` (hover `#005C9C`) | Botones, enlaces, barras de datos y **la barra superior de las tarjetas** |
| Azul marca | `#1D3F76` | Títulos, cifras y borde de la tarjeta del panel |
| Celeste EsSalud | `#41B6E6` (tinte `#EAF3FB`) | Solo en bordes y en el tinte de los íconos; la «A» de SIREA sobre la banda va en `#9FD6F0` |
| Banda | `#0071BE` → `#00579A` | Encabezado de todas las pantallas públicas, también los accesos |
| Fondo / línea / tinta | `#F5F8FB` / `#D6E2EE` / `#13213A` | Superficies y texto |

**El color va en los bordes, no en rellenos**: tarjetas y fichas blancas con barra superior de 4 px (azul, celeste o
azul marca); íconos azules sobre tinte claro; botones azules (o blancos sobre la banda). Sin verde, celeste, lila ni
aguamarina como relleno, sin amarillo mostaza, sin marca de agua ni reflejos. Los rellenos de color quedan solo para
los estados: verde = a tiempo, naranja `#96500A` sobre `#FFF3E3` = observado o aviso, rojo = tardío,
magenta `#9C2465` = duplicado. «Falta un dato» en los formularios va en azul: incompleto no es alerta.
El quipu alterna dos tonos por mes (blanco y celeste claro en la banda; azul y azul marca sobre blanco) y la semana
activa es un nudo blanco con aro.

## Fondo con figuras de salud

`patron_salud()` arma un mosaico SVG de 360 × 360 px con 11 figuras de trazo (cruz, corazón, estetoscopio, gota,
termómetro, lupa, curva epidémica, microbio, vacuna, pastilla y reporte). Va en azul al 7,5 % sobre el fondo claro de toda la
app y en blanco al 13 % sobre la banda: se nota sin competir con el texto.

## Pantalla completa

El contenido ocupa todo el ancho (`max-width: 100%`) con un margen lateral que crece con la pantalla
(`clamp(20px, 4vw, 72px)`). Aplica a la portada, Enviar reporte, Mi progreso y todas las páginas del panel.
Nada queda «encasillado»: el menú superior llega al borde derecho, la cabecera de cada página reparte texto y ficha
en una rejilla sin hueco central, los botones de acceso y de descarga ocupan su columna completa, «Cómo funciona»
y «Plazos» tienen la misma altura, la franja final son tres bloques de color y la cuerda del panel va de lado a lado.

## Accesos (red y panel)

Van sobre la misma banda azul que el resto: a la izquierda el título, los pasos y un ejemplo; a la derecha la tarjeta
blanca del formulario con barra superior azul. Los enlaces de abajo son botones con contorno blanco.

## Portada

Banda azul con el quipu multicolor y, a la derecha, un **mosaico de cuatro fichas**: anillo de avance (blanco),
con barra de avance azul, centros con reporte, redes y fecha de corte: todas blancas con barra superior de color
(la de la fecha de corte pasa a roja cuando el plazo venció). Las tres tarjetas de acceso son blancas con barra superior
azul, celeste o azul marca, ícono azul sobre tinte claro y botón a todo el ancho.

## Barra lateral

Clara (`#EAF4FC`) con texto azul marca; el ítem activo va en blanco con una barra azul a la izquierda.

## Tipografía

- **Bricolage Grotesque** (títulos y cifras grandes).
- **IBM Plex Sans** (interfaz y tablas, con cifras tabulares).
- Ambas viajan dentro del proyecto (`static/fonts/`, licencia SIL OFL): funcionan en una intranet sin Google Fonts.

## Reglas

- **Etiquetas:** con minúscula inicial, sin MAYÚSCULAS ni letras espaciadas.
- **Superficies:** bordes finos y casi sin sombras. Radio según jerarquía: paneles 14 px, controles 8 px, chips redondos.
- **Contraste:** todo texto cumple WCAG AA (4,5:1; 3:1 en letra grande), revisado pantalla por pantalla. El texto sobre la banda azul va siempre en blanco; el celeste nunca va como texto sobre blanco.
- **Accesibilidad:** foco visible (azul `#0077C8`; blanco sobre la banda) al navegar con teclado; se respeta «reducir movimiento».

## Dónde está

- `utils/tema.py`: constantes de color, `marca_svg()` (el quipu de la marca), `quipu_semanas()` (la cuerda),
  `_CSS_SIREA` y `_CSS_SIREA_BANDA` (la capa de identidad, que se aplica siempre al final).
- `.streamlit/config.toml`: colores y fuentes de los componentes nativos de Streamlit.
- `app.py`: la portada (`.sirea-hero`, `.sirea-registro`).
- Los correos y el PDF del informe conservan el azul institucional.

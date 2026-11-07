# utils/cuentas_ui.py
"""
Piezas de pantalla para crear cuentas y elegir contraseñas:

  * lista de requisitos de contraseña con el porqué de cada uno, barra de
    fortaleza y aviso de coincidencia (se actualiza al salir del campo);
  * campo de usuario con sugerencias: si el usuario está vacío, ya existe o es
    demasiado común, se ofrecen alternativas que se llenan con un clic.

La lógica de qué es una contraseña aceptable vive en src/password_policy.py;
aquí solo se dibuja.
"""

import base64
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

import streamlit as st

from src.password_policy import (
    PERFIL_ESTRICTO, PERFIL_RED, datos_para_navegador, evaluar, fuerza, generar, generar_legible,
    sugerir_usuarios, usuario_demasiado_comun,
)
from utils.tema import TONOS, icono, mostrar

_COLOR_FUERZA = {0: "#C4D6E6", 1: "#B42318", 2: "#E08A1E", 3: "#2A8FD0", 4: "#1E6B3A"}


def _esc(texto: str) -> str:
    import html
    return html.escape(str(texto or ""), quote=True)


# ============================================================
# REQUISITOS DE CONTRASEÑA
# ============================================================

def requisitos_html(password: str, contexto: Sequence[str] = (), actual: str = None,
                    perfil: str = PERFIL_ESTRICTO) -> str:
    """Lista de requisitos (cumplidos en verde) y barra de fortaleza, como HTML."""
    reqs = evaluar(password, contexto, actual, perfil)
    escrita = bool(password)
    items = []
    for r in reqs:
        if escrita and r.cumple:
            ico = icono("check", 18, TONOS["ok"][0], 2.4)
            cls = "ok"
            extra = ""
        elif escrita:
            ico = icono("alerta", 18, "#9E2B2B", 2.2)
            cls = "mal"
            extra = f'<span class="sire-req-m">{_esc(r.motivo)}</span>'
        else:
            ico = icono("circulo", 18, "#6B7C8C", 2.2)
            cls = ""
            extra = ""
        items.append(f'<div class="sire-req-i {cls}">{ico}<span>{_esc(r.texto)}{extra}</span></div>')

    nivel, etiqueta = fuerza(password, contexto, actual, perfil)
    color = _COLOR_FUERZA[nivel]
    segmentos = "".join(
        f'<i style="background:{color if i < nivel else "#E3F0FA"}"></i>' for i in range(4)
    )
    barra = (
        f'<div class="sire-fuerza"><div class="sire-fuerza-p" role="img" aria-label="Fortaleza: {etiqueta}">{segmentos}</div>'
        f'<span class="sire-fuerza-n" style="color:{color if nivel else "#4F6070"}">{etiqueta}</span></div>'
    )
    return f'<div class="sire-req"><div class="sire-req-t">Su contraseña debe cumplir</div>{barra}{"".join(items)}</div>'


def explicacion_requisitos(titulo: str = "¿Por qué pedimos esto?", perfil: str = PERFIL_ESTRICTO):
    """Desplegable que explica el motivo de cada requisito, en lenguaje sencillo."""
    reqs = evaluar("", perfil=perfil)  # solo para leer los textos y motivos
    lis = "".join(f"<li><b>{_esc(r.texto)}.</b> {_esc(r.motivo)}</li>" for r in reqs)
    consejo = (
        "Un consejo práctico: una frase de 12 o más caracteres, por ejemplo cuatro palabras sueltas unidas con guiones, "
        "es fácil de recordar y muy difícil de adivinar. Si lo prefiere, use el botón «Sugerir una contraseña»."
        if perfil == PERFIL_RED else
        "Un consejo práctico: una frase corta con palabras que solo usted conozca, "
        "combinada con números y un símbolo, es fácil de recordar y difícil de adivinar."
    )
    with st.expander(titulo):
        mostrar(
            '<div class="sire-porque">Los reportes epidemiológicos son información sensible de EsSalud. '
            'Una contraseña débil permite que otra persona entre con su cuenta y envíe o consulte datos en su nombre. '
            f"<ul>{lis}</ul>"
            f"<p style=\"margin:10px 0 0\">{consejo}</p></div>"
        )


# ============================================================
# PANEL DE REQUISITOS EN TIEMPO REAL (perfil de las redes)
# ============================================================

@lru_cache(maxsize=1)
def _js_vivo() -> str:
    ruta = Path(__file__).resolve().parent.parent / "components" / "password_vivo.js"
    js = ruta.read_text(encoding="utf-8")
    # st.html descarta el script entero si dentro hay texto con forma de etiqueta (por ejemplo en un comentario).
    if re.search(r"<[A-Za-z/!]", js):
        raise ValueError("components/password_vivo.js no puede contener texto con forma de etiqueta HTML (< seguido de letra, / o !).")
    return js


def _ico_img(nombre: str, color: str, grosor: float = 2.2) -> str:
    """
    Ícono como imagen (data URI). st.html elimina los <svg> en línea, pero deja pasar <img>
    con data URI, y así el ícono se ve igual que en el resto del sistema.
    """
    svg = icono(nombre, 18, color, grosor)
    if "xmlns=" not in svg:
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" ', 1)
    b64 = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f'<img src="data:image/svg+xml;base64,{b64}" width="18" height="18" alt="" style="display:block">'


def panel_vivo_html(password: str, confirmar: str, contexto: Sequence[str], prefijo: str) -> str:
    """
    Panel «Su contraseña debe cumplir» para el perfil de las redes. Se dibuja con el estado
    ya confirmado en el servidor y components/password_vivo.js lo va actualizando mientras la
    persona escribe (sin esperar a que salga del campo). Va dentro de st.html con JavaScript.
    """
    perfil = PERFIL_RED
    reqs = evaluar(password, contexto, None, perfil)
    escrita = bool(password)
    ico = {
        "ok": _ico_img("check", TONOS["ok"][0], 2.4),
        "mal": _ico_img("alerta", "#9E2B2B", 2.2),
        "vacio": _ico_img("circulo", "#6B7C8C", 2.2),
    }
    items = []
    for r in reqs:
        estado = "vacio" if not escrita else ("ok" if r.cumple else "mal")
        cls = {"ok": "ok", "mal": "mal", "vacio": ""}[estado]
        extra = ""
        if r.clave == "largo" and escrita and not r.cumple:
            from src.password_policy import LONGITUD_MINIMA_RED
            extra = f" · le faltan {max(0, LONGITUD_MINIMA_RED - len(password))}"
        items.append(
            f'<div class="sire-req-i {cls}" data-req="{r.clave}"><span class="sire-req-ico">{ico[estado]}</span>'
            f'<span>{_esc(r.texto)}<span class="sire-req-x">{extra}</span>'
            f'<span class="sire-req-m">{_esc(r.motivo)}</span></span></div>'
        )

    todos = escrita and all(r.cumple for r in reqs)
    if not confirmar:
        est_c = "vacio"
    else:
        est_c = "ok" if (confirmar == password and password) else "mal"
    texto_c = "Las contraseñas no coinciden" if est_c == "mal" else "Las dos contraseñas coinciden"
    items.append(
        f'<div class="sire-req-i {"ok" if est_c == "ok" else ("mal" if est_c == "mal" else "")}" data-coincide="1">'
        f'<span class="sire-req-ico">{ico[est_c]}</span><span class="sire-req-t2">{texto_c}</span></div>'
    )
    listo = todos and est_c == "ok"
    pie = ("Todo listo: ya puede guardar su contraseña." if listo
           else "Cuando todo esté en verde, podrá guardar.")

    nivel, etiqueta = fuerza(password, contexto, None, perfil)
    color = _COLOR_FUERZA[nivel]
    segmentos = "".join(f'<i style="background:{color if i < nivel else "#E3F0FA"}"></i>' for i in range(4))
    barra = (
        f'<div class="sire-fuerza"><div class="sire-fuerza-p" role="img" aria-label="Fortaleza: {etiqueta}">{segmentos}</div>'
        f'<span class="sire-fuerza-n" style="color:{color if nivel else "#4F6070"}">{etiqueta}</span></div>'
    )

    cfg = datos_para_navegador(contexto)
    cfg.update({
        "pos": ["largo", "letras_numero"],
        "ico": ico,
        "col": {str(k): v for k, v in _COLOR_FUERZA.items()},
        "fz": {"0": "Sin escribir", "1": "Muy débil", "2": "Débil", "3": "Aceptable", "4": "Fuerte"},
    })
    cfg_attr = _esc(json.dumps(cfg, ensure_ascii=False, separators=(",", ":")))
    return (
        f'<div class="sire-req sire-req-vivo" data-pw-prefijo="{_esc(prefijo)}" data-cfg="{cfg_attr}">'
        f'<div class="sire-req-t">Su contraseña debe cumplir</div>{barra}{"".join(items)}'
        f'<div class="sire-req-listo {"ok" if listo else ""}" data-listo="1">{pie}</div></div>'
        f"<script>{_js_vivo()}</script>"
    )


def campos_nueva_password(
    prefijo: str,
    contexto: Iterable[str] = (),
    actual: str = None,
    etiqueta_nueva: str = "Nueva contraseña",
    etiqueta_confirmar: str = "Confirmar nueva contraseña",
    ofrecer_generador: bool = False,
    perfil: str = PERFIL_ESTRICTO,
    en_vivo: bool = False,
    zona_boton_out: bool = False,
):
    """
    Dibuja los dos campos de contraseña con la lista de requisitos y devuelve
    (nueva, confirmar).

    Por defecto los campos viven fuera de un formulario y la lista se actualiza
    al terminar de escribir (al salir del campo o con Enter).

    Con `en_vivo=True` y el perfil de las redes, los campos van a la izquierda y los
    requisitos a la derecha, y la lista se marca MIENTRAS se escribe (JavaScript en el
    navegador; el servidor revalida todo al guardar). Con `zona_boton_out=True` devuelve un
    tercer valor: un contenedor justo debajo de los campos, donde poner el botón de guardar.
    """
    contexto = list(contexto)
    k_nueva, k_conf = f"{prefijo}_nueva", f"{prefijo}_confirmar"
    vivo = bool(en_vivo) and perfil == PERFIL_RED and actual is None

    def _generador():
        if perfil == PERFIL_RED:
            etiqueta_btn, nota = "Sugerir una contraseña fácil de recordar", "Anótela o cópiela antes de guardar: no se volverá a mostrar."
        else:
            etiqueta_btn, nota = "Generar una contraseña segura", "Cópiela y entréguela por un canal seguro: no se volverá a mostrar."

        def _generar():
            g = generar_legible(contexto) if perfil == PERFIL_RED else generar()
            st.session_state[k_nueva] = g
            st.session_state[k_conf] = g
            st.session_state[f"{prefijo}_generada"] = g
        st.button(etiqueta_btn, key=f"{prefijo}_btn_generar", on_click=_generar, icon=":material/autorenew:")
        generada = st.session_state.get(f"{prefijo}_generada")
        if generada and st.session_state.get(k_nueva) == generada:
            mostrar(
                '<div class="sire-aviso" style="background:#FFF3E3;border:1px solid #F5C892;border-left:5px solid #E08A1E">'
                f'{icono("alerta", 20, "#96500A")}<div><div class="sire-aviso-t" style="color:#96500A">'
                f'{"Contraseña sugerida" if perfil == PERFIL_RED else "Contraseña generada"}</div>'
                f'<code style="font-size:15px">{_esc(generada)}</code><br>{nota}</div></div>'
            )

    if vivo:
        izq, der = st.columns([1.05, 1], gap="large")
        with izq:
            if ofrecer_generador:
                _generador()
            nueva = st.text_input(etiqueta_nueva, type="password", key=k_nueva, autocomplete="new-password")
            confirmar = st.text_input(etiqueta_confirmar, type="password", key=k_conf, autocomplete="new-password")
            zona_boton = st.container()
        with der:
            with st.container(key=f"{prefijo}_panel"):
                st.html(panel_vivo_html(nueva, confirmar, contexto, prefijo), unsafe_allow_javascript=True)
                explicacion_requisitos(perfil=perfil)
        if zona_boton_out:
            return nueva, confirmar, zona_boton
        return nueva, confirmar

    if ofrecer_generador:
        _generador()

    nueva = st.text_input(etiqueta_nueva, type="password", key=k_nueva, autocomplete="new-password")
    confirmar = st.text_input(etiqueta_confirmar, type="password", key=k_conf, autocomplete="new-password")

    mostrar(requisitos_html(nueva, contexto, actual, perfil))
    if confirmar:
        if nueva == confirmar:
            mostrar(f'<div class="sire-req-i ok" style="margin:-4px 0 8px">{icono("check", 18, TONOS["ok"][0], 2.4)}<span>Las contraseñas coinciden</span></div>')
        else:
            mostrar(f'<div class="sire-req-i" style="margin:-4px 0 8px;color:#9E2B2B;font-weight:700">{icono("alerta", 18, "#9E2B2B", 2.2)}<span>Las contraseñas no coinciden</span></div>')
    explicacion_requisitos(perfil=perfil)
    return nueva, confirmar


def limpiar_campos_password(prefijo: str):
    """Vacía los campos de contraseña de un prefijo (después de guardar)."""
    for sufijo in ("_nueva", "_confirmar", "_generada"):
        st.session_state.pop(f"{prefijo}{sufijo}", None)


# ============================================================
# USUARIO CON SUGERENCIAS
# ============================================================

def campo_usuario_con_sugerencias(
    key: str,
    nombre_key: str,
    correo_key: str,
    ocupados: Iterable[str] = (),
    etiqueta: str = "Usuario",
) -> str:
    """
    Campo de usuario. Si está vacío (y ya se escribió el nombre), si ya existe
    o si es demasiado común, muestra sugerencias; un clic en una de ellas
    llena el campo.
    """
    ocupados = [str(o) for o in ocupados]
    usuario = st.text_input(etiqueta, key=key, placeholder="Ej. inicial y apellido: mquispe")
    valor = (usuario or "").strip()
    nombre = st.session_state.get(nombre_key, "")
    correo = st.session_state.get(correo_key, "")

    ocupado = valor.lower() in {o.lower() for o in ocupados} if valor else False
    comun = bool(valor) and usuario_demasiado_comun(valor)
    corto = bool(valor) and len(valor) < 3

    if ocupado:
        motivo = f"El usuario «{_esc(valor)}» ya existe."
    elif comun:
        motivo = f"El usuario «{_esc(valor)}» es demasiado común y fácil de adivinar."
    elif corto:
        motivo = "El usuario debe tener al menos 3 caracteres."
    elif not valor and (nombre or correo):
        motivo = "Sugerencias a partir del nombre y del correo."
    else:
        return usuario

    sugerencias = sugerir_usuarios(nombre, correo, ocupados)
    if not sugerencias:
        if ocupado or comun or corto:
            mostrar(f'<div class="sire-req-i" style="color:#9E2B2B;font-weight:700">{icono("alerta", 18, "#9E2B2B", 2.2)}<span>{motivo}</span></div>')
        return usuario

    with st.container(key="sire_sugerencias"):
        mostrar(f'<div class="sire-req-i" style="color:#33485A"><span>{motivo} Haga clic en una opción para usarla:</span></div>')
        cols = st.columns(min(len(sugerencias), 4))
        for i, (col, sug) in enumerate(zip(cols, sugerencias)):
            with col:
                st.button(
                    sug, key=f"{key}_sug_{i}", use_container_width=True,
                    on_click=lambda v=sug: st.session_state.__setitem__(key, v),
                )
    return usuario


# ============================================================
# CORREO CON DOBLE VERIFICACIÓN
# ============================================================

def _aplicar_sugerencia(key_correo: str, key_repetido: str, key_confirma: str, correo: str):
    st.session_state[key_correo] = correo
    st.session_state[key_repetido] = correo
    st.session_state.pop(key_confirma, None)


def campos_correo_verificado(
    key_correo: str,
    key_repetido: str,
    key_confirma: str,
    key_sugerencia: str,
    etiqueta: str = "Correo electrónico *",
    etiqueta_repetido: str = "Repita el correo electrónico *",
    ayuda: str = "A este correo se enviará el acuse de recibo.",
    que_recibira: str = "el acuse de recibo",
):
    """
    Dos campos de correo (se escribe dos veces), con las reglas de
    src/validacion_correo.py: coincidencia, dominio institucional
    (nombre@essalud.gob.pe), sugerencia de corrección con un clic y
    confirmación expresa para otros dominios. Devuelve (correo_normalizado, evaluación).
    """
    from src.validacion_correo import evaluar, normalizar
    from utils.helpers import sanitizar_html
    from utils.tema import mostrar_aviso

    c1, c2 = st.columns(2)
    with c1:
        correo = st.text_input(etiqueta, placeholder="nombre@essalud.gob.pe", key=key_correo, help=ayuda)
    with c2:
        repetido = st.text_input(
            etiqueta_repetido, placeholder="Escríbalo de nuevo", key=key_repetido,
            help="Se pide dos veces para evitar errores de escritura: si el correo está mal, no recibirá el mensaje.")

    ev = evaluar(correo, repetido, bool(st.session_state.get(key_confirma, False)))

    if ev["sugerencia"]:
        sug = ev["sugerencia"]
        with st.container(key=key_sugerencia):
            mostrar_aviso("warn", "Revise el correo",
                          f"{sanitizar_html(ev['detalle'])} ¿Quiso escribir <strong>{sanitizar_html(sug)}</strong>?")
            st.button(f"Usar {sug}", key=f"{key_sugerencia}_btn", icon=":material/check:",
                      on_click=_aplicar_sugerencia, args=(key_correo, key_repetido, key_confirma, sug))
    elif ev["estado"] == "error" and ev["detalle"]:
        mostrar_aviso("bad", ev["mensaje"], sanitizar_html(ev["detalle"]))
    elif ev["requiere_confirmacion"]:
        st.checkbox(f"Confirmo que {normalizar(correo)} es correcto y que allí recibiré {que_recibira}",
                    key=key_confirma)
        if ev["estado"] == "pendiente":
            mostrar_aviso("warn", "Correo no institucional", sanitizar_html(ev["detalle"]))
    elif ev["estado"] == "ok":
        mostrar(f'<div class="sire-correo-ok">{icono("check", 18, "#1E6B3A", 2.4)}'
                f'<span>Enviaremos {que_recibira} a <strong>{sanitizar_html(normalizar(correo))}</strong></span></div>')
    return normalizar(correo), ev

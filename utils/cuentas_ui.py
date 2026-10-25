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

from typing import Iterable, Sequence

import streamlit as st

from src.password_policy import (
    evaluar, fuerza, generar, sugerir_usuarios, usuario_demasiado_comun,
)
from utils.tema import TONOS, icono, mostrar

_COLOR_FUERZA = {0: "#C4D6E6", 1: "#B42318", 2: "#B7791F", 3: "#2A8FD0", 4: "#1E6B3A"}


def _esc(texto: str) -> str:
    import html
    return html.escape(str(texto or ""), quote=True)


# ============================================================
# REQUISITOS DE CONTRASEÑA
# ============================================================

def requisitos_html(password: str, contexto: Sequence[str] = (), actual: str = None) -> str:
    """Lista de requisitos (cumplidos en verde) y barra de fortaleza, como HTML."""
    reqs = evaluar(password, contexto, actual)
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

    nivel, etiqueta = fuerza(password, contexto, actual)
    color = _COLOR_FUERZA[nivel]
    segmentos = "".join(
        f'<i style="background:{color if i < nivel else "#E3EEF7"}"></i>' for i in range(4)
    )
    barra = (
        f'<div class="sire-fuerza"><div class="sire-fuerza-p" role="img" aria-label="Fortaleza: {etiqueta}">{segmentos}</div>'
        f'<span class="sire-fuerza-n" style="color:{color if nivel else "#4F6070"}">{etiqueta}</span></div>'
    )
    return f'<div class="sire-req"><div class="sire-req-t">Su contraseña debe cumplir</div>{barra}{"".join(items)}</div>'


def explicacion_requisitos(titulo: str = "¿Por qué pedimos esto?"):
    """Desplegable que explica el motivo de cada requisito, en lenguaje sencillo."""
    reqs = evaluar("")  # solo para leer los textos y motivos
    lis = "".join(f"<li><b>{_esc(r.texto)}.</b> {_esc(r.motivo)}</li>" for r in reqs)
    with st.expander(titulo):
        mostrar(
            '<div class="sire-porque">Los reportes epidemiológicos son información sensible de EsSalud. '
            'Una contraseña débil permite que otra persona entre con su cuenta y envíe o consulte datos en su nombre. '
            f"<ul>{lis}</ul>"
            "<p style=\"margin:10px 0 0\">Un consejo práctico: una frase corta con palabras que solo usted conozca, "
            "combinada con números y un símbolo, es fácil de recordar y difícil de adivinar.</p></div>"
        )


def campos_nueva_password(
    prefijo: str,
    contexto: Iterable[str] = (),
    actual: str = None,
    etiqueta_nueva: str = "Nueva contraseña",
    etiqueta_confirmar: str = "Confirmar nueva contraseña",
    ofrecer_generador: bool = False,
):
    """
    Dibuja los dos campos de contraseña con la lista de requisitos y devuelve
    (nueva, confirmar). Los campos viven fuera de un formulario para que la
    lista se actualice al terminar de escribir (al salir del campo o con Enter).
    """
    contexto = list(contexto)
    k_nueva, k_conf = f"{prefijo}_nueva", f"{prefijo}_confirmar"

    if ofrecer_generador:
        def _generar():
            g = generar()
            st.session_state[k_nueva] = g
            st.session_state[k_conf] = g
            st.session_state[f"{prefijo}_generada"] = g
        st.button("Generar una contraseña segura", key=f"{prefijo}_btn_generar", on_click=_generar,
                  icon=":material/autorenew:")
        generada = st.session_state.get(f"{prefijo}_generada")
        if generada and st.session_state.get(k_nueva) == generada:
            mostrar(
                '<div class="sire-aviso" style="background:#FFF4D6;border:1px solid #EBD08A;border-left:5px solid #B7791F">'
                f'{icono("alerta", 20, "#7A5A00")}<div><div class="sire-aviso-t" style="color:#7A5A00">Contraseña generada</div>'
                f'<code style="font-size:15px">{_esc(generada)}</code><br>'
                'Cópiela y entréguela por un canal seguro: no se volverá a mostrar.</div></div>'
            )

    nueva = st.text_input(etiqueta_nueva, type="password", key=k_nueva, autocomplete="new-password")
    confirmar = st.text_input(etiqueta_confirmar, type="password", key=k_conf, autocomplete="new-password")

    mostrar(requisitos_html(nueva, contexto, actual))
    if confirmar:
        if nueva == confirmar:
            mostrar(f'<div class="sire-req-i ok" style="margin:-4px 0 8px">{icono("check", 18, TONOS["ok"][0], 2.4)}<span>Las contraseñas coinciden</span></div>')
        else:
            mostrar(f'<div class="sire-req-i" style="margin:-4px 0 8px;color:#9E2B2B;font-weight:700">{icono("alerta", 18, "#9E2B2B", 2.2)}<span>Las contraseñas no coinciden</span></div>')
    explicacion_requisitos()
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

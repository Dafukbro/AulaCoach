"""
AulaCoach — punto de entrada.

    python -m streamlit run app.py

Flujo:
  1. Si la escuela aún no tiene cuenta de dirección -> configuración inicial
     (solo desde la computadora de la escuela).
  2. Sin sesión -> entrar / crear cuenta de docente.
  3. Contraseña temporal -> crear una propia.
  4. Dirección -> panel de la dirección.   Docente -> su salón y sus ideas.
"""

import logging
import threading
import time

import streamlit as st

import BaseDatos as BD
import Interfaz as ui
import Motor
import Seguridad as seg

log = logging.getLogger("aulacoach")


# ---------------------------------------------------------------------------
# Arranque (una sola vez por proceso, no en cada clic)
# ---------------------------------------------------------------------------

def _precargar_modelo() -> None:
    """Carga el modelo en memoria al encender el servidor, para que el primer
    docente del día no espere la carga."""
    try:
        import ollama
        ollama.generate(model=Motor.MODELO, prompt="", keep_alive=-1)
    except Exception as error:  # Ollama apagado o modelo sin descargar: se avisa al usarlo
        log.warning("No se pudo precargar el modelo %s: %s", Motor.MODELO, error)


@st.cache_resource(show_spinner=False)
def arranque() -> threading.Lock:
    BD.inicializar_bd()
    threading.Thread(target=_precargar_modelo, daemon=True).start()
    # Un solo turno para el modelo: en una PC modesta, dos consultas a la vez
    # tardan más que dos seguidas.
    return threading.Lock()


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------

def sesion_actual() -> tuple[BD.Usuario | None, str | None]:
    token = st.session_state.get("token") or ui.leer_cookie()
    usuario = BD.usuario_de_sesion(token)
    if usuario:
        st.session_state.token = token
        return usuario, token
    st.session_state.pop("token", None)
    return None, None


def iniciar_sesion(usuario: BD.Usuario) -> None:
    token, segundos = BD.crear_sesion(usuario)
    st.session_state.clear()
    st.session_state.token = token
    st.session_state.cookie_pendiente = (token, segundos)
    st.rerun()


def salir(token: str | None) -> None:
    BD.cerrar_sesion(token)
    st.session_state.clear()
    st.session_state.borrar_cookie = True
    st.rerun()


# ---------------------------------------------------------------------------
# Pantallas sin sesión
# ---------------------------------------------------------------------------

def pantalla_configuracion_inicial() -> None:
    ui.portada("Antes de empezar, la dirección crea su cuenta.")
    if st.context.ip_address is not None:
        # Nadie desde la red Wi-Fi puede adueñarse de la escuela antes que la dirección.
        ui.nota("AulaCoach aún no está listo. La dirección debe abrirlo una primera vez en "
                "la computadora de la escuela para crear su cuenta.")
        return

    ui.parrafo("Crea la cuenta de la dirección. Con ella verás la actividad de los docentes "
               "y podrás darles una contraseña temporal si olvidan la suya.", "subtitulo")
    with st.form("form_direccion", border=False):
        nombre = st.text_input("Nombre", placeholder="Ej.: Directora Ana Pérez", max_chars=60)
        usuario = st.text_input("Usuario", value="direccion", max_chars=30, autocomplete="username")
        clave = st.text_input("Contraseña", type="password", max_chars=128, autocomplete="new-password",
                              help=f"Mínimo {seg.CLAVE_MINIMA_DIRECCION} caracteres. Esta cuenta ve todo: "
                                   "que sea difícil de adivinar.")
        clave2 = st.text_input("Repite la contraseña", type="password", max_chars=128,
                               autocomplete="new-password")
        enviar = st.form_submit_button("Crear cuenta de la dirección", type="primary", width="stretch")

    if enviar:
        usuario_n, error = seg.validar_usuario(usuario)
        error = error or (None if nombre.strip() else "Escribe un nombre.")
        error = error or seg.validar_clave(clave, usuario_n, seg.CLAVE_MINIMA_DIRECCION)
        error = error or (None if clave == clave2 else "Las contraseñas no coinciden.")
        if error:
            ui.nota(error, "alerta")
            return
        if BD.hay_direccion():  # otra pestaña se adelantó
            st.rerun()
        BD.crear_usuario(usuario_n, nombre, clave, rol="admin")
        usuario_obj, _ = BD.autenticar(usuario_n, clave)
        iniciar_sesion(usuario_obj)


def _form_entrar() -> None:
    with st.form("form_entrar", border=False):
        usuario = st.text_input("Usuario", placeholder="Ej.: maria.lopez", max_chars=30,
                                autocomplete="username")
        clave = st.text_input("Contraseña", type="password", max_chars=128,
                              autocomplete="current-password")
        enviar = st.form_submit_button("Entrar", type="primary", width="stretch")
    if enviar:
        if not usuario.strip() or not clave:
            ui.nota("Escribe tu usuario y tu contraseña.", "alerta")
            return
        cuenta, error = BD.autenticar(usuario, clave)
        if error:
            time.sleep(0.8)  # frena a quien intente adivinar contraseñas; un docente ni lo nota
            ui.nota(error, "alerta")
            return
        iniciar_sesion(cuenta)
    ui.parrafo("¿Olvidaste tu contraseña? La dirección puede darte una temporal.", "tenue")


def _form_registro() -> None:
    with st.form("form_registro", border=False):
        nombre = st.text_input("¿Cómo te dicen tus estudiantes?", placeholder="Ej.: Profe María", max_chars=60)
        usuario = st.text_input("Elige un usuario", placeholder="Ej.: maria.lopez", max_chars=30,
                                autocomplete="username", help="Sin espacios. Lo usarás para entrar.")
        clave = st.text_input("Crea una contraseña", type="password", max_chars=128,
                              autocomplete="new-password",
                              help=f"Mínimo {seg.CLAVE_MINIMA_DOCENTE} caracteres. Puede ser una frase corta.")
        enviar = st.form_submit_button("Crear mi cuenta", type="primary", width="stretch")
    ui.parrafo("La dirección de tu escuela podrá ver las ideas y consejos que guardes aquí.", "tenue")

    if enviar:
        usuario_n, error = seg.validar_usuario(usuario)
        error = (None if nombre.strip() else "Escribe tu nombre.") or error
        error = error or seg.validar_clave(clave, usuario_n)
        if not error and not BD.usuario_libre(usuario_n):
            error = "Ese usuario ya existe. Elige otro."
        if error:
            ui.nota(error, "alerta")
            return
        try:
            BD.crear_usuario(usuario_n, nombre, clave)
        except ValueError as ex:
            ui.nota(str(ex), "alerta")
            return
        cuenta, _ = BD.autenticar(usuario_n, clave)
        iniciar_sesion(cuenta)


def pantalla_entrada() -> None:
    ui.portada("Dos ideas para tu clase de hoy.<br>Un consejo cuando termines.")
    if BD.registro_abierto():
        entrar, registro = st.tabs(["Entrar", "Crear cuenta"], key="entrada_pestana", on_change="rerun")
        if entrar.open:
            with entrar:
                _form_entrar()
        if registro.open:
            with registro:
                _form_registro()
    else:
        _form_entrar()
        ui.parrafo("Para tener una cuenta, pídela a la dirección.", "tenue")


def pantalla_cambiar_clave(usuario: BD.Usuario, token: str, forzada: bool) -> None:
    ui.marca()
    if forzada:
        st.title("Crea tu contraseña")
        ui.parrafo("Entraste con una contraseña temporal. Elige una que solo tú conozcas.", "subtitulo")
    else:
        st.title("Cambiar contraseña")
    minimo = seg.CLAVE_MINIMA_DIRECCION if usuario.es_direccion else seg.CLAVE_MINIMA_DOCENTE
    with st.form("form_clave", border=False):
        actual = None if forzada else st.text_input("Contraseña actual", type="password", max_chars=128,
                                                   autocomplete="current-password")
        nueva = st.text_input("Nueva contraseña", type="password", max_chars=128, autocomplete="new-password",
                              help=f"Mínimo {minimo} caracteres. Puede ser una frase corta.")
        enviar = st.form_submit_button("Guardar contraseña", type="primary", width="stretch")
    if not forzada and st.button("Volver", width="stretch"):
        st.session_state.vista = None
        st.rerun()
    if enviar:
        error = BD.cambiar_clave(usuario, actual, nueva, token_actual=token)
        if error:
            ui.nota(error, "alerta")
            return
        st.session_state.vista = None
        st.session_state.aviso = "Listo, tu contraseña quedó guardada."
        st.rerun()


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------

def main() -> None:
    lock = arranque()
    usuario, token = sesion_actual()

    st.set_page_config(
        page_title="AulaCoach",
        page_icon=":material/local_library:",
        layout="wide" if usuario and usuario.es_direccion else "centered",
        initial_sidebar_state="collapsed",
        menu_items={"Get help": None, "Report a bug": None,
                    "About": "AulaCoach: acompañante pedagógico que funciona sin internet."},
    )
    ui.aplicar_estilo(ancho=bool(usuario and usuario.es_direccion))

    # La cookie se escribe en el navegador una vez que la página ya cargó.
    if "cookie_pendiente" in st.session_state:
        ui.guardar_cookie(*st.session_state.pop("cookie_pendiente"))
    if st.session_state.pop("borrar_cookie", False):
        ui.borrar_cookie()

    if not BD.hay_direccion():
        pantalla_configuracion_inicial()
        return
    if not usuario:
        pantalla_entrada()
        return
    if usuario.debe_cambiar_clave:
        pantalla_cambiar_clave(usuario, token, forzada=True)
        return
    if st.session_state.get("vista") == "clave":
        pantalla_cambiar_clave(usuario, token, forzada=False)
        return

    acciones = {"salir": lambda: salir(token)}
    if usuario.es_direccion:
        import Direccion
        Direccion.mostrar(usuario, acciones)
    else:
        import Docente
        Docente.mostrar(usuario, lock, acciones)


main()

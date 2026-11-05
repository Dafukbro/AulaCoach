"""
Panel de la dirección: ver la actividad de los docentes, ayudarles con su
contraseña y respaldar la base de datos. Cada función de BaseDatos que usa este
panel vuelve a comprobar que quien la pide es la dirección.
"""

from datetime import datetime

import streamlit as st

import BaseDatos as BD
import Interfaz as ui
import Motor
import Seguridad as seg


def _estado(d: dict) -> str:
    if not d["activo"]:
        return "Desactivada"
    if d["sin_clave"]:
        return "Sin contraseña"
    if d["bloqueado_hasta"] and d["bloqueado_hasta"] > datetime.now().strftime("%Y-%m-%d %H:%M:%S"):
        return "Bloqueada por intentos"
    if d["debe_cambiar_clave"]:
        return "Con contraseña temporal"
    return "Activa"


def _mostrar_temporal() -> None:
    temporal = st.session_state.get("temporal")
    if temporal:
        nombre, clave = temporal
        st.markdown(
            f'<div class="nota nota-clave">Contraseña temporal de {ui.esc(nombre)}: <b>{ui.esc(clave)}</b><br>'
            "Dígasela en persona. Al entrar tendrá que crear una propia.</div>",
            unsafe_allow_html=True)
        if st.button("Ya la anoté", key="dir_temp_ok"):
            st.session_state.pop("temporal", None)
            st.rerun()


_CUENTAS_DEMO = ("profe.maria", "profe.carlos", "profe.elena")


def _panel_qr(usuario: BD.Usuario) -> None:
    with st.expander("Conectar celulares (código QR)", icon=":material/qr_code_2:"):
        urls = ui.direcciones_red()
        otra = "Otra dirección"
        opciones = [*urls, otra]
        eleccion = st.pills("Dirección para los celulares", opciones, default=urls[0], key="dir_qr_op")
        if eleccion == otra:
            url = st.text_input("Escriba o pegue la dirección (ej.: túnel público o IP)", value=urls[0],
                                max_chars=100, key="dir_qr_txt").strip()
        else:
            url = eleccion or urls[0]
        registrados = {d["usuario"] for d in BD.resumen_docentes(usuario)}
        demos = [u for u in _CUENTAS_DEMO if u in registrados]
        if url:
            ui.tarjeta_qr(url, cuentas_demo=demos or None)


def resumen(usuario: BD.Usuario) -> None:
    t = BD.totales(usuario, dias=7)
    ideas = "1 idea preparada" if t["ideas"] == 1 else f"{t['ideas']} ideas preparadas"
    clases = "1 clase reflexionada" if t["consejos"] == 1 else f"{t['consejos']} clases reflexionadas"
    probados = "reto probado en clase" if t["probados"] == 1 else "retos probados en clase"
    funcionaron = f"{t['funcionaron']} funcionó" if t["funcionaron"] == 1 else f"{t['funcionaron']} funcionaron"
    st.markdown(
        f"""<div class="pizarron">
              <p class="tiza-titulo">Los últimos 7 días</p>
              <div class="cifras">
                <div><span class="cifra">{t['activos']} de {t['docentes']}</span>
                     <span class="cifra-texto">docentes usaron AulaCoach</span></div>
                <div><span class="cifra">{t['ideas']}</span>
                     <span class="cifra-texto">{ideas.split(' ', 1)[1]}</span></div>
                <div><span class="cifra">{t['consejos']}</span>
                     <span class="cifra-texto">{clases.split(' ', 1)[1]}</span></div>
                <div><span class="cifra">{t['probados']}</span>
                     <span class="cifra-texto">{probados} ({funcionaron})</span></div>
              </div>
            </div>""",
        unsafe_allow_html=True)

    avisos = BD.alertas(usuario, dias=30)
    if avisos:
        with st.container(key="alerta_direccion"):
            ui.parrafo("Registros que pueden necesitar su atención", "rojo-titulo")
            ui.parrafo("AulaCoach no dio consejos sobre estos casos: indicó al docente seguir el protocolo "
                       "de protección y avisar a la dirección.", "tenue")
            for a in avisos:
                ui.parrafo(f"{a['nombre']} ({ui.fecha_corta(a['fecha'])}), en {a['tema'].strip()}: "
                           f"«{a['que_costo']}»")

    temas = BD.competencias_escuela(usuario, dias=30)
    if temas:
        st.subheader("En qué piden más apoyo")
        ui.parrafo("Lo más difícil en las clases del último mes, según lo que cuentan los docentes. "
                   "Sirve para elegir el próximo taller o la próxima visita de acompañamiento.", "tenue")
        ui.barras_competencias(temas)

    docentes = BD.resumen_docentes(usuario)
    st.subheader("Actividad por docente")
    if not docentes:
        ui.nota("Aún no hay docentes registrados. Pueden crear su cuenta desde su celular, "
                "o puede crearla usted en la pestaña Docentes.")
        return
    filas = [{"Docente": d["nombre"], "Grado": d["grado"] or "—", "Ideas": d["ideas"],
              "Reflexiones": d["consejos"], "Retos probados": d["retos_probados"],
              "Funcionaron": d["retos_funcionaron"],
              "Última actividad": ui.fecha_corta(d["ultima_actividad"] or None),
              "Cuenta": _estado(d)} for d in docentes]
    st.dataframe(filas, hide_index=True, width="stretch")


def docentes(usuario: BD.Usuario) -> None:
    lista = BD.resumen_docentes(usuario)
    pendientes = [d for d in lista if d["sin_clave"] and d["activo"]]
    if pendientes:
        cuantas = "1 cuenta" if len(pendientes) == 1 else f"{len(pendientes)} cuentas"
        ui.nota(f"{cuantas} de la versión anterior aún sin contraseña: "
                + ", ".join(d["nombre"] for d in pendientes)
                + ". Elija cada una abajo y toque «Dar contraseña temporal».")

    if lista:
        por_id = {d["id"]: d for d in lista}
        elegido = st.selectbox("Docente", list(por_id), index=None, placeholder="Elija un docente",
                               format_func=lambda i: f"{por_id[i]['nombre']} ({por_id[i]['usuario']})",
                               key="dir_docente")
        if elegido:
            d = por_id[elegido]
            acceso = ui.fecha_corta(d["ultimo_acceso"])
            ui.parrafo(f"Usuario {d['usuario']}. Cuenta: {_estado(d).lower()}. "
                       f"Último acceso: {acceso}{'' if acceso.endswith('.') else '.'}", "tenue")
            with st.container(horizontal=True, gap="small"):
                if st.button("Dar contraseña temporal", key="dir_temp"):
                    clave = BD.restablecer_clave(usuario, d["id"])
                    st.session_state.temporal = (d["nombre"], clave)
                    st.rerun()
                if d["activo"]:
                    if st.button("Desactivar cuenta", key="dir_off",
                                 help="No podrá entrar. Sus ideas y consejos se conservan."):
                        BD.cambiar_estado(usuario, d["id"], False)
                        st.rerun()
                elif st.button("Activar cuenta", key="dir_on"):
                    BD.cambiar_estado(usuario, d["id"], True)
                    st.rerun()

            entradas = BD.actividad_docente(usuario, d["id"], limite=30)
            st.subheader(f"Lo que ha trabajado {d['nombre']}")
            if entradas:
                ui.lista_entradas(entradas, f"dir{d['id']}")
            else:
                ui.parrafo("Todavía no ha preparado ideas ni reflexiones.", "tenue")

    with st.expander("Crear una cuenta de docente"):
        with st.form("dir_nuevo", border=False, clear_on_submit=True):
            nombre = st.text_input("Nombre", placeholder="Ej.: Profe Luis Pérez", max_chars=60)
            cuenta = st.text_input("Usuario", placeholder="Ej.: luis.perez", max_chars=30)
            crear = st.form_submit_button("Crear cuenta", type="primary")
        if crear:
            cuenta_n, error = seg.validar_usuario(cuenta)
            error = (None if nombre.strip() else "Escriba el nombre.") or error
            if not error:
                try:
                    clave = BD.crear_docente(usuario, cuenta_n, nombre)
                    st.session_state.temporal = (nombre.strip(), clave)
                    st.rerun()
                except ValueError as ex:
                    error = str(ex)
            ui.nota(error, "alerta")


def ajustes(usuario: BD.Usuario) -> None:
    abierto = st.toggle("Los docentes pueden crear su propia cuenta", value=BD.registro_abierto(),
                        help="Si lo apaga, solo usted podrá crear cuentas desde la pestaña Docentes.")
    if abierto != BD.registro_abierto():
        BD.guardar_ajuste(usuario, "registro_abierto", "1" if abierto else "0")

    st.subheader("Copia de seguridad")
    ui.parrafo("Guárdela en una memoria USB una vez por semana. Contiene la actividad de todos los "
               "docentes: guárdela en un lugar seguro.", "tenue")
    st.download_button("Descargar copia", data=lambda: BD.copia_de_respaldo(usuario),
                       file_name=f"aulacoach-{datetime.now():%Y-%m-%d}.db",
                       mime="application/octet-stream", key="dir_respaldo")

    st.subheader("Asistente de IA")
    ui.parrafo(f"Modelo configurado: {Motor.MODELO}", "tenue")
    if st.button("Comprobar que responde", key="dir_comprobar"):
        try:
            import ollama
            cargados = [m.model for m in ollama.ps().models]
            instalados = [m.model for m in ollama.list().models]
            if any(n.startswith(Motor.MODELO) for n in cargados):
                ui.nota("El asistente está listo y cargado en memoria.", "clave")
            elif any(n.startswith(Motor.MODELO) for n in instalados):
                ui.nota("El modelo está instalado. Se cargará con la primera consulta (tarda unos segundos).")
            else:
                ui.nota(f"Ollama está abierto, pero falta descargar el modelo. En la computadora de la "
                        f"escuela, con internet, ejecute: ollama pull {Motor.MODELO}", "alerta")
        except Exception:
            ui.nota("Ollama no responde. Ábralo en la computadora de la escuela y vuelva a comprobar.", "alerta")


def mostrar(usuario: BD.Usuario, acciones: dict) -> None:
    def cambiar_clave():
        st.session_state.vista = "clave"
        st.rerun()

    ui.barra_superior(usuario.nombre, [("Cambiar contraseña", cambiar_clave), ("Salir", acciones["salir"])],
                      subtitulo="Dirección")
    if "aviso" in st.session_state:
        ui.nota(st.session_state.pop("aviso"), "clave")
    st.title("Panel de la dirección")
    _mostrar_temporal()
    _panel_qr(usuario)

    # Con estado: la pestaña abierta se mantiene al tocar algo, y solo se calcula esa.
    t_resumen, t_docentes, t_ajustes = st.tabs(["Resumen", "Docentes", "Ajustes"], key="dir_pestana",
                                                on_change="rerun")
    if t_resumen.open:
        with t_resumen:
            resumen(usuario)
    if t_docentes.open:
        with t_docentes:
            docentes(usuario)
    if t_ajustes.open:
        with t_ajustes:
            ajustes(usuario)

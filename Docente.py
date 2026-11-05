"""
Pantallas del docente. Cada pantalla busca lo mismo: llegar a una idea o a un
consejo con 2 o 3 toques, sin escribir, y que la app recuerde lo de la vez pasada.

  Antes de clase   -> dos micro-rutas, el docente elige y adapta, recibe su micro-acción.
  Después de clase -> ¿probaste el reto?, qué pasó, un paso pequeño para la próxima.
  Mi avance        -> lo que ha probado, lo que le funcionó y su siguiente paso digital.
"""

import logging
import threading
from contextlib import contextmanager
from datetime import datetime

import streamlit as st

import BaseDatos as BD
import Guias
import Interfaz as ui
import Motor
import Seguridad as seg

log = logging.getLogger("aulacoach")

GRADOS = ["Preescolar", "1.º", "2.º", "3.º", "4.º", "5.º", "6.º", "Secundaria"]
TAMANOS = {"Menos de 20": 15, "20 a 30": 25, "30 a 40": 35, "Más de 40": 45}
MATERIALES = ["Pizarrón y tiza", "Hojas recicladas", "Cuadernos", "Libros de texto", "Patio o cancha",
              "Material reciclado", "Cartulina y marcadores", "Proyector", "Bocina", "Computadora"]
TECNOLOGIA = {"No uso tecnología": "basico", "Solo mi celular": "intermedio",
              "Proyector o computadora": "avanzado"}

TEMAS_BASE = ["Fracciones", "Comprensión lectora", "Multiplicación", "Seres vivos",
              "Suma y resta", "Escritura"]
QUE_HICIERON = ["Trabajaron en equipos", "Explicación en el pizarrón", "Salimos al patio",
                "Leímos en voz alta", "Trabajo individual en hojas"]
LO_DIFICIL = list(BD.COMPETENCIAS)   # cada opción corresponde a una competencia de "Mi avance"
OTRO = "Otro"
RESULTADO_RETO = {"Sí, funcionó": "funciono", "Lo probé, no funcionó": "no_funciono", "No lo probé": "no_probe"}
GRUPO = list(Guias.SITUACIONES)

MOMENTOS = ["Antes de clase", "Después de clase", "Mi avance"]

# El siguiente paso digital de cada nivel: pequeño, sin internet y con lo que ya tiene.
PASOS_DIGITALES = {
    "basico": ("Usa el cronómetro de tu celular",
               "En tu próxima dinámica, mide con el cronómetro cuánto dura cada parte. "
               "Los estudiantes no necesitan celular ni internet."),
    "intermedio": ("Graba un minuto de tu clase, solo el sonido",
                   "Graba con tu celular un minuto de una dinámica y escúchalo en casa: "
                   "notarás cuánto hablas tú y cuánto hablan ellos. Bórralo después."),
    "intermedio_con_equipo": ("Proyecta una sola pregunta",
                              "Al empezar la clase, muestra con el proyector o la computadora una imagen "
                              "o la pregunta del día, guardada antes y sin internet."),
    "avanzado": ("Que el grupo produzca algo con la tecnología",
                 "En lugar de solo mostrar, pide a un equipo que use la computadora del salón para "
                 "registrar las respuestas del grupo durante la dinámica."),
}


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

@contextmanager
def turno(lock: threading.Lock):
    """Si otro docente está usando el modelo, espera su turno avisando en pantalla."""
    if not lock.acquire(blocking=False):
        aviso = st.empty()
        aviso.markdown('<p class="tenue">Otro docente está usando el asistente. '
                       'Tu respuesta sale en cuanto termine…</p>', unsafe_allow_html=True)
        if not lock.acquire(timeout=240):
            aviso.empty()
            raise TimeoutError("turno")
        aviso.empty()
    try:
        yield
    finally:
        lock.release()


def mostrar_error_modelo(error: Exception) -> None:
    log.exception("Fallo al consultar el modelo", exc_info=error)
    texto = str(error).lower()
    if isinstance(error, TimeoutError):
        mensaje = "El asistente está muy ocupado. Intenta de nuevo en un minuto."
    elif "not found" in texto or "pull" in texto:
        mensaje = (f"Falta instalar el modelo de IA ({Motor.MODELO}) en la computadora de la escuela. "
                   "Avisa a la dirección.")
    else:
        mensaje = ("No pude conectar con el asistente. Revisa que la computadora de la escuela esté "
                   "encendida y que Ollama esté abierto, o avisa a la dirección.")
    ui.nota(mensaje, "alerta")


def _elegir(etiqueta: str, opciones: list[str], key: str, default: str | None = None,
            otro_placeholder: str = "", max_chars: int = 80) -> str:
    """Píldoras de un toque + campo libre solo si elige 'Otro'."""
    eleccion = st.pills(etiqueta, opciones + [OTRO], default=default if default in opciones else None, key=key)
    if eleccion == OTRO:
        return seg.limpiar_texto(st.text_input("Escríbelo", key=f"{key}_otro", max_chars=max_chars,
                                               placeholder=otro_placeholder), max_chars)
    return eleccion or ""


def _temas(usuario_id: int) -> tuple[list[str], str | None]:
    """Temas recientes del docente primero, luego los comunes. Devuelve (opciones, el más reciente)."""
    recientes = BD.temas_recientes(usuario_id, 4)
    vistos = {t.lower() for t in recientes}
    opciones = recientes + [t for t in TEMAS_BASE if t.lower() not in vistos][: max(0, 7 - len(recientes))]
    return opciones, (recientes[0] if recientes else None)


# ---------------------------------------------------------------------------
# Mi salón (se llena una vez)
# ---------------------------------------------------------------------------

def _materiales_previos(recursos: str) -> tuple[list[str], str]:
    partes = [p.strip() for p in recursos.split(",") if p.strip()]
    elegidos, otros = [], []
    for p in partes:
        coincide = next((m for m in MATERIALES if m.lower() == p.lower()), None)
        (elegidos if coincide else otros).append(coincide or p)
    return elegidos, ", ".join(otros)


def formulario_salon(usuario: BD.Usuario, perfil: Motor.PerfilDocente | None) -> None:
    nuevo = perfil is None
    st.title("Cuéntame de tu salón" if nuevo else "Tu salón")
    ui.parrafo("Solo te lo pregunto una vez. Así las ideas usan lo que de verdad tienes."
               if nuevo else "Cámbialo cuando quieras.", "subtitulo")

    grado_prev = (perfil.grado.replace(" grado", "") if perfil else None)
    tam_prev = None
    if perfil:
        tam_prev = min(TAMANOS, key=lambda k: abs(TAMANOS[k] - (perfil.estudiantes or 30)))
    mats_prev, otros_prev = _materiales_previos(perfil.recursos) if perfil else (["Pizarrón y tiza", "Hojas recicladas"], "")
    tec_prev = next((k for k, v in TECNOLOGIA.items() if perfil and v == Motor.nivel_clave(perfil.nivel_digital)),
                    "No uso tecnología")

    grado = st.pills("¿Qué grado das?", GRADOS, default=grado_prev if grado_prev in GRADOS else None, key="s_grado")
    tam = st.pills("¿Cuántos estudiantes tienes?", list(TAMANOS), default=tam_prev or "20 a 30", key="s_tam")
    mats = st.pills("¿Qué hay en tu salón?", MATERIALES, selection_mode="multi", default=mats_prev, key="s_mats")
    otros = st.text_input("¿Algo más?", value=otros_prev, max_chars=150, key="s_otros",
                          placeholder="Opcional. Ej.: tapitas, semillas, una grabadora")
    tec = st.pills("¿Usas tecnología en clase?", list(TECNOLOGIA), default=tec_prev, key="s_tec")

    falta = None if grado else "Toca tu grado para continuar."
    if falta:
        ui.parrafo(falta, "tenue")
    if st.button("Guardar" if not nuevo else "Guardar y empezar", type="primary", width="stretch",
                 disabled=bool(falta)):
        recursos = [m.lower() for m in (mats or [])]
        extra = seg.limpiar_texto(otros, 150)
        if extra:
            recursos.append(extra)
        grado_txt = grado if grado in ("Preescolar", "Secundaria") else f"{grado} grado"
        BD.guardar_perfil(usuario.id, grado_txt, TAMANOS[tam or "20 a 30"],
                          TECNOLOGIA[tec or "No uso tecnología"], ", ".join(recursos) or "pizarrón y voz")
        _cerrar_salon()
    if not nuevo and st.button("Cancelar", width="stretch"):
        _cerrar_salon()


def _cerrar_salon() -> None:
    for k in ("s_grado", "s_tam", "s_mats", "s_otros", "s_tec"):
        st.session_state.pop(k, None)  # la próxima vez el formulario abre con lo guardado
    st.session_state.vista = None
    st.rerun()


# ---------------------------------------------------------------------------
# Antes de clase
# ---------------------------------------------------------------------------

def _mostrar_mientras_escribe(generador) -> str:
    """Muestra el texto a medida que llega y devuelve el original (sin formato) para guardarlo."""
    crudo: list[str] = []

    def copiar():
        for parte in generador:
            crudo.append(parte)
            yield parte

    st.write_stream(ui.flujo_modelo(copiar()))
    return "".join(crudo)


def _texto_grupo(elegidos: list[str] | None) -> str:
    return ", ".join(elegidos or [])


def _generar_idea(perfil, tema: str, minutos: int, grupo: str, guia: str,
                  lock: threading.Lock) -> tuple[str | None, bool]:
    """Escribe las dos rutas en el pizarrón mientras llegan. Devuelve (texto, riesgo)."""
    zona = st.empty()
    ui.desplazar_a("pizarron_borrador")
    metricas: dict = {}
    try:
        with turno(lock):
            with zona.container(key="pizarron_borrador"):
                ui.parrafo(f"{tema}, para {minutos} minutos", "tiza-titulo")
                texto = _mostrar_mientras_escribe(
                    Motor.generar_plan(perfil, tema, minutos=minutos, guia=guia, grupo=grupo, metricas=metricas))
            # Revisión en Python: materiales que no tiene, rutas que no caben en el tiempo
            # o que ponen de pie al grupo sin motivo. Si hace falta, se reescriben una vez.
            _, evitar = Motor.revisar_plan(texto, perfil)
            corregir = Motor.revisar_tiempos(texto, minutos)
            if (evitar or corregir) and not metricas.get("riesgo"):
                log.info("Rutas reescritas. Evitar: %s. Corregir: %s", evitar, corregir)
                zona.empty()
                with zona.container(key="pizarron_ajuste"):
                    ui.parrafo("Las borro y las ajusto a tu salón y a tu tiempo.", "tiza-tenue")
                    texto = _mostrar_mientras_escribe(
                        Motor.generar_plan(perfil, tema, minutos=minutos, guia=guia, grupo=grupo,
                                           evitar=evitar, corregir=corregir, metricas=metricas))
    except Exception as error:
        zona.empty()
        mostrar_error_modelo(error)
        return None, False
    zona.empty()
    return (texto.strip() or None), bool(metricas.get("riesgo"))


def _pedir_compromiso(usuario: BD.Usuario, perfil, idea: dict, letra: str, adaptacion: str,
                      lock: threading.Lock) -> None:
    ruta = Motor.ruta_como_texto(idea["rutas"], letra)
    zona = st.empty()
    ui.desplazar_a("pizarron_pensando")
    try:
        with turno(lock):
            with zona.container():
                ui.pizarron_pensando("Pensando en una micro-acción para tu clase…")
            compromiso, _ = Motor.comprometer(perfil, idea["tema"], ruta, adaptacion, idea["grupo"])
    except Exception as error:
        zona.empty()
        mostrar_error_modelo(error)
        return
    zona.empty()
    BD.elegir_ruta(usuario.id, idea["plan_id"], letra, adaptacion, compromiso)
    st.session_state.compromiso = {**compromiso, "ruta": letra}
    st.session_state.compromiso_nuevo = True


def _olvidar_eleccion() -> None:
    for k in ("compromiso", "a_ruta", "a_adapta"):
        st.session_state.pop(k, None)


def antes_de_clase(usuario: BD.Usuario, perfil, lock: threading.Lock) -> None:
    temas, ultimo = _temas(usuario.id)
    tema = _elegir("¿Qué tema darás?", temas, key="a_tema", default=ultimo, otro_placeholder="Ej.: El ciclo del agua")
    minutos_prev = BD.ultimos_minutos(usuario.id) or 15
    minutos = st.pills("¿Cuánto tiempo tienes?", [10, 15, 20, 30, 45], default=minutos_prev if minutos_prev in (10, 15, 20, 30, 45) else 15,
                       format_func=lambda m: f"{m} min", key="a_min")
    grupo_sel = st.pills("¿Cómo viene tu grupo hoy? (opcional)", GRUPO, selection_mode="multi", key="a_grupo")

    pedir = st.button("Darme dos ideas", type="primary", width="stretch", disabled=not tema, key="a_pedir")
    excluir: tuple[str, ...] = ()
    if st.session_state.pop("otra_idea", None):
        previa = st.session_state.idea
        pedir, excluir = True, tuple(previa.get("guias_id", ()))
        tema, minutos, grupo_sel = previa["tema"], previa["minutos"], previa["grupo_sel"]

    if pedir and tema:
        minutos = minutos or 15
        grupo = _texto_grupo(grupo_sel)
        situacion = " ".join(Guias.SITUACIONES.get(g, "") for g in grupo_sel or [])
        fichas = Guias.buscar(tema, situacion, perfil.recursos, cuantas=2, excluir=excluir, minutos=minutos)
        if len(fichas) < 2 and excluir:   # ya no quedan fichas nuevas: se repiten las mejores
            fichas = Guias.buscar(tema, situacion, perfil.recursos, cuantas=2, minutos=minutos)
        texto, riesgo = _generar_idea(perfil, tema, minutos, grupo, Guias.texto_para_modelo(fichas, minutos), lock)
        if texto:
            nombres = Guias.nombres(fichas) if not riesgo else []
            plan_id = BD.guardar_plan(usuario.id, tema, minutos, texto, contexto=grupo,
                                      guias=" y ".join(nombres), riesgo=riesgo)
            _olvidar_eleccion()
            st.session_state.idea = {"tema": tema, "minutos": minutos, "texto": texto, "plan_id": plan_id,
                                     "rutas": Motor.separar_rutas(texto), "grupo": grupo,
                                     "grupo_sel": list(grupo_sel or []), "guias": nombres,
                                     "guias_id": [f["id"] for f in fichas], "riesgo": riesgo}

    idea = st.session_state.get("idea")
    if not idea:
        if not (pedir and tema):
            ui.pizarron_vacio()
        return

    if idea["riesgo"]:
        with st.container(key="alerta_idea"):
            ui.parrafo("Esto necesita a una persona", "rojo-titulo")
            ui.parrafo(Motor.MENSAJE_RIESGO)
        return

    compromiso = st.session_state.get("compromiso")
    con_rutas = ui.tiene_rutas(idea["rutas"])
    elegida = compromiso["ruta"] if compromiso else st.session_state.get("a_ruta")
    ui.pizarron_rutas(f"{idea['tema']}, para {idea['minutos']} minutos", idea["rutas"], idea["guias"],
                      elegida=elegida, texto_crudo=idea["texto"])

    if con_rutas and not compromiso:
        rutas = idea["rutas"]
        letra = st.pills("¿Cuál vas a usar?", ["A", "B"], key="a_ruta",
                         format_func=lambda l: f"Ruta {l}: {rutas[l]['nombre'].replace('**', '')}")
        adaptacion = st.text_input("¿Cómo la vas a adaptar a tu grupo? (opcional)", key="a_adapta", max_chars=200,
                                   placeholder="Ej.: La hago sentados, por filas")
        ui.dictado()
        if st.button("Darme mi micro-acción", type="primary", width="stretch", disabled=not letra,
                     key="a_comprometer"):
            _pedir_compromiso(usuario, perfil, idea, letra, seg.limpiar_texto(adaptacion, 200), lock)
            compromiso = st.session_state.get("compromiso")
            if compromiso:
                st.rerun()   # vuelve a pintar el pizarrón con la ruta elegida encerrada

    if compromiso:
        if st.session_state.pop("compromiso_nuevo", False):
            ui.desplazar_a("nota_compromiso")
        ui.tarjeta_compromiso(compromiso, f"Ruta {compromiso['ruta']}")
        if st.button("Cambiar mi elección", width="stretch", key="a_cambiar",
                     disabled=bool(compromiso.get("riesgo"))):
            _olvidar_eleccion()
            st.rerun()
    elif not con_rutas:
        ui.parrafo("Quedó guardada en tus ideas. Después de la clase, cuéntame cómo te fue.", "tenue")

    if st.button("Quiero otras dos ideas", width="stretch", key="a_otra"):
        st.session_state.otra_idea = True
        st.rerun()


# ---------------------------------------------------------------------------
# Después de clase
# ---------------------------------------------------------------------------

def _guardar_resultado_reto(usuario_id: int, reto_id: int) -> None:
    """Se guarda al tocar la opción: cuenta en "Mi avance" aunque no pida un consejo."""
    respuesta = st.session_state.get("d_reto")
    if respuesta in RESULTADO_RETO:
        BD.registrar_resultado_reto(usuario_id, reto_id, RESULTADO_RETO[respuesta])


def despues_de_clase(usuario: BD.Usuario, perfil, lock: threading.Lock) -> None:
    # El reto se fija al abrir la pantalla: al responder ya no está "abierto", pero sigue a la vista.
    if "reto_visto" not in st.session_state:
        st.session_state.reto_visto = BD.reto_abierto(usuario.id)
    reto = st.session_state.reto_visto
    resultado_reto = None
    if reto:
        hoy = reto["fecha"][:10] == datetime.now().strftime("%Y-%m-%d")
        ui.nota_reto(reto["texto"], reto.get("que_observar", ""),
                     "Tu reto de hoy" if hoy else "Tu reto de la última vez")
        resultado_reto = st.pills("¿Lo probaste?", list(RESULTADO_RETO), key="d_reto",
                                  on_change=_guardar_resultado_reto, args=(usuario.id, reto["id"]))
        if resultado_reto:
            ui.parrafo("Anotado en tu avance.", "tenue")

    temas, ultimo = _temas(usuario.id)
    tema = _elegir("¿Qué tema diste?", temas, key="d_tema", default=ultimo, otro_placeholder="Ej.: El ciclo del agua")
    que_paso = _elegir("¿Qué hicieron hoy?", QUE_HICIERON, key="d_paso", otro_placeholder="Ej.: Un juego de preguntas")
    que_costo = _elegir("¿Qué fue lo más difícil?", LO_DIFICIL, key="d_costo",
                        otro_placeholder="Ej.: Había mucho ruido afuera", max_chars=150)
    with st.expander("Contarlo con tus palabras o dictarlo (opcional)", icon=":material/mic:"):
        nota = st.text_area("Nota", label_visibility="collapsed", max_chars=300, key="d_nota",
                            placeholder="Lo que quieras recordar. Sin nombres de estudiantes, por favor.")
        ui.dictado()

    listo = bool(tema and que_paso and que_costo)
    if not listo:
        ui.parrafo("Toca una opción en cada pregunta.", "tenue")
    if st.button("Darme un consejo", type="primary", width="stretch", disabled=not listo, key="d_pedir"):
        nota = seg.limpiar_texto(nota, 300)
        texto_costo = f"{que_costo}. {nota}" if nota else que_costo
        accion_anterior = ""
        if reto:
            accion_anterior = f"{reto['texto']} (El docente dice: {resultado_reto})" if resultado_reto else reto["texto"]
        fichas = Guias.buscar(tema, texto_costo, perfil.recursos, cuantas=1)
        zona = st.empty()
        ui.desplazar_a("pizarron_pensando")
        try:
            with turno(lock):
                with zona.container():
                    ui.pizarron_pensando("Pensando en un paso pequeño para tu próxima clase…")
                resultado, _ = Motor.reflexionar(perfil=perfil, tema=tema, que_paso=que_paso,
                                                 que_costo=texto_costo, accion_anterior=accion_anterior,
                                                 guia=Guias.texto_para_modelo(fichas))
        except Exception as error:
            zona.empty()
            mostrar_error_modelo(error)
            return
        zona.empty()
        nombres = Guias.nombres(fichas) if not resultado.get("riesgo") else []
        BD.guardar_bitacora(usuario.id, tema, que_paso, texto_costo, resultado, guias=" y ".join(nombres))
        st.session_state.consejo = {**resultado, "guias": nombres}
        st.session_state.consejo_nuevo = True

    if st.session_state.get("consejo"):
        if st.session_state.pop("consejo_nuevo", False):
            ui.desplazar_a("pizarron_consejo_actual")
            ui.desplazar_a("alerta_actual")
        ui.tarjeta_consejo(st.session_state.consejo, "actual")
        if not st.session_state.consejo.get("riesgo"):
            ui.parrafo("Guardado como tu próximo reto. La próxima vez te preguntaré si lo probaste.", "tenue")


# ---------------------------------------------------------------------------
# Mi avance (panel de evolución docente)
# ---------------------------------------------------------------------------

def _paso_digital(perfil) -> tuple[str, str, str | None]:
    """(título, texto, a qué nivel sube si dice que ya lo probó)."""
    nivel = Motor.nivel_clave(perfil.nivel_digital)
    recursos = Guias.normalizar(perfil.recursos)
    if nivel == "basico":
        return (*PASOS_DIGITALES["basico"], "Ya lo probé: dame ideas que usen mi celular")
    if nivel == "intermedio" and ("proyector" in recursos or "computadora" in recursos):
        return (*PASOS_DIGITALES["intermedio_con_equipo"], "Ya lo probé: dame ideas con proyector o computadora")
    return (*PASOS_DIGITALES[nivel], None)


def mi_avance(usuario: BD.Usuario, perfil) -> None:
    av = BD.avance(usuario.id)
    if not (av["clases"] or av["retos"] or av["ideas"]):
        st.markdown('<div class="pizarron pizarron-vacio"><p class="tiza-titulo">Aquí verás tu avance</p>'
                    '<p class="tiza-tenue">Cada vez que pruebes una micro-acción y me cuentes cómo te fue, '
                    'este pizarrón se va llenando.</p></div>', unsafe_allow_html=True)
    else:
        ui.pizarron_avance(av)

    if av["competencias"]:
        st.subheader("Lo que más has trabajado")
        ui.barras_competencias(av["competencias"])

    if av["ultimos_retos"]:
        st.subheader("Tus retos")
        ui.lista_retos(av["ultimos_retos"])

    st.subheader("Tu siguiente paso digital")
    titulo, texto, boton = _paso_digital(perfil)
    ui.paso_digital(titulo, texto)
    if boton and st.button(boton, width="stretch", key="av_subir"):
        BD.subir_nivel_digital(usuario.id)
        st.session_state.aviso = "Listo. Desde ahora las ideas pueden usar un poco más de tecnología, siempre sin internet."
        st.rerun()

    entradas = BD.historial(usuario.id, limite=8)
    if entradas:
        st.subheader("Tus ideas y consejos")
        ui.lista_entradas(entradas, "doc")


# ---------------------------------------------------------------------------
# Pantalla principal del docente
# ---------------------------------------------------------------------------

def mostrar(usuario: BD.Usuario, lock: threading.Lock, acciones: dict) -> None:
    def ir(vista):
        def _ir():
            st.session_state.vista = vista
            st.rerun()
        return _ir

    ui.barra_superior(usuario.nombre, [("Mi salón", ir("salon")), ("Cambiar contraseña", ir("clave")),
                                       ("Salir", acciones["salir"])])

    perfil = BD.obtener_perfil(usuario.id)
    if perfil is None or st.session_state.get("vista") == "salon":
        formulario_salon(usuario, perfil)
        return

    if "aviso" in st.session_state:
        ui.nota(st.session_state.pop("aviso"), "clave")

    detalle = f"{perfil.grado}, unos {perfil.estudiantes} estudiantes" if perfil.grado else ""
    ui.saludo_docente(usuario.nombre, detalle)

    if "momento" not in st.session_state:
        st.session_state.momento = MOMENTOS[1] if BD.tiene_clase_sin_reflexion(usuario.id) else MOMENTOS[0]
    momento = st.segmented_control("Momento", MOMENTOS, key="momento", required=True,
                                   label_visibility="collapsed", width="stretch",
                                   on_change=lambda: st.session_state.pop("reto_visto", None))

    if momento == MOMENTOS[0]:
        antes_de_clase(usuario, perfil, lock)
    elif momento == MOMENTOS[1]:
        despues_de_clase(usuario, perfil, lock)
    else:
        mi_avance(usuario, perfil)
    ui.pie_privacidad()

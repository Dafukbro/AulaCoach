"""
Piezas de interfaz compartidas: estilo, cookie de sesión, barra superior y tarjetas.

Regla de seguridad: todo texto que escribe una persona o el modelo y se pinta con
HTML pasa por `esc()`. El texto del modelo se pinta con st.markdown, que no
interpreta HTML.
"""

import html
import re
import socket
from datetime import datetime
from pathlib import Path

import streamlit as st

COOKIE_SESION = "aulacoach_sesion"
_CARPETA = Path(__file__).resolve().parent

_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def esc(texto) -> str:
    return html.escape(str(texto or ""), quote=True)


def md_seguro(texto: str) -> str:
    """Para mostrar texto de una persona con st.markdown sin que se interprete como formato."""
    return re.sub(r"([\\`*_{}\[\]<>()#+\-.!|:$~])", r"\\\1", texto or "")


def _separar_secciones(texto: str, previo: str = "") -> str:
    t = re.sub(r"(?<!\n)\n(?=\*\*)", "\n\n", previo + texto)
    return t[len(previo):]


def md_modelo(texto: str) -> str:
    """El modelo escribe markdown. Se separan sus secciones ('**Materiales:**', etc.) para que no
    queden pegadas al último paso de la lista, y se evita que '$' active fórmulas matemáticas."""
    return _separar_secciones(texto or "").replace("$", r"\$")


def flujo_modelo(partes):
    """Lo mismo que md_modelo, mientras el texto va llegando en pedazos."""
    pendiente, ultimo = "", ""
    for parte in partes:
        texto = pendiente + parte
        corte = len(texto)
        for cola in ("\n*", "\n"):  # un posible "\n**" a medio llegar: se espera al siguiente pedazo
            if texto.endswith(cola):
                corte -= len(cola)
                break
        listo, pendiente = texto[:corte], texto[corte:]
        if listo:
            yield _separar_secciones(listo, ultimo).replace("$", r"\$")
            ultimo = listo[-1]
    if pendiente:
        yield _separar_secciones(pendiente, ultimo).replace("$", r"\$")


# ---------------------------------------------------------------------------
# Estilo
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _css() -> str:
    return (_CARPETA / "estilo.css").read_text(encoding="utf-8")


def aplicar_estilo(ancho: bool = False) -> None:
    extra = ".block-container{max-width:72rem}" if ancho else ""
    st.markdown(f"<style>{_css()}{extra}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Cookie de sesión (para no pedir la contraseña cada vez que se recarga la página)
# ---------------------------------------------------------------------------

def leer_cookie() -> str | None:
    return st.context.cookies.get(COOKIE_SESION)


def guardar_cookie(token: str, segundos: int) -> None:
    # El token solo tiene letras, números, '-' y '_' (Seguridad.token_valido), así que es seguro incrustarlo.
    st.html(
        f"""<script>
        (function () {{
          var extra = location.protocol === "https:" ? "; Secure" : "";
          document.cookie = "{COOKIE_SESION}={token}; path=/; max-age={int(segundos)}; SameSite=Strict" + extra;
        }})();
        </script>""",
        unsafe_allow_javascript=True,
    )


def desplazar_a(clave: str) -> None:
    """Lleva la pantalla del celular al resultado apenas empieza a aparecer."""
    st.html(
        f"""<script>
        (function () {{
          var intentos = 0;
          var buscar = function () {{
            var docs = [document];
            try {{ if (window.parent && window.parent.document) docs.push(window.parent.document); }} catch (e) {{}}
            for (var i = 0; i < docs.length; i++) {{
              var el = docs[i].querySelector(".st-key-{clave}");
              if (el) {{ el.scrollIntoView({{behavior: "smooth", block: "start"}}); return; }}
            }}
            if (++intentos < 40) setTimeout(buscar, 100);
          }};
          buscar();
        }})();
        </script>""",
        unsafe_allow_javascript=True,
    )


def borrar_cookie() -> None:
    st.html(
        f"""<script>document.cookie = "{COOKIE_SESION}=; path=/; max-age=0; SameSite=Strict";</script>""",
        unsafe_allow_javascript=True,
    )


# ---------------------------------------------------------------------------
# Textos de fecha y saludo
# ---------------------------------------------------------------------------

def saludo() -> str:
    hora = datetime.now().hour
    if hora < 12:
        return "Buenos días"
    if hora < 19:
        return "Buenas tardes"
    return "Buenas noches"


def fecha_corta(fecha_txt: str | None) -> str:
    if not fecha_txt:
        return "—"
    try:
        fecha = datetime.strptime(fecha_txt[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        return fecha_txt
    hoy = datetime.now().date()
    dias = (hoy - fecha.date()).days
    hora = fecha.strftime("%I:%M").lstrip("0") + (" a. m." if fecha.hour < 12 else " p. m.")
    if dias == 0:
        return f"hoy, {hora}"
    if dias == 1:
        return f"ayer, {hora}"
    texto = f"{fecha.day} {_MESES[fecha.month - 1]}"
    return texto if fecha.year == hoy.year else f"{texto} {fecha.year}"


# ---------------------------------------------------------------------------
# Componentes. Papel = lo que escribe el docente. Pizarrón = lo que responde el coach.
# ---------------------------------------------------------------------------

def marca(subtitulo: str | None = None) -> None:
    sub = f'<span class="marca-sub">{esc(subtitulo)}</span>' if subtitulo else ""
    st.markdown(f'<div><span class="marca">AulaCoach</span>{sub}</div>', unsafe_allow_html=True)


def barra_superior(nombre: str, opciones: list[tuple[str, object]], subtitulo: str | None = None) -> None:
    """Marca a la izquierda y el menú de la cuenta a la derecha. No se apila en el celular."""
    corto = nombre if len(nombre) <= 18 else nombre[:17] + "…"
    with st.container(key="barra", horizontal=True, horizontal_alignment="distribute",
                      vertical_alignment="center", gap="small", wrap=False):
        marca(subtitulo)
        with st.popover(corto, icon=":material/account_circle:"):
            for i, (texto, accion) in enumerate(opciones):
                if st.button(texto, key=f"menu_{i}", width="stretch"):
                    accion()


def portada(texto_html: str) -> None:
    """Pizarrón de bienvenida. `texto_html` es texto fijo de la app, nunca de un usuario."""
    st.markdown(
        f"""<div class="pizarron pizarron-portada">
              <div class="portada-marca">AulaCoach</div>
              <svg class="trazo" viewBox="0 0 260 14" aria-hidden="true">
                <path d="M3 9 C 55 3, 105 12, 155 7 S 225 4, 257 8"/></svg>
              <p class="portada-texto">{texto_html}</p>
            </div>""",
        unsafe_allow_html=True)


def saludo_docente(nombre: str, detalle: str) -> None:
    st.markdown(
        f'<div class="saludo"><span class="saludo-hola">{esc(saludo())},</span>'
        f'<span class="saludo-nombre">{esc(nombre)}</span></div>'
        f'<p class="saludo-detalle">{esc(detalle)}</p>',
        unsafe_allow_html=True)


def nota(texto: str, tipo: str = "suave") -> None:
    """Aviso. tipo: suave | alerta (lapicero rojo) | clave (resaltado)"""
    st.markdown(f'<div class="nota nota-{tipo}">{esc(texto)}</div>', unsafe_allow_html=True)


def parrafo(texto: str, clase: str = "") -> None:
    st.markdown(f'<p class="{clase}">{esc(texto)}</p>', unsafe_allow_html=True)


def pizarron_vacio() -> None:
    st.markdown(
        '<div class="pizarron pizarron-vacio">'
        '<p class="tiza-titulo">Aquí te escribo dos ideas</p>'
        '<p class="tiza-tenue">Elige el tema y el tiempo que tienes, y toca «Darme dos ideas». '
        'Tú decides cuál usar.</p>'
        '</div>', unsafe_allow_html=True)


def _limpio(texto: str) -> str:
    return esc((texto or "").replace("**", "").strip())


def _ruta_html(letra: str, ruta: dict, estado: str = "") -> str:
    minutos = f' <span class="ruta-min">{_limpio(ruta.get("minutos"))}</span>' if ruta.get("minutos") else ""
    return (f'<div class="ruta ruta-{letra.lower()} {estado}">'
            f'<span class="ruta-letra" aria-hidden="true">{letra}</span>'
            f'<div><p class="ruta-nombre"><span class="lector">Ruta {letra}: </span>{_limpio(ruta["nombre"])}{minutos}</p>'
            f'<p class="ruta-texto">{_limpio(ruta["texto"])}</p></div></div>')


def tiene_rutas(rutas: dict) -> bool:
    return bool(rutas.get("A") and rutas.get("B") and rutas["A"]["texto"] and rutas["B"]["texto"])


def pizarron_rutas(titulo: str, rutas: dict, guias: list[str], elegida: str | None = None,
                   texto_crudo: str = "") -> None:
    """Las dos micro-rutas en tiza. La elegida queda encerrada; la otra se borra un poco."""
    with st.container(key="pizarron_idea"):
        parrafo(titulo, "tiza-titulo")
        fuente = (f'<p class="tiza-fuente">Basado en las guías: {esc(" y ".join(guias))}</p>' if guias else "")
        if tiene_rutas(rutas):
            bloques = []
            for letra in "AB":
                estado = "" if not elegida else ("elegida" if letra == elegida else "no-elegida")
                bloques.append(_ruta_html(letra, rutas[letra], estado))
            if rutas.get("pregunta"):
                bloques.append(f'<p class="tiza-rosada">Pregunta para ti</p>'
                               f'<p class="tiza-pregunta">{_limpio(rutas["pregunta"])}</p>')
            st.markdown("".join(bloques) + fuente, unsafe_allow_html=True)
        else:   # el modelo no respetó el formato: se muestra tal cual
            st.markdown(md_modelo(texto_crudo))
            if fuente:
                st.markdown(fuente, unsafe_allow_html=True)


def dictado() -> None:
    st.markdown('<p class="dictado"><span class="microfono" aria-hidden="true"></span>'
                'Puedes dictarlo: toca el micrófono de tu teclado y habla.</p>', unsafe_allow_html=True)


def tarjeta_compromiso(compromiso: dict, ruta: str) -> None:
    """La micro-acción elegida, en una nota adhesiva: la misma que verá después de clase."""
    if compromiso.get("riesgo"):
        with st.container(key="alerta_compromiso"):
            parrafo("Esto necesita a una persona", "rojo-titulo")
            parrafo(compromiso["micro_accion"])
        return
    with st.container(key="nota_compromiso"):
        parrafo(compromiso["valoracion"], "nota-tenue")
        parrafo(f"Tu micro-acción para esta clase ({ruta})", "nota-titulo")
        parrafo(compromiso["micro_accion"], "nota-grande")
        if compromiso.get("que_observar"):
            parrafo(f"Fíjate en: {compromiso['que_observar']}")
        st.markdown('<p class="nota-cierre"><span>¿Te animas? Después de clase me cuentas cómo te fue.</span></p>',
                    unsafe_allow_html=True)


def pizarron_pensando(texto: str) -> None:
    with st.container(key="pizarron_pensando"):
        parrafo(texto, "tiza-tenue")


def nota_reto(texto: str, que_observar: str = "", titulo: str = "Tu reto de la última vez") -> None:
    with st.container(key="nota_reto"):
        parrafo(titulo, "nota-titulo")
        parrafo(texto)
        if que_observar:
            parrafo(f"Fíjate en: {que_observar}", "nota-tenue")


def tarjeta_consejo(resultado: dict, clave: str) -> None:
    if resultado.get("riesgo"):
        with st.container(key=f"alerta_{clave}"):
            parrafo("Esto necesita a una persona", "rojo-titulo")
            parrafo(resultado["micro_accion"])
        return
    with st.container(key=f"pizarron_consejo_{clave}"):
        parrafo(resultado["reconocimiento"], "tiza-tenue")
        parrafo("Para tu próxima clase", "tiza-titulo")
        parrafo(resultado["micro_accion"], "tiza-grande")
        parrafo("Para pensar", "tiza-rosada")
        parrafo(resultado["pregunta_reflexiva"])
        if resultado.get("guias"):
            parrafo("Basado en la guía: " + " y ".join(resultado["guias"]), "tiza-fuente")


_SELLOS = {"funciono": ("Funcionó", "sello-bien"), "no_funciono": ("No funcionó", "sello-mal"),
           "no_probe": ("No lo probé", "sello-gris"), None: ("Pendiente", "sello-pendiente")}


def sello(resultado: str | None) -> str:
    texto, clase = _SELLOS.get(resultado, _SELLOS[None])
    return f'<span class="sello {clase}">{texto}</span>'


def _titulo_entrada(e: dict) -> str:
    cuando = fecha_corta(e["fecha"])
    e = {**e, "tema": (e["tema"] or "").strip()}
    if e.get("riesgo"):
        return f"{e['tema']}: necesitó atención, {cuando}"
    if e["tipo"] == "idea":
        return f"Ideas para {e['tema']}, {cuando}"
    return f"Consejo sobre {e['tema']}, {cuando}"


def _reto_en_papel(texto: str, resultado: str | None) -> None:
    st.markdown(f'<p class="reto-papel">{sello(resultado)} {esc(texto)}</p>', unsafe_allow_html=True)


def lista_entradas(entradas: list[dict], prefijo: str) -> None:
    """Historial de ideas y consejos (lo usan el docente y la dirección)."""
    from Motor import separar_rutas  # aquí para que Interfaz no dependa del motor al importarse
    iconos = {"idea": ":material/lightbulb:", "consejo": ":material/edit_note:"}
    with st.container(key="historial"):
        for e in entradas:
            icono = ":material/flag:" if e.get("riesgo") else iconos[e["tipo"]]
            with st.expander(md_seguro(_titulo_entrada(e)), icon=icono):
                if e["tipo"] == "idea":
                    rutas = separar_rutas(e["texto"])
                    if e.get("contexto"):
                        parrafo(f"Tu grupo: {e['contexto']}", "tenue")
                    if tiene_rutas(rutas):
                        elegida = e.get("ruta_elegida")
                        st.markdown("".join(
                            _ruta_html(l, rutas[l], "" if not elegida else ("elegida" if l == elegida else "no-elegida"))
                            for l in "AB"), unsafe_allow_html=True)
                    else:
                        st.markdown(md_modelo(e["texto"]))
                    if e.get("adaptacion"):
                        parrafo(f"Cómo la adaptaste: {e['adaptacion']}", "tenue")
                    if e.get("reto"):
                        _reto_en_papel(e["reto"], e.get("resultado_reto"))
                    continue
                parrafo(f"Pasó: {e['que_paso']}. Lo difícil: {e['que_costo']}", "tenue")
                if e.get("riesgo"):
                    nota(e["micro_accion"], "alerta")
                else:
                    _reto_en_papel(e["micro_accion"], e.get("resultado_reto"))
                    parrafo(e["pregunta"], "tenue")


# ---------------------------------------------------------------------------
# Mi avance
# ---------------------------------------------------------------------------

def _plural(n: int, uno: str, varios: str) -> str:
    return uno if n == 1 else varios


def pizarron_avance(av: dict) -> None:
    cifras = [
        (av["clases"], _plural(av["clases"], "clase contada", "clases contadas")),
        (av["probados"], _plural(av["probados"], "reto probado", "retos probados")),
        (av["funcionaron"], _plural(av["funcionaron"], "funcionó", "funcionaron")),
    ]
    celdas = "".join(f'<div><span class="cifra">{n}</span><span class="cifra-texto">{esc(t)}</span></div>'
                     for n, t in cifras)
    semanas = ""
    if av["semanas"] > 1:
        semanas = f'<p class="tiza-tenue">Llevas {av["semanas"]} semanas preparando y revisando tus clases.</p>'
    st.markdown(f'<div class="pizarron pizarron-avance"><p class="tiza-titulo">Tu avance</p>'
                f'<div class="cifras">{celdas}</div>{semanas}</div>', unsafe_allow_html=True)


def barras_competencias(competencias: list[dict]) -> None:
    mayor = max((c["veces"] for c in competencias), default=1) or 1
    filas = []
    for c in competencias:
        ancho = max(12, round(100 * c["veces"] / mayor))
        logro = (f' · {c["funcionaron"]} {_plural(c["funcionaron"], "reto funcionó", "retos funcionaron")}'
                 if c["funcionaron"] else "")
        filas.append(
            f'<div class="competencia"><p class="competencia-nombre">{esc(c["competencia"])}'
            f'<span class="tenue"> {c["veces"]} {_plural(c["veces"], "vez", "veces")}{logro}</span></p>'
            f'<div class="barra"><span style="width:{ancho}%"></span></div></div>')
    st.markdown(f'<div class="competencias">{"".join(filas)}</div>', unsafe_allow_html=True)


def lista_retos(retos: list[dict]) -> None:
    filas = "".join(
        f'<li>{sello(r["resultado"])}<span class="reto-texto">{esc(r["texto"])}</span>'
        f'<span class="reto-cuando">{esc((r["tema"] or "").strip())}, {esc(fecha_corta(r["fecha"]))}</span></li>'
        for r in retos)
    st.markdown(f'<ul class="retos">{filas}</ul>', unsafe_allow_html=True)


def paso_digital(titulo: str, texto: str) -> None:
    with st.container(key="paso_digital"):
        parrafo(titulo, "paso-titulo")
        parrafo(texto)


def pie_privacidad() -> None:
    parrafo("Lo que guardas aquí lo ves tú y la dirección de tu escuela.", "pie")


# ---------------------------------------------------------------------------
# Código QR sin internet ni librerías extra (ISO/IEC 18004, nivel L, versiones 1-5)
# ---------------------------------------------------------------------------

_CAPACIDAD_QR = [(1, 19, 7), (2, 34, 10), (3, 55, 15), (4, 80, 20), (5, 108, 26)]
_GF_EXP, _GF_LOG = [1] * 512, [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _GF_EXP[_i + 255] = _x
    _GF_LOG[_x] = _i
    _x = (_x << 1) ^ (0x11D if _x & 0x80 else 0)


def _rs_ec(datos: list[int], n_ec: int) -> list[int]:
    gen = [1]
    for i in range(n_ec):
        nuevo = [0] * (len(gen) + 1)
        for j, c in enumerate(gen):
            nuevo[j] ^= c
            nuevo[j + 1] ^= _GF_EXP[_GF_LOG[c] + i] if c else 0
        gen = nuevo
    resto = list(datos) + [0] * n_ec
    for i in range(len(datos)):
        coef = resto[i]
        if coef:
            for j in range(1, len(gen)):
                if gen[j]:
                    resto[i + j] ^= _GF_EXP[_GF_LOG[gen[j]] + _GF_LOG[coef]]
    return resto[len(datos):]


def qr_svg(texto: str) -> str | None:
    """Devuelve un <svg> con el código QR del texto (hasta 106 bytes, sin internet)."""
    raw = (texto or "").strip().encode("utf-8")
    cap = next(((v, d, e) for v, d, e in _CAPACIDAD_QR if 0 < len(raw) and len(raw) + 2 <= d), None)
    if not cap:
        return None
    version, n_datos, n_ec = cap
    bits = [0, 1, 0, 0]
    for b in [len(raw), *raw]:
        bits.extend((b >> i) & 1 for i in range(7, -1, -1))
    bits.extend([0] * min(4, n_datos * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    palabras = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    base = len(palabras)
    while len(palabras) < n_datos:
        palabras.append(0xEC if (len(palabras) - base) % 2 == 0 else 0x11)
    flujo = [(b >> i) & 1 for b in (palabras + _rs_ec(palabras, n_ec)) for i in range(7, -1, -1)]

    n = 17 + 4 * version
    m = [[0] * n for _ in range(n)]
    fijo = [[False] * n for _ in range(n)]

    def poner(r: int, c: int, val: int | bool) -> None:
        m[r][c] = int(bool(val))
        fijo[r][c] = True

    for fr, fc in ((0, 0), (0, n - 7), (n - 7, 0)):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = fr + dr, fc + dc
                if 0 <= r < n and 0 <= c < n:
                    poner(r, c, 0 <= dr <= 6 and 0 <= dc <= 6
                          and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)))
    if version >= 2:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                poner(n - 7 + dr, n - 7 + dc, max(abs(dr), abs(dc)) in (0, 2))
    for i in range(8, n - 8):
        if not fijo[6][i]:
            poner(6, i, i % 2 == 0)
        if not fijo[i][6]:
            poner(i, 6, i % 2 == 0)
    poner(n - 8, 8, 1)
    for i in range(9):
        fijo[8][i] = fijo[i][8] = True
    for i in range(8):
        fijo[8][n - 1 - i] = fijo[n - 1 - i][8] = True

    idx, col, arriba = 0, n - 1, True
    while col > 0:
        if col == 6:
            col -= 1
        for r in (range(n - 1, -1, -1) if arriba else range(n)):
            for c in (col, col - 1):
                if not fijo[r][c]:
                    bit = flujo[idx] if idx < len(flujo) else 0
                    idx += 1
                    m[r][c] = bit ^ ((r + c) % 2 == 0)
        arriba = not arriba
        col -= 2

    fmt = 0x77C4  # Nivel L, máscara 0
    pos_tl = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
              (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    for i, (r, c) in enumerate(pos_tl):
        m[r][c] = (fmt >> (14 - i)) & 1
    for i in range(7):
        m[n - 1 - i][8] = (fmt >> (14 - i)) & 1
    for i in range(8):
        m[8][n - 8 + i] = (fmt >> (7 - i)) & 1

    margen = 3
    tam = n + 2 * margen
    trazos = "".join(f"M{c + margen},{r + margen}h1v1h-1z"
                     for r in range(n) for c in range(n) if m[r][c])
    return (f'<svg class="qr-svg" viewBox="0 0 {tam} {tam}" xmlns="http://www.w3.org/2000/svg" '
            f'shape-rendering="crispEdges" role="img" aria-label="Código QR para abrir {esc(texto)}">'
            f'<rect width="{tam}" height="{tam}" fill="#FFFFFF" rx="1.5"/>'
            f'<path d="{trazos}" fill="#1F2E57"/></svg>')


def direcciones_red(puerto: int = 8501) -> list[str]:
    """Direcciones locales de esta computadora para que los celulares entren por Wi-Fi."""
    ips: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ips.append(s.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith(("127.", "169.254.")) and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    # Si el Hotspot de Windows (192.168.137.1) está encendido, ponerlo de primero
    ips.sort(key=lambda ip: (0 if ip == "192.168.137.1" else 1))
    return [f"http://{ip}:{puerto}" for ip in ips] or [f"http://localhost:{puerto}"]


def tarjeta_qr(url: str, cuentas_demo: list[str] | None = None, clave_demo: str = "aula2026") -> None:
    """Muestra el código QR y las instrucciones para conectarse desde el celular."""
    svg = qr_svg(url)
    if not svg:
        nota("La dirección es demasiado larga para generar el código QR.", "alerta")
        return
    if cuentas_demo:
        usuarios_html = ", ".join(f"<b>{esc(u)}</b>" for u in cuentas_demo)
        detalle = (f'<p class="qr-paso">1. Escanea el código con la cámara de tu celular (o escribe la dirección).</p>'
                   f'<p class="qr-paso">2. Entra con cualquiera de estas cuentas de prueba:<br>'
                   f'Usuario: {usuarios_html}<br>'
                   f'Contraseña: <b>{esc(clave_demo)}</b> '
                   f'<span class="tenue">(o toca «Crear cuenta»)</span></p>')
    else:
        detalle = ('<p class="qr-paso">1. Conecte el celular al mismo Wi-Fi (o Zona Wi-Fi) de esta computadora.</p>'
                   '<p class="qr-paso">2. Escanee el código con la cámara o escriba la dirección en el navegador.</p>')
    st.markdown(
        f'<div class="qr-caja">{svg}'
        f'<div class="qr-info">'
        f'<p class="qr-titulo">Entrar desde el celular</p>'
        f'<p class="qr-url">{esc(url)}</p>'
        f'{detalle}</div></div>',
        unsafe_allow_html=True,
    )

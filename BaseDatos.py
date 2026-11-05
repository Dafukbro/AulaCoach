"""
Base de datos de AulaCoach (SQLite, un solo archivo, sin servidor).

- Cada docente tiene su cuenta y SOLO ve sus propios datos: toda consulta de docente
  filtra por el `usuario_id` de la sesión, nunca por algo que escriba el usuario.
- La dirección (rol "admin") puede ver la actividad de todos; esas funciones exigen
  el rol en este mismo archivo, no solo en la interfaz.
- El esquema tiene versión (PRAGMA user_version). Las bases de versiones anteriores
  se migran solas, guardando antes una copia de respaldo:
    v1 (tabla `profesores`, sin contraseñas) -> v3
    v2 (cuentas, una sola idea por plan)     -> v3 (dos rutas, retos y avance del docente)
"""

import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import Seguridad as seg
from Motor import PerfilDocente, nivel_clave

RUTA_BD = Path(os.getenv("AULACOACH_BD", Path(__file__).resolve().with_name("escuela.db")))
VERSION_ESQUEMA = 3

# Lo difícil de la clase (lo que el docente toca en "Después de clase") -> la
# competencia docente que se trabaja. Así el panel "Mi avance" muestra en qué
# ha ido mejorando sin pedirle al docente que lo clasifique.
COMPETENCIAS = {
    "Se distrajeron mucho": "Manejo del grupo",
    "Participaron siempre los mismos": "Participación de todos",
    "No entendieron las instrucciones": "Instrucciones claras",
    "Faltó tiempo": "Manejo del tiempo",
    "Se copiaban entre ellos": "Trabajo autónomo",
}
RESULTADOS_RETO = ("funciono", "no_funciono", "no_probe")
DIAS_RETO_ABIERTO = 30

INTENTOS_MAXIMOS = 5
MINUTOS_BLOQUEO = 5
DIAS_SESION_DOCENTE = 7     # el docente no vuelve a escribir su contraseña en toda la semana
HORAS_SESION_DIRECCION = 8  # la dirección ve todo: sesión más corta

_ESQUEMA = [
    """CREATE TABLE IF NOT EXISTS usuarios (
        id                 INTEGER PRIMARY KEY,
        usuario            TEXT NOT NULL UNIQUE COLLATE NOCASE,
        nombre             TEXT NOT NULL,
        rol                TEXT NOT NULL DEFAULT 'docente' CHECK (rol IN ('docente', 'admin')),
        clave_hash         TEXT,
        debe_cambiar_clave INTEGER NOT NULL DEFAULT 0,
        activo             INTEGER NOT NULL DEFAULT 1,
        intentos_fallidos  INTEGER NOT NULL DEFAULT 0,
        bloqueado_hasta    TEXT,
        creado             TEXT NOT NULL,
        ultimo_acceso      TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS perfiles (
        usuario_id    INTEGER PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
        grado         TEXT NOT NULL DEFAULT '',
        estudiantes   INTEGER NOT NULL DEFAULT 30 CHECK (estudiantes BETWEEN 1 AND 200),
        nivel_digital TEXT NOT NULL DEFAULT 'basico'
                      CHECK (nivel_digital IN ('basico', 'intermedio', 'avanzado')),
        recursos      TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS sesiones (
        token_hash TEXT PRIMARY KEY,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        creada     TEXT NOT NULL,
        expira     TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS planes (
        id         INTEGER PRIMARY KEY,
        usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        fecha      TEXT NOT NULL,
        tema       TEXT NOT NULL,
        minutos    INTEGER,
        respuesta  TEXT NOT NULL,
        contexto     TEXT NOT NULL DEFAULT '',
        guias        TEXT NOT NULL DEFAULT '',
        ruta_elegida TEXT CHECK (ruta_elegida IN ('A', 'B')),
        adaptacion   TEXT,
        riesgo       INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS bitacora (
        id                 INTEGER PRIMARY KEY,
        usuario_id         INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        fecha              TEXT NOT NULL,
        tema               TEXT NOT NULL,
        que_paso           TEXT NOT NULL,
        que_costo          TEXT NOT NULL,
        reconocimiento     TEXT NOT NULL,
        micro_accion       TEXT NOT NULL,
        pregunta_reflexiva TEXT NOT NULL,
        riesgo             INTEGER NOT NULL DEFAULT 0,
        competencia        TEXT,
        guias              TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS retos (
        id              INTEGER PRIMARY KEY,
        usuario_id      INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        fecha           TEXT NOT NULL,
        origen          TEXT NOT NULL CHECK (origen IN ('plan', 'bitacora')),
        origen_id       INTEGER NOT NULL,
        texto           TEXT NOT NULL,
        que_observar    TEXT NOT NULL DEFAULT '',
        resultado       TEXT CHECK (resultado IN ('funciono', 'no_funciono', 'no_probe')),
        fecha_resultado TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS ajustes (
        clave TEXT PRIMARY KEY,
        valor TEXT NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_planes_usuario ON planes(usuario_id, id)",
    "CREATE INDEX IF NOT EXISTS idx_bitacora_usuario ON bitacora(usuario_id, id)",
    "CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones(usuario_id)",
    "CREATE INDEX IF NOT EXISTS idx_retos_usuario ON retos(usuario_id, id)",
]

# De la versión 2 a la 3: columnas nuevas y la tabla de retos.
_DE_V2_A_V3 = [
    "ALTER TABLE planes ADD COLUMN contexto TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE planes ADD COLUMN guias TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE planes ADD COLUMN ruta_elegida TEXT CHECK (ruta_elegida IN ('A', 'B'))",
    "ALTER TABLE planes ADD COLUMN adaptacion TEXT",
    "ALTER TABLE planes ADD COLUMN riesgo INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE bitacora ADD COLUMN competencia TEXT",
    "ALTER TABLE bitacora ADD COLUMN guias TEXT NOT NULL DEFAULT ''",
]


@dataclass(frozen=True)
class Usuario:
    id: int
    usuario: str
    nombre: str
    rol: str
    debe_cambiar_clave: bool

    @property
    def es_direccion(self) -> bool:
        return self.rol == "admin"


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

def _ahora() -> datetime:
    return datetime.now().replace(microsecond=0)


def _txt(momento: datetime) -> str:
    return momento.strftime("%Y-%m-%d %H:%M:%S")


@contextmanager
def conectar():
    """Una conexión corta por operación: SQLite la abre en microsegundos y así
    ningún hilo de Streamlit comparte conexiones."""
    con = sqlite3.connect(RUTA_BD, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA synchronous = NORMAL")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _usuario_desde_fila(fila) -> Usuario:
    return Usuario(fila["id"], fila["usuario"], fila["nombre"], fila["rol"],
                   bool(fila["debe_cambiar_clave"]))


# ---------------------------------------------------------------------------
# Creación y migración
# ---------------------------------------------------------------------------

def inicializar_bd() -> None:
    RUTA_BD.parent.mkdir(parents=True, exist_ok=True)
    nueva = not RUTA_BD.exists()
    con = sqlite3.connect(RUTA_BD, timeout=10)
    con.isolation_level = None  # transacciones manuales para migrar todo o nada
    try:
        con.execute("PRAGMA journal_mode = WAL")  # lecturas y escrituras a la vez, menos esperas
        version = con.execute("PRAGMA user_version").fetchone()[0]
        tablas = {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        if version < VERSION_ESQUEMA:
            if "profesores" in tablas:
                con.close()
                _respaldar(f"respaldo-v1-{_ahora():%Y%m%d-%H%M}")
                con = sqlite3.connect(RUTA_BD, timeout=10)
                con.isolation_level = None
                _migrar_desde_v1(con)
            elif version == 2:
                con.close()
                _respaldar(f"respaldo-v2-{_ahora():%Y%m%d-%H%M}")
                con = sqlite3.connect(RUTA_BD, timeout=10)
                con.isolation_level = None
                _migrar_desde_v2(con)
            else:
                con.execute("BEGIN IMMEDIATE")
                for sentencia in _ESQUEMA:
                    con.execute(sentencia)
                con.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
                con.execute("COMMIT")

        con.execute("DELETE FROM sesiones WHERE expira < ?", (_txt(_ahora()),))
    finally:
        con.close()

    if nueva and os.name == "posix":
        os.chmod(RUTA_BD, 0o600)  # solo el usuario del sistema que corre la app puede leerla


def _respaldar(sufijo: str) -> Path:
    destino = RUTA_BD.with_name(f"{RUTA_BD.stem}.{sufijo}.db")
    origen = sqlite3.connect(RUTA_BD)
    copia = sqlite3.connect(destino)
    with copia:
        origen.backup(copia)
    origen.close()
    copia.close()
    return destino


def _usuario_desde_nombre(nombre: str, ocupados: set[str]) -> str:
    palabras = re.findall(r"[a-z0-9]+", seg.normalizar_usuario(nombre))
    base = ".".join(palabras[:2])[:24] or "docente"
    if len(base) < 3:
        base = f"docente.{base}"
    candidato, n = base, 2
    while candidato in ocupados:
        candidato, n = f"{base}{n}", n + 1
    ocupados.add(candidato)
    return candidato


def _migrar_desde_v1(con: sqlite3.Connection) -> None:
    """Versión anterior: profesores sin contraseña + historial + bitacora.
    Los docentes migrados quedan SIN contraseña: la dirección les asigna una temporal."""
    con.execute("PRAGMA foreign_keys = OFF")
    con.execute("BEGIN IMMEDIATE")
    try:
        tablas = {f[0] for f in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        con.execute("ALTER TABLE profesores RENAME TO v1_profesores")
        if "historial" in tablas:
            con.execute("ALTER TABLE historial RENAME TO v1_historial")
        if "bitacora" in tablas:
            con.execute("ALTER TABLE bitacora RENAME TO v1_bitacora")
        for sentencia in _ESQUEMA:
            con.execute(sentencia)

        ahora, ocupados = _txt(_ahora()), set()
        cursor = con.execute("SELECT * FROM v1_profesores ORDER BY id")
        columnas = [d[0] for d in cursor.description]
        for fila in cursor.fetchall():
            datos = dict(zip(columnas, fila))
            usuario = _usuario_desde_nombre(datos["nombre"], ocupados)
            con.execute("""INSERT INTO usuarios (id, usuario, nombre, rol, clave_hash, debe_cambiar_clave, creado)
                           VALUES (?, ?, ?, 'docente', NULL, 1, ?)""",
                        (datos["id"], usuario, datos["nombre"][:60], ahora))
            estudiantes = datos.get("estudiantes") or 30
            con.execute("""INSERT INTO perfiles (usuario_id, grado, estudiantes, nivel_digital, recursos)
                           VALUES (?, ?, ?, ?, ?)""",
                        (datos["id"], datos.get("grado") or "", max(1, min(int(estudiantes), 200)),
                         nivel_clave(datos.get("nivel_digital") or ""), datos.get("recursos_salon") or ""))

        if "historial" in tablas:
            con.execute("""INSERT INTO planes (usuario_id, fecha, tema, minutos, respuesta)
                           SELECT profesor_id, fecha, tema, NULL, respuesta_ia FROM v1_historial
                           WHERE profesor_id IN (SELECT id FROM usuarios) ORDER BY id""")
        if "bitacora" in tablas:
            con.execute("""INSERT INTO bitacora (usuario_id, fecha, tema, que_paso, que_costo,
                                                 reconocimiento, micro_accion, pregunta_reflexiva)
                           SELECT profesor_id, fecha, tema, que_paso, que_costo,
                                  reconocimiento, micro_accion, pregunta_reflexiva
                           FROM v1_bitacora WHERE profesor_id IN (SELECT id FROM usuarios) ORDER BY id""")

        for tabla in ("v1_bitacora", "v1_historial", "v1_profesores"):
            con.execute(f"DROP TABLE IF EXISTS {tabla}")
        _completar_v3(con)
        con.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")


def _migrar_desde_v2(con: sqlite3.Connection) -> None:
    con.execute("BEGIN IMMEDIATE")
    try:
        for sentencia in _DE_V2_A_V3:
            con.execute(sentencia)
        for sentencia in _ESQUEMA:   # crea `retos` y su índice
            con.execute(sentencia)
        _completar_v3(con)
        con.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def _completar_v3(con: sqlite3.Connection) -> None:
    """Datos que la v3 deduce de los registros anteriores: la competencia de cada
    bitácora y un reto por cada micro-acción ya recibida (sin resultado conocido)."""
    for dificil, competencia in COMPETENCIAS.items():
        con.execute("UPDATE bitacora SET competencia = ? WHERE competencia IS NULL AND que_costo LIKE ?",
                    (competencia, dificil + "%"))
    con.execute("""INSERT INTO retos (usuario_id, fecha, origen, origen_id, texto)
                   SELECT usuario_id, fecha, 'bitacora', id, micro_accion FROM bitacora
                   WHERE riesgo = 0 AND id NOT IN (SELECT origen_id FROM retos WHERE origen = 'bitacora')
                   ORDER BY id""")


def competencia_de(que_costo: str) -> str | None:
    return next((c for d, c in COMPETENCIAS.items() if (que_costo or "").startswith(d)), None)


# ---------------------------------------------------------------------------
# Cuentas y acceso
# ---------------------------------------------------------------------------

def hay_direccion() -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM usuarios WHERE rol = 'admin' AND activo = 1").fetchone() is not None


def usuario_libre(usuario: str) -> bool:
    with conectar() as con:
        return con.execute("SELECT 1 FROM usuarios WHERE usuario = ?", (usuario,)).fetchone() is None


def crear_usuario(usuario: str, nombre: str, clave: str | None, rol: str = "docente",
                  debe_cambiar_clave: bool = False) -> int:
    """`usuario` y `clave` ya deben venir validados (Seguridad.validar_*)."""
    nombre = seg.limpiar_texto(nombre, 60)
    try:
        with conectar() as con:
            cur = con.execute(
                """INSERT INTO usuarios (usuario, nombre, rol, clave_hash, debe_cambiar_clave, creado)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (usuario, nombre, rol, seg.hash_clave(clave) if clave else None,
                 int(debe_cambiar_clave), _txt(_ahora())))
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("Ese usuario ya existe. Elige otro.") from None


def autenticar(usuario: str, clave: str) -> tuple[Usuario | None, str | None]:
    """Devuelve (usuario, None) si entra, o (None, mensaje para mostrar)."""
    generico = "Usuario o contraseña incorrectos."
    usuario = seg.normalizar_usuario(usuario)
    with conectar() as con:
        fila = con.execute("SELECT * FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        if fila is None:
            seg.verificar_ficticio(clave)
            return None, generico
        if not fila["activo"]:
            return None, "Esta cuenta está desactivada. Habla con la dirección."
        ahora = _ahora()
        if fila["bloqueado_hasta"] and fila["bloqueado_hasta"] > _txt(ahora):
            hasta = datetime.strptime(fila["bloqueado_hasta"], "%Y-%m-%d %H:%M:%S")
            minutos = max(1, round((hasta - ahora).total_seconds() / 60))
            return None, f"Demasiados intentos. Espera {minutos} min o pide ayuda a la dirección."
        if fila["clave_hash"] is None:
            return None, "Tu cuenta aún no tiene contraseña. Pide a la dirección una contraseña temporal."

        if not seg.verificar_clave(clave, fila["clave_hash"]):
            intentos = fila["intentos_fallidos"] + 1
            if intentos >= INTENTOS_MAXIMOS:
                con.execute("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = ? WHERE id = ?",
                            (_txt(ahora + timedelta(minutes=MINUTOS_BLOQUEO)), fila["id"]))
                return None, f"Demasiados intentos. Espera {MINUTOS_BLOQUEO} min o pide ayuda a la dirección."
            con.execute("UPDATE usuarios SET intentos_fallidos = ? WHERE id = ?", (intentos, fila["id"]))
            return None, generico

        con.execute("""UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL,
                       ultimo_acceso = ? WHERE id = ?""", (_txt(ahora), fila["id"]))
        return _usuario_desde_fila(fila), None


def crear_sesion(usuario: Usuario) -> tuple[str, int]:
    """Devuelve (token para la cookie, duración en segundos)."""
    duracion = (timedelta(hours=HORAS_SESION_DIRECCION) if usuario.es_direccion
                else timedelta(days=DIAS_SESION_DOCENTE))
    token, token_hash = seg.nuevo_token()
    ahora = _ahora()
    with conectar() as con:
        con.execute("INSERT INTO sesiones (token_hash, usuario_id, creada, expira) VALUES (?, ?, ?, ?)",
                    (token_hash, usuario.id, _txt(ahora), _txt(ahora + duracion)))
    return token, int(duracion.total_seconds())


def usuario_de_sesion(token: str | None) -> Usuario | None:
    if not seg.token_valido(token):
        return None
    with conectar() as con:
        fila = con.execute(
            """SELECT u.* FROM sesiones s JOIN usuarios u ON u.id = s.usuario_id
               WHERE s.token_hash = ? AND s.expira > ? AND u.activo = 1""",
            (seg.hash_token(token), _txt(_ahora()))).fetchone()
    return _usuario_desde_fila(fila) if fila else None


def cerrar_sesion(token: str | None) -> None:
    if seg.token_valido(token):
        with conectar() as con:
            con.execute("DELETE FROM sesiones WHERE token_hash = ?", (seg.hash_token(token),))


def _cerrar_sesiones_de(con: sqlite3.Connection, usuario_id: int, excepto_token: str | None = None) -> None:
    if excepto_token:
        con.execute("DELETE FROM sesiones WHERE usuario_id = ? AND token_hash <> ?",
                    (usuario_id, seg.hash_token(excepto_token)))
    else:
        con.execute("DELETE FROM sesiones WHERE usuario_id = ?", (usuario_id,))


def cambiar_clave(usuario: Usuario, actual: str | None, nueva: str, token_actual: str | None = None) -> str | None:
    """Cambia la contraseña. `actual` es None solo en el cambio obligatorio tras una
    contraseña temporal (ya la acaba de escribir para entrar). Cierra las demás sesiones."""
    minimo = seg.CLAVE_MINIMA_DIRECCION if usuario.es_direccion else seg.CLAVE_MINIMA_DOCENTE
    error = seg.validar_clave(nueva, usuario.usuario, minimo)
    if error:
        return error
    with conectar() as con:
        fila = con.execute("SELECT clave_hash, debe_cambiar_clave FROM usuarios WHERE id = ?",
                           (usuario.id,)).fetchone()
        if actual is None and not fila["debe_cambiar_clave"]:
            return "Escribe tu contraseña actual."
        if actual is not None and not seg.verificar_clave(actual, fila["clave_hash"]):
            return "Tu contraseña actual no es correcta."
        if seg.verificar_clave(nueva, fila["clave_hash"]):
            return "La nueva contraseña debe ser distinta a la anterior."
        con.execute("UPDATE usuarios SET clave_hash = ?, debe_cambiar_clave = 0 WHERE id = ?",
                    (seg.hash_clave(nueva), usuario.id))
        _cerrar_sesiones_de(con, usuario.id, excepto_token=token_actual)
    return None


# ---------------------------------------------------------------------------
# Perfil del salón (cada docente, el suyo)
# ---------------------------------------------------------------------------

def obtener_perfil(usuario_id: int) -> PerfilDocente | None:
    with conectar() as con:
        fila = con.execute("SELECT * FROM perfiles WHERE usuario_id = ?", (usuario_id,)).fetchone()
    if not fila:
        return None
    return PerfilDocente(nivel_digital=fila["nivel_digital"], recursos=fila["recursos"],
                         grado=fila["grado"], estudiantes=fila["estudiantes"])


def guardar_perfil(usuario_id: int, grado: str, estudiantes: int, nivel_digital: str, recursos: str) -> None:
    with conectar() as con:
        con.execute(
            """INSERT INTO perfiles (usuario_id, grado, estudiantes, nivel_digital, recursos)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(usuario_id) DO UPDATE SET grado = excluded.grado,
                   estudiantes = excluded.estudiantes, nivel_digital = excluded.nivel_digital,
                   recursos = excluded.recursos""",
            (usuario_id, seg.limpiar_texto(grado, 40), max(1, min(int(estudiantes), 200)),
             nivel_clave(nivel_digital), seg.limpiar_texto(recursos, 400)))


# ---------------------------------------------------------------------------
# Ideas (antes de clase) y bitácora (después de clase)
# ---------------------------------------------------------------------------

def guardar_plan(usuario_id: int, tema: str, minutos: int | None, respuesta: str,
                 contexto: str = "", guias: str = "", riesgo: bool = False) -> int:
    with conectar() as con:
        cur = con.execute(
            """INSERT INTO planes (usuario_id, fecha, tema, minutos, respuesta, contexto, guias, riesgo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (usuario_id, _txt(_ahora()), seg.limpiar_texto(tema, 80), minutos, respuesta,
             seg.limpiar_texto(contexto, 200), seg.limpiar_texto(guias, 200), int(riesgo)))
        return cur.lastrowid


def elegir_ruta(usuario_id: int, plan_id: int, ruta: str, adaptacion: str, compromiso: dict) -> int | None:
    """El docente eligió A o B y recibió su micro-acción. Devuelve el id del reto creado
    (None si era una situación de riesgo: eso no es un reto, es un aviso)."""
    if ruta not in ("A", "B"):
        raise ValueError("ruta")
    adaptacion = seg.limpiar_texto(adaptacion, 300)
    riesgo = bool(compromiso.get("riesgo"))
    with conectar() as con:
        cur = con.execute("""UPDATE planes SET ruta_elegida = ?, adaptacion = ?, riesgo = max(riesgo, ?)
                             WHERE id = ? AND usuario_id = ?""",
                          (ruta, adaptacion, int(riesgo), plan_id, usuario_id))
        if not cur.rowcount:
            return None   # el plan no es de este docente
        # Si vuelve a elegir sobre el mismo plan, el reto anterior de ese plan se reemplaza.
        con.execute("DELETE FROM retos WHERE origen = 'plan' AND origen_id = ? AND usuario_id = ? AND resultado IS NULL",
                    (plan_id, usuario_id))
        if riesgo:
            return None   # un aviso de riesgo no es un reto
        cur = con.execute(
            """INSERT INTO retos (usuario_id, fecha, origen, origen_id, texto, que_observar)
               VALUES (?, ?, 'plan', ?, ?, ?)""",
            (usuario_id, _txt(_ahora()), plan_id, compromiso["micro_accion"], compromiso.get("que_observar", "")))
        return cur.lastrowid


def guardar_bitacora(usuario_id: int, tema: str, que_paso: str, que_costo: str, resultado: dict,
                     guias: str = "") -> int:
    """Guarda la bitácora y, si no es un aviso de riesgo, su micro-acción como reto nuevo."""
    riesgo = bool(resultado.get("riesgo"))
    with conectar() as con:
        cur = con.execute(
            """INSERT INTO bitacora (usuario_id, fecha, tema, que_paso, que_costo, reconocimiento,
                                     micro_accion, pregunta_reflexiva, riesgo, competencia, guias)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (usuario_id, _txt(_ahora()), seg.limpiar_texto(tema, 80), seg.limpiar_texto(que_paso, 300),
             seg.limpiar_texto(que_costo, 500), resultado["reconocimiento"], resultado["micro_accion"],
             resultado["pregunta_reflexiva"], int(riesgo), competencia_de(que_costo),
             seg.limpiar_texto(guias, 200)))
        bitacora_id = cur.lastrowid
        if not riesgo:
            con.execute("""INSERT INTO retos (usuario_id, fecha, origen, origen_id, texto)
                           VALUES (?, ?, 'bitacora', ?, ?)""",
                        (usuario_id, _txt(_ahora()), bitacora_id, resultado["micro_accion"]))
        return bitacora_id


def reto_abierto(usuario_id: int) -> dict | None:
    """El reto más reciente que el docente aún no dijo si probó."""
    desde = _txt(_ahora() - timedelta(days=DIAS_RETO_ABIERTO))
    with conectar() as con:
        fila = con.execute("""SELECT id, fecha, origen, texto, que_observar FROM retos
                              WHERE usuario_id = ? AND resultado IS NULL AND fecha >= ?
                              ORDER BY id DESC LIMIT 1""", (usuario_id, desde)).fetchone()
    return dict(fila) if fila else None


def registrar_resultado_reto(usuario_id: int, reto_id: int, resultado: str) -> None:
    if resultado not in RESULTADOS_RETO:
        raise ValueError("resultado")
    with conectar() as con:
        con.execute("""UPDATE retos SET resultado = ?, fecha_resultado = ?
                       WHERE id = ? AND usuario_id = ?""", (resultado, _txt(_ahora()), reto_id, usuario_id))


def ultima_micro_accion(usuario_id: int) -> str:
    reto = reto_abierto(usuario_id)
    return reto["texto"] if reto else ""


def temas_recientes(usuario_id: int, limite: int = 4) -> list[str]:
    with conectar() as con:
        filas = con.execute("""SELECT trim(tema) AS tema FROM planes WHERE usuario_id = ? AND trim(tema) <> ''
                               GROUP BY lower(trim(tema)) ORDER BY max(id) DESC LIMIT ?""",
                            (usuario_id, limite)).fetchall()
    return [f["tema"] for f in filas]


def ultimos_minutos(usuario_id: int) -> int | None:
    with conectar() as con:
        fila = con.execute("""SELECT minutos FROM planes WHERE usuario_id = ? AND minutos IS NOT NULL
                              ORDER BY id DESC LIMIT 1""", (usuario_id,)).fetchone()
    return fila["minutos"] if fila else None


def tiene_clase_sin_reflexion(usuario_id: int) -> bool:
    """¿Preparó una idea hoy y aún no contó cómo le fue? Así la app abre en 'Después de clase'."""
    hoy = _ahora().strftime("%Y-%m-%d")
    with conectar() as con:
        plan = con.execute("SELECT max(fecha) f FROM planes WHERE usuario_id = ? AND fecha >= ?",
                           (usuario_id, hoy)).fetchone()["f"]
        if not plan:
            return False
        nota = con.execute("SELECT 1 FROM bitacora WHERE usuario_id = ? AND fecha >= ?",
                           (usuario_id, plan)).fetchone()
    return nota is None


def historial(usuario_id: int, limite: int = 10) -> list[dict]:
    """Ideas y consejos mezclados, del más reciente al más antiguo, con su reto."""
    with conectar() as con:
        filas = con.execute(
            """SELECT * FROM (
                   SELECT 'idea' AS tipo, p.fecha, p.tema, p.respuesta AS texto, NULL AS que_paso,
                          NULL AS que_costo, NULL AS reconocimiento, NULL AS micro_accion,
                          NULL AS pregunta, p.riesgo, p.id, p.ruta_elegida, p.adaptacion, p.contexto,
                          p.guias, r.texto AS reto, r.resultado AS resultado_reto
                   FROM planes p
                   LEFT JOIN retos r ON r.origen = 'plan' AND r.origen_id = p.id
                   WHERE p.usuario_id = :u
                   UNION ALL
                   SELECT 'consejo', b.fecha, b.tema, NULL, b.que_paso, b.que_costo, b.reconocimiento,
                          b.micro_accion, b.pregunta_reflexiva, b.riesgo, b.id, NULL, NULL, b.competencia,
                          b.guias, r.texto, r.resultado
                   FROM bitacora b
                   LEFT JOIN retos r ON r.origen = 'bitacora' AND r.origen_id = b.id
                   WHERE b.usuario_id = :u)
               ORDER BY fecha DESC, id DESC LIMIT :n""",
            {"u": usuario_id, "n": limite}).fetchall()
    return [dict(f) for f in filas]


def avance(usuario_id: int) -> dict:
    """Panel "Mi avance": lo que el docente ha ido probando y cómo le fue."""
    with conectar() as con:
        uno = lambda sql: con.execute(sql, (usuario_id,)).fetchone()[0]
        datos = {
            "ideas": uno("SELECT count(*) FROM planes WHERE usuario_id = ? AND riesgo = 0"),
            "elegidas": uno("SELECT count(*) FROM planes WHERE usuario_id = ? AND ruta_elegida IS NOT NULL"),
            "clases": uno("SELECT count(*) FROM bitacora WHERE usuario_id = ? AND riesgo = 0"),
            "retos": uno("SELECT count(*) FROM retos WHERE usuario_id = ?"),
            "probados": uno("SELECT count(*) FROM retos WHERE usuario_id = ? AND resultado IN ('funciono', 'no_funciono')"),
            "funcionaron": uno("SELECT count(*) FROM retos WHERE usuario_id = ? AND resultado = 'funciono'"),
            "semanas": uno("""SELECT count(DISTINCT strftime('%Y-%W', fecha)) FROM (
                                  SELECT fecha FROM bitacora WHERE usuario_id = ?1
                                  UNION ALL SELECT fecha FROM planes WHERE usuario_id = ?1)"""),
        }
        datos["competencias"] = [dict(f) for f in con.execute(
            """SELECT b.competencia, count(*) AS veces,
                      sum(CASE WHEN r.resultado = 'funciono' THEN 1 ELSE 0 END) AS funcionaron
               FROM bitacora b
               LEFT JOIN retos r ON r.origen = 'bitacora' AND r.origen_id = b.id
               WHERE b.usuario_id = ? AND b.riesgo = 0 AND b.competencia IS NOT NULL
               GROUP BY b.competencia ORDER BY veces DESC, b.competencia""", (usuario_id,))]
        datos["ultimos_retos"] = [dict(f) for f in con.execute(
            """SELECT r.fecha, r.texto, r.resultado, r.origen,
                      coalesce(p.tema, b.tema) AS tema
               FROM retos r
               LEFT JOIN planes p   ON r.origen = 'plan'     AND p.id = r.origen_id
               LEFT JOIN bitacora b ON r.origen = 'bitacora' AND b.id = r.origen_id
               WHERE r.usuario_id = ? ORDER BY r.id DESC LIMIT 8""", (usuario_id,))]
    return datos


def subir_nivel_digital(usuario_id: int) -> str | None:
    """El docente probó su siguiente paso digital: las ideas pueden usar un poco más de tecnología."""
    siguiente = {"basico": "intermedio", "intermedio": "avanzado"}
    with conectar() as con:
        fila = con.execute("SELECT nivel_digital FROM perfiles WHERE usuario_id = ?", (usuario_id,)).fetchone()
        nuevo = siguiente.get(fila["nivel_digital"]) if fila else None
        if nuevo:
            con.execute("UPDATE perfiles SET nivel_digital = ? WHERE usuario_id = ?", (nuevo, usuario_id))
    return nuevo


# ---------------------------------------------------------------------------
# Ajustes de la escuela
# ---------------------------------------------------------------------------

def leer_ajuste(clave: str, defecto: str) -> str:
    with conectar() as con:
        fila = con.execute("SELECT valor FROM ajustes WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila else defecto


def registro_abierto() -> bool:
    return leer_ajuste("registro_abierto", "1") == "1"


# ---------------------------------------------------------------------------
# Funciones de la dirección (verifican el rol aquí mismo)
# ---------------------------------------------------------------------------

def _exigir_direccion(solicitante: Usuario) -> None:
    if not solicitante or not solicitante.es_direccion:
        raise PermissionError("Solo la dirección puede hacer esto.")


def guardar_ajuste(solicitante: Usuario, clave: str, valor: str) -> None:
    _exigir_direccion(solicitante)
    with conectar() as con:
        con.execute("""INSERT INTO ajustes (clave, valor) VALUES (?, ?)
                       ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor""", (clave, valor))


def resumen_docentes(solicitante: Usuario) -> list[dict]:
    _exigir_direccion(solicitante)
    with conectar() as con:
        filas = con.execute(
            """SELECT u.id, u.usuario, u.nombre, u.activo, u.clave_hash IS NULL AS sin_clave,
                      u.debe_cambiar_clave, u.ultimo_acceso, u.bloqueado_hasta, p.grado,
                      (SELECT count(*) FROM planes   WHERE usuario_id = u.id) AS ideas,
                      (SELECT count(*) FROM bitacora WHERE usuario_id = u.id) AS consejos,
                      (SELECT count(*) FROM retos WHERE usuario_id = u.id
                          AND resultado IN ('funciono', 'no_funciono')) AS retos_probados,
                      (SELECT count(*) FROM retos WHERE usuario_id = u.id AND resultado = 'funciono') AS retos_funcionaron,
                      (SELECT count(*) FROM bitacora WHERE usuario_id = u.id AND riesgo = 1)
                        + (SELECT count(*) FROM planes WHERE usuario_id = u.id AND riesgo = 1) AS alertas,
                      max(coalesce((SELECT max(fecha) FROM planes   WHERE usuario_id = u.id), ''),
                          coalesce((SELECT max(fecha) FROM bitacora WHERE usuario_id = u.id), '')) AS ultima_actividad
               FROM usuarios u LEFT JOIN perfiles p ON p.usuario_id = u.id
               WHERE u.rol = 'docente'
               ORDER BY u.activo DESC, ultima_actividad DESC, u.nombre""").fetchall()
    return [dict(f) for f in filas]


def totales(solicitante: Usuario, dias: int = 7) -> dict:
    _exigir_direccion(solicitante)
    desde = _txt(_ahora() - timedelta(days=dias))
    with conectar() as con:
        return {
            "docentes": con.execute("SELECT count(*) FROM usuarios WHERE rol='docente' AND activo=1").fetchone()[0],
            "ideas": con.execute("SELECT count(*) FROM planes WHERE fecha >= ?", (desde,)).fetchone()[0],
            "consejos": con.execute("SELECT count(*) FROM bitacora WHERE fecha >= ?", (desde,)).fetchone()[0],
            "probados": con.execute("""SELECT count(*) FROM retos WHERE fecha_resultado >= ?
                                       AND resultado IN ('funciono', 'no_funciono')""", (desde,)).fetchone()[0],
            "funcionaron": con.execute("""SELECT count(*) FROM retos WHERE fecha_resultado >= ?
                                          AND resultado = 'funciono'""", (desde,)).fetchone()[0],
            "activos": con.execute(
                """SELECT count(DISTINCT usuario_id) FROM (
                       SELECT usuario_id FROM planes WHERE fecha >= :d
                       UNION SELECT usuario_id FROM bitacora WHERE fecha >= :d)""", {"d": desde}).fetchone()[0],
        }


def alertas(solicitante: Usuario, dias: int = 30) -> list[dict]:
    _exigir_direccion(solicitante)
    desde = _txt(_ahora() - timedelta(days=dias))
    with conectar() as con:
        filas = con.execute(
            """SELECT * FROM (
                   SELECT b.fecha, u.nombre, b.tema, b.que_costo FROM bitacora b
                   JOIN usuarios u ON u.id = b.usuario_id WHERE b.riesgo = 1 AND b.fecha >= :d
                   UNION ALL
                   SELECT p.fecha, u.nombre, p.tema, trim(p.contexto || ' ' || coalesce(p.adaptacion, ''))
                   FROM planes p JOIN usuarios u ON u.id = p.usuario_id WHERE p.riesgo = 1 AND p.fecha >= :d)
               ORDER BY fecha DESC""", {"d": desde}).fetchall()
    return [dict(f) for f in filas]


def competencias_escuela(solicitante: Usuario, dias: int = 30) -> list[dict]:
    """Lo que más les cuesta a los docentes de la escuela (para planear la formación)."""
    _exigir_direccion(solicitante)
    desde = _txt(_ahora() - timedelta(days=dias))
    with conectar() as con:
        filas = con.execute(
            """SELECT b.competencia, count(*) AS veces,
                      sum(CASE WHEN r.resultado = 'funciono' THEN 1 ELSE 0 END) AS funcionaron
               FROM bitacora b
               LEFT JOIN retos r ON r.origen = 'bitacora' AND r.origen_id = b.id
               WHERE b.riesgo = 0 AND b.competencia IS NOT NULL AND b.fecha >= ?
               GROUP BY b.competencia ORDER BY veces DESC, b.competencia""", (desde,)).fetchall()
    return [dict(f) for f in filas]


def actividad_docente(solicitante: Usuario, usuario_id: int, limite: int = 30) -> list[dict]:
    _exigir_direccion(solicitante)
    return historial(usuario_id, limite)


def restablecer_clave(solicitante: Usuario, usuario_id: int) -> str:
    """Genera una contraseña temporal. El docente tendrá que cambiarla al entrar."""
    _exigir_direccion(solicitante)
    temporal = seg.clave_temporal()
    with conectar() as con:
        con.execute("""UPDATE usuarios SET clave_hash = ?, debe_cambiar_clave = 1, intentos_fallidos = 0,
                       bloqueado_hasta = NULL WHERE id = ? AND rol = 'docente'""",
                    (seg.hash_clave(temporal), usuario_id))
        _cerrar_sesiones_de(con, usuario_id)
    return temporal


def crear_docente(solicitante: Usuario, usuario: str, nombre: str) -> str:
    """La dirección crea la cuenta; devuelve la contraseña temporal."""
    _exigir_direccion(solicitante)
    temporal = seg.clave_temporal()
    crear_usuario(usuario, nombre, temporal, rol="docente", debe_cambiar_clave=True)
    return temporal


def cambiar_estado(solicitante: Usuario, usuario_id: int, activo: bool) -> None:
    _exigir_direccion(solicitante)
    with conectar() as con:
        con.execute("UPDATE usuarios SET activo = ? WHERE id = ? AND rol = 'docente'", (int(activo), usuario_id))
        if not activo:
            _cerrar_sesiones_de(con, usuario_id)


def copia_de_respaldo(solicitante: Usuario) -> bytes:
    """Copia consistente de la base (aunque haya docentes usándola) para guardar en una USB."""
    _exigir_direccion(solicitante)
    with tempfile.TemporaryDirectory() as carpeta:
        destino = Path(carpeta) / "respaldo.db"
        origen = sqlite3.connect(RUTA_BD)
        copia = sqlite3.connect(destino)
        with copia:
            origen.backup(copia)
        origen.close()
        copia.close()
        return destino.read_bytes()


# ---------------------------------------------------------------------------
# Uso desde la terminal de la computadora de la escuela (ver admin.py)
# ---------------------------------------------------------------------------

def restablecer_direccion_local(usuario: str, nueva: str) -> bool:
    """Solo desde la PC de la escuela (admin.py): recupera el acceso de la dirección."""
    with conectar() as con:
        cur = con.execute("""UPDATE usuarios SET clave_hash = ?, debe_cambiar_clave = 0, activo = 1,
                             intentos_fallidos = 0, bloqueado_hasta = NULL
                             WHERE usuario = ? AND rol = 'admin'""", (seg.hash_clave(nueva), usuario))
        if cur.rowcount:
            con.execute("DELETE FROM sesiones WHERE usuario_id = (SELECT id FROM usuarios WHERE usuario = ?)",
                        (usuario,))
        return cur.rowcount > 0


def cuentas_direccion() -> list[str]:
    with conectar() as con:
        return [f["usuario"] for f in con.execute("SELECT usuario FROM usuarios WHERE rol = 'admin'")]

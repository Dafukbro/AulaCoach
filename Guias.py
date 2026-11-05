"""
Guías pedagógicas locales (la "memoria" de AulaCoach, sin internet).

Antes de pedirle algo al modelo, se buscan en guias/fichas.json las estrategias
que mejor encajan con el tema, la situación del grupo y los recursos del salón.
La búsqueda es por palabras (sin embeddings ni librerías extra): corre en
milisegundos en cualquier PC y no necesita más memoria.

Las fichas van al prompt dentro de <guia>, así el modelo se apoya en
estrategias reales en lugar de inventarlas, y la pantalla muestra al docente
en qué guía se basó la idea.

Para agregar fichas: editar guias/fichas.json (mismo formato) y reiniciar.
"""

import json
import logging
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("aulacoach")

RUTA_FICHAS = Path(__file__).resolve().with_name("guias") / "fichas.json"

# Palabras que no ayudan a distinguir una ficha de otra.
_VACIAS = set("""
a al algo algun alguna algunos ante con contra cual cuando de del desde donde
el ella ellos en entre era es esa ese eso esta este esto estos fue ha hay la las
le les lo los mas me mi mis muy ni no nos o otra otro para pero poco por que se
sin sobre son su sus tambien tan te tema tiene tienen todo todos tu un una unos
y ya yo hoy clase clases grado estudiantes alumnos ninos vez veces mucho mucha
""".split())

# Pistas para saber de qué área es el tema.
_AREAS = {
    "matematicas": ["fraccion", "suma", "resta", "multiplic", "divis", "numer", "geometr", "figura",
                    "medida", "medir", "porcentaje", "ecuacion", "algebra", "decimal", "tabla", "calcul",
                    "problema", "perimetro", "area", "angulo", "estadistic", "grafica", "dinero", "matemat"],
    "lenguaje": ["lectur", "leer", "lect", "cuento", "escrit", "ortograf", "gramatic", "poema", "poesia",
                 "texto", "verbo", "sustantiv", "adjetiv", "silaba", "letra", "palabra", "oracion",
                 "redacc", "fabula", "leyenda", "lenguaje", "espanol", "comunicacion"],
    "ciencias": ["agua", "ciclo", "planta", "animal", "seres vivos", "ser vivo", "cuerpo", "energia",
                 "materia", "celula", "ecosistema", "experiment", "clima", "suelo", "sistema solar",
                 "planeta", "alimenta", "salud", "luz", "sonido", "fuerza", "ciencia", "natural"],
    "sociales": ["historia", "geograf", "mapa", "comunidad", "independencia", "region", "pais",
                 "cultura", "ciudadan", "derecho", "familia", "pueblo", "civica", "social", "patria"],
}

# La situación del grupo que el docente toca en pantalla -> palabras de las fichas.
SITUACIONES = {
    "Vienen inquietos": "inquietos energia recreo movimiento",
    "Es tema nuevo": "tema nuevo",
    "Es repaso": "repaso",
    "Hay niveles muy distintos": "varios niveles atrasados multigrado",
    "Participan siempre los mismos": "participan siempre los mismos timidez participacion",
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def _raiz(palabra: str) -> str:
    """Raíz muy simple: 'inquietos', 'inquieta' e 'inquietud' cuentan igual."""
    return palabra[:5] if len(palabra) > 5 else palabra.rstrip("s")


def _raices(texto: str) -> set[str]:
    palabras = re.findall(r"[a-z0-9]+", normalizar(texto))
    return {_raiz(p) for p in palabras if p not in _VACIAS and len(p) > 2}


@lru_cache(maxsize=1)
def cargar_fichas() -> tuple[dict, ...]:
    try:
        datos = json.loads(RUTA_FICHAS.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("No se pudieron leer las guías en %s", RUTA_FICHAS)
        return ()
    fichas = []
    for f in datos.get("fichas", []):
        if not all(isinstance(f.get(k), str) and f[k].strip() for k in ("id", "nombre", "como")):
            continue  # una ficha mal escrita no debe tumbar la app
        f = dict(f)
        f["_situacion"] = _raices(" ".join(f.get("sirve_para", [])))
        f["_texto"] = _raices(f"{f['nombre']} {f['como']} {f.get('por_que', '')}")
        fichas.append(f)
    return tuple(fichas)


def area_del_tema(tema: str) -> str | None:
    t = normalizar(tema)
    puntos = {area: sum(p in t for p in pistas) for area, pistas in _AREAS.items()}
    mejor = max(puntos, key=puntos.get)
    return mejor if puntos[mejor] else None


def _se_puede(ficha: dict, recursos: str) -> bool:
    """Descarta fichas que necesitan algo que el salón no tiene (pizarrón, patio, hojas)."""
    r = normalizar(recursos)
    return all(n in r for n in ficha.get("necesita", []))


CLASE_CORTA = 15   # hasta aquí se usa la versión "corta" de cada ficha


def buscar(tema: str, situacion: str = "", recursos: str = "", cuantas: int = 2,
           excluir: tuple[str, ...] = (), minutos: int | None = None) -> list[dict]:
    """Las fichas que mejor encajan, de la más a la menos útil. Siempre devuelve algo
    si hay fichas posibles: las de 'todas' las áreas sirven de comodín.
    Con `minutos`, se descartan las que no caben en ese tiempo (unas estaciones
    rotativas no se hacen en 15 minutos)."""
    if minutos:
        elegidas = buscar(tema, situacion, recursos, cuantas, excluir)
        caben = [f for f in _puntuar(tema, situacion, recursos, excluir) if f.get("minutos", 0) <= minutos]
        return caben[:cuantas] if len(caben) >= cuantas else elegidas
    return _puntuar(tema, situacion, recursos, excluir)[:cuantas]


def _puntuar(tema: str, situacion: str, recursos: str, excluir: tuple[str, ...]) -> list[dict]:
    area = area_del_tema(tema)
    pedido_situacion = _raices(situacion)
    pedido_texto = _raices(f"{tema} {situacion}")

    puntuadas = []
    for f in cargar_fichas():
        if f["id"] in excluir or not _se_puede(f, recursos):
            continue
        areas = f.get("areas", [])
        if area and area not in areas and "todas" not in areas:
            continue  # una ficha de lectura no sirve para fracciones
        puntos = 3 * len(pedido_situacion & f["_situacion"])
        puntos += len(pedido_texto & (f["_texto"] | f["_situacion"]))
        if area and area in areas:
            puntos += 1.5
        elif not area and "todas" in areas:
            puntos += 0.5  # tema desconocido: mejor una estrategia general
        puntuadas.append((puntos, f["id"], f))

    puntuadas.sort(key=lambda x: (-x[0], x[1]))
    return [f for _, _, f in puntuadas]


def texto_para_modelo(fichas: list[dict], minutos: int | None = None) -> str:
    """Lo que va dentro de <guia>. Corto: un modelo de 4B se pierde con textos largos.
    En clases cortas va la versión corta de la ficha: así el modelo no intenta
    meter todas las fases de la estrategia en 15 minutos."""
    partes = []
    for i, f in enumerate(fichas):
        letra = "AB"[i] if len(fichas) > 1 and i < 2 else ""
        encabezado = f"Estrategia {letra}: " if letra else "Estrategia: "
        como = f.get("corta") if minutos and minutos <= CLASE_CORTA and f.get("corta") else f["como"]
        partes.append(f"{encabezado}{f['nombre']}. {como} Por qué sirve: {f.get('por_que', '')}".strip())
    return "\n".join(partes)


def nombres(fichas: list[dict]) -> list[str]:
    return [f["nombre"] for f in fichas]


def por_nombre(nombre: str) -> dict | None:
    return next((f for f in cargar_fichas() if f["nombre"] == nombre), None)

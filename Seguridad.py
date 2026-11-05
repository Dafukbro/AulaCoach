"""
Seguridad de AulaCoach: contraseñas, tokens de sesión y limpieza de texto.

Todo usa la biblioteca estándar de Python (sin dependencias extra) y funciona sin internet.
"""

import base64
import hashlib
import hmac
import re
import secrets
import unicodedata

# scrypt usa memoria a propósito para frenar ataques de fuerza bruta (~16 MB por intento).
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2 ** 14, 8, 1
_PBKDF2_ITERACIONES = 300_000  # respaldo si el Python no trae scrypt

CLAVE_MINIMA_DOCENTE = 6
CLAVE_MINIMA_DIRECCION = 8

_CLAVES_DEBILES = {
    "123456", "1234567", "12345678", "123456789", "000000", "111111", "654321",
    "contraseña", "contrasena", "password", "qwerty", "abc123", "escuela",
    "aulacoach", "profesor", "profesora", "maestro", "maestra", "docente",
}

_PALABRAS_TEMPORALES = ["tiza", "lapiz", "regla", "libro", "mapa", "globo", "recreo",
                        "pupitre", "cuaderno", "pizarra", "mochila", "borrador"]


def _b64(datos: bytes) -> str:
    return base64.b64encode(datos).decode("ascii")


def hash_clave(clave: str) -> str:
    sal = secrets.token_bytes(16)
    if hasattr(hashlib, "scrypt"):
        derivada = hashlib.scrypt(clave.encode("utf-8"), salt=sal, n=_SCRYPT_N,
                                  r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
        return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(sal)}${_b64(derivada)}"
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, _PBKDF2_ITERACIONES)
    return f"pbkdf2${_PBKDF2_ITERACIONES}${_b64(sal)}${_b64(derivada)}"


def verificar_clave(clave: str, guardado: str | None) -> bool:
    if not guardado:
        return False
    try:
        partes = guardado.split("$")
        if partes[0] == "scrypt":
            n, r, p = int(partes[1]), int(partes[2]), int(partes[3])
            sal, esperado = base64.b64decode(partes[4]), base64.b64decode(partes[5])
            obtenido = hashlib.scrypt(clave.encode("utf-8"), salt=sal, n=n, r=r, p=p,
                                      dklen=len(esperado))
        elif partes[0] == "pbkdf2":
            iteraciones = int(partes[1])
            sal, esperado = base64.b64decode(partes[2]), base64.b64decode(partes[3])
            obtenido = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal, iteraciones)
        else:
            return False
    except (ValueError, IndexError):
        return False
    return hmac.compare_digest(obtenido, esperado)


_hash_ficticio: str | None = None


def verificar_ficticio(clave: str) -> None:
    """Gasta el mismo tiempo que una verificación real cuando el usuario no existe,
    para no revelar qué usuarios están registrados."""
    global _hash_ficticio
    if _hash_ficticio is None:
        _hash_ficticio = hash_clave(secrets.token_hex(8))
    verificar_clave(clave, _hash_ficticio)


def normalizar_usuario(usuario: str) -> str:
    texto = unicodedata.normalize("NFD", (usuario or "").strip().lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def validar_usuario(usuario: str) -> tuple[str, str | None]:
    """Devuelve (usuario normalizado, mensaje de error o None)."""
    u = normalizar_usuario(usuario)
    if len(u) < 3:
        return u, "El usuario debe tener al menos 3 letras."
    if len(u) > 30:
        return u, "El usuario puede tener hasta 30 caracteres."
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", u):
        return u, "Usa solo letras, números, punto o guion, sin espacios. Ej.: maria.lopez"
    return u, None


def validar_clave(clave: str, usuario: str = "", minimo: int = CLAVE_MINIMA_DOCENTE) -> str | None:
    if len(clave) < minimo:
        return f"La contraseña debe tener al menos {minimo} caracteres."
    if len(clave) > 128:
        return "La contraseña es demasiado larga."
    if clave.lower() in _CLAVES_DEBILES or len(set(clave)) <= 2:
        return "Esa contraseña es muy fácil de adivinar. Prueba con otra."
    if usuario and normalizar_usuario(clave) == normalizar_usuario(usuario):
        return "La contraseña no puede ser igual a tu usuario."
    return None


def nuevo_token() -> tuple[str, str]:
    """Devuelve (token para la cookie del navegador, hash que se guarda en la base de datos)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", errors="ignore")).hexdigest()


def token_valido(token: str | None) -> bool:
    return bool(token) and bool(re.fullmatch(r"[A-Za-z0-9_-]{20,100}", token))


def clave_temporal() -> str:
    """Fácil de dictar en persona: 'tiza-4821'."""
    return f"{secrets.choice(_PALABRAS_TEMPORALES)}-{secrets.randbelow(9000) + 1000}"


def limpiar_texto(texto: str | None, maximo: int) -> str:
    """Quita caracteres de control, junta espacios y recorta. Para todo texto que escribe una persona."""
    if not texto:
        return ""
    texto = "".join(c for c in str(texto) if c in "\n\t" or unicodedata.category(c)[0] != "C")
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    return texto[:maximo].strip()

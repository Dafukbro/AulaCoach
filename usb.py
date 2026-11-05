"""
Instalar AulaCoach desde una memoria USB, en una escuela sin internet.

  1. En una computadora CON internet (una sola vez):
         python usb.py preparar
     Deja en la carpeta `instalador/` todo lo que la escuela necesita:
     los paquetes de Python para Windows y el modelo de IA ya descargado.
     (preparar_usb.bat hace esto y además baja los instaladores de Python y Ollama.)

  2. Copiar la carpeta de AulaCoach completa a la USB.

  3. En la computadora de la escuela, SIN internet:
         python usb.py instalar
     (instalar_sin_internet.bat instala antes Python y Ollama si faltan.)

El modelo se copia comprobando su huella SHA-256: si la USB se dañó o alguien
cambió el archivo, la instalación lo detecta y no lo usa.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
INSTALADOR = CARPETA / "instalador"
PLATAFORMAS = {
    "windows": ["win_amd64"],
    "linux": ["manylinux_2_28_x86_64", "manylinux_2_17_x86_64", "manylinux2014_x86_64"],
}
BLOQUE = 8 * 1024 * 1024


def _modelo_por_defecto() -> str:
    return os.getenv("AULACOACH_MODELO", "qwen3.5:4b")


def carpeta_modelos_ollama() -> Path:
    """Donde Ollama guarda los modelos (la misma regla que usa Ollama)."""
    propia = os.getenv("OLLAMA_MODELS")
    return Path(propia) if propia else Path.home() / ".ollama" / "models"


def ruta_manifiesto(modelo: str) -> Path:
    nombre, _, etiqueta = modelo.partition(":")
    etiqueta = etiqueta or "latest"
    partes = nombre.split("/")
    if len(partes) == 1:
        partes = ["library", *partes]
    return Path("manifests", "registry.ollama.ai", *partes, etiqueta)


def _blobs_del_manifiesto(manifiesto: Path) -> list[tuple[str, int]]:
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    capas = [datos["config"], *datos.get("layers", [])]
    return [(c["digest"], int(c.get("size", 0))) for c in capas]


def _archivo_blob(digest: str) -> str:
    return digest.replace(":", "-")   # "sha256:abc" -> "sha256-abc"


def _copiar_verificando(origen: Path, destino: Path, digest: str) -> None:
    """Copia y calcula la huella a la vez (un solo paso por el disco: importa en una USB lenta)."""
    algoritmo, esperado = digest.split(":", 1)
    huella = hashlib.new(algoritmo)
    temporal = destino.with_name(destino.name + ".parcial")
    destino.parent.mkdir(parents=True, exist_ok=True)
    with open(origen, "rb") as f, open(temporal, "wb") as g:
        while bloque := f.read(BLOQUE):
            huella.update(bloque)
            g.write(bloque)
    if huella.hexdigest() != esperado:
        temporal.unlink(missing_ok=True)
        raise SystemExit(f"\n  El archivo {origen.name} está dañado o fue modificado. Vuelva a preparar la USB.")
    os.replace(temporal, destino)


def _copiar_modelo(origen: Path, destino: Path, modelo: str) -> int:
    """Copia el manifiesto y los blobs de un modelo entre dos carpetas con formato de Ollama."""
    manifiesto = origen / ruta_manifiesto(modelo)
    if not manifiesto.exists():
        raise SystemExit(f"\n  No encuentro el modelo {modelo} en {origen}.")
    total = 0
    for digest, tam in _blobs_del_manifiesto(manifiesto):
        nombre = _archivo_blob(digest)
        de, a = origen / "blobs" / nombre, destino / "blobs" / nombre
        if a.exists() and a.stat().st_size == de.stat().st_size:
            print(f"  ya estaba: {nombre[:19]}…")
            continue
        print(f"  copiando {nombre[:19]}… ({tam / 1e9:.2f} GB)" if tam > 1e8 else f"  copiando {nombre[:19]}…")
        _copiar_verificando(de, a, digest)
        total += tam
    (destino / ruta_manifiesto(modelo)).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifiesto, destino / ruta_manifiesto(modelo))
    return total


def preparar(args) -> None:
    INSTALADOR.mkdir(exist_ok=True)

    print(f"\n1/2  Descargando los paquetes de Python ({args.sistema}, Python {args.python})…")
    plataformas = [x for p in PLATAFORMAS[args.sistema] for x in ("--platform", p)]
    subprocess.run([sys.executable, "-m", "pip", "download", "-r", str(CARPETA / "requirements.txt"),
                    "-d", str(INSTALADOR / "paquetes"), "--only-binary=:all:", *plataformas,
                    "--python-version", args.python, "--implementation", "cp", "--quiet"], check=True)
    (INSTALADOR / "python-version.txt").write_text(f"{args.python}\n{args.sistema}\n", encoding="utf-8")

    print(f"\n2/2  Copiando el modelo {args.modelo}…")
    modelos = carpeta_modelos_ollama()
    if not (modelos / ruta_manifiesto(args.modelo)).exists():
        if not shutil.which("ollama"):
            raise SystemExit("\n  Instale Ollama en esta computadora y vuelva a intentarlo.")
        subprocess.run(["ollama", "pull", args.modelo], check=True)
    _copiar_modelo(modelos, INSTALADOR / "modelos", args.modelo)
    (INSTALADOR / "modelo.txt").write_text(args.modelo + "\n", encoding="utf-8")

    tam = sum(f.stat().st_size for f in INSTALADOR.rglob("*") if f.is_file())
    print(f"\nListo. La carpeta instalador/ pesa {tam / 1e9:.1f} GB.")
    print("Copie la carpeta completa de AulaCoach a la USB.")


def instalar(args) -> None:
    if not INSTALADOR.exists():
        raise SystemExit("\n  No encuentro la carpeta instalador/. ¿Se preparó la USB con preparar_usb.bat?")
    modelo = args.modelo or (INSTALADOR / "modelo.txt").read_text(encoding="utf-8").strip()

    print("\n1/2  Instalando los paquetes de Python (sin internet)…")
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--find-links",
                    str(INSTALADOR / "paquetes"), "-r", str(CARPETA / "requirements.txt"), "--quiet"], check=True)

    destino = carpeta_modelos_ollama()
    print(f"\n2/2  Copiando el modelo {modelo} a {destino} (comprobando que no esté dañado)…")
    _copiar_modelo(INSTALADOR / "modelos", destino, modelo)

    print("\nListo. AulaCoach ya puede usarse sin internet: abra iniciar.bat")


def main() -> None:
    p = argparse.ArgumentParser(description="Instalar AulaCoach desde una USB, sin internet.")
    sub = p.add_subparsers(dest="orden", required=True)
    a = sub.add_parser("preparar", help="en una computadora con internet")
    a.add_argument("--sistema", choices=list(PLATAFORMAS), default="windows")
    a.add_argument("--python", default="3.12", help="versión de Python de la escuela (por defecto 3.12)")
    a.add_argument("--modelo", default=_modelo_por_defecto())
    a.set_defaults(func=preparar)
    b = sub.add_parser("instalar", help="en la computadora de la escuela, sin internet")
    b.add_argument("--modelo", default=None)
    b.set_defaults(func=instalar)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

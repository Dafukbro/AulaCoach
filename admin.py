"""
Herramienta de la dirección, solo desde la computadora de la escuela.

    python admin.py crear        Crea la cuenta de la dirección (si aún no existe)
    python admin.py restablecer  La dirección olvidó su contraseña

Como se ejecuta en la propia computadora (no desde el Wi-Fi), es la forma
segura de recuperar el acceso de la dirección.
"""

import sys
from getpass import getpass

import BaseDatos as BD
import Seguridad as seg


def _pedir_clave() -> str:
    while True:
        clave = getpass("Nueva contraseña (no se ve al escribir): ")
        error = seg.validar_clave(clave, minimo=seg.CLAVE_MINIMA_DIRECCION)
        if error:
            print(f"  {error}")
            continue
        if getpass("Repítela: ") != clave:
            print("  No coinciden. Intenta de nuevo.")
            continue
        return clave


def crear() -> None:
    if BD.hay_direccion():
        print("Ya existe una cuenta de la dirección:", ", ".join(BD.cuentas_direccion()))
        print("Si olvidó la contraseña, use: python admin.py restablecer")
        return
    nombre = input("Nombre (ej.: Directora Ana Pérez): ").strip() or "Dirección"
    usuario, error = seg.validar_usuario(input("Usuario [direccion]: ").strip() or "direccion")
    if error:
        print(error)
        return
    BD.crear_usuario(usuario, nombre, _pedir_clave(), rol="admin")
    print(f"Listo. Entre a AulaCoach con el usuario «{usuario}».")


def restablecer() -> None:
    cuentas = BD.cuentas_direccion()
    if not cuentas:
        print("No hay cuenta de la dirección. Use: python admin.py crear")
        return
    usuario = cuentas[0] if len(cuentas) == 1 else input(f"Usuario ({', '.join(cuentas)}): ").strip()
    if BD.restablecer_direccion_local(seg.normalizar_usuario(usuario), _pedir_clave()):
        print(f"Listo. La contraseña de «{usuario}» quedó cambiada y se cerraron sus sesiones abiertas.")
    else:
        print("No encontré esa cuenta de la dirección.")


if __name__ == "__main__":
    BD.inicializar_bd()
    accion = sys.argv[1] if len(sys.argv) > 1 else ""
    if accion == "crear":
        crear()
    elif accion == "restablecer":
        restablecer()
    else:
        print(__doc__)

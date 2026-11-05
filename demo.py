"""
Prepara AulaCoach para una demostración en vivo ante un jurado.

    python demo.py preparar    Carga una escuela de ejemplo con cuentas listas para el jurado
    python demo.py restaurar   Devuelve la base de datos original (antes de la demo)
"""

import shutil
import sqlite3
import sys
from datetime import datetime, timedelta

import BaseDatos as BD
import Interfaz as ui
import Motor

RESPALDO_DEMO = BD.RUTA_BD.with_name("escuela.antes-de-demo.db")
CLAVE_DIRECCION = "escuela-demo"
CLAVE_JURADO = "aula2026"


def _fecha(dias_atras: int, hora: int = 9, minuto: int = 30) -> str:
    momento = (datetime.now() - timedelta(days=dias_atras)).replace(
        hour=hora, minute=minuto, second=0, microsecond=0
    )
    return momento.strftime("%Y-%m-%d %H:%M:%S")


def preparar() -> None:
    if BD.RUTA_BD.exists() and not RESPALDO_DEMO.exists():
        origen = sqlite3.connect(BD.RUTA_BD)
        copia = sqlite3.connect(RESPALDO_DEMO)
        with copia:
            origen.backup(copia)
        origen.close()
        copia.close()
        print(f"  Respaldo guardado en: {RESPALDO_DEMO.name}")

    for sufijo in ("", "-wal", "-shm"):
        archivo = BD.RUTA_BD.with_name(BD.RUTA_BD.name + sufijo)
        archivo.unlink(missing_ok=True)

    BD.inicializar_bd()
    BD.crear_usuario("direccion", "Directora Ana Pérez", CLAVE_DIRECCION, rol="admin")

    docentes = [
        ("profe.maria", "Profe María", "4.º grado", 25, "basico",
         "pizarrón y tiza, hojas recicladas, cuadernos, patio o cancha"),
        ("profe.carlos", "Profe Carlos", "2.º grado", 25, "basico",
         "pizarrón y tiza, hojas recicladas, material reciclado, tapitas y semillas"),
        ("profe.elena", "Profe Elena", "6.º grado", 35, "intermedio",
         "pizarrón y tiza, cuadernos, libros de texto, cartulina y marcadores"),
        ("profe.lucia", "Profe Lucía", "3.º grado", 25, "basico",
         "pizarrón y tiza, hojas recicladas, libros de texto"),
        ("profe.jorge", "Profe Jorge", "Secundaria", 35, "intermedio",
         "pizarrón y tiza, cuadernos, patio o cancha"),
    ]
    ids: dict[str, int] = {}
    for cuenta, nombre, grado, est, nivel, recursos in docentes:
        uid = BD.crear_usuario(cuenta, nombre, CLAVE_JURADO, rol="docente")
        BD.guardar_perfil(uid, grado, est, nivel, recursos)
        ids[cuenta] = uid

    planes = [
        # (cuenta, dias_atras, tema, minutos, respuesta, contexto, guias, ruta, adaptacion, reto_txt, observar, res_reto)
        (
            "profe.maria", 14, "Multiplicación", 20,
            "**Ruta A: Grupos de tapitas** (20 min)\n"
            "En parejas desde sus puestos, arman montoncitos iguales en una hoja reciclada y dictan la suma repetida para que tú la escribas como multiplicación en el pizarrón.\n"
            "**Ruta B: El número escondido** (20 min)\n"
            "Escribes 4 productos en el pizarrón y cada fila busca en su cuaderno qué multiplicación los forma. Un vocero por fila pasa al frente a explicar cómo lo pensaron.\n"
            "**Pregunta para ti:** ¿Tu grupo entiende ya la multiplicación como grupos iguales o conviene que hoy la vean primero con dibujos?",
            "Hay niveles muy distintos", "Piensa, conversa en pareja y comparte", "A",
            "Dibujan círculos en la hoja en vez de usar tapitas.",
            "Empareja a quien ya domina las tablas con quien aún suma de uno en uno y pide que el segundo sea quien dicte el resultado.",
            "Si ambos integrantes de la pareja participan antes de levantar la mano.",
            "funciono",
        ),
        (
            "profe.maria", 6, "Comprensión lectora", 15,
            "**Ruta A: Tres paradas del cuento** (15 min)\n"
            "Lees un párrafo corto en voz alta y te detienes dos veces para que, en parejas desde su lugar, adivinen qué pasará después en media hoja.\n"
            "**Ruta B: Pregunta del detective** (15 min)\n"
            "Escribes una sola pregunta en el pizarrón antes de leer; escuchan desde sus puestos buscando la pista y tres estudiantes dicen cómo la encontraron.\n"
            "**Pregunta para ti:** ¿Qué les cuesta más hoy: seguir el hilo de la historia o animarse a hablar frente al grupo?",
            "Participan siempre los mismos", "Piensa, conversa en pareja y comparte", "B",
            "Que primero se lo digan al compañero de al lado.",
            "Da 30 segundos para que cada quien ensaye su respuesta con su compañero antes de pedir voluntarios.",
            "Si levantan la mano estudiantes que casi nunca hablan.",
            "funciono",
        ),
        (
            "profe.maria", 2, "Fracciones", 20,
            "**Ruta A: Doblamos mitades y cuartos** (20 min)\n"
            "Cada estudiante dobla una hoja reciclada en 2 y luego en 4 partes iguales desde su puesto, pinta una mitad y comprueba cuántos cuartos caben en ella.\n"
            "**Ruta B: La recta en el pizarrón** (20 min)\n"
            "Trazas una barra grande en el pizarrón dividida en octavos y, por turnos, un representante de cada fila pasa a colorear la fracción equivalente que su equipo calculó.\n"
            "**Pregunta para ti:** ¿Tu grupo ya ubicó mitades y cuartos con papel o todavía confunde el número de abajo con el de arriba?",
            "Vienen inquietos", "Del objeto al dibujo y al símbolo", "A",
            "Lo hacemos paso a paso todos juntos para que no hagan aviones de papel.",
            "Pide a 2 estudiantes inquietos que repartan las hojas y muestra tú el primer doblez en alto antes de que ellos toquen el papel.",
            "Si todo el grupo termina el segundo doblez al mismo tiempo sin distraerse.",
            None,  # Reto abierto para mostrar en "Después de clase"
        ),
        (
            "profe.carlos", 4, "Suma y resta", 15,
            "**Ruta A: Tiendita con tapitas** (15 min)\n"
            "Cada pareja recibe 10 tapitas en su mesa; tú dices un precio en voz alta y ellos separan lo que pagan y dicen cuánto cambio les queda.\n"
            "**Ruta B: Saltos en el piso** (15 min)\n"
            "Dibujas con tiza una recta del 1 al 15 frente al pizarrón; un niño pasa a dar los saltos mientras el resto cuenta en voz alta desde su lugar.\n"
            "**Pregunta para ti:** ¿Hoy necesitas que todos practiquen al mismo tiempo en su mesa o que vean el movimiento uno por uno?",
            "Vienen inquietos", "Material concreto del entorno", "A",
            "Con 10 semillas por pareja.",
            "Nombra a un encargado del banco en cada pareja para que cuente las semillas en voz baja antes de empezar.",
            "Si logran hacer 3 rondas sin que se caigan las semillas al piso.",
            "funciono",
        ),
        (
            "profe.elena", 3, "Seres vivos", 30,
            "**Ruta A: Mapa de cadenas en el pizarrón** (30 min)\n"
            "Cada equipo elige 4 seres vivos de la comunidad en su cuaderno y un vocero pasa a unirlos con flechas de tiza en el pizarrón según quién se alimenta de quién.\n"
            "**Ruta B: ¿Qué pasa si falta uno?** (30 min)\n"
            "Borras un ser vivo de la cadena del pizarrón y cada fila discute 3 minutos qué ocurre con los demás antes de defender su idea.\n"
            "**Pregunta para ti:** ¿Tu grupo ya distingue productores y consumidores o conviene armar primero la cadena entre todos?",
            "Es tema nuevo", "Mapa en el pizarrón entre todos", "B",
            "Uso animales y cultivos que ellos conocen de la región.",
            "Asigna un rol de vocero en cada fila a alguien distinto de quienes participaron ayer.",
            "Si las 4 filas dan un argumento usando ejemplos locales.",
            "funciono",
        ),
        (
            "profe.jorge", 1, "Escritura", 30,
            "**Ruta A: Un párrafo entre dos** (30 min)\n"
            "En parejas, escriben una historia de 4 oraciones en el cuaderno alternando quién escribe cada oración y revisan juntos que no se repitan palabras.\n"
            "**Ruta B: Finales distintos** (30 min)\n"
            "Copias el inicio de una noticia en el pizarrón y cada estudiante escribe en 10 minutos un desenlace distinto para leerlo a su fila.\n"
            "**Pregunta para ti:** ¿A tu grupo le cuesta más arrancar a escribir la primera línea o revisar lo que ya escribió?",
            "Es repaso", "Escritura en pareja con roles", "A",
            "Uno dicta la idea y el otro cuida los puntos y comas.",
            "Escribe en una esquina del pizarrón los 3 conectores que deben incluir en su párrafo.",
            "Si las parejas usan al menos 2 conectores sin que tengas que recordárselo.",
            "no_funciono",
        ),
    ]

    bitacoras = [
        # (cuenta, dias_atras, tema, que_paso, que_costo, reconocimiento, micro_accion, pregunta, riesgo, guias, res_reto)
        (
            "profe.maria", 12, "Multiplicación",
            "Trabajaron en equipos", "Participaron siempre los mismos. Dos niños hicieron todo el cálculo.",
            "Notaste quién concentró la tarea en los equipos; eso te permite repartir mejor los turnos.",
            "Numera del 1 al 4 a cada equipo y avisa al inicio que tú dirás al azar qué número explica el resultado.",
            "¿Qué tarea pequeña podrías encargarles a los más callados antes de pasar al pizarrón?",
            0, "Cabezas numeradas", "funciono",
        ),
        (
            "profe.maria", 9, "Fracciones",
            "Explicación en el pizarrón", "No entendieron las instrucciones. Preguntaban varias veces qué doblar.",
            "Identificaste el momento exacto en que se perdieron durante la consigna.",
            "Antes de repartir las hojas, haz tú el doblez frente al grupo y pide a un estudiante que repita los 2 pasos.",
            "¿En qué parte de la explicación sientes que empiezan a distraerse?",
            0, "Consigna en tres pasos", "funciono",
        ),
        (
            "profe.maria", 5, "Comprensión lectora",
            "Leímos en voz alta", "Faltó tiempo. Nos quedamos sin hacer el cierre de la lectura.",
            "Cuidaste la lectura compartida y viste que el cierre necesita su propio espacio.",
            "Nombra a un guardián del tiempo en primera fila que levante la mano cuando falten 3 minutos para terminar.",
            "¿Qué parte de la lectura podrías acortar un poco para asegurar esos 3 minutos finales?",
            0, "Boleto de salida verbal", "funciono",
        ),
        (
            "profe.carlos", 4, "Suma y resta",
            "Trabajaron en equipos", "Se distrajeron mucho. Jugaban con las tapitas después de contar.",
            "Usaste material concreto de tu entorno para que vieran la resta con sus manos.",
            "Acuerda una señal de manos arriba: al verla, todos guardan las tapitas en el centro de la mesa en 5 segundos.",
            "¿En qué momento de la clase estuvieron más concentrados con el material?",
            0, "Señal silenciosa de atención", "funciono",
        ),
        (
            "profe.elena", 2, "Seres vivos",
            "Explicación en el pizarrón", "Participaron siempre los mismos",
            "Lograste que conectaran el tema con los animales de su propia comunidad.",
            "Pide que cada estudiante escriba primero un ejemplo en su cuaderno durante 1 minuto antes de levantar la mano.",
            "¿Qué cambia cuando tienen algo escrito frente a ellos antes de hablar?",
            0, "Piensa, conversa en pareja y comparte", "funciono",
        ),
        (
            "profe.lucia", 3, "Escritura",
            "Trabajo individual en hojas", "Se copiaban entre ellos. Miraban la hoja del compañero de al lado.",
            "Observaste que buscaban apoyo en el compañero porque dudaban cómo empezar.",
            "Da dos opciones de tema en el pizarrón para que los compañeros de la misma mesa elijan uno distinto.",
            "¿Copiaban por falta de tiempo o porque no sabían cómo empezar la frase?",
            0, "Dos variantes en el pizarrón", "no_funciono",
        ),
        (
            "profe.lucia", 1, "Comprensión lectora",
            "Trabajo individual en hojas",
            "Un estudiante llegó con moretones en los brazos y dijo que le pegan en su casa.",
            "Hiciste bien en registrarlo.",
            Motor.MENSAJE_RIESGO,
            "¿A quién de tu escuela le vas a avisar hoy?",
            1, "", None,
        ),
    ]

    with BD.conectar() as con:
        for (cuenta, dias, tema, mins, resp, ctx, guias, ruta, adapta, reto_txt, obs, res_reto) in planes:
            uid = ids[cuenta]
            f_plan = _fecha(dias, 8, 15)
            cur = con.execute(
                """INSERT INTO planes (usuario_id, fecha, tema, minutos, respuesta, contexto, guias,
                                       ruta_elegida, adaptacion, riesgo)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (uid, f_plan, tema, mins, resp, ctx, guias, ruta, adapta),
            )
            f_res = _fecha(max(0, dias - 1), 13, 10) if res_reto else None
            con.execute(
                """INSERT INTO retos (usuario_id, fecha, origen, origen_id, texto, que_observar,
                                      resultado, fecha_resultado)
                   VALUES (?, ?, 'plan', ?, ?, ?, ?, ?)""",
                (uid, f_plan, cur.lastrowid, reto_txt, obs, res_reto, f_res),
            )

        for (cuenta, dias, tema, paso, costo, rec, micro, preg, riesgo, guias, res_reto) in bitacoras:
            uid = ids[cuenta]
            f_bit = _fecha(dias, 12, 45)
            cur = con.execute(
                """INSERT INTO bitacora (usuario_id, fecha, tema, que_paso, que_costo, reconocimiento,
                                         micro_accion, pregunta_reflexiva, riesgo, competencia, guias)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, f_bit, tema, paso, costo, rec, micro, preg, riesgo,
                 None if riesgo else BD.competencia_de(costo), guias),
            )
            if not riesgo:
                f_res = _fecha(max(0, dias - 1), 14, 0) if res_reto else None
                con.execute(
                    """INSERT INTO retos (usuario_id, fecha, origen, origen_id, texto, resultado, fecha_resultado)
                       VALUES (?, ?, 'bitacora', ?, ?, ?, ?)""",
                    (uid, f_bit, cur.lastrowid, micro, res_reto, f_res),
                )

        for cuenta, dias in (("profe.maria", 0), ("profe.carlos", 1), ("profe.elena", 1),
                             ("profe.lucia", 1), ("profe.jorge", 1)):
            con.execute("UPDATE usuarios SET ultimo_acceso = ? WHERE id = ?", (_fecha(dias, 11, 20), ids[cuenta]))

    urls = ui.direcciones_red()
    print("\n============================================================")
    print("  DEMO DE AULACOACH LISTA PARA PRESENTAR")
    print("============================================================")
    print(f"\n  1. En tu laptop (proyector), entra como DIRECCIÓN:")
    print(f"     Usuario:     direccion")
    print(f"     Contraseña:  {CLAVE_DIRECCION}")
    print(f"     -> Ahí abre «Conectar celulares (código QR)» para proyectar el QR.")
    print(f"\n  2. Para los celulares del JURADO (escaneando el QR):")
    print(f"     Direcciones detectadas: {', '.join(urls)}")
    print(f"     Usuarios de prueba:     profe.maria  |  profe.carlos  |  profe.elena")
    print(f"     Contraseña (todos):     {CLAVE_JURADO}")
    print("\n  Cuando termines la presentación, recupera tu base anterior con:")
    print("     python demo.py restaurar\n")


def restaurar() -> None:
    if not RESPALDO_DEMO.exists():
        print("No hay un respaldo previo (escuela.antes-de-demo.db).")
        return
    for sufijo in ("-wal", "-shm"):
        BD.RUTA_BD.with_name(BD.RUTA_BD.name + sufijo).unlink(missing_ok=True)
    shutil.move(str(RESPALDO_DEMO), str(BD.RUTA_BD))
    print("Listo. Se restauró la base de datos original (escuela.db).")


if __name__ == "__main__":
    orden = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    if orden == "preparar":
        preparar()
    elif orden == "restaurar":
        restaurar()
    else:
        print(__doc__)


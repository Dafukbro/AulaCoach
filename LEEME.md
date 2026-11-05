# AulaCoach

Acompañante pedagógico para docentes, que funciona sin internet en la computadora de la escuela.
Los docentes lo usan desde el navegador de su celular, conectados al Wi-Fi de la escuela.

## Cómo acompaña al docente

1. **Antes de clase.** El docente toca el tema, el tiempo y, si quiere, cómo viene su grupo.
   AulaCoach le escribe **dos micro-rutas** distintas (A y B, de 2 oraciones cada una) con lo que
   hay en su salón, y le hace **una pregunta** sobre algo que solo él sabe de su grupo.
   El docente elige una ruta, dice cómo la adapta (escribiendo o dictando) y recibe
   **una micro-acción** concreta para esa clase.
2. **Después de clase.** AulaCoach le pregunta si probó la micro-acción, qué pasó y qué fue lo
   más difícil. Responde con un reconocimiento, **un solo paso pequeño** para la próxima clase
   y una pregunta para pensar.
3. **Mi avance.** Lo que ha probado, lo que le funcionó, en qué ha trabajado más
   (manejo del grupo, participación de todos, instrucciones claras…) y su
   **siguiente paso digital**, pequeño y sin internet.

AulaCoach nunca escribe una clase completa: el docente decide.

Las rutas respetan el tiempo real del aula. Antes de cada consulta se calcula cuánto da de sí la clase
(organizarse, actividad y cierre, con más margen en los primeros grados) y se le pasa al modelo. Después,
una revisión en Python reescribe una vez las rutas que tienen demasiados pasos para los minutos elegidos
o que piden al grupo ponerse de pie solo para escuchar. Cada ficha de las guías indica los minutos
mínimos que necesita y, si tiene, su versión para una clase de 15 minutos.

La dirección ve la actividad de cada docente, cuántos retos se probaron y en qué piden más apoyo
sus docentes, para elegir el próximo taller o visita de acompañamiento.

## Guías pedagógicas (sin internet)

Las ideas se apoyan en las fichas de `guias/fichas.json` (28 estrategias de aprendizaje activo).
Antes de cada consulta se buscan las que encajan con el tema, el grupo y los recursos del salón,
y la pantalla dice en qué guía se basó la idea. La búsqueda es por palabras: no necesita más memoria.

Las fichas son un borrador del equipo. **Conviene que las revise una persona experta en pedagogía**
y agregar las del ministerio o de ProFuturo: mismo formato, y reiniciar AulaCoach.

## Instalar (una sola vez, con internet)

1. Instalar [Python 3.10 o superior](https://www.python.org/downloads/) y [Ollama](https://ollama.com/download).
2. En una terminal, dentro de esta carpeta:

   ```
   python -m pip install -r requirements.txt
   ollama pull qwen3.5:4b
   ```

Desde aquí ya no se necesita internet.

## Instalar desde una USB (escuela sin internet)

1. En una computadora **con** internet, con Python y Ollama: doble clic en `preparar_usb.bat`.
   Descarga en la carpeta `instalador/` los instaladores de Python 3.12 y Ollama, los paquetes de
   Python para Windows y el modelo de IA (en total unos 3.5 GB).
2. Copiar la carpeta completa de AulaCoach a una USB de 8 GB o más.
3. En la computadora de la escuela, **sin** internet: doble clic en `instalar_sin_internet.bat`.
   Instala Python y Ollama si faltan, los paquetes y el modelo. Al copiar el modelo comprueba su
   huella SHA-256: si la USB se dañó o alguien cambió el archivo, no lo instala.

Si la descarga de los instaladores falla, se pueden bajar a mano de python.org (Windows, 64 bits,
versión 3.12) y de ollama.com, y guardarlos en `instalador/`. En Linux: `python3 usb.py preparar --sistema linux`
y luego `python3 usb.py instalar` dentro de un entorno virtual.

## Usar cada día

- **Windows:** doble clic en `iniciar.bat`.
- **Linux o Mac:** `./iniciar.sh`

Se abre AulaCoach en la computadora. En la ventana negra aparece una dirección como
`Network URL: http://192.168.1.20:8501`: esa es la que los docentes escriben en su celular.
La primera vez, Windows puede preguntar si permite el acceso a la red: elija **Redes privadas**.

## Primera vez

1. La dirección abre AulaCoach **en la computadora de la escuela** y crea su cuenta.
   Desde un celular no se puede: así nadie se adelanta a la dirección.
2. Cada docente entra desde su celular, toca **Crear cuenta** y llena su salón una vez.
   (La dirección puede apagar esto en *Ajustes* y crear las cuentas ella misma.)

## Cuentas y privacidad

- Cada docente ve solo sus ideas y consejos. La dirección ve la actividad de todos, y la app se lo dice al docente al registrarse.
- Las contraseñas no se guardan tal cual: se guarda una huella con scrypt que no se puede revertir.
- La conexión por Wi-Fi no va cifrada (http). Use una red Wi-Fi de la escuela protegida con contraseña.
- Tras 5 intentos fallidos, la cuenta espera 5 minutos.
- El docente no vuelve a escribir su contraseña durante 7 días en su celular. La sesión de la dirección dura 8 horas.
- Si un docente olvida su contraseña, la dirección le da una temporal en *Docentes*. Al entrar con ella, el docente crea una propia.
- Si la dirección olvida la suya, en la computadora de la escuela: `python admin.py restablecer`
- Si un docente describe una posible situación de abuso o riesgo (antes o después de clase), la app no da consejos: le indica seguir el protocolo de la escuela. Además, el registro le aparece a la dirección en *Resumen*.
- Para escribir con la voz se usa el micrófono del teclado del celular. La app no graba audio.

## Respaldo

En *Ajustes → Descargar copia* la dirección obtiene una copia de toda la base de datos.
Guárdela en una USB una vez por semana, en un lugar seguro: contiene la actividad de todos los docentes.

Al actualizar desde una versión anterior, la base `escuela.db` se convierte sola. Antes de hacerlo, se guarda una copia como `escuela.respaldo-v1-*.db` o `escuela.respaldo-v2-*.db`.
Los docentes de la primera versión quedan sin contraseña hasta que la dirección les da una temporal.

## Archivos

| Archivo | Para qué sirve |
| --- | --- |
| `app.py` | Entrada, inicio de sesión y cuenta de la dirección |
| `Docente.py` | Pantallas del docente: antes de clase, después de clase y Mi avance |
| `Direccion.py` | Panel de la dirección |
| `Motor.py` | Prompts y llamadas al modelo de IA: dos rutas, micro-acción y bitácora |
| `Guias.py`, `guias/fichas.json` | Guías pedagógicas locales y su búsqueda |
| `BaseDatos.py` | Base de datos SQLite, cuentas, permisos, retos y avance |
| `Seguridad.py` | Contraseñas y sesiones |
| `Interfaz.py`, `estilo.css` | Aspecto visual: el cuaderno (lo que escribe el docente) y el pizarrón (lo que responde el coach) |
| `static/fuentes/` | Letras Andika y Kalam (licencia OFL), incluidas para funcionar sin internet |
| `admin.py` | Recuperar la cuenta de la dirección |
| `usb.py`, `preparar_usb.bat`, `instalar_sin_internet.bat` | Instalación desde una USB, sin internet |
| `.streamlit/config.toml` | Configuración para PC modesta y sin internet |

Para probar otro modelo: `set AULACOACH_MODELO=ministral-3:3b` (Windows) antes de `iniciar.bat`.

import getpass
import os
import sys

from dotenv import load_dotenv


def _app_dir():
    """
    Carpeta donde viven el .env y todo lo que el bot va guardando
    (respuestas aprendidas, lecciones bloqueadas, logs).

    Empaquetado como .exe (PyInstaller), `__file__` apunta a una carpeta
    TEMPORAL que se borra al cerrar: guardar ahí las respuestas aprendidas
    las perdería en cada ejecución. En el exe se usa la carpeta del propio
    ejecutable.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR = _app_dir()
ENV_FILE = os.path.join(APP_DIR, ".env")

_FIELDS = [
    ("FLUENCY_EMAIL", "Correo de Rosetta Stone", False),
    ("FLUENCY_PASSWORD", "Contraseña de Rosetta Stone (no se verá al escribir)", True),
    ("AI_API_KEY", "API key de build.nvidia.com (empieza por nvapi-)", False),
]


def _quote(value):
    """Entre comillas dobles y escapada: una contraseña con #, espacios o comillas no rompe el .env."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _first_run_setup(missing):
    """
    Pide por consola los datos que falten y los guarda en el .env.

    Pensado para el .exe: quien lo descarga no tiene por qué saber crear un
    archivo .env a mano. Solo se pregunta lo que falta, así un .env a medias
    se completa en vez de sobrescribirse.
    """
    print()
    print("Faltan datos para arrancar. Se guardarán en:")
    print(f"  {ENV_FILE}")
    print()

    # Un .env que no acaba en salto de línea pegaría la línea nueva a la
    # última que ya había, y las dos quedarían inservibles.
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "rb") as fh:
            content = fh.read()
        if content and not content.endswith(b"\n"):
            with open(ENV_FILE, "a", encoding="utf-8") as fh:
                fh.write("\n")

    for name, label, secret in _FIELDS:
        if name not in missing:
            continue
        value = ""
        while not value:
            try:
                # La contraseña va tal cual: podría acabar en espacio de verdad.
                value = getpass.getpass(f"{label}: ") if secret else input(f"{label}: ").strip()
            except EOFError:
                # En Windows, una entrada redirigida a NUL (ej. el Programador
                # de tareas) dice ser una consola pero no hay nadie que
                # escriba. Se sale sin más y el aviso de abajo ("Falta ...
                # en el archivo .env") explica qué hacer, en vez de un
                # EOFError críptico.
                print()
                return
        os.environ[name] = value
        with open(ENV_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={_quote(value)}\n")
    print()


# interpolate=False: una contraseña con "${...}" se tomaría como variable y se
# vaciaría. Aquí no se usa interpolación para nada.
load_dotenv(ENV_FILE, interpolate=False)

_missing = [name for name, _, _ in _FIELDS if not os.getenv(name)]
if _missing and sys.stdin is not None and sys.stdin.isatty():
    _first_run_setup(_missing)

EMAIL = os.getenv("FLUENCY_EMAIL")
PASSWORD = os.getenv("FLUENCY_PASSWORD")
AI_API_KEY = os.getenv("AI_API_KEY")

if not EMAIL:
    raise ValueError("Falta FLUENCY_EMAIL en el archivo .env")

if not PASSWORD:
    raise ValueError("Falta FLUENCY_PASSWORD en el archivo .env")

if not AI_API_KEY:
    raise ValueError("Falta AI_API_KEY en el archivo .env")

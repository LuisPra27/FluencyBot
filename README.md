# Fluency Bot

Bot de automatización desarrollado en Python que utiliza **Playwright** e **inteligencia artificial** para interactuar automáticamente con una plataforma de aprendizaje de idiomas.

## Objetivo

El objetivo del proyecto es crear un bot capaz de **detectar, interpretar y resolver automáticamente los ejercicios presentados por la plataforma mediante una inteligencia artificial**, para posteriormente introducir o seleccionar las respuestas correspondientes utilizando automatización del navegador.

La IA será el componente encargado de resolver los ejercicios. Playwright será el componente encargado de interactuar con la plataforma.

### Flujo principal

```text
┌──────────────────────────────┐
│      Plataforma educativa    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│          Playwright          │
│  Detecta y extrae ejercicio  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       Inteligencia Artificial│
│                              │
│   Analiza y RESUELVE         │
│       el ejercicio           │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│          Playwright          │
│                              │
│ Introduce/selecciona         │
│ la respuesta proporcionada   │
│ por la IA                    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       Siguiente ejercicio    │
└──────────────────────────────┘
```

## Funciones principales

El bot deberá ser capaz de:

* Iniciar sesión automáticamente.
* Acceder a las actividades.
* Detectar el ejercicio mostrado.
* Extraer texto, opciones, imágenes u otros elementos relevantes.
* Identificar el tipo de ejercicio.
* Enviar la información a una inteligencia artificial.
* **Permitir que la IA resuelva el ejercicio.**
* Recibir la respuesta generada por la IA.
* Interpretar la respuesta.
* Seleccionar la opción correspondiente.
* Escribir respuestas cuando sea necesario.
* Continuar automáticamente con el siguiente ejercicio.
* Detectar cuándo termina una actividad.
* Registrar errores durante el proceso.

## Arquitectura

El proyecto estará dividido en tres componentes principales.

### Browser Controller

Utiliza Playwright para controlar el navegador.

Responsabilidades:

```text
Abrir navegador
      ↓
Iniciar sesión
      ↓
Navegar
      ↓
Detectar ejercicio
      ↓
Extraer información
      ↓
Ejecutar respuesta
      ↓
Continuar
```

### AI Solver

Es el componente encargado de **resolver los ejercicios**.

Recibirá la información obtenida desde la página y determinará la respuesta.

Ejemplo:

```text
Ejercicio:
"She ____ to school every day."

Opciones:
1. go
2. goes
3. going
4. gone
```

La IA analizará el ejercicio y devolverá una respuesta estructurada:

```json
{
    "answer": "goes",
    "option": 2
}
```

El bot utilizará posteriormente esta respuesta para interactuar con la página.

### Controller

Coordina Playwright y la IA.

```text
Playwright
    │
    │ ejercicio
    ▼
Controller
    │
    │ ejercicio
    ▼
AI Solver
    │
    │ respuesta
    ▼
Controller
    │
    │ respuesta
    ▼
Playwright
```

## Tipos de ejercicios

El sistema deberá poder manejar diferentes tipos de actividades.

Entre ellos:

* Selección múltiple.
* Completar espacios.
* Traducción.
* Ordenamiento de palabras.
* Asociación de palabras.
* Selección de imágenes.
* Preguntas escritas.
* Ejercicios basados en audio.
* Ejercicios basados en texto.

Cada tipo de ejercicio podrá utilizar una estrategia de resolución e interacción diferente.

## Respuesta estructurada

La comunicación entre el bot y la IA deberá utilizar respuestas estructuradas para reducir errores.

Lo implementado hoy usa una respuesta estructurada por tipo (sin campo `"type"`, ya que `bot.apply_solution()` conoce el tipo por el ejercicio que se le pasó):

```json
// multiple_choice
{"answer": 3}

// cloze_dropdown (uno por espacio en blanco, en orden)
{"answers": [1, 2, 0]}

// matching
{"pairs": {"fuel cap": 4, "hinge": 3}}
```

Los ejemplos originales de `text_input` y `word_order` eran del diseño inicial; esos tipos de ejercicio (preguntas escritas, ordenar palabras) todavía no están mapeados — ver "Pendiente" abajo.

## Estructura del proyecto

```text
FluencyBot/
│
├── bot.py
├── ai.py
├── browser.py
├── config.py
├── requirements.txt
├── .env
├── .gitignore
├── blocked_lessons.json   # generado por el bot: lecciones ya confirmadas como bloqueadas
└── README.md
```

### `bot.py`

Punto de entrada principal.

Se encargará de coordinar todo el proceso:

```text
START
 ↓
Login
 ↓
Abrir actividad
 ↓
Detectar ejercicio
 ↓
Enviar ejercicio a IA
 ↓
Recibir solución
 ↓
Ejecutar solución
 ↓
Siguiente ejercicio
 ↓
Repetir
 ↓
FIN
```

### `browser.py`

Contiene todas las funciones de Playwright. Agrupadas por lo que hacen:

```python
# Sesión y navegación
open_browser(), login(), open_fluency_builder()
go_to_courses(), get_courses(), start_course(), get_course_title(), get_course_progress()
get_lessons(), start_lesson(), exit_lesson()

# Detección y extracción de ejercicios
get_current_exercise(), get_exercise_options(), get_cloze_text(), get_cloze_options()
get_choice_audio_data_uris()  # extrae audio real para opciones solo-audio

# Interacción por tipo de ejercicio
click_option(), select_cloze_option(), drag_matching_pair()
submit_answer(), get_feedback_state(), go_to_next_exercise()

# Pantallas no-ejercicio (informativas, de habla, paginadas)
has_speech_modal(), dismiss_speech_modal()
has_paginated_content(), advance_paginated_content()
```

### `ai.py`

Contendrá la integración con el modelo de inteligencia artificial.

Ejemplo conceptual:

```python
solve_exercise(exercise_data)
```

La función recibirá los datos del ejercicio y devolverá la solución.

### `config.py`

Gestionará la configuración del proyecto y las variables de entorno.

## Configuración

Las credenciales y claves API deberán almacenarse mediante variables de entorno.

Archivo `.env`:

```env
FLUENCY_EMAIL=tu_correo
FLUENCY_PASSWORD=tu_contraseña
AI_API_KEY=tu_api_key_de_build.nvidia.com
```

Nunca se deberán almacenar credenciales directamente dentro del código fuente.

## Instalación

Crear entorno virtual:

```powershell
python -m venv venv
```

Activarlo:

```powershell
.\venv\Scripts\Activate.ps1
```

Instalar dependencias:

```powershell
pip install -r requirements.txt
```

Instalar Chromium para Playwright:

```powershell
playwright install chromium
```

## Ejecución

```powershell
python bot.py
```

## Flujo de resolución

El funcionamiento completo esperado es:

```text
1. Abrir plataforma
        ↓
2. Iniciar sesión
        ↓
3. Acceder a actividad
        ↓
4. Detectar ejercicio
        ↓
5. Extraer contenido
        ↓
6. Identificar tipo de ejercicio
        ↓
7. Enviar ejercicio a IA
        ↓
8. IA analiza el ejercicio
        ↓
9. IA RESUELVE el ejercicio
        ↓
10. Recibir respuesta
        ↓
11. Validar formato
        ↓
12. Playwright ejecuta respuesta
        ↓
13. Enviar ejercicio
        ↓
14. Esperar siguiente ejercicio
        ↓
15. Repetir
```

## Manejo de errores

La plataforma puede modificar sus elementos HTML y selectores.

Por ejemplo:

```python
page.locator('[data-qa="SignInButton"]')
```

puede dejar de funcionar si cambia la estructura de la página.

Por ello, el proyecto deberá:

* Utilizar selectores robustos.
* Esperar correctamente los elementos.
* Comprobar que los elementos estén disponibles.
* Manejar `TimeoutError`.
* Registrar errores.
* Detectar cambios en el tipo de ejercicio.
* Evitar que un error individual cierre todo el proceso.

Ejemplo:

```python
locator = page.locator('[data-qa="SignInButton"]')

locator.wait_for(state="visible")
locator.click()
```

## Tecnologías

| Tecnología    | Función                                                    |
| ------------- | ----------------------------------------------------------- |
| Python        | Lenguaje principal                                          |
| Playwright    | Automatización del navegador                                |
| Chromium      | Navegador automatizado                                      |
| python-dotenv | Gestión de variables de entorno                              |
| openai (SDK)  | Cliente para la API de NVIDIA build (compatible con OpenAI)  |
| NVIDIA build  | `meta/muse-glimmer-30b` (texto + imágenes) y `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (audio) |

## Estado del proyecto

### Completado

* [x] Proyecto Python
* [x] Configuración inicial de Playwright
* [x] Apertura del navegador
* [x] Automatización inicial del login
* [x] Reorganización en módulos (`config.py`, `browser.py`, `ai.py`, `bot.py`)
* [x] Detección y extracción de ejercicios: `multiple_choice`, `matching`, `cloze_dropdown`, `ordering` ("Organización": arrastrar tarjetas a la secuencia correcta)
* [x] Interacción completa para los 4 tipos: `click_option`, `select_cloze_option`, `drag_matching_pair`, `reorder_items`
* [x] Detección de feedback (`get_feedback_state`: correcto/incorrecto) y avance (`go_to_next_exercise`)
* [x] Loop completo en `bot.py` (detectar → pedir solución a la IA → aplicar → enviar → avanzar), verificado de punta a punta contra la app real con una solución simulada
* [x] Reintento automático: hasta `MAX_ATTEMPTS` (3) intentos por ejercicio, pasándole a la IA las soluciones previas fallidas; si se agotan, pausa el bot en vez de cerrar el navegador de golpe
* [x] Integración real con IA: NVIDIA build API (compatible OpenAI SDK), modelo `meta/muse-glimmer-30b` (texto + visión, necesaria para `matching`). Verificado en vivo resolviendo un ejercicio real de punta a punta.
* [x] Navegación automática entre cursos y lecciones: `find_next_lesson()` recorre todos los cursos (`get_courses`/`start_course`) y elige la primera lección con actividades pendientes (`get_lessons`/`start_lesson`); `run_lesson()` resuelve toda la lección saltando pantallas informativas (Objetivos, Demostración, Vocabulario...) con el mismo botón "Omitir", y al terminar verifica contra el contador real de la plataforma (`LessonActivitiesCompletedText`) si de verdad se completó antes de pasar a la siguiente. Ya no hace falta ningún `input()` manual para arrancar.
* [x] Saltar ejercicios ya completados al "Reanudar": `find_next_lesson()` reporta cuántos ya estaban correctos y `run_lesson()` los pasa con "Omitir" sin llamar a la IA (en vez de volver a contestarlos).
* [x] Manejo de ejercicios de habla (no automatizables, requieren grabar audio real): `open_browser()` deniega el micrófono de antemano para que el sitio muestre su propio modal "Continuar sin voz" en vez del popup nativo; `run_lesson()` lo descarta, deja esas actividades pendientes para el usuario, y sigue con la próxima lección en vez de bloquearse (con protección contra bucle infinito si la misma lección se vuelve a topar con voz).
* [x] `_ask_json` en `ai.py` imprime el `reasoning_content` del modelo en consola (no solo la respuesta final), y `max_tokens` subido a 3000 tras ver preguntas que necesitaban más margen de razonamiento.
* [x] Persistencia entre corridas: `blocked_lessons.json` guarda qué lecciones ya se confirmaron bloqueadas (voz u otro motivo), para no re-verificarlas desde cero en cada reinicio.
* [x] `bot.py` nunca se detiene a esperar input manual: `main()` devuelve True/False y un wrapper en `__main__` reintenta automáticamente hasta `MAX_RESTARTS` (30) si algo falla (timeout, error de API, sesión expirada), sin perder progreso.
* [x] Fallos aislados por lección: un timeout/error dentro de una lección puntual la marca como bloqueada y sigue con la siguiente, en vez de tumbar toda la corrida repetidamente sin nunca registrar el problema.
* [x] **Soporte real de audio**: opciones de `multiple_choice` que son solo audio (sin texto) ya no se saltan — `get_choice_audio_data_uris()` en `browser.py` extrae el audio real (interceptando la petición de red vía `page.route()`, con reintentos porque el servidor de medios de Rosetta Stone a veces da 500 transitorio) y se lo manda a `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (el único de los dos modelos que entiende audio) para que "escuche" y responda. Verificado en vivo con una respuesta correcta real. El modelo de audio a veces alucina/degenera su respuesta; se maneja como intento fallido normal dentro del reintento existente, no como crash.
* [x] Corregido: la detección de "solo audio" tenía falsos positivos — varias variantes de "Prácticas de conversación" y "matching" con audio *opcional* (texto real + ícono de audio al lado) se estaban tratando como no-soportadas cuando sí eran resolubles por texto.
* [x] Paginación de Vocabulario/Explicación (`NavigateForwardButton`) en vez de "Omitir" (que las dejaba "Omitida" en vez de "Completa"), con tope de seguridad de 100 clics; y solo pagina de verdad en territorio nuevo (no en lo ya completado, para no re-paginar en cada "Reanudar").
* [x] Pantallas de "Demostración" (video): `skip_video()` reproduce el video real a 16x en vez de esperar su duración completa (simular el final con `currentTime`/eventos sintéticos no funciona, Rosetta lo marca "Omitida"); `can_advance()` evita re-intentar el salto una vez que Rosetta ya lo marcó "Completa".
* [x] Ejercicio `ordering` ("Organización"): `reorder_items()` arrastra las tarjetas (drag & drop nativo) hasta lograr el orden que pide la IA, re-leyendo el orden real tras cada arrastre en vez de asumir cómo reordena la librería al soltar.
* [x] Cuando no hay señal legible para resolver un ejercicio (audio que no se pudo capturar, en `multiple_choice` o `matching`) ya no se omite la actividad de una: se marca `"unsolvable"` y `ai.py` prueba una respuesta al azar sin gastar una llamada a la IA. `browser.is_answer_revealed()` detecta cuando Rosetta, tras un par de fallos, resalta ella misma la respuesta correcta ("Esta es la respuesta correcta.") y el bot avanza aprovechando eso en vez de seguir adivinando.
* [x] `bot.py` reconfigura `stdout`/`stderr` a UTF-8 al arrancar: la consola de Windows no siempre usa ese codepage por defecto, y un `print()` con un carácter fuera de él (tildes, `→`, etc.) tiraba el intento entero con `UnicodeEncodeError` en vez de solo verse mal.

### Pendiente

* [ ] Mapear tipos de ejercicio restantes (traducción, preguntas escritas, etc.) — al toparse con uno genuinamente sin nada interactuable, `run_lesson()` se detiene y avisa en vez de fallar en silencio
* [ ] El soporte de audio no es 100% confiable (servidor de medios y modelo omni son algo flaky) — funciona pero puede necesitar más de un intento
* [ ] Manejo avanzado de errores
* [ ] Sistema de logs
* [ ] Ejecución completa de actividades

## Objetivo final

El resultado esperado es un sistema completamente automatizado capaz de seguir el siguiente ciclo:

```text
DETECTAR
   ↓
INTERPRETAR
   ↓
RESOLVER CON IA
   ↓
RESPONDER
   ↓
CONTINUAR
```

La **inteligencia artificial será responsable de resolver los ejercicios**, mientras que **Playwright será responsable de ejecutar las respuestas dentro de la interfaz**.

El sistema continuará este proceso automáticamente hasta completar la actividad.

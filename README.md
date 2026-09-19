# Fluency Bot

Bot de automatización desarrollado en Python que utiliza **Playwright** e **inteligencia artificial** para interactuar automáticamente con una plataforma de aprendizaje de idiomas.

## Objetivo

El objetivo del proyecto es crear un bot capaz de **detectar, interpretar y resolver automáticamente los ejercicios presentados por la plataforma mediante una inteligencia artificial**, para posteriormente introducir o seleccionar las respuestas correspondientes utilizando automatización del navegador.

La IA será el componente encargado de resolver los ejercicios. Playwright será el componente encargado de interactuar con la plataforma.

### El criterio de éxito (lo que de verdad importa)

> **Todo tiene que quedar resuelto CORRECTAMENTE. Lo único que se puede
> dejar omitido son las actividades en las que hay que hablar.**

Esto no es un matiz: es el criterio contra el que se mide cualquier cambio
en este proyecto, y varias decisiones de diseño existen solo por él.

* **"Completado" NO es lo mismo que "correcto".** El contador de Rosetta
  ("X de Y actividades completadas") sube igual estés bien o mal, así que
  **nunca** sirve como señal de éxito. La única fuente de verdad es el
  estado por actividad del panel lateral: `Correcta` / `Completa` cuentan;
  `Omitida` y `Vuelva a intentarlo` no. Por eso `run_lesson()` dicta su
  veredicto leyendo el panel desde el resumen, no el contador.
* **Que Rosetta te enseñe la respuesta tampoco te da crédito.** Un
  ejercicio que llega a "Mostrar respuesta" queda mal igual. Por eso el bot
  aprende esa respuesta, reabre la actividad desde el panel y la responde
  de verdad (ver `known_answers.json`).
* **Omitir es la excepción, no el atajo.** Solo se aceptan sin resolver las
  actividades que exigen grabar la propia voz
  (`browser.SPEECH_ACTIVITY_TYPES`). Cualquier otro tipo que no se sepa
  resolver es un hueco a tapar, no un caso aceptable: un ejercicio de
  ESCUCHA (audio) sí se resuelve — se captura el audio y lo escucha el
  modelo de audio.
* **Un tipo desconocido se trata como resoluble.** Ante la duda, se
  reintenta en vez de darse por bloqueado; dar lecciones por perdidas de
  más es el error que llenó `blocked_lessons.json` de falsos positivos.
* **Nada de éxitos inventados.** Si no se pudo verificar el estado (por
  ejemplo, no se pudo abrir el resumen), el resultado es `failed`, no
  "completado".

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

// cloze_input ("Llene los espacios en blanco" con texto libre; uno por espacio, en orden)
{"answers": ["not"]}

// text_input ("Escriba la respuesta": texto libre, una respuesta por paso)
{"answer": "benefits"}

// matching
{"pairs": {"fuel cap": 4, "hinge": 3}}
```

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
├── blocked_lessons.json   # generado por el bot: {"curso::lección": {reason, failures, pending}}
├── known_answers.json     # generado por el bot: respuestas que Rosetta enseñó, por ejercicio
├── speech_activities.json # generado por el bot: actividades cuya pantalla exige hablar
├── logs/                  # generado por el bot: un bot_<fecha>_<hora>.log por corrida
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
get_cloze_input_text()                                  # blanks de texto libre, marcados ___N___
get_choice_audio_data_uris()                            # audio real de opciones solo-audio
get_matching_target_audio_data_uris()                   # audio real de targets solo-audio

# Interacción por tipo de ejercicio
click_option(), select_cloze_option(), fill_cloze_input(), write_answer(), drag_matching_pair()
submit_answer(), get_feedback_state(), wait_for_feedback(), go_to_next_exercise()
get_action_button_label()      # que dice el boton del pie, para no clickear a ciegas
exercise_is_locked()           # Rosetta ya cerro el ejercicio (campos deshabilitados)
is_answer_revealed(), can_show_answer(), get_revealed_answer(), get_exercise_key()

# Pantallas no-ejercicio (informativas, de habla, paginadas, video)
has_speech_modal(), dismiss_speech_modal(), has_read_aloud_activity()
has_paginated_content(), advance_paginated_content()
has_video(), video_is_watched(), skip_video()

# Panel lateral y resumen: el estado REAL de cada actividad
# (ver "El panel lateral y el resumen" más abajo)
go_to_lesson_summary()          # única pantalla donde TODAS tienen estado
get_activity_statuses()         # [{id, type, status, status_qa}, ...]
get_pending_activities()        # las que no están Correcta/Completa
get_flagged_activity_ids()      # las Omitida / Vuelva a intentarlo, clickeables
all_pending_are_speech()        # ¿la lección está bloqueada de verdad?
open_activity()                 # salta directo a una actividad, tocada o no
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
* [x] Pantallas de "Demostración" (video): `skip_video()` reproduce el video real a 16x en vez de esperar su duración completa (simular el final con `currentTime`/eventos sintéticos no funciona, Rosetta lo marca "Omitida"); `video_is_watched()` evita re-intentar el salto una vez que el video ya se vio de verdad. **Ojo:** originalmente esto usaba `can_advance()` (miraba si `[data-qa="SubmitButton"]` tenía el atributo `disabled`), pero ese botón es un `<div>` que NUNCA tiene `disabled` de verdad — el chequeo daba `True` siempre, así que `skip_video()` nunca se llegaba a llamar en la práctica y la Demostración quedaba "Omitida". Corregido revisando el estado real del `<video>` (`currentTime`/`duration`/`ended`) en vez del botón.
* [x] **Segundo bug real en el mismo mecanismo, encontrado y corregido esta sesión**: `video_is_watched()`/`skip_video()` aceptaban como "visto" tanto `v.ended` como "le faltan 3 segundos o menos" (margen pensado para no colgarse esperando una igualdad exacta de `currentTime` a 16x). Confirmado en vivo con capturas que ese margen NO es suficiente: Rosetta exige el final real y la Demostración quedaba "Omitida" igual (avanzando ~2.7s antes de que el video terminara de verdad). El evento `ended` del navegador es fiable sin importar la velocidad de reproducción, así que se quitó el margen por completo — ahora se exige `v.ended` estricto. Confirmado en vivo que con el fix la Demostración queda "Completa" (antes del fix, en la misma lección, quedaba "Omitida").
* [x] Ejercicio `ordering` ("Organización"): `reorder_items()` arrastra las tarjetas (drag & drop nativo) hasta lograr el orden que pide la IA, re-leyendo el orden real tras cada arrastre en vez de asumir cómo reordena la librería al soltar.
* [x] Cuando no hay señal legible para resolver un ejercicio (audio que no se pudo capturar, en `multiple_choice` o `matching`) ya no se omite la actividad de una: se marca `"unsolvable"` y `ai.py` prueba una respuesta al azar sin gastar una llamada a la IA. `browser.is_answer_revealed()` detecta cuando Rosetta, tras un par de fallos, resalta ella misma la respuesta correcta ("Esta es la respuesta correcta.") y el bot avanza aprovechando eso en vez de seguir adivinando.
* [x] `bot.py` reconfigura `stdout`/`stderr` a UTF-8 al arrancar: la consola de Windows no siempre usa ese codepage por defecto, y un `print()` con un carácter fuera de él (tildes, `→`, etc.) tiraba el intento entero con `UnicodeEncodeError` en vez de solo verse mal.
* [x] **Mecanismo de "revelación" de Rosetta, confirmado en vivo y aprovechado**: tras fallar un ejercicio unas cuantas veces, Rosetta misma resalta/aplica la respuesta correcta y muestra el aviso "Esta es la respuesta correcta.", dejando avanzar sin acertar de verdad. `browser.is_answer_revealed()` lo detecta. Confirmado que el momento exacto en que aparece VARÍA por tipo de ejercicio:
  - `multiple_choice`: aparece recién **después** de enviar el intento (junto con `feedback == "correct"`), aunque la opción que se haya clickeado haya sido la incorrecta.
  - `cloze_dropdown`: aparece **antes** de tocar nada, apenas se carga la pantalla de "Volver a intentar" — y en ese estado el dropdown ya NO es interactuable (intentar abrirlo cuelga 30s hasta timeout).
  - Por eso `resolve_current_exercise()` en `bot.py` revisa `is_answer_revealed()` en DOS puntos: al principio de cada intento (antes de pedirle nada a la IA o tocar cualquier control) Y después de enviar una respuesta. Verificado en vivo con capturas para ambos tipos.
  - No se probó todavía en `matching` ni en `ordering`, pero el mismo chequeo debería cubrirlos igual al ser genérico.
* [x] Gracias a lo anterior, cuando no hay señal legible para resolver un ejercicio (audio que no se pudo capturar, en `multiple_choice` o `matching`) ya no se omite la actividad de una: se marca `"unsolvable"` y `ai.py` prueba una respuesta al azar sin gastar una llamada a la IA, confiando en que la revelación lo termine resolviendo.
* [x] Corregido un crash en cascada: si el navegador se cierra inesperadamente (error real, o cierre manual), el intento de `main()` de guardar `error.png` para diagnosticar TAMBIÉN fallaba (el navegador ya no existe) y ese segundo fallo se escapaba sin capturar, tumbando todo el wrapper de reintentos de `__main__` en vez de solo reportar y reiniciar. `_try_save_error_screenshot()` en `bot.py` protege ambos pasos (leer `page.url` y la captura) con su propio try/except.
* [x] Instrumentación temporal de depuración: `bot.py` guarda una captura en `debug_omits/` cada vez que se omite una pantalla no reconocida genuinamente (NO las de video/Demostración, que tienen su propio manejo), para poder revisar visualmente qué se está saltando. Activo actualmente — ver "Pendiente" para el plan de quitarlo.
* [x] **Ejercicio `cloze_input` ("Llene los espacios en blanco" con texto libre)**: encontrado en vivo en "Manage Your Career (B1) :: The Perfect Job, Part II" — un `<input data-qa="ClozeInput">` inline dentro de la oración (sin opciones para elegir, a diferencia de `cloze_dropdown`). `browser.get_current_exercise()` lo detecta (`get_cloze_input_text()` marca cada blank como `___N___`, igual que hace `get_cloze_text()` para los dropdowns); `browser.fill_cloze_input()` escribe la respuesta; `bot.apply_solution()` tiene el caso `cloze_input`. Confirmado en vivo que tras "Volver a intentar" el input vuelve a quedar editable y vacío (mismo patrón de reset que los demás tipos).
* [x] **Corregido bug real de timing en el feedback**: confirmado en vivo que `cloze_input` tarda más de 1.5s en mostrar su feedback (a diferencia de `multiple_choice`/`matching`, casi instantáneos). La espera fija que usaba `resolve_current_exercise()` (`page.wait_for_timeout(1500)` antes de leer `get_feedback_state()`) hacía que el resultado se leyera como `None` mientras el envío seguía procesándose, y el reintento subsiguiente caía sobre una vista a medio actualizar (el siguiente intento de rellenar el input colgaba hasta el timeout de Playwright). Reemplazado por `browser.wait_for_feedback()`, que sondea (igual que `_wait_for_advance`) hasta que aparezca feedback reconocible o la respuesta sea revelada, en vez de una espera fija — se usa ahora para todos los tipos de ejercicio, no solo `cloze_input`.
* [x] **Detección explícita de "Lectura en voz alta"**: pantalla con pestañas "Leer"/"Escuchar"/"Hablar" (grabarse leyendo un texto en voz alta) — no automatizable, igual que las demás actividades de habla, pero a diferencia del modal inicial ("Continuar sin voz", una sola vez por sesión de navegador) esta pantalla aparece como una actividad más dentro de la lección sin disparar ningún modal. Antes caía en el camino genérico de "pantalla no reconocida" (se saltaba igual de bien, pero el mensaje de log no dejaba claro que era una omisión intencional de habla y no un hueco real de mapeo — confundía al usuario viendo el log en vivo). `browser.has_read_aloud_activity()` la detecta por texto ("Lectura en voz alta") y `run_lesson()` la salta con un mensaje explícito.
* [x] **Hallazgo importante sobre la "revelación" de Rosetta (corrige una suposición incorrecta de sesiones anteriores)**: confirmado en vivo con capturas que la revelación NO da crédito real. Se probó a propósito fallando un `matching` dos veces: Rosetta revela la pareja correcta (la deja puesta y arrastrable en el DOM), pero al hacer clic en Enviar sobre ese estado, el ítem queda marcado **"Vuelva a intentarlo" (incorrecto) para siempre** en el panel de la lección — el clic solo avanza a la siguiente actividad, no corrige la nota. El contador general "X de Y completadas" avanza iguel, pero el estado individual del ítem queda mal. Por eso, para cualquier tipo de ejercicio donde el contenido SÍ sea legible (aunque no haya opciones para elegir, como `cloze_input`), vale mucho más darle a la IA una oportunidad real de acertar dentro del límite de intentos de Rosetta (parece ser 2) que adivinar a ciegas y confiar en la revelación — por eso `cloze_input` pasó de `_blind_guess` a un solver real (`ai._solve_cloze_input`, ya no se marca `"unsolvable"`). La adivinanza ciega + revelación sigue siendo la única opción razonable para lo genuinamente ilegible (audio sin poder capturarse), donde no hay nada mejor que intentar.
* [x] **Mensaje corregido** en `run_lesson()`: la rama que salta actividades ya contadas por Rosetta al reanudar (`solved < already_completed`) decía "Ejercicio ya completado antes ... omitiendo sin llamar a la IA", dando a entender que esas actividades estaban bien resueltas. Falso: `already_completed` (el contador "X de Y" de Rosetta) cuenta CUALQUIER actividad ya atravesada, esté "Correcta" u "Omitida"/incorrecta. Confirmado en vivo: el usuario vio que las actividades 2 y 3 de "Résumés, Part II" decían "ya completado" en el log pero mostraban "Omitida" en el panel real de Rosetta. Mensaje corregido para no insinuar que "ya contado" significa "correcto" — pero esto por sí solo NO arreglaba el problema real (ver el siguiente punto, la solución de verdad).
* [x] **LA SOLUCIÓN DE VERDAD (parcial) — sí se puede re-intentar una actividad marcada "Vuelva a intentarlo"**: cuando el usuario cuestionó (con razón) que solo corregir el mensaje del log era esconder el problema en vez de arreglarlo, se investigó si de verdad no había forma de corregir una actividad ya mal marcada. Resultado, confirmado en vivo: **para ejercicios reales (matching, cloze_dropdown, cloze_input, etc.) marcados "Vuelva a intentarlo" (los fallaste), sí se puede**. Haciendo clic en el item del panel lateral de la lección, Rosetta vuelve a mostrar ese ejercicio interactivo, como si no se hubiera tocado. Probado de punta a punta: se reabrió una "Correspondencia" marcada "Vuelva a intentarlo", se resolvió con la IA real, y el panel pasó a **"Correcta"**.
  - Implementado en `bot.work_pending_activities()`, llamado en **varias rondas** (`MAX_RETRY_ROUNDS = 5`) al final de `run_lesson()` — no un solo intento, porque cada reapertura da un juego fresco de intentos reales antes de que Rosetta vuelva a revelar/rendirse.
  - Usa `browser.get_flagged_activity_ids()`, que lee el DOM real del panel lateral — más robusto que buscar por texto visible o posición. Ver abajo ("El panel lateral y el resumen") el mapa completo de sufijos de estado, confirmado volcando el DOM.
  - **Bug real encontrado y corregido**: la primera versión usaba `.first` sin registrar qué ya se había intentado — si un item no cambiaba de estado, `.first` seguía apuntando siempre al mismo, y el bucle lo reintentaba sin avanzar (confirmado en vivo: el usuario vio el bot yendo y viniendo entre los mismos dos ejercicios varios minutos). El siguiente intento (cortar toda la pasada al ver una URL repetida) tampoco servía: si el PRIMER item resultaba no arreglable, la función se rendía sin intentar los demás. La solución final usa los IDs estables de cada actividad, tomados una sola vez al principio, recorridos por ID (no por posición) — así cada uno se intenta exactamente una vez sin importar qué se arregle en el camino.
  - Las actividades genuinamente no automatizables (habla grabada, "Lectura en voz alta") se vuelven a omitir con el mismo criterio de siempre — eso es lo único que el usuario aceptó que quede sin resolver.
* [x] **Conclusión errónea, retractada: NO es una limitación de Rosetta que una Demostración "Omitida" no se pueda reabrir.** Durante cuatro intentos en vivo el video nunca volvía a mostrarse al reabrirlo, y se dio por confirmado que Rosetta trataba "omitir un video sin tocarlo" como una decisión permanente. El usuario rechazó esa conclusión ("no es del rosetta stone, yo sí lo puedo hacer, es una limitación del bot o tuya") y tenía razón. Depurando paso a paso con capturas tras CADA acción apareció la causa real: **el modal de habla ya estaba abierto ANTES del clic en el panel lateral**, y un modal abierto bloquea toda interacción con la página de fondo — el clic no hacía nada (ni con `force=True`) y la URL nunca cambiaba. El bot descartaba el modal *después* del clic, cuando ya era tarde. Corregido en `work_pending_activities()`: se descarta el modal ANTES de hacer clic, igual que haría una persona. **Lección de método**: cuatro fallos idénticos no prueban que la plataforma no lo permita; prueban que la hipótesis sobre la causa no había cambiado en cuatro intentos.
* [x] **Bug real encontrado por el usuario: en `cloze_input` el bot escribía la respuesta pero nunca la enviaba**. Causa: `fill_cloze_input()` hacía `.fill(text)` y `resolve_current_exercise()` llamaba a `submit_answer()` inmediatamente después, sin ninguna espera. El botón de enviar es un `<div>` (no un `<button disabled>` real), así que Playwright no espera a que React registre el cambio antes de permitir el clic — el clic ocurría, pero podía caer como no-op silencioso justo antes de que el campo quedara realmente marcado como lleno, dejando el texto visible pero sin enviar. Corregido en dos frentes: `fill_cloze_input()` ahora espera un poco tras escribir, y `resolve_current_exercise()` reintenta el clic de enviar una vez si no aparece feedback ni revelación (red de seguridad general para cualquier tipo, no solo `cloze_input`, ante el mismo patrón de "clic silenciosamente ignorado").
* [x] **Bug crítico externo encontrado y corregido: el modelo principal de IA dejó de funcionar de un día para otro**: `meta/muse-glimmer-30b` empezó a devolver `404 NotFoundError` en CUALQUIER llamada (confirmado en vivo con una prueba directa a la API, fuera del bot). Ojo: el modelo seguía apareciendo listado en `_client.models.list()` — solo la inferencia real fallaba, así que "sigue en el catálogo" no significa "sigue funcionando". Esto tumbó una corrida completa en cascada: cada ejercicio que necesitaba IA real fallaba 3/3 intentos con el mismo error y la lección quedaba bloqueada, lección tras lección, sin que fuera un problema de contenido — exactamente el tipo de "se salta algo indebido" que más le preocupa al usuario, y esta vez la causa era completamente externa al código. `AUDIO_MODEL` (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`) seguía funcionando bien, lo que ayudó a aislar que era el modelo específico y no la cuenta/clave API. Reemplazado por `meta/llama-3.2-11b-vision-instruct` (confirmado en vivo que funciona con texto Y con imágenes reales, y que resuelve correctamente el ejercicio exacto que había fallado). Se limpiaron de `blocked_lessons.json` las lecciones bloqueadas por este bug durante la corrida afectada (no eran bloqueos legítimos de habla).

* [x] **`blocked_lessons.json` dejó de ser una lista plana y permanente.** Antes, cualquier resultado que no fuera "completado" —una actividad de voz, un ejercicio que la IA no supo, o un simple timeout de navegación— metía la lección en el mismo archivo y la excluía para siempre, sin guardar el motivo. Eso lo convirtió en la cicatriz de todos los bugs pasados: durante el apagón de `muse-glimmer-30b` cada lección intentada quedó marcada, y ahí siguieron decenas que el bot sí puede hacer. Caso concreto que lo prueba: `Manage Your Career (B1)::The Perfect Job, Part I` estaba en la lista, y al inspeccionarla resultó estar en 16/17 con un único pendiente de tipo "Escriba la respuesta" — ni siquiera de voz. Ahora el archivo guarda `{"reason", "failures", "pending"}` por lección: solo `reason: "speech"` es definitivo, y un fallo de otro tipo se reintenta hasta `MAX_LESSON_FAILURES = 3` corridas antes de darse por perdido. El formato viejo se migra al leerlo, tratando las entradas sin motivo como revalidables.
* [x] **El veredicto de una lección ya no sale del contador.** `run_lesson()` termina yendo al resumen y leyendo `browser.get_pending_activities()`: devuelve `"completed"` si no queda nada, `"speech_blocked"` si todo lo pendiente es de voz (`browser.SPEECH_ACTIVITY_TYPES`), y `"failed"` si queda algo que no es de voz — con la lista de tipos pendientes en el log, para saber QUÉ faltó y no solo que faltó algo. Los tipos desconocidos cuentan como resolubles a propósito: dar una lección por bloqueada de más es justo el error que llenó el archivo de falsos positivos.
* [x] **Las rondas de reintento se deciden contando pendientes reales**, no por lo que devuelve `work_pending_activities()` (que solo cuenta ejercicios resueltos): una ronda que arreglaba únicamente un video o un Vocabulario devolvía 0 y cortaba las rondas de más.
* [x] **Un fallo al reabrir una actividad ya no tumba la corrida**: el `data-qa` del hijo de estado cambia en cuanto cambia el estado, así que un item ya inexistente hacía fallar el clic y el `force=True` de respaldo, y esa excepción se escapaba hasta el handler genérico de `main()`. Ahora se captura por actividad y se sigue con la siguiente.
* [x] **Un ejercicio que la IA no resuelve ya no abandona la lección al instante**: antes había un `return "failed"` que salía de la lección ahí mismo, tirando la segunda oportunidad que dan las rondas de reintento (reabrir desde el panel lateral da un juego fresco de intentos). Ahora corta el recorrido lineal pero pasa igual por los reintentos.

* [x] **Saltar directo a lo pendiente en vez de recorrer la lección entera.** "Reanudar" siempre reinicia desde el paso 1, así que arreglar la última actividad de una lección de 42 costaba pasar de largo por las 41 anteriores, una por una. Ahora `run_lesson()` reserva el recorrido lineal para las lecciones nuevas (`already_completed == 0`); si ya está empezada va al resumen y trabaja solo lo que falta con `work_pending_activities()`. Confirmado en vivo: "The Perfect Job, Part I" pasó de 16/17 a **17/17 en 61 segundos**, con todas las actividades en Correcta/Completa.
* [x] **`browser.open_activity()` abre cualquier actividad, tocada o no.** Las que ya tienen estado se abren por su hijo de estado; las **nunca tocadas no tienen hijo de estado**, y para esas se clickea el contenedor `activity_<id>`. Confirmado en vivo en una lección 0/13: clickear el contenedor de una "Explicación" jamás abierta llevó de `…/summary` a `…/8/1`. Eso es lo que hace posible saltarse el recorrido lineal.
* [x] **No hacer clics a ciegas en el botón del pie.** Rosetta reutiliza el mismo `data-qa="SubmitButton"` para todo y solo le cambia el texto (`data-qa-button-text`): "Omitir" / "Revisar respuesta" / "Volver a intentar" / "Próxima actividad". La red de seguridad que re-enviaba al no ver feedback, y el clic de "Volver a intentar", se hacían sin mirar qué decía el botón — y si el envío anterior sí había funcionado, ese clic de más **avanzaba de paso**. Confirmado en vivo: el bot saltó del paso 1 al paso 4 de una "Escriba la respuesta", dejando dos preguntas sin responder. Ahora se comprueba la etiqueta (y que la URL no haya cambiado) antes de cada clic.
* [x] **`browser.exercise_is_locked()`**: tras agotar los intentos, Rosetta deja los campos `disabled` sin mostrar el aviso que busca `is_answer_revealed()`. Escribir ahí se colgaba 30s esperando a que el campo se habilitara, y encima gastaba una llamada a la IA. Ahora se detecta antes de intentar nada y simplemente se avanza.
* [x] **`_format_previous_attempts()` estaba en español** mientras el resto del prompt está en inglés, y los modelos chicos lo ignoraban: confirmado en vivo que la IA devolvió **la misma respuesta equivocada tres veces seguidas**, gastando los tres intentos en una sola idea. Reescrito en inglés y en tono imperativo.

* [x] **Bucle infinito por el contador desincronizado de Rosetta.** Confirmado en vivo: el contador de una lección se queda en "16 de 17" aunque el panel lateral muestre las 17 actividades en Correcta/Completa. Como `find_next_lesson()` filtra por ese contador, elegía la misma lección una y otra vez — entrar, no encontrar nada pendiente, salir, repetir. Dos arreglos: (1) `main()` agrega la clave a `skip_keys` ANTES de intentar la lección, así ninguna se intenta más de una vez por corrida pase lo que pase; (2) al terminar completa se relee el contador con `_counter_still_lags()` y, si sigue desfasado, se guarda con `reason: "completed"` para no volver a entrar en futuras corridas. El panel lateral es la fuente de verdad, el contador no.
* [x] **Un fallo al abrir el resumen se reportaba como lección completada.** `run_lesson()` dejaba `pending = []` cuando `go_to_lesson_summary()` fallaba, y luego `if not pending` lo interpretaba como "no queda nada". Ahora se distingue "no hay pendientes" de "no se pudo mirar": sin verificación devuelve `"failed"`.

* [x] **Log de cada corrida en `logs/bot_<fecha>_<hora>.log`.** Copia de TODO lo que sale por consola —mensajes del bot, razonamiento de la IA y tracebacks de errores— con la hora al principio de cada línea (solo en el archivo; la consola se ve igual). Se hace duplicando stdout/stderr (`bot._Tee`), no cambiando cada `print()`, para que no se escape nada. Se vacía al disco en cada escritura: con la salida en buffer, detener el bot a mano perdía el log entero justo cuando más falta hacía. Solo se activa al ejecutar `bot.py`, no al importarlo, para que los scripts de prueba no vayan dejando logs.

### Lo que destapó correr el bot leyendo su log (2026-09-19)

* [x] **"Lectura en voz alta" en el panel lateral hacía omitir TODAS las actividades de la lección.** `has_read_aloud_activity()` buscaba ese texto en toda la página, y también es el nombre de otra actividad en el panel lateral. En una opción múltiple normal devolvía True (confirmado con el DOM real), y `work_pending_activities()` lo mira antes que el ejercicio. Era la causa principal de las lecciones bloqueadas con pendientes que el bot sí sabe resolver. Ahora ignora el panel lateral.
* [x] **El contador de fallos contaba reinicios, no intentos.** Tras cada caída, `main()` arrancaba de cero, volvía a entrar a todas las lecciones `failed` y les sumaba un fallo: 39 de 42 llegaron a `failures=3` y quedaron bloqueadas para siempre. Ahora hay memoria de sesión (`_SESSION_ATTEMPTED`) que sobrevive a los reinicios, un intento que aprendió respuestas no cuenta como fallo, y una lección con respuestas guardadas sin usar nunca se bloquea.
* [x] **Buscar la siguiente lección recorría todos los cursos desde el primero** (~4 s por curso, más de un minuto por lección). Ahora empieza por el curso de la última (`_SESSION_COURSE_HINT`): ~9 s.
* [x] **La captura de audio no funcionaba NUNCA.** El audio ya no se sirve desde `MediumHandler.ashx` sino desde `resources.rosettastone.com/rs3/content/LotusAssets/data/<hash>` (MP3, `application/octet-stream`). El bot solo interceptaba la ruta vieja: esperaba 8 s por botón, se rendía (~35 s por ejercicio) y la IA respondía a ciegas. Ahora intercepta la ruta nueva (interceptar además desactiva la caché, así cada clic se ve), descarga el clip entero y deduce el formato por sus primeros bytes: 0,7 s, y el modelo de audio escucha de verdad (identificó "Land/Hand/Planned/Sand" y razonó el grupo consonántico).
* [x] **Rosetta baraja las opciones de audio en cada apertura.** Tres respuestas guardadas seguidas ("la opción 2") fallaron al reabrir, y cada revelación daba otra posición. La URL de cada clip es un hash de su contenido, así que ahora se guarda `answer_audio_id` y al reabrir se busca en qué posición quedó ese clip (`bot._locate_remembered`).
* [x] **`ordering` con listas largas no llegaba nunca al orden pedido.** Con la ventana de 720 px, el sexto ítem iba de y=691 a y=773: todo arrastre desde o hacia él apuntaba fuera de pantalla. Además, soltar en el centro del destino hacía caer una posición de más al bajar. Ahora se agranda la ventana lo justo mientras se reordena y se suelta junto al borde según la dirección: 6 ítems en 2,3 s (antes: 25 s oscilando sin llegar).
* [x] **Un error en UNA actividad tiraba la lección entera**, y tras un timeout la recuperación iba a "Mis cursos" desde dentro de la lección (ese enlace ahí no existe) y provocaba la caída siguiente. Ahora el error se queda en la actividad y se sale de la lección antes de navegar.
* [x] **Cada omisión deja su motivo en el log**; antes había ramas que avanzaban sin resolver en silencio.
* [x] La IA daba 2 respuestas para 1 hueco y permutaciones de 5 para 6 ítems; ahora el prompt le da el número exacto y el bot solo rellena los huecos que existen.

### Tipos de ejercicio del curso "Talking with Clients" (mapeados en vivo)

Ninguno se reconocía y todas sus actividades quedaban "Omitida" para siempre.

| tipo | cómo se ve | cómo se responde | revelación |
| --- | --- | --- | --- |
| `cloze_drag` | huecos `ClozeDropTarget` + banco de palabras `DragDropText` | **arrastrando** cada palabra a su hueco (un clic no hace nada) | cada hueco queda con su palabra |
| `sentence_build` | palabras sueltas `SBDItem` + zona `TopDropArea` | **un clic** en cada palabra la añade al final de la oración | la oración correcta queda arriba |
| `matching_audio_options` | destinos con texto + clips `DragDropAudio` para arrastrar | arrastrando cada clip; el modelo de audio decide las parejas | cada destino queda con su clip (se identifica escuchándolo) |
| `text_rewrite` | ejemplo resuelto + varios `<textarea>` sin `data-qa` en `inputContainer` | una frase por campo, siguiendo el patrón del ejemplo | los campos quedan con la respuesta |
| Documento (no es un ejercicio) | imagen de un documento en `PageImageContainer`, con su propia barra | **desplazarlo hasta el final**: el botón pasa de "Omitir" a "Próxima actividad" y al pulsarlo queda Completa | — |

* **Con un hueco vacío el botón sigue diciendo "Omitir", y pulsarlo SALTA la actividad** (confirmado en vivo). Por eso `resolve_current_exercise()` nunca pulsa el botón si tras aplicar la respuesta sigue en "Omitir": significa que la respuesta no quedó puesta. Comprobado que en opción múltiple el botón sí pasa a "Revisar respuesta" al elegir, así que la regla vale para todos los tipos.
* **Actividades de voz con nombre de tipo engañoso.** "Llene los espacios en blanco" puede ser "Seleccione la mejor respuesta y diga la oración completa", y "Prácticas de conversación" es igual: tienen botón de micrófono (`SpeechButton`) y, tras elegir una opción, el botón sigue en "Omitir" — no se puede enviar sin hablar. `browser.requires_speech()` las reconoce por el micrófono y sus ids se guardan en `speech_activities.json`, para que la lección pueda darse por bloqueada por voz aunque el tipo no lo diga.
* Si un ejercicio no avanza y no se aprendió nada, no se insiste en la misma pasada: antes se reintentó 12 veces seguidas la misma pantalla, gastando una llamada a la IA cada vez.
* `browser.fit_exercise_in_viewport()`: cualquier arrastre necesita que todo el ejercicio quepa en pantalla; con 720 px el tercer hueco de un `cloze_drag` quedaba fuera, igual que el sexto ítem de un `ordering`.

Verificado en vivo: "The Welcome Desk" pasó de no reconocer ninguna actividad a quedar resuelta salvo la voz en 58 s, y "Preparing for an Interview, Part II" al 100% (`matching_audio_options` correcto al primer intento).

### El botón del pie y la revelación de la respuesta

Rosetta usa un único `data-qa="SubmitButton"` para todo y solo le cambia el
texto, que lleva en `data-qa-button-text`. Secuencia real, confirmada
fallando un ejercicio a propósito y volcando el DOM en cada paso:

| estado | botón | `data-qa` del feedback |
| --- | --- | --- |
| nada respondido | "Omitir" | — |
| tras fallar 1 vez | "Volver a intentar" | `IncorrectFeedback` |
| tras fallar 2 veces | **"Mostrar respuesta"** | `IncorrectFeedback` |
| tras pulsarlo | "Próxima actividad" | `ShowAnswerFeedback` |

* **Son solo 2 intentos reales, no 3.** `MAX_ATTEMPTS = 3` nunca se agota:
  al tercero Rosetta ya solo ofrece enseñar la respuesta.
* **Bug real que esto destapó**: en el estado revelado Rosetta pinta
  `FeedbackCorrectIcon` — el MISMO icono verde que cuando aciertas de
  verdad. `get_feedback_state()` lo leía y devolvía `"correct"`, así que el
  bot daba por resuelto un ejercicio que en realidad había fallado. Ahora
  se mira `ShowAnswerFeedback` primero y se devuelve `"revealed"`.
**Dónde está la respuesta correcta, por tipo.** Se volcó el DOM revelado de
cada tipo por separado, fallando un ejercicio a propósito hasta llegar a
"Mostrar respuesta". El hallazgo clave: **salvo en `multiple_choice`,
Rosetta escribe la respuesta correcta directamente en los propios
controles**, así que leerla es trivial.

| tipo | dónde queda la respuesta | qué guarda `get_revealed_answer()` |
| --- | --- | --- |
| `multiple_choice` | la opción correcta recibe una clase distinta a la del resto | `{"answer": <n>}` (1-based, de `data-qa-choice`) |
| `text_input` | el `<textarea data-qa="TextInput">` pasa a contenerla | `{"answer": "experience"}` |
| `cloze_input` | cada `[data-qa="ClozeInput"]` queda con su texto | `{"answers": ["power"]}` |
| `cloze_dropdown` | cada `ClozeDropdown_<n>` queda con su opción elegida | `{"answers": ["out", "were", ...]}` (texto, no índice) |
| `matching` | cada palabra queda colocada en su destino correcto | `{"pairs": {"<palabra>": <destino>}}` |
| `ordering` | los ítems quedan reordenados correctamente | `{"order": [...]}` |

Los seis extractores están probados contra el DOM real volcado de su
propio tipo, no por parecido con otro.

* En `cloze_dropdown` se guarda el **texto** de la opción, no su índice:
  `select_cloze_option()` acepta ambos y el texto no depende del orden del
  menú.
* En `multiple_choice` los nombres de clase son hashes generados
  (`css-1jr9iaz-RadioButtonDiv`) que cambian entre despliegues, así que
  **no se busca una clase concreta**: se busca la única que se diferencia
  de la mayoría. Ojo: la opción que marcaste MAL también tiene clase
  propia, así que la lectura solo vale con `ShowAnswerFeedback` en
  pantalla — hay una guarda explícita, porque sin ella la función devolvía
  la respuesta equivocada (lo atrapó un test contra el DOM volcado).
* En `matching` se exige que TODOS los destinos tengan palabra colocada:
  una lectura incompleta dejaría el ejercicio mal igual al aplicarla.

* [x] **La ronda de reintentos que APRENDE ya no se desperdicia.** El bucle de `run_lesson()` decidía si valía otra pasada contando los pendientes, y una pasada en la que la IA falla y Rosetta enseña la respuesta **no baja ese contador** (el ejercicio sigue mal) — aunque es la pasada más valiosa, porque deja la respuesta guardada. Cortaba justo ahí y el aprendizaje no se usaba hasta la corrida siguiente. Ahora la condición de corte también mira si se aprendió algo nuevo, así la pasada que aprende y la que aplica ocurren en la MISMA corrida.
* [x] **Memoria de las respuestas que Rosetta enseña (`known_answers.json`).** Confirmado desde hace tiempo que la revelación NO da crédito: un ejercicio que llega a "Mostrar respuesta" queda mal igual. La única forma de arreglarlo es reabrir la actividad desde el panel lateral — pero ahí la IA volvía a adivinar a ciegas con los mismos dos intentos, así que lo más probable era fallar otra vez. Ahora el ciclo es: (1) ¿hay respuesta guardada de este ejercicio? se aplica directo, sin gastar IA; (2) si no, se le pregunta a la IA; (3) agotados los intentos se pulsa "Mostrar respuesta" **a propósito**, se lee y se guarda, indexada por `browser.get_exercise_key()` (la ruta del ejercicio dentro del curso, estable entre reaperturas); (4) el ejercicio queda mal en esa pasada, pero la siguiente lo responde de memoria; (5) una vez correcto, la respuesta se borra para no acumular basura. Cubre los seis tipos (ver la tabla de arriba), cada uno probado contra el DOM real volcado de su propio tipo.

### El panel lateral y el resumen (confirmado volcando el DOM real)

Cada actividad de la lección es un contenedor `data-qa="activity_<id>"` con
un hijo cuyo `data-qa` es ese mismo id **más un sufijo que cambia según el
estado** — por eso no hay que asumir un sufijo fijo:

| sufijo del hijo | texto visible | qué significa |
| --- | --- | --- |
| `_completed` | "Completa" | contenido no evaluado ya visto (Demostración, Vocabulario, Explicación) |
| `_correctly_completed` | "Correcta" | ejercicio evaluado respondido bien |
| `_skipped` | "Omitida" | se pasó por encima sin hacerla |

Dos items del panel no son actividades: `activity_objectives` ("Objetivos
de la lección") y `activity_summary` ("Resumen de la lección").

Hechos que hacen que `browser.go_to_lesson_summary()` sea el punto de
lectura correcto:

* **Parado en una actividad, esa actividad no tiene hijo de estado.** Se
  confirmó con el mismo caso visto desde dos pantallas: estando en ella
  salía sin estado, y desde el resumen la misma salía `_skipped`/"Omitida".
  Leer los pendientes desde cualquier otra pantalla se salta justo la que
  estás viendo. En el resumen estás parado en `activity_summary`, así que
  todas las actividades reales sí muestran su estado.
* **`activity_summary` es clickeable y estable** (no depende del idioma ni
  de la posición); lleva a `…/<lección>/summary`.
* **El panel central del resumen lista solo lo que falta**: en una lección
  16/17, `data-qa="step_content"` contenía exactamente un item ("Escriba la
  respuesta" / "Omitida"). Útil como confirmación visual, pero el panel
  lateral es mejor fuente porque además trae el id clickeable de cada
  actividad; el panel central no.
* **"Omitida" NO cuenta para el contador**: 3 "Completa" + 13 "Correcta" =
  16 de 17, y la que faltaba era la "Omitida". Distinto de "Vuelva a
  intentarlo", que sí cuenta aunque esté mal — por eso el contador nunca
  sirve como veredicto y `run_lesson()` lee el panel lateral en su lugar.

### Pendiente

* [ ] **PRÓXIMO PASO CONCRETO — corrida real de verificación completa**: con `cloze_input` resuelto con IA real, el bug de `video_is_watched()` corregido, `work_pending_activities()` reintentando de verdad lo que quede "Omitida"/"Vuelva a intentarlo", y el modelo de IA principal reemplazado (ver el hallazgo del 404), relanzar una corrida completa real (`python bot.py`) de punta a punta con `python -u` (salida sin buffer, necesario para poder leer el log en vivo — con buffer normal no se ve nada hasta que el proceso termina). Revisar que no se omita nada salvo audio/habla, y que `work_pending_activities()` efectivamente suba el número de "Correcta" en el panel al final de cada lección.
* [ ] **Límite real de reintentos de Rosetta, confirmado en vivo**: Rosetta revela la respuesta y da por perdido el ejercicio tras solo **2** intentos fallidos (no 3) — `MAX_ATTEMPTS = 3` en `bot.py` rara vez llega a usarse completo porque `is_answer_revealed()` ya corta antes en el intento 3. Ya no es tan grave como se pensó al principio (ver `work_pending_activities()`: si falla, se puede re-intentar de verdad al final de la lección), pero sigue limitando cuántos intentos reales tiene la IA antes de la revelación.
* [ ] **`matching` con audio puro ahora se resuelve de verdad, no se adivina** (implementado, falta confirmar en vivo) — el usuario aclaró que lo ÚNICO omitible es grabar la propia voz; un ejercicio de escucha (aunque sea audio) SÍ se puede resolver. `browser.get_matching_target_audio_data_uris()` captura el audio real de cada target (mismo patrón que `get_choice_audio_data_uris()` para `multiple_choice`) y `ai._solve_matching_audio()` usa `AUDIO_MODEL` para emparejar de verdad. Solo cae en `_blind_guess` si la captura de audio falla técnicamente (ej. servidor de medios caído), no como estrategia por defecto. **Aún no probado en vivo** — implementado por razonamiento/paridad con el patrón ya confirmado de `multiple_choice` de audio, pendiente de verificar con un caso real.
* [ ] `work_pending_activities()` se probó en vivo contra `matching` (texto) y Demostración (video), ambos confirmados arreglando el estado a "Correcta"/"Completa". Falta confirmar con `cloze_dropdown`, `cloze_input` y el nuevo `matching` de audio real, y con lecciones que tengan muchos ítems marcados a la vez (ya se corrigió un bug de bucle infinito encontrado en esa situación, ver "Completado").
* [x] **Tipo `text_input` ("Escriba la respuesta") mapeado y confirmado en vivo** — era el pendiente más viejo del proyecto (`browser.write_answer()` llevaba desde el principio como `NotImplementedError`). Es un `<textarea data-qa="TextInput">` de texto libre, con la pregunta en `WritingPracticeTopic-<n>`, a veces una imagen de apoyo, y una pista de longitud entre paréntesis ("(7 caracteres)") que se le pasa a la IA. **Es una actividad de VARIOS pasos**: el pie dice "1 de 4 pasos" y cada pregunta es una pantalla aparte (`…/11/1` … `…/11/4`), con 2 intentos cada una antes de que Rosetta muestre la respuesta; solo se pasa a la siguiente al acertar o agotar los intentos. Por eso `bot._work_single_activity()` sigue trabajando mientras el índice de actividad de la URL no cambie, en vez de resolver una pantalla y darse por satisfecho.
* [ ] **Verificar en vivo la lógica nueva de bloqueo.** Está probada contra el DOM real volcado (los estados, los pendientes y la decisión `all_pending_are_speech()` se validaron sobre `dom_01_sidebar_resumen.html` fuera de línea) y contra el estado en disco (migración del formato viejo, `speech` definitivo, tope de `failures`), pero **no se ha corrido de punta a punta contra Rosetta**. Lo que falta confirmar: que `go_to_lesson_summary()` funcione también desde mitad de una lección con el modal de habla de por medio, y que una lección resuelta se quite sola de `blocked_lessons.json`.
* [ ] **`SPEECH_ACTIVITY_TYPES` está incompleta a propósito.** Solo se confirmó "Lectura en voz alta" en vivo; "Pronunciación", "Hablar" y "Habla" están puestas por suposición. Cualquier tipo que no esté en la lista se trata como resoluble (se reintenta), que es el lado seguro del error: si aparece un tipo de voz con otro nombre, la lección se reintentará 3 veces antes de bloquearse en vez de bloquearse al primer intento. Conviene ir confirmando los nombres reales según aparezcan en el log de pendientes.
* [ ] **Una lección que Rosetta cuenta como 100% pero tiene actividades "Vuelva a intentarlo" no se vuelve a visitar**: `find_next_lesson()` filtra por `completed < total`, y "Vuelva a intentarlo" SÍ cuenta para ese contador (a diferencia de "Omitida"). Habría que recorrer también las lecciones al 100% y mirar su resumen para detectarlas.
* [ ] Quitar (o dejar, a discreción) la instrumentación temporal `_debug_screenshot_omit` en `bot.py` una vez ya no se necesite revisar capturas — no rompe nada si se deja, solo genera archivos en `debug_omits/`.
* [ ] Mapear otros tipos de ejercicio que puedan aparecer más adelante (traducción, etc.) — al toparse con uno genuinamente sin nada interactuable, `run_lesson()` se detiene y avisa en vez de fallar en silencio
* [ ] El soporte de audio no es 100% confiable (servidor de medios y modelo omni son algo flaky) — funciona pero puede necesitar más de un intento
* [ ] Manejo avanzado de errores
* [ ] Sistema de logs
* [ ] Ejecución completa de actividades

## Estado de la sesión anterior (contexto para retomar)

**Lo que el usuario pidió como último paso** (aún no completado del todo):
correr una sesión real del bot (`python bot.py`) con `blocked_lessons.json`
vacío, y verificar con capturas de pantalla que NO se omita nada salvo las
actividades que requieren grabar audio/voz.

**Qué se hizo en esta sesión** (dos hallazgos importantes que corrigen
suposiciones de sesiones anteriores):

1. Se investigó y mapeó `cloze_input` ("Llene los espacios en blanco" con
   texto libre) — ver "Completado".
2. **El usuario notó en vivo, viendo la corrida, que un ejercicio de
   `matching` con audio quedaba "Vuelva a intentarlo" (rojo) en el panel
   incluso después de que el bot "avanzara" tras la revelación de Rosetta.**
   Se investigó a fondo y se confirmó con capturas: la revelación de
   Rosetta NO da crédito real, solo dice "date por vencido y sigue" — el
   ítem queda marcado incorrecto para siempre aunque el contador general de
   la lección progrese. Por eso `cloze_input` se cambió de adivinanza ciega
   a un solver real con IA (si el contenido es legible, vale mucho más
   intentarlo de verdad que confiar en la revelación). El matching de audio
   puro sigue sin señal legible y sigue sin poder resolverse de verdad (ver
   "Pendiente").
3. El usuario también notó que el video de "Demostración" avanzaba antes de
   que se viera el check de "Completa". Se confirmó con capturas: el margen
   de "le faltan 3 segundos" que usaba `video_is_watched()` no bastaba —
   Rosetta exige el final real (`v.ended`). Corregido quitando el margen.
4. Se corrigió un bug real de timing en `cloze_input`: su feedback tarda más
   de 1.5s en aparecer; se agregó `browser.wait_for_feedback()` (sondeo) en
   vez de una espera fija, usado ahora para todos los tipos.

**Estado actual de los archivos**:
- `blocked_lessons.json`: se vació a `[]` al principio de esta sesión: hay
  que confirmar su contenido actual antes de una corrida de verificación
  (puede tener entradas nuevas de las pruebas de esta sesión).
- `debug_omits/` acumuló capturas de varias corridas de prueba — se pueden
  revisar o borrar, no son necesarias para el código.
- Esta sesión tocó muchas lecciones de varios cursos distintos con pruebas
  en vivo (algunas resueltas por accidente, otras dejadas a medias
  intencionalmente para investigar) — es normal ver progreso parcial
  disperso en la cuenta real de Rosetta Stone.
- El repo es un repositorio git con un commit inicial; `README.md`, `ai.py`,
  `bot.py` y `browser.py` tienen cambios sin commitear. Confirmar con el
  usuario antes de hacer commit.
- El bot no está corriendo actualmente. Verificar con
  `Get-Process chrome | Where-Object { $_.Path -like "*ms-playwright*" }`
  antes de lanzar una sesión propia.

### Prompt sugerido para continuar

```text
Retoma FluencyBot desde el README (sección "Estado de la sesión
anterior"). Confirma el contenido de blocked_lessons.json, corre una
sesión real del bot (python bot.py) de punta a punta y verifica con
capturas que: (1) no se omita nada salvo actividades de habla/voz, y
(2) los ítems que la IA sí puede resolver con señal legible (incluido
cloze_input) queden realmente "Correcta" en el panel de la lección, no
solo "completados" por la vía de la revelación de Rosetta (que no da
crédito real — ver "Completado"/"Pendiente" sobre este hallazgo).
Reporta cualquier bug u omisión indebida que encuentres.
```

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

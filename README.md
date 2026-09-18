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

// cloze_input ("Llene los espacios en blanco" con texto libre; uno por espacio, en orden)
{"answers": ["not"]}

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
  - Implementado en `bot.retry_flagged_items()`, llamado en **varias rondas** (`MAX_RETRY_ROUNDS = 5`) al final de `run_lesson()` — no un solo intento, porque cada reapertura da un juego fresco de intentos reales antes de que Rosetta vuelva a revelar/rendirse.
  - Usa `browser.get_flagged_activity_ids()`, que lee el DOM real del panel lateral (`data-qa="activity_<id>"` con un hijo de estado cuyo sufijo VARÍA según el estado: `_completed` para "Correcta"/"Completa", `_skipped` para "Omitida" — no hay que asumir un sufijo fijo) — más robusto que buscar por texto visible o posición.
  - **Bug real encontrado y corregido**: la primera versión usaba `.first` sin registrar qué ya se había intentado — si un item no cambiaba de estado, `.first` seguía apuntando siempre al mismo, y el bucle lo reintentaba sin avanzar (confirmado en vivo: el usuario vio el bot yendo y viniendo entre los mismos dos ejercicios varios minutos). El siguiente intento (cortar toda la pasada al ver una URL repetida) tampoco servía: si el PRIMER item resultaba no arreglable, la función se rendía sin intentar los demás. La solución final usa los IDs estables de cada actividad, tomados una sola vez al principio, recorridos por ID (no por posición) — así cada uno se intenta exactamente una vez sin importar qué se arregle en el camino.
  - Las actividades genuinamente no automatizables (habla grabada, "Lectura en voz alta") se vuelven a omitir con el mismo criterio de siempre — eso es lo único que el usuario aceptó que quede sin resolver.
* [ ] **LIMITACIÓN REAL CONFIRMADA (no un bug del código) — una Demostración (video) marcada "Omitida" NO se puede recuperar reabriéndola**: se intentó CUATRO VECES en vivo, con distintos ajustes (clic en el contenedor, clic en el hijo de estado exacto, manejo del modal de habla que aparece al reabrir, bucle interno para no saltarse el video tras descartar el modal) y siempre terminó igual: al reabrir, la pantalla no vuelve a mostrar el video interactivo, simplemente avanza hasta "Vocabulario" dejando la Demostración "Omitida" para siempre. Esto es distinto de "Vuelva a intentarlo" (que si funciona al reabrir) — parece ser que Rosetta trata "omitir sin tocar" un video como una decisión permanente, mientras que "intentar y fallar" un ejercicio sí se puede reabrir. **Importante**: esto NO contradice el fix anterior de `video_is_watched()`/`skip_video()` (ese sigue siendo válido y confirmado: un video visto por PRIMERA vez con el fix aplicado sí queda "Completa" correctamente) — el problema es específicamente re-arreglar uno que ya quedó "Omitida" de una corrida/prueba anterior. Mientras el bot nunca omita un video sin verlo primero (que es el comportamiento normal de `run_lesson()`), este caso no debería producirse en una corrida real desde cero.
* [x] **Bug real encontrado por el usuario: en `cloze_input` el bot escribía la respuesta pero nunca la enviaba**. Causa: `fill_cloze_input()` hacía `.fill(text)` y `resolve_current_exercise()` llamaba a `submit_answer()` inmediatamente después, sin ninguna espera. El botón de enviar es un `<div>` (no un `<button disabled>` real), así que Playwright no espera a que React registre el cambio antes de permitir el clic — el clic ocurría, pero podía caer como no-op silencioso justo antes de que el campo quedara realmente marcado como lleno, dejando el texto visible pero sin enviar. Corregido en dos frentes: `fill_cloze_input()` ahora espera un poco tras escribir, y `resolve_current_exercise()` reintenta el clic de enviar una vez si no aparece feedback ni revelación (red de seguridad general para cualquier tipo, no solo `cloze_input`, ante el mismo patrón de "clic silenciosamente ignorado").
* [x] **Bug crítico externo encontrado y corregido: el modelo principal de IA dejó de funcionar de un día para otro**: `meta/muse-glimmer-30b` empezó a devolver `404 NotFoundError` en CUALQUIER llamada (confirmado en vivo con una prueba directa a la API, fuera del bot). Ojo: el modelo seguía apareciendo listado en `_client.models.list()` — solo la inferencia real fallaba, así que "sigue en el catálogo" no significa "sigue funcionando". Esto tumbó una corrida completa en cascada: cada ejercicio que necesitaba IA real fallaba 3/3 intentos con el mismo error y la lección quedaba bloqueada, lección tras lección, sin que fuera un problema de contenido — exactamente el tipo de "se salta algo indebido" que más le preocupa al usuario, y esta vez la causa era completamente externa al código. `AUDIO_MODEL` (`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`) seguía funcionando bien, lo que ayudó a aislar que era el modelo específico y no la cuenta/clave API. Reemplazado por `meta/llama-3.2-11b-vision-instruct` (confirmado en vivo que funciona con texto Y con imágenes reales, y que resuelve correctamente el ejercicio exacto que había fallado). Se limpiaron de `blocked_lessons.json` las lecciones bloqueadas por este bug durante la corrida afectada (no eran bloqueos legítimos de habla).

### Pendiente

* [ ] **PRÓXIMO PASO CONCRETO — corrida real de verificación completa**: con `cloze_input` resuelto con IA real, el bug de `video_is_watched()` corregido, `retry_flagged_items()` reintentando de verdad lo que quede "Omitida"/"Vuelva a intentarlo", y el modelo de IA principal reemplazado (ver el hallazgo del 404), relanzar una corrida completa real (`python bot.py`) de punta a punta con `python -u` (salida sin buffer, necesario para poder leer el log en vivo — con buffer normal no se ve nada hasta que el proceso termina). Revisar que no se omita nada salvo audio/habla, y que `retry_flagged_items()` efectivamente suba el número de "Correcta" en el panel al final de cada lección.
* [ ] **Riesgo real, expuesto por el incidente del modelo dado de baja**: si la IA falla por un problema de infraestructura (no de contenido) durante los 3 intentos de `resolve_current_exercise()`, la lección queda bloqueada PARA SIEMPRE en `blocked_lessons.json`, indistinguible de un fallo genuino de contenido — aunque el problema se resuelva minutos después (como pasó esta sesión), esa lección nunca se vuelve a intentar sola. No se implementó una distinción entre "la IA no supo la respuesta" y "la IA no pudo ni responder" — sería una mejora real dado que el usuario quiere que NADA quede sin resolver salvo habla.
* [ ] **Límite real de reintentos de Rosetta, confirmado en vivo**: Rosetta revela la respuesta y da por perdido el ejercicio tras solo **2** intentos fallidos (no 3) — `MAX_ATTEMPTS = 3` en `bot.py` rara vez llega a usarse completo porque `is_answer_revealed()` ya corta antes en el intento 3. Ya no es tan grave como se pensó al principio (ver `retry_flagged_items()`: si falla, se puede re-intentar de verdad al final de la lección), pero sigue limitando cuántos intentos reales tiene la IA antes de la revelación.
* [ ] **`matching` con audio puro ahora se resuelve de verdad, no se adivina** (implementado, falta confirmar en vivo) — el usuario aclaró que lo ÚNICO omitible es grabar la propia voz; un ejercicio de escucha (aunque sea audio) SÍ se puede resolver. `browser.get_matching_target_audio_data_uris()` captura el audio real de cada target (mismo patrón que `get_choice_audio_data_uris()` para `multiple_choice`) y `ai._solve_matching_audio()` usa `AUDIO_MODEL` para emparejar de verdad. Solo cae en `_blind_guess` si la captura de audio falla técnicamente (ej. servidor de medios caído), no como estrategia por defecto. **Aún no probado en vivo** — implementado por razonamiento/paridad con el patrón ya confirmado de `multiple_choice` de audio, pendiente de verificar con un caso real.
* [ ] `retry_flagged_items()` se probó en vivo contra `matching` (texto) y Demostración (video), ambos confirmados arreglando el estado a "Correcta"/"Completa". Falta confirmar con `cloze_dropdown`, `cloze_input` y el nuevo `matching` de audio real, y con lecciones que tengan muchos ítems marcados a la vez (ya se corrigió un bug de bucle infinito encontrado en esa situación, ver "Completado").
* [ ] El tipo "Escriba la respuesta" con 4 sub-preguntas + imagen, descrito en una sesión anterior como visto en "The Perfect Job, Part I", no volvió a aparecer en esta sesión (en su lugar se encontró `cloze_input`, ver "Completado"). Puede que fuera el mismo tipo mal recordado, o uno genuinamente distinto que aún no se ha vuelto a encontrar.
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

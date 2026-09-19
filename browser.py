import base64
import time

import config


# Rutas desde las que Rosetta sirve el audio. La primera es la actual;
# MediumHandler.ashx es la antigua y se conserva por si alguna actividad aún
# la usa. Confirmado en vivo registrando la red al pulsar un ListenButton:
# el audio ya NO pasaba por MediumHandler.ashx, así que la captura (que solo
# interceptaba esa ruta) esperaba 8 s por botón y se rendía SIEMPRE — unos
# 35 s perdidos por ejercicio, y la IA respondiendo a ciegas.
_AUDIO_ROUTES = ("**/LotusAssets/data/**", "**/MediumHandler.ashx*")


def _audio_mime(data):
    """Tipo de audio según los primeros bytes (el servidor manda octet-stream)."""
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[:4] == b"RIFF":
        return "audio/wav"
    if data[4:8] == b"ftyp":
        return "audio/mp4"
    return None


def _download_audio(page, url):
    """
    Descarga el clip entero. El navegador lo pide por trozos (206, rangos),
    así que no sirve lo que pasa por la red al reproducirlo: se baja aparte.
    Devuelve (data_uri, None) o (None, motivo).
    """
    last_error = None
    for attempt in range(3):
        try:
            response = page.request.get(url, timeout=15000)
            if response.ok:
                data = response.body()
                mime = _audio_mime(data)
                if mime:
                    return f"data:{mime};base64,{base64.b64encode(data).decode('utf-8')}", None
                last_error = f"formato no reconocido ({data[:8]!r})"
            else:
                last_error = f"HTTP {response.status}"
        except Exception as e:
            last_error = str(e)
        time.sleep(1)
    return None, last_error


def _capture_audio_from_buttons(page, listen_buttons, with_ids=False):
    """
    Pulsa cada ListenButton (en orden) y captura el audio real que carga,
    como data URI base64.

    Se usa page.route() para ver la petición: además de interceptarla,
    activar el enrutado desactiva la caché HTTP del navegador, así que cada
    clic genera su petición aunque ese clip ya se hubiera reproducido antes.
    La petición solo se usa para saber QUÉ URL es; el archivo se descarga
    completo aparte (ver _download_audio).

    Devuelve una lista del mismo largo que `listen_buttons` (None donde no
    se pudo). Con with_ids=True devuelve (data_uris, urls): la URL de cada
    clip es un hash de su contenido, o sea un identificador ESTABLE de la
    opción — imprescindible porque Rosetta baraja el orden de las opciones
    de audio en cada apertura (confirmado en vivo: guardar "la opción 2" no
    servía al reabrir).
    """
    urls = [None] * len(listen_buttons)
    current = {"i": None}

    def handle_route(route):
        idx = current["i"]
        if idx is not None and urls[idx] is None:
            urls[idx] = route.request.url
        route.continue_()

    for pattern in _AUDIO_ROUTES:
        page.route(pattern, handle_route)
    try:
        for i, button in enumerate(listen_buttons):
            current["i"] = i
            try:
                button.click(timeout=5000)
            except Exception as e:
                print(f"  (no se pudo pulsar el botón de audio {i + 1}: {e})")
                continue
            waited = 0
            while urls[i] is None and waited < 5000:
                page.wait_for_timeout(100)
                waited += 100
        current["i"] = None
    finally:
        for pattern in _AUDIO_ROUTES:
            page.unroute(pattern, handle_route)

    data_uris = []
    for i, url in enumerate(urls):
        if url is None:
            print(f"  (audio {i + 1}: el botón no pidió ningún clip)")
            data_uris.append(None)
            continue
        data_uri, error = _download_audio(page, url)
        if error:
            print(f"  (audio {i + 1}: no se pudo descargar: {error})")
        data_uris.append(data_uri)

    return (data_uris, urls) if with_ids else data_uris


def get_choice_audio_data_uris(page, count, with_ids=False):
    """Para un ejercicio "multiple_choice" cuyas opciones son solo audio (sin ChoiceText)."""
    choices = page.locator('[data-qa="ChoiceButton"]')
    buttons = [choices.nth(i).locator('[data-qa="ListenButton"]') for i in range(count)]
    return _capture_audio_from_buttons(page, buttons, with_ids=with_ids)


def get_matching_target_audio_data_uris(page, count):
    """
    Para un ejercicio "matching" cuyos targets son solo audio (sin
    PromptTitle legible ni imagen) — es un ejercicio de ESCUCHA, no de
    habla grabada, así que sí se puede resolver de verdad "escuchando"
    cada target en vez de adivinar parejas al azar.
    """
    targets = page.locator('[data-qa="MatchingDropTarget"]')
    buttons = [targets.nth(i).locator('[data-qa="ListenButton"]') for i in range(count)]
    return _capture_audio_from_buttons(page, buttons)


def get_prompt_audio_data_uri(page):
    """
    Para un ejercicio "multiple_choice" cuya PREGUNTA es solo audio (sin
    MultipleChoicePromptText, aunque las opciones sí tengan texto legible).
    """
    button = page.locator('[data-qa="MultipleChoicePromptAudio"] [data-qa="ListenButton"]')
    if button.count() == 0:
        return None
    return _capture_audio_from_buttons(page, [button])[0]


def open_browser(playwright):
    browser = playwright.chromium.launch(headless=False)
    # permissions=[] deniega micrófono/cámara sin preguntar: evita el popup nativo
    # del navegador y hace que el sitio muestre su propio modal "Continuar sin voz"
    # en los ejercicios de habla (que no podemos automatizar de todos modos).
    context = browser.new_context(permissions=[], viewport={"width": 1280, "height": 720})
    page = context.new_page()
    return browser, page


def login(page):
    print("Abriendo Rosetta Stone...")
    page.goto("https://learn.rosettastone.com/", wait_until="domcontentloaded")
    print("Página cargada.")
    print("URL:", page.url)

    print("Esperando formulario de inicio de sesión...")
    page.locator('[data-qa="Email"]').wait_for(state="visible", timeout=15000)

    print("Introduciendo correo...")
    page.locator('[data-qa="Email"]').fill(config.EMAIL)

    print("Introduciendo contraseña...")
    page.locator('[data-qa="Password"]').fill(config.PASSWORD)

    print("Haciendo clic en Sign in...")
    page.locator('[data-qa="SignInButton"]').click()
    print("Login enviado.")

    print("Esperando panel principal...")
    page.wait_for_timeout(3000)

    print("URL después del login:", page.url)
    print("Título:", page.title())


def open_fluency_builder(page):
    print("Buscando Fluency Builder...")
    fluency = page.get_by_text("Fluency Builder", exact=True)
    fluency.wait_for(state="visible", timeout=15000)
    print("Fluency Builder encontrado.")

    print("Entrando a Fluency Builder...")
    fluency.click()
    print("Click realizado.")

    page.wait_for_timeout(5000)

    print("--------------------------------")
    print("Ya estamos dentro de Fluency Builder")
    print("--------------------------------")
    print("URL actual:", page.url)
    print("Título:", page.title())


def go_to_courses(page):
    """
    Navega a "Mis cursos" desde cualquier pantalla de Fluency Builder
    (lista de cursos, detalle de un curso, o tras salir de una lección).
    """
    back_link = page.get_by_text("Mis cursos", exact=True)
    if back_link.count() > 0:
        back_link.first.click()
    else:
        page.get_by_text("Cursos", exact=True).first.click()
    page.wait_for_timeout(2000)


def get_courses(page):
    """Debe estar en 'Mis cursos'. Devuelve el número de cursos disponibles."""
    return page.locator('[data-qa="LaunchCourseButton"]').count()


def start_course(page, index):
    """
    Debe estar en 'Mis cursos'. Hace clic en Iniciar/Continuar del curso en
    la posición 'index' (0-based), llevando a su página de detalle (lista
    de lecciones de ese curso).
    """
    page.locator('[data-qa="LaunchCourseButton"]').nth(index).click()
    page.wait_for_timeout(2000)


def get_course_progress(page):
    """Debe estar en la página de detalle de un curso. Devuelve {"completed", "total"} de lecciones."""
    text = page.locator('[data-qa="LessonsCompletedCount"]').inner_text()
    completed, total = text.split("/")
    return {"completed": int(completed), "total": int(total)}


def get_course_title(page):
    """Debe estar en la página de detalle de un curso. Devuelve su nombre."""
    return page.locator('[data-qa="CoursePageCourseTitle"]').inner_text()


def get_lessons(page):
    """
    Debe estar en la página de detalle de un curso. Devuelve una lista de
    dicts por lección: {"title", "completed", "total"}.
    """
    lessons = []
    cards = page.locator('[data-qa="LessonDisplayer"]')
    for i in range(cards.count()):
        card = cards.nth(i)
        title = card.locator('[data-qa="LessonTitle"]').inner_text()
        text = card.locator('[data-qa="LessonActivitiesCompletedText"]').inner_text()
        completed, total = text.replace(" actividades completadas", "").split(" de ")
        lessons.append({"title": title, "completed": int(completed), "total": int(total)})
    return lessons


def start_lesson(page, index):
    """
    Debe estar en la página de detalle de un curso. Hace clic en
    Iniciar/Reanudar de la lección en la posición 'index' (0-based).
    """
    page.locator('[data-qa="LessonDisplayer"]').nth(index).locator('[data-qa="LaunchButton"]').click()
    page.wait_for_timeout(2000)


def exit_lesson(page):
    """
    Desde dentro de una lección, vuelve a la página de detalle de su curso.

    Confirmado en vivo que algo puede tapar el enlace e interceptar el clic
    ("...subtree intercepts pointer events"): Playwright lo interpreta como
    un overlay transitorio y reintenta en bucle hasta agotar los 30s por
    defecto en vez de fallar rápido. Se descarta el modal de habla primero
    y, si aun así no se puede, se fuerza el clic — mismo patrón que
    open_activity().
    """
    if has_speech_modal(page):
        dismiss_speech_modal(page)
        page.wait_for_timeout(500)

    link = page.get_by_text("Salir de la lección", exact=True).first
    try:
        link.click(timeout=5000)
    except Exception:
        if has_speech_modal(page):
            dismiss_speech_modal(page)
            page.wait_for_timeout(500)
        link.click(force=True, timeout=5000)
    page.wait_for_timeout(2000)


def has_speech_modal(page):
    """
    Detecta el modal "Habilitar actividades de habla" que aparece cuando la
    lección incluye ejercicios de pronunciación (no automatizables: requieren
    grabar audio real). Aparece porque open_browser() deniega el micrófono
    de antemano en vez de dejar que salga el popup nativo del navegador.
    """
    return page.get_by_text("Continuar sin voz", exact=True).count() > 0


# Nombres de tipo de actividad (tal como aparecen en el ActivityMapTitle del
# panel lateral) que requieren grabar la propia voz: lo ÚNICO que se acepta
# dejar sin resolver. Cualquier tipo que NO esté aquí se considera
# resoluble — el default tiene que ser "reintentable", porque dar por
# bloqueada una lección de más es justo el error que llenó
# blocked_lessons.json de falsos positivos.
SPEECH_ACTIVITY_TYPES = {
    "Lectura en voz alta",
    # Confirmado en vivo: su pantalla pide "Practique sus habilidades de
    # conversación al decir sus respuestas", tiene botón de micrófono, y al
    # elegir una opción el botón del pie sigue en "Omitir" (no se puede
    # enviar sin hablar).
    "Prácticas de conversación",
    "Pronunciación",
    "Hablar",
    "Habla",
}

# Textos de estado que significan "esta actividad ya quedó bien de verdad".
# "Completa" es de contenido no evaluado (Demostración, Vocabulario,
# Explicación); "Correcta" es de un ejercicio evaluado respondido bien.
DONE_ACTIVITY_STATUSES = {"Completa", "Correcta"}

# Items del panel lateral que no son actividades reales de la lección.
_NON_ACTIVITY_IDS = {"objectives", "summary"}


def get_activity_statuses(page):
    """
    Lee el panel lateral (`data-qa="ActivityMapList"`) y devuelve una lista
    de dicts, uno por actividad real de la lección, en orden:

        {"id", "type", "status", "status_qa"}

    "type" es el nombre visible del tipo ("Demostración", "Opción
    múltiple", "Escriba la respuesta", ...). "status" es el texto del
    estado ("Completa", "Correcta", "Omitida", "Vuelva a intentarlo") o
    None. "status_qa" es el `data-qa` del hijo de estado, que es lo que
    hay que clickear para reabrir la actividad (ver open_activity).

    Cada actividad es un contenedor `data-qa="activity_<id>"` con un hijo
    cuyo `data-qa` es ese mismo id más un sufijo de estado — **el sufijo
    varía según el estado** (confirmado en vivo volcando el DOM):

        _completed            -> "Completa"  (contenido no evaluado)
        _correctly_completed  -> "Correcta"  (ejercicio respondido bien)
        _skipped              -> "Omitida"

    Por eso no se busca por un sufijo fijo, sino cualquier hijo cuyo
    data-qa empiece por `activity_<id>_`.

    **Mientras estás PARADO en una actividad, esa no tiene hijo de estado
    en absoluto** (confirmado en vivo: la actividad en la que estaba la
    página salía sin estado, y desde el resumen la misma salía "Omitida").
    Por eso conviene leer esto desde la pantalla de resumen, donde estás
    parado en `activity_summary` y todas las actividades reales sí tienen
    su estado (ver go_to_lesson_summary).
    """
    return page.evaluate(
        """
        () => {
            const out = [];
            document.querySelectorAll('[data-qa^="activity_"]').forEach((el) => {
                const qa = el.getAttribute('data-qa');
                const rest = qa.slice('activity_'.length);
                if (rest.includes('_')) return; // hijo de estado, no el contenedor
                const titleEl = el.querySelector('[data-qa="ActivityMapTitle"]');
                const statusEl = Array.from(el.querySelectorAll('[data-qa]')).find(
                    c => c.getAttribute('data-qa').startsWith(qa + '_')
                );
                out.push({
                    id: rest,
                    type: titleEl ? titleEl.textContent.trim() : '',
                    status: statusEl ? statusEl.textContent.trim() : null,
                    status_qa: statusEl ? statusEl.getAttribute('data-qa') : null,
                });
            });
            return out;
        }
        """
    )


def get_pending_activities(page):
    """
    Actividades que todavía NO están bien ("Omitida", "Vuelva a
    intentarlo", o sin estado). Leer esto desde el resumen — ver
    get_activity_statuses sobre por qué desde otra pantalla se escapa
    justo la actividad en la que estás parado.
    """
    return [
        a
        for a in get_activity_statuses(page)
        if a["id"] not in _NON_ACTIVITY_IDS and a["status"] not in DONE_ACTIVITY_STATUSES
    ]


def all_pending_are_speech(pending, speech_ids=()):
    """
    True si todo lo que queda pendiente requiere grabar la propia voz, es
    decir: la lección está genuinamente bloqueada y no tiene sentido
    volver a intentarla en futuras corridas. Una lista vacía NO cuenta
    como bloqueada (no queda nada pendiente, que es otra cosa).
    """
    return bool(pending) and all(is_speech_activity(a, speech_ids) for a in pending)


def is_speech_activity(activity, speech_ids=()):
    """
    Una actividad es de voz si su TIPO lo es, o si ya se vio que su pantalla
    exige hablar (`speech_ids`, ver requires_speech). Lo segundo hace falta
    porque hay actividades de voz con nombre de tipo engañoso: confirmado en
    vivo, "Llene los espacios en blanco" puede ser "Seleccione la mejor
    respuesta y diga la oración completa", que no se puede enviar sin hablar.
    """
    return activity["type"] in SPEECH_ACTIVITY_TYPES or activity["id"] in speech_ids


def requires_speech(page):
    """
    True si la pantalla actual exige hablar: tiene el botón de micrófono
    (`data-qa="SpeechButton"`) fuera del panel lateral. Confirmado en vivo
    en tres pantallas distintas ("diga la oración completa", "Prácticas de
    conversación"): tras elegir una opción, el botón del pie sigue diciendo
    "Omitir" — Rosetta no deja enviar sin grabar la voz.
    """
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('[data-qa="SpeechButton"], [data-qa="MicIcon"]'))
            .some((el) => !el.closest('[data-qa="ActivityMapList"]'))
        """
    )


def go_to_lesson_summary(page):
    """
    Va a la pantalla "Resumen de la lección" haciendo clic en su item del
    panel lateral (`data-qa="activity_summary"`, estable: no depende del
    idioma ni de la posición). Devuelve True si se llegó.

    Sirve para dos cosas: es la única pantalla desde la que TODAS las
    actividades tienen su estado en el panel lateral (ver
    get_activity_statuses), y su panel central lista explícitamente lo que
    falta por hacer de la lección.
    """
    if has_speech_modal(page):
        dismiss_speech_modal(page)
        page.wait_for_timeout(500)

    item = page.locator('[data-qa="activity_summary"]')
    if item.count() == 0:
        return False

    try:
        item.first.click(timeout=5000)
    except Exception:
        if has_speech_modal(page):
            dismiss_speech_modal(page)
        try:
            item.first.click(force=True, timeout=5000)
        except Exception:
            return False

    page.wait_for_timeout(2000)
    return page.url.rstrip("/").endswith("/summary")


def get_flagged_activity_ids(page):
    """
    Devuelve el `data-qa` del hijo de estado de cada actividad marcada
    "Omitida" o "Vuelva a intentarlo" — que es lo que hay que clickear
    para reabrirla (ver open_activity).

    **Confirmado en vivo que importa cuál de los dos elementos se
    clickea**: clickear el CONTENEDOR (`activity_<id>`) no siempre
    funciona igual que clickear el hijo de estado directamente (con el
    contenedor, una Demostración "Omitida" a veces se saltaba de nuevo en
    vez de mostrar el video otra vez; con el hijo de estado sí volvía a
    mostrar el video interactivo).

    Usar el id estable de cada actividad (en vez de posición o texto
    visible) es lo que permite recorrer la lista reintentando cada una
    exactamente una vez, sin importar cuáles se arreglen en el camino.
    """
    return [
        a["status_qa"]
        for a in get_activity_statuses(page)
        if a["id"] not in _NON_ACTIVITY_IDS
        and a["status"] in ("Omitida", "Vuelva a intentarlo")
    ]


def open_activity(page, activity):
    """
    Abre una actividad desde el panel lateral, saltando directo a ella sin
    tener que recorrer la lección entera. `activity` es un dict de
    get_activity_statuses().

    Qué se clickea depende de si la actividad ya tiene estado:

    * **Con estado** (`status_qa`): se clickea el hijo de estado. Confirmado
      en vivo que importa: clickear el contenedor de una Demostración
      "Omitida" a veces la volvía a saltar, mientras que el hijo de estado
      sí volvía a mostrar el video interactivo.
    * **Sin estado** (nunca tocada, `status_qa is None`): no hay hijo que
      clickear, así que se usa el contenedor `activity_<id>`. Confirmado en
      vivo en una lección 0/13: clickear el contenedor de una "Explicación"
      jamás abierta llevó de `…/summary` a `…/8/1`, o sea directo a esa
      actividad. Es lo que permite saltarse el recorrido lineal.

    Confirmado en vivo: reabrir una actividad desde el panel puede disparar
    el modal de habla de nuevo, incluso si ya se descartó antes en la misma
    sesión. Playwright lo interpreta como un overlay transitorio y reintenta
    el clic en bucle hasta agotar el timeout (30s) en vez de fallar rápido,
    así que se descarta explícitamente antes de reintentar.
    """
    qa = activity["status_qa"] or f"activity_{activity['id']}"
    locator = page.locator(f'[data-qa="{qa}"]').first
    try:
        locator.click(timeout=5000)
    except Exception:
        if has_speech_modal(page):
            dismiss_speech_modal(page)
        locator.click(force=True, timeout=5000)


def has_read_aloud_activity(page):
    """
    Detecta la pantalla "Lectura en voz alta" (pestañas "Leer"/"Escuchar"/
    "Hablar"): requiere grabarse leyendo el texto en voz alta, no
    automatizable. A diferencia del modal inicial de habla (una sola vez
    por sesión de navegador, ver has_speech_modal), esta pantalla aparece
    como una actividad más dentro de la lección y no dispara ningún modal
    — sin esta detección, run_lesson() la trata como "pantalla no
    reconocida" genérica, lo cual la salta igual de bien pero no dice en
    el log que es una omisión intencional (de habla) y no un hueco real
    de mapeo.
    """
    # OJO: se ignora el panel lateral a propósito. Ahí aparece
    # "Lectura en voz alta" como NOMBRE de otra actividad de la lección, y
    # buscar el texto en toda la página hacía que CUALQUIER pantalla de una
    # lección con lectura en voz alta se tomara por una. Confirmado con el
    # DOM real: en una pantalla de opción múltiple normal devolvía True, y
    # como work_pending_activities() mira esto antes que el ejercicio, cada
    # actividad reabierta en esas lecciones se omitía en silencio. Era la
    # causa de que tantas lecciones quedaran bloqueadas con pendientes que el
    # bot sí sabe resolver.
    return page.evaluate(
        """
        () => Array.from(document.querySelectorAll('body *')).some(
            (el) => el.childElementCount === 0
                && el.textContent.trim() === 'Lectura en voz alta'
                && !el.closest('[data-qa="ActivityMapList"]')
        )
        """
    )


def has_paginated_content(page):
    """
    Detecta pantallas paginadas (Vocabulario, Explicación) con varios
    sub-pasos navegables vía NavigateForwardButton/NavigateBackButton.
    """
    return page.locator('[data-qa="NavigateForwardButton"]').count() > 0


def advance_paginated_content(page):
    """
    Avanza un sub-paso en una pantalla paginada (Vocabulario, Explicación),
    para que quede "Completa" en vez de "Omitida". Devuelve True si avanzó,
    False si ya estaba en el último paso (botón deshabilitado) y hay que
    usar el SubmitButton genérico ("Próxima actividad") para salir de ahí.
    """
    forward_button = page.locator('[data-qa="NavigateForwardButton"]')
    if forward_button.count() == 0 or forward_button.first.get_attribute("disabled") is not None:
        return False
    forward_button.first.click()
    page.wait_for_timeout(800)
    return True


def has_video(page):
    """Detecta una pantalla de "Demostración" (video)."""
    return page.locator("video").count() > 0


def video_is_watched(page):
    """
    True si todos los <video> de la pantalla ya realmente terminaron
    (evento "ended" del propio navegador). NO usar el atributo "disabled"
    de [data-qa="SubmitButton"] para esto: ese botón es un <div>, nunca
    tiene "disabled" de verdad, así que siempre parecía "listo para
    avanzar" incluso con el video sin ver — eso hacía que skip_video()
    nunca se llegara a llamar en la práctica y la Demostración quedara
    "Omitida" en vez de "Completa".

    Antes se aceptaba también "le faltan 3 segundos o menos" como
    equivalente a terminado (margen de seguridad para no colgarse
    esperando una igualdad exacta de currentTime===duration a 16x). Pero
    confirmado en vivo que ese margen deja la Demostración "Omitida" de
    todas formas: Rosetta exige el final real, no "casi terminado". El
    evento "ended" del navegador es fiable sin importar la velocidad de
    reproducción, así que no hace falta ningún margen.
    """
    return page.evaluate(
        """
        () => {
            const videos = document.querySelectorAll('video');
            if (videos.length === 0) return false;
            return Array.from(videos).every((v) => v.ended);
        }
        """
    )


def skip_video(page):
    """
    Mover currentTime a mano y disparar eventos sintéticos NO funciona:
    Rosetta lo ignora y la Demostración queda "Omitida" en vez de
    "Completa" (confirmado viéndolo en vivo). En vez de simular el final,
    se reproduce el video de verdad pero a velocidad muy alta (16x), para
    que los eventos que dispara el propio navegador sean reales y Rosetta
    los cuente igual que si se hubiera visto completo, solo que mucho más
    rápido. Esta función solo arranca la reproducción rápida; quien la
    llama debe esperar (via video_is_watched) a que efectivamente termine
    ("ended" real, no "casi terminado" — ver video_is_watched).
    """
    page.evaluate(
        """
        () => {
            document.querySelectorAll('video').forEach((v) => {
                v.muted = true;
                const setRate = () => { try { v.playbackRate = 16; } catch (e) {} };
                v.addEventListener('loadedmetadata', setRate);
                setRate();
                v.play().catch(() => {});
            });
        }
        """
    )
    try:
        page.wait_for_function(
            "() => { const v = document.querySelector('video'); return v && v.ended; }",
            timeout=30000,
        )
    except Exception:
        pass


def dismiss_speech_modal(page):
    """
    Hace clic en "Continuar sin voz". Esto no completa los ejercicios de
    habla (quedan pendientes en la lección para hacerlos a mano), pero
    desbloquea el resto de la lección/curso para que el bot pueda seguir.
    """
    page.get_by_text("Continuar sin voz", exact=True).first.click()
    page.wait_for_timeout(1500)


def _drag_to(page, source, target):
    """Arrastre genérico con ratón: pequeño movimiento inicial (umbral de la
    librería de arrastre) y suelta en el centro del destino."""
    a, b = source.bounding_box(), target.bounding_box()
    page.mouse.move(a["x"] + a["width"] / 2, a["y"] + a["height"] / 2)
    page.mouse.down()
    page.mouse.move(a["x"] + a["width"] / 2 + 5, a["y"] + a["height"] / 2 + 5, steps=3)
    page.mouse.move(b["x"] + b["width"] / 2, b["y"] + b["height"] / 2, steps=15)
    page.wait_for_timeout(150)
    page.mouse.up()
    page.wait_for_timeout(500)


# --- cloze_drag: huecos que se rellenan ARRASTRANDO palabras de un banco ---

def get_cloze_drag_text(page):
    """Texto de un 'cloze_drag' con cada hueco marcado como ___N___."""
    return page.evaluate(
        """
        () => {
            const clone = document.querySelector('[data-qa="step_content"]').cloneNode(true);
            const bank = clone.querySelector('[data-qa="ClozeDragAndDropBottomArea"]');
            if (bank) bank.remove();
            let i = 0;
            clone.querySelectorAll('[data-qa="ClozeDropTarget"]').forEach((el) => {
                i += 1;
                el.replaceWith(document.createTextNode(` ___${i}___ `));
            });
            return clone.innerText.trim();
        }
        """
    )


def get_cloze_drag_state(page):
    """(palabra en cada hueco, palabras que quedan en el banco)."""
    return page.evaluate(
        """
        () => [
            Array.from(document.querySelectorAll('[data-qa="ClozeDropTarget"]')).map(t => t.innerText.trim()),
            Array.from(document.querySelectorAll('[data-qa="ClozeDragAndDropBottomArea"] [data-qa="DragDropText"]'))
                .map(w => w.innerText.trim()),
        ]
        """
    )


def fill_cloze_drag(page, answers):
    """
    Arrastra cada palabra de `answers` a su hueco, en orden. Confirmado en
    vivo: un clic en la palabra NO hace nada, hay que arrastrarla. Tras cada
    arrastre se comprueba que la palabra quedó en su sitio y se reintenta
    si no. Devuelve True si todos los huecos quedaron llenos.

    Importante: con algún hueco vacío el botón del pie sigue diciendo
    "Omitir", y pulsarlo SALTA la actividad entera (confirmado en vivo).
    """
    original = fit_exercise_in_viewport(page)
    try:
        targets = page.locator('[data-qa="ClozeDropTarget"]')
        for i, word in enumerate(answers[:targets.count()]):
            for _ in range(3):
                placed, bank = get_cloze_drag_state(page)
                if placed[i] == word or word not in bank:
                    break
                source = page.locator('[data-qa="ClozeDragAndDropBottomArea"] [data-qa="DragDropText"]').nth(bank.index(word))
                _drag_to(page, source, targets.nth(i))
        placed, _ = get_cloze_drag_state(page)
        return all(placed)
    finally:
        restore_viewport(page, original)


# --- sentence_build: palabras sueltas que se ordenan para formar una oración ---

def get_sentence_build_state(page):
    """(palabras ya colocadas en la oración, palabras todavía sueltas)."""
    return page.evaluate(
        """
        () => {
            const items = Array.from(document.querySelectorAll('[data-qa="SBDItem"]'));
            const text = (el) => (el.querySelector('[data-qa="SBDItemText"]') || el).innerText.trim();
            return [
                items.filter(e => e.closest('[data-qa="TopDropArea"]')).map(text),
                items.filter(e => !e.closest('[data-qa="TopDropArea"]')).map(text),
            ];
        }
        """
    )


def build_sentence(page, words):
    """
    Forma la oración pulsando las palabras en orden. Confirmado en vivo: un
    CLIC en una palabra suelta la añade al final de la oración, sin
    necesidad de arrastrar. Con palabras repetidas ("a", "the") se pulsa la
    primera que siga suelta. Devuelve True si la oración quedó exactamente
    como se pidió.
    """
    for word in words:
        items = page.locator('[data-qa="SBDItem"]')
        target = None
        for i in range(items.count()):
            item = items.nth(i)
            if item.evaluate("e => !!e.closest('[data-qa=\"TopDropArea\"]')"):
                continue
            if item.inner_text().strip() == word:
                target = item.element_handle()
                break
        if target is None:
            break
        target.click(timeout=5000)
        page.wait_for_timeout(250)
    placed, _ = get_sentence_build_state(page)
    return placed == list(words)


# --- matching con OPCIONES de audio (lo que se arrastra son clips) ---

def get_matching_audio_option_ids(page):
    """Captura el audio de cada clip que queda abajo (DragDropAudio)."""
    options = page.locator('[data-qa="MatchingBottomArea"] [data-qa="DragDropAudio"]')
    buttons = [options.nth(i).locator('[data-qa="ListenButton"]') for i in range(options.count())]
    return _capture_audio_from_buttons(page, buttons, with_ids=True)


def place_matching_audio_options(page, clip_ids, target_for_clip):
    """
    Arrastra cada clip a su destino. `clip_ids` son los clips del banco en
    el orden en que estaban al detectar el ejercicio; `target_for_clip`
    mapea clip -> destino (1-based). El banco se va vaciando a medida que se
    arrastra, así que se lleva la cuenta de qué clips quedan y en qué orden.
    Devuelve True si todos los destinos quedaron con un clip.
    """
    original = fit_exercise_in_viewport(page)
    try:
        remaining = list(clip_ids)
        targets = page.locator('[data-qa="MatchingDropTarget"]')
        for clip, target in sorted(target_for_clip.items(), key=lambda kv: kv[1]):
            if clip not in remaining:
                continue
            idx = remaining.index(clip)
            bank = page.locator('[data-qa="MatchingBottomArea"] [data-qa="DragDropAudio"]')
            before = bank.count()
            _drag_to(page, bank.nth(idx), targets.nth(target - 1))
            if page.locator('[data-qa="MatchingBottomArea"] [data-qa="DragDropAudio"]').count() < before:
                remaining.pop(idx)
        return page.locator('[data-qa="MatchingBottomArea"] [data-qa="DragDropAudio"]').count() == 0
    finally:
        restore_viewport(page, original)


# --- text_rewrite: "Vuelva a escribir el texto según el ejemplo" ---

def get_text_rewrite(page):
    """
    Varias frases en la misma pantalla, cada una con su propio <textarea>
    (sin data-qa), dentro de `data-qa="inputContainer"`. Antes va un ejemplo
    ya resuelto (su textarea está deshabilitado y trae la respuesta), que es
    la clave para saber qué transformación se pide. Confirmado en vivo.
    """
    data = page.evaluate(
        """
        () => {
            const root = document.querySelector('[data-qa="step_content"]');
            const container = root.querySelector('[data-qa="inputContainer"]');
            const pair = (ta) => {
                const box = ta.parentElement;
                const prompt = box ? Array.from(box.children).filter(c => c !== ta).map(c => c.innerText.trim()).join(' ') : '';
                return {prompt, value: ta.value};
            };
            const examples = Array.from(root.querySelectorAll('textarea'))
                .filter(ta => !container.contains(ta)).map(pair);
            const items = Array.from(container.querySelectorAll('textarea')).map(pair);
            return {examples, items};
        }
        """
    )
    instructions = page.locator('[data-qa="Instructions"]')
    return {
        "type": "text_rewrite",
        "instructions": instructions.first.inner_text().strip() if instructions.count() else "",
        "examples": data["examples"],
        "prompts": [item["prompt"] for item in data["items"]],
    }


def fill_text_rewrite(page, answers):
    fields = page.locator('[data-qa="inputContainer"] textarea')
    for i, text in enumerate(answers[:fields.count()]):
        fields.nth(i).fill(text, timeout=5000)
    page.wait_for_timeout(300)


def get_current_exercise(page, capture_audio=True):
    """
    Detecta el ejercicio mostrado actualmente y devuelve un dict consumible
    por ai.solve_exercise(). El shape varía según "type":

        multiple_choice -> {"type", "prompt", "options": [str, ...], "image_url": str|None,
                            "prompt_audio_url": str|None (si la pregunta es solo audio),
                            "option_audio_urls": [str|None, ...] opcional (opciones solo-audio,
                            "options" queda vacío en ese caso)}
        matching        -> {"type", "targets": [str, ...], "targets_are_images": bool, "options": [str, ...],
                            "target_audio_urls": [str, ...] opcional (targets solo-audio)}
                            (targets son URLs de imagen si targets_are_images, si no son oraciones/frases)
        cloze_dropdown  -> {"type", "text", "blanks": [[str, ...], ...]}
        cloze_input     -> {"type", "text", "blank_count": int}
                            (espacios en blanco de texto libre, sin opciones para elegir)

    Confirmado inspeccionando el HTML real de Fluency Builder.

    capture_audio=False salta la captura de audio de los ejercicios que
    son solo-audio. Esa captura intercepta peticiones reales de red y es
    de lejos lo más lento de esta función, así que no vale la pena cuando
    quien llama solo necesita saber QUÉ pantalla es y ya sabe que la va a
    omitir (ver run_lesson: al "Reanudar", Rosetta siempre reinicia desde
    el paso 1, y las actividades ya contadas se pasan de largo sin llamar
    a la IA — bajar su audio para tirarlo era tiempo puro perdido, que es
    justo lo que el usuario notó en vivo: "escucha todas las opciones
    consumiendo tiempo y aun así las omite"). El dict devuelto queda
    marcado "unsolvable" porque sin ese audio de verdad no se puede
    resolver: NO uses el resultado para intentar responder.
    """
    # Tres tipos encontrados en vivo en "Talking with Clients, Customers,
    # and Partners (B1)" que el bot no reconocía y dejaba "Omitida" para
    # siempre. Van primero porque sus selectores son exclusivos.
    if page.locator('[data-qa="ClozeDropTarget"]').count() > 0:
        _, bank = get_cloze_drag_state(page)
        return {
            "type": "cloze_drag",
            "text": get_cloze_drag_text(page),
            "blank_count": page.locator('[data-qa="ClozeDropTarget"]').count(),
            "options": bank,
        }

    if page.locator('[data-qa="inputContainer"] textarea').count() > 0:
        return get_text_rewrite(page)

    if page.locator('[data-qa="SBDItem"]').count() > 0:
        placed, loose = get_sentence_build_state(page)
        return {"type": "sentence_build", "words": placed + loose}

    if page.locator('[data-qa="MatchingBottomArea"] [data-qa="DragDropAudio"]').count() > 0:
        targets = page.locator('[data-qa="MatchingDropTarget"] [data-qa="PromptTitle"]')
        count = page.locator('[data-qa="MatchingBottomArea"] [data-qa="DragDropAudio"]').count()
        if capture_audio:
            clips, clip_ids = get_matching_audio_option_ids(page)
        else:
            clips, clip_ids = [None] * count, [None] * count
        return {
            "type": "matching_audio_options",
            "targets": [targets.nth(i).inner_text().strip() for i in range(targets.count())],
            "option_audio_urls": clips,
            "option_audio_ids": clip_ids,
            "unsolvable": any(c is None for c in clips),
        }

    if (
        page.locator('[data-qa="MultipleChoicePromptText"]').count() > 0
        or page.locator('[data-qa="MultipleChoicePromptAudio"]').count() > 0
    ):
        choices = page.locator('[data-qa="ChoiceButton"]')

        # Puede haber más de un PromptText (ej. "Mire la imagen..." + la
        # pregunta real), y opcionalmente una imagen de apoyo. Si no hay
        # PromptText en absoluto, la pregunta en sí es solo audio (aunque
        # las opciones tengan texto legible) — se extrae ese audio real.
        # "unsolvable": no se pudo capturar algún audio necesario (pregunta
        # y/o opciones), así que no hay señal real para razonar. En vez de
        # omitir la actividad entera (queda "Omitida" para siempre), se
        # deja que ai.py intente una respuesta al azar: tras un par de
        # fallos Rosetta suele revelar la respuesta correcta ella misma
        # (ver browser.is_answer_revealed), y se avanza igual sin haber
        # tenido que adivinar bien.
        unsolvable = False

        prompt_parts = page.locator('[data-qa="MultipleChoicePromptText"] [data-qa="PromptText"]')
        if prompt_parts.count() > 0:
            prompt = " ".join(prompt_parts.nth(i).inner_text() for i in range(prompt_parts.count()))
            prompt_audio_url = None
        else:
            prompt = ""
            prompt_audio_url = get_prompt_audio_data_uri(page) if capture_audio else None
            if prompt_audio_url is None:
                unsolvable = True

        image = page.locator('[data-qa="step_content"] [data-qa="ContentImage"] img')
        image_url = image.first.get_attribute("src") if image.count() > 0 else None

        # Variante con opciones SOLO de audio, sin texto legible en absoluto
        # (ChoiceText no existe). Ojo: muchas opciones normales tienen texto
        # Y ADEMÁS un botón de audio opcional (ListenButton) al lado — esas
        # sí se resuelven por texto, por eso el chequeo es "falta ChoiceText",
        # no "hay ListenButton". Cuando falta, se extrae el audio real (en
        # vez de rendirse) para que la IA lo escuche.
        if choices.count() > 0 and choices.nth(0).locator('[data-qa="ChoiceText"]').count() == 0:
            if capture_audio:
                option_audio_urls, option_audio_ids = get_choice_audio_data_uris(
                    page, choices.count(), with_ids=True
                )
            else:
                option_audio_urls = [None] * choices.count()
                option_audio_ids = [None] * choices.count()
            if any(url is None for url in option_audio_urls):
                unsolvable = True
            return {
                "type": "multiple_choice",
                "prompt": prompt,
                "options": [],
                "option_count": choices.count(),
                "option_audio_urls": [] if unsolvable else option_audio_urls,
                # Identificador estable de cada opción (URL del clip, que es
                # un hash de su contenido): Rosetta baraja estas opciones en
                # cada apertura, así que su POSICIÓN no sirve para recordar
                # cuál era la correcta.
                "option_audio_ids": option_audio_ids,
                "image_url": image_url,
                "prompt_audio_url": prompt_audio_url,
                "unsolvable": unsolvable,
            }

        return {
            "type": "multiple_choice",
            "prompt": prompt,
            "options": get_exercise_options(page),
            "image_url": image_url,
            "prompt_audio_url": prompt_audio_url,
            "unsolvable": unsolvable,
        }

    if page.locator('[data-qa="MatchingDropTarget"]').count() > 0:
        targets = page.locator('[data-qa="MatchingDropTarget"] [data-qa="PromptTitle"]')
        words = page.locator('[data-qa="DragDropText"]')
        target_count = targets.count()

        # El destino es una imagen (ContentImage > img) o es directamente
        # texto (una oración/frase en el PromptTitle) — que puede venir
        # acompañado de un botón de audio opcional (ListenButton), lo cual
        # no impide resolverlo por texto.
        targets_are_images = target_count > 0 and targets.nth(0).locator("img").count() > 0

        if targets_are_images:
            target_values = [targets.nth(i).locator("img").get_attribute("src") for i in range(target_count)]
        else:
            target_values = [targets.nth(i).inner_text().strip() for i in range(target_count)]

        option_values = [words.nth(i).inner_text() for i in range(words.count())]

        # Sin ninguna palabra arrastrable detectada no hay nada que
        # interactuar; eso sí es genuinamente no soportado.
        if not option_values:
            raise NotImplementedError(
                "Tipo 'matching' sin palabras arrastrables detectadas (variante no mapeada) no soportado."
            )

        # Targets SOLO de audio (sin imagen ni texto legible): es un
        # ejercicio de ESCUCHA, no de habla grabada, así que SÍ se puede
        # resolver de verdad capturando el audio real de cada target (igual
        # que ya se hace para "multiple_choice" de audio) en vez de
        # adivinar parejas al azar — confirmado en vivo que la revelación
        # de Rosetta no da crédito real, así que adivinar no es aceptable
        # aquí si en realidad se puede "escuchar".
        target_audio_urls = None
        if capture_audio and not targets_are_images and not any(target_values):
            target_audio_urls = get_matching_target_audio_data_uris(page, target_count)

        # "unsolvable" solo si de verdad no hay ninguna señal usable (ni
        # texto/imagen, ni se pudo capturar el audio de todos los targets):
        # ahí sí no queda otra que adivinar y confiar en la revelación.
        unsolvable = not any(target_values) and (
            target_audio_urls is None or any(url is None for url in target_audio_urls)
        )

        return {
            "type": "matching",
            "targets": target_values,
            "targets_are_images": targets_are_images,
            "options": option_values,
            "target_audio_urls": target_audio_urls,
            "unsolvable": unsolvable,
        }

    cloze_dropdowns = page.locator('[data-qa^="ClozeDropdown_"]')
    if cloze_dropdowns.count() > 0:
        return {
            "type": "cloze_dropdown",
            "text": get_cloze_text(page),
            "blanks": get_cloze_options(page, cloze_dropdowns.count()),
        }

    cloze_inputs = page.locator('[data-qa="ClozeInput"]')
    if cloze_inputs.count() > 0:
        # "Llene los espacios en blanco" con texto libre (no hay opciones para
        # elegir, hay que escribir la palabra/frase exacta). El texto SÍ es
        # legible por contexto, así que ai.py intenta una respuesta real en
        # vez de adivinar a ciegas: confirmado en vivo que Rosetta revela la
        # respuesta y avanza tras solo 2 fallos, pero deja el ejercicio
        # marcado como incorrecto para siempre (la revelación no da crédito
        # real, solo evita que el bot se quede trabado) — más vale que la IA
        # tenga una oportunidad genuina de acertar dentro de esos 2 intentos.
        return {
            "type": "cloze_input",
            "text": get_cloze_input_text(page),
            "blank_count": cloze_inputs.count(),
        }

    if page.locator('[data-qa="DraggableSentenceItem"]').count() > 0:
        return {
            "type": "ordering",
            "items": get_ordering_items(page),
        }

    if page.locator('[data-qa="TextInput"]').count() > 0:
        # "Escriba la respuesta": un `<textarea>` de texto libre, con la
        # pregunta en WritingPracticeTopic-<n> y a veces una imagen de
        # apoyo. Es una actividad de VARIOS pasos (el pie muestra "1 de 4
        # pasos"), cada uno en su propia pantalla — quien llama tiene que
        # seguir resolviendo mientras siga en la misma actividad (ver
        # bot._work_single_activity).
        #
        # Rosetta muestra además la longitud esperada de la respuesta
        # ("(7 caracteres)"), que es una pista real y muy fuerte para
        # acertar texto libre, así que se le pasa a la IA.
        topics = page.locator('[data-qa^="WritingPracticeTopic-"]')
        prompt = " ".join(topics.nth(i).inner_text().strip() for i in range(topics.count()))

        image = page.locator('[data-qa="step_content"] [data-qa="ContentImage"] img')
        image_url = image.first.get_attribute("src") if image.count() > 0 else None

        instructions = page.locator('[data-qa="Instructions"]')
        expected_length = page.evaluate(
            """
            () => {
                const ta = document.querySelector('[data-qa="TextInput"]');
                if (!ta) return null;
                const m = (ta.parentElement ? ta.parentElement.textContent : '').match(/\\((\\d+)\\s*caracteres?\\)/);
                return m ? parseInt(m[1], 10) : null;
            }
            """
        )

        return {
            "type": "text_input",
            "prompt": prompt,
            "instructions": instructions.first.inner_text().strip() if instructions.count() > 0 else "",
            "image_url": image_url,
            "expected_length": expected_length,
        }

    raise NotImplementedError(
        "Tipo de ejercicio no reconocido o aún no mapeado (soportados: "
        "'multiple_choice', 'matching', 'cloze_dropdown', 'cloze_input', "
        "'ordering', 'text_input')."
    )


def get_exercise_options(page):
    choices = page.locator('[data-qa="ChoiceButton"]')
    return [
        choices.nth(i).locator('[data-qa="ChoiceText"]').inner_text()
        for i in range(choices.count())
    ]


def click_option(page, option):
    """
    Selecciona una opción en un ejercicio "multiple_choice".

    option: índice 1-based de la opción (según data-qa-choice="ChoiceButton_N")
    o el texto exacto de la opción.
    """
    if isinstance(option, int):
        locator = page.locator(f'[data-qa-choice="ChoiceButton_{option}"]')
    else:
        locator = page.locator('[data-qa="ChoiceButton"]').filter(has_text=option)
    # Timeout corto: si la opción no existe, fallar rápido en vez de 30 s.
    locator.first.click(timeout=5000)


def get_cloze_text(page):
    """
    Devuelve el texto del ejercicio "cloze_dropdown" con cada espacio en
    blanco marcado explícitamente como "___N___" (N = número de
    ClozeDropdown_N). Un simple inner_text() deja los espacios como saltos
    de línea ambiguos, lo que confunde a la IA en textos largos con varios
    blancos no consecutivos.
    """
    return page.evaluate(
        """
        () => {
            const container = document.querySelector('[data-qa="step_content"]');
            const clone = container.cloneNode(true);
            clone.querySelectorAll('[data-qa^="ClozeDropdown_"]').forEach((el) => {
                const num = el.getAttribute('data-qa').replace('ClozeDropdown_', '');
                el.replaceWith(document.createTextNode(` ___${num}___ `));
            });
            return clone.innerText;
        }
        """
    )


def get_cloze_input_text(page):
    """
    Devuelve el texto de un ejercicio "cloze_input" (espacios en blanco de
    texto libre) con cada espacio marcado como "___N___" (N = orden en que
    aparece el <input data-qa="ClozeInput"> en el DOM), igual que
    get_cloze_text() hace para los dropdowns.
    """
    return page.evaluate(
        """
        () => {
            const container = document.querySelector('[data-qa="step_content"]');
            const clone = container.cloneNode(true);
            let i = 0;
            clone.querySelectorAll('[data-qa="ClozeInput"]').forEach((el) => {
                i += 1;
                el.replaceWith(document.createTextNode(` ___${i}___ `));
            });
            return clone.innerText;
        }
        """
    )


def fill_cloze_input(page, blank_index, text):
    """
    Escribe texto en el espacio en blanco blank_index (1-based) de un
    ejercicio "cloze_input" (Llene los espacios en blanco con texto libre).

    El botón de enviar es un <div> (no un <button disabled> real), así que
    Playwright no espera a que React procese el cambio antes de permitir el
    siguiente clic. Sin una pequeña espera aquí, bot.py podía hacer clic en
    "Enviar" justo antes de que el campo quedara realmente registrado como
    lleno, y el clic caía como no-op silencioso: el texto se veía escrito
    pero nunca se enviaba (confirmado en vivo por el usuario).
    """
    page.locator('[data-qa="ClozeInput"]').nth(blank_index - 1).fill(text, timeout=5000)
    page.wait_for_timeout(300)


def get_cloze_options(page, blank_count):
    """
    Abre cada dropdown de un ejercicio "cloze_dropdown" para leer sus
    opciones (no aparecen en el HTML hasta que se abren) y los vuelve a
    cerrar. Devuelve una lista de listas: options[i] son las opciones del
    espacio en blanco i+1.
    """
    options_per_blank = []
    for i in range(1, blank_count + 1):
        dropdown = page.locator(f'[data-qa="ClozeDropdown_{i}"]')
        menu_button = dropdown.locator('[data-qa="MenuButton"]')
        menu_button.click()
        items = dropdown.locator('[data-qa^="MenuItem_"]')
        options_per_blank.append([items.nth(j).inner_text() for j in range(items.count())])
        menu_button.click()  # cerrar sin seleccionar
    return options_per_blank


def select_cloze_option(page, blank_index, option):
    """
    Selecciona una opción en un espacio en blanco de un ejercicio
    "cloze_dropdown".

    blank_index: índice 1-based del espacio (ClozeDropdown_N).
    option: índice 0-based de la opción (MenuItem_N) o su texto exacto.
    """
    dropdown = page.locator(f'[data-qa="ClozeDropdown_{blank_index}"]')
    dropdown.locator('[data-qa="MenuButton"]').click()

    items = dropdown.locator('[data-qa^="MenuItem_"]')
    item = items.nth(option) if isinstance(option, int) else items.filter(has_text=option)
    item.first.click()


def drag_matching_pair(page, word, target_index):
    """
    Arrastra una palabra (data-qa="DragDropText") a un destino de un
    ejercicio "matching".

    word: texto exacto de la palabra a arrastrar.
    target_index: índice 1-based del destino (data-qa="MatchingDropTarget"),
    en el mismo orden que "image_urls" en get_current_exercise().
    """
    word_locator = page.locator('[data-qa="DragDropText"]').filter(has_text=word).first
    target_locator = page.locator('[data-qa="MatchingDropTarget"]').nth(target_index - 1)

    word_box = word_locator.bounding_box()
    target_box = target_locator.bounding_box()

    page.mouse.move(word_box["x"] + word_box["width"] / 2, word_box["y"] + word_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        target_box["x"] + target_box["width"] / 2,
        target_box["y"] + target_box["height"] / 2,
        steps=10,
    )
    page.mouse.up()


def get_ordering_items(page):
    """Ejercicio 'ordering' (Organización): textos en el orden actual (desordenado)."""
    items = page.locator('[data-qa="DraggableSentenceContent"]')
    return [items.nth(i).inner_text() for i in range(items.count())]


def _drag_ordering_item(page, source_locator, target_locator, moving_down):
    """
    Arrastra un ítem sobre otro. **Dónde se suelta importa**: la librería de
    arrastre inserta antes o después del destino según a qué mitad llegues.
    Soltar en el CENTRO (como se hacía antes) hacía que al bajar un ítem
    cayera una posición de más, la corrección siguiente lo deshacía, y el
    bucle oscilaba hasta agotar los movimientos sin llegar nunca al orden
    pedido — confirmado en vivo con una respuesta guardada CORRECTA que igual
    salió "incorrecta" (Rosetta reveló después exactamente ese orden).
    Ahora: subiendo se suelta junto al borde superior del destino, bajando
    junto al inferior.
    """
    source_box = source_locator.bounding_box()
    target_box = target_locator.bounding_box()
    start_x = source_box["x"] + source_box["width"] / 2
    start_y = source_box["y"] + source_box["height"] / 2
    edge = min(8, target_box["height"] / 4)
    end_y = (target_box["y"] + target_box["height"] - edge) if moving_down else (target_box["y"] + edge)
    end_x = target_box["x"] + target_box["width"] / 2

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    # Un primer movimiento corto: las librerías de arrastre no empiezan a
    # arrastrar hasta superar un umbral de distancia.
    page.mouse.move(start_x, start_y + (6 if moving_down else -6), steps=3)
    page.mouse.move(end_x, end_y, steps=15)
    page.wait_for_timeout(150)
    page.mouse.up()
    page.wait_for_timeout(400)


def fit_exercise_in_viewport(page):
    """
    Agranda la ventana lo justo para que TODO el ejercicio quepa en
    pantalla, y devuelve el tamaño original para restaurarlo después (ver
    restore_viewport).

    Imprescindible para cualquier arrastre: el ratón no puede soltar en una
    coordenada fuera de la ventana. Confirmado en vivo dos veces con la
    ventana de 720 px: el sexto ítem de un 'ordering' iba de y=691 a y=773,
    y el tercer hueco de un 'cloze_drag' de y=705 a y=742 — ningún arrastre
    llegaba a ellos y el ejercicio nunca quedaba completo.
    """
    original = page.viewport_size
    if not original:
        return None
    bottom = page.evaluate(
        """
        () => {
            let max = 0;
            const root = document.querySelector('[data-qa="step_content"]') || document.body;
            root.querySelectorAll('*').forEach((el) => {
                const r = el.getBoundingClientRect();
                if (r.height > 0) max = Math.max(max, r.bottom + window.scrollY);
            });
            return Math.ceil(max);
        }
        """
    )
    needed = bottom + 150
    if needed > original["height"]:
        page.set_viewport_size({"width": original["width"], "height": needed})
        page.wait_for_timeout(300)
    return original


def restore_viewport(page, original):
    if original and page.viewport_size != original:
        page.set_viewport_size(original)


def reorder_items(page, target_order):
    """
    Arrastra los DraggableSentenceItem de un ejercicio 'ordering' hasta
    lograr que queden en target_order (lista de textos exactos, en el
    orden final deseado).

    No asume de antemano cómo reordena exactamente la librería de arrastre
    al soltar un ítem sobre otro (inserta antes/después según su propia
    lógica, no documentada): después de cada arrastre vuelve a leer el
    orden real en pantalla y decide el siguiente movimiento en base a eso,
    en vez de calcular todos los movimientos por adelantado.
    """
    original_viewport = fit_exercise_in_viewport(page)
    try:
        max_moves = len(target_order) * len(target_order) + 5
        for _ in range(max_moves):
            current = get_ordering_items(page)
            if current == target_order:
                return True
            for i, wanted_text in enumerate(target_order):
                if current[i] != wanted_text:
                    src_index = current.index(wanted_text)
                    items = page.locator('[data-qa="DraggableSentenceItem"]')
                    _drag_ordering_item(page, items.nth(src_index), items.nth(i), moving_down=src_index < i)
                    break
        return get_ordering_items(page) == target_order
    finally:
        restore_viewport(page, original_viewport)


def write_answer(page, answer):
    """
    Escribe en el `<textarea data-qa="TextInput">` de "Escriba la respuesta".

    Espera un poco tras escribir por el mismo motivo que fill_cloze_input():
    el botón de enviar es un `<div>`, no un `<button disabled>` real, así
    que Playwright no espera a que React registre el cambio antes de
    permitir el clic y un envío inmediato puede caer como no-op silencioso.
    """
    # Timeout corto a propósito: tras enviar, Rosetta deshabilita el
    # textarea, y con el timeout por defecto (30s) un intento de escribir
    # en ese estado se queda colgado medio minuto antes de fallar. Si no
    # se puede escribir, quien llama ya debería haberlo detectado con
    # exercise_is_locked() — que falle rápido y se vea.
    page.locator('[data-qa="TextInput"]').first.fill(answer, timeout=5000)
    page.wait_for_timeout(300)


def submit_answer(page):
    """
    Hace clic en el botón de acción del pie de página. Este mismo botón
    (data-qa="SubmitButton") sirve para enviar la respuesta, reintentar
    ("Volver a intentar" tras un fallo) o avanzar ("Próxima actividad"
    tras un acierto) — el texto cambia pero el selector es el mismo.
    """
    page.locator('[data-qa="SubmitButton"]').click()


def get_feedback_state(page):
    """
    Devuelve "correct", "incorrect", "revealed" o None si aún no se envió
    respuesta.

    **Ojo con "revealed"**: cuando Rosetta muestra la respuesta correcta
    tras agotar los intentos, pinta `FeedbackCorrectIcon` (el MISMO icono
    verde que cuando aciertas de verdad) dentro de un
    `ShowAnswerFeedback`. Confirmado volcando el DOM. Sin distinguirlos,
    esta función devolvía "correct" para un ejercicio que en realidad se
    falló, y el bot lo daba por resuelto — reportando un éxito que no
    existió. Por eso se mira ShowAnswerFeedback ANTES que el icono.
    """
    if page.locator('[data-qa="ShowAnswerFeedback"]').count() > 0:
        return "revealed"
    if page.locator('[data-qa="FeedbackCorrectIcon"]').count() > 0:
        return "correct"
    if page.locator('[data-qa="IncorrectFeedback"]').count() > 0:
        return "incorrect"
    return None


def wait_for_feedback(page, timeout_ms=8000, poll_ms=250):
    """
    Sondea hasta que aparezca feedback reconocible (correcto/incorrecto) o
    Rosetta revele la respuesta, en vez de una espera fija. Confirmado en
    vivo que "cloze_input" tarda más de 1.5s en mostrar su feedback (a
    diferencia de multiple_choice/matching, que son casi instantáneos): una
    espera fija corta hacía que get_feedback_state() devolviera None
    mientras el envío seguía procesándose, y el reintento de bot.py caía
    sobre esa vista a medio actualizar (el siguiente fill() ya no
    encontraba el input, con timeout de 30s).
    """
    elapsed = 0
    while elapsed < timeout_ms:
        feedback = get_feedback_state(page)
        if feedback is not None or is_answer_revealed(page):
            return feedback
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    return get_feedback_state(page)


def get_action_button_label(page):
    """
    Texto del botón de acción del pie. Rosetta reutiliza el MISMO
    `data-qa="SubmitButton"` para todo y solo le cambia el texto, que lleva
    además en `data-qa-button-text`: "Omitir" (campo vacío), "Revisar
    respuesta" (hay algo escrito sin enviar), "Volver a intentar" (fallaste),
    "Próxima actividad" (acertaste).

    Sirve para no hacer clics a ciegas: confirmado en vivo que un clic de
    más en ese botón avanza de paso, y en una actividad de varios pasos eso
    se salta preguntas enteras sin responderlas (el bot pasó del paso 1 al 4
    de una "Escriba la respuesta", dejando dos preguntas sin tocar).
    """
    button = page.locator('[data-qa="SubmitButton"]')
    if button.count() == 0:
        return None
    return button.first.get_attribute("data-qa-button-text") or button.first.inner_text().strip()


def exercise_is_locked(page):
    """
    True si el ejercicio de la pantalla tiene campos de entrada pero TODOS
    están deshabilitados, o sea que Rosetta ya lo dio por cerrado y no
    acepta más interacción.

    Confirmado en vivo con "Escriba la respuesta": al enviar, el
    `<textarea>` pasa a `disabled` y el botón cambia a "Volver a intentar";
    hasta hacer clic ahí, cualquier intento de escribir se queda esperando
    a que el campo se habilite (30s hasta el timeout de Playwright). Tras
    agotar los intentos, Rosetta muestra la respuesta y el campo se queda
    deshabilitado para siempre — sin este chequeo, el bot insistía contra
    un campo que nunca se iba a volver a habilitar.

    Es un chequeo genérico (no por tipo) porque el mismo patrón ya había
    causado cuelgues de 30s con los dropdowns de 'cloze_dropdown'.
    """
    return page.evaluate(
        """
        () => {
            const els = document.querySelectorAll(
                '[data-qa="TextInput"], [data-qa="ClozeInput"], [data-qa^="ClozeDropdown_"]'
            );
            if (!els.length) return false;
            return Array.from(els).every((el) => el.disabled === true);
        }
        """
    )


SHOW_ANSWER_LABEL = "Mostrar respuesta"


def get_lesson_path(page):
    """
    Ruta de la lección actual dentro del curso (`course/<curso>/<lección>`),
    o None fuera de una lección. Es el prefijo de las claves de
    get_exercise_key(), lo que permite saber si hay respuestas guardadas
    pendientes de usar para una lección concreta.
    """
    parts = page.url.split("//", 1)[-1].split("/", 1)
    if len(parts) < 2:
        return None
    segments = parts[1].strip("/").split("/")
    if len(segments) < 3 or segments[0] != "course":
        return None
    return "/".join(segments[:3])


def get_exercise_key(page):
    """
    Identificador estable del ejercicio que hay en pantalla, para poder
    recordar su respuesta entre reaperturas y entre corridas.

    Se usa la ruta de la URL, que dentro de una lección es
    `course/<curso>/<lección>/<actividad>/<paso>` — el índice de actividad
    sale del orden del panel lateral (fijo) y el de paso del orden dentro
    de la actividad, así que al reabrirla se llega a la misma ruta.
    Devuelve None fuera de un ejercicio (ej. en `…/summary`).
    """
    parts = page.url.split("//", 1)[-1].split("/", 1)
    if len(parts) < 2:
        return None
    path = parts[1].rstrip("/")
    tail = path.split("/")
    if len(tail) < 2 or not tail[-1].isdigit() or not tail[-2].isdigit():
        return None
    return path


def is_answer_revealed(page):
    """
    Tras agotar los intentos, Rosetta muestra la respuesta correcta con el
    aviso "Esta es la respuesta correcta.", dejando avanzar sin acertar.

    Se detecta por `data-qa="ShowAnswerFeedback"` (estable, independiente
    del idioma) en vez de por ese texto en español.
    """
    return page.locator('[data-qa="ShowAnswerFeedback"]').count() > 0


def can_show_answer(page):
    """
    True si el botón del pie ofrece "Mostrar respuesta", o sea que se
    agotaron los intentos y Rosetta puede revelar la solución.

    Secuencia real del botón, confirmada volcando el DOM tras fallar a
    propósito: "Omitir" -> (fallo 1) "Volver a intentar" -> (fallo 2)
    "Mostrar respuesta" -> (clic) "Próxima actividad", ya con la respuesta
    correcta resaltada en pantalla.
    """
    return get_action_button_label(page) == SHOW_ANSWER_LABEL


def get_revealed_answer(page, exercise):
    """
    Con la respuesta ya revelada en pantalla (ver is_answer_revealed),
    devuelve la solución correcta en el MISMO formato que produce
    ai.solve_exercise(), para poder reaplicarla tal cual al reabrir la
    actividad. Devuelve None si no se puede leer.

    Por qué vale la pena: confirmado en vivo que la revelación NO da
    crédito — el ejercicio queda mal igual. La única forma de arreglarlo
    es reabrir la actividad desde el panel lateral, y ahí la IA volvería a
    adivinar a ciegas con los mismos intentos. Guardar lo que Rosetta
    enseñó convierte ese caso en un acierto seguro.

    Confirmado volcando el DOM de cada tipo por separado (fallando un
    ejercicio a propósito hasta llegar a "Mostrar respuesta"): **salvo en
    multiple_choice, Rosetta escribe la respuesta correcta directamente en
    los propios controles**, así que basta con leerlos.

    * `multiple_choice`: cada opción es un `data-qa="ChoiceButton"` con
      `data-qa-choice="ChoiceButton_<n>"` (índice estable, 1-based). Al
      revelar, la correcta recibe una clase distinta a la del resto. Los
      nombres son hashes generados (`css-1jr9iaz-RadioButtonDiv`) que
      cambian entre despliegues, así que NO se busca una clase concreta:
      se busca la única que se diferencia de la mayoría.
    * `text_input`: el `<textarea data-qa="TextInput">` pasa a contener la
      respuesta correcta.
    * `cloze_input`: cada `[data-qa="ClozeInput"]` queda con su texto
      correcto.
    * `cloze_dropdown`: cada `ClozeDropdown_<n>` queda con la opción
      correcta seleccionada; se guarda su TEXTO, que select_cloze_option()
      acepta igual que un índice y no depende del orden del menú.
    * `matching`: cada palabra queda colocada en su destino correcto, así
      que el `DragDropText` que hay dentro de cada `MatchingDropTarget` es
      la pareja buena.
    * `ordering`: los ítems quedan reordenados correctamente.
    """
    # Guarda imprescindible: la opción que acabas de marcar MAL también
    # recibe una clase propia distinta de las demás, así que sin este
    # chequeo la heurística de "la que se diferencia" devuelve la respuesta
    # EQUIVOCADA cuando todavía no hay revelación. Solo tiene sentido leer
    # esto con ShowAnswerFeedback en pantalla.
    if not is_answer_revealed(page):
        return None

    kind = exercise["type"]

    if kind == "multiple_choice":
        index = page.evaluate(
            """
            () => {
                const nodes = Array.from(document.querySelectorAll('[data-qa="ChoiceButton"]'));
                if (nodes.length < 3) return null;  // sin mayoría clara no se puede decidir
                const counts = {};
                nodes.forEach((el) => {
                    const c = el.getAttribute('class') || '';
                    counts[c] = (counts[c] || 0) + 1;
                });
                const odd = nodes.filter((el) => counts[el.getAttribute('class') || ''] === 1);
                if (odd.length !== 1) return null;
                const m = (odd[0].getAttribute('data-qa-choice') || '').match(/(\\d+)$/);
                return m ? parseInt(m[1], 10) : null;
            }
            """
        )
        if not index:
            return None
        solution = {"answer": index}
        ids = exercise.get("option_audio_ids") or []
        if len(ids) >= index and ids[index - 1]:
            # Opciones de solo audio: se barajan al reabrir, así que se
            # recuerda QUÉ clip era el correcto, no en qué posición estaba.
            solution["answer_audio_id"] = ids[index - 1]
        return solution

    if kind == "text_input":
        field = page.locator('[data-qa="TextInput"]')
        if field.count() == 0:
            return None
        value = field.first.input_value().strip()
        return {"answer": value} if value else None

    if kind == "cloze_input":
        fields = page.locator('[data-qa="ClozeInput"]')
        values = [fields.nth(i).input_value().strip() for i in range(fields.count())]
        return {"answers": values} if values and all(values) else None

    if kind == "cloze_dropdown":
        labels = page.evaluate(
            """
            () => {
                const out = [];
                for (let i = 1; ; i++) {
                    const el = document.querySelector(`[data-qa="ClozeDropdown_${i}"]`);
                    if (!el) break;
                    const label = el.querySelector('[data-qa="MenuButtonLabel"]');
                    out.push(label ? label.textContent.trim() : '');
                }
                return out;
            }
            """
        )
        return {"answers": labels} if labels and all(labels) else None

    if kind == "matching":
        pairs = page.evaluate(
            """
            () => {
                const targets = Array.from(document.querySelectorAll('[data-qa="MatchingDropTarget"]'));
                const pairs = {};
                targets.forEach((t, i) => {
                    const word = t.querySelector('[data-qa="DragDropText"]');
                    if (word) pairs[word.textContent.trim()] = i + 1;
                });
                // Si algún destino quedó vacío la lectura está incompleta y
                // aplicarla dejaría el ejercicio mal igual.
                return Object.keys(pairs).length === targets.length ? pairs : null;
            }
            """
        )
        return {"pairs": pairs} if pairs else None

    if kind == "ordering":
        items = get_ordering_items(page)
        return {"order": items} if items else None

    if kind == "text_rewrite":
        fields = page.locator('[data-qa="inputContainer"] textarea')
        values = [fields.nth(i).input_value().strip() for i in range(fields.count())]
        return {"answers": values} if values and all(values) else None

    if kind == "cloze_drag":
        placed, _ = get_cloze_drag_state(page)
        return {"answers": placed} if placed and all(placed) else None

    if kind == "sentence_build":
        placed, loose = get_sentence_build_state(page)
        return {"order": placed} if placed and not loose else None

    if kind == "matching_audio_options":
        # Qué clip quedó en cada destino: hay que pulsar su botón de
        # escuchar para saber cuál es (los clips no tienen texto).
        targets = page.locator('[data-qa="MatchingDropTarget"]')
        buttons = [targets.nth(i).locator('[data-qa="ListenButton"]').last for i in range(targets.count())]
        _, ids = _capture_audio_from_buttons(page, buttons, with_ids=True)
        if not ids or any(i is None for i in ids):
            return None
        return {"target_for_clip": {clip: n for n, clip in enumerate(ids, start=1)}}

    return None


def go_to_next_exercise(page):
    """
    Una vez la respuesta fue correcta, el botón de SubmitButton se
    convierte en "Próxima actividad"; hacer clic en él avanza.
    """
    submit_answer(page)

import base64
import time

import config


def _capture_audio_from_buttons(page, listen_buttons):
    """
    Hace clic en cada locator de `listen_buttons` (uno por cada botón de
    escuchar, en orden) y captura el audio real de cada uno como data URI
    base64. La URL del audio no se puede descargar directamente sin el
    contexto exacto del navegador (da 500 — y a veces incluso así, de forma
    transitoria, así que hay reintentos con pausa), y el navegador cachea el
    audio (un clic repetido no siempre dispara una nueva petición de red que
    un listener "response" pueda ver) — por eso se usa page.route() para
    interceptar la petición en sí.

    Devuelve una lista del mismo largo que `listen_buttons`; una entrada
    queda None si no se pudo capturar ese audio.
    """
    data_uris = [None] * len(listen_buttons)
    current_index = {"i": None}

    def handle_route(route):
        idx = current_index["i"]
        if idx is not None and "MediumHandler" in route.request.url:
            last_response = None
            for attempt in range(5):
                if attempt > 0:
                    time.sleep(1)
                try:
                    last_response = route.fetch()
                    content_type = last_response.headers.get("content-type", "")
                    if content_type.startswith("audio/"):
                        body = last_response.body()
                        data_uris[idx] = f"data:{content_type};base64,{base64.b64encode(body).decode('utf-8')}"
                        route.fulfill(response=last_response)
                        return
                except Exception:
                    pass
            try:
                if last_response is not None:
                    route.fulfill(response=last_response)
                else:
                    route.continue_()
            except Exception:
                pass
            return
        route.continue_()

    page.route("**/MediumHandler.ashx*", handle_route)
    try:
        for i, button in enumerate(listen_buttons):
            current_index["i"] = i
            button.click()
            # Un solo clic: el handler de arriba ya reintenta la petición
            # internamente si el servidor falla (hasta 5 veces con pausa,
            # ~5s en el peor caso). Reintentar el CLIC además de eso hacía
            # que se reprodujera el mismo audio varias veces de más. La
            # espera activa solo necesita cubrir ese peor caso.
            waited = 0
            while data_uris[i] is None and waited < 8000:
                page.wait_for_timeout(200)
                waited += 200
    finally:
        page.unroute("**/MediumHandler.ashx*", handle_route)

    return data_uris


def get_choice_audio_data_uris(page, count):
    """Para un ejercicio "multiple_choice" cuyas opciones son solo audio (sin ChoiceText)."""
    choices = page.locator('[data-qa="ChoiceButton"]')
    buttons = [choices.nth(i).locator('[data-qa="ListenButton"]') for i in range(count)]
    return _capture_audio_from_buttons(page, buttons)


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
    """Desde dentro de una lección, vuelve a la página de detalle de su curso."""
    page.get_by_text("Salir de la lección", exact=True).first.click()
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
    hay que clickear para reabrir la actividad (ver click_activity).

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


def all_pending_are_speech(pending):
    """
    True si todo lo que queda pendiente requiere grabar la propia voz, es
    decir: la lección está genuinamente bloqueada y no tiene sentido
    volver a intentarla en futuras corridas. Una lista vacía NO cuenta
    como bloqueada (no queda nada pendiente, que es otra cosa).
    """
    return bool(pending) and all(a["type"] in SPEECH_ACTIVITY_TYPES for a in pending)


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
    para reabrirla (ver click_activity).

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


def click_activity(page, status_qa):
    """
    Hace clic en el hijo de estado ("Omitida"/"Vuelva a intentarlo") de una
    actividad del panel lateral, identificado por su `data-qa` completo
    (ver get_flagged_activity_ids) — reabre esa actividad de verdad.

    Confirmado en vivo: reabrir una actividad desde el sidebar puede
    disparar el modal de habla ("Habilitar actividades de habla") de
    nuevo, incluso si ya se había descartado antes en la misma sesión.
    Playwright interpreta el modal como un overlay transitorio y reintenta
    el clic en bucle hasta agotar el timeout (30s) en vez de fallar rápido
    o detectar que hay que descartarlo primero.
    """
    locator = page.locator(f'[data-qa="{status_qa}"]').first
    try:
        locator.click(timeout=5000)
    except Exception:
        if has_speech_modal(page):
            dismiss_speech_modal(page)
        locator.click(force=True)


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
    return page.get_by_text("Lectura en voz alta", exact=True).count() > 0


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
            option_audio_urls = (
                get_choice_audio_data_uris(page, choices.count())
                if capture_audio
                else [None] * choices.count()
            )
            if any(url is None for url in option_audio_urls):
                unsolvable = True
            return {
                "type": "multiple_choice",
                "prompt": prompt,
                "options": [],
                "option_count": choices.count(),
                "option_audio_urls": [] if unsolvable else option_audio_urls,
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

    raise NotImplementedError(
        "Tipo de ejercicio no reconocido o aún no mapeado "
        "(soportados: 'multiple_choice', 'matching', 'cloze_dropdown', 'ordering')."
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
    locator.first.click()


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
    page.locator('[data-qa="ClozeInput"]').nth(blank_index - 1).fill(text)
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


def _drag_ordering_item(page, source_locator, target_locator):
    source_box = source_locator.bounding_box()
    target_box = target_locator.bounding_box()
    page.mouse.move(source_box["x"] + source_box["width"] / 2, source_box["y"] + source_box["height"] / 2)
    page.mouse.down()
    page.mouse.move(
        target_box["x"] + target_box["width"] / 2,
        target_box["y"] + target_box["height"] / 2,
        steps=10,
    )
    page.mouse.up()
    page.wait_for_timeout(400)


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
    max_moves = len(target_order) * len(target_order) + 5
    for _ in range(max_moves):
        current = get_ordering_items(page)
        if current == target_order:
            return True
        for i, wanted_text in enumerate(target_order):
            if current[i] != wanted_text:
                src_index = current.index(wanted_text)
                items = page.locator('[data-qa="DraggableSentenceItem"]')
                _drag_ordering_item(page, items.nth(src_index), items.nth(i))
                break
    return get_ordering_items(page) == target_order


def write_answer(page, answer):
    raise NotImplementedError(
        "Pendiente: tipo de ejercicio de texto libre aún no encontrado/mapeado."
    )


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
    Devuelve "correct", "incorrect" o None si aún no se envió respuesta.
    """
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


def is_answer_revealed(page):
    """
    Tras fallar suficientes veces en un ejercicio, Rosetta resalta/marca
    directamente la respuesta correcta y lo indica con un aviso "Esta es
    la respuesta correcta.", dejando avanzar sin necesidad de acertar.
    Detectarlo evita gastar otro intento de IA que de todos modos no
    haría falta (la respuesta ya quedó aplicada por la propia página).
    """
    return page.get_by_text("Esta es la respuesta correcta.", exact=True).count() > 0


def go_to_next_exercise(page):
    """
    Una vez la respuesta fue correcta, el botón de SubmitButton se
    convierte en "Próxima actividad"; hacer clic en él avanza.
    """
    submit_answer(page)

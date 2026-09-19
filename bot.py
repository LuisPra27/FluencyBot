import json
import os
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

import browser
import ai

# La consola de Windows no siempre usa UTF-8 por defecto: un print() con un
# carácter que no existe en su codepage (ej. "→" en el razonamiento de la
# IA) lanza UnicodeEncodeError y tira todo el intento en vez de solo verse
# mal. Reconfigurar a UTF-8 con reemplazo evita que un simple print rompa
# nada.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


class _Tee:
    """
    Duplica todo lo que se escribe en la consola a un archivo de log, con
    la hora al principio de cada línea (solo en el archivo; la consola se
    ve igual que siempre).

    Se hace a nivel de stdout/stderr en vez de cambiar cada print() para
    que el log tenga TODO: los mensajes del bot, el razonamiento de la IA y
    los tracebacks de errores inesperados.

    Se vacía al disco en cada escritura a propósito: confirmado en esta
    misma historia que con la salida en buffer, detener el bot a mano
    perdía el log entero justo cuando más se necesitaba leerlo.
    """

    def __init__(self, stream, log_file):
        self._stream = stream
        self._log = log_file
        self._at_line_start = True

    def write(self, text):
        self._stream.write(text)
        self._stream.flush()
        for piece in text.splitlines(keepends=True):
            if self._at_line_start and piece.strip():
                self._log.write(time.strftime("[%H:%M:%S] "))
            self._log.write(piece)
            self._at_line_start = piece.endswith("\n")
        self._log.flush()
        return len(text)

    def flush(self):
        self._stream.flush()
        self._log.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


def _start_logging():
    """
    Abre logs/bot_<fecha>_<hora>.log y redirige ahí una copia de toda la
    salida. Un archivo por corrida, para poder comparar corridas. Se llama
    solo al ejecutar bot.py directamente, no al importarlo (los scripts de
    prueba importan bot y no deben ir dejando logs sueltos).
    """
    os.makedirs(LOGS_DIR, exist_ok=True)
    path = os.path.join(LOGS_DIR, time.strftime("bot_%Y-%m-%d_%H-%M-%S.log"))
    log_file = open(path, "a", encoding="utf-8", errors="replace")
    sys.stdout = _Tee(sys.stdout, log_file)
    sys.stderr = _Tee(sys.stderr, log_file)
    print(f"Log de esta corrida: {path}")
    return path


MAX_ATTEMPTS = 3
MAX_SKIPS = 10
MAX_RETRY_ROUNDS = 5

# Cuántas veces seguidas puede fallar una lección por algo que NO es voz
# antes de darla por perdida. Un fallo puntual (un flake de navegación, un
# modelo de IA caído, un tipo de ejercicio que todavía no se soportaba) no
# debe condenar la lección para siempre: se reintenta en la próxima corrida.
MAX_LESSON_FAILURES = 3

# Tope de pantallas a trabajar dentro de UNA actividad. Casi todas tienen
# una sola, pero "Escriba la respuesta" muestra "1 de 4 pasos" en el pie:
# hay que resolver los cuatro o la actividad queda incompleta. El tope es
# solo una red de seguridad para no colgarse si algo nunca avanza.
MAX_ACTIVITY_STEPS = 12

BLOCKED_LESSONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blocked_lessons.json")
KNOWN_ANSWERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "known_answers.json")
SPEECH_ACTIVITIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "speech_activities.json")

# Motivos por los que no hay que volver a entrar a una lección.
#   speech    -> lo único pendiente requiere grabar la propia voz.
#   completed -> el panel lateral confirma que está TODA resuelta, pero el
#                contador de Rosetta sigue diciendo que falta algo (ver
#                main()). Definitivo igual que "speech": el panel es la
#                fuente de verdad, el contador no.
#   failed    -> quedó algo pendiente que no es de voz; se reintenta.
BLOCKED_SPEECH = "speech"
BLOCKED_DONE = "completed"
BLOCKED_FAILED = "failed"

# Memoria de ESTE proceso, que sobrevive a los reinicios de main().
#
# El bot reinicia main() desde cero tras un error inesperado. Antes, todo lo
# que se sabía de la corrida vivía dentro de main() y se perdía en cada
# reinicio: se volvía a entrar a las lecciones ya intentadas y, peor, a cada
# lección "failed" se le sumaba otro fallo. Tres caídas bastaban para dejar
# TODAS las lecciones reintentables bloqueadas para siempre — confirmado en
# blocked_lessons.json: 39 de 42 en failures=3, muchas con pendientes que el
# bot sí sabe resolver. El contador de fallos estaba contando reinicios, no
# intentos reales.
_SESSION_ATTEMPTED = set()   # claves "curso::lección" ya intentadas en este proceso
_SESSION_COURSE_HINT = [0]   # curso donde se encontró la última lección pendiente


def _load_blocked_lessons():
    """
    Estado por lección bloqueada, indexado por clave "curso::lección"
    (ej. "Speak with Pilots and Airline Mechanics (B1)::Preflight"):

        {"reason": "speech"|"completed"|"failed", "failures": int, "pending": [str, ...]}

    **Por qué esto dejó de ser una lista plana**: antes cualquier
    resultado que no fuera "completado" —una actividad de voz, un
    ejercicio que la IA no supo, o un simple timeout de navegación— metía
    la lección en el mismo archivo y la excluía PARA SIEMPRE, sin guardar
    el motivo. Eso convirtió el archivo en la cicatriz de todos los bugs
    pasados en vez de una lista real: durante el apagón del modelo
    `muse-glimmer-30b` (404 en toda llamada, ver ai.py) cada lección que
    se intentó quedó marcada, y ahí siguen decenas que el bot sí puede
    hacer hoy. Con el motivo guardado, "speech" y "completed" son
    definitivos; "failed" se reintenta hasta MAX_LESSON_FAILURES veces.

    Lee también el formato viejo (lista de claves) y lo migra tratando
    esas entradas como fallos sin confirmar, para que se revaliden en vez
    de heredar el bloqueo a ciegas.
    """
    if not os.path.exists(BLOCKED_LESSONS_FILE):
        return {}
    with open(BLOCKED_LESSONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        print(
            f"blocked_lessons.json está en el formato viejo ({len(data)} lección(es) sin motivo "
            "guardado); se revalidarán en vez de darlas por bloqueadas."
        )
        return {key: {"reason": BLOCKED_FAILED, "failures": 0, "pending": []} for key in data}

    return data


def _save_blocked_lessons(blocked):
    with open(BLOCKED_LESSONS_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(blocked.items())), f, indent=2, ensure_ascii=False)


def _mark_blocked(blocked, key, reason, pending=(), lesson_path=None, count_failure=True):
    """
    Registra por qué no hay que volver a entrar a una lección. "speech" y
    "completed" son definitivos y no acumulan fallos; solo "failed" suma un
    intento y se vuelve definitivo al llegar al tope.

    count_failure=False: la lección no quedó completa, pero el intento SÍ
    avanzó (aprendió respuestas que la próxima pasada puede usar). Contarlo
    como fallo sería castigar justo el intento que más acerca al objetivo.

    lesson_path (`course/<curso>/<lección>`) se guarda para poder cruzar la
    lección con known_answers.json, cuyas claves usan esa ruta y no el título.
    """
    previous = blocked.get(key, {})
    previous_failures = previous.get("failures", 0)
    if reason != BLOCKED_FAILED:
        failures = 0
    elif count_failure:
        failures = previous_failures + 1
    else:
        failures = previous_failures
    blocked[key] = {
        "reason": reason,
        "failures": failures,
        "pending": sorted({a["type"] for a in pending}),
        "lesson_path": lesson_path or previous.get("lesson_path"),
    }
    _save_blocked_lessons(blocked)
    return blocked[key]


def _permanently_blocked_keys(blocked, known_answers=None):
    """
    Las que de verdad no hay que volver a intentar: las de voz, las ya
    confirmadas como resueltas por el panel lateral (aunque el contador de
    Rosetta siga desincronizado), y las que ya agotaron sus reintentos.
    El resto se vuelve a probar — revalidarlas
    cuesta una navegación y cero llamadas a la IA, mucho menos que dejar
    lecciones perfectamente resolubles marcadas para siempre.

    Excepción al tope de fallos: si hay respuestas guardadas para esa
    lección que todavía no se usaron, se vuelve a intentar igual. Tener la
    respuesta a mano y no usarla es exactamente lo que no puede pasar.
    """
    if known_answers is None:
        known_answers = _load_known_answers()
    answer_keys = list(known_answers)

    def has_unused_answers(state):
        path = state.get("lesson_path")
        return bool(path) and any(k.startswith(path + "/") for k in answer_keys)

    return {
        key
        for key, state in blocked.items()
        if state.get("reason") in (BLOCKED_SPEECH, BLOCKED_DONE)
        or (state.get("failures", 0) >= MAX_LESSON_FAILURES and not has_unused_answers(state))
    }


def _load_speech_ids():
    """
    Ids de actividades cuya pantalla exige hablar aunque su TIPO no lo diga
    (ej. un "Llene los espacios en blanco" que pide "diga la oración
    completa"). Sin recordarlas, esas lecciones nunca podían darse por
    bloqueadas por voz y se reintentaban en cada corrida.
    """
    if not os.path.exists(SPEECH_ACTIVITIES_FILE):
        return set()
    try:
        with open(SPEECH_ACTIVITIES_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except (json.JSONDecodeError, OSError):
        return set()


def _remember_speech_activity(activity_id):
    ids = _load_speech_ids()
    if activity_id not in ids:
        ids.add(activity_id)
        with open(SPEECH_ACTIVITIES_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(ids), f, indent=2)


def _load_known_answers():
    """
    Respuestas que Rosetta ya nos enseñó, indexadas por
    `browser.get_exercise_key()` (la ruta del ejercicio dentro del curso).

    **Por qué existe**: confirmado en vivo que la revelación NO da crédito
    — un ejercicio que llega a "Mostrar respuesta" queda mal igual. La
    única forma de arreglarlo es reabrir la actividad desde el panel
    lateral, pero ahí la IA volvía a adivinar a ciegas con los mismos dos
    intentos, así que lo más probable era volver a fallar. Guardando lo
    que Rosetta enseñó, la reapertura pasa a ser un acierto seguro y sin
    gastar ni una llamada a la IA.

    Se guarda la solución con el mismo shape que devuelve
    ai.solve_exercise(), para poder pasársela tal cual a apply_solution().
    """
    if not os.path.exists(KNOWN_ANSWERS_FILE):
        return {}
    try:
        with open(KNOWN_ANSWERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"(no se pudo leer {KNOWN_ANSWERS_FILE}: {e}; empiezo sin respuestas guardadas)")
        return {}


def _save_known_answers(answers):
    with open(KNOWN_ANSWERS_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(answers.items())), f, indent=2, ensure_ascii=False)


def _remember_answer(key, solution):
    answers = _load_known_answers()
    answers[key] = solution
    _save_known_answers(answers)


def _forget_answer(key):
    """
    Una respuesta guardada solo sirve hasta que el ejercicio queda bien: a
    partir de ahí ocupa espacio sin aportar nada (y si estaba equivocada,
    peor). Se borra en cuanto cumple su función.
    """
    answers = _load_known_answers()
    if answers.pop(key, None) is not None:
        _save_known_answers(answers)


# --- Instrumentación temporal para verificar en vivo que solo se omiten
# actividades de habla (ver run_lesson) --- #
_DEBUG_OMIT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_omits")
_debug_omit_count = 0


def _debug_screenshot_omit(page, lesson_title):
    global _debug_omit_count
    _debug_omit_count += 1
    os.makedirs(_DEBUG_OMIT_DIR, exist_ok=True)
    safe_title = "".join(c if c.isalnum() else "_" for c in lesson_title)[:40]
    path = os.path.join(_DEBUG_OMIT_DIR, f"{_debug_omit_count:03d}_{safe_title}.png")
    try:
        page.screenshot(path=path)
        print(f"  (captura de depuración guardada: {path})")
    except Exception as e:
        print(f"  (no se pudo guardar captura de depuración: {e})")


def _try_save_error_screenshot(page):
    """
    Best-effort: si el navegador/página ya se cerró (ej. el propio error
    fue justamente que se cerró inesperadamente), intentar leer page.url
    o tomar la captura también falla — sin este try/except ese segundo
    fallo se escapaba de main() sin capturar y tumbaba todo el wrapper de
    reintentos en vez de solo reportar el error original y reiniciar.
    """
    try:
        print("URL actual:", page.url)
    except Exception:
        print("(no se pudo leer la URL: la página ya no está disponible)")
    try:
        page.screenshot(path="error.png", full_page=True)
        print("Captura guardada como error.png")
    except Exception as e:
        print(f"(no se pudo guardar la captura de error: {e})")


def _wait_for_advance(page, timeout_ms=8000, poll_ms=500):
    """
    Sondea cada poll_ms (hasta timeout_ms) si ya apareció el modal de habla,
    un ejercicio reconocible, o un botón de avance (SubmitButton/
    StartLessonButton). Las transiciones entre pantallas a veces tardan más
    de lo esperado; una sola espera fija no siempre alcanza. Devuelve True
    si apareció algo por lo que vale la pena reintentar, False si de verdad
    no hay nada tras esperar.
    """
    elapsed = 0
    while elapsed < timeout_ms:
        if browser.has_speech_modal(page):
            return True
        if page.locator('[data-qa="SubmitButton"], [data-qa="StartLessonButton"]').count() > 0:
            return True
        try:
            # Solo interesa SI hay un ejercicio, no cuál: sin capture_audio
            # esto se repetiría bajando el audio entero en cada sondeo.
            browser.get_current_exercise(page, capture_audio=False)
            return True
        except NotImplementedError:
            pass
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    return False


def apply_solution(page, exercise, solution):
    exercise_type = exercise["type"]

    if exercise_type == "multiple_choice":
        browser.click_option(page, solution["answer"])

    elif exercise_type == "cloze_dropdown":
        for blank_index, answer in enumerate(solution["answers"][:len(exercise["blanks"])], start=1):
            browser.select_cloze_option(page, blank_index, answer)

    elif exercise_type == "cloze_input":
        # Solo se rellenan los espacios que existen. Confirmado en vivo: para
        # un ejercicio de UN solo espacio la IA devolvió dos respuestas
        # (['over', 'past']), el bot fue a buscar un segundo campo que no
        # existe, esperó 30 s y el timeout tiró la lección entera.
        answers = solution["answers"]
        if len(answers) != exercise["blank_count"]:
            print(f"  (aviso: la IA dio {len(answers)} respuesta(s) para {exercise['blank_count']} espacio(s); uso solo las necesarias)")
        for blank_index, text in enumerate(answers[:exercise["blank_count"]], start=1):
            browser.fill_cloze_input(page, blank_index, text)

    elif exercise_type == "text_input":
        browser.write_answer(page, solution["answer"])

    elif exercise_type == "text_rewrite":
        browser.fill_text_rewrite(page, solution["answers"])

    elif exercise_type == "cloze_drag":
        if not browser.fill_cloze_drag(page, solution["answers"]):
            print("  (aviso: no se lograron llenar todos los huecos arrastrando)")

    elif exercise_type == "sentence_build":
        if not browser.build_sentence(page, solution["order"]):
            print("  (aviso: la oración no quedó exactamente como se pidió)")

    elif exercise_type == "matching_audio_options":
        ids = exercise.get("option_audio_ids") or []
        mapping = solution["target_for_clip"]
        if any(k.startswith("#") for k in mapping):
            ids = [f"#{i}" for i in range(len(ids))]
        if not browser.place_matching_audio_options(page, ids, mapping):
            print("  (aviso: no se lograron colocar todos los clips)")

    elif exercise_type == "matching":
        for word, target_index in solution["pairs"].items():
            browser.drag_matching_pair(page, word, target_index)

    elif exercise_type == "ordering":
        if not browser.reorder_items(page, solution["order"]):
            # No es un fallo de la respuesta sino de colocarla: se envía
            # igual (no hay otra forma de seguir), pero que quede claro en
            # el log que un "incorrect" aquí no significa que la respuesta
            # estuviera mal.
            print("  (aviso: no se logró dejar los ítems en el orden pedido; lo que se envía NO es esa respuesta)")

    else:
        raise NotImplementedError(f"No se sabe aplicar el tipo de ejercicio '{exercise_type}'")


def resolve_current_exercise(page, exercise, max_attempts=MAX_ATTEMPTS):
    """
    Resuelve un ejercicio ya detectado (ver browser.get_current_exercise),
    reintentando con la IA hasta max_attempts veces si falla. En cada
    reintento se le pasan a la IA las soluciones previas que ya fallaron,
    para que no las repita.

    Nota: el reintento reutiliza submit_answer() para el clic de "Volver a
    intentar" (mismo botón que enviar/avanzar). Confirmado que esto resetea
    la selección en 'multiple_choice'; para 'matching'/'cloze_dropdown' se
    asume el mismo comportamiento pero aún no se verificó en vivo.

    Ciclo completo, con memoria de lo que Rosetta enseñó:

      1. ¿Hay respuesta guardada de este ejercicio? Se aplica directo, sin
         gastar una llamada a la IA.
      2. Si no, se le pregunta a la IA (hasta max_attempts veces).
      3. Agotados los intentos, el botón pasa a "Mostrar respuesta": se
         pulsa a propósito, se lee la solución y se guarda.
      4. El ejercicio queda mal igual (la revelación no da crédito), pero
         al reabrir la actividad desde el panel ya se responde de memoria.
      5. Una vez correcto, la respuesta guardada se borra.

    Devuelve "correct", "incorrect", "revealed" (se falló pero ya se sabe
    la respuesta para la próxima) o None.
    """
    print("Ejercicio detectado:", exercise)

    previous_attempts = []
    feedback = None
    key = browser.get_exercise_key(page)

    remembered = _load_known_answers().get(key) if key else None
    if remembered is not None:
        to_apply = _locate_remembered(exercise, remembered)
        print(f"Respuesta ya conocida de este ejercicio: {to_apply} (sin gastar IA)")
        apply_solution(page, exercise, to_apply)
        browser.submit_answer(page)
        if browser.wait_for_feedback(page) == "correct":
            browser.go_to_next_exercise(page)
            page.wait_for_timeout(1500)
            _forget_answer(key)
            return "correct"
        # Guardada pero equivocada (mal leída, o el ejercicio cambió):
        # no sirve de nada conservarla, y dejarla haría fallar cada
        # reapertura igual. Se borra y se sigue con la IA normalmente.
        print("La respuesta guardada no funcionó; la borro y sigo con la IA.")
        _forget_answer(key)
        # Ya se probó y falló: que la IA no la repita (confirmado en vivo que
        # sin esto proponía justo la misma opción que acababa de fallar).
        previous_attempts.append(remembered)
        if browser.get_action_button_label(page) == "Volver a intentar":
            browser.submit_answer(page)
            page.wait_for_timeout(1000)

    for attempt in range(1, max_attempts + 1):
        # Tras un par de fallos, Rosetta a veces revela la respuesta
        # correcta apenas se carga la pantalla de "Volver a intentar" —
        # ANTES de tocar nada — y en ese estado los controles (ej. los
        # dropdowns de 'cloze_dropdown') ya no responden normalmente:
        # intentar aplicar otra solución ahí cuelga 30s hasta el timeout
        # de Playwright. Hay que revisar esto antes de intentar aplicar
        # cualquier solución, no solo después de enviarla.
        if browser.is_answer_revealed(page):
            print("Rosetta ya tenía la respuesta revelada en pantalla; la guardo y avanzo.")
            return _capture_revealed_and_advance(page, exercise, key)

        # Mismo problema, distinta señal: "Escriba la respuesta" agota sus
        # intentos dejando el campo deshabilitado sin mostrar el aviso que
        # busca is_answer_revealed(). Intentar escribir ahí se cuelga
        # esperando a que el campo se habilite, y encima gasta una llamada
        # a la IA para nada. Si ya no se puede interactuar, lo único que
        # queda es avanzar.
        if browser.exercise_is_locked(page):
            print("El ejercicio ya no acepta interacción (Rosetta lo dio por cerrado); avanzando.")
            browser.go_to_next_exercise(page)
            page.wait_for_timeout(1500)
            return feedback or "incorrect"

        try:
            solution = ai.solve_exercise(exercise, previous_attempts=previous_attempts)
        except Exception as e:
            # Un modelo puede devolver basura no-JSON (ej. el modelo de
            # audio a veces alucina y se queda repitiendo hasta agotar
            # tokens). Que cuente como intento fallido normal, no que tumbe
            # todo el ejercicio.
            print(f"Intento {attempt}/{max_attempts} - la IA no devolvió una solución válida: {str(e)[:160]}")
            # Sin solución de la IA el intento no llega a Rosetta, y sin
            # intentos fallidos Rosetta nunca ofrece "Mostrar respuesta":
            # el bot se quedaba sin aprender nada. Si el tipo lo permite, se
            # intenta a ciegas para que el ciclo siga hasta la revelación.
            try:
                solution = ai._blind_guess(exercise, previous_attempts)
                print(f"  (intento a ciegas para poder avanzar hasta la respuesta revelada: {solution})")
            except NotImplementedError:
                feedback = "incorrect"
                if attempt < max_attempts:
                    continue
                return feedback

        print(f"Intento {attempt}/{max_attempts} - Solución de la IA:", solution)

        url_before = page.url
        apply_solution(page, exercise, solution)
        label_before = browser.get_action_button_label(page)
        if label_before == "Omitir":
            # Si tras aplicar la respuesta el botón sigue diciendo "Omitir",
            # la respuesta NO quedó puesta (ej. un hueco sin rellenar al
            # arrastrar). Pulsarlo no enviaría nada: SALTARÍA la actividad
            # entera, dejándola "Omitida" (confirmado en vivo). Mejor no
            # tocarlo y que la pasada siguiente lo reintente.
            print("  (la respuesta no quedó completa en pantalla; NO pulso 'Omitir' para no saltar la actividad)")
            return "incorrect"
        browser.submit_answer(page)

        feedback = browser.wait_for_feedback(page)
        if (
            feedback is None
            and not browser.is_answer_revealed(page)
            and page.url == url_before
            and browser.get_action_button_label(page) == label_before
        ):
            # Red de seguridad: el botón de enviar es un <div>, no un
            # <button disabled> real, así que un clic puede caer como
            # no-op silencioso si React todavía no había registrado el
            # cambio (confirmado en vivo con "cloze_input": el texto
            # quedaba escrito pero nunca se enviaba).
            #
            # Pero re-enviar a ciegas es peligroso: si el primer clic SÍ
            # había funcionado y el feedback solo tardó, el segundo clic
            # cae sobre "Volver a intentar"/"Próxima actividad" y avanza de
            # paso. En una actividad de varios pasos eso salta preguntas
            # enteras sin responderlas — confirmado en vivo: el bot pasó
            # del paso 1 al 4 de una "Escriba la respuesta". Por eso solo
            # se reintenta si NADA cambió: misma URL y el botón sigue
            # diciendo exactamente lo mismo que antes del clic.
            browser.submit_answer(page)
            feedback = browser.wait_for_feedback(page)
        print("Resultado:", feedback)

        if page.url != url_before:
            # Rosetta avanzó de paso por su cuenta: este ejercicio ya no
            # está en pantalla, así que no tiene sentido seguir intentando
            # (ni reintentar sobre lo que ahora es otra pregunta).
            return feedback or "incorrect"

        if feedback == "correct":
            browser.go_to_next_exercise(page)
            page.wait_for_timeout(1500)
            if key:
                _forget_answer(key)
            return feedback

        if browser.is_answer_revealed(page):
            return _capture_revealed_and_advance(page, exercise, key)

        previous_attempts.append(solution)

        # Se agotaron los intentos reales y Rosetta ofrece enseñar la
        # respuesta: pulsarlo a propósito para poder leerla y guardarla.
        # El ejercicio queda mal igual (la revelación no da crédito), pero
        # al reabrir la actividad se responderá de memoria y sin IA.
        if browser.can_show_answer(page):
            print("Se agotaron los intentos; pulso \"Mostrar respuesta\" para aprenderla.")
            browser.submit_answer(page)
            page.wait_for_timeout(1500)
            return _capture_revealed_and_advance(page, exercise, key)

        if attempt < max_attempts:
            # Solo clickear si el botón de verdad ofrece reintentar. Si dice
            # otra cosa ("Próxima actividad", "Omitir"), el clic avanzaría
            # de paso en vez de resetear la vista — y en una actividad de
            # varios pasos eso salta preguntas sin responderlas.
            label = browser.get_action_button_label(page)
            if label != "Volver a intentar":
                print(f"Incorrecto, pero el botón dice {label!r} (ya no se puede reintentar aquí); sigo.")
                return feedback
            print("Incorrecto, reintentando...")
            browser.submit_answer(page)  # "Volver a intentar": resetea la vista
            page.wait_for_timeout(1000)

    return feedback


def _locate_remembered(exercise, remembered):
    """
    Adapta una respuesta guardada a cómo está la pantalla AHORA.

    Opción múltiple de solo audio: Rosetta baraja el orden de las opciones
    en cada apertura, así que la posición guardada ya no sirve. Confirmado
    en vivo: tres respuestas guardadas seguidas fallaron y cada revelación
    daba una posición distinta. Se busca en qué posición está hoy el clip
    que se guardó como correcto.
    """
    audio_id = remembered.get("answer_audio_id")
    ids = exercise.get("option_audio_ids") or []
    if audio_id and audio_id in ids:
        now = ids.index(audio_id) + 1
        if now != remembered.get("answer"):
            print(f"  (las opciones se barajaron: la correcta pasó de la posición {remembered.get('answer')} a la {now})")
        return {**remembered, "answer": now}
    return remembered


def _capture_revealed_and_advance(page, exercise, key):
    """
    Con la respuesta revelada en pantalla: leerla, guardarla para la
    próxima vez que se reabra esta actividad, y avanzar.

    Devuelve "revealed", NO "correct": confirmado en vivo que la
    revelación no da crédito — el ejercicio queda mal en el panel lateral.
    Antes esto devolvía "correct" y el bot reportaba como resuelto algo que
    en realidad había fallado.
    """
    solution = browser.get_revealed_answer(page, exercise)
    if solution is not None and key:
        _remember_answer(key, solution)
        print(f"Respuesta aprendida y guardada para la próxima: {solution}")
    elif solution is None:
        print(f"Rosetta reveló la respuesta pero no se pudo leer del tipo '{exercise['type']}'.")

    browser.go_to_next_exercise(page)
    page.wait_for_timeout(1500)
    return "revealed"


def _wait_for_activity_screen(page, timeout_ms=8000, poll_ms=500):
    """
    Tras saltar a una actividad desde el panel lateral, la pantalla tarda
    en montarse: justo después del clic puede no haberse detectado todavía
    ni el video, ni el contenido paginado, ni el ejercicio (confirmado en
    vivo saltando a una "Explicación" nunca abierta: al instante siguiente
    la pantalla no era reconocible como nada). Sondea hasta que aparezca
    algo con lo que trabajar. Devuelve True si apareció.
    """
    elapsed = 0
    while elapsed < timeout_ms:
        if (
            browser.has_speech_modal(page)
            or browser.requires_speech(page)
            or browser.has_read_aloud_activity(page)
            or browser.has_video(page)
            or browser.has_paginated_content(page)
        ):
            return True
        try:
            browser.get_current_exercise(page, capture_audio=False)
            return True
        except NotImplementedError:
            pass
        page.wait_for_timeout(poll_ms)
        elapsed += poll_ms
    return False


def _current_activity_index(page):
    """
    Dentro de una lección la URL es `…/<lección>/<actividad>/<paso>` (ej.
    `…/the-perfect-job-part-i/11/1`). Devuelve el número de actividad, o
    None si la URL no tiene esa forma (ej. `…/summary`). Sirve para saber
    si seguimos en la MISMA actividad tras resolver un paso.
    """
    parts = page.url.rstrip("/").split("/")
    if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
        return parts[-2]
    return None


def _work_single_activity(page, activity):
    """
    Trabaja la actividad que está abierta en pantalla ahora mismo, sea del
    tipo que sea. Devuelve True si resolvió correctamente algún ejercicio.

    Es un bucle, no un if/elif de un solo paso, por dos motivos:

    * Más de una condición puede aplicar en secuencia para la MISMA
      actividad (ej. abrir una Demostración puede mostrar el modal de habla
      ANTES de llegar al video). Confirmado en vivo: con un if/elif de un
      solo paso, al descartar el modal se pasaba directo a la SIGUIENTE
      actividad sin llegar a ver el video de esta.
    * Una actividad puede tener VARIOS pasos, cada uno una pantalla aparte
      ("Escriba la respuesta" muestra "1 de 4 pasos" en el pie). Resolver
      solo el primero la dejaba incompleta, así que se sigue mientras la
      URL diga que seguimos en la misma actividad.
    """
    activity_index = _current_activity_index(page)
    solved_any = False

    for _ in range(MAX_ACTIVITY_STEPS):
        if browser.has_speech_modal(page):
            browser.dismiss_speech_modal(page)
            page.wait_for_timeout(500)
            continue

        if browser.requires_speech(page):
            _remember_speech_activity(activity["id"])
            print(f"  '{activity['type']}': la pantalla exige hablar (botón de micrófono); se omite a propósito.")
            _click_advance(page)
            return solved_any

        if browser.has_read_aloud_activity(page):
            # Requiere grabarse leyendo: es lo único que se acepta omitir.
            print(f"  '{activity['type']}': es lectura en voz alta (requiere grabarse); se omite a propósito.")
            _click_advance(page)
            return solved_any

        if browser.has_video(page):
            if not browser.video_is_watched(page):
                browser.skip_video(page)
            # El <video> sigue en el DOM aunque ya se haya visto completo
            # (ver browser.video_is_watched), así que NO se puede hacer
            # "continue" aquí: has_video() seguiría dando True para siempre
            # y nunca se llegaría a hacer clic en el botón de avance. Justo
            # al terminar el video, Rosetta puede mostrar el modal de habla
            # encima de ese botón — se descarta antes de intentar el clic.
            for _ in range(3):
                if not browser.has_speech_modal(page):
                    break
                browser.dismiss_speech_modal(page)
                page.wait_for_timeout(500)
            print(f"  '{activity['type']}': video visto hasta el final; avanzo.")
            _click_advance(page)
            return solved_any

        if browser.has_paginated_content(page):
            # Vocabulario/Explicación: paginar de verdad para que quede
            # "Completa" en vez de "Omitida".
            pages = 0
            for _ in range(100):
                if not browser.advance_paginated_content(page):
                    break
                pages += 1
            print(f"  '{activity['type']}': contenido paginado recorrido ({pages} página(s)); avanzo.")
            _click_advance(page)
            return solved_any

        try:
            exercise = browser.get_current_exercise(page)
        except NotImplementedError:
            # Pantalla no reconocida (ej. Objetivos, o un video ya visto
            # esperando el clic de avance): avanzar igual que hace el
            # recorrido lineal.
            print(f"  '{activity['type']}': pantalla no reconocida como ejercicio ({page.url.split('/course/')[-1]}); avanzo SIN resolver.")
            _debug_screenshot_omit(page, activity['type'])
            _click_advance(page)
            return solved_any
        else:
            url_before = page.url
            outcome = resolve_current_exercise(page, exercise)
            if outcome == "correct":
                solved_any = True
            elif page.url == url_before and outcome != "revealed":
                # No avanzó y no aprendió nada: insistir aquí repetiría lo
                # mismo (confirmado en vivo: la misma pantalla se reintentó
                # 12 veces seguidas gastando una llamada a la IA cada vez).
                # La siguiente pasada la volverá a intentar desde cero.
                return solved_any
            # Actividad de varios pasos ("1 de 4 pasos"): seguir mientras
            # la URL diga que seguimos en la misma. Si cambió de actividad
            # (o ya no estamos dentro de una), esta ya quedó terminada.
            now = _current_activity_index(page)
            if now != activity_index:
                print(f"  (fin de la actividad {activity_index}; la pantalla pasó a {now} — {page.url})")
                return solved_any

    return solved_any


def _click_advance(page):
    """Clic en el botón de avance/omitir, si está."""
    button = page.locator('[data-qa="SubmitButton"], [data-qa="StartLessonButton"]')
    if button.count() == 0:
        return False
    button.first.click()
    page.wait_for_timeout(1500)
    return True


def work_pending_activities(page, lesson_title):
    """
    Hace una pasada por TODO lo que falta de la lección saltando directo a
    cada actividad desde el panel lateral, sin recorrer la lección entera.
    Debe llamarse estando en el resumen (ver browser.go_to_lesson_summary).

    Esto sirve para dos cosas a la vez:

    1. **Lecciones a medias**: en vez de entrar y pasar de largo por decenas
       de actividades ya hechas solo porque falta una del final, se va
       directo a las que faltan. "Reanudar" siempre reinicia desde el paso
       1, así que sin esto el coste de arreglar la última actividad de una
       lección era recorrerla entera.
    2. **Reintentar lo que quedó mal**: confirmado en vivo que Rosetta deja
       reabrir una actividad "Omitida"/"Vuelva a intentarlo" desde el panel
       y da un juego fresco de intentos, así que lo que falló antes no
       queda así para siempre.

    Las actividades de voz se saltan a propósito (es lo único que el
    usuario aceptó dejar sin resolver) y ni se abren, para no perder tiempo.

    **Historial de bugs reales aquí, todos encontrados en vivo**: la
    primera versión usaba `.first` sobre el texto visible sin registrar qué
    ya se había intentado, y se quedaba pegada reintentando el mismo item
    para siempre. Luego se intentó cortar al detectar una URL repetida,
    pero eso hacía que un solo item no arreglable al principio abortara
    toda la pasada. La solución es la de ahora: tomar la lista de
    actividades UNA vez al principio y recorrerla por su id único y
    estable, así cada una se intenta exactamente una vez sin importar qué
    se arregle en el camino.

    Devuelve en cuántas ACTIVIDADES se resolvió correctamente al menos un
    ejercicio. Ojo: es por actividad, no por ejercicio (una actividad de
    varios pasos cuenta una sola vez), y los arreglos de video y de
    contenido paginado no pasan por resolve_current_exercise() así que no
    se cuentan. Quien llama NO debe usar este número para decidir si vale
    otra pasada — para eso hay que volver a contar los pendientes reales en
    el resumen (ver run_lesson).
    """
    pending = browser.get_pending_activities(page)
    speech_ids = _load_speech_ids()
    workable = [a for a in pending if not browser.is_speech_activity(a, speech_ids)]
    speech = len(pending) - len(workable)

    if not workable:
        return 0

    print(
        f"'{lesson_title}': {len(workable)} actividad(es) pendientes"
        + (f" (+{speech} de voz que se omiten a propósito)" if speech else "")
        + "; saltando directo a cada una..."
    )
    fixed = 0

    for activity in workable:
        # Confirmado en vivo (el bug real detrás de por qué una Demostración
        # "Omitida" nunca se lograba reabrir): si el modal de habla ya está
        # abierto ANTES del clic, bloquea TODA interacción con la página de
        # fondo — el clic en el panel simplemente no hacía nada, ni con
        # force=True, y la URL nunca cambiaba. Hay que descartarlo primero,
        # igual que haría una persona.
        if browser.has_speech_modal(page):
            browser.dismiss_speech_modal(page)
            page.wait_for_timeout(500)

        # Una actividad que ya no exista con ese data-qa (el sufijo cambia
        # en cuanto cambia el estado) hace fallar el clic Y el force=True de
        # respaldo. Sin este try, esa excepción se escapaba hasta el handler
        # genérico de main() y tumbaba la corrida entera por UNA actividad.
        try:
            browser.open_activity(page, activity)
        except Exception as e:
            print(f"  No se pudo abrir '{activity['type']}': {e}; sigo con la siguiente.")
            continue

        if not _wait_for_activity_screen(page):
            print(f"  '{activity['type']}' no llegó a mostrar nada con lo que trabajar ({page.url.split('/course/')[-1]}); sigo con la siguiente.")
            _debug_screenshot_omit(page, activity["type"])
            continue

        # Un error en UNA actividad no debe costar la lección entera.
        # Confirmado en vivo: un timeout en un solo ejercicio subía hasta
        # main(), la lección se daba por fallida y las demás actividades
        # pendientes ni se intentaban.
        try:
            if _work_single_activity(page, activity):
                fixed += 1
        except PlaywrightTimeoutError as e:
            print(f"  '{activity['type']}': error inesperado ({e.message.splitlines()[0]}); sigo con la siguiente.")
            _debug_screenshot_omit(page, activity["type"])

        # Volver al resumen deja la página en un punto conocido para el
        # siguiente salto; si se falla, el propio open_activity de la
        # próxima vuelta se encarga igual.
        browser.go_to_lesson_summary(page)

    print(
        f"'{lesson_title}': se trabajaron {len(workable)} actividad(es) pendientes; "
        f"{fixed} con al menos un ejercicio correcto (los arreglos de video/contenido no se cuentan aquí)."
    )
    return fixed


def run_lesson(page, lesson_title, already_completed=0, max_skips=MAX_SKIPS):
    """
    Resuelve ejercicios de la lección actual uno tras otro. Las pantallas
    que no son un ejercicio reconocido (Objetivos, Vocabulario, Demostración,
    etc.) se saltan con el mismo botón "Omitir" que usan los ejercicios.

    Como "Reanudar" siempre vuelve al principio de la lección (no al primer
    ejercicio pendiente), los primeros `already_completed` ejercicios que
    aparezcan se saltan con "Omitir" sin llamar a la IA, en vez de
    resolverlos de nuevo — ya están correctos según
    LessonActivitiesCompletedText.

    Si la lección incluye ejercicios de habla (requieren grabar audio real,
    no automatizable), se descarta ese modal con "Continuar sin voz" y esas
    actividades quedan pendientes para completarlas a mano; el bot sigue
    con la siguiente lección en vez de bloquearse ahí.

    Al terminar el recorrido lineal, reintenta desde el panel lateral todo
    lo que quedó "Omitida"/"Vuelva a intentarlo" y después va al resumen
    para dictar el veredicto leyendo el estado real de cada actividad.
    **No se usa el contador de la plataforma para eso**: sube igual esté
    la respuesta bien o mal, así que no distingue una lección terminada de
    una llena de actividades incorrectas.

    Devuelve (resultado, pendientes):
        "completed"      -> no queda nada pendiente
        "speech_blocked" -> lo único pendiente requiere grabar la voz
        "failed"         -> quedó algo pendiente que NO es de voz
    donde "pendientes" son los dicts de browser.get_pending_activities().
    """
    skips = 0
    solved = 0
    page_advances = 0
    modal_dismiss_attempts = 0
    read_aloud_skip_attempts = 0
    video_skip_attempts = 0
    video_completed = False

    # Lección ya empezada: no tiene sentido recorrerla entera. "Reanudar"
    # siempre reinicia desde el paso 1, así que con el recorrido lineal el
    # coste de arreglar la última actividad de una lección de 42 era pasar
    # de largo por las 41 anteriores, una por una. Desde el resumen se salta
    # directo a lo que falta (confirmado en vivo que el contenedor del panel
    # lateral abre incluso actividades nunca tocadas, ver
    # browser.open_activity), así que el recorrido lineal se reserva para
    # las lecciones nuevas, donde de todas formas hay que hacerlo todo.
    linear_walk = already_completed == 0
    if not linear_walk:
        print(f"'{lesson_title}' ya está empezada ({already_completed} contadas); voy directo a lo que falta.")
        if not browser.go_to_lesson_summary(page):
            print(f"No se pudo abrir el resumen de '{lesson_title}'; recorro la lección entera como antes.")
            linear_walk = True

    while linear_walk:
        if browser.has_speech_modal(page):
            modal_dismiss_attempts += 1
            if modal_dismiss_attempts > 5:
                # No debería pasar, pero por si "Continuar sin voz" alguna
                # vez no lo hace desaparecer: mejor rendirse que colgar para
                # siempre reintentando lo mismo.
                print(f"El modal de habla en '{lesson_title}' no se cierra tras varios intentos; abandonando esta lección.")
                break
            print(f"'{lesson_title}' tiene actividades de habla (requieren micrófono); las dejo pendientes para ti...")
            browser.dismiss_speech_modal(page)
            continue

        # Mientras seguimos pasando de largo por lo ya contado (ver la rama
        # `solved < already_completed` más abajo) solo hace falta saber QUÉ
        # pantalla es, no resolverla: capturar el audio de un ejercicio
        # solo-audio intercepta peticiones reales de red y es lo más lento
        # de get_current_exercise(). Bajarlo para tirarlo era tiempo puro
        # perdido en cada "Reanudar", que siempre reinicia desde el paso 1.
        # Pantalla que exige hablar (botón de micrófono), aunque su tipo no
        # lo diga: se omite a propósito, igual que la lectura en voz alta.
        if browser.requires_speech(page):
            skips += 1
            if skips > max_skips:
                break
            print(f"'{lesson_title}': pantalla que exige hablar; la omito a propósito...")
            skip_button = page.locator('[data-qa="SubmitButton"], [data-qa="StartLessonButton"]')
            if skip_button.count() > 0:
                skip_button.first.click()
                page.wait_for_timeout(1500)
            continue

        try:
            exercise = browser.get_current_exercise(page, capture_audio=solved >= already_completed)
        except NotImplementedError:
            # Si ya se descartó el modal de habla antes en esta misma sesión
            # de navegador (ej. en una lección anterior), no vuelve a
            # aparecer en las siguientes lecciones: sus actividades de habla
            # se omiten directo y aterrizamos en el resumen sin pasar por
            # get_current_exercise() ni por un SubmitButton reconocible.
            if "/summary" in page.url:
                print(f"'{lesson_title}' llegó al resumen sin completar todo (actividades de habla ya descartadas antes en esta sesión).")
                break

            # El modal de habla a veces aparece con un pequeño delay después
            # de cargar la pantalla: re-chequear justo antes de intentar
            # cualquier clic, para no toparnos con él bloqueando el clic
            # (y colgando 30s hasta el timeout de Playwright).
            page.wait_for_timeout(500)
            if browser.has_speech_modal(page):
                continue

            # "Lectura en voz alta" (Leer/Escuchar/Hablar): requiere
            # grabarse leyendo, no automatizable — igual que el modal de
            # habla, pero esta pantalla no dispara ningún modal, así que
            # sin este chequeo caía en el camino genérico de abajo con un
            # mensaje ambiguo ("pantalla no reconocida") que no dejaba
            # claro que la omisión era intencional (de habla) y no un
            # hueco real de mapeo.
            if browser.has_read_aloud_activity(page):
                read_aloud_skip_attempts += 1
                if read_aloud_skip_attempts > 5:
                    # No debería pasar, pero por si el botón de avance alguna
                    # vez no la hace desaparecer: mejor rendirse que colgar
                    # para siempre reintentando lo mismo.
                    print(f"La actividad de \"Lectura en voz alta\" en '{lesson_title}' no se puede saltar tras varios intentos; abandonando esta lección.")
                    break
                print(f"'{lesson_title}' tiene una actividad de \"Lectura en voz alta\" (requiere grabarse); la omito a propósito...")
                skip_button = page.locator('[data-qa="SubmitButton"], [data-qa="StartLessonButton"]')
                if skip_button.count() > 0:
                    skip_button.first.click()
                    page.wait_for_timeout(1500)
                continue

            # Demostración: browser.skip_video() reproduce el video de
            # verdad a 16x (ver ahí por qué: simular el final con
            # currentTime/eventos sintéticos no funciona, Rosetta lo marca
            # "Omitida"). El <video> sigue en el DOM aunque ya esté
            # completo, así que solo reintentamos mientras no se haya
            # visto de verdad (video_is_watched, NO can_advance: ese
            # chequeaba "disabled" en un <div> que nunca lo tiene, así que
            # siempre daba "listo" aunque el video nunca se hubiera visto
            # — bug real, confirmado en vivo: la Demostración quedaba
            # "Omitida" porque skip_video() nunca se llegaba a llamar).
            if browser.has_video(page):
                if not browser.video_is_watched(page) and video_skip_attempts < 2:
                    video_skip_attempts += 1
                    browser.skip_video(page)
                    continue
                if browser.video_is_watched(page):
                    # El video ya se vio de verdad; el clic de abajo solo
                    # avanza, no "omite" nada.
                    video_completed = True
                # Si no, se agotaron los reintentos sin lograr verlo:
                # cae al camino genérico de abajo como último recurso
                # (mejor eso que colgarse para siempre).

            # Vocabulario/Explicación: en vez de "Omitir" (que las deja como
            # "Omitida"), hay que pasar por sus sub-pasos para que queden
            # "Completa". Al llegar al último paso, el botón de avance queda
            # deshabilitado y cae al SubmitButton genérico de abajo.
            # Tope de seguridad: si por algún motivo el botón nunca se
            # detecta como deshabilitado, no colgarse paginando para siempre.
            #
            # Solo vale la pena paginar de verdad en territorio nuevo
            # (solved >= already_completed): "Reanudar" siempre reinicia la
            # lección desde el paso 1, así que un Vocabulario ya visto en
            # una corrida anterior lo volveríamos a paginar entero sin
            # necesidad. Mientras seguimos en la zona ya completada, el
            # "Omitir" genérico de abajo salta la sección completa de un
            # solo clic (como hacía antes de tener soporte de paginación).
            if solved >= already_completed and browser.has_paginated_content(page) and page_advances < 100:
                if browser.advance_paginated_content(page):
                    page_advances += 1
                    continue

            # SubmitButton: "Omitir" dentro de una lección ya iniciada.
            # StartLessonButton: pantalla de "Objetivos" de una lección nunca
            # iniciada antes (aparece una sola vez, con su propio botón).
            skip_button = page.locator('[data-qa="SubmitButton"], [data-qa="StartLessonButton"]')
            if skip_button.count() == 0 and skips < max_skips:
                # Puede que el modal de habla (u otra transición) todavía
                # esté renderizando; sondear un poco antes de rendirse.
                if _wait_for_advance(page):
                    continue

            if skip_button.count() == 0 or skips >= max_skips:
                break
            if video_completed:
                print("Demostración completada (video adelantado); avanzando a la siguiente actividad...")
                video_completed = False
            else:
                print("Pantalla no reconocida como ejercicio; omitiendo...")
                _debug_screenshot_omit(page, lesson_title)
            skip_button.first.click()
            page.wait_for_timeout(1500)
            skips += 1
            continue

        skips = 0
        video_skip_attempts = 0
        video_completed = False

        if solved < already_completed:
            # "already_completed" viene del contador de Rosetta ("X de Y
            # actividades completadas"), que cuenta cualquier actividad ya
            # atravesada, sea "Correcta" o haya quedado "Omitida"/incorrecta
            # (ej. por la revelación de Rosetta en una corrida o prueba
            # anterior — ver README, "la revelación no da crédito real").
            # "Reanudar" no permite volver atrás a re-intentar una actividad
            # ya pasada, así que aquí solo se puede seguir avanzando, esté
            # bien o mal — no asumir que "ya completado" significa "correcto".
            print(f"Actividad ya contada como completada ({solved + 1}/{already_completed}); no se puede re-intentar desde 'Reanudar', solo avanzo...")
            browser.submit_answer(page)  # mismo botón, en este estado actúa como "Omitir"
            page.wait_for_timeout(1500)
            solved += 1
            continue

        feedback = resolve_current_exercise(page, exercise)
        if feedback == "revealed":
            # Se falló, pero Rosetta enseñó la respuesta y ya quedó
            # guardada: seguir recorriendo la lección normalmente. Las
            # pasadas de abajo reabrirán esta actividad y la responderán
            # de memoria, sin IA y sin adivinar.
            print("Respuesta aprendida; sigo con el resto de la lección y la arreglo en la pasada de reintentos.")
            solved += 1
            continue
        if feedback != "correct":
            # Antes esto salía de la lección de inmediato. Ahora corta el
            # recorrido lineal pero cae igual en las rondas de reintento de
            # abajo: el ejercicio que falló queda marcado en el panel
            # lateral, y reabrirlo desde ahí da un juego fresco de intentos
            # — abandonar aquí era tirar esa segunda oportunidad.
            print(f"No se pudo resolver un ejercicio de '{lesson_title}' (resultado: {feedback}); paso a reintentar lo que quedó marcado...")
            break
        solved += 1

    # El objetivo no es solo "completar" la lección (el contador de Rosetta
    # sube igual esté bien o mal, ver README) sino que quede "Correcta" TODO
    # lo que no sea grabar la propia voz. Una sola pasada no basta: cada vez
    # que se reabre una actividad desde el panel, Rosetta da un juego fresco
    # de intentos reales antes de volver a revelar/rendirse, así que
    # insistir varias rondas aumenta de verdad las chances de acertar (no es
    # solo repetir lo mismo).
    #
    # Cada ronda arranca desde el resumen porque es la única pantalla donde
    # TODAS las actividades tienen su estado en el panel lateral: parado en
    # una actividad, esa no tiene hijo de estado, así que leer los
    # pendientes desde otra pantalla se salta justo la que estás viendo
    # (confirmado volcando el DOM, ver browser.get_activity_statuses).
    #
    # Si vale la pena otra ronda se decide contando los pendientes reales
    # antes y después, NO por lo que devuelve work_pending_activities: ese
    # solo cuenta ejercicios resueltos, así que una ronda que arregló
    # únicamente un video o un Vocabulario devolvía 0 y cortaba de más.
    #
    # Pero el número de pendientes tampoco basta por sí solo: una ronda en
    # la que la IA falla y Rosetta enseña la respuesta NO baja el contador
    # (el ejercicio sigue mal) y sin embargo es la ronda más valiosa de
    # todas, porque deja la respuesta guardada. Cortar ahí dejaba el
    # aprendizaje sin usar hasta la siguiente corrida. Por eso también se
    # mira si se aprendió algo nuevo.
    pending = []
    previous_pending = None
    learned = set()
    for retry_round in range(1, MAX_RETRY_ROUNDS + 1):
        if not browser.go_to_lesson_summary(page):
            print(f"No se pudo abrir el resumen de '{lesson_title}'; no se puede verificar qué quedó pendiente.")
            break

        pending = browser.get_pending_activities(page)
        speech_ids = _load_speech_ids()
        workable = [a for a in pending if not browser.is_speech_activity(a, speech_ids)]
        if not workable:
            break
        if previous_pending is not None and len(workable) >= previous_pending and not learned:
            print(f"'{lesson_title}': la última ronda no cambió nada ({len(workable)} pendiente(s)); no insisto más.")
            break

        previous_pending = len(workable)
        print(f"'{lesson_title}': pasada {retry_round}/{MAX_RETRY_ROUNDS} sobre {len(workable)} pendiente(s)...")
        answers_before = set(_load_known_answers())
        work_pending_activities(page, lesson_title)
        learned = set(_load_known_answers()) - answers_before
        if learned:
            print(f"'{lesson_title}': se aprendieron {len(learned)} respuesta(s) nueva(s); otra pasada para usarlas.")

    # Veredicto real de la lección, leído del panel lateral y no del
    # contador: el contador sube igual esté bien o mal, así que no sirve
    # para saber si algo quedó "Omitida"/"Vuelva a intentarlo".
    verified = browser.go_to_lesson_summary(page)
    if verified:
        pending = browser.get_pending_activities(page)

    browser.exit_lesson(page)

    if not verified:
        # Sin haber podido leer el resumen no sabemos nada: `pending` está
        # vacío porque no se pudo mirar, NO porque no quede nada. Darlo por
        # completado aquí sería inventarse un éxito.
        print(f"Nunca se pudo abrir el resumen de '{lesson_title}': no hay forma de verificar qué quedó.")
        return "failed", []

    if not pending:
        print(f"Lección '{lesson_title}' completada: todas las actividades quedaron Correcta/Completa.")
        return "completed", pending

    detail = ", ".join(f"{a['type']} ({a['status'] or 'sin empezar'})" for a in pending)
    speech_ids = _load_speech_ids()
    not_speech = [a for a in pending if not browser.is_speech_activity(a, speech_ids)]
    not_speech_detail = ", ".join(f"{a['type']} ({a['status'] or 'sin empezar'})" for a in not_speech)
    if browser.all_pending_are_speech(pending, speech_ids):
        print(
            f"Lección '{lesson_title}': lo único pendiente requiere grabar tu voz [{detail}]. "
            "La marco como bloqueada de verdad y sigo."
        )
        return "speech_blocked", pending

    print(
        f"Lección '{lesson_title}' quedó con {len(not_speech)} actividad(es) pendientes que NO son de voz: "
        f"{not_speech_detail}" + (f" (más {len(pending) - len(not_speech)} de voz)" if len(pending) > len(not_speech) else "")
    )
    return "failed", pending


def find_next_lesson(page, skip_keys=()):
    """
    Busca la primera lección con actividades pendientes (cuya clave
    "curso::lección" no esté en skip_keys) y la abre. Devuelve
    (título_lección, actividades_ya_completadas, título_curso), o
    (None, 0, None) si no queda ninguna.

    **Empieza por el curso donde encontró la última**, no por el primero.
    Antes recorría todos los cursos desde el 0 en cada búsqueda, entrando
    en cada uno (~4 s por curso): si la siguiente lección estaba en el
    curso 20, se iba más de un minuto solo en encontrarla, y eso se repetía
    con CADA lección. Los cursos anteriores ya quedaron agotados en esta
    sesión, así que empezar ahí no se salta nada; igualmente se da la
    vuelta completa al final para no perder nada.

    Un curso cuya página no carga bien (visto en vivo: timeout leyendo su
    título) se salta en vez de tumbar toda la búsqueda y forzar un
    reinicio.
    """
    browser.go_to_courses(page)
    course_count = browser.get_courses(page)
    if course_count == 0:
        return None, 0, None

    start = _SESSION_COURSE_HINT[0] % course_count
    for offset in range(course_count):
        course_index = (start + offset) % course_count
        try:
            browser.go_to_courses(page)
            browser.start_course(page, course_index)
            course_title = browser.get_course_title(page)
            lessons = browser.get_lessons(page)
        except PlaywrightTimeoutError as e:
            print(f"(no se pudo leer el curso {course_index + 1}/{course_count}: {e.message.splitlines()[0]}; lo salto)")
            continue

        for lesson_index, lesson in enumerate(lessons):
            key = f"{course_title}::{lesson['title']}"
            if lesson["completed"] < lesson["total"] and key not in skip_keys:
                _SESSION_COURSE_HINT[0] = course_index
                print(
                    f"Iniciando lección '{lesson['title']}' ({lesson['completed']}/{lesson['total']} ya completadas) "
                    f"[curso {course_index + 1}/{course_count}: {course_title}]..."
                )
                browser.start_lesson(page, lesson_index)
                return lesson["title"], lesson["completed"], course_title

    return None, 0, None


def main():
    """
    Devuelve True si el bot terminó de verdad (no quedan lecciones
    pendientes en ningún curso), False si se interrumpió por un error
    inesperado (timeout, error de la API, sesión expirada, etc.) — en cuyo
    caso conviene reintentar desde cero (el progreso ya hecho y las
    lecciones bloqueadas quedan guardados, así que reintentar es barato).
    """
    with sync_playwright() as p:
        print("Iniciando Playwright...")
        pw_browser, page = browser.open_browser(p)

        try:
            browser.login(page)
            browser.open_fluency_builder(page)

            page.screenshot(path="fluency_builder.png", full_page=True)
            print("Captura guardada: fluency_builder.png")

            blocked = _load_blocked_lessons()
            permanent = _permanently_blocked_keys(blocked)
            retryable = len(blocked) - len(permanent)
            if blocked:
                print(
                    f"{len(permanent)} lección(es) bloqueadas de verdad (voz, ya resueltas, o "
                    f"{MAX_LESSON_FAILURES} fallos sin respuestas pendientes) se omiten; "
                    f"{retryable} se van a revalidar por si ya son resolubles."
                )
            if _SESSION_ATTEMPTED:
                print(
                    f"Reinicio tras un error: {len(_SESSION_ATTEMPTED)} lección(es) ya intentadas en esta "
                    "sesión no se vuelven a abrir (y no se les suma otro fallo)."
                )
            skip_keys = permanent | _SESSION_ATTEMPTED

            while True:
                lesson_title, already_completed, course_title = find_next_lesson(page, skip_keys=skip_keys)
                if lesson_title is None:
                    print("No quedan lecciones pendientes en ningún curso (aparte de las bloqueadas).")
                    return True

                key = f"{course_title}::{lesson_title}"
                # Red de seguridad contra bucles: una lección se intenta
                # como máximo UNA vez por corrida, pase lo que pase. Sin
                # esto, cualquier caso en que run_lesson() termine sin que
                # el contador de Rosetta cambie hace que find_next_lesson()
                # vuelva a elegir la misma lección para siempre (confirmado
                # en vivo con el contador desincronizado). La memoria entre
                # corridas la lleva blocked_lessons.json, no esta variable.
                skip_keys.add(key)
                _SESSION_ATTEMPTED.add(key)
                lesson_path = browser.get_lesson_path(page)
                answers_before = set(_load_known_answers())
                try:
                    result, pending = run_lesson(page, lesson_title, already_completed=already_completed)
                except PlaywrightTimeoutError as e:
                    # A veces, tras varios intentos fallidos, la propia
                    # Rosetta Stone avanza sola a la pantalla de resumen (sin
                    # que nuestro código la mande) — lo siguiente que
                    # intentemos hacer en la pantalla vieja truena con
                    # timeout. Si no se localiza el fallo en ESTA lección,
                    # el problema se repite en cada reinicio sin nunca
                    # quedar marcado como bloqueado (gastando los reintentos
                    # del wrapper en vano). Marcar y seguir con la próxima.
                    print(f"Timeout inesperado en '{lesson_title}': {e}")
                    state = _mark_blocked(blocked, key, BLOCKED_FAILED, lesson_path=lesson_path)
                    print(
                        f"'{key}': fallo {state['failures']}/{MAX_LESSON_FAILURES} por timeout. "
                        + ("No se vuelve a intentar." if state["failures"] >= MAX_LESSON_FAILURES
                           else "Se reintentará en otra corrida.")
                    )
                    # Tras un timeout seguimos DENTRO de la lección, donde el
                    # enlace "Mis cursos" no existe: ir directo ahí daba otro
                    # timeout y tumbaba la corrida entera (confirmado en vivo).
                    # Primero salir de la lección; si ni eso funciona, que
                    # lo resuelva el reinicio.
                    try:
                        browser.exit_lesson(page)
                    except Exception as exit_error:
                        print(f"(no se pudo salir de la lección tras el timeout: {exit_error})")
                    browser.go_to_courses(page)
                    continue

                # Ni "speech_blocked" ni "failed" detienen el bot: se registra
                # el resultado y se sigue con la próxima lección. Solo un error
                # inesperado (fuera de run_lesson) pausa de verdad, más abajo.
                if result == "completed":
                    # Se guarda SIEMPRE como "completed", sin consultar el
                    # contador de Rosetta. El contador puede quedarse en
                    # "16 de 17" aunque el panel lateral muestre todo en
                    # Correcta/Completa, y como find_next_lesson() filtra por
                    # él, la lección se volvía a abrir en cada corrida.
                    # Antes se intentaba detectar ese desfase releyendo el
                    # contador al salir, pero confirmado en vivo que no es
                    # fiable: justo al salir la página enseña un número que
                    # luego no se mantiene. Guardarla no cuesta nada si el
                    # contador ya estaba bien (entonces no se volvería a
                    # elegir de todos modos). El panel manda, no el contador.
                    _mark_blocked(blocked, key, BLOCKED_DONE, lesson_path=lesson_path)
                    print(f"'{key}': resuelta según el panel lateral; no se vuelve a abrir.")
                    continue

                # Se omite el resto de la corrida para esta lección SIEMPRE,
                # pero solo se deja de intentar en el futuro si el motivo es
                # definitivo (voz) o si ya agotó sus reintentos.
                learned = set(_load_known_answers()) - answers_before
                state = _mark_blocked(
                    blocked, key, BLOCKED_SPEECH if result == "speech_blocked" else BLOCKED_FAILED, pending,
                    lesson_path=lesson_path, count_failure=not learned,
                )
                if learned and state["reason"] == BLOCKED_FAILED:
                    print(
                        f"'{key}': no quedó completa, pero aprendió {len(learned)} respuesta(s); "
                        "no lo cuento como fallo y la próxima vez las usa."
                    )
                if state["reason"] == BLOCKED_SPEECH:
                    print(f"'{key}': bloqueada definitivamente (solo queda voz). Sigo con la próxima.")
                else:
                    print(
                        f"'{key}': fallo {state['failures']}/{MAX_LESSON_FAILURES} "
                        f"(pendiente: {', '.join(state['pending'])}). "
                        + ("No se vuelve a intentar." if state["failures"] >= MAX_LESSON_FAILURES
                           else "Se reintentará en otra corrida.")
                    )
                continue

        except PlaywrightTimeoutError:
            print()
            print("ERROR: Se agotó el tiempo esperando un elemento.")
            print()
            print("URL actual:", page.url)
            print()
            print("Se guardará una captura para revisar el problema.")

            _try_save_error_screenshot(page)

            return False

        except Exception as e:
            print()
            print("ERROR:")
            print(e)
            print()

            _try_save_error_screenshot(page)

            return False

        finally:
            pw_browser.close()


MAX_RESTARTS = 30

if __name__ == "__main__":
    _start_logging()
    for attempt in range(1, MAX_RESTARTS + 1):
        print(f"=== Intento {attempt}/{MAX_RESTARTS} ===")
        if main():
            print("Terminado de verdad: no quedan lecciones pendientes.")
            break
        print("Se interrumpió por un error; reiniciando desde cero (el progreso ya hecho no se pierde)...")
    else:
        print(f"Se alcanzó el máximo de {MAX_RESTARTS} reintentos sin terminar. Revisar manualmente.")

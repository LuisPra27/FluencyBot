import json
import os
import sys

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

MAX_ATTEMPTS = 3
MAX_SKIPS = 10
MAX_RETRY_ROUNDS = 5

# Cuántas veces seguidas puede fallar una lección por algo que NO es voz
# antes de darla por perdida. Un fallo puntual (un flake de navegación, un
# modelo de IA caído, un tipo de ejercicio que todavía no se soportaba) no
# debe condenar la lección para siempre: se reintenta en la próxima corrida.
MAX_LESSON_FAILURES = 3

BLOCKED_LESSONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blocked_lessons.json")

# Motivos de bloqueo. Solo "speech" es definitivo: significa que lo único
# que queda pendiente en esa lección requiere grabar la propia voz.
BLOCKED_SPEECH = "speech"
BLOCKED_FAILED = "failed"


def _load_blocked_lessons():
    """
    Estado por lección bloqueada, indexado por clave "curso::lección"
    (ej. "Speak with Pilots and Airline Mechanics (B1)::Preflight"):

        {"reason": "speech"|"failed", "failures": int, "pending": [str, ...]}

    **Por qué esto dejó de ser una lista plana**: antes cualquier
    resultado que no fuera "completado" —una actividad de voz, un
    ejercicio que la IA no supo, o un simple timeout de navegación— metía
    la lección en el mismo archivo y la excluía PARA SIEMPRE, sin guardar
    el motivo. Eso convirtió el archivo en la cicatriz de todos los bugs
    pasados en vez de una lista real: durante el apagón del modelo
    `muse-glimmer-30b` (404 en toda llamada, ver ai.py) cada lección que
    se intentó quedó marcada, y ahí siguen decenas que el bot sí puede
    hacer hoy. Con el motivo guardado, solo "speech" es permanente; lo
    demás se reintenta hasta MAX_LESSON_FAILURES veces.

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


def _mark_blocked(blocked, key, reason, pending=()):
    """
    Registra el resultado de una lección que no quedó completa. Un bloqueo
    por voz es definitivo y no acumula fallos; cualquier otro motivo suma
    un intento fallido y solo se vuelve definitivo al llegar al tope.
    """
    previous_failures = blocked.get(key, {}).get("failures", 0)
    blocked[key] = {
        "reason": reason,
        "failures": 0 if reason == BLOCKED_SPEECH else previous_failures + 1,
        "pending": sorted({a["type"] for a in pending}),
    }
    _save_blocked_lessons(blocked)
    return blocked[key]


def _permanently_blocked_keys(blocked):
    """
    Las que de verdad no hay que volver a intentar: las de voz, y las que
    ya agotaron sus reintentos. El resto se vuelve a probar — revalidarlas
    cuesta una navegación y cero llamadas a la IA, mucho menos que dejar
    lecciones perfectamente resolubles marcadas para siempre.
    """
    return {
        key
        for key, state in blocked.items()
        if state.get("reason") == BLOCKED_SPEECH
        or state.get("failures", 0) >= MAX_LESSON_FAILURES
    }


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
        for blank_index, answer in enumerate(solution["answers"], start=1):
            browser.select_cloze_option(page, blank_index, answer)

    elif exercise_type == "cloze_input":
        for blank_index, text in enumerate(solution["answers"], start=1):
            browser.fill_cloze_input(page, blank_index, text)

    elif exercise_type == "matching":
        for word, target_index in solution["pairs"].items():
            browser.drag_matching_pair(page, word, target_index)

    elif exercise_type == "ordering":
        browser.reorder_items(page, solution["order"])

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
    """
    print("Ejercicio detectado:", exercise)

    previous_attempts = []
    feedback = None

    for attempt in range(1, max_attempts + 1):
        # Tras un par de fallos, Rosetta a veces revela la respuesta
        # correcta apenas se carga la pantalla de "Volver a intentar" —
        # ANTES de tocar nada — y en ese estado los controles (ej. los
        # dropdowns de 'cloze_dropdown') ya no responden normalmente:
        # intentar aplicar otra solución ahí cuelga 30s hasta el timeout
        # de Playwright. Hay que revisar esto antes de intentar aplicar
        # cualquier solución, no solo después de enviarla.
        if browser.is_answer_revealed(page):
            print("Rosetta ya reveló la respuesta correcta antes de intentar nada más; avanzando.")
            browser.go_to_next_exercise(page)
            page.wait_for_timeout(1500)
            return "correct"

        try:
            solution = ai.solve_exercise(exercise, previous_attempts=previous_attempts)
        except Exception as e:
            # Un modelo puede devolver basura no-JSON (ej. el modelo de
            # audio a veces alucina y se queda repitiendo hasta agotar
            # tokens). Que cuente como intento fallido normal, no que tumbe
            # todo el ejercicio.
            print(f"Intento {attempt}/{max_attempts} - la IA no devolvió una solución válida: {e}")
            feedback = "incorrect"
            if attempt < max_attempts:
                continue
            return feedback

        print(f"Intento {attempt}/{max_attempts} - Solución de la IA:", solution)

        apply_solution(page, exercise, solution)
        browser.submit_answer(page)

        feedback = browser.wait_for_feedback(page)
        if feedback is None and not browser.is_answer_revealed(page):
            # Red de seguridad: el botón de enviar es un <div>, no un
            # <button disabled> real, así que un clic puede caer como
            # no-op silencioso si React todavía no había registrado el
            # cambio (confirmado en vivo con "cloze_input": el texto
            # quedaba escrito pero nunca se enviaba). Un segundo clic no
            # hace daño si el primero sí funcionó (ya se habría avanzado o
            # revelado, y no llegaríamos aquí).
            browser.submit_answer(page)
            feedback = browser.wait_for_feedback(page)
        print("Resultado:", feedback)

        if feedback == "correct":
            browser.go_to_next_exercise(page)
            page.wait_for_timeout(1500)
            return feedback

        if browser.is_answer_revealed(page):
            # Rosetta ya resaltó la respuesta correcta ella misma tras
            # varios fallos: no tiene sentido gastar otro intento de IA,
            # solo avanzar (la respuesta ya quedó aplicada por la página).
            print("Rosetta reveló la respuesta correcta; avanzando sin gastar otro intento de IA.")
            browser.go_to_next_exercise(page)
            page.wait_for_timeout(1500)
            return "correct"

        previous_attempts.append(solution)

        if attempt < max_attempts:
            print("Incorrecto, reintentando...")
            browser.submit_answer(page)  # botón "Volver a intentar": resetea la vista
            page.wait_for_timeout(1000)

    return feedback


def retry_flagged_items(page, lesson_title):
    """
    Confirmado en vivo: a diferencia de lo que se asumía antes, Rosetta SÍ
    permite reabrir una actividad marcada "Omitida" o "Vuelva a
    intentarlo" — basta con hacer clic en su item del panel lateral de la
    lección para que vuelva a mostrarse interactiva, como si no se hubiera
    tocado. Esto significa que las actividades que quedaron mal por la
    revelación de Rosetta, o genuinamente omitidas, SÍ se pueden re-
    intentar de verdad en vez de quedar así para siempre.

    **Historial de bugs reales en esta función, todos encontrados en
    vivo**: primero usaba `.first` sobre el texto visible sin llevar
    registro de qué ya se había intentado (se quedaba pegada reintentando
    el mismo item para siempre). Luego se intentó cortar al detectar una
    URL repetida, pero eso hacía que un solo item no arreglable al
    principio de la lista abortara toda la pasada, dejando sin intentar
    items que sí eran arreglables más adelante. La solución definitiva:
    en vez de posición/texto visible, se usa el ID único y estable de cada
    actividad (`browser.get_flagged_activity_ids()`, leído directamente
    del DOM vía `data-qa="activity_<id>_completed"`). Al tomar la lista de
    IDs UNA sola vez al principio y recorrerla por ID (no por posición),
    no importa qué se arregle o no en el camino — cada ID se intenta
    exactamente una vez.

    Algunas actividades (habla, "Lectura en voz alta") seguirán sin poder
    resolverse y eso es esperado — se vuelven a omitir con el mismo
    criterio que usa el recorrido normal de la lección, una sola vez, sin
    insistir.

    Devuelve cuántas actividades quedaron "correct" tras el reintento.
    """
    flagged_status_qas = browser.get_flagged_activity_ids(page)
    if not flagged_status_qas:
        return 0

    print(f"'{lesson_title}': {len(flagged_status_qas)} actividad(es) quedaron marcadas Omitida/Vuelva a intentarlo; reintentando de verdad...")
    fixed = 0

    for status_qa in flagged_status_qas:
        # Confirmado en vivo (el bug real detrás de por qué una Demostración
        # "Omitida" nunca se lograba reabrir): si el modal de habla ya está
        # abierto ANTES de intentar el clic (ej. porque quedó abierto en la
        # pantalla siguiente a la que se está reintentando), bloquea TODA
        # interacción con la página de fondo — el clic en el item del
        # sidebar simplemente no hacía nada, ni con `force=True`, y la URL
        # nunca cambiaba. Hay que descartarlo primero, igual que haría una
        # persona, antes de intentar reabrir la actividad.
        if browser.has_speech_modal(page):
            browser.dismiss_speech_modal(page)
            page.wait_for_timeout(500)

        # Un item que ya no exista (su data-qa cambia de sufijo en cuanto
        # cambia su estado) hace fallar el clic Y el force=True de respaldo.
        # Sin este try, esa excepción se escapaba hasta el handler genérico
        # de main() y tumbaba la corrida entera por UNA actividad.
        try:
            browser.click_activity(page, status_qa)
        except Exception as e:
            print(f"  No se pudo reabrir la actividad '{status_qa}': {e}; sigo con la siguiente.")
            continue
        page.wait_for_timeout(1500)

        # Bucle interno para ESTA MISMA actividad: no basta con un if/elif
        # de un solo paso, porque más de una condición puede aplicar en
        # secuencia para la misma actividad (ej. reabrir una Demostración
        # puede volver a mostrar el modal de habla ANTES de llegar al
        # video en sí). Confirmado en vivo: con un if/elif de un solo paso,
        # al descartar el modal se pasaba directo a la SIGUIENTE actividad
        # de la lista sin nunca llegar a revisar el video de esta.
        for _ in range(6):
            if browser.has_speech_modal(page):
                browser.dismiss_speech_modal(page)
                page.wait_for_timeout(500)
                continue

            if browser.has_read_aloud_activity(page):
                skip_button = page.locator('[data-qa="SubmitButton"]')
                if skip_button.count() > 0:
                    skip_button.first.click()
                    page.wait_for_timeout(1500)
                break

            if browser.has_video(page):
                if not browser.video_is_watched(page):
                    browser.skip_video(page)
                # El <video> sigue en el DOM aunque ya se haya visto
                # completo (ver browser.video_is_watched), así que NO se
                # puede simplemente "continue" aquí: has_video() seguiría
                # dando True para siempre y nunca se llegaría a hacer clic
                # en el botón de avance. Justo al terminar el video,
                # Rosetta puede mostrar el modal de habla encima de ese
                # botón — se descarta aquí mismo antes de intentar el clic.
                for _ in range(3):
                    if not browser.has_speech_modal(page):
                        break
                    browser.dismiss_speech_modal(page)
                    page.wait_for_timeout(500)
                skip_button = page.locator('[data-qa="SubmitButton"]')
                if skip_button.count() > 0:
                    skip_button.first.click()
                    page.wait_for_timeout(1500)
                break

            if browser.has_paginated_content(page):
                # Vocabulario/Explicación: paginar de verdad (igual que
                # run_lesson) para que quede "Completa" en vez de "Omitida".
                for _ in range(100):
                    if not browser.advance_paginated_content(page):
                        break
                skip_button = page.locator('[data-qa="SubmitButton"]')
                if skip_button.count() > 0:
                    skip_button.first.click()
                    page.wait_for_timeout(1500)
                break

            try:
                exercise = browser.get_current_exercise(page)
            except NotImplementedError:
                # Pantalla no reconocida (ej. Objetivos, o un video ya
                # visto esperando el clic de avance): omitir/avanzar igual
                # que hace el recorrido normal.
                skip_button = page.locator('[data-qa="SubmitButton"], [data-qa="StartLessonButton"]')
                if skip_button.count() > 0:
                    skip_button.first.click()
                    page.wait_for_timeout(1500)
                break
            else:
                feedback = resolve_current_exercise(page, exercise)
                if feedback == "correct":
                    fixed += 1
                break

    # Solo se cuentan los EJERCICIOS resueltos: las reparaciones de video,
    # Vocabulario/Explicación y demás no pasan por resolve_current_exercise
    # y no tienen un "correcto" que contar aquí. Por eso quien llama NO debe
    # usar este número para decidir si vale otra ronda — para eso hay que
    # mirar cuántos pendientes quedan de verdad en el resumen (ver
    # run_lesson), que sí refleja cualquier tipo de arreglo.
    print(
        f"'{lesson_title}': se reintentaron {len(flagged_status_qas)} actividad(es) marcadas; "
        f"{fixed} ejercicio(s) quedaron correctos (los arreglos de video/contenido no se cuentan aquí)."
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

    while True:
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
    # lo que no sea grabar la propia voz. Un solo intento de
    # retry_flagged_items no basta: cada vez que se reabre una actividad
    # desde el sidebar, Rosetta da un juego fresco de intentos reales antes
    # de volver a revelar/rendirse, así que insistir varias rondas aumenta
    # de verdad las chances de acertar (no es solo repetir lo mismo).
    #
    # Cada ronda arranca desde el resumen porque es la única pantalla donde
    # TODAS las actividades tienen su estado en el panel lateral: parado en
    # una actividad, esa no tiene hijo de estado, así que leer los
    # pendientes desde otra pantalla se salta justo la que estás viendo
    # (confirmado volcando el DOM, ver browser.get_activity_statuses).
    #
    # Si vale la pena otra ronda se decide contando los pendientes reales
    # antes y después, NO por lo que devuelve retry_flagged_items: ese solo
    # cuenta ejercicios resueltos, así que una ronda que arregló únicamente
    # un video o un Vocabulario devolvía 0 y cortaba las rondas de más.
    pending = []
    previous_pending = None
    for retry_round in range(1, MAX_RETRY_ROUNDS + 1):
        if not browser.go_to_lesson_summary(page):
            print(f"No se pudo abrir el resumen de '{lesson_title}'; no se puede verificar qué quedó pendiente.")
            break

        pending = browser.get_pending_activities(page)
        if not pending:
            break
        if previous_pending is not None and len(pending) >= previous_pending:
            print(f"'{lesson_title}': la última ronda no cambió nada ({len(pending)} pendiente(s)); no insisto más.")
            break

        previous_pending = len(pending)
        print(f"'{lesson_title}': ronda de reintento {retry_round}/{MAX_RETRY_ROUNDS} sobre {len(pending)} pendiente(s)...")
        retry_flagged_items(page, lesson_title)

    # Veredicto real de la lección, leído del panel lateral y no del
    # contador: el contador sube igual esté bien o mal, así que no sirve
    # para saber si algo quedó "Omitida"/"Vuelva a intentarlo".
    if browser.go_to_lesson_summary(page):
        pending = browser.get_pending_activities(page)

    browser.exit_lesson(page)

    if not pending:
        print(f"Lección '{lesson_title}' completada: todas las actividades quedaron Correcta/Completa.")
        return "completed", pending

    detail = ", ".join(f"{a['type']} ({a['status'] or 'sin empezar'})" for a in pending)
    if browser.all_pending_are_speech(pending):
        print(
            f"Lección '{lesson_title}': lo único pendiente requiere grabar tu voz [{detail}]. "
            "La marco como bloqueada de verdad y sigo."
        )
        return "speech_blocked", pending

    print(f"Lección '{lesson_title}' quedó con {len(pending)} actividad(es) pendientes que NO son de voz: {detail}")
    return "failed", pending


def find_next_lesson(page, skip_keys=()):
    """
    Recorre todos los cursos buscando la primera lección con actividades
    pendientes (cuya clave "curso::lección" no esté en skip_keys) y la abre.
    Devuelve (título_lección, actividades_ya_completadas, título_curso), o
    (None, 0, None) si no queda ninguna.

    skip_keys: claves "curso::lección" a ignorar aunque tengan actividades
    pendientes (ej. las ya confirmadas como bloqueadas por voz, cargadas
    desde speech_only_lessons.json o acumuladas en esta misma corrida).
    """
    browser.go_to_courses(page)
    course_count = browser.get_courses(page)

    for course_index in range(course_count):
        browser.go_to_courses(page)
        browser.start_course(page, course_index)
        course_title = browser.get_course_title(page)

        for lesson_index, lesson in enumerate(browser.get_lessons(page)):
            key = f"{course_title}::{lesson['title']}"
            if lesson["completed"] < lesson["total"] and key not in skip_keys:
                print(f"Iniciando lección '{lesson['title']}' ({lesson['completed']}/{lesson['total']} ya completadas)...")
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
            skip_keys = _permanently_blocked_keys(blocked)
            retryable = len(blocked) - len(skip_keys)
            if blocked:
                print(
                    f"{len(skip_keys)} lección(es) bloqueadas de verdad (voz o {MAX_LESSON_FAILURES} "
                    f"fallos) se omiten; {retryable} se van a revalidar por si ya son resolubles."
                )

            while True:
                lesson_title, already_completed, course_title = find_next_lesson(page, skip_keys=skip_keys)
                if lesson_title is None:
                    print("No quedan lecciones pendientes en ningún curso (aparte de las bloqueadas).")
                    return True

                key = f"{course_title}::{lesson_title}"
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
                    state = _mark_blocked(blocked, key, BLOCKED_FAILED)
                    print(
                        f"'{key}': fallo {state['failures']}/{MAX_LESSON_FAILURES} por timeout. "
                        + ("No se vuelve a intentar." if state["failures"] >= MAX_LESSON_FAILURES
                           else "Se reintentará en otra corrida.")
                    )
                    if state["failures"] >= MAX_LESSON_FAILURES:
                        skip_keys.add(key)
                    browser.go_to_courses(page)
                    continue

                # Ni "speech_blocked" ni "failed" detienen el bot: se registra
                # el resultado y se sigue con la próxima lección. Solo un error
                # inesperado (fuera de run_lesson) pausa de verdad, más abajo.
                if result == "completed":
                    # Pudo estar marcada de antes por un bug ya arreglado o un
                    # fallo puntual: si ahora quedó completa, que no siga
                    # ocupando lugar en la lista.
                    if blocked.pop(key, None) is not None:
                        _save_blocked_lessons(blocked)
                        print(f"'{key}' estaba marcada como bloqueada y se completó: la quito de la lista.")
                    continue

                # Se omite el resto de la corrida para esta lección SIEMPRE,
                # pero solo se deja de intentar en el futuro si el motivo es
                # definitivo (voz) o si ya agotó sus reintentos.
                state = _mark_blocked(
                    blocked, key, BLOCKED_SPEECH if result == "speech_blocked" else BLOCKED_FAILED, pending
                )
                if state["reason"] == BLOCKED_SPEECH:
                    skip_keys.add(key)
                    print(f"'{key}': bloqueada definitivamente (solo queda voz). Sigo con la próxima.")
                else:
                    print(
                        f"'{key}': fallo {state['failures']}/{MAX_LESSON_FAILURES} "
                        f"(pendiente: {', '.join(state['pending'])}). "
                        + ("No se vuelve a intentar." if state["failures"] >= MAX_LESSON_FAILURES
                           else "Se reintentará en otra corrida.")
                    )
                    if state["failures"] >= MAX_LESSON_FAILURES:
                        skip_keys.add(key)
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
    for attempt in range(1, MAX_RESTARTS + 1):
        print(f"=== Intento {attempt}/{MAX_RESTARTS} ===")
        if main():
            print("Terminado de verdad: no quedan lecciones pendientes.")
            break
        print("Se interrumpió por un error; reiniciando desde cero (el progreso ya hecho no se pierde)...")
    else:
        print(f"Se alcanzó el máximo de {MAX_RESTARTS} reintentos sin terminar. Revisar manualmente.")

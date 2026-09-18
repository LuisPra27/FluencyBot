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

BLOCKED_LESSONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blocked_lessons.json")


def _load_blocked_lessons():
    """
    Claves "curso::lección" (ej. "Speak with Pilots and Airline Mechanics (B1)::Preflight")
    ya confirmadas como no completables por el bot (por voz, o porque la IA
    no pudo resolver algo), guardadas entre corridas para no tener que
    re-entrar y re-verificarlas cada vez.
    """
    if not os.path.exists(BLOCKED_LESSONS_FILE):
        return set()
    with open(BLOCKED_LESSONS_FILE, "r", encoding="utf-8") as f:
        return set(json.load(f))


def _save_blocked_lessons(keys):
    with open(BLOCKED_LESSONS_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(keys), f, indent=2, ensure_ascii=False)


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
            browser.get_current_exercise(page)
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
        page.wait_for_timeout(1500)

        feedback = browser.get_feedback_state(page)
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

    Al no encontrar más ejercicios ni poder seguir saltando, sale de la
    lección y confirma contra el contador real de la plataforma si de
    verdad se completó, en vez de asumirlo — un tipo de ejercicio no
    soportado también deja de reconocerse y no queremos confundir eso con
    "lección terminada".

    Devuelve True si la lección quedó completa (o tan completa como se
    puede sin voz), False si se detuvo por un ejercicio fallido o una
    pantalla no reconocida ni saltable.
    """
    skips = 0
    solved = 0
    page_advances = 0
    modal_dismiss_attempts = 0
    video_skip_attempts = 0
    video_completed = False
    speech_skipped = False

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
            speech_skipped = True
            continue

        try:
            exercise = browser.get_current_exercise(page)
        except NotImplementedError:
            # Si ya se descartó el modal de habla antes en esta misma sesión
            # de navegador (ej. en una lección anterior), no vuelve a
            # aparecer en las siguientes lecciones: sus actividades de habla
            # se omiten directo y aterrizamos en el resumen sin pasar por
            # get_current_exercise() ni por un SubmitButton reconocible.
            if "/summary" in page.url:
                print(f"'{lesson_title}' llegó al resumen sin completar todo (actividades de habla ya descartadas antes en esta sesión).")
                speech_skipped = True
                break

            # El modal de habla a veces aparece con un pequeño delay después
            # de cargar la pantalla: re-chequear justo antes de intentar
            # cualquier clic, para no toparnos con él bloqueando el clic
            # (y colgando 30s hasta el timeout de Playwright).
            page.wait_for_timeout(500)
            if browser.has_speech_modal(page):
                continue

            # Demostración: browser.skip_video() reproduce el video de
            # verdad a 16x (ver ahí por qué: simular el final con
            # currentTime/eventos sintéticos no funciona, Rosetta lo marca
            # "Omitida"). El <video> sigue en el DOM aunque ya esté
            # completo, así que solo reintentamos mientras el botón de
            # avance no esté listo; tope de seguridad por si el video
            # nunca queda "listo" (ej. play() bloqueado).
            if browser.has_video(page):
                if not browser.can_advance(page) and video_skip_attempts < 2:
                    video_skip_attempts += 1
                    browser.skip_video(page)
                    continue
                if browser.can_advance(page):
                    # El video ya quedó marcado "Completa" de verdad; el
                    # clic de abajo solo avanza, no "omite" nada.
                    video_completed = True
                # Si no, se agotaron los reintentos sin lograr que Rosetta
                # lo marque completo: cae al camino genérico de abajo como
                # último recurso (mejor eso que colgarse para siempre).

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
            skip_button.first.click()
            page.wait_for_timeout(1500)
            skips += 1
            continue

        skips = 0
        video_skip_attempts = 0
        video_completed = False

        if solved < already_completed:
            print(f"Ejercicio ya completado antes ({solved + 1}/{already_completed}); omitiendo sin llamar a la IA...")
            browser.submit_answer(page)  # mismo botón, en este estado actúa como "Omitir"
            page.wait_for_timeout(1500)
            solved += 1
            continue

        feedback = resolve_current_exercise(page, exercise)
        if feedback != "correct":
            print(f"No se pudo resolver un ejercicio de '{lesson_title}' (resultado: {feedback}). Saliendo de la lección...")
            browser.exit_lesson(page)
            return "failed"
        solved += 1

    browser.exit_lesson(page)

    lesson = next((l for l in browser.get_lessons(page) if l["title"] == lesson_title), None)
    if lesson and lesson["completed"] >= lesson["total"]:
        print(f"Lección '{lesson_title}' completada ({lesson['completed']}/{lesson['total']}).")
        return "completed"

    if speech_skipped:
        print(
            f"Lección '{lesson_title}' quedó en {lesson['completed']}/{lesson['total']} "
            "(el resto son actividades de habla pendientes para ti). Sigo con la próxima lección."
        )
        return "speech_blocked"

    print(f"Lección '{lesson_title}' se detuvo en una pantalla no reconocida ni saltable.")
    return "failed"


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

            blocked_keys = _load_blocked_lessons()
            if blocked_keys:
                print(f"{len(blocked_keys)} lección(es) ya confirmadas como bloqueadas (de corridas anteriores), se omiten.")

            while True:
                lesson_title, already_completed, course_title = find_next_lesson(page, skip_keys=blocked_keys)
                if lesson_title is None:
                    print("No quedan lecciones pendientes en ningún curso (aparte de las bloqueadas).")
                    return True

                try:
                    result = run_lesson(page, lesson_title, already_completed=already_completed)
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
                    print(f"Marcando '{course_title}::{lesson_title}' como bloqueada (fallo irrecuperable) y siguiendo.")
                    blocked_keys.add(f"{course_title}::{lesson_title}")
                    _save_blocked_lessons(blocked_keys)
                    browser.go_to_courses(page)
                    continue

                # Ni "speech_blocked" ni "failed" detienen el bot: se marca la
                # lección como bloqueada (para no reintentarla en el futuro)
                # y se sigue con la próxima. Solo un error inesperado (fuera
                # de run_lesson) pausa de verdad, más abajo.
                if result in ("speech_blocked", "failed"):
                    print(f"Marcando '{course_title}::{lesson_title}' como bloqueada y siguiendo con la próxima lección.")
                    blocked_keys.add(f"{course_title}::{lesson_title}")
                    _save_blocked_lessons(blocked_keys)
                    continue

        except PlaywrightTimeoutError:
            print()
            print("ERROR: Se agotó el tiempo esperando un elemento.")
            print()
            print("URL actual:", page.url)
            print()
            print("Se guardará una captura para revisar el problema.")

            page.screenshot(path="error.png", full_page=True)
            print("Captura guardada como error.png")

            return False

        except Exception as e:
            print()
            print("ERROR:")
            print(e)
            print()
            print("URL actual:", page.url)

            page.screenshot(path="error.png", full_page=True)
            print()
            print("Captura guardada como error.png")

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

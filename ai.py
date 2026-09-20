"""
Integración con el modelo de IA encargado de resolver los ejercicios.

Usa la API de NVIDIA build (https://build.nvidia.com), compatible con el SDK
de OpenAI. Modelo principal: meta/llama-3.2-11b-vision-instruct (texto +
imágenes, lo que hace falta para "matching" con imágenes). Para opciones que
son solo audio (sin texto legible) se usa
nvidia/nemotron-3-nano-omni-30b-a3b-reasoning, que sí entiende audio (el
modelo principal no).

NOTA: el modelo principal era antes meta/muse-glimmer-30b, dado de baja por
NVIDIA sin aviso entre sesiones — empezó a devolver 404 en cualquier llamada
de un día para otro (confirmado en vivo: seguía apareciendo en
`_client.models.list()` pero la inferencia fallaba). Si este modelo también
deja de funcionar en el futuro, revisar `_client.models.list()` para ver
qué sigue disponible antes de asumir que es un bug del código.
"""

import json
import random

from collections import Counter

from openai import OpenAI

import config

MODEL = "meta/llama-3.2-11b-vision-instruct"
AUDIO_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=config.AI_API_KEY)

# Tope por llamada a la IA. Confirmado en vivo que el modelo de audio (que
# razona antes de responder) puede tardar más de 5 minutos en UNA respuesta,
# y encima equivocarse. Desde que el bot aprende la respuesta que Rosetta
# revela tras dos fallos, esperar tanto no compensa: mejor fallar rápido y
# llegar antes a "Mostrar respuesta".
AI_TIMEOUT_S = 90


def _ask_json(content, max_tokens=3000, model=MODEL):
    """
    Llama al modelo y parsea su respuesta como JSON. El modelo razona antes
    de responder (consume tokens en eso), por lo que max_tokens debe dejar
    margen suficiente para el razonamiento + la respuesta final.
    """
    response = _client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=max_tokens,
        timeout=AI_TIMEOUT_S,
    )
    message = response.choices[0].message

    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        print("--- Razonamiento de la IA ---")
        print(reasoning)
        print("--- Fin razonamiento ---")

    text = message.content
    if not text:
        raise RuntimeError(
            "El modelo no devolvió contenido (probablemente se quedó sin "
            f"tokens razonando; max_tokens={max_tokens}). Subí max_tokens en _ask_json."
        )
    return json.loads(text)


def _format_previous_attempts(previous_attempts):
    """
    El resto de los prompts está en inglés; este trozo estaba en español y
    los modelos chicos lo ignoraban. Confirmado en vivo con
    "Escriba la respuesta": la IA devolvió LA MISMA respuesta equivocada
    tres veces seguidas, gastando los tres intentos en una sola idea. De
    ahí el tono imperativo y el listado explícito de lo ya descartado.
    """
    if not previous_attempts:
        return ""
    return (
        "\n\nIMPORTANT: these answers were already tried and are WRONG. "
        "Do NOT repeat any of them — give a DIFFERENT answer:\n"
        + "\n".join(f"  - {json.dumps(a, ensure_ascii=False)}" for a in previous_attempts)
    )


def _blind_guess(exercise_data, previous_attempts):
    """
    No hay señal legible para razonar (típicamente audio que no se pudo
    capturar): gastarle una llamada a la IA a una adivinanza a ciegas no
    tiene sentido. Se elige una respuesta válida al azar (evitando repetir
    intentos ya fallidos cuando se puede) y se deja que Rosetta, tras un
    par de fallos, revele la respuesta correcta ella misma — bot.py avanza
    igual en cuanto la detecta (ver browser.is_answer_revealed), en vez de
    dejar la actividad "Omitida" para siempre.
    """
    exercise_type = exercise_data["type"]

    if exercise_type == "multiple_choice":
        option_count = exercise_data.get("option_count") or len(exercise_data["options"])
        tried = {a["answer"] for a in previous_attempts}
        remaining = [i for i in range(1, option_count + 1) if i not in tried]
        return {"answer": random.choice(remaining or list(range(1, option_count + 1)))}

    if exercise_type == "matching":
        words = exercise_data["options"]
        target_count = len(exercise_data["targets"])
        order = list(range(1, target_count + 1))
        random.shuffle(order)
        return {"pairs": {word: order[i % target_count] for i, word in enumerate(words)}}

    # Para el resto no hay forma útil de "adivinar", pero tampoco hace falta:
    # basta con enviar ALGO para gastar el intento y que Rosetta acabe
    # ofreciendo "Mostrar respuesta", de donde el bot aprende la buena. Así
    # ni siquiera una caída total de la IA (como el apagón de
    # muse-glimmer-30b) bloquea el avance.
    if exercise_type == "cloze_dropdown":
        return {"answers": [random.randrange(len(opts)) for opts in exercise_data["blanks"]]}

    if exercise_type == "cloze_input":
        return {"answers": ["x"] * exercise_data["blank_count"]}

    if exercise_type == "text_input":
        return {"answer": "x"}

    if exercise_type == "ordering":
        items = list(exercise_data["items"])
        random.shuffle(items)
        return {"order": items}

    if exercise_type == "text_rewrite":
        return {"answers": ["x"] * len(exercise_data["prompts"])}

    if exercise_type == "cloze_drag":
        words = list(exercise_data["options"])
        random.shuffle(words)
        return {"answers": words[:exercise_data["blank_count"]]}

    if exercise_type == "sentence_build":
        words = list(exercise_data["words"])
        random.shuffle(words)
        return {"order": words}

    if exercise_type == "matching_audio_options":
        ids = list(exercise_data["option_audio_ids"])
        numbers = list(range(1, len(ids) + 1))
        random.shuffle(numbers)
        if all(ids):
            return {"target_for_clip": dict(zip(ids, numbers))}
        # Sin identificadores de clip se arrastra por posición (clave "#n").
        return {"target_for_clip": {f"#{i}": n for i, n in enumerate(numbers)}}

    raise NotImplementedError(f"No se sabe adivinar a ciegas el tipo '{exercise_type}'")


def _solve_multiple_choice(exercise, previous_attempts):
    prompt_audio_url = exercise.get("prompt_audio_url")
    option_audio_urls = exercise.get("option_audio_urls")
    if prompt_audio_url or option_audio_urls:
        return _solve_multiple_choice_audio(exercise, prompt_audio_url, option_audio_urls, previous_attempts)

    options_text = "\n".join(f"{i}. {opt}" for i, opt in enumerate(exercise["options"], start=1))
    # Hay preguntas que son SOLO una imagen, sin enunciado de texto
    # (confirmado en vivo: una imagen de una encuesta con las opciones
    # "to circle" / "to check" / ...).
    question = exercise["prompt"] or "(the question is the image below; answer according to what it shows)"
    text = (
        "You are solving an English (B1 level) multiple-choice exercise.\n"
        f"Question: {question}\n"
        f"Options:\n{options_text}"
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object like {"answer": 3} using the 1-based '
        f"option number (from 1 to {exercise.get('option_count') or len(exercise.get('options') or [])}), "
        "no other text, no markdown."
    )

    image_url = exercise.get("image_url")
    if not image_url:
        return _ask_json(text)

    content = [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
    return _ask_json(content)


def _solve_multiple_choice_audio(exercise, prompt_audio_url, option_audio_urls, previous_attempts):
    """
    La pregunta y/o las opciones son clips de audio (sin texto legible en
    esa parte). Usa AUDIO_MODEL (el único de los dos modelos que entiende
    audio) y le manda cada clip presente, etiquetado en el texto.
    """
    question_desc = (
        "The question itself is given as an audio clip below (listen to it first)."
        if prompt_audio_url
        else f"Question: {exercise['prompt']}"
    )

    if option_audio_urls:
        options_desc = (
            "The options are given as audio clips below, in order (option 1, "
            "option 2, ...). Listen to each and pick the best answer."
        )
    else:
        options_text = "\n".join(f"{i}. {opt}" for i, opt in enumerate(exercise["options"], start=1))
        options_desc = f"Options:\n{options_text}"

    text = (
        "You are solving an English (B1 level) multiple-choice exercise.\n"
        f"{question_desc}\n"
        f"{options_desc}"
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object like {"answer": 3} using the 1-based '
        f"option number (from 1 to {exercise.get('option_count') or len(exercise.get('options') or [])}), "
        "no other text, no markdown."
    )
    content = [{"type": "text", "text": text}]
    if prompt_audio_url:
        content.append({"type": "audio_url", "audio_url": {"url": prompt_audio_url}})
    if option_audio_urls:
        for url in option_audio_urls:
            if url:
                content.append({"type": "audio_url", "audio_url": {"url": url}})
    return _ask_json(content, model=AUDIO_MODEL)


def _solve_cloze_dropdown(exercise, previous_attempts):
    blanks_text = "\n".join(
        f"Blank {i}: " + ", ".join(f"{j}={opt}" for j, opt in enumerate(opts))
        for i, opts in enumerate(exercise["blanks"], start=1)
    )
    prompt = (
        "You are solving an English (B1 level) fill-in-the-blank exercise.\n"
        "Each blank in the text is marked exactly where it goes as ___N___ "
        "(e.g. ___1___ is where Blank 1 goes).\n"
        f"Text: {exercise['text']}\n\n"
        f"Options per blank:\n{blanks_text}"
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        f"There are EXACTLY {len(exercise['blanks'])} blank(s).\n"
        'Respond with ONLY a JSON object like {"answers": [1, 2, 0]} using the '
        "0-based option index for each blank IN ORDER (one number per blank, each "
        "within that blank's own option list), no other text, no markdown."
    )
    return _ask_json(prompt)


def _solve_cloze_input(exercise, previous_attempts):
    text = (
        "You are solving an English (B1 level) fill-in-the-blank exercise. "
        "There are no options to choose from — you must supply the exact "
        "word or short phrase that belongs in each blank, based on context "
        "and grammar.\n"
        "Each blank in the text is marked exactly where it goes as ___N___ "
        "(e.g. ___1___ is where blank 1 goes).\n"
        f"Text: {exercise['text']}"
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        f"There are EXACTLY {exercise['blank_count']} blank(s). "
        'Respond with ONLY a JSON object like {"answers": ["not"]} with EXACTLY '
        f"{exercise['blank_count']} string(s), one per blank, in order, no other text, no markdown."
    )
    return _ask_json(text)


def _solve_text_input(exercise, previous_attempts):
    """
    "Escriba la respuesta": texto libre, sin opciones. Rosetta compara
    contra una respuesta esperada concreta, así que la longitud que muestra
    ("(7 caracteres)") es una pista muy fuerte y se le pasa al modelo para
    que descarte parafraseos del largo equivocado.
    """
    length_hint = exercise.get("expected_length")
    instructions = exercise.get("instructions")
    text = (
        "You are solving an English (B1 level) written-answer exercise. "
        "There are no options: write the exact answer expected, nothing more.\n"
        + (f"Instructions shown on screen: {instructions}\n" if instructions else "")
        + f"Question: {exercise['prompt']}\n"
    )
    if length_hint:
        # Rosetta muestra "(N caracteres)" junto al campo, con el campo aún
        # vacío. Se le pasa al modelo como pista fuerte de longitud, pero
        # NO como restricción absoluta: no está confirmado si es la
        # longitud exacta esperada o un mínimo.
        text += (
            f"The page shows a hint that the answer is around {length_hint} "
            "characters long. Prefer an answer of about that length.\n"
        )
    text += (
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object like {"answer": "driving"} — just '
        "the answer text, no explanation, no other text, no markdown."
    )

    image_url = exercise.get("image_url")
    if not image_url:
        return _ask_json(text)

    content = [
        {"type": "text", "text": text},
        {"type": "image_url", "image_url": {"url": image_url}},
    ]
    return _ask_json(content)


def _solve_matching(exercise, previous_attempts):
    words = exercise["options"]
    targets = exercise["targets"]

    if exercise.get("target_audio_urls"):
        return _solve_matching_audio(exercise, previous_attempts)

    if exercise["targets_are_images"]:
        if len(targets) > 1:
            # El modelo solo acepta UNA imagen por petición ("At most 1
            # image(s) may be provided", confirmado en vivo), así que una
            # correspondencia con varias imágenes no tiene forma de
            # resolverse preguntándole. Se avisa ya, sin gastar la llamada:
            # quien llama pasa al intento a ciegas y el bot aprende la
            # respuesta que Rosetta revela tras dos fallos.
            raise ValueError(
                f"correspondencia con {len(targets)} imágenes: el modelo solo admite una por petición"
            )
        content = [
            {
                "type": "text",
                "text": (
                    f"These images are numbered 1 to {len(targets)} in the order shown. "
                    f"Match each word to the number of the image it represents: {words}."
                    f"{_format_previous_attempts(previous_attempts)}\n\n"
                    'Respond with ONLY a JSON object like {"fuel cap": 1, "hinge": 3}, '
                    "mapping every word to an image number, no other text, no markdown."
                ),
            }
        ]
        for url in targets:
            content.append({"type": "image_url", "image_url": {"url": url}})
    else:
        targets_text = "\n".join(f"{i}. {t}" for i, t in enumerate(targets, start=1))
        content = (
            "You are matching English (B1 level) sentences. Match each of these "
            f"phrases/sentences to the numbered target sentence it best completes "
            f"or explains:\nPhrases: {words}\n\nTargets:\n{targets_text}"
            f"{_format_previous_attempts(previous_attempts)}\n\n"
            'Respond with ONLY a JSON object mapping each phrase (exact text) to the '
            'target number, e.g. {"She lowers the flaps.": 1}, no other text, no markdown.'
        )

    result = _ask_json(content)
    return {"pairs": {word: int(target) for word, target in result.items()}}


def _solve_matching_audio(exercise, previous_attempts):
    """
    Los targets son clips de audio (sin texto ni imagen) — es un ejercicio
    de escucha, no de habla grabada. Usa AUDIO_MODEL (el único de los dos
    que entiende audio) para "escuchar" cada target y emparejarlo con la
    frase que mejor le corresponde.
    """
    words = exercise["options"]
    target_audio_urls = exercise["target_audio_urls"]
    target_count = len(target_audio_urls)

    # Confirmado en vivo que la redacción anterior confundía al modelo: en su
    # razonamiento dudaba si tenía que devolver el número de la FRASE o el del
    # CLIP. Ahora se numeran los clips explícitamente y se dice qué número va.
    phrases_text = "\n".join(f"- {w}" for w in words)
    text = (
        "You are matching English (B1 level) phrases to spoken audio clips.\n"
        f"Below are {target_count} audio clips, in order: AUDIO 1, AUDIO 2, ..., AUDIO {target_count}.\n"
        "Listen to each clip. Then, for EACH phrase below, decide which audio clip it "
        "goes with (the phrase that best completes or describes what is said in that clip).\n"
        f"Phrases:\n{phrases_text}\n"
        f"Each audio number (1 to {target_count}) must be used exactly once."
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object mapping each phrase (copied EXACTLY) to its AUDIO '
        'number, e.g. {"<phrase>": 2}, no other text, no markdown.'
    )
    content = [{"type": "text", "text": text}]
    for url in target_audio_urls:
        content.append({"type": "audio_url", "audio_url": {"url": url}})

    result = _ask_json(content, model=AUDIO_MODEL)
    return {"pairs": {word: int(target) for word, target in result.items()}}


def _solve_ordering(exercise, previous_attempts):
    items = exercise["items"]
    items_text = "\n".join(f"{i}. {item}" for i, item in enumerate(items))
    text = (
        "You are solving an English (B1 level) ordering exercise: arrange these "
        "items/phrases into the most logical order (e.g. steps in a process, or "
        "a grammatically correct sentence).\n"
        f"Items (currently in a random order):\n{items_text}"
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        f"There are EXACTLY {len(items)} items, numbered 0 to {len(items) - 1}. "
        f'Respond with ONLY a JSON object like {{"order": {list(reversed(range(len(items))))}}} listing '
        f"ALL {len(items)} indices in the correct final order, each index exactly once "
        "(do not drop any item), no other text, no markdown."
    )
    result = _ask_json(text)
    order_indices = result["order"]
    if sorted(order_indices) != list(range(len(items))):
        raise ValueError(f"Respuesta de la IA no es una permutación válida de los {len(items)} ítems: {order_indices}")
    return {"order": [items[i] for i in order_indices]}


def _solve_text_rewrite(exercise, previous_attempts):
    """
    "Vuelva a escribir el texto según el ejemplo": se le da al modelo el
    ejemplo ya resuelto por Rosetta, que es lo que dice qué transformación
    se pide (ej. "I (may/to take) your coat?" -> "May I take your coat?").
    """
    n = len(exercise["prompts"])
    examples = "\n".join(f'  "{e["prompt"]}" -> "{e["value"]}"' for e in exercise["examples"] if e.get("value"))
    items = "\n".join(f"{i}. {p}" for i, p in enumerate(exercise["prompts"], start=1))
    text = (
        "You are solving an English (B1 level) rewriting exercise: rewrite each sentence "
        "following EXACTLY the same pattern as the solved example.\n"
        f"Solved example:\n{examples}\n\n"
        f"Sentences to rewrite:\n{items}\n"
        f"There are EXACTLY {n} sentences."
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object like {"answers": ["...", ...]} with EXACTLY '
        f"{n} rewritten sentences in order, no other text, no markdown."
    )
    answers = _ask_json(text)["answers"]
    if len(answers) != n:
        raise ValueError(f"se esperaban {n} frases y la IA dio {len(answers)}")
    return {"answers": answers}


def _solve_cloze_drag(exercise, previous_attempts):
    """
    Huecos que se rellenan con palabras de un banco común (cada palabra se
    usa como mucho una vez).
    """
    n = exercise["blank_count"]
    text = (
        "You are solving an English (B1 level) fill-in-the-blank exercise.\n"
        "Each blank in the text is marked exactly where it goes as ___N___.\n"
        f"Text:\n{exercise['text']}\n\n"
        f"Word bank (use each word at most once): {json.dumps(exercise['options'], ensure_ascii=False)}\n"
        f"There are EXACTLY {n} blank(s)."
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object like {"answers": ["word for blank 1", ...]} with EXACTLY '
        f"{n} strings copied exactly from the word bank, in blank order, no other text, no markdown."
    )
    result = _ask_json(text)
    answers = result["answers"]
    bank = Counter(exercise["options"])
    if len(answers) != n or any(Counter(answers)[w] > bank[w] for w in answers):
        raise ValueError(f"respuesta inválida para {n} hueco(s) con el banco {exercise['options']}: {answers}")
    return {"answers": answers}


def _solve_sentence_build(exercise, previous_attempts):
    """Ordenar palabras sueltas para formar una oración correcta."""
    words = exercise["words"]
    text = (
        "You are solving an English (B1 level) exercise: arrange ALL of these words "
        "into one correct, natural English sentence.\n"
        f"Words (in random order): {json.dumps(words, ensure_ascii=False)}\n"
        f"Use every word exactly once ({len(words)} words, keep punctuation attached as given)."
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object like {"order": ["first", "second", ...]} '
        "with the words copied exactly, no other text, no markdown."
    )
    result = _ask_json(text)
    order = result["order"]
    if Counter(order) != Counter(words):
        raise ValueError(f"no usa exactamente las {len(words)} palabras dadas: {order}")
    return {"order": order}


def _solve_matching_audio_options(exercise, previous_attempts):
    """
    Correspondencia donde los DESTINOS son texto y lo que se arrastra son
    clips de audio. Se le da al modelo de audio cada clip numerado y se
    traduce su respuesta al identificador estable de cada clip.
    """
    targets = exercise["targets"]
    clips = exercise["option_audio_urls"]
    ids = exercise["option_audio_ids"]
    targets_text = "\n".join(f"{i}. {t}" for i, t in enumerate(targets, start=1))
    text = (
        "You are solving an English (B1 level) matching exercise.\n"
        f"Below are {len(clips)} audio clips, in order: AUDIO 1 ... AUDIO {len(clips)}.\n"
        f"And these {len(targets)} numbered texts:\n{targets_text}\n"
        "Listen to each clip and decide which numbered text it answers or goes with. "
        "Each text number is used exactly once."
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object mapping each AUDIO number to a text number, like '
        '{"1": 3, "2": 1}, no other text, no markdown.'
    )
    content = [{"type": "text", "text": text}]
    for url in clips:
        content.append({"type": "audio_url", "audio_url": {"url": url}})
    result = _ask_json(content, model=AUDIO_MODEL)
    mapping = {}
    for audio_n, target_n in result.items():
        a, t = int(audio_n), int(target_n)
        if not (1 <= a <= len(ids)) or not (1 <= t <= len(targets)):
            raise ValueError(f"número fuera de rango en {result}")
        mapping[ids[a - 1]] = t
    if len(mapping) != len(ids) or len(set(mapping.values())) != len(ids):
        raise ValueError(f"asignación incompleta o repetida: {result}")
    return {"target_for_clip": mapping}


def solve_exercise(exercise_data: dict, previous_attempts: list | None = None) -> dict:
    """
    exercise_data: dict con el ejercicio extraído por browser.get_current_exercise(),
    con forma según su "type":

        multiple_choice -> {"type", "prompt", "options": [str, ...]}
        matching        -> {"type", "targets": [str, ...], "targets_are_images": bool, "options": [str, ...],
                            "target_audio_urls": [str, ...] opcional (targets solo-audio)}
        cloze_dropdown  -> {"type", "text", "blanks": [[str, ...], ...]}
        cloze_input     -> {"type", "text", "blank_count": int}
        text_input      -> {"type", "prompt", "instructions", "image_url": str|None,
                            "expected_length": int|None}
        ordering        -> {"type", "items": [str, ...]}  (en orden desordenado, a reordenar)

    previous_attempts: soluciones ya intentadas para este mismo ejercicio que
    resultaron incorrectas (mismo shape que el return de esta función), para
    que la IA no repita la misma respuesta al reintentar. Vacía en el primer
    intento.

    return: solución estructurada que bot.apply_solution() sabe aplicar:

        multiple_choice -> {"answer": <índice 1-based de la opción>}
        cloze_dropdown  -> {"answers": [<índice 0-based>, ...]}  (uno por blank)
        cloze_input     -> {"answers": [<str>, ...]}  (texto libre, uno por blank)
        text_input      -> {"answer": <str>}  (respuesta escrita completa)
        matching        -> {"pairs": {<palabra>: <índice 1-based del target>, ...}}
        ordering        -> {"order": [str, ...]}  (los mismos "items", en el orden correcto)
    """
    previous_attempts = previous_attempts or []
    exercise_type = exercise_data["type"]

    if exercise_data.get("unsolvable"):
        return _blind_guess(exercise_data, previous_attempts)

    if exercise_type == "multiple_choice":
        solution = _solve_multiple_choice(exercise_data, previous_attempts)
        # Confirmado en vivo: la IA respondió "opción 5" en una pregunta de 4.
        # El bot fue a pulsar una quinta opción inexistente y esperó 30 s.
        count = exercise_data.get("option_count") or len(exercise_data.get("options") or [])
        answer = solution.get("answer")
        if count and not (isinstance(answer, int) and 1 <= answer <= count):
            raise ValueError(f"respuesta fuera de rango: {answer!r} (hay {count} opciones)")
        return solution

    if exercise_type == "cloze_dropdown":
        solution = _solve_cloze_dropdown(exercise_data, previous_attempts)
        # Confirmado en vivo: la IA devolvió [3, 1] para UN espacio de 3
        # opciones (índices válidos 0-2). El bot fue a pulsar una opción
        # inexistente y esperó 30 s.
        blanks = exercise_data["blanks"]
        answers = solution.get("answers") or []
        if len(answers) != len(blanks) or any(
            not isinstance(a, int) or not (0 <= a < len(opts)) for a, opts in zip(answers, blanks)
        ):
            raise ValueError(f"respuesta inválida para {len(blanks)} espacio(s) de {[len(o) for o in blanks]} opciones: {answers}")
        return solution

    if exercise_type == "cloze_input":
        return _solve_cloze_input(exercise_data, previous_attempts)

    if exercise_type == "matching":
        solution = _solve_matching(exercise_data, previous_attempts)
        # Confirmado en vivo: la IA devolvió las FRASES de destino como
        # claves en vez de las palabras a arrastrar, y el bot se puso a
        # buscar una palabra que no existe.
        options = exercise_data["options"]
        targets = exercise_data["targets"]
        pairs = solution.get("pairs") or {}
        if set(pairs) != set(options) or sorted(pairs.values()) != list(range(1, len(targets) + 1)):
            raise ValueError(
                f"emparejamiento inválido: claves {list(pairs)[:2]}... deben ser las palabras {options[:2]}... "
                f"y los destinos 1..{len(targets)}"
            )
        return solution

    if exercise_type == "ordering":
        return _solve_ordering(exercise_data, previous_attempts)

    if exercise_type == "text_input":
        return _solve_text_input(exercise_data, previous_attempts)

    if exercise_type == "text_rewrite":
        return _solve_text_rewrite(exercise_data, previous_attempts)

    if exercise_type == "cloze_drag":
        return _solve_cloze_drag(exercise_data, previous_attempts)

    if exercise_type == "sentence_build":
        return _solve_sentence_build(exercise_data, previous_attempts)

    if exercise_type == "matching_audio_options":
        return _solve_matching_audio_options(exercise_data, previous_attempts)

    raise NotImplementedError(f"ai.solve_exercise no soporta el tipo '{exercise_type}'")

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

from openai import OpenAI

import config

MODEL = "meta/llama-3.2-11b-vision-instruct"
AUDIO_MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"

_client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=config.AI_API_KEY)


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

    raise NotImplementedError(f"No se sabe adivinar a ciegas el tipo '{exercise_type}'")


def _solve_multiple_choice(exercise, previous_attempts):
    prompt_audio_url = exercise.get("prompt_audio_url")
    option_audio_urls = exercise.get("option_audio_urls")
    if prompt_audio_url or option_audio_urls:
        return _solve_multiple_choice_audio(exercise, prompt_audio_url, option_audio_urls, previous_attempts)

    options_text = "\n".join(f"{i}. {opt}" for i, opt in enumerate(exercise["options"], start=1))
    text = (
        "You are solving an English (B1 level) multiple-choice exercise.\n"
        f"Question: {exercise['prompt']}\n"
        f"Options:\n{options_text}"
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object like {"answer": 3} using the 1-based '
        "option number, no other text, no markdown."
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
        "option number, no other text, no markdown."
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
        'Respond with ONLY a JSON object like {"answers": [1, 2, 0]} using the '
        "0-based option index for each blank in order, no other text, no markdown."
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

    text = (
        "You are matching English (B1 level) phrases to spoken audio clips. "
        f"The targets are given as audio clips below, in order (target 1, target 2, "
        f"..., target {target_count}). Listen to each clip and match it to the phrase "
        f"that best completes or explains it.\nPhrases: {words}"
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object mapping each phrase (exact text) to the '
        'target number, e.g. {"She lowers the flaps.": 1}, no other text, no markdown.'
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
        return _solve_multiple_choice(exercise_data, previous_attempts)

    if exercise_type == "cloze_dropdown":
        return _solve_cloze_dropdown(exercise_data, previous_attempts)

    if exercise_type == "cloze_input":
        return _solve_cloze_input(exercise_data, previous_attempts)

    if exercise_type == "matching":
        return _solve_matching(exercise_data, previous_attempts)

    if exercise_type == "ordering":
        return _solve_ordering(exercise_data, previous_attempts)

    if exercise_type == "text_input":
        return _solve_text_input(exercise_data, previous_attempts)

    raise NotImplementedError(f"ai.solve_exercise no soporta el tipo '{exercise_type}'")

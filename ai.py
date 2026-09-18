"""
Integración con el modelo de IA encargado de resolver los ejercicios.

Usa la API de NVIDIA build (https://build.nvidia.com), compatible con el SDK
de OpenAI. Modelo principal: meta/muse-glimmer-30b (texto + imágenes, lo que
hace falta para "matching" con imágenes). Para opciones que son solo audio
(sin texto legible) se usa nvidia/nemotron-3-nano-omni-30b-a3b-reasoning, que
sí entiende audio (muse-glimmer no).
"""

import json
import random

from openai import OpenAI

import config

MODEL = "meta/muse-glimmer-30b"
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
    if not previous_attempts:
        return ""
    return (
        "\n\nYa se intentaron estas respuestas y fueron INCORRECTAS, no las repitas: "
        + json.dumps(previous_attempts)
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


def _solve_matching(exercise, previous_attempts):
    words = exercise["options"]
    targets = exercise["targets"]

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


def _solve_ordering(exercise, previous_attempts):
    items = exercise["items"]
    items_text = "\n".join(f"{i}. {item}" for i, item in enumerate(items))
    text = (
        "You are solving an English (B1 level) ordering exercise: arrange these "
        "items/phrases into the most logical order (e.g. steps in a process, or "
        "a grammatically correct sentence).\n"
        f"Items (currently in a random order):\n{items_text}"
        f"{_format_previous_attempts(previous_attempts)}\n\n"
        'Respond with ONLY a JSON object like {"order": [3, 1, 0, 2, 4]} listing '
        "the 0-based indices of the items above in the correct final order "
        "(same length as the items, each index used exactly once), no other "
        "text, no markdown."
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
        matching        -> {"type", "targets": [str, ...], "targets_are_images": bool, "options": [str, ...]}
        cloze_dropdown  -> {"type", "text", "blanks": [[str, ...], ...]}
        ordering        -> {"type", "items": [str, ...]}  (en orden desordenado, a reordenar)

    previous_attempts: soluciones ya intentadas para este mismo ejercicio que
    resultaron incorrectas (mismo shape que el return de esta función), para
    que la IA no repita la misma respuesta al reintentar. Vacía en el primer
    intento.

    return: solución estructurada que bot.apply_solution() sabe aplicar:

        multiple_choice -> {"answer": <índice 1-based de la opción>}
        cloze_dropdown  -> {"answers": [<índice 0-based>, ...]}  (uno por blank)
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

    if exercise_type == "matching":
        return _solve_matching(exercise_data, previous_attempts)

    if exercise_type == "ordering":
        return _solve_ordering(exercise_data, previous_attempts)

    raise NotImplementedError(f"ai.solve_exercise no soporta el tipo '{exercise_type}'")

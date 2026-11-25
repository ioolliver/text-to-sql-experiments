"""Generate one SQL prediction per example without feedback from the database."""

import re
from time import perf_counter

from .llm import LLMError, complete


def predict(
    example: dict[str, str],
    *,
    dialect: str,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
) -> dict:
    prompt = (
        f"Write a single {dialect} SQL query that answers the question. "
        "Return only the SQL query.\n\n"
        f"Database schema:\n{example['schema']}\n\n"
        f"Question:\n{example['question']}"
    )
    prediction = {
        "id": example["id"],
        "prompt": prompt,
        "response": None,
        "sql": None,
        "response_model": None,
        "usage": None,
        "finish_reason": None,
        "error": None,
    }

    started = perf_counter()
    try:
        prediction.update(complete(
            base_url=base_url,
            api_key=api_key,
            model=model,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        ))
    except LLMError as exc:
        prediction["error"] = str(exc)
    prediction["latency_ms"] = round((perf_counter() - started) * 1000, 3)

    if prediction["response"] is not None:
        response = prediction["response"].strip()
        fenced = re.fullmatch(r"```(?:sql)?[ \t]*\r?\n(.*?)\r?\n```", response, re.IGNORECASE | re.DOTALL)
        prediction["sql"] = (fenced[1].strip() if fenced else response) or None
        if prediction["sql"] is None:
            prediction["error"] = "Empty SQL response"
    return prediction

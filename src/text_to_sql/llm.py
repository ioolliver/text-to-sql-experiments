"""Minimal client for a Chat Completions-compatible HTTP endpoint."""

import json
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class LLMError(Exception):
    """The request failed or the response did not match the expected format."""


class RejectRedirects(HTTPRedirectHandler):
    # A redirect could forward the prompt or authorization header to another host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def complete(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout_seconds: float,
) -> dict:
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with build_opener(RejectRedirects()).open(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except HTTPError as exc:
        exc.close()
        raise LLMError(f"HTTP {exc.code}") from exc
    except (URLError, OSError) as exc:
        raise LLMError(f"Request failed: {exc}") from exc
    except (ValueError, UnicodeError) as exc:
        raise LLMError("Invalid JSON response") from exc

    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise TypeError("Expected text content")
        return {
            "response": content,
            "response_model": payload.get("model"),
            "usage": payload.get("usage"),
            "finish_reason": choice.get("finish_reason"),
        }
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Response did not contain a text completion") from exc

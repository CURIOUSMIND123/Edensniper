"""Thin wrapper over the Gemini text API.

Text generation sits on the free tier of a Google AI Studio key, so this
works even when video is being produced by hand in the Gemini app.
"""
from __future__ import annotations

import json
import re
from typing import Any

_client = None


class LLMUnavailable(RuntimeError):
    """No API key, or the SDK isn't installed."""


def get_client(api_key: str | None):
    global _client
    if _client is not None:
        return _client
    if not api_key:
        raise LLMUnavailable(
            "No GEMINI_API_KEY set. Get a free key at https://aistudio.google.com/apikey"
        )
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - depends on install
        raise LLMUnavailable("google-genai not installed (pip install google-genai)") from exc
    _client = genai.Client(api_key=api_key)
    return _client


def extract_json(text: str) -> Any:
    """Pull JSON out of a model response, fenced or not."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Last resort: the outermost array or object in the response.
    for opener, closer in (("[", "]"), ("{", "}")):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError(f"model did not return usable JSON: {text[:300]}")


def generate_json(api_key: str | None, model: str, prompt: str, temperature: float = 1.0) -> Any:
    """One JSON-returning text call. Exceptions bubble up to the QuotaGate."""
    from google.genai import types

    client = get_client(api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
        ),
    )
    return extract_json(response.text or "")

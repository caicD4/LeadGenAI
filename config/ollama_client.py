"""
Gemini AI client for LeadGenAI.

This module is intentionally named ollama_client.py (legacy name) to avoid
breaking existing imports.  All AI calls now go through Google Gemini.
"""

import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

load_dotenv()

# gemini-3.5-flash-lite: fast, cost-effective, confirmed available for this key.
# (gemini-2.0-flash-lite and gemini-2.5-flash are deprecated/unavailable)
MODEL = "gemini-3.5-flash-lite"

# How many times to retry on transient errors (429 rate-limit, 503 overload).
_MAX_RETRIES = 4
# Initial back-off seconds — doubles on each retry.
_BACKOFF_BASE = 5


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from the environment. "
            "Add it to your .env file."
        )

    return genai.Client(api_key=api_key)


def ask_ai(prompt: str) -> str:
    """
    Send a prompt to Gemini and return the response text.

    Automatically retries on 429 (quota / rate-limit) and 503 (overload)
    with exponential back-off.

    Raises:
        RuntimeError: If all retries are exhausted or a non-retryable error
                      occurs.
    """

    client = _get_client()
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
            )
            return response.text

        except genai_errors.ClientError as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "code", None)

            # Retry on rate-limit (429) or server overload (503).
            if status in (429, 503) and attempt < _MAX_RETRIES:
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))  # 5, 10, 20, …
                print(
                    f"[Gemini] HTTP {status} on attempt {attempt}/{_MAX_RETRIES}."
                    f" Retrying in {wait}s…"
                )
                time.sleep(wait)
                last_exc = exc
                continue

            raise RuntimeError(f"Gemini API call failed (HTTP {status}): {exc}") from exc

        except Exception as exc:
            raise RuntimeError(f"Gemini API call failed: {exc}") from exc

    raise RuntimeError(
        f"Gemini API call failed after {_MAX_RETRIES} retries: {last_exc}"
    ) from last_exc


def ask_ai_json(prompt: str) -> dict:
    """
    Send a prompt to Gemini, parse the response as JSON, and return the dict.

    The prompt should instruct the model to return only JSON.
    This function strips markdown code fences and re-tries once on bad JSON.

    Raises:
        ValueError: If the response cannot be parsed as JSON after cleaning.
        RuntimeError: If the underlying Gemini call fails.
    """

    raw = ask_ai(prompt)
    cleaned = clean_json_response(raw)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Second attempt: ask Gemini to fix its own output.
        fix_prompt = (
            "The following text was supposed to be valid JSON but is not.\n"
            "Return ONLY the corrected valid JSON with no explanation and no code fences:\n\n"
            + cleaned[:2000]
        )
        raw2 = ask_ai(fix_prompt)
        cleaned2 = clean_json_response(raw2)
        try:
            return json.loads(cleaned2)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Gemini returned non-JSON after two attempts.\n"
                f"First response (first 300 chars): {raw[:300]!r}\n"
                f"Error: {exc}"
            ) from exc


def clean_json_response(raw: str) -> str:
    """
    Strip markdown code fences that models sometimes wrap JSON in.

    Handles:
        ```json
        { ... }
        ```
    and bare ``` ... ``` fences.
    """

    text = raw.strip()

    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]  # drop the opening fence line (e.g. ```json)

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # drop the closing fence

        text = "\n".join(lines).strip()

    return text
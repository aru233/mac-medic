from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors

load_dotenv()

# Any Gemini model that supports text generation. Flash-Lite is cheapest.
MODEL_ID = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")

# Fallback model used if the primary model hits a rate limit (HTTP 429).
# Once switched within a session, we stay on the fallback for the rest of
# the session to avoid hammering the exhausted quota.
FALLBACK_MODEL_ID = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")

_client: genai.Client | None = None
_active_model: str = MODEL_ID  # flips to FALLBACK_MODEL_ID after the first 429


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Create a .env file next to llm.py with:\n"
                "  GEMINI_API_KEY=your-key-here\n"
                "  GEMINI_MODEL=gemini-2.5-flash-lite\n"
                "Get a free key at: https://aistudio.google.com/apikey"
            )
        _client = genai.Client(api_key=api_key)
    return _client


def active_model() -> str:
    """Return the model ID currently being used (primary or fallback)."""
    return _active_model


def _is_rate_limit_error(err: Exception) -> bool:
    status = getattr(err, "status_code", None) or getattr(err, "code", None)
    if status == 429:
        return True
    msg = str(err).lower()
    return "429" in msg or "rate" in msg or "quota" in msg or "resource_exhausted" in msg


def generate_with_fallback(contents, config):
    """
    Call Gemini, falling back to FALLBACK_MODEL_ID on rate-limit errors.

    Returns the SDK response object. Prints a one-line notice when the
    fallback kicks in, so the user sees which model actually answered.
    """
    global _active_model
    client = get_client()

    try:
        return client.models.generate_content(
            model=_active_model,
            contents=contents,
            config=config,
        )
    except genai_errors.ClientError as err:
        if not _is_rate_limit_error(err) or _active_model == FALLBACK_MODEL_ID:
            raise
        print(
            f"  [rate limit on {_active_model} — switching to {FALLBACK_MODEL_ID} "
            f"for the rest of the session]"
        )
        _active_model = FALLBACK_MODEL_ID
        return client.models.generate_content(
            model=_active_model,
            contents=contents,
            config=config,
        )

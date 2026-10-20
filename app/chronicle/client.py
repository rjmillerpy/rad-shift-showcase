"""Anthropic client wrapper for chronicle generation.

Owns the single shared Anthropic client (rule 66) and the broad-catch logging
around external network calls. Both `call_haiku` and `stream_haiku` degrade to
a `None`/empty result on failure so callers can fall back gracefully.
"""

import logging
import os
from collections.abc import Iterator

import anthropic

from app.chronicle.constants import (
    ANTHROPIC_TIMEOUT_SECONDS,
    CHRONICLE_MAX_TOKENS,
    CHRONICLE_MODEL,
)

logger = logging.getLogger(__name__)


_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic | None:
    """Return the shared Anthropic client, or None when ANTHROPIC_API_KEY is unset."""
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    _client = anthropic.Anthropic(api_key=api_key)
    return _client


def reset_client() -> None:
    """Drop the cached client. Intended for tests that toggle the env var."""
    global _client
    _client = None


def call_haiku(prompt: str, system: str) -> str | None:
    """Call Anthropic Haiku. Returns the response text or None on failure.

    The broad `Exception` catch is deliberate: chronicle generation degrades to
    the rule-based fallback for *any* API-side error, and callers must not
    surface Anthropic internals to end users (rule 10).
    """
    client = get_client()
    if client is None:
        logger.warning("ANTHROPIC_API_KEY not set, falling back")
        return None
    try:
        msg = client.messages.create(
            model=CHRONICLE_MODEL,
            max_tokens=CHRONICLE_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            timeout=ANTHROPIC_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 — see docstring above
        logger.error("Haiku call failed: %s", exc)
        return None
    # A response can open with non-text blocks (e.g. thinking); take the first text one.
    return next((block.text for block in msg.content if block.type == "text"), None)


def stream_haiku(
    prompt: str,
    system: str,
) -> Iterator[str]:
    """Stream tokens from Anthropic Haiku. Yields nothing on failure."""
    client = get_client()
    if client is None:
        logger.warning("ANTHROPIC_API_KEY not set")
        return
    try:
        with client.messages.stream(
            model=CHRONICLE_MODEL,
            max_tokens=CHRONICLE_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            timeout=ANTHROPIC_TIMEOUT_SECONDS,
        ) as stream:
            yield from stream.text_stream
    except Exception as exc:  # noqa: BLE001 — see call_haiku above
        logger.error("Haiku stream failed: %s", exc)

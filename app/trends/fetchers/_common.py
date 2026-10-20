"""Shared plumbing for the trend fetchers — HTTP fetch + error mapping.

Every fetcher pulls text from a public HTTP endpoint and converts underlying
`httpx` errors into a domain-level `ConnectionError` so the caller (the
service layer) only has to catch one exception type (rule 33/36).
"""

# Stdlib ElementTree only for the Element type; parsing goes through defusedxml.
import xml.etree.ElementTree as ET  # nosec B405

import httpx

REQUEST_TIMEOUT_SECONDS = 10
MAX_TITLE_CHARS = 200


def http_get_text(url: str, prefix: str, headers: dict | None = None) -> str:
    """Fetch `url` and return its response body as text.

    `prefix` labels the failure in the raised `ConnectionError` so the caller
    (or a log line) can identify which source failed without inspecting a
    traceback. Callers that expect JSON should call this then wrap
    `json.loads` in their own try/except (see `reddit._fetch_json`).
    """
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
    except httpx.TimeoutException as exc:
        raise ConnectionError(f"{prefix} timed out for {url}") from exc
    except httpx.HTTPStatusError as exc:
        raise ConnectionError(f"{prefix} HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise ConnectionError(f"{prefix} fetch failed: {exc}") from exc


def child_text(element: ET.Element, tag: str) -> str | None:
    """The stripped text of `element`'s first `tag` child; None if absent or blank."""
    child = element.find(tag)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None

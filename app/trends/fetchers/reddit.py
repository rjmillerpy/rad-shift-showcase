"""Fetch r/popular top posts via Reddit's public Atom feed.

Reddit's `r/popular.json` endpoint now returns HTTP 403 for unauthenticated
callers regardless of User-Agent. The `.rss` endpoint (Atom feed) still
serves the same top-25 list without auth, so we parse that instead. The
trade-off is that RSS does not carry upvote counts — `volume` is therefore
always None for Reddit items (compared to the old JSON path which set it to
'N upvotes').
"""

import logging

# Stdlib ElementTree only for the Element/ParseError types; all parsing of the
# (untrusted, remote) feed goes through defusedxml, which blocks XML bombs and
# external-entity tricks.
import xml.etree.ElementTree as ET  # nosec B405

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_fromstring

from app.trends.fetchers._common import MAX_TITLE_CHARS, child_text, http_get_text
from app.trends.schema import SOURCE_REDDIT, TrendItem

logger = logging.getLogger(__name__)

REDDIT_POPULAR_URL = "https://old.reddit.com/r/popular/.rss"
MAX_ITEMS = 25
USER_AGENT = "rad-shift-trends/1.0 (https://radshift.local)"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


def fetch_reddit_popular() -> list[TrendItem]:
    """Return the current top 25 posts from r/popular as trend items."""
    xml_text = http_get_text(
        REDDIT_POPULAR_URL,
        "reddit",
        headers={"User-Agent": USER_AGENT},
    )
    return _parse_trend_items(xml_text)


def _parse_trend_items(xml_text: str) -> list[TrendItem]:
    try:
        root = safe_fromstring(xml_text)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ConnectionError(f"reddit returned invalid XML: {exc}") from exc

    items: list[TrendItem] = []
    for entry in root.iter(f"{ATOM_NS}entry"):
        if len(items) >= MAX_ITEMS:
            break
        title = child_text(entry, f"{ATOM_NS}title")
        if not title:
            continue
        items.append(
            TrendItem(
                source=SOURCE_REDDIT,
                rank=len(items) + 1,
                keyword=title[:MAX_TITLE_CHARS],
                url=_get_link_href(entry),
                # RSS does not include upvote counts; kept None on purpose.
                volume=None,
                category=_get_category_label(entry),
            )
        )
    return items


def _get_link_href(entry: ET.Element) -> str | None:
    link = entry.find(f"{ATOM_NS}link")
    if link is None:
        return None
    href = link.get("href")
    return href or None


def _get_category_label(entry: ET.Element) -> str | None:
    category = entry.find(f"{ATOM_NS}category")
    if category is None:
        return None
    return category.get("label") or None

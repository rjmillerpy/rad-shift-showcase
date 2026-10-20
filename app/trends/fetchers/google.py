"""Fetch Google daily search trends via their public RSS feed."""

import logging

# Stdlib ElementTree only for the Element/ParseError types; all parsing of the
# (untrusted, remote) feed goes through defusedxml, which blocks XML bombs and
# external-entity tricks.
import xml.etree.ElementTree as ET  # nosec B405

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as safe_fromstring

from app.trends.fetchers._common import child_text, http_get_text
from app.trends.schema import SOURCE_GOOGLE, TrendItem

logger = logging.getLogger(__name__)

GOOGLE_TRENDS_RSS_TEMPLATE = "https://trends.google.com/trending/rss?geo={geo}"
HT_NAMESPACE = "{https://trends.google.com/trending/rss}"
MAX_ITEMS = 50


def fetch_google_trends(geo: str = "US") -> list[TrendItem]:
    """Pull the top ~20 daily search trends for a given geo code (e.g. 'US')."""
    url = GOOGLE_TRENDS_RSS_TEMPLATE.format(geo=geo)
    xml = http_get_text(url, "google trends")
    return _parse_trend_items(xml)


def _parse_trend_items(xml_text: str) -> list[TrendItem]:
    try:
        root = safe_fromstring(xml_text)
    except (ET.ParseError, DefusedXmlException) as exc:
        raise ConnectionError(f"google trends returned invalid XML: {exc}") from exc

    items: list[TrendItem] = []
    for item in root.iter("item"):
        if len(items) >= MAX_ITEMS:
            break
        keyword = child_text(item, "title")
        if not keyword:
            continue
        items.append(
            TrendItem(
                source=SOURCE_GOOGLE,
                rank=len(items) + 1,
                keyword=keyword,
                url=None,
                volume=child_text(item, f"{HT_NAMESPACE}approx_traffic"),
                category=None,
            )
        )
    return items

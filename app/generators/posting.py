"""Helpers for turning filtered ScrapedItems into ``posts`` rows.

Split out from ``service`` to keep that module under the 400-line cap and to
group all "write a scraped item as a post" concerns in one place:
  * picking which bot account to post as,
  * deduping against the bot's recent post history,
  * cleaning Reddit/Markdown formatting out of the body,
  * building the ``post_metadata`` JSON and calling ``create_post``.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.auth.models import User
from app.posts.service import create_post

from .items import ScrapedItem
from .models import GeneratorSource
from .post_metadata import build_scraped_post_metadata

logger = logging.getLogger(__name__)

DEDUPE_LOOKBACK_POSTS = 200
MAX_POST_TEXT_CHARS = 5000
# When the post will display a LinkCard (item has a link), the body can be
# tighter — the card carries the title and the source link, so the body just
# needs to be a teaser. Without a link, the body must stand alone, so it gets
# the much higher cap.
SCRAPED_BODY_MAX_WITH_LINK = 600
CONTINUATION_MARKER = " … (continued at source)"

# Markdown-stripping regexes. Order matters: links first (so the link text is
# preserved before its surrounding formatting is processed); bullets are
# converted to a • glyph BEFORE italic stripping so leading "* item" isn't
# misread as emphasis.
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_HEADING_RE = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_BULLET_RE = re.compile(r"^[*\-]\s+", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_STRIKE_RE = re.compile(r"~~([^~]+)~~")
_CODE_RE = re.compile(r"`([^`]+)`")
_ITALIC_AST_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_ITALIC_UND_RE = re.compile(r"(?<![A-Za-z0-9_])_([^_\n]+)_(?![A-Za-z0-9_])")


def strip_markdown(text: str) -> str:
    r"""Convert common Reddit/Markdown syntax to plain text.

    Preserves line breaks. Not a full markdown parser — just enough cleanup
    to keep scraped Reddit selftext readable when rendered as plain text:

      * ``[label](url)`` → ``label``
      * ``**bold**`` / ``*italic*`` / ``_italic_`` / ``~~strike~~`` → body
      * ``\`code\``` → ``code``
      * ``# Heading`` → ``Heading``
      * ``* item`` / ``- item`` (at line start) → ``• item``
    """
    if not text:
        return ""
    text = _LINK_RE.sub(r"\1", text)
    text = _STRIKE_RE.sub(r"\1", text)
    text = _BOLD_RE.sub(r"\1", text)
    text = _CODE_RE.sub(r"\1", text)
    text = _HEADING_RE.sub("", text)
    text = _BULLET_RE.sub("• ", text)
    text = _ITALIC_AST_RE.sub(r"\1", text)
    text = _ITALIC_UND_RE.sub(r"\1", text)
    return text


def _build_post_text(item: ScrapedItem) -> str:
    """Construct the post body text for a scraped item.

    * Strips Markdown so the body reads as plain prose.
    * When the item has a link, the LinkCard will display the title — so we
      omit the title prefix and cap at ``SCRAPED_BODY_MAX_WITH_LINK`` to keep
      the post from becoming a wall of text.
    * When the item has no link, the title is prepended (since there's no
      card to carry it) and the higher ``MAX_POST_TEXT_CHARS`` cap applies.
    """
    body = strip_markdown(item.text or "")
    has_link = bool(item.link)
    if item.title and not has_link and item.title not in body:
        body = f"{item.title}\n\n{body}"

    cap = SCRAPED_BODY_MAX_WITH_LINK if has_link else MAX_POST_TEXT_CHARS
    if len(body) > cap:
        body = body[: cap - len(CONTINUATION_MARKER)].rstrip() + CONTINUATION_MARKER
    return body


def _get_active_user(source: GeneratorSource, db: Session) -> User:
    """Pick an active profile's user for posting. Rotates randomly."""
    active_profiles = [p for p in source.profiles if p.is_active]
    if not active_profiles:
        raise HTTPException(status_code=400, detail="No active profiles attached to this source")

    profile = random.choice(active_profiles)  # nosec B311 - spreads posts across bots; not security
    user = db.query(User).filter_by(id=profile.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="Attached user account not found")
    return user


def _get_existing_texts(user: User, db: Session) -> set[str]:
    """Return the bot user's recent post texts for dedupe purposes."""
    from app.posts.models import PostModel  # local import keeps module import-time cheap

    recent: list[Any] = (
        db.query(PostModel.text)
        .filter_by(user_id=user.id)
        .order_by(PostModel.id.desc())
        .limit(DEDUPE_LOOKBACK_POSTS)
        .all()
    )
    return {row[0] for row in recent}


def _create_scraped_post(
    item: ScrapedItem,
    source: GeneratorSource,
    user: User,
    body: str,
    db: Session,
) -> None:
    """Persist one scraped item as a post with source + link-card metadata."""
    metadata = build_scraped_post_metadata(source, item)
    create_post(
        text=body,
        post_metadata=json.dumps(metadata),
        unix_timestamp=int(time.time()),
        user=user,
        image_url=item.image_url,
        video_url=None,
        audio_url=None,
        db=db,
    )


def post_filtered_items(source: GeneratorSource, filtered: list[ScrapedItem], db: Session) -> int:
    """Post non-duplicate items as the source's active profile. Returns count posted."""
    user = _get_active_user(source, db)
    existing_texts = _get_existing_texts(user, db)
    posted = 0
    for item in filtered:
        body = _build_post_text(item)
        if body in existing_texts:
            continue
        _create_scraped_post(item, source, user, body, db)
        existing_texts.add(body)
        posted += 1
    return posted

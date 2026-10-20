"""Editions: the one place the public build and the private one differ (open core).

The app reaches every private feature through an `Edition`: the routers it
adds, the generator platforms and web scraper it registers, the Chronicle
prompt and the Amble bindings file. A private package registers its edition
under the entry point group `radshift.plugins`; without one the app runs the
public baseline (app/baseline.py), so the public repository works end to end.

RADSHIFT_EDITION pins the choice. `private` (set in the production image)
makes a missing private package a startup error instead of a quiet fall-back
to the baseline; `public` forces the baseline even when the private package
is installed (the public tests run that way).
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter

    from app.chronicle.prompt import ChroniclePrompt
    from app.generators.platforms.base import PlatformAdapter
    from app.generators.web import WebScraper

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "radshift.plugins"
EDITION_ENV_VAR = "RADSHIFT_EDITION"
PUBLIC = "public"
PRIVATE = "private"
# Reserved for the CSS-selector scraper, which an edition supplies as `web_scraper`.
WEB_PLATFORM = "web"


class EditionError(RuntimeError):
    """The pinned edition can't be loaded, or an edition is malformed."""


@dataclass(frozen=True)
class Edition:
    """Everything an edition contributes. Built once per process."""

    name: str
    routers: tuple[tuple[APIRouter, str], ...]
    platform_adapters: tuple[PlatformAdapter, ...]
    web_scraper: WebScraper | None
    chronicle_prompt: ChroniclePrompt
    amble_bindings_path: Path

    def __post_init__(self) -> None:
        names = [adapter.platform for adapter in self.platform_adapters]
        if "" in names or WEB_PLATFORM in names:
            raise EditionError(f"adapter platform names must be non-empty and not {WEB_PLATFORM!r}")
        if len(set(names)) != len(names):
            raise EditionError(f"duplicate adapter platforms: {sorted(names)}")


def _private_edition() -> Edition | None:
    found = entry_points(group=ENTRY_POINT_GROUP)
    if not found:
        return None
    if len(found) > 1:
        raise EditionError(f"more than one {ENTRY_POINT_GROUP} entry point: {found.names}")
    (entry,) = found
    edition = entry.load()
    if not isinstance(edition, Edition):
        raise EditionError(f"{entry.value} is not an Edition")
    return edition


def _public_edition() -> Edition:
    from app.baseline import EDITION

    return EDITION


def _load(pinned: str | None) -> Edition:
    if pinned not in (None, PUBLIC, PRIVATE):
        raise EditionError(f"{EDITION_ENV_VAR} must be {PUBLIC!r} or {PRIVATE!r}, not {pinned!r}")
    if pinned == PUBLIC:
        return _public_edition()
    private = _private_edition()
    if private is not None:
        return private
    if pinned == PRIVATE:
        raise EditionError(
            f"{EDITION_ENV_VAR}=private but no {ENTRY_POINT_GROUP} package is installed"
        )
    return _public_edition()


@cache
def _loaded() -> Edition:
    edition = _load(os.environ.get(EDITION_ENV_VAR))
    logger.info("Running the %s edition", edition.name)
    return edition


_override: Edition | None = None


def edition() -> Edition:
    """The edition this process runs."""
    return _override if _override is not None else _loaded()


@contextmanager
def use_edition(chosen: Edition) -> Iterator[Edition]:
    """Run a block on another edition (tests pin the public or private one)."""
    global _override
    previous = _override
    _override = chosen
    try:
        yield chosen
    finally:
        _override = previous

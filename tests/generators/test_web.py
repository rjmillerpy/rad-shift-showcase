"""Tests for app/generators/web.py — the "web" platform's seam."""

from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.generators.constants import WEB_SCRAPING_UNAVAILABLE
from app.generators.web import web_scraper
from app.plugins import use_edition


def test_422_when_the_edition_has_no_web_scraper():
    with pytest.raises(HTTPException) as exc:
        web_scraper()
    assert exc.value.status_code == 422
    assert exc.value.detail == WEB_SCRAPING_UNAVAILABLE


def test_returns_the_editions_scraper(test_edition):
    scraper = object()
    with use_edition(replace(test_edition, web_scraper=scraper)):
        assert web_scraper() is scraper

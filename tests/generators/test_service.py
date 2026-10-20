"""Tests for app/generators/service.py — scraper orchestration internals.

Endpoint-level behavior is covered in test_views.py; these tests focus on the
service helpers that don't naturally surface through HTTP (validators, the
selector-healing branch, failure accounting). The "web" platform runs on a
stub WebScraper, the edition's seam; the real one is tested with the private edition.
"""

from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.generators import service
from app.generators.constants import WEB_SCRAPING_UNAVAILABLE
from app.generators.items import ScrapedItem
from app.generators.models import GeneratorProfile, GeneratorRun, GeneratorSource
from app.plugins import use_edition

FEED = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Post A</title><description>hello</description><link>https://e.com/a</link></item>
<item><title>Post B</title><description>world</description><link>https://e.com/b</link></item>
</channel></rss>"""


class StubWebScraper:
    """A WebScraper (app/generators/web.py) with canned answers that records calls."""

    def __init__(self, *, items_for=None, healed=None, fetch_error=None):
        self.items_for = items_for or {}
        self.healed = healed
        self.fetch_error = fetch_error
        self.fetched: list[str] = []

    def fetch_page(self, url, *, use_browser, browser_engine):
        self.fetched.append(url)
        if self.fetch_error:
            raise self.fetch_error
        return "<html></html>"

    def extract_items(self, html, selectors):
        return self.items_for.get(selectors["post_container"], [])

    def analyze_page(self, url, content_hint, *, use_browser, browser_engine):
        return {"post_container": "div", "text": "p"}

    def heal_selectors(self, url, old_selectors, content_hint, *, use_browser, browser_engine):
        return self.healed


@pytest.fixture()
def with_web(test_edition):
    """Run the public edition with a stub web scraper; yields a factory."""

    def install(scraper: StubWebScraper) -> StubWebScraper:
        stack.enter_context(use_edition(replace(test_edition, web_scraper=scraper)))
        return scraper

    from contextlib import ExitStack

    with ExitStack() as stack:
        yield install


def _web_source(db_session, selectors=None):
    source = GeneratorSource(name="S", site_url="https://x.com", config={}, selectors=selectors)
    db_session.add(source)
    db_session.commit()
    return source


class TestValidateSelectors:
    @pytest.mark.parametrize(
        "bad_selectors",
        [
            None,
            {},
            {"post_container": ""},
            {"post_container": "div", "text": ""},
            {"post_container": "div", "text": None, "title": None},
        ],
        ids=["none", "empty", "no-container", "no-content-fields", "explicit-nulls"],
    )
    def test_rejects_missing_or_incomplete(self, bad_selectors):
        with pytest.raises(HTTPException) as exc:
            service._validate_selectors(bad_selectors)
        assert exc.value.status_code == 422

    @pytest.mark.parametrize(
        "good_selectors",
        [
            {"post_container": "div", "text": "p"},
            {"post_container": "tr.athing", "title": ".titleline a"},
            {"post_container": "article", "text": ".body", "title": "h2"},
        ],
        ids=["text-only", "title-only", "both"],
    )
    def test_accepts_when_container_plus_one_content_field(self, good_selectors):
        service._validate_selectors(good_selectors)  # must not raise


class TestWebWithoutScraper:
    def test_creating_a_web_source_is_rejected(self, db_session):
        with pytest.raises(HTTPException) as exc:
            service.create_source(name="N", site_url="https://x.com", db=db_session)
        assert exc.value.status_code == 422
        assert exc.value.detail == WEB_SCRAPING_UNAVAILABLE

    def test_running_a_stored_web_source_is_rejected(self, db_session):
        source = _web_source(db_session, {"post_container": "div", "text": "p"})
        with pytest.raises(HTTPException) as exc:
            service.run_scraper(source.id, db_session)
        assert exc.value.detail == WEB_SCRAPING_UNAVAILABLE


class TestRunScraperSelectorGuard:
    def test_missing_selectors_raises_422_before_any_fetch(self, db_session, with_web):
        scraper = with_web(StubWebScraper())
        source = _web_source(db_session, selectors=None)

        with pytest.raises(HTTPException) as exc:
            service.run_scraper(source.id, db_session)

        assert exc.value.status_code == 422
        assert scraper.fetched == []


class TestSelectorHealingBranch:
    def test_healing_replaces_selectors_when_fresh_extract_succeeds(
        self, db_session, create_user, with_web
    ):
        """Bug-fix regression: if heal_selectors returns new selectors that extract items,
        source.selectors should be updated and selectors_updated flag set."""
        healed = {"post_container": "article", "text": "p"}
        item = ScrapedItem(title=None, text="fresh", image_url=None, link=None, popularity=0)
        with_web(StubWebScraper(items_for={"article": [item]}, healed=healed))
        source = _web_source(db_session, {"post_container": "div.will-not-match", "text": "p"})
        bot = create_user(username="healbot")
        db_session.add(GeneratorProfile(source_id=source.id, user_id=bot.id))
        run = GeneratorRun(source_id=source.id, started_at=1, status="running")
        db_session.add(run)
        db_session.commit()

        service._execute_scrape(source, run, db_session)

        assert source.selectors == healed
        assert run.selectors_updated is True

    def test_no_healing_when_scraper_finds_nothing_better(self, db_session, create_user, with_web):
        with_web(StubWebScraper(healed=None))
        source = _web_source(db_session, {"post_container": "div", "text": "p"})
        db_session.add(GeneratorProfile(source_id=source.id, user_id=create_user(username="b").id))
        run = GeneratorRun(source_id=source.id, started_at=1, status="running")
        db_session.add(run)
        db_session.commit()

        service._execute_scrape(source, run, db_session)

        assert run.selectors_updated is False


class TestFailureAccounting:
    def test_connection_error_increments_consecutive_failures(self, db_session, with_web):
        with_web(StubWebScraper(fetch_error=ConnectionError("timeout")))
        source = _web_source(db_session, {"post_container": "div", "text": "p"})

        with pytest.raises(HTTPException) as exc:
            service.run_scraper(source.id, db_session)

        assert exc.value.status_code == 502
        db_session.refresh(source)
        assert source.consecutive_failures == 1
        assert "timeout" in source.last_error


class TestPlatformDispatch:
    """run_scraper should route non-web sources through the platform adapter."""

    def test_unknown_platform_rejected_at_create_time(self, db_session):
        with pytest.raises(HTTPException) as exc:
            service.create_source(
                name="N",
                site_url="https://example.com",
                db=db_session,
                platform="myspace",
                platform_config={},
            )
        assert exc.value.status_code == 422

    def test_invalid_platform_config_rejected_at_create_time(self, db_session):
        with pytest.raises(HTTPException) as exc:
            service.create_source(
                name="N",
                site_url="https://example.com",
                db=db_session,
                platform="rss",
                platform_config={},  # missing feed_url
            )
        assert exc.value.status_code == 422

    def test_run_scraper_with_rss_platform_uses_adapter(self, db_session, create_user):
        """RSS source: real adapter, mocked at the feed's httpx boundary."""
        source = service.create_source(
            name="feed",
            site_url="https://e.com",
            db=db_session,
            platform="rss",
            platform_config={"feed_url": "https://e.com/feed.xml"},
            config={"max_items_per_run": 5},
        )
        bot = create_user(username="rss_bot")
        db_session.add(GeneratorProfile(source_id=source.id, user_id=bot.id))
        db_session.commit()

        response = MagicMock(content=FEED, headers={})
        with patch("app.generators.platforms.feeds.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value.get.return_value = response
            run = service.run_scraper(source.id, db_session)

        assert run.status == "success"
        assert run.items_found == 2
        assert run.items_posted == 2

    def test_run_scraper_with_invalid_platform_config_at_run_time(self, db_session):
        """Source persisted with broken config still validates pre-run."""
        source = GeneratorSource(
            name="bad", site_url="https://e.com", platform="rss", platform_config={}, config={}
        )
        db_session.add(source)
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            service.run_scraper(source.id, db_session)
        assert exc.value.status_code == 422

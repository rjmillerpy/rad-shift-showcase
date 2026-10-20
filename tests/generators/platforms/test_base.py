"""Tests for app/generators/platforms/base.py — adapter lookup and fallbacks."""

from dataclasses import replace

import pytest

from app.generators.platforms.base import (
    PLATFORM_WEB,
    PlatformAdapter,
    PlatformConfigError,
    fetch_with_fallbacks,
    get_adapter,
    has_web_scraper,
    is_platform_supported,
    supported_platforms,
)
from app.plugins import Edition, use_edition


class _StubAdapter(PlatformAdapter):
    platform = "stub_test_platform"

    def validate_config(self, platform_config):
        if "required" not in platform_config:
            raise PlatformConfigError("missing 'required'")

    def fetch_items(self, platform_config, max_items):
        return []


class _StubWebScraper:
    """Stands in for an edition's web scraper; only its presence matters here."""


@pytest.fixture()
def stub_edition(test_edition: Edition):
    """The public edition with one extra adapter and a web scraper."""
    adapters = (*test_edition.platform_adapters, _StubAdapter())
    with use_edition(
        replace(test_edition, platform_adapters=adapters, web_scraper=_StubWebScraper())
    ) as chosen:
        yield chosen


class TestRegistry:
    def test_get_adapter_for_the_editions_platform(self, stub_edition):
        assert isinstance(get_adapter("stub_test_platform"), _StubAdapter)

    def test_public_edition_has_rss(self):
        assert get_adapter("rss").platform == "rss"

    def test_get_adapter_for_unknown_platform_raises(self):
        with pytest.raises(KeyError):
            get_adapter("definitely_not_registered_xyz")

    def test_web_is_not_an_adapter(self, stub_edition):
        with pytest.raises(KeyError):
            get_adapter(PLATFORM_WEB)


class TestFetchWithFallbacks:
    """Endpoint fallback chain used by fragile-platform adapters."""

    def test_returns_first_successful_response(self):
        attempts: list[str] = []

        def fetcher(url: str) -> str:
            attempts.append(url)
            return f"body from {url}"

        result = fetch_with_fallbacks(["https://a", "https://b"], fetcher)
        assert result == "body from https://a"
        assert attempts == ["https://a"]  # short-circuits

    def test_falls_through_to_next_on_connection_error(self):
        attempts: list[str] = []

        def fetcher(url: str) -> str:
            attempts.append(url)
            if url == "https://a":
                raise ConnectionError("first dead")
            return f"body from {url}"

        result = fetch_with_fallbacks(["https://a", "https://b"], fetcher)
        assert result == "body from https://b"
        assert attempts == ["https://a", "https://b"]

    def test_raises_when_all_fail_and_message_lists_every_url(self):
        def fetcher(url: str) -> str:
            raise ConnectionError(f"{url} down")

        with pytest.raises(ConnectionError) as exc:
            fetch_with_fallbacks(["https://a", "https://b"], fetcher)
        assert "https://a" in str(exc.value)
        assert "https://b" in str(exc.value)

    def test_empty_urls_list_raises_value_error(self):
        with pytest.raises(ValueError):
            fetch_with_fallbacks([], lambda u: u)


class TestSupportedPlatforms:
    def test_web_needs_a_web_scraper(self):
        assert not has_web_scraper()
        assert not is_platform_supported(PLATFORM_WEB)

    def test_web_supported_when_the_edition_has_a_scraper(self, stub_edition):
        assert has_web_scraper()
        assert is_platform_supported(PLATFORM_WEB)

    def test_registered_platforms_are_supported(self, stub_edition):
        assert is_platform_supported("stub_test_platform")
        assert is_platform_supported("rss")

    def test_unknown_platform_not_supported(self):
        assert not is_platform_supported("myspace")

    def test_public_edition_lists_only_rss(self):
        assert supported_platforms() == ["rss"]

    def test_web_first_then_adapters_sorted(self, stub_edition):
        assert supported_platforms() == [PLATFORM_WEB, "rss", "stub_test_platform"]

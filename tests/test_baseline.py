"""Tests for app/baseline.py — the public edition runs end to end on its own."""

from app.baseline import EDITION
from app.chronicle.prompt import PlainPrompt
from app.plugins import PUBLIC


def test_is_the_public_edition_with_no_extra_routes():
    assert EDITION.name == PUBLIC
    assert EDITION.routers == ()


def test_generators_offer_rss_and_no_web_scraping():
    assert [adapter.platform for adapter in EDITION.platform_adapters] == ["rss"]
    assert EDITION.web_scraper is None


def test_chronicle_uses_the_plain_prompt_and_amble_the_demo_town():
    assert isinstance(EDITION.chronicle_prompt, PlainPrompt)
    assert EDITION.amble_bindings_path.is_file()


def test_public_app_has_no_admin_console(client):
    assert not any(path.startswith("/admin") for path in client.app.openapi()["paths"])

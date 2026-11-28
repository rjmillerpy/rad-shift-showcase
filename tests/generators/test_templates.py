"""Source templates (app/generators/templates.py) on the public edition, which has RSS only."""

import re

import pytest

from app.auth.models import User
from app.generators.models import GeneratorProfile, GeneratorSource
from app.generators.templates import TEMPLATES

RSS = {
    "name": "BBC World",
    "feed_url": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "topics": "news, World",
}


@pytest.fixture()
def admin_header(create_user, auth_header):
    create_user(username="admin", is_admin=True)
    return auth_header("admin")


def _create(client, headers, template_id, values):
    return client.post(
        f"/generators/templates/{template_id}", json={"values": values}, headers=headers
    )


def test_the_public_edition_offers_only_templates_it_can_run(client, admin_header):
    res = client.get("/generators/templates", headers=admin_header)
    assert res.status_code == 200
    (rss,) = res.json()["templates"]
    assert rss["id"] == "rss_feed"
    assert [f["key"] for f in rss["fields"]] == ["name", "feed_url", "topics"]


def test_a_template_makes_a_working_source_and_its_bot(client, admin_header, db_session):
    res = _create(client, admin_header, "rss_feed", RSS)

    assert res.status_code == 200
    body = res.json()
    assert body["bot_username"] == "bbc_world_bot"
    source = db_session.get(GeneratorSource, body["source"]["id"])
    assert (source.platform, source.platform_config) == ("rss", {"feed_url": RSS["feed_url"]})
    assert source.config["topics"] == ["news", "World"]
    assert source.run_interval_minutes == 60
    bot = db_session.query(User).filter_by(username="bbc_world_bot").one()
    assert (
        db_session.query(GeneratorProfile).filter_by(source_id=source.id, user_id=bot.id).count()
        == 1
    )
    assert bot.email is None and not bot.is_admin


def test_the_bot_cant_be_signed_in_as(client, admin_header):
    _create(client, admin_header, "rss_feed", RSS)
    for guess in ("", "password", "bbc_world_bot"):
        res = client.post("/auth/login", json={"username": "bbc_world_bot", "password": guess})
        assert res.status_code in (401, 422)


def test_a_taken_bot_name_gets_a_number(client, admin_header):
    _create(client, admin_header, "rss_feed", RSS)
    assert _create(client, admin_header, "rss_feed", RSS).json()["bot_username"] == "bbc_world_bot2"


@pytest.mark.parametrize(
    ("values", "detail"),
    [
        ({**RSS, "feed_url": "ftp://example.com/feed"}, "Feed URL: an http(s) link to the feed"),
        ({"feed_url": RSS["feed_url"]}, "Name is required"),
        ({**RSS, "topics": ",".join(f"t{i}" for i in range(11))}, "Topics: comma-separated"),
    ],
)
def test_bad_fields_are_named(client, admin_header, values, detail, db_session):
    res = _create(client, admin_header, "rss_feed", values)
    assert res.status_code == 422
    assert res.json()["detail"].startswith(detail)
    assert db_session.query(GeneratorSource).count() == 0


@pytest.mark.parametrize("template_id", ["nope", "subreddit_hot"])
def test_unknown_or_unavailable_templates_are_404(client, admin_header, template_id):
    assert _create(client, admin_header, template_id, {"subreddit": "python"}).status_code == 404


def test_only_admins_use_templates(client, create_user, auth_header):
    create_user(username="someone")
    headers = auth_header("someone")
    assert client.get("/generators/templates", headers=headers).status_code == 403
    assert _create(client, headers, "rss_feed", RSS).status_code == 403


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda t: t.id)
def test_every_templates_fields_are_well_formed(template):
    for field in template.fields:
        re.compile(field.pattern)
        assert re.fullmatch(field.pattern, field.placeholder), (
            f"{field.key}'s example fails its own check"
        )

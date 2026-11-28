"""The random feed (app/posts/random_feed.py), through GET /posts/random."""

import pytest

from app.generators.models import GeneratorProfile, GeneratorSource
from app.posts.random_feed import MAX_RANDOM_OFFSET


@pytest.fixture()
def feed(client, create_user, create_post, db_session):
    """Four posts by people and two scraped ones (by a generator's bot account)."""
    person = create_user(username="person")
    bot = create_user(username="bot")
    source = GeneratorSource(name="src", site_url="https://example.com", config={})
    db_session.add(source)
    db_session.commit()
    db_session.add(GeneratorProfile(source_id=source.id, user_id=bot.id))
    db_session.commit()
    for i in range(4):
        create_post(person, text=f"person {i}")
    for i in range(2):
        create_post(bot, text=f"scraped {i}")
    create_post(person, text="a draft", is_draft=True)
    create_post(person, text="a reply", is_reply=True)

    def _texts(**params):
        res = client.get("/posts/random", params=params)
        assert res.status_code == 200
        return [post["text"] for post in res.json()["posts"]]

    return _texts


def test_the_pools_take_turns_until_one_runs_out(feed):
    kinds = [text.split()[0] for text in feed(seed=7)]
    assert kinds == ["person", "scraped", "person", "scraped", "person", "person"]


def test_drafts_and_replies_stay_out(feed):
    assert {"a draft", "a reply"}.isdisjoint(feed(seed=7))


def test_the_same_seed_pages_through_one_shuffle(feed):
    whole = feed(seed=42)
    pages = feed(seed=42, limit=4) + feed(seed=42, offset=4, limit=4)
    assert pages == whole


def _rotated_to_start(order, first):
    start = order.index(first)
    return tuple(order[start:] + order[:start])


def test_another_seed_is_another_shuffle(feed):
    """Not one fixed order rotated (what a linear hash of id + seed gives)."""
    people = [[t for t in feed(seed=seed) if t.startswith("person")] for seed in range(10)]
    cycles = {_rotated_to_start(order, "person 0") for order in people}
    assert len(cycles) > 1


def test_offsets_past_the_cap_are_refused(client):
    assert client.get("/posts/random", params={"offset": MAX_RANDOM_OFFSET + 1}).status_code == 422


def test_an_empty_site_is_an_empty_page(client):
    assert client.get("/posts/random").json() == {"posts": [], "has_more": False}

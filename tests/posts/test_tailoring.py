"""Tailored feeds (app/posts/tailoring.py): each algo setting, through the real feed endpoints."""

import time

import pytest

from app.engagement.models import PostTrending

# Every boost off, so a test turns on only the one it's about.
NEUTRAL = {
    "randomness": 0,
    "interest_adaptation": 0,
    "category_diversity": 0,
    "show_followed_boost": False,
}


@pytest.fixture()
def author(create_user):
    return create_user(username="author")


@pytest.fixture()
def reader(create_user, auth_header, db_session):
    """Sets the reader's settings (NEUTRAL plus overrides); returns their auth header."""
    user = create_user(username="reader")

    def _settings(**overrides):
        user.algo_settings = {**NEUTRAL, **overrides}
        db_session.commit()
        return auth_header("reader")

    return _settings


@pytest.fixture()
def posts(author, create_post):
    """Makes posts oldest first, a minute apart, from (text) or (text, user) pairs."""
    now = int(time.time())

    def _make(*specs):
        made = []
        for i, spec in enumerate(specs):
            text, user = spec if isinstance(spec, tuple) else (spec, author)
            made.append(create_post(user, text=text, unix_timestamp=now - 60 * (len(specs) - i)))
        return made

    return _make


def _algo(client, headers, **params):
    res = client.get("/posts/algo", headers=headers, params=params)
    assert res.status_code == 200
    return [post["text"] for post in res.json()["posts"]]


def test_neutral_settings_are_newest_first(client, reader, posts):
    posts("old", "new")
    assert _algo(client, reader()) == ["new", "old"]


def test_a_preferred_topic_lifts_a_post(client, reader, posts):
    posts("older #rust", "newer #golf")
    assert _algo(client, reader(preferred_categories=["Rust"])) == ["older #rust", "newer #golf"]


@pytest.mark.parametrize("path", ["/posts/algo", "/posts/trending", "/posts/random"])
def test_blocked_topics_leave_every_ranked_feed(client, reader, posts, db_session, path):
    for post in posts("#politics again", "#cats"):
        db_session.add(PostTrending(post_id=post.id, score=1.0, updated_at=time.time()))
    db_session.commit()
    headers = reader(blocked_categories=["#Politics"])
    texts = [post["text"] for post in client.get(path, headers=headers).json()["posts"]]
    assert texts == ["#cats"]


def test_following_an_author_lifts_their_posts_when_the_boost_is_on(
    client, reader, posts, create_user, auth_header
):
    friend = create_user(username="friend")
    posts(("from a friend", friend), "from a stranger")
    headers = reader(show_followed_boost=True)
    assert client.post("/follow/friend", headers=headers).status_code == 200
    assert _algo(client, headers) == ["from a friend", "from a stranger"]
    assert _algo(client, reader(show_followed_boost=False)) == ["from a stranger", "from a friend"]


def test_interest_adaptation_lifts_topics_the_reader_reacts_to(client, reader, posts):
    liked, older_chess, newer_golf = posts("#chess opening", "#chess endgame", "#golf swing")
    headers = reader(interest_adaptation=1)
    assert client.post(f"/posts/like/{liked.id}", headers=headers).status_code == 200
    # The liked post itself now has a like, so compare the other two.
    ranked = _algo(client, headers)
    assert ranked.index("#chess endgame") < ranked.index("#golf swing")
    unadapted = _algo(client, reader(interest_adaptation=0))
    assert unadapted.index("#golf swing") < unadapted.index("#chess endgame")


def test_hiding_posts_the_reader_reacted_to(client, reader, posts):
    liked, _other = posts("liked it", "not yet")
    headers = reader(hide_seen_posts=True)
    assert client.post(f"/posts/save/{liked.id}", headers=headers).status_code == 200
    assert _algo(client, headers) == ["not yet"]
    assert sorted(_algo(client, reader(hide_seen_posts=False))) == ["liked it", "not yet"]


def test_randomness_never_repeats_or_skips_a_post_between_pages(client, reader, posts):
    posts(*(f"post {i}" for i in range(9)))
    headers = reader(randomness=1)
    pages = [_algo(client, headers, offset=offset, limit=3) for offset in (0, 3, 6)]
    seen = [text for page in pages for text in page]
    assert sorted(seen) == sorted(f"post {i}" for i in range(9))


def test_category_diversity_spreads_a_pages_topics(client, reader, posts):
    posts("#b oldest", "#a middle", "#a newest")
    assert _algo(client, reader(category_diversity=0)) == ["#a newest", "#a middle", "#b oldest"]
    assert _algo(client, reader(category_diversity=1)) == ["#a newest", "#b oldest", "#a middle"]


def test_signed_out_readers_get_the_untailored_feed(client, posts):
    posts("old #x", "new")
    assert [p["text"] for p in client.get("/posts/algo").json()["posts"]] == ["new", "old #x"]

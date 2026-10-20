"""Tests for Phase 2.3 — moderation filter, freshness bias, follow-boost,
(auto-suggest and the admin API are tested with the private edition)."""

import time

from app.amble.content.bindings import override_bindings
from app.amble.content.schema import (
    EntityConfig,
)
from app.auth.models import followers


def _cfg(entity_id: str, **overrides) -> EntityConfig:
    payload = {
        "entity_id": entity_id,
        "binding": {"kind": "persistent-identity", "usernames": ["author"]},
    }
    payload.update(overrides)
    return EntityConfig.model_validate(payload)


# ── 2.3a — Banned authors excluded from feed ────────────────────────────────


def test_banned_author_posts_are_excluded_from_amble_feed(
    client,
    create_user,
    create_post,
    auth_header,
    db_session,
) -> None:
    override_bindings({"cafe": _cfg("cafe")})
    reader = create_user(username="reader_ban")  # noqa: F841 (kept for symmetry)
    author = create_user(username="author")
    create_post(user=author, text="visible before ban")
    resp1 = client.get("/amble/content/cafe", headers=auth_header("reader_ban"))
    assert resp1.status_code == 200
    assert resp1.json()["empty"] is False

    author.is_banned = True
    db_session.commit()

    resp2 = client.get("/amble/content/cafe", headers=auth_header("reader_ban"))
    assert resp2.status_code == 200
    assert resp2.json()["empty"] is True


# ── 2.3b — Freshness bias re-orders older posts down ────────────────────────


def test_freshness_bias_boosts_recent_posts_over_old_ones(
    client,
    create_user,
    create_post,
    auth_header,
) -> None:
    override_bindings(
        {
            "newsstand": _cfg("newsstand", freshness_bias=0.8),
        }
    )
    author = create_user(username="author")
    create_user(username="reader_fresh")
    now = int(time.time())
    # 90 days old and 1 day old — bias 0.8 should push the old post
    # far down the sort key.
    create_post(user=author, text="ancient", unix_timestamp=now - 60 * 60 * 24 * 90)
    create_post(user=author, text="today", unix_timestamp=now - 60 * 60 * 24)
    resp = client.get("/amble/content/newsstand", headers=auth_header("reader_fresh"))
    assert resp.status_code == 200
    posts = resp.json()["posts"]
    assert posts[0]["text"] == "today"


def test_no_freshness_bias_preserves_pure_recency_order(
    client,
    create_user,
    create_post,
    auth_header,
) -> None:
    override_bindings({"antique-shop": _cfg("antique-shop", freshness_bias=0.0)})
    author = create_user(username="author")
    create_user(username="reader_arch")
    now = int(time.time())
    create_post(user=author, text="old-but-newer", unix_timestamp=now - 60 * 60 * 24 * 30)
    create_post(user=author, text="ancient", unix_timestamp=now - 60 * 60 * 24 * 365)
    resp = client.get("/amble/content/antique-shop", headers=auth_header("reader_arch"))
    posts = resp.json()["posts"]
    assert posts[0]["text"] == "old-but-newer"
    assert posts[1]["text"] == "ancient"


# ── 2.3c — Follow-graph personalisation boosts followed authors ────────────


def test_personalise_by_follow_boosts_followed_author(
    client,
    create_user,
    create_post,
    auth_header,
    db_session,
) -> None:
    override_bindings(
        {
            "cafe": _cfg(
                "cafe",
                binding={"kind": "category", "tags": ["coffee"]},
                personalise_by_follow=True,
            ),
        }
    )
    reader = create_user(username="reader_follow")
    followed = create_user(username="pal")
    other = create_user(username="stranger")
    # Follow "pal" so their post should win.
    db_session.execute(followers.insert().values(follower_id=reader.id, followed_id=followed.id))
    db_session.commit()
    now = int(time.time())
    # Stranger posts more recently, but reader follows pal — follow-boost
    # should win.
    create_post(user=followed, text="from pal #coffee", unix_timestamp=now - 3600)
    create_post(user=other, text="from stranger #coffee", unix_timestamp=now)
    resp = client.get("/amble/content/cafe", headers=auth_header("reader_follow"))
    posts = resp.json()["posts"]
    assert posts[0]["text"].startswith("from pal")


def test_personalise_disabled_by_default(
    client,
    create_user,
    create_post,
    auth_header,
    db_session,
) -> None:
    override_bindings(
        {
            "cafe": _cfg(
                "cafe",
                binding={"kind": "category", "tags": ["coffee"]},
            ),
        }
    )
    reader = create_user(username="reader_nof")
    followed = create_user(username="pal2")
    other = create_user(username="stranger2")
    db_session.execute(followers.insert().values(follower_id=reader.id, followed_id=followed.id))
    db_session.commit()
    now = int(time.time())
    create_post(user=followed, text="from pal2 #coffee", unix_timestamp=now - 3600)
    create_post(user=other, text="from stranger2 #coffee", unix_timestamp=now)
    resp = client.get("/amble/content/cafe", headers=auth_header("reader_nof"))
    # Without follow-boost, pure recency wins → stranger's post first.
    assert resp.json()["posts"][0]["text"].startswith("from stranger2")

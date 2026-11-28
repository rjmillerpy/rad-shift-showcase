"""Content branches (app/posts/branches.py), through /posts/branches and /posts/topics/*."""

import pytest

from app.posts.branches import MAX_FOLLOWED_TOPICS


@pytest.fixture()
def author(create_user):
    return create_user(username="author")


@pytest.fixture()
def reader(create_user, auth_header, db_session):
    """Sets the reader's Bubbles and algo settings; returns their auth header."""
    user = create_user(username="reader")

    def _settings(follows=(), bubble=None, algo=None):
        user.bubble_settings = {"custom_topics": list(follows), **(bubble or {})}
        user.algo_settings = {"randomness": 0, **(algo or {})}
        db_session.commit()
        return auth_header("reader")

    return _settings


@pytest.fixture()
def chess_world(author, create_post):
    """Go shares two posts with chess; poker only one; cooking none."""
    for text in ("#chess #go", "#chess #go", "#chess #poker", "#go alone", "#cooking #baking"):
        create_post(author, text=text)


def _branches(client, headers):
    res = client.get("/posts/branches", headers=headers)
    assert res.status_code == 200
    return res.json()


def test_a_topic_sharing_posts_with_one_you_follow_is_a_branch(client, reader, chess_world):
    body = _branches(client, reader(follows=["Chess"]))
    assert body["branches"] == [{"topic": "go", "via": "chess", "posts": 3}]
    assert sorted(post["text"] for post in body["posts"]) == [
        "#chess #go",
        "#chess #go",
        "#go alone",
    ]


def test_topics_you_react_to_root_branches_too(client, reader, author, create_post):
    liked = create_post(author, text="#cooking dinner")
    for _ in range(2):
        create_post(author, text="#cooking #grilling")
    headers = reader()
    assert client.post(f"/posts/like/{liked.id}", headers=headers).status_code == 200
    assert [b["topic"] for b in _branches(client, headers)["branches"]] == ["grilling"]


def test_a_topic_found_everywhere_ranks_below_one_found_next_to_yours(
    client, reader, author, create_post
):
    for _ in range(3):
        create_post(author, text="#chess #news")
    for _ in range(17):
        create_post(author, text="#news")
    for _ in range(2):
        create_post(author, text="#chess #go")
    # news: 3 shared / √20 posts ≈ 0.67; go: 2 / √2 ≈ 1.41.
    topics = [b["topic"] for b in _branches(client, reader(follows=["chess"]))["branches"]]
    assert topics == ["go", "news"]


def test_blocked_and_hidden_topics_never_branch(client, reader, chess_world, author, create_post):
    for _ in range(2):
        create_post(author, text="#chess #shogi")
    headers = reader(
        follows=["chess"], bubble={"hidden_topics": ["Shogi"]}, algo={"blocked_categories": ["go"]}
    )
    assert _branches(client, headers) == {"branches": [], "posts": [], "has_more": False}


def test_no_roots_no_branches(client, reader, chess_world):
    assert _branches(client, reader())["branches"] == []


def test_following_a_branch_grows_the_tree(client, reader, chess_world, author, create_post):
    for _ in range(2):
        create_post(author, text="#go #baduk")
    headers = reader(follows=["chess"], bubble={"animation_speed": 0.9})

    res = client.post("/posts/topics/follow", json={"topic": "#Go"}, headers=headers)

    assert res.json() == {"topics": ["chess", "go"]}
    assert [b["topic"] for b in _branches(client, headers)["branches"]] == ["baduk"]
    bubble = client.get("/profile/me/bubble-settings", headers=headers).json()
    assert bubble["custom_topics"] == ["chess", "go"]
    assert bubble["animation_speed"] == 0.9  # the rest of the settings kept


def test_unfollowing_a_topic(client, reader):
    headers = reader(follows=["chess", "go"])
    res = client.post("/posts/topics/unfollow", json={"topic": "GO"}, headers=headers)
    assert res.json() == {"topics": ["chess"]}


def test_following_is_capped(client, reader):
    headers = reader(follows=[f"t{i}" for i in range(MAX_FOLLOWED_TOPICS)])
    res = client.post("/posts/topics/follow", json={"topic": "one more"}, headers=headers)
    assert res.status_code == 400


def test_a_topic_that_is_only_a_hash_is_refused(client, reader):
    res = client.post("/posts/topics/follow", json={"topic": "#"}, headers=reader())
    assert res.status_code == 422


@pytest.mark.parametrize("path", ["/posts/topics/follow", "/posts/topics/unfollow"])
def test_signed_out_readers_cant_follow_topics(client, path):
    assert client.post(path, json={"topic": "x"}).status_code == 401


def test_signed_out_readers_have_no_branches(client):
    assert client.get("/posts/branches").status_code == 401

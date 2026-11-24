"""Engagement flows through Kafka into the trending feed (roadmap item 29b).

The whole path, nothing mocked: the API publishes a post event to Kafka
after the commit, the aggregator container consumes it and updates the
post's score in Postgres, and GET /posts/trending ranks by it.
"""

import time
import uuid

import httpx

TRENDING_TIMEOUT_SECONDS = 30


def trending_texts(api: httpx.Client) -> list[str]:
    response = api.get("/posts/trending", params={"limit": 50})
    response.raise_for_status()
    return [post["text"] for post in response.json()["posts"]]


def test_a_liked_post_shows_up_in_trending(api: httpx.Client, verified_user: dict) -> None:
    headers = {"Authorization": f"Bearer {verified_user['access_token']}"}
    text = f"trending via kafka {uuid.uuid4().hex[:8]}"
    api.post("/posts/add", data={"text": text}, headers=headers).raise_for_status()
    post_id = next(p["id"] for p in api.get("/posts/").json()["posts"] if p["text"] == text)

    api.post(f"/posts/like/{post_id}", headers=headers).raise_for_status()
    api.post(f"/posts/repost/{post_id}", headers=headers).raise_for_status()

    deadline = time.monotonic() + TRENDING_TIMEOUT_SECONDS
    while text not in trending_texts(api):
        assert time.monotonic() < deadline, "the aggregator never scored the post"
        time.sleep(0.5)

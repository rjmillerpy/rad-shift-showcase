"""End-to-end journeys through the real stack: browser → Next.js → FastAPI → Postgres.

Every step here crosses a boundary that the unit tests mock: CORS, the API
URL baked into the frontend bundle, JWT handling in the browser, email
verification, and persistence in a real Postgres.
"""

import re
import uuid

import httpx
from playwright.sync_api import Locator, Page, expect

from e2e.helpers import verification_token_for


def _post_card(page: Page, text: str) -> Locator:
    """The feed card containing `text`: its nearest ancestor with the
    "Show/Hide interactions" toggle (action buttons are collapsed by default)."""
    return page.get_by_text(text, exact=True).locator(
        "xpath=ancestor::div[.//button[contains(., 'interactions')]][1]"
    )


def _open_actions(card: Locator) -> None:
    card.get_by_role("button", name="Show interactions").click()


def _like_count(card: Locator) -> Locator:
    # PostActions renders the count as the <span> right after the Like button.
    return card.locator("xpath=.//button[@title='Like']/following-sibling::span[1]")


def test_signup_verify_login_post_and_like(page: Page, new_user: dict) -> None:
    # ── Sign up through the UI ────────────────────────────────────────────
    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))

    page.goto("/signup")
    page.get_by_placeholder("Username").fill(new_user["username"])
    page.get_by_placeholder("Email").fill(new_user["email"])
    page.get_by_placeholder("Password").fill(new_user["password"])
    page.get_by_role("button", name="Sign Up").click()

    expect(page).to_have_url(re.compile(r"/login$"))
    assert any("Signup successful" in m for m in dialogs), dialogs

    # ── Click the verification link ───────────────────────────────────────
    token = verification_token_for(new_user["username"])
    page.goto(f"/verify?token={token}")
    expect(page.get_by_text("Email verified successfully")).to_be_visible()

    # ── Log in ────────────────────────────────────────────────────────────
    page.get_by_role("link", name="Go to Login").click()
    page.get_by_placeholder("Username").fill(new_user["username"])
    page.get_by_placeholder("Password").fill(new_user["password"])
    page.get_by_role("button", name="Login").click()

    expect(page.get_by_text("Choose your experience")).to_be_visible()
    assert page.evaluate("localStorage.getItem('token')"), "no JWT stored after login"

    # ── Write a post from the classic feed ────────────────────────────────
    text = f"Hello from the e2e suite {uuid.uuid4().hex[:8]}"
    page.goto("/lame")
    page.get_by_role("button", name="New post").click()
    page.get_by_placeholder("Write a post...").fill(text)
    page.get_by_role("button", name="Post", exact=True).click()

    card = _post_card(page, text)
    expect(card).to_be_visible()
    _open_actions(card)
    expect(_like_count(card)).to_have_text("0")

    # ── Like it, and check the like survives a reload (i.e. hit Postgres) ─
    with page.expect_response(
        lambda r: "/posts/like/" in r.url and r.request.method == "POST"
    ) as like_response:
        card.get_by_role("button", name="Like", exact=True).click()
    assert like_response.value.ok

    page.reload()
    card = _post_card(page, text)
    _open_actions(card)
    expect(_like_count(card)).to_have_text("1")


def test_anonymous_visitor_can_read_but_not_post(
    page: Page,
    api: httpx.Client,
    verified_user: dict,
) -> None:
    # Someone else posts (through the API; signup is covered above).
    text = f"Public post {uuid.uuid4().hex[:8]}"
    api.post(
        "/posts/add",
        data={"text": text, "post_metadata": "{}"},
        headers={"Authorization": f"Bearer {verified_user['access_token']}"},
    ).raise_for_status()

    # A visitor with no session sees it in the public feed...
    page.goto("/lame")
    expect(page.get_by_text(text, exact=True)).to_be_visible()
    # ...but gets no way to post.
    expect(page.get_by_role("button", name="New post")).to_have_count(0)

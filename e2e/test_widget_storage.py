"""Widget storage in a real browser (product roadmap Phase 1).

A widget runs in a sandboxed iframe, where the browser refuses localStorage.
radshift.storage (the SDK the API adds) posts to the page, which saves through
the API with the viewer's login. Nothing here is mocked: the iframe, the
postMessage round trip, the API and Postgres are all real.
"""

import uuid

import httpx
from playwright.sync_api import Page, expect

from e2e.helpers import approve_widget

# Counts its own visits for the signed-in viewer.
VISIT_COUNTER = """
<div id="visits">loading</div>
<script>
  radshift.storage.get("visits")
    .then(function (seen) {
      var visits = (seen || 0) + 1;
      return radshift.storage.set("visits", visits).then(function () {
        document.getElementById("visits").textContent = "visit " + visits;
      });
    })
    .catch(function (error) { document.getElementById("visits").textContent = error.message; });
</script>
"""


def test_a_widget_remembers_a_value_across_page_loads(
    page: Page, api: httpx.Client, verified_user: dict
) -> None:
    headers = {"Authorization": f"Bearer {verified_user['access_token']}"}
    title = f"Visit counter {uuid.uuid4().hex[:6]}"
    created = api.post(
        "/widgets",
        json={"title": title, "category": "tool", "language": "html", "code": VISIT_COUNTER},
        headers=headers,
    )
    created.raise_for_status()
    widget_id = created.json()["id"]
    approve_widget(widget_id)

    page.goto("/")
    page.evaluate("token => localStorage.setItem('token', token)", verified_user["access_token"])
    page.goto(f"/widgets/{widget_id}")
    widget = page.frame_locator(f"iframe[title='{title}']")
    expect(widget.locator("#visits")).to_have_text("visit 1")

    page.reload()
    expect(page.frame_locator(f"iframe[title='{title}']").locator("#visits")).to_have_text(
        "visit 2"
    )

    saved = api.get(f"/widgets/{widget_id}/storage", headers=headers).json()
    assert saved == {"items": {"visits": 2}}


def test_a_signed_out_viewer_is_told_to_sign_in(
    page: Page, api: httpx.Client, verified_user: dict
) -> None:
    headers = {"Authorization": f"Bearer {verified_user['access_token']}"}
    title = f"Visit counter {uuid.uuid4().hex[:6]}"
    widget_id = api.post(
        "/widgets",
        json={"title": title, "category": "tool", "language": "html", "code": VISIT_COUNTER},
        headers=headers,
    ).json()["id"]
    approve_widget(widget_id)

    page.goto(f"/widgets/{widget_id}")
    expect(page.frame_locator(f"iframe[title='{title}']").locator("#visits")).to_have_text(
        "Sign in to save widget data"
    )

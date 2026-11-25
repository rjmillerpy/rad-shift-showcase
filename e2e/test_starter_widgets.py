"""The Phase 1 starter widgets in a real browser, in the sandboxed widget iframe.

Each starter's code comes from GET /widgets/templates (the built-in list).
WebGL: the widget reads back a pixel it drew. State: a Redux-style store
saves through radshift.storage, so the count survives a reload.
"""

import uuid

import httpx
from playwright.sync_api import Page, expect

from e2e.helpers import approve_widget


def _widget_from_template(api: httpx.Client, headers: dict, template_name: str) -> tuple[int, str]:
    templates = api.get("/widgets/templates").json()["templates"]
    (template,) = [t for t in templates if t["name"] == template_name]
    title = f"{template_name} {uuid.uuid4().hex[:6]}"
    created = api.post(
        "/widgets",
        json={"title": title, "category": template["category"], "language": template["language"],
              "code": template["starter_code"]},
        headers=headers,
    )  # fmt: skip
    created.raise_for_status()
    widget_id = created.json()["id"]
    approve_widget(widget_id)
    return widget_id, title


def _sign_in(page: Page, token: str) -> None:
    page.goto("/")
    page.evaluate("token => localStorage.setItem('token', token)", token)


def test_webgl_draws_inside_the_sandboxed_iframe(
    page: Page, api: httpx.Client, verified_user: dict
) -> None:
    headers = {"Authorization": f"Bearer {verified_user['access_token']}"}
    widget_id, title = _widget_from_template(api, headers, "WebGL Starter")

    page.goto(f"/widgets/{widget_id}")

    widget = page.frame_locator(f"iframe[title='{title}']")
    expect(widget.locator("body")).to_have_attribute("data-webgl", "drawing")


def test_the_state_store_survives_a_reload(
    page: Page, api: httpx.Client, verified_user: dict
) -> None:
    headers = {"Authorization": f"Bearer {verified_user['access_token']}"}
    widget_id, title = _widget_from_template(api, headers, "State Store (Redux-style)")
    _sign_in(page, verified_user["access_token"])

    page.goto(f"/widgets/{widget_id}")
    widget = page.frame_locator(f"iframe[title='{title}']")
    expect(widget.locator("body")).to_have_attribute("data-ready", "yes")
    widget.get_by_role("button", name="+1").click()
    widget.get_by_role("button", name="+1").click()
    expect(widget.locator("#status")).to_have_text("saved")

    page.reload()
    widget = page.frame_locator(f"iframe[title='{title}']")
    expect(widget.locator("#status")).to_have_text("restored")
    expect(widget.locator("#count")).to_have_text("2")

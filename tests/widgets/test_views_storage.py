"""Widget storage over HTTP, the SDK route, and the SDK in rendered widgets."""

import pytest

from app.widgets.views import WIDGET_SDK_TAG, with_sdk
from tests.widgets._view_helpers import _make_approved_widget


@pytest.fixture()
def widget_id(client, auth_header, create_user, db_session):
    return _make_approved_widget(client, auth_header, create_user, db_session)["id"]


@pytest.fixture()
def fan(create_user, auth_header):
    create_user(username="fan")
    return auth_header("fan")


def test_set_get_list_remove(client, widget_id, fan):
    base = f"/widgets/{widget_id}/storage"

    saved = client.put(f"{base}/best", json={"value": {"score": 9}}, headers=fan)
    got = client.get(f"{base}/best", headers=fan)
    listed = client.get(base, headers=fan)
    removed = client.delete(f"{base}/best", headers=fan)

    assert saved.json() == {"status": "saved", "key": "best"}
    assert got.json() == {"key": "best", "value": {"score": 9}}
    assert listed.json() == {"items": {"best": {"score": 9}}}
    assert removed.json() == {"status": "removed", "key": "best"}
    assert client.get(f"{base}/best", headers=fan).status_code == 404


@pytest.mark.parametrize("key", ["has space", "x" * 65, "slash%2Fkey"])
def test_keys_are_restricted(client, widget_id, fan, key):
    resp = client.put(f"/widgets/{widget_id}/storage/{key}", json={"value": 1}, headers=fan)
    assert resp.status_code in (404, 422)


def test_a_value_is_required(client, widget_id, fan):
    assert client.put(f"/widgets/{widget_id}/storage/k", json={}, headers=fan).status_code == 422


def test_anonymous_has_no_storage(client, widget_id):
    assert client.get(f"/widgets/{widget_id}/storage").status_code == 401


class TestSdk:
    def test_the_sdk_is_served_as_javascript(self, client):
        resp = client.get("/widgets/sdk.js")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/javascript")
        assert "radshift.storage" in resp.text

    def test_a_rendered_widget_loads_the_sdk_before_its_own_code(self, client, widget_id):
        html = client.get(f"/widgets/{widget_id}/render").text
        assert WIDGET_SDK_TAG in html
        assert html.index(WIDGET_SDK_TAG) < html.index("Hello")

    @pytest.mark.parametrize(
        ("html", "expected"),
        [
            ("<html><head><title>t</title></head></html>",
             f"<html><head>{WIDGET_SDK_TAG}<title>t</title></head></html>"),
            ("<div>no head</div>", f"{WIDGET_SDK_TAG}<div>no head</div>"),
        ],
    )  # fmt: skip
    def test_with_sdk_puts_it_first(self, html, expected):
        assert with_sdk(html) == expected

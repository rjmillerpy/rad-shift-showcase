"""API-level tests for app/widgets/views.py: the telemetry endpoint and the
response contracts shared across the widget endpoints.

The per-area endpoint tests live next to this file: test_views_browse.py,
test_views_crud.py, test_views_execute.py, test_views_interactions.py and
test_views_moderation.py.
"""

import pytest

from app.widgets.schema import MAX_TELEMETRY_EVENTS, WidgetOut

from ._view_helpers import _create_widget

TELEMETRY = "/widgets/1/sandbox/telemetry"


@pytest.fixture()
def headers(create_user, auth_header):
    create_user(username="tester")
    return auth_header("tester")


class TestTelemetry:
    def test_requires_auth(self, client):
        assert client.post(TELEMETRY, json={"events": []}).status_code == 401

    def test_analyses_the_submitted_events(self, client, headers):
        events = [
            {"type": "fetch", "url": "https://evil.example/collect"},
            {"type": "websocket", "url": "wss://evil.example/socket"},
        ]

        body = client.post(TELEMETRY, json={"events": events}, headers=headers).json()

        assert body["widget_id"] == 1
        assert body["analysis"]["total_requests"] >= 1
        assert "evil.example" in body["analysis"]["external_domains"]

    def test_events_default_to_empty(self, client, headers):
        resp = client.post(TELEMETRY, json={}, headers=headers)

        assert resp.status_code == 200
        assert resp.json()["analysis"]["total_requests"] == 0

    def test_analysis_has_every_documented_field(self, client, headers):
        analysis = client.post(TELEMETRY, json={"events": []}, headers=headers).json()["analysis"]

        assert set(analysis) == {
            "total_requests",
            "external_domains",
            "suspicious_domains",
            "websocket_connections",
            "service_workers",
            "timer_count",
            "risk_level",
            "risk_reasons",
            "warnings",
        }

    @pytest.mark.parametrize(
        "body",
        [
            {"events": "not-a-list"},
            {"events": ["not-an-object"]},
            {"events": [1, 2]},
            ["a", "list"],
        ],
        ids=["events-is-a-string", "event-is-a-string", "event-is-a-number", "body-is-a-list"],
    )
    def test_malformed_bodies_are_rejected_at_the_boundary(self, client, headers, body):
        """These used to reach the analysis loop and fail there (rule 46)."""
        assert client.post(TELEMETRY, json=body, headers=headers).status_code == 422

    def test_event_count_is_capped(self, client, headers):
        """Rule 11: the analysis loops over every event, so the list is bounded."""
        at_limit = {"events": [{"type": "timer"}] * MAX_TELEMETRY_EVENTS}
        over_limit = {"events": [{"type": "timer"}] * (MAX_TELEMETRY_EVENTS + 1)}

        assert client.post(TELEMETRY, json=at_limit, headers=headers).status_code == 200
        assert client.post(TELEMETRY, json=over_limit, headers=headers).status_code == 422


class TestWidgetShape:
    def test_every_widget_endpoint_returns_the_same_fields(self, client, headers):
        """create, get and list all serialise through WidgetOut, so the
        frontend can treat a widget identically wherever it came from."""
        created = _create_widget(client, lambda _name: headers, "tester")
        fetched = client.get(f"/widgets/{created['id']}", headers=headers).json()["widget"]
        listed = client.get("/widgets/my", headers=headers).json()["widgets"][0]

        expected = set(WidgetOut.model_fields)
        assert set(created) == set(fetched) == set(listed) == expected

    def test_nullable_fields_are_present_as_null_not_missing(self, client, headers):
        created = _create_widget(client, lambda _name: headers, "tester")

        for field in ("html_panel", "compute_panel", "tags", "published_at", "review_notes"):
            assert field in created
            assert created[field] is None


class TestTemplatesAndConfigs:
    def test_templates_share_one_shape(self, client):
        templates = client.get("/widgets/templates").json()["templates"]

        assert templates
        assert len({frozenset(template) for template in templates}) == 1

    def test_sandbox_configs_share_one_shape(self, client):
        configs = client.get("/widgets/sandbox/configs").json()["configs"]

        assert configs
        assert all(set(config) == {"browser", "os", "user_agent"} for config in configs)

"""API endpoint tests for server-side widget execution and sandbox endpoints."""

import pytest

from app.auth.models import User
from app.flags.constants import Flag
from app.widgets.models import Widget
from app.widgets.views import SERVER_EXECUTION_ENV_VAR
from tests.widgets._view_helpers import _make_approved_widget


@pytest.fixture()
def execution_enabled(monkeypatch):
    monkeypatch.setenv(SERVER_EXECUTION_ENV_VAR, "true")


def _promote(db_session, username):
    db_session.query(User).filter(User.username == username).update({"is_admin": True})
    db_session.commit()


class TestExecutionGate:
    """Server execution is not a real sandbox: off by default, admin-only when on."""

    @pytest.mark.parametrize("path", ["/widgets/execute", "/widgets/1/execute"])
    def test_disabled_by_default_even_for_admin(
        self,
        client,
        auth_header,
        create_user,
        monkeypatch,
        path,
    ):
        monkeypatch.delenv(SERVER_EXECUTION_ENV_VAR, raising=False)
        create_user(username="gateadmin", is_admin=True)
        resp = client.post(
            path,
            json={"language": "python", "code": "print(1)"},
            headers=auth_header("gateadmin"),
        )
        assert resp.status_code == 503

    @pytest.mark.parametrize("path", ["/widgets/execute", "/widgets/1/execute"])
    def test_non_admin_forbidden_when_enabled(
        self,
        client,
        auth_header,
        create_user,
        execution_enabled,
        path,
    ):
        create_user(username="gateuser")
        resp = client.post(
            path,
            json={"language": "python", "code": "print(1)"},
            headers=auth_header("gateuser"),
        )
        assert resp.status_code == 403


class TestExecutionKillSwitch:
    """The widget-server-execution flag turns execution off at runtime, never on past the env var."""

    def _execute(self, client, auth_header):
        return client.post(
            "/widgets/execute",
            json={"language": "python", "code": "print(1)"},
            headers=auth_header("switchadmin"),
        )

    def test_flag_off_disables_execution_even_with_the_env_var_on(
        self, client, auth_header, create_user, execution_enabled, set_flags
    ):
        create_user(username="switchadmin", is_admin=True)
        set_flags({Flag.WIDGET_SERVER_EXECUTION: False})
        assert self._execute(client, auth_header).status_code == 503

    def test_flag_on_cannot_override_the_env_var(
        self, client, auth_header, create_user, monkeypatch, set_flags
    ):
        monkeypatch.delenv(SERVER_EXECUTION_ENV_VAR, raising=False)
        create_user(username="switchadmin", is_admin=True)
        set_flags({Flag.WIDGET_SERVER_EXECUTION: True})
        assert self._execute(client, auth_header).status_code == 503

    def test_the_checked_in_flags_leave_execution_to_the_env_var(
        self, client, auth_header, create_user, execution_enabled
    ):
        create_user(username="switchadmin", is_admin=True)
        assert self._execute(client, auth_header).status_code == 200


@pytest.mark.usefixtures("execution_enabled")
class TestServerSideExecuteEndpoint:
    def test_execute_python_requires_auth(self, client):
        resp = client.post("/widgets/execute", json={"language": "python", "code": "print(1)"})
        assert resp.status_code in (401, 422)

    def test_execute_python_runs_code(self, client, auth_header, create_user):
        create_user(username="runner", is_admin=True)
        resp = client.post(
            "/widgets/execute",
            json={"language": "python", "code": "print('hello')"},
            headers=auth_header("runner"),
        )
        assert resp.status_code == 200
        assert "hello" in resp.json()["stdout"]

    def test_execute_sql_runs(self, client, auth_header, create_user):
        create_user(username="sqluser", is_admin=True)
        resp = client.post(
            "/widgets/execute",
            json={"language": "sql", "code": "SELECT 1"},
            headers=auth_header("sqluser"),
        )
        assert resp.status_code == 200

    def test_execute_rejects_unsupported_language(self, client, auth_header, create_user):
        create_user(username="otherlang", is_admin=True)
        resp = client.post(
            "/widgets/execute",
            json={"language": "javascript", "code": "x"},
            headers=auth_header("otherlang"),
        )
        # Pydantic schema rejects unsupported language before the handler (422);
        # the handler's own 400 branch exists as a defensive fallback.
        assert resp.status_code in (400, 422)


@pytest.mark.usefixtures("execution_enabled")
class TestWidgetExecuteEndpoint:
    def test_execute_widget_404_when_missing(self, client, auth_header, create_user):
        create_user(username="u1", is_admin=True)
        resp = client.post(
            "/widgets/99999/execute",
            json={},
            headers=auth_header("u1"),
        )
        assert resp.status_code == 404

    def test_execute_widget_400_when_no_compute_panel(
        self,
        client,
        auth_header,
        create_user,
        db_session,
    ):
        data = _make_approved_widget(client, auth_header, create_user, db_session, username="cw1")
        _promote(db_session, "cw1")
        resp = client.post(
            f"/widgets/{data['id']}/execute",
            json={},
            headers=auth_header("cw1"),
        )
        assert resp.status_code == 400
        assert "compute" in resp.json()["detail"].lower()

    def test_execute_widget_400_when_not_server_mode(
        self,
        client,
        auth_header,
        create_user,
        db_session,
    ):
        data = _make_approved_widget(client, auth_header, create_user, db_session, username="cw2")
        _promote(db_session, "cw2")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.compute_panel = "print('x')"
        w.compute_language = "python"
        # execution_mode stays "client" by default
        db_session.commit()
        resp = client.post(
            f"/widgets/{data['id']}/execute",
            json={},
            headers=auth_header("cw2"),
        )
        assert resp.status_code == 400

    def test_execute_widget_python_compute_runs(
        self,
        client,
        auth_header,
        create_user,
        db_session,
    ):
        data = _make_approved_widget(client, auth_header, create_user, db_session, username="cw3")
        _promote(db_session, "cw3")
        w = db_session.query(Widget).filter(Widget.id == data["id"]).first()
        w.compute_panel = "print('compute-ok')"
        w.compute_language = "python"
        w.execution_mode = "server"
        db_session.commit()
        resp = client.post(
            f"/widgets/{data['id']}/execute",
            json={"input_data": {"x": 1}},
            headers=auth_header("cw3"),
        )
        assert resp.status_code == 200
        assert "compute-ok" in resp.json()["stdout"]


class TestSandboxEndpoints:
    def test_get_sandbox_configs_is_public(self, client):
        resp = client.get("/widgets/sandbox/configs")
        assert resp.status_code == 200
        assert "configs" in resp.json()
        assert isinstance(resp.json()["configs"], list)

    def test_sandbox_render_404_on_missing_widget(self, client):
        resp = client.get("/widgets/99999/sandbox")
        assert resp.status_code == 404

    def test_sandbox_render_serves_quarantined_html(
        self,
        client,
        auth_header,
        create_user,
        db_session,
    ):
        data = _make_approved_widget(client, auth_header, create_user, db_session, username="sb1")
        resp = client.get(f"/widgets/{data['id']}/sandbox")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_submit_telemetry_requires_auth(self, client):
        resp = client.post("/widgets/1/sandbox/telemetry", json={"events": []})
        assert resp.status_code in (401, 422)

    def test_submit_telemetry_returns_analysis(
        self,
        client,
        auth_header,
        create_user,
        db_session,
    ):
        data = _make_approved_widget(client, auth_header, create_user, db_session, username="tel1")
        resp = client.post(
            f"/widgets/{data['id']}/sandbox/telemetry",
            json={"events": [{"type": "network", "url": "https://evil.com"}]},
            headers=auth_header("tel1"),
        )
        assert resp.status_code == 200
        assert "analysis" in resp.json()

import pytest
from pydantic import ValidationError

from app.auth.schema import AuthData, PromoteAdminRequest


class TestAuthData:
    def test_valid_with_email(self):
        data = AuthData(username="alice", password="pass123", email="a@b.com")
        assert data.email == "a@b.com"

    def test_email_optional(self):
        data = AuthData(username="alice", password="pass123")
        assert data.email is None

    def test_username_and_password_required(self):
        with pytest.raises(ValidationError):
            AuthData(username="alice")
        with pytest.raises(ValidationError):
            AuthData(password="pass123")

    def test_fields_stored_correctly(self):
        data = AuthData(username="bob", password="secret", email="bob@test.com")
        assert data.username == "bob"
        assert data.password == "secret"
        assert data.email == "bob@test.com"


class TestPromoteAdminRequest:
    def test_valid_secret(self):
        req = PromoteAdminRequest(secret="the-key")
        assert req.secret == "the-key"

    def test_secret_required(self):
        with pytest.raises(ValidationError):
            PromoteAdminRequest()

    def test_empty_secret_rejected(self):
        with pytest.raises(ValidationError):
            PromoteAdminRequest(secret="")

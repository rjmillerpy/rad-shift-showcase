"""Tests for app/avatar/schema.py."""

import pytest
from pydantic import ValidationError

from app.avatar.schema import AvatarUrlResponse


class TestAvatarUrlResponse:
    def test_shape(self):
        assert AvatarUrlResponse(url="https://cdn/a.png").model_dump() == {
            "url": "https://cdn/a.png"
        }

    def test_url_is_required(self):
        with pytest.raises(ValidationError):
            AvatarUrlResponse()

    def test_immutable(self):
        response = AvatarUrlResponse(url="https://cdn/a.png")
        with pytest.raises(ValidationError):
            response.url = "https://cdn/b.png"

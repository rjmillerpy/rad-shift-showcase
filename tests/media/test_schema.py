"""Tests for app/media/schema.py: the queue message is checked before use."""

import pytest
from pydantic import ValidationError

from app.media.schema import VariantResult

VALID = {
    "bucket": "b",
    "source_key": "posts/a_1_0.jpg",
    "width": 800,
    "variants": {"480": "variants/posts/a_1_0-480.webp"},
}


def test_a_lambda_message_validates():
    assert VariantResult.model_validate(VALID).variants == VALID["variants"]


@pytest.mark.parametrize(
    "change",
    [
        {"bucket": ""},
        {"source_key": ""},
        {"variants": {}},
        {"variants": {"480": 5}},
        {"bucket": None},
        {"width": 0},
        {"width": None},
    ],
    ids=[
        "no-bucket",
        "no-key",
        "no-variants",
        "non-string-variant",
        "null-bucket",
        "zero-width",
        "no-width",
    ],
)
def test_anything_else_is_refused(change):
    with pytest.raises(ValidationError):
        VariantResult.model_validate({**VALID, **change})


def test_it_is_immutable():
    with pytest.raises(ValidationError):
        VariantResult.model_validate(VALID).bucket = "other"  # type: ignore[misc]

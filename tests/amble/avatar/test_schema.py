"""Schema-level validation tests. Parametrized against every attribute the
schema enforces so a loosening or renaming shows up as a red case, not a
silent 500 in production."""

import pytest
from pydantic import ValidationError

from app.amble.avatar.constants import MAX_ATTRIBUTE_LENGTH
from app.amble.avatar.schema import (
    AvatarHalfSchema,
    AvatarResponse,
    AvatarSchema,
    AvatarUpdateRequest,
)

VALID_HALF = {
    "gender": "boy",
    "skin_tone": "warm",
    "hairstyle": "short",
    "clothing": "hoodie",
}


def _half(**overrides: object) -> dict:
    merged = dict(VALID_HALF)
    merged.update(overrides)
    return merged


def test_valid_half_parses_cleanly() -> None:
    parsed = AvatarHalfSchema.model_validate(VALID_HALF)
    assert parsed.gender == "boy"
    assert parsed.hairstyle == "short"


@pytest.mark.parametrize(
    "payload,field",
    [
        pytest.param(_half(gender="other"), "gender", id="unknown-gender"),
        pytest.param(_half(skin_tone=""), "skin_tone", id="empty-skin_tone"),
        pytest.param(_half(hairstyle=""), "hairstyle", id="empty-hairstyle"),
        pytest.param(_half(clothing=""), "clothing", id="empty-clothing"),
        pytest.param(
            _half(skin_tone="x" * (MAX_ATTRIBUTE_LENGTH + 1)), "skin_tone", id="oversized-skin_tone"
        ),
        pytest.param(
            _half(hairstyle="x" * (MAX_ATTRIBUTE_LENGTH + 1)), "hairstyle", id="oversized-hairstyle"
        ),
    ],
)
def test_invalid_half_raises(payload: dict, field: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        AvatarHalfSchema.model_validate(payload)
    assert field in str(excinfo.value)


def test_frozen_half_cannot_be_mutated() -> None:
    half = AvatarHalfSchema.model_validate(VALID_HALF)
    with pytest.raises((ValidationError, TypeError)):
        half.gender = "girl"  # type: ignore[misc]


def test_avatar_requires_both_halves() -> None:
    with pytest.raises(ValidationError):
        AvatarSchema.model_validate({"left": VALID_HALF})


def test_avatar_response_permits_null_avatar_with_exists_false() -> None:
    r = AvatarResponse(avatar=None, exists=False)
    assert r.exists is False
    assert r.avatar is None


def test_avatar_update_request_requires_avatar_key() -> None:
    with pytest.raises(ValidationError):
        AvatarUpdateRequest.model_validate({})

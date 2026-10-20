"""Pydantic request/response schemas for the Amble avatar endpoints.

All models are frozen (``ConfigDict(frozen=True)``) so callers can't mutate them after
construction (rule 59). Field-length limits come from constants.py so the DB,
the API docs, and the tests agree on one set of numbers (rule 16).
"""

from typing import Literal

from pydantic import Field

from app.common.schema import FrozenModel

from .constants import MAX_ATTRIBUTE_LENGTH, MIN_ATTRIBUTE_LENGTH

Gender = Literal["boy", "girl"]


class AvatarHalfSchema(FrozenModel):
    gender: Gender
    skin_tone: str = Field(min_length=MIN_ATTRIBUTE_LENGTH, max_length=MAX_ATTRIBUTE_LENGTH)
    hairstyle: str = Field(min_length=MIN_ATTRIBUTE_LENGTH, max_length=MAX_ATTRIBUTE_LENGTH)
    clothing: str = Field(min_length=MIN_ATTRIBUTE_LENGTH, max_length=MAX_ATTRIBUTE_LENGTH)


class AvatarSchema(FrozenModel):
    left: AvatarHalfSchema
    right: AvatarHalfSchema


class AvatarResponse(FrozenModel):
    avatar: AvatarSchema | None = None
    exists: bool


class AvatarUpdateRequest(FrozenModel):
    avatar: AvatarSchema

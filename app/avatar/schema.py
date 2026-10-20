"""Response schemas for avatar endpoints."""

from app.common.schema import FrozenModel


class AvatarUrlResponse(FrozenModel):
    url: str

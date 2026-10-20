"""Schema building blocks shared by every domain."""

from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Base for response models: immutable after construction (rule 59)."""

    # Frozen instances can't change after validation, so nesting one in
    # another model never needs revalidating ("never" is Pydantic's default;
    # stated so the choice is explicit).
    model_config = ConfigDict(frozen=True, revalidate_instances="never")


class MessageResponse(FrozenModel):
    """An action succeeded and the only thing to report is a sentence."""

    message: str


class StatusResponse(FrozenModel):
    """An action succeeded and the only thing to report is a status word."""

    status: str

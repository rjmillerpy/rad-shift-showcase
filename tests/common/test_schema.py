"""Tests for app/common/schema.py — the shared schema building blocks."""

import pytest
from pydantic import ValidationError

from app.common.schema import FrozenModel, MessageResponse, StatusResponse


class TestFrozenModel:
    def test_subclasses_cannot_be_mutated(self):
        class Example(FrozenModel):
            value: int

        example = Example(value=1)
        with pytest.raises(ValidationError):
            example.value = 2


class TestSharedResponses:
    @pytest.mark.parametrize(
        ("model", "field"),
        [(MessageResponse, "message"), (StatusResponse, "status")],
        ids=["message", "status"],
    )
    def test_shape_is_one_required_string(self, model, field):
        assert model(**{field: "done"}).model_dump() == {field: "done"}
        with pytest.raises(ValidationError):
            model()

    @pytest.mark.parametrize("model", [MessageResponse, StatusResponse], ids=["message", "status"])
    def test_immutable(self, model):
        field = next(iter(model.model_fields))
        instance = model(**{field: "done"})
        with pytest.raises(ValidationError):
            setattr(instance, field, "changed")

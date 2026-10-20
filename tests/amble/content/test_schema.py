"""Tests for app/amble/content/schema.py."""

import pytest
from pydantic import TypeAdapter, ValidationError

from app.amble.content.schema import (
    AmbleContentResponse,
    AmblePost,
    Binding,
    BlendedBinding,
    CategoryBinding,
    EntityConfig,
    PersistentIdentityBinding,
)

_binding = TypeAdapter(Binding)


class TestBindingUnion:
    @pytest.mark.parametrize(
        ("payload", "expected_type"),
        [
            ({"kind": "persistent-identity", "usernames": ["alice"]}, PersistentIdentityBinding),
            ({"kind": "category", "tags": ["coffee"]}, CategoryBinding),
            (
                {"kind": "blended", "parts": [{"kind": "category", "tags": ["coffee"]}]},
                BlendedBinding,
            ),
        ],
        ids=["persistent-identity", "category", "blended"],
    )
    def test_kind_selects_the_model(self, payload, expected_type):
        assert isinstance(_binding.validate_python(payload), expected_type)

    @pytest.mark.parametrize(
        "payload",
        [
            {"kind": "unknown", "tags": ["x"]},
            {"tags": ["x"]},
            {"kind": "category", "tags": []},
            {"kind": "persistent-identity", "usernames": []},
            {"kind": "blended", "parts": []},
            {"kind": "category", "tags": ["x"], "weight": 1.5},
            {"kind": "category", "tags": ["x"], "weight": -0.1},
            {"kind": "blended", "parts": [{"kind": "blended", "parts": []}]},
        ],
        ids=[
            "unknown-kind",
            "missing-kind",
            "empty-tags",
            "empty-usernames",
            "empty-parts",
            "weight-above-1",
            "weight-below-0",
            "blended-inside-blended",
        ],
    )
    def test_rejects_invalid_bindings(self, payload):
        with pytest.raises(ValidationError):
            _binding.validate_python(payload)

    def test_weight_defaults_to_full(self):
        assert _binding.validate_python({"kind": "category", "tags": ["x"]}).weight == 1.0

    def test_bindings_are_immutable(self):
        binding = CategoryBinding(kind="category", tags=["x"])
        with pytest.raises(ValidationError):
            binding.weight = 0.5


class TestEntityConfig:
    def test_defaults(self):
        config = EntityConfig(entity_id="cafe", binding={"kind": "category", "tags": ["coffee"]})
        assert config.empty_state_text is None
        assert config.freshness_bias == 0.0
        assert config.personalise_by_follow is False

    @pytest.mark.parametrize(
        "overrides",
        [
            {"entity_id": ""},
            {"entity_id": "x" * 65},
            {"freshness_bias": 1.1},
            {"freshness_bias": -1},
        ],
        ids=["empty-id", "id-too-long", "bias-above-1", "bias-below-0"],
    )
    def test_rejects_out_of_range_values(self, overrides):
        fields = {"entity_id": "cafe", "binding": {"kind": "category", "tags": ["coffee"]}}
        with pytest.raises(ValidationError):
            EntityConfig(**{**fields, **overrides})


class TestContentResponse:
    def test_post_counters_default_to_zero_and_flags_to_false(self):
        post = AmblePost(id=1, author="alice", text="hi", unix_timestamp=1)
        assert (post.likes, post.reposts, post.saves) == (0, 0, 0)
        assert (post.liked_by_me, post.reposted_by_me) == (False, False)

    def test_empty_page_shape(self):
        response = AmbleContentResponse(entity_id="cafe", posts=[], empty=True)
        assert response.model_dump() == {
            "entity_id": "cafe",
            "posts": [],
            "next_cursor": None,
            "empty": True,
        }

"""YAML loader + registry tests. Parses a temp file so we don't couple
tests to the shipped `entity-bindings.yaml`."""

from pathlib import Path

import pytest

from app.amble.content.bindings import (
    BindingsLoadError,
    load_bindings_from_path,
)
from app.amble.content.schema import (
    BlendedBinding,
    CategoryBinding,
    PersistentIdentityBinding,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "bindings.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_missing_file_returns_empty_registry(tmp_path: Path) -> None:
    result = load_bindings_from_path(tmp_path / "nope.yaml")
    assert result == {}


def test_persistent_identity_binding_parses(tmp_path: Path) -> None:
    yaml_body = """
entities:
  shopkeeper:
    binding:
      kind: persistent-identity
      usernames: [alice, bob]
      weight: 0.5
"""
    path = _write(tmp_path, yaml_body)
    result = load_bindings_from_path(path)
    assert "shopkeeper" in result
    binding = result["shopkeeper"].binding
    assert isinstance(binding, PersistentIdentityBinding)
    assert binding.usernames == ["alice", "bob"]
    assert binding.weight == 0.5


def test_category_binding_parses(tmp_path: Path) -> None:
    yaml_body = """
entities:
  cafe:
    binding:
      kind: category
      tags: [coffee, morning]
"""
    result = load_bindings_from_path(_write(tmp_path, yaml_body))
    binding = result["cafe"].binding
    assert isinstance(binding, CategoryBinding)
    assert binding.tags == ["coffee", "morning"]


def test_blended_binding_parses_with_mixed_parts(tmp_path: Path) -> None:
    yaml_body = """
entities:
  park:
    binding:
      kind: blended
      parts:
        - kind: persistent-identity
          usernames: [parks_dept]
        - kind: category
          tags: [outdoors]
"""
    result = load_bindings_from_path(_write(tmp_path, yaml_body))
    binding = result["park"].binding
    assert isinstance(binding, BlendedBinding)
    assert len(binding.parts) == 2


def test_malformed_yaml_raises_load_error(tmp_path: Path) -> None:
    yaml_body = "entities: [not a mapping"
    with pytest.raises(BindingsLoadError):
        load_bindings_from_path(_write(tmp_path, yaml_body))


def test_unknown_binding_kind_raises(tmp_path: Path) -> None:
    yaml_body = """
entities:
  bad:
    binding:
      kind: nonsense
"""
    with pytest.raises(BindingsLoadError):
        load_bindings_from_path(_write(tmp_path, yaml_body))

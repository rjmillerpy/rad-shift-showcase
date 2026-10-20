"""Tests for app/avatar/silhouettes.py — animal silhouette shape data integrity."""

import pytest
from PIL import Image, ImageDraw

from app.avatar.constants import AVATAR_SIZE
from app.avatar.generator import _draw_animal
from app.avatar.silhouettes import ANIMAL_COUNT, ANIMALS

VALID_SHAPE_KINDS = {"circle", "ellipse", "polygon"}


class TestAnimalDataset:
    def test_animal_count_matches_list(self):
        assert len(ANIMALS) == ANIMAL_COUNT

    def test_has_thirty_animals(self):
        assert ANIMAL_COUNT == 30

    def test_names_are_unique_and_non_empty(self):
        names = [name for name, _ in ANIMALS]
        assert len(names) == len(set(names))
        assert all(name.strip() for name in names)

    @pytest.mark.parametrize("name,shapes", ANIMALS, ids=[n for n, _ in ANIMALS])
    def test_each_animal_has_at_least_three_shapes(self, name, shapes):
        assert len(shapes) >= 3, f"{name} has too few shapes"


class TestShapeIntegrity:
    @pytest.mark.parametrize("name,shapes", ANIMALS, ids=[n for n, _ in ANIMALS])
    def test_every_shape_uses_a_known_kind(self, name, shapes):
        for shape in shapes:
            kind = shape[0]
            assert kind in VALID_SHAPE_KINDS, f"{name}: unknown shape kind {kind!r}"

    @pytest.mark.parametrize("name,shapes", ANIMALS, ids=[n for n, _ in ANIMALS])
    def test_shape_coordinates_within_unit_box(self, name, shapes):
        for shape in shapes:
            kind = shape[0]
            if kind == "polygon":
                points = shape[1]
                for x, y in points:
                    assert 0 <= x <= 1 and 0 <= y <= 1, f"{name}: polygon point out of range"
            elif kind == "circle":
                _, cx, cy, r = shape
                assert 0 <= cx <= 1 and 0 <= cy <= 1
                assert 0 < r < 1
            elif kind == "ellipse":
                _, cx, cy, rx, ry = shape
                assert 0 <= cx <= 1 and 0 <= cy <= 1
                assert 0 < rx < 1 and 0 < ry < 1


class TestRendering:
    @pytest.mark.parametrize("idx", range(len(ANIMALS)), ids=[a[0] for a in ANIMALS])
    def test_every_animal_renders_without_error(self, idx):
        img = Image.new("RGB", (AVATAR_SIZE, AVATAR_SIZE), (50, 50, 50))
        draw = ImageDraw.Draw(img)
        _draw_animal(draw, idx, AVATAR_SIZE, (255, 255, 255))

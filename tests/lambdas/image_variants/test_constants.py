"""Tests for lambdas/image_variants/constants.py, and its agreement with the
Terraform that deploys it (infra/media-pipeline/variables.tf)."""

import re
from pathlib import Path

from lambdas.image_variants.constants import (
    IMAGE_EXTENSIONS,
    SOURCE_PREFIX,
    VARIANT_PREFIX,
    VARIANT_WIDTHS,
)

STACK = Path(__file__).resolve().parents[3] / "infra" / "media-pipeline"
VARIABLES = STACK / "variables.tf"


def _default(name: str) -> str:
    block = re.search(rf'variable "{name}" \{{(.*?)\n\}}', VARIABLES.read_text(), re.S)
    assert block, name
    default = re.search(r"default\s*=\s*(.+)", block.group(1))
    assert default, name
    return default.group(1).strip()


def test_terraform_triggers_on_the_prefix_the_code_processes():
    assert _default("source_prefix") == f'"{SOURCE_PREFIX}"'


def test_terraform_grants_writes_where_the_code_writes():
    assert _default("variant_prefix") == f'"{VARIANT_PREFIX}"'


def test_every_triggering_suffix_is_an_extension_the_code_handles():
    suffixes = set(re.findall(r'"\.(\w+)"', _default("image_suffixes")))
    assert suffixes == IMAGE_EXTENSIONS


def test_widths_ascend_and_are_web_sized():
    assert list(VARIANT_WIDTHS) == sorted(VARIANT_WIDTHS)
    assert all(200 <= width <= 2560 for width in VARIANT_WIDTHS)

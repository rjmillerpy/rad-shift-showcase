"""Tests for scripts/build_lambda.py (the parts that don't download Pillow)."""

import hashlib
import zipfile

import pytest

from scripts import build_lambda


def test_pillow_comes_from_the_backends_own_pin():
    assert build_lambda.pinned("pillow").startswith("pillow==")
    assert build_lambda.pinned("PILLOW") == build_lambda.pinned("pillow")


def test_an_unpinned_package_is_an_error():
    with pytest.raises(LookupError):
        build_lambda.pinned("left-pad")


def test_the_package_is_copied_at_its_repository_path(tmp_path):
    build_lambda.copy_package(tmp_path)
    assert (tmp_path / "lambdas" / "__init__.py").is_file()
    assert (tmp_path / "lambdas" / "image_variants" / "handler.py").is_file()
    assert not list(tmp_path.rglob("__pycache__"))


def _tree(root):
    (root / "b").mkdir(parents=True)
    (root / "b" / "two.py").write_text("2")
    (root / "one.py").write_text("1")
    (root / "b" / "__pycache__").mkdir()
    (root / "b" / "__pycache__" / "two.cpython-312.pyc").write_bytes(b"cache")


def test_the_zip_is_reproducible(tmp_path):
    """Same input, same bytes: Terraform redeploys only real changes."""
    _tree(tmp_path / "src")
    first, second = tmp_path / "a.zip", tmp_path / "b.zip"
    build_lambda.write_zip(tmp_path / "src", first)
    (tmp_path / "src" / "one.py").touch()  # a newer mtime must not matter
    build_lambda.write_zip(tmp_path / "src", second)
    digest = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (first, second)]
    assert digest[0] == digest[1]


def test_the_zip_is_sorted_dated_and_cache_free(tmp_path):
    _tree(tmp_path / "src")
    build_lambda.write_zip(tmp_path / "src", tmp_path / "out" / "f.zip")
    with zipfile.ZipFile(tmp_path / "out" / "f.zip") as archive:
        entries = archive.infolist()
    assert [e.filename for e in entries] == ["b/two.py", "one.py"]
    assert {e.date_time for e in entries} == {build_lambda.FIXED_DATE}
